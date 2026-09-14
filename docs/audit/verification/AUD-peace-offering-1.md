<!-- Working record for AUD-peace-offering-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Peace Offering  (`peace-offering`)

- type: PROGRAM, colour: GREEN, cost: 1, power: None, RAM: 1
- keywords: none
- tags: ['BRAINDANCE']

## Printed text (byte-exact from data/cards/wnc.json)

```
You may set a Gig's value to the value of another Gig. Then, if you control a value-pair, draw 1.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 367-381

@script("peace-offering")
def _():
    def play(c):
        def pick_target(c2, o, i):
            others = [(o2, j) for o2 in (0, 1) for j in range(len(c2.gigs(o2))) if (o2, j) != (o, i)]

            def pick_source(c3, src):
                c3.set_gig(o, i, c3.gigs(src[0])[src[1]][1])
                if c3.has_value_pair():
                    c3.draw(1)
            c2.choose(others, pick_source, prompt="Copy the value of")
        c.choose_gig([0, 1], pick_target, prompt="Set which Gig?", optional=True)
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-peace-offering-1

card: `peace-offering`

claim: the draw is nested inside the optional set, so declining the 'may' skips the separate value-pair draw clause

failing test: `tests/cards/audit/test_a04.py::test_peace_offering_draws_when_the_set_is_declined`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Peace Offering (`peace-offering`)

Printed text (byte-exact):

```
You may set a Gig's value to the value of another Gig. Then, if you control a value-pair, draw 1.
```

Implementation: `src/cptcg/cards/sets/wnc.py` lines 367-381.

Clause split used below:

1. "You may ..." — the whole set is optional.
2. "set a Gig's value" — the target: one Gig, either player's.
3. "to the value of another Gig" — the source: a different Gig, either player's; the target takes its value.
4. "Then, if you control a value-pair," — a state condition on the controller's own Gig area, tested after clause 2-3.
5. "draw 1." — the controller draws one card.

---

## 1. "You may" — the set is optional

**Text requires:** the controller may decline the set entirely. Declining is a legal line of play (e.g. you do not want to collapse a value you need, or you already have what you want).

**Implements:** `wnc.py:378` — `c.choose_gig([0, 1], pick_target, prompt="Set which Gig?", optional=True)`. `EffectCtx.choose_gig` (`effects.py:341-353`) forwards `optional=True` to `choose` (`effects.py:144-175`), which appends a `Pick(())` decline option; with `otherwise=None`, declining runs nothing.

**Match:** yes for the optionality itself. (The consequence of the decline path is clause 4-5 below.)

## 2. "set a Gig's value" — the target

**Text requires:** "a Gig", unqualified — one Gig, and nothing in the text or in `docs/rules.md` restricts it to friendly Gigs, so either player's die is a legal target. Exactly one is set ("a", not "all").

**Implements:** `wnc.py:378` `c.choose_gig([0, 1], ...)` enumerates `(o, i, k, v)` over both players' Gig areas (`effects.py:345-346`) and calls `pick_target(c2, o, i)` for exactly one pick. `choose_gig`'s `_do` re-validates that the die at that index is still the same `(sides, value)` before running the continuation (`effects.py:348-352`).

**Match:** yes — single target, both sides in scope.

## 3. "to the value of another Gig" — the source

**Text requires:** a *different* Gig supplies the value; again unqualified as to owner. The target's value becomes the source's value. Per ruling 037 (`docs/rulings.md`, CR 6.4.4/6.4.5), setting to a value not on the target die's face, or to the value it already shows, makes the effect fail with no change.

**Implements:** `wnc.py:372` builds `others = [(o2, j) for o2 in (0, 1) for j in range(len(c2.gigs(o2))) if (o2, j) != (o, i)]` — every die of either player except the target itself, so "another" is honoured. `wnc.py:374` `c3.set_gig(o, i, c3.gigs(src[0])[src[1]][1])` reads the source's current face value at resolution time and writes it to the target. `EffectCtx.set_gig` → `ops.set_gig` (`ops.py:498-509`) returns without change when the value is off the target die's face (`set_gig_off_face_fails`) or equals the current value — exactly ruling 037.

**Match:** yes. Minor, not a rules discrepancy: illegal source picks (off-face for the target, or equal to its current value) are offered and then silently fail rather than being filtered out of the prompt; that is the "the effect fails" behaviour ruling 037 asks for.

## 4. "Then, if you control a value-pair,"

**Text requires:** after the set resolves (or does not), test a **state** condition about the board: does the controller control a value-pair — two of their own dice showing the same value? Two points matter:

* *Whose* Gigs: "you control", so the controller's own Gig area only.
* *When it runs:* the sentence's only condition is the value-pair. "Then" sequences the two sentences; it is not a back-reference like "If you do" or "If it becomes ...". The condition is testable against the board whether or not any die was set, so declining clause 1 must not skip this sentence. The repo's own lint states this convention explicitly — `tests/cards/test_script_lints.py:335` asserts `not _BACKREF.match("Then, if you control a value-pair, draw 1.")`, i.e. this is a state condition, not a back-reference.

**Implements:** `wnc.py:375` `if c3.has_value_pair():` — `effects.py:112-118` counts `Counter(gig_values(player))` pairs with each die in at most one pair, defaulting `player` to `self.player`, the controller. The *whose* half is right.

**The placement is wrong.** `wnc.py:375` sits inside `pick_source`, which is the continuation of the source prompt (`wnc.py:377`), which is itself inside `pick_target`, the continuation of the optional target prompt (`wnc.py:378`). So the condition is only ever evaluated on the path where the player accepted the set and a source existed. Two ways it is skipped:

* **Decline.** `choose(..., optional=True)` with no `otherwise` runs nothing on the decline branch (`effects.py:169-172`). The value-pair test and the draw never happen.
* **No legal source.** If the target prompt resolves but `others` is empty (only one die on the table), `choose` with an empty `vals` and `otherwise=None` returns immediately (`effects.py:165-168`) — again no test, no draw. (Harmless here, since one die cannot be a pair.)

**Match:** condition and side are correct; the **timing/condition-gating is wrong** — it is gated on the optional first sentence having been accepted.

## 5. "draw 1."

**Text requires:** the controller draws exactly one card whenever clause 4's condition holds.

**Implements:** `wnc.py:376` `c3.draw(1)` → `EffectCtx.draw` (`effects.py:221-222`) → `ops.draw` for `self.player`. Count and side are right.

**Match:** the draw itself is right; it inherits clause 4's wrong gating.

---

## Concrete failure case

Controller's Gig area: two d6 both showing **2** (already a value-pair). Rival has a d8 showing 5. Play Peace Offering and decline the "you may" — a sensible line, since every legal set would break the pair or is off-face.

* Printed text: the set does not happen; "Then, if you control a value-pair, draw 1" tests the board, finds the 2/2 pair, and the controller **draws 1**.
* Script: `choose_gig(..., optional=True)` takes the decline branch, `otherwise` is `None`, `pick_target` never runs, `pick_source` never runs, `has_value_pair()` is never evaluated — **no draw**.

The same loss occurs whenever the player declines with a pre-existing pair, which is also the normal "protect my pair" line of play.

## Verdict

One discrepancy, in clause 4-5: the state-based tail sentence is implemented inside the continuation of the optional first sentence, so declining the "may" (and, degenerately, having no legal source) skips the value-pair draw entirely. Correct behaviour is to run the `has_value_pair()` / `draw(1)` step on every path — e.g. as an `otherwise` on the target prompt and after the source continuation (or queued with `c.later(...)` before asking).

Everything else — optionality, single target, either-side target and source, "another" exclusion, ruling-037 failure semantics, friendly-only value-pair counting, draw count and recipient — matches the printed text.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-peace-offering-1 — kill attempt: FAILED (finding survives)

Card text (byte-exact, `data/cards/wnc.json`):
`You may set a Gig's value to the value of another Gig. Then, if you control a value-pair, draw 1.`

Reproduction: `tests/cards/audit/test_a04.py::test_peace_offering_draws_when_the_set_is_declined`
is **XFAIL** (strict). With `--runxfail` the first assertion (`s.gig[0] == [(6, 2), (8, 2)]`)
passes — so `Pick(())` really did take the engine's decline branch — and only
`len(s.zone(0, Zone.HAND)) == 1` fails (`0 == 1`). The decline path exists, is taken, and the draw
does not happen.

I worked all five kill routes. None of them closes.

## 1. No ruling covers it
`docs/rulings.md` has exactly 41 rows (file is 53 lines). None of the usual deliberate-ruling rows
apply: 012 (BLOCKER redirect scope), 015 (GO SOLO slot), 019 (once-per-turn scope), 025 (payment
order), 026 (field limit), 030 (⊡ on Gear) are all unrelated subject matter. The only Gig-adjacent
ruling is **037** ("adjusting a Gig to a value it already has — the effect fails"), and it cuts
*for* the finding, not against it: it is another way the first sentence can do nothing while the
board condition in the second sentence is still true. No row anywhere says a declined optional
clause ends the resolution of the rest of the card.

## 2. The engine does not already handle it
`src/cptcg/cards/sets/wnc.py:388` puts `c3.draw(1)` inside `pick_source`, which is inside
`pick_target`, which is the continuation of `c.choose_gig([0, 1], ..., optional=True)`. In
`src/cptcg/core/effects.py:341-362`, `choose_gig` passes `otherwise=after` — and `peace-offering`
passes **no** `after=`, so on decline `EffectCtx.choose`'s `_cont` (effects.py:166-171) runs nothing
at all. Nothing in `ops.py`, `steps.py` or `legal.py` re-runs a tail clause.

Worse for the kill: the engine already grew the fix and the repo already names this card.
* `effects.py:364-381` (`adjust_up_to` docstring) states the doctrine outright: `cont` "runs only
  when a die actually moved", `after` "runs whatever happens ... and is right for a separate printed
  sentence with its own board condition (\"Then, **if you control** a min Gig, draw 1\")", and
  "Six cards in this set were written that way."
* `tests/cards/test_after_hook.py` lands that plumbing with a decline test and a no-legal-candidate
  test, saying "No card uses it yet".
* `tests/cards/test_script_lints.py:290-294` lists `TRAPPED_TAIL_CLAUSES_OPEN` — and
  **`peace-offering` is one of the six named entries**, with the guard test passing today precisely
  so a seventh card cannot join them. Its sibling xfail docstring says in terms: "\"up to N\"
  includes zero, **\"you may\" can be refused**, and a prompt with no legal candidate is skipped."
  This is the project's own prior analysis agreeing with the filer, not a deliberate ruling.

## 3. The board is reachable
`Side(hand=["peace-offering"], eddies=9, gig=[(6, 2), (8, 2)], deck=["floor-it"])` is a d6 and a d8
each rolled to 2 in the controller's Gig area, one Program in hand, Eddies to pay its cost 1. Two
dice rolling the same face is ordinary; nothing here needs an illegal state.

## 4. The test asserts printed-text outcomes only
It asserts die faces (`s.gig[0]`) and hand size. It never inspects a continuation, a tag, or a
script internal.

## 5. The text is not misread
This set templates dependency explicitly and elsewhere: "You may defeat a friendly Gear. **If you
do**, draw 2" (dum-dum), "You may discard 1 Program. **If you do**, bottom-deck a rival Unit"
(placide), "You may pay 2 €$. **If you do**, ..." (el-sombreron), "You may discard 2 Programs. **If
you do**, ..." (maman-brigitte). Peace Offering does not say "If you do". It says "**Then, if you
control a value-pair**" — the same shape as trust-no-one ("Then, if you control a min Gig"),
zetatech-faceplate, evelyn-parker and yorinobu-arasaka: `Then` sequences, and the condition is read
off the board, not off whether the optional action was taken. `has_value_pair()`
(effects.py:112-118) is a pure board query on the controller's dice; with 2 and 2 it is true whether
or not a die moved.

## Best argument I could build against the finding, and why it fails
One could argue the second sentence is mere reminder text, since a completed set makes the target
Gig equal to the source Gig and therefore always produces a pair — which would make the clause
meaningful only as part of the set. It does not hold: the script and the text both allow setting
**a rival's** Gig (`choose_gig([0, 1], ...)`, printed "a Gig", not "a friendly Gig"), where the pair
formed is not one *you* control; and under ruling 037 a set to the value a Gig already shows fails.
So "if you control a value-pair" is a genuine, independently-testable condition — exactly the shape
`after=` was built for.

## Verdict
Survives. Classification **B2-missing-clause**: on the reachable decline line the printed second
sentence never resolves. Fix shape (not applied here): give `choose_gig` an `after=` that tests
`has_value_pair()` and draws, so it runs after a pick, after a decline, and when there is no legal
Gig to offer.
