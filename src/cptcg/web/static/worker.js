// Web Worker: runs the Python backend in Pyodide.
//   role "main"  — answers the client's requests (games, decks, reports)
//   role "jobs"  — runs lab jobs; when a pool is attached it farms games out to
//   role "game"  — workers that each play chunks of games and write results to shared memory
let pyodide = null, bridge = null, runner = null, role = "main";

// Shared-memory pool layout (Int32 words): [0] done count, [1] byte allocator, [2] error flag,
// [3] number of chunks, [4] next chunk to claim; from word TABLE0: (offset, length) of each chunk's
// result; from INTABLE0: (offset, length) of each chunk's job; data follows the tables.
// Chunks are a work queue: every game worker keeps claiming the next unplayed chunk until none are
// left, so a run ends when the last chunk does, not when the unluckiest worker finishes its share.
const CTRL_DONE = 0, CTRL_ALLOC = 1, CTRL_ERROR = 2, CTRL_N = 3, CTRL_NEXT = 4, TABLE0 = 8, MAX_CHUNKS = 4096;
const INTABLE0 = TABLE0 + 2 * MAX_CHUNKS;
const DATA0 = (INTABLE0 + 2 * MAX_CHUNKS) * 4;
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
  Atomics.store(ctrl, CTRL_DONE, 0); Atomics.store(ctrl, CTRL_ALLOC, DATA0); Atomics.store(ctrl, CTRL_ERROR, 0);
  Atomics.store(ctrl, CTRL_N, jobs.length); Atomics.store(ctrl, CTRL_NEXT, 0);
  const enc = new TextEncoder();
  jobs.forEach((job, i) => {
    const buf = enc.encode(JSON.stringify(job));
    const off = Atomics.add(ctrl, CTRL_ALLOC, (buf.length + 7) & ~7);
    if (off + buf.length > bytes.length) throw new Error("pool buffer too small for the jobs");
    bytes.set(buf, off);
    Atomics.store(ctrl, INTABLE0 + 2 * i, off); Atomics.store(ctrl, INTABLE0 + 2 * i + 1, buf.length);
  });
  ports.forEach((port) => port.postMessage({ type: "run", n: jobs.length }));
  // Every chunk is always claimed and completed (a failed run skips the work but still counts), so
  // when done reaches n no worker is still writing into the buffer and the next run can reuse it.
  for (;;) {
    const done = Atomics.load(ctrl, CTRL_DONE);
    if (done >= jobs.length) break;
    Atomics.wait(ctrl, CTRL_DONE, done, 30000);
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

// ---- game role: claim chunks off the shared queue, publish each result into shared memory
function gamePort(port) {
  port.onmessage = (e) => {
    const n = e.data.n, enc = new TextEncoder(), dec = new TextDecoder();
    for (;;) {
      const chunk = Atomics.add(ctrl, CTRL_NEXT, 1);
      if (chunk >= n) break;
      let payload, failed = false;
      if (Atomics.load(ctrl, CTRL_ERROR)) { payload = new Uint8Array(0); }            // run already failed: drain
      else {
        const joff = Atomics.load(ctrl, INTABLE0 + 2 * chunk), jlen = Atomics.load(ctrl, INTABLE0 + 2 * chunk + 1);
        const job = dec.decode(bytes.slice(joff, joff + jlen));                       // slice: TextDecoder refuses shared memory
        try { payload = enc.encode(runner.run_chunk_json(job)); }
        catch (err) { payload = enc.encode(String(err).split("\n").slice(-2).join(" ")); failed = true; }
      }
      const off = Atomics.add(ctrl, CTRL_ALLOC, (payload.length + 7) & ~7);
      if (off + payload.length > bytes.length) { failed = true; }
      else bytes.set(payload, off);
      Atomics.store(ctrl, TABLE0 + 2 * chunk, off); Atomics.store(ctrl, TABLE0 + 2 * chunk + 1, payload.length);
      if (failed) { Atomics.store(ctrl, TABLE0, off); Atomics.store(ctrl, TABLE0 + 1, payload.length); Atomics.store(ctrl, CTRL_ERROR, 1); }
      Atomics.add(ctrl, CTRL_DONE, 1); Atomics.notify(ctrl, CTRL_DONE);
    }
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
