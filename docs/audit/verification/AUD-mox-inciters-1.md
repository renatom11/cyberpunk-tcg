<!-- Working record for AUD-mox-inciters-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Mox Inciters  (`mox-inciters`)

- type: UNIT, colour: BLUE, cost: 3, power: 2, RAM: 2
- keywords: ['BLOCKER']
- tags: ['GANGER', 'MOX']

## Printed text (byte-exact from data/cards/wnc.json)

```
PLAY: A rival Unit must attack next turn if it can.
BLOCKER
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 513-518

@script("mox-inciters")
def _():
    return CardScript(on_play=lambda c: c.choose(
        c.rival_units(), lambda c2, u: c2.mod("must_attack", u, until_my_next_turn=True), prompt="Must attack"))
```

---

# The finding, and the test that failed

# AUD-mox-inciters-1

card: `mox-inciters`

claim: the 'must attack' mod is written but never read by the engine, so the named rival Unit is under no obligation on the rival's next turn

failing test: `tests/cards/audit/test_a06.py::test_mox_inciters_forces_the_named_rival_unit_to_attack`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Mox Inciters (`mox-inciters`)

Printed text (byte-exact):

```
PLAY: A rival Unit must attack next turn if it can.
BLOCKER
```

Implementation (`src/cptcg/cards/sets/wnc.py` lines 513-518):

```python
@script("mox-inciters")
def _():
    return CardScript(on_play=lambda c: c.choose(
        c.rival_units(), lambda c2, u: c2.mod("must_attack", u, until_my_next_turn=True), prompt="Must attack"))
```

---

## 1. `PLAY:` — the trigger

**Text requires:** the effect fires when this Unit is played (and, per ruling 032, would also fire
on GO SOLO, which does not apply to a non-Legend).

**Implements it:** `CardScript(on_play=...)` (wnc.py:515). `docs/effects-authoring.md` lists
`on_play` as exactly the printed PLAY timing trigger.

**Verdict: matches.**

## 2. `A rival Unit` — one, on the Rival's side, mandatory, chosen by the Mox controller

**Text requires:** exactly one Unit, and it must be a *rival* Unit. Singular "A", no "up to",
no "may" — so a target must be chosen whenever one exists; if the Rival controls no Units the
effect simply does nothing.

**Implements it:** `c.rival_units()` (effects.py:53 → `units(self.rival)`) is the candidate set —
correct side, Units only, no ready/spent or power restriction, matching the unqualified text.
`c.choose(...)` with `optional` left at its default `False` (effects.py:143) adds **no** decline
option, so the pick is mandatory — right for a non-"may" effect. `choose` with an empty candidate
list and no `otherwise` returns without asking (effects.py:156-159), which is the right behaviour
for "no rival Units".

Chooser: `choose` defaults `player=self.player`, i.e. the controller of Mox Inciters picks which
rival Unit is put under the obligation. That is the normal reading of "A rival Unit ..." on a card
you control (the Rival would otherwise choose their least inconvenient Unit, which would make the
card near-blank), and it matches how every other rival-targeting script in this set reads
(e.g. `defeat_one(c, c.rival_units())`).

**Verdict: matches.**

## 3. `must attack` — the obligation itself

**Text requires:** the chosen rival Unit is *forced* to attack. `docs/rules.md` line 150 states the
default this overrides: "A Unit doesn't have to attack." So on the Rival's next turn the engine
must refuse to let that Rival finish their turn (or at minimum must remove the "do nothing"
option) while the named Unit still has a legal attack available.

**Implements it:** nothing. The script writes a `must_attack` mod via `EffectCtx.mod`
(effects.py:315-317 → `GameState.add_mod`, state.py:223-226), which appends
`("must_attack", unit, None, expiry)` to `s.mods`. **No code anywhere in `src/` ever reads that
mod.** `grep -rn must_attack src/` returns exactly two lines and both are *writers*: wnc.py:516
(this card) and wnc.py:1251 (Evelyn Parker *Beautiful Enigma*, whose ability has the same printed
sentence).

Concretely, the places that would have to read it do not:

- `legal.attack_permission` (legal.py:24-48) reads `cant_attack`, `attack_units_now`,
  `attack_gigs_now` — never `must_attack`.
- `legal.attack_targets` / `can_attack` (legal.py:51-67) read `attack_ready_units` and the
  `attack_ready_blockers_if_more_cred` extra — never `must_attack`.
- `legal.main_menu` (legal.py:114-160) begins `opts: list = [EndTurn()]` unconditionally and never
  inspects `s.mods` for an obligation, so the Rival can always simply end the turn.
- `engine.legal_actions` (engine.py:69-80) just materialises `main_menu`; it filters nothing.
- `steps.EndTurnStep` / `EndTurnCleanupStep` (steps.py:160-190) only act on `defeat_at_end`; no
  obligation check, no penalty.

There is even a dedicated instance flag reserved for this exact sentence —
`F_MUST_ATTACK = 1 << 3  # "must attack next turn if it can"` (enums.py:65) — and it is likewise
never set and never read (`grep -rn F_MUST_ATTACK src/` matches only its definition). Compare the
neighbouring flags: `F_GO_SOLO` and `F_NO_READY_NEXT` are both set *and* read (ops.py:450,
steps.py:114-115), so the engine does honour instance flags it actually wires — this one is not
wired.

Note this is not covered by the `DESCRIPTIVE` escape hatch in `config.py:82-105`: that set is for
`RulesConfig` ruling fields whose behaviour is hard-coded elsewhere. `must_attack` is not a ruling
flag; `docs/effects-authoring.md` line 65 lists it under "Mods **the engine understands**", which
is false for this mod.

Result: playing Mox Inciters resolves a real choice, writes a bookkeeping tuple, and changes
nothing about what the Rival may or may not do on their next turn. The Rival's legal-move set on
their following turn is bit-for-bit identical with and without the mod. The entire printed PLAY
effect is inert.

**Verdict: DOES NOT match — the clause is unimplemented (missing).**

## 4. `next turn` — the duration

**Text requires:** the obligation applies on the Rival's next turn, i.e. the turn immediately after
the one Mox Inciters was played (Units are played in your own main phase), and it lapses when that
turn ends.

**Implements it:** `until_my_next_turn=True` → `EffectCtx.mod` (effects.py:315-317) computes
`turns = 1 if self.s.active == self.player else 0`; a PLAY trigger always resolves on the
controller's own turn, so `turns = 1` and the mod's expiry is `s.turn + 1` (state.py:226).
`EndTurnCleanupStep` prunes with `s.mods = [m for m in s.mods if m[3] > s.turn]` *before*
`s.turn += 1` (steps.py:180, 190). Walking it: added on turn T with expiry T+1; cleanup of turn T
keeps it (T+1 > T); it is live for turn T+1, the Rival's turn; cleanup of turn T+1 drops it
(T+1 > T+1 is false). Exactly one rival turn of coverage.

**Verdict: the duration bookkeeping is correct** (it is only the thing being booked that is never
consulted — see §3).

## 5. `if it can` — the obligation is conditional on a legal attack existing

**Text requires:** the forced Unit is excused when it has no legal attack (spent, lagged with no
`ADRENALINE`/`GO SOLO`, `cant_attack`, or no legal target — e.g. every rival Unit ready and the Gig
area empty under ruling 009). Note the condition attaches to the *obligation*, not to the *choice*:
you may name any rival Unit, even one that plainly cannot attack.

**Implements it:** the candidate list is correctly unrestricted (`c.rival_units()` with no
predicate), so the choice half is right. The conditional half has no implementation because the
obligation has none at all (§3): with nothing enforcing "must attack", there is nothing to excuse.

**Verdict: vacuously unimplemented, subsumed by §3.**

## 6. `BLOCKER` — keyword

**Text requires:** the printed keyword only; reminder text per rules.md line 92 / 135.

**Implements it:** the keyword is in the card data (`keywords: ["BLOCKER"]`, data/cards/wnc.json)
and handled generically by the engine — `legal.reaction_menu` (legal.py:184-196) offers a `Block`
for each ready friendly Unit with `Keyword.BLOCKER`, honouring rulings 011-014. No script line is
needed or wanted for a bare keyword (`docs/effects-authoring.md`: keyword-only text needs no
script).

**Verdict: matches.**

---

## Most serious discrepancy

§3. "A rival Unit must attack next turn if it can" is not implemented. The script writes a
`must_attack` mod that no engine code reads — `legal.main_menu` always offers `EndTurn()`, and
`attack_permission` / `attack_targets` never consult the mod — so the card's whole PLAY effect is a
no-op that costs the controller a real decision and buys nothing. Direction: **missing**.

Everything else about the script (side, count, mandatory pick, unrestricted target, chooser, and
the one-rival-turn duration) is faithful to the printed text.

---

# Skeptic 2 — told the finding is presumed wrong

# Kill attempt — AUD-mox-inciters-1 (`mox-inciters`)

**Verdict: the finding SURVIVES.** I tried all five kill routes and every one of them fails.
Classification: **B2 — missing clause** (the printed PLAY clause produces no game effect at all).

Printed text (byte-exact, `data/cards/wnc.json:1612`):
`PLAY: A rival Unit must attack next turn if it can.\nBLOCKER`

## 1. Is there a ruling that makes this deliberate? No.

`docs/rulings.md` has 41 rows. None of them touches attack obligations. The usual suspects do not
apply: 012 is BLOCKER redirect scope, 015 is GO SOLO slot vacation, 019 is once-per-turn scope,
025 is payment order, 026 is field limit, 030 is the ⊡ symbol on Gear. Nothing in the table says
"a Unit may ignore an effect that tells it to attack".

`src/cptcg/core/config.py` is the other place a deliberate decision would be recorded — every
ruling is a `RulesConfig` field, and the twelve knowingly-unwired ones are named in `DESCRIPTIVE`.
There is no `must_attack` field, wired or descriptive, so this is not a recorded approximation
either.

`docs/rules.md` does say "A Unit doesn't have to attack" — but that is the default rule the card
overrides, and the same file carries the guide's own conflict clause: *"If there's a conflict
between a card's text and this guide, follow the text on the card."* (precedent: ruling 023). So
the default rule is not a defence; it is exactly the thing the card is printed to change.

## 2. Does the engine handle it somewhere the filer did not look? No.

I checked all four named files plus `state.py`, `engine.py` and `enums.py`:

- `src/cptcg/core/state.py:228` `has_mod` is the only reader API; the full set of call sites is
  `legal.py:27` (`cant_attack`), `legal.py:42-43` (`attack_units_now`, `attack_gigs_now`),
  `legal.py:57` (`attack_ready_units`), `steps.py:270,272,367,369,377,380,390,393`
  (`protect_*`, `no_defeat_in_fight`, `next_fight_no_defeat`, `next_loss_defeats_winner`),
  `ops.py:386` (`kw`), `wnc.py:367,1281`, `agents/heuristic.py:108`. **`must_attack` appears at
  no call site.**
- `src/cptcg/core/legal.py:117` — `main_menu` starts `opts: list = [EndTurn()]` unconditionally
  and never consults `s.mods`. There is no other gate on ending a turn.
- `steps.py` has no forced-attack step; a repo-wide grep for `must_attack` outside tests/docs
  finds only the two writers in `wnc.py` (516/542 for Mox Inciters, 1251/1277 for Evelyn Parker)
  and one suggestive dead constant:

  `src/cptcg/core/enums.py:65` — `F_MUST_ATTACK = 1 << 3   # "must attack next turn if it can"`

  That flag bit is **defined and never read or written anywhere in `src/`**. It is evidence that
  the obligation was scoped and then never wired, not evidence that it exists.
- There is no `web/` tree; `src/` is the whole engine.

`docs/effects-authoring.md:65` lists `must_attack` among "Mods the engine understands". That
sentence is simply false today, which strengthens the finding rather than killing it.

## 3. Is the test board unreachable? Not in any way that matters.

The test does use an odd side: `Side(field=["psycho-squad"], deck=[...], fixer=[])` gives player 1
zero dice in fixer and Gig area at turn 3 (`turns_taken=[1,1]`), which no real game reaches — a
player cannot have emptied a fixer by turn 3, and the 12 dice are not conserved. The helper uses
it only to skip the start-phase `TakeGigDie` question.

I rebuilt the same scenario on a dice-conserving, turn-3-legal board (each side one die in the Gig
area, five in the fixer, both decks stocked) and resolved the start-phase die pick by hand
(`scratchpad/probe2.py`). Result on the rival's turn:

```
after die pick: pending 3 (EndTurn(), Sell(inst=49), Attack(inst=50))
attack offered: True
endturn offered: True
must_attack still: True [('must_attack', 50, None, 4)] turn 4
```

Identical behaviour. The board quirk does not carry the failure, so route 3 cannot kill it.

## 4. Does the test assert a script internal? No.

It asserts two things about `s.pending.options` — the set of legal actions the rival is offered:
`Attack(psycho) in options` and `EndTurn() not in options`. Both are printed-text outcomes. The
*old* test, `tests/cards/test_units.py:161` (`assert s.has_mod("must_attack", find(s, "psycho-squad"))`),
is the one that asserts bookkeeping, and it is precisely what hid the gap.

## 5. Does the finding misread a word? No.

- "A rival Unit" — rival of Mox Inciters' controller; the test names Psycho Squad, the only rival
  Unit, so the `choose` auto-resolves. With one rival Unit even the loosest reading ("some rival
  Unit") binds this one.
- "next turn" — the turn that follows, i.e. the rival's. The mod is stamped `expiry = s.turn + 1`
  and `EndTurnCleanupStep` keeps mods with `expiry > s.turn`, so it is live for exactly that turn:
  the probe shows `has_mod == True` on turn 4 while the rival holds the menu. Duration is right;
  only the obligation is missing.
- "if it can" — it can: `Attack(psycho)` is in the menu (the Gig area of player 0 holds a die, and
  `attack_permission` grants `gigs_ok`). So the escape clause does not fire.

## Residual wiggle room (does not rescue the engine)

One could argue a correct engine might keep `EndTurn` in the menu and force the attack when it is
chosen, rather than withholding `EndTurn` while the obligated Unit can still attack. Withholding is
the natural encoding (the rival still chooses when to attack and what to target), and it is what
the test asserts. But the point is moot: under *either* shape, today's engine lets the rival end
the turn having attacked with nothing, which the printed text forbids. The obligation has no
representation anywhere in the engine.

## Conclusion

The clause "A rival Unit must attack next turn if it can" is inert. Mox Inciters is a 3-cost 2-power
BLOCKER whose entire PLAY line does nothing. The same dead mod is Evelyn Parker *Beautiful Enigma*'s
ability (`wnc.py:1277`), so a fix — reading `must_attack` in `legal.main_menu` to suppress `EndTurn`
while an obligated rival Unit still has a legal attack — repairs both cards.
