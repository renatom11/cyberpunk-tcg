<!-- Working record for AUD-placide-voodoo-sentinel-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Placide — Voodoo Sentinel  (`placide-voodoo-sentinel`)

- type: UNIT, colour: BLUE, cost: 8, power: 10, RAM: 2
- keywords: none
- tags: ['GANGER', 'NETRUNNER', 'VOODOO BOYS']

## Printed text (byte-exact from data/cards/wnc.json)

```
PLAY / ATTACK: You may discard 1 Program. If you do, bottom-deck a rival Unit.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 588-601

@script("placide-voodoo-sentinel")
def _():
    def eff(c):
        progs = hand_of_type(c, PROGRAM)

        def yes(c2):
            from cptcg.core.ops import discard
            c2.choose(hand_of_type(c2, PROGRAM),
                      lambda c3, i: (discard(c3.s, i), bottom_deck_one(c3, c3.rival_units())), prompt="Discard")
        if progs and c.rival_units():
            c.maybe(yes, prompt="Discard a Program to bottom-deck a rival Unit?")
    return CardScript(on_play=eff, on_attack=eff)
```

---

# The finding, and the test that failed

# AUD-placide-voodoo-sentinel-1

card: `placide-voodoo-sentinel`

claim: the 'you may discard 1 Program' offer is suppressed when the rival controls no Units, although the bottom-deck is a separate 'if you do' rider

failing test: `tests/cards/audit/test_a06.py::test_placide_may_discard_a_program_with_no_rival_units`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Placide, Voodoo Sentinel (`placide-voodoo-sentinel`)

Printed text (byte-exact):

```
PLAY / ATTACK: You may discard 1 Program. If you do, bottom-deck a rival Unit.
```

Script (src/cptcg/cards/sets/wnc.py:588-601):

```python
def eff(c):
    progs = hand_of_type(c, PROGRAM)

    def yes(c2):
        from cptcg.core.ops import discard
        c2.choose(hand_of_type(c2, PROGRAM),
                  lambda c3, i: (discard(c3.s, i), bottom_deck_one(c3, c3.rival_units())), prompt="Discard")
    if progs and c.rival_units():
        c.maybe(yes, prompt="Discard a Program to bottom-deck a rival Unit?")
return CardScript(on_play=eff, on_attack=eff)
```

## 1. "PLAY / ATTACK:" — two timing triggers

Requires: the whole effect fires when this Unit is played (PLAY) and when it attacks (ATTACK,
after the target is declared, per ruling 023 / CR 9.3).

Implemented by `CardScript(on_play=eff, on_attack=eff)` (line 601). `ops.push_trigger`
(src/cptcg/core/ops.py:532-540) dispatches both hooks as one-argument `HookStep`s, so both
timings run the identical body. Empirically confirmed: playing Placide queues the prompt, and
attacking with Placide queues it after the "Declare a target" choice resolves (correct per
ruling 023, which places ATTACK triggers after target declaration).

**Match.**

## 2. "You may discard 1 Program."

Requires: an optional (may) discard, by *you* (Placide's controller), of exactly one card,
which must be a Program, from your hand (rules.md glossary: discard = hand to trash), chosen by
you. The permission is stated unconditionally — the only natural precondition is owning at
least one Program to discard.

Implemented by:
- `progs = hand_of_type(c, PROGRAM)` (dsl.py:52 → `c.hand()` defaults to `c.player`): your hand,
  Programs only. Correct side and zone.
- `c.maybe(yes, ...)` (effects.py:208) → `choose([True], ..., optional=True)` — a yes/no asked of
  `self.player` (Placide's controller). Correct "may".
- Inside `yes`, `c2.choose(hand_of_type(c2, PROGRAM), ...)` — non-optional, exactly one pick, so
  saying "yes" commits you to discarding exactly one Program of your choice; `ops.discard`
  (ops.py:264) moves it to the trash and emits the `discard` event. Correct "1 Program".
- The continuations correctly use the ctx they are given (`c2`, `c3`), per docs/effects-authoring.md.

**Mismatch — the guard on line 597.** The prompt is only offered when
`progs and c.rival_units()`. The `progs` half is fine (with no Program you cannot pay). The
`c.rival_units()` half is an extra condition the printed text does not state: when the rival
controls no Units, the player is never offered the "may discard" at all. Verified by running the
card: with a Program in hand and an empty rival field, playing Placide queues no choice and the
Program stays in hand; with a rival Unit on the field the prompt appears.

That is a real, not merely cosmetic, difference: discarding a Program is itself a resource move
in this set (e.g. the trash-recursion cards at wnc.py:1137 "add a BRAINDANCE Program from your
trash" and wnc.py:1322 "play a Program from your trash" want Programs in the trash), so "may
discard with no rival Unit on board" is a legal, sometimes desirable line that the script
removes. Note the sibling card built on the same template, Maman Brigitte (wnc.py:478-495),
gates only on having the Programs to discard and lets the follow-up fizzle on its own — so the
codebase's own convention is not to gate the cost on target availability.

## 3. "If you do, bottom-deck a rival Unit."

Requires: strictly conditional on the discard actually happening; then a mandatory bottom-deck
of one Unit controlled by the rival, chosen by you, onto the bottom of its owner's (the
rival's) deck.

Implemented by the lambda at line 596: `(discard(c3.s, i), bottom_deck_one(c3, c3.rival_units()))`.
- Conditionality: the bottom-deck lives inside the discard continuation, so declining the
  `maybe` does nothing at all (verified: decline leaves the Program in hand and the rival Unit
  on the field). Correct "if you do".
- Mandatory: `bottom_deck_one` (dsl.py:65) calls `c.choose(..., optional=False)` — no decline
  option. Correct (the text is not "you may").
- "a rival Unit", singular, any of them: candidates are `c3.rival_units()` (effects.py:52 →
  `s.units(1 - controller)`, which excludes attached Gear). Verified with friendly Units on
  board: only the two rival Units were offered. Chooser defaults to `self.player`, i.e. you.
- Destination: `ops.bottom_deck` → `move(..., Zone.DECK, bottom=True)` moves the card to *its
  owner's* deck and inserts at index 0, which ruling 022 defines as the bottom. Verified: the
  chosen rival Unit ends at the bottom of the rival's deck.

**Match.**

## 4. Cross-cutting checks

- No "once per turn" is printed and none is implemented — correct.
- The effect is not restricted by Lag, spent state, or power — nor is the script.
- Both triggers share the same body, so the ATTACK use is also subject to the clause-2 guard:
  attacking a Gig area while the rival has no Units likewise never offers the discard.
- Chosen-option counts, prompts, and side-of-board were confirmed by running the real engine
  (registry `load_default()`, the test `board()` helper) on four scenarios: no rival Units, one
  rival Unit, two rival Units + two Programs + friendly Units, and a declined prompt.

## Conclusion

One discrepancy: the optional discard is gated on the rival controlling at least one Unit, a
condition the printed text does not impose. Everything else — both triggers, the "may", the
1-Program cost from your own hand, the strict "if you do" dependency, the mandatory single
rival-Unit bottom-deck to the owner's deck bottom — is faithful.

---

# Skeptic 2 — told the finding is presumed wrong

# Kill attempt — AUD-placide-voodoo-sentinel-1

**Verdict: SURVIVES.** Classification: **B4 — scope/condition** (the printed permission is
implemented, but gated behind a condition the card does not print).

Card text (byte-exact, `data/cards/wnc.json`):

> `PLAY / ATTACK: You may discard 1 Program. If you do, bottom-deck a rival Unit.`

Implementation, `src/cptcg/cards/sets/wnc.py:597`:

```python
if progs and c.rival_units():
    c.maybe(yes, prompt="Discard a Program to bottom-deck a rival Unit?")
```

Test result: `XFAIL` (strict) — the engine really does suppress the offer.

## Route 1 — a ruling deliberately covers it: NO

`docs/rulings.md` has 41 rows and none of them is about optional effects, "you may" offers, or
riders whose target is absent. The six usual suspects were checked individually:

- **012** BLOCKER redirect scope — reactions, not PLAY/ATTACK offers.
- **015** GO SOLO slot vacation — Legend slots.
- **019** once-per-turn scope — counter reset timing; Placide's offer is not once-per-turn.
- **025** payment order — the closest thing to a "don't offer pointless branches" precedent, and
  it does not reach here. 025 is scoped to *cost payment* and rests on the explicit premise that
  the branches are indistinguishable: "no card ever reads the identity of a card sitting in an
  Eddies area." Discarding a Program is not indistinguishable — it moves a card from hand to
  trash, and this set has three printed cards that read the trash for Programs:
  `alt-cunningham-soulkiller-architect` ("1 €$, ⊡: Play a Program from your trash"),
  `lizzy-wizzy-delicate-weapon` ("play a Program with cost 3 or less from your hand or trash for
  free") and `v-streetkid` ("add 1 BRAINDANCE Program from your trash to your hand"). All three
  verified present in `data/cards/wnc.json`. So the suppressed branch is a real line, and 025's
  reasoning argues *against* the gate, not for it.
- **026** field limit / **030** ⊡ on Gear — unrelated.

`docs/rules.md` was read end to end: it contains no rule that an optional action may be taken
only when its consequence can be applied, and no "do as much as possible" rule.

## Route 2 — the engine already handles it: NO

The gate is card-local. `EffectCtx.maybe` (`src/cptcg/core/effects.py:208-226`) is never reached,
so nothing downstream can re-open the question: `maybe` delegates to `choose(..., optional=True)`,
and `choose` (`effects.py:144-160`) only ever *removes* options for an empty candidate list — it
never adds a question a script declined to ask. `ops.py`, `steps.py` and `legal.py` contain no
pass that re-offers a card's own skipped "may". Grepping for a deliberate offer-suppression
policy (`branching|no-op|pointless|nothing to do|degenerate`) across `wnc.py`, `effects.py`,
`ops.py`, `steps.py`, `legal.py` returns exactly one hit — `ops.py:270`, the ruling-025 payment
comment — and nothing about card offers.

## Route 3 — unreachable board: NO

`board(pool, Side(hand=["placide-voodoo-sentinel", "floor-it"], eddies=9, deck=["floor-it"]), Side())`
is a rival with an empty field. That is the single most ordinary state in the game — the opening
turns, or any turn after a sweep. The controller has 9 €$ for an 8-cost Unit and one Program
(Floor It) in hand. Nothing here is contrived.

## Route 4 — asserts a script internal: NO

The asserts are `s.pending.kind is ChoiceKind.PICK and s.pending.player == 0`, then
`do(s, Pick((0,)))`, then `s.i_zone[find(s, "floor-it", player=0)] == Zone.TRASH`. `ChoiceKind`
(`src/cptcg/core/actions.py:18-25`) makes `PICK = 6` distinct from `MAIN = 3`, so the first
assert is a genuine legal-action claim ("an effect question is pending for me"), not a
main-menu tautology, and the load-bearing assert is a zone. No mods, no flags, no internals.

## Route 5 — misreads the text: NO — and the set's own twin settles it

The permission attaches to the first sentence alone: "You may discard 1 Program." The
bottom-deck is a separate sentence hanging off "If you do", i.e. a rider conditioned on the
discard having happened, not a precondition on being asked.

Decisive: this set prints the same sentence shape twice, and the *other* copy is scripted the
way the finding asks for. `maman-brigitte-spirit-of-death` — "PLAY: You may discard 2 Programs.
If you do, bottom-deck a rival unequipped Unit." — at `wnc.py:528-544` gates only on having the
Programs (`if len(progs) < 2: return`) and then calls `c.maybe(yes, ...)` unconditionally; the
rider falls off harmlessly because `bottom_deck_one` (`src/cptcg/cards/dsl.py:65-70`) routes an
empty candidate list into `choose([])`, which returns without asking. `gilded-maton`
(`wnc.py:474-481`, "You may defeat a friendly Gear. If you do, defeat a rival Unit with cost 3 or
less") does the same: `optional=True` on the Gear choice, no gate on rival Units existing.
`unlikely-bond` (`wnc.py:87-98`) carries a comment spelling out this set's convention — "'If you
do' is this set's standard guard for an action that can fail to happen ... not evidence of an
implied 'may'." Placide's extra `and c.rival_units()` is the outlier, not the house style.

## Conclusion

Every route is closed. The printed text conditions the offer on nothing but the player's
willingness to discard a Program; `wnc.py:597` adds `and c.rival_units()`, a condition that is
not on the card, is not in `docs/rules.md`, is not settled by any row of `docs/rulings.md`, and
is contradicted by the identically-worded `maman-brigitte-spirit-of-death` in the same file.
The finding stands as B4 (scope/condition). The minimal fix is to drop `and c.rival_units()`;
`bottom_deck_one` already no-ops on an empty list, so no other change is needed.
