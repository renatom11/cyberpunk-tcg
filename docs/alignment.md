# Alignment audit: Stage 0 against the unified design

Written 2026-09-21, 18:30–19:30 UTC, while the KT1 rerun pipeline runs and **before any panel or
head-to-head result of the rerun exists**. Read against the unified design's Parts 1, 2, 5 and 6
and its capability-by-layer matrix. Labels as before: **Confirmed** (in the tree or an output file
named here), **My judgement**, **Uncertain**.

The one-paragraph version. Stage 0 built the instruments and the engine the design asked for, and
then spent its second half almost entirely on one cell of the matrix: C4's identity ablation (kill
test 1), its rerun, its corpus, its refits and its oracle. Along the way three whole rows of the
matrix got nothing beyond an instrument (C3c denial has not even that), the deck-discovery row has a
one-off measurement where the design asked for a population that exists from stage 0, and the
Stage 0 gate "all instruments produce numbers" is **not met** for seven of the Part 5 instruments.
None of that was hidden, but none of it was said in one place either. This is that place.

## 1. Capability by capability

### C1 — position evaluation (including race and clock)

* **Delivered.** Dice tokens, the choice-context token and one attention layer in the card-aware
  model (`tools/cards_model.py`; Confirmed). The 114 aggregates keep the race features (Gigs,
  fixer counts, deck sizes; the context carries the Overtime flag). The numpy value path inside the
  search (`tools/cards_agents.py::ismcts-cards`). Visits and root values recorded per decision in
  the harvest (`tools/harvest.py`, `GameRecord.visits/values`).
* **Instrument and day-0 number.** Oracle agreement (`data/arena/oracle.json`, 2,000 positions;
  `out/s0/baselines/oracle_agree_*.json`): shipped head Spearman 0.950, refit 114 head 0.925,
  card model 0.865, ablated 0.845; Brier 0.0105 / 0.0184 / 0.0462 / 0.0497 — against a label that
  uses the shipped head itself, so partly self-agreement (the independent playout label is being
  built in the rerun). Monotonicity (`tools/monotonicity.py`, legal perturbations after the
  instrument fix): the card model is monotone on the steal perturbation 98.9% of the time; every
  head dislikes fewer fixer dice than the rival, a learned turn-parity signal. Race suite: 12
  positions, `ismcts:32` solves 3 (`docs/stage0.md` §5).
* **Missing.** The n-turn boundary bootstrap target (design C: "root value at the start of the
  mover's next turn") — every fit so far used the game outcome z only. The evaluation head has
  never been trained on a search value. Plan candidates evaluated at the turn boundary (B) not
  built. Population decks (D) do not exist, so the value head's distribution is the sampler's.
* **Stage 1 must carry.** Per-decision targets (visits, root values, boundary bootstrap) into
  the fit; the independent oracle label as the agreement instrument; monotonicity every generation.

### C2 — turn planning (including reaction play as defender)

* **Delivered.** Payment as a Pick (E12) — the design's one engine change for C2 — measured first
  (14.18% of payments had content), then wired. The delayed suite grew 68 → 132 positions in
  thirteen families, every one accepted only by `qualify`; the defender family exists as
  `mode: "defend"` positions (13). Plan regret exists (`tools/plan_regret.py`). Semantic Pick
  features (31 features on the policy side, `learn/policy.py`), so a Pick is no longer a bare size.
* **Instrument and day-0 number.** Suite by family and horizon (`docs/stage0.md` §5 table):
  `ismcts:32` 31/132 (h1 24/110, h2 7/22). Plan regret −0.038 (search ≥ plan-deep line in 70.8%
  of 500 turns), scored by the head the search optimises against, so weakly meaningful. Defender:
  3/13. Reaction entropy in the s10k corpus 0.50 nats (coverage report).
* **Missing.** Plan-candidate proposals at the root (design B/C; scheduled for Stage 2 by the
  design, so a deferral by design, not a quiet one). The policy prior over sequences exists only
  as the card model's option head; the shipped `ismcts` still pays one-ply previews. Rival PICKs in
  the tree still answered by `_default_index` (Stage 2 by design). Families at zero for every
  agent: gig-shaping 0/9 and recursion-trade 0/8 for `ismcts:32`; play-around 1/12.
* **Stage 1 must carry.** The policy head as the PUCT prior in the generator; the suite by family
  every generation with the zero families named; a first, budget-capped plan-candidate stage if
  Stage 1's compute allows (the plan draft says where it fits).

### C3a — inference

* **Delivered.** `B_deck` and `B_legend` from public evidence (`learn/tokens.py::belief`),
  `RivalPrior` — a sampler over the possible pool with legality (`learn/opponent.py`), which is more
  than the design asked of Stage 0 ("no sampler yet") because decision 3 made the inferred list the
  default. Known-list mode kept as a flag and recorded in every arena/tourney JSON.
* **Instrument and day-0 number.** Belief log-likelihood gain 0.528 nats a card [0.505, 0.553]
  over the uniform pool, zero-probability truths 0 (`out/s0/baselines/belief_ll_r8k.json`).
  Known-vs-inferred gap on the panel: +0.9 points against the heuristic, inside the band
  (`out/s0/kt3/`).
* **Missing.** `B_hand` (the hypergeometric expectation conditioned on tells) is not an input.
  Tell rejection in the sampler (worlds where the reaction window could not have opened) is not
  built. The population prior for `B_deck` (D) does not exist because the population does not.
  The belief sampler's per-world cost is inside the timing table's `ismcts` rows but never reported
  on its own.
* **Stage 1 must carry.** `B_hand`; the sampler's cost line; belief LL every generation.

### C3b — exploitation

* **Delivered.** The 114 aggregates carry threat and reaction-budget scalars from `opponent.py`.
  Play-around family (12 positions). Exploit gap measured under both samplers.
* **Instrument and day-0 number.** Exploit gap: cheat beats honest 44.6% [39.0, 50.2] inferred,
  52.1% [46.2, 57.9] known — perfect information is worth nothing measurable at budget 32. This
  is also the **cheating-critic gate** from the design's Part 2C: the gate says *do not build the
  critic*; the conclusion was never written down as such until now. Play-around: `ismcts:32` 1/12.
* **Missing.** Forced exploration including attack orderings (B) — nothing forced exists.
  Tell rejection (C).
* **Stage 1 must carry.** The forced-exploration slice; the play-around family reported with the
  reason the search fails it (the sampler's worlds do not contain the QUICK in proportion, or the
  head does not read the belief).

### C3c — denial. **Nothing built. No instrument. No number.**

* The design's matrix row: mirror features (A), Sell/Call as coverage modes (B — this part exists,
  the coverage matrix counts `Sell` and `CallLegend`), a belief-using rival (C/E — the `ismcts`
  self-play rival uses `RivalPrior`, so it is belief-using in the weakest sense), and the leakage
  instrument (F): rival belief entropy after my turn, and the turn at which my triple becomes
  provable, against a denial-blind control.
* Part 6 put mirror features and the leakage instrument in Stage 3. Part 5 lists leakage as an
  instrument, and Part 6's Stage 0 gate is "all instruments produce numbers". By the design's own
  rule this row should have a day-0 number and it has none. **This is the clearest drift.** It is
  also the cheapest to repair: the leakage instrument needs only the belief model that exists
  (`belief_ll.py` already computes the rival's per-card likelihood over a game) — the number is the
  entropy of `B_deck` from the rival's seat after each of my turns, and the first turn at which
  `colour_bounds` fixes my triple. My judgement: half a day. It goes into Stage 1, generation 1.

### C4 — card knowledge

* **Delivered.** Identity embeddings + static card table + text features + attention; option
  tokens carry the card; the coverage sidecar; the identity-ablation agent; the card-semantics
  family (15 positions from FAQ answers).
* **Instrument and day-0 number.** Kill test 1 FAIL on both legs (first run; the rerun is in
  progress and unread). Card-semantics: `ismcts:32` 3/15. Coverage: 871 triples offered in s10k,
  6 starved.
* **Missing.** Exposure floor per card and per (card, mode) (D) — not started; the corpus's
  rarest card appears in about 11% of games (217 of the first 2,000) against a median of 26%.
  Synergy realisation and context play rates (F) — no instrument, no number. Population (E).
* **Stage 1 must carry.** Exposure floor from generation 1; the two missing instruments (both are
  counts over the harvest sidecar plus a card-pair table; a day each); the ablation every generation.

### C5 — dice and Street Cred

* **Delivered.** Dice tokens; die-semantic Pick features; the dice-regret instrument; the dice
  family (12 positions).
* **Instrument and day-0 number.** GIG_DIE regret 0.0010, chosen best 55%, biggest best 40.9%;
  steal regret 0.0006, chosen best 79.5% (`out/s0/baselines/dice_regret_cov.json`). Dice suite:
  `ismcts:32` 2/12.
* **Missing.** The exact die-regret labels as a training signal (C) — computed, never fed back.
* **Stage 1 must carry.** Dice regret and the family every generation; the regret label as an
  auxiliary target once per-decision targets are in the fit.

### G5 — every mode of every card is exercised

* **Delivered.** Coverage accounting at harvest time (`learn/coverage.py`, the sidecar), the
  report and the starvation list (`tools/decision_coverage.py`), per-kind entropy, the policy
  target from visits (`fit_cards.py fit`).
* **Instrument and day-0 number.** s10k: 871 offered / 845 chosen / 6 starved; h20k 872 / 21
  starved. Per-kind visit entropy: MAIN 1.10, PICK 1.34, GIG_DIE 1.19, TARGET 0.39, REACTION 0.50.
* **Missing.** Count-balanced forced exploration and the forced-slice paired advantages — not
  started. The exposure floor. The starvation detector's "valued within a margin" half exists as a
  flag (`--margins`) and was not run for the s10k list.
* **Stage 1 must carry.** Forced slice + exposure floor from generation 1; the detector with
  margins every generation; a zero-growth rule on the starved list in the gate.

### G6 — the system discovers which decks win

* **Delivered.** One round robin under each player (kill test 2: 20 decks, 190 pairs) with
  Bradley–Terry, residuals, Nash and a permutation null (`tools/meta_report.py`), and the
  two-player rank agreement (0.59 [0.17, 0.85]).
* **Instrument and day-0 number.** Residual RMS 0.109 vs null 0.095 (p < 0.001) and Nash support
  1 under `ismcts:32` (panel-5-b 0.999); support 3 under the heuristic. Top of the table under the
  search: panel-0-b 2.68, panel-5-b 2.22, Embracing Power 2.13, panel-5-a 2.03 (BT strengths).
* **Missing.** Everything that makes it a *system* rather than a measurement: the population file
  with identities, the archive, the Legend-triple bandit, `hill_climb` proposals against a rated
  field, the exposure-floor builds, the deck fingerprint as an input, exploitability, transfer,
  diversity and rating-stability numbers. Part 4 is titled "integrated from stage 0" and Part 6's
  Stage 1 says "the population seeded by kill test 2 rated under `ismcts:32`" — the seed exists
  (`out/s0/kt2/ismcts/tournament.json`), the population does not.
* **Stage 1 must carry.** The population from generation 1, rated under both players, with the
  four G6 numbers that are missing today (the plan draft, §G6).

## 2. The capability-by-layer matrix, cell by cell

built = exists in the tree and produced a number; partial = exists in part or exists but is not
used where the design puts it; not started = nothing.

| | A representation | B action & policy | C signal | D decks | E coupling | F evaluation | G compute |
|---|---|---|---|---|---|---|---|
| **C1** | built (dice, context, attention; race in the aggregates) | partial (leaf value yes; plan candidates no) | partial (visits + root values stored; fits use z only; no boundary bootstrap) | not started | not started (no generation yet) | built (oracle, monotonicity, race) | built |
| **C2** | built | partial (payment Pick yes; plan proposals no; policy prior not yet the search's prior) | partial (visits yes; no plan candidates in them) | — | — | built (suite by family/horizon, plan regret, defender) | partial (plan walk exists, not budget-capped inside search) |
| **C3a** | partial (`B_deck`, `B_legend`, scalars; no `B_hand`) | not started (rival PICKs by policy) | built (inferred-list worlds in s10k) | not started (population prior) | built (known-list flag) | built (belief LL, known-vs-inferred) | partial (cost inside timing rows, unreported) |
| **C3b** | partial (threat/budget scalars in the 114) | not started (forced exploration) | partial (sampled worlds; no tell rejection) | — | — | built (play-around, exploit gap) | — |
| **C3c** | not started (mirror features) | partial (Sell/Call counted in coverage) | partial (rival uses `RivalPrior`) | — | partial | **not started (leakage instrument)** | — |
| **C4** | built | built | partial (one corpus; no loop) | not started (exposure floor) | not started (population) | partial (ablation, card-semantics yes; synergy realisation, context play rates no) | built |
| **C5** | built | built | partial (regret labels computed, not trained on) | — | — | built | built |
| **G5** | built | partial (accounting, starvation yes; forced exploration no) | built (visits are the policy target) | not started (exposure floor) | built (sampler slice) | partial (report, entropy yes; forced-slice advantages no) | built |
| **G6** | not started (fingerprint input) | — | — | partial (BT/Nash/residuals run once; no population, bandit, archive) | not started | partial (residual norm, support, agreement yes; exploitability, transfer, diversity, stability no) | partial |

Rows with nothing built beyond an instrument or a one-off: **C3c** (no instrument either) and
**G6** (a measurement, not a system). Those two are the drift.

## 3. Where the work narrowed, and what was quietly dropped

Narrowing (Confirmed from the progress log's timestamps):

* From the first KT1 FAIL onward the machine's four cores were spent on C4/C1 alone: the h20k/r8k
  fits, the two panels, the diagnosis, the 10,000-game search corpus (4 h), five card-model
  configs (about 70 min each on 806k rows), the oracle relabel, and the independent oracle. The
  rulings landed in between because the owner asked for them before any new corpus. Nothing in
  that period moved C2, C3, C5, G5 or G6 except as a side effect of the corpus (the coverage report
  and the reaction entropy come free from the sidecar).
* The report's recommendation (§8 of `docs/stage0.md`) reasons entirely about the card model.
  The owner's rerun instruction was itself about KT1. Both are legitimate — KT1 is the gate — but
  the design's rule is "sequencing is allowed, deferral is not: every stage moves every capability,
  with a number for each", and Stage 0's second half moved one.

Dropped or deferred, item by item (the ones the owner named, then the rest):

| item | design said | Stage 0 did | quiet? |
|---|---|---|---|
| defender family | Part 5: defender suite; Part 6 Stage 2: PICK semantics on reactions | 13 `mode: "defend"` positions built and measured (3/13); reaction PICK semantics exist in the features | not dropped |
| belief sampler | Part 2A: inferred-list sampler in `tools/`, with tell rejection; Stage 2 | `RivalPrior` built in `src/cptcg/learn/opponent.py` (stdlib) with legality, **no tell rejection**, no population prior | partly: the rejection half is unmentioned in the report |
| plan-candidate root proposals | Stage 2 | not built | deferred by design; **Stage 1 draft brings a budget-capped version forward** |
| deck population | Part 4 "from stage 0"; Stage 1 "seeded by kill test 2" | round robin run; no population file | **quiet** — the report lists no G6 obligation for Stage 1 |
| exposure floor | Part 4 (D column, C4/G5) | not built | **quiet** — mentioned nowhere in the report |
| leakage instrument | Part 5 (C3c); Stage 3 | not built; no C3c number | **quiet** — the report's baselines table has no C3c row |
| cheating-critic gate | Part 2C: build only if the exploit gap is positive and material | exploit gap measured at 44.6% (negative); conclusion never stated | quiet — stated here: the gate says do not build it |
| gen0 panel slot | Part 5 | filled in Stage 1 by owner decision 6 | not quiet |
| `B_hand` | Part 2A | not built | quiet |
| mirror features | Part 2A (C3c) | not built | Stage 3 by design |
| n-turn boundary bootstrap | Part 2C | not built; every fit is on z | **quiet** — the report calls the corpus "with visits + values" and never says the fits ignore them |
| forced exploration | Part 3 | not built | Stage 1 by design |
| synergy realisation, context play rates | Part 5 (C4) | no instrument | quiet |
| exploitability, transfer, diversity, rating stability | Part 5 (G6) | no instrument | quiet |
| deck fingerprint as an input | Part 2A | not built | quiet |
| rival PICKs answered by the policy in-tree | Part 2B; Stage 2 | not built | deferred by design |
| engine tells: silent skips, PICK width | decision 2d: report cost, do not land | cost reported; frequency never measured | as instructed |
| `tools/opponent_influence.py` | audit found it broken | deleted 2026-09-25 (the rival-facing block it ablated is no longer in the 114 vector; its historical result stays in `docs/learning.md`; the rival reading is measured by `belief_ll.py` and `leakage.py`) | closed |

**The Stage 0 gate.** "All instruments produce numbers; kill test 1 passes." KT1 failed and is being
rerun as the owner instructed. "All instruments produce numbers" is false for: leakage (C3c),
synergy realisation and context play rates (C4), exploitability, transfer, diversity and rating
stability (G6). Seven of the Part 5 table's instruments have no number. The report said "every Part
5 instrument" in its §5 heading; that was wrong, and it is corrected here.

## 4. Honest reading

* The engine work and the instruments that exist are solid and reproducible; the golden protocol
  held through twelve changes and four rulings; the suite and the oracle are real assets.
* The design's rule that no capability waits was broken in practice by a gate that consumed the
  machine. The right correction is not to stop the rerun (it is pre-registered and nearly done) but
  to make Stage 1's first generation carry every row, whatever KT1 says — which the plan draft does.
* The two things Stage 1 most needs to change: **(1) the learning signal** — per-decision targets
  (visits, root values, the turn-boundary bootstrap) instead of one outcome per game, which is the
  reason 806k rows overfit in three epochs; **(2) the population** — deck discovery as a running
  system from generation 1, rated under both players, because without it C1's data distribution,
  C4's exposure and G6 itself all stay unaddressed. If only one may change, it is the signal.
