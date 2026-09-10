/* report.js — the LAB report page, drawn entirely from a saved tournament.json as GET /api/report
   serves it. Every sentence about the statistics (the summary, the shape of each deck, the
   glossary) is computed and unit-tested in Python and printed here verbatim; this file lays the
   numbers out, draws the win-rate bars, the head-to-head matrix and the league chart, and gives
   every card its name and picture. Loaded before app.js; app.js calls Report.render(). */

// A deck list grouped Units / Programs / Gear (then anything the card map does not know), each
// group sorted by cost then name. Shared by the BUILD sheet and the report. Returns
// [[type, [[cardDef, count], ...]], ...] with every group present, empty ones included.
function groupDeck(main, cards) {
  const groups = { Unit: [], Program: [], Gear: [], Other: [] };
  Object.entries(main || {}).forEach(([id, n]) => {
    const c = cards[id] || { id, name: id, cost: null, type: "Other", unknown: true };
    (groups[c.type] || groups.Other).push([c, n]);
  });
  Object.values(groups).forEach(rows => rows.sort((a, b) => (a[0].cost ?? 99) - (b[0].cost ?? 99) || String(a[0].name).localeCompare(String(b[0].name))));
  return Object.entries(groups);
}

const Report = (() => {
  // ------------------------------------------------------------ small helpers
  const h = (tag, cls, ...kids) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    kids.forEach(k => { if (k == null || k === false) return; e.append(k.nodeType ? k : document.createTextNode(String(k))); });
    return e;
  };
  const svg = (tag, attrs = {}) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v)); return e; };
  // Python's "{:.0f}" rounds an exact half to the even digit; match it so the numbers here agree
  // with the sentences the summary prints.
  const round0 = (x) => { const f = Math.floor(x), d = x - f; return d > 0.5 ? f + 1 : d < 0.5 ? f : (f % 2 ? f + 1 : f); };
  const pct = (k, n) => n ? `${round0(100 * k / n)}%` : "—";
  const pctOf = (x) => `${round0(100 * x)}%`;
  const fmtSecs = (s) => s == null ? "" : s < 90 ? `${round0(s)} s` : s < 3600 ? `${round0(s / 60)} min` : `${(s / 3600).toFixed(1)} h`;
  const fmtWhen = (iso) => { const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); };
  const num = (n) => Number(n || 0).toLocaleString();
  // Wilson score interval, the same formula as sim/stats.py.
  function wilson(k, n, z = 1.959964) {
    if (!n) return [0, 1];
    const p = k / n, denom = 1 + z * z / n;
    const centre = (p + z * z / (2 * n)) / denom;
    const half = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom;
    return [Math.max(0, centre - half), Math.min(1, centre + half)];
  }
  // How much to trust a matchup: the thresholds of report.sig_word.
  function sigText(q, n) {
    const word = q < 0.01 ? "statistically very solid — unlikely to be luck" : q < 0.05 ? "statistically solid — unlikely to be luck"
      : q < 0.2 ? "suggestive but not settled" : "not established — it could be noise";
    return word + (n < 30 ? ` (only ${n} games)` : "");
  }
  const qText = (q) => q < 1 ? ` (adjusted p-value q = ${q < 0.001 ? "< 0.001" : q.toFixed(3)})` : "";
  const kindOf = (deck) => { const m = (deck && deck.meta) || {}; return m.archetype || m.strategy || null; };
  // What the tables print for a deck's archetype (the same rule as report.deck_label in Python):
  // the kind it was built toward, plus the nearest current archetype for a deck that was not built
  // toward one — hand-built ("nearest: X"), exploring, an old personality label — or whose
  // archetype has since been renamed or merged ("now nearest: X").
  function labelOf(deck) {
    const kind = kindOf(deck), near = deck && deck.nearest;
    if (kind && near) { const m = deck.meta || {}; const stale = !!m.archetype_id && kind !== "exploring"; return `${kind}, ${stale ? "now nearest" : "nearest"}: ${near}`; }
    return kind || (near ? `nearest: ${near}` : null);
  }
  // The win rate a rating predicts against the field: the mean over the other decks of
  // bt_i / (bt_i + bt_j) — the field averages exactly 50% (Tournament.expected_rates).
  function fieldExpected(bt) {
    const n = bt.length;
    if (n < 2) return bt.map(() => 0.5);
    return bt.map((b, i) => bt.reduce((a, o, j) => j === i ? a : a + b / (b + o), 0) / (n - 1));
  }
  // Title attributes never show on a touch screen, so anything a tooltip says is also shown in a
  // note line under the table when the cell is tapped (or clicked).
  function tapNote(section) {
    const note = h("p", "tapnote"); note.hidden = true;
    const fn = (cell, text) => { cell.title = text; cell.classList.add("tap"); cell.onclick = () => { note.textContent = text; note.hidden = false; }; };
    fn.node = note;
    return fn;
  }
  const cardOf = (cards, id) => cards[id] || { id, name: id, cost: null, type: "Other", unknown: true };
  const cardName = (c) => c.name + (c.subtitle ? " — " + c.subtitle : "");
  const statText = (c) => { if (c.unknown) return "unknown card"; const p = [`cost ${c.cost ?? "—"}`]; if (c.power != null && c.type !== "Program") p.push(`power ${c.power}`); return p.join(", "); };
  const shortName = (name) => name.length > 9 ? name.slice(0, 8) + "…" : name;
  const TOUCH = window.matchMedia("(hover: none)").matches || navigator.maxTouchPoints > 0;

  // A chip naming a card: its picture when there is one, hover/tap preview through the host page.
  function cardChip(c, ctx, opts = {}) {
    const chip = h("span", "cardchip" + (opts.img ? " pic" : ""));
    chip.title = `${cardName(c)}\n${statText(c)}${c.text ? "\n" + c.text : ""}`;
    if (opts.img && c.image) {
      const img = h("img"); img.src = `images/${c.id}.jpg`; img.alt = cardName(c); img.loading = "lazy";
      img.onerror = () => img.remove();
      chip.append(img);
    }
    chip.append(h("span", "nm", opts.label != null ? opts.label : cardName(c)));
    if (c.image && ctx.preview) {
      // Hover previews only where hovering exists: a touch screen fires synthetic mouse events
      // around a tap, and a mouseleave right after the tap would close the preview it opened.
      if (!TOUCH) { chip.onmouseenter = () => ctx.preview(c, false); chip.onmouseleave = () => ctx.unpreview && ctx.unpreview(); }
      chip.onclick = (e) => { e.stopPropagation(); ctx.preview(c, true); };
    }
    return chip;
  }
  function kindBadge(kind) {
    if (!kind) return null;
    const b = h("span", "kind", kind);
    b.title = kind.startsWith("exploring") ? "an Explorer deck: the builder invented a shape at random instead of aiming at a learned archetype" +
      (kind.includes("nearest") ? "; the learned archetype its list sits closest to is named in brackets" : "")
      : kind.startsWith("nearest:") ? "this deck was not built toward an archetype; this is the learned archetype its list sits closest to"
      : kind.includes("now nearest") ? "the archetype this deck was built toward has since been renamed or merged; the current archetype its list sits closest to is named in brackets"
      : kind.includes("nearest") ? "an older builder label, with the learned archetype the list sits closest to in brackets"
      : "the learned archetype this deck was built toward";
    if (kind.startsWith("exploring")) b.classList.add("exploring");
    return b;
  }
  function section(title, lede, id) {
    const s = h("section", "rsec"); if (id) s.id = id;
    s.append(h("h3", "", title));
    if (lede) s.append(h("p", "lede", lede));
    return s;
  }
  function scrollX(node) { const w = h("div", "scroll-x"); w.append(node); return w; }

  // ------------------------------------------------------------ the numbers behind the page
  function model(t) {
    const decks = t.decks || [];
    const n = decks.length;
    const bt = (t.bradley_terry || decks.map(() => 1)).map(Number);
    const nash = t.nash || decks.map(() => 0);
    const field = t.field || decks.map(() => ({ wins: 0, games: 0 }));
    const order = (t.standings && t.standings.length === n) ? t.standings.slice() : decks.map((_, i) => i).sort((a, b) => bt[b] - bt[a]);
    const cell = {}; (t.cells || []).forEach(c => { cell[`${c.i},${c.j}`] = c; });
    const rate = (i, j) => {        // [wins of i, games, q] for the pair, whichever way it is stored
      const c = cell[`${Math.min(i, j)},${Math.max(i, j)}`];
      if (!c) return [0, 0, 1];
      return [i < j ? c.wins_i : c.n - c.wins_i, c.n, c.q == null ? 1 : c.q];
    };
    const info = t.info || {};
    const total = info.total_games != null ? info.total_games : (t.cells || []).reduce((a, c) => a + c.n, 0);
    const kinds = decks.map(labelOf);
    const expected = (t.expected && t.expected.length === n) ? t.expected.map(Number) : fieldExpected(bt);
    return { decks, n, bt, expected, nash, field, order, rate, info, total, kinds, showKind: kinds.some(Boolean), names: decks.map(d => d.name) };
  }

  // ------------------------------------------------------------ 1. header
  function header(t, m) {
    const root = h("div", "rhead");
    const title = m.info.title || (t.file ? t.file.replace(/\/tournament\.json$/, "").split("/").slice(-2).join(" / ") : "Tournament");
    root.append(h("h2", "", title));
    const facts = [`${m.n} decks`];
    if (m.info.games_per_pair) facts.push(`up to ${num(m.info.games_per_pair)} games per pair`);
    facts.push(`${num(m.total)} games played`);
    if (t.agent) facts.push(`${t.agent} agents on both sides`);
    if (t.seed != null) facts.push(`seed ${t.seed}`);
    if (m.info.elapsed_s != null) facts.push(`run time ${fmtSecs(m.info.elapsed_s)}`);
    if (m.info.finished_at) facts.push(`finished ${fmtWhen(m.info.finished_at)}`);
    root.append(h("p", "facts", facts.join(" · ")));
    if (m.info.generation) {
      const g = m.info;
      const swaps = (g.climb || []).reduce((a, hist) => a + (hist || []).reduce((b, x) => b + (x.games || 0), 0), 0);
      root.append(h("p", "lede", `Generation ${g.generation}${g.generations ? ` of ${g.generations}` : ""} of a league` +
        `${g.league_seed != null ? ` (seed ${g.league_seed}${g.steps != null ? `, ${g.steps} improvement steps per builder` : ""})` : ""}: ` +
        "each builder improved its deck by measured card swaps, then everyone played a round robin" +
        (swaps ? ` — the ${num(m.total)} games above are the round robin; the card-swap tests played another ${num(swaps)} challenger games (the champion played the same seeds).` : ".")));
    }
    let how = "Every pair of decks played mirrored games: each random seed is played twice with the seats swapped, so going first evens out.";
    // How many games each matchup really played, and why, is computed from the cells in Python
    // (report.how_played) and printed verbatim; a file without it gets only the cap.
    if (t.how_played) how += " " + t.how_played;
    else if (m.info.games_per_pair && !m.info.sprt) how += ` Every matchup played the full ${num(m.info.games_per_pair)} games.`;
    root.append(h("p", "lede", how));
    if (t.file) root.append(h("p", "dim file", t.file));
    return root;
  }

  // ------------------------------------------------------------ 2. summary in words
  function summary(t) {
    const s = section("Summary in words", "What this run says, in plain English. Each sentence is computed from the results below, including how much to trust it.");
    const lines = t.summary || [];
    if (!lines.length) { s.append(h("p", "dim", "This file carries no summary sentences.")); return s; }
    const ul = h("ul", "words"); lines.forEach(x => ul.append(h("li", "", x))); s.append(ul);
    return s;
  }

  // ------------------------------------------------------------ 3. standings
  function winBar(k, g) {
    const [lo, hi] = wilson(k, g);
    const bar = h("div", "bar");
    bar.title = g ? `won ${k} of ${g} games (${pct(k, g)}); the true win rate plausibly lies between ${pctOf(lo)} and ${pctOf(hi)} (95% interval)` : "no games";
    const ci = h("i", "ci"); ci.style.left = `${100 * lo}%`; ci.style.width = `${100 * (hi - lo)}%`;
    const pt = h("b"); pt.style.left = `${g ? 100 * k / g : 50}%`;
    const mid = h("s"); bar.append(mid, ci, pt);
    const txt = h("span", "bartext", g ? `${pct(k, g)} ` : "— ", h("small", "", g ? `(${pctOf(lo)}–${pctOf(hi)}, ${num(g)} games)` : "(no games)"));
    const wrap = h("div", "barwrap", bar, txt);
    return wrap;
  }
  function standings(t, m, ctx) {
    const s = section("Standings",
      "Win rate is over every opponent, drawn as a bar with its 95% range of plausible values (the lighter band) and the games it rests on. " +
      "Strength is a rating fitted to all matchups at once, shown as the win rate that rating predicts against this field (the field averages 50%), with the raw rating in brackets (1.0 is the field's mean rating). " +
      "Bring it? is how often a player picking a deck blind for this field should bring this one. Tap a bar or a strength to see the numbers behind it.");
    const note = tapNote(s);
    const table = h("table", "stand");
    const head = h("tr"); ["#", "Deck", "Legends", "Win rate", "Strength", "Bring it?", ""].forEach(x => head.append(h("th", "", x)));
    table.append(h("thead", "", head));
    const body = h("tbody");
    m.order.forEach((i, r) => {
      const d = m.decks[i], f = m.field[i] || { wins: 0, games: 0 };
      const tr = h("tr");
      const td = (cls, label, ...kids) => { const c = h("td", cls, ...kids); c.dataset.l = label; tr.append(c); return c; };
      td("rank", "Rank", `${r + 1}`);
      td("deck", "Deck", h("b", "", d.name), " ", kindBadge(m.kinds[i]));
      const legs = h("div", "legs");
      (d.legends || []).forEach(id => legs.append(cardChip(cardOf(ctx.cards, id), ctx, { img: true, label: cardOf(ctx.cards, id).name })));
      td("legends", "Legends", legs);
      const [lo, hi] = wilson(f.wins, f.games);
      const wr = td("wr", "Win rate", winBar(f.wins, f.games));
      note(wr, f.games ? `${d.name} won ${f.wins} of ${f.games} games (${pct(f.wins, f.games)}); the true win rate plausibly lies between ${pctOf(lo)} and ${pctOf(hi)} (95% interval).` : `${d.name} played no games.`);
      const exp = m.expected[i];
      const st = td("bt", "Strength", pctOf(exp), h("small", "", " expected vs this field "), h("small", "dim", `(rating ${m.bt[i].toFixed(2)})`));
      note(st, `${d.name}: Bradley–Terry rating ${m.bt[i].toFixed(2)}, where 1.0 is the mean rating of this field; against these opponents that rating predicts a ${pctOf(exp)} win rate. The plain win rate is ${pct(f.wins, f.games)}: when the two disagree, the win rate is the fact and the rating is the model's view.`);
      td("nash", "Bring it?", pctOf(m.nash[i] || 0));
      const acts = h("div", "acts");
      const dl = h("button", "", "Decklist"); dl.onclick = () => openDeck(ctx.target, i);
      acts.append(dl);
      if (ctx.openInBuild) { const ob = h("button", "", "Open in BUILD"); ob.onclick = () => ctx.openInBuild(d); acts.append(ob); }
      td("act", "", acts);
      body.append(tr);
    });
    table.append(body);
    s.append(scrollX(table));
    s.append(note.node);
    if (m.showKind) s.append(kindsTable(m));
    return s;
  }
  // The same numbers pooled by kind of deck, so a building idea is judged by all its decks.
  function kindsTable(m) {
    const groups = {};
    m.decks.forEach((d, i) => { const k = m.kinds[i] || "—"; (groups[k] = groups[k] || []).push(i); });
    const wrap = h("div", "kinds");
    const keys = Object.keys(groups);
    if (keys.length < 2) {
      // One kind only: a round robin's pooled win rate is always 50%, so a table would say nothing.
      const only = keys[0];
      wrap.append(h("p", "lede", `All ${m.n} decks are ${only === "exploring" ? "Explorer builds" : "labelled " + only}, so there is no second archetype to compare them with in this run; a round robin's pooled win rate is always 50%.`));
      return wrap;
    }
    function avg(idxs, arr) { return idxs.reduce((a, i) => a + arr[i], 0) / idxs.length; }
    const rows = Object.entries(groups).sort((a, b) => avg(b[1], m.expected) - avg(a[1], m.expected));
    wrap.append(h("h4", "", "Archetypes in this run"), h("p", "lede", "The same numbers pooled by kind of deck, so a building idea is judged by all the decks it produced, not by its single best one. Strength is averaged over the group's decks and shown as an expected win rate against this field."));
    const table = h("table", "rep small");
    const head = h("tr"); ["Archetype", "Decks", "Strength", "Win rate (games)", "Best deck"].forEach(x => head.append(h("th", "", x))); table.append(head);
    rows.forEach(([kind, idxs]) => {
      const k = idxs.reduce((a, i) => a + (m.field[i]?.wins || 0), 0), g = idxs.reduce((a, i) => a + (m.field[i]?.games || 0), 0);
      const best = idxs.reduce((a, i) => m.bt[i] > m.bt[a] ? i : a, idxs[0]);
      const tr = h("tr", "", h("td", "", kindBadge(kind === "—" ? null : kind) || "—"), h("td", "", `${idxs.length}`),
        h("td", "", `${pctOf(avg(idxs, m.expected))}`, h("small", "dim", ` (rating ${avg(idxs, m.bt).toFixed(2)})`)), h("td", "", `${pct(k, g)} (${num(g)})`), h("td", "", m.names[best]));
      table.append(tr);
    });
    wrap.append(scrollX(table));
    return wrap;
  }

  // ------------------------------------------------------------ 4. head-to-head
  function matrix(t, m, ctx) {
    const s = section("Head-to-head", "Read across: the row deck's win rate against the column deck, with the games in brackets. Green means the row deck won more than half, red less; the deeper the colour, the further from even. Tap a cell to see the exact count and how much to trust it.");
    if (!m.n) return s;
    const note = tapNote(s);
    const table = h("table", "matrix");
    const head = h("tr", "", h("th"));
    m.order.forEach(j => { const th = h("th", "", h("span", "full", m.names[j]), h("span", "short", shortName(m.names[j]))); th.title = m.names[j]; head.append(th); });
    table.append(head);
    m.order.forEach(i => {
      const tr = h("tr");
      const rh = h("th", "", h("span", "full", m.names[i]), h("span", "short", shortName(m.names[i]))); rh.title = m.names[i]; tr.append(rh);
      m.order.forEach(j => {
        if (i === j) { tr.append(h("td", "self", "·")); return; }
        const [w, g, q] = m.rate(i, j);
        const td = h("td");
        if (!g) { td.append("—"); note(td, `${m.names[i]} and ${m.names[j]} did not play.`); tr.append(td); return; }
        const r = w / g, d = r - 0.5;
        const alpha = Math.min(1, Math.abs(d) / 0.35) * 0.55;
        td.style.background = d > 0 ? `rgba(143,242,106,${alpha})` : d < 0 ? `rgba(255,92,108,${alpha})` : "transparent";
        const solid = q < 0.05;
        td.append(h("span", "r", pct(w, g)));
        if (solid) td.append(h("span", "sig", "✓"));
        td.append(" ", h("small", "", `(${g})`));
        if (solid) td.classList.add("solid");
        note(td, `${m.names[i]} beat ${m.names[j]} in ${w} of ${g} games (${pct(w, g)}) — ${sigText(q, g)}${qText(q)}.`);
        tr.append(td);
      });
      table.append(tr);
    });
    s.append(scrollX(table));
    s.append(h("p", "legend", "row beats column · ✓ = statistically solid (fewer than one such mark in twenty is expected to be a fluke) · numbers in brackets = games · tap a cell to see the exact count and how much to trust it"));
    s.append(note.node);
    return s;
  }

  // ------------------------------------------------------------ 5. the decks
  function openDeck(target, i) {
    const det = target.querySelector(`#rep-deck-${i}`);
    if (!det) return;
    det.open = true;
    det.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function curveBars(curve) {
    const c = h("div", "curve mini");
    const mx = Math.max(1, ...curve);
    curve.forEach((n, i) => { const d = h("div"); d.style.height = `${Math.round(40 * n / mx)}px`; d.dataset.n = n || ""; d.dataset.c = i === 6 ? "7+" : String(i + 1); c.append(d); });
    return c;
  }
  function changes(hist, ctx) {
    const wrap = h("div", "changes");
    wrap.append(h("h5", "", "What changed this generation"));
    if (!hist || !hist.length) { wrap.append(h("p", "", "No card swap was tried.")); return wrap; }
    const acc = hist.filter(x => x.accepted), rej = hist.length - acc.length;
    if (!acc.length) {
      wrap.append(h("p", "", `None — all ${rej} proposed swap${rej !== 1 ? "s were" : " was"} rejected by the swap test, so the list is unchanged.`));
      return wrap;
    }
    const ul = h("ul");
    acc.forEach(x => {
      const p = x.proposal || {};
      const out = cardOf(ctx.cards, p.out || "?"), inn = cardOf(ctx.cards, p.in || "?");
      const what = p.kind === "legend" ? "Legend" : "card";
      const disc = x.discordant || 0, wins = x.challenger_wins || 0;
      ul.append(h("li", "", p.kind === "legend" ? "Legend " : "", cardChip(out, ctx), " → ", cardChip(inn, ctx),
        h("span", "dim", ` (the new ${what} won ${pct(wins, disc)} of the ${disc} games that differed, ${num(x.games)} games each side)`)));
    });
    wrap.append(h("p", "", `Accepted ${acc.length} swap${acc.length !== 1 ? "s" : ""}:`), ul);
    if (rej) wrap.append(h("p", "dim", `${rej} other proposal${rej !== 1 ? "s were" : " was"} rejected: the new card did not win clearly more of the games that came out differently.`));
    return wrap;
  }
  function deckDetails(t, m, i, rank, ctx) {
    const d = m.decks[i];
    const det = h("details", "deck"); det.id = `rep-deck-${i}`;
    const sum = h("summary", "", h("b", "", `${rank}. ${d.name}`), " ", kindBadge(m.kinds[i]),
      h("span", "dim legnames", " · " + (d.legends || []).map(id => cardOf(ctx.cards, id).name).join(", ")));
    det.append(sum);
    const body = h("div", "body");
    if (d.shape) body.append(h("p", "shape", h("b", "", "Shape: "), d.shape));
    const legs = h("div", "legs big");
    (d.legends || []).forEach(id => legs.append(cardChip(cardOf(ctx.cards, id), ctx, { img: true })));
    body.append(h("div", "row", h("span", "lbl", "LEGENDS"), legs));
    const grid = h("div", "deckgrid");
    let size = 0;
    groupDeck(d.main, ctx.cards).forEach(([type, rows]) => {
      if (!rows.length) return;
      const count = rows.reduce((a, r) => a + r[1], 0); size += count;
      const col = h("div", "group", h("h5", "", `${type === "Gear" ? "Gear" : type === "Other" ? "Unknown cards" : type + "s"} · ${count}`));
      rows.forEach(([c, n]) => col.append(h("div", "line", h("span", "n", `${n}×`), cardChip(c, ctx), h("small", "dim", ` (${statText(c)})`))));
      grid.append(col);
    });
    body.append(grid);
    const prof = d.profile;
    const curve = prof && prof.curve ? prof.curve : null;
    body.append(h("div", "row curverow", h("span", "lbl", `COST CURVE · ${size} cards${prof && prof.sell_tags != null ? ` · ${prof.sell_tags} with a sell tag` : ""}`), curve ? curveBars(curve) : h("span", "dim", "unknown cards, no curve")));
    if ((m.info.generation || 0) > 1 && (m.info.fresh || []).includes(d.name)) body.append(h("p", "fresh", `Built fresh this generation, replacing last generation's ${d.name}.`));
    const climb = m.info.climb;
    if (climb && i < climb.length && climb[i] != null) body.append(changes(climb[i], ctx));
    if (m.info.replaced === d.name) body.append(h("p", "replaced", "This builder is replaced by a fresh deck next generation: it finished last."));
    if (ctx.openInBuild) { const ob = h("button", "", "Open in BUILD"); ob.onclick = () => ctx.openInBuild(d); body.append(h("div", "acts", ob)); }
    det.append(body);
    return det;
  }
  function decks(t, m, ctx) {
    const s = section("The decks", "Every list in this run, in ranking order: its archetype, the shape numbers in words, the three Legends, the cards grouped by type with cost and power, the cost curve, and in a league the card swaps that were tried this generation.");
    m.order.forEach((i, r) => s.append(deckDetails(t, m, i, r + 1, ctx)));
    return s;
  }

  // ------------------------------------------------------------ 6. cards that helped and hurt
  const MIN_CARD_GAMES = 10, THIN_GAMES = 20;      // the thresholds of report.card_rows / THIN_GAMES
  function cardRows(stats) {
    const rows = [];
    Object.entries(stats || {}).forEach(([id, s]) => {
      if (!s || s.drawn_games < MIN_CARD_GAMES || s.other_games < MIN_CARD_GAMES) return;
      const gih = s.drawn_wins / s.drawn_games, gnd = s.other_wins / s.other_games;
      rows.push({ id, gih, gnd, iwd: gih - gnd, games: s.drawn_games, other: s.other_games, thin: Math.min(s.drawn_games, s.other_games) < THIN_GAMES });
    });
    rows.sort((a, b) => b.iwd - a.iwd || a.id.localeCompare(b.id));
    if (rows.length <= 8) return rows;
    return rows.slice(0, 5).concat([null], rows.slice(-3));
  }
  function cardsSection(t, m, ctx) {
    const s = section("Cards that helped and hurt",
      "Per deck: the difference in percentage points between the win rate in games where the card was drawn at least once and the win rate in games where it stayed in the deck, with the games behind each side. " +
      `Only cards drawn in at least ${MIN_CARD_GAMES} games and left in the deck in at least ${MIN_CARD_GAMES} are listed — the five that helped most and the three that hurt most (every card when a deck has eight or fewer); the … row stands for the cards in between. ` +
      `Three-of cards are drawn in most games, so the not-drawn side is often a handful of games: a difference marked thin rests on fewer than ${THIN_GAMES} games on one side and is noise until the swap test confirms it. ` +
      "All of it is correlation, not proof: the card was drawn in particular games, next to particular cards, against particular opponents. " +
      "The hill-climb's swap test, which plays the same games with and without a card, is the causal check.");
    let any = false;
    m.order.forEach(i => {
      const rows = cardRows((t.cards || [])[i]);
      if (!rows.length) return;
      any = true;
      const table = h("table", "rep small helped");
      const head = h("tr");
      [["Card", ""], ["Diff.", "difference in percentage points: won when drawn minus won when not drawn"], ["Won when drawn", ""], ["Won when not drawn", ""], ["Games drawn / not drawn", ""]]
        .forEach(([x, tip]) => { const th = h("th", "", x); if (tip) th.title = tip; head.append(th); });
      table.append(head);
      rows.forEach(r => {
        if (!r) { table.append(h("tr", "gap", h("td", "", "…"), h("td"), h("td"), h("td"), h("td"))); return; }
        const diff = round0(100 * r.iwd);
        const dtd = h("td", (diff > 0 ? "pos" : diff < 0 ? "neg" : "") + (r.thin ? " thin" : ""), `${diff > 0 ? "+" : ""}${diff}`, r.thin ? h("small", "", " thin") : null);
        if (r.thin) dtd.title = `one side rests on only ${Math.min(r.games, r.other)} games: noise until the swap test confirms it`;
        table.append(h("tr", "", h("td", "", cardChip(cardOf(ctx.cards, r.id), ctx)), dtd, h("td", "", pctOf(r.gih)), h("td", "", pctOf(r.gnd)), h("td", "", `${num(r.games)} / ${num(r.other)}`)));
      });
      s.append(h("h4", "", m.names[i], " ", kindBadge(m.kinds[i])), scrollX(table));
    });
    if (!any) s.append(h("p", "dim", `No card was both drawn and left in the deck in ${MIN_CARD_GAMES} or more games, so there is nothing to show yet.`));
    return s;
  }

  // ------------------------------------------------------------ 7. league evolution
  const PALETTE = ["#58e0ff", "#f4e01f", "#8ff26a", "#ff5c6c", "#c98bff", "#ffa94d", "#6aa8ff", "#ff7ad9", "#a3e4d7", "#f0b27a"];
  const NO_ARCH = "no archetype recorded";
  // A row's strength as the win rate it predicts against its own generation's field (league.json
  // stores it as "expected"; older series fall back to rating ÷ (rating + 1)).
  const rowValue = (r) => r.expected != null ? Number(r.expected) : (Number(r.bt || 0) / (Number(r.bt || 0) + 1));
  function colourMap(series) {
    const map = { exploring: "#7f95a3" }; let k = 0;
    series.generations.forEach(g => (g.standings || []).forEach(r => { const a = r.archetype || NO_ARCH; if (!(a in map)) map[a] = PALETTE[k++ % PALETTE.length]; }));
    return map;
  }
  function chart(series, width) {
    const gens = series.generations.slice().sort((a, b) => a.gen - b.gen);
    const G = gens.length;
    const W = Math.max(300, Math.min(720, width)), H = W < 480 ? 230 : 280;
    const narrow = W < 480;
    const padL = 42, padR = narrow ? 70 : 110, padT = 14, padB = 30;
    const x = (k) => padL + (G > 1 ? (k / (G - 1)) : 0.5) * (W - padL - padR);
    const y = (v) => padT + (1 - v) * (H - padT - padB);
    const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "evo", role: "img" });
    root.setAttribute("aria-label", "expected win rate of each builder against its generation's field, per generation");
    [0, 0.25, 0.5, 0.75, 1].forEach(v => {
      root.append(svg("line", { x1: padL, x2: W - padR, y1: y(v), y2: y(v), class: v === 0.5 ? "mid" : "grid" }));
      const tx = svg("text", { x: padL - 6, y: y(v) + 4, class: "tick", "text-anchor": "end" }); tx.textContent = `${round0(100 * v)}%`; root.append(tx);
    });
    gens.forEach((g, k) => { const tx = svg("text", { x: x(k), y: H - padB + 16, class: "tick", "text-anchor": "middle" }); tx.textContent = `gen ${g.gen}`; root.append(tx); });
    const colours = colourMap(series);
    const byName = {};
    gens.forEach((g, k) => (g.standings || []).forEach(r => { (byName[r.name] = byName[r.name] || []).push({ k, r }); }));
    const ends = [];
    Object.entries(byName).forEach(([name, pts]) => {
      const v = rowValue;
      for (let a = 1; a < pts.length; a++) {
        const p = pts[a - 1], q = pts[a];
        if (q.k !== p.k + 1) continue;
        // A replaced deck and the fresh deck that inherits its builder name are two different
        // lists: the segment between them is dashed, not drawn as one deck improving.
        const dashed = p.r.replaced || q.r.fresh;
        root.append(svg("line", { x1: x(p.k), y1: y(v(p.r)), x2: x(q.k), y2: y(v(q.r)), class: "seg" + (dashed ? " newdeck" : ""), stroke: colours[q.r.archetype || NO_ARCH] }));
      }
      pts.forEach(p => {
        const c = colours[p.r.archetype || NO_ARCH];
        const dot = svg("circle", { cx: x(p.k), cy: y(v(p.r)), r: 4.5, stroke: c, fill: p.r.fresh ? "#0d1420" : c, "stroke-width": 2 });
        const title = svg("title"); title.textContent = `${name} · gen ${gens[p.k].gen} · ${p.r.archetype || NO_ARCH} · ${pctOf(v(p.r))} expected vs that generation's field (rating ${Number(p.r.bt || 0).toFixed(2)}) · won ${p.r.wins} of ${p.r.games}${p.r.fresh ? " · built fresh this generation" : ""}${p.r.replaced ? " · replaced after this generation" : ""}`;
        dot.append(title); root.append(dot);
        if (p.r.replaced) { const t = svg("text", { x: x(p.k), y: y(v(p.r)) - 8, class: "cross", "text-anchor": "middle" }); t.textContent = "✕"; root.append(t); }
      });
      const last = pts[pts.length - 1];
      ends.push({ name, y: y(v(last.r)), x: x(last.k), c: colours[last.r.archetype || NO_ARCH] });
    });
    ends.sort((a, b) => a.y - b.y);
    for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 12) ends[i].y = ends[i - 1].y + 12;
    ends.forEach(e => { const t = svg("text", { x: e.x + 8, y: e.y + 4, class: "name", fill: e.c }); t.textContent = narrow ? shortName(e.name) : e.name; root.append(t); });
    return { node: root, colours };
  }
  function seriesTable(series) {
    const agg = {};
    series.generations.forEach(g => (g.standings || []).forEach(r => {
      const a = r.archetype || NO_ARCH;
      const s = agg[a] = agg[a] || { gens: new Set(), decks: 0, wins: 0, games: 0, bt: 0, exp: 0, n: 0 };
      s.gens.add(g.gen); s.decks += 1; s.wins += r.wins || 0; s.games += r.games || 0; s.bt += Number(r.bt || 0); s.exp += rowValue(r); s.n += 1;
    }));
    const rows = Object.entries(agg).sort((a, b) => (b[1].games ? b[1].wins / b[1].games : 0) - (a[1].games ? a[1].wins / a[1].games : 0));
    const table = h("table", "rep small");
    const head = h("tr");
    [["Archetype", ""], ["Generations", "generations in which a deck of this kind played"], ["Deck-generations", "one deck playing one round robin"],
     ["Win rate (95% range, games)", ""], ["Strength (relative to its own generation)", "expected win rate against its own generation's field, averaged over the group's deck-generations; every generation's field averages 50%, so this compares a deck with its rivals, not with an absolute scale"]]
      .forEach(([x, tip]) => { const th = h("th", "", x); if (tip) th.title = tip; head.append(th); });
    table.append(head);
    rows.forEach(([a, s]) => {
      const [lo, hi] = wilson(s.wins, s.games); const mean = s.bt / Math.max(1, s.n), exp = s.exp / Math.max(1, s.n);
      table.append(h("tr", "", h("td", "", kindBadge(a === NO_ARCH ? null : a) || NO_ARCH), h("td", "", `${s.gens.size}`), h("td", "", `${s.decks}`),
        h("td", "", `${pct(s.wins, s.games)} (${pctOf(lo)}–${pctOf(hi)}, ${num(s.games)})`), h("td", "", `${pctOf(exp)}`, h("small", "dim", ` (rating ${mean.toFixed(2)})`))));
    });
    return table;
  }
  function fillEvolution(sec, series, ctx) {
    const width = (ctx.target.clientWidth || window.innerWidth) - 40;
    const { node, colours } = chart(series, width);
    sec.append(node);
    const leg = h("div", "evolegend");
    Object.entries(colours).forEach(([a, c]) => { const sw = h("i"); sw.style.background = c; leg.append(h("span", "", sw, a === "exploring" ? "exploring (Explorer builder)" : a)); });
    leg.append(h("span", "dim", "hollow point = built fresh that generation · ✕ = replaced after that generation · a dashed segment joins a replaced deck to the new list that took its slot"));
    sec.append(leg);
    sec.append(h("h4", "", "Archetype win rate across all generations of this league"),
      h("p", "lede", "Every deck of every generation, pooled by the archetype it was built toward. A deck-generation is one deck playing one round robin. The range is the 95% interval of plausible values for the pooled win rate; strength is relative to each deck's own generation. A group that only ever fielded one or two decks is thin evidence however good the number looks."),
      scrollX(seriesTable(series)));
  }
  // The series comes with the report (league.json); an older league without one is rebuilt from
  // its sibling generation reports when the host page lends us its API.
  async function siblingSeries(t, ctx) {
    const mt = /^(.*)\/gen(\d+)\/tournament\.json$/.exec(t.file || "");
    if (!mt || !ctx.api) return null;
    const files = (await ctx.api("/api/reports")).filter(f => f.startsWith(mt[1] + "/gen") && /\/gen\d+\/tournament\.json$/.test(f));
    if (files.length < 2) return null;
    const gens = [];
    for (const f of files) {
      const r = f === t.file ? t : await ctx.api(`/api/report?file=${encodeURIComponent(f)}`);
      const g = +(/gen(\d+)\//.exec(f) || [])[1];
      const info = r.info || {};
      const exp = (r.expected && r.expected.length === (r.decks || []).length) ? r.expected : fieldExpected((r.bradley_terry || []).map(Number));
      gens.push({ gen: g, standings: (r.decks || []).map((d, i) => ({ name: d.name, archetype: kindOf(d), bt: (r.bradley_terry || [])[i] || 0, expected: exp[i],
        wins: (r.field || [])[i]?.wins || 0, games: (r.field || [])[i]?.games || 0, fresh: (info.fresh || []).includes(d.name) || null, replaced: info.replaced === d.name })) });
    }
    return { generations: gens.sort((a, b) => a.gen - b.gen) };
  }
  function evolution(t, m, ctx) {
    const isLeague = !!(t.league_series || m.info.generation || /\/gen\d+\/tournament\.json$/.test(t.file || ""));
    if (!isLeague) return null;
    const s = section("League evolution", "Each builder's strength from generation to generation, shown as the win rate it predicts against that generation's field — relative to its rivals: the field always averages 50%, so a rising line means the deck gained on the others, not that it got stronger on an absolute scale. Points are coloured by the archetype the deck was built toward.");
    const series = t.league_series;
    if (series && series.generations && series.generations.length) fillEvolution(s, series, ctx);
    else {
      const note = h("p", "dim", "Looking for the other generations of this league…"); s.append(note);
      siblingSeries(t, ctx).then(ser => {
        note.remove();
        if (ser) fillEvolution(s, ser, ctx);
        else s.append(h("p", "dim", "Only this generation is available, so there is no evolution to draw."));
      }).catch(e => { note.textContent = "Could not load the other generations: " + e.message; });
    }
    return s;
  }

  // ------------------------------------------------------------ 8. glossary + text version
  function glossary(t) {
    const g = t.glossary || [];
    if (!g.length) return null;
    const det = h("details", "how rglossary");
    det.append(h("summary", "", "How to read this report"));
    const dl = h("dl");
    g.forEach(e => dl.append(h("dt", "", e.term), h("dd", "", e.text)));
    det.append(dl);
    return det;
  }
  function textVersion(t) {
    if (!t.markdown) return null;
    const det = h("details", "textver");
    det.append(h("summary", "", `Text version (${t.file ? t.file.replace(/tournament\.json$/, "report.md") : "report.md"}) — for copy and paste`));
    const pre = h("pre", "md", t.markdown);
    if (navigator.clipboard) { const b = h("button", "", "Copy"); b.onclick = async () => { try { await navigator.clipboard.writeText(t.markdown); b.textContent = "Copied"; setTimeout(() => { b.textContent = "Copy"; }, 1500); } catch (e) { b.textContent = "select the text and copy"; } }; det.append(h("div", "acts", b)); }
    det.append(pre);
    return det;
  }

  // ------------------------------------------------------------ entry point
  // target: the element to fill; t: the /api/report object; opts: {cards, preview(card, touch),
  // unpreview(), openInBuild(deck), api(path, body)}. Missing fields in t degrade to an
  // absent section, never to an error.
  function render(target, t, opts = {}) {
    const ctx = { cards: opts.cards || {}, preview: opts.preview, unpreview: opts.unpreview, openInBuild: opts.openInBuild, api: opts.api, target };
    target.innerHTML = "";
    const root = h("div", "report");
    const m = model(t);
    root.append(header(t, m), summary(t), standings(t, m, ctx), matrix(t, m, ctx), decks(t, m, ctx), cardsSection(t, m, ctx));
    [evolution(t, m, ctx), glossary(t), textVersion(t)].forEach(x => { if (x) root.append(x); });
    target.append(root);
    return root;
  }
  return { render, groupDeck, wilson };
})();
