# Learning from play

The deckbuilder learns from games; the player does not. Its evaluation is a table of hand-written
constants that ten thousand games leave untouched. The training loop closes that gap:

```
   self-play with search  ──►  experience files  ──►  train policy + value  ──►  gate
          ▲                                                                       │
          └────────────────────  accepted weights  ◄────────────────────────────────┘
```

This page is the shipped record of that loop. **What exists today is the first box: experience
capture.** The search agent, the model and the gate arrive in later stages, and each one adds its
section here — including the generation-by-generation numbers, published whether or not they
flatter the run. Until then the honest summary is: the format is in place, and the only games it
has stored were played by the existing heuristic agent, which does not search.

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
