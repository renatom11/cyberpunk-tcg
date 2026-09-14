<!-- Working record for AUD-trust-no-one-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Trust No One  (`trust-no-one`)

- type: PROGRAM, colour: BLUE, cost: 1, power: None, RAM: 1
- keywords: none
- tags: ['BRAINDANCE']

## Printed text (byte-exact from data/cards/wnc.json)

```
Decrease a Gig by up to 3. Then, if you control a min Gig, draw 1.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 357-366

@script("trust-no-one")
def _():
    def play(c):
        def after(c2, _o, _i):
            if c2.min_gigs():
                c2.draw(1)
        c.adjust_up_to([c.player, c.rival], -3, -1, cont=after, prompt="Decrease a Gig")
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-trust-no-one-1

card: `trust-no-one`

claim: the draw is nested in the adjust continuation, so when no decrease is legal the separate min-Gig draw clause never runs

failing test: `tests/cards/audit/test_a04.py::test_trust_no_one_draws_when_no_gig_can_be_decreased`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Trust No One (`trust-no-one`)

Printed text (byte-exact):

```
Decrease a Gig by up to 3. Then, if you control a min Gig, draw 1.
```

Implementation (`src/cptcg/cards/sets/wnc.py` lines 357-366):

```python
@script("trust-no-one")
def _():
    def play(c):
        def after(c2, _o, _i):
            if c2.min_gigs():
                c2.draw(1)
        c.adjust_up_to([c.player, c.rival], -3, -1, cont=after, prompt="Decrease a Gig")
    return CardScript(on_play=play)
```

Helpers read: `EffectCtx.adjust_up_to`, `EffectCtx.choose`, `EffectCtx.min_gigs`,
`EffectCtx.draw` (`src/cptcg/core/effects.py`), `ops.adjust_gig` (`src/cptcg/core/ops.py`).

---

## 1. Timing: this is a PROGRAM with no timing label — the whole text resolves on play

**Text requires:** a costed Blue Program with no `PLAY:` / `ATTACK:` label resolves its text when
played, once.

**Implementation:** `CardScript(on_play=play)`, the single hook. No other hooks, no `once` gate.

**Verdict: match.**

## 2. "Decrease a Gig" — which Gig, and whose

**Text requires:** *one* Gig ("a Gig", not "all Gigs"), unqualified as to controller. The pool's
convention is that restricted targeting is printed: Jackie Welles prints "decrease a **friendly**
Gig", El Sombreron "a **friendly** max Gig", Three Mouths One Desire "each **friendly** min Gig".
An unqualified "a Gig" therefore means any Gig in either Gig area — the same reading used by
Industrial Assembly ("Increase a Gig by up to 4") and Afterparty at Lizzie's ("Adjust a Gig by up
to 1"), both of which pass `[c.player, c.rival]`.

**Implementation:** `adjust_up_to([c.player, c.rival], ...)` builds candidates as
`(owner, index, amount)` triples over both players' dice and asks one `choose`, which resolves
exactly one triple and calls `c.adjust_gig(o, i, a)` once.

**Verdict: match** — one Gig, either side.

## 3. "by up to 3" — the legal amounts

**Text requires:** a decrease of 1, 2 or 3 (decrease, so never an increase), and "up to N" also
admits 0 — i.e. the player may decline. Ruling 037 (CR 6.4.4/6.4.5): an adjustment to a value not
on the die's face simply fails, and "'Up to N' effects let you pick a legal amount", so the offer
must be limited to amounts that leave the die on a real face (>= 1).

**Implementation:** `for a in range(lo, hi + 1)` with `lo=-3, hi=-1` yields exactly `-3, -2, -1`;
each candidate is kept only if `a != 0 and 1 <= v + a <= k`. `choose(..., optional=True)` adds a
decline option, which is the "up to N includes 0" case. `ops.adjust_gig` re-checks
`1 <= value + delta <= sides` under `set_gig_off_face_fails` and re-validates the die
(`gigs[i] != (k, v)` guard in `_do`) in case it moved between question and answer.

**Verdict: match.**

## 4. "Then, if you control a min Gig" — the condition, its subject, and when it is checked

**Text requires:** after the first sentence has resolved, check a *board* condition — do **you**
(the card's controller, not the Rival) control a Gig showing its minimum face (1)? Two things
matter here:

- The subject of the condition is "**you control**", i.e. the state of the board at that moment.
  It is *not* "if it becomes a min Gig" (the shape Jackie Welles prints, which is genuinely about
  the die just decreased). Nothing in the sentence makes it contingent on a decrease having
  actually happened. "Then" is sequencing — check after the first sentence — not causation.
- Because "by up to 3" legally includes 0, declining the decrease is a *complete* performance of
  the first sentence, not a failure to perform it. The second sentence must still be checked.
  The same holds when no legal decrease exists at all (e.g. every die on the board already shows
  1 — precisely the case where you *do* control a min Gig): the first sentence does as much as it
  can, and the board check still happens.

**Implementation:** the draw lives in `after`, which is passed as `cont=` to `adjust_up_to`.
`cont` is invoked only from inside `_do`, the branch `choose` takes when a candidate triple is
actually picked:

- decline (`Pick(())`) → `_cont` falls to `elif otherwise is not None:`; `adjust_up_to` passes no
  `otherwise`, so **nothing runs** and the min-Gig check never happens;
- empty candidate list → `choose` returns early at `if not vals:` with `otherwise is None`, so
  again **nothing runs**;
- the stale-die guard inside `_do` (`if i >= len(gigs) or gigs[i] != (k, v): return`) also skips
  `cont`.

So the script implements the second sentence as conditional on a decrease having been *performed*,
not on the board state.

**Verdict: MISMATCH.** The condition itself is read correctly (`min_gigs()` with the default
`player=None` resolves to `self.player`, the controller, and returns indices of dice with
`v == 1`, i.e. the minimum face — correct on both subject and meaning). The defect is the
*gating*: a printed board-state condition is trapped inside the continuation of the previous
sentence. Concretely — you control a d6 showing 1 and a d20 showing 14, the Rival's only die shows
1. You play Trust No One and decline the decrease (or, with every die on the board at 1, are never
even asked). You control a min Gig, so the card says draw 1; the script draws nothing.

## 5. "draw 1"

**Text requires:** the controller draws exactly one card.

**Implementation:** `c2.draw(1)` → `ops.draw(s, self.player, 1)` — controller, one card.

**Verdict: match** (conditional on §4 running at all).

---

## Conclusion

One discrepancy. Clauses 1-3 and 5 are faithful; the targeting (both Gig areas), the amount range,
the face-legality clamp, the "you"-scoped min-Gig test and the draw size are all right. The second
sentence is a board-state condition that the printed text checks unconditionally after the first
sentence resolves, and the script only checks it when a die was actually decreased — so declining
the (legally zero-inclusive) "up to 3", or having no legal decrease, silently drops the draw.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-trust-no-one-1 — kill attempt: FAILED (finding survives)

Card text (byte-exact, `data/cards/wnc.json` #139):
`Decrease a Gig by up to 3. Then, if you control a min Gig, draw 1.`

Implementation, `src/cptcg/cards/sets/wnc.py:357-366`: the draw is hung off `cont=after`
in `c.adjust_up_to([c.player, c.rival], -3, -1, cont=after, prompt="Decrease a Gig")`.

## The five kill routes, each tried

1. **A ruling covers it.** No. I read every row of `docs/rulings.md` (001-041). None of
   012/015/019/025/026/030 touches Gig adjustment or clause sequencing. The only relevant row,
   **037** ("Adjusting a Gig to a value not on its face, or to the value it already has — the
   effect fails, no change; CR 6.4.4, 6.4.5"), *supports* the filer: a d4 already showing 1 has no
   legal decrease, so the first sentence does nothing — and 037 says the *adjustment* fails, not
   that the rest of the card is skipped. Nothing in `docs/rules.md` says an instruction that
   cannot be performed aborts the remainder of the card (grepped for "fails", "impossible",
   "cannot be performed", "as much as possible" — no hits).

2. **The engine already handles it.** No — and the engine's own documentation says the opposite.
   `EffectCtx.adjust_up_to` (`src/cptcg/core/effects.py:364-401`) takes two hooks and its
   docstring distinguishes them in exactly this case:

   > ``cont(ctx, owner, index)`` runs only when a die actually moved, and is right for a clause
   > that talks about *that* Gig ("If **it** becomes a min Gig, draw 1"). ``after(ctx)`` runs
   > whatever happens — after the adjustment, after a decline, and when no legal adjustment
   > existed to offer — and is right for a separate printed sentence with its own board condition
   > ("Then, **if you control** a min Gig, draw 1").

   That second example is this card's second sentence, quoted verbatim. In the code path, `cands`
   is built only from `a != 0 and 1 <= v + a <= k`; with a lone d4 at 1 the list is empty, and
   `self.choose(..., optional=True, otherwise=after, ...)` is called with `after=None`, so nothing
   runs. Nothing in `core/ops.py`, `core/steps.py` or `core/legal.py` compensates. Confirmed
   empirically: the test reports **XFAIL** (strict), i.e. it fails exactly as filed.

3. **Unreachable board.** No. `board(pool, Side(hand=["trust-no-one"], eddies=9, gig=[(4, 1)],
   deck=["floor-it"]), Side())` is a d4 in the Gig area showing 1. Dice are `DICE = (4, 6, 8, 10,
   12, 20)` (`core/enums.py:58`) and `docs/rules.md` has you roll a die out of the fixer into the
   Gig area each turn — a d4 rolling a 1 is an ordinary turn-3 board. The only cosmetic artifact
   is the helper's default full fixer, which is irrelevant to the effect and to every assertion.

4. **Asserts an internal.** No. The test asserts `s.gig[0] == [(4, 1)]` (die values) and
   `len(s.zone(0, Zone.HAND)) == 1` (hand size). Both are printed-text outcomes; no script
   internals, no hook names.

5. **Misreads the text.** No, on either word that could carry the kill.
   - *"Then"* sequences the clauses; the dependency template would be "if you do". The sentence's
     own condition is spelled out and is a **board check** — "if you **control** a min Gig" — not
     "if it becomes a min Gig". Nothing was made contingent on a die having moved.
   - *"min Gig"* holds under every available reading: `EffectCtx.min_gigs`
     (`core/effects.py:120`) is `v == 1`, and a d4 showing 1 is also trivially the minimum among
     the player's Gigs. `docs/rules.md` has no competing glossary entry.

## Conclusion

The finding stands. The script gates a separate printed sentence behind an unprinted condition
(a die actually moved), so with no legal decrease available the draw is silently skipped. The fix
is the one the engine's own docstring prescribes: pass the draw as `after=` rather than `cont=`.
