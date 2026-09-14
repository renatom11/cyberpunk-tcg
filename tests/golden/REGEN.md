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

---

## 2026-09-14 — `afterparty-at-lizzies` (AUD-afterparty-at-lizzies-1)

**The fix.** "Adjust a Gig by up to 1. **If you control 2 or more Gigs with different values, draw
1.**" Two Gigs showing 3 and 4 are two Gigs with different values whether or not a die moved, and
"up to 1" includes zero — the engine offers the decline explicitly. Moved to `after=`.

**1. Prediction.** Four keys. Observed: two, both `random`.
**2. Localisation.** decisions 47 and 25, card first a legal option at 4 and earlier.
**3. Revert confirmation.** DIFFERENT on exactly those two keys at exactly those actions.
**4. Aggregate.** 4 of 40 and 1 of 40, one winner flip, no end-reason changes, turn deltas +0.25 and
0.00. Both heuristic keys unmoved.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `el-sombreron-la-venganza-lenta` (AUD-el-sombreron-la-venganza-lenta-1)

**The fix.** "ATTACK: You may pay 2 €$. If you do, this Unit gains power equal to a friendly **max
Gig** this turn." A max Gig is a die showing its maximum face — the mirror of "min Gig", which six
cards in this set use and which `EffectCtx.min_gigs` implements exactly that way. The script used
`max(gig_values())`, the largest *value* in the area, so a d12 on 9 beside a d4 on 4 gave +9 where
the card gives +4. `EffectCtx.max_gigs` already existed and was unused.

A pre-existing green test encoded the bug — a d12 on 9 expecting +9 — which is why no one noticed.
It now uses a real max Gig, and a control beside it shows the card does not even ask when there is
none.

**1. Prediction.** Two keys. Observed: both.
**2. Localisation.** decisions 146 and 62; the card first a legal option at 80 and earlier, and the
narration shows it attacking one line before.
**3. Revert confirmation.** DIFFERENT on exactly those two keys at exactly those actions.
**4. Aggregate.** 3 of 16 and 1 of 40 games, no winner flips, no end-reason changes, turn deltas
0.00. A pure power-number change on one Unit in one deck: the games stay the same games.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `sketchy-ripper` (AUD-sketchy-ripper-1)

**The fix.** "ATTACK: Search the top 3 cards of your deck. **Reveal a Gear and add it to your
hand.** Bottom-deck the rest." No "may", and Sasha Yakovleva's identical verb phrase is already
scripted as mandatory. The search ran with a lower bound of zero, so the engine offered a decline.
`lo=1` is safe with no Gear in the top three: `choose_many` clamps hi to the candidates available
and then lo to hi, so the search resolves with an empty pick and still bottom-decks all three — a
control test pins that.

A pre-existing green test answered the Pick that only existed because of the bug. It now asserts
that nothing is asked, which is the printed behaviour.

**1. Prediction.** Two keys. Observed: both.
**2. Localisation.** decisions 114 and 82; card first a legal option at 41 and earlier.
**3. Revert confirmation.** DIFFERENT on exactly those two keys at exactly those actions.
**4. Aggregate.** 4 of 16 and 13 of 40 games, two winner flips, three end-reason changes, turn
deltas 0.00 and +0.54. A third of the random games is a large share and an expected one: removing a
decision from an ATTACK trigger shifts every index after it in any game where the Unit attacks, and
random attacks with it often.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `zetatech-faceplate` (AUD-zetatech-faceplate-1) — the last of the six

**The fix.** "When this Unit or Legend is spent, adjust a Gig by up to 1. **Then, if you control 3
or more Gigs with different values, draw 1.**" The sixth and last card written with its tail clause
inside the first clause's continuation. `tests/cards/test_script_lints.py::test_a_state_based_tail_clause_is_not_trapped_in_a_continuation`
goes green with this one, which is what the whole detector was for.

**The lint needed teaching first.** It flagged Peace Offering after that card was fixed, because
Peace Offering's tail *has* to live inside a continuation — its set is two nested questions, so the
tail belongs on the inner one. The lint now distinguishes the slot a continuation is passed into:
`cont=`/`then=` run only if the prompt was answered, `after=`/`otherwise=` run whatever happens. A
clause in the second kind is sequenced, not trapped.

**The test needed strengthening too**, and this is the sharper lesson. Its first assertion said the
Gig area was unchanged — but the attack that spends the host also *steals*, so the test had been
failing on the steal rather than on the missing draw. A strict xfail proves a test fails; it does
not prove it fails for the reason in its reason string. The board now attacks a spent rival Unit
instead, and the test fails, and now passes, for the clause it names.

**1. Prediction.** Two keys. Observed: one.
**2. Localisation.** decision 89; the Gear first a legal option at 32.
**3. Revert confirmation.** DIFFERENT on exactly that key.
**4. Aggregate.** 3 of 40 games, no winner flips, no end-reason changes, turn delta 0.00.
**5. Two-sided reachability.** Not applicable at G1.

## 2026-09-14 — `dying-night-vs-pistol` (AUD-dying-night-vs-pistol-1)

**The fix.** "At the end of your turn, if this Unit is named "V", ready 2 Eddies." The clause tested
the host's *name* and nothing else, so the Gear paid out while sitting on a face-up V in the Legends
area — which is not a Unit. The gate is now the host's zone, so a V that has GONE SOLO onto the
field keeps paying (ruling 015) and a Called one does not.

**1. Prediction.** Four keys may change: `the_heist` and `sample_corpos` are the two golden decks
holding the card, in one matchup each, heuristic and random. Observed: two, both of them random.
Observed ⊂ predicted.

**2. Localisation.** `sample_corpos~sample_nomads~random` game 3 diverges at decision 23, and the
narration of the game the *current* engine plays shows the cause outright: eight decisions earlier,
sample_corpos "plays Dying Night — V's Pistol (Gear) on V — Corporate Exile" — a Legend in the
Legends area, the exact board the fix changes. `the_heist~embracing_power~random` game 13 diverges
at 26 with the card first a legal option at 10.

**3. Revert confirmation.** Old script against the new golden: DIFFERENT on exactly those two keys,
same games, same action numbers.

**4. Aggregate.** 2 of 40 and 1 of 40 games, no winner flips, one end-reason change, mean turn delta
+0.50 and +0.00. An Eddie source removed from a board where a Legend hosted the Gear shifts a turn
and rarely more; nothing here is unexplainable.

**5. Two-sided reachability.** Not required at G1, but recorded: `fuzz --agent random -n 400
--seed 1` moves c0f43d0ac9ccbc54221d480d → 3b4932720efc3f3b2354f268 and the default heuristic fuzz
digest is 8a1e68700fe9fd617d05d0df.

## 2026-09-14 — `reboot-optics` (AUD-reboot-optics-1)

**The fix.** "The next time a rival Unit fights this turn, it doesn't defeat the opposing friendly
Unit." The shield was consumed only by a fight it actually saved a Unit from, so a rival Unit that
fought and lost — or tied, or was already barred from defeating anything by CR 9.19.2 — left it
standing for every later fight that turn. The fight is the trigger; the shield is spent by it either
way. The edit is in `steps.fight`, but `next_fight_no_defeat` is written by this card alone and read
only there, so the deck-membership prediction still applies.

**1. Prediction.** Four keys: `sample_arasaka` and `the_heist` hold the card. Observed: one.

**2. Localisation.** `sample_arasaka~sample_fixers~random` game 20 at decision 114; the Program was
first a legal option at 95. The window shows a fight resolving at Sketchy Ripper 0 against Ruthless
Lowlife 6 — a 0-power attacker that cannot defeat anything under CR 9.19.2, which is precisely the
fight that used to leave the shield unspent.

**3. Revert confirmation.** Old `steps.py` against the new golden: DIFFERENT on that one key, same
game, same action.

**4. Aggregate.** 1 of 40 games, no winner flips, no end-reason change, mean turn delta −1.00: one
game ended a turn earlier, which is what a Unit dying when it should have is worth.

**5. Two-sided reachability.** Not required at G1 reach. The card-level test is the evidence, and it
now pins both halves — the first fight spends the shield even though it protected nobody, and the
second fight kills the Unit that used to be saved.

## 2026-09-14 — `mox-inciters` / `evelyn-parker-beautiful-enigma` (AUD-mox-inciters-1)

**The fix.** "A rival Unit must attack next turn if it can." Two cards wrote the `must_attack` mod
and nothing in `src/` read it, so the obligation was bookkeeping. `legal.main_menu` now drops
EndTurn while an obligated Unit can attack. G2 by file and unlocalisable by construction: a card
script cannot remove an option from a menu the engine builds.

**1. Prediction.** Four keys — `sample_gangers` holds Mox Inciters, `sample_fixers` holds Evelyn
Parker. Observed: all four, and nothing else.

**2. Localisation.** `sample_arasaka~sample_fixers~heuristic` game 4 diverges at decision 157, and
the line immediately before it is `sample_fixers activates Evelyn Parker — Beautiful Enigma: A rival
Unit must attack`. The rival's next turn then opens with an attack. The other three keys diverge in
the forties, where Mox Inciters lands early.

**3. Revert confirmation.** Old `legal.py` against the new golden: DIFFERENT on exactly those four
keys.

**4. Aggregate.** 22/40 and 24/40 random games, 2/16 and 12/16 heuristic games, ten winner flips,
turn deltas +0.00 to +0.32. Much the largest regeneration in this ledger, and the size is the point:
an obligation that was inert on two cards across two golden decks changes every game in which either
card is played, and removing an option renumbers every index after it. An unchanged golden here
would have meant the fix did nothing.

**5. Two-sided reachability.** `fuzz --agent random -n 400 --seed 1` moves
3b4932720efc3f3b2354f268 → 739dfb303644a4bcbad64a06 (32335 → 32481 actions) and the default
heuristic fuzz moves 8a1e68700fe9fd617d05d0df → 399958ef4d06ba064c0411b6 (8601 → 8634). Both
instruments see it, which no other fix in this ledger has managed.

## 2026-09-14 — `alt-cunningham-soulkiller-architect` (AUD-alt-cunningham-soulkiller-architect-1)

**The fix.** "⊡: Your next Program this turn plays for -1 €$ for each friendly min Gig, to a minimum
of 1 €$." A `legal=` guard the card does not print made the ability unavailable with no min Gig, so
the Legend could not be spent at all. Deleting the guard restores an activation whose discount is
zero — and whose ⊡ is worth paying when something watches for the spend.

**1. Prediction.** Two keys: `sample_gangers` is the only golden deck holding the card. Observed:
both.

**2. Localisation.** `sample_gangers~sample_netrunners~heuristic` game 1 at decision 76, with the
card a legal option from decision 9; the random key diverges at 20. The narration around the
heuristic divergence shows sample_gangers activating a *different* Legend's ability in the same
window — the frozen agent's arithmetic over an enlarged menu, which is what adding a legal action to
every turn does.

**3. Revert confirmation.** The guard restored against the new golden: DIFFERENT on exactly those
two keys, same games, same actions.

**4. Aggregate.** 13 of 16 heuristic games and 28 of 40 random ones, 10 winner flips in the random
key, turn deltas −0.38 and +0.18. Large for one card, and the mechanism is the one the ledger has
seen before with Unlikely Bond: a new option in the main menu renumbers every action index after it,
so a key diverges as soon as the card is *on the board*, not when it is used.

**5. Two-sided reachability.** Not required at G1; recorded anyway — `fuzz --agent random -n 400
--seed 1` moves 5e97831a765d264cbf2bd32c → 57d2e94a287e533545144a7f, 32,561 → 32,633 actions, which
is this fix alone (Kerry's had already been taken).
