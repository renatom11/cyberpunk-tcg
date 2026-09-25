# Stage 1 plan, drafted before the KT1 rerun verdict

Written 2026-09-21 while the rerun pipeline runs; no panel or head-to-head result of the rerun has
been read. Two versions, one per KT1 outcome, sharing everything that does not depend on it. Both
move every capability from generation 1 and both run deck discovery (G6) from generation 1. The
alignment audit (`docs/alignment.md`) is the list of debts this plan pays.

Numbers used below and where they come from: 10.6 h a generation for 30,000 `ismcts:32` games on
4 cores (`out/s0/timing_*.json`, parallel efficiency 0.956); 4.86 s a game with both sides
searching; heuristic self-play 0.16 s a game; the card model fits at about 10 min an epoch on 806k
rows with 4 threads (`out/s1/fitcards_a.log`); the 114 head fits in 3 min on the same rows; the
s10k corpus holds 1,204,666 decisions of which 978,865 were searched (`out/s1/baselines/
coverage_s10k.md`); the rarest card appears in 11% of games and the median card in 26% (first
2,000 games of s10k).

## 0. What is the same in both versions

### 0.1 The learning signal: per-decision targets, not one label a game

806,514 rows from 10,000 games carry about 10,000 independent outcomes: every row of a game shares
its label, and the two seats' labels are complements. That is why config a's holdout Brier was best
after one epoch (0.1283) and rose from the second while train Brier kept falling: 141k parameters against
10k bits. The design (Part 2C) never asked for outcome-only fitting; Stage 0 did it because the
first corpora had no search in them. Stage 1 fits on three per-decision signals that the harvest
already records:

1. **Visit targets** (policy). The root visit distribution at every searched decision — 978,865 of
   them in s10k, all kinds except MULLIGAN and ORDER. Cross-entropy against it is one target per
   decision, and it is the target the card model's option head was already given (config a's
   `ce 1.21`). It carries no outcome noise.
2. **Search root values** (value). `GameRecord.values` holds the search's root value at every
   searched decision: the mean over 32 leaf evaluations, averaged over sampled worlds and rolls. It
   is biased toward the head that evaluated the leaves, so it is mixed, not used alone.
3. **The turn-boundary bootstrap** (value). The target at a decision is the root value at the start
   of the mover's *next* turn (the first searched decision of that turn), and the game outcome z
   beyond two of the mover's turns: `target = λ·v_next_turn + (1−λ)·z`, λ = 0.7 at first (My
   judgement; it is a hyperparameter chosen on holdout Brier against the independent oracle label,
   never on the panel). Where the game ends before the next turn, the target is z.

The fit's value loss is Brier against (3); (2) enters only through (3). The rows tool gains the
boundary lookup (`fit_cards.py rows --boundary`), a `learn/`-level function that walks a game's
decisions and pairs each with the next turn start of its mover; about a day, with a test on a
two-game file where the pairing is hand-checked.

What this buys: the value head sees ~1M distinct targets instead of 10k, and the target at a
mid-turn decision is the position's value *after* the turn resolves, which is the turn-boundary
idea `plan.py` proved and Stage 0 never fed back.

### 0.2 Corpus size before the embeddings mean anything

In s10k the rarest card is in about 1,100 games and the median card in about 2,600. A card's
*marginal* effect on the outcome at ±2 points of standard error needs about 2,500 games with the
card in a list; its *conditional* effect (with the Gear, against that colour, at that die) needs
an order of magnitude more contexts. So:

* marginal effects for every card: ~25,000 games with the exposure floor lifting the tail to the
  median (one generation at the compute below, or two at the 4-core scale);
* interaction structure, the thing the attention layer exists for: ~100,000 games (three to four
  generations at 30k).

The check that an embedding "means something", run every generation (cheap, on rows): the held-out
ablation drop is stable across two by-game splits, and the embedding's nearest-neighbour structure
agrees with the static table above chance (cards that share tags and text features sit closer
than random pairs). A card whose embedding row has moved less than the init scale since generation
1 is listed as *cold*, by name, beside the coverage report's starved list.

### 0.3 Rating the deck population: plain Bradley–Terry, Nash only as a diagnostic

Kill test 2 split: under the frozen heuristic the twenty-deck field is non-transitive (residual RMS
above the null, Nash support 3 — panel-3-b 0.54, panel-5-b 0.38, panel-0-b 0.08); under
`ismcts:32` the residuals are still above the null (p < 0.001) but the equilibrium puts 99.9% of
its weight on one deck (panel-5-b), so it is transitive-with-a-dominant-deck by the criterion; and
the two players' rankings agree only at Spearman 0.59 [0.17, 0.85].

What that means for the population: (i) any rating is a rating *under a player*, so every deck
carries two — under the frozen heuristic (cheap, stable, the fixed yardstick) and under the current
agent (the one that matters, and the one that moves); (ii) sampling training decks from a Nash
mixture under the search would mean training on one deck, so **training samples the population
uniformly** (the design's 50% slice), and **Bradley–Terry with a bootstrap interval is the rating**
because it is defined whether or not the field cycles and its intervals are honest at 20 games a
cell; (iii) Nash weight and support are computed and reported every generation as a diagnostic of
cycling, not used to weight anything.

What would justify Nash weighting later: Nash support ≥ 3 under the *learned* agent for two
consecutive generations, with residual RMS above the permutation null both times, and the
two-player rank agreement not falling while it happens (so the cycling is not an artefact of a
weak player). Until then, the field under the strong player looks like a hierarchy and a
hierarchy is what BT rates.

### 0.4 The six starved triples, forced exploration and the exposure floor

Starved in s10k (offered ≥ 20, never chosen): `Order: first` (10,000 offers — the search never
searches ORDER; `IsmctsAgent.act` hands ORDER and MULLIGAN to the heuristic's rule, which goes
second), Rogue Amendiares *Preem Solo* plain play (4,993), Panam *Strength Through Family* decline
(385), Adam Smasher *Ender of Legends* plain play (219), Shattered Memories decline (112), Adam
Smasher *Metal Over Meat* Unit target (26).

Three of the six are the *plain* (no-GO SOLO) Legend play and two are declines: modes the design
added or the FAQ created, that no agent has ever taken, so no head has a value for the resulting
position. This is what the design's forced-exploration slice is for, and it is built exactly as
Part 3 says: in 10% of generation games, at one uniformly chosen decision, the generator takes an
offered option with probability inverse to its (card, kind, sub-mode) chosen-count so far in the
generation, plays on normally, and the policy target at that decision is the visit distribution
computed *before* the forced move. Each forced game is paired with an unforced replay of its seed.
With 3,000 forced games a generation and ~120 decisions a game the six triples above receive, in
expectation, more forced picks than their whole offered count today allows them chosen ones — the
`Order: first` case in particular gets ~150 forced "go first" games a generation, enough for the
value head to learn what going first is worth instead of never seeing it.

ORDER and MULLIGAN also stop being delegated: the generator searches them at budget 8 (two
options; cheap), so the sidecar shows them as searched and the coverage table stops reading 0.

The exposure floor is the design's D-column item for C4 and G5: per generation, every card must be
in ≥ F lists and every (card, mode) offered ≥ M times, F = the s10k median (26% of games) for the
tail, M = 50. `tools/playtest.py`'s coverage-driven builder already builds legal decks around the
cards with the fewest games; it becomes the 15% "exposure-floor builds" slice of the schedule and
is pointed at the coverage sidecar instead of the knowledge table. What the floor cannot do is
make a mode *good*; the starvation detector with margins (`decision_coverage.py --margins`)
separates "never taken" from "rightly refused" every generation, and the gate carries a
no-growth rule on the starved list.

### 0.5 The delayed suite by family: which layer owns each zero

`ismcts:32` at day 0 (`docs/stage0.md` §5): gig-shaping 0/9, recursion-trade 0/8, play-around
1/12, defensive-setup 1/4, dice 2/12, defend 3/13, card-semantics 3/15.

| family | what the winning lines need | layer responsible | what Stage 1 does about it |
|---|---|---|---|
| gig-shaping | set or adjust dice so a condition holds later in the turn (Industrial Assembly before Octant; a pair for Hanako) | A (dice tokens exist) + B (a within-turn setup the one-ply prior never proposes) + C (the value head has never been trained on faces) | dice tokens in the value head fitted on boundary targets; the plan-candidate stage (0.7) proposes the two-step line |
| recursion-trade | trade now, replay from the trash later; horizon 2 | C (the boundary bootstrap is the only signal that sees the second turn) + A (trash tokens carry identity) | boundary targets; horizon-2 reported separately |
| play-around | the right play depends on whether a QUICK is live given proven colours | C3a sampler (worlds must contain the QUICK in proportion) + A (`B_hand` as an input) | `B_hand`; tell rejection in `RivalPrior`; the family reported with the sampler's world statistics |
| defend | the right reaction (Block, hold, blind Call, QUICK) | B (the policy prior on REACTION; rival PICKs in-tree) | policy head as the prior at REACTION; reactions in the forced slice |
| dice | which die to roll or steal | C5 signal (the exact regret label is computed and never trained on) | dice regret as an auxiliary target at GIG_DIE and steal Picks |
| card-semantics | one card's text decides the play | A (identity) | the PASS/FAIL branches below |

Every family is reported every generation; a family flat for two generations while the panel
rises is the design's stop signal and is treated as one.

### 0.6 Deck discovery from generation 1: what exists at the end of Stage 1

The population starts from the twenty decks of kill test 2 (twelve frozen panel lists, six sample
lists, two starters held out as evaluation-only), with the `ismcts:32` and heuristic round robins
of Stage 0 as their first matchup rows. Every generation: the population is re-rated under the
new agent on a mirrored, sparse matrix (each deck plays 6 sampled opponents × 20 games; cells
decay by 0.5 per promotion, so the full matrix fills over generations); `hill_climb` proposes one
candidate per member against a uniform field with the promoted agent as the player; a candidate
enters on the paired SPRT and displaces the member with the lowest BT under *both* players; the
Legend-triple bandit (arms = colour classes, value = best member's BT) proposes the triples for
the Explorer slots; the exposure-floor builder adds its lists as non-evicting members; nothing is
deleted — a deck that leaves goes to the archive with its rows.

Artifacts at the end of Stage 1 (all under `data/population/`, committed, plus a rendered
`docs/decks.md`):

* `population.json` — per deck: id, name, triple, list, archetype label, games; BT strength and
  bootstrap interval under the heuristic and under each promoted generation; Nash weight; origin
  (seed / hill-climb / bandit / floor).
* `matrix.json` — the matchup matrix under each player, with residuals and the permutation null.
* `triples.json` — the bandit table: every triple tried, its colour class, pulls, best member BT.
* `archive.json` — every deck that ever existed, with its rows.
* `policy_dependent.json` — decks whose BT interval under one player excludes the other's point
  estimate, listed as *player-dependent*, never as "good".
* `docs/decks.md` — the four G6 numbers per generation: exploitability (best proposal's win rate
  against the population), residual RMS and Nash support, two-player rank agreement, transfer
  (the top five against the two starters and the six samples under both players), diversity
  (distinct triples, mean list similarity), and rating stability (rank correlation between
  consecutive generations).

What a reader learns: which triples and lists win under a strong player and by how much (with
intervals); whether the field cycles or ranks; which discoveries depend on who plays them; which
cards have earned their place in winning lists and which never got a fair trial (the exposure
floor's report); and, from the triple table, which of the 2,528 usable triples have been tried at
all.

### 0.7 What else moves every capability in generation 1

* **C3c**: the leakage instrument, from the belief model that exists — after each of the agent's
  turns, the entropy of `B_deck` from the rival's seat and the turn at which `colour_bounds`
  proves the agent's triple, against a control that Sells and Calls by the heuristic's rule on the
  same decks. Half a day. Mirror features stay in Stage 3; the number does not wait.
* **C4**: synergy realisation (printed combos executed when both halves were available, from the
  sidecar) and context play rates (play rate of a card conditioned on the rival's board class).
  A day each; both are counts over the harvest sidecar.
* **G6**: the four missing numbers in 0.6.
* **C2**: a budget-capped plan-candidate stage brought forward from Stage 2 in its cheapest form —
  at the first MAIN decision of a turn only, `plan.py`'s walk at budget 8 proposes up to three
  whole-turn lines whose first actions get extra root prior mass (design Part 2B). Cost measured
  on 200 turns before it is switched on; if it exceeds 15% of a game's search time it stays off
  and the number is reported.
* **Gate** (every generation): `decide` (panel, head-to-head, generalisation) plus the identity
  ablation, no growth in the starved list, and every instrument reported — the suite by family,
  oracle agreement against the independent label, monotonicity, belief LL, exploit gap (every
  third generation, it costs 20 min), dice regret, coverage, leakage, the four G6 numbers.

### 0.8 Compute

Measured: 30,000 games at 4.86 s on 4 cores at efficiency 0.956 = 10.6 h. Not in that figure: the
fit (card model 10 min an epoch on 806k rows; 30k games at rate 0.5 is ~2.4M rows, 30 min an epoch,
so a 10-epoch fit is 5 h; the 114 head is minutes), the gate (three arena runs plus the suite, ~1.5
h), the deck phase (20 decks × 6 opponents × 20 games = 2,400 searching games ≈ 0.9 h; at 40
decks 1.8 h), the exposure-floor and forced slices (inside the 30k).

**A week on 4 cores** (168 h): at 30k games a generation is 10.6 + 5 + 1.5 + 1 ≈ 18 h → nine
generations, of which the fit is a quarter. The plan for 4 cores: 15,000 games a generation for the
first three generations (the per-decision targets make 15k games ~1.5M targets, more than Stage 0
ever had), rows at rate 0.25, 8 epochs — ~9 h a generation → ~18 generations a week, the deck phase
every generation at 20–30 members. Rows are materialised once per generation and the fit reads a
window of three generations.

**A week on 16 cores**: play scales linearly (efficiency measured at 0.956 on 4; assume 0.9 on
16): 30k games in 3 h; the torch fit on 16 threads roughly 2.5× faster (attention batches are
small; My judgement) → 2 h; gate and deck phase in parallel with the next generation's play.
About 6 h a generation → ~28 generations a week at 30k, the full design's cadence with a 48-deck
population.

**When renting cores changes the plan.** Two thresholds. (1) The moment the deck phase is wanted
every generation at the design's 32–48 members: on 4 cores that alone is 1.8 h a generation, a
fifth of the budget, so the 4-core plan runs it at 20–30 members and fills the matrix over three
generations. (2) The moment the fit exceeds a third of the generation: at 30k games it does on 4
cores today. Below those thresholds the 4-core box is the right tool because the design's own
Part 6 says the engine, not the network, dominates and the engine scales with cores; a GPU stays
irrelevant until the corpus is several million decisions with visits and the fit is the bottleneck
even on 16 cores.

Recommendation: start on 4 cores at 15k games a generation for three generations (about 27 h);
rent 16 cores from generation 4 if the first three show the instruments moving, because by then
the population and the corpus justify the full cadence.

## 1. Version PASS: the card-aware model is the agent

KT1 passed means: `neural-cards` above `neural@w114` on the panel by more than the between-pairing
band *and* the ablation drops it by more than the band. Then:

* **Generator and player**: `ismcts-cards:32` with the chosen weights (`out/s1/wcards.npz` →
  `out/learn/gen-003/…`), the policy head as the PUCT prior (retiring the one-ply previews; the
  numpy path is in `cards_agents.py`), the value head at the leaves. The `gen0` panel slot is filled
  with this promotion (owner decision 6).
* **Fit each generation**: the card model on the per-decision targets of 0.1, window of three
  generations, hyperparameters from the rerun's choice (config a–e whichever won), changed only on
  holdout Brier against the independent oracle label and the monotonicity rate. The 114 head is
  refit alongside on the same rows as the comparison head — the ablation gate and the 114
  comparison are both run every generation, so a later loss of the identity effect is seen.
* **Everything in §0.**
* **Failure signal inside Stage 1** (design Part 6): panel flat across two generations with the
  ablation still passing → the search budget is binding; raise it to 64 before adding anything.

## 2. Version FAIL: the 114 head runs the loop, the representation question runs beside it

### 2.1 What a second FAIL would establish

With the inference-context bug fixed, the monotonicity instrument legal, and the corpus symmetric
search self-play: a 141k-parameter token model fitted on 10k games' *outcomes* does not produce
better greedy play than a 114-aggregate head fitted on the same rows, and its identity embedding
is not load-bearing in play. It would **not** establish that card identity is useless; it would
establish that outcome-only fitting at this corpus size cannot make a token model's play better
than aggregates, which 0.1 and 0.2 predict independently of the panel. The panel result and the
Brier result (config a's best holdout 0.1283 against the 114 head's 0.1377 on the same rows; corrected 2026-09-23, the draft first quoted 0.1364, a misread of the log) would
then agree: at 10k outcomes the representation has nothing to learn from.

### 2.2 The next diagnostic (not a re-tune)

Two experiments, both on rows, both cheap, both pre-registered here:

1. **Signal, not representation.** Fit the 114 head and the card model on the s10k *per-decision*
   targets (0.1) with the same split, and score both against the independent oracle (the playout
   label) and on policy top-1 against held-out visits. If the card model pulls ahead of the 114
   head on those and not on outcome Brier, the failure was the signal. This uses the corpus that
   exists and the rows tool with the boundary lookup; no new games.
2. **Held-out-card generalisation.** Hold out every game containing one of 12 chosen cards (four
   Legends, four Units, two Programs, two Gear, spread across the exposure range), fit both heads,
   and score each on positions containing the held-out card only. A head that reads identity
   should be *worse* than the 114 head on cards it never saw and better on the rest; a head whose
   embedding is decorative shows no gap either way. This is the direct test of whether the
   embedding carries anything, independent of play.

### 2.3 The alternative representation and signal it would test

If (1) says signal: Stage 1 runs on per-decision targets with the token model (this is then the
PASS loop delayed one generation, and the plan above applies). If (1) says representation and (2)
says the embedding is decorative: the alternative is the **114 aggregates plus a bag of cards** — a
151-wide multi-hot per owner and zone-class (field, hand-known, trash, Legends face-up) added to
the aggregate head, no attention, no tokens, ~5k parameters. It tests whether identity helps at all
when it cannot overfit, which the attention model cannot answer. If *that* head clears the ablation
(shuffling the bag's columns must cost panel points), identity matters and the token model's
failure is capacity; if it does not, identity is not what the 114 features lack, and the design's
premise is refuted for this game at this strength — the report says so and Stage 1 continues on
the 114 head with the policy head from visits as the only new input.

### 2.4 The loop meanwhile

Nothing in §0 waits for the diagnostic. Stage 1 under FAIL runs the existing `ismcts` (114 head,
`RivalPrior`, inferred list) as generator and player, with:

* the policy head from visits (`fit_policy.py` exists; it becomes the PUCT prior in `ismcts`) —
  the one B-layer change that is independent of the representation;
* per-decision value targets (0.1) for the 114 head;
* forced exploration, the exposure floor, the population, the leakage and G6 numbers, the
  plan-candidate stage — all of §0;
* the gate as in §0.7 minus the identity ablation (reported as not applicable for the 114 head),
  plus the two diagnostics' results attached to generation 1's ledger entry.

The gen0 panel slot stays empty under FAIL until a card-aware head passes the ablation; the plan
records that as an open obligation rather than filling it with a head that failed the gate.

### 2.5 Card knowledge (C4) without a card-aware model — what the FAIL version still does

*(Added 2026-09-25 on the owner's instruction: the FAIL version must move every capability.)*

Card knowledge does not have to live in the value head. In this programme it lives in three other
places, and Stage 1 moves each of them with a number every generation:

* **Search.** The search plays the engine's scripts, so it evaluates a card by what the card does,
  whatever the value head knows. Stage 1 makes the search reach cards it would otherwise skip:
  * the forced-exploration slice and the exposure floor (§0.4);
  * the policy head from visits as the prior (§2.4). Its option features already carry per-card
    features for Play options and the 31 semantic Pick features, so the prior can prefer one card
    over another without an identity embedding.
* **Deck-level identity.** Per-card evidence is collected on the deck population, not in the
  network:
  * the paired single-card swap test (\`hill_climb\`) on every member each generation;
  * the paired Legend-swap test (\`tools/legend_swap.py\`);
  * in-deck win-rate difference per colour context, from the population's games.

  These say which cards win in which decks under the current player, with intervals. That is the
  C4 knowledge a deck builder uses.
* **Instruments, every generation:**
  * the card-semantics family of the delayed suite (15 positions, solved count);
  * context play rates (a card's play rate by the rival's board class);
  * synergy realisation (printed combos executed when both halves were available);
  * the starved-triples list;
  * the per-card swap results.

  The first two and the last are counts over the harvest sidecar and the population's games,
  with no model.

**When a card-aware model comes back.** Only if the pre-registered diagnostic says so:
* experiment 1's R2 holds for the card model and R3's legs clear; or
* experiment 2 finds the embeddings "did work"; or
* the corpus of per-decision targets has grown past ~100k games (§0.2) and the held-out-card test
  is re-run and passes.

Until then C4's number is the card-semantics family and the swap tests, not an ablation.

### 2.6 The deck population starts now, on the 114 head (G6)

*(Added 2026-09-25.)* The population exists before any training loop:
* **Seed:** the twenty KT2 decks, the twelve frozen panel lists and the eight \`data/decks\` lists.
  The two retail starters are marked evaluation-only.
* **Rating:** each deck gets a Bradley–Terry strength with a 95% bootstrap interval (1,000
  resamples of games within each matchup) under three players:
  * the frozen heuristic (KT2, 40 games a pair);
  * \`ismcts:32\` (KT2, 20 games a pair);
  * the Stage 1 head \`neural@out/s1/w114.json\` (new, 20 games a pair, greedy).

  The first two re-read existing round robins; the third is a new round robin run between
  experiment steps.
* **Files:**
  * \`data/population/population.json\`: members, lists, triples, colour class, origin, and the
    ratings per player with intervals;
  * \`data/population/matrix_<player>.json\`: the matchup cells.
* **What a reader gets from day one:** a ranked list of twenty decks, each rated under three
  players with intervals, and a player-dependent flag (a deck whose interval under one player
  excludes the other's point estimate).
* **What comes later:** proposals, the Legend bandit, the archive and the per-generation re-rating
  come with the loop (§0.6). Nothing here trains anything.

## 3. What this plan does not do

It does not tune the card model on the panel, in either version. It does not add a second
attention layer, a bigger embedding or more epochs as a response to FAIL (2.3 is a *smaller*
model). It does not change a rule. It does not build mirror features, tell rejection beyond the
window case, or the cheating critic (the exploit gap says no). It does not start before the rerun's
verdict is read and written into `docs/stage0.md`.
