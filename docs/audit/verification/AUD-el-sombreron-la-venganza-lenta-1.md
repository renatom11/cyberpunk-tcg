<!-- Working record for AUD-el-sombreron-la-venganza-lenta-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# El Sombrerón — La Venganza Lenta  (`el-sombreron-la-venganza-lenta`)

- type: UNIT, colour: RED, cost: 5, power: 4, RAM: 4
- keywords: none
- tags: ['GANGER', 'VALENTINO']

## Printed text (byte-exact from data/cards/wnc.json)

```
ATTACK: You may pay 2 €$. If you do, this Unit gains power equal to a friendly max Gig this turn.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 665-679

@script("el-sombreron-la-venganza-lenta")
def _():
    from cptcg.core.ops import available, pay

    def attack(c):
        if available(c.s, c.player) < 2 or not c.gigs():
            return

        def yes(c2):
            pay(c2.s, c2.player, 2)
            c2.temp_power(c2.inst, max(c2.gig_values()))
        c.maybe(yes, prompt="Pay 2 €$ for +power?")
    return CardScript(on_attack=attack)
```

---

# The finding, and the test that failed

# AUD-el-sombreron-la-venganza-lenta-1

card: `el-sombreron-la-venganza-lenta`

claim: 'a friendly max Gig' means a die showing its maximum face (cf. 'min Gig' / EffectCtx.max_gigs), but the script adds the largest value in the Gig area

failing test: `tests/cards/audit/test_a07.py::test_el_sombreron_gains_the_value_of_a_max_gig_not_the_largest_value`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — El Sombrerón, La Venganza Lenta (`el-sombreron-la-venganza-lenta`)

Printed text (byte-exact):

```
ATTACK: You may pay 2 €$. If you do, this Unit gains power equal to a friendly max Gig this turn.
```

Implementation (`src/cptcg/cards/sets/wnc.py` lines 665-679):

```python
@script("el-sombreron-la-venganza-lenta")
def _():
    from cptcg.core.ops import available, pay

    def attack(c):
        if available(c.s, c.player) < 2 or not c.gigs():
            return

        def yes(c2):
            pay(c2.s, c2.player, 2)
            c2.temp_power(c2.inst, max(c2.gig_values()))
        c.maybe(yes, prompt="Pay 2 €$ for +power?")
    return CardScript(on_attack=attack)
```

## 1. `ATTACK:` — the trigger

Requires: the effect fires when this Unit attacks (per ruling 023, after the target is declared and
the attacker is spent; the script does not need to care).

Implemented by: `CardScript(on_attack=attack)` (line 679). `docs/effects-authoring.md` lists
`on_attack` as exactly the printed ATTACK timing trigger; the engine dispatches it for the Unit's
own attack.

Match: yes.

## 2. "You may pay 2 €$" — optional cost, controller's choice

Requires: the *controller of this Unit* gets a yes/no decision; declining is legal and nothing
further happens; if they say yes, exactly 2 €$ are paid.

Implemented by:
- `c.maybe(yes, prompt=...)` (line 677). `EffectCtx.maybe` (effects.py) is `choose([True], ...,
  optional=True)` with `player=None` → defaults to `self.player`, the card's owner. The decline
  option is added and no `otherwise` is given, so declining does nothing. Correct "may", correct
  side.
- `pay(c2.s, c2.player, 2)` inside the continuation (line 674) spends 2 payable sources
  (`ops.pay` → `payable_sources`: ready Eddies / Legends, per ruling 025). Correct amount, paid by
  the controller.
- Gate `available(c.s, c.player) < 2: return` (line 670): if the player cannot afford 2, no prompt
  is offered. Suppressing an unaffordable "may" is faithful — the cost could not be paid, so the
  "If you do" branch could never happen. Also protects `ops.pay` from its RuntimeError.

Note the continuation uses the ctx it is given (`c2`), as `docs/effects-authoring.md` requires, so
this is search/clone-safe.

Match: yes.

## 3. "If you do, this Unit gains power … this turn" — conditionality, subject, duration

Requires: the power gain happens **only** if the 2 €$ were actually paid; it applies to *this Unit*
(`c.inst`), not to a chosen or to every Unit; and it lasts until end of turn.

Implemented by: the whole gain sits inside `yes(c2)`, the accept branch of `maybe`, after `pay`.
Declining runs nothing (no `otherwise`). Subject is `c2.inst` — this Unit. `c2.temp_power(inst,
delta)` → `ops.add_temp_power` with `cond=0` (unconditional situation mask), and `s.temp_power` is
cleared by `EndTurnCleanupStep` (steps.py line 179), i.e. it expires at end of turn. Also cleared
for the instance when it leaves play (ops.py 213-214), which is correct.

Match: yes.

## 4. "power equal to a friendly max Gig" — the amount  ← DISCREPANCY

Requires two things.

(a) **friendly**: the Gig must be one the controller controls, not a rival's.
(b) **a max Gig**: "max Gig" is the mirror of the set's "min Gig" term. `EffectCtx.min_gigs` is
documented as "Indices of dice showing their minimum face (1)" and `EffectCtx.max_gigs` is
`[i for i, (k, v) in enumerate(self.gigs(player)) if v == k]` — a die **showing its maximum face**.
Other cards in this set use the term the same way ("If it becomes a min Gig", "If a friendly d4 is
a min Gig" — a d4 showing 1, not merely the smallest die). So the bonus is the value of a friendly
die that is currently on its top face, i.e. that die's number of sides. (With several such dice,
"a" implies one of them — at worst a choice; the strictly larger-is-better reading would be the
largest max Gig.)

Implemented by: `max(c2.gig_values())` (line 675). `gig_values()` with no player defaults to
`self.player`, so (a) friendly is correct. But it computes the **highest face value among all
friendly Gigs**, which is not "a max Gig". The helper the clause names, `max_gigs()`, is never
called; nothing anywhere checks `v == k`.

Concretely, with friendly Gigs `[(20, 15), (4, 4)]`:
- printed text: the only max Gig is the d4 showing 4 → **+4 power**;
- script: `max([15, 4])` → **+15 power**.

The two agree only by accident, when the largest-valued die happens to be on its max face — e.g.
`[(6, 6), (4, 3)]` gives 6 either way. Whenever a bigger die sits below its top face, the script
pays out far too much power, up to +20 from a d20 that is not a max Gig at all.

Match: **no** — wrong effect (wrong quantity: highest die value instead of the value of a Gig
showing its max face).

## 5. The `not c.gigs()` guard — when the effect is offered at all

Requires: with no friendly max Gig there is nothing to gain; the "may pay" would buy +0 (the
engine may legitimately skip an empty prompt, but it must not grant power).

Implemented by: `if ... or not c.gigs(): return` (line 670) — it only suppresses the prompt when the
player controls **no Gigs at all**. This is really a consequence of clause 4's reading: under the
correct reading the guard should be `not c.max_gigs()`. As written, a player with Gigs but no die on
its max face is still offered the deal and still gains power equal to the largest value — the same
bug seen from the gating side, so I count it as part of finding 4 rather than a separate one. (The
guard is also what keeps `max()` from raising on an empty sequence, so a fix must keep a guard.)

Match: no (same defect as clause 4).

## Summary

Clauses 1-3 (trigger, optional cost and its side, conditionality/subject/duration) are faithful.
Clause 4 is wrong: the script grants power equal to the highest friendly Gig **value**
(`max(c.gig_values())`) where the card grants power equal to a friendly **max Gig** — a die showing
its maximum face (`c.max_gigs()` / `v == k`). It over-grants whenever the largest die is not on its
top face, and grants power at all when no friendly max Gig exists.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-el-sombreron-la-venganza-lenta-1 — kill attempt: FAILED (finding survives)

Printed text (byte-exact, `data/cards/wnc.json:619`):
`ATTACK: You may pay 2 €$. If you do, this Unit gains power equal to a friendly max Gig this turn.`

Reproduction: `tests/cards/audit/test_a07.py::test_el_sombreron_gains_the_value_of_a_max_gig_not_the_largest_value`
is **XFAIL** (strict). With `--runxfail` it fails `assert 13 == 8` — the attack resolved, the
`Pick((0,))` really paid the 2 €$, and `ops.power` reports 4 + 9, the d12's value, on a board whose
only die showing its maximum face is the d4.

I worked all five kill routes. None of them closes.

## 1. No ruling covers it
`docs/rulings.md` holds 41 rows. None mentions Gig faces as a quantity. The usual deliberate rows —
012 (BLOCKER redirect scope), 015 (GO SOLO slot), 019 (once-per-turn scope), 025 (payment order),
026 (field limit), 030 (⊡ on Gear) — are unrelated subject matter. The only Gig-face ruling is **037**
(setting a Gig to a value not on its face, or to the value it already shows, fails), which is about
adjustment legality and says nothing about what "max Gig" denotes. `docs/rules.md` never uses the
words "min Gig" or "max Gig" at all; its glossary (lines 183-185) defines only *Gigs* and *Street
Cred*. So there is no deliberate ruling to shelter behind.

## 2. The engine does not already handle it
`src/cptcg/cards/sets/wnc.py:675` is `c2.temp_power(c2.inst, max(c2.gig_values()))`.
`EffectCtx.gig_values` (`src/cptcg/core/effects.py:109`) returns every friendly die's face value, so
`max(...)` is the largest value in the area. The helper the clause names,
`EffectCtx.max_gigs` (`effects.py:124`, `[i for i, (k, v) in ... if v == k]` — die showing its
maximum face), is **called by no script in the repo**. Nothing in `core/ops.py` (`add_temp_power`,
`power`), `core/steps.py` or `core/legal.py` rewrites the amount; `ops.power` just sums
`s.temp_power`. There is no second implementation anywhere.

## 3. The board is reachable, and the defect is not board-specific
`Side(field=["el-sombreron-la-venganza-lenta"], eddies=2, gig=[(12, 9), (4, 4)])` vs
`Side(gig=[(4, 1)])` is the standard `tests/conftest.py:75` mid-game fixture (turn 3,
`turns_taken=[1, 1]`). A d12 rolled to 9 and a d4 rolled to 4 are ordinary rolls, and
`docs/rules.md:33-35` puts only one constraint on the order dice leave the fixer area — "any die
**except the d20, which is always last**" — so holding a d12 and a d4 and no others is legal. Even
if one wanted to quibble about the exact turn count behind three dice on the table, the discrepancy
survives every larger board: any friendly d20 showing 15 alongside a d4 showing 4 pays +15 where the
text pays at most +4. The claim does not depend on this particular state.

## 4. The test asserts a printed-text outcome
It asserts `power(s, u)` — effective power after the attack and the payment — which is exactly what
"this Unit gains power equal to ... this turn" prints. It never touches a continuation, a mod key,
`temp_power` internals, or the script's structure.

## 5. The text is not misread — and this is where the kill dies
"min Gig" is set terminology for **a die showing its minimum face (1)**, not "your smallest die":
* `EffectCtx.min_gigs` (`effects.py:120-122`) is documented "Indices of dice showing their minimum
  face (1)" and is read by six scripts (`wnc.py:128, 219, 401, 1360, 1371`).
* The comparative reading is impossible on the printed cards. Trust No One — "Decrease a Gig by up
  to 3. Then, if you control a min Gig, draw 1" — would be an unconditional draw if "min Gig" meant
  "your lowest-valued die", since anyone with a Gig has a lowest one. Same for Chrome Reverie's free
  Call and Alt Cunningham's per-min-Gig discount.
* **Kerry Eurodyne — Axe, Attitude, Audience** prints the mirror term in the open: "When you roll a
  **min or max value** on a Gig, draw 1. If it's a d20, draw 3 instead." Its script (`wnc.py:1280`)
  is `if v == 1 or v == sides`. That is the set's own definition of *max* on a Gig: the die is on its
  top face. The d20 rider only makes sense face-relative.
* The template matches exactly. "a friendly min Gig" (Pyramid Song, Alt Cunningham) → "a friendly
  max Gig". Where this set means a comparison *between* cards it says so in different words:
  "a Rival's **lowest-power** Unit. (If there are multiple, choose 1.)" (Les Elemens), "value
  **higher than** their power" (Chrome Fang), "cost **equal to or less than**" (Over the Edge). It
  never uses min/max for a comparison across permanents.

## Best arguments I could build against the finding, and why they fail
* **The indefinite article.** Under the face reading, "a friendly max Gig" is under-specified when a
  d4 and a d20 are both on their top faces, whereas under the largest-value reading every tied die
  gives the same number. But the set already templates choices this loosely ("Decrease a Gig by up
  to 3"), and Les Elemens shows the designers add "(If there are multiple, choose 1.)" only when they
  feel like it. An ambiguity about *which* max Gig does not turn the term into a comparison of values,
  and it does not reach the test's board, where the d4 is the only max Gig.
* **The docs agree with the script.** `data/strategy/cards.json` says El Sombrerón "becomes as big as
  your largest Gig", and `data/arena/delayed.json` (position `gig-shaping-raise-the-max-next-turn`)
  reasons "attacks for 4 + max" with max = 5 on dice showing 5/3/4/1 — the largest value, no die on
  its top face. Both are downstream prose generated against the current engine, and neither is
  `docs/rules.md` or `docs/rulings.md`. Ruling **023** is the standing precedent that printed text
  outranks the project's own earlier reading when the two disagree. (For what it is worth, that
  arena position's solution is unaffected: its winning move raises a d6 from 5 to 6, which is both
  the largest value *and* a max Gig, so it still reaches exactly 10 power under either reading.)

## Verdict
Survives. Classification **B1-wrong-effect** — wrong quantity: the script grants the largest friendly
Gig **value** (`max(c.gig_values())`) where the card grants the value of a friendly **max Gig**, a die
showing its maximum face (`c.max_gigs()`, `v == k`). Fix shape (not applied here): compute the amount
from `c.max_gigs()` (largest such die, or a choice) and move the gate at `wnc.py:670` from
`not c.gigs()` to "no friendly max Gig", keeping a guard so `max()` never sees an empty sequence.
