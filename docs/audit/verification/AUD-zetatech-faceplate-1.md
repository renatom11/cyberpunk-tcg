<!-- Working record for AUD-zetatech-faceplate-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Zetatech Faceplate  (`zetatech-faceplate`)

- type: GEAR, colour: YELLOW, cost: 2, power: 2, RAM: 2
- keywords: none
- tags: ['CYBERWARE', 'ZETATECH']

## Printed text (byte-exact from data/cards/wnc.json)

```
(Equip to a friendly Unit or face-up Legend.)
When this Unit or Legend is spent, adjust a Gig by up to 1. Then, if you control 3 or more Gigs with different values, draw 1.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 1045-1055

@script("zetatech-faceplate")
def _():
    def ev(c, e):
        if _host_spent(c, e):
            def after(c2, _o, _i):
                if len(set(c2.gig_values())) >= 3:
                    c2.draw(1)
            c.adjust_up_to([c.player, c.rival], -1, 1, cont=after)
    return CardScript(on_event=ev, events=frozenset({"spent"}))
```

---

# The finding, and the test that failed

# AUD-zetatech-faceplate-1

card: `zetatech-faceplate`

claim: the draw is nested in the adjust continuation, so declining the 'up to 1' skips the separate different-values draw clause

failing test: `tests/cards/audit/test_lint.py::test_zetatech_faceplate_draws_when_the_adjust_is_declined`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Zetatech Faceplate (`zetatech-faceplate`)

Printed text:

```
(Equip to a friendly Unit or face-up Legend.)
When this Unit or Legend is spent, adjust a Gig by up to 1. Then, if you control 3 or more Gigs with different values, draw 1.
```

Script (`src/cptcg/cards/sets/wnc.py:1045-1055`):

```python
@script("zetatech-faceplate")
def _():
    def ev(c, e):
        if _host_spent(c, e):
            def after(c2, _o, _i):
                if len(set(c2.gig_values())) >= 3:
                    c2.draw(1)
            c.adjust_up_to([c.player, c.rival], -1, 1, cont=after)
    return CardScript(on_event=ev, events=frozenset({"spent"}))
```

## 1. "(Equip to a friendly Unit or face-up Legend.)"

Requires: reminder text for the GEAR type — the card attaches to a friendly Unit or a face-up
friendly Legend. No card-specific behaviour beyond the generic Gear equip rules.

Implementation: nothing in the script; handled by the engine's Gear machinery
(`card.type is GEAR`, `s.i_host`, `EffectCtx.host` at `src/cptcg/core/effects.py:40-42`).
Consistent with every other Gear in the set (all of them rely on `_host_spent`/`c.host()`
rather than restating the equip rule).

Verdict: match (nothing to implement).

## 2. "When this Unit or Legend is spent, ..."

Requires: the trigger fires when the *host* (the Unit or Legend this Gear is equipped to) is
spent — not when any unit is spent, and not when the Gear itself is spent.

Implementation: `events=frozenset({"spent"})` plus
`_host_spent` (`src/cptcg/cards/sets/wnc.py:1020-1021`):

```python
def _host_spent(c, e):
    return e[0] == "spent" and e[1] == c.host()
```

`c.host()` returns `s.i_host[self.inst]`, i.e. the instance this Gear is attached to. So the
trigger is correctly scoped to the host, and to the host only. Unequipped Gear has
`i_host == NO_INST`, which cannot equal a spent instance, so it does not fire off-board.

Verdict: match.

## 3. "adjust a Gig by up to 1"

Requires:
- "a Gig" — singular, exactly one die.
- unscoped ownership: the text does not say "a friendly Gig", so either player's Gig is a legal
  target. Set precedent is explicit about this (see the comment at `wnc.py:940-944`: "'increase
  a Gig' is unscoped here ... only text that says 'a friendly Gig' (Jackie Welles) narrows it").
- "adjust ... by up to 1" — either direction, magnitude 0 or 1; zero is a legal choice, so the
  whole adjustment is optional.
- ruling 037: a die cannot be moved off its face, so +1 on a die already at its max face and -1
  on a die at 1 are not legal picks.

Implementation: `c.adjust_up_to([c.player, c.rival], -1, 1, ...)`
(`src/cptcg/core/effects.py:364-...`). Candidate generation is

```python
for a in range(lo, hi + 1):
    if a != 0 and 1 <= v + a <= k:
```

so deltas are exactly -1 and +1 (0 is excluded from the enumerated list but reappears as the
decline option, since `choose(..., optional=True)`), both owners are offered, face bounds are
respected per ruling 037, and exactly one (owner, index, amount) triple is picked. The
staleness guard (`gigs[i] == (k, v)`) is the standard re-check.

Verdict: match.

## 4. "Then, if you control 3 or more Gigs with different values, draw 1."

Requires:
- This is a **separate printed sentence with its own board condition** ("if you control ...").
  It is not conditional on the adjustment having happened. It must be evaluated after the
  adjustment step resolves, whether or not a die actually moved — including when the player
  declines the "up to 1" (zero is an explicitly legal choice) and when no legal adjustment
  existed at all (e.g. every die on the table is pinned, though with both owners' dice that is
  rare; a single die at 1 on a 1-face die, or a board where every candidate is blocked).
- "you control" — the Gear controller's own Gig area, not the rival's and not both.
- "3 or more Gigs with different values" — at least 3 *distinct* values among the controller's
  dice.
- "draw 1" — the controller draws one card.

Implementation: the continuation

```python
def after(c2, _o, _i):
    if len(set(c2.gig_values())) >= 3:
        c2.draw(1)
```

is passed as **`cont=after`**, not as `after=after`.

Sub-checks that *do* match:
- `c2.gig_values()` with no player argument defaults to `self.player`
  (`effects.py:109-110` → `gigs()` → `self.s.gig[self.player]`), i.e. the controller's own
  dice. Correct side.
- `len(set(...)) >= 3` is "3 or more distinct values". Correct counting.
- `c2.draw(1)` defaults to `self.player`, the controller. Correct.

The wiring, however, is wrong. `adjust_up_to`'s own docstring
(`src/cptcg/core/effects.py:366-381`) draws exactly this distinction:

> ``cont(ctx, owner, index)`` runs only when a die actually moved, and is right for a clause
> that talks about *that* Gig ("If **it** becomes a min Gig, draw 1"). ``after(ctx)`` runs
> whatever happens — after the adjustment, after a decline, and when no legal adjustment
> existed to offer — and is right for a separate printed sentence with its own board condition
> ("Then, **if you control** a min Gig, draw 1").

Zetatech Faceplate's second sentence is verbatim the second shape: "Then, **if you control**
3 or more Gigs with different values, draw 1". It never refers to the adjusted die. It must
therefore hang off `after`.

Because it is passed as `cont`, the mechanics are:
- `_do` only calls `cont` inside the `if i < len(gigs) and gigs[i] == (k, v)` branch, i.e. only
  after a die actually moved;
- `after` is `None`, so the `otherwise=after` argument given to `choose` is `None`. Per
  `choose`'s docstring (`effects.py:148-151`), on a decline — and when `vals` is empty and
  there is nothing to choose — `otherwise` runs, and here that is nothing at all.

Consequences: if the controller declines the adjustment (legal: "up to 1" includes 0), or if
no legal adjustment exists, the "Then, ..." sentence is silently skipped and the draw never
happens, even when the controller does control 3+ differently-valued Gigs. The player is
forced to move a die — possibly a harmful move on their own board, or a helpful one on the
rival's — merely to be allowed to check a condition the card says is checked unconditionally.

Verdict: **mismatch** — the second sentence is made conditional on the first actually
happening, which the printed text does not say. Fix: pass the continuation as
`after=lambda c2: ...` (one-argument signature) instead of `cont=`.

## Summary

Clauses 1-3 are faithful. Clause 4 is mis-wired: the unconditional "Then, if you control ..."
sentence is attached to the did-something hook (`cont`) instead of the always-runs hook
(`after`), so declining the optional adjustment — or having no legal adjustment — suppresses
the draw.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-zetatech-faceplate-1 — attempted kill

**Verdict: the finding SURVIVES.** I tried all five kill routes and every one of them fails.

## What the test actually shows

`python -m pytest 'tests/cards/audit/test_lint.py::test_zetatech_faceplate_draws_when_the_adjust_is_declined' -q -rx`
→ **XFAIL** (strict). The engine currently does not draw when the "up to 1" is declined.

## Route 1 — a ruling covers it: NO

Nothing in `docs/rulings.md` touches tail clauses, "Then" sequencing, or declined "up to N"
adjustments. The only nearby row is **ruling 037** ("Adjusting a Gig to a value not on its face, or
to the value it already has. **The effect fails** — no change… 'Up to N' effects let you pick a
legal amount"), and it cuts *against* the kill: it establishes that the first sentence legitimately
performs no change, which is exactly the path on which the second sentence disappears. Rulings 012,
015, 019, 025, 026, 030 are unrelated (BLOCKER redirect, GO SOLO slot, once-per-turn scope, payment
order, field limit, ⊡ on Gear).

## Route 2 — the engine already handles it: NO

`src/cptcg/core/effects.py:388-432` (`EffectCtx.adjust_up_to`) documents this exact split and then
implements it literally:

```python
def _do(c, t):
    ...
        c.adjust_gig(o, i, a)
        if cont is not None:
            cont(c, o, i)          # only on the path where a die moved
    if after is not None:
        after(c)
self.choose(cands, _do, prompt=prompt, optional=True, otherwise=after, ...)
```

`after` is wired to `otherwise` (the decline / no-legal-candidate path); `cont` is not. The
docstring states it outright: *"``cont(ctx, owner, index)`` runs only when a die actually moved…
``after(ctx)`` runs whatever happens… and is right for a separate printed sentence with its own
board condition ('Then, **if you control** a min Gig, draw 1')… Getting that backwards is invisible
and common… Six cards in this set were written that way."*

Zetatech Faceplate (`src/cptcg/cards/sets/wnc.py:1130-1138`) passes the draw as `cont=after`, so it
is on the die-moved path only. Nothing in `core/ops.py`, `core/steps.py` or `core/legal.py` re-runs
a declined choice's continuation — `choose`'s decline path calls `otherwise` and nothing else
(`effects.py:144-176`).

The set itself already fixed three identical cards with `after=`, each with a comment saying why:
`afterparty-at-lizzies` (wnc.py:380-386), `industrial-assembly` (wnc.py:391-400) and
`trust-no-one` (wnc.py:404-414 — *"'Then' sequences them rather than making the draw conditional.
It was hung off ``cont``, so a declined 'up to 3' … skipped it."*). Faceplate prints the same shape
and is still on `cont`.

There is even an in-repo detector for precisely this bug class:
`tests/cards/test_script_lints.py::test_a_state_based_tail_clause_is_not_trapped_in_a_continuation`
(line 306), xfail with reason `AUD-tail-clause`, whose companion
`test_no_new_card_traps_a_state_based_tail_clause` keeps an open list `TRAPPED_TAIL_CLAUSES_OPEN`.
Faceplate is one of that open six — this is a known-open bug, not a deliberate ruling.

## Route 3 — the board is unreachable: NO

`Side(field=[("psycho-squad", {"gear": ["zetatech-faceplate"]})], gig=[(4,1),(6,2),(10,7)],
deck=["floor-it"])` vs `Side(gig=[(8,3)])` is **byte-for-byte the same board** as the already-passing
`tests/cards/test_statics.py::test_zetatech_faceplate_on_spend` (line 253-258). If the board were
illegal the accepted test would be too. The rival Gig area is non-empty, so the attack target is
legal under ruling 009.

## Route 4 — it asserts a script internal: NO

The two assertions are `s.gig[0] == [(4,1),(6,2),(10,7)]` (no die moved) and
`len(s.zone(0, Zone.HAND)) == 1` (a card was drawn). Both are printed-text outcomes on public
zones. No hook name, no call count, no internal flag.

## Route 5 — the finding misreads the text: NO

Printed text: *"When this Unit or Legend is spent, adjust a Gig by up to 1. **Then, if you control
3 or more Gigs with different values, draw 1.**"*

- "up to 1" includes 0, and `adjust_up_to` passes `optional=True`, so the decline is explicitly
  offered — the declined path is a real, printed-legal line of play.
- "**if you control** 3 or more Gigs with different values" is a board condition, not a
  back-reference to the die that moved. The repo's own lint draws exactly this line
  (`test_the_tail_clause_lint_separates_back_references_from_state_conditions`, line 324):
  `"If it becomes a min Gig"` is a back-reference and belongs in `cont`; `"Then, if you control …"`
  is not and does not.
- "Then" sequences the sentences; it does not make the draw conditional on the adjust succeeding.
  That reading is already settled in this codebase by the Trust No One fix (wnc.py:404-414), which
  prints "Decrease a Gig by up to 3. Then, if you control a min Gig, draw 1." and was moved from
  `cont` to `after` for this reason.
- The test's board has friendly values {1, 2, 7} *before* anything moves — three different values,
  so the condition holds on the declined path on its own terms.

## Conclusion

I could not kill it. `cont=after` on `src/cptcg/cards/sets/wnc.py:1137` should be `after=` with the
callback taking only `(c2)`, matching `afterparty-at-lizzies` / `industrial-assembly` /
`trust-no-one`. Classification: **B2-missing-clause** — the second printed sentence never executes
on the declined (or no-legal-adjustment) path.
