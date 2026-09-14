<!-- Working record for AUD-gunpoint-diplomacy-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Gunpoint Diplomacy  (`gunpoint-diplomacy`)

- type: PROGRAM, colour: RED, cost: 4, power: None, RAM: 3
- keywords: none
- tags: ['GANGER', 'PLAN']

## Printed text (byte-exact from data/cards/wnc.json)

```
Give a friendly Unit these effects. If you have less ★ (Street Cred) than a Rival, they instead choose one effect for you.
- The next time this Unit attacks this turn, it may attack ready Units.
- Give this Unit +3 power this turn.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 205-218

@script("gunpoint-diplomacy")
def _():
    def play(c):
        def give(c2, u):
            opts = [("May attack ready Units", lambda c3: c3.mod("attack_ready_units", u)),
                    ("+3 power", lambda c3: c3.temp_power(u, 3))]
            if c2.less_cred():
                c2.choose_one(opts, player=c2.rival)
            else:
                c2.choose_one(opts, both=True)
        c.choose(c.units(), give, prompt="Give a friendly Unit")
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-gunpoint-diplomacy-1

card: `gunpoint-diplomacy`

claim: 'the next time this Unit attacks this turn' is granted as an until-end-of-turn mod, so every attack that turn may hit ready Units

failing test: `tests/cards/audit/test_a02.py::test_gunpoint_diplomacy_ready_attack_lasts_one_attack`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Gunpoint Diplomacy (`gunpoint-diplomacy`)

Printed text:

```
Give a friendly Unit these effects. If you have less ★ (Street Cred) than a Rival, they instead choose one effect for you.
- The next time this Unit attacks this turn, it may attack ready Units.
- Give this Unit +3 power this turn.
```

Implementation: `src/cptcg/cards/sets/wnc.py` lines 205-218.

## 1. "Give a friendly Unit ..." — target selection

Requires: one Unit you control is chosen (mandatory, not "may", not "up to"), and the
controller of the card makes that choice. It is a single Unit ("a friendly Unit"), not all.

Implements: line 214 `c.choose(c.units(), give, prompt="Give a friendly Unit")`.
`EffectCtx.units()` (effects.py:48-50) defaults `player=self.player`, i.e. the card's owner,
so the candidate list is friendly Units only. `choose` (effects.py:144-176) defaults
`player=self.player` (you choose), and `optional` defaults to `False`, so there is no decline
option — mandatory, exactly one pick. With no friendly Units and no `otherwise`, nothing
happens, which is the correct "no legal target" behaviour.

**Match.**

## 2. "If you have less ★ (Street Cred) than a Rival, they instead choose one effect for you."

Requires: a condition checked as the effect resolves — your Street Cred strictly less than the
Rival's. If true, the *Rival* picks exactly one of the two bullets (and only that one applies).
The "instead" replaces only the "these effects" (both) part; you still pick the Unit.

Implements: lines 211-212. `c2.less_cred()` (effects.py:103-104) is
`self.cred() < self.cred(self.rival)` where `cred` is `state.street_cred` = sum of top faces
(state.py:219-220). Correct direction, correct sides, and it is evaluated inside the
continuation `give` on the post-choice ctx, so it reads the state at resolution.
`c2.choose_one(opts, player=c2.rival)` (effects.py:198-206) asks the rival to pick exactly one
of the two labelled effects and runs only that one. The Unit itself was still picked by you in
clause 1. Edge case only: ruling 038 says Null Street Cred (no Gigs) compares as smaller than
0; `less_cred` treats no-Gigs as 0, so a Null-vs-Null board reads "not less". That is an
engine-wide helper convention shared by every `more_cred`/`less_cred` card, not a defect
specific to this script.

**Match.**

## 3. "these effects" (the non-conditional branch: both bullets apply)

Requires: when you do **not** have less Street Cred, the chosen Unit gets *both* listed
effects, with no choice offered.

Implements: line 213 `c2.choose_one(opts, both=True)`. In `choose_one`, `both=True` skips the
question entirely and queues every option via `later` in reversed order so they resolve in
printed order (effects.py:200-203). Both effects therefore apply, to the same chosen Unit
(`u` is captured by both closures). No prompt is raised, which is right — the text offers no
choice on this branch.

**Match.**

## 4. Bullet 1 — "The next time this Unit attacks this turn, it may attack ready Units."

Requires three things:
(a) a *permission*, not a compulsion — "may attack ready Units" means ready Units are added to
    the legal target set; attacking a spent Unit or the Gig area stays legal;
(b) duration "this turn";
(c) **one use only** — "the next time this Unit attacks". The permission is spent on that
    Unit's *first* attack this turn; a second attack in the same turn (possible: several cards
    ready Units mid-turn, e.g. wnc.py:844 "Ready up to 3 Units", 935, 1284) must no longer be
    able to hit ready Units.

Implements: line 209 `c3.mod("attack_ready_units", u)`.
- `EffectCtx.mod` (effects.py:320-322) with `until_my_next_turn=False` gives `turns=0`, and
  `state.add_mod` stores expiry `self.turn`; `EndTurnCleanupStep` (steps.py:180) keeps only
  mods with `m[3] > s.turn`, so the mod dies at end of this turn. (b) is satisfied.
- `legal.attack_targets` (legal.py:55-62) reads `ready_ok = s.has_mod("attack_ready_units",
  attacker)` and, when set, *adds* every rival Unit to the target list rather than restricting
  to ready ones; spent Units and the Gig target remain available. (a) is satisfied.
- (c) is **not** satisfied. Nothing anywhere consumes the mod when the Unit attacks. A grep of
  `src/` finds exactly two occurrences of the string `attack_ready_units`: the write at
  wnc.py:209 and the read at legal.py:57. The engine's own idiom for one-shot "the next time"
  mods is to strip the mod at the moment it is used — see steps.py:377-382 for
  `next_fight_no_defeat` and steps.py:389-394 for `next_loss_defeats_winner`, each of which
  filters itself out of `s.mods` after firing. No equivalent removal exists on the attack path
  (`AttackStep`/`attack_targets` never touch `s.mods`).

So the script implements "**each** time this Unit attacks this turn, it may attack ready
Units" instead of "the next time". The divergence is observable whenever the Unit attacks more
than once in the turn — ready it with one of the ready-a-Unit effects and its second, third,
... attack still illegally reaches ready (untapped) rival Units, which is precisely the
protection ready status is supposed to give (rules.md:177 "ready Units can't be attacked").

**MISMATCH — wrong scope/duration: the one-shot grant is never consumed.**

## 5. Bullet 2 — "Give this Unit +3 power this turn."

Requires: +3 power, to the same chosen Unit, until end of turn, unconditional.

Implements: line 210 `c3.temp_power(u, 3)` → `ops.add_temp_power(s, u, 3, 0)` with `cond=0`
(no situational gate). `s.temp_power` is cleared in `EndTurnCleanupStep` (steps.py:179), so the
bonus lasts exactly this turn. Subject is `u`, the Unit chosen in clause 1.

**Match.**

## Conclusion

One discrepancy: clause 4. The "next time ... this turn" one-shot on the ready-Unit attack
permission is implemented as an until-end-of-turn permission with no consumption on use.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-gunpoint-diplomacy-1 — attempted kill

**Verdict: the finding survives.** I could not kill it on any of the five grounds.

Printed text (byte-exact, `data/cards/wnc.json` line 865):

> - The next time this Unit attacks this turn, it may attack ready Units.

Implementation (`src/cptcg/cards/sets/wnc.py:221`):

```python
("May attack ready Units", lambda c3: c3.mod("attack_ready_units", u)),
```

`EffectCtx.mod` (`src/cptcg/core/effects.py:320-322`) calls `s.add_mod(kind, subject, value, turns=0)`,
which stores an expiry of `s.turn + 0` (`src/cptcg/core/state.py:223-226`). Mods are pruned only at the
turn boundary — `src/cptcg/core/steps.py:180`: `s.mods = [m for m in s.mods if m[3] > s.turn]`. Nothing
else ever removes an `attack_ready_units` entry. Its single reader, `src/cptcg/core/legal.py:57`
(`ready_ok = s.has_mod("attack_ready_units", attacker)`), therefore answers `True` for *every* attack the
Unit makes for the rest of the turn, not just the next one.

## Ground 1 — a ruling deliberately covers it? No.

`docs/rulings.md` has no row on the duration or consumption of "the next time ... this turn" grants, and
`RulesConfig` (`src/cptcg/core/config.py:27-67`) has no corresponding field — every deliberate deviation in
this repo carries one. The usual suspects are all off-topic: 012 is BLOCKER redirect scope, 015 GO SOLO
slot vacation, 019 is the *reset cadence* of "once per turn" counters across turns (it says nothing about a
one-shot grant inside a turn), 025 payment order, 026 field limit, 030 the ⊡ symbol on Gear. Nothing here.

## Ground 2 — the engine already handles it elsewhere? No — and the engine's own convention is against it.

I searched `core/effects.py`, `core/ops.py`, `core/steps.py`, `core/legal.py`, `core/state.py` and
`core/engine.py`. `attack_ready_units` appears exactly twice in the whole source: the grant at
`wnc.py:221` and the read at `legal.py:57`. There is no consumption site.

By contrast the engine *does* implement one-shot "next time" mods for the two other cards that print that
wording: `next_fight_no_defeat` and `next_loss_defeats_winner` are explicitly stripped after they fire —
`src/cptcg/core/steps.py:379, 382, 391, 394`. And the fourth "next time" card, Appetite for Destruction
(`wnc.py:253-271`), uses the listener pattern and deletes its own listener the moment it fires
(`wnc.py:261`), exactly as `docs/effects-authoring.md:59-60` instructs:

> "The next time ... this turn" effects that outlive a Program: register a listener,
> `c.mod("listener", c.player, fn)` where `fn(state, ev)` runs on every event until end of turn.

So three of the four "next time" cards in the set are one-shot in code. Gunpoint Diplomacy is the outlier,
which makes this an oversight rather than a house ruling.

## Ground 3 — an unreachable board? No.

The board is `Side(hand=["gunpoint-diplomacy"], field=["psycho-squad"], gig=[(20,20)])` vs
`Side(field=["psycho-squad", "psycho-squad"], gig=[(4,1)])` — higher Street Cred, so the controller takes
both effects (+3 power *and* the ready-attack grant), which is why the attacker wins the first fight and
survives. The only step that needs justification is `during_main(s, lambda st: ops.ready(st, mine))`:
readying an already-spent attacker so it can attack a second time. Real cards do exactly that on the
controller's own turn — Wraith Marauders (`wnc.py:940-948`) readies a friendly spent Unit whose power
equals a Gig it just stole; `wnc.py:1104` readies a Gear's host; `wnc.py:1288, 1296` ready Units too. Ruling
024 confirms a Unit is merely spent by attacking, not otherwise barred. So "attack a ready Unit, get readied,
attack again" is a line a real game reaches.

## Ground 4 — asserts a script internal? No.

The final assertion is `Target(TARGET_UNIT, second) not in legal.attack_targets(s, mine)` — the engine's
public legality answer to "may this Unit attack that ready Unit", i.e. precisely the printed permission. The
supporting assertions are `s.i_spent[second]` and `s.i_zone[first] == Zone.TRASH`, both board facts. No
mod key, listener or script field is inspected.

## Ground 5 — misreads the text? No.

"The next time this Unit attacks this turn" bounds the grant to one attack and additionally caps it at the
end of turn; "this turn" is the outer limit, not the grant's extent. Reading it as "every attack this turn"
would make "the next time" do no work at all, and would collapse it into the wording the set uses when it
means all turn ("Give this Unit +3 power this turn" — the very next line on the same card). The test also
spends the grant in the least arguable way possible: the first attack actually targets a ready Unit.

## Reproduction

`python -m pytest 'tests/cards/audit/test_a02.py::test_gunpoint_diplomacy_ready_attack_lasts_one_attack' -q -rx`
→ **XFAIL**. With `--runxfail` the failure lands on the intended final assertion
(`tests/cards/audit/test_a02.py:77`), not on an earlier setup assertion, so the test proves what it claims:
after the grant has been used on one attack, `attack_targets` still offers the second ready Unit.

## Classification

**B4-scope-or-condition** — the effect is implemented with the wrong duration/scope: a one-attack grant
issued as an until-end-of-turn mod. The fix belongs in `wnc.py:221` (a self-removing `"listener"` on the
`("attack", unit, player)` event, per `docs/effects-authoring.md:59-60`), not in `core/legal.py`.
