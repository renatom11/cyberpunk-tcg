<!-- Working record for AUD-westbrook-netrunner-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Westbrook Netrunner  (`westbrook-netrunner`)

- type: UNIT, colour: BLUE, cost: 4, power: 5, RAM: 2
- keywords: none
- tags: ['NETRUNNER']

## Printed text (byte-exact from data/cards/wnc.json)

```
PLAY: Until your next turn, rival Legends can't steal friendly Gigs with value less than their power.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 411-415

@script("westbrook-netrunner")
def _():
    return CardScript(on_play=lambda c: c.mod("protect_legends_lt_power", c.player, until_my_next_turn=True))
```

---

# The finding, and the test that failed

# AUD-westbrook-netrunner-1

card: `westbrook-netrunner`

claim: the protection is only consulted on the attack-steal path (steps.stealable), so an effect-driven steal such as Gorilla Arms takes a Gig with value less than the rival Legend's power

failing test: `tests/cards/audit/test_a05.py::test_westbrook_stops_every_steal_of_a_gig_below_the_legends_power`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Westbrook Netrunner (`westbrook-netrunner`)

Printed text (byte-exact):

```
PLAY: Until your next turn, rival Legends can't steal friendly Gigs with value less than their power.
```

Implementation:

```python
# src/cptcg/cards/sets/wnc.py:411-413
@script("westbrook-netrunner")
def _():
    return CardScript(on_play=lambda c: c.mod("protect_legends_lt_power", c.player, until_my_next_turn=True))
```

The whole behaviour of the mod lives in the shared steal gate:

```python
# src/cptcg/core/steps.py:264-276
def stealable(s: GameState, thief_unit: int, victim: int) -> list[int]:
    out = []
    thief_is_legend = s.card(thief_unit).type is CardType.LEGEND
    pw = power(s, thief_unit, ATTACKING)
    for i, (_sides, value) in enumerate(s.gig[victim]):
        if s.has_mod("protect_gt_power", victim) and value > pw:
            continue
        if thief_is_legend and s.has_mod("protect_legends_lt_power", victim) and value < pw:
            continue
        out.append(i)
    return out
```

## 1. "PLAY:"

*Requires:* the effect fires when the Unit is played, once, as a `PLAY` trigger.

*Implements:* `CardScript(on_play=...)` (wnc.py:413). This is the standard `PLAY` hook used by
every other `PLAY:` card in the set (e.g. `chrome-fang` at wnc.py:406-408, `delamain-rideshare-ai`
at wnc.py:416-418). No condition, no cost, no choice — matching a bare `PLAY:`.

**Match.**

## 2. "Until your next turn,"

*Requires:* a continuous effect that is live from resolution of the PLAY trigger, covers the rest
of your turn and the whole of the Rival's turn, and ends when your next turn begins.

*Implements:* `until_my_next_turn=True` →
`EffectCtx.mod` (effects.py:320-322) computes `turns = 1 if s.active == self.player else 0` and
calls `s.add_mod(kind, subject, value, turns=turns)`, which stores expiry `s.turn + turns`
(state.py:223-226). `EndTurnCleanupStep` prunes with `s.mods = [m for m in s.mods if m[3] > s.turn]`
(steps.py:180) *before* `s.turn += 1`.

Played on your own turn N: expiry N+1. End of turn N → `N+1 > N`, kept. Rival's turn N+1 → live for
their whole turn. End of turn N+1 → `N+1 > N+1` false, dropped, immediately before your turn N+2
starts.

Probe (`scratchpad/wb_probe_std.py`, "duration"):

```
after play  turn 3 [('protect_legends_lt_power', 0, 4)]
rival turn  turn 4 [('protect_legends_lt_power', 0, 4)]
my next     turn 5 []
```

**Match.**

## 3. "rival Legends"

*Requires:* the restriction binds only thieves that are Legends, and only the Rival's (a friendly
Legend stealing is not restricted — and cannot steal from you anyway).

*Implements:* the clause is gated on `thief_is_legend = s.card(thief_unit).type is CardType.LEGEND`
(steps.py:266). This is the same idiom the engine uses for Legend-ness of an on-field card in
`fight()` (steps.py:351-352), so a GO SOLO Legend on the field still counts as a Legend — which is
the only way a Legend can be an attacker at all, and therefore the only way the card can ever do
anything. "Rival" is structural: `stealable(s, thief_unit, victim)` is always called with the
victim being the non-thief side (`victim = 1 - thief` in `ResolveAttackStep`, steps.py:332-333;
`1 - me` in `appetite-for-destruction`, wnc.py:250), and the mod is keyed to the victim, so only a
steal *from* the mod's owner is ever tested.

Probe: a rival non-Legend Unit (`psycho-squad`, power 6) was offered both of my dice
(`pick opts [(0,), (1,)]`, values 11 and 2) and took the 2 — unrestricted, correct.
Probe: my own face-up `v-streetkid` attacking the Rival's Gig area was offered both rival dice —
the mod does not protect the Rival.

**Match.**

## 4. "can't steal"

*Requires:* a hard prohibition (not "may not choose first", not a power/count reduction): protected
dice are simply not available to the steal.

*Implements:* the index is skipped, so it never enters `cands` in `ResolveAttackStep`
(steps.py:336) and never reaches `push_steals`/`StealOneStep`. If every die is protected,
`not cands` → the attack resolves and steals nothing (steps.py:337-338), which is the right
outcome: the Gig-area attack is still a legal declaration (ruling 009 only bars attacking an
*empty* Gig area), it just yields nothing. A Legend with power ≥ 10 that would steal 2-3 dice is
likewise capped to the unprotected ones (`if n >= len(cands): push_steals(s, a, cands)`).

**Match** for every steal that goes through the attack step.

*Noted gap (not this card's script):* `gorilla-arms` (wnc.py:1024-1032) queues its bonus steal with
`push_steals` directly and filters candidates only by `v not in mine` — it never consults
`stealable`. A rival Legend wearing Gorilla Arms therefore steals a die this card protects.
Verified (`scratchpad/wb_probe4.py`): with the mod live and my Gig area `[(12,11),(4,2)]`, a
power-6 Gorilla-Armed `v-streetkid` took **both** dice, including the protected `2`. The sibling
card `appetite-for-destruction` (wnc.py:250) does call `stealable`, and the protection is a
central engine gate, so this reads as a defect in `gorilla-arms`' own script (it equally defeats
`chrome-fang`'s `protect_gt_power`), not a mis-implementation of Westbrook's line. Recording it
here for whoever audits Gorilla Arms.

## 5. "friendly Gigs"

*Requires:* only the controller's own Gig area is protected.

*Implements:* the mod's subject is `c.player` (wnc.py:413), where `EffectCtx.player = s.i_owner[inst]`
(effects.py:25) — the controller of Westbrook. The gate reads `s.has_mod("protect_legends_lt_power",
victim)` (steps.py:272), i.e. it is the *victim's* mod that protects the victim's dice, and the loop
walks `s.gig[victim]` only. Subject is a player index, and no other mod kind shares this key, so
there is no instance/player id collision.

Probe (third case above) confirms the Rival's dice are untouched by my copy of the mod.

**Match.**

## 6. "with value less than their power"

*Requires:* strictly `die value < the Legend's power`. A die whose value *equals* the Legend's power
is still stealable; a die worth more is still stealable.

*Implements:* `value < pw` with `pw = power(s, thief_unit, ATTACKING)` — the *thief's* power ("their"
can only refer to the Legends; dice have no power), computed with the same situation flag and the
same `power()` call used for `steal_count` in the attack step (steps.py:334), so Gear, temp power
and auras on the Legend are included. `value` is the second element of the `(sides, value)` Gig
tuple, consistent with `street_cred` (state.py:220) and `EffectCtx.choose_gig` (effects.py:344).

Boundary probes with `v-streetkid` (power 6):

- my Gig area `[(8,6),(4,2)]` → the Legend auto-stole the `6` and could not touch the `2`
  (equality is *not* protected — correct for "less than").
- existing regression `tests/cards/test_units.py::test_westbrook_protects_from_legends`:
  `[(4,2),(12,11)]` → the `11` is taken, the `2` is protected.

Also note the direction is genuinely the opposite of the neighbouring `chrome-fang`
("value higher than their power" → `protect_gt_power`, `value > pw`), and each card is wired to its
own key; the two are not swapped.

**Match.**

## Verdict

All six clauses of the printed line are implemented faithfully: correct trigger, correct duration
window, correct actor restriction (Legends only, Rival side only), hard prohibition, correct side
of the board protected, and the correct strict `<` comparison against the thieving Legend's power.
I found no discrepancy in this card's script or in the helper it relies on.

The only behavioural hole I could produce — a rival Legend equipped with Gorilla Arms stealing a
protected die — comes from `gorilla-arms` bypassing the engine's `stealable` gate, affects
`chrome-fang` identically, and belongs to that card's audit rather than this one.

---

# Skeptic 2 — told the finding is presumed wrong

# Kill attempt — AUD-westbrook-netrunner-1

**Verdict: SURVIVES.** Classification **B4-scope-or-condition** (the printed prohibition is
enforced on one code path only; its real scope is every steal).

Printed text: `PLAY: Until your next turn, rival Legends can't steal friendly Gigs with value
less than their power.`

Reproduction (`python -m pytest 'tests/cards/audit/test_a05.py::test_westbrook_stops_every_steal_of_a_gig_below_the_legends_power' -q -rx`) → **XFAIL**, i.e. the engine really does let the
protected die go. Instrumented probe (scratchpad, not committed):

```
p0 gig [(6,3),(12,11)]   power(V) = 9   mods [('protect_legends_lt_power', 0, None, 4)]
after Attack(v-streetkid):  p0 gig []   p1 gig [(4,2), (12,11), (6,3)]
```

The attack step itself obeyed the card: with power 9 `steal_count` is 1 and `stealable`
(`src/cptcg/core/steps.py:264-276`) returned exactly one index — the (12,11) — so no choice was
offered and the protected `3` was correctly withheld. The `(6,3)` left player 0's Gig area
afterwards, from Gorilla Arms' bonus steal (`src/cptcg/cards/sets/wnc.py:1045-1053`), which calls
`push_steals(c2.s, c2.host(), [i])` on a candidate list filtered only by `v not in mine`. The
filer's mechanism is exactly right.

## The five kills, each tried and each failed

**1. A ruling deliberately covers it.** No. `docs/rulings.md` runs 001-041 and none of them is
about the reach of a "can't steal" prohibition. The usual suspects were read in full and none
touches this: 012 (BLOCKER redirect scope), 015 (GO SOLO spendability/slot), 019 (once-per-turn
scope), 025 (payment order), 026 (field limit), 030 (⊡ on Gear). 009 is the only steal-adjacent
row and it only bars attacking an *empty* Gig area.

I tried hardest to build a kill on **015** ("Not spendable — *it is a Unit now*") plus the GO SOLO
keyword text ("play it as a ready Unit", `docs/rules.md:90`): if a GO SOLO'd Legend on the field is
a Unit and no longer a Legend, V is not a "rival Legend" and Westbrook never applies to this board.
That argument is dead on the card data: `rogue-amendiares-preem-solo` is a Legend with GO SOLO
whose printed text reads *"When a friendly **Legend** steals a Gig…"*, and the only way any Legend
can ever steal is by attacking from the field. If an on-field GO SOLO Legend stopped being a
Legend, that card — and Westbrook itself — would be blank text. So the card type survives GO SOLO,
which is also what `steps.py:266` (`s.card(thief_unit).type is CardType.LEGEND`) assumes, and what
the attack-step half of the probe above demonstrates.

**2. The engine already handles it elsewhere.** No. `protect_legends_lt_power` is written in one
place (`wnc.py:434`) and read in exactly one place (`steps.py:272`), inside `stealable`. Callers of
`stealable` are `ResolveAttackStep` (`steps.py:336`) and `appetite-for-destruction`
(`wnc.py:270,276`) — nothing else. `push_steals` (`steps.py:278-282`), `StealOneStep`
(`steps.py:286-306`) and `do_steal` (`steps.py:309-312`) never consult it; `StealOneStep`'s only
gate is the `would_steal` replacement list (used by `alt-cunningham-mother-of-daemons`), which
Westbrook does not register. `core/ops.py:474 steal_gig` is a pure mover. `core/legal.py` is not on
this path at all. Grepped the whole tree: `grep -rn protect_legends_lt_power src/` returns two hits.

Worse for the kill: the engine's *own* convention contradicts it. The set's other effect-driven
steal, `appetite-for-destruction` ("it also steals a Gig"), routes its candidates through
`stealable` (`wnc.py:276`). So effect steals respecting protections is established engine design,
not the filer's invention; `gorilla-arms` is the outlier.

**3. Unreachable board.** No. Player 1 holds a face-up `v-streetkid` on the field wearing
`gorilla-arms`. Legends reach the field by GO SOLO (ruling 033: every costed Legend in this set has
it; V costs 5 and carries the keyword), and Gear reaches a Legend legally — `docs/rules.md:73`
("equip it to a friendly Unit or Legend") and `core/legal.py::gear_hosts` — and ruling 016 says
Gear on a Legend that Go Solos moves with it. V went solo on an earlier turn, so ruling 027's
arrival Lag is long gone (`docs/rulings.md` 039: Lag clears at end of turn). Player 0 has 9 Eddies
for a cost-4 Unit, and a two-die Gig area on turn 3 is ordinary.

**4. Asserts a script internal.** No. The two assertions are `(6, 3) in s.gig[0]` and
`(6, 3) not in s.gig[1]` — which Gig area a die sits in. That is the printed outcome and nothing
else; no mod names, no trigger counts.

**5. Misreads the printed text.** No. "their power" can only be the Legends' (dice have no power);
V's power is 6 + 3 Gear = 9, and 3 < 9. "value" is the die face, matching `state.py`'s
`(sides, value)` tuple. "can't steal" is unqualified — it names the act, not the attack step that
usually causes it, and the set proves steals happen outside attacks (`appetite-for-destruction`,
`gorilla-arms`, and `take-control`'s "steals 1 fewer Gig" all speak of steals as a thing effects
touch). Authority order does not help either: `docs/rules.md:130-141` describes the attack-step
steal but never says it is the only kind, so there is no doc to set against the card text.

The best surviving argument *against* the finding is a thin one, and I could not make it stand up:
that Gorilla Arms' second sentence ("steal a rival Gig…") is addressed to the player, so the
*Legend* is not the thief and Westbrook's clause does not bind it. But Gorilla Arms' own first
sentence attributes steals to the host ("The first time **this Unit** steals"), `maelstrom-goons`,
`6th-street-recruits`, `v-roamer-of-the-badlands` and `rogue-amendiares-preem-solo` all read steals
as done *by* a Unit or Legend, and the engine agrees (`do_steal` dispatches `("steal", unit, …)`
with `unit = host`). A bonus steal from the Legend's own arms is the Legend stealing.

## Honest caveat on where the fix belongs

The deviation is real, but `westbrook-netrunner`'s own script (`wnc.py:434`) is faithful: it sets a
mod, and the mod is a shared engine gate. The same hole voids `chrome-fang`'s `protect_gt_power`
(sibling finding AUD-chrome-fang-1). The fix is one change on the shared path — filter in
`push_steals`/`StealOneStep`, or make `gorilla-arms` call `stealable` the way
`appetite-for-destruction` already does — not an edit to Westbrook's line.
