# Regenerations of `games.json`

`tests/golden/games.json` pins 224 games as exact action-index streams. A real card fix will
legitimately change some of them, and the danger has never been the change — it is regenerating on a
diff nobody localised, which turns "the fix worked" into "the fix, plus whatever else was on the
tree". This file is the ledger, so `git log -- tests/golden/games.json` stays a readable history of
deliberate decisions rather than a list of times the file moved.

Every entry records the five pieces of evidence from `docs/verification.md`. A regeneration without
all five is not one.

---

## 2026-09-14 — `unlikely-bond` (AUD-unlikely-bond-1)

**The fix.** "Bottom-deck a ready friendly Unit. If you do, bottom-deck a spent rival Unit." The
friendly bottom-deck was scripted `optional=True`, manufacturing a decline the card never grants.
Verified first: the blind reader landed on the same clause in the same direction, and the kill
attempt failed on all five routes.

**1. Prediction, written before the change.** `golden_impact.py predict unlikely-bond` → tier G1,
two keys, `sample_gangers~sample_netrunners~{heuristic,random}`. Only `sample_gangers` runs the card
and it runs three copies. Observed: exactly those two keys. Nothing outside the prediction moved.

**2. Localisation.** In the heuristic key the game diverges at decision 138; the card first became a
legal option at decision 130. In the random key, decision 29 against 28 — and there the card is
visibly played in the narration one line before.

This is the entry that corrected the protocol. The rule used to be "the fixed card must appear in
the replay window", and in the heuristic game it never appears: Unlikely Bond was drawn, sat in
hand, and was never cast. The frozen heuristic scores candidate actions by resolving them a ply
deep, so a card that is merely *playable* changes what the agent thinks the board is worth. The rule
is now "a named card must have been an option before the divergence", which is the claim the
evidence can actually support.

It also corrected the instrument. `golden_impact.py` narrated the window by replaying the golden
action indices on the fixed engine, which is unsound: an action index names a position in an option
list, not a move, so removing an option — or removing a whole decision, as dropping `optional=True`
does when `AskStep` then resolves a one-option choice inline — makes every later index mean
something else. The replay kept succeeding and narrated a game that never happened. It now narrates
the game the current engine actually plays.

**3. Revert confirmation.** Script hunk reverted, new golden kept: `check` went DIFFERENT on exactly
those two keys and no others, at exactly actions 138 and 29. The regeneration was taken on a tree
carrying only the intended change.

**4. Aggregate.** heuristic 10/16 games changed, 3 winner flips, 2 end-reason changes, mean turn
delta +0.10. random 1/40 changed, 1 winner flip, mean turn delta −3.00. A three-of Program in one of
the two decks, played by an agent that previews it: a third of the heuristic games touched and
almost none of the random ones is the expected shape, since random rarely assembles the board the
card wants.

**5. Two-sided reachability.** Not applicable at G1 — the golden sees this card directly. (The fuzz
check exists for the 54 cards no golden deck contains.)

---

## 2026-09-14 — `shattered-memories` (AUD-shattered-memories-1)

**The fix.** "Each player discards their hand and **may** draw 5." The script drew for both players
unconditionally, with a comment reading `# "may draw 5": always beneficial, auto`. It is not always
beneficial: `ops.draw` ends the game on an empty deck, so the Program could deck a player out
against their will — and the Rival's "may" is the Rival's to spend, not the controller's to assume.
Both players are now asked. `EffectCtx.maybe` gains the same `after=` hook `adjust_up_to`,
`choose_gig` and `spend_one` have, so the third sentence ("If the total number of discarded cards
equals the value of a friendly Gig, draw 2") is sequenced after both answers without being made
conditional on either.

**1. Prediction.** Tier G1, two keys, `the_heist~embracing_power~{heuristic,random}`. Observed:
exactly those two.

**2. Localisation.** heuristic diverges at decision 17, card first a legal option at 15. random
diverges at 26, first an option at 11.

**3. Revert confirmation.** Script hunk reverted, new golden kept: DIFFERENT on exactly those two
keys, at exactly actions 17 and 26.

**4. Aggregate.** heuristic 9/16 games, 1 winner flip, 1 end-reason change, mean turn delta −0.22.
random 8/40, 2 flips, 2 end-reason changes, −0.62. Turning one unconditional draw into two
questions changes the decision count in every game that plays the card, so a majority of the
heuristic games moving is expected; the small turn deltas say the games are otherwise the same
games.

**5. Two-sided reachability.** Not applicable at G1.

`EffectCtx.maybe` also changed, which is a `core/**` edit and so G2 by the letter of the tier table.
It is additive — no existing caller passes `after` — and the revert in step 3 reverted only the card
hunk, leaving the engine change in place; `check` went DIFFERENT on the two card keys and nothing
else, which is the evidence that the engine change on its own moves nothing.

---

## 2026-09-14 — `peace-offering` (AUD-peace-offering-1)

**The fix.** "You may set a Gig's value to the value of another Gig. **Then, if you control a
value-pair, draw 1.**" The draw was nested inside the set's continuation, so declining the "may" —
or having no second Gig to copy from — skipped a sentence that is about the board rather than about
the set.

**The interesting part is what the first attempt got wrong.** Hanging the tail off the outer
prompt's `after=` hook looked right and produced a passing decline test and a *failing* take test:
with the set taken, no draw happened. `after` runs the moment `cont` returns, and a continuation
returns as soon as it asks a further question — asking pushes a step and comes straight back. Peace
Offering's set is two nested questions, so `after` fired before the die had moved and found no pair.

`after` is therefore for a continuation that finishes synchronously; where `cont` opens another
prompt, the tail belongs on *that* prompt. `choose_gig` gains `otherwise=` for exactly this — the
paths where `cont` did not run — and the limitation is now written into `adjust_up_to`'s docstring,
with this card named as the worked example. The three earlier `after=` uses were re-checked and are
all synchronous continuations.

**1. Prediction.** Tier G1, two keys. Observed: one of them, `sample_corpos~sample_nomads~random`.
**2. Localisation.** Diverges at decision 37; card first a legal option at 34. The narration shows
it directly: "plays Peace Offering ... declines ... draws a card".
**3. Revert confirmation.** DIFFERENT on exactly that one key at exactly action 37.
**4. Aggregate.** 1 of 40 games, 1 winner flip, 1 end-reason change, mean turn delta −1.00. The
heuristic key did not move at all, which fits: this changes the game only when the set is declined
or impossible, and the heuristic takes it whenever it is offered.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `trust-no-one` (AUD-trust-no-one-1)

**The fix.** "Decrease a Gig by up to 3. **Then, if you control a min Gig, draw 1.**" The draw hung
off `cont`, so a declined "up to 3" — or a Gig already on its minimum face, which cannot be
decreased at all under ruling 037 — skipped it. Moved to `after=`, which is safe here because this
continuation finishes synchronously.

**1. Prediction.** Tier G1, four keys. Observed: two of them, both `random`.
**2. Localisation.** decisions 29 and 12, with the card first a legal option at 4 and earlier.
**3. Revert confirmation.** DIFFERENT on exactly those two keys, at exactly actions 29 and 12.
**4. Aggregate.** 1 of 40 and 3 of 40 games, two winner flips, two end-reason changes. Both
heuristic keys unmoved: the heuristic takes a decrease whenever one is legal, so the changed path —
declined or impossible — is one only random play reaches.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `industrial-assembly` (AUD-industrial-assembly-1)

**The fix.** "Increase a Gig by up to 4. **If you control a Gig with 8+ value, draw 1.**" Same shape
as Trust No One and sharper in one respect: a d10 already showing 10 cannot be raised at all
(ruling 037), so the engine asks nothing and the continuation is never scheduled — and that d10 is
exactly the 8+ Gig the second sentence is asking about.

**1. Prediction.** Tier G1, four keys. Observed: two, both `random`.
**2. Localisation.** decisions 16 and 27, card first a legal option at 4 and earlier.
**3. Revert confirmation.** DIFFERENT on exactly those two keys at exactly those actions.
**4. Aggregate.** 3 of 40 and 1 of 40, no winner flips, one end-reason change. Both heuristic keys
unmoved, same reason as Trust No One: the heuristic takes an increase whenever one is legal.
**5. Two-sided reachability.** Not applicable at G1.
