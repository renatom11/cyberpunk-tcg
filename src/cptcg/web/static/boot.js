// Static build: replace the HTTP API with the Python backend running in the browser (Pyodide).
// app.js calls window.CPTCG_BRIDGE.api(path, body) exactly as it would call fetch().
(function () {
  const cfg = window.CPTCG_STATIC;
  if (!cfg) return;
  const base = document.baseURI.replace(/[^/]*$/, "");
  const V = cfg.v ? "?v=" + encodeURIComponent(cfg.v) : "";      // cache-buster stamped at build time
  const STORE = "cptcg:files";
  const brand = document.querySelector(".brand");
  if (brand && cfg.v) { const b = document.createElement("span"); b.className = "build"; b.textContent = "v " + cfg.v; brand.append(b); }
  const $ = (s) => document.querySelector(s);

  // ---- loading overlay
  const ov = document.createElement("div"); ov.id = "engineLoading";
  ov.innerHTML = '<div class="box"><div class="t">LOADING THE RULES ENGINE</div><div class="s" id="engineStatus">Downloading Python runtime…</div><div class="bar"><i></i></div><div class="n">About 15 MB the first time; cached afterwards. Everything then runs on this device.</div></div>';
  document.body.append(ov);
  const status = (t) => { const s = $("#engineStatus"); if (s) s.textContent = t; };

  // ---- files written by the user persist in this browser
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(STORE) || "{}"); } catch (e) {}
  const persist = (path, text) => {
    saved[path] = text;
    try {
      let s = JSON.stringify(saved);
      while (s.length > 4_000_000) { delete saved[Object.keys(saved)[0]]; s = JSON.stringify(saved); }   // oldest first
      localStorage.setItem(STORE, s);
    } catch (e) {}
  };

  // ---- workers
  let seq = 0; const pending = {};
  function makeWorker(role, files, imageIds) {
    const w = new Worker(base + "static/worker.js" + V);
    const ready = new Promise((res, rej) => {
      w.onmessage = (e) => {
        const m = e.data;
        if (m.type === "ready") return res(w);
        if (m.type === "error") { status("The engine failed to start: " + m.error); return rej(new Error(m.error)); }
        if (m.type === "progress") { const j = JOBS[m.job.id]; if (j) Object.assign(j, m.job, { status: "running" }); return; }
        const p = pending[m.id]; if (p) { delete pending[m.id]; p(m); }
      };
      w.onerror = (e) => rej(new Error("engine failed to start: " + e.message));
    });
    w.postMessage({ type: "init", role, base, v: V, pyodideUrl: cfg.pyodide, files, imageIds });
    return { w, ready };
  }
  const send = (w, msg) => new Promise((res) => { msg.id = ++seq; pending[msg.id] = res; w.postMessage(msg); });

  let files = {}, manifest = null, main = null, jobs = null;
  const JOBS = {};

  async function boot() {
    manifest = await (await fetch(base + "manifest.json" + V)).json();
    status("Loading cards and decks…");
    const fetches = [["data/cards/wnc.json", "data/cards/wnc.json"], ...manifest.decks.map(p => [p, p]), ...(manifest.replays || []).map(p => [p, p])];
    await Promise.all(fetches.map(async ([path, url]) => { files[path] = await (await fetch(base + url + V)).text(); }));
    Object.assign(files, saved);                       // the user's own decks and reports come back
    status("Starting the engine…");
    main = makeWorker("main", files, manifest.images);
    try { await main.ready; } catch (e) { const bar = ov.querySelector(".bar"); if (bar) bar.remove(); throw e; }
    ov.remove();
  }

  async function jobsWorker() {
    if (jobs) return jobs.ready;
    jobs = makeWorker("jobs", files, manifest.images);
    return jobs.ready;
  }

  async function api(path, body) {
    const [p, qs] = path.split("?");
    const query = Object.fromEntries(new URLSearchParams(qs || ""));
    const method = body ? "POST" : "GET";
    // lab jobs: run in their own engine, stream progress, then copy the results into the main one
    if (p === "/api/jobs" && method === "GET") return Object.values(JOBS).sort((a, b) => b.started - a.started).map(j => ({ ...j, elapsed: Math.round(((j.finished || Date.now()) - j.started) / 100) / 10 }));
    if (p.startsWith("/api/jobs/") && method === "GET") { const j = JOBS[p.split("/")[3]]; if (!j) throw new Error("no such job"); return j; }
    if (p.startsWith("/api/jobs/") && p.endsWith("/cancel") && method === "POST") {
      const j = JOBS[p.split("/")[3]];
      if (j && j.status === "running") {
        if (jobs) { try { (await jobs.ready).terminate(); } catch (e) {} jobs = null; }   // kills the job outright
        j.status = "cancelled"; j.lines.push("cancelled"); j.finished = Date.now();
      }
      return j;
    }
    if (p === "/api/jobs" && method === "POST") {
      const id = Math.random().toString(16).slice(2, 10);
      const job = { id, kind: body.kind, params: { ...body, job_id: id }, status: "running", lines: ["starting the lab engine…"], reports: [], decks: [], error: null, started: Date.now(), finished: null };
      JOBS[id] = job;
      (async () => {
        try {
          const w = await jobsWorker();
          // decks saved since the workers started must exist in the jobs engine too
          for (const [fp, text] of Object.entries(files)) await send(w, { type: "write", path: fp, text });
          const r = await send(w, { type: "api", method: "POST", path: "/api/jobs", body: job.params });
          if (r.status !== 200) throw new Error(r.body.error || "job failed");
          Object.assign(job, r.body);
          // bring the produced files (reports, generated decks) into the main engine and the browser store
          for (const prefix of ["out/lab", "data/decks/generated"]) {
            const { files: produced } = await send(w, { type: "list", prefix });
            for (const fp of produced) {
              if (files[fp] !== undefined) continue;
              const { text } = await send(w, { type: "read", path: fp });
              files[fp] = text; persist(fp, text);
              await send(main.w, { type: "write", path: fp, text });
            }
          }
        } catch (e) { job.status = "failed"; job.error = String(e.message || e); job.lines.push("failed: " + job.error); }
        job.finished = Date.now();
      })();
      return job;
    }
    const r = await send(main.w, { type: "api", method, path: p, query, body: body || {} });
    if (r.status !== 200 && r.status !== 204) throw new Error((r.body && r.body.error) || `error ${r.status}`);
    if (p === "/api/decks" && method === "POST" && r.body && r.body.path) {        // saved a deck: keep it
      const { text } = await send(main.w, { type: "read", path: r.body.path });
      files[r.body.path] = text; persist(r.body.path, text);
    }
    return r.body;
  }

  window.CPTCG_BRIDGE = { ready: boot(), api, download(name, obj) {
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(obj)], { type: "application/json" })); a.download = name; a.click();
  } };
})();
