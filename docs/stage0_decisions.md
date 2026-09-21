# Stage 0 — engineering decisions made without asking

One line each: what was decided and why. Rules questions are not here; they go to
`docs/stage0_questions.md`.

- **Decision-coverage tool is `tools/decision_coverage.py`, not `tools/coverage.py`** — that
  name already means card-script test coverage (`data/COVERAGE.md`); renaming a shipped tool is
  churn for nothing.
- **Fuzz baseline re-taken on the committed tree** — the 046 ledger entry's random-agent digest
  (`a70eb43f…`, 33,954 actions) does not reproduce on `750c723` (`2e54e2c3…`, 33,880, stable
  across three runs); the Stage 0 entries use the reproducible figure and say so.
- **E1's four fixes share one commit and one regeneration** — three card scripts answered by name
  in the FAQ, each G0/G1 with disjoint golden keys; splitting them would cost three requalify
  cycles for no extra attribution (each key is localised to its own card in the entry).
- **Take Control's reduction is a helper (`ops.steal_reduction`) read by each effect steal** rather
  than a change to `push_steals` — `push_steals` is also called after the attack path has already
  subtracted it, and a second subtraction there would double-count.
- **Flathead's unblockability travels on `AttackContext`** (read once in `engine._attack`) — the
  FAQ fixes it at declaration; the field is in the attack key of `view.info_key`, so a search sees
  it as the public fact it is.
- **No editing of engine or script files while a verification job for the previous item is
  running** — E4's script edit landed while E3's fuzz was starting and could have contaminated
  E3's digest; the fuzz was re-run on the clean tree. Each item's golden cycle now completes
  before the next item's edit begins.
- **E5 applies the field-inclusive reading to every "friendly Legends" reader, not only the four
  FAQ-named cards** — Pepe Najarro ("Ready up to 2 spent MERC Legends") now also reaches a spent
  solo'd MERC Legend; the owner's Goro ruling states the principle (a Legend on the field is a
  face-up Legend), and one helper (`EffectCtx.all_legends`/`faceup_legends`) applied everywhere is
  what keeps the six sites from drifting apart again.
- **E6 converts every "first time … each turn" script, not only the three FAQ-named ones** —
  Johnny Silverhand, Rita Wheeler, Gorilla Arms, Rogue Amendiares and Viktor Vektor read the same
  phrase; the FAQ fixes its meaning (events, not the card's memory), and one helper applied to all
  eight is what stops the phrase meaning two things. Viktor's conversion turned the audit's open
  finding AUD-viktor-vektor-drop-your-illusions-1 green, which is the reading the audit had
  already reached from the text alone.
- **E7's fuzz digests cannot move and the ledger says so** — the fuzz hashes outcomes of
  perfect-information play and nothing reads an Eddie's identity; the change is to who may name a
  card, which the determinization property tests and the scenario test observe. Treated as
  satisfying the G0 rule's intent (the change is provably not a no-op) rather than its letter.
- **The bootstrap sample is re-recorded whenever the full suite says it no longer replays**, in the
  regeneration commit of the item that caught it (here E7, for streams E5/E6 moved); the ledger
  entry names it.
- **E8 and E9 land as one commit** — E9's deferred spend triggers *are* an E8 group, and the
  `deferring` collection mode is what both need; the ledger entry covers both.
- **`CardScript.wants(ctx, ev)` added and declared on all 37 event hooks** — a trigger that would
  not act is not pending, so it must not be offered for ordering; 046's "3.2% of events" was mostly
  inactive hooks, and the true ordering rate is 1.8% of decisions. A lint would be the right guard
  for new scripts (not added in Stage 0; `registry.load_default` check in the report instead).
- **Listeners carry the registering card's instance and an event-kind attribute** (`fn.kinds`) —
  the lint that proves one-shot listeners remove themselves reads the `m[2] is listen` idiom, so
  the filter lives on the function rather than in a tuple value.
- **A Call's spend triggers resolve after the Call and join its CALL group** — by analogy with
  the FAQ's "play the card first"; no FAQ answer names the Call case (listed in the questions file).
- **Pass-only reaction windows are real decisions in the stream, and `conftest.do` answers them
  for scenario tests** — auto-resolving them in the engine would keep the tell in the action
  stream (the very thing E10 removes); hiding them from card tests keeps 148 attack-driving tests
  readable without asserting a Pass each.
- **E11's seat key lives in `agents/neural.py` (`seat_key`) and the frozen heuristic keeps
  `_equiv_key`** — the heuristic is frozen and is the yardstick; the neural greedy and the search
  root are the agents being built. `tests/unit/test_neural_agent.py` now pins the dedup key as the
  second deliberate difference between the two `_greedy` bodies.
- **The Pass-only window that re-opens after a Block stays closed** — opening it made the frozen
  heuristic stop blocking (its preview cannot see past a pending decision on the rival's turn)
  and cost the suite a defensive position; the residual tell is recorded in the report. The first
  window, the one the leak was about, always opens.

## E12 — payment as a Pick (kill test 4 said WIRE)

* **Measured, not assumed.** `dump.py --pay-events out/s0/h20k -n 5000`: 109,748 payments, a Legend with content spent while another source stayed ready in 15,567 = **14.18%** (ability 12,151; last face-down 4,643; spend-trigger Gear 27) — the gate was 2%.
* **The flag is not flipped.** `explicit_payment` stays `False` in `RulesConfig` because every field is hashed into `digest()` and the shipped `weights.json` (rules `149b39c8f55e9d41`), the corpus and the suite are refused on a mismatch; the day-0 baselines and kill test 1 need those weights under this digest. The behaviour is hard-coded in `engine._with_payment`, the field's comment says so, and `DESCRIPTIVE` keeps it (the ruling-flag test pins that nothing reads it). Same precedent as 047's orientation (`engine.go_solo`).
* **Eddies first, always.** Plans differ only in *which Legends* cover what the Eddies do not. Keeping an Eddie back to spend a Legend with a spend trigger instead was wanted in 27 of 109,748 payments (0.02%); enumerating those plans would multiply the width of every payment for that. Recorded as a residual in ruling 025.
* **Ask only when there is a choice.** One plan (Eddies suffice, or every Legend must pay) asks nothing, so the goldens move only where a real choice was inserted.
* **Script-internal payments stay automatic** (El Sombrerón's optional 2 €$, and one other): a Pick inside a continuation would need the effect rewritten around it; two cards, rare, noted.
* **The prompt names no card**: the view-redaction test caught the first version naming the payer's face-down Legends in a prompt both seats receive. Labels go through the identity gate instead.
* **Token layout moved** (`tokens_digest` `ae121dc0ed23616c` → `1c4b67e7c9000efc`): a `pay` tag class and a `payplan` pick class. No card-aware weights existed yet, so nothing is refused.

## Step 2 — how the timing table was measured

* Each agent group ran as its own single-threaded process (`heuristic,neural,ismcts:32` / `ismcts:200` / `plan:32` / `plan-deep:32`), four at once on the four cores, so every measurement had a core to itself; the micro-costs and the 1-vs-4-worker harvest throughput ran afterwards on the otherwise idle machine. Per-decision times are therefore per-core quiet, not machine-quiet; memory-bandwidth sharing is the residual.
* The table is taken under the **inferred-list** sampler (the Stage 1 default), so `ismcts` rows include a `RivalPrior` draw per world. The design's 1.1 ms/iteration was measured under the known-list sampler.
* `plan` and `plan-deep` search once per turn (at the GIG_DIE decision) and replay the plan, so their per-kind MAIN medians read 0.00; the per-game column is the comparable number.
* `tools/timing.py` scaled the decision counts by 1000 along with the milliseconds; fixed in the tool and in the four JSON files (quantiles were unaffected).

## Step 4 — the defender family is built as a `mode: "defend"` position

* `qualify` gains a second goal: for `mode: "defend"` the position's `player` is the defender, the rival is active and the claim is `delayed.held` — the rival's turn ends without the rival winning or reaching the winning Gig count. The solver searches the defender's decisions during the rival's turn (reaction windows, Calls, QUICK plays, the defender's own Picks) with the rival on the frozen policy; the heuristic must fail to hold on every seed and random must hold on at most 25% of the scoring seeds, the same shape as a mover position. Horizon is 1 by construction.
* Chosen over a separate `defend_search` because the existing exhaustive search, trials and floor are one `goal` parameter away from it; the "prevents the winning Gig this turn" criterion of the design is exactly `held`. What a defend position cannot express: a defence that only pays off two turns later.
* Positions for the family are authored the same way as the others (propose → `check`); none exist yet at the time of this note.

## Kill test 4 after E12 — what the classifier now measures

`dump.py --pay-events` on the re-recorded corpus (5,000 games): 109,558 payments, 15,397 (14.05%) spent a Legend with content while another source stayed ready. Under E12 those are no longer the auto-payer's doing: whenever such a payment had more than one plan the heuristic was *asked* and its preview chose. The classifier cannot tell an asked payment from an unasked one, so the number is now "how often the chosen plan spent a Legend with content", not an approximation share. The residual approximations E12 leaves (Eddies always first; two script-internal payments) were sized on the pre-E12 corpus (0.02% for the spend-trigger case) and are recorded in ruling 025.

## Observations from the family proposals (recorded, not acted on — the heuristic is frozen)

* The frozen defender's reaction preview stops at the attacker's die Pick (`HeuristicAgent._resolve` returns when the active player is not itself), so it Blocks only when the naive attack would take **all** its stealable dice or its Unit would lose a fight; a Gig attack that leaves a die behind is never blocked. Several verified positions in the play-around and card-semantics families lean on this. It is the same mechanism that produced E10's residual (the re-window after a Block stays closed), and it is a property of the yardstick, not of the engine.
* The heuristic answers an optional prompt with option 0 (the first candidate, not the decline), which is why Alt Cunningham *Mother of Daemons* cannot anchor a play-around position against it.
* The heuristic's evaluator counts Eddies and Legends as cards regardless of orientation, so spending is free to it; proposals gate lines on legality (exact Eddies) rather than on the greedy not wanting to spend.

## Merging the families: two repo standards the proposals had to meet

* `tests/learn/test_delayed_reward.py::test_hand_built_positions_look_like_real_games` requires three Legends a side and at least twenty cards in each deck. The proposals were briefed with "6+ cards", so the 52 merged positions were padded to twenty at the **bottom** of the deck (the front of the spec list) by repeating their own cards, which leaves the top — the only part a line can draw or reveal — exactly as authored; every padded position was then re-qualified and its `verified` block replaced. A Legend that went solo stands on the field and is still one of the deck's three, so the test now counts it.
* `MAX_DEPTH` (own decisions a searched turn may hold) raised 14 → 22: with E10's Pass at every attack, E12's payment question and E8's orderings, a turn with two attacks and two Legend-paid plays reaches fourteen and the solver reported "not exhausted" on a position it had in fact solved (`play-around-overwatch-eats-the-fang`).

## Defend family merged (13 positions)

* Observations from the proposer, recorded: the frozen heuristic on defence Calls a face-down Legend at the first reaction window whenever it can pay (its evaluator counts Eddies and Legends as cards, so payment is free and face-up is +2) and prefers "Draw 1" over a pending modal, so a Call is never a discriminating line by itself; nine of the thirteen positions make that Call cost something (a QUICK that becomes unaffordable). The re-window after a Block still offers the other Blocker (legal per CR 9.7), so "Block A then Block B" is a line random play stumbles into. A single-candidate `choose` is auto-resolved on some paths and asked as a one-option PICK on others — harmless to solver and agents (one option) but it shifts stored line indices; left as is, no rule content.
* `qualify` in defend mode relies on the rival's frozen turn being a pure function of the position (`fixed_policy`, `POLICY_SEED`); the order between equal-valued attackers is decided inside that policy's own noise and is therefore reproducible, but a proposer cannot choose it.

