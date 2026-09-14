<!-- Working record for AUD-chrome-fang-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Chrome Fang  (`chrome-fang`)

- type: UNIT, colour: RED, cost: 5, power: 6, RAM: 1
- keywords: none
- tags: ['GANGER', 'NETRUNNER', 'TYGER CLAWS']

## Printed text (byte-exact from data/cards/wnc.json)

```
PLAY: Until your next turn, rival Units can't steal friendly Gigs with value higher than their power.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 406-410

@script("chrome-fang")
def _():
    return CardScript(on_play=lambda c: c.mod("protect_gt_power", c.player, until_my_next_turn=True))
```

---

# The finding, and the test that failed

# AUD-chrome-fang-1

card: `chrome-fang`

claim: the protection is only consulted on the attack-steal path (steps.stealable), so an effect-driven steal such as Gorilla Arms takes a Gig with value higher than the rival Unit's power

failing test: `tests/cards/audit/test_a05.py::test_chrome_fang_stops_every_steal_of_a_gig_above_the_thiefs_power`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Chrome Fang (`chrome-fang`)

Printed text (byte-exact):

```
PLAY: Until your next turn, rival Units can't steal friendly Gigs with value higher than their power.
```

Implementation:

```python
@script("chrome-fang")
def _():
    return CardScript(on_play=lambda c: c.mod("protect_gt_power", c.player, until_my_next_turn=True))
```

The real behaviour lives in two helpers:

- `EffectCtx.mod` — `src/cptcg/core/effects.py:320-322`
- `GameState.add_mod` / `has_mod` — `src/cptcg/core/state.py:223-233`
- `stealable` — `src/cptcg/core/steps.py:264-276` (the only consumer of `protect_gt_power`)
- steal resolution — `src/cptcg/core/steps.py:278-313` and `ResolveAttackStep` at `steps.py:315-348`
- mod expiry — `EndTurnCleanupStep`, `src/cptcg/core/steps.py:180`

---

## 1. "PLAY:" — the effect happens when this Unit is played

**Requires:** a one-shot trigger on play, not a static/continuous ability tied to the card staying
on the field.

**Implements:** `CardScript(on_play=...)` (wnc.py:408). The effect it installs is a mod keyed to a
*player* (`c.player`), not to the card instance, so it correctly survives Chrome Fang leaving the
field — which is what a duration effect ("Until your next turn, ...") should do, as opposed to a
static aura.

**Match.**

## 2. "Until your next turn" — duration

**Requires:** the effect covers the rest of your turn and the whole of the Rival's turn, and is
gone when your next turn begins (rulings 039: "until your next turn" effects are removed at the
start of your turn, before Ready/Draw).

**Implements:** `c.mod(..., until_my_next_turn=True)` → `effects.py:321`
`turns = 1 if s.active == self.player else 0`, then `add_mod(..., turns=turns)` stores
`expires_turn = s.turn + turns`. `EndTurnCleanupStep` (steps.py:180) keeps only
`m[3] > s.turn` at the end of each turn.

Traced concretely (and verified by running the engine): played on my turn T=4, the mod is stored
with expiry 5. End of turn 4: `5 > 4` → kept. Turn 5 is the Rival's turn (`s.active` flips at
`steps.py:196`), and the mod is live for all of it, including the Rival's end-of-turn triggers
(`EndTurnStep` dispatches `end_turn` *before* the cleanup step runs). End of turn 5: `5 > 5` is
false → removed, so it is gone when my turn 6 starts. That is exactly "until your next turn";
removing it at the end of the Rival's turn instead of at the top of mine is the same instant for
every effect in the set.

If the card were ever played during the Rival's turn, `turns = 0` → expiry = that same turn →
removed at the end of the Rival's turn, i.e. immediately before my next turn. Also correct.

**Match.**

## 3. "rival Units" — which side, and which cards

**Requires:** the restriction binds the *opponent's* Units (the thieves), not friendly ones.

**Implements:** the mod's subject is `c.player` (the Chrome Fang controller), and `stealable`
(steps.py:270) reads `s.has_mod("protect_gt_power", victim)` where `victim` is the *defending*
player (`ResolveAttackStep`: `thief = atk.attacker_ctrl; victim = 1 - thief`, steps.py:331-332;
`StealOneStep`: `victim = 1 - self.thief`, steps.py:293). So the mod only ever restrains the side
that is *not* the Chrome Fang player. Chrome Fang's controller stealing from the Rival is
unaffected (`has_mod("protect_gt_power", rival)` is false). Correct side.

Sub-question — does "Units" wrongly cover Legends? `stealable` applies `protect_gt_power` to *any*
attacker, while the sibling card Westbrook Netrunner ("rival **Legends** can't steal ... less than
their power") is gated on `thief_is_legend` (steps.py:267, 272). That asymmetry is correct, not a
bug: the only way a Legend can be on the field to steal at all is GO SOLO, and rules.md:90 says
GO SOLO plays it "as a ready **Unit**" (ruling 015: "it is a Unit now"); `GameState.units()`
(state.py:201-205) likewise counts every non-Gear field card, Legend cards included. So a GO SOLO
Legend *is* a rival Unit and Chrome Fang should stop it; Westbrook is the narrower card, and its
extra test is what makes *it* Legend-only.

**Match.**

## 4. "can't steal friendly Gigs" — which dice are protected

**Requires:** the dice in the Chrome Fang controller's own Gig area.

**Implements:** `stealable` iterates `s.gig[victim]` — the victim's (= friendly) Gig area — and
`continue`s past protected indices, so they never enter the candidate list. `ResolveAttackStep`
takes `cands = stealable(s, a, victim)` and returns without stealing when `cands` is empty
(steps.py:336-337); when the attacker's power entitles it to more steals than there are legal
candidates (`n >= len(cands)`), it takes only the legal ones. Extra steals from power 10/20 are
therefore capped by the protection, which is right.

Note the protection is a *gate on the candidate list*, not a check at steal time, so attacking a
fully protected Gig area is still a legal attack that simply steals nothing — consistent with
ruling 009 ("if it empties after the declaration the attack proceeds and steals nothing").

**Match.**

## 5. "with value higher than their power" — the comparison

**Requires:** a die is protected iff its value is *strictly greater* than the power of the rival
Unit doing the stealing ("their" = the rival Units').

**Implements:** `pw = power(s, thief_unit, ATTACKING)` (the thief's power, in the attacking
situation, matching how `steal_count` computes the number of steals at steps.py:333) and
`if s.has_mod("protect_gt_power", victim) and value > pw: continue` — strictly greater, thief's
power, die face value (ruling 005: a stolen die keeps its face value). Equal value is *not*
protected, which is what "higher than" means. The mirror card Westbrook uses `value < pw` for "less
than", so the pair is consistent.

Verified by running the engine: friendly Gigs (20→12), (6→3), (20→7) against a 10-power rival
attacker gives `stealable == [1, 2]` — the 12 is protected, the 3 and the 7 are not.

**Match.**

---

## Verdict

Every clause matches. The card's own line, `EffectCtx.mod`, the expiry rule and `stealable` all
agree with the printed text on side, comparison direction, strictness and duration. I found no
discrepancy in Chrome Fang's implementation.

## One adjacent observation (not a Chrome Fang defect)

`protect_gt_power` is enforced only where a steal's candidate list is built through `stealable`.
Two card scripts build their own list: Appetite for Destruction (wnc.py:250) correctly calls
`stealable`, but **Gorilla Arms** (wnc.py:1027-1031) computes
`cands = [i for i, (_k, v) in enumerate(c.gigs(c.rival)) if v not in mine]` and calls `push_steals`
directly, and `StealOneStep` never re-checks protection (steps.py:293-306, only `would_steal`
replacement hooks run there). So a rival Unit wearing Gorilla Arms can take its bonus Gig from a
Chrome Fang player even when that die's value exceeds its power. The printed clause is violated in
that line, but the unfaithful script is Gorilla Arms', which ignores a global protection effect
when self-selecting steal targets; Chrome Fang's own implementation is the correct one. I am
recording it here rather than reporting it as this card's error.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-chrome-fang-1 — kill attempt: FAILED (finding survives)

card: `chrome-fang` — "PLAY: Until your next turn, rival Units can't steal friendly Gigs with
value higher than their power."

## What the engine actually does

Reproduced by hand (same line-up as the test, seed 1):

```
mods after play      [('protect_gt_power', 0, None, 4)]     # still live during the rival turn
power(psycho-squad)  9                                       # 6 + 3 from Gorilla Arms
stealable(...)       [0]                                     # only the d4 showing 2 — correct
after attack         gig[0] = []   gig[1] = [(4,2), (4,2), (12,11)]
```

The attack itself respects the prohibition (`steps.stealable`, src/cptcg/core/steps.py:264-275
filters the d12 out). Gorilla Arms then fires and takes the d12 showing 11 off a player whose
Chrome Fang says a power-9 rival Unit can't take it. `pytest ... -q -rx` reports **XFAIL**, i.e.
the engine fails as filed.

## Each kill route, and why it doesn't work

1. **A ruling covers it.** No. I read all 41 rows of docs/rulings.md. The steal-adjacent rows are
   009 (attacking an empty Gig area), 005 (stolen dice aren't rerolled) and 012 (BLOCKER redirect
   scope); none of them scopes a "can't steal" protection to the attack step, and none of 012,
   015, 019, 025, 026, 030 touches this. `git log -S"protect_gt_power"` shows the mod has existed
   unchanged since the original Phase-3 scripting commit — it was never revisited as a decision.

2. **The engine already handles it elsewhere.** No. `push_steals` / `do_steal` /
   `StealOneStep.run` (src/cptcg/core/steps.py:279-311) consult only the `would_steal`
   replacement watchers; `ops.steal_gig` (src/cptcg/core/ops.py:474) does no filtering;
   core/legal.py never mentions steal. `has_mod("protect_gt_power")` is read in exactly one place
   in the whole tree — `stealable`, steps.py:270.

   Worse for the defence: the codebase's own convention is the opposite of this behaviour.
   Appetite for Destruction, an *effect-driven* extra steal, routes through `stealable` before
   pushing its steal (src/cptcg/cards/sets/wnc.py:265-271), and Alt Cunningham's "when a rival
   Unit **would steal** a Gig" is honoured on every steal path via the `would_steal` hook
   (wnc.py:1019-1035, steps.py:302-305). So the engine already treats a Gear-driven steal by a
   host Unit as "a rival Unit stealing" for Alt Cunningham's replacement, but not for Chrome
   Fang's prohibition. Gorilla Arms (wnc.py:1057) is the single caller of `push_steals` that
   skips `stealable`.

3. **Unreachable board.** No. Gorilla Arms is Yellow RAM 3, so it needs two Yellow Legends
   (2+2=4); the third Legend can be Blue RAM 2, which covers Psycho Squad (Blue RAM 1) and Floor
   It (Blue RAM 1) — a legal deck. Chrome Fang (Red RAM 1) sits opposite with a Red Legend. Gear
   on a Unit, a rival Unit attacking a Gig area on its own turn, and the "until your next turn"
   window are all ordinary. The one artefact I found is that `board()` never removes a Gig die
   from the fixer list, so both sides hold 14 dice between them instead of 12 — but that is a
   property of the shared test helper (tests/conftest.py:95-98) used by the *passing* baseline
   test tests/cards/test_units.py:60 as well, and the surplus dice sit in the fixer areas and
   touch nothing in the steal path. It does not make this result an artefact.

4. **Asserts a script internal.** No. The two assertions are `(12, 11) in s.gig[0]` and
   `(12, 11) not in s.gig[1]` — Gig-area contents, the printed-text outcome.

5. **Misreads the text.** No. "rival Units" — Psycho Squad is a rival Unit of Chrome Fang's
   controller. "friendly Gigs" — the d12 is still in player 0's Gig area when Gorilla Arms takes
   it. "their power" can only be the rival Unit's (a Gig has no power), and it is 9. "value" is
   11 under the face reading and 12 under the die-size reading — protected either way. The
   prohibition names no step: it is about stealing, not about attacking, and nothing in
   docs/rules.md "Attacking" (lines 126-156) makes steal a word that only exists inside step 4.

   The one reading that would save the engine is that the second sentence of Gorilla Arms ("steal
   a rival Gig with a value not shared by a friendly Gig") is the *player* stealing rather than
   the Unit, so "rival Units can't steal" would not bind. The engine itself rejects that reading:
   `push_steals(c2.s, c2.host(), [i])` attributes the steal to the host Unit, `do_steal` records
   `("stole", unit)` and emits `("steal", unit, …)`, which is what makes Wraith Marauders,
   Maelstrom Goons and 6th Street Recruits ("when this/a friendly **Unit** steals") see it. You
   cannot have it both ways for one and the same steal.

## Verdict

Survives. Classification **B4-scope-or-condition**: the clause is implemented but enforced at
one call site only, so it binds the attack-step steal and not an effect-driven steal by the same
rival Unit in the same attack.

Note on where the fix belongs: `chrome-fang`'s one-liner (wnc.py:429) is arguably fine — the
narrow enforcement point is the engine's. Either `gorilla-arms` (wnc.py:1045-1053) filters its
candidates through `stealable` the way `appetite-for-destruction` does, or, better,
`StealOneStep.run` / `push_steals` checks the protection mods centrally so every future
effect-driven steal inherits it. The same defect is filed for `westbrook-netrunner`
(`protect_legends_lt_power`, steps.py:272) and one central fix settles both.
