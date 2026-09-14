<!-- Working record for AUD-cyberpsychosis-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Cyberpsychosis  (`cyberpsychosis`)

- type: PROGRAM, colour: YELLOW, cost: 3, power: None, RAM: 2
- keywords: ['QUICK']
- tags: ['QUICKHACK']

## Printed text (byte-exact from data/cards/wnc.json)

```
QUICK: Give an equipped Unit +3 power this turn for each of its equipped Gears. If that Unit steals or fights, defeat it at the end of this turn.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 318-333

@script("cyberpsychosis")
def _():
    def play(c):
        def give(c2, u):
            c2.temp_power(u, 3 * len(c2.gear(u)))

            def listen(s, ev):
                # "If that Unit steals or fights, defeat it at the end of this turn."
                if ev[0] in ("steal", "fight_won", "fight_lost") and ev[1] == u \
                        and not s.has_mod("defeat_at_end", u):
                    s.add_mod("defeat_at_end", u)
            c2.mod("listener", c2.player, listen)
        c.choose([u for p in (0, 1) for u in c.units(p) if c.equipped(u)], give, prompt="Equipped Unit")
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-cyberpsychosis-1

card: `cyberpsychosis`

claim: 'if that Unit ... fights' is implemented as fight_won/fight_lost, and a tied fight dispatches neither, so a Unit that survives a tie is never defeated at end of turn

failing test: `tests/cards/audit/test_a03.py::test_cyberpsychosis_defeats_a_unit_that_fought_to_a_tie`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Cyberpsychosis (`cyberpsychosis`)

Printed text (byte-exact):

> QUICK: Give an equipped Unit +3 power this turn for each of its equipped Gears. If that Unit steals or fights, defeat it at the end of this turn.

Implementation: `src/cptcg/cards/sets/wnc.py` lines 318-333.

```python
@script("cyberpsychosis")
def _():
    def play(c):
        def give(c2, u):
            c2.temp_power(u, 3 * len(c2.gear(u)))

            def listen(s, ev):
                if ev[0] in ("steal", "fight_won", "fight_lost") and ev[1] == u \
                        and not s.has_mod("defeat_at_end", u):
                    s.add_mod("defeat_at_end", u)
            c2.mod("listener", c2.player, listen)
        c.choose([u for p in (0, 1) for u in c.units(p) if c.equipped(u)], give, prompt="Equipped Unit")
    return CardScript(on_play=play)
```

---

## 1. "QUICK:" — playable as a reaction when a rival Unit attacks

**Requires.** The Program may also be played during the defender's reaction window
(rules.md, Keywords table; Attacking step 3).

**Implements.** Nothing in the script — the keyword is data (`keywords: ['QUICK']`) and
`src/cptcg/core/legal.py:196` adds `PROGRAM` cards carrying `Keyword.QUICK` to the reaction menu.

**Verdict.** Match. Verified live: with a rival Unit attacking, the defender's reaction menu offered
`Play(cyberpsychosis)` and resolving it pumped the defending Unit before the fight.

## 2. "Give an equipped Unit ..." — one Unit, mandatory, must have Gear, either side

**Requires.** Exactly one Unit ("an", not "all"); it must be *equipped*, i.e. have at least one Gear
on it; the effect is mandatory ("Give", no "may"). The noun is **unqualified** — no "friendly", no
"rival" — so any Unit on the field is eligible.

**Implements.** Line 330: `c.choose([u for p in (0, 1) for u in c.units(p) if c.equipped(u)], give, ...)`.
`EffectCtx.units(p)` (effects.py:56) returns `state.units(p)` — non-Gear, non-hosted cards in that
player's FIELD, so GO SOLO Legends on the field count as Units, which is right. `equipped()`
(effects.py:70) is `bool(gear_on(inst))`. The `choose` is not `optional=True`, so no decline option;
with no candidates `choose` simply does nothing (effects.py:150), which is correct — there is no
"that Unit" for the second sentence either.

**Side check.** The set is scrupulous about saying "friendly"/"rival" when it means one side
(13+ cards say "a friendly Unit", 8+ "a rival Unit", including the near-twin Dum Dum ability
"Give a **friendly** Unit +1 power this turn for each of its equipped Gear"). Cyberpsychosis says
neither, and the house convention for an unqualified noun is both sides: Over the Edge
("Defeat a Unit …") → `[u for p in (0, 1) …]` (wnc.py:47) and Heywood Ripperdoc ("You may defeat a
Gear") → `c.all_gear(0) + c.all_gear(1)` (wnc.py:460). Rival Units can genuinely be equipped
(Kiroshi Optics: "Equip to a Unit or friendly face-up Legend"), so the wider reading is meaningful.

**Verdict.** Match. Verified live: with one equipped Unit on each side, the prompt offered 2 options.

## 3. "+3 power this turn for each of its equipped Gears"

**Requires.** +3 × (number of Gears equipped to *that Unit*), lasting until end of turn.

**Implements.** Line 321: `c2.temp_power(u, 3 * len(c2.gear(u)))` → `ops.add_temp_power` with
`cond=0`, i.e. unconditional (not only while attacking/fighting). `gear(u)` is `state.gear_on(u)`,
the Gear hosted by that Unit only — not the controller's total Gear. `ops.power` (ops.py:409) adds
every `temp_power` entry whose `cond` is 0, and `EndTurnCleanupStep` (steps.py:179) does
`s.temp_power.clear()`, so the bonus expires exactly at end of turn.

The count is snapshotted when the effect resolves rather than recomputed continuously; that matches
the house reading of the same phrase on Dum Dum (`temp_power(u, len(c2.gear(u)))`, wnc.py:1197) and
the wording "Give … +3 power this turn" (a one-shot grant) as opposed to Royce *Psycho on the Edge*'s
static "has +2 power for each of its equipped Gear".

**Verdict.** Match. Verified live: Animals Wrecker (10) + Mantis Blades (2) reads 15 after the pump.

## 4. "If that Unit steals ..."

**Requires.** A steal performed by the pumped Unit (and only that Unit) arms the end-of-turn defeat.

**Implements.** The listener fires on `("steal", unit, thief, sides, value)` with `ev[1] == u`.
`do_steal` (steps.py:308) dispatches one such event per die actually moved; an attack that steals
nothing (power 0, `steal_fewer`, an emptied Gig area per ruling 009) dispatches nothing, which is
the correct reading of "steals". The `not s.has_mod("defeat_at_end", u)` guard only suppresses
duplicate mods.

**Verdict.** Match. Verified live: pumped Unit attacked the Gig area, stole, and hit the trash at
end of turn.

## 5. "... or fights"

**Requires.** The Unit taking part in a fight — as attacker or as defender, won, lost **or tied** —
arms the end-of-turn defeat.

**Implements.** The listener also accepts `("fight_won", unit, loser, margin)` and
`("fight_lost", unit, winner)`, in both of which `ev[1]` is the Unit in question, so attacker and
defender are both covered. Verified live in both roles (attacker that won a fight, and a defender
pumped by a QUICK reaction that won the fight — both were defeated at end of turn).

**Gap.** `steps.fight()` (steps.py:383-388) dispatches those two events **only** when someone wins:

```python
if a_wins:   dispatch fight_won a / fight_lost t
elif t_wins: dispatch fight_won t / fight_lost a
```

A tie (`pa == pt`) dispatches neither, so the listener never arms `defeat_at_end` even though the
Unit did fight. Normally a tie defeats both Units anyway (rules.md: "on a tie they defeat each
other"), so the omission is invisible — but a fight-protection effect makes it observable:
Reboot Optics (`next_fight_no_defeat`, wnc.py:310) or Muamar Reyes *El Capitan*
("A friendly Unit can't be defeated in a fight this turn", `no_defeat_in_fight`, wnc.py:1178).

Reproduced: Animals Wrecker + Mantis Blades pumped to 15, Reboot Optics played, attacks a spent
Adam Smasher *Metal Over Meat* (15). Tie → Adam Smasher is trashed, my Unit survives, and at
`EndTurn` my Unit is **still on the field**. The printed text says it fought, so it should have
been defeated at the end of that turn.

**Verdict.** Mismatch (narrow): the implemented condition is "wins or loses a fight", the printed
condition is "fights".

## 6. "... defeat it at the end of this turn."

**Requires.** The defeat is deferred to the end of the turn in which the card was played (not
immediate), and it applies to that Unit whichever side controls it.

**Implements.** `s.add_mod("defeat_at_end", u)` with the default `turns=0`, i.e. expiry `s.turn`.
`EndTurnStep` (steps.py:165-169) pushes the cleanup step, then defeats every instance carrying a
`defeat_at_end` mod, and only afterwards does `EndTurnCleanupStep` drop expired mods — so the mod is
still present when it is read. `ops.defeat` no-ops on a card that already left play, so a Unit that
died in its fight is not defeated twice. The listener mod itself also lives until the same cleanup,
so it can still fire late in the turn.

For a QUICK play on the rival's turn, "this turn" is that rival's turn: `EndTurnStep` runs at the
end of the current turn either way — verified live (pumped defender defeated at the end of the
rival's turn).

**Verdict.** Match.

---

## Summary

Clauses 1, 2, 3, 4 and 6 are faithful, including the side-agnostic targeting (which matches the
printed text's unqualified "an equipped Unit" and the set's own convention for unqualified nouns).

The only discrepancy is in clause 5: "or fights" is implemented as the pair of
`fight_won`/`fight_lost` events, and the engine emits neither for a tied fight, so a pumped Unit
that fights to a draw and survives (Reboot Optics / Muamar Reyes) escapes the end-of-turn defeat the
card imposes. Demonstrated, but it needs an exact power tie plus a fight-protection effect, so it is
a corner rather than a mainline error.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-cyberpsychosis-1 — attempt to kill

Verdict: **survives** (classification B4 — scope/condition too narrow). One real defect in the
filer's *test* (its board is not deck-legal), but it does not save the card: the same failure
reproduces on a board a legal game reaches.

## What the engine actually does

`src/cptcg/core/steps.py:351-388` (`fight`). On a tie `a_wins` and `t_wins` are both `False`, so
control skips both `dispatch(...)` branches:

```python
if a_wins:
    dispatch(s, ("fight_won", a, t, pa - pt)); dispatch(s, ("fight_lost", t, a))
elif t_wins:
    dispatch(s, ("fight_won", t, a, pt - pa)); dispatch(s, ("fight_lost", a, t))
```

`s.emit("fight", a, t, pa, pt)` on line 363 is **log-only** — `GameState.emit`
(`src/cptcg/core/state.py:245`) appends to `self.log` and never reaches a hook or a `listener`
mod (`ops.dispatch`, `src/cptcg/core/ops.py:136-163`). So on a tie no card in the game observes
the fight. The Cyberpsychosis listener (`wnc.py:345-350`) filters on
`("steal", "fight_won", "fight_lost")` and therefore never sets `defeat_at_end`.

Run: XFAIL, failing on the last line (`--runxfail` shows `assert Zone.FIELD == Zone.TRASH` at
test_a03.py:78). Every earlier assertion passes, so the board resolves the tie and the Gear
replacement exactly as the docstring claims.

## The five kill routes, each tried

1. **A ruling covers it.** No ruling mentions the event taxonomy, and the one ruling that touches
   ties runs *against* the card: ruling 010 — "Ties: **both lose** and both are defeated
   (CR 9.17.3)". By the docs a tie is a fight and both participants lose it, so the card's own
   `fight_lost` filter should already be enough; the engine simply never dispatches it. Ruling 010
   is Settled, not Uncertain, so there is no deliberate-approximation shelter here. None of
   012/015/019/025/026/030 is in the neighbourhood.
2. **The engine handles it elsewhere.** It does not. `defeat_at_end` exists in exactly two places:
   set by this script (`wnc.py:354`) and consumed at end of turn
   (`steps.py:167`, `EndTurnStep`). I verified the consumer works — with a non-replacement Gear
   and a decisive fight the Unit is trashed at end of turn; the tie is the only gap.
   (The first control run looked like a second bug, but it was the Deadman Transmitter eating the
   end-of-turn defeat, which is correct behaviour for its printed text.)
   `legal.py` and `ops.py` contain no tie hook; `grep -n fight src/cptcg/core/*.py` finds nothing
   else. `docs/effects-authoring.md:51-52` lists the whole event vocabulary: there is no tie event.
3. **Unreachable board.** This one *does* land — against the test, not the card. The filer's own
   side holds `psycho-squad` (Blue RAM 1), `deadman-transmitter` (Red RAM 3), `cyberpsychosis`
   (Yellow RAM 2) and `floor-it` (Blue RAM 1). Every Legend in the set is RAM 2 and a deck has
   exactly 3 of them (`src/cptcg/deck/validate.py:47-72`, rules.md "Deck building & RAM"), so Red 3
   demands two Red Legends and the single remaining Legend cannot cover both Blue and Yellow —
   4 Legends' worth of RAM in a 3-Legend deck. No card in the set changes control of a Unit or
   hosts Gear on a rival Unit (`legal.gear_hosts`, line 18: friendly Units and own face-up
   Legends), so the side cannot be assembled any other way.
   It does not kill the finding, for two reasons. (a) It is the suite's standing convention, not a
   flaw specific to this test: the same scan flags `test_confirmed_a08.py::test_the_relic_cannot_
   recur_its_own_host` and five other audit tests, and `tests/conftest.py:75-102` hand-builds
   states with no Legends and no deck validation at all. (b) The failure reproduces on a fully
   deck-legal board, which I ran:

   - Me (Yellow Legend): `rockn-rockerboy` (Yellow 1, power 8) spent, `cyberpsychosis` (Yellow 2)
     in hand.
   - Rival (1 Blue + 2 Red Legends): `delamain-cab` (Blue 2, power 4) equipped with
     `deadman-transmitter` (Red 3, power 1).
   - Rival's turn: their Unit attacks my spent Unit; in the defender's reaction window
     (rules.md "Attacking" step 3) I play QUICK Cyberpsychosis on their attacker — printed text
     says "an equipped Unit", unqualified, and the script offers both players' Units.
     4 + 1 + 3 = 8 vs 8 → tie. My Unit is trashed, their Deadman Transmitter takes their Unit's
     defeat, their Unit fought and survived — and `s.mods` still holds only the listener: no
     `defeat_at_end`, and the Unit is on the FIELD after `EndTurn`.

   So the card is wrong on a board built from two legal decks. The test should be rebuilt on that
   board; the finding stands either way.
4. **Asserts an internal.** No. Every assertion is a `Zone` of a card — the tie resolved, the Gear
   trashed, the Unit's whereabouts at end of turn. Printed-text outcomes throughout.
5. **Misreads the printed text.** "If that Unit steals or **fights**, defeat it at the end of this
   turn." The trigger word is *fights*, not *wins* or *defeats*. rules.md "Attacking" step 4 calls
   the whole exchange a Fight — "The higher power Unit defeats the other; on a tie they defeat each
   other" — a tie is a fight that happened, and ruling 010 restates it. There is no word left to
   read differently.

## Corroboration

`tests/cards/audit/test_b02.py:94-98` (`AUD-safety-override-1`) files the identical root cause
against Safety Override and cites ruling 010 for it. Two independent cards hitting the same
`a_wins/t_wins` blind spot is an unimplemented case, not a house ruling.

## Where the fix belongs

Not in `wnc.py`. Ruling 010 says both Units lose a tied fight, so `steps.fight` should dispatch
`("fight_lost", a, t)` and `("fight_lost", t, a)` on a tie (and no `fight_won`); Cyberpsychosis's
existing filter then does the right thing, and `AUD-safety-override-1` is fixed with it.
