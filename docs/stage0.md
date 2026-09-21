# Stage 0 report

Execution of Stage 0 of the unified design (Part 6): the engine changes that had to land before
any corpus was recorded, the timing table, the Stage 0 engineering, the oracle set and the new
suite families, the six kill tests and the day-0 baselines. Everything here is on branch
`claude/wizardly-archimedes-e20tzv`; the running logs are `docs/stage0_progress.md`,
`docs/stage0_decisions.md` and `docs/stage0_questions.md`.

Status labels, as the task asked: **Confirmed** (run, reproducible from the command given),
**My judgement**, **Uncertain**, **Could not determine**.

## 1. Engine changes landed

All twelve items were first reproduced red (`tests/rules/test_stage0_engine.py`, commit a8c3624:
23 strict-xfail tests and 5 documenting tests), then landed one commit each under the golden
protocol, with a regeneration commit carrying the five evidences in `tests/golden/REGEN.md`, the
delayed suite requalified and the bootstrap sample re-recorded. Confirmed.

| item | change | golden | suite effect |
|---|---|---|---|
| E1 | Sketchy Ripper may reveal nothing; Misty may name Legend; El Sombrerón may pay with no max Gig and chooses which | 2 keys | none |
| E2 | Take Control's reduction reaches effect steals (Appetite for Destruction, Gorilla Arms) | IDENTICAL, fuzz moved | none |
| E3 | Flathead's unblockable is fixed at declaration (`AttackContext.unblockable`) | IDENTICAL, fuzz moved | none |
| E4 | Dying Night readies the Eddies even after V dies (end-of-turn listener) | IDENTICAL, fuzz moved | none |
| E5 | face-up Legends on the field count (Synapse Burnout counts itself; Berserk, Panam, MaxTac Squadron, Pepe, Goro per owner ruling) | 2 keys | none |
| E6 | "the first time each turn" counts events before the card arrived (eight scripts; Yorinobu counts the defeat that brought him) | 3 keys | none |
| E7 | Bootleg's sold card is hidden from both seats (`F_FACEDOWN` Eddies) | IDENTICAL (G0), fuzz moved | none |
| E8 | trigger ordering over printed hooks and listeners, with `wants` on every hook (046's spurious prompts gone: 15.6 → 2.0 prompts a game) | all 8 keys | one mined position hit the node cap (73 → 72) |
| E9 | costs resolve after what they paid for (activation and play) | with E8 | — |
| E10 | the reaction window always opens (Pass-only windows recorded); the re-window after a Block stays closed (residual) | all 8 keys, no outcome moved | none |
| E11 | root dedup without hidden identities (`neural.seat_key`) | agent-only | none |
| E12 | which Legends pay is the payer's choice (kill test 4: 14.18% ≥ 2%) | all 8 keys | four positions no longer qualify (72 → 68): two now won by the heuristic, three with a random floor above 25% |

Full suite green after every commit; the site builds (`tools/build_site.py`). Rulings rows 048–053
record the settled items; ruling 025 is revised. **No further rule changes after E12.**

Category (ii), listed and not changed (see `docs/rulings.md` and `docs/stage0_questions.md`):
bottom-deck order after a search; Null Street Cred compared as 0; two Deadman Transmitters on one
host; mulligan narration in the web layer; the two engine-side tells (silent skips, PICK menu
width). Parked rules questions: a Call's spend triggers by analogy; two copies of one card in an
ordering group; whether a Gear's ⊡ spends the Gear or its host.

Engine tells: the reaction-window tell is removed (E10) except for the re-window after a Block,
whose cost is written in the E10 ledger entry (the frozen heuristic stops blocking if it opens).
Agent-side tells are removed (E11). Engine-side tells not landed: silent skips of an optional
effect with no candidates (six cards; a decline-only PICK would add an action per such trigger and
a G2 regeneration) and the width of a rival-hidden PICK in the information key (a `view.py`
change with no golden movement). My judgement: both are small; neither was measured for frequency
in this task beyond the coverage matrix, which lists the decline branches offered.

## 2. Timing table and the Stage 1 projection

n = 20 games per agent, seat 0 against the frozen heuristic, one process per agent group on its
own core, inferred-list sampler (`out/s0/timing_{a,b,c,d}.json`). Confirmed.

| agent | game median s | IQR | min | max | decisions/game | median ms MAIN / PICK / TARGET / GIG_DIE |
|---|---:|---:|---:|---:|---:|---|
| heuristic | 0.16 | 0.06–0.20 | 0.05 | 0.40 | 76.7 | 0.88 / 0.19 / 0.65 / 0.00 |
| neural | 0.17 | 0.12–0.27 | 0.08 | 0.38 | 65.1 | 2.71 / 0.64 / 1.37 / 0.00 |
| ismcts:32 | 3.22 | 2.03–4.05 | 1.02 | 12.26 | 68.3 | 42.8 / 47.0 / 60.2 / 51.9 |
| ismcts:200 | 14.05 | 9.92–16.63 | 8.20 | 24.01 | 56.5 | 246 / 255 / 301 / 285 |
| plan:32 | 9.77 | 8.73–13.02 | 6.26 | 22.87 | 65.5 | plan once per turn: 1,237 |
| plan-deep:32 | 18.79 | 12.41–27.17 | 9.00 | 61.61 | 63.7 | plan once per turn: 2,289 |

Micro-costs (10,000 calls each): clone 4.5 µs, determinize 71 µs, clone+apply 43 µs, features
48 µs, features+forward 107 µs. One `ismcts:32` iteration on a MAIN decision costs 1.34 ms (the
design's n = 1 figure was 1.1 ms under the known-list sampler).

Parallel efficiency: 200 games of `ismcts:32` vs `ismcts:32` took 972 s on one worker (4.86 s a
game) and 254 s on four: **0.956**.

**Stage 1 projection**: 30,000 games × 4.86 s ÷ 4 ÷ 0.956 ≈ **10.6 h a generation** on this
machine, before the card-aware forward at the leaves. Wall-clock scales almost linearly with cores
(8 → 5.3 h, 16 → 2.7 h): four cores give a generation a night, eight a generation a working day.
That is when more cores change the plan. The oracle labelling is a one-off.

## 3. What was built

All under `tools/` unless marked (numpy/torch never under `src/cptcg`; the stdlib test passes).

* `learn/coverage.py` (stdlib): decision records keyed by (card id, action kind, sub-mode), a
  `Coverage` aggregate with per-kind entropy, lossless JSON round trip; `learn/tokens.py`
  (stdlib): card, die, context, belief and option tokens with a pinned layout digest.
* `harvest.py`: records the search's root visits and value per decision, and a coverage block per
  run in the `.harvest.json` manifest (`runner.play_game(observe=)`).
* `decision_coverage.py`: the coverage matrix, per-kind entropy and the starvation list.
* `cards_model.py` / `fit_cards.py`: the card-aware model (151×32 embedding + static card table →
  per-token MLP → one attention layer → pooled summary ⊕ 114 aggregates ⊕ beliefs → value head;
  policy head over option tokens), torch for fitting, a numpy twin for inference (agreement to
  1e-4 pinned), ragged rows from a corpus, `eval` with `--ablate`. 141,057 parameters.
* `cards_agents.py`: `neural-cards`, `neural-cards-ablated`, `ismcts-cards`, `ismcts-cards-ablated`,
  registered through the new `CPTCG_AGENT_PLUGINS` hook so harvest and arena workers can use them.
* Belief inputs: `learn/opponent.RivalPrior` (public evidence only; the inferred-list sampler),
  `tokens.belief` (per-card remaining copies, Legend candidates).
* Known vs inferred list: `CPTCG_KNOWN_LIST` (default inferred, decision 3), recorded in arena and
  tournament JSON as `list_mode`.
* Semantic Pick features in `learn/policy.py` (52 → 83 action features; no fitted policy head
  existed, so nothing is refused).
* `dump.py --pay-events`, `dice_regret.py`, `timing.py`, `meta_report.py` (kill test 2),
  `oracle.py` (sample / label / agree), `belief_ll.py`, `monotonicity.py`, `plan_regret.py`.
* The `append_section` fix: renderers put fixed prose after a marker and it is written once.
* `learn/delayed.py`: `mode: "defend"` positions (the defender family) and per-family reporting.
* Suite: 68 → 133 positions (dice 12, race 12, play-around 13, card-semantics 15, defend 13), every one
  accepted only by `qualify`.

Every module has a test; the full suite passes at every commit.

## 4. The six kill tests

Each run once, criterion as written in Part 6, commands as run in the progress log and
`scratchpad/kt1.sh` / `kt_rest.sh`. Confirmed unless marked.

**Kill test 1 — does card identity buy play strength? FAIL.** Panels (frozen panel v2, 360 games a
member, inferred list; `out/s0/kt1/`):

| head | vs heuristic | between-pairing 95% | vs random | between-pairing 95% |
|---|---:|---|---:|---|
| `neural@w114` (114 features, refit on h20k + r8k) | 0.503 | [0.339, 0.667] | 0.883 | [0.864, 0.902] |
| `neural-cards@wcards` | 0.656 | [0.533, 0.779] | 0.703 | [0.613, 0.792] |
| `neural-cards-ablated@wcards` | 0.642 | [0.517, 0.767] | 0.675 | [0.568, 0.782] |

Leg 1 (card-aware above the 114 head by more than the between-pairing band): 0.656 sits inside the
114 head's band (upper 0.667), and against random the card-aware agent is 18 points worse. Leg 2
(the ablation drops it by more than the band): 0.656 → 0.642 and 0.703 → 0.675, inside the bands.
Both legs fail. The fit itself is real — held-out Brier 0.116 at the best epoch, 0.102 vs 0.114 for
the ablation on all rows, values correlating 0.908 with the 114 head on fresh positions at the same
Brier — but the play it produces is not better and the identity it learned does not carry into
play. The first panel run had an inference-path bug (previews scored under mismatched decision
contexts); it was fixed, documented, and the panels re-run once (decisions log). My judgement on
why: the greedy agent ranks *previews*, and a head whose extra inputs are card tokens is a
better position evaluator but a noisier ranker of one-ply siblings than a head with 114 summary
features and twice the rows; nothing in Stage 0 tunes that, by design.

**Kill test 4 — payment content. WIRE (14.18% ≥ 2%).** `dump.py --pay-events out/s0/h20k -n 5000`
on the corpus recorded after E11: 109,748 payments, 15,567 with strategic content (a usable
ability 12,151; the last face-down Legend a Call could still use 4,643; a spend-trigger Gear 27).
E12 was wired accordingly (§1) before any other corpus was recorded.

**Kill test 5 — decision coverage on searched play.** 1,000 games of `ismcts:32` self-play with
visits and the coverage sidecar (`out/s0/cov`, 120,558 decisions): every kind produces numbers;
mean root-visit entropy 1.11 nats on MAIN (6.6 options), 1.33 on PICK, 0.41 on TARGET; 809
distinct (card, kind, sub-mode) triples offered, 775 chosen. Starvation list (offered ≥ 20, never
chosen): 13 triples — the plain (no-keyword) Legend play for Sasha Yakovleva (1,154 offers), Royce,
Jackie *Mama's Favorite* and Rogue *Preem Solo*; Gear on a Legend for Netwatch Netdriver (1,052),
The Relic and Gorilla Arms; and "go first" after winning the order roll (1,000). Full matrix in
`out/s0/baselines/coverage_cov.json` (and the heuristic corpus's in `coverage_h20k.json`: 872
triples offered, 21 starved).

**Kill test 6 — dice regret with the shipped head** (`dice_regret.py out/s0/cov`, 16 rolls a
die): GIG_DIE 8,000 decisions, mean regret 0.0010 win-probability points, median 0, the chosen die
was the head's best in 55.0%, the *biggest* die was best in 40.9%; steal Picks 9,039 decisions,
mean regret 0.0006, chosen best in 79.5%. Uncertain what the small numbers mean: the shipped head
is the yardstick and it barely distinguishes dice; the instrument works and the number is day-0.

**Kill test 3 — known vs inferred list, and the exploit gap (measurements with intervals, no
pass/fail).** `arena.py exploit ismcts:32 -n 240` (cheat vs honest, 6 deck pairings) under both
samplers:

| sampler | cheat beats honest | over the deck population 95% | per-pairing |
|---|---:|---|---|
| inferred (`CPTCG_KNOWN_LIST=0`, the default) | 44.6% | [39.0, 50.2] | 0.35 0.43 0.45 0.48 0.48 0.50 |
| known (`=1`) | 52.1% | [46.2, 57.9] | 0.48 0.50 0.63 0.53 0.48 0.53 |

At a budget of 32 the value of perfect information to the search is within noise of zero under
either sampler; the honest inferred-list agent even edges the cheater (the interval's upper end
touches 50%). The known-vs-inferred gap on the frozen panel (`arena.py panel ismcts:32`, 360
games a member):

| sampler | vs heuristic | between-pairing 95% | vs random | between-pairing 95% |
|---|---:|---|---:|---|
| inferred | 0.847 | [0.808, 0.886] | 0.983 | [0.961, 1.000] |
| known | 0.856 | [0.794, 0.917] | 0.978 | [0.957, 0.999] |

The gap is 0.9 points against the heuristic and −0.5 against random, both inside the bands: at
this budget the inferred list costs the search nothing measurable, so the default of decision 3
stands at no cost. Confirmed.

**Kill test 2 — is the deck metagame non-transitive?** Round robin over the twelve frozen panel
lists plus the eight `data/decks` lists (20 decks, 190 pairs), `--no-sprt`, meta-report with a
1,000-draw transitive null (`tools/meta_report.py`).

| agent | games | residual RMS | null mean / 95th pct | p | Nash support (weights) |
|---|---:|---:|---|---:|---|
| heuristic, n = 40 a pair | 7,600 | 0.0892 | 0.0688 / 0.0751 | < 0.001 | 3: panel-3-b 0.54, panel-5-b 0.38, panel-0-b 0.08 |
| ismcts:32, n = 20 a pair | *(running)* | | | | |

Under the heuristic the field is **non-transitive** by Part 6's criterion (residual RMS above the
null at p < 0.05 and a Nash support of at least three). The `ismcts:32` row decides the test.


## 5. Day-0 baselines

*(filled in as the runs complete)*

## 6. Deviations from the plan

* `explicit_payment` is not flipped: the behaviour is hard-coded (E12), because every
  `RulesConfig` field is hashed into the ruleset digest and flipping one refuses the shipped
  weights the day-0 baselines need (the 047 precedent). The field's comment says so.
* Payment plans differ only in which Legends pay; Eddies are always spent first (0.02% of payments
  would have wanted otherwise) and two script-internal payments stay automatic.
* The decision-coverage tool is `tools/decision_coverage.py`, because `tools/coverage.py` already
  exists with another meaning.
* The timing table was measured with one process per agent group on the four cores at once (per
  core quiet), not on a wholly idle machine.
* The card-aware rows were subsampled at rate 0.04 (269,278 rows) so a fit finishes in hours on
  four cores; the design did not fix a rate.
* Proposals were briefed with "6+ deck cards"; the repo's realism test wants twenty, so the merged
  positions were padded at the bottom and re-qualified; the solver's depth cap rose 14 → 22.
* The oracle set is sampled from the corpora available at the time (heuristic self-play,
  heuristic vs random, and the `ismcts:32` self-play of kill test 5).

## 7. Open items and Stage 1 obligations

* gen0 panel slot: filled by the first card-aware promotion in Stage 1 (decision 6).
* Rules questions parked for the owner: `docs/stage0_questions.md` (Q1–Q3).
* The frozen heuristic's reaction model (it blocks only when the naive attack would take all its
  dice) is now documented; several suite positions lean on it, and revising the heuristic would
  re-qualify them.
* Defender family: 13 positions merged under `mode: "defend"`; the rules question it raised (a spent face-down Legend may be Called) is parked as Q4.

## 8. Recommendation on Stage 1

*(written after the kill tests)*
