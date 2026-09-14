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
const TARGET_GIG = 1;      // cptcg.core.enums: a Target is at a Unit (0) or at a Gig area (1)
let GAME = null;           // {id, view, log[]}
let LOG = [];

// ---------------------------------------------------------------- cards
// Rebuilding the whole board on every frame means every <img> is a NEW element, and a new element
// decodes before it paints even when its bytes are already in cache. At one frame per rival move
// that read as the board blinking: for two or three frames every card was an empty outline, once
// per move, all the way down the AI's turn. The images are kept across renders and moved into the
// new tree instead, so a card that was on screen a moment ago is never decoded twice.
let IMG_POOL = new Map();
function harvestImages(root) {
  IMG_POOL = new Map();
  root.querySelectorAll("img[data-src]").forEach(img => {
    if (!img.complete || !img.naturalWidth) return;      // never pool one that has nothing to show
    const a = IMG_POOL.get(img.dataset.src);
    if (a) a.push(img); else IMG_POOL.set(img.dataset.src, [img]);
  });
}
function cardImg(src, alt, cls) {
  const a = IMG_POOL.get(src);
  let img = a && a.length ? a.pop() : null;
  if (!img) {
    img = el("img");
    img.decoding = "sync";           // and one that does have to be made paints in the same frame
    img.draggable = false;
    img.dataset.src = src;
    img.src = src;
  }
  img.className = cls || "";
  img.alt = alt || "";
  img.onerror = null;                // the caller's, if it wants one, replaces this
  return img;
}

function cardNode(c, opts = {}) {
  const d = el("div", "card " + (c.color || ""));
  // Only where the view already gives one: a face-down Legend and a rival hand card are built from
  // {} on purpose, and must not gain an identity here.
  if (c && c.inst != null) d.dataset.inst = c.inst;
  d._card = c;                      // what this node is, for the slide-to-preview below
  if (opts.back) {
    d.className = "card back" + (opts.small ? " sm" : "");
    if (HAS_BACK) {
      const img = cardImg(opts.legend ? "images/_back_legend.jpg" : "images/_back.jpg", "card back");
      img.onerror = () => { HAS_BACK = false; img.remove(); };
      d.append(img);
    }
    return d;
  }
  if (opts.small) d.classList.add("sm");
  const def = CARDS[c.id] || {};
  if (def.image) {
    const img = cardImg(`images/${c.id}.jpg`, c.name);
    if (CAN_HOVER) { d.onmouseenter = () => showPreview(img.src, c, false, placeOf(d)); d.onmouseleave = hidePreview; }
    // Touch has no onclick preview: a tap is how you ACT on a card now, and a tap that also threw
    // the card up full-screen meant every move began by dismissing a picture of the card you had
    // just moved. Reading is the press-and-hold instead (see `startScrub`), which is a
    // document-level gesture rather than a per-card one because it has to be able to begin on the
    // table between two cards, on the prompt, or during the mulligan.
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
// What the board has taken responsibility for this render. The prompt is then the REMAINDER: every
// legal action the board could not put under a finger still gets a button, so no fix here can make
// a move unreachable and strand a game. Nothing is filtered out of the prompt by name.
let CLAIM = null;
function claim(o) { if (CLAIM && o) CLAIM.add(o.index); }

// Ending the turn is the one move with no way back that a thumb can reach by accident: it sits in
// a fixed place, it is the button a player aims for twenty times a game, and there is no card to
// tap by mistake instead — the tap either lands on it or it does not. So it asks twice. The first
// tap arms it and says so; the second ends the turn. Anything else on the page stands it down, and
// so does a few seconds of nothing, because a button left hot is its own accident waiting.
let ARMED = null;
function disarm() { if (ARMED) { const a = ARMED; ARMED = null; a.reset(); } }
document.addEventListener("click", disarm);

function endTurnButton(end, onAct, cls) {
  const b = el("button", cls, "END TURN");
  let timer = null;
  const reset = () => { clearTimeout(timer); b.classList.remove("armed"); b.textContent = "END TURN"; };
  b.onclick = (e) => {
    e.stopPropagation();
    if (ARMED && ARMED.b === b) { disarm(); onAct(end.index); return; }
    disarm();
    b.classList.add("armed"); b.textContent = "END TURN · CONFIRM";
    timer = setTimeout(() => { if (ARMED && ARMED.b === b) disarm(); }, 5000);
    ARMED = { b, reset };
  };
  return b;
}

function renderBoard(root, v, { interactive, onAct, watching, onSkip, fresh } = {}) {
  harvestImages(root);              // keep the faces; only the boxes around them are rebuilt
  root.innerHTML = "";
  closeCardMenu();
  disarm();
  endDrag();                          // nothing survives a render: the nodes a drag held are gone
  CLAIM = new Set();
  const me = v.perspective == null ? 0 : v.perspective;   // bottom seat
  const opp = 1 - me;
  const P = v.players;
  const pend = v.pending;
  // `onAct` as well as `interactive`: the rival-turn playback renders interactively so the board
  // still reads as live, but it has no way to act -- and its last frame is the one where the turn
  // has come back to you, so without this the board offered moves it could not carry out and the
  // buttons threw. Nothing is offered that cannot be done.
  const myTurn = interactive && !!onAct && pend && pend.player === me;
  const byInst = {};          // inst -> [options]
  if (myTurn) pend.options.forEach(o => { if (o.inst != null && o.kind !== "Die") (byInst[o.inst] = byInst[o.inst] || []).push(o); });
  const targets = new Set(myTurn ? pend.options.filter(o => o.kind === "Target").map(o => o.inst) : []);
  const atk = v.atk;

  const decorate = (node, inst) => {
    if (!myTurn) return;
    const opts = byInst[inst];
    if (targets.has(inst)) { node.classList.add("target"); }
    else if (opts && opts.length) { node.classList.add("can"); }
    // A card's own moves belong to the card. Once a glowing card can be tapped for them, the prompt
    // does not list them again — it is a board, not a menu, and a player who knows the game reaches
    // for the card they mean. Tapping opens the short list of what THAT card can do; dragging it to
    // the field, the Eddies or a host is the fast path for the three that have a place to go.
    (opts || []).forEach(claim);
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
    if (end) phase.append(endTurnButton(end, onAct, "endturn"));
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
      // Ruling 002: an Eddies area is public as an unordered multiset — selling reveals the card and
      // both players saw it; only the order is lost. So a card that has just arrived is shown face
      // up for a beat and then turns over, which is what happens at the table. Without it the
      // rival's sale was a card back appearing out of nowhere.
      if (fresh && fresh.has(c.inst) && (CARDS[c.id] || {}).image) {
        const face = cardImg(`images/${c.id}.jpg`, c.name, "eddieface");
        n.classList.add("flipdown");
        n.append(face);
      }
      if (c.spent) n.classList.add("spent");
      if (c.image) { n.onmouseenter = () => showPreview(`images/${c.id}.jpg`, c, false, placeOf(n)); n.onmouseleave = hidePreview; }
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
    ed.classList.add(mine ? "p-my-eddies" : "p-opp-eddies");
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
  let leftovers = null;
  const right = el("div", "col");
  const controls = el("div", "panel controls p-controls");
  controls.append(el("span", "lbl", "ROOM"));
  if (interactive) {
    controls.append(el("div", "desc", "Take back the last move, concede the match, or leave for a new one."));
    const undo = el("button", "", "UNDO"); undo.onclick = () => act("undo");
    const concede = el("button", "", "CONCEDE"); concede.onclick = () => { if (confirm("Concede?")) act("concede"); };
    const leave = el("button", "", "NEW GAME"); leave.onclick = () => { GAME = null; $("#board").classList.add("hidden"); $("#setup").classList.remove("hidden"); matLock(); };
    const dl = el("button", "", "EXPORT"); dl.onclick = async () => {
      if (window.CPTCG_BRIDGE) window.CPTCG_BRIDGE.download(`cptcg-game-${GAME.id}.json`, await api(`/api/games/${GAME.id}/replay`));
      else window.open(`/api/games/${GAME.id}/replay`);
    };
    // No PAY toggle: what you spend is a move, and a move is not a setting.
    controls.append(undo, concede, leave, dl);
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
    prompt.append(el("div", "q", pend.prompt || pend.phase));
    if (myTurn) {
      // The turn bar: where you are, what you have not spent yet, and the one move that ends it.
      // The two once-a-turn rights are the ones a player loses track of, because nothing on the
      // table shows them going — the sale is a card in the Eddies like any other, and a called
      // Legend is face up like the rest. So they are said out loud here, and struck through once
      // they are spent.
      const bar = el("div", "turnbar");
      bar.append(el("span", "tn", `TURN ${v.turn}${v.overtime ? " · OVERTIME" : ""}`));
      // Not during the mulligan, the roll-off, or the Gig die: none of them is a moment where
      // selling or calling is on offer, and a struck-through right you could not have taken yet
      // reads as one you have spent.
      if (pend.kind !== "MULLIGAN" && pend.kind !== "ORDER" && pend.kind !== "GIG_DIE") {
        const chip = (name, used, what) => {
          const c = el("span", "chip" + (used ? " used" : ""), name + (used ? " · done" : ""));
          c.dataset.hint = what + (used ? " — already taken this turn" : " — still yours this turn");
          return c;
        };
        bar.append(chip("SELL", P[me].sold, "One card sold for an Eddie"),
                   chip("CALL LEGEND", P[me].called, "Call a Legend for 1 €$"));
      }
      const end = (pend.options || []).find(o => o.kind === "EndTurn");
      if (end) { bar.append(endTurnButton(end, onAct, "end")); claim(end); }
      prompt.append(bar);
      // The Gig die is the first thing asked every turn and it is asked of the fixer, which on a
      // phone is a 34px column of six dice down the flank -- a target for a stylus. The whole tray
      // is laid out again here at thumb size: every die still in the fixer, the ones you may take
      // lit and the d20 shown but out of reach until it is the last one left, which is the rule
      // and is worth seeing rather than being told.
      if (pend.kind === "PICK") {
        const shownPicker = revealPicker(pend, onAct);
        if (shownPicker) { prompt.append(shownPicker); (pend.options || []).forEach(claim); }
        else {
          const picker = adjustPicker(pend, onAct, me);
          if (picker) { prompt.append(picker); (pend.options || []).forEach(claim); }
        }
      }
      if (pend.kind === "GIG_DIE") {
        const tray = el("div", "gigpick");
        const can = new Map();
        (pend.options || []).forEach(o => { if (o.kind === "Die") can.set(o.inst, o); });
        [4, 6, 8, 10, 12, 20].forEach(k => {
          if (!P[me].fixer.includes(k)) return;
          const d = dieNode(k, null, "fixer big");
          const o = can.get(k);
          if (o) { d.classList.add("pick"); d.onclick = () => onAct(o.index); claim(o); }
          else { d.classList.add("off"); d.dataset.hint = `d${k} \u00b7 only when it is the last die left`; }
          tray.append(d);
        });
        if (tray.childNodes.length) prompt.append(tray);
      }
      // Filled at the end of the render, once every panel has had its chance to claim what it can
      // put under a finger. What is left here is what the board has no place for: keep or mulligan,
      // who goes first, a card effect's choices, passing a reaction.
      leftovers = el("div", "opts");
      prompt.append(leftovers, el("div", "desc", hintFor(pend)));
    } else if (interactive) {
      prompt.append(el("div", "desc", hintFor(pend)), el("div", "waiting", "Waiting for the AI…"));
    } else if (v.next_action) {
      prompt.append(el("div", "desc", hintFor(pend)), el("div", "waiting", "Next: " + v.next_action));
    }
  }
  right.append(prompt, cardPanel(v, byInst, pend, myTurn, onAct));
  root.append(left, center, right);
  if (fresh && fresh.size) {
    root.querySelectorAll(".card[data-inst]").forEach(n => {
      if (fresh.has(+n.dataset.inst)) n.classList.add("fresh");
    });
  }
  // The card is rebuilt on every render, so it cannot transition from a state it never held: the
  // turn has to be an animation, played on the cards that have just changed hands-on state.
  const spun = turns(v);
  if (spun.length) {
    const set = new Set(spun);
    root.querySelectorAll(".card[data-inst]").forEach(n => {
      if (set.has(+n.dataset.inst)) n.classList.add("turning");
    });
  }
  if (leftovers) {
    // Two options that read the same are still two options. This used to drop the second, on the
    // reasoning that identical labels are identical choices -- true for three face-down Legends,
    // false the moment a label is ambiguous for any other reason, and then the move it named was
    // simply unreachable. Misty Olszewski asks you to choose a card type and two of her three
    // buttons read the same; one of the three types could not be picked at all. They are numbered
    // instead, so the duplicate is visible rather than missing.
    const seen = new Map();
    let n = 0;
    pend.options.forEach(o => {
      if (CLAIM.has(o.index)) return;
      const dup = (seen.get(o.label) || 0) + 1;
      seen.set(o.label, dup);
      n++;
      const b = el("button", o.kind === "EndTurn" ? "end" : "",
                   dup > 1 ? `${o.label} (${dup})` : o.label);
      b.onclick = () => onAct(o.index);
      leftovers.append(b);
    });
    // ... and nothing to say when the prompt is already holding the thing to tap.
    if (!n && !leftovers.parentNode.querySelector(".gigpick, .gigadj, .reveal"))
      leftovers.append(el("div", "none", "Tap a lit card to act on it."));
  }
  // The attack, drawn on the board instead of described in the prompt. "React?" over a wall of
  // cards does not say which card is coming at you or what it is coming at, and that is the whole
  // of the decision — so the attacker is ringed, and so is the thing it is aimed at, whether that
  // is a Unit or a Gig area. Marked here rather than in `decorate` because an attack is worth
  // seeing whoever's turn it is: watching a replay or the AI's turn go by, this is the only thing
  // on screen that says what just happened.
  if (atk && atk.attacker != null && atk.attacker >= 0 && !atk.fizzled) {
    const mark = (inst, cls) => {
      const n = root.querySelector(`.card[data-inst="${inst}"]`);
      if (n) n.classList.add(cls);
    };
    mark(atk.attacker, "attacking");
    if (atk.target_kind === TARGET_GIG) {
      const defender = 1 - atk.ctrl;                        // a Gig area belongs to the other seat
      const panel = root.querySelector(defender === me ? ".p-my-gig" : ".p-opp-gig");
      if (panel) panel.classList.add("underattack");
    } else if (atk.target != null && atk.target >= 0) {
      mark(atk.target, "defending");
    }
  }
  if (myTurn) wireDrag(root, pend, onAct);
  fitBoard(root);                   // the size first, then the fan that is measured against it
  root.querySelectorAll(".hand, .eddies .list, .legends, .field").forEach(fanHand);
  root.querySelectorAll(".card[data-inst]").forEach(n => {
    n.addEventListener("click", (e) => {
      if (n.classList.contains("payable")) return;      // paying: the click means "spend this"
      e.stopPropagation();
      const inst = +n.dataset.inst;
      SELECTED = inst;
      const box = root.querySelector(".p-cardinfo");
      if (box) box.replaceWith(cardPanel(v, byInst, pend, myTurn, onAct));
      root.querySelectorAll(".card.picked").forEach(x => x.classList.remove("picked"));
      n.classList.add("picked");
      openCardMenu(n, findOnBoard(v, inst), myTurn ? (byInst[inst] || []) : [], onAct);
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
  const plays = {}, sells = {}, gear = {}, attacks = {};
  pend.options.forEach(o => {
    if (o.inst == null || o.inst < 0) return;
    if (o.kind === "Play" && o.host >= 0) (gear[o.inst] = gear[o.inst] || {})[o.host] = o;
    else if (o.kind === "Play" || o.kind === "GoSolo") plays[o.inst] = o;
    else if (o.kind === "Sell") sells[o.inst] = o;
    else if (o.kind === "Attack") attacks[o.inst] = o;
  });
  const field = root.querySelector(".p-my-field");
  const eddies = root.querySelector(".p-my-eddies");

  // My field joins the hand and my Legends: a Unit that can attack is dragged at the rival, which
  // is the gesture the table has for it — you push the card forward across the middle of the mat.
  root.querySelectorAll(".hand.mine > .card[data-inst], .p-my-legends .card[data-inst]:not(.gearcard), .p-my-field .card[data-inst]:not(.gearcard)").forEach(node => {
    const inst = +node.dataset.inst;
    const mine = { play: plays[inst], sell: sells[inst], gear: gear[inst], attack: attacks[inst] };
    if (!mine.play && !mine.sell && !mine.gear && !mine.attack) return;
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
  // Two places to aim at, because an attack has two things it can be aimed at: a Unit on their
  // field, or their Gig area. Three lit zones {D} their Legend band was one of them {D} read as three
  // different attacks, and the extra one was not a third kind of anything. The drop declares the
  // attack and stops; what it is aimed at is a second decision with a reaction window between the
  // two (CR 9.26), so the board asks it rather than the drop answering it.
  [[".p-opp-field", "DROP TO ATTACK"], [".p-opp-gig", "DROP TO RAID THE GIGS"]].forEach(([sel, label]) => {
    const z = root.querySelector(sel);
    if (z) DRAG_ZONES.push({ el: z, label, pick: (d) => d.opts.attack });
  });
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

// Every way a drag can end runs through here, and it cleans up by SEARCHING rather than by
// remembering: a ghost is a clone in the body and the lifted card is a node in a board that may
// have been re-rendered underneath it, so `d.node.classList.remove(...)` can be talking to a node
// that is no longer on the page. A card left tilted and glowing in mid-air with nothing touching
// the screen is what that looks like, and it needs a real gesture to clear because the state that
// would clear it is gone.
function endDrag() {
  const d = DRAG;
  DRAG = null;
  document.querySelectorAll(".dragghost").forEach(g => g.remove());
  document.querySelectorAll(".card.dragging").forEach(n => n.classList.remove("dragging"));
  document.querySelectorAll(".droptarget, .dropover").forEach(z => {
    z.classList.remove("droptarget", "dropover"); delete z.dataset.drop;
  });
  return d;
}
document.addEventListener("pointerup", (e) => {
  const d = endDrag();
  if (!d || !d.moved) return;                 // a click: the node's own handler deals with it
  const z = zoneAt(d, e.clientX, e.clientY);
  const opt = z && z.pick(d);
  if (opt) { SUPPRESS_CLICK = Date.now() + 400; d.onAct(opt.index); }
});
// iOS takes a pointer away whenever something else claims the gesture, and it sends pointercancel
// rather than pointerup when it does. With nothing listening, the drag never ended: the ghost
// stayed in the body and the card stayed lifted out of its row for the rest of the game.
document.addEventListener("pointercancel", endDrag);
document.addEventListener("touchcancel", endDrag);

// A pointerup that ended a drag is followed by a click on whatever is underneath; swallow it once
// so dropping a card does not also fire the card's own action menu.
//
// A DEADLINE, and cleared by the next press. A bare flag was a licence with no expiry, and on a
// touchscreen a drag does not produce the click it was waiting for — so the licence sat there until
// the player's next tap, wherever and whenever that was, and ate it. With a mouse the click always
// arrived and spent it, which is why this only ever happened on the phone: drag a card to play it,
// be asked which Eddies to spend, and the first Eddie you tap does nothing at all.
let SUPPRESS_CLICK = 0;
document.addEventListener("pointerdown", () => { SUPPRESS_CLICK = 0; }, true);
document.addEventListener("click", (e) => {
  if (!SUPPRESS_CLICK) return;
  const live = Date.now() < SUPPRESS_CLICK;
  SUPPRESS_CLICK = 0;
  if (!live) return;
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
  // The WIDEST card as drawn, not the first card's layout box. A spent card lies on its side, so
  // the space it takes is its height, and getBoundingClientRect reports the rotated box while
  // offsetWidth reports the upright one. Capping the overlap at a fraction of the upright width
  // meant two sideways Eddies could not be brought close enough to touch, let alone to fit a 40%
  // panel — which is why the rival's Eddies were cut off down the side exactly when they were
  // turned over.
  let w = 0;
  cards.forEach(c => { w = Math.max(w, c.getBoundingClientRect().width, c.offsetWidth); });
  if (!w) return;                    // not laid out yet (a hidden tab); the resize hook retries
  // Measured, not computed from n * card width. A spent card lies on its side and carries margins
  // of half the difference between the two dimensions to make room for it, and a row holding one
  // is wider than the arithmetic thinks by 32px a card — which is exactly how a Legend band with a
  // spent Legend in it kept overflowing while the fan believed it had already fixed it. Asking the
  // browser costs one layout flush per row and cannot be wrong.
  hand.style.setProperty("--overlap", "0px");
  // An Eddies area is a PILE, and a pile may be squeezed to slivers: every card in it is the same
  // face-down back, so what a reader takes from it is how many there are and how many lie on their
  // side, both of which survive any amount of overlap. A hand is not a pile — it keeps the fifth of
  // itself that makes each card recognisable.
  const cap = hand.closest(".eddies")
    ? Math.max(4, Math.round(w - 5))
    : Math.round(w * HAND_MAX_OVERLAP);
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
// Everything has to fit on one screen, and the arithmetic for that cannot be written in CSS. The
// height a board really has is the VISUAL viewport — what is left once Safari's toolbars have taken
// their share, which moves as they come and go and which `svh` and `dvh` only approximate — and the
// space the non-card rows want depends on what is in them: a prompt with five choices in it is not
// the prompt with none. The old rule guessed both with one constant, and any slack it left over
// went into the empty half of the field rows instead of into the cards.
//
// So the board is measured and the card height solved for. Five rows hold a card: the two Legend
// bands, the two fields and the hand. Everything else — the control strip, the Gig line, the prompt
// — is content-sized and does not move when the cards do, so one pass of arithmetic lands it and a
// second absorbs the rounding.
const FIT_MIN = 44;
function fitBoard(root) {
  if (!root || root.classList.contains("hidden") || !root.isConnected) return;
  if (!window.matchMedia("(max-width: 700px)").matches) {
    root.style.removeProperty("height"); root.style.removeProperty("--card-h");
    root.style.removeProperty("--card-w");
    return;
  }
  const top = document.querySelector("header.top");
  const vh = (window.visualViewport && window.visualViewport.height) || window.innerHeight;
  const H = Math.floor(vh - (top ? top.getBoundingClientRect().height : 0));
  if (H < 200) return;
  root.style.height = H + "px";
  const hOf = (sel) => { const n = root.querySelector(sel); return n ? n.getBoundingClientRect().height : 0; };
  const set = (h) => {
    root.style.setProperty("--card-h", h + "px");
    root.style.setProperty("--card-w", Math.floor(h / 1.41) + "px");
  };
  const GRID = 3 * 7 + 3 * 2;        // the grid's seven gaps and its own padding
  const PANEL = 8;                   // a card row sits in a panel, which costs a few pixels
  const chrome = hOf(".p-controls") + Math.max(hOf(".p-my-gig"), hOf(".p-opp-gig")) + hOf(".p-prompt");
  let card = Math.max(FIT_MIN, Math.floor((H - chrome - GRID - 5 * PANEL) / 5));
  set(card);
  // Then let the board correct the arithmetic, because the arithmetic has to guess at padding and
  // the board does not. What it asks each of the five rows is the only question that matters: how
  // much room is there below your bottom card? Spare room in every row means the cards can all be
  // bigger; a row whose card hangs past its own edge reports a negative and they all come down.
  // Taking the WORST row is what keeps the two that stretch from hiding a third that is being
  // squeezed — which is exactly how the hand ended up eight pixels short of its own cards while
  // the fields sat there with room to spare.
  // Layout heights, not drawn ones: a spent card lies on its side, so the box it is drawn in is a
  // card's width tall while the box the row reserves for it is still a card's height, and asking
  // for the drawn one had this measuring 63 where the row had committed 90.
  const spare = (sel) => {
    const row = root.querySelector(sel);
    const c = row && row.querySelector(".card, .slot");
    if (!c) return null;
    const n = c.parentElement;                    // the box that actually holds the row of cards
    const cs = getComputedStyle(n);
    return n.clientHeight - (parseFloat(cs.paddingTop) || 0) - (parseFloat(cs.paddingBottom) || 0)
           - c.offsetHeight;
  };
  const ROWS = [".p-opp-legends", ".p-opp-field", ".p-my-field", ".p-my-legends", ".p-my-hand"];
  for (let pass = 0; pass < 8; pass++) {
    let worst = Infinity;
    for (const sel of ROWS) { const v = spare(sel); if (v != null) worst = Math.min(worst, v); }
    if (!isFinite(worst)) break;
    const step = Math.trunc((worst - 2) * 2 / 5);      // 2px of air, not 0: a hairline is not a fit
    if (!step) break;
    card = Math.max(FIT_MIN, card + step);
    set(card);
  }
}
function refit() {
  document.querySelectorAll(".board:not(.hidden)").forEach(b => {
    fitBoard(b);
    b.querySelectorAll(".hand, .eddies .list, .legends, .field").forEach(fanHand);
  });
}
let FAN_TIMER = null;
function refitSoon() { clearTimeout(FAN_TIMER); FAN_TIMER = setTimeout(refit, 80); }
window.addEventListener("resize", refitSoon);
window.addEventListener("orientationchange", refitSoon);
// Safari gives and takes back height as its toolbars slide, and only the visual viewport reports it.
if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", refitSoon);
}

// ---------------------------------------------------------------- arrivals
// Which cards are on the board that were not a moment ago. The board is the source of truth rather
// than the log, because the log is prose and this has to be exact: a card that arrives gets the
// arrival glow, and the first one gets shown full size the way the reference client does.
let SEEN = new Set(), SEEN_READY = false;
function visibleCards(v) {
  const out = [];
  (v.players || []).forEach(p => {
    (p.field || []).forEach(c => out.push(c));
    (p.legends || []).forEach(l => { if (l.name) out.push(l); });   // a Legend still face-down has none
    ((p.eddies && p.eddies.list) || []).forEach(c => out.push(c));
  });
  return out;
}
// Which cards have just been turned, either way. Spending a card is the one move on a table you
// make with your hand rather than by saying it — you turn it on its side, and the turn is how
// everyone at the table knows it is spent. Arriving already sideways says the same thing and shows
// none of it, and when four Eddies go over at once for one cost, the turn is the only part that
// says they went together.
let TURNED = new Set(), TURNED_READY = false;
function turns(v) {
  const now = new Set(), spun = [];
  // Its own walk, not `visibleCards`: that one skips a face-down Legend on purpose, because a card
  // with no identity has no arrival to announce -- but a face-down Legend is the commonest thing in
  // the game to spend, since on turn one it is the only thing you have to spend, and its turn is
  // the whole of what the board can show you about a payment.
  const see = (c) => {
    if (!c || c.inst == null || !c.spent) return;
    now.add(c.inst);
    if (!TURNED.has(c.inst)) spun.push(c.inst);
  };
  (v.players || []).forEach(p => {
    (p.field || []).forEach(see);
    (p.legends || []).forEach(see);
    ((p.eddies && p.eddies.list) || []).forEach(see);
  });
  const opening = !TURNED_READY;                 // the first board of a game turns nothing
  TURNED = now; TURNED_READY = true;
  // Only the turn out, not the turn back: a card standing up again is drawn in the narrower slot
  // an upright card gets, so the first half of that animation would be clipped by the panel it is
  // standing in. Readying stays instant until the slot can be animated with it.
  return opening ? [] : spun;
}

function arrivals(v) {
  const now = new Set(), fresh = [];
  visibleCards(v).forEach(c => {
    if (c.inst == null) return;
    now.add(c.inst);
    if (!SEEN.has(c.inst)) fresh.push(c);
  });
  // The first board of a game: everything on it is new, so none of it is news. This used to ask
  // whether SEEN was empty, which is not the same question -- a game opens with nothing visible at
  // all (both Legend rows are face down, both fields are empty, neither player has sold anything),
  // so SEEN stayed empty and *every* render counted as the opening one until the first card
  // appeared. That first card was therefore the one arrival that never got its glow: a card sold
  // into an Eddies area, which is exactly where the arrival is the only thing that says what it was.
  const opening = !SEEN_READY;
  SEEN = now; SEEN_READY = true;
  return opening ? [] : fresh;
}

// A card that just hit the board used to be thrown full size into the middle of the screen for a
// beat. On a phone that is the whole board covered, once per move, including for a card you just
// played yourself and a card you sold face-down into your Eddies — where the image is not even
// information the game gives you. What the arrival needs to say is "this one moved", and
// `.card.fresh` says it in place, on the card, without taking the board away.
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

// ---------------------------------------------------------------- what this card can do
// Tapping a glowing card opens its own short list, at the card. This is the whole of the change
// the prompt gave up: the prompt used to carry a button for every legal action in the game, so a
// main phase with a hand of seven and a field of four was thirty buttons of "Play X" and "Sell X"
// to read through in order to do the thing you were already pointing at. A player who knows the
// game reaches for the card; the card answers.
//
// The list drops the card's name from every label, because the menu is standing on the card — the
// question it answers is "what", not "which".
const VERB = { Sell: "SELL", Play: "PLAY", GoSolo: "GO SOLO", Call: "CALL A LEGEND (1 €$)",
               Attack: "ATTACK", Target: "ATTACK THIS", Block: "BLOCK" };
function verbFor(o) {
  if (o.kind === "Activate") { const i = o.label.indexOf(": "); return i < 0 ? o.label : o.label.slice(i + 2); }
  if (o.kind === "Play" && o.host >= 0) { const i = o.label.indexOf(" on "); return i < 0 ? "EQUIP" : "EQUIP TO" + o.label.slice(i + 3); }
  return VERB[o.kind] || o.label;
}
// Tapping a card opens the card, full size: its face, where it is standing, what is bolted to it
// and what that comes to, and what it can do. A forty-pixel sliver is a thing to point at, not a
// thing to read, and a little menu hanging off one was answering only the last of those questions.
// Tap it again, or anywhere off it, and it goes away.
let SHEET_INST = null, CARDMENU = null;
function closeCardMenu() {
  SHEET_INST = null;
  if (CARDMENU) { CARDMENU.remove(); CARDMENU = null; }
  if (PREVIEW) { PREVIEW.classList.remove("sheet"); hidePreview(); }
}
// A face-down card has nothing to read, so blowing it up full screen shows a card back the size of
// the phone — all of the room and none of the answer. What it has is what it can do, and that is
// all it gets: a short list standing on the card, the way every card's list used to work.
function openCardPopover(node, c, acts, onAct) {
  if (!acts.length) return;
  const m = el("div", "cardmenu");
  acts.forEach(o => {
    const b = el("button", "", verbFor(o));
    b.onclick = (e) => { e.stopPropagation(); closeCardMenu(); onAct(o.index); };
    m.append(b);
  });
  m.addEventListener("click", (e) => e.stopPropagation());
  document.body.append(m);
  // Above the card if it fits, below if it does not, and never off either edge: on a phone the card
  // this is hanging off can be twenty pixels from the side of the screen.
  const r = node.getBoundingClientRect(), mb = m.getBoundingClientRect();
  const above = r.top - mb.height - 8;
  m.style.top = (above >= 6 ? above : Math.min(r.bottom + 8, innerHeight - mb.height - 6)) + "px";
  m.style.left = Math.max(6, Math.min(r.left + r.width / 2 - mb.width / 2, innerWidth - mb.width - 6)) + "px";
  CARDMENU = m;
  SHEET_INST = c.inst;
}
// What a Unit's power is made of. Each piece of Gear contributes its own printed power and nothing
// else (ops.power sums exactly that), so the breakdown is honest rather than inferred; whatever is
// left over after the print and the Gear is the turn's buffs and auras, and it is named as such
// rather than hidden in a total that does not add up.
function powerParts(c) {
  const printed = typeof c.power === "number" ? c.power : null;
  const gear = (c.gear || []).reduce((n, g) => n + (typeof g.power === "number" ? g.power : 0), 0);
  if (printed == null || typeof c.power_now !== "number") return null;
  return { printed, gear, other: c.power_now - printed - gear, now: c.power_now };
}
function openCardMenu(node, c, acts, onAct) {
  if (!c) return;
  const open = SHEET_INST != null && SHEET_INST === c.inst;
  closeCardMenu();
  if (open) return;                                      // a second tap on the same card closes it
  if (node.classList.contains("back")) { openCardPopover(node, c, acts, onAct); return; }
  const img = node.querySelector("img");
  showPreview(img ? img.getAttribute("src") : "", c, true, placeOf(node));
  PREVIEW.classList.remove("scrub");
  PREVIEW.classList.add("sheet");
  PREVIEW.querySelector("img").classList.toggle("hidden", !img);

  const body = PREVIEW.querySelector(".sheetbody");
  body.innerHTML = "";
  const parts = powerParts(c);
  if (parts) {
    const line = el("div", "pow");
    line.append(el("b", "", `POWER ${parts.now}`));
    const bits = [`${parts.printed} printed`];
    if (parts.gear) bits.push(`${parts.gear >= 0 ? "+" : ""}${parts.gear} Gear`);
    if (parts.other) bits.push(`${parts.other >= 0 ? "+" : ""}${parts.other} this turn`);
    line.append(el("span", "", bits.join(" \u00b7 ")));
    body.append(line);
  }
  if (c.gear && c.gear.length) {
    const list = el("div", "gearlist");
    list.append(el("div", "lbl", c.gear.length === 1 ? "EQUIPPED" : `EQUIPPED \u00d7${c.gear.length}`));
    c.gear.forEach(g => {
      const row = el("div", "g" + (g.spent ? " spent" : ""));
      row.append(el("b", "", g.name),
                 el("i", "", typeof g.power === "number" && g.power ? `${g.power >= 0 ? "+" : ""}${g.power} power` : ""));
      if (g.text) row.append(el("div", "t", g.text.replace(/\n/g, " ")));
      list.append(row);
    });
    body.append(list);
  }
  if (acts && acts.length) {
    const row = el("div", "opts");
    acts.forEach(o => {
      const b = el("button", "", verbFor(o));
      b.onclick = (e) => { e.stopPropagation(); closeCardMenu(); onAct(o.index); };
      row.append(b);
    });
    body.append(row);
  }
  body.classList.toggle("hidden", !body.childNodes.length);
  SHEET_INST = c.inst;
}
// Anything else on the page closes it. The card's own click stops propagating, so opening one does
// not immediately close it, and so does the sheet's.
document.addEventListener("click", closeCardMenu);

// The long press is this board's own gesture — it reads the card under the finger — and iOS wants to
// answer it with a system callout at the same time, which is where the stray "Share..." bubble over
// the control strip came from. `-webkit-touch-callout: none` is the CSS for that and is set, but it
// is advisory and does not reach everything; cancelling the contextmenu event is the same refusal
// said in a way the browser has to honour, and it is what a right-click on a desktop board would
// have raised too. Scoped to the board and its chrome, so the guide and the reports keep theirs.
// No zoom. A board is a fixed layout that has just been measured to the pixel against the screen it
// is on; a pinch or a double-tap does not reveal more of it, it slides the half you are looking at
// off the edge and leaves you to find your way back. The viewport meta says so, but iOS has ignored
// `user-scalable=no` since iOS 10 — the gesture events are the part it does honour, and
// `touch-action: manipulation` is what takes the double-tap.
["gesturestart", "gesturechange", "gestureend"].forEach(k => {
  document.addEventListener(k, (e) => e.preventDefault(), { passive: false });
});

document.addEventListener("contextmenu", (e) => {
  const t = e.target;
  if (t && t.closest && t.closest(".board, .top, .preview, .pileview, .cardmenu, .paypanel"))
    e.preventDefault();
});

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
  // A reader, not a second set of controls. What the card can do is offered at the card itself,
  // where the hand is — a panel on the far side of the board is a longer trip to the same button.
  const acts = myTurn ? (byInst[SELECTED] || []) : [];
  box.append(el("div", "desc", acts.length
    ? "Tap it again on the board for what it can do, or drag it where it goes."
    : "This card has no card actions in the current phase."));
  return box;
}

function hintFor(p) {
  const h = {
    MULLIGAN: "Keep your opening hand, or shuffle it back and draw 6 new cards. You may do this only once.",
    ORDER: "You won the d20 roll-off, so you choose. Going first means the first turn's draw and Gig, but your two left-most Legends start spent and don't ready on that turn.",
    GIG_DIE: "Start of your turn: take one die from your fixer area, roll it and add it to your Gig area. Click a lit die in the fixer. The d20 can only be taken when it is the last die left.",
    MAIN: "Your main phase. Do things in any order: play cards (pay their cost in €$ from ready Eddies and Legends), sell one card this turn for an Eddie, Call a Legend for 1 €$ (once per turn), GO SOLO a Legend, use abilities, and attack with ready Units that didn't enter this turn. Every one of those belongs to a card: the ones you can use carry a faint gold edge, so tap one for what it can do, or drag it to the field, your Eddies or a host. Only what is not a card is a button here.",
    TARGET: "Declare the target of the attack: tap a ringed rival Unit to start a fight (higher power wins, ties defeat both), or take the Gig area button to steal 1 die plus 1 more per 10 power. The attacker is then spent and its ATTACK effects resolve.",
    REACTION: "A rival Unit is attacking. You may spend a ready BLOCKER Unit to redirect the attack to it, play a QUICK Program or ability by paying its cost, or Call a Legend for 1 €$ (if you haven't this turn) — all of those are on the cards themselves. Pass to let the attack resolve.",
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
  // The two Gig areas meet along the centre line and are otherwise identical boxes. A die keeps the
  // colour of whoever brought it, so a stolen one sits in the other tray still wearing your green,
  // which is exactly when knowing which box you are looking at matters most.
  g.append(el("div", "tag", p.seat === meSeat ? "FRIENDLY GIGS" : "OPPONENT GIGS"));
  return g;
}
// ---------------------------------------------------------------- resolving with the cards up
// Some questions are about CARDS, and a row of buttons reading their names is the wrong shape for
// them: the cards are the thing, and on a phone the names are also the longest labels the prompt
// ever has to carry. So when the engine says this question has SHOWN the asker some cards
// (Choice.revealed), they are laid out in the middle of the screen at a size you can read, and the
// choice is made on the cards themselves.
//
// It also fixes a real gap rather than only looking better. Viktor Vektor looks at the top 5 and
// may take 2 Gears from them; the client was offering the 2 and never showing the other 3 the
// player had just looked at, because `revealed` was never sent. Fool on the Hill asks your RIVAL to
// send two revealed cards to your hand or your trash, and had to paste both names into its prompt
// string to be answerable at all.
function revealPicker(pend, onAct) {
  const shown = pend.revealed || [];
  if (!shown.length) return null;
  const opts = pend.options || [];
  if (!opts.length || !opts.every(o => Array.isArray(o.pick))) return null;

  // Which revealed cards each option takes. An option whose picks are not cards (a yes/no, say)
  // still belongs here -- it is a decision ABOUT the revealed cards -- it just selects none of them.
  const rows = opts.map(o => ({
    o,
    insts: o.pick.filter(x => x && x.t === "card").map(x => x.inst),
    bools: o.pick.filter(x => x && x.t === "bool").map(x => x.value),
  }));
  const selectable = new Set();
  rows.forEach(r => r.insts.forEach(i => selectable.add(i)));
  const anyCards = selectable.size > 0;
  if (!anyCards && !rows.some(r => r.bools.length)) return null;

  const box = el("div", "reveal");
  const row = el("div", "shown");
  let chosen = [];

  const match = () => rows.find(r =>
    r.insts.length === chosen.length && r.insts.every(i => chosen.includes(i)));

  const go = el("button", "primary hidden", "CONFIRM");
  const paint = () => {
    row.querySelectorAll(".card").forEach(n => {
      const i = +n.dataset.inst;
      n.classList.toggle("paypicked", chosen.includes(i));
      n.classList.toggle("can", selectable.has(i) && !chosen.includes(i));
      n.classList.toggle("idle", anyCards && !selectable.has(i));
    });
    const m = match();
    go.classList.toggle("hidden", !m);
    go.textContent = chosen.length ? `TAKE ${chosen.length}` : "CONFIRM";
    count.textContent = anyCards
      ? `${chosen.length} of ${shown.length} chosen` + (match() ? "" : " \u2014 not a legal set")
      : "";
  };
  const count = el("div", "count", "");

  shown.forEach(c => {
    const n = cardNode(c);
    n.dataset.inst = c.inst;
    n.onclick = (e) => {
      e.stopPropagation();
      if (!selectable.has(c.inst)) return;              // shown, but not one you may take
      const at = chosen.indexOf(c.inst);
      if (at >= 0) chosen.splice(at, 1); else chosen.push(c.inst);
      paint();
    };
    row.append(n);
  });

  const buttons = el("div", "opts");
  go.onclick = (e) => { e.stopPropagation(); const m = match(); if (m) onAct(m.o.index); };
  buttons.append(go);
  // Everything that is not "take exactly this set of cards" keeps a button, because a yes/no about
  // the revealed cards is still a sentence: "to their hand" / "to the trash", "Decline".
  rows.forEach(r => {
    if (r.insts.length) return;
    const b = el("button", "", r.o.label);
    b.onclick = (e) => { e.stopPropagation(); onAct(r.o.index); };
    buttons.append(b);
  });
  box.append(row, count, buttons);
  paint();
  return box;
}

// ---------------------------------------------------------------- adjusting a Gig
// "Decrease a Gig" used to be seven buttons reading "your d4=3 -2", "your d4=3 -1", "rival d12=10
// -2" and so on: every (die, amount) pair in the game written out as a sentence, for a decision
// that is a die and a number. So it is a die and a number. Pick the die off a row of the actual
// dice, pick the amount off a stepper that only offers what that die allows, watch the result
// change as you do, and confirm. The engine's options are unchanged -- each combination is still
// one of them -- this only stops asking the question in prose.
//
// It builds only when every option really is one Gig (the view ships the structure behind each
// label); anything else falls back to the buttons, which are still correct, just plainer.
function adjustPicker(pend, onAct, me) {
  const opts = pend.options || [];
  if (!opts.length || !opts.every(o => Array.isArray(o.pick))) return null;
  const real = opts.filter(o => o.pick.length === 1 && o.pick[0].t === "gig");
  const decline = opts.find(o => o.pick.length === 0);
  if (!real.length || real.length + (decline ? 1 : 0) !== opts.length) return null;

  const dice = [];                                  // one entry per die, with the amounts it allows
  real.forEach(o => {
    const g = o.pick[0], key = g.owner + ":" + g.i;
    let d = dice.find(x => x.key === key);
    if (!d) dice.push(d = { key, g, moves: [] });
    d.moves.push({ delta: g.delta, index: o.index });
  });
  dice.forEach(d => d.moves.sort((a, b) => a.delta - b.delta));

  const box = el("div", "gigadj");
  const row = el("div", "dicerow");
  const stepRow = el("div", "steprow");
  const go = el("button", "primary hidden", "CONFIRM");
  let picked = null, move = null;

  const paint = () => {
    row.querySelectorAll(".pick").forEach(n => n.classList.toggle("on", n.dataset.key === (picked && picked.key)));
    stepRow.innerHTML = "";
    if (!picked) { go.classList.add("hidden"); return; }
    const g = picked.g;
    picked.moves.forEach(m => {
      const b = el("button", "step" + (move && move.index === m.index ? " on" : ""),
                   m.delta > 0 ? `+${m.delta}` : String(m.delta));
      b.onclick = (e) => { e.stopPropagation(); move = m; paint(); };
      stepRow.append(b);
    });
    const now = move ? g.value + move.delta : g.value;
    stepRow.append(el("span", "to", `d${g.sides}: ${g.value}` + (move ? ` \u2192 ${now}` : "")));
    go.classList.toggle("hidden", !move);
    go.textContent = move ? `CONFIRM ${move.delta > 0 ? "+" : ""}${move.delta}` : "CONFIRM";
  };

  dice.forEach(d => {
    const wrap = el("div", "pick");
    wrap.dataset.key = d.key;
    wrap.append(dieNode(d.g.sides, d.g.value, d.g.owner === me ? "own" : "rival"),
                el("span", "whose", d.g.owner === me ? "FRIENDLY" : "OPPONENT"));
    wrap.onclick = (e) => {
      e.stopPropagation();
      picked = d; move = d.moves.length === 1 ? d.moves[0] : null;
      paint();
    };
    row.append(wrap);
  });
  go.onclick = (e) => { e.stopPropagation(); if (move) onAct(move.index); };
  const buttons = el("div", "opts");
  buttons.append(go);
  if (decline) {
    const b = el("button", "", "DECLINE");
    b.onclick = (e) => { e.stopPropagation(); onAct(decline.index); };
    buttons.append(b);
  }
  box.append(row, stepRow, buttons);
  paint();
  return box;
}

// The fixer: the dice not yet rolled, dim, named rather than numbered.
function diceTray(p, pick, pend, onAct) {
  const t = el("div", "panel dice");
  const can = new Set(pick ? pend.options.filter(o => o.kind === "Die").map(o => o.inst) : []);
  [4, 6, 8, 10, 12, 20].forEach(k => {
    if (!p.fixer.includes(k)) return;
    const d = dieNode(k, null, "fixer");
    if (can.has(k)) {
      const o = pend.options.find(x => x.kind === "Die" && x.inst === k);
      d.classList.add("pick"); d.onclick = () => onAct(o.index);
      claim(o);                        // the tray is the die's own control; the prompt need not repeat it
    }
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
      timer = setTimeout(tick, step);
    };
    tick();
  });
}

// ---- choosing what to spend
// The engine auto-pays (ruling 025) because making payment a decision multiplies the AI's branching
// factor. At a table you push the Eddies forward yourself, so here the human always does: there is
// no "let the game pick" and no setting to turn this off. Between two face-down Eddies the choice
// changes nothing in the rules — no card ever reads which card is sitting in an Eddies area — but
// between an Eddie and a Legend it very much does, and it is not the game's decision to make.
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
    const hint = el("div", "desc", "Tap the glowing cards, in any order. Between two Eddies it changes nothing — no card ever reads which one you spent — but spending a Legend keeps an Eddie ready for later.");
    const row = el("div", "opts");
    // The confirm only exists once the cost is covered. Paying used to fire the moment the count
    // came right, which meant the last card you tapped was also the card that committed the move,
    // and a mis-tap on it was a move you had not decided to make yet.
    const go = el("button", "primary pay-go hidden", `PAY ${cost}`);
    const cancel = el("button", "", "CANCEL");
    row.append(go, cancel);
    panel.append(q, count, hint, row);

    const done = (val) => {
      panel.remove();
      nodes.forEach(n => { n.classList.remove("payable", "paypicked"); n.onclick = n._payPrev || null; });
      document.removeEventListener("keydown", onKey);
      resolve(val);
    };
    const onKey = (e) => { if (e.key === "Escape") done(null); };
    go.onclick = () => { if (picked.length === cost) done(picked.slice()); };
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
        go.classList.toggle("hidden", picked.length !== cost);
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
  if (typeof verbOrIndex === "number") {
    const pend = GAME.view && GAME.view.pending;
    const opt = pend && pend.options && pend.options.find(o => o.index === verbOrIndex);
    const me = GAME.view && (GAME.view.perspective == null ? 0 : GAME.view.perspective);
    const src = (opt && opt.cost > 0 && GAME.view.players[me].pay_sources) || [];
    // Every paid move, not only the ones with a choice in them. Even when the ready cards are
    // exactly the cost, pushing them forward yourself is the move; the alternative is a game that
    // sometimes takes your Eddies without asking and sometimes does not, which is worse than
    // either rule on its own.
    if (opt && opt.cost > 0 && src.length >= opt.cost) {
      pay = await askPayment(opt.cost, src);
      if (pay === null) return;            // cancelled: the action was never sent
      if (!pay.length) pay = null;
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
  SEEN = new Set(); SEEN_READY = false;
  TURNED = new Set(); TURNED_READY = false;
  arrivals(r.view);                        // seed the board history; the opening board is not news
  $("#setup").classList.add("hidden"); $("#board").classList.remove("hidden"); matLock();
  renderBoard($("#board"), r.view, { interactive: true, onAct: act });
}

// ---------------------------------------------------------------- watch
let RP = { file: null, step: 0, steps: 0, auto: null };
async function rpGo(step) {
  const r = await api(`/api/replay?file=${encodeURIComponent(RP.file)}&step=${step}`);
  RP.step = r.step; RP.steps = r.steps;
  $("#rpSlider").max = r.steps - 1; $("#rpSlider").value = r.step; $("#rpPos").textContent = `${r.step + 1} / ${r.steps}`;
  $("#rpBoard").classList.remove("hidden"); matLock();
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
let MEASURED_NOTE = "", MEASURED_GAMES = 0, MEASURED_AGENT = "", MEASURED_STALE = false;

async function loadCardLinks() {
  try {
    const d = await api("/api/cardlinks");
    LINKS = d.links || {}; TOKENS = d.tokens || {}; ARCHES = d.archetypes || {};
    MEASURED_NOTE = d.measured_note || ""; MEASURED_GAMES = d.measured_games || 0;
    MEASURED_AGENT = d.measured_agent || ""; MEASURED_STALE = !!d.measured_stale;
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
  if (L && L.archetypes && L.archetypes.length) {
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
  // Straight under the written notes, and above the interaction lists: the whole point of putting a
  // measurement on this page is that it can disagree with the paragraph directly above it, and a
  // reader who has to scroll past thirty combo chips to find it will never notice when it does.
  // Hoisted out of the links block for the same reason it is worth showing at all — a card with no
  // interactions still has a record, and for those cards the record is the only thing to say.
  if (c.measured) measuredPanel(right, c.measured);
  if (L) {
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

// What the card actually did, from tools/playtest.py. Shown beside the written notes on purpose:
// the two can disagree, and when they do that is the interesting thing on the page rather than an
// embarrassment to hide. Every number carries its sample size, because a rate without one invites
// exactly the reading it cannot support.
function pct(x) { return x == null ? "—" : `${(100 * x).toFixed(1)}%`; }

function measuredPanel(right, m) {
  right.append(el("h4", "", `MEASURED <span class=dim>· ${MEASURED_GAMES.toLocaleString()} ` +
    `${MEASURED_AGENT || "self-play"} games</span>`));
  if (MEASURED_STALE) {
    right.append(el("div", "warn", "The card scripts have changed since this run, so these " +
      "numbers describe the game as it behaved before that change. Re-run tools/playtest.py."));
  }
  const grid = el("div", "gmeas");
  const rows = [
    ["played", `${m.played.toLocaleString()}`, "games where this copy reached the table"],
    ["play rate", pct(m.play_rate), "of the games where it was drawn"],
    ["won when played", pct(m.gip), "a level, not a contrast — partly about the decks it was in"],
    ["won when drawn", pct(m.gih), `over ${m.drawn.toLocaleString()} draws`],
    ["IWD", m.iwd == null ? "—" : `${m.iwd >= 0 ? "+" : ""}${(100 * m.iwd).toFixed(1)}pp`,
     "won when drawn minus won when not — the contrast"],
  ];
  rows.forEach(([k, v, why]) => {
    const cell = el("div", "mcell");
    cell.append(el("div", "mk", k));
    cell.append(el("div", "mv", v));
    cell.append(el("div", "mw", why));
    grid.append(cell);
  });
  right.append(grid);
  if (m.play_rate != null && m.play_rate < 0.25 && m.drawn >= 200) {
    right.append(el("div", "warn",
      `The agent held this card and played something else ${pct(1 - m.play_rate)} of the time it ` +
      `drew it. Every rate above is measured on the ${m.played.toLocaleString()} games where it ` +
      `did play it, so read them narrowly.`));
  }
  // Folded away by default. It is the same paragraph on all 151 cards, and printed open it is the
  // largest block on the page — but it must be *reachable*, because every rate above it is
  // conditional on how the run was built and a number without that context is the one that gets
  // quoted back years later as a fact about the game.
  if (MEASURED_NOTE) {
    const d = el("details", "mnote");
    d.append(el("summary", "", "how this was measured"));
    d.append(el("p", "dim small", MEASURED_NOTE));
    right.append(d);
  }
}

function closeCardGuide() { if (GUIDE_OPEN) GUIDE_OPEN.classList.remove("show"); }

// ---------------------------------------------------------------- card preview
// The board draws cards small; hovering any card shows its face at full resolution, like the sim.
let PREVIEW = null;
// Where a card is standing, in the words a player would use. Read off the board rather than out of
// the view, because the board is where the answer already is — one of these panels is its parent.
// It matters most for the pair the art cannot tell apart: two identical face-down backs, one of
// them yours and one of them the opponent's, in two piles at opposite ends of the mat.
function placeOf(n) {
  if (!n || !n.closest) return "";
  if (n.closest(".p-my-eddies"))   return "Your face-down Eddie";
  if (n.closest(".p-opp-eddies"))  return "Opponent face-down Eddie";
  if (n.closest(".p-my-hand"))     return "Your card in hand";
  if (n.closest(".p-opp-hand"))    return "Opponent card in hand";
  if (n.closest(".p-my-field"))    return "Your Unit";
  if (n.closest(".p-opp-field"))   return "Opponent Unit";
  if (n.closest(".p-my-legends"))  return "Your Legend";
  if (n.closest(".p-opp-legends")) return "Opponent Legend";
  if (n.closest(".pileview"))      return "In the trash";
  if (n.closest(".stackbox"))      return "Top of the trash";
  return "";
}
function showPreview(src, c, touch, place) {
  if (!PREVIEW) {
    PREVIEW = el("div", "preview");
    PREVIEW.append(el("div", "cap"), el("img"), el("div", "sheetbody hidden"));
    document.body.append(PREVIEW);
    PREVIEW.onclick = (e) => { e.stopPropagation(); closeCardMenu(); };
  }
  // Whoever is opening it owns it: a read takes the plain card, a tap builds the sheet back up.
  PREVIEW.classList.remove("sheet");
  const body = PREVIEW.querySelector(".sheetbody");
  body.innerHTML = ""; body.classList.add("hidden");
  const img = PREVIEW.querySelector("img");
  img.classList.remove("hidden");
  img.src = src; img.alt = c.name;
  const cap = PREVIEW.querySelector(".cap");
  cap.textContent = place || "";
  cap.classList.toggle("hidden", !place);
  PREVIEW.classList.add("show"); PREVIEW.classList.toggle("touch", !!touch);
  // Centred, not following the cursor: the card lands in the same place every time, so reading it
  // is a glance rather than a chase, and moving along a row of cards swaps one image for another.
  // pointer-events stay off, so the preview never steals the hover from the card underneath it.
  PREVIEW.style.left = ""; PREVIEW.style.top = "";
}
function hidePreview() {
  SHEET_INST = null;
  if (PREVIEW) PREVIEW.classList.remove("show", "touch", "sheet");
}

// The mat is a table, not a document. While a board is on screen the page itself is pinned: a
// finger dragged across the cards was scrolling the whole page up and down, which is the one thing
// this gesture must not do. Fixing the body takes the document out of flow, so there is nothing
// left for the browser to scroll or rubber-band; the panels that are *meant* to scroll (the prompt,
// the control strip, the log) are inside the board and keep their own overflow.
function matLock() {
  const on = !!document.querySelector("main.mode:not(.hidden) .board:not(.hidden)");
  document.documentElement.classList.toggle("mat", on);
  document.body.classList.toggle("mat", on);
}

// Hold, then slide: the board becomes a reader. Whatever card is under the finger is shown, and it
// follows the finger from card to card, so a row can be read without lifting and pressing again.
//
// A card is not only the rectangle it occupies — it owns the whole column of screen above and below
// it, its LANE. That is what makes the gesture usable one-handed: a hand of seven cards on a phone
// is seven slivers about forty pixels wide, and a thumb reading them covers the very thing it is
// reading. Sliding along underneath the row, over the prompt, moves card to card without the hand
// ever being hidden behind the finger. Lanes are not a fixed grid; they are measured from where the
// cards actually are when the hold arms, so a hand of three has three wide lanes and a hand of eight
// has eight narrow ones, and a fanned row divides at the edges you can see rather than at the full
// width of cards that are mostly covered.
//
// Once something is up it stays up until the finger lifts. Sliding into a gap used to blank the
// screen, which made the row flicker as a thumb crossed it; there is nothing a reader wants to see
// less than the card they were reading disappearing because they moved four pixels.
//
// The gesture belongs to the document, not to the cards. A hold that has to *begin* on a card can
// only read the row it started in, and the moments a player most wants to read — deciding a
// mulligan, looking over the rival's field on their turn — are moments when the finger is as likely
// to come down on the table between two cards. Starting anywhere and sliding onto the cards is the
// same gesture with the restriction taken off.
//
// The thing it must not break is drag-to-play: the arming timer is cancelled by any real movement
// before it fires, so moving straight off a card plays it and staying still reads it.
//
// Two thresholds, because the press asks two questions and they are not the same question.
// HOLD_MS is "show me this card", and a reader wants that the moment they press: past about a tenth
// of a second it stops being a response and starts being a wait. TAP_MS is "and do not play it",
// which has to clear a real tap, and a deliberate tap is down for longer than a picture should take
// to appear. Splitting them is what lets the card come up at once without a brisk tap losing its
// card — the picture shows at HOLD_MS, and the click is only swallowed if the finger was still down
// at TAP_MS or had slid to another card by then.
const HOLD_MS = 120, TAP_MS = 260;
let SCRUB = false, SCRUB_TIMER = null, SCRUB_FROM = null, SCRUB_ATE_CLICK = false;
let SCRUB_AT = 0, SCRUB_READ = false, SCRUB_ROWS = null;

function cardUnder(x, y) {
  const under = document.elementFromPoint(x, y);
  const node = under && under.closest && under.closest(".card");
  const c = node && node._card;
  return (c && c.id && (CARDS[c.id] || {}).image) ? node : null;
}

// The rows of readable cards on screen, measured once when the hold arms: the board does not move
// while a finger is resting on it, and measuring every card on every touchmove is the sort of thing
// that makes a phone feel like treacle. Cards are grouped into a row by their vertical overlap
// rather than by which panel drew them, so this needs to know nothing about the layout and holds
// for the hand, the two fields, the Legend bands and the Eddies piles alike.
function cardRows() {
  const board = document.querySelector("main.mode:not(.hidden) .board:not(.hidden)");
  const rows = [];
  if (!board) return rows;
  for (const n of board.querySelectorAll(".card")) {
    const c = n._card;
    if (!c || !c.id || !(CARDS[c.id] || {}).image) continue;      // a face-down card reads as nothing
    const r = n.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    let row = rows.find(q => Math.min(q.bottom, r.bottom) - Math.max(q.top, r.top)
                             > 0.5 * Math.min(q.bottom - q.top, r.height));
    if (!row) rows.push(row = { top: r.top, bottom: r.bottom, items: [] });
    row.top = Math.min(row.top, r.top); row.bottom = Math.max(row.bottom, r.bottom);
    row.items.push({ n, left: r.left });
  }
  for (const row of rows) row.items.sort((a, b) => a.left - b.left);
  return rows;
}
// Lanes belong to your hand and to nothing else. The hand is the one row with open screen below it
// — the prompt, and the bottom edge — so it is the one row a finger can sit under without sitting on
// something else, which is what the lane was for: reading a fan of seven forty-pixel slivers
// without the thumb covering them. Every other row has a row directly above and below it, so a
// lane there is not a lane, it is a guess about which neighbour was meant; and the answer came
// back as a card in an Eddies pile two rows away, from a press that was nowhere near it.
//
// Within the row it is the last card that begins at or before x. That last-one-wins rule is the
// fan's own geometry: a later card is drawn over the one before it, so the slice of card i you can
// actually see runs from its left edge to the next card's, which is exactly the lane it answers to.
function laneCard(x, y) {
  if (!SCRUB_ROWS || !SCRUB_ROWS.length) return null;
  let row = null;
  for (const q of SCRUB_ROWS) if (!row || q.top > row.top) row = q;   // the lowest row is the hand
  if (!row || y < row.top) return null;
  let pick = row.items[0];
  for (const it of row.items) if (it.left <= x) pick = it;
  return pick ? pick.n : null;
}
function previewCard(node) {
  const c = node && node._card;
  if (!c || !c.id) return;
  const src = `images/${c.id}.jpg`;
  const img = PREVIEW && PREVIEW.querySelector("img");
  if (img && PREVIEW.classList.contains("show") && img.getAttribute("src") === src) return;
  showPreview(src, c, true, placeOf(node));
  PREVIEW.classList.add("scrub");
}
function startScrub(x, y) {
  SCRUB = true;
  endDrag();                         // a hold is a read, not a drag: drop the pending drag-to-play
  SCRUB_ROWS = cardRows();
  SCRUB_READ = false;                // not a read yet: a tap this brief still plays the card it hit
  const n = cardUnder(x, y) || laneCard(x, y);
  if (n) previewCard(n);
}
function endScrub() {
  clearTimeout(SCRUB_TIMER); SCRUB_TIMER = null; SCRUB_FROM = null;
  if (!SCRUB) return;
  SCRUB = false; SCRUB_ROWS = null;
  // The lift that ends a *read* must not also play the card it ended on. A brisk tap is not a read
  // even though it showed the card, so it keeps its click and plays what it touched.
  if (!(SCRUB_READ || Date.now() - SCRUB_AT >= TAP_MS)) {
    if (PREVIEW) PREVIEW.classList.remove("scrub");
    hidePreview();
    return;
  }
  // A touch click follows its lift within a few milliseconds, so the licence expires quickly — left
  // standing it would eat the next real click instead, which is the sort of bug that makes a button
  // "randomly" not work.
  SCRUB_ATE_CLICK = true;
  setTimeout(() => { SCRUB_ATE_CLICK = false; }, 400);
  if (PREVIEW) PREVIEW.classList.remove("scrub");
  hidePreview();
}
document.addEventListener("touchstart", (e) => {
  if (e.touches.length !== 1) { endScrub(); return; }
  SCRUB_ATE_CLICK = false;           // a new touch: whatever the last hold was owed, it is spent
  const t = e.touches[0];
  SCRUB_FROM = { x: t.clientX, y: t.clientY };
  SCRUB_AT = Date.now();
  clearTimeout(SCRUB_TIMER);
  SCRUB_TIMER = setTimeout(() => { SCRUB_TIMER = null; startScrub(SCRUB_FROM.x, SCRUB_FROM.y); }, HOLD_MS);
}, { passive: true });
document.addEventListener("touchmove", (e) => {
  const t = e.touches[0];
  if (!t) return;
  if (SCRUB_TIMER && SCRUB_FROM) {
    // moved before the hold armed: a swipe or a drag, and neither is this gesture
    if (Math.abs(t.clientX - SCRUB_FROM.x) + Math.abs(t.clientY - SCRUB_FROM.y) > 12) {
      clearTimeout(SCRUB_TIMER); SCRUB_TIMER = null;
    }
    return;
  }
  if (!SCRUB) return;
  // A hold that landed on one of the board's own scrolling panels would otherwise scroll it while
  // reading, so the listener is not passive and this move belongs to the gesture.
  if (e.cancelable) e.preventDefault();
  // Slid far enough to be aiming at another card: a read whatever the clock says. The threshold
  // matters — a finger resting on a card jitters a pixel or two, and counting that as a slide would
  // turn brisk taps into reads at random, which is the failure that looks like a dead button.
  if (SCRUB_FROM && Math.abs(t.clientX - SCRUB_FROM.x) + Math.abs(t.clientY - SCRUB_FROM.y) > 12)
    SCRUB_READ = true;
  const n = cardUnder(t.clientX, t.clientY) || laneCard(t.clientX, t.clientY);
  if (n) previewCard(n);             // and if there is nothing at all, what is up stays up
}, { passive: false });
document.addEventListener("touchend", endScrub);
document.addEventListener("touchcancel", endScrub);
// One click is swallowed after a hold, wherever it lands: the finger came down to read, and the
// card it came down on is often one a tap would have played.
document.addEventListener("click", (e) => {
  if (!SCRUB_ATE_CLICK) return;
  SCRUB_ATE_CLICK = false;
  e.stopImmediatePropagation();
  e.preventDefault();
}, true);

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
    matLock();
  });
}
document.querySelectorAll("details.how").forEach(d => {
  let pref = null; try { pref = localStorage.getItem("how:" + d.id); } catch (e) {}
  if (pref === "closed" || (pref === null && window.innerWidth < 700)) d.open = false;   // phones: collapsed until asked
  d.addEventListener("toggle", () => { try { localStorage.setItem("how:" + d.id, d.open ? "open" : "closed"); } catch (e) {} });
});
init().catch(e => alert("init failed: " + e.message));
