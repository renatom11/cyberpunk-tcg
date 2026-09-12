/* cptcg web client. No game logic here: render the view JSON, post back an option index. */
const $ = (s, el = document) => el.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const api = async (path, body) => {
  if (window.CPTCG_BRIDGE) return window.CPTCG_BRIDGE.api(path, body);        // static build: engine in the browser
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json();
  if (j.error) throw new Error(j.error);
  return j;
};

let CARDS = {};            // id -> card def (+ image flag)
let HAS_BACK = true;       // data/images/_back.jpg exists (cleared on first failed load)
// A Windows laptop with a touchscreen reports maxTouchPoints > 0 and still has a mouse, so these
// are not two kinds of device but two kinds of input, and a hybrid has both. Reading touch
// capability as "cannot hover" is what stopped the card preview ever appearing on those machines.
// any-hover asks whether ANY attached pointer can hover, which is the question that matters here.
const CAN_HOVER = window.matchMedia("(any-hover: hover)").matches || window.matchMedia("(hover: hover)").matches;
const CAN_TOUCH = navigator.maxTouchPoints > 0 || window.matchMedia("(hover: none)").matches;
const TOUCH = CAN_TOUCH && !CAN_HOVER;      // touch only: a tap has to do the work a hover would
let GAME = null;           // {id, view, log[]}
let LOG = [];

// ---------------------------------------------------------------- cards
function cardNode(c, opts = {}) {
  const d = el("div", "card " + (c.color || ""));
  // Only where the view already gives one: a face-down Legend and a rival hand card are built from
  // {} on purpose, and must not gain an identity here.
  if (c && c.inst != null) d.dataset.inst = c.inst;
  if (opts.back) {
    d.className = "card back" + (opts.small ? " sm" : "");
    if (HAS_BACK) { const img = el("img"); img.draggable = false; img.src = opts.legend ? "images/_back_legend.jpg" : "images/_back.jpg"; img.alt = "card back"; img.onerror = () => { HAS_BACK = false; img.remove(); }; d.append(img); }
    return d;
  }
  if (opts.small) d.classList.add("sm");
  const def = CARDS[c.id] || {};
  if (def.image) {
    const img = el("img"); img.draggable = false; img.src = `images/${c.id}.jpg`; img.alt = c.name;
    if (CAN_HOVER) { d.onmouseenter = () => showPreview(img.src, c); d.onmouseleave = hidePreview; }
    if (CAN_TOUCH) {
      // Touch: a long-press previews any card without acting. On a touch-only screen a plain tap
      // does it too, since there is no hover to fall back on (decorate() replaces onclick for cards
      // that can act); where a mouse is also present, tapping is left alone so it can still click.
      if (!CAN_HOVER) d.onclick = () => showPreview(img.src, c, true);
      let press = null, fired = false;
      d.addEventListener("touchstart", () => { fired = false; press = setTimeout(() => { press = null; fired = true; showPreview(img.src, c, true); }, 450); }, { passive: true });
      const cancel = () => { if (press) { clearTimeout(press); press = null; } };
      d.addEventListener("touchend", cancel); d.addEventListener("touchmove", cancel, { passive: true }); d.addEventListener("touchcancel", cancel);
      d.addEventListener("click", (e) => { if (fired) { fired = false; e.stopImmediatePropagation(); e.preventDefault(); } }, true);
    }
    img.onerror = () => { img.remove(); d.append(...textFace(c)); };
    d.append(img);
  } else {
    d.append(...textFace(c));
  }
  if (c.spent) d.classList.add("spent");
  if (c.lag_blocks) d.classList.add("lag");   // lagged AND stopped by it; a GO SOLO Legend is neither
  // The chip is for power that is *not* what the card prints — Gear, a buff, a debuff. A Unit
  // standing at its printed power says so in its own bottom corner already, and a second copy of
  // that number in a circle on every card made the board look like every card was modified.
  // A variable-power card ("0+") prints no fixed number, so it always gets the chip.
  if (c.power_now != null && c.type !== "Program" && c.power_now !== c.power) {
    const pn = el("div", "pnow", c.power_now);
    if (typeof c.power === "number") pn.classList.add(c.power_now > c.power ? "up" : "down");
    d.append(pn);
  }
  if (c.gear && c.gear.length) d.append(gearStack(c.gear));
  return d;
}
// Gear is equipped *under* the Unit it is on, the way it is laid on the table: the Unit covers all
// but the top strip of each piece, and a second piece slides out sideways from the first, so you
// can see how many are on there and read the top of each one. The Unit's power badge already shows
// what they add up to.
function gearStack(gear) {
  const g = el("div", "gearstack");
  gear.forEach((x, i) => {
    const n = cardNode(x, { small: true });
    n.classList.add("gearcard");
    n.style.setProperty("--i", i);
    g.append(n);
  });
  return g;
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
function renderBoard(root, v, { interactive, onAct, watching, onSkip, fresh } = {}) {
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
    // What a click does is *select*: the card's actions are listed in a panel that stays put,
    // rather than a menu that appears under the cursor and vanishes. Dragging is the fast path.
    if (atk && atk.attacker === inst) node.classList.add("attacking");
  };

  // ----- left column
  // Top to bottom the way the reference client lays it out: the rival's hand, their fixer and Gig
  // area, the turn box, then mine mirrored back out to my hand. The two name plates sit outside
  // the panels, at the very top and bottom of the column, so the board says whose end is whose
  // without a label on every area.
  const left = el("div", "col left");
  left.append(el("div", "nameplate", P[opp].name.toUpperCase()));
  const oppHand = el("div", "panel hand opp p-opp-hand");
  if (P[opp].hand) P[opp].hand.forEach(c => oppHand.append(cardNode(c, { small: true })));
  else for (let i = 0; i < P[opp].hand_count; i++) oppHand.append(cardNode({}, { back: true, small: true }));
  // A row of identical backs is a count wearing a costume. Where there is room the costume is
  // worth it; where there is not, the phone hides the backs and shows this instead.
  oppHand.append(el("div", "handcount", `HAND ${P[opp].hand_count}`));
  const oppTray = diceTray(P[opp], false); oppTray.classList.add("p-opp-fixer");
  const oppGig = gigPanel(P[opp], me); oppGig.classList.add("p-opp-gig");
  left.append(oppHand, oppTray, oppGig);

  // The banner says what is being asked of you, not which phase the engine is in — "ROLL FIXER DIE"
  // is a instruction, "START PHASE" is a label. The turn and phase stay on the line below it.
  const phase = el("div", "panel phase");
  const STATE = { MULLIGAN: "OPENING HAND", ORDER: "TURN ORDER", GIG_DIE: "ROLL FIXER DIE",
                  MAIN: "YOUR TURN", TARGET: "CHOOSE A TARGET", REACTION: "RIVAL ATTACKS",
                  PICK: "MAKE A CHOICE" };
  const mine = pend && pend.player === me;
  const title = v.over ? "GAME OVER"
    : !pend ? "…"
    : mine ? (STATE[pend.kind] || pend.phase.toUpperCase())
    : "RIVAL'S TURN";
  phase.classList.toggle("waiting", !v.over && !!pend && !mine);
  phase.classList.toggle("done", !!v.over);
  const sub = v.over ? `${P[v.winner].name} wins · ${v.end_reason}`
    : `TURN ${v.turn}${v.overtime ? " · OVERTIME" : ""} | ${(pend ? pend.phase : "").toUpperCase()}`;
  phase.append(el("div", "title", title), el("div", "sub", sub));
  // The one move that ends the turn belongs in the banner, where it is always in the same place,
  // rather than somewhere in a list of every legal action.
  if (mine && interactive) {
    const end = (pend.options || []).find(o => o.kind === "EndTurn");
    if (end) { const b = el("button", "endturn", "END TURN"); b.onclick = () => onAct(end.index); phase.append(b); }
  }
  phase.classList.add("p-banner");
  const myGig = gigPanel(P[me], me); myGig.classList.add("p-my-gig");
  const myTray = diceTray(P[me], myTurn && pend.kind === "GIG_DIE", pend, onAct); myTray.classList.add("p-my-fixer");
  left.append(phase, myGig, myTray);
  const myHand = el("div", "panel hand mine p-my-hand");
  if (P[me].hand) P[me].hand.forEach(c => { const n = cardNode(c); decorate(n, c.inst); myHand.append(n); });
  else for (let i = 0; i < P[me].hand_count; i++) myHand.append(cardNode({}, { back: true }));
  left.append(myHand, el("div", "nameplate", P[me].name.toUpperCase()));

  // ----- centre column
  const center = el("div", "col center");
  // The official playmat (gameplay guide, "Playmat areas") puts LEGENDS and EDDIES side by side on
  // one band, with FIELD between the two bands and DECK/TRASH down the right edge of the fields.
  const eddiesPanel = (p) => {
    const ed = el("div", "panel eddies"); 
    const list = el("div", "list");
    if (!p.eddies.list.length) list.append(el("span", "waiting", "No Eddies yet."));
    p.eddies.list.forEach(c => {
      const n = cardNode(c, { back: true, small: true });
      if (c.spent) n.classList.add("spent");
      if (c.image) { n.onmouseenter = () => showPreview(`images/${c.id}.jpg`, c); n.onmouseleave = hidePreview; if (TOUCH) n.onclick = () => showPreview(`images/${c.id}.jpg`, c, true); }
      list.append(n);
    });
    ed.append(list);
    return ed;
  };
  const legRow = (p, mine) => {
    const band = el("div", "legendrow");
    const row = el("div", "panel legends");
    p.legends.forEach(l => {
      let n;
      if (l.faceup || l.known_only) { n = cardNode(l, { small: true }); if (l.faceup) n.classList.add("faceup-legend"); if (l.known_only) n.style.opacity = .7; }
      else { n = cardNode({ inst: l.inst }, { back: true, small: true, legend: true }); }
      if (l.spent) n.classList.add("spent");
      if (l.gear && l.gear.length) n.append(gearStack(l.gear));
      decorate(n, l.inst);
      row.append(n);
    });
    const ed = eddiesPanel(p);
    if (mine) ed.classList.add("p-my-eddies");
    band.append(row, ed);
    return band;
  };
  const fieldRow = (p) => {
    const row = el("div", "panel field");
    if (!p.field.length) for (let i = 0; i < 4; i++) row.append(el("div", "slot"));
    p.field.forEach(u => { const n = cardNode(u); decorate(n, u.inst); row.append(n); });
    return row;
  };
  // Deck and trash live in a strip down the right-hand edge of the two field rows, rival's pair
  // above mine: trash on the outside, deck on the inside, so the four boxes mirror across the
  // middle of the board like everything else does.
  const stack = (p, kind) => {
    const box = el("div", "stackbox " + kind);
    if (kind === "trash") {
      const top = p.trash.length ? p.trash[p.trash.length - 1] : null;
      if (top) { const n = cardNode(top, { small: true }); n.classList.add("thumb"); box.append(n); }
      box.append(el("span", "n", p.trash.length || ""));
      box.dataset.hint = `${p.name} · trash · ${p.trash.length} card${p.trash.length === 1 ? "" : "s"}`
                       + (p.trash.length ? " · click to look through it" : "");
      if (p.trash.length) {
        box.classList.add("open");
        box.onclick = () => openPile(`${p.name} trash`, p.trash);
      }
    } else {
      box.append(el("span", "n big", p.deck));
      box.dataset.hint = `${p.name} · deck · ${p.deck} card${p.deck === 1 ? "" : "s"} left`;
    }
    return box;
  };
  // One strip per player rather than one for the pair. On a wide screen they stack into the same
  // column and read as the four boxes they always were; on a phone each one becomes the right-hand
  // flank of its own field row, opposite that player's fixer, and no CSS can put the children of a
  // single grid item into two different grid areas.
  const oppStacks = el("div", "stacks opp");
  oppStacks.append(stack(P[opp], "trash"), stack(P[opp], "deck"));
  const myStacks = el("div", "stacks mine");
  myStacks.append(stack(P[me], "deck"), stack(P[me], "trash"));
  const oppLeg = legRow(P[opp], false), oppField = fieldRow(P[opp]), myField = fieldRow(P[me]), myLeg = legRow(P[me], true);
  oppLeg.classList.add("p-opp-legends"); oppField.classList.add("p-opp-field"); myField.classList.add("p-my-field"); myLeg.classList.add("p-my-legends");
  center.append(oppLeg, oppField, myField, myLeg, oppStacks, myStacks);

  // ----- right column
  const right = el("div", "col");
  const controls = el("div", "panel controls p-controls");
  controls.append(el("span", "lbl", "ROOM"));
  if (interactive) {
    controls.append(el("div", "desc", "Take back the last move, concede the match, or leave for a new one."));
    const undo = el("button", "", "UNDO"); undo.onclick = () => act("undo");
    const concede = el("button", "", "CONCEDE"); concede.onclick = () => { if (confirm("Concede?")) act("concede"); };
    const leave = el("button", "", "NEW GAME"); leave.onclick = () => { GAME = null; $("#board").classList.add("hidden"); $("#setup").classList.remove("hidden"); };
    const dl = el("button", "", "EXPORT"); dl.onclick = async () => {
      if (window.CPTCG_BRIDGE) window.CPTCG_BRIDGE.download(`cptcg-game-${GAME.id}.json`, await api(`/api/games/${GAME.id}/replay`));
      else window.open(`/api/games/${GAME.id}/replay`);
    };
    // Payment choice is off the critical path, so it lives as a toggle rather than a settings page.
    const paybtn = el("button", "", autopay() ? "PAY: AUTO" : "PAY: ASK");
    // aria-label, not title: a title is the browser's white tooltip box, and nothing on the
    // board should pop one of those over the cards.
    paybtn.setAttribute("aria-label", "Whether to be asked which Eddies and Legends to spend when you can pay more than one way");
    paybtn.onclick = () => {
      const now = !autopay();
      try { localStorage.setItem(AUTOPAY_KEY, now ? "1" : "0"); } catch (e) {}
      paybtn.textContent = now ? "PAY: AUTO" : "PAY: ASK";
    };
    controls.append(undo, concede, leave, dl, paybtn);
  }
  right.append(controls);
  const logp = el("div", "panel logwrap p-log");
  // The log is the tallest thing in the column and the least urgent; it folds away to its own
  // header so the prompt and the selected card are never below the fold. The choice sticks.
  const logHead = el("div", "loghead");
  const fold = el("button", "foldbtn", logMin() ? "＋" : "−");
  fold.setAttribute("aria-label", "minimise the log");
  logHead.append(el("span", "lbl", "LOG"), fold);
  logp.append(logHead);
  logp.classList.toggle("min", logMin());
  fold.onclick = (e) => {
    e.stopPropagation();
    const now = !logMin();
    try { localStorage.setItem(LOG_MIN_KEY, now ? "1" : "0"); } catch (err) {}
    logp.classList.toggle("min", now);
    fold.textContent = now ? "＋" : "−";
  };
  const logBtn = el("button", "logbtn", "LOG"); logBtn.onclick = () => logp.classList.toggle("open"); controls.append(logBtn);
  logp.onclick = (e) => { if (e.target === logp) logp.classList.remove("open"); };
  const who = (v.players || []).map(x => x.name);
  // Newest first, the way the reference client reads: the turn that just happened is at the top of
  // the panel with its most recent line under the header, and older turns fall away below. Nothing
  // worth reading is ever off the bottom of a scroll box you have to chase.
  const blocks = [];
  (v.log || LOG).forEach(line => {
    if (line.startsWith("—") || !blocks.length) blocks.push([]);
    blocks[blocks.length - 1].push(line);
  });
  blocks.reverse().forEach(block => {
    const head = block[0].startsWith("—") ? block.shift() : null;
    if (head) logp.append(el("p", "turn", markLog(head.replace(/^—\s*|\s*—$/g, "").replace(":", " -").toUpperCase(), who.map(x => x.toUpperCase()))));
    block.reverse().forEach(line => {
      logp.append(el("p", line.startsWith("GAME OVER") ? "end" : "", markLog(line, who)));
    });
  });
  right.append(logp);
  const prompt = el("div", "panel prompt p-prompt"); prompt.append(el("span", "lbl", "PROMPT"));
  if (v.over) {
    prompt.append(el("div", "q", `${P[v.winner].name.toUpperCase()} WINS`), el("div", "desc", v.end_reason));
  } else if (pend && watching) {
    // Replaying the rival's turn: their own prompt text and the human hints below it would both be
    // about a decision that is not the reader's to make.
    prompt.append(el("div", "q", `${watching} is playing`),
                  el("div", "desc", "Their turn, one move at a time. Click anywhere, or SKIP, to jump to the end."));
    const opts = el("div", "opts");
    const b = el("button", "end", "SKIP"); b.onclick = onSkip; opts.append(b);
    prompt.append(opts);
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
  right.append(prompt, cardPanel(v, byInst, pend, myTurn, onAct));
  root.append(left, center, right);
  if (fresh && fresh.size) {
    root.querySelectorAll(".card[data-inst]").forEach(n => {
      if (fresh.has(+n.dataset.inst)) n.classList.add("fresh");
    });
  }
  if (myTurn) wireDrag(root, pend, onAct);
  root.querySelectorAll(".hand, .eddies .list, .legends, .field").forEach(fanHand);
  root.querySelectorAll(".card[data-inst]").forEach(n => {
    n.addEventListener("click", (e) => {
      if (n.classList.contains("payable")) return;      // paying: the click means "spend this"
      e.stopPropagation();
      SELECTED = +n.dataset.inst;
      const box = root.querySelector(".p-cardinfo");
      if (box) box.replaceWith(cardPanel(v, byInst, pend, myTurn, onAct));
      root.querySelectorAll(".card.picked").forEach(x => x.classList.remove("picked"));
      n.classList.add("picked");
    });
  });
  logp.scrollTop = 0;
}

// ---------------------------------------------------------------- drag to play
// Clicking still does everything; this is the other way round, the way the cards work on a table.
// Pointer events rather than HTML5 drag-and-drop, because HTML5 drag does not fire on touch at all
// and this has to work on a phone.
let DRAG = null;
// A card face is an <img>, and an <img> is draggable by default: letting the native drag start puts
// Chromium into HTML5 drag mode, which stops delivering pointermove entirely and leaves the gesture
// frozen a few pixels from where it began. Images are marked draggable=false as they are built and
// this is the backstop for anything else inside a card.
document.addEventListener("dragstart", (e) => { if (e.target.closest(".card")) e.preventDefault(); });

function wireDrag(root, pend, onAct) {
  const plays = {}, sells = {}, gear = {};
  pend.options.forEach(o => {
    if (o.inst == null || o.inst < 0) return;
    if (o.kind === "Play" && o.host >= 0) (gear[o.inst] = gear[o.inst] || {})[o.host] = o;
    else if (o.kind === "Play" || o.kind === "GoSolo") plays[o.inst] = o;
    else if (o.kind === "Sell") sells[o.inst] = o;
  });
  const field = root.querySelector(".p-my-field");
  const eddies = root.querySelector(".p-my-eddies");

  root.querySelectorAll(".hand.mine > .card[data-inst], .p-my-legends .card[data-inst]:not(.gearcard)").forEach(node => {
    const inst = +node.dataset.inst;
    const mine = { play: plays[inst], sell: sells[inst], gear: gear[inst] };
    if (!mine.play && !mine.sell && !mine.gear) return;
    node.classList.add("draggable");
    node.addEventListener("pointerdown", (e) => {
      if (e.button !== undefined && e.button !== 0) return;
      DRAG = { node, inst, opts: mine, x0: e.clientX, y0: e.clientY, ghost: null, moved: false, onAct };
      // No setPointerCapture: the listeners are on `document`, and capturing to a node that a
      // re-render can replace silently stops delivering the rest of the drag.
    });
  });

  // The zones this drag could end on, and what each one would do.
  DRAG_ZONES = [];
  if (field) DRAG_ZONES.push({ el: field, label: "DROP TO PLAY", pick: (d) => d.opts.play });
  if (eddies) DRAG_ZONES.push({ el: eddies, label: "DROP TO SELL", pick: (d) => d.opts.sell });
  root.querySelectorAll(".card[data-inst]").forEach(host => {
    DRAG_ZONES.push({ el: host, label: "EQUIP", host: +host.dataset.inst,
                      pick: (d) => d.opts.gear && d.opts.gear[+host.dataset.inst] });
  });
}
let DRAG_ZONES = [];

function dragZonesFor(d) { return DRAG_ZONES.filter(z => z.pick(d)); }

document.addEventListener("pointermove", (e) => {
  const d = DRAG;
  if (!d) return;
  if (!d.moved) {
    if (Math.abs(e.clientX - d.x0) + Math.abs(e.clientY - d.y0) < 8) return;   // still a click
    d.moved = true;
    hidePreview();
    const r = d.node.getBoundingClientRect();
    const g = d.ghost = d.node.cloneNode(true);
    g.className = d.node.className.replace(/\bfresh\b/, "") + " dragghost";
    g.style.width = r.width + "px"; g.style.height = r.height + "px";
    g.dataset.dx = (r.left - e.clientX); g.dataset.dy = (r.top - e.clientY);
    document.body.append(g);
    d.node.classList.add("dragging");
    dragZonesFor(d).forEach(z => { z.el.classList.add("droptarget"); z.el.dataset.drop = z.label; });
  }
  const g = d.ghost;
  g.style.left = (e.clientX + +g.dataset.dx) + "px";
  g.style.top = (e.clientY + +g.dataset.dy) + "px";
  const over = zoneAt(d, e.clientX, e.clientY);
  DRAG_ZONES.forEach(z => z.el.classList.toggle("dropover", z === over));
}, { passive: true });

function zoneAt(d, x, y) {
  let best = null;
  dragZonesFor(d).forEach(z => {
    const r = z.el.getBoundingClientRect();
    if (x < r.left || x > r.right || y < r.top || y > r.bottom) return;
    // the smallest box wins, so a card inside the field takes the drop over the field itself
    if (!best || r.width * r.height < best.area) best = { z, area: r.width * r.height };
  });
  return best && best.z;
}

document.addEventListener("pointerup", (e) => {
  const d = DRAG;
  DRAG = null;
  if (!d) return;
  const wasDrag = d.moved;
  if (d.ghost) d.ghost.remove();
  d.node.classList.remove("dragging");
  DRAG_ZONES.forEach(z => { z.el.classList.remove("droptarget", "dropover"); delete z.el.dataset.drop; });
  if (!wasDrag) return;                       // a click: the node's own handler deals with it
  const z = zoneAt(d, e.clientX, e.clientY);
  const opt = z && z.pick(d);
  if (opt) { SUPPRESS_CLICK = true; d.onAct(opt.index); }
});

// A pointerup that ended a drag is followed by a click on whatever is underneath; swallow it once
// so dropping a card does not also fire the card's own action menu.
let SUPPRESS_CLICK = false;
document.addEventListener("click", (e) => {
  if (!SUPPRESS_CLICK) return;
  SUPPRESS_CLICK = false;
  e.stopPropagation(); e.preventDefault();
}, true);

// ---------------------------------------------------------------- fanning a row of cards
// Cards overlap by however much they have to, rather than the row scrolling: a hand is a fan you
// hold, and a scroll bar hides the cards it is scrolling past. The overlap has to be measured
// rather than fixed, because it depends on how many cards are in the hand and how wide the column
// is, and both change. Hovering then reveals the card in full — see the CSS: only the cards *after*
// the hovered one need to move, because those are the ones drawn on top of it.
const HAND_MAX_OVERLAP = 0.8;        // never hide more than this much of a card
function fanHand(row) {
  const hand = row;                  // a hand, an Eddies pile, a Legend band, a field: same treatment
  // Empty field slots are the same shape as the cards that will replace them, so they overlap the
  // same way; a row of four that fanned once it was full and overflowed while it was empty would
  // be the strangest possible behaviour.
  const cards = hand.querySelectorAll(".card, .slot");
  const n = cards.length;
  if (!n) return;
  const w = cards[0].offsetWidth;
  if (!w) return;                    // not laid out yet (a hidden tab); the resize hook retries
  // Measured, not computed from n * card width. A spent card lies on its side and carries margins
  // of half the difference between the two dimensions to make room for it, and a row holding one
  // is wider than the arithmetic thinks by 32px a card — which is exactly how a Legend band with a
  // spent Legend in it kept overflowing while the fan believed it had already fixed it. Asking the
  // browser costs one layout flush per row and cannot be wrong.
  hand.style.setProperty("--overlap", "0px");
  const cap = Math.round(w * HAND_MAX_OVERLAP);
  let over = 0;
  // Two corrections, then stop. scrollWidth does not count the last child's right margin, and a
  // spent card carries one of 16px, so a single pass can come back still overflowing by exactly
  // that much. Re-measuring is cheaper than reasoning about which browser counts what.
  for (let pass = 0; pass < 4 && over < cap; pass++) {
    const short = hand.scrollWidth - hand.clientWidth;
    if (short <= 0) break;
    over = Math.min(cap, over + Math.ceil(short / (n - 1)) + 1);   // +1: converge rather than oscillate on a rounding remainder
    hand.style.setProperty("--overlap", over + "px");
  }
}
let FAN_TIMER = null;
window.addEventListener("resize", () => {
  clearTimeout(FAN_TIMER);
  FAN_TIMER = setTimeout(() => document.querySelectorAll("#board .hand, #board .eddies .list, #board .legends, #board .field").forEach(fanHand), 80);
});

// ---------------------------------------------------------------- arrivals
// Which cards are on the board that were not a moment ago. The board is the source of truth rather
// than the log, because the log is prose and this has to be exact: a card that arrives gets the
// arrival glow, and the first one gets shown full size the way the reference client does.
let SEEN = new Set();
function visibleCards(v) {
  const out = [];
  (v.players || []).forEach(p => {
    (p.field || []).forEach(c => out.push(c));
    (p.legends || []).forEach(l => { if (l.name) out.push(l); });   // a Legend still face-down has none
    ((p.eddies && p.eddies.list) || []).forEach(c => out.push(c));
  });
  return out;
}
function arrivals(v) {
  const now = new Set(), fresh = [];
  visibleCards(v).forEach(c => {
    if (c.inst == null) return;
    now.add(c.inst);
    if (!SEEN.has(c.inst)) fresh.push(c);
  });
  const opening = SEEN.size === 0;        // a new game: everything is new, so nothing is news
  SEEN = now;
  return opening ? [] : fresh;
}

// The card that just hit the board, shown full size for a beat. This is what makes a rival's turn
// readable: without it a card appears in a row of six and nothing tells you which one moved.
let SPOT_TIMER = null;
function showcase(c) {
  if (!c || !(CARDS[c.id] || {}).image) return;
  let box = $("#spotlight");
  if (!box) {
    box = el("div", "spotlight"); box.id = "spotlight";
    box.append(el("img"));
    document.body.append(box);
  }
  box.querySelector("img").src = `images/${c.id}.jpg`;
  box.classList.remove("show");
  void box.offsetWidth;                    // restart the animation on a repeat play
  box.classList.add("show");
  clearTimeout(SPOT_TIMER);
  SPOT_TIMER = setTimeout(() => box.classList.remove("show"), 1100);
}
// ---------------------------------------------------------------- log
// A wall of sentences is hard to scan for the thing that changed, so the two kinds of proper noun
// in it are marked: who did it, and which card. Both are matched against lists the client already
// holds — the player names in the view and every card name in CARDS — rather than guessed at from
// the sentence, so nothing is highlighted that is not actually one of them.
let LOG_RE = null;
function logPattern(who) {
  const esc = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const cards = [];
  for (const id in CARDS) {
    const d = CARDS[id];
    cards.push(d.subtitle ? `${d.name} — ${d.subtitle}` : d.name);
    if (d.subtitle) cards.push(d.name);          // some lines name the card without its subtitle
  }
  // longest first: "Goro Takemura — Losing His Way" must win over "Goro Takemura"
  const all = cards.concat(who).filter(Boolean).sort((a, b) => b.length - a.length);
  return new RegExp("(" + all.map(esc).join("|") + ")", "g");
}
function markLog(line, who) {
  const key = who.join("|") + "#" + Object.keys(CARDS).length;   // CARDS arrives asynchronously
  if (!LOG_RE || LOG_RE._key !== key) {
    LOG_RE = logPattern(who);
    LOG_RE._key = key;
  }
  LOG_RE.lastIndex = 0;
  const whoSet = new Set(who);
  return line.replace(/[&<>]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]))
             .replace(LOG_RE, (m) => `<b class="${whoSet.has(m) ? "who" : "cardname"}">${m}</b>`);
}

//: The card the player last clicked. It survives a re-render, the way a selection should.
let SELECTED = null;

function findOnBoard(v, inst) {
  for (const p of v.players || []) {
    for (const c of (p.hand || [])) if (c.inst === inst) return c;
    for (const c of (p.field || [])) if (c.inst === inst) return c;
    for (const l of (p.legends || [])) if (l.inst === inst) return l.name ? l : { inst, name: "Face-down Legend" };
    for (const c of ((p.eddies && p.eddies.list) || [])) if (c.inst === inst) return c;
  }
  return null;
}

const LOG_MIN_KEY = "cptcg.logmin";
function logMin() { try { return localStorage.getItem(LOG_MIN_KEY) === "1"; } catch (e) { return false; } }

function cardPanel(v, byInst, pend, myTurn, onAct) {
  const box = el("div", "panel cardinfo p-cardinfo");
  box.append(el("span", "lbl", "SELECTED CARD"));
  const c = SELECTED == null ? null : findOnBoard(v, SELECTED);
  if (!c) {
    box.append(el("div", "desc", "Select a card to see what it can do here."));
    return box;
  }
  box.append(el("div", "q", c.name + (c.subtitle ? ` — ${c.subtitle}` : "")));
  if (c.text) box.append(el("div", "ctext", c.text.replace(/\n/g, "<br>")));
  const acts = myTurn
    ? (byInst[SELECTED] || []).concat((pend.options || []).filter(o => o.kind === "Target" && o.inst === SELECTED))
    : [];
  if (!acts.length) {
    box.append(el("div", "desc", "This card has no card actions in the current phase."));
    return box;
  }
  const row = el("div", "opts");
  acts.forEach(o => { const b = el("button", "", o.label); b.onclick = () => onAct(o.index); row.append(b); });
  box.append(row);
  return box;
}

function hintFor(p) {
  const h = {
    MULLIGAN: "Keep your opening hand, or shuffle it back and draw 6 new cards. You may do this only once.",
    ORDER: "You won the d20 roll-off, so you choose. Going first means the first turn's draw and Gig, but your two left-most Legends start spent and don't ready on that turn.",
    GIG_DIE: "Start of your turn: take one die from your fixer area, roll it and add it to your Gig area. Click a glowing die, or a button. The d20 can only be taken when it is the last die left.",
    MAIN: "Your main phase. Do things in any order: play cards (pay their cost in €$ from ready Eddies and Legends), sell one card this turn for an Eddie, Call a Legend for 1 €$ (once per turn), GO SOLO a Legend, use abilities, and attack with ready Units that didn't enter this turn. Glowing cards can act — click them — and every legal action is also a button here. End the turn when you're done.",
    TARGET: "Declare the target of the attack: a spent rival Unit starts a fight (higher power wins, ties defeat both), or the rival's Gig area lets you steal 1 die plus 1 more per 10 power. The attacker is then spent and its ATTACK effects resolve.",
    REACTION: "A rival Unit is attacking. You may spend a ready BLOCKER Unit to redirect the attack to it, play a QUICK Program or ability by paying its cost, or Call a Legend for 1 €$ (if you haven't this turn). Pass to let the attack resolve.",
    PICK: "A card effect is asking you to choose. The buttons list every legal choice; where the choice is a die, the label shows which die and its value.",
  };
  return h[p.kind] || p.prompt || "";
}
function badge(label, val) { const b = el("div", "badge", `${label}<b>${val}</b>`); return b; }

// ---------------------------------------------------------------- dice
// A die is drawn as the solid it is — the shapes the reference client uses, and the ones on the
// table: a tetrahedron for the d4, a cube for the d6, an octahedron for the d8, a trapezohedron
// for the d10, a dodecahedron for the d12, an icosahedron for the d20. Outline only, with the
// rolled face in the middle. Everything is laid out in a 100x100 box and scaled by CSS.
const ring = (n, r, turn) => {
  const out = [];
  for (let i = 0; i < n; i++) {
    const a = -Math.PI / 2 + (2 * Math.PI * (i + (turn || 0))) / n;
    out.push([50 + r * Math.cos(a), 50 + r * Math.sin(a)]);
  }
  return out;
};
const poly = (pts) => pts.map(p => p.map(v => v.toFixed(1)).join(",")).join(" ");
const line = (a, b) => `<line x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}" x2="${b[0].toFixed(1)}" y2="${b[1].toFixed(1)}"/>`;
// The faint interior edges are what make an outline read as a solid rather than a road sign, so
// each shape carries its own few.
const DIE_ART = {
  4: () => {
    const A = [48, 6], B = [94, 74], C = [94, 94], D = [6, 94];
    return `<polygon points="${poly([A, B, C, D])}"/>${line(A, C)}`;
  },
  6: () => `<path d="M10,30 H72 V92 H10 Z"/><path d="M10,30 L30,8 H92 L72,30"/><path d="M72,92 L92,70 V8"/>`,
  8: () => {
    const h = ring(6, 47);
    return `<polygon points="${poly(h)}"/>${line(h[0], h[4])}${line(h[0], h[2])}${line(h[2], h[4])}`;
  },
  10: () => {
    const P = [[50, 3], [94, 33], [82, 66], [50, 98], [18, 66], [6, 33]];
    const m = [50, 58];
    return `<polygon points="${poly(P)}"/>${line(P[0], m)}${line(m, P[2])}${line(m, P[4])}` +
           line(P[5], m) + line(P[1], m);
  },
  12: () => {
    const o = ring(10, 47), i = ring(5, 27);
    return `<polygon points="${poly(o)}"/><polygon points="${poly(i)}"/>` +
           i.map((p, k) => line(p, o[2 * k])).join("");
  },
  20: () => {
    const o = ring(6, 47), i = ring(3, 30, 0.5);
    return `<polygon points="${poly(o)}"/><polygon points="${poly(i)}"/>` +
           i.map((p, k) => line(p, o[(2 * k + 1) % 6])).join("");
  },
};
// `face` is the rolled value, or null for a die still in the fixer, which shows its name instead.
function dieNode(kind, face, cls) {
  const d = el("div", "die " + (cls || ""));
  const art = (DIE_ART[kind] || DIE_ART[20])();
  d.innerHTML = `<svg viewBox="0 0 100 100" aria-hidden="true">${art}</svg>` +
                `<span class="face">${face == null ? "D" + kind : face}</span>`;
  d.dataset.kind = kind;
  // Not a `title`: that is the browser's white tooltip box, and nothing on the board pops one of
  // those over the cards. `data-hint` is drawn by the stylesheet, in the board's own colours.
  d.dataset.hint = "d" + kind + (face == null ? " · not rolled yet" : ` · rolled ${face}`) +
                   (cls && cls.indexOf("own") >= 0 ? " · yours" : cls && cls.indexOf("rival") >= 0 ? " · the rival's" : "");
  return d;
}

// The Gig area. A die keeps the colour of the player who brought it, so a die stolen from you sits
// in the rival's area still wearing your green — which is the whole story of the game at a glance.
function gigPanel(p, meSeat) {
  const g = el("div", "panel gigs");
  const list = el("div", "list");
  if (!p.gigs.length) list.append(el("span", "waiting", "No Gigs yet."));
  p.gigs.forEach(([k, v, owner]) => {
    list.append(dieNode(k, v, (owner == null ? p.seat : owner) === meSeat ? "own" : "rival"));
  });
  const score = el("div", "score");
  const n = el("div", "n", `${p.gigs.length}/7`);
  if (p.gigs.length >= 7) n.classList.add("hot");
  score.append(n, el("div", "c" + (p.seat === meSeat ? " own" : ""), p.gigs.length ? p.cred : "Null"));
  g.append(list, score);
  return g;
}
// The fixer: the dice not yet rolled, dim, named rather than numbered.
function diceTray(p, pick, pend, onAct) {
  const t = el("div", "panel dice");
  const can = new Set(pick ? pend.options.filter(o => o.kind === "Die").map(o => o.inst) : []);
  [4, 6, 8, 10, 12, 20].forEach(k => {
    if (!p.fixer.includes(k)) return;
    const d = dieNode(k, null, "fixer");
    if (can.has(k)) { d.classList.add("pick"); d.onclick = () => onAct(pend.options.find(o => o.kind === "Die" && o.inst === k).index); }
    t.append(d);
  });
  return t;
}

// ---------------------------------------------------------------- play
let PLAYBACK = null;        // a function that ends the rival-turn replay early, while one is running

// Play the rival's turn back move by move. Without this the board cuts from "end turn" straight to
// the next prompt and everything they did is only in the log. The server sends one frame per move
// that said something; the whole sequence is held to about seven seconds, and a click ends it.
function playRival(v) {
  const frames = v.frames;
  const step = Math.max(220, Math.round(Math.min(7000, frames.length * 850) / frames.length));
  // The frames carry the rival's lines, which are the tail of everything new. The head is what the
  // human's own action said, and it belongs on screen before their turn starts playing.
  const rivalLines = frames.reduce((n, f) => n + f.log.length, 0);
  let acc = LOG.concat(v.log.slice(0, Math.max(0, v.log.length - rivalLines))), i = 0, timer = null;
  return new Promise(resolve => {
    const stop = () => {
      if (!PLAYBACK) return;
      clearTimeout(timer); document.removeEventListener("click", stop, true); PLAYBACK = null; resolve();
    };
    PLAYBACK = stop;
    document.addEventListener("click", stop, true);
    const tick = () => {
      if (i >= frames.length) return stop();
      const f = frames[i++];
      acc = acc.concat(f.log);
      const fv = f.view; fv.log = acc; fv.human = v.human;
      const fresh = arrivals(fv);
      renderBoard($("#board"), fv, { interactive: true, watching: v.rival || "The rival", onSkip: stop,
                                     fresh: new Set(fresh.map(c => c.inst)) });
      showcase(f.played || fresh[0]);
      timer = setTimeout(tick, step);
    };
    tick();
  });
}

// ---- choosing what to spend
// The engine auto-pays (ruling 025) because making payment a decision multiplies the AI's branching
// factor. At a table you do get to choose, so when the human has more ready sources than the cost,
// ask. Between two face-down Eddies the choice changes nothing in the rules — no card ever reads
// which card is sitting in an Eddies area — but between an Eddie and a Legend it very much does,
// and the player is the one who should decide. "Let the game pick" is remembered per browser.
const AUTOPAY_KEY = "cptcg.autopay";
function autopay() { try { return localStorage.getItem(AUTOPAY_KEY) === "1"; } catch (e) { return false; } }

function askPayment(cost, sources) {
  // On the board, not in a dialog: the sources are cards sitting in front of you, so the thing to
  // click is the card. The panel only keeps the count and the way out.
  return new Promise(resolve => {
    const board = $("#board");
    const picked = [];
    const nodes = new Map();
    sources.forEach(src => {
      const n = board.querySelector('.card[data-inst="' + src.inst + '"]');
      if (n) nodes.set(src.inst, n);
    });
    if (!nodes.size) return resolve([]);           // nothing to point at: let the game pay

    // Only ever one of these: a second request while the first is open replaces it, rather than
    // stacking two identical panels down the column.
    board.querySelectorAll(".paypanel").forEach(x => x.remove());
    const panel = el("div", "panel paypanel");
    panel.append(el("span", "lbl", "PAY COST"));
    const q = el("div", "q", `Spend ${cost} ready ${cost === 1 ? "Eddie or Legend" : "Eddies or Legends"}`);
    const count = el("div", "count", `Selected 0 of ${cost}`);
    const hint = el("div", "desc", "Click the glowing cards. Between two Eddies it changes nothing — no card ever reads which one you spent — but spending a Legend keeps an Eddie ready for later.");
    const row = el("div", "opts");
    const auto = el("button", "", "LET THE GAME PICK");
    const cancel = el("button", "", "CANCEL");
    row.append(auto, cancel);
    panel.append(q, count, hint, row);

    const done = (val) => {
      panel.remove();
      nodes.forEach(n => { n.classList.remove("payable", "paypicked"); n.onclick = n._payPrev || null; });
      document.removeEventListener("keydown", onKey);
      resolve(val);
    };
    const onKey = (e) => { if (e.key === "Escape") done(null); };
    auto.onclick = () => done([]);
    cancel.onclick = () => done(null);
    nodes.forEach((n, inst) => {
      n.classList.add("payable");
      n._payPrev = n.onclick;                      // the card's own action menu, restored on the way out
      n.onclick = (e) => {
        e.stopPropagation();
        const at = picked.indexOf(inst);
        if (at >= 0) { picked.splice(at, 1); n.classList.remove("paypicked"); }
        else { picked.push(inst); n.classList.add("paypicked"); }
        count.textContent = `Selected ${picked.length} of ${cost}`;
        if (picked.length === cost) done(picked.slice());
      };
    });
    document.addEventListener("keydown", onKey);
    const prompt = board.querySelector(".p-prompt");
    if (prompt) prompt.before(panel); else board.append(panel);
  });
}

async function act(verbOrIndex) {
  if (!GAME || PLAYBACK) return;
  const since = LOG.length;
  let pay = null;
  if (typeof verbOrIndex === "number" && !autopay()) {
    const pend = GAME.view && GAME.view.pending;
    const opt = pend && pend.options && pend.options.find(o => o.index === verbOrIndex);
    const me = GAME.view && (GAME.view.perspective == null ? 0 : GAME.view.perspective);
    const src = (opt && opt.cost > 0 && GAME.view.players[me].pay_sources) || [];
    if (opt && opt.cost > 0 && src.length > opt.cost) {
      pay = await askPayment(opt.cost, src);
      if (pay === null) return;            // cancelled: the action was never sent
      if (!pay.length) pay = null;         // "let the game pick" is just the default order
    }
  }
  const about = typeof verbOrIndex === "number" && GAME.view.pending
    ? cardOfOption(GAME.view, (GAME.view.pending.options || []).find(o => o.index === verbOrIndex))
    : null;
  let v;
  if (verbOrIndex === "undo") { LOG = []; v = await api(`/api/games/${GAME.id}/undo`, { since: 0 }); }
  else if (verbOrIndex === "concede") v = await api(`/api/games/${GAME.id}/concede`, { since });
  else v = await api(`/api/games/${GAME.id}/act`, { index: verbOrIndex, since, pay });
  if (v.frames && v.frames.length) await playRival(v);
  LOG = LOG.concat(v.log);
  GAME.view = v; v.log = LOG;
  const fresh = arrivals(v);
  renderBoard($("#board"), v, { interactive: true, onAct: act, fresh: new Set(fresh.map(c => c.inst)) });
  // The card the move was about comes first: a Program resolves and goes to the trash, so diffing
  // the board would never show the one card that mattered.
  showcase(about || fresh[0]);
}

//: Which card an option is about, looked up in the board we were holding when it was chosen.
function cardOfOption(v, o) {
  if (!o || o.inst == null || o.inst < 0) return null;
  if (!["Play", "GoSolo", "Sell", "Activate", "Attack"].includes(o.kind)) return null;
  for (const p of v.players || []) {
    for (const c of (p.hand || [])) if (c.inst === o.inst) return c;
    for (const c of (p.field || [])) if (c.inst === o.inst) return c;
    for (const l of (p.legends || [])) if (l.inst === o.inst && l.name) return l;
  }
  return null;
}
async function newGame() {
  const body = { deck_me: $("#deckMe").value, deck_ai: $("#deckAi").value, agent: $("#agent").value, seat: +$("#seat").value };
  if ($("#seed").value) body.seed = +$("#seed").value;
  const r = await api("/api/games", body);
  GAME = { id: r.id, view: r.view };
  LOG = r.view.log.slice();
  SEEN = new Set();
  arrivals(r.view);                        // seed the board history; the opening board is not news
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
// The report page is drawn by report.js from the /api/report JSON; this page lends it the card
// map, the hover/tap preview, the API and a way into BUILD.
function renderReport(t) { Report.render($("#report"), t, { cards: CARDS, preview: (c, touch) => showPreview(`images/${c.id}.jpg`, c, touch), unpreview: hidePreview, openInBuild: openDeckInBuild, api }); }
// Open a report's deck in BUILD: the saved file when the report knows it, else a deck of the same
// name from the deck lists, else the list exactly as the report carries it (validated on load).
async function openDeckInBuild(d) {
  let deck = null;
  const load = async (path) => { try { return await api(`/api/deck?path=${encodeURIComponent(path)}`); } catch (e) { return null; } };
  if (d.path) deck = await load(d.path);
  if (!deck) { const same = (await api("/api/decks")).find(x => x.name === d.name); if (same) deck = await load(same.path); }
  if (!deck) {
    try { deck = { ...(await api("/api/validate", { name: d.name, legends: d.legends, main: d.main })), name: d.name, legends: d.legends, main: d.main }; }
    catch (e) { alert("could not open this deck: " + e.message); return; }
  }
  bLoadDeck(deck);
  $("nav button[data-mode=build]").click();
  // On a narrow screen the builder stacks the card library above the deck sheet, so land the
  // reader on the sheet (name, Legends, list) rather than on the top of the library.
  const sheet = $(".decksheet");
  if (sheet && window.innerWidth <= 1100) sheet.scrollIntoView({ block: "start" }); else window.scrollTo(0, 0);
  toast(`${deck.name} loaded in BUILD (${Object.values(deck.main || {}).reduce((a, n) => a + n, 0)} cards)`);
}
// A short message that fades: confirmation the reader can see without a dialog to dismiss.
function toast(text) {
  let t = $("#toast");
  if (!t) { t = el("div", "toast"); t.id = "toast"; document.body.append(t); }
  t.textContent = text; t.classList.add("show");
  clearTimeout(t._timer); t._timer = setTimeout(() => t.classList.remove("show"), 2500);
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
    if (j.est_games == null && j.params) j.est_games = j.params.est_games;
    const head = el("div", "head");
    head.append(el("b", "", j.kind.toUpperCase()), el("span", "", j.params.name || j.id), el("span", "dim", `${fmtDuration(j.elapsed)}`), el("span", "st " + j.status, j.status));
    if (j.status === "running") { const c = el("button", "cancel", "CANCEL"); c.onclick = async () => { c.disabled = true; try { await api(`/api/jobs/${j.id}/cancel`, {}); } catch (e) { alert(e.message); } pollJobs(); }; head.append(c); }
    d.append(head);
    const p = j.progress;
    if (p && p.phase) {
      // Structural progress from the job itself: what it is doing, how many of its comparisons are
      // settled, and the games it can still play at best and at worst. The time left applies the
      // job's own measured speed to that range; the games counter is information, not a target.
      const parts = [p.phase];
      if (p.steps) parts.push(`${p.step} of ${p.steps} ${p.unit || "steps"} done`);
      if (j.status === "running") {
        const own = j.games >= 40 && j.elapsed >= 3;
        const rate = own ? j.games / j.elapsed : gamesPerSecond();
        if (p.remaining_max > 0) parts.push(`about ${fmtSpan(p.remaining_min / rate, p.remaining_max / rate)} left${own ? "" : " (rough until the job has run a while)"}`);
        else parts.push("finishing");
        if (j.games > 0) parts.push(`${j.games.toLocaleString()} games so far` + (own ? ` (${rate.toFixed(1)} per second)` : ""));
      } else if (j.games > 0 && !/\bgames\b/.test(p.phase)) parts.push(`${j.games.toLocaleString()} games`);   // unless the phase already says it
      d.append(el("div", "dim prog-text", parts.join(" · ")));
      const bar = el("div", "prog"); const fill = el("i");
      fill.style.width = `${p.steps ? Math.min(100, Math.round(100 * p.step / p.steps)) : (j.status === "running" ? 0 : 100)}%`;
      bar.append(fill); d.append(bar);
    } else if (j.games != null && (j.status === "running" || j.games > 0)) {
      // A job without a progress object (started by an older engine): games and the old rough guess.
      let txt = `${j.games.toLocaleString()} games played`;
      if (j.status === "running" && j.est_games && j.games > 0) {
        const rate = j.games / Math.max(1, j.elapsed);
        const left = Math.max(0, j.est_games - j.games) / rate;
        txt += ` · roughly ${fmtDuration(left)} left (${rate.toFixed(1)} games/s)`;
      } else if (j.status === "running" && j.est_games) txt += ` of roughly ${j.est_games.toLocaleString()}`;
      d.append(el("div", "dim prog-text", txt));
    }
    if (j.decks && j.decks.length) d.append(el("div", "dim", `${j.decks.length} decks saved under ${j.decks[0].split("/").slice(0, -1).join("/")}/ — they are now in the deck lists.`));
    if (j.reports.length) { const r = el("div", "reps"); j.reports.forEach((f, i) => { const a = el("a", "", j.kind === "league" ? `gen ${i + 1}` : "report"); a.onclick = () => openReport(f); r.append(a); }); d.append(r); }
    const pre = el("pre", "", j.lines.slice(-12).join("\n")); d.append(pre);
    root.append(d);
    pre.scrollTop = pre.scrollHeight;                    // the newest line, which matches the phase above, stays in view
  });
}
async function pollJobs() {
  const jobs = await api("/api/jobs");
  renderJobs(jobs);
  const running = jobs.some(j => j.status === "running");
  if (running && !JOBTIMER) JOBTIMER = setInterval(async () => {
    const js = await api("/api/jobs"); renderJobs(js);
    if (!js.some(j => j.status === "running")) { clearInterval(JOBTIMER); JOBTIMER = null; refreshReports(); refreshDecks(); refreshArchetypes().catch(() => {}); ESTIMATES.forEach(f => f()); }
  }, 1500);
}
async function refreshReports() {
  const sel = $("#reportFile"); const cur = sel.value; sel.innerHTML = "";
  (await api("/api/reports")).forEach(f => { const o = el("option", "", f); o.value = f; sel.append(o); });
  if (cur) sel.value = cur;
}
function fillDeckChecklist(decks) {
  const tl = $("#tDecks");   // change events bubble to #tDecks, where the estimate listens
  const was = new Set([...tl.querySelectorAll("input:checked")].map(c => c.value)); tl.innerHTML = "";
  decks.forEach(d => { const l = el("label"); const c = el("input"); c.type = "checkbox"; c.value = d.path; c.checked = was.size ? was.has(d.path) : (window.CPTCG_BRIDGE ? /the_heist|embracing_power/.test(d.path) : d.path.startsWith("data/decks/sample_")); l.append(c, `${d.name} `, el("small", "", `(${d.size}) ${d.legends.map(x => CARDS[x]?.name || x).join(" / ")}`)); tl.append(l); });
}
async function refreshDecks() {
  const decks = (await api("/api/decks")).filter(d => d.ok);
  fillDeckChecklist(decks);
  for (const sel of [$("#deckMe"), $("#deckAi"), $("#bLoad")]) {
    const have = new Set([...sel.options].map(o => o.value));
    decks.forEach(d => { if (!have.has(d.path)) { const o = el("option", "", sel.id === "bLoad" ? `${d.name} (${d.size})` : `${d.name} (${d.size}) — ${d.path}`); o.value = d.path; sel.append(o); } });
  }
}
// The builders a league or a batch can use: the Explorer (invents a deck shape) and every
// archetype learned from play so far, each with its pooled win rate so the reader can judge it.
function archetypeChecklist(root, arche) {
  const was = new Set([...root.querySelectorAll("input:checked")].map(c => c.value)); const had = root.children.length > 0;
  root.innerHTML = "";
  // Each row: the name and record on one line, the description wrapped underneath — a phone
  // never shows a title tooltip, so the description has to be visible text.
  const add = (id, name, record, desc) => {
    const l = el("label"); const c = el("input"); c.type = "checkbox"; c.value = id; c.checked = had ? was.has(id) : true;
    const txt = el("span", "txt"); txt.append(el("b", "", name), record ? el("span", "rec", " · " + record) : "", el("small", "", desc || ""));
    l.append(c, txt); root.append(l);
  };
  add("explorer", "Explorer", "", arche.builders.find(b => b.id === "explorer")?.description || "invents a deck shape at random — how new archetypes get found");
  const plural = (n, w) => `${n.toLocaleString()} ${w}${n === 1 ? "" : "s"}`;
  arche.archetypes.forEach(a => add(a.id, a.name,
    `won ${Math.round(100 * a.win_rate)}% of ${plural(a.games, "game")} · ${plural(a.decks, "deck")}${a.lineages ? " · " + a.separation_word : ""}`, a.description));
  if (!arche.archetypes.length) root.append(el("div", "hint", `No archetypes learned yet: ${arche.distinct ?? arche.decks} of the ${arche.needed} distinct decks needed have played here (one-card variants of a list count once). Every builder explores until then; each finished tournament or league adds its decks, and the groups appear on their own.`));
  else if (arche.archetypes.length === 1) root.append(el("div", "hint", "One group so far: the decks that have played do not split into kinds yet. More varied decks (Explorer builds, hand-built lists) will let groups appear."));
}
let ARCHETYPES = null;
async function refreshArchetypes() {
  ARCHETYPES = await api("/api/archetypes");
  for (const id of ["#lArchetypes", "#gArchetypes"]) archetypeChecklist($(id), ARCHETYPES);
  const ssel = $("#bArchetype"); if (ssel) { const cur = ssel.value; ssel.innerHTML = ""; ARCHETYPES.builders.forEach(b => { const o = el("option", "", b.name); o.value = b.id; o.title = b.description; ssel.append(o); }); if ([...ssel.options].some(o => o.value === cur)) ssel.value = cur; ssel.dispatchEvent(new Event("change")); }
}
// Job sizes, so nobody starts an hours-long run by accident. The games come from POST
// /api/estimate — the same budget formulas the running job reports against — as a range: the low
// end if every comparison settles at its first batch, the high end if none does. Games per second:
// a browser engine plays ~2-3 heuristic games/s per core and the LAB pools one engine per core; the
// local server uses every core. The bridge reports the rate measured on this device once a job has run.
function gamesPerSecond() { return window.CPTCG_BRIDGE ? window.CPTCG_BRIDGE.rate() : 15; }
function picked(sel) { return [...document.querySelectorAll(`${sel} input:checked`)].map(c => c.value); }
// The body a START button posts to /api/jobs; the estimate sends the same one to /api/estimate.
function jobBody(kind) {
  if (kind === "tourney") return { kind, name: $("#tName").value, decks: picked("#tDecks"), games: +$("#tGames").value, agent: $("#tAgent").value, seed: +$("#tSeed").value };
  if (kind === "league") return { kind, name: $("#lName").value, archetypes: picked("#lArchetypes"), builders: +$("#lBuilders").value, generations: +$("#lGens").value, steps: +$("#lSteps").value, games: +$("#lGames").value, seed: +$("#lSeed").value, knowledge: $("#lKnowledge").checked, hof: $("#lHof").checked };
  return { kind: "generate", name: $("#gName").value, archetypes: picked("#gArchetypes"), count: +$("#gCount").value, seed: +$("#gSeed").value, screen: +$("#gScreen").value, keep: +$("#gKeep").value };
}
// Under two minutes the answer is seconds: "about 100 s left" is a number a reader can act on,
// "about 2 min left" rounds away most of what is left.
function fmtDuration(secs) { return secs <= 120 ? `${Math.round(secs)} s` : secs < 5400 ? `${Math.round(secs / 60)} min` : `${(secs / 3600).toFixed(1)} h`; }
// A range collapses to one value when the ends are within 25% of each other.
function fmtRange(lo, hi, fmt = x => x.toLocaleString()) { return hi <= 0 || hi / Math.max(lo, 1e-9) < 1.25 ? fmt(hi) : `${fmt(lo)}–${fmt(hi)}`; }
// A time range in one unit ("3–20 min"), collapsing like fmtRange.
function fmtSpan(lo, hi) {
  if (hi <= 0 || hi / Math.max(lo, 1e-9) < 1.25) return fmtDuration(hi);
  if (hi <= 120) return `${Math.round(lo)}–${Math.round(hi)} s`;
  if (hi < 5400) return `${Math.max(1, Math.round(lo / 60))}–${Math.round(hi / 60)} min`;
  if (lo >= 5400) return `${(lo / 3600).toFixed(1)}–${(hi / 3600).toFixed(1)} h`;
  return `${fmtDuration(lo)} to ${fmtDuration(hi)}`;
}
async function estimate(kind) {
  const body = jobBody(kind);
  const est = await api("/api/estimate", body);
  const rate = gamesPerSecond();
  const extra = kind === "generate" ? (body.count || 0) * 0.4 : 0;       // building a deck takes a moment even without games
  const lo = est.games_min / rate + extra, hi = est.games_max / rate + extra;
  const b = window.CPTCG_BRIDGE;
  const where = b ? (b.measured() ? " on this device (speed measured on an earlier job)" : ` on this device (${b.pool >= 2 ? b.pool + " engines" : "1 engine"}, a rough speed until a job has run)`) : " on this machine";
  const why = est.games_max > est.games_min ? " — the low end if every comparison settles at its first batch, the high end if none does; most runs land near the low end, and the job card narrows the range as it runs" : "";
  const warn = hi > 1200 ? " — that is long; consider fewer games, steps or builders" : "";
  const games = est.games_max > 0 ? `≈ ${fmtRange(est.games_min, est.games_max)} games` : `no games (${body.count || est.steps} decks to build, nothing to screen)`;
  return { text: `${games} · about ${fmtSpan(lo, hi)}${where}${why}${warn}`, warn: !!warn };
}
const ESTIMATES = [];       // refreshed when a job finishes (the measured speed changes the numbers)
function wireEstimate(kind, form, inputs) {
  const note = el("div", "estimate"); form.append(note);
  let timer = null, seq = 0;
  const run = async () => {
    const mine = ++seq;
    try { const r = await estimate(kind); if (mine !== seq) return; note.textContent = r.text; note.classList.toggle("warn", r.warn); }
    catch (e) { if (mine === seq) { note.textContent = "estimate unavailable: " + e.message; note.classList.remove("warn"); } }
  };
  const upd = () => { clearTimeout(timer); timer = setTimeout(run, 250); };   // debounced: one request per pause in typing
  ESTIMATES.push(upd);
  inputs.forEach(sel => document.querySelectorAll(sel).forEach(i => { i.addEventListener("input", upd); i.addEventListener("change", upd); }));
  upd();
  return upd;
}

async function initLab(decks, arche) {
  if (window.CPTCG_BRIDGE) {                    // browser build: one thread — start small
    $("#tGames").value = 40; $("#lBuilders").value = 3; $("#lGens").value = 1; $("#lSteps").value = 1; $("#lGames").value = 20; $("#gCount").value = 12;
  }
  fillDeckChecklist(decks);
  archetypeChecklist($("#gArchetypes"), arche);
  $("#gRun").onclick = async () => {
    const body = jobBody("generate");
    if (!body.archetypes.length) { alert("tick the Explorer or at least one archetype"); return; }
    try { await api("/api/jobs", body); }
    catch (e) { alert(e.message); return; }
    pollJobs();
  };
  archetypeChecklist($("#lArchetypes"), arche);
  $("#tRun").onclick = async () => {
    const body = jobBody("tourney");
    if (body.decks.length < 2) { alert("pick at least two decks"); return; }
    try { await api("/api/jobs", body); }
    catch (e) { alert(e.message); return; }
    pollJobs();
  };
  const updT = wireEstimate("tourney", $("#tRun").closest(".setup"), ["#tDecks input", "#tGames"]);
  wireEstimate("league", $("#lRun").closest(".setup"), ["#lBuilders", "#lGens", "#lSteps", "#lGames", "#lHof"]);
  wireEstimate("generate", $("#gRun").closest(".setup"), ["#gCount", "#gScreen"]);
  $("#tDecks").addEventListener("change", updT);
  $("#lRun").onclick = async () => {
    const body = jobBody("league");
    if (!body.archetypes.length) { alert("tick the Explorer or at least one archetype"); return; }
    try { await api("/api/jobs", body); }
    catch (e) { alert(e.message); return; }
    pollJobs();
  };
  pollJobs();
}

// ---------------------------------------------------------------- cards
function renderCardGrid(q) {
  const grid = $("#cardGrid"); grid.innerHTML = "";
  const s = (q || "").toLowerCase(), set = $("#cardSet").value;
  const arch = $("#cardArch") ? $("#cardArch").value : "";
  Object.values(CARDS).filter(c => (!set || c.set === set)
      && (!arch || ((LINKS[c.id] || {}).archetypes || []).includes(arch))
      && (!s || `${c.name} ${c.subtitle || ""} ${c.text} ${c.tags.join(" ")} ${c.keywords.join(" ")} ${c.type} ${c.color}`.toLowerCase().includes(s)))
    .slice(0, 200).forEach(c => {
      const n = cardNode(c);
      // One tap or click opens the guide, on every device. cardNode() takes onclick for the image
      // preview on a touch-only screen, and leaving that in place cost the feature its front door:
      // a phone tap opened a picture and the guide needed a double-tap nobody would guess. Nothing
      // is lost by overriding it here — the guide shows the same face at the same size, and the
      // long-press preview cardNode installs still works for a quick look without leaving the grid.
      n.onclick = () => openCardGuide(c.id);
      n.title = "open the strategy guide";
      grid.append(n);
    });
}

// ---------------------------------------------------------------- the card guide
// Every card's page: what it does, what it combos with, and what wants it. The connections come
// from data/strategy/graph.json — each of the 151 cards hand-tagged with what it CREATES and what
// it is PAID FOR — so "works with" is a fact about the two texts rather than an opinion.
let LINKS = {}, TOKENS = {}, ARCHES = {}, GUIDE_OPEN = null;

async function loadCardLinks() {
  try {
    const d = await api("/api/cardlinks");
    LINKS = d.links || {}; TOKENS = d.tokens || {}; ARCHES = d.archetypes || {};
  } catch (e) { LINKS = {}; }                    // the pool still browses without the map
  const sel = $("#cardArch");
  if (sel && Object.keys(ARCHES).length) {
    Object.keys(ARCHES).sort().forEach(a => {
      const o = el("option", "", `${a} (${ARCHES[a].length})`); o.value = a; sel.append(o);
    });
  }
}

function tokenLabel(tok) {
  if (tok.startsWith("tribe.")) return tok.slice(6);
  return TOKENS[tok] || tok;
}

function linkRow(list, dir) {
  // Group by the reason, so a card reads as "these six all want my min Gig" rather than as a
  // flat list of names whose connection you have to reconstruct.
  const by = {};
  list.forEach(l => { (by[l.token] = by[l.token] || []).push(l); });
  const wrap = el("div", "links");
  Object.keys(by).sort((a, b) => by[a].length - by[b].length).forEach(tok => {
    const g = el("div", "lgroup");
    const kinds = new Set(by[tok].map(l => l.kind));
    g.append(el("div", "why", `${dir} <b>${tokenLabel(tok)}</b>` +
      (kinds.has("indirect") && !kinds.has("direct") ? " <i class=dim>(one step away)</i>" : "")));
    const row = el("div", "row");
    by[tok].slice(0, 14).forEach(l => {
      const c = CARDS[l.id]; if (!c) return;
      const chip = el("button", "chip" + (l.kind === "indirect" ? " soft" : ""),
        c.subtitle ? `${c.name} <span class=sub>${c.subtitle}</span>` : c.name);
      chip.title = c.subtitle ? `${c.name} — ${c.subtitle}` : c.name;
      chip.onclick = () => openCardGuide(l.id);
      row.append(chip);
    });
    if (by[tok].length > 14) row.append(el("span", "dim", `+${by[tok].length - 14} more`));
    g.append(row); wrap.append(g);
  });
  return wrap;
}

function openCardGuide(id) {
  const c = CARDS[id]; if (!c) return;
  if (!GUIDE_OPEN) {
    GUIDE_OPEN = el("div", "guideview");
    GUIDE_OPEN.append(el("div", "sheet"));
    document.body.append(GUIDE_OPEN);
    GUIDE_OPEN.onclick = (e) => { if (e.target === GUIDE_OPEN) closeCardGuide(); };
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeCardGuide(); });
  }
  const sheet = GUIDE_OPEN.querySelector(".sheet");
  sheet.innerHTML = "";
  const head = el("div", "head");
  head.append(el("h3", "", c.name + (c.subtitle ? ` <small class=dim>— ${c.subtitle}</small>` : "")));
  const x = el("button", "x", "✕"); x.onclick = closeCardGuide; head.append(x);
  sheet.append(head);

  const body = el("div", "gbody");
  const left = el("div", "gleft");
  if (c.image) { const img = el("img"); img.src = `images/${c.id}.jpg`; img.alt = c.name; left.append(img); }
  const stats = el("div", "gstats");
  [["type", c.type], ["colour", c.color], ["cost", c.cost ?? "—"], ["power", c.power ?? "—"],
   ["RAM", c.ram]].forEach(([k, v]) => stats.append(el("span", "", `${k} <b>${v}</b>`)));
  left.append(stats);
  if (c.tags && c.tags.length) left.append(el("div", "gtags", c.tags.join(" · ")));
  body.append(left);

  const right = el("div", "gright");
  if (c.text) right.append(el("pre", "gtext", c.text));
  if (!c.verified) right.append(el("div", "warn", "This card is unverified — its printed face was never captured, so the values shown are placeholders."));

  const L = LINKS[c.id];
  if (L) {
    if (L.archetypes && L.archetypes.length) {
      const a = el("div", "garch");
      a.append(el("span", "dim", "plays in: "));
      L.archetypes.forEach(k => a.append(el("span", "tag", k)));
      right.append(a);
    }
    const guide = c.guide;
    if (guide && guide.guide) {
      right.append(el("h4", "", "HOW IT PLAYS"));
      right.append(el("p", "", guide.guide));
      if (guide.tips && guide.tips.length) {
        const ul = el("ul", "tips");
        guide.tips.forEach(tp => ul.append(el("li", "", tp)));
        right.append(ul);
      }
    }
    const sections = [["WHAT THIS TURNS ON", L.enables, "sets up"],
                      ["WHAT SETS THIS UP", L.enabled_by, "needs"],
                      ["WANTS THE SAME BOARD", L.co_need, "both want"],
                      ["TRIBAL", L.tribal, "tag"]];
    let any = false;
    sections.forEach(([title, list, dir]) => {
      if (!list || !list.length) return;
      any = true;
      right.append(el("h4", "", `${title} <span class=dim>· ${list.length}</span>`));
      right.append(linkRow(list, dir));
    });
    if (!any) right.append(el("p", "dim", "No interactions with the rest of the pool — this card does its job on its own."));
  }
  body.append(right);
  sheet.append(body);
  GUIDE_OPEN.classList.add("show");
  sheet.scrollTop = 0;
}

function closeCardGuide() { if (GUIDE_OPEN) GUIDE_OPEN.classList.remove("show"); }

// ---------------------------------------------------------------- card preview
// The board draws cards small; hovering any card shows its face at full resolution, like the sim.
let PREVIEW = null;
function showPreview(src, c, touch) {
  if (!PREVIEW) { PREVIEW = el("div", "preview"); PREVIEW.append(el("img")); document.body.append(PREVIEW); PREVIEW.onclick = (e) => { e.stopPropagation(); hidePreview(); }; }
  const img = PREVIEW.querySelector("img"); img.src = src; img.alt = c.name;
  PREVIEW.classList.add("show"); PREVIEW.classList.toggle("touch", !!touch);
  // Centred, not following the cursor: the card lands in the same place every time, so reading it
  // is a glance rather than a chase, and moving along a row of cards swaps one image for another.
  // pointer-events stay off, so the preview never steals the hover from the card underneath it.
  PREVIEW.style.left = ""; PREVIEW.style.top = "";
}
function hidePreview() { if (PREVIEW) PREVIEW.classList.remove("show", "touch"); }

// ---------------------------------------------------------------- looking through a pile
// The trash is public — every card in it was played face up — so it is something to read rather
// than remember. Clicking the pile lays the whole thing out at a size the text can be read at.
let PILE = null;
function openPile(title, cards) {
  if (!PILE) {
    PILE = el("div", "pileview");
    PILE.append(el("div", "sheet"));
    document.body.append(PILE);
    PILE.onclick = (e) => { if (e.target === PILE) closePile(); };
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePile(); });
  }
  const sheet = PILE.querySelector(".sheet");
  sheet.innerHTML = "";
  const head = el("div", "head");
  head.append(el("div", "t", title.toUpperCase()),
              el("div", "c", `${cards.length} card${cards.length === 1 ? "" : "s"}`));
  const close = el("button", "", "CLOSE"); close.onclick = closePile;
  head.append(close);
  const grid = el("div", "pilegrid");
  // Newest on top of a pile, so newest first here too.
  cards.slice().reverse().forEach(c => grid.append(cardNode(c)));
  sheet.append(head, grid);
  PILE.classList.add("show");
}
function closePile() { if (PILE) PILE.classList.remove("show"); }

// ---------------------------------------------------------------- deck builder
// The page holds the deck being edited; legality, RAM limits and the saved file all come from
// the server so the rules live in exactly one place (deck/validate.py).
let B = { name: "New deck", legends: [], main: {}, note: "", meta: {}, v: null, path: null };
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
  const s = $("#bSearch").value.toLowerCase(), t = $("#bType").value, col = $("#bColor").value, cost = $("#bCost").value, legalOnly = $("#bLegal").checked, set = $("#bSet").value;
  const list = Object.values(CARDS).filter(c => {
    if (t && c.type !== t) return false;
    if (set && c.set !== set) return false;
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
  const groups = groupDeck(B.main, CARDS);          // shared with the report (report.js)
  groups.forEach(([type, rows]) => {
    if (!rows.length) return;
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
  groups.forEach(([type, rows]) => { if (rows.length) { lines.push(`### ${type}s`); rows.forEach(([c, n]) => lines.push(`${n} ${c.name}${c.subtitle ? " — " + c.subtitle : ""}`)); } });
  $("#bText").value = lines.join("\n");
}

function bLoadDeck(d) {
  // meta (what built the deck, which archetype it aimed at) rides along so saving keeps the label
  B = { name: d.name, legends: d.legends.slice(), main: { ...d.main }, note: d.note || "", meta: { ...(d.meta || {}) }, v: d, path: d.path || null };
  renderDeckSheet(); renderLibrary();
}

async function initBuilder(decks) {
  const sel = $("#bLoad");
  decks.forEach(d => { const o = el("option", "", `${d.name} (${d.size})`); o.value = d.path; sel.append(o); });
  sel.onchange = async () => { if (!sel.value) return; bLoadDeck(await api(`/api/deck?path=${encodeURIComponent(sel.value)}`)); };
  ["#bSearch", "#bType", "#bColor", "#bCost", "#bLegal", "#bSet"].forEach(id => { $(id).oninput = renderLibrary; $(id).onchange = renderLibrary; });
  $("#bName").onchange = (e) => { B.name = e.target.value; renderDeckSheet(); };
  $("#bClear").onclick = () => { B = { name: "New deck", legends: [], main: {}, note: "", meta: {}, v: null, path: null }; renderDeckSheet(); renderLibrary(); };
  $("#bExport").onclick = () => { const t = $("#bText"); t.classList.toggle("hidden"); if (!t.classList.contains("hidden")) { t.select(); } };
  $("#bSave").onclick = async () => {
    B.name = $("#bName").value || "untitled";
    const body = { name: B.name, legends: B.legends, main: B.main, note: B.note, meta: B.meta };
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
  // AI build: the Explorer, every archetype learned from play (built toward its centre), the old
  // unopinionated builder and a random deck. The list is refreshed when a lab job finishes.
  const ssel = $("#bArchetype");
  const showDesc = () => { const b = (ARCHETYPES?.builders || []).find(x => x.id === ssel.value); $("#bArchetypeDesc").textContent = b ? b.description : ""; };
  ssel.onchange = showDesc;
  await refreshArchetypes();
  $("#bBuild").onclick = async () => {
    const keep = $("#bKeepLegends").checked && B.legends.length === 3;
    try { bLoadDeck(await api("/api/build", { mode: ssel.value, legends: keep ? B.legends : null, name: $("#bName").value })); }
    catch (e) { alert(e.message); }
  };
  renderDeckSheet(); renderLibrary();
}

// ---------------------------------------------------------------- init
async function init() {
  if (window.CPTCG_BRIDGE) await window.CPTCG_BRIDGE.ready;
  const cards = await api("/api/cards");
  cards.forEach(c => { CARDS[c.id] = c; });
  await loadCardLinks();
  const decks = await api("/api/decks");
  for (const sel of [$("#deckMe"), $("#deckAi")]) {
    decks.filter(d => d.ok).forEach(d => { const o = el("option", "", `${d.name} (${d.size}) — ${d.path}`); o.value = d.path; sel.append(o); });
  }
  const pick = (sel, path, fallback) => { const o = [...sel.options].find(x => x.value === path); if (o) sel.value = path; else if (sel.options.length > fallback) sel.selectedIndex = fallback; };
  pick($("#deckMe"), "data/decks/the_heist.json", 0);            // the retail starters are the default matchup
  pick($("#deckAi"), "data/decks/embracing_power.json", 1);
  $("#newGame").onclick = () => newGame().catch(e => alert(e.message));
  const reps = await api("/api/replays");
  reps.forEach(f => { const o = el("option", "", f); o.value = f; $("#replayFile").append(o); });
  if (!reps.length) { const o = el("option", "", "no replays yet — EXPORT a game from PLAY, or run: cptcg sim --replays out/replays"); o.value = ""; o.disabled = true; $("#replayFile").append(o); }
  $("#loadReplay").onclick = async () => { RP.file = $("#replayFile").value; $("#replayControls").classList.remove("hidden"); await rpGo(0); };
  $("#rpPrev").onclick = () => rpGo(Math.max(0, RP.step - 1));
  $("#rpNext").onclick = () => rpGo(Math.min(RP.steps - 1, RP.step + 1));
  $("#rpStart").onclick = () => rpGo(0);
  $("#rpEnd").onclick = () => rpGo(RP.steps - 1);
  $("#rpSlider").oninput = (e) => rpGo(+e.target.value);
  $("#rpAuto").onclick = () => { if (RP.auto) { clearInterval(RP.auto); RP.auto = null; } else RP.auto = setInterval(() => { if (RP.step < RP.steps - 1) rpGo(RP.step + 1); else { clearInterval(RP.auto); RP.auto = null; } }, 900); };
  const reports = await api("/api/reports");
  reports.forEach(f => { const o = el("option", "", f); o.value = f; $("#reportFile").append(o); });
  if (!reports.length) { const o = el("option", "", "no reports yet — run a tournament or league on the left"); o.value = ""; o.disabled = true; $("#reportFile").append(o); }
  $("#loadReport").onclick = async () => renderReport(await api(`/api/report?file=${encodeURIComponent($("#reportFile").value)}`));
  $("#cardSearch").oninput = (e) => renderCardGrid(e.target.value);
  $("#cardSet").onchange = () => renderCardGrid($("#cardSearch").value);
  $("#cardArch").onchange = () => renderCardGrid($("#cardSearch").value);
  renderCardGrid("");
  await initBuilder(decks);
  await initLab(decks.filter(d => d.ok), ARCHETYPES || await api("/api/archetypes"));
  document.querySelectorAll("nav button").forEach(b => b.onclick = () => {
    document.querySelectorAll("nav button").forEach(x => x.classList.toggle("active", x === b));
    document.querySelectorAll("main.mode").forEach(m => m.classList.toggle("hidden", m.id !== b.dataset.mode));
  });
}
document.querySelectorAll("details.how").forEach(d => {
  let pref = null; try { pref = localStorage.getItem("how:" + d.id); } catch (e) {}
  if (pref === "closed" || (pref === null && window.innerWidth < 700)) d.open = false;   // phones: collapsed until asked
  d.addEventListener("toggle", () => { try { localStorage.setItem("how:" + d.id, d.open ? "open" : "closed"); } catch (e) {} });
});
init().catch(e => alert("init failed: " + e.message));
