// Web Worker: runs the Python backend in Pyodide. One instance answers the client's requests;
// a second one runs lab jobs so a long tournament never blocks a game in progress.
let pyodide = null, bridge = null, role = "main";

async function init(msg) {
  role = msg.role;
  importScripts(msg.pyodideUrl + "pyodide.js");
  pyodide = await loadPyodide({ indexURL: msg.pyodideUrl });
  const zip = await (await fetch(msg.base + "cptcg.zip" + (msg.v || ""))).arrayBuffer();
  pyodide.FS.mkdirTree("/cptcg/src");
  pyodide.unpackArchive(zip, "zip", { extractDir: "/cptcg/src" });
  for (const [path, text] of Object.entries(msg.files)) {
    const full = "/cptcg/" + path;
    pyodide.FS.mkdirTree(full.slice(0, full.lastIndexOf("/")));
    pyodide.FS.writeFile(full, text);
  }
  pyodide.globals.set("js_progress", (s) => self.postMessage({ type: "progress", job: JSON.parse(s) }));
  await pyodide.runPythonAsync(`
import sys, json
sys.path.insert(0, "/cptcg/src")
from cptcg.web import bridge
bridge.setup("/cptcg", json.loads(${JSON.stringify(JSON.stringify(msg.imageIds || []))}), progress=js_progress)
`);
  bridge = pyodide.pyimport("cptcg.web.bridge");
  self.postMessage({ type: "ready", role });
}

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === "init") return await init(m);
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
