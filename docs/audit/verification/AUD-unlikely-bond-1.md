<!-- Working record for AUD-unlikely-bond-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Unlikely Bond  (`unlikely-bond`)

- type: PROGRAM, colour: BLUE, cost: 4, power: None, RAM: 2
- keywords: none
- tags: ['MAELSTROM', 'MOX']

## Printed text (byte-exact from data/cards/wnc.json)

```
Bottom-deck a ready friendly Unit. If you do, bottom-deck a spent rival Unit.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 81-89

@script("unlikely-bond")
def _():
    def play(c):
        def after(c2, _u):
            bottom_deck_one(c2, [u for u in c2.rival_units() if c2.s.i_spent[u]])
        bottom_deck_one(c, [u for u in c.units() if not c.s.i_spent[u]], optional=True, then=after)
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-unlikely-bond-1

card: `unlikely-bond`

claim: the friendly bottom-deck is scripted optional=True, but the card prints no 'may'

failing test: `tests/cards/audit/test_a01.py::test_unlikely_bond_first_bottom_deck_is_not_optional`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Unlikely Bond (`unlikely-bond`)

Printed text (byte-exact):

```
Bottom-deck a ready friendly Unit. If you do, bottom-deck a spent rival Unit.
```

Implementation (`src/cptcg/cards/sets/wnc.py` lines 81-89):

```python
@script("unlikely-bond")
def _():
    def play(c):
        def after(c2, _u):
            bottom_deck_one(c2, [u for u in c2.rival_units() if c2.s.i_spent[u]])
        bottom_deck_one(c, [u for u in c.units() if not c.s.i_spent[u]], optional=True, then=after)
    return CardScript(on_play=play)
```

Helpers read: `bottom_deck_one` (`src/cptcg/cards/dsl.py:65-70`), `EffectCtx.choose`
(`src/cptcg/core/effects.py:144-175`), `EffectCtx.units` / `rival_units`
(`src/cptcg/core/effects.py:46-51`), `GameState.units` (`src/cptcg/core/state.py:201-205`),
`EffectCtx.bottom_deck` -> `ops.bottom_deck` (`src/cptcg/core/effects.py:247`,
`src/cptcg/core/ops.py:260-261`).

---

## 1. Timing: the whole text is a Program's play effect

**Text requires:** the card is a PROGRAM with no trigger word, so the text resolves when the
Program is played (docs/rules.md "Play"; ruling 035 places the Program outside every area while
it resolves).

**Implements:** `CardScript(on_play=play)`.

**Match:** yes.

## 2. "Bottom-deck a ready friendly Unit." — which cards are legal targets

**Text requires:** exactly one target; it must be (a) a Unit, (b) friendly — controlled by the
player resolving the card, not the rival — and (c) *ready*, i.e. upright / not spent
(docs/rules.md:175-177 glossary: "Spend / spent — turn a card sideways"; "Ready — upright").

**Implements:** `[u for u in c.units() if not c.s.i_spent[u]]`. `EffectCtx.units()` with no
argument defaults to `self.player` (effects.py:46-48), i.e. the controller of the Program —
friendly, correct side. `GameState.units` (state.py:201-205) returns field cards that are not
attached Gear and are not of type GEAR, so GO-SOLO Legends now on the field are included and
equipped Gear is excluded — right notion of "Unit". `not i_spent[u]` is exactly "ready".
`bottom_deck_one` passes a single-pick `c.choose(...)` (dsl.py:70), so exactly one Unit, chosen
by the controller (`player=None` → `self.player`, effects.py:173).

**Match:** yes — side, "a" (one, not all), and the ready filter are all right.

## 3. "Bottom-deck …" — the effect applied to the chosen friendly Unit

**Text requires:** put that Unit on the bottom of its owner's deck (ruling 022: index 0 is the
bottom).

**Implements:** `_do` in dsl.py:66-69 calls `c2.bottom_deck(u)` → `ops.bottom_deck` →
`move(s, inst, Zone.DECK, bottom=True)`.

**Match:** yes.

## 4. "Bottom-deck a ready friendly Unit." — mandatory vs optional  ← **MISMATCH**

**Text requires:** a *mandatory* instruction. The printed line has no "may": it reads
"Bottom-deck a ready friendly Unit.", not "You may bottom-deck a ready friendly Unit." Across
this set, optionality is always printed explicitly — e.g. Gilded Maton "PLAY: **You may** defeat
a friendly Gear. If you do, defeat a rival Unit with cost 3 or less."; Maman Brigitte "**You
may** discard 2 Programs. If you do, bottom-deck a rival unequipped Unit."; Placide "**You may**
discard 1 Program. If you do, bottom-deck a rival Unit." Unlikely Bond is the one card of that
shape that omits "may", so the omission is meaningful: if the player controls at least one ready
friendly Unit, they must bottom-deck one (and then the second sentence follows). The trailing
"If you do" is not evidence of optionality — it covers the case where the instruction cannot be
carried out at all (no ready friendly Unit), which is exactly how the engine's `choose` on an
empty candidate list behaves.

**Implements:** `optional=True` on the friendly-side `bottom_deck_one` (wnc.py:86). In
`EffectCtx.choose` (effects.py:162-163) `optional=True` appends `Pick(())`, a decline option, to
the question; picking it runs no continuation at all (effects.py:168-171, no `otherwise` given).

**Match:** no. The script lets the controller decline the self-cost even with legal ready
friendly Units on the board. Since the card is then a 4-cost, 2-RAM Program that does nothing,
the wrong branch is rarely *taken* on purpose — but it is a real difference: the text makes the
loss of a ready friendly Unit compulsory whenever one exists, and here it can be avoided.
Compare the set's mandatory analogue, Les Élémens (wnc.py:71-78), which calls `bottom_deck_one`
with no `optional`.

Direction: **extra** — the script offers a choice (decline) that the printed text does not grant.
Contrast the correctly-optional Gilded Maton / Maman Brigitte / Placide scripts, whose printed
text does say "You may".

## 5. "If you do, …" — the second sentence is conditional on the first actually happening

**Text requires:** the rival-side bottom-deck happens only if a friendly Unit was in fact
bottom-decked. No friendly bottom-deck (no legal target — or, under the script's reading, a
decline) ⇒ no rival bottom-deck.

**Implements:** `then=after` is invoked from inside `_do` (dsl.py:66-69), i.e. only on the branch
where a Unit was actually picked and bottom-decked. With an empty candidate list,
`choose` returns immediately without a continuation (effects.py:157-160, no `otherwise`), so
`after` never runs. On a decline, `_cont` runs neither `cont` nor `otherwise`
(effects.py:168-171), so `after` never runs either.

**Match:** yes — the conditional gating is correct in every branch.

## 6. "bottom-deck a spent rival Unit" — side, count, and state filter

**Text requires:** exactly one target; it must be a Unit, controlled by the rival, and *spent*
(sideways). Mandatory (no "may"), and the controller of Unlikely Bond chooses it.

**Implements:** `bottom_deck_one(c2, [u for u in c2.rival_units() if c2.s.i_spent[u]])`.
`rival_units()` = `units(self.rival)` (effects.py:50-51) — correct side, and correctly *not*
"all units" of both players. `i_spent[u]` is exactly "spent". No `optional`, so
`optional=False` — mandatory, matching the absent "may"; with no spent rival Unit the `choose`
simply finds nothing to ask and the effect does nothing, which is the correct failure mode. The
candidate list is rebuilt from `c2` (the continuation's own ctx), per docs/effects-authoring.md
"the one rule", so it is evaluated after the friendly Unit has left the field — correct, and it
also means the two picks cannot collide.

**Match:** yes.

## 7. No extra effects

**Text requires:** nothing beyond the two bottom-decks — no draw, no ready/spend side effect, no
restriction on which rival Unit beyond "spent".

**Implements:** the script does nothing else.

**Match:** yes.

---

## Verdict

One discrepancy: clause 4. The friendly-side bottom-deck is written with `optional=True`
(wnc.py:86) although the printed instruction "Bottom-deck a ready friendly Unit." carries no
"may". Everything else — sides, singular targets, the ready/spent filters, the "If you do"
gating, and the mandatory rival-side bottom-deck — matches the printed text.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-unlikely-bond-1 — kill attempt: FAILED (finding survives)

Card text, byte-exact from `data/cards/wnc.json` (`"verified": true`):

    Bottom-deck a ready friendly Unit. If you do, bottom-deck a spent rival Unit.

Script, `/home/user/cyberpunk-tcg/src/cptcg/cards/sets/wnc.py:86`:

    bottom_deck_one(c, [u for u in c.units() if not c.s.i_spent[u]], optional=True, then=after)

`optional=True` reaches `EffectCtx.choose` (`/home/user/cyberpunk-tcg/src/cptcg/core/effects.py:162`), which
appends a bare `Pick(())` decline option. The player may therefore play the card, be shown the
prompt, and decline — an out the printed text never grants.

## The five kill routes, each tried

**1. A ruling deliberately covers it.** No. I read all 41 rows of `docs/rulings.md`. The usual
suspects are untouched: 012 (BLOCKER redirect scope), 015 (GO SOLO slot vacation), 019 (once-per-turn
scope), 025 (payment order), 026 (field limit), 030 (⊡ on Gear). Nothing in the table addresses
optionality of an effect's own action, "may" vs. no "may", or a player's right to decline a
self-harming mandatory effect. Row 022 defines bottom-deck ordering only. There is no
`RulesConfig` knob in play here, so this is not a recorded default — it is an unrecorded choice in
one card script.

**2. The engine already handles it.** No — the engine handles the *opposite*. `steps.AskStep.run`
(`/home/user/cyberpunk-tcg/src/cptcg/core/steps.py:48-50`) resolves a one-option choice inline
("no real decision"). With `optional=False` and a single ready friendly Unit, the bottom-deck would
fire automatically with no prompt; `optional=True` is what manufactures the second option and stops
it. `core/ops.py`, `core/legal.py` and `core/effects.py` contain no compensating rule that forces a
declined mandatory effect. The decline is real, not an artifact of the test harness.

**3. The board is unreachable.** No. The audit board is byte-identical to the board in the
long-standing green test `tests/cards/test_programs.py:68-72` (`psycho-squad` ready on our field,
`corpo-security` spent on the rival's). A rival Unit stays spent through our turn after attacking —
Start Phase step 1 readies only the active player's cards (`docs/rules.md`, Start Phase). The only
non-game-like detail is `E = 9` eddies, the suite-wide "plenty of eddies" convention used by every
card test in the repo, and it is immaterial to the assertion.

**4. The test asserts an internal.** No. It asserts two zones, `s.i_zone[...] == Zone.DECK` for both
Units — exactly the printed outcome, no script state, no `optional` flag, no prompt text.

**5. The finding misreads a word.** No. I checked the raw JSON: there is no "You may". The rider
"If you do" is not evidence of an implied "may" in this set — it is the standard guard for an
action that can fail to happen. The same set prints the identical mandatory shape on
`panam-palmer-strength-through-family` ("ATTACK: Discard 1. If you do, draw 1 for each friendly
face-up Legend."), and that card is scripted mandatory: `c.discard(1, cont=after)` with an
`if picks:` guard for an empty hand (`wnc.py:641-647`). Every *optional* card in the set spells it
out — "You may defeat a friendly Gear. If you do, ...", "You may discard 2 Programs. If you do, ...",
"You may pay 2 €$. If you do, ...". Unlikely Bond is the lone "If you do" card with no "may", and
under the mandatory reading the rider still does work: with no ready friendly Unit you do not do it,
`choose` sees an empty candidate list and returns (`effects.py:157-160`), and the rival bottom-deck
correctly does not happen. Ruling 023's precedent (printed text beats the docs) points the same way.

## Verification run

    python -m pytest 'tests/cards/audit/test_a01.py::test_unlikely_bond_first_bottom_deck_is_not_optional' -q -rx
    XFAIL — AUD-unlikely-bond-1

XFAIL, so the engine does behave as the filer claims: with one ready friendly Unit the effect stops
and asks instead of resolving. Given `AskStep.run`'s one-option shortcut, deleting `optional=True`
on `wnc.py:86` makes both assertions pass, and the pre-existing `test_unlikely_bond` would need its
now-superfluous `do(s, Pick((0,)))` removed (the pick becomes automatic).

## Verdict

Survives. Classification **B4-scope-or-condition**: the script gates a printed-mandatory action
behind a player consent the card does not print.
