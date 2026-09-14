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
