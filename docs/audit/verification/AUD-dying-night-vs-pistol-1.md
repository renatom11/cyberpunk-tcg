<!-- Working record for AUD-dying-night-vs-pistol-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Dying Night — V's Pistol  (`dying-night-vs-pistol`)

- type: GEAR, colour: BLUE, cost: 2, power: 2, RAM: 2
- keywords: none
- tags: ['MERC', 'WEAPON']

## Printed text (byte-exact from data/cards/wnc.json)

```
ATTACK: Decrease a Gig by up to 2. At the end of your turn, if this Unit is named "V", ready 2 Eddies.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 705-714

@script("dying-night-vs-pistol")
def _():
    def ev(c, e):
        h = c.host()
        if e[0] == "end_turn" and e[1] == c.player and h >= 0 and c.d(h).name == "V":
            c.ready_eddies(2)
    return CardScript(on_attack=lambda c: c.adjust_up_to([c.player, c.rival], -2, -1, prompt="Decrease a Gig"),
                      on_event=ev, events=frozenset({"end_turn"}))
```

---

# The finding, and the test that failed

# AUD-dying-night-vs-pistol-1

card: `dying-night-vs-pistol`

claim: readies 2 Eddies for a face-up Legend host named V, but the text says 'this Unit'

failing test: `tests/cards/audit/test_a08.py::test_dying_night_ready_2_only_when_the_host_is_a_unit`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Dying Night — V's Pistol (`dying-night-vs-pistol`)

Printed text (byte-exact, single line — no `\n` anywhere in it):

```
ATTACK: Decrease a Gig by up to 2. At the end of your turn, if this Unit is named "V", ready 2 Eddies.
```

Script (`src/cptcg/cards/sets/wnc.py` lines 705-714):

```python
@script("dying-night-vs-pistol")
def _():
    def ev(c, e):
        h = c.host()
        if e[0] == "end_turn" and e[1] == c.player and h >= 0 and c.d(h).name == "V":
            c.ready_eddies(2)
    return CardScript(on_attack=lambda c: c.adjust_up_to([c.player, c.rival], -2, -1, prompt="Decrease a Gig"),
                      on_event=ev, events=frozenset({"end_turn"}))
```

## Layout premise (used by clauses 3 and 4)

Throughout `data/cards/wnc.json`, **independent abilities on one card are separated by `\n`**, and
sentences that share a line belong to the same ability. Every multi-ability card follows it:
`dexter-deshawn-one-last-chance` (`'PLAY / ATTACK: ...\nDEFEATED: ...'`), `sandevistan`
(`'(Equip ...)\nAt the end of your turn, ready this Unit or Legend.'`), `v-roamer-of-the-badlands`,
`panam-palmer-nomad-cavalry`, `jackie-welles-ride-or-die-choom`, `sasha-yakovleva-...`,
`the-relic-experimental-biochip`, `kiroshi-optics`. Conversely every card whose second sentence sits
on the same line as a trigger keyword is one ability with a follow-on sentence:
`evelyn-parker-scheming-siren` (`'ATTACK: Draw 1. Then, if you have more ★ ... discard 1.'`),
`royce-dont-call-me-simon`, `caliber-totentanzs-top-dog`, `trust-no-one`, `industrial-assembly`.

Dying Night has **no** `\n`: the whole printed text is the one `ATTACK:` ability. So the second
sentence is a delayed effect set up **by the attack**, not a standing ability.

## 1. `ATTACK:` — trigger

Requires: fires when this Gear's host attacks, after the target is declared (ruling 023 /
`steps.attack_triggers`, which pushes `Trigger.ATTACK` for each Gear on the attacker before the
Unit's own). Implemented by `on_attack=...`; docs/effects-authoring.md states Gear's `on_attack`
fires when its host attacks. **Match.**

## 2. "Decrease a Gig by up to 2."

Requires: one Gig, either player's (unqualified "a Gig"; the set says "a friendly Gig" when it means
friendly — `jackie-welles-pour-one-out-for-me`, line 1370 — and the other eleven unqualified
`adjust_up_to` scripts in this file all pass `[c.player, c.rival]`); decrease only; by 1 or 2;
"up to" includes zero, so declining must be offered; ruling 037 means an amount that would take the
die off its face is simply not available.

`adjust_up_to([c.player, c.rival], -2, -1, ...)` enumerates `a ∈ {-2,-1}` over both players' dice,
keeps only `1 <= v + a <= k`, and passes `optional=True` so the decline is an explicit option.
No `cont`/`after` is passed and nothing hangs off this decision, so the `cont`-vs-`after` trap
documented in `EffectCtx.adjust_up_to` is not engaged here. **Match.**

## 3. "At the end of your turn, ... ready 2 Eddies." — conditional on the ATTACK

Requires (given the layout premise): the end-of-turn effect exists **only because the host attacked
this turn**. On a turn in which the equipped Unit does not attack, the `ATTACK` ability never
resolves and nothing readies at end of turn. The controller-side test ("your turn") is right in both
readings, since the host can only attack on its controller's turn.

Script: the end-of-turn behaviour is a standing `on_event` trigger (`events={"end_turn"}`) with no
link whatsoever to the attack. It readies 2 Eddies at the end of **every** one of the controller's
turns while a host named "V" is equipped — no attack required, and it also fires on turns where the
host was played that turn (Lag), was already spent for something else, or the Gear was equipped
mid-turn after combat.

The engine has the machinery for the conditional form: `delamain-cab` (line 909) tests
`("stole", c.inst) in c.s.used` from an `end_turn` handler, and `c.once(...)` /
`c.mod("listener", ...)` exist for the same purpose. Nothing analogous is done here — there is no
per-turn "attacked" flag set by `on_attack` and tested by `ev`. **Mismatch: the ATTACK precondition
is dropped, so the ability fires unconditionally every turn.** This is the most serious finding: it
converts a once-per-attack reward into a free 2-Eddie-per-turn engine.

## 4. "if this Unit is named \"V\""

Requires: the host is a **Unit** named "V". The card names are stored as `name` + `subtitle`
(`v-corporate-exile`, `v-roamer-of-the-badlands`, `v-streetkid` all have `name == "V"`), so the
string test itself is right. The type restriction is not: `legal.gear_hosts` allows Gear on friendly
Units **and face-up Legends**, and this set deliberately writes "this Unit or Legend" when a Gear
means both (`sandevistan`, `the-relic-experimental-biochip`). Dying Night says only "this Unit".

Script: `h >= 0 and c.d(h).name == "V"` — no `is_type(h, CardType.UNIT)` and no field check. Two of
the three "V" cards in the set (`v-corporate-exile`, `v-streetkid`) are **Legends**, so equipping
Dying Night to a face-up V in the Legends area satisfies the script's test while the printed text
does not. **Mismatch (narrower than clause 3, and it compounds it: a Legend host never attacks from
the Legends area at all, yet under the script it still pays out every turn).**

Timing of the check itself (evaluated at end of turn, not at attack time) is fine — the sentence
puts the condition after "At the end of your turn".

## 5. "ready 2 Eddies"

Requires: ready up to 2 spent Eddies belonging to the Gear's controller. `c.ready_eddies(2)` →
`ops.ready_eddies(s, self.player, 2)`, which unspends at most 2 spent cards in that player's Eddies
zone and returns how many. "Up to" semantics are implicit and harmless. **Match.**

## Verdict

Clause 2, 1 and 5 are faithful. The end-of-turn payout is implemented as an unconditional standing
trigger instead of an effect set up by the `ATTACK` ability (clause 3), and its host test omits the
"Unit" restriction (clause 4). Most serious: clause 3.

---

# Skeptic 2 — told the finding is presumed wrong

# Kill attempt — AUD-dying-night-vs-pistol-1

**Verdict: SURVIVES.** I tried all five kill routes and none of them closes.

Card: `dying-night-vs-pistol`, printed text (byte-exact, one line, no `\n`):

```
ATTACK: Decrease a Gig by up to 2. At the end of your turn, if this Unit is named "V", ready 2 Eddies.
```

Script (`src/cptcg/cards/sets/wnc.py:778-787`): `h = c.host()` … `h >= 0 and c.d(h).name == "V"` —
the host's **name** is tested, its type/zone never is.

## Route 1 — a ruling deliberately covers it? No.

I read every row of `docs/rulings.md`. The Gear rows are 016 (no re-equip), 030 (⊡ on Gear spends
the Gear) and 034 (Gear follows a removed host). None of them says anything about what "this Unit"
in Gear text denotes. The trap-list rows do not touch this: 012 is BLOCKER redirect scope, 019 is
once-per-turn scope, 025 payment order, 026 field limit, 030 the spend symbol.

Row **015** is the closest, and it cuts *against* the kill: "A `GO SOLO` Legend on the field …
**(it is a Unit now)**". The parenthesis is the row's premise — a Legend becomes a Unit *by being
played to the field*. A face-up Legend sitting in the Legends area is therefore not one. Rows 031,
034 and 040 likewise speak of Legends in the Legends area as Legends, never as Units, and
`docs/rules.md` ("Reading your cards" → Type) lists Legend and Unit as disjoint types.

## Route 2 — the engine handles it elsewhere? No.

`core/effects.py:40` `host()` returns `s.i_host[inst]` with no zone or type filter; `ready_eddies`
(`effects.py:324` → `ops.ready_eddies`) is unconditional. `core/legal.py:18-20` `gear_hosts` =
`s.units(player) + [face-up Legends]`, so the Legends-area host is an engine-offered, legal host,
and nothing downstream re-checks it. I reproduced it directly, and isolated the cause:

```
no gear:      available(s,0) 3 -> 3
dying night:  available(s,0) 3 -> 5      # the Gear on a Legends-area Legend readied 2 Eddies
```

## Route 3 — unreachable board? No.

- Deckbuilding: Dying Night is Blue RAM 2; the test's third Legend is
  `wakako-okada-peace-and-harmony` (Blue, RAM 2), so Blue RAM 2 is inside the limit, and `floor-it`
  is Blue RAM 1. The deck is legal.
- The host `v-streetkid` is face-up (Call a Legend) in the Legends area, and `legal.gear_hosts`
  offers exactly that as a Play target for a 2-cost Gear. `eddies=2, spent_eddies=2` is an ordinary
  mid-turn state (two Eddies sold earlier, both spent); `available(s,0) == 3` before EndTurn
  confirms it (0 ready Eddies + 3 payable Legends, ruling 040). Player 1's start phase then draws
  from a 2-card deck without decking out.

## Route 4 — asserts a script internal? No.

The assertion is `ops.available(s, 0)` — how many €$ the player can actually pay with — before and
after `EndTurn()`. That is the printed outcome of "ready 2 Eddies" observed from the outside, not a
peek at `i_host`, a flag, or a hook.

## Route 5 — misreads the text? No. This is where I pushed hardest.

Best kill available: read "this Unit" as loose shorthand for "the card this Gear is equipped to".
The set's own vocabulary refuses it. Of the 17 Gear in WNC, five spell out **"this Unit or
Legend"** when they mean both — `sandevistan` ("ready this Unit or Legend"), `zetatech-faceplate`,
`netwatch-netdriver`, `tetratronic-rippler`, `arasaka-emergency-radioport` — and nine equip
parentheticals read "a friendly **Unit or face-up Legend**". Dying Night says "this Unit". Every
*other* "this Unit" Gear (`adrenaline-converter`, `satori`, `gorilla-arms`, `deadman-transmitter`,
`the-relic`) carries an effect that is inherently field-only (ADRENALINE, fights, steals, defeat),
so their scripts need no host test and their silence proves nothing. Dying Night's end-of-turn
clause is the one place in the set where "this Unit" actually discriminates — so it is the one
place the word is load-bearing.

Second attempt, from the layout: the whole text is a single line with no `\n`, unlike sibling cards
that separate abilities with newlines (`v-roamer-of-the-badlands`), so "At the end of your turn …"
can be read as a delayed effect created by the `ATTACK` trigger. That reading does **not** rescue
the engine: a Legend in the Legends area never attacks, so the payout would still be wrong here,
and the script (an unconditional `end_turn` listener) would additionally be wrong for a Unit host
that never attacked. Both readings agree the test's expectation is right.

## What the fix must be (and a caveat for whoever lands it)

Gate on the host's **zone**, not its `CardType`: `Zone.FIELD` = a Unit, `Zone.LEGENDS` = not. A V
Legend that has GO SOLO'd onto the field *is* a Unit (ruling 015) and must keep paying out; a
`d(h).type is UNIT` test would silently break that case and is the one way to over-fix this.

Classification: **B4** (scope/condition — the printed condition is narrower than the implemented
one). Test is sound; the failing assertion (`5 == 3`) is a printed-text outcome on a legal board.
