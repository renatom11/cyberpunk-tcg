/* cptcg web client. No game logic here: render the view JSON, post back an option index. */
const $ = (s, el = document) => el.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const api = async (path, body) => {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json();
  if (j.error) throw new Error(j.error);
  return j;
};

let CARDS = {};            // id -> card def (+ image flag)
let HAS_BACK = true;       // data/images/_back.jpg exists (cleared on first failed load)
let GAME = null;           // {id, view, log[]}
let LOG = [];

// ---------------------------------------------------------------- cards
function cardNode(c, opts = {}) {
  const d = el("div", "card " + (c.color || ""));
  if (opts.back) {
    d.className = "card back" + (opts.small ? " sm" : "");
    if (HAS_BACK) { const img = el("img"); img.src = "/images/_back.jpg"; img.alt = "card back"; img.onerror = () => { HAS_BACK = false; img.remove(); }; d.append(img); }
    return d;
  }
  if (opts.small) d.classList.add("sm");
  const def = CARDS[c.id] || {};
  if (def.image) {
    const img = el("img"); img.src = `/images/${c.id}.jpg`; img.alt = c.name;
    img.onerror = () => { img.remove(); d.append(...textFace(c)); };
    d.append(img);
  } else {
    d.append(...textFace(c));
  }
  if (c.spent) d.classList.add("spent");
  if (c.lag) d.classList.add("lag");
  if (c.power_now != null && c.type !== "Program") {
    const pn = el("div", "pnow", `⚔ ${c.power_now}`); d.append(pn);
  }
  if (c.gear && c.gear.length) {
    const g = el("div", "gearlist"); c.gear.forEach(x => g.append(el("span", "", x.name))); d.append(g);
  }
  d.title = `${c.name}${c.subtitle ? " — " + c.subtitle : ""}\n${c.type} · cost ${c.cost ?? "—"} · power ${c.power ?? "—"}\n${c.text || ""}`;
  return d;
}
function textFace(c) {
  const nodes = [];
  const hd = el("div", "hd"); hd.append(el("span", "cost", c.cost == null ? "—" : c.cost), el("span", "type", (c.type || "").toUpperCase())); nodes.push(hd);
  nodes.push(el("div", "nm", c.name || "?"));
  if (c.subtitle) nodes.push(el("div", "sub", c.subtitle));
  if (c.tags && c.tags.length) nodes.push(el("div", "tags", c.tags.join(" · ")));
  nodes.push(el("div", "txt", (c.text || "").replace(/\n/g, "<br>")));
  if (c.power != null && c.type !== "Program") nodes.push(el("div", "pw", c.power));
  if (c.sell_tag) nodes.push(el("div", "sell", "€$"));
  return nodes;
}

// ---------------------------------------------------------------- board
function renderBoard(root, v, { interactive, onAct } = {}) {
  root.innerHTML = "";
  const me = v.perspective == null ? 0 : v.perspective;   // bottom seat
  const opp = 1 - me;
  const P = v.players;
  const pend = v.pending;
  const myTurn = interactive && pend && pend.player === me;
  const byInst = {};          // inst -> [options]
  if (myTurn) pend.options.forEach(o => { if (o.inst != null && o.kind !== "Die") (byInst[o.inst] = byInst[o.inst] || []).push(o); });
  const targets = new Set(myTurn ? pend.options.filter(o => o.kind === "Target").map(o => o.inst) : []);
  const atk = v.atk;

  const decorate = (node, inst) => {
    if (!myTurn) return;
    const opts = byInst[inst];
    if (targets.has(inst)) { node.classList.add("target"); }
    else if (opts && opts.length) { node.classList.add("can"); }
    if ((opts && opts.length) || targets.has(inst)) {
      node.onclick = (e) => {
        const all = (byInst[inst] || []).concat(pend.options.filter(o => o.kind === "Target" && o.inst === inst));
        if (all.length === 1) onAct(all[0].index);
        else showPopover(e, all, onAct);
      };
    }
    if (atk && atk.attacker === inst) node.classList.add("attacking");
  };

  // ----- left column
  const left = el("div", "col");
  const oppHand = el("div", "panel hand opp"); oppHand.append(el("span", "lbl", `${P[opp].name.toUpperCase()} · HAND ${P[opp].hand_count}`));
  if (P[opp].hand) P[opp].hand.forEach(c => oppHand.append(cardNode(c, { small: true })));
  else for (let i = 0; i < P[opp].hand_count; i++) oppHand.append(cardNode({}, { back: true, small: true }));
  left.append(oppHand, diceTray(P[opp], false), gigPanel(P[opp]));

  const phase = el("div", "panel phase");
  const title = v.over ? "GAME OVER" : (pend ? pend.phase.toUpperCase() : "…");
  const who = v.over ? `${P[v.winner].name} wins (${v.end_reason})` : (pend ? (pend.player === me ? "YOUR DECISION" : `${P[pend.player].name} is deciding`) : "");
  phase.append(el("div", "title", title), el("div", "sub", `Turn ${v.turn}${v.overtime ? " · OVERTIME" : ""} · ${who}`));
  left.append(phase, gigPanel(P[me]), diceTray(P[me], myTurn && pend.kind === "GIG_DIE", pend, onAct));
  const myHand = el("div", "panel hand mine"); myHand.append(el("span", "lbl", `${P[me].name.toUpperCase()} · HAND`));
  if (P[me].hand) P[me].hand.forEach(c => { const n = cardNode(c); decorate(n, c.inst); myHand.append(n); });
  else for (let i = 0; i < P[me].hand_count; i++) myHand.append(cardNode({}, { back: true }));
  left.append(myHand);

  // ----- centre column
  const center = el("div", "col center");
  const legRow = (p, mine) => {
    const row = el("div", "panel legends"); row.append(el("span", "lbl", "LEGENDS"));
    p.legends.forEach(l => {
      let n;
      if (l.faceup || l.known_only) { n = cardNode(l, { small: true }); if (l.faceup) n.classList.add("faceup-legend"); if (l.known_only) n.style.opacity = .7; }
      else { n = cardNode({}, { back: true, small: true }); }
      if (l.spent) n.classList.add("spent");
      if (l.gear && l.gear.length) { const g = el("div", "gearlist"); l.gear.forEach(x => g.append(el("span", "", x.name))); n.append(g); }
      decorate(n, l.inst);
      row.append(n);
    });
    const counts = el("div", "counts");
    counts.append(badge("EDDIES", `${p.eddies.ready}/${p.eddies.total}`), badge("DECK", p.deck), badge("TRASH", p.trash.length));
    row.append(counts);
    return row;
  };
  const fieldRow = (p) => {
    const row = el("div", "panel field"); row.append(el("span", "lbl", `${p.name.toUpperCase()} · FIELD`));
    if (!p.field.length) for (let i = 0; i < 4; i++) row.append(el("div", "slot"));
    p.field.forEach(u => { const n = cardNode(u); decorate(n, u.inst); row.append(n); });
    return row;
  };
  center.append(legRow(P[opp], false), fieldRow(P[opp]), fieldRow(P[me]), legRow(P[me], true));

  // ----- right column
  const right = el("div", "col");
  const controls = el("div", "panel controls");
  if (interactive) {
    const undo = el("button", "", "UNDO"); undo.onclick = () => act("undo");
    const concede = el("button", "", "CONCEDE"); concede.onclick = () => { if (confirm("Concede?")) act("concede"); };
    const leave = el("button", "", "NEW GAME"); leave.onclick = () => { GAME = null; $("#board").classList.add("hidden"); $("#setup").classList.remove("hidden"); };
    const dl = el("button", "", "EXPORT"); dl.onclick = () => window.open(`/api/games/${GAME.id}/replay`);
    controls.append(undo, concede, leave, dl);
  }
  right.append(controls);
  const logp = el("div", "panel logwrap"); logp.append(el("span", "lbl", "LOG"));
  (v.log || LOG).forEach(line => { const p = el("p", line.startsWith("—") ? "turn" : line.startsWith("GAME OVER") ? "end" : "", line); logp.append(p); });
  right.append(logp);
  const prompt = el("div", "panel prompt"); prompt.append(el("span", "lbl", "PROMPT"));
  if (v.over) {
    prompt.append(el("div", "q", `${P[v.winner].name.toUpperCase()} WINS`), el("div", "desc", v.end_reason));
  } else if (pend) {
    prompt.append(el("div", "q", pend.prompt || pend.phase), el("div", "desc", hintFor(pend)));
    if (myTurn) {
      const opts = el("div", "opts");
      const seen = new Set();   // identical labels are identical choices (e.g. three face-down Legends)
      pend.options.forEach(o => {
        if (seen.has(o.label)) return;
        seen.add(o.label);
        const b = el("button", o.kind === "EndTurn" ? "end" : "", o.label);
        b.onclick = () => onAct(o.index);
        opts.append(b);
      });
      prompt.append(opts);
    } else if (interactive) {
      prompt.append(el("div", "waiting", "Waiting for the AI…"));
    } else if (v.next_action) {
      prompt.append(el("div", "waiting", "Next: " + v.next_action));
    }
  }
  right.append(prompt);
  root.append(left, center, right);
  logp.scrollTop = logp.scrollHeight;
}
function hintFor(p) {
  return { MULLIGAN: "Keep your opening hand or shuffle it back and draw 6 new cards (once).",
           ORDER: "You won the roll-off. Going first costs 2 spent Legends on turn 1.",
           GIG_DIE: "Take a die from the fixer area, roll it, add it to your Gig area (d20 always last).",
           MAIN: "Play, sell (once), Call a Legend (once), attack, or end the turn. Click a glowing card or use the buttons.",
           TARGET: "Attack a spent rival Unit (red) or the Gig area.",
           REACTION: "A rival Unit is attacking. Block, play a QUICK card, Call a Legend, or pass.",
           PICK: "Choose an option." }[p.kind] || "";
}
function badge(label, val) { const b = el("div", "badge", `${label}<b>${val}</b>`); return b; }
function gigPanel(p) {
  const g = el("div", "panel gigs"); g.append(el("span", "lbl", "GIG AREA"));
  const list = el("div", "list");
  if (!p.gigs.length) list.append(el("span", "waiting", "No Gigs yet."));
  p.gigs.forEach(([k, v]) => list.append(el("div", "die gig", `${v}<small style="font-size:9px;color:#7f95a3">d${k}</small>`)));
  g.append(list, badge(`${p.gigs.length}/7`, p.cred || "Null"));
  return g;
}
function diceTray(p, pick, pend, onAct) {
  const t = el("div", "panel dice"); t.append(el("span", "lbl", "FIXER"));
  const can = new Set(pick ? pend.options.filter(o => o.kind === "Die").map(o => o.inst) : []);
  [4, 6, 8, 10, 12, 20].forEach(k => {
    const d = el("div", "die" + (p.fixer.includes(k) ? "" : " hidden"), `D${k}`);
    if (can.has(k)) { d.classList.add("pick"); d.onclick = () => onAct(pend.options.find(o => o.kind === "Die" && o.inst === k).index); }
    t.append(d);
  });
  return t;
}
function showPopover(e, opts, onAct) {
  const pop = $("#popover"); pop.innerHTML = "";
  opts.forEach(o => { const b = el("button", "", o.label); b.onclick = () => { pop.classList.add("hidden"); onAct(o.index); }; pop.append(b); });
  const cancel = el("button", "", "cancel"); cancel.onclick = () => pop.classList.add("hidden"); pop.append(cancel);
  pop.style.left = Math.min(e.clientX, window.innerWidth - 260) + "px"; pop.style.top = Math.min(e.clientY, window.innerHeight - 200) + "px";
  pop.classList.remove("hidden");
  e.stopPropagation();
}
document.addEventListener("click", (e) => { if (!e.target.closest("#popover")) $("#popover").classList.add("hidden"); });

// ---------------------------------------------------------------- play
async function act(verbOrIndex) {
  if (!GAME) return;
  const since = LOG.length;
  let v;
  if (verbOrIndex === "undo") { LOG = []; v = await api(`/api/games/${GAME.id}/undo`, { since: 0 }); }
  else if (verbOrIndex === "concede") v = await api(`/api/games/${GAME.id}/concede`, { since });
  else v = await api(`/api/games/${GAME.id}/act`, { index: verbOrIndex, since });
  LOG = LOG.concat(v.log);
  GAME.view = v; v.log = LOG;
  renderBoard($("#board"), v, { interactive: true, onAct: act });
}
async function newGame() {
  const body = { deck_me: $("#deckMe").value, deck_ai: $("#deckAi").value, agent: $("#agent").value, seat: +$("#seat").value };
  if ($("#seed").value) body.seed = +$("#seed").value;
  const r = await api("/api/games", body);
  GAME = { id: r.id, view: r.view };
  LOG = r.view.log.slice();
  $("#setup").classList.add("hidden"); $("#board").classList.remove("hidden");
  renderBoard($("#board"), r.view, { interactive: true, onAct: act });
}

// ---------------------------------------------------------------- watch
let RP = { file: null, step: 0, steps: 0, auto: null };
async function rpGo(step) {
  const r = await api(`/api/replay?file=${encodeURIComponent(RP.file)}&step=${step}`);
  RP.step = r.step; RP.steps = r.steps;
  $("#rpSlider").max = r.steps - 1; $("#rpSlider").value = r.step; $("#rpPos").textContent = `${r.step + 1} / ${r.steps}`;
  $("#rpBoard").classList.remove("hidden");
  renderBoard($("#rpBoard"), r.view, { interactive: false });
}

// ---------------------------------------------------------------- lab
function renderReport(t) {
  const names = t.decks.map(d => d.name);
  const bt = t.bradley_terry, nash = t.nash, order = t.standings;
  let h = `<table class="rep"><tr><th>#</th><th>Deck</th><th>Legends</th><th>BT</th><th>vs field</th><th>Nash</th></tr>`;
  order.forEach((i, r) => { const f = t.field[i]; h += `<tr><td>${r + 1}</td><td>${names[i]}</td><td>${t.decks[i].legends.join(", ")}</td><td>${bt[i].toFixed(2)}</td><td>${f.games ? Math.round(100 * f.wins / f.games) + "%" : "—"} (${f.games})</td><td>${Math.round(100 * nash[i])}%</td></tr>`; });
  h += `</table><h3>Head-to-head (row beats column)</h3><table class="rep"><tr><th></th>${order.map(i => `<th>${names[i].slice(0, 14)}</th>`).join("")}</tr>`;
  const cell = {}; t.cells.forEach(c => { cell[`${c.i},${c.j}`] = c; });
  order.forEach(i => {
    h += `<tr><th>${names[i].slice(0, 14)}</th>`;
    order.forEach(j => {
      if (i === j) { h += "<td>·</td>"; return; }
      const c = cell[`${Math.min(i, j)},${Math.max(i, j)}`];
      if (!c) { h += "<td>—</td>"; return; }
      const w = i < j ? c.wins_i : c.n - c.wins_i;
      const sig = c.q < 0.05 ? "font-weight:800;color:#f4e01f" : "";
      h += `<td style="${sig}">${Math.round(100 * w / c.n)}% <small>(${c.n})</small></td>`;
    });
    h += "</tr>";
  });
  h += "</table>";
  if (t.markdown) h += `<details><summary>Full report (${t.file || ""})</summary><pre class="md">${t.markdown.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]))}</pre></details>`;
  $("#report").innerHTML = h;
}

// ---------------------------------------------------------------- lab jobs
let JOBTIMER = null;
async function openReport(file) {
  const sel = $("#reportFile");
  if (![...sel.options].some(o => o.value === file)) { const o = el("option", "", file); o.value = file; sel.prepend(o); }
  sel.value = file;
  renderReport(await api(`/api/report?file=${encodeURIComponent(file)}`));
}
function renderJobs(jobs) {
  const root = $("#jobs"); root.innerHTML = "";
  if (!jobs.length) { root.append(el("div", "hint", "No jobs yet. Start a tournament or a league above; results land in out/lab/.")); return; }
  jobs.forEach(j => {
    const d = el("div", "job");
    const head = el("div", "head");
    head.append(el("b", "", j.kind.toUpperCase()), el("span", "", j.params.name || j.id), el("span", "dim", `${j.elapsed}s`), el("span", "st " + j.status, j.status));
    d.append(head);
    if (j.decks && j.decks.length) d.append(el("div", "dim", `${j.decks.length} decks saved under ${j.decks[0].split("/").slice(0, -1).join("/")}/ — they are now in the deck lists.`));
    if (j.reports.length) { const r = el("div", "reps"); j.reports.forEach((f, i) => { const a = el("a", "", j.kind === "league" ? `gen ${i + 1}` : "report"); a.onclick = () => openReport(f); r.append(a); }); d.append(r); }
    const pre = el("pre", "", j.lines.slice(-12).join("\n")); d.append(pre);
    root.append(d);
  });
}
async function pollJobs() {
  const jobs = await api("/api/jobs");
  renderJobs(jobs);
  const running = jobs.some(j => j.status === "running");
  if (running && !JOBTIMER) JOBTIMER = setInterval(async () => {
    const js = await api("/api/jobs"); renderJobs(js);
    if (!js.some(j => j.status === "running")) { clearInterval(JOBTIMER); JOBTIMER = null; refreshReports(); refreshDecks(); }
  }, 1500);
}
async function refreshReports() {
  const sel = $("#reportFile"); const cur = sel.value; sel.innerHTML = "";
  (await api("/api/reports")).forEach(f => { const o = el("option", "", f); o.value = f; sel.append(o); });
  if (cur) sel.value = cur;
}
function fillDeckChecklist(decks) {
  const tl = $("#tDecks"); const was = new Set([...tl.querySelectorAll("input:checked")].map(c => c.value)); tl.innerHTML = "";
  decks.forEach(d => { const l = el("label"); const c = el("input"); c.type = "checkbox"; c.value = d.path; c.checked = was.size ? was.has(d.path) : d.path.startsWith("data/decks/sample_"); l.append(c, `${d.name} `, el("small", "", `(${d.size}) ${d.legends.map(x => CARDS[x]?.name || x).join(" / ")}`)); tl.append(l); });
}
async function refreshDecks() {
  const decks = (await api("/api/decks")).filter(d => d.ok);
  fillDeckChecklist(decks);
  for (const sel of [$("#deckMe"), $("#deckAi"), $("#bLoad")]) {
    const have = new Set([...sel.options].map(o => o.value));
    decks.forEach(d => { if (!have.has(d.path)) { const o = el("option", "", sel.id === "bLoad" ? `${d.name} (${d.size})` : `${d.name} (${d.size}) — ${d.path}`); o.value = d.path; sel.append(o); } });
  }
}
function strategyChecklist(root, strategies) {
  strategies.filter(s => s.name !== "random").forEach(s => { const l = el("label"); const c = el("input"); c.type = "checkbox"; c.value = s.name; c.checked = s.name !== "legacy"; l.title = s.description; l.append(c, s.name, el("small", "", s.description.split(". ")[0])); root.append(l); });
}
async function initLab(decks, strategies) {
  fillDeckChecklist(decks);
  const gl = $("#gStrategies"); strategyChecklist(gl, strategies);
  $("#gRun").onclick = async () => {
    const picked = [...gl.querySelectorAll("input:checked")].map(c => c.value);
    if (!picked.length) { alert("pick at least one builder personality"); return; }
    try { await api("/api/jobs", { kind: "generate", name: $("#gName").value, strategies: picked, count: +$("#gCount").value, seed: +$("#gSeed").value, screen: +$("#gScreen").value, keep: +$("#gKeep").value }); }
    catch (e) { alert(e.message); return; }
    pollJobs();
  };
  const tl = $("#tDecks");
  const sl = $("#lStrategies"); strategyChecklist(sl, strategies);
  $("#tRun").onclick = async () => {
    const picked = [...tl.querySelectorAll("input:checked")].map(c => c.value);
    if (picked.length < 2) { alert("pick at least two decks"); return; }
    try { await api("/api/jobs", { kind: "tourney", name: $("#tName").value, decks: picked, games: +$("#tGames").value, agent: $("#tAgent").value, seed: +$("#tSeed").value }); }
    catch (e) { alert(e.message); return; }
    pollJobs();
  };
  $("#lRun").onclick = async () => {
    const picked = [...sl.querySelectorAll("input:checked")].map(c => c.value);
    if (!picked.length) { alert("pick at least one builder personality"); return; }
    try { await api("/api/jobs", { kind: "league", name: $("#lName").value, strategies: picked, builders: +$("#lBuilders").value, generations: +$("#lGens").value, steps: +$("#lSteps").value, games: +$("#lGames").value, seed: +$("#lSeed").value, knowledge: $("#lKnowledge").checked, hof: $("#lHof").checked }); }
    catch (e) { alert(e.message); return; }
    pollJobs();
  };
  pollJobs();
}

// ---------------------------------------------------------------- cards
function renderCardGrid(q) {
  const grid = $("#cardGrid"); grid.innerHTML = "";
  const s = (q || "").toLowerCase();
  Object.values(CARDS).filter(c => !s || `${c.name} ${c.subtitle || ""} ${c.text} ${c.tags.join(" ")} ${c.type} ${c.color}`.toLowerCase().includes(s))
    .slice(0, 200).forEach(c => grid.append(cardNode(c)));
}

// ---------------------------------------------------------------- deck builder
// The page holds the deck being edited; legality, RAM limits and the saved file all come from
// the server so the rules live in exactly one place (deck/validate.py).
let B = { name: "New deck", legends: [], main: {}, note: "", v: null, path: null };
const COLORS = ["Red", "Green", "Blue", "Yellow", "Purple", "Grey"];

function bRam() { const r = {}; COLORS.forEach(c => r[c] = 0); B.legends.forEach(id => { const c = CARDS[id]; if (c) r[c.color] += c.ram; }); return r; }
function bLegal(c) { return c.type !== "Legend" && c.ram <= (bRam()[c.color] || 0); }
function bSize() { return Object.values(B.main).reduce((a, n) => a + n, 0); }

async function bRefresh() {
  try { B.v = await api("/api/validate", { name: B.name, legends: B.legends, main: B.main, note: B.note }); }
  catch (e) { B.v = { ok: false, errors: [e.message], warnings: [], ram: bRam() }; }
  renderDeckSheet(); renderLibrary();
}
function bAdd(id) {
  const c = CARDS[id]; if (!c) return;
  if (c.type === "Legend") {
    if (B.legends.includes(id)) B.legends = B.legends.filter(x => x !== id);
    else if (B.legends.length < 3) B.legends.push(id);
    else { B.legends[2] = id; }
    return bRefresh();
  }
  if ((B.main[id] || 0) >= 3) return;
  B.main[id] = (B.main[id] || 0) + 1; bRefresh();
}
function bRemove(id) { if (!B.main[id]) return; B.main[id] -= 1; if (!B.main[id]) delete B.main[id]; bRefresh(); }

function renderLibrary() {
  const grid = $("#bGrid"); grid.innerHTML = "";
  const s = $("#bSearch").value.toLowerCase(), t = $("#bType").value, col = $("#bColor").value, cost = $("#bCost").value, legalOnly = $("#bLegal").checked;
  const list = Object.values(CARDS).filter(c => {
    if (t && c.type !== t) return false;
    if (col && c.color !== col) return false;
    if (cost) { const k = c.cost == null ? -1 : c.cost; if (cost === "6+" ? k < 6 : k !== +cost) return false; }
    if (legalOnly && c.type !== "Legend" && !bLegal(c)) return false;
    if (s && !`${c.name} ${c.subtitle || ""} ${c.text} ${c.tags.join(" ")} ${c.keywords.join(" ")} ${c.type} ${c.color}`.toLowerCase().includes(s)) return false;
    return true;
  }).sort((a, b) => (a.type === "Legend") - (b.type === "Legend") || (a.cost ?? 99) - (b.cost ?? 99) || a.name.localeCompare(b.name));
  $("#bCount").textContent = `${list.length} cards`;
  list.forEach(c => {
    const n = cardNode(c);
    const have = B.main[c.id] || 0;
    if (c.type === "Legend") { if (B.legends.includes(c.id)) n.classList.add("legend-pick"); }
    else { if (!bLegal(c)) n.classList.add("illegal"); if (have >= 3) n.classList.add("maxed"); if (have) n.append(el("span", "have", `×${have}`)); }
    n.title = c.type === "Legend" ? "click to add / remove as a Legend" : "click to add a copy · right-click to remove one";
    n.onclick = () => bAdd(c.id);
    n.oncontextmenu = (e) => { e.preventDefault(); bRemove(c.id); };
    grid.append(n);
  });
}

function renderDeckSheet() {
  $("#bName").value = B.name;
  const slots = $("#bLegends"); slots.innerHTML = "";
  for (let i = 0; i < 3; i++) {
    const id = B.legends[i];
    if (id) { const n = cardNode(CARDS[id], { small: true }); n.title = "click to remove"; n.onclick = () => { B.legends.splice(i, 1); bRefresh(); }; slots.append(n); }
    else slots.append(el("div", "slot"));
  }
  const ram = $("#bRam"); ram.innerHTML = "";
  const limits = B.v ? B.v.ram : bRam();
  COLORS.forEach(c => { if (limits[c]) ram.append(el("span", c, `${c}<b>${limits[c]}</b>`)); });
  if (!ram.children.length) ram.append(el("span", "dim", "pick 3 Legends to unlock RAM"));
  // curve
  const curve = $("#bCurve"); curve.innerHTML = "";
  const buckets = [0, 0, 0, 0, 0, 0, 0];
  Object.entries(B.main).forEach(([id, n]) => { const c = CARDS[id]; if (!c) return; buckets[Math.min(6, c.cost ?? 0)] += n; });
  const mx = Math.max(1, ...buckets);
  buckets.forEach((n, i) => { const d = el("div"); d.style.height = `${Math.round(44 * n / mx)}px`; d.dataset.n = n || ""; d.dataset.c = i === 6 ? "6+" : i; curve.append(d); });
  const size = bSize(); const sz = $("#bSize"); sz.textContent = `${size} / 40–50`; sz.classList.toggle("bad", size < 40 || size > 50);
  // status
  const st = $("#bStatus"); st.innerHTML = "";
  if (B.v) {
    if (B.v.ok) st.append(el("div", "ok", "✔ legal deck"));
    B.v.errors.forEach(e => st.append(el("div", "err", "✖ " + e)));
    B.v.warnings.forEach(w => st.append(el("div", "warn", "· " + w)));
  }
  // list grouped by type
  const list = $("#bList"); list.innerHTML = "";
  const groups = { Unit: [], Program: [], Gear: [] };
  Object.entries(B.main).forEach(([id, n]) => { const c = CARDS[id]; if (c) (groups[c.type] || (groups[c.type] = [])).push([c, n]); });
  Object.entries(groups).forEach(([type, rows]) => {
    if (!rows.length) return;
    rows.sort((a, b) => (a[0].cost ?? 99) - (b[0].cost ?? 99) || a[0].name.localeCompare(b[0].name));
    list.append(el("h4", "", `${type.toUpperCase()}S · ${rows.reduce((a, r) => a + r[1], 0)}`));
    rows.forEach(([c, n]) => {
      const line = el("div", "line" + (bLegal(c) ? "" : " bad"));
      line.append(el("span", "n", `${n}×`), el("span", "", `${c.name}${c.subtitle ? " <small class=dim>— " + c.subtitle + "</small>" : ""}`), el("span", "cost", c.cost ?? "—"));
      const ctl = el("span"); const minus = el("button", "", "−"), plus = el("button", "", "+");
      minus.onclick = () => bRemove(c.id); plus.onclick = () => bAdd(c.id); ctl.append(minus, plus); line.append(ctl);
      list.append(line);
    });
  });
  // text export
  const lines = [`# ${B.name}`, "", "## Legends", ...B.legends.map(id => `- ${CARDS[id]?.name || id}`), "", "## Main deck"];
  Object.entries(groups).forEach(([type, rows]) => { if (rows.length) { lines.push(`### ${type}s`); rows.forEach(([c, n]) => lines.push(`${n} ${c.name}${c.subtitle ? " — " + c.subtitle : ""}`)); } });
  $("#bText").value = lines.join("\n");
}

function bLoadDeck(d) {
  B = { name: d.name, legends: d.legends.slice(), main: { ...d.main }, note: d.note || "", v: d, path: d.path || null };
  renderDeckSheet(); renderLibrary();
}

async function initBuilder(decks) {
  const sel = $("#bLoad");
  decks.forEach(d => { const o = el("option", "", `${d.name} (${d.size})`); o.value = d.path; sel.append(o); });
  sel.onchange = async () => { if (!sel.value) return; bLoadDeck(await api(`/api/deck?path=${encodeURIComponent(sel.value)}`)); };
  ["#bSearch", "#bType", "#bColor", "#bCost", "#bLegal"].forEach(id => { $(id).oninput = renderLibrary; $(id).onchange = renderLibrary; });
  $("#bName").onchange = (e) => { B.name = e.target.value; renderDeckSheet(); };
  $("#bClear").onclick = () => { B = { name: "New deck", legends: [], main: {}, note: "", v: null, path: null }; renderDeckSheet(); renderLibrary(); };
  $("#bExport").onclick = () => { const t = $("#bText"); t.classList.toggle("hidden"); if (!t.classList.contains("hidden")) { t.select(); } };
  $("#bSave").onclick = async () => {
    B.name = $("#bName").value || "untitled";
    const body = { name: B.name, legends: B.legends, main: B.main, note: B.note };
    let r;
    try { r = await api("/api/decks", body); }
    catch (e) {
      if (e.message !== "exists") { alert(e.message); return; }
      if (!confirm(`A deck file with this name already exists. Overwrite it?`)) return;
      try { r = await api("/api/decks", { ...body, overwrite: true }); } catch (e2) { alert(e2.message); return; }
    }
    B.path = r.path; B.v = r; renderDeckSheet();
    if (![...$("#bLoad").options].some(o => o.value === r.path)) { const o = el("option", "", `${r.name} (${r.size})`); o.value = r.path; $("#bLoad").append(o); }
    for (const s of [$("#deckMe"), $("#deckAi")]) if (![...s.options].some(o => o.value === r.path)) { const o = el("option", "", `${r.name} (${r.size}) — ${r.path}`); o.value = r.path; s.append(o); }
    alert(`saved ${r.path}`);
  };
  const strategies = await api("/api/strategies");
  const ssel = $("#bStrategy");
  strategies.forEach(st => { const o = el("option", "", st.name); o.value = st.name; o.title = st.description; ssel.append(o); });
  const showDesc = () => { const st = strategies.find(x => x.name === ssel.value); $("#bStrategyDesc").textContent = st ? st.description : ""; };
  ssel.onchange = showDesc; showDesc();
  $("#bBuild").onclick = async () => {
    const keep = $("#bKeepLegends").checked && B.legends.length === 3;
    try { bLoadDeck(await api("/api/build", { mode: ssel.value, legends: keep ? B.legends : null, name: $("#bName").value })); }
    catch (e) { alert(e.message); }
  };
  renderDeckSheet(); renderLibrary();
}

// ---------------------------------------------------------------- init
async function init() {
  const cards = await api("/api/cards");
  cards.forEach(c => { CARDS[c.id] = c; });
  const decks = await api("/api/decks");
  for (const sel of [$("#deckMe"), $("#deckAi")]) {
    decks.filter(d => d.ok).forEach(d => { const o = el("option", "", `${d.name} (${d.size}) — ${d.path}`); o.value = d.path; sel.append(o); });
  }
  if ($("#deckAi").options.length > 1) $("#deckAi").selectedIndex = 1;
  $("#newGame").onclick = () => newGame().catch(e => alert(e.message));
  const reps = await api("/api/replays");
  reps.forEach(f => { const o = el("option", "", f); o.value = f; $("#replayFile").append(o); });
  $("#loadReplay").onclick = async () => { RP.file = $("#replayFile").value; $("#replayControls").classList.remove("hidden"); await rpGo(0); };
  $("#rpPrev").onclick = () => rpGo(Math.max(0, RP.step - 1));
  $("#rpNext").onclick = () => rpGo(Math.min(RP.steps - 1, RP.step + 1));
  $("#rpStart").onclick = () => rpGo(0);
  $("#rpEnd").onclick = () => rpGo(RP.steps - 1);
  $("#rpSlider").oninput = (e) => rpGo(+e.target.value);
  $("#rpAuto").onclick = () => { if (RP.auto) { clearInterval(RP.auto); RP.auto = null; } else RP.auto = setInterval(() => { if (RP.step < RP.steps - 1) rpGo(RP.step + 1); else { clearInterval(RP.auto); RP.auto = null; } }, 900); };
  const reports = await api("/api/reports");
  reports.forEach(f => { const o = el("option", "", f); o.value = f; $("#reportFile").append(o); });
  $("#loadReport").onclick = async () => renderReport(await api(`/api/report?file=${encodeURIComponent($("#reportFile").value)}`));
  $("#cardSearch").oninput = (e) => renderCardGrid(e.target.value);
  renderCardGrid("");
  await initBuilder(decks);
  await initLab(decks.filter(d => d.ok), await api("/api/strategies"));
  document.querySelectorAll("nav button").forEach(b => b.onclick = () => {
    document.querySelectorAll("nav button").forEach(x => x.classList.toggle("active", x === b));
    document.querySelectorAll("main.mode").forEach(m => m.classList.toggle("hidden", m.id !== b.dataset.mode));
  });
}
init().catch(e => alert("init failed: " + e.message));
