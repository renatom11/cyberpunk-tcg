<!-- Working record for AUD-reboot-optics-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Reboot Optics  (`reboot-optics`)

- type: PROGRAM, colour: BLUE, cost: 2, power: None, RAM: 2
- keywords: ['QUICK']
- tags: ['QUICKHACK']

## Printed text (byte-exact from data/cards/wnc.json)

```
QUICK: The next time a rival Unit fights this turn, it doesn't defeat the opposing friendly Unit.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 308-312

@script("reboot-optics")
def _():
    return CardScript(on_play=lambda c: c.mod("next_fight_no_defeat", c.player))
```

---

# The finding, and the test that failed

# AUD-reboot-optics-1

card: `reboot-optics`

claim: the shield is consumed only by a fight it actually saves a Unit from, so one Program protects every later fight that turn

failing test: `tests/cards/audit/test_a03.py::test_reboot_optics_shield_covers_only_the_next_fight`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Reboot Optics (`reboot-optics`)

Printed text (byte-exact):

```
QUICK: The next time a rival Unit fights this turn, it doesn't defeat the opposing friendly Unit.
```

Implementation:

```python
# src/cptcg/cards/sets/wnc.py:308-310
@script("reboot-optics")
def _():
    return CardScript(on_play=lambda c: c.mod("next_fight_no_defeat", c.player))
```

Consumer: `src/cptcg/core/steps.py:350-400` (`fight`), specifically lines 376-382.
Helpers: `EffectCtx.mod` (`src/cptcg/core/effects.py:320-322`), `GameState.add_mod` /
`has_mod` (`src/cptcg/core/state.py:223-232`), end-of-turn mod sweep
(`src/cptcg/core/steps.py:180`).

---

## 1. `QUICK:`

**Requires.** The card may be played in a reaction window (rival's turn / during an attack),
not only in its controller's main phase.

**Implemented by.** Card data (`keywords: ['QUICK']`) plus the generic rule in
`src/cptcg/core/legal.py:193-199`: every PROGRAM in the reacting player's hand with
`Keyword.QUICK` and an affordable cost is offered as a `Play` option in the reaction menu.
Nothing card-specific is needed.

**Match.** Yes.

## 2. "... the opposing friendly Unit" — which side is protected

**Requires.** The protection is granted to the *controller of Reboot Optics* (friendly Units),
not to the rival.

**Implemented by.** `wnc.py:310` sets the mod with subject `c.player`; `EffectCtx.player` is
`s.i_owner[inst]`, i.e. the controller (`effects.py:25`). In `fight` (`steps.py:377-382`) the
mod is looked up under `ot = s.i_owner[t]` when the *defender* would be defeated and under
`oa = s.i_owner[a]` when the *attacker* would be defeated — in both cases the owner of the
unit that is about to be defeated. So only a Unit belonging to the Reboot Optics controller is
ever saved.

**Match.** Yes.

## 3. "a rival Unit fights" — does a *defending* rival Unit count?

**Requires.** Reading `fight` in docs/rules.md:137-139 ("Fight. Compare both Units' power"),
both participants fight, so the clause covers a rival Unit that is attacking my Unit *and* a
rival Unit that is defending against my attacking Unit; in either case my Unit is not defeated.

**Implemented by.** The two symmetric branches at `steps.py:377-382`: `defeat_t` (my Unit is
the defender, rival attacked) and `defeat_a` (my Unit is the attacker, rival defended).

**Match.** Yes — both roles are covered, which is the natural reading of the clause.

## 4. "it doesn't defeat" — the effect is prevention of a defeat, only in that fight

**Requires.** The rival Unit does not defeat my Unit; my Unit still fights normally (it can
still defeat the rival, ties still kill the rival), and nothing else about the fight changes.

**Implemented by.** `steps.py:378` / `381` set only `defeat_t` / `defeat_a` to `False` for my
side. `a_wins` / `t_wins` (and therefore the `fight_won` / `fight_lost` dispatches at
`steps.py:384-388`) are untouched, so my Unit still defeats the rival on a win and on a tie
(`defeat_t = a_wins or not t_wins`, `steps.py:365-366`, matching rules.md:137-138).

**Match.** Yes.

## 5. "this turn" — duration

**Requires.** The effect lapses at the end of the current turn even if never used.

**Implemented by.** `c.mod(..., until_my_next_turn=False)` → `turns=0` (`effects.py:320-322`)
→ `add_mod` stores expiry `self.turn` (`state.py:226`); `EndTurnCleanupStep` keeps only
`m[3] > s.turn` (`steps.py:180`), so the mod is dropped at the end of the turn it was played
in. This is right whether the card is played on its controller's turn or (via QUICK) on the
rival's turn.

**Match.** Yes.

## 6. "The next time ... fights" — *when the one-shot is spent*  ← MISMATCH

**Requires.** The effect is bound to one specific fight: the *next* fight in which a rival Unit
takes part this turn. If that fight happens and my Unit would not have been defeated anyway,
the effect has been used up and does nothing further; later fights that turn are unprotected.

**Implemented by.** `steps.py:377-382`:

```python
if defeat_t and s.has_mod("next_fight_no_defeat", ot):
    defeat_t = False
    s.mods = [m for m in s.mods if not (m[0] == "next_fight_no_defeat" and m[1] == ot)]
if defeat_a and s.has_mod("next_fight_no_defeat", oa):
    defeat_a = False
    s.mods = [m for m in s.mods if not (m[0] == "next_fight_no_defeat" and m[1] == oa)]
```

The mod is only consulted — and only removed — inside `if defeat_t:` / `if defeat_a:`. A fight
in which my Unit was never in danger does not consume it. The effective trigger is therefore
"the next time a rival Unit **would defeat** a friendly Unit this turn", i.e. the shield floats
over every fight of the turn until it finds one to negate, instead of being spent on the next
rival fight.

Cases where the mod survives a rival fight it should have been spent on:

- my Unit wins the fight, or the rival Unit wins nothing (`defeat_t` / `defeat_a` false);
- my Unit is already protected by `no_defeat_in_fight` (`steps.py:371-374`);
- the rival Unit has power <= 0 under `zero_power_cannot_defeat` (`steps.py:375-376`, CR 9.19.2).

**Demonstration** (scratch script, run against the real engine):

p0 fields Mox Inciters (power 2) and Animals Wrecker (power 10); p1 holds Reboot Optics and has
two spent Units, Psycho Squad (6) and Corpo Security (2).

1. Mox Inciters attacks Psycho Squad; p1 plays Reboot Optics in the reaction window. Psycho
   Squad wins; Mox Inciters is trashed. A rival Unit fought — per the printed text this was
   "the next time", and the effect is now spent. The engine leaves
   `('next_fight_no_defeat', 1, None, 3)` in `s.mods`.
2. Animals Wrecker (10) then attacks Corpo Security (2). Per the printed text Corpo Security is
   defeated. The engine leaves it on the field (zone FIELD), because the leftover mod absorbs
   this second fight.

**Match.** No. The script/engine grants strictly more protection than the card prints: the
one-shot is consumed by the next *prevented defeat* rather than by the next rival fight.

---

## Verdict

Clauses 1-5 are faithful. Clause 6 is mis-implemented: the "next time a rival Unit fights"
trigger is implemented as "the next fight in which a friendly Unit would be defeated", so when
the next rival fight is one the friendly Unit would have survived anyway the shield is not used
up and illegally carries over to a later fight in the same turn.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-reboot-optics-1 — attempted kill

**Verdict: the finding survives.** I tried all five grounds and none of them lands.

Printed text (byte-exact, `data/cards/wnc.json`, id `reboot-optics`):

> QUICK: The next time a rival Unit fights this turn, it doesn't defeat the opposing friendly Unit.

Implementation (`/home/user/cyberpunk-tcg/src/cptcg/cards/sets/wnc.py:320-322`):

```python
@script("reboot-optics")
def _():
    return CardScript(on_play=lambda c: c.mod("next_fight_no_defeat", c.player))
```

Sole consumer (`/home/user/cyberpunk-tcg/src/cptcg/core/steps.py:376-382`):

```python
if defeat_t and s.has_mod("next_fight_no_defeat", ot):
    defeat_t = False
    s.mods = [m for m in s.mods if not (m[0] == "next_fight_no_defeat" and m[1] == ot)]
if defeat_a and s.has_mod("next_fight_no_defeat", oa):
    defeat_a = False
    s.mods = [m for m in s.mods if not (m[0] == "next_fight_no_defeat" and m[1] == oa)]
```

The mod is read *and* stripped only inside `if defeat_t:` / `if defeat_a:`. So the implemented
trigger is "the next time a rival Unit **would defeat** a friendly Unit this turn", not "the next
time a rival Unit **fights** this turn". The shield floats over every fight of the turn until it
finds a defeat to negate.

## Ground 1 — a ruling deliberately covers it? No.

`docs/rulings.md` has no row on when a "the next time ... this turn" one-shot is spent, and
`RulesConfig` (`src/cptcg/core/config.py:27-67`) has no field for it — in this repo every
deliberate deviation carries a numbered field (see the `# 0NN` comments on lines 37-67). The usual
suspects are all off-topic: 012 BLOCKER redirect scope, 015 GO SOLO slot vacation, 019 the *reset
cadence across turns* of once-per-turn counters (it says nothing about spending a one-shot inside a
turn), 025 payment order, 026 field limit, 030 the spend symbol on Gear. The fight-adjacent rulings
010 (ties, 0-power, CR 9.17-9.19) and 011 (reaction count) do not touch consumption either.

## Ground 2 — the engine handles it elsewhere? No.

`next_fight_no_defeat` appears exactly three places in the whole source: the grant at `wnc.py:322`
and the read/strip pair at `steps.py:377-382`. Every site that mutates `s.mods` is accounted for
(`state.py:226` add, `steps.py:180` end-of-turn sweep `m[3] > s.turn`, `steps.py:379/382/391/394`
the two one-shot strips, `ops.py:368` `consume_cost_mods`); none of them strips this mod on a fight
that produced no friendly defeat. The documented alternative machinery exists and is unused here:
`docs/effects-authoring.md:59-60` prescribes the listener pattern for exactly this wording
(`c.mod("listener", ...)`, dispatched at `ops.py:159-162`), and Appetite for Destruction uses it.
Reboot Optics does not. Note also that `s.emit("fight", a, t, pa, pt)` (`steps.py:363`) is a log
emit, not a `dispatch`, so nothing else observes the fight event.

## Ground 3 — an unreachable board? No.

`Side(field=["maxtac-suppression-team", "psycho-squad"], hand=["reboot-optics"], eddies=9)` vs
`Side(field=[("corpo-security", {"spent": True}), ("animals-wrecker", {"spent": True})])` at
`tests/conftest.py:75` is an ordinary mid-game main phase (turn 3, units ready and un-lagged unless
specified). Both rival Units are spent, which rules 130-131 require for them to be attacked, and
both spent states are reachable: Animals Wrecker attacked on the rival's turn; Corpo Security prints
"This Unit can't attack" but has BLOCKER, and ruling 013 says blocking spends a ready Unit — so it
blocked an earlier attack this turn by a 0/1-power Unit and survived (2 beats 1). MaxTac's text
("Rival Units can't attack the turn they're played") is inert here; Psycho Squad and Animals Wrecker
have no text, so the fights are plain power comparisons: 7 > 2, then 10 > 6.

## Ground 4 — asserts a script internal? No.

The three assertions are `s.i_zone[corpo] == Zone.TRASH`, `s.i_zone[wrecker] == Zone.FIELD`,
`s.i_zone[mine] == Zone.TRASH` — zones only. No mod key, listener, or script field is inspected.
With `--runxfail` the failure lands on the intended final line
(`tests/cards/audit/test_a03.py:49`, `Zone.FIELD != Zone.TRASH`), not on a setup assertion, so the
test proves what it claims. Without `--runxfail` it is XFAIL, i.e. the engine fails as filed.

## Ground 5 — misreads a word? No — and both candidate readings condemn the engine.

The clause names a *fight* as the trigger, not a defeat: "The next time a rival Unit **fights** this
turn". The set's own sibling shows the distinction is deliberate — Safety Override prints "The next
time a friendly Unit **loses a fight** this turn" and is consumed on exactly that narrower event
(`steps.py:389-394`). Had Reboot Optics meant "would defeat", it had the vocabulary to say so.

- Broad reading ("fights" covers attacker and defender — the reading the engine itself adopts, since
  `steps.py:380-382` shields a friendly *attacker* from a defending rival): fight 1 is a rival Unit
  fighting, so the one-shot is spent there even though it saved nobody, and Psycho Squad dies in
  fight 2.
- Narrow reading ("a rival Unit fights" = a rival Unit attacks): no rival Unit attacks on our turn
  at all, so the shield never applies and Psycho Squad dies in fight 2 for that reason.

Either way Psycho Squad must be in the trash; the engine leaves it on the field. "Rival"/"friendly"
are controller-relative as everywhere else in the set, and `c.player` (`effects.py`, owner of the
instance) plus the `ot`/`oa` lookups get that part right — clauses 1-5 of the blind audit are fine.
There is no reading on which "fights" means "would defeat", so this is not even ambiguous.

## Classification

B4-scope-or-condition: the one-shot's trigger condition is implemented as "next prevented defeat"
instead of the printed "next fight", so the Program grants protection across strictly more fights
than the card allows.

## Reproduction

`python -m pytest 'tests/cards/audit/test_a03.py::test_reboot_optics_shield_covers_only_the_next_fight' -q -rx`
→ XFAIL (fails as filed).
