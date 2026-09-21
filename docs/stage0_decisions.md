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

