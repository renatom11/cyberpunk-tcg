<!-- Working record for AUD-yorinobu-arasaka-steel-dragon-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Yorinobu Arasaka — Steel Dragon  (`yorinobu-arasaka-steel-dragon`)

- type: UNIT, colour: RED, cost: 7, power: 9, RAM: 3
- keywords: none
- tags: ['ARASAKA', 'CORPO']

## Printed text (byte-exact from data/cards/wnc.json)

```
PLAY: You may play a Unit with cost 4 or less from your hand or trash for free. It can attack rival Units this turn.
The first time an ARASAKA Unit is defeated each turn, draw 1.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 566-578

@script("yorinobu-arasaka-steel-dragon")
def _():
    def play(c):
        cands = [i for i in c.hand() + c.trash() if c.is_type(i, UNIT) and (c.d(i).cost or 0) <= 4]
        c.choose(cands, lambda c2, i: c2.play_free(i, then=lambda c3, u: c3.mod("attack_units_now", u)),
                 prompt="Play a Unit for free?", optional=True)

    def ev(c, e):
        if e[0] == "defeated" and e[2] == c.player and "ARASAKA" in c.d(e[1]).tags and c.once("arasaka_defeated"):
            c.draw(1)
    return CardScript(on_play=play, on_event=ev, events=frozenset({"defeated"}))
```

---

# The finding, and the test that failed

# AUD-yorinobu-arasaka-steel-dragon-1

card: `yorinobu-arasaka-steel-dragon`

claim: the defeated-ARASAKA draw is restricted to the controller's own Units, but the printed clause names no side

failing test: `tests/cards/audit/test_a06.py::test_yorinobu_draws_when_a_rival_arasaka_unit_is_defeated`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Yorinobu Arasaka — Steel Dragon (`yorinobu-arasaka-steel-dragon`)

Printed text (byte-exact):

```
PLAY: You may play a Unit with cost 4 or less from your hand or trash for free. It can attack rival Units this turn.
The first time an ARASAKA Unit is defeated each turn, draw 1.
```

Implementation: `/home/user/cyberpunk-tcg/src/cptcg/cards/sets/wnc.py` lines 566-576.

---

## 1. "PLAY:" — the trigger timing

**Requires:** the first sentence fires when this Unit is played.

**Implements:** `CardScript(on_play=play, ...)` (line 576). Per `docs/effects-authoring.md`, `on_play`
is the `PLAY` printed timing trigger.

**Verdict:** match.

## 2. "You may play a Unit ... for free" — optional, exactly one

**Requires:** a "may", i.e. the controller can decline; and *a* Unit — at most one.

**Implements:** line 570-571, `c.choose(cands, ..., prompt="Play a Unit for free?", optional=True)`.
`EffectCtx.choose` (effects.py 144-175) asks for exactly one value, and with `optional=True`
appends a `Pick(())` decline option; no `otherwise` is supplied, so declining does nothing.
If `cands` is empty the call returns without asking (effects.py 156-160) — correct, since there is
nothing to play and nothing else the card would do.

**Verdict:** match.

## 3. "a Unit with cost 4 or less from your hand or trash"

**Requires:** the candidate pool is (a) cards in **your** hand and **your** trash, (b) type UNIT,
(c) printed cost <= 4.

**Implements:** line 569:
`cands = [i for i in c.hand() + c.trash() if c.is_type(i, UNIT) and (c.d(i).cost or 0) <= 4]`.
`c.hand()` / `c.trash()` default to `self.player` (effects.py 61-65), i.e. the controller's own
zones — "your hand or trash". `is_type(i, UNIT)` restricts to Units. `(cost or 0) <= 4` is the
cost filter (`or 0` only matters for null-cost cards, which are Legends, already excluded by the
type test).

**Verdict:** match.

## 4. "for free"

**Requires:** no cost is paid.

**Implements:** `c2.play_free(i, ...)` → `EffectCtx.play_free` (effects.py 285-299), which calls
`play_card(self.s, self.player, inst, cost=0)` for a non-Gear. Units can never be Gear here
(filtered in clause 3), so the Gear/host branch is dead for this card.

**Verdict:** match.

## 5. "It can attack rival Units this turn."

**Requires:** (a) "It" = the Unit just played, not any other Unit; (b) it may attack **rival Units**
— that permission only, not the rival Gig area; (c) lasts this turn; (d) this sentence is
conditional on the first one actually happening — if the player declines, or there was nothing to
play, nothing happens.

**Implements:** `then=lambda c3, u: c3.mod("attack_units_now", u)` (line 570). `play_free` queues
`self.later(lambda c2: then(c2, inst))` before calling `play_card`, so `then` receives the played
instance and runs after the played card's own PLAY trigger (effects.py 297-299, LIFO stack).

- (a) subject is `u`, the played instance. OK.
- (b) `legal.attack_permission` (`src/cptcg/core/legal.py` line 42) reads
  `units_ok = s.has_mod("attack_units_now", unit)` for a lagged Unit without ADRENALINE/GO SOLO;
  `gigs_ok` is left to `attack_gigs_now`, which is not granted. So the Unit may attack rival Units
  and not the Gig area — exactly what the text says.
- (c) `EffectCtx.mod` with `until_my_next_turn=False` → `add_mod(..., turns=0)`
  (effects.py 320-322, state.py 223-226); `EndTurnCleanupStep` (steps.py 178) drops mods with
  `expiry <= s.turn`, so it lasts to end of this turn.
- (d) the `then` continuation only runs inside `play_free`, which only runs from the `choose`
  continuation — declining or an empty candidate list never reaches it.

**Verdict:** match.

## 6. "The first time an ARASAKA Unit is defeated each turn"

**Requires:** a trigger watching defeat events, with these conditions and no others:
(i) the defeated card is a **Unit**; (ii) it has the ARASAKA tag; (iii) **either player's** —
the text says "an ARASAKA Unit", with no "friendly"/"rival" qualifier; (iv) first time each turn,
i.e. once per turn per copy of this card, on any player's turn.

**Implements:** lines 573-575:

```python
def ev(c, e):
    if e[0] == "defeated" and e[2] == c.player and "ARASAKA" in c.d(e[1]).tags and c.once("arasaka_defeated"):
        c.draw(1)
```

with `events=frozenset({"defeated"})`.

- Event shape `("defeated", inst, owner, was_equipped)` is dispatched from `ops.defeat`
  (`src/cptcg/core/ops.py` line 458), and `ops.dispatch` delivers to the active cards of **both**
  players (slot 6 of `_rebuild_active`, ops.py 136-156), so the hook does see rival defeats.
- (ii) tag test present. OK.
- (iv) `c.once("arasaka_defeated")` is keyed on `(self.inst, key)` and `s.used` is cleared in
  `EndTurnCleanupStep` (steps.py 181), so it is once per turn per copy, on any turn. It is the last
  term of the `and`-chain, so the "once" is not consumed by a non-matching event. OK.
- **(iii) MISMATCH.** `e[2] == c.player` restricts the trigger to ARASAKA Units owned by this card's
  controller. The printed text has no such qualifier. The set writes "friendly" when it means
  friendly: the sister card *Yorinobu Arasaka — Embracing Destruction* reads "The first time a
  **friendly** ARASAKA Unit attacks each turn", and *River Ward — Detective on the Hunt* reads
  "When a **friendly** equipped Unit is defeated" — whose script (wnc.py line 1209) uses exactly
  this `e[2] == c.player` test. Steel Dragon's text deliberately omits "friendly", so it should
  also draw when a **rival** ARASAKA Unit is defeated (mirror matches, rival ARASAKA decks, and
  cards that defeat your own units in fights against ARASAKA). As written, roughly half the
  intended triggers never fire.
- (i) SECONDARY MISMATCH. There is no type test. `ops.defeat` dispatches the event for Units **and**
  Legends (ops.py 453-458), and six ARASAKA-tagged Legends exist in the set
  (Saburo Arasaka, Hanako Arasaka, Goro Takemura ×2, Adam Smasher — Ender of Legends,
  Yorinobu Arasaka — Embracing Destruction). A defeated face-up ARASAKA **Legend** (e.g. defeated
  in the Legends area by a replacement effect such as Jackie Welles) would trigger the draw even
  though it is not a Unit. River Ward's analogous script does test `c.d(e[1]).type is UNIT`.
  (A GO SOLO ARASAKA Legend on the field is arguably a Unit under ruling 015, so that case is
  defensible; the Legends-area case is not.) ARASAKA-tagged Gear cannot trigger it, because
  `ops.defeat` only dispatches for UNIT/LEGEND.

**Verdict:** mismatch — an extra side condition ("friendly") that the printed text does not have,
plus a missing "Unit" type condition.

## 7. "draw 1."

**Requires:** this card's controller draws 1.

**Implements:** `c.draw(1)` → `ops.draw(self.s, self.player, 1)` (effects.py 221-222); `c.player`
is the owner of this instance.

**Verdict:** match.

---

## Most serious discrepancy

Clause 6: `e[2] == c.player` in `wnc.py` line 574 narrows "an ARASAKA Unit is defeated" to
*friendly* ARASAKA Units. Wrong scope — a rival ARASAKA Unit being defeated should also draw 1.

---

# Skeptic 2 — told the finding is presumed wrong

# Kill attempt — AUD-yorinobu-arasaka-steel-dragon-1

**Verdict: SURVIVES.** I tried all five kill routes and none of them holds.

Card: `yorinobu-arasaka-steel-dragon`. Gate under attack: `src/cptcg/cards/sets/wnc.py:614`

```python
if e[0] == "defeated" and e[2] == c.player and "ARASAKA" in c.d(e[1]).tags and c.once("arasaka_defeated"):
```

`e[2]` is the owner of the defeated card — `ops.defeat` dispatches `("defeated", inst, owner, bool(gear))`
at `src/cptcg/core/ops.py:459`, with `owner = s.i_owner[inst]` (line 438). So the clause only ever sees
the controller's own ARASAKA deaths.

## Route 1 — a ruling covers it: NO

I read all 41 rows of `docs/rulings.md`. None of them touches the side-scope of a triggered clause.
The usual suspects are all off-target: 012 (BLOCKER redirect targets), 015 (GO SOLO slot), 019
(once-per-turn scope), 025 (payment order), 026 (field limit), 030 (⊡ on Gear). Nothing gives
"an X Unit" a friendly default.

Ruling 019 in fact cuts the other way. It settles that once-per-turn counters reset at the start of
*every* turn for *both* players, so "The first time an ARASAKA Unit is defeated each turn" is
perfectly coherent as an any-side trigger that can fire once on your turn and once on the Rival's.
The unqualified reading needs no special machinery.

## Route 2 — the engine already handles it elsewhere: NO

I checked the dispatch path rather than assuming. `ops.dispatch` (`src/cptcg/core/ops.py:136-156`)
delivers the event to `act[6][s.active]`, which per the `_rebuild_active` docstring
(`src/cptcg/core/ops.py:36`) is "slot 4 in **both** delivery orders, indexed by the active player
(that player's cards first)" — i.e. both players' `on_event` hooks, not just the active player's.
So Yorinobu's hook *is* invoked when the Rival's Minotaur dies; the script's own `e[2] == c.player`
test is the only thing that suppresses the draw. `grep -rn ARASAKA src/cptcg/` outside
`cards/sets/` finds only deck-building heuristics (`deck/strategies.py`), no engine-side handling.

I confirmed this empirically by monkeypatching only the hook (registry entry, nothing on disk):

- rival Minotaur defeated, as shipped → hand 0 (no draw)
- friendly Minotaur defeated, as shipped → hand 1 (the hook itself is alive and wired)
- rival Minotaur defeated with `e[2] == c.player` dropped → hand 1

So it is a one-conjunct scope restriction, not a missing implementation and not an engine gap.

## Route 3 — the test builds an unreachable board: NO

`board(pool, Side(field=["yorinobu-arasaka-steel-dragon"], deck=["floor-it"]*3), Side(field=["minotaur"]))`
is an ordinary turn-3 mid-game state: a 7-cost Unit each, active player 0, `defeat_now` on the
Rival's Unit during player 0's main phase. Defeating a rival Unit mid-turn is what half this set
does (Adam Smasher *Ender of Legends*, Royce, Gilded Maton, Over the Edge). Minotaur is a genuine
Unit carrying ARASAKA (`data/cards/wnc.json`: type Unit, tags `['ARASAKA','DRONE','MILITECH']`,
`verified: true`), and it sits in the Rival's deck, so no deck-building constraint of Yorinobu's
deck is violated.

## Route 4 — the test asserts a script internal: NO

The single assertion is `len(s.zone(0, Zone.HAND)) == 1`, against a starting hand of zero. That is
a printed-text outcome (did the controller draw 1), not a mod, flag or `once` key.

## Route 5 — the finding misreads a word: NO — and the set's own vocabulary sinks this route

The printed line is byte-exact: `The first time an ARASAKA Unit is defeated each turn, draw 1.`
No side qualifier. Every other event-triggered clause in the pool that means "mine" says so:

- River Ward: "When a **friendly** equipped Unit is defeated, ..."
- Alt Cunningham: "When a **friendly** equipped Unit or Legend is spent, ..."
- 6th Street Recruits, Goro Takemura, Evelyn Parker, Rogue *Queen of the Afterlife*: all "friendly".
- And decisively, the same character on the other card: **Yorinobu Arasaka *Embracing Destruction*** —
  "The first time a **friendly** ARASAKA Unit attacks each turn, draw 1." Same template, same
  "The first time ... each turn" frame, same ARASAKA tag, and it *does* carry the qualifier.
  `tools/transcribe_wnc.py:435-440` has the two cards three lines apart, one with "friendly" and one
  without, so this is not a transcription slip.

Symmetrically, the set uses bare nouns when it means either side: "Defeat a spent Unit" (Wild in the
Streets), "Defeat a Unit with power equal to..." (Over the Edge), "You may defeat a Gear" (Heywood
Ripperdoc), "Defeat all other Units" (Adam Smasher *Metal over Meat*). Bare noun = any side is the
house style, not an oversight of the filer's.

Printed text is the top authority (precedent: ruling 023) and it names no side. Nothing in
`docs/rules.md` establishes a friendly default for unqualified nouns — the "Reading your cards"
and "Timing triggers" sections say nothing of the kind.

## Conclusion

The finding is correct and is class **B4 (scope/condition)**: the conjunct `e[2] == c.player` at
`src/cptcg/cards/sets/wnc.py:614` narrows an unqualified printed clause to one side. The fix is to
drop that conjunct (keeping the draw going to `c.player`, the controller of Yorinobu, which the
probe confirms).

One caveat for whoever lands it, out of scope here: removing the gate makes the trigger fire on the
Rival's turn as well, which ruling 019's per-turn reset already supports, and it interacts with the
separately recorded S-SUSPICION U-1 in `out/audit/a06/findings.md` (Yorinobu not drawing for its own
defeat) — that one is about the card leaving the field before the event, not about side scope.
