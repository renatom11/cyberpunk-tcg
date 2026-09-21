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
| ismcts:32, n = 20 a pair | 3,800 | 0.1092 | 0.0953 / 0.1039 | < 0.001 | **1**: panel-5-b 0.999 |

Under the heuristic the field is **non-transitive** by Part 6's criterion (residual RMS above the
null at p < 0.05 and a Nash support of at least three). **Under `ismcts:32` it is not**: the
residuals sit above the transitive null (p < 0.001, 1,000 draws), but the equilibrium puts 99.9%
of its weight on one deck (panel-5-b), so the support condition fails and the verdict is
*transitive with a dominant deck* — the search flattens the heuristic's rock-paper-scissors into
a hierarchy. **Kill test 2 verdict: not non-transitive at `ismcts:32`.** Confirmed, run once.

**Two-player rank agreement** (Spearman of Bradley–Terry ratings, 20 decks, heuristic vs
`ismcts:32`, bootstrap over decks): **0.59 [0.17, 0.85]**. The top five under the heuristic are
Sample Gangers, panel-5-b, panel-0-b, panel-5-a, panel-2-a; under the search panel-0-b, panel-5-b,
Embracing Power, panel-5-a, The Heist. Deck rankings measured with the heuristic transfer only
partly to the search. `out/s0/baselines/rank_agreement.json`.


## 5. Day-0 baselines

Every Part 5 instrument, with the shipped weights (`src/cptcg/agents/weights.json`, gen-1) and
`ismcts:32` where an agent is needed; JSON under `out/s0/baselines/`. The refit 114 head (`w114`)
and the card-aware model (`cards`, and its identity ablation) are shown beside the shipped head
where the instrument takes a head.

**Oracle set** (`data/arena/oracle.json`): 2,000 MAIN decisions sampled uniformly over 4.13M
decisions of the h20k (1,530), r8k (415) and cov (55) corpora, stored as board specs with the
rules and cards digests; labelled by `cheat:ismcts:2000`'s root value (mean 0.551, quartiles
0.30 / 0.57 / 0.84) and `plan-deep:32`'s best-line replay score, 6.1 s + 6.4 s a position on the
loaded machine (6,236 s on four workers in all). **Caveat, Confirmed by construction:** both
labellers evaluate leaves with the *shipped* 114 head, so the shipped head's agreement with the
oracle is partly self-agreement; the set is a reference for ranking heads against each other and
for Stage 1's oracle-relabelling, not an independent truth.

| instrument | shipped head | w114 (refit) | cards | cards ablated |
|---|---:|---:|---:|---:|
| oracle agreement, Spearman vs `cheat:ismcts:2000` (95% bootstrap) | 0.950 [0.942, 0.956] | 0.925 [0.915, 0.932] | 0.865 [0.851, 0.877] | 0.845 [0.830, 0.859] |
| oracle agreement, Brier vs cheat value (constant 0.5: 0.1005) | 0.0105 | 0.0184 | 0.0462 | 0.0497 |
| oracle agreement, Spearman vs plan-deep score | 0.825 | 0.807 | 0.797 | 0.776 |
| monotonicity, overall violation rate (500 positions, tol 0.005) | 0.0017 | 0.0006 | 0.0663 | 0.0680 |
| monotonicity, `+gig` violations | 0.000 | 0.000 | **0.220** | **0.228** |

The card-aware model fails the `+gig` perturbation one time in five: adding a die to its own Gig
area lowers its value in 22% of positions, where both 114 heads never err. My judgement: that,
more than the identity embedding, is the reason its greedy play trails (kill test 1) — a head
that cannot be trusted on the plainest improvement mis-ranks one-ply previews.

**Belief log-likelihood** (`belief_ll.py out/s0/r8k --games 200`): 72,541 hidden cards and 1,734
face-down Legend slots scored; belief −4.255 nats a card vs uniform-pool −4.783: gain **0.528**
[0.505, 0.553]; zero-probability truths: **0** (the colour bounds never rule out the truth).

**Coverage** (kill test 5 above): h20k 872 triples offered / 21 starved; cov 809 / 13.

**Dice regret** (kill test 6 above): GIG_DIE mean 0.0010, chosen best 55.0%, biggest best 40.9%;
steal mean 0.0006, chosen best 79.5%.

**Identity ablation on the 114 head**: not applicable — the 114 features carry no card identity,
so the ablation is flat by construction; reported as such rather than measured.

**Delayed suite, 133 positions, solved on all 16 scoring seeds** (`arena.py delayed AGENT`;
floor: uniform random 163 of 2,128 trials). Per family (solved/positions) and horizon:

| agent | solved | h1 | h2 | card-sem | play-around | race | dice | defend | removal-first | legend-call | steal-thr | sell-to-afford | gig-shaping | recursion | def-setup |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| heuristic (frozen) | 0/133 | 0/110 | 0/23 | 0/15 | 0/13 | 0/12 | 0/12 | 0/13 | 0/9 | 0/11 | 0/11 | 0/14 | 0/9 | 0/8 | 0/4 |
| neural (shipped) | 28/133 | 21 | 7 | 3 | 1 | 3 | 1 | 0 | 7 | 3 | 4 | 2 | 0 | 2 | 1 |
| ismcts:32 (shipped) | **31/133** | 24 | 7 | 3 | 1 | 3 | 2 | 3 | 7 | 3 | 4 | 3 | 0 | 0 | 1 |
| neural@w114 | 16/133 | 12 | 4 | 2 | 1 | 1 | 1 | 1 | 3 | 1 | 3 | 1 | 0 | 0 | 1 |
| neural-cards | 9/133 | 6 | 3 | 1 | 0 | 1 | 1 | 0 | 3 | 0 | 0 | 2 | 0 | 1 | 0 |
| neural-cards ablated | 16/133 | 9 | 7 | 2 | 1 | 1 | 1 | 0 | 6 | 0 | 1 | 2 | 0 | 1 | 1 |

(Also `mined` 1/1 for the shipped heads and w114, 0 for the card heads; `two-pieces-of-gear` 0
for all.) The new families are hard for every day-0 agent: the search solves 3 of 13 defend and
1 of 13 play-around positions; nothing solves a gig-shaping position. Day-0 numbers, not a
verdict.

**Plan regret** (`plan_regret.py out/s0/h20k --turns 500`, 500 sampled turn starts, both agents'
turns scored by the shipped head): mean regret **−0.038** win-probability points (median −0.002):
the `ismcts:32` turn scores at least the `plan-deep:32` line's in 70.8% of turns, mean scores
0.611 vs 0.574. Cost 1.7 s vs 8.9 s a turn on the loaded machine. Uncertain what the sign means
beyond day 0: the scorer is the same head the search optimises against, so a negative regret
partly says the search is better at pleasing its own evaluator.

**Deck round-robin residuals, Nash support and two-player rank agreement**: kill test 2 above and
the `ismcts:32` row when its run completes.

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

**Do not start Stage 1 on the card-aware model as built.** Kill test 1 is the gate and it failed
on both legs: the card-aware greedy agent does not beat the 114 head by more than the
between-pairing band, and permuting its identity embedding costs it 1.4 points, which is noise.
The test was run once, on the criterion as written, after one documented instrument fix.

What Stage 0 established that survives the failure (all Confirmed):

* The engine is now the FAQ's game (E1–E12), every golden regeneration has its five evidences,
  and the corpora, oracle set and suite were recorded after the last rule change.
* The instruments all produce numbers with intervals, and they agree with each other about the
  card-aware model: it is a better *position evaluator* than its ablation (Brier 0.102 vs 0.114)
  and a worse *ranker of one-ply previews* than the 114 head (panel, delayed suite 9 vs 28,
  oracle Spearman 0.865 vs 0.950), and it fails the plainest monotonicity check one time in
  five where the 114 heads never do.
* The inferred list costs the search nothing measurable at budget 32; the metagame is
  non-transitive under the heuristic (Nash support 3, p < 0.001); a generation costs 10.6 h here.

What I would do before re-running kill test 1 (my judgement, not started, none of it a rule
change): fit the card-aware model with more rows (the 114 head had roughly twice as many) and
with the monotonicity perturbations as an auxiliary loss or as data augmentation, since a head
that rates an added Gig die as bad in 22% of positions cannot rank previews; and evaluate the
greedy agent on the delayed suite and the monotonicity instrument *before* the panel, because
both predicted the panel result at a fraction of the cost. If the refit clears monotonicity and
still fails the panel, the design's premise — that card identity is what the 114 features are
missing — should be treated as refuted rather than retried.
