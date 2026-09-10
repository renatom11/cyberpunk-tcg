# Writing card scripts

Static card data lives in `data/cards/*.json`. Behaviour lives in Python, bound by card id:

```python
@script("japantown-jonin")
def _():
    return CardScript(on_play=lambda c: temp_power_one(c, c.units(), 2))
```

Cards with no rules text (or only keyword reminder text) need **no script** — the JSON is enough.
Cards whose text implies an effect but have no script load as `needs_script` and fail deck
validation unless `--allow-unscripted` is passed, so nothing silently plays as vanilla.

## The one rule

**Effects never block.** A hook does its work and returns. Anything that needs a decision goes
through `ctx.choose(...)` (or `choose_many`, `choose_one`, `maybe`, `adjust_up_to`, ...), which
queues the question and takes a *continuation* to run with the answer.

A continuation must use the ctx it is **given**, never the enclosing one:

```python
def play(c):
    c.choose(c.rival_units(), lambda c2, u: c2.defeat(u))   # c2, not c
```

The enclosing `c` is bound to whichever state existed when the question was asked. A search agent
resolves the same question on cloned states, and only the ctx passed into the continuation
points at the right clone.

## Hooks (`CardScript` fields)

| Field | When |
|---|---|
| `on_play`, `on_call`, `on_attack`, `on_defeated` | The four printed timing triggers. Gear's `on_attack` / `on_defeated` fire when its *host* attacks / is defeated. |
| `on_event(ctx, ev)` | Any event while the card is active (Units and Gear in play, face-up Legends). `ev` is a tuple; see below. Declare the kinds the hook reacts to with `events=frozenset({"steal", ...})` so the engine skips it for every other event; `None` (the default) means all. The hook must still test `ev[0]` itself. |
| `power_mod(ctx, unit, sit)` | Continuous power delta for any unit. `sit` is a bit set of `ATTACKING`, `FIGHTING`, `VS_UNIT`, `VS_LEGEND`. |
| `kw_mod(ctx, inst, kw)` | Continuous, conditional keyword grant: `True` if this card gives `inst` the keyword *right now*. Read on every `has_keyword` call, so a condition that changes mid-turn (Adrenaline Converter's Gig count) stays correct; use `c.grant(inst, KW)` instead for "this turn" grants. |
| `cost_mod(ctx, player, inst, go_solo)` | Delta to the cost of anyone playing `inst`. |
| `self_cost(ctx, player, base)` | The cost to play *this* card ("play this for -1 €$ per ..."). |
| `attack_perm(ctx, (units_ok, gigs_ok))` | Override attack permission for this Unit; receives the base permission. |
| `would_defeat(ctx, inst)` | Replacement: return `True` to take over the defeat. |
| `would_steal(ctx, thief_unit, victim, index)` | Return `True` if you took over the steal (e.g. asked a question). |
| `unblockable(ctx)` | This attacking Unit can't be blocked. |
| `abilities` | Tuple of `Ability(effect, cost, self_spend, quick, legal, label)`. `cost` may be a callable. |
| `extra` | Rare static flags: `cant_attack`, `wins_vs_tag`, `suppress_new_units`, `attack_ready_blockers_if_more_cred`. |

## Events

`("steal", unit, thief, sides, value)`, `("fight_won", unit, loser, margin)`,
`("fight_lost", unit, winner)`, `("blocked", blocker, attacker)`, `("spent", inst)`,
`("played", inst, player)`, `("attack", unit, player)`, `("defeated", inst, owner, was_equipped)`,
`("called", inst, player)`, `("gig_rolled", player, sides, value)`,
`("gig_changed", actor, owner, index)`, `("start_turn", player)`, `("end_turn", player)`.

"The first time ... each turn": `if c.once("key"):` — true once per card per turn.

"The next time ... this turn" effects that outlive a Program: register a listener,
`c.mod("listener", c.player, fn)` where `fn(state, ev)` runs on every event until end of turn.

## Temporary effects

`c.temp_power(inst, delta, cond)`, `c.grant(inst, KEYWORD)`, `c.mod(kind, subject, value,
until_my_next_turn=False)`. Mods the engine understands: `cant_attack`, `must_attack`,
`attack_units_now`, `attack_gigs_now`, `attack_ready_units`, `steal_fewer`,
`no_defeat_in_fight`, `next_fight_no_defeat`, `next_loss_defeats_winner`, `protect_gt_power`,
`protect_legends_lt_power`, `cost_next_program`, `cost_go_solo`, `defeat_at_end`.

## Testing

Every scripted card has a scenario in `tests/cards/`. Build a board with the test helpers:

```python
s = board(pool, Side(hand=["over-the-edge"], eddies=9, gig=[(20, 6)]),
          Side(field=["psycho-squad", "animals-wrecker"]))
play(s, "over-the-edge")
assert s.i_zone[find(s, "psycho-squad")] == Zone.TRASH
```

A choice with a single option resolves automatically, so count your `Pick`s from what the
*engine* will actually ask. `during_main(s, fn)` / `defeat_now(s, inst)` run an effect as if it
happened mid-turn and resolve everything it queues.
