<!-- Working record for AUD-afterparty-at-lizzies-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Afterparty at Lizzie's  (`afterparty-at-lizzies`)

- type: PROGRAM, colour: YELLOW, cost: 1, power: None, RAM: 1
- keywords: none
- tags: ['BRAINDANCE', 'MOX']

## Printed text (byte-exact from data/cards/wnc.json)

```
Adjust a Gig by up to 1. If you control 2 or more Gigs with different values, draw 1.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 337-346

@script("afterparty-at-lizzies")
def _():
    def play(c):
        def after(c2, _o, _i):
            if len(set(c2.gig_values())) >= 2:
                c2.draw(1)
        c.adjust_up_to([c.player, c.rival], -1, 1, cont=after)
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-afterparty-at-lizzies-1

card: `afterparty-at-lizzies`

claim: the draw is nested in the adjust continuation, so declining the 'up to 1' (or having no legal adjustment) skips the separate different-values draw clause

failing test: `tests/cards/audit/test_a04.py::test_afterparty_draws_when_the_adjust_is_declined`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Afterparty at Lizzie's (`afterparty-at-lizzies`)

Printed text (byte-exact):

> Adjust a Gig by up to 1. If you control 2 or more Gigs with different values, draw 1.

Implementation, `src/cptcg/cards/sets/wnc.py:337-346`:

```python
@script("afterparty-at-lizzies")
def _():
    def play(c):
        def after(c2, _o, _i):
            if len(set(c2.gig_values())) >= 2:
                c2.draw(1)
        c.adjust_up_to([c.player, c.rival], -1, 1, cont=after)
    return CardScript(on_play=play)
```

Type is PROGRAM with no printed timing keyword, so the whole text resolves on play; `on_play`
is the right hook (rules.md "Program — instantaneous. Pay its cost, resolve the effect, move it
to the trash").

## 1. "Adjust a Gig ..." — one Gig, either player's

Requires: exactly one Gig is affected, and "a Gig" is unscoped, so either player's Gig is a legal
choice. rules.md does not define a default scope; the set's own usage settles it — Jackie Welles
says "a **friendly** Gig" and is scripted `adjust_up_to([c.player], ...)` (wnc.py:1370), while every
unscoped "adjust/increase/decrease a Gig" is scripted over both owners (Kiroshi Optics carries an
explicit comment to that effect at wnc.py:940-947).

Implemented by `c.adjust_up_to([c.player, c.rival], -1, 1, ...)`. `EffectCtx.adjust_up_to`
(effects.py:355-379) builds candidate `(owner, index, amount)` triples over the owners given and
asks a single `choose`, so exactly one Gig is adjusted. **Matches.**

## 2. "... by up to 1" — magnitude at most 1, either direction, and 0 allowed

Requires: "adjust" is direction-agnostic (contrast "increase"/"decrease" elsewhere in the set), so
-1 or +1; "up to" permits choosing 0 (do nothing); an amount that would take the die off its face
is not a legal choice (ruling 037 / CR 6.4.4).

`adjust_up_to(..., lo=-1, hi=1)` enumerates `a in {-1, +1}` (a != 0 is filtered out of the value
list) and keeps only triples with `1 <= v + a <= k`, so off-face amounts are never offered; the
zero case is the decline option added by `choose(..., optional=True)`. `ops.adjust_gig`
(ops.py:484-495) re-checks the face bound and re-checks that the die has not moved. Sibling cards
use the identical mapping (`-3..-1` for "decrease by up to 3", `1..4` for "increase by up to 4",
`-1..1` for Zetatech Faceplate's "adjust a Gig by up to 1"). **Matches.**

## 3. "If you control 2 or more Gigs with different values" — the condition

Requires: look at the Gigs *you* control, after the adjustment; the condition holds iff there exist
at least two of your Gigs whose values differ — equivalently, iff your Gigs show at least 2 distinct
values.

`c2.gig_values()` defaults to `self.player` (effects.py:106-110), i.e. the controller of this card
(`EffectCtx.player = s.i_owner[inst]`), so the rival's Gigs are correctly excluded even when the
Gig that was adjusted belonged to the rival. `len(set(...)) >= 2` is exactly "at least 2 distinct
values". Ordering is right: the check runs inside the continuation, i.e. after `adjust_gig` has
applied. The parallel card Zetatech Faceplate ("3 or more Gigs with different values") uses
`len(set(...)) >= 3` (wnc.py:1046-1052), so the N -> `>= N` mapping is the set's convention.
**Matches.**

## 4. "draw 1" — who draws, how many

`c2.draw(1)` with no player argument draws for `self.player`, the card's controller
(effects.py:221-222). One card. **Matches.**

## 5. Is the second sentence conditional on the first having happened?

Requires: the second sentence is a separate, state-based sentence. It is *not* joined by "Then,"
— and this set does use "Then," deliberately when it means dependence (Trust No One: "Decrease a
Gig by up to 3. **Then,** if you control a min Gig, draw 1."; Zetatech Faceplate: "... **Then,** if
you control 3 or more Gigs ..."). Since "up to 1" expressly allows adjusting by 0, a player who
declines the adjustment has still finished the first sentence legally, and the second sentence
should then be evaluated on the current board: if they already control 2+ Gigs with different
values, they draw 1.

Implemented as `cont=after`. `adjust_up_to` passes the continuation into
`choose(..., optional=True)`, and `choose._cont` only calls `cont` when the answer carries a pick;
on the decline option (`Pick(())`) it calls `otherwise`, which `adjust_up_to` never supplies
(effects.py:165-173, 355-379). It also returns without running anything when the candidate list is
empty. So the draw check is reachable **only** when a Gig was actually adjusted.

**Does not match.** Concretely: you control (d4,2) and (d6,5), the rival controls nothing, and you
play this card. Two distinct values are already on the board, so the second sentence is satisfied
no matter what. The printed card draws 1 whichever amount you pick, 0 included; the script draws
only if you pick -1 or +1, and declining (the correct play whenever any ±1 would hurt you — e.g.
you need your Street Cred parity unchanged for another card, and there is no rival Gig to shrink)
silently loses the draw. The "no legal option" variant of the same trap is unreachable here: the
candidate list is empty only when neither player has a Gig, in which case the condition is false
anyway.

## Verdict

Clauses 1-4 are faithful, including the side each half applies to (adjust: either player's Gig;
condition and draw: yours), the ±1 range, the zero option, and the post-adjustment timing of the
check. The one discrepancy is clause 5: the state-based tail clause is trapped inside the
continuation of the "up to" choice, so declining the adjustment — a legal way to resolve "by up to
1" — skips the draw entirely.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-afterparty-at-lizzies-1 — verification (attempted kill)

Verdict: **survives** (B4 scope-or-condition). I tried all five kill routes; none of them closes.

## What the card prints

`data/cards/wnc.json`, card 65:

> "Adjust a Gig by up to 1. If you control 2 or more Gigs with different values, draw 1."

Two sentences. The second one's condition is **"if you control 2 or more Gigs with different
values"** — a board state read on your own Gig area. It does not say "if **it** becomes ...",
it does not say "if you do", and it is not joined to the first sentence by "then" or "if you do".
So the draw is gated on the board, not on a die having moved.

## The implementation

`src/cptcg/cards/sets/wnc.py:347-355`

```python
def play(c):
    def after(c2, _o, _i):
        if len(set(c2.gig_values())) >= 2:
            c2.draw(1)
    c.adjust_up_to([c.player, c.rival], -1, 1, cont=after)
```

The locally-named `after` is passed as **`cont=`**, not `after=`. Those are different hooks.

## Route 1 — a ruling deliberately covers it? No.

I read all 41 rows of `docs/rulings.md`. Nothing covers clause sequencing after an "up to"
adjust, and none of the usual suspects (012, 015, 019, 025, 026, 030) is anywhere near this card.
The only relevant row, **037**, cuts the other way: "Adjusting a Gig ... to the value it already
has — **the effect fails**, no change. 'Up to N' effects let you pick a legal amount." That row
confirms 'up to N' has a legal zero/no-op branch, which is exactly the branch where the draw is
being lost.

## Route 2 — the engine already handles it? No — and it documents this exact bug.

`src/cptcg/core/effects.py:364-400`, the docstring of `adjust_up_to` itself:

> "``cont(ctx, owner, index)`` runs **only when a die actually moved**, and is right for a clause
> that talks about *that* Gig ... ``after(ctx)`` runs **whatever happens** — after the adjustment,
> after a decline, and when no legal adjustment existed to offer — and is right for a separate
> printed sentence with its own board condition. ... Getting that backwards is invisible and
> common ... a second sentence hung off ``cont`` silently never runs. **Six cards in this set were
> written that way.**"

The code path confirms it: in `adjust_up_to`, `cont` is called only inside the branch that first
calls `c.adjust_gig(...)` (effects.py:392-395), and the decline route is `self.choose(...,
optional=True, otherwise=after, ...)` (effects.py:399) where `after` is `None` here — so declining
resolves to nothing at all. `choose` (effects.py:156-160) likewise runs only `otherwise` when the
candidate list is empty, so a board with no legal ±1 also drops the draw. I checked `core/ops.py`,
`core/steps.py` and `core/legal.py` for any compensating re-check of the second sentence: there is
none; the whole clause lives in this script.

## Route 3 — unreachable board? No.

`tests/conftest.py:75-102` `board()` builds an ordinary turn-3 main phase: player 0 with a d6
showing 3 and a d8 showing 4 in the Gig area, 9 Eddies, the Program in hand, one card in deck.
Two Gigs of different kinds and faces by turn 3 is the normal result of rolling a die into your
Gig area each Start Phase; nothing here needs an illegal state.

## Route 4 — asserts an internal? No.

The test asserts `s.gig[0] == [(6, 3), (8, 4)]` (printed die faces unchanged) and
`len(s.zone(0, Zone.HAND)) == 1` (a card was drawn). Both are printed-text outcomes. No script
internals, no hook names, no tags.

## Route 5 — misreads a word? No.

"by up to 1" includes 0, and the engine itself offers the decline option (`optional=True` at
effects.py:399), which is what `Pick(())` takes in the test. The second sentence's subject is
"you control ... Gigs", not the adjusted Gig, and `gig_values()` with no argument already reads
the controller's own Gigs (effects.py:109-110) — so the condition the script computes is the right
one; only its trigger point is wrong.

## Observed behaviour

`python -m pytest 'tests/cards/audit/test_a04.py::test_afterparty_draws_when_the_adjust_is_declined' -q -rx`
→ **XFAIL** (with `--runxfail`: `assert 0 == 1`, hand empty). Declining the adjust on a board with
Gigs at 3 and 4 draws nothing, though the player plainly controls 2 or more Gigs with different
values.

## Conclusion

The finding is correct. The fix is one keyword: pass the closure as `after=` instead of `cont=`
(and drop the two unused positional parameters), so the second sentence resolves after an
adjustment, after a decline, and when no legal adjustment exists.
