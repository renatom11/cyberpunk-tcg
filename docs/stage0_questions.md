# Stage 0 — rules questions parked for the owner

Items skipped because answering them would guess at a rule or alter the game. Each says what is
blocked on it. (Answered 2026-09-21 in the session: Kiroshi Optics host scope; Goro *Losing His
Way* with an empty Legends area.)

- **Spend triggers raised by paying for a Call.** The FAQ settles the play ("After. Play the card
  first") and the activated effect ("After. Resolve the activated effect first") but says nothing
  about paying 1 €$ for a Call with a Legend that hosts a spend-trigger Gear. Implemented by
  analogy with the play (Call first, then the spend triggers, ordered with the CALL trigger when
  the controller has a choice). Nothing blocked; say if the analogy is wrong.
- **Two copies of one card in an ordering group.** Two Deadman Transmitters on one host (FAQ: "choose
  one of them") and, more generally, identical triggers of one card are collapsed to one choice, as
  ruling 046 already does. Nothing blocked.

**Q1 and Q2 above — SETTLED (owner rulings 054, 055).**

## Q3 — does a Gear's ⊡ ability spend the Gear or its host? — SETTLED (owner ruling 056)

Raised by the play-around proposals (Overwatch: Panam's Gift). The engine spends the **Gear instance** (`legal.ability_options` / `engine.activate` test and spend `inst`, the Gear), so a Gear's ⊡ can be used while its host is spent, and using it leaves the host ready to BLOCK afterwards. The glossary says any card can be spent, which makes this defensible, but the printed ⊡ on a Gear could also be read as spending the host it is attached to. Not changed (no rule changes after E12); one verified position (`play-around-overwatch-on-the-lowlife`) depends on the current reading and would need re-qualifying if the ruling went the other way.

## Q4 — may a spent face-down Legend be Called? — SETTLED (owner ruling 057)

Raised by the defend proposals. `legal.main_menu` / `reaction_menu` offer a Call for any face-down Legend when 1 €$ is available, without checking the target's orientation, so a spent face-down Legend can be Called (it flips face-up and stays spent, CR 11.11.1.3). The rules text does not forbid it and the FAQ does not address it. Several defend positions use spent face-down Legends as Eddie-eating decoys for the frozen heuristic; they hold either way. Not changed.

## Q3 addendum — every Gear with a spend-icon ability (for the owner's ruling)

Searched the registry: exactly **one** Gear carries a ⊡ ability.

- **Overwatch** (`overwatch-panams-gift`, cost 4): "(Equip to a friendly Unit or face-up Legend.)\nQUICK 1 €$, ⊡: Discard 1. Defeat a spent rival Unit with cost equal to or less than the discarded card's cost."

Its text does not say which card the ⊡ spends, so nothing contradicts the ruling that it spends the equipped Unit or Legend; the ruling is landed for it (Q3, Settled — owner ruling). No card is parked.


---

# Housekeeping for one batch of rulings after KT1 (written 2026-09-21, unattended)

Each item: the question in plain words, the options, what the engine does now (Confirmed from the
code cited), and my recommendation (My judgement). Nothing here has been changed.

## R-015 — a Legend that went solo: can it still be spent for 1 €$, and what happens to its slot?

* **Question.** GO SOLO plays a Legend to the field as a Unit. Ruling 044 (FAQ) says it is then
  *both* a Unit and a Legend. The rules let you "spend any number of Legends as 1 €$ each, face-up
  or face-down" (`docs/rules.md`, Play). Does that reach a Legend standing on the field? And is its
  Legends-area slot empty for good?
* **Options.** (a) Not spendable while on the field; the slot stays empty; when it leaves the field
  it is removed from the game (CR 4.4.1), so that Eddie source is gone for the rest of the game.
  (b) Spendable as 1 €$ like any face-up Legend with a Sell Tag (all 27 have one), because 044
  says it is still a Legend; slot as in (a). (c) As (a) but the slot is re-usable by a returned
  Legend (no card in the set returns one, so (c) is moot today).
* **Engine now.** (a). `ops.payable_sources` reads `s.legends(player)` — the Legends area only —
  so a field Legend is never a payment source; the slot is vacated (`go_solo_vacates_slot`,
  descriptive, hard-coded).
* **Recommendation.** (a). The €$ rule sits in the Legends-area section of the rules and the
  spend-for-€$ of a *Unit* has no precedent in the set; (b) would make a solo'd Legend a body and
  an Eddie at once, which the printed cost already prices out. Note that (b) would be a G2 engine
  change touching every payment plan and would move the goldens.

## R-019 — "once per turn": does a reaction Call on the rival's turn use up your own turn's Call?

* **Question.** Call a Legend and Sell are "once per turn". Is that once per *each* turn (so a
  player may Call on their own turn and again during the rival's turn as a reaction), or once per
  *your own* turn (one Call between your turn starts)?
* **Options.** (a) Per each turn: both players' counters reset at the start of every turn. (b) Per
  own turn: your Call counter resets only when your turn begins.
* **Engine now.** (a). `EndTurnCleanupStep` clears `s.used` and both `s.once` counters at the end
  of every turn (`core/steps.py`), for both players.
* **Recommendation.** (a) — it is the literal reading, and the rules text describes the reaction
  Call ("may be done during your turn or your Rival's") without a cross-turn limit. (b) would
  change reaction play materially (a defender who Called on their own turn could not Call blind in
  the window) and several defend positions in the suite would need re-qualifying.

## R-026 — is the field size-limited?

* **Question.** The guide names no cap; the online simulator draws a fixed row of field slots.
* **Options.** (a) No limit. (b) A cap of N (N unknown; the official simulator's row would set it).
* **Engine now.** (a): `field_limit = None`; `legal.main_menu` computes `field_full` only when a
  limit is set (`core/legal.py`).
* **Recommendation.** (a) unless the official simulator's slot count is confirmed, in which case
  (b) with that N. A cap would be a G2 change with wide consequences (wide-board decks, MaxTac
  Heavy's pricing, Panam *Nomad Cavalry*'s five-Gear line), so it should be ruled from a source,
  not inferred from a playmat drawing.

## R-030 — what a Gear's ⊡ spends: **already settled by Q3 (owner ruling 056)**

Row 030 in `docs/rulings.md` still says "the Gear itself — Uncertain", which now contradicts 056
(the equipped Unit or Legend; `engine.ability_spender`). This batch should mark 030 as superseded
by 056. (Done in this commit as a cross-reference in the 030 row; no rule content changed.)

## R-043 — may "Spend a rival Unit" target a Unit that is already spent?

* **Question.** An effect says "spend a rival Unit". Is a Unit that is already spent a legal
  target (the spend does nothing), or must the target be ready?
* **Options.** (a) Legal target, spend is a no-op (the mainstream convention for tap effects).
  (b) Only a ready Unit is a legal target (ruling 013's reading for BLOCKER, where the spend is a
  cost).
* **Engine now.** (a): `ops.spend` returns immediately if the instance is spent; the target lists
  do not filter by orientation.
* **What it changes.** Exactly one card is observably different: Memory Relapse ("spend a rival
  Unit. It can't ready until your next turn") — under (a) its rider can be put on a Unit that was
  never actually spent, which is strictly better for the Memory Relapse player; Corporate
  Surveillance is unobservable either way.
* **Recommendation.** (a), as the engine has it, because the card text does not say "ready" and
  the set never distinguishes cost from effect in print; but this is a coin-flip and the FAQ is
  silent, so the ruling is yours. Under (b) one script changes (a target filter) and the golden
  may move on decks that run Memory Relapse (G1).

## R-045 — may an ability with no legal target be activated?

* **Question.** Four abilities are guarded by the engine (they cannot be activated unless their
  effect can happen): Hanako *Daughter of the Emperor* (needs a die on each side), Panam *Nomad
  Cavalry* (needs a Gear on her and an unequipped friendly Unit), Overwatch — Panam's Gift (needs a
  card to discard), Panam *Strength Through Family* (the once-per-turn Call). Padre — Man of the
  Cross prints the same two-sided shape ("set a player's Gig to the same value as another player's
  Gig"), is unguarded, and can be activated with no dice on the board: spent, nothing happens.
* **Options.** (a) As the engine has it (guards on those four, Padre unguarded). (b) Uniform,
  permissive: any ability may be activated; an impossible effect fails (ruling 037's reading for
  Gig effects). (c) Uniform, strict: an ability whose effect has no legal target cannot be
  activated; Padre gains a guard.
* **Why it matters.** Spending is watched: NetWatch NetDriver draws when its host Legend is
  spent, Sandevistan readies it, so under (b) an ability with nothing to do is a paid draw.
* **Engine now.** (a) (`legal.ability_options`: a guard may test a target, not a magnitude or a
  printed condition; `docs/rulings.md` row 045 records the Padre counterexample).
* **Recommendation.** (c). It is the reading the four guarded cards already embody, it removes
  the one inconsistency in the set, and it closes the NetDriver-draw loophole. (b) is defensible by
  037's analogy but makes every unguarded ability a spend outlet. Both (b) and (c) are one-script
  or one-helper changes; the golden moves only for decks with Padre (G1).

## The web-layer leaks (fix described, not landed)

1. **Mulligan narration.** `sim/narrate.py` turns the `mulligan` event into "*P* mulligans." and
   `web/backend.py::_narrate` appends every line to `self.lines`, which `view_state` ships to the
   human seat — so the human reads whether the AI mulliganed, which ruling 018 hides. **Fix:**
   `_narrate` filters the new events by viewer before narrating (drop the rival's `mulligan` event;
   keep the human's own), or `narrate` takes a `viewer` argument and emits "the rival decides on
   their hand" for the other seat. **Blast radius:** `sim/narrate.py` and `web/backend.py` only;
   the replay watcher (backend line ~780, both seats visible) keeps full narration; no engine
   change, goldens IDENTICAL, one test in `tests/web/` asserting the human's log never contains
   the AI's mulligan line. Half a day.
2. **Hidden card names in prompts.** `view_state` puts `ch.prompt` into `pending` for *both* seats
   (`web/view.py`, "pending = {… 'prompt': ch.prompt …}" is built whether or not `mine`), and
   seven scripts format a card name into the prompt (`wnc.py` lines 182, 1241, 1260, 1442, 1517,
   1574, 1667): Fool on the Hill (revealed to the rival by design — not a leak), Tetratronic
   Rippler's "Trash {name}?" (a private peek — a leak to the rival), Chrome Reverie's "Call {name}
   for free?" (names a face-down Legend to both seats — a leak), Kerry's reroll (public die — not a
   leak), Viktor's "Add {name} to hand?" (private — a leak), Jackie *Mama's Favorite* (public — no),
   Judy's "Play {name} for free?" (revealed top card — public per the text, no leak). **Fix:** in
   `view_state`, send `prompt` only when `mine`, and for the other seat send the tag-derived label
   the view already computes (`_pick_env` / the tag class); the three leaking scripts keep their
   prompts, because the seat asked may see the name. **Blast radius:** `web/view.py` and the
   client's rendering of the rival's pending banner (`static/app.js`, one branch); no engine
   change; the existing view-redaction test extended with the three cards. Half a day.

## Other items parked for a decision

* **Engine-side tells not landed** (decision 2d): silent skips of an optional effect with no
  candidates (six cards; a decline-only PICK would add an action to the stream on every such
  trigger, G2 regeneration) and the width of a rival-hidden PICK in the information key
  (`view.py` only, no golden movement). Their frequency was never measured; the coverage sidecar
  now counts declines, so the first can be measured from s10k in an hour if you want the number
  before ruling.
* **`explicit_payment` and `go_solo_requires_ready` stay at their recorded values** because every
  `RulesConfig` field is hashed into the ruleset digest and flipping one refuses every fitted
  artifact. Stage 1's first promotion is the natural moment to flip both and re-record, if you
  want the flags to be truthful; it costs one bootstrap re-record and the oracle set's digest.
* **The frozen heuristic's reaction model** (it blocks only when the naive attack would take all
  its stealable dice; it Calls at the first window whenever it can pay) is now load-bearing for
  about a dozen suite positions. Revising the heuristic is a project rule change and would
  re-qualify the suite; recommended: leave frozen, note it in the guide.
* **`tools/opponent_influence.py`** imports `features._derive`, which no longer exists; the tool
  has been broken since the feature refactor. Engineering call unless you object: delete it in
  Stage 1's first housekeeping commit and fold what it measured into `belief_ll.py`.
* **The residual reaction-window tell** (the re-window after a Block stays closed; E10 ledger):
  opening it makes the frozen heuristic stop blocking. Left closed; the cost is written in the
  ledger. Your call whether fidelity to the table outweighs the yardstick.
* **Compute** for Stage 1: the plan draft asks for a decision on renting 16 cores from
  generation 4 (`docs/stage1_plan_draft.md` §0.8).
