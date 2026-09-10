// Web Worker: runs the Python backend in Pyodide.
//   role "main"  — answers the client's requests (games, decks, reports)
//   role "jobs"  — runs lab jobs; when a pool is attached it farms games out to
//   role "game"  — workers that each play chunks of games and write results to shared memory
let pyodide = null, bridge = null, runner = null, role = "main";

// Shared-memory pool layout (Int32 words): [0] done count, [1] byte allocator, [2] error flag,
// [3] number of chunks; from word TABLE0: (offset, length) per chunk; data follows the table.
const CTRL_DONE = 0, CTRL_ALLOC = 1, CTRL_ERROR = 2, CTRL_N = 3, TABLE0 = 8, MAX_CHUNKS = 4096;
const DATA0 = (TABLE0 + 2 * MAX_CHUNKS) * 4;
let sab = null, ctrl = null, bytes = null, ports = [];

async function init(msg) {
  role = msg.role;
  importScripts(msg.pyodideUrl + "pyodide.js");
  pyodide = await loadPyodide({ indexURL: msg.pyodideUrl });
  const zip = await (await fetch(msg.base + "cptcg.zip" + (msg.v || ""))).arrayBuffer();
  pyodide.FS.mkdirTree("/cptcg/src");
  pyodide.unpackArchive(zip, "zip", { extractDir: "/cptcg/src" });
  for (const [path, text] of Object.entries(msg.files || {})) {
    const full = "/cptcg/" + path;
    pyodide.FS.mkdirTree(full.slice(0, full.lastIndexOf("/")));
    pyodide.FS.writeFile(full, text);
  }
  pyodide.globals.set("js_progress", (s) => self.postMessage({ type: "progress", job: JSON.parse(s) }));
  pyodide.globals.set("js_pool_run", poolRun);
  await pyodide.runPythonAsync(`
import sys, json
sys.path.insert(0, "/cptcg/src")
from cptcg.web import bridge
bridge.setup("/cptcg", json.loads(${JSON.stringify(JSON.stringify(msg.imageIds || []))}), progress=js_progress)
`);
  bridge = pyodide.pyimport("cptcg.web.bridge");
  runner = pyodide.pyimport("cptcg.sim.runner");
  if (role === "game") runner.load_registry();
  self.postMessage({ type: "ready", role });
}

// ---- jobs role: attach a pool of game workers, and the executor Python calls
function attachPool(msg) {
  sab = msg.sab; ctrl = new Int32Array(sab); bytes = new Uint8Array(sab); ports = msg.ports;
  pyodide.runPython("from cptcg.web import bridge; bridge.use_pool(js_pool_run, " + ports.length + ")");
}
function poolRun(jobsJson) {
  const jobs = JSON.parse(jobsJson);
  if (jobs.length > MAX_CHUNKS) throw new Error("too many chunks for the pool");
  Atomics.store(ctrl, CTRL_DONE, 0); Atomics.store(ctrl, CTRL_ALLOC, DATA0); Atomics.store(ctrl, CTRL_ERROR, 0); Atomics.store(ctrl, CTRL_N, jobs.length);
  jobs.forEach((job, i) => ports[i % ports.length].postMessage({ chunk: i, job: JSON.stringify(job) }));
  for (;;) {
    const done = Atomics.load(ctrl, CTRL_DONE);
    if (done >= jobs.length) break;
    Atomics.wait(ctrl, CTRL_DONE, done, 30000);
    if (Atomics.load(ctrl, CTRL_ERROR)) break;
  }
  if (Atomics.load(ctrl, CTRL_ERROR)) throw new Error("a game worker failed: " + readError());
  const dec = new TextDecoder(); const out = [];
  for (let i = 0; i < jobs.length; i++) {
    const off = Atomics.load(ctrl, TABLE0 + 2 * i), len = Atomics.load(ctrl, TABLE0 + 2 * i + 1);
    out.push(dec.decode(bytes.slice(off, off + len)));   // slice: TextDecoder refuses shared memory
  }
  return "[" + out.join(",") + "]";
}
function readError() { const off = Atomics.load(ctrl, TABLE0), len = Atomics.load(ctrl, TABLE0 + 1); return new TextDecoder().decode(bytes.slice(off, off + len)); }

// ---- game role: play a chunk, publish the results into shared memory
function gamePort(port) {
  port.onmessage = (e) => {
    const { chunk, job } = e.data;
    let payload, failed = false;
    try { payload = new TextEncoder().encode(runner.run_chunk_json(job)); }
    catch (err) { payload = new TextEncoder().encode(String(err).split("\n").slice(-2).join(" ")); failed = true; }
    const off = Atomics.add(ctrl, CTRL_ALLOC, (payload.length + 7) & ~7);
    if (off + payload.length > bytes.length) { failed = true; }
    else bytes.set(payload, off);
    Atomics.store(ctrl, TABLE0 + 2 * chunk, off); Atomics.store(ctrl, TABLE0 + 2 * chunk + 1, payload.length);
    if (failed) { Atomics.store(ctrl, TABLE0, off); Atomics.store(ctrl, TABLE0 + 1, payload.length); Atomics.store(ctrl, CTRL_ERROR, 1); }
    Atomics.add(ctrl, CTRL_DONE, 1); Atomics.notify(ctrl, CTRL_DONE);
  };
}

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === "init") return await init(m);
    if (m.type === "pool") return attachPool(m);
    if (m.type === "port") { sab = m.sab; ctrl = new Int32Array(sab); bytes = new Uint8Array(sab); gamePort(m.port); return; }
    if (m.type === "api") {
      const r = JSON.parse(bridge.handle(m.method, m.path, JSON.stringify(m.query || {}), JSON.stringify(m.body || {})));
      return self.postMessage({ id: m.id, status: r.status, body: r.body });
    }
    if (m.type === "write") { bridge.write_file(m.path, m.text); return self.postMessage({ id: m.id, ok: true }); }
    if (m.type === "read") return self.postMessage({ id: m.id, text: bridge.read_file(m.path) });
    if (m.type === "list") return self.postMessage({ id: m.id, files: JSON.parse(bridge.list_files(m.prefix)) });
  } catch (err) {
    const error = String(err).split("\n").filter(Boolean).slice(-3).join(" ");
    if (m.type === "init") self.postMessage({ type: "error", error });
    else self.postMessage({ id: m.id, status: 500, body: { error } });
  }
};
