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

**The blind leg has one structural blind spot, and it is worth naming rather than patching.** A
*prohibition* — "rival Units can't steal friendly Gigs with value higher than their power" — is not
verifiable from the card that prints it. That script only *records* the protection; whether it is
*consulted* is a fact about every other card that steals. The blind reader for Chrome Fang returned
"every clause matches", correctly, having read Chrome Fang, `EffectCtx.mod`, the expiry rule and the
protection gate — and the bug is in Gorilla Arms, which it was never shown. Findings of this shape
are adjudicated against the whole pool instead, and the adjudication is what the detector is built
from: the set contains two effect-driven steals, one routes its candidates through the protection
gate and one does not, and nothing in either printed text distinguishes them.

## The cards digest

`RulesConfig.digest()` exists so that changing a ruling *visibly* invalidates comparisons with older
runs instead of quietly shifting them, and `Replay.load` refuses a mismatch. Card behaviour was never
in that hash — so a card-script fix changes what the game *is*, every bit as much as flipping a
ruling does, and did it silently across every stored replay, league table, arena result and fitted
model.

`cards.registry.cards_digest()` now fingerprints the card data and the script sources together, and
is recorded beside `rules` in replays, tournaments, arena results, model files and harvest
manifests. **Recorded, not
enforced**: enforcing it on the day it was introduced would reject every artifact already on disk.
It did real work on the very first card fix, in two places. The website's card guide compares it
against the digest stamped into the published measurement and now says, in as many words, that
those numbers describe the game as it behaved before the fix. And
`tests/learn/test_harvest.py::test_the_committed_sample_still_replays` — a hundred games committed
as exact action-index streams, with the same staleness contract as the golden file — failed loudly,
because a card whose option count changes shifts every index after it. That is the alarm working:
the sample was regenerated deliberately, from the same seed and the same decks, and the diff is the
fingerprint of a small real change (14,848 decisions to 14,855, one game's winner moved). The
harvest manifest had recorded only `rules`, so it could say which *ruleset* produced a file and not
which *cards*; it records both now, which is what makes a future regeneration explicable rather than
merely necessary.

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
winner flips, end-reason changes, mean turn delta) and narrates each first divergence.

**Two things about that narration were wrong, and the first G1 fix found both.**

The rule was "the fixed card must appear in the replay window". Too narrow. The frozen heuristic
scores candidate actions by resolving them a ply deep, so a card that is merely *playable* changes
what the agent thinks the board is worth — Unlikely Bond was drawn, sat in hand, was never cast, and
the game still diverged eight decisions after it first became a legal option. The rule is now "a
named card must have been an **option** before the divergence", which is the claim the evidence can
support, and `verify` reports when it first was.

The instrument was worse: it narrated by replaying the *golden* action indices on the fixed engine.
An action index names a position in an option list, not a move. Removing an option changes what
index *i* means; removing a whole decision — `AskStep` resolves a one-option choice inline, so
dropping `optional=True` can delete a question outright — shifts every index after it. The replay
kept succeeding, because the shifted indices stayed in range, and narrated a game that never
happened. It now narrates the game the current engine actually plays, which needs no such
assumption. Two evidence
steps stay manual: revert the script hunk while keeping the new golden and confirm the same keys go
DIFFERENT, and — for a G0 card, which the golden cannot see at all — confirm `bench.py fuzz` moves,
or the fix is a no-op.

**The fuzz rule needs one qualification, learned on the second fix and confirmed on the Gorilla
Arms fix.** For the latter, both digests are identical over 200 fuzz games, and the reason is
measurable: in 400 heuristic games Gorilla Arms is played in 7 and a protection card in 98, but
both in only 3 — and the fix bites only when the protection is still live at the moment the Gear
triggers *and* the one die whose value is not already shared is a forbidden one.

 A G0 fix must move `fuzz` *or*
be a fix to a branch the fuzz demonstrably cannot reach — and "demonstrably" means measured, not
assumed. Memory Relapse's draw only differs when the rival controls no Units, and the frozen
heuristic is played 10 times in 300 games and essentially never casts a spend-a-rival-Unit Program
into an empty field, because the spend is the whole reason it plays the card. The branch matters to
a human and to a searching agent, not to the fuzz. Where that is the case, the red-to-green xfail
test *is* the reachability proof: it failed on a board a real game reaches and now passes.

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


## The prior the deck builders were reading

`Knowledge` is the builders' card prior — shrunk IWD per card, fed into the static score so each
generation of builders starts smarter than the last. It is the cheapest feedback loop in the project
and it is only as good as the games behind it.

The store the builders had been reading holds **1,440 games over 76 cards**, with effective sample
sizes small enough to print: Peace Offering at n=10.8, Meredith Stout at n=13.1, median n≈60. Put
beside the 24,240-game coverage sweep (median n≈636 over 150 cards), the two stores **disagree about
the direction of 34 of the 76 cards they both have an opinion on — 45%**.

That is not a curiosity about two datasets. Shrinkage was supposed to handle a thin estimate:
`iwd * n / (n + k)` pulls it toward zero. But shrinkage controls the *magnitude* of a noisy number,
not its sign, and the sign is what a builder reads when it decides whether a card earns a slot. For
half the cards the old store had an opinion about, that opinion was noise wearing a preference.

`tools/compare_knowledge.py` is the comparison, kept so it can be re-run rather than remembered.

What has deliberately **not** happened is swapping one store for the other. The newer one was
measured on coverage-driven decks — built to reach the tail of the card pool, not to be good decks —
and IWD differences out deck *shape* but not the field a deck faced. Whether the bigger store builds
better decks is a question for the builder, played head to head against itself with each prior, and
it is not a question either store can answer about itself. Until that runs, the honest statement is
narrower and still worth having: **the prior was thin enough that half of it was sign-noise**, which
is a much better reason to distrust the learned-archetype results than anything in the model.


## Does a stronger agent play the cards the heuristic refuses?

The coverage sweep's most surprising output was a set of cards the frozen heuristic holds and does
not cast. Two readings pointed opposite ways — the card is bad, or the evaluator is blind to it,
since a one-ply agent scores the board at the end of its own turn and a card whose whole value is
what the *rival* cannot do next turn is invisible to it by construction.

`tools/play_rate_compare.py` pairs them: the same decks, the same seeds, the same opponents, only
the agent differs. Twelve cards, 600 games per arm, split into three colour-feasible probes because
three Legends cannot cover four colours.

| card | heuristic | ismcts:8 | delta |
|---|---|---|---|
| Reboot Optics | 19.5% | 31.0% | **+11.5pp** |
| Adam Smasher — Metal Over Meat | 19.8% | 28.7% | **+8.9pp** |
| Appetite for Destruction | 6.3% | 9.7% | +3.5pp |
| Sandevistan | 21.8% | 25.6% | +3.8pp (n.s.) |
| Chrome Reverie | 8.0% | 9.6% | +1.6pp (n.s.) |
| We Gotta Live Together | 8.0% | 8.5% | n.s. |
| Safety Override | 6.6% | 6.2% | n.s. |
| Take Control | 12.9% | 11.6% | n.s. |
| Cyberpsychosis | 8.7% | 7.2% | n.s. |
| Unlikely Bond | 7.8% | 4.2% | **−3.6pp** |
| Bootleg Black Sapphire Show | 12.7% | 2.3% | **−10.5pp** |
| Gunpoint Diplomacy | 19.6% | 5.5% | **−14.1pp** |

The headline is a negative, and it is the one worth having. **Chrome Reverie is not rescued by
search.** It is the card the opponent-reading module was written around, the card whose strategy
note calls it the answer to a rival winning on one attacker, and the searching agent plays it no
more often than the greedy one does. Whatever its 2.6% play rate in the coverage sweep means, it is
not simply that a one-ply evaluator cannot see it.

The two largest disagreements come with a caveat that is more interesting than the numbers.
**Reboot Optics and Gunpoint Diplomacy both have open audit findings**, and both findings say the
card currently behaves more broadly than it prints — the Optics shield is consumed only by a fight
it actually saves a Unit from, so one Program covers every later fight that turn; the Diplomacy
grant is written as an until-end-of-turn modifier where the card says "the next time this Unit
attacks this turn". Those play rates are measurements of the bug, not of the card, for both agents.
They have to be re-measured after the fixes land, and until then the right reading of the ±11 and
±14 point gaps is "the two agents disagree about a card that is not yet the printed card".


## What the verification pass actually returned

Twenty-four findings, forty-eight agents, two per finding. Every one of the twenty-four came back
with both legs run.

| | |
|---|---|
| survives | 23 |
| killed | 1 |
| blind reader independently found an error | 21 of 24 |
| tests judged sound (printed-text outcome, reachable board) | 23 of 24 |

Class: 17 scope-or-condition, 4 missing-clause, 1 wrong-effect, 1 genuinely ambiguous, 1 false
positive.

**The three cases where the blind reader found nothing are the interesting ones, and they are
exactly the three you would want.** Two are Chrome Fang and Westbrook Netrunner — the prohibition
blind spot described above, where the bug lives in a card the reader was never shown. The third is
the one real false positive, and the blind reader agreeing with the killer there is the
anti-anchoring leg doing precisely its job: it saw the card, found it faithful, and said so.

**The false positive.** Kiroshi Optics prints "(Equip to a Unit or friendly face-up Legend.)" where
the other nine Gear print "(Equip to a **friendly** Unit or face-up Legend.)", and the finding read
the difference as permission to equip a rival's Unit. Killed on the parse: taking "friendly" as
conjunct-local on Kiroshi but as distributing on the other nine is inconsistent, and the
conjunct-local reading would also let those nine equip a *rival* face-up Legend, which nobody filed
and nobody believes. `docs/rules.md` fixes the template as "a friendly Unit or Legend", and seven
Gear print no equip line at all yet host identically — the parenthetical is reminder text, and
reminder text nowhere in this set grants an exception. The withdrawn finding leaves a passing test
behind rather than nothing, which is the right residue.

What it also leaves is a **transcription doubt**: Kiroshi's word order differs from every sibling,
which is what a slip looks like rather than a design decision. Settling it needs the card face, so
it is recorded rather than guessed at.

**The ambiguity.** Goro Takemura — Losing His Way reads "If all friendly Legends are face-up" and
the engine additionally requires at least one. With an empty Legends area — reachable, and
deck-legal — "all" over an empty set is vacuously true on one reading and unsatisfied on the other.
Both defensible; the card does not say. It is `docs/rulings.md` row 042, **Uncertain**, left as the
engine has it, with the failing test for the other reading still in place. Ruling 038 (Street Cred
with no Gigs is *null*, not 0) is the nearest precedent and leans against the vacuous reading, which
is why the engine's behaviour is the one left standing rather than the filer's.
