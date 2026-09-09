"""State-mutation primitives.

Everything that changes a GameState goes through here — the engine, the effect atoms and the
tests all use the same handful of verbs, so an invariant (a card is in exactly one zone, Gear
travels with its host, dice are conserved) is enforced in one place.
"""

from __future__ import annotations

from cptcg.core.enums import (F_GO_SOLO, NO_INST, NZONE, CardType, EndReason, Keyword,
                              Trigger, Zone)
from cptcg.core.state import ONCE_CALLED, GameState


# ------------------------------------------------------------------- zones
def move(s: GameState, inst: int, zone: Zone, *, bottom: bool = False, host: int = NO_INST) -> None:
    """Move an instance (and any Gear equipped to it) to ``zone`` of its owner."""
    owner = s.i_owner[inst]
    old = s.i_zone[inst]
    s.z[owner * NZONE + old].remove(inst)
    dst = s.z[owner * NZONE + zone]
    if bottom:
        dst.insert(0, inst)
    else:
        dst.append(inst)
    s.i_zone[inst] = zone
    s.i_host[inst] = host
    if zone is not Zone.FIELD and zone is not Zone.LEGENDS:
        s.i_spent[inst] = 0
        s.i_lag[inst] = 0
        s.i_faceup[inst] = 0
        s.i_flags[inst] = 0
    # Gear travels with its host; if the host leaves play, so does the Gear.
    for g in [i for i in s.z[owner * NZONE + old] if s.i_host[i] == inst]:
        move(s, g, zone, bottom=bottom, host=inst if zone in (Zone.FIELD, Zone.LEGENDS) else NO_INST)
    s.emit("move", inst, old, zone)


def draw(s: GameState, player: int, n: int = 1) -> int:
    """Draw up to ``n``. Drawing from an empty deck loses the game (rival wins). Returns count drawn."""
    deck = s.z[player * NZONE + Zone.DECK]
    drawn = 0
    for _ in range(n):
        if not deck:
            end_game(s, winner=1 - player, reason=EndReason.DECKOUT)
            return drawn
        inst = deck[-1]
        move(s, inst, Zone.HAND)
        drawn += 1
    s.emit("draw", player, drawn)
    return drawn


def shuffle_deck(s: GameState, player: int) -> None:
    s.rng.shuffle(s.z[player * NZONE + Zone.DECK])
    s.emit("shuffle", player)


def trash_top(s: GameState, player: int, n: int) -> list[int]:
    """Trash the top ``n`` cards of the deck, preserving order. Does *not* trigger deckout."""
    deck = s.z[player * NZONE + Zone.DECK]
    out = []
    for _ in range(min(n, len(deck))):
        inst = deck[-1]
        move(s, inst, Zone.TRASH)
        out.append(inst)
    return out


def bottom_deck(s: GameState, inst: int) -> None:
    move(s, inst, Zone.DECK, bottom=True)


# ----------------------------------------------------------------- economy
def payable_sources(s: GameState, player: int, exclude: int = NO_INST) -> list[int]:
    """Ready sources of €$ in payment-priority order: Eddies, face-down Legends, face-up Legends."""
    spent = s.i_spent
    base = player * NZONE
    eddies = [i for i in s.z[base + Zone.EDDIES] if not spent[i]]
    legs = [i for i in s.legends(player) if not spent[i] and i != exclude]
    facedown = [i for i in legs if not s.i_faceup[i]]
    faceup = [i for i in legs if s.i_faceup[i]]
    return eddies + facedown + faceup


def available(s: GameState, player: int, exclude: int = NO_INST) -> int:
    return len(payable_sources(s, player, exclude))


def pay(s: GameState, player: int, amount: int, exclude: int = NO_INST) -> None:
    if amount <= 0:
        return
    srcs = payable_sources(s, player, exclude)
    if len(srcs) < amount:
        raise RuntimeError(f"player {player} cannot pay {amount} (has {len(srcs)})")
    for inst in srcs[:amount]:
        s.i_spent[inst] = 1
    s.emit("pay", player, amount)


def spend(s: GameState, inst: int) -> None:
    s.i_spent[inst] = 1


def ready(s: GameState, inst: int) -> None:
    s.i_spent[inst] = 0


# ------------------------------------------------------------------- power
def power(s: GameState, inst: int) -> int:
    """Effective power: printed + equipped Gear + temporary modifiers.

    Static/aura modifiers are layered on here in Phase 3. Never cached — buffs can't go stale.
    """
    d = s.card(inst)
    p = d.power or 0
    owner = s.i_owner[inst]
    defs = s.reg.defs
    for g in s.z[owner * NZONE + s.i_zone[inst]]:
        if s.i_host[g] == inst:
            p += defs[s.i_card[g]].power or 0
    for target, delta, _tag in s.temp_power:
        if target == inst:
            p += delta
    return p


def add_temp_power(s: GameState, inst: int, delta: int, tag: int = 0) -> None:
    s.temp_power.append((inst, delta, tag))


def steal_count(pwr: int) -> int:
    """Gigs stolen by a Gig-area attack: 0 at power 0, one more per 10 power above that."""
    return 0 if pwr <= 0 else 1 + pwr // 10


# ------------------------------------------------------------------ combat
def defeat(s: GameState, inst: int) -> None:
    """Send a card in play to the trash (or out of the game for a GO SOLO Legend)."""
    if s.i_zone[inst] not in (Zone.FIELD, Zone.LEGENDS):
        return
    d = s.card(inst)
    dest = Zone.REMOVED if s.i_flags[inst] & F_GO_SOLO else Zone.TRASH
    s.emit("defeated", inst)
    move(s, inst, dest)
    if d.type is CardType.UNIT or d.type is CardType.LEGEND:
        push_trigger(s, Trigger.DEFEATED, inst)


# -------------------------------------------------------------------- dice
def gain_gig(s: GameState, player: int, sides: int) -> int:
    """Take ``sides`` from the fixer area, roll it, put it in the Gig area. Returns the value."""
    s.fixer[player].remove(sides)
    value = s.rng.die(sides)
    s.gig[player].append((sides, value))
    s.emit("gig", player, sides, value)
    return value


def steal_gig(s: GameState, thief: int, index: int) -> None:
    victim = 1 - thief
    die = s.gig[victim].pop(index)
    if s.cfg.reroll_stolen_dice:
        die = (die[0], s.rng.die(die[0]))
    s.gig[thief].append(die)
    s.emit("steal", thief, die)


def adjust_gig(s: GameState, player: int, index: int, delta: int) -> None:
    sides, value = s.gig[player][index]
    s.gig[player][index] = (sides, max(1, min(sides, value + delta)))
    s.emit("adjust", player, index, delta)


def set_gig(s: GameState, player: int, index: int, value: int) -> None:
    sides, _ = s.gig[player][index]
    s.gig[player][index] = (sides, max(1, min(sides, value)))


# --------------------------------------------------------------- triggers
def push_trigger(s: GameState, kind: Trigger, inst: int) -> None:
    """Queue a card's trigger hook, if it has one. Hooks run as steps so they never block."""
    sc = s.card(inst).script
    if sc is None:
        return
    hook = (sc.on_play, sc.on_call, sc.on_attack, sc.on_defeated)[kind]
    if hook is not None:
        from cptcg.core.steps import HookStep
        s.stack.append(HookStep(hook, inst))


# ------------------------------------------------------------------- legend
def call_legend(s: GameState, player: int, inst: int) -> None:
    s.i_faceup[inst] = 1
    s.i_known[inst] = 0b11
    s.once[player] |= ONCE_CALLED
    s.emit("call", player, inst)
    push_trigger(s, Trigger.CALL, inst)


# --------------------------------------------------------------------- end
def end_game(s: GameState, winner: int, reason: EndReason) -> None:
    if s.over:
        return
    s.over = True
    s.winner = winner
    s.end_reason = reason
    s.pending = None
    s.stack.clear()
    s.emit("end", winner, reason)


def has_keyword(s: GameState, inst: int, kw: Keyword) -> bool:
    """Printed keyword or one granted this turn (grants are Phase 3 temp flags)."""
    return kw in s.card(inst).keywords
