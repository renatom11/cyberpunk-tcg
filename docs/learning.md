# Learning from play

The deckbuilder learns from games; the player does not. Its evaluation is a table of hand-written
constants that ten thousand games leave untouched. The training loop closes that gap:

```
   self-play with search  ──►  experience files  ──►  train policy + value  ──►  gate
          ▲                                                                       │
          └────────────────────  accepted weights  ◄────────────────────────────────┘
```

This page is the shipped record of that loop. **What exists today is the first box and the last
one: experience capture, and the gate that every future generation has to pass.** The search agent
and the model arrive in later stages, and each one adds its section here — including the
generation-by-generation numbers, published whether or not they flatter the run. Until then the
honest summary is: the format is in place, the measuring instruments are built and tested, and the
only games stored so far were played by the existing heuristic agent, which does not search.

## What is stored, and what is deliberately not

**Replays plus search output. Never features.**

A game of this TCG is fully determined by `(ruleset digest, decklists, seed, action indices)`.
Nothing else is needed: `ops.draw` pops the top of an already-shuffled deck and consumes no
randomness, and every choice is recorded as an index into the legal option list the engine built.
So `sim.record.Replay.steps(reg, cfg)` re-yields the exact `(state, action index)` pair for every
decision of the original game, from an action list of a few bytes per decision.

That makes every *derived* quantity free to recompute and expensive to keep:

* the feature vector — recomputable, and it changes shape whenever `learn/features.py` changes, so
  a stored copy would be a second source of truth that silently goes stale;
* the legal option list — recomputable, and it is the engine's business, not the file's;
* the value label — recomputable, because it is just who eventually won.

Exactly one thing is **not** recomputable: what the search was thinking. Which options it spent its
iterations on is the policy training target, and it exists nowhere else once the process exits. So
that, and the search's own value estimate, is written alongside the replay and nothing else is.

A record with no search output is still a complete value-training example, because the value label
comes from the outcome. That is what the cheap bootstrap generation writes.

## The file

One JSON object per line (JSONL), UTF-8, gzip when the path ends in `.gz`. Appendable in both
forms — a gzip append writes a second member, and concatenated members read back as one stream —
so a chunked session can keep adding to the generation it is filling.

Written and read by `src/cptcg/learn/experience.py`:

```python
write_games(path, records, *, append=True) -> int
read_games(path, *, rules=DEFAULT_CONFIG.digest()) -> Iterator[GameRecord]
```

### Schema, field by field

Version `format = 1`. Every field is present on every line; optional ones are `null` when absent.

| Field | Type | Units / meaning |
|---|---|---|
| `format` | int | On-disk schema version. A reader refuses anything it does not know. |
| `rules` | string | `RulesConfig.digest()`, 16 hex characters: the ruleset this game was played under. |
| `seed` | int | The game seed. With the decks and the ruleset it reproduces the game exactly. |
| `decks` | array of 2 objects | `{"name": str, "legends": [card id ×3], "main": {card id: count}}` — the same serialisation `Replay` uses. |
| `agents` | array of 2 strings | Agent name per seat, e.g. `["heuristic", "heuristic"]`. |
| `actions` | array of int | One entry per decision, in order: the index into that decision's legal option list that was played. |
| `winner` | int or null | Seat 0 or 1; `null` if the game reached no winner. |
| `end_reason` | string or null | `EndReason` name, e.g. `SEVEN_GIGS`, `OVERTIME`. |
| `turns` | int or null | Turn number the game ended on. |
| `visits` | array of strings, or null | Per decision, base64 of one **byte per legal option**: the search's visit counts. An empty string marks a decision the search skipped. `null` means the whole game carries no search output. |
| `values` | string or null | base64 of one **byte per decision**: the search's win probability for the player to move at that decision. All-or-nothing — either every decision has one or the field is `null`. |
| `sims` | int or null | Search iterations per decision, if the search ran a fixed budget. Documentation for the visit bytes, which are scale-free. |
| `meta` | object | Free-form and omitted when empty: generation number, sampler mix, anything a later analyst would want. Never anything about a human being. |

`len(actions)` is the number of decisions, and `visits` (when present) has exactly that many
entries; the *i*-th entry has exactly as many bytes as decision *i* had legal options. Reading
checks that width against the engine and raises rather than silently misaligning every example
after it.

### Quantisation

Both search outputs are quantised to one byte, which is what keeps a searched record at 26 bytes
per decision rather than several hundred.

**Visit counts** are normalised by the **maximum**, not by the sum:

```
byte[i] = int(255 * count[i] / max(count) + 0.5)          # half-up, so it is reproducible
```

Normalising by the maximum keeps the search's choice exactly — the argmax is always the byte 255,
whatever the iteration budget was — and a training distribution is recovered by renormalising:
`visit_policy(bytes)` returns `byte[i] / sum(bytes)`. What is lost is the absolute number of
iterations, which is why `sims` records it once for the whole game. An all-zero row (a decision the
search did not visit at all) reads back as a uniform distribution: no opinion, rather than a false
one. Worst-case error on a share is under half a byte, about 0.2 percentage points at a typical
branching factor.

**Values** are a win probability in `[0, 1]` for **the player to move at that decision**, not for
seat 0:

```
byte = int(255 * clip(v, 0, 1) + 0.5)      # back: v ≈ byte / 255, error ≤ 1/510
```

Values outside `[0, 1]` are clipped rather than wrapped, so a broken search cannot write a byte
that decodes to nonsense.

### The ruleset gate

Every record carries the digest of the `RulesConfig` it was played under, and `read_games` refuses
a record whose digest is not the one the caller asked for, naming both:

```
gen3.jsonl:412: record was played under ruleset 149b39c8f55e9d41, this build is 6b1f…
```

A changed ruling makes the stored game a different game. Mixing one generation's experience into
another's training set after a rules fix would be invisible in a loss curve and would corrupt the
model quietly, so this is an error and not a warning. `read_games(path, rules=None)` reads anything
— for a forensic look at an old file, never for training. `Replay.steps` applies the same check at
replay time, so a mismatch cannot slip through by another door.

## Reading it back

One function turns storage into examples, so there is exactly one way to do it:

```python
replay_features(record, reg, cfg) -> Iterator[(state, chosen, visits, value)]
```

It walks `Replay.steps` and yields, once per decision: the live `GameState` at that decision, the
option index that was played, the quantised visit bytes (or `None`), and the search's value
estimate (or `None`). The state is the *same object* mutated forward by the engine, so read what
you need from it before asking for the next item — `features(state, state.pending.player)`, say —
and clone it if you want to keep it.

The value **label** is not in that tuple on purpose: it is `outcome(record, player)`, which is who
eventually won. A value head must be fitted to the future, not to the search's guess about the
future; the search's estimate is stored for diagnostics and for later comparison, not as a target.

## Reading a game

`cptcg dump <file>` (also `python tools/dump.py <file>`) renders one stored game as text: turn by
turn, every decision with all of its legal options **in words**, the search's visit share beside
each, a marker on the one that was played, the value estimate, and the result.

```
--- Turn 1, P1 active -----------------   gigs 0-0   cred 0-0   units 0-0   hand 6-7
  #3    P1  Start phase - Take a Gig    [search value 0.157 for P1]
         [ 0] Roll d4                                                       99   21%  ####
         [ 1] Roll d6                                                       59   12%  ##
         [ 2] Roll d8                                                       45   10%  ##
         [ 3] Roll d10                                                      15    3%  #
      -> [ 4] Roll d12                                                     255   54%  ###########
```

(The visit numbers in that excerpt are synthetic — nothing searches yet.)

The wording comes from `web/view.view_state` — the same labels the browser shows a human player —
so the dump and the UI cannot drift apart, and a fiddly Pick option gets the same careful
description in both. This is the archival deliverable: a later analyst can read **what the AI
considered**, not just who won. It is optimised for reading; a tool that wants the numbers should
call `replay_features`.

`--stats` prints the size budget for a file, `--list` one line per game, `--game N` picks a record.

## Size budget

Measured on 100 heuristic self-play games over freshly sampled deck pairs (136 decisions per game,
6.0 legal options per decision), with `tools/dump.py --sample`:

| Stored | bytes / decision | bytes / game | 10,000 games |
|---|---|---|---|
| Replay only (no search output) | 12.6 | 1.7 KB | 17 MB, **2.4 MB gzipped** |
| Replay + visits + values | 26.1 | 3.5 KB | 35 MB, **11 MB gzipped** |

Gzipped, that is 1.8 and 8.0 bytes per decision respectively. The search rows dominate: they are
`4/3 × options` characters of base64 per decision, which is why the counts are bytes and not JSON
integers. (The searched row is measured with synthetic visit counts of realistic shape; a real
search distribution is peakier and compresses at least as well.)

**Retention policy for this repository: keep the most recent generations, prune everything older.**
Experience is regenerable — a seed, two decklists and a digest reproduce it exactly — while trained
weights are not. So weights are committed and kept forever, and a generation's experience is
deleted once the generation that learned from it has been gated. This is a public repository and a
few hundred MB of regenerable JSONL has no business in its history.

## The gate

`tools/arena.py` (also `cptcg arena`) is the gate. **Nothing about this project's AI may be claimed
without a number from it**, so it matters more than anything else built for the loop. Five
instruments, one command each:

```bash
python tools/arena.py a-vs-b heuristic random     # two agents, paired seeds, SPRT, Wilson
python tools/arena.py panel heuristic             # the frozen benchmark panel
python tools/arena.py exploit AGENT               # the cheating upper bound
python tools/arena.py delayed heuristic           # the delayed-reward suite: solved N of M
python tools/arena.py generalisation heuristic    # training decks vs the held-out starters
```

Every command writes JSON under `out/arena/` and appends its report to the end of this page,
whether or not the numbers flatter the run.

### The design: a strong deck must never read as a strong agent

`sim.runner.run_match` already plays every seed from both seats, so first-player advantage and
shuffle luck cancel for free. That is not enough. In `run_match(a, b, A, B)` agent A always holds
deck `a`, so an agent handed the better half of a pairing looks better than it is. So every match
here is played **twice**, with the deck assignments swapped and the seeds shared:

| | agent A holds | agent B holds |
|---|---|---|
| match 0 | deck a | deck b |
| match 1 | deck b | deck a |

Four games per seed, and each agent has held each deck in each seat. Those two games also form a
**pair**, and the pair is what the sequential test runs on, exactly as `deck.builder.hill_climb`
pairs a champion against a challenger on shared seeds:

* the same deck won both games — the *deck* decided the pair, and it says nothing about play;
* different decks won — the *agent* decided; count the pair for whoever won both games.

The SPRT then runs on those decisive pairs only, which strips out most of the deck-and-shuffle
variance; a hopeless matchup settles in a few dozen games rather than a few hundred. The headline
rate and its Wilson interval are still reported over every game played, because that is the number
a reader wants and a paired count is not a win rate.

The design is exact rather than merely unbiased, and that is a test rather than a claim: put the
*same* agent name on both sides and the two swapped matches are the same games, so the headline
rate is exactly 50%, there are no decisive pairs at all, and each agent sits in each seat in
exactly half the games (`tests/learn/test_arena.py`). Decks come from `learn.decks.sample_pair`, so
a match is measured over many freshly sampled decks and an agent that is only good with one list
has nowhere to hide.

### Calibration: the 98.6% figure, and why this tool does not print it

The plan quotes the shipping heuristic at **98.6% against random**, measured over 360 games, three
deck pairings, seats mirrored. Reproducing that number was the acceptance test for the arena. It
does not reproduce it, and the reason is the whole point of building the tool:

| measurement | games | heuristic vs random |
|---|---:|---|
| balanced, sampled decks (`arena a-vs-b heuristic random --no-sprt`) | 360 | **93.9%** [90.9–95.9] |
| unbalanced, sampled decks (`--no-swap`) | 360 | 95.8% [93.2–97.5] |
| unbalanced, the three retail matchups (the original recipe), seeds 0 / 11 / 21 | 360 each | 96.7% / 97.5% / 97.8% |
| the same with the four `bench.py` matchups | 360 each | 96.9% / 97.8% / 98.1% |

So the historical figure is reproducible *under the historical protocol* — 96.7–98.1% across
seeds, with 98.6% at the top of that spread — and it is about a point and a half too high because
the heuristic always held the same half of every pairing. On the three retail matchups at one seed
the effect is stark:

| the heuristic holds | its win rate |
|---|---|
| deck A of each pairing (the old recipe) | 97.2% |
| deck B of each pairing | 88.6% |
| both, half the games each (the arena) | 93.1% |

An 8.6-point swing from nothing but which list the agent was handed. `--no-swap` is kept as a flag
so anyone can re-derive that table, and it prints a warning line into its own report saying deck
strength is inside the number.

**The honest summary: the shipping heuristic beats random about 94% of the time, not 98.6%.** Every
older number in this repository that compared two agents on fixed deck assignments is high by
roughly this much, and none of them is restated here — they are simply superseded by whatever the
arena prints from now on.

### The frozen panel

`data/arena/panel.json` is **data, not code**, so freezing it is visible in a diff. It pins the
opponents (`random`, the frozen `heuristic`, and a generation-0 snapshot that does not exist yet
and is reported as "not available yet" rather than quietly skipped), *and* the protocol: six deck
pairings from deck seed 20260910, 60 games each, no early stopping. A fixed sample is what makes
two generations comparable, so the panel never uses the SPRT.

The file carries a digest of its own contents; loading it checks that digest, and
`tests/learn/test_arena.py` pins the digest a second time in the test itself. Changing the panel is
allowed — changing it silently is not, and a change makes scores before and after incomparable.

### The cheating upper bound

`arena exploit AGENT` plays an agent against `cheat:AGENT`: the same agent, the same budget, the
same evaluation, with determinization (`core/view.determinize`) replaced by the true state. The
gap is the value of perfect information to that search, which is the cost of hidden information —
**a ceiling for that agent at that budget, and not an upper bound on play quality in general.**

`cheat:` is a name prefix, so a worker process can build the cheating variant from the name alone,
and it refuses an agent that never samples hidden information: the one-ply heuristic reads the true
state already, so there is nothing to take away from it. No search agent exists yet, so today the
mechanism is exercised end to end against a stub that consults `core/view.py`
(`tests/learn/test_arena.py::test_exploit_measures_honest_against_cheating`). The instrument is
built and tested; the number it exists to print arrives with the search agent.

### The delayed-reward suite

This is the falsifiability instrument for the whole loop. `data/arena/delayed.json` holds positions
where the winning move has low immediate impact, each of which qualifies only if **all three** hold:

1. an exhaustive search over the acting player's own decisions for that turn finds a line that
   wins the game inside the position's **horizon**, and
2. the frozen heuristic does **not** find it, on any of the seeds the suite scores agents on, and
3. uniform **random** play does not stumble into it on more than a quarter of those seeds.

#### The horizon: what "wins" means, and how far ahead

Reaching seven Gigs does not end the game where it happens — `WinCheckStep` runs at the *start* of
a turn — so "wins" is not "seven Gigs on the board". After the searched turn ends the game is
played on with the frozen heuristic in both seats, and the line counts only if the game then really
ends with the searched player as the winner. A line that reaches seven and has them stolen back
does not count.

Each position carries a `max_turns`, counted in the searched player's own turns, and
`arena delayed` prints it as a column:

| horizon | what the position tests | what wins it |
|---|---|---|
| 1 | within-turn sequencing | the searched turn banks the win by itself; the check fires at the start of the next turn |
| 2 | a **delayed** reward | the searched turn cannot win; it has to leave a board the *greedy* continuation converts a turn later |

A horizon-2 position is the plan's claim in its smallest honest form: the move that wins is worth
nothing on this turn's board, the rival answers in between, and the payoff arrives on the turn
after the one that earned it. A one-ply agent scoring the board at the end of its turn cannot see
it. The first version of this suite had no such position — every entry was won inside the searched
turn — so it measured within-turn sequencing and nothing else, whatever the headline said.

**What it still does not measure.** It is not a search over multi-turn *plans*. Only the searched
turn's decisions are chosen, by the solver and by the scored agent alike; every later turn, on both
sides, is the frozen policy. A horizon-2 row asks "is there a move here whose payoff lands next
turn, and do you make it", not "can you plan two of your own turns".

That is not a preference, it is what fits. Searching two of my own turns is a product, not a sum,
and the measurement is not close: on fourteen of fifteen sampled mid-game turns, one turn's own
tree passed 30,000 clones without exhausting, at roughly 12,000 leaves. Crossing that with a
second turn's tree is on the order of 3.6 × 10⁸ clones — about five hours per position at the
~20,000 clones a second this engine manages — against the ~6 s scoring an agent on the whole suite
costs today, and the ~9 s `--verify` costs. Widening the *goal* was affordable; widening the
*search* was not, and the difference is stated here rather than blurred.

#### The floor, and why the heuristic's zero is not one

The frozen heuristic scores **zero** on this suite — but that zero is a *selection criterion*, not
a measurement: a position is only in the file because the heuristic missed it on exactly the seeds
it is scored on. Read alone it says nothing about how hard the suite is. Uniform random play, on
the first version of this suite, solved 1 of 6 positions and won 9 of 24 trials, because several
positions were winnable by many lines rather than by one.

So every position now stores what random play scores on it, measured on the same sixteen seeds
agents are scored on, and the report prints it as a **floor** column beside the agent's own. Three
things keep the number readable:

* a position qualifies only if random wins at most a quarter of those seeds (`MAX_FLOOR`), which
  is checked at qualification and re-derived by the tests;
* agents are scored on sixteen seeds, and a position counts as solved only when the agent wins
  **all** of them — a floor-level agent reaches that by luck with probability 0.25¹⁶;
* the seeds a position is hand-picked on (1–4) are disjoint from the ones it is scored on
  (101–116), so no agent is ever graded on the seeds that selected the position.

#### The solver, and where positions come from

The solver (`learn/delayed.turn_search`) is exhaustive up to two limits it states rather than
hides: a node cap, after which it reports `exhausted=False` and has proved nothing, and the same
option equivalence the frozen agent uses (two options that differ only in which *copy* of a card
they name are one option). It stops at the first win, because existence is all the suite needs.

Positions arrive two ways. Hand-built ones are board specs in the same shape as
`tests/conftest.board`, and a test builds one both ways and compares information keys so the two
cannot drift. They are built like real mid-game boards — three Legends and a real remaining deck
per side — because a value head reads list size, undrawn fraction and Legend RAM, and a
three-card deck would have it extrapolating for reasons that have nothing to do with planning.
Mined ones come from `arena delayed --mine N [--max-turns 2]`, which scans self-play games for
turns where the solver finds a win the heuristic misses and stores them as a replay prefix, which
reproduces the position exactly. Mining runs its three tests cheapest-first — the heuristic must
miss, random must not win it often, and only then is the tree searched — which matters at a
horizon of two, where a hopeless candidate costs a minute of solver and the other two tests cost a
second.

Every position is stored **with its verification** — the winning line, the nodes it cost, the
heuristic's failure, the random floor — and `tests/learn/test_delayed_reward.py` re-derives all of
it, so a stored claim that stops being true is a test failure and not a silent lie.
`arena delayed --verify` does the same from the command line.

The honest caveat: the rival's reply is one competent defence and one sample of their Gig die, not
a proof against every defence. A position is a witness that a win was available, not a
game-theoretic value.

### The generalisation gap

`arena generalisation AGENT` measures the same agent against the same baseline on three deck
populations: the training mix, the two **held-out retail starters**, and fresh random decks from a
deck seed training never used. Both seats draw from the same population in every row, so each
number is about play rather than about which population is stronger; what matters is the difference
between the rows. A gap that grows generation over generation means the model is memorising
matchups instead of learning the game, and it is reported every generation whether or not it
flatters the run.

The frozen heuristic's baseline, measured below, is **negative**: against random it wins 91.1% on
the training mix, 95.8% on the held-out starters and 94.4% on fresh random decks, a gap of −4.7
points to the holdout (z = −2.56). That is the expected sign for an agent that cannot memorise
anything — a hand-built retail deck rewards competent play more than a random list does, so the
held-out row is the *easier* one. The number to watch is the change: a model that has learned the
game keeps this gap where it is, and one that has learned six deck pairings drives it positive.

## Honest caveats

* **The games stored today were played by the heuristic agent**, which does not search. They carry
  no visit counts, so they train a value head and not a policy.
* **A value function fitted to heuristic games predicts outcomes under heuristic play.** It is a
  starting prior that makes the first search generation cheap, not ground truth, and it inherits
  that agent's biases until search generations correct them.
* **Nothing here is validated against human play.** No human has played this game competitively and
  this project records no human games. Every number in this document is the AI measured against
  itself.
* **The card pool is 150 of 151.** `rebecca-having-a-moment` is excluded until her ability is
  revealed, so a model trained now has never seen her; see `data/COVERAGE.md`.

## Arena runs

Everything below this line is appended by `tools/arena.py`, newest last. A run's machine-readable
twin is in `out/arena/`.


### heuristic vs random — 2026-09-10 19:58 UTC

`arena a-vs-b heuristic random --no-sprt` over 6 deck pairings sampled from deck seed 20260910.

360 games over 6 deck pairings, 180 paired comparisons — every seed played from both seats and with the deck assignments swapped. Ruleset `149b39c8f55e9d41`, 2.7s.

| | games | win rate | 95% Wilson |
|---|---:|---:|---|
| **heuristic** | 360 | 93.9% | 90.9–95.9% |
| random | 360 | 6.1% | 4.1–9.1% |

Paired test: 159 of 160 decisive pairs (99.4%) — no sequential test was run (fixed sample).

heuristic sat in seat 0 in 180 of 360 games — exactly half, by construction. heuristic on the play: 98.9% [94.0–99.8] (who goes first is the d20 winner's *choice*, so this is description, not balance). Average game length 11.4 turns. End reasons: OVERTIME 15, SEVEN_GIGS 345.

| deck pairing | games | heuristic win rate |
|---|---:|---|
| `sampled-0` built vs built-b | 60 | 95.0% [86.3–98.3] |
| `sampled-1` built vs explorer | 60 | 91.7% [81.9–96.4] |
| `sampled-2` Sample Gangers vs random | 60 | 91.7% [81.9–96.4] |
| `sampled-3` random vs random-b | 60 | 95.0% [86.3–98.3] |
| `sampled-4` random vs random-b | 60 | 95.0% [86.3–98.3] |
| `sampled-5` random vs built | 60 | 95.0% [86.3–98.3] |


### heuristic vs random — 2026-09-10 19:58 UTC

`arena a-vs-b heuristic random --no-swap --no-sprt` over 6 deck pairings sampled from deck seed 20260910.

360 games over 6 deck pairings, seats mirrored but deck assignments **not** swapped — agent A held deck A in every game, so deck strength is inside this number. Ruleset `149b39c8f55e9d41`, 2.4s.

| | games | win rate | 95% Wilson |
|---|---:|---:|---|
| **heuristic** | 360 | 95.8% | 93.2–97.5% |
| random | 360 | 4.2% | 2.5–6.8% |

Unpaired test on 360 games (95.8%) — no sequential test was run (fixed sample).

heuristic sat in seat 0 in 180 of 360 games — exactly half, by construction. heuristic on the play: 100.0% [96.1–100.0] (who goes first is the d20 winner's *choice*, so this is description, not balance). Average game length 11.2 turns. End reasons: OVERTIME 14, SEVEN_GIGS 346.

| deck pairing | games | heuristic win rate |
|---|---:|---|
| `sampled-0` built vs built-b | 60 | 90.0% [79.9–95.3] |
| `sampled-1` built vs explorer | 60 | 100.0% [94.0–100.0] |
| `sampled-2` Sample Gangers vs random | 60 | 98.3% [91.1–99.7] |
| `sampled-3` random vs random-b | 60 | 95.0% [86.3–98.3] |
| `sampled-4` random vs random-b | 60 | 96.7% [88.6–99.1] |
| `sampled-5` random vs built | 60 | 95.0% [86.3–98.3] |


### Frozen panel: heuristic — 2026-09-10 19:58 UTC

Panel `17064172ad6626e2`, frozen 2026-09-10: 6 deck pairings from deck seed 20260910, 60 games each, no early stopping. The protocol never changes, so these numbers are comparable across every generation.

| opponent | games | win rate | 95% Wilson | decisive pairs |
|---|---:|---:|---|---|
| uniform random legal play (`random`) | 360 | 93.9% | 90.9–95.9% | 159/160 |
| the frozen one-ply heuristic (`heuristic`) | 360 | 50.0% | 44.9–55.1% | 0/0 |
| the generation-0 snapshot (`gen0`) | — | not available yet | — | lands with the first trained model; until then this row reads "not available yet" and the panel is two members |


### Generalisation gap: heuristic vs random — 2026-09-10 20:00 UTC

The same agent against the same baseline on three deck populations. Both seats draw from the same population in each row, so the number measures play, not deck strength; what matters is the difference between the rows.

| deck population | games | win rate | 95% Wilson |
|---|---:|---:|---|
| training — the training mix (learn.decks.DEFAULT_MIX), the distribution self-play draws from | 360 | 91.1% | 87.7–93.6% |
| holdout — the two retail starters, held out of training entirely | 360 | 95.8% | 93.2–97.5% |
| unseen-random — fresh RAM-legal random decks from a deck seed training never used | 360 | 94.4% | 91.6–96.4% |

Gap to the held-out starters: -4.7 points (z = -2.56). Gap to fresh random decks: -3.3 points (z = -1.73). A gap that grows generation over generation means memorised matchups.


### Delayed-reward suite: heuristic — 2026-09-10 21:11 UTC

**Solved 0 of 8** (0 of 128 trials won), against a floor of 12 of 128 trials for uniform random play. Every position has a verified winning line that the frozen heuristic does not find on any of these seeds; a position counts as solved only when the agent wins it on every one of them. The suite holds 5 at a horizon of one turn (won inside the searched turn), 3 at a horizon of two turns (the payoff lands after the rival's answer).

| position | source | horizon | trials won | floor | solved |
|---|---|---:|---:|---:|---|
| `gear-before-the-raid` | hand-built | 1 | 0/16 | 3/16 | no |
| `sell-to-afford-the-raid` | hand-built | 1 | 0/16 | 3/16 | no |
| `two-pieces-of-gear` | hand-built | 1 | 0/16 | 0/16 | no |
| `mined-23767-79` | mined from heuristic self-play | 1 | 0/16 | 3/16 | no |
| `mined-23773-81` | mined from heuristic self-play | 1 | 0/16 | 0/16 | no |
| `mined-166300-77` | mined from heuristic self-play | 2 | 0/16 | 3/16 | no |
| `mined-166302-115` | mined from heuristic self-play | 2 | 0/16 | 0/16 | no |
| `mined-166305-59` | mined from heuristic self-play | 2 | 0/16 | 0/16 | no |

**Horizon** is how far past the searched turn the win may land, counted in the searched player's own turns. At 1 the line wins inside the turn; at 2 the searched turn cannot win by itself and has to leave a board the frozen policy converts on the following turn — a reward that arrives after the move that earned it. Only the searched turn is chosen by the agent either way: the suite measures which line you take *this* turn, not whether you can plan two of them.

**Floor** is uniform random play over the same turn, on the same seeds, stored when the position was qualified. Read the agent's column against it, not against the frozen heuristic's zero: the heuristic scores zero here by construction, because missing these positions on these seeds is how they were selected.

The win is confirmed by playing the turn out and the rival's whole reply with the frozen heuristic in both seats, so a line that reaches seven Gigs and has them stolen back does not count. That reply is one competent defence and one sample of the rival's Gig die, not a proof against every defence.
