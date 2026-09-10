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
let GAME = null;           // {id, view, log[]}
let LOG = [];

// ---------------------------------------------------------------- cards
function cardNode(c, opts = {}) {
  const d = el("div", "card " + (c.color || ""));
  if (opts.back) { d.className = "card back" + (opts.small ? " sm" : ""); return d; }
  if (opts.small) d.classList.add("sm");
  const def = CARDS[c.id] || {};
  if (def.image) {
    const img = el("img"); img.src = `/images/${c.id}.png`; img.alt = c.name;
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
  $("#report").innerHTML = h;
}

// ---------------------------------------------------------------- cards
function renderCardGrid(q) {
  const grid = $("#cardGrid"); grid.innerHTML = "";
  const s = (q || "").toLowerCase();
  Object.values(CARDS).filter(c => !s || `${c.name} ${c.subtitle || ""} ${c.text} ${c.tags.join(" ")} ${c.type} ${c.color}`.toLowerCase().includes(s))
    .slice(0, 200).forEach(c => grid.append(cardNode(c)));
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
  document.querySelectorAll("nav button").forEach(b => b.onclick = () => {
    document.querySelectorAll("nav button").forEach(x => x.classList.toggle("active", x === b));
    document.querySelectorAll("main.mode").forEach(m => m.classList.toggle("hidden", m.id !== b.dataset.mode));
  });
}
init().catch(e => alert("init failed: " + e.message));
