# Learning from play

The deckbuilder learns from games; the player does not. Its evaluation is a table of hand-written
constants that ten thousand games leave untouched. The training loop closes that gap:

```
   self-play with search  ──►  experience files  ──►  train policy + value  ──►  gate
          ▲                                                                       │
          └────────────────────  accepted weights  ◄────────────────────────────────┘
```

This page is the shipped record of that loop. **Three of the four boxes exist today: experience
capture, a fitted value head, and the gate.** The search agent arrives in the next stage and adds
its section here, as every stage does — including the generation-by-generation numbers, published
whether or not they flatter the run.

Where the loop stands: 50,000 heuristic and random self-play games became 1.45M labelled positions;
a 1,857-parameter value head fitted to them predicts held-out outcomes at a Brier of 0.139 against
0.206 for the frozen heuristic's own evaluation; and `neural` — the *same* one-ply agent, scored by
that head instead of by seventeen hand-written constants — beats the frozen heuristic 75.8% of the
time, and 80.0% on the two retail starters it was never trained on. The pre-registered gate wanted
a Wilson lower bound above 0.55 on decks it never trained on; it got 0.756. What is still missing
is any claim about positions neither agent reaches, because nothing here searches.

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

## The cheap bootstrap

`tools/harvest.py` turns heuristic and random self-play into labelled positions at scale. The value
head can learn most of what it needs from games that are already free, because those games already
contain accidental setup sequences; nothing here claims the labels are ground truth, and the caveat
is at the bottom of this section rather than left implied.

```bash
python tools/harvest.py play --games 200000 --agent heuristic --workers 4   # self-play, resumable
python tools/harvest.py play --games 200000 --agent heuristic --resume      # after an interrupt
python tools/harvest.py compact OUT.jsonl.gz                                # when it is finished
python tools/harvest.py examples --in OUT.jsonl.gz --out train              # -> train.f32 + .json
python tools/harvest.py stats OUT.jsonl.gz                                  # size + composition
```

Nothing under `src/cptcg` changes: everything harvest needs is already importable, so the
stdlib-only rule for the Pyodide build holds by construction and `tools/bench.py check` cannot
move. No numpy either — harvesting is engine-bound, the `.f32` file is written with
`array('f').tofile`, and the numpy half of the split begins at the trainer that reads it.

### A fresh deck pair per game, indexed rather than streamed

Every game draws its own pair from `learn.decks.sample_pair`, so what is learned is how to play *a*
deck and not how to play one matchup — and the two retail starters stay out of training entirely,
which is what the generalisation gap rests on. `tools/harvest.py stats` re-checks that by
**contents** (`decks.is_holdout` on the reconstructed `Decklist`), not by trusting the sampler's
name filter, and so does the test suite over a 40-game harvest.

The pair is a pure function of the game index, not of a sequential generator:

```python
pair_rng(seed, i)  = Pcg32((seed ^ (i * 0x9E3779B1)) & MASK64, seq=909)
game_seed(seed, i) = (seed * 1000003 + i) & 0x7FFFFFFF
```

`arena.sampled_pairings` advances one `Pcg32` across games, which is right for a gate and wrong
here: it makes game *i* reachable only by drawing the *i−1* pairs before it, and that breaks both
sharding and resume. Indexed, a worker handed games 5000–5099 draws exactly the decks and seeds
those games would have had in any other run with the same `--seed`, so whole-run reproducibility,
arbitrary sharding and exact resume all fall out of one property. Each record carries
`meta={"i": i}`, and a 4-game harvest is byte-for-byte the first four records of a 6-game one.

### Resume: a manifest with a byte offset, and a truncate

Sessions get wiped mid-run, and an interrupt can tear the last line — or the last gzip member. The
data file is the bulk; the truth about how far it got is the sidecar `<out>.harvest.json`, rewritten
atomically (temp file + `os.replace`) after every chunk:

```json
{"format": 1, "out": "...", "seed": 7, "agents": ["heuristic", "heuristic"], "mix": null,
 "rules": "149b39c8f55e9d41", "games_target": 3000, "games_done": 372, "bytes": 91146,
 "decisions": 52104, "elapsed_s": 11.3, "sources": {...}, "end_reasons": {...}, "winners": {...}}
```

`--resume` does three things, in order:

1. **refuses** if the seed, the agents, the mix or the ruleset digest differ from the manifest — a
   resume that silently mixed two distributions would be invisible in a loss curve, which is the
   same failure `read_games`' ruleset gate exists to prevent;
2. **truncates** the data file back to `bytes`, which discards a torn tail and nothing else;
3. continues from game index `games_done`.

This is exact for gzip because `gzip.open(path, "at")` writes a **discrete member** per call,
concatenated members read back as one stream, and truncating to a recorded member boundary yields
exactly the committed records. Verified for real and not only in a test: a 3000-game harvest was
`SIGKILL`ed 12 seconds in at 372 games, resumed, and finished holding indices 0–2999 once each.

That safety has a price, and it is worth naming rather than hiding: each member restarts the
compressor with an empty window, so a 100-game harvest written in 34 chunks costs **666 gzipped
bytes per game** where the same records in one member cost **246**. `harvest.py compact` rewrites a
*finished* harvest as a single member and updates the manifest's byte count so a later `--resume`
still lines up; it refuses a file whose manifest disagrees with its size, and one that is not
finished.

### What a training row is

`examples` reads replays and writes `(features, label)` rows.

* **label** = `outcome(record, me)` — 1.0 if `me` eventually won, 0.0 if they lost, 0.5 if nobody
  did. `me` is the player to move by default, matching `features(s, me)`.
* **columns**: the `NFEAT` (114) features, then `label`, `game`, `ply`. `game` is the harvest's game
  index, and it is there so the trainer can **split train/val by game, never by position** — the
  single most important thing this file has to make possible. `ply` is the decision index, for
  calibration by game phase. float32 holds a game index exactly to 16.7M games.
* **format**: raw little-endian float32 rows in `PREFIX.f32`, plus a `PREFIX.json` header with the
  row count, column names, dtype, source files, rate, seed, the decorrelation table and the source
  harvest manifests. One `numpy.fromfile(path, dtype="<f4").reshape(rows, cols)` reads it. The
  header is written **last**, and refuses to be written at all if the data file's size disagrees
  with the row count, so a killed run leaves an obviously incomplete pair rather than a plausible
  one.

#### `--perspectives both`: one position, two rows

The obvious row — the player to move, labelled with whether that player won — has a flaw that no
loss curve would ever show. `to_move_me` (feature 3, "1 if the pending choice is mine") is then
**1.0 in every single row**: a constant column.

But an agent does not score decision states, it scores *previews*, and its most common preview by
far is the one where its own turn has just ended. There `pending.player` is the rival, so the agent
feeds `to_move_me = 0.0` — a value the network was never trained on — on exactly the comparison
that decides whether to end the turn. Whatever weight training happened to leave on a constant
input applies there, unlearned and unmeasured.

So `--perspectives both` writes that row **and** the same position seen from the other seat, with
that seat's own label. `features(s, me)` and `outcome(record, me)` are both already defined for
either player, so it costs one extra feature extraction per kept decision and changes neither the
column list nor `cols = 117`. The constant column stops being constant, the model sees every
position from both sides, and `p(s, 0) + p(s, 1) ~ 1` becomes a free calibration check. Both rows
carry the same `game`, so the by-game split keeps them together and the label still cannot leak.

The default stays `move`, because that is what the column list literally says a row is; the shipped
weights were fitted with `both`, and the example file's header records which was used.

#### `--perspectives both`: one position, two rows

The obvious row — the player to move, labelled with whether that player won — has a flaw that no
loss curve would ever show. `to_move_me` (feature 3, "1 if the pending choice is mine") is then
**1.0 in every single row**: a constant column.

But an agent does not score decision states, it scores *previews*, and its most common preview by
far is the one where its own turn has just ended. There `pending.player` is the rival, so the agent
feeds `to_move_me = 0.0` — a value the network was never trained on — on exactly the comparison
that decides whether to end the turn. Whatever weight training happened to leave on a constant
input applies there, unlearned and unmeasured.

So `--perspectives both` writes that row **and** the same position seen from the other seat, with
that seat's own label. `features(s, me)` and `outcome(record, me)` are both already defined for
either player, so it costs one extra feature extraction per kept decision and changes neither the
column list nor `cols = 117`. The constant column stops being constant, the model sees every
position from both sides, and `p(s, 0) + p(s, 1) ≈ 1` becomes a free calibration check. Both rows
carry the same `game`, so the by-game split keeps them together and the label still cannot leak.

The default stays `move`, because that is what the column list literally says a row is; the shipped
weights were fitted with `both`, and the example file's header records which was used.

### The sampling rate, measured

Consecutive decisions inside one turn share almost the whole feature vector and share the label
exactly, so they add loss weight without adding information. Rather than assert that, `examples`
measures it on every run and prints it: the mean L2 distance between feature vectors *k* decisions
apart. Over 554,479 heuristic decisions from 4,000 games:

| gap *k* | mean L2 | share of an independent pair | gained by halving the rate |
|---:|---:|---:|---|
| 1 | 1.098 | 32.3% | — |
| 2 | 1.517 | 44.7% | +0.419 |
| 4 | 1.928 | 56.8% | +0.411 |
| 8 | 2.501 | 73.6% | **+0.573** |
| 16 | 2.699 | 79.5% | +0.198 |
| two positions from the same game, any gap | 2.953 | 86.9% | — |
| two positions from **different** games | 3.397 | 100% | — |

**This moved the default.** The plan guessed 1-in-4; the curve says 1-in-4 is still only 57% of the
way to an independent pair and is climbing steeply, while the gain flattens after 1-in-8. Halving
from 1-in-4 to 1-in-8 buys +0.573 for half the rows; halving again buys +0.198. So `--rate` defaults
to **0.125**, and since games are the cheap resource here (34/s, below) the right way to want more
rows is to harvest more games. `--rate 1.0` keeps everything, for anyone who wants to re-test this.

The last two rows are the part subsampling cannot fix: positions from one game are *never*
independent, because they share a game, a deck pair and a label however far apart they are — 2.953
against 3.397. That is why the `game` column exists and why the split must use it.

The Bernoulli draw is a `Pcg32` seeded from each record's own seed, so the same replays give the
same rows every time, in any order and at any worker count.

### What it cost, measured on this box

4 cores, the real card pool, deck pairs from `learn.decks.sample_pair`, one fresh pair per game.
These are measurements from the runs described above, not estimates, and they are this box's — not
a portable figure.

| run | games | decisions | wall | games/s | positions/hour |
|---|---:|---:|---:|---:|---:|
| heuristic self-play, 4 workers | 4,000 | 554,479 | 116.3 s | **34.4** | **17.2M** |
| random self-play, 4 workers | 40,000 | 3,333,512 | 69.7 s | **573.9** | **172.2M** |
| heuristic, interrupted and resumed | 3,000 | 421,811 | 90.6 s | 33.1 | 16.8M |
| `examples` at `--rate 1.0`, 4 workers | 4,000 | 554,479 | 19.5 s | 205 | — |
| `examples` at `--rate 0.125`, 4 workers | 4,000 | 554,479 | 17.6 s | 227 | — |

Storage, from `harvest.py stats` on those files: heuristic 12.4 bytes/decision raw and **1.7
gzipped**, 238 gzipped bytes per game at 138.6 decisions per game; random 19.1 raw and 2.2 gzipped,
183 bytes per game at 83.3 decisions. So **10 million labelled heuristic positions is about 5 hours
of wall clock and about 17 MB gzipped**, and at `--rate 0.125` that is 1.25M training rows at 117
float32 each, 585 MB on disk as raw f32.

Realised deck mix over the 4,000-game heuristic harvest, tallied from the decklist names rather
than assumed from the config: explorer 19.7%, heuristic 36.1%, random 29.7%, sample 14.5% (against
the configured 20/35/30/15). End reasons: SEVEN_GIGS 2164, OVERTIME 1834, DECKOUT 2. Seat 0 won
1989 of 4000 — the harvest is balanced by construction, because each game draws an independent pair
rather than mirroring one.

`data/experience/bootstrap-sample.jsonl.gz` is 100 of these games, 24 KB, committed so the schema
has a real example in the repository and so a ruling that changes the digest fails a test loudly —
the same staleness contract `tests/golden/games.json` has. The bulk harvest is **not** committed: it
is regenerable exactly from `(seed, agent, mix, ruleset digest)`, all four of which are in the
manifest, and the retention rule is that experience is regenerable and weights are not.

### The caveat the numbers come with

A value head fitted to these games predicts the outcome **under heuristic play**. It inherits the
heuristic's biases: positions the heuristic never reaches are unlabelled, and positions it
misvalues are labelled with its mistakes. That is why the `random` agent is available here too — it
covers state space the heuristic never visits — and why this stage claims a data path and no
playing-strength result at all. The claim about strength has to come from the gate below.

## The value head

`src/cptcg/learn/model.py` is the middle box of the diagram at the top of this page, and
`src/cptcg/agents/neural.py` is what plays with it. Together they replace
`agents/heuristic.py`'s dict of seventeen hand-written constants with 1,857 numbers fitted to what
actually happened in 50,000 games.

```python
from cptcg.learn.model import load_weights
m = load_weights()              # cached; reads src/cptcg/agents/weights.json
m.value(state, me)              # probability that `me` wins from here
m.score(state, me)              # the same thing before the logistic — what the agent ranks on
```

One hidden layer of 16 `tanh` units over the 114 features, one output through a logistic.

**Inference is pure stdlib; training is not.** `src/cptcg` is zipped into a phone browser by
`tools/build_site.py`, where there is no pip, so the forward pass is hand-written Python
(`math.sumprod` where the interpreter has it, `sum(map(mul, …))` where it does not) while the
trainer in `tools/fit_eval.py` imports numpy lazily inside `fit`. Two implementations of one piece
of arithmetic is a real risk, so `tests/learn/test_model.py` checks them against each other to
1e-12, and `tests/unit/test_stdlib_only.py` walks every module under `src/cptcg` and fails on any
import that is neither stdlib nor `cptcg` — the Pyodide constraint as a test rather than a promise.
`weights.json` needs no build change: the site build already packs every non-`.pyc` file under
`src/cptcg`.

`ValueModel.from_json` refuses rather than scoring plausibly from the wrong numbers: a format it
does not know, an activation it does not implement, a feature list that differs from
`FEATURE_NAMES` (the message names the first differing index, both names and both lengths), any
shape mismatch (the message names the row), or a ruleset digest that is not this build's.
`rules=None` is the deliberate escape a refit needs — the same convention `experience.read_games`
uses.

### Choosing the width, before any game was played

The agent's budget is a *move*, not a forward pass: a leaf costs `features()` **and** the model,
and under Pyodide both cost more. So the cost table comes first (`tools/fit_eval.py bench`, this
box, 4 cores, CPython 3.11 without `math.sumprod`):

| hidden | parameters | forward pass | vs the 29.8 µs feature extraction | leaf evaluations/s |
|---:|---:|---:|---:|---:|
| 8 | 929 | 19.4 µs | 0.65× | 20,325 |
| 16 | 1,857 | 38.6 µs | 1.29× | 14,618 |
| 24 | 2,785 | 57.6 µs | 1.93× | 11,435 |
| 32 | 3,713 | 76.9 µs | 2.58× | 9,372 |
| 48 | 5,569 | 115.1 µs | 3.86× | 6,902 |
| 64 | 7,425 | 154.0 µs | 5.16× | 5,441 |
| 96 | 11,137 | 234.5 µs | 7.86× | 3,784 |
| 128 | 14,849 | 314.4 µs | 10.54× | 2,905 |

**This is the number that shapes the stage.** `evaluate()` costs about 4 µs; `features()` alone
costs 30. The neural agent is not "the heuristic with a different scorer", it is roughly a five
times slower agent, and every arena budget below is sized from that.

The selection rule was fixed in advance: fit every width on the *same* by-game split, and ship the
smallest whose held-out Brier is within 1% relative of the best, subject to ≤150 µs a forward pass.
**No arena result enters this decision.** Every width is published whether shipped or not
(`tools/fit_eval.py sweep`, all 1.45M rows, early stopping on held-out Brier):

| hidden | held-out Brier | log-loss | accuracy | best epoch | shipped |
|---:|---:|---:|---:|---:|---|
| 8 | 0.14058 | 0.42715 | 78.90% | 74 | — |
| **16** | **0.13929** | 0.42376 | 79.14% | 63 | **yes** |
| 24 | 0.13916 | 0.42325 | 79.13% | 63 | — |
| 32 | 0.13937 | 0.42373 | 79.10% | 36 | — |
| 48 | 0.13922 | 0.42353 | 79.16% | 72 | — |
| 64 | 0.13942 | 0.42369 | 79.08% | 47 | — |

The curve is flat from 16 to 64 — a spread of 0.0003 Brier across four times the parameters — so
the rule picks 16 and, more importantly, **capacity is not what is holding this model back**. That
is a measurement, not a consolation: see the diagnosis at the end of this section.

### The data, and how it was split

| | games | decisions | rows kept | wall, 4 cores |
|---|---:|---:|---:|---:|
| heuristic self-play, seed 7 | 30,000 | 4,156,939 | 1,039,492 | 924 s |
| random self-play, seed 21 | 20,000 | 1,665,923 | 414,500 | 35 s |
| **total** | **50,000** | **5,822,862** | **1,453,992** | 16 min |

`--rate 0.125` (the measured knee, above), `--perspectives both` (the constant-column fix, above).
680 MB of float32 in the scratchpad; **not committed** — it is regenerable exactly from
`(seed, agent, mix, ruleset digest)`, all four of which are in each harvest manifest.

The split is **by game**: 40,000 games train, 10,000 held out, which is 1,161,380 training rows
against 292,612. Splitting the 1.45M rows at random instead would put the two perspectives of the
same decision — and the 140 near-identical decisions of the same game, all sharing one label — on
both sides, and every number below would be inflated by memorisation rather than earned.

### What it learned

Adam on Brier (squared error after the logistic, so one noisy sample of an outcome cannot dominate
the gradient), batches of 4,096, L2 1e-4 on the two weight matrices and not on the biases, early
stopping on held-out Brier with the best weights restored: best at epoch 95, stopped at 120, 254 s.

Four models, all scored on held-out **games**. The first table is all 292,612 held-out rows; the
second is the 182,516 of them that were replayed so that `heuristic.evaluate()` could be scored on
exactly the same positions — the score is not a column of the training matrix, because the matrix
stores a description and not an opinion.

| model | Brier | log-loss | accuracy |
|---|---:|---:|---:|
| always 0.5 | 0.25000 | 0.69315 | 50.00% |
| logistic regression, same 114 features, no hidden layer | 0.16074 | 0.48293 | 75.50% |
| **the value head, hidden=16** | **0.13914** | **0.42351** | **79.14%** |

| model, on the replayed subsample | Brier | log-loss | accuracy |
|---|---:|---:|---:|
| always 0.5 | 0.25000 | 0.69315 | 50.00% |
| the frozen heuristic's `evaluate()`, squashed through a logistic fitted on the training split | 0.20631 | 0.59824 | 67.23% |
| logistic regression, same 114 features | 0.16489 | 0.49317 | 74.70% |
| **the value head, hidden=16** | **0.14350** | **0.43533** | **78.45%** |

The heuristic baseline is fitted rather than assumed: its scale and offset are learned on the
*training* split, so the comparison is against the best probability that score can be turned into,
not against a badly calibrated version of it. Against that, the value head takes 30% off the Brier
and adds 11 points of accuracy. The no-hidden-layer row says how much of that is the feature set
(most of it) and how much is the hidden layer (0.0021 Brier, about a sixth of the gap).

### Calibration

Held-out games, ten buckets, expected calibration error **0.0219**, worst bucket gap **0.0435**.

| predicted | n | mean prediction | actually won | 95% Wilson |
|---|---:|---:|---:|---|
| 0.0–0.1 | 42,009 | 0.041 | 0.021 | 0.020–0.023 |
| 0.1–0.2 | 24,599 | 0.149 | 0.105 | 0.101–0.109 |
| 0.2–0.3 | 22,697 | 0.250 | 0.215 | 0.210–0.221 |
| 0.3–0.4 | 24,931 | 0.352 | 0.323 | 0.317–0.329 |
| 0.4–0.5 | 30,250 | 0.451 | 0.437 | 0.431–0.442 |
| 0.5–0.6 | 30,555 | 0.549 | 0.549 | 0.543–0.554 |
| 0.6–0.7 | 25,444 | 0.648 | 0.664 | 0.658–0.669 |
| 0.7–0.8 | 23,134 | 0.750 | 0.779 | 0.774–0.784 |
| 0.8–0.9 | 25,059 | 0.852 | 0.885 | 0.881–0.889 |
| 0.9–1.0 | 43,934 | 0.961 | 0.975 | 0.973–0.976 |

It is slightly *under*-confident at both ends — it says 4% and wins 2%, says 96% and wins 97.5% —
which is the expected shape for a Brier-trained head and the harmless direction: a ranking is
unaffected by a monotone squash.

## The agent: same search, learned value

`src/cptcg/agents/neural.py` registers `neural`. It **inherits** `act`, `_keep` and `_resolve` from
the frozen `HeuristicAgent` and copies `_greedy` line for line, changing one line: the score.
`tests/unit/test_neural_agent.py` asserts the inheritance by identity and compares the two `_greedy`
bodies statement by statement, so a win here cannot quietly become a difference in mulligan policy
or preview depth. Configuration rides on class attributes (`weights_path`, `noise`, `depth`,
`go_first`), because `make_agent(name, seed)` has no config channel; `agents/base.py` gained one
import line.

Three things do differ from `evaluate()`, and all three are forced.

**It ranks on the logit, not the probability.** `ValueModel.raw` is the unbounded pre-logistic
score. The logistic is monotone so the ordering is identical, but in a position the model reads as
99% won, two options can differ by 1e-5 in probability and by 0.2 in log-odds; squashing first
throws the deciding difference into float noise.

**The tie-break noise is measured, not copied.** `tools/fit_eval.py diagnose` scores the options of
4,275 real multi-option decisions with both scorers. The median spread of `evaluate()` across one
decision's options is 7.50 points and the heuristic's noise reaches 0.0999 — 1.33% of it. The
median spread of the learned logit across the *same* decisions is 0.595, so the same 1.33% is
`noise = 8e-6` per unit. Copying the heuristic's `1e-4` would have been a noise term 1.7× the whole
spread, and this agent would have played at random.

**A preview it cannot tell apart from the position it is in is scored as a loss.** This one is a
bug report. A greedy agent on a static evaluation hangs the moment the rules offer a free no-op,
and this pool has one: activate Panam Palmer, decline the pick, get the identical main menu back.
The frozen heuristic escapes it by accident — it happens to rate taking the pick above declining —
but nothing in its design prevents it, and the fitted value rates declining higher. The first gate
run died with `game 5005167 exceeded 50000 actions` after `neural` re-activated the same Legend 750
times. `_value` now compares the previewed position to the position being chosen from, field by
field (an exact comparison, never a hash or a feature match, so it cannot mistake two different
positions for one), and scores an exact repeat as a loss: taking it leads back here and the same
choice would be made again, for ever. `tests/unit/test_neural_agent.py` keeps that game in the
suite. The first version of the guard compared pending menus and was silent through the very loop
it guarded; "The 50,000-action ceiling", at the end of this page, is the post-mortem.

### The pre-registered gate, and what it said

Pre-registered before any number existed: **`neural` beats the frozen `heuristic` with a Wilson
lower bound above 0.55 on decks it never trained on, the held-out retail starters included.**
Model selection was by held-out Brier only; every gate command was run once, with docs appended by
default (`--no-docs` was never passed), and the full sections are below.

| instrument | result | gate |
|---|---|---|
| `a-vs-b neural heuristic --no-sprt`, 360 games, 6 sampled pairings | **75.8%**, Wilson 71.2–80.0%, between-pairing 75.8 [69.9–81.8]% | lower bound 0.712 |
| `generalisation`, **holdout** — the two retail starters, never trained on | **80.0%**, Wilson 75.6–83.8% | lower bound **0.756 > 0.55 ✓** |
| `generalisation`, unseen-random — fresh random decks on a seed training never used | 75.8%, Wilson 71.2–80.0% | lower bound 0.712 |
| `generalisation`, training — the mix self-play draws from | 79.7%, Wilson 75.3–83.6% | — |
| `panel neural` — the frozen panel | 96.1% vs `random`, 75.8% vs `heuristic` | — |
| `delayed neural` | solved 3 of 8, 56/128 trials, against a random floor of 12/128 | — |

**The gate passes**, and it passes hardest on the population it was meant to be hardest on: the gap
from the training decks to the held-out retail starters is **−0.3 points** — the holdout rate sits
inside the 63.3–91.7% spread the six training pairings cover among themselves. `exploit` was not
run: `neural` does not consult `core.view.determinize`, so `run_exploit` correctly refuses it. That
instrument belongs to the search stage.

### Why it worked, and where the ceiling is

The plan pre-registered a diagnosis for the case where greedy play on a learned value failed to beat
greedy play on hand-tuned weights. It did not fail, but the diagnostics were collected either way,
because they say what the *next* stage should spend its time on.

**It is not copying the teacher.** Argmax agreement with `heuristic` over 4,275 held-out
multi-option decisions is **42.1%** — `MAIN` 38.3%, `PICK` 19.9%, `TARGET` 79.3%, `REACTION` 72.6%.
The two agents agree about which attack to answer and disagree about almost everything else. Had
this come back near 95%, a 75.8% win rate would have been impossible and no amount of data or width
would have fixed it.

**More data would not help.** Held-out Brier against how much training data there is, on a fixed
held-out set:

| training games | training rows | held-out Brier | accuracy |
|---:|---:|---:|---:|
| 3,999 (10%) | 116,980 | 0.14330 | 78.41% |
| 9,999 (25%) | 290,132 | 0.13991 | 78.98% |
| 19,999 (50%) | 580,080 | 0.13973 | 79.02% |
| 39,999 (100%) | 1,161,380 | 0.13929 | 79.14% |

Quadrupling the data past 25% buys 0.0006 Brier. Together with the flat width sweep, **both of the
"more of the same" levers are exhausted**: the remaining error is the feature set, or it is the
irreducible noise in a single sampled outcome. The 0.0021 Brier between the logistic and the
network says how little is left for the hidden layer to find in these 114 numbers.

**Random games are coverage, not poison.** Three fits, all scored on the *same* held-out rows:

| trained on | training rows | held-out Brier, all | on heuristic games | on random games |
|---|---:|---:|---:|---:|
| both (shipped) | 1,161,380 | **0.13929** | 0.13066 | 0.16094 |
| heuristic games only | 830,262 | 0.14378 | **0.12836** | 0.18248 |
| random games only | 331,118 | 0.18759 | 0.19640 | 0.16547 |

Heuristic-only is marginally better on heuristic positions and much worse on unstructured ones;
random-only is worse everywhere. The mix costs 0.0023 Brier on the heuristic's own distribution and
buys 0.0215 on the other end of the state space — and the random half of the harvest cost 35
seconds against the heuristic half's 924.

**The honest caveat stands.** These labels are outcomes *under heuristic play*. The value head is
well calibrated about a world in which both players are the frozen heuristic, and the gate shows
that ranking moves by that value beats the heuristic itself. It does not show the value is right
about positions neither agent reaches, and it cannot: nothing in this stage searches.

### Reproducing it

```bash
python tools/harvest.py play --games 30000 --agent heuristic --seed 7  --workers 4 --out H.jsonl.gz --fresh
python tools/harvest.py play --games 20000 --agent random    --seed 21 --workers 4 --out R.jsonl.gz --fresh
python tools/harvest.py examples --in H.jsonl.gz --out ex-h --rate 0.125 --perspectives both --workers 4
python tools/harvest.py examples --in R.jsonl.gz --out ex-r --rate 0.125 --perspectives both --workers 4
python tools/fit_eval.py bench --markdown
python tools/fit_eval.py sweep ex-h ex-r --widths 8,16,24,32,48,64 --epochs 120 --patience 12
python tools/fit_eval.py fit   ex-h ex-r --hidden 16 --l2 1e-4 --epochs 400 --patience 25 \
       --out src/cptcg/agents/weights.json --name bootstrap-1
python tools/fit_eval.py curve ex-h ex-r --hidden 16
python tools/fit_eval.py diagnose --games 40
python tools/arena.py a-vs-b neural heuristic --no-sprt -n 360 --decks 6
python tools/arena.py panel neural
python tools/arena.py generalisation neural --baseline heuristic
python tools/arena.py delayed neural
```

Everything except the last four is deterministic given the seeds; the arena commands are
deterministic given their own (`--seed`, `--deck-seed`), which they print.

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

### The two error bars, and which one a claim has to clear

The games of one deck pairing share decks and shuffles, so they are **not** independent Bernoulli
trials, and the dominant variance in an arena number is *which deck pairings were drawn* rather
than how the games inside them fell. Every report therefore prints two intervals:

| | what it answers |
|---|---|
| **95% Wilson**, over the games | how much more would *more games on these decks* tell me — conditional on the pairings played, and the right and only interval for the frozen panel, whose decks never change |
| **between-pairing**, mean of the per-pairing rates ± t(k−1)·s/√k | would this hold *on another sample of decks* — which is what a claim about an agent means |

The difference is not cosmetic. Running the identical protocol (heuristic vs random, six pairings,
360 games, same game seed) and changing **only** the deck seed:

| deck seed | win rate | 95% Wilson | between-pairing |
|---|---:|---|---|
| 20260910 | 93.9% | 90.9–95.9 | 92.1–95.7 |
| 1 | 88.3% | 84.6–91.3 | 82.1–94.6 |
| 2 | 94.2% | 91.2–96.2 | 91.3–97.0 |
| 3 | 95.0% | 92.2–96.8 | 91.3–98.7 |
| 4 | 94.7% | 91.9–96.6 | 91.3–98.1 |

Nothing about either agent changed across those five rows, yet the first two Wilson intervals **do
not overlap** — an interval that excludes the truth in a case this ordinary is not a 95% interval.
Every between-pairing interval in the same table does overlap the others. (Varying only the *game*
seed on fixed decks gives 91.9–94.2%, inside binomial noise, which is what confirms the deck sample
is the term the Wilson interval leaves out.)

So: **a generation-over-generation claim must clear the between-pairing interval**, not the Wilson
one. The between-pairing interval is itself estimated from only k pairings, so it is noisy and can
come out either side of the Wilson bracket — narrower when six pairings happened to agree, much
wider when one of them did not. Widen the sample of decks, not the number of games, to tighten it.

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

**The disclosure printed the old figures until now.** `sim.report.disclosure` is the one
paragraph that heads every Markdown report, the web report and the GUIDE, and it quoted 98.6%
against random plus two loss rates — 61.7% to a two-ply version of the agent and 59.4% to
versions that never mulligan or take the smallest die — that no shipped command prints. Those
came from a throwaway probe over three fixed curated deck pairings — the two retail starters
plus two of the `sample_*` matchups — 360 games, seats mirrored. The arena measures over
*sampled* decks instead, so the paragraph was presenting a measurement of one population as the
number, and the reconstruction in the table above lands 96.7–98.1% under the old protocol and
93.9% under this one. It now quotes the frozen panel — 93.9%, with `tools/arena.py panel
heuristic` named beside it, the decks and the game count stated, and the 88–95% spread across
deck seeds printed so the figure cannot be read as a constant — and the delayed-reward suite
for what the agent cannot do. The two variant figures are simply gone: no variant of the frozen
agent ships, so no command re-derives them, and a claim that cannot be re-derived is cut rather
than kept.

The same paragraph also said the heuristic "never holds a Blocker back". Counting, over 240
heuristic self-play games on decks from `learn.decks.sample_pair`, the turns in which a ready
Blocker could have attacked and the turn ended without it attacking: **54 of 1126**, about one
turn in twenty (per deck sample: 20/281, 14/270, 7/292, 13/283). So it is "almost never", not
"never", and `tests/unit/test_report.py` re-measures a 12-game slice of that count and fails if
it reaches zero or passes 15%. The rule the paragraph now follows is the same one this page
follows: no figure without a shipped command that prints it.

### The frozen panel

`data/arena/panel.json` is **data, not code**, so freezing it is visible in a diff. It pins the
opponents (`random`, the frozen `heuristic`, and a generation-0 snapshot that does not exist yet
and is reported as "not available yet" rather than quietly skipped), the protocol (six deck
pairings, 60 games each, no early stopping — a fixed sample is what makes two generations
comparable, so the panel never uses the SPRT), **and the twelve decklists themselves, written out
card for card**.

That last part is version 2 of the file and it matters more than it sounds. Version 1 stored only
the deck sampler's seed and redrew the lists at run time from `learn.decks.sample_pair`. Its digest
covered the *recipe* and not the decks, so retuning `DEFAULT_MIX`, the deck sizes or curve
constants, either builder in `deck/builder.py`, or merely adding or deleting one
`data/decks/sample_*.json` file would have silently changed all six matchups while the digest still
matched and the file still loaded — and the deck sample is worth several points of win rate (see
the table above), so generation N and generation N+2 could have been scored on different opponents
with nothing in the output saying so. The lists in v2 are exactly what that seed drew on the day
the panel was frozen, byte for byte, so **v1 and v2 scores are directly comparable** — the
heuristic scores 93.9% against `random` under both. From here the panel plays the same twelve decks
in 2027 that it played in 2026, whatever the sampler has since become; the seed is kept in the file
as provenance only and is never re-run.

Two digests guard it, both checked on load: `digest` over the whole file, and `decks_digest` over
just the decklists by contents — `(name, legends, sorted(main))` per deck — so it survives
reformatting and fires on a single card moving in a single list. `tests/learn/test_arena.py` pins
both a second time, pins the first pairing card for card, and mutates `DEFAULT_MIX` mid-test to
prove the panel does not move when the sampler does. Changing the panel is allowed — changing it
silently is not, and a change makes scores before and after incomparable.

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

The three rows are not statistically alike, and the report says so instead of averaging over the
difference:

* **training** and **unseen-random** are six deck pairings each, so the gap between them gets an
  interval over the pairings (Welch, two independent samples of pairings).
* **holdout** is **one** matchup — `the_heist` against `embracing_power`, the only two retail
  starters the game has. Its 360 games are 360 games on one pair of decks, not 360 draws from a
  deck population, so it carries **no test statistic at all**. It is reported as the single matchup
  it is, beside the training row's own pairing-to-pairing scatter, which is the only honest thing
  to read it against.
* **unseen-random** is not out-of-distribution and the report no longer lets it be read that way:
  `random` is the 0.30 slice of `DEFAULT_MIX`, so that row is a fresh draw from a source training
  does use. It isolates the unstructured end of the training mix; it does not test transfer.

The frozen heuristic's baseline, measured below, is **negative**: against random it wins 91.1% on
the training mix, 95.8% on the held-out starters and 94.4% on fresh random decks, a gap of −4.7
points to the holdout. An earlier version of this section called that gap significant (z = −2.56).
It is not, and the z has been withdrawn: it treated one matchup as a sample of a deck population.
The training row's six pairings run **86.7–96.7%** on their own, so 95.8% on the holdout sits
comfortably inside the scatter the training decks already show, and −4.7 points is smaller than the
deck-to-deck term rather than larger. The gap to fresh random decks is −3.3 points with a 95%
interval over the pairings of −9.1 to +2.5, which likewise includes zero.

The sign is still the one to expect from an agent that cannot memorise anything — a hand-built
retail deck rewards competent play more than a random list does, so the held-out row is the
*easier* one — but the honest reading today is "no gap detectable above deck-to-deck noise". The
number to watch is the change: a model that has learned the game keeps this gap where it is, and
one that has learned six deck pairings drives it positive by more than that scatter.

## Honest caveats

* **The games stored today were played by the heuristic and random agents**, neither of which
  searches. They carry no visit counts, so they train a value head and not a policy.
* **The value head's ceiling is measured, and it is not data or capacity.** Held-out Brier is flat
  from 25% of the training games onward and flat from 16 hidden units to 64. What is left is the
  feature set and the noise in a single sampled outcome, so the next gain has to come from search
  or from richer features, not from a bigger harvest.
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

Runs dated 2026-09-10 19:58–20:00 UTC predate two corrections and are kept rather than edited, so
that what changed is visible. They print a single 95% Wilson interval with no qualifier, which is
an interval conditional on the deck pairings played and not an error bar for the agent; the
generalisation run among them prints a two-proportion z against the one-matchup holdout, which has
since been withdrawn as unsupportable. Their panel run cites panel digest `17064172ad6626e2`,
version 1 of `data/arena/panel.json`. **Its win rates are still comparable with the v2 panel below**
— v2 wrote down the very decklists v1 was redrawing, and the heuristic scores 93.9% against
`random` under both.


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


### heuristic vs random — 2026-09-10 21:48 UTC

`arena a-vs-b heuristic random --no-sprt` over 6 deck pairings sampled from deck seed 20260910.

360 games over 6 deck pairings, 180 paired comparisons — every seed played from both seats and with the deck assignments swapped. Ruleset `149b39c8f55e9d41`, 2.7s.

| | games | win rate | 95% Wilson (these decks) |
|---|---:|---:|---|
| **heuristic** | 360 | 93.9% | 90.9–95.9% |
| random | 360 | 6.1% | 4.1–9.1% |

The Wilson interval above is **conditional on these 6 deck pairings**: it says what more games on these decks would tell you, and nothing about other decks. Per-pairing rates run 91.7–95.0%; over the deck population the mean is 93.9 [92.1–95.7]% (t5 on 6 pairings). **That second band is the error bar for heuristic's strength**, and a generation-over-generation claim has to clear it rather than the Wilson one — the same protocol on five different deck samples moves several points while nothing about the agents changes. It is estimated from only 6 pairings, so it is itself noisy and can land either side of the Wilson bracket: narrower when the pairings happened to agree, much wider when one of them did not.

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


### Frozen panel: heuristic — 2026-09-10 21:48 UTC

Panel `a1832d477c27193f`, decks `1b1799dbc029a6b7`, frozen 2026-09-10: 6 deck pairings whose **decklists are stored verbatim in `data/arena/panel.json`** and are never redrawn from the sampler, 60 games each, no early stopping. Both digests are checked on load, so these numbers are comparable across every generation as long as they read `a1832d477c27193f` / `1b1799dbc029a6b7`.

| opponent | games | win rate | 95% Wilson (these decks) | per-pairing spread | decisive pairs |
|---|---:|---:|---|---|---|
| uniform random legal play (`random`) | 360 | 93.9% | 90.9–95.9% | 91.7–95.0% | 159/160 |
| the frozen one-ply heuristic (`heuristic`) | 360 | 50.0% | 44.9–55.1% | 50.0–50.0% | 0/0 |
| the generation-0 snapshot (`gen0`) | — | not available yet | — | — | lands with the first trained model; until then this row reads "not available yet" and the panel is two members |

Here the Wilson interval is the right one and the *only* one that changes between generations: the decks are fixed by the panel, so nothing but more games is being sampled. The per-pairing spread is printed beside it as a reminder of what the panel is not — a panel score is a score on these twelve decklists, and generalises no further than they do. For a claim about play in general, use the between-pairing interval from `a-vs-b` or `generalisation`.


### Generalisation gap: heuristic vs random — 2026-09-10 21:48 UTC

The same agent against the same baseline on three deck populations. Both seats draw from the same population in each row, so the number measures play, not deck strength; what matters is the difference between the rows.

| deck population | pairings | games | win rate | 95% Wilson (these decks) | per-pairing spread |
|---|---:|---:|---:|---|---|
| training — the training mix (learn.decks.DEFAULT_MIX), the distribution self-play draws from | 6 | 360 | 91.1% | 87.7–93.6% | 86.7–96.7% |
| holdout — the two retail starters, held out of training entirely — **one** matchup, because the game has exactly two of them | 1 | 360 | 95.8% | 93.2–97.5% | one matchup |
| unseen-random — fresh RAM-legal random decks on a deck seed training never used. **Not** out of distribution: `random` is the 0.30 slice of the training mix, so this row is a fresh draw from a source the model does train on, and it isolates the unstructured end of that mix rather than testing transfer | 6 | 360 | 94.4% | 91.6–96.4% | 86.7–100.0% |

**Gap to the held-out starters: -4.7 points, and no test statistic.** The holdout is 1 matchup, so those games are not a sample of a deck population and a two-proportion z over them would claim a precision the design cannot support. Read it against the training row's own scatter instead: its 6 pairings run 86.7–96.7%, which puts the holdout rate inside the range the training decks themselves cover.

Gap to fresh random decks: -3.3 points, 95% interval over the pairings -3.3 [-9.1 to +2.5] points (Welch, two independent samples of deck pairings). Both rows have deck pairings to spare, so this comparison is between deck *populations* and not between two piles of games.

A gap that grows generation over generation means memorised matchups. Watch the change in these numbers, and only trust a change that is large against the per-pairing spread beside it.


> **The four sections that follow were measured before the no-op guard in `agents/neural.py`
> worked** (see "The 50,000-action ceiling" at the end of this file). They are kept because they
> are the record of what was run, and because the re-runs at 01:06 and 01:07 came back with the
> same numbers: the guard only changes a game in which the agent was about to cycle for ever, and
> no game that finished was played differently. Read the 01:06 block as the current one.

### neural vs heuristic — 2026-09-11 00:55 UTC

`arena a-vs-b neural heuristic --no-sprt` over 6 deck pairings sampled from deck seed 20260910.

360 games over 6 deck pairings, 180 paired comparisons — every seed played from both seats and with the deck assignments swapped. Ruleset `149b39c8f55e9d41`, 14.8s.

| | games | win rate | 95% Wilson (these decks) |
|---|---:|---:|---|
| **neural** | 360 | 75.8% | 71.2–80.0% |
| heuristic | 360 | 24.2% | 20.0–28.8% |

The Wilson interval above is **conditional on these 6 deck pairings**: it says what more games on these decks would tell you, and nothing about other decks. Per-pairing rates run 68.3–83.3%; over the deck population the mean is 75.8 [69.9–81.8]% (t5 on 6 pairings). **That second band is the error bar for neural's strength**, and a generation-over-generation claim has to clear it rather than the Wilson one — the same protocol on five different deck samples moves several points while nothing about the agents changes. It is estimated from only 6 pairings, so it is itself noisy and can land either side of the Wilson bracket: narrower when the pairings happened to agree, much wider when one of them did not.

Paired test: 96 of 99 decisive pairs (97.0%) — no sequential test was run (fixed sample).

neural sat in seat 0 in 180 of 360 games — exactly half, by construction. neural on the play: 71.1% [64.1–77.2] (who goes first is the d20 winner's *choice*, so this is description, not balance). Average game length 13.3 turns. End reasons: OVERTIME 116, SEVEN_GIGS 244.

| deck pairing | games | neural win rate |
|---|---:|---|
| `sampled-0` built vs built-b | 60 | 73.3% [61.0–82.9] |
| `sampled-1` built vs explorer | 60 | 75.0% [62.8–84.2] |
| `sampled-2` Sample Gangers vs random | 60 | 68.3% [55.8–78.7] |
| `sampled-3` random vs random-b | 60 | 73.3% [61.0–82.9] |
| `sampled-4` random vs random-b | 60 | 83.3% [72.0–90.7] |
| `sampled-5` random vs built | 60 | 81.7% [70.1–89.4] |


### Frozen panel: neural — 2026-09-11 00:55 UTC

Panel `a1832d477c27193f`, decks `1b1799dbc029a6b7`, frozen 2026-09-10: 6 deck pairings whose **decklists are stored verbatim in `data/arena/panel.json`** and are never redrawn from the sampler, 60 games each, no early stopping. Both digests are checked on load, so these numbers are comparable across every generation as long as they read `a1832d477c27193f` / `1b1799dbc029a6b7`.

| opponent | games | win rate | 95% Wilson (these decks) | per-pairing spread | decisive pairs |
|---|---:|---:|---|---|---|
| uniform random legal play (`random`) | 360 | 96.1% | 93.6–97.7% | 88.3–100.0% | 166/166 |
| the frozen one-ply heuristic (`heuristic`) | 360 | 75.8% | 71.2–80.0% | 68.3–83.3% | 96/99 |
| the generation-0 snapshot (`gen0`) | — | not available yet | — | — | lands with the first trained model; until then this row reads "not available yet" and the panel is two members |

Here the Wilson interval is the right one and the *only* one that changes between generations: the decks are fixed by the panel, so nothing but more games is being sampled. The per-pairing spread is printed beside it as a reminder of what the panel is not — a panel score is a score on these twelve decklists, and generalises no further than they do. For a claim about play in general, use the between-pairing interval from `a-vs-b` or `generalisation`.


### Delayed-reward suite: neural — 2026-09-11 00:57 UTC

**Solved 3 of 8** (56 of 128 trials won), against a floor of 12 of 128 trials for uniform random play. Every position has a verified winning line that the frozen heuristic does not find on any of these seeds; a position counts as solved only when the agent wins it on every one of them. The suite holds 5 at a horizon of one turn (won inside the searched turn), 3 at a horizon of two turns (the payoff lands after the rival's answer).

| position | source | horizon | trials won | floor | solved |
|---|---|---:|---:|---:|---|
| `gear-before-the-raid` | hand-built | 1 | 16/16 | 3/16 | yes |
| `sell-to-afford-the-raid` | hand-built | 1 | 8/16 | 3/16 | no |
| `two-pieces-of-gear` | hand-built | 1 | 0/16 | 0/16 | no |
| `mined-23767-79` | mined from heuristic self-play | 1 | 16/16 | 3/16 | yes |
| `mined-23773-81` | mined from heuristic self-play | 1 | 0/16 | 0/16 | no |
| `mined-166300-77` | mined from heuristic self-play | 2 | 0/16 | 3/16 | no |
| `mined-166302-115` | mined from heuristic self-play | 2 | 16/16 | 0/16 | yes |
| `mined-166305-59` | mined from heuristic self-play | 2 | 0/16 | 0/16 | no |

**Horizon** is how far past the searched turn the win may land, counted in the searched player's own turns. At 1 the line wins inside the turn; at 2 the searched turn cannot win by itself and has to leave a board the frozen policy converts on the following turn — a reward that arrives after the move that earned it. Only the searched turn is chosen by the agent either way: the suite measures which line you take *this* turn, not whether you can plan two of them.

**Floor** is uniform random play over the same turn, on the same seeds, stored when the position was qualified. Read the agent's column against it, not against the frozen heuristic's zero: the heuristic scores zero here by construction, because missing these positions on these seeds is how they were selected.

The win is confirmed by playing the turn out and the rival's whole reply with the frozen heuristic in both seats, so a line that reaches seven Gigs and has them stolen back does not count. That reply is one competent defence and one sample of the rival's Gig die, not a proof against every defence.


### neural vs heuristic — 2026-09-11 01:06 UTC

`arena a-vs-b neural heuristic --no-sprt` over 6 deck pairings sampled from deck seed 20260910.

360 games over 6 deck pairings, 180 paired comparisons — every seed played from both seats and with the deck assignments swapped. Ruleset `149b39c8f55e9d41`, 14.8s.

| | games | win rate | 95% Wilson (these decks) |
|---|---:|---:|---|
| **neural** | 360 | 75.8% | 71.2–80.0% |
| heuristic | 360 | 24.2% | 20.0–28.8% |

The Wilson interval above is **conditional on these 6 deck pairings**: it says what more games on these decks would tell you, and nothing about other decks. Per-pairing rates run 68.3–83.3%; over the deck population the mean is 75.8 [69.9–81.8]% (t5 on 6 pairings). **That second band is the error bar for neural's strength**, and a generation-over-generation claim has to clear it rather than the Wilson one — the same protocol on five different deck samples moves several points while nothing about the agents changes. It is estimated from only 6 pairings, so it is itself noisy and can land either side of the Wilson bracket: narrower when the pairings happened to agree, much wider when one of them did not.

Paired test: 96 of 99 decisive pairs (97.0%) — no sequential test was run (fixed sample).

neural sat in seat 0 in 180 of 360 games — exactly half, by construction. neural on the play: 71.1% [64.1–77.2] (who goes first is the d20 winner's *choice*, so this is description, not balance). Average game length 13.3 turns. End reasons: OVERTIME 116, SEVEN_GIGS 244.

| deck pairing | games | neural win rate |
|---|---:|---|
| `sampled-0` built vs built-b | 60 | 73.3% [61.0–82.9] |
| `sampled-1` built vs explorer | 60 | 75.0% [62.8–84.2] |
| `sampled-2` Sample Gangers vs random | 60 | 68.3% [55.8–78.7] |
| `sampled-3` random vs random-b | 60 | 73.3% [61.0–82.9] |
| `sampled-4` random vs random-b | 60 | 83.3% [72.0–90.7] |
| `sampled-5` random vs built | 60 | 81.7% [70.1–89.4] |


### Frozen panel: neural — 2026-09-11 01:06 UTC

Panel `a1832d477c27193f`, decks `1b1799dbc029a6b7`, frozen 2026-09-10: 6 deck pairings whose **decklists are stored verbatim in `data/arena/panel.json`** and are never redrawn from the sampler, 60 games each, no early stopping. Both digests are checked on load, so these numbers are comparable across every generation as long as they read `a1832d477c27193f` / `1b1799dbc029a6b7`.

| opponent | games | win rate | 95% Wilson (these decks) | per-pairing spread | decisive pairs |
|---|---:|---:|---|---|---|
| uniform random legal play (`random`) | 360 | 96.1% | 93.6–97.7% | 88.3–100.0% | 166/166 |
| the frozen one-ply heuristic (`heuristic`) | 360 | 75.8% | 71.2–80.0% | 68.3–83.3% | 96/99 |
| the generation-0 snapshot (`gen0`) | — | not available yet | — | — | lands with the first trained model; until then this row reads "not available yet" and the panel is two members |

Here the Wilson interval is the right one and the *only* one that changes between generations: the decks are fixed by the panel, so nothing but more games is being sampled. The per-pairing spread is printed beside it as a reminder of what the panel is not — a panel score is a score on these twelve decklists, and generalises no further than they do. For a claim about play in general, use the between-pairing interval from `a-vs-b` or `generalisation`.


### Generalisation gap: neural vs heuristic — 2026-09-11 01:06 UTC

The same agent against the same baseline on three deck populations. Both seats draw from the same population in each row, so the number measures play, not deck strength; what matters is the difference between the rows.

| deck population | pairings | games | win rate | 95% Wilson (these decks) | per-pairing spread |
|---|---:|---:|---:|---|---|
| training — the training mix (learn.decks.DEFAULT_MIX), the distribution self-play draws from | 6 | 360 | 79.7% | 75.3–83.6% | 63.3–91.7% |
| holdout — the two retail starters, held out of training entirely — **one** matchup, because the game has exactly two of them | 1 | 360 | 80.0% | 75.6–83.8% | one matchup |
| unseen-random — fresh RAM-legal random decks on a deck seed training never used. **Not** out of distribution: `random` is the 0.30 slice of the training mix, so this row is a fresh draw from a source the model does train on, and it isolates the unstructured end of that mix rather than testing transfer | 6 | 360 | 75.8% | 71.2–80.0% | 70.0–90.0% |

**Gap to the held-out starters: -0.3 points, and no test statistic.** The holdout is 1 matchup, so those games are not a sample of a deck population and a two-proportion z over them would claim a precision the design cannot support. Read it against the training row's own scatter instead: its 6 pairings run 63.3–91.7%, which puts the holdout rate inside the range the training decks themselves cover.

Gap to fresh random decks: +3.9 points, 95% interval over the pairings +3.9 [-7.9 to +15.7] points (Welch, two independent samples of deck pairings). Both rows have deck pairings to spare, so this comparison is between deck *populations* and not between two piles of games.

A gap that grows generation over generation means memorised matchups. Watch the change in these numbers, and only trust a change that is large against the per-pairing spread beside it.


### Delayed-reward suite: neural — 2026-09-11 01:07 UTC

**Solved 3 of 8** (56 of 128 trials won), against a floor of 12 of 128 trials for uniform random play. Every position has a verified winning line that the frozen heuristic does not find on any of these seeds; a position counts as solved only when the agent wins it on every one of them. The suite holds 5 at a horizon of one turn (won inside the searched turn), 3 at a horizon of two turns (the payoff lands after the rival's answer).

| position | source | horizon | trials won | floor | solved |
|---|---|---:|---:|---:|---|
| `gear-before-the-raid` | hand-built | 1 | 16/16 | 3/16 | yes |
| `sell-to-afford-the-raid` | hand-built | 1 | 8/16 | 3/16 | no |
| `two-pieces-of-gear` | hand-built | 1 | 0/16 | 0/16 | no |
| `mined-23767-79` | mined from heuristic self-play | 1 | 16/16 | 3/16 | yes |
| `mined-23773-81` | mined from heuristic self-play | 1 | 0/16 | 0/16 | no |
| `mined-166300-77` | mined from heuristic self-play | 2 | 0/16 | 3/16 | no |
| `mined-166302-115` | mined from heuristic self-play | 2 | 16/16 | 0/16 | yes |
| `mined-166305-59` | mined from heuristic self-play | 2 | 0/16 | 0/16 | no |

**Horizon** is how far past the searched turn the win may land, counted in the searched player's own turns. At 1 the line wins inside the turn; at 2 the searched turn cannot win by itself and has to leave a board the frozen policy converts on the following turn — a reward that arrives after the move that earned it. Only the searched turn is chosen by the agent either way: the suite measures which line you take *this* turn, not whether you can plan two of them.

**Floor** is uniform random play over the same turn, on the same seeds, stored when the position was qualified. Read the agent's column against it, not against the frozen heuristic's zero: the heuristic scores zero here by construction, because missing these positions on these seeds is how they were selected.

The win is confirmed by playing the turn out and the rival's whole reply with the frozen heuristic in both seats, so a line that reaches seven Gigs and has them stolen back does not count. That reply is one competent defence and one sample of the rival's Gig die, not a proof against every defence.


### The 50,000-action ceiling: the no-op guard did not work

The first `arena generalisation neural` run died on `RuntimeError: game 5005167 exceeded 50000
actions` — `sim/runner.py`'s safety ceiling, which means an agent was cycling rather than advancing
the game. It is exactly the failure `agents/neural.py`'s `_value` guard was written to prevent, and
the guard did not prevent it, because of how it asked the question:

```python
if (here is not None and c.pending is not None and c.pending.player == self.me
        and c.pending.options == here.options and x == here.x):
```

A preview is produced by `apply` on a clone and then handed straight to the scorer, so its pending
menu has not been through `legal_actions` and does not hold the options the agent would actually
face. Comparing it against the live menu therefore fails on positions that genuinely are the same
one, and the guard stayed silent through the loop it was guarding.

The replacement does not ask what the agent can perceive; it compares the two states directly —
every mutable board array, both players' zones, the dice, the per-turn bookkeeping, and the kind of
choice and player to move — so it can neither miss a repeat nor mistake two different positions for
the same one. Cheap scalars are tested first, so a mismatch costs a couple of integer comparisons
and only a genuine repeat pays for the whole comparison.

Measured on the pairing the crash came from, scanning every seed across both match orderings and
both seat assignments: **3 hung games with the old guard, 0 with the new one.**

Two process notes worth keeping, because both nearly buried this:

* Every attempt to reproduce the crash *succeeded* — that is, found nothing — because the fix
  landed at 01:04:55, thirty seconds before the run died, and everything afterwards ran the fixed
  code. The reproduction only worked once the old file was checked out again deliberately.
* The ceiling used to report only a seed. Seeds are reused across pairings and across both seat
  assignments, so a bare seed cannot be replayed without re-deriving the arena's seed arithmetic by
  hand. It now names both decks and both agents.



### ismcts vs neural — 2026-09-11 04:28 UTC

`arena a-vs-b ismcts neural` over 6 deck pairings sampled from deck seed 20260910, SPRT at delta 0.05.

300 games over 5 deck pairings, 150 paired comparisons — every seed played from both seats and with the deck assignments swapped. Ruleset `149b39c8f55e9d41`, 764.0s.

| | games | win rate | 95% Wilson (these decks) |
|---|---:|---:|---|
| **ismcts** | 300 | 61.0% | 55.4–66.3% |
| neural | 300 | 39.0% | 33.7–44.6% |

The Wilson interval above is **conditional on these 5 deck pairings**: it says what more games on these decks would tell you, and nothing about other decks. Per-pairing rates run 55.0–66.7%; over the deck population the mean is 61.0 [55.6–66.4]% (t4 on 5 pairings). **That second band is the error bar for ismcts's strength**, and a generation-over-generation claim has to clear it rather than the Wilson one — the same protocol on five different deck samples moves several points while nothing about the agents changes. It is estimated from only 5 pairings, so it is itself noisy and can land either side of the Wilson bracket: narrower when the pairings happened to agree, much wider when one of them did not.

Paired test: 38 of 43 decisive pairs (88.4%) — agent A is stronger (SPRT accepted H1). Stopped early.

ismcts sat in seat 0 in 150 of 300 games — exactly half, by construction. ismcts on the play: 66.7% [58.8–73.7] (who goes first is the d20 winner's *choice*, so this is description, not balance). Average game length 12.9 turns. End reasons: OVERTIME 80, SEVEN_GIGS 220.

| deck pairing | games | ismcts win rate |
|---|---:|---|
| `sampled-0` built vs built-b | 60 | 55.0% [42.5–66.9] |
| `sampled-1` built vs explorer | 60 | 60.0% [47.4–71.4] |
| `sampled-2` Sample Gangers vs random | 60 | 66.7% [54.1–77.3] |
| `sampled-3` random vs random-b | 60 | 63.3% [50.7–74.4] |
| `sampled-4` random vs random-b | 60 | 60.0% [47.4–71.4] |


### Delayed-reward suite: ismcts — 2026-09-11 04:32 UTC

**Solved 4 of 8** (64 of 128 trials won), against a floor of 12 of 128 trials for uniform random play. Every position has a verified winning line that the frozen heuristic does not find on any of these seeds; a position counts as solved only when the agent wins it on every one of them. The suite holds 5 at a horizon of one turn (won inside the searched turn), 3 at a horizon of two turns (the payoff lands after the rival's answer).

| position | source | horizon | trials won | floor | solved |
|---|---|---:|---:|---:|---|
| `gear-before-the-raid` | hand-built | 1 | 16/16 | 3/16 | yes |
| `sell-to-afford-the-raid` | hand-built | 1 | 16/16 | 3/16 | yes |
| `two-pieces-of-gear` | hand-built | 1 | 0/16 | 0/16 | no |
| `mined-23767-79` | mined from heuristic self-play | 1 | 16/16 | 3/16 | yes |
| `mined-23773-81` | mined from heuristic self-play | 1 | 0/16 | 0/16 | no |
| `mined-166300-77` | mined from heuristic self-play | 2 | 0/16 | 3/16 | no |
| `mined-166302-115` | mined from heuristic self-play | 2 | 16/16 | 0/16 | yes |
| `mined-166305-59` | mined from heuristic self-play | 2 | 0/16 | 0/16 | no |

**Horizon** is how far past the searched turn the win may land, counted in the searched player's own turns. At 1 the line wins inside the turn; at 2 the searched turn cannot win by itself and has to leave a board the frozen policy converts on the following turn — a reward that arrives after the move that earned it. Only the searched turn is chosen by the agent either way: the suite measures which line you take *this* turn, not whether you can plan two of them.

**Floor** is uniform random play over the same turn, on the same seeds, stored when the position was qualified. Read the agent's column against it, not against the frozen heuristic's zero: the heuristic scores zero here by construction, because missing these positions on these seeds is how they were selected.

The win is confirmed by playing the turn out and the rival's whole reply with the frozen heuristic in both seats, so a line that reaches seven Gigs and has them stolen back does not count. That reply is one competent defence and one sample of the rival's Gig die, not a proof against every defence.


### Frozen panel: ismcts — 2026-09-11 04:32 UTC

Panel `a1832d477c27193f`, decks `1b1799dbc029a6b7`, frozen 2026-09-10: 6 deck pairings whose **decklists are stored verbatim in `data/arena/panel.json`** and are never redrawn from the sampler, 60 games each, no early stopping. Both digests are checked on load, so these numbers are comparable across every generation as long as they read `a1832d477c27193f` / `1b1799dbc029a6b7`.

| opponent | games | win rate | 95% Wilson (these decks) | per-pairing spread | decisive pairs |
|---|---:|---:|---|---|---|
| uniform random legal play (`random`) | 360 | 97.2% | 95.0–98.5% | 95.0–100.0% | 170/170 |
| the frozen one-ply heuristic (`heuristic`) | 360 | 83.6% | 79.4–87.1% | 76.7–91.7% | 123/125 |
| the generation-0 snapshot (`gen0`) | — | not available yet | — | — | lands with the first trained model; until then this row reads "not available yet" and the panel is two members |

Here the Wilson interval is the right one and the *only* one that changes between generations: the decks are fixed by the panel, so nothing but more games is being sampled. The per-pairing spread is printed beside it as a reminder of what the panel is not — a panel score is a score on these twelve decklists, and generalises no further than they do. For a claim about play in general, use the between-pairing interval from `a-vs-b` or `generalisation`.


### ismcts vs neural — 2026-09-11 17:51 UTC

`arena a-vs-b ismcts neural` over 6 deck pairings sampled from deck seed 20260910, SPRT at delta 0.05.

216 games over 6 deck pairings, 108 paired comparisons — every seed played from both seats and with the deck assignments swapped. Ruleset `149b39c8f55e9d41`, 762.2s.

| | games | win rate | 95% Wilson (these decks) |
|---|---:|---:|---|
| **ismcts** | 216 | 57.9% | 51.2–64.3% |
| neural | 216 | 42.1% | 35.7–48.8% |

The Wilson interval above is **conditional on these 6 deck pairings**: it says what more games on these decks would tell you, and nothing about other decks. Per-pairing rates run 50.0–66.7%; over the deck population the mean is 57.9 [50.4–65.3]% (t5 on 6 pairings). **That second band is the error bar for ismcts's strength**, and a generation-over-generation claim has to clear it rather than the Wilson one — the same protocol on five different deck samples moves several points while nothing about the agents changes. It is estimated from only 6 pairings, so it is itself noisy and can land either side of the Wilson bracket: narrower when the pairings happened to agree, much wider when one of them did not.

Paired test: 25 of 33 decisive pairs (75.8%) — undecided at this sample size.

ismcts sat in seat 0 in 108 of 216 games — exactly half, by construction. ismcts on the play: 60.2% [50.8–68.9] (who goes first is the d20 winner's *choice*, so this is description, not balance). Average game length 13.2 turns. End reasons: OVERTIME 73, SEVEN_GIGS 143.

| deck pairing | games | ismcts win rate |
|---|---:|---|
| `sampled-0` built vs built-b | 36 | 55.6% [39.6–70.5] |
| `sampled-1` built vs explorer | 36 | 66.7% [50.3–79.8] |
| `sampled-2` Sample Gangers vs random | 36 | 66.7% [50.3–79.8] |
| `sampled-3` random vs random-b | 36 | 52.8% [37.0–68.0] |
| `sampled-4` random vs random-b | 36 | 55.6% [39.6–70.5] |
| `sampled-5` random vs built | 36 | 50.0% [34.5–65.5] |


### Frozen panel: ismcts — 2026-09-11 17:51 UTC

Panel `a1832d477c27193f`, decks `1b1799dbc029a6b7`, frozen 2026-09-10: 6 deck pairings whose **decklists are stored verbatim in `data/arena/panel.json`** and are never redrawn from the sampler, 60 games each, no early stopping. Both digests are checked on load, so these numbers are comparable across every generation as long as they read `a1832d477c27193f` / `1b1799dbc029a6b7`.

| opponent | games | win rate | 95% Wilson (these decks) | per-pairing spread | decisive pairs |
|---|---:|---:|---|---|---|
| uniform random legal play (`random`) | 360 | 96.9% | 94.6–98.3% | 91.7–100.0% | 169/169 |
| the frozen one-ply heuristic (`heuristic`) | 360 | 85.0% | 80.9–88.3% | 81.7–90.0% | 127/128 |
| the generation-0 snapshot (`gen0`) | — | not available yet | — | — | lands with the first trained model; until then this row reads "not available yet" and the panel is two members |

Here the Wilson interval is the right one and the *only* one that changes between generations: the decks are fixed by the panel, so nothing but more games is being sampled. The per-pairing spread is printed beside it as a reminder of what the panel is not — a panel score is a score on these twelve decklists, and generalises no further than they do. For a claim about play in general, use the between-pairing interval from `a-vs-b` or `generalisation`.


### Generalisation gap: ismcts vs heuristic — 2026-09-11 18:26 UTC

The same agent against the same baseline on three deck populations. Both seats draw from the same population in each row, so the number measures play, not deck strength; what matters is the difference between the rows.

| deck population | pairings | games | win rate | 95% Wilson (these decks) | per-pairing spread |
|---|---:|---:|---:|---|---|
| training — the training mix (learn.decks.DEFAULT_MIX), the distribution self-play draws from | 6 | 24 | 79.2% | 59.5–90.8% | 50.0–100.0% |
| holdout — the two retail starters, held out of training entirely — **one** matchup, because the game has exactly two of them | 1 | 24 | 95.8% | 79.8–99.3% | one matchup |
| unseen-random — fresh RAM-legal random decks on a deck seed training never used. **Not** out of distribution: `random` is the 0.30 slice of the training mix, so this row is a fresh draw from a source the model does train on, and it isolates the unstructured end of that mix rather than testing transfer | 6 | 24 | 91.7% | 74.2–97.7% | 75.0–100.0% |

**Gap to the held-out starters: -16.7 points, and no test statistic.** The holdout is 1 matchup, so those games are not a sample of a deck population and a two-proportion z over them would claim a precision the design cannot support. Read it against the training row's own scatter instead: its 6 pairings run 50.0–100.0%, which puts the holdout rate inside the range the training decks themselves cover.

Gap to fresh random decks: -12.5 points, 95% interval over the pairings -12.5 [-34.0 to +9.0] points (Welch, two independent samples of deck pairings). Both rows have deck pairings to spare, so this comparison is between deck *populations* and not between two piles of games.

A gap that grows generation over generation means memorised matchups. Watch the change in these numbers, and only trust a change that is large against the per-pairing spread beside it.


### Generalisation gap: ismcts vs heuristic — 2026-09-11 18:52 UTC

The same agent against the same baseline on three deck populations. Both seats draw from the same population in each row, so the number measures play, not deck strength; what matters is the difference between the rows.

| deck population | pairings | games | win rate | 95% Wilson (these decks) | per-pairing spread |
|---|---:|---:|---:|---|---|
| training — the training mix (learn.decks.DEFAULT_MIX), the distribution self-play draws from | 6 | 72 | 84.7% | 74.7–91.2% | 58.3–100.0% |
| holdout — the two retail starters, held out of training entirely — **one** matchup, because the game has exactly two of them | 1 | 72 | 94.4% | 86.6–97.8% | one matchup |
| unseen-random — fresh RAM-legal random decks on a deck seed training never used. **Not** out of distribution: `random` is the 0.30 slice of the training mix, so this row is a fresh draw from a source the model does train on, and it isolates the unstructured end of that mix rather than testing transfer | 6 | 72 | 88.9% | 79.6–94.3% | 75.0–100.0% |

**Gap to the held-out starters: -9.7 points, and no test statistic.** The holdout is 1 matchup, so those games are not a sample of a deck population and a two-proportion z over them would claim a precision the design cannot support. Read it against the training row's own scatter instead: its 6 pairings run 58.3–100.0%, which puts the holdout rate inside the range the training decks themselves cover.

Gap to fresh random decks: -4.2 points, 95% interval over the pairings -4.2 [-20.7 to +12.4] points (Welch, two independent samples of deck pairings). Both rows have deck pairings to spare, so this comparison is between deck *populations* and not between two piles of games.

A gap that grows generation over generation means memorised matchups. Watch the change in these numbers, and only trust a change that is large against the per-pairing spread beside it.


### Cost of hidden information: ismcts — 2026-09-11 19:22 UTC

`cheat:ismcts` is the same agent with determinization replaced by the true state: same budget, same evaluation, same policy, perfect information.

Cheating beats honest **45.8%** [27.9–64.9] over 24 games (0/1 decisive pairs), the bracket conditional on 6 deck pairings; over the deck population 45.8 [35.1–56.5]%.

*This is a ceiling for this agent at this budget — the value of perfect information to its own search — not an upper bound on play quality.*


## Stage 3: the search teacher, and what it did not buy

The stage shipped and its headline claim passed. It did not do the thing it was named for, and that
is the first sentence rather than a footnote.

`two-pieces-of-gear` in `data/arena/delayed.json` is the position the plan called "the thesis of
this stage as a unit test": both Gear equipped *before* the attack, because 7+2 and 7+1 each still
steal one Gig and only 7+2+1 crosses the threshold, so each equip alone scores as a rounding error
and no per-decision agent can reach it at any strength of evaluation. **ISMCTS at 200 iterations
solves it 0 times in 16.** Three of the eight suite positions are still unsolved and they are the
horizon-2 ones. Searching the sequence produced a materially stronger player; it did not produce
the two-move plan that justified building it.

### Every row here was re-measured after the no-op fix

The fix at the end of this section changes which actions the search considers at the root, so an
agent measured before it is not the agent in the repo. The first four rows of this gate were run
pre-fix and are not quoted as the result; they are quoted beside it, because the *difference*
between them is the only honest estimate this project has of what re-running a row costs in noise.

| row | post-fix result | pre-fix reading | Stage 2's agent |
|---|---|---|---|
| `a-vs-b` vs `neural` | 57.9% [51.2–64.3] over 216, SPRT undecided | 61.0% over 300, SPRT accepted | — |
| `panel` vs uniform random | 96.9% [94.6–98.3] over 360 | 97.2% [95.0–98.5] | — |
| `panel` vs the frozen heuristic | **85.0%** [80.9–88.3] over 360 | 83.6% [79.4–87.1] | **75.8%** |
| `generalisation`, gap to fresh random | −4.2 [−20.7 to +12.4] over 72/row | never produced a number | +3.9 [−7.9 to +15.7] |
| `exploit`, the cheating agent | 45.8% [27.9–64.9] over 24 | 47.5% over 200 | — |

Two of those moved by about a point and a half and one moved by three. None of the movements is
large against its own interval, which is the expected result and worth recording precisely because
it is boring: it says a re-run of this protocol is worth a couple of points of wobble, and a
generation-over-generation claim of two points is therefore worth nothing.

The `a-vs-b` row deserves its own sentence, because the number went *down* and the verdict went
with it. 61.0% over 300 games cleared SPRT; 57.9% over 216 does not, and the honest reason is that
the second run is smaller, not that the agent got worse — 57.9% is inside the first run's interval
and the first is inside the second's. The row that carries the stage is the panel row anyway.

The panel row is the one worth keeping. The frozen heuristic cannot move — it is frozen by project
rule and by test — so a score against it is the closest thing this project has to a fixed yardstick,
and search over the *same weights* is worth **nine points** on it, 75.8% to 85.0%, with the two
Wilson intervals nowhere near touching. That is the version of the result that cannot be explained
by two agents drifting together, and it is exactly the check that `learn/loop.py` now makes a
condition of promotion.

### Generalisation: the row the hang cost us, and what it does not say

This row has never produced a number before — it crashed three hours in on the cycle described
below, and two attempts to re-run it were killed by the container restarting. It exists now, and it
was run twice, which turned out to matter.

| | training mix | held-out starters | fresh random decks |
|---|---:|---:|---:|
| 24 games/row | 79.2% [59.5–90.8] | 95.8% | 91.7% [74.2–97.7] |
| **72 games/row** | **84.7%** [74.7–91.2] | **94.4%** [86.6–97.8] | **88.9%** [79.6–94.3] |

Both gaps come out **negative** — the agent scores *better* off the training mix than on it, which
is the opposite sign from memorisation. And both shrank toward zero as the sample grew, −16.7 to
−9.7 on the holdout and −12.5 to −4.2 on fresh random, which is what a gap of zero measured twice
looks like. The Welch interval on the fresh-random gap is [−20.7 to +12.4]: it contains zero and it
contains Stage 2's +3.9, so the bar the plan set — *the gap must not widen* — is cleared in the only
sense this sample can support, which is that a widening large enough to see is not there.

The first of those two runs is the reason the pair is printed. It was launched at `-n 20`, which
the arena reads as games *per row* and rounds to 24 — four games a deck pairing, Wilson bars of
±16 points. That row cannot detect the thing it exists to detect, and publishing it alone would
have been publishing a coin flip with a table around it. The re-run at 72 is still small; it is
labelled small rather than quoted as though it were the 360-game protocol.

### The exploit row, and what a two-searching-sides game costs

`cheat:ismcts` searches the true state instead of a world sampled from what its seat may
legitimately know, and over 200 pre-fix games it **was not ahead**: 47.5%, every cumulative reading
below even money, the trend flat. On 200 games the interval around that is roughly 40.6–54.5%, so
this does not establish that cheating *hurts* — it establishes that whatever hidden information is
worth to this search is smaller than this measurement can resolve, and is certainly not the large
advantage one would expect if determinization were failing. Two readings, and the row cannot
separate them: the determinization is doing its job, or the search is not deep enough to exploit
what it is handed. The second would be another argument for the policy head, whose entire purpose
is to buy depth.

The post-fix check on this row is deliberately small, and the arithmetic is the reason. A game
where **both** sides run a 200-iteration search costs about 150 CPU-seconds — fifteen times the
`a-vs-b` row, whose opponent is a one-ply agent doing almost none of the work — and this is the
only row in the gate with two searching sides. At the 240 games the protocol wants, that is two and
a half hours in one unbroken block, on a box that went down three times in an afternoon. The
pre-fix 200-game number therefore stands as the estimate and the post-fix run is sized as a
direction check, with bars wide enough that it can only contradict the estimate, never refine it.
It does not contradict it: 45.8% [27.9–64.9] over 24 games, the same side of even money, an
interval that contains the 200-game figure and most other figures besides.

Sizing every other run in this project off the `a-vs-b` number was an error that cost most of a
night before it was caught. It is written down here because the cost of the mistake was entirely in
not having measured the thing that was being assumed.

### The 50,000-action ceiling, again: a guard is not a guard on a class of bug

`arena generalisation ismcts` ran for three hours and died on
`game 5005167 exceeded 50000 actions ... pending 6` — a PICK. It is the *same seed* that hung
`neural`, documented above, and the same cause.

The pool contains one free no-op. `panam-palmer-strength-through-family` has a zero-cost ability
with no spend and no once-per-turn marker, and it calls `offer_call_free`, which is `optional=True`
with no `otherwise`: activate it, choose the trailing `Pick(())`, and the continuation does nothing.
You are returned to a byte-identical position. That is rules-correct — the card says you *may* Call
a Legend for free, and declining means you have not Called, so the flag is rightly unset. Real
players never do it. The agent has to be the robust part.

`neural` was given a guard for exactly this: `_same_position`, compared field by field, scored as a
loss inside `_value`. Then `IsmctsAgent` replaced `_greedy` wholesale, and its three scoring paths —
`_leaf`, `_priors`, `_terminal` — all bypass `_value`. It **imported `_same_position` and never
called it**, which is why the module read as though the guard were wired in. A child that returns to
the root scored the root's own value: competitive with any real move, and free. It collected visits
and `_choose` handed it back for ever.

`_root_actions` now drops any option that leaves the game in a position indistinguishable from the
one being chosen from. The root is where this has to be caught, because `_choose` can only return
something the root offered. If every option is a no-op it keeps them all — refusing to move is not
available — and it settles before comparing, so a compound action is judged on where it lands.
Measured at 230 us for the whole method on a 13-option menu against ~140 ms for a decision. It does
not catch a two-step cycle, and the comment says so rather than leaving that to be discovered.

**The lesson is about the test, not the guard.** The guard was written, measured, documented, and
given a regression test — a test that named `neural`, the agent that was broken at the time. The
next agent bypassed the code path holding it and nothing noticed for a month.
`tests/props/test_no_agent_cycles.py` plays the known-hanging seed with *every* agent the registry
can build, from both seats, at a reduced search budget, so the next one is covered on the day it is
written rather than on the day it costs a three-hour gate run. Run against the code before the fix
it fails on `ismcts` and `ismcts-flat` — and passes on `ismcts-explore`, whose visit-proportional
sampling shakes it loose by luck, exactly the way the frozen heuristic escapes by luck. Neither
passing was ever evidence of anything.

The same shape of mistake turned up twice more while finishing this gate, both in the shell rather
than the engine, and both worth a line because they are the same error. The chunk scripts waited
for each other with `pgrep -f "tools/arena.py"`, a pattern that matches any process whose command
line merely *contains* that string — including the session's own monitoring commands — so a chunk
sat waiting eleven minutes on a phantom. And an earlier run of this project killed its own shell
with `pkill -f`, for the same reason. A predicate that can match the thing asking the question is
not a predicate; the fix in both cases was to remove the question, not to sharpen it.


## Generation 1: the handle turns

The loop promoted a generation. It is the first one, generation 0 having been rejected at 10%, and
the reason for the gap between them is not compute — it is that the loop could not have promoted
anything at any budget until two things were fixed.

### Why generation 0 could never have worked

`step_fit` built its replay window by globbing generation directories. The bootstrap corpus the
model is supposed to improve *on* lives in none of them, so generation 0 was fitted on its own 300
games alone: **6,900 rows, against an incumbent fitted on 1,453,992.** It scored 10% and that was
written down here as the promotion rule working correctly. It was — but it was also a structural
failure, and the half that was missed is the more important one. Every future generation would
have failed the same way, for the same invisible reason, and the failure would have looked like
evidence that the idea was wrong rather than that the plumbing was.

The window now carries a *seed corpus* and retires it once self-play rows reach three times its
size, so the bootstrap anchors the early generations and does not anchor them for ever. Generation
1 was fitted on 2,147,010 rows: the seed's 1,453,992 plus 693,018 of its own.

### The second fix: a budget that could be reached

Search budget was a class attribute. Everything ran at 200 iterations. Measured on the shape a
generation actually runs — both sides `ismcts-explore`, four cores:

| iterations | games/hour |
|---:|---:|
| 8 | 11,913 |
| 32 | 3,335 (observed 3,700–5,400 in the real run) |
| 200 | 434 |

At 200, matching the bootstrap's 50,000 games is eleven hundred hours. The budget now travels
inside the agent name (`ismcts-explore:32@weights.json`) beside `cheat:` and `@weights`, so it
reaches worker processes. **The data is therefore search-selected by a shallower search than the
one being measured, and that is a real concession, stated here rather than buried.**

### What generation 1 is, and what the gate said

30,000 games — 25,500 self-play, 3,000 against the frozen heuristic, 1,500 against random — at
budget 32, sampled at 0.125 from both perspectives into 693,018 rows.

Both sides of the gate ran at budget 32. That matters: the incumbent's 85.0% panel score on record
was measured at 200, and comparing a candidate at 32 against it would have been comparing budgets
rather than weights. So the incumbent was re-measured at the candidate's budget.

| check | candidate | incumbent | verdict |
|---|---|---|---|
| head-to-head, 408 games | **59.1%** [54.2–63.7], band from 54.3 | — | SPRT accepted H1 |
| frozen panel vs `heuristic` | **87.2%** [83.4–90.3] | 79.4% [75.0–83.3] | +7.8, intervals clear |
| frozen panel vs `random` | 97.2% | 96.9% | unchanged |
| delayed-reward suite | 4 of 8 | 4 of 8 | no ability lost |

`decide` returns **promote**: *beat the incumbent 59.1% [band from 54.3%], panel 87.2% against
79.4%, delayed 4 against 4.*

The panel row is the one that carries it. The frozen heuristic cannot move, so a score against it
is the nearest thing to a fixed yardstick, and 79.4 to 87.2 at matched budget cannot be explained
by the candidate and the incumbent drifting together — which is the exact failure the panel exists
to catch.

### What this does not say

The holdout Brier went the *wrong* way: 0.14420 against the bootstrap's 0.13914. That is not
evidence of a worse model, because the two numbers are computed on different holdout sets — the
candidate's includes search self-play, which is closer and harder to call than heuristic and random
games. It is also not evidence of a better one. Comparing Brier across distributions establishes
nothing in either direction, and the only reason it appears here is that quoting it as an
improvement would have been easy and wrong.

`two-pieces-of-gear` is still 0 of 16. Three generations of work have now gone past the position
this whole line of work was named for, and none of them solves it.

### The container, which shaped the schedule more than any decision did

The box reclaims itself when the session goes idle, and — measured, not assumed — a *scheduled
wake provisions a fresh container*, killing whatever is running.

| condition | throughput |
|---|---|
| hourly watchdog + 10-minute keepalive armed | 160 games / 80 min |
| no timers, session actively working | **640 games / 9.5 min** |
| no timers, session idle | dies about 6 minutes later |

Every trigger fire landed on a container with 0 minutes of uptime, three for three. The watchdog
built to protect the run was the thing ending it, and an earlier note in this session calling it
"earning its keep" when it relaunched the harvest had it backwards: it was cleaning up its own
damage. With both timers deleted the harvest ran 4 hours 46 minutes without interruption and
finished all 30,000 games.

`--chunk` became a flag for the same reason. The chunk is also the unit of resume, and the default
sized it from the job — 250 games, about eighteen minutes — so a restart threw away a third of an
interval. At 40 it is well under a minute.

### A third instance of the same bug

The gate refused to start: `unknown agent 'ismcts:32@out/learn/gen-001/weights.json'`. `agent_base`
in `learn/arena.py` undresses a decorated name, and its docstring says *"there is exactly one place
that does: here."* A third decoration was added to `make_agent` and not to it. The promise in the
docstring did not keep itself, in the same way the no-op guard's regression test did not cover the
agent that came after the one it named.

`tests/learn/test_arena.py` now asserts against the separator *constants* rather than literal
strings, so a fourth decoration fails on the day it is added rather than five hours into the next
generation.


## The gear-aware feature set, and why it was not shipped

The agent plays Units on 11.5% of the menus that offer them, Programs on 6.9%, Gear on 4.0%, and
the eight zero-power Units on 3–6%. That is not taste. The feature vector is 114 aggregate numbers
and **not one of them can see what a card does**: Gear appears as a count and a deck share, and the
only ability the model can read at all is BLOCKER. A simulator built to playtest a card pool could
not evaluate two of its four card types.

Eleven features were added to fix it — the power Gear actually contributes, how many bodies are
equipped, the largest Gear stack (Royce's payoff), Units carrying rules text, and what the hand can
*do* (draw, removal, pump, Gig manipulation). Every one was validated against hand-counted truth on
40 real positions rather than trusted, which caught a real bug: Gear equipped to a **face-up
Legend** was being dropped, because the side scan only walked the field. Cards say "Equip to a
friendly Unit or face-up Legend", so that was real power going uncounted.

Changing the vector is affordable precisely because games are stored as action sequences: all
80,000 games of history — the 50,000-game bootstrap and generation 1's 30,000 — were re-featured in
**five minutes**, with no searching agent replaying anything, into the same 2,147,010 rows.

The result was better prediction and worse play.

| | features | holdout Brier | accuracy | ECE | panel vs the frozen heuristic |
|---|---:|---:|---:|---:|---|
| gen-1 | 114 | 0.14420 | 0.7816 | 0.0211 | **87.2%** [83.4–90.3] |
| gear-aware | 125 | **0.14361** | **0.7825** | **0.0198** | 82.8% [78.5–86.3] |

Both were fitted on identical rows with an identical split, so the Brier comparison is valid for
once — and it moved the right way on all three measures. The panel moved 4.4 points the wrong way,
past the 3-point regression tolerance `learn.loop.decide` enforces. The intervals overlap, so this
does not establish that the extra features *hurt*; it establishes that they did not pay for
themselves, and that a model can be better calibrated and worse at playing.

It did do what it was built for, though the first measurement said otherwise. Compared against
plain `ismcts` the Gear play rate looked *down*, 4.0% to 3.4% — but the 4.0% baseline was measured
with `ismcts-explore`, which samples visit-proportionally and plays more variety by construction.
Against the same agent the honest number is **4.0% → 5.3%**, a third more often, on ~4,200 offers.
Units moved +0.3 and Programs not at all.

So the trade on offer was a third more Gear for four points of strength, and it was declined. The
work is parked rather than deleted, because the diagnosis stands and the next attempt is a better
one: aggregate counts still cannot express *"I control Royce and two Gear"*, which is where Gear's
value actually lives. The interaction map in `data/strategy/graph.json` already names those
relationships — a feature keyed to its tokens ("I hold a card paid for equipped Units, and I have
equipped Units") can say the thing eleven more counters could not.


## Generation 2: the handle turned and nothing moved

Thirty thousand more games — 18,000 self-play under generation 1's promoted weights, 7,500 against
the bootstrap as a league opponent, 3,000 against the frozen heuristic, 1,500 against random —
fitted over a window of 2,841,008 rows. **Rejected.**

| check | gen-2 | gen-1 (incumbent) | verdict |
|---|---|---|---|
| head-to-head, 408 games | 52.5% [47.6–57.3], band from **48.3** | — | SPRT undecided |
| frozen panel vs `heuristic` | 86.4% [82.5–89.5] | 87.2% [83.4–90.3] | flat |
| frozen panel vs `random` | 96.4% | 97.2% | flat |
| delayed-reward suite | 4 of 8 | 4 of 8 | flat |

`decide` returns reject on the first clause: the sequential test says `continue` at 52.5%, and the
between-pairing band reaches 48.3%, which does not clear even money on the deck population. Every
other row is within noise of the incumbent.

This is the more interesting outcome of the two. Generation 1 gained nine points on the frozen
panel by being the first generation fitted on *more data than the bootstrap alone*. Generation 2
added a comparable pile of data — 693,998 rows against generation 1's 693,018 — and bought nothing
measurable. Two readings, and this gate cannot separate them: the loop has found what a 16-unit
network over 114 aggregate features can express about this game, or 30,000 games a generation is
simply too few to move it and the curve is flat at this scale rather than finished.

The first reading is the one the evidence around it favours. The same day, eleven features that let
the model see Gear and card abilities improved every prediction measure and *lost* four points of
play, which is what a representation at its ceiling looks like: more information, no more skill.
The next thing worth trying is not another turn of the handle at this size. It is a representation
that can express what the interaction map already names — "I control Royce and two Gear" — because
neither the current features nor eleven more counters can say that sentence, and the pool's whole
Gear archetype is built on it.

The ledger now reads: generation 0 rejected at 10% (the loop could not fit), generation 1 promoted
at 59.1%, generation 2 rejected at 52.5%. That is a promotion rule doing its job in both
directions, which is the property worth having before any of this is trusted.
