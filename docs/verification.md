# What is actually checked, and what was not

This project has always had a lot of tests. Until this pass it had almost no *card* tests, and no
way to tell the difference — which is the more serious half of the sentence.

## The zero that said nothing

`CardDef.needs_script` was the only card-correctness signal in the repository. It is derived from
"the printed text implies an effect and there is no script", so it detects a **missing** script and
is structurally blind to a wrong or partial one. It read `0` for every card in the pool, and the
project quoted that zero as coverage.

Everything the lab has produced — 80,000 harvested games, every gate run, the panel, the delayed
suite, every deck report, every fitted model — rests on 140 hand-written card scripts in one file.
Nothing had ever verified that any of them does what its card says. The repo's own history says what
that costs: a hand-authored classification was wrong at Chrome Reverie and MaxTac Suppression Team
for weeks, and nothing raised. The graph loaded, the site rendered, the counts looked plausible.

## Four kinds of check, in order of how much they can prove

### 1. Lints over printed text vs implementation — `tests/cards/test_script_lints.py`

Each reads the whole pool mechanically rather than by someone looking, which is the only kind of
check that scales to 151 cards.

| lint | what it would catch |
|---|---|
| printed timing label → hook | text says `DEFEATED:` and the script has no `on_defeated` — the check `needs_script` cannot make, because it only asks whether *a* script exists |
| hook → printed timing label | an `on_attack` on a card whose text never mentions attacking |
| no continuation closes over the enclosing ctx | invisible in ordinary play, wrong under every searching agent — and every strong agent here searches |
| a state-based tail clause is not trapped in a continuation | **currently failing, six cards** — see below |

The last one is the Chrome Reverie rule applied: every confirmed finding is asked whether the error
is mechanically detectable from printed text across all 151 cards, and if it is, the detector ships
with the fix. Two audit batches working on unrelated sections filed five findings that turned out to
be one bug with five card names on it: a card prints two sentences, the second has its own board
condition, and the script implements it inside the *continuation* of the first — so declining the
first sentence, or having no legal way to perform it, skips the second entirely. Written as a lint
and run over the pool, it reproduced all five and found a sixth nobody had been assigned.

Getting the exclusions right is the whole detector. "If **it** becomes a min Gig" has nothing to
test when nothing was decreased, so nesting *that* is correct; "If **you control** a min Gig" is
about the board and is not. Both shapes are in the pool and only the second is a bug, so the
detector reads the subject of the condition and a self-test pins both directions.

### 2. Coverage floors — `tests/cards/test_coverage.py`, `tests/cards/test_pool_sweep.py`

A test that has never run against a card proves nothing about it, and nothing was tracking which
cards any test had ever *mentioned*. Eight scripted cards turned out never to be named by any test
module. Six of the eight are Legends, which is not chance: a Legend is never drawn and never sits in
`deck.main`, so it falls out of every draw-conditioned measurement too. Nothing was looking at them
from any direction. All eight now have scenario tests and the floor is a test of its own.

The sweep is the deterministic other half of `tools/smoke_pool.py`'s random fuzz. Each scripted card
is set up on a board rich enough for its effect to have something to work on and then played,
Called, sent GO SOLO, attacked with, activated or defeated — whichever its script actually hooks —
with every following decision answered twice, once always taking the first option and once always
the last. Invariants are checked after every action. It offers 300 entry points across 140 cards,
274 are legal, and **no card is left without one**; that last number is what the test asserts,
because a sweep that quietly stops reaching cards still reports green.

This finds exactly one class of thing — the crash or broken invariant — and finds it without anyone
reading a card. It says nothing about whether a card does what its text says.

### 3. Rules over the real pool — `tests/rules/test_pool_rules.py`

Forty-four rules tests existed and all but a handful ran on a thirteen-card toy registry. That
registry is the right tool for pinning a rule, but it says nothing about the 151 cards the lab plays
with: a rule that holds for `T-U4` and fails for one printed Unit in sixty was invisible.

Six properties are now asserted per card, so each test is a statement with a denominator rather than
an example. The Lag test found its own exceptions, which is the argument for writing them this way:
Nadia — Fighting Through Grief and Sandayu Oda — Hanako's Guardian each print that they can attack
the turn they are played and carry no keyword. Card text outranks the general rule, so both are
correct and the first version of the test was incomplete. It reads the exception off the printed
text now, so a third such card is caught the day it is printed.

### 4. The audit — reading 140 scripts against 145 card texts

Only a person (or an agent) reading the card can catch a wrong *effect*. The audit runs one reader
per contiguous section of `wnc.py`, in both directions — text→script for a missing clause and
script→text for an extra one, the direction auditors skip.

Two rules make the output trustworthy rather than merely voluminous.

**A finding has two legs.** An observed failing test *and* an expectation derived clause by clause
from the byte-exact printed text. A test alone proves what the engine does, not what it should do;
a test written by a reader who misread the card freezes a wrong expectation into the repo, which is
worse than the bug.

**Findings land red, mechanically.** Every finding is committed *before* any fix as
`@pytest.mark.xfail(strict=True)` with its id in the reason. Strict is the mechanism: the suite
stays green while findings are open, and the moment a fix makes one pass, pytest reports XPASS as a
failure. A fix cannot land without deleting the marker, and that deletion is the git record of red
before and green after. It replaces "the agent says it saw it fail" with something the repo
enforces.

Tests under `tests/cards/audit/` assert printed-text outcomes only — zones, Gig faces, hand size,
power, keywords — never a script internal. A test asserting a flag bit is unreviewable.

**Verification is two asymmetric skeptics.** The first is shown only the card and its script and
never the finding, and re-derives the card clause by clause; agreement counts only if it lands on
the same clause with the same direction of error. That is the anti-anchoring leg, and it is the
reason the pass is worth running at all. The second is told the finding is presumed wrong and must
kill it: a ruling covers it, the engine already handles it somewhere the filer did not look, the
test's board is unreachable, the test asserts internals, or the expectation misreads a word.

## The cards digest

`RulesConfig.digest()` exists so that changing a ruling *visibly* invalidates comparisons with older
runs instead of quietly shifting them, and `Replay.load` refuses a mismatch. Card behaviour was never
in that hash — so a card-script fix changes what the game *is*, every bit as much as flipping a
ruling does, and did it silently across every stored replay, league table, arena result and fitted
model.

`cards.registry.cards_digest()` now fingerprints the card data and the script sources together, and
is recorded beside `rules` in replays, tournaments, arena results and model files. **Recorded, not
enforced**: enforcing it on the day it was introduced would reject every artifact already on disk.
It does real work in one place already — the website's card guide compares it against the digest
stamped into the published measurement and says, in as many words, when the numbers describe the
game as it behaved before a fix.

## The golden protocol

`tests/golden/games.json` pins 224 games as exact action-index streams. A genuine card fix will
legitimately change some. The danger is regenerating on a diff nobody localised, which turns "the fix
worked" into "the fix, plus whatever else was on the tree". That file's history has exactly one
deliberate regeneration in it and that is the standard worth keeping.

Two measurements make per-fix gating affordable: `bench.py check` is about seven seconds, and the
eight golden decks between them reach only 95 of the 151 cards.

| tier | condition | expectation |
|---|---|---|
| **G0** | the card is in no golden deck (54 cards) | `check` **must** stay IDENTICAL; a change means the edit escaped its card |
| **G1** | the card is in at least one golden deck (86) | may differ, only on keys whose decks contain it |
| **G2** | the fix touches `dsl.py`, `effects.py` or `core/**` | unbounded; needs a written reason why it could not be localised |

`tools/golden_impact.py predict` writes the permitted key set down from deck membership alone,
before anything is touched. `verify` runs the check and refuses the result when an observed key
falls outside it — a hard stop with no regeneration. It prints the aggregate per key (games changed,
winner flips, end-reason changes, mean turn delta) and replays each first divergence into sentences,
because the fixed card has to appear in that window or the change there is unexplained. Two evidence
steps stay manual: revert the script hunk while keeping the new golden and confirm the same keys go
DIFFERENT, and — for a G0 card, which the golden cannot see at all — confirm `bench.py fuzz` moves,
or the fix is a no-op.

G0 fixes batch freely; the unbroken run of IDENTICAL across the batch *is* the proof of neutrality.
G1 and G2 land one at a time, each with its own regeneration commit, ordered by ascending golden-key
count so divergences are learned on cheap cases first. Two golden-affecting fixes between
regenerations destroys attribution.

## What the measurements can and cannot say

`tools/playtest.py` gives every card in the set a record by driving deck construction *from* the
coverage table — 48 of 124 non-Legend cards had no rows at all, and that is a coverage problem, not
a sample-size one. It reaches 147 of 150 cards at 500 games each.

Three statistics, in decreasing order of how much they are worth:

* **play rate** — of the games where a card was drawn, how often it was actually cast. New, and the
  one the draw-conditioned numbers could not see. A low one is not noise: the agent had the card in
  hand and chose something else, every time.
* **IWD** — win rate when drawn minus when not. A contrast, so it differences out most of what a
  deck contributes. Draw order still confounds it, and the repo's own report code says the causal
  instrument is `hill_climb`'s paired swap test rather than IWD.
* **win rate when played** — a *level*, not a contrast: there is no "not drawn" arm to difference
  against. For a Legend it is almost entirely a fact about the deck it was in, and the first sweep
  made that unmissable — the six Yellow Legends came back at .56–.62 and the six Blue ones at
  .28–.32, in blocks, with near-identical sample sizes, because each block is the same few decks
  played over and over. `tools/legend_swap.py` is the paired instrument for that question: replace
  exactly one Legend, replay the same seeds against the same gauntlet, count only the games exactly
  one arm won. On The Heist, swapping V — Corporate Exile for Judy Álvarez costs 0.062, not the 0.30
  the raw rates implied. The gap between those two numbers is the confound, measured.

The three cards the sweep cannot drive to target are the interesting output rather than a failure.
Chrome Reverie was drawn 2,424 times and played 62 — a 2.6% play rate — and the hand-written note
for it calls it "the card that punishes a rival who wins on exactly one attacker". Both of those are
now on the same page of the website, one under the other.
