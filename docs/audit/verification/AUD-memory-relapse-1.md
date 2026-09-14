<!-- Working record for AUD-memory-relapse-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Memory Relapse  (`memory-relapse`)

- type: PROGRAM, colour: GREEN, cost: 4, power: None, RAM: 2
- keywords: none
- tags: ['BRAINDANCE']

## Printed text (byte-exact from data/cards/wnc.json)

```
Spend a rival Unit. It can't ready until your next turn. If your ★ (Street Cred) is an even number, draw 1.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 95-105

@script("memory-relapse")
def _():
    def play(c):
        def after(c2, u):
            c2.cant_ready(u)
            if c2.cred_even():
                c2.draw(1)
        spend_one(c, c.rival_units(), then=after)
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-memory-relapse-1

card: `memory-relapse`

claim: the even-Street-Cred draw is nested in the spend's continuation, so it never happens when the rival has no Unit to spend

failing test: `tests/cards/audit/test_a01.py::test_memory_relapse_draws_on_even_cred_with_no_rival_units`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Memory Relapse (`memory-relapse`)

Printed text (byte-exact):

> Spend a rival Unit. It can't ready until your next turn. If your ★ (Street Cred) is an even number, draw 1.

Implementation (`src/cptcg/cards/sets/wnc.py:95-105`):

```python
@script("memory-relapse")
def _():
    def play(c):
        def after(c2, u):
            c2.cant_ready(u)
            if c2.cred_even():
                c2.draw(1)
        spend_one(c, c.rival_units(), then=after)
    return CardScript(on_play=play)
```

---

## 1. "Spend a rival Unit."

**Text requires:** on play, a single (`a`, not `all`) Unit controlled by the *rival* is chosen and
spent. Mandatory ("Spend", not "you may spend"): if the rival controls at least one Unit, one must
be chosen. With no rival Units the clause simply does nothing.

**Implements it:** `spend_one(c, c.rival_units(), then=after)`
→ `src/cptcg/cards/dsl.py:71-77`, which calls `c.choose(list(cands), _do, prompt="Spend", optional=False)`
and `_do` calls `c2.spend(u)` (`effects.py:305` → `ops.spend`, `ops.py:320`).

- Side: `c.rival_units()` = `effects.py:52` → `self.units(self.rival)` → `state.units(1 - player)`,
  field Units of the opponent only, Gear and attached cards excluded. Correct side.
- Cardinality: exactly one (`choose`, one `Pick`). Correct.
- Mandatory: `optional` defaults to `False`, so no decline option is offered. Correct.
- Empty board: `choose` with an empty list returns immediately without asking. Correct for this
  clause in isolation (see §3 for the consequence).
- Already-spent rival Units are not filtered out of the candidate list, and `ops.spend` early-returns
  on an already-spent card. This matches the convention used by every other spend card in the set
  (`corporate-surveillance`, `dont-fear-the-reaper`, `judy-alvarez-...`), and the printed text gives
  no readiness restriction, so I do not count it as a deviation. It is worth noting only because it
  lets clause 2 be applied to an already-spent Unit.

**Verdict: match.**

## 2. "It can't ready until your next turn."

**Text requires:** the Unit spent by the previous sentence ("It" — the same object, not any Unit)
skips its next ready step, i.e. it does not ready during the rival's next turn and only rights
itself at the ready step after your next turn has passed. Strictly dependent on sentence 1: if no
Unit was spent there is no "it".

**Implements it:** `c2.cant_ready(u)` inside `after`, where `u` is the Unit `spend_one` just spent
(`dsl.py:73-75` passes the same `u` to `then`). `EffectCtx.cant_ready` (`effects.py:324-326`) sets
`F_NO_READY_NEXT` on that instance; `ReadyStep.run` (`steps.py:107-119`) walks only the *active*
player's zones, and for a flagged card clears the flag instead of readying it. Because the Unit sits
in the rival's field, the single skipped ready step is the rival's next one — exactly "not until your
next turn". Nesting inside the continuation correctly makes it depend on a Unit actually being spent.

**Verdict: match.**

## 3. "If your ★ (Street Cred) is an even number, draw 1."

**Text requires:** a self-contained sentence with exactly one condition — *your* Street Cred being an
even number. It carries no "If you do", no "then", and no pronoun referring back to the spend, so on
the plain reading it resolves on its own: if your Cred is even you draw 1, regardless of what
happened in sentences 1-2.

**Implements it:** `if c2.cred_even(): c2.draw(1)` — but *inside* `after`, the `then=` continuation of
`spend_one`.

- Whose Cred: `cred_even()` (`effects.py:93-98`) defaults to `self.player`, and the continuation's
  ctx is rebuilt as `EffectCtx(st, inst)` with `player = s.i_owner[inst]`, i.e. the controller of
  Memory Relapse. Correct side.
- Even: `cred() % 2 == 0`, with Null Cred (no Gigs) returning `False` per ruling 038 / CR 11.2.3.
  Correct.
- Amount / who draws: `c2.draw(1)` draws one card for `self.player`. Correct.
- **Gating: wrong.** `dsl.spend_one` only invokes `then` from inside `c.choose(...)`'s continuation
  (`dsl.py:73-77`), and `EffectCtx.choose` (`effects.py:158-161`) returns immediately, running
  neither `cont` nor `otherwise`, when the candidate list is empty. So when the rival controls no
  Units, the whole of `after` is skipped and **no card is drawn even though Street Cred is even**.
  The printed text makes the draw conditional only on Cred, not on a Unit having been spent.

The set's own authoring convention confirms the reading: cards that *do* gate a later sentence say
so in words and are nested accordingly — `gilded-maton` ("You may defeat a friendly Gear. **If you
do**, defeat a rival Unit...") and `unlikely-bond` ("Bottom-deck a ready friendly Unit. **If you
do**, ...") both nest in `then=`. The structurally identical card without an "If you do",
`chrome-reverie` ("A rival Unit can't attack until your next turn. If you control a min Gig, you may
Call a Legend for free."), deliberately places its second sentence *outside* the `choose`
continuation (`wnc.py:100-107` of that entry: `c.choose(...)` then `if c.min_gigs(): c.offer_call_free()`),
so it fires even with no rival Unit on board. Memory Relapse should follow `chrome-reverie`, not
`gilded-maton`.

**Verdict: MISMATCH.** The draw is given an extra precondition (a rival Unit existed to spend) that
the printed text does not state.

Correct shape would be to hoist the Cred check out of the continuation, e.g.

```python
def play(c):
    spend_one(c, c.rival_units(), then=lambda c2, u: c2.cant_ready(u))
    c.later(lambda c2: c2.draw(1) if c2.cred_even() else None)
```

(or an equivalent that evaluates the Cred check after the spend resolves).

---

## Summary

Clauses 1 and 2 are faithful, including side, cardinality, mandatoriness, the pronoun binding of
"It", and the one-ready-step meaning of "until your next turn". Clause 3 is mis-scoped: the draw is
nested inside the spend's continuation, so it silently does not happen when the rival controls no
Units — an extra condition the card text does not impose.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-memory-relapse-1 — kill attempt: FAILED (finding survives)

Card: `memory-relapse`. Printed text, byte-exact from `data/cards/wnc.json`:

> Spend a rival Unit. It can't ready until your next turn. If your ★ (Street Cred) is an even number, draw 1.

Script (`src/cptcg/cards/sets/wnc.py:94-105`) nests both later sentences inside the spend's
continuation:

```python
def after(c2, u):
    c2.cant_ready(u)
    if c2.cred_even():
        c2.draw(1)
spend_one(c, c.rival_units(), then=after)
```

`spend_one` (`src/cptcg/cards/dsl.py:73-79`) calls `c.choose(list(cands), _do, ...)`, and
`EffectCtx.choose` (`src/cptcg/core/effects.py:144-155`) returns immediately when the candidate
list is empty and no `otherwise` was supplied:

```python
vals = list(values)
if not vals:
    if otherwise is not None:
        otherwise(self)
    return
```

So with no rival Unit on the field, `after` never runs and the third sentence never resolves.

## The five kill routes, each tried

1. **A ruling covers it.** No. I read all 41 rows of `docs/rulings.md`. 012 (BLOCKER redirect
   scope), 015 (GO SOLO slot), 019 (once-per-turn scope), 025 (payment order), 026 (field limit)
   and 030 (⊡ on Gear) are untouched by this card. The only Street Cred ruling is **038**
   (Street Cred with no Gigs is *null*, neither even nor odd) — and it does not apply here: the
   test board gives player 0 one Gig `(6, 4)`, and `GameState.street_cred`
   (`src/cptcg/core/state.py:219-220`) sums die values, so cred = 4 and `cfg.null_cred` never
   fires (`effects.py:93-98`). Nothing in `docs/rules.md` says an instruction that cannot be
   performed cancels the rest of a Program; line 72 only says "Pay its cost, resolve the effect,
   move it to the trash".

2. **The engine already handles it.** No. I checked `core/effects.py` (`choose` bails silently),
   `core/ops.py`, `core/steps.py` and `core/legal.py`. Nothing supplies the draw on the
   no-target path. Empirically: I ran the same board with a rival Unit present
   (`corpo-security`) and the engine printed `cred 4 ... hand 1` — the draw fires only when the
   spend found a target. With an empty rival field the hand stays at 0.

3. **The test board is unreachable.** No. A rival with no Units in the field is the most ordinary
   board in the game, and `legal.main_menu` (`src/cptcg/core/legal.py`, the PROGRAM branch:
   `elif d.type is CardType.PROGRAM: opts.append(Play(i))`) offers a Program with **no** target
   test at all — so playing Memory Relapse into an empty rival field is a legal, generated move
   that a search agent will actually pick for the draw. One d6 Gig showing 4 is reachable on any
   turn.

4. **The test asserts a script internal.** No. It asserts `len(s.zone(0, Zone.HAND)) == 1` after
   playing the card from a one-card hand — a printed-text outcome (hand size), exactly the
   contract stated in the batch docstring.

5. **The finding misreads a word.** No. The draw sentence carries no back-reference: sentence 2
   says "**It** can't ready", tying it to the spent Unit, while sentence 3 is a standalone
   conditional on the controller's own Street Cred. This set writes dependency explicitly —
   10 cards in `wnc.json` print "If you do" (`unlikely-bond`, `panam-palmer-nomad-cavalry`,
   `placide-voodoo-sentinel`, ...) — and `field-operator` prints the identical tail
   ("PLAY: If your ★ (Street Cred) is an even number, draw 1.") as a complete, self-standing
   effect. Per ruling 023's precedent, printed text governs.

## Test result

`python -m pytest 'tests/cards/audit/test_a01.py::test_memory_relapse_draws_on_even_cred_with_no_rival_units' -q -rx`
→ **XFAIL** (strict), i.e. the engine currently fails exactly as filed.

## Verdict

Survives. Classification **B4-scope-or-condition**: the draw clause is implemented but gated on
an extra condition the text does not print (a rival Unit existing to spend). The fix is to hoist
the even-cred draw out of the `then=` continuation (e.g. run it after `spend_one`, or pass it as
`choose`'s `otherwise` as well), not to change `cant_ready`, which correctly stays tied to the
spent Unit.
