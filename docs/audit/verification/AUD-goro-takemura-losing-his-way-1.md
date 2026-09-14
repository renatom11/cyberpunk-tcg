<!-- Working record for AUD-goro-takemura-losing-his-way-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Goro Takemura — Losing His Way  (`goro-takemura-losing-his-way`)

- type: UNIT, colour: GREEN, cost: 4, power: 4, RAM: 3
- keywords: none
- tags: ['ARASAKA', 'CORPO']

## Printed text (byte-exact from data/cards/wnc.json)

```
ATTACK: If all friendly Legends are face-up, this Unit has +5 power this turn.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 680-685

@script("goro-takemura-losing-his-way")
def _():
    return CardScript(on_attack=lambda c: c.temp_power(c.inst, 5)
                      if c.legends() and all(c.s.i_faceup[l] for l in c.legends()) else None)
```

---

# The finding, and the test that failed

# AUD-goro-takemura-losing-his-way-1

card: `goro-takemura-losing-his-way`

claim: with an empty Legends area 'all friendly Legends are face-up' is vacuously true, but the script requires at least one Legend

failing test: `tests/cards/audit/test_a07.py::test_goro_gets_the_bonus_with_an_empty_legends_area`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Goro Takemura, Losing His Way (`goro-takemura-losing-his-way`)

Printed text (data/cards/wnc.json, id `goro-takemura-losing-his-way`):

```
ATTACK: If all friendly Legends are face-up, this Unit has +5 power this turn.
```

Implementation (src/cptcg/cards/sets/wnc.py:680-684):

```python
@script("goro-takemura-losing-his-way")
def _():
    return CardScript(on_attack=lambda c: c.temp_power(c.inst, 5)
                      if c.legends() and all(c.s.i_faceup[l] for l in c.legends()) else None)
```

## 1. `ATTACK:` — trigger timing

Requires: the effect fires when this Unit attacks, after the target is declared and the attacker is
spent (ruling 023 overrides the older guide wording; rules.md line 128 and the keyword table line 82).

Implemented by: `CardScript(on_attack=...)`. `ops.push_trigger` (src/cptcg/core/ops.py:531-540)
maps `Trigger.ATTACK` to `sc.on_attack` and pushes a `HookStep`; the engine's attack flow is the one
shared by every ATTACK card, so declaration order is ruling-023 behaviour, not something this card
chooses. `c.inst` is the attacking Unit itself, and the hook only fires for the attacker (there is no
defender path into `Trigger.ATTACK`).

Match: yes.

## 2. `If all friendly Legends are face-up` — the condition, side

Requires: look at the Legends of *this card's controller only* (friendly), not the Rival's, and not
both.

Implemented by: `c.legends()` — `EffectCtx.legends` (src/cptcg/core/effects.py:55-59) defaults
`player` to `self.player`, which is `s.i_owner[inst]` (effects.py:22-24), i.e. the Unit's own side.
`GameState.legends` (src/cptcg/core/state.py:214-216) returns the cards in that player's Legends area,
excluding Gear equipped to them. No card in this set transfers control (no "gain control"/"control of"
text in data/cards/wnc.json), so owner == controller.

Match: yes — friendly-only, Legends-area only.

## 3. `... are face-up` — the face-up test

Requires: every one of those Legends is face-up (Called), not face-down.

Implemented by: `all(c.s.i_faceup[l] for l in c.legends())`. `i_faceup` is the same flag
`ops.call_legend` sets to 1 when a Legend is Called (ops.py:545), and the same flag
`effects.legends(faceup=...)` and `ops.can_call_free` read. Face-down Legends have 0, so a single
face-down Legend correctly suppresses the bonus.

Match: yes.

## 4. `... all friendly Legends ...` — what happens with **zero** friendly Legends (the guard)

Requires: "all X are face-up" over an empty set is vacuously true, so with no Legends in the friendly
Legends area the condition is satisfied and the Unit gets +5. Nothing in the printed text, in
docs/rules.md, or in docs/rulings.md carves out an exception (contrast ruling 038, where the rules
explicitly declare Street Cred *Null* with no Gigs — there is no analogous ruling for Legends, and
docs/effects-authoring.md states no house convention for "all" conditions; this is the set's only
"If all ..." card, so there is no sibling script to compare against).

Implemented by: `c.legends() and all(...)`. The leading truthiness test makes the empty Legends area
evaluate **False**, so the script grants nothing where the text grants +5.

Is the empty case reachable? Yes, though rare. Ruling 015 (`go_solo_vacates_slot` = true): a GO SOLO
Legend played to the field vacates its Legend slot, and `GameState.legends` only scans
`Zone.LEGENDS`, so it stops counting. Ruling 034: a Legend that leaves the Legends area or field is
removed from the game (e.g. Jackie Welles *Mama's Favorite* defeating itself as a replacement), so the
slot never refills. Getting all three Legends out of the area is an extreme board, but the same guard
also means the engine's answer diverges from the printed text there, deterministically.

Match: **no** — the script adds a "you must control at least one Legend" precondition that the card
does not print. Direction: an extra condition, i.e. the effect is withheld in a case the text allows.

Severity note: this is the only divergence I found, and it only bites on a board with zero friendly
Legends in the Legends area.

## 5. `this Unit has +5 power` — subject and amount

Requires: +5, applied to this Unit (the attacker), not to a chosen or other Unit.

Implemented by: `c.temp_power(c.inst, 5)` → `ops.add_temp_power(s, inst, 5, cond=0)`
(effects.py:314-315, ops.py:423-424). Amount 5 matches; subject `c.inst` is this card.

Match: yes.

## 6. `... this turn` — duration and unconditionality

Requires: the bonus lasts for the rest of the turn and applies in every situation (attacking, fighting,
vs Unit, vs Legend, and to any other reading of its power), not only during this attack.

Implemented by: `cond` defaults to 0. `ops.power` (ops.py:409-412) adds a temp entry when
`cond == 0 or sit & cond == cond`, so `cond == 0` means unconditional in all situations — correct for
plain "this turn" wording. `EndTurnCleanupStep` (src/cptcg/core/steps.py:179) clears `s.temp_power` at
end of turn, so the bonus expires exactly at end of turn; ops.py:213-214 strips a card's temp power when
it leaves play (CR 5.3.2.2), which is general engine behaviour, not a card-specific deviation.
The bonus is locked in at trigger time and does not re-check if a Legend changes later — matching
"If ... , this Unit has +5 power this turn" as a one-shot conditional grant.

Match: yes.

## 7. Other clauses

There is no "may", no "up to N", no choice, and no second sentence conditional on the first, so no
prompt/continuation questions arise. Only one script is registered for this id (single `@script`
occurrence in src/cptcg/cards/sets/wnc.py); no override elsewhere.

## Conclusion

Six of seven readings match. The single discrepancy is the `c.legends() and` guard in section 4:
with zero friendly Legends the printed condition is vacuously true and should grant +5, but the script
grants nothing.

---

# Skeptic 2 — told the finding is presumed wrong

# Kill attempt — AUD-goro-takemura-losing-his-way-1

**Verdict: survives, classified A (genuine ambiguity). I could not refute it.**

Card: `goro-takemura-losing-his-way` — *"ATTACK: If all friendly Legends are face-up, this Unit has
+5 power this turn."*
Script (current lines, `src/cptcg/cards/sets/wnc.py:743-746`):

```python
return CardScript(on_attack=lambda c: c.temp_power(c.inst, 5)
                  if c.legends() and all(c.s.i_faceup[l] for l in c.legends()) else None)
```

The `c.legends() and` conjunct is an unwritten clause — "…and you control at least one Legend". That
part of the finding is a fact about the source, not an interpretation.

Test run just now:
`tests/cards/audit/test_a07.py::test_goro_gets_the_bonus_with_an_empty_legends_area` → **XFAIL**
(power 4, not 9), i.e. the engine does behave as the filer says.

## The five kill routes, tried

**1. A ruling covers it — NO.** I read every row of `docs/rulings.md`. None addresses a universal
over an empty collection. The two that touch this card's neighbourhood do not shield the script:

* **015** (`go_solo_vacates_slot` = true, Uncertain) is *relied on* by the finding, not contradicted —
  it is what says the slot sits empty. The presumed-deliberate trap on 015 would apply to a finding
  that argued the slot should stay occupied; this one argues nothing about the slot.
* Worse for the shield: the empty area does not even depend on 015's coin-flip. **034**
  (`legends_removed_when_leaving`, Settled, CR 4.4.1) removes any Legend that leaves the Legends area
  by any route, implemented at `src/cptcg/core/ops.py:188-190`; Jackie Welles — *Mama's Favorite*
  prints "defeat this Legend instead. (Remove it from the game.)", a non-GO-SOLO way to empty a slot.
  So flipping 015 to the other branch would not make this state go away.
* **038** (null Street Cred with no Gigs) is the only "degenerate empty collection" precedent in the
  docs, and it cuts *against* the script, not for it: with an empty Gig area a comparison still
  resolves ("smaller than 0 when compared" — Towerfall's "less ★ than a Rival" is true with no Gigs).
  The game's own convention for an empty collection is a defined answer, not an automatic failure.

**2. The engine already handles it — NO.** `wnc.py:746` is the only grant of this +5. `EffectCtx.legends`
(`core/effects.py:55-59`) delegates to `GameState.legends` (`core/state.py:214-216`), which is exactly
the owner's `LEGENDS` zone; nothing in `core/ops.py`, `core/steps.py` or `core/legal.py` adds power for
this card. `grep -rn "goro-takemura-losing"` over `src/` returns the one script line.

**3. The board is unreachable — NO.** Three checks, all pass:
* *Zone-legality*: `ops.py:450` sends a GO SOLO Unit to `Zone.REMOVED` when it leaves the field and
  `ops.py:188` removes any Legend leaving the Legends area, so an empty Legends area is a state the
  engine itself produces.
* *Deckbuilding*: Goro *Losing His Way* is Green RAM 3, so the deck needs ≥3 cumulative Green RAM,
  i.e. two Green Legends. Both costed Green Legends — Goro Takemura *Hands Unclean* (5, GO SOLO) and
  Jackie Welles *Mama's Favorite* (6, GO SOLO) — are RAM 2, giving 4 Green RAM, and the third slot can
  be any other costed GO SOLO Legend (unique names hold). All three can therefore leave the area.
* *Test-harness convention*: the only artificial thing about the board is `board()`'s default
  `turn=3`, at which nobody could have paid three GO SOLO costs. But `turn` is decorative throughout
  this suite — `docs/effects-authoring.md`'s own example builds `eddies=9` at the same default turn —
  so the same objection would void most card tests. Killing on it would be sophistry.

**4. The test asserts an internal — NO.** It asserts `power(s, u) == 9` after a real `Attack` action.
That is a printed-text outcome (effective power), reviewable by anyone holding the card.

**5. The expectation misreads a word — the only live route, and it ends in a draw.** The whole
dispute is the empty case of "all":
* *For the filer*: a universal over an empty domain is true, which is the convention every major TCG
  uses, and the set demonstrably knows how to write the counting alternative when it wants one —
  Panam Palmer "for each friendly face-up Legend", Synapse Burnout, Zetatech Berserk all degrade to 0
  with no Legends without needing a guard. Goro is the pool's only "if all …" gate (checked over
  every text in `data/cards/wnc.json`), so there is no sibling card whose scripting settles it.
* *For the script*: "if all friendly Legends are face-up" can be read as presupposing Legends you
  have, and the design intent plainly rewards Calling your Legends rather than losing them.

Nothing in the printed text, `docs/rules.md` (whose Legends-area entry only says "Your 3 Legends"),
or `docs/rulings.md` decides between those two readings, and ruling 038 — the nearest analogy —
leans toward the filer. I cannot show the finding misreads the card.

## What I am left with

The script does add an unwritten existence requirement, on a board a real game can reach, and no
rule, ruling or line of code justifies it. That is not a kill. It is also not a B-class defect: the
reading the script implements is defensible from the same sentence, so the honest landing is **A —
genuine ambiguity**, which is where the original audit (`out/audit/a07/findings.md:195`) put it too.
If the ambiguity is resolved toward the standard TCG convention, the fix is to drop the `c.legends()
and` conjunct (it would be B4, scope/condition); until someone rules, the xfail test is the correct
record and no code should change on my say-so.
