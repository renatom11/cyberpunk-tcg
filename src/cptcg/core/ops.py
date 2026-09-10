"""State-mutation primitives.

Everything that changes a GameState goes through here — the engine, the effect atoms and the
tests all use the same handful of verbs, so an invariant (a card is in exactly one zone, Gear
travels with its host, dice are conserved) is enforced in one place.

Rule for anything that needs a player decision: push an AskStep (see ``ask``). Never set
``s.pending`` from inside a hook — two hooks in one dispatch would trample each other.
"""

from __future__ import annotations

from cptcg.core.enums import (F_GO_SOLO, NO_INST, NZONE, CardType, EndReason, Keyword,
                              Trigger, Zone)
from cptcg.core.state import ONCE_CALLED, GameState

# power() situations (bit flags)
ATTACKING = 1
FIGHTING = 2
VS_UNIT = 4
VS_LEGEND = 8


# ------------------------------------------------------------- scripts in play
_FIELD = Zone.FIELD
_LEGENDS = Zone.LEGENDS


def _rebuild_active(s: GameState) -> tuple:
    """Index of the cards whose text is active, cached on the state (``s._active``) and
    invalidated by any zone or face-up change. Slots:

      0, 1  per-player active instances (Units and Gear in play, face-up Legends), zone order
      2     ((inst, power_mod), ...)          3  ((inst, cost_mod), ...)
      4     ((inst, on_event, events), ...)   5  {host: (gear, ...)}
      6     slot 4 in both delivery orders, indexed by the active player (that player's cards first)
      7     per-player ((inst, would_steal), ...)    8  per-player ((inst, would_defeat), ...)
      9     per-player ((inst, script), ...) for scripts with abilities
      10    per-player suppress_new_units flag

    Per-player slots list player p's cards in slot-p order. Slots 2-4 and 6 list player 0's cards
    then player 1's, which is also ownership order: an instance only ever sits in its owner's
    zones.
    """
    per = ([], [])
    pm, cm = [], []
    evs, ws, wd, ab = ([], []), ([], []), ([], []), ([], [])
    sup = [False, False]
    gear_of: dict[int, tuple] = {}
    hooks = s.reg.hooks
    i_host = s.i_host
    i_faceup = s.i_faceup
    i_card = s.i_card
    z = s.z
    for p in (0, 1):
        base = p * NZONE
        lst = per[p]
        field = z[base + _FIELD]
        legs = z[base + _LEGENDS]
        lst += field
        for i in legs:
            if i_faceup[i] or (i_host[i] != NO_INST and i_faceup[i_host[i]]):
                lst.append(i)
        for g in field:                          # gear_of insertion order: FIELD then LEGENDS, zone order
            h = i_host[g]
            if h != NO_INST:
                gear_of[h] = gear_of.get(h, ()) + (g,)
        for g in legs:
            h = i_host[g]
            if h != NO_INST:
                gear_of[h] = gear_of.get(h, ()) + (g,)
        ev_p, ws_p, wd_p, ab_p = evs[p], ws[p], wd[p], ab[p]
        for i in lst:
            hk = hooks[i_card[i]]
            if hk is None:
                continue
            if hk[0] is not None:
                pm.append((i, hk[0]))
            if hk[1] is not None:
                cm.append((i, hk[1]))
            if hk[2] is not None:
                ev_p.append((i, hk[2], hk[3]))       # (inst, on_event, event kinds or None)
            if hk[4] is not None:
                ws_p.append((i, hk[4]))
            if hk[5] is not None:
                wd_p.append((i, hk[5]))
            if hk[6] is not None:
                ab_p.append((i, hk[6]))
            if hk[7]:
                sup[p] = True
    ev0, ev1 = tuple(evs[0]), tuple(evs[1])
    ev = ev0 + ev1
    cache = (tuple(per[0]), tuple(per[1]), tuple(pm), tuple(cm), ev, gear_of, (ev, ev1 + ev0),
             (tuple(ws[0]), tuple(ws[1])), (tuple(wd[0]), tuple(wd[1])), (tuple(ab[0]), tuple(ab[1])),
             (sup[0], sup[1]))
    s._active = cache
    return cache


def gear_of(s: GameState, inst: int) -> tuple:
    """Gear equipped to ``inst`` while it is in play (cached with the active-card index)."""
    return _active(s)[5].get(inst, ())


def _active(s: GameState) -> tuple:
    return s._active if s._active is not None else _rebuild_active(s)


def active_cards(s: GameState, first: int | None = None) -> list[int]:
    """Instances whose text is active: Units and Gear in play, and *face-up* Legends.
    Ordered active player first (or ``first``), then the rival."""
    p0 = s.active if first is None else first
    a = _active(s)
    return list(a[p0]) + list(a[1 - p0])


def _ctx(s: GameState, inst: int):
    c = s._ctxs.get(inst)
    if c is None:
        from cptcg.core.effects import EffectCtx
        c = s._ctxs[inst] = EffectCtx(s, inst)
    return c


def dispatch(s: GameState, ev: tuple) -> None:
    """Deliver an event to every active card with an ``on_event`` hook.

    Hooks are called immediately (they never block). Because a hook that needs a decision pushes
    a step, and the stack is LIFO, hooks are called in reverse so the first card's question
    surfaces first.
    """
    act = s._active
    if act is None:
        act = _rebuild_active(s)
    hooks = act[6][s.active]                         # active player's cards first
    if hooks:
        kind = ev[0]
        for inst, h, kinds in reversed(hooks):
            # The game-over test stays ahead of the kind filter: a skipped hook is one that
            # would have returned without doing anything, so the early return happens at
            # exactly the same hook as it would without the filter.
            if s.over:
                return
            if kinds is None or kind in kinds:
                h(_ctx(s, inst), ev)
    # Temporary listeners registered by effects ("the next time ... this turn"): (s, ev) callables.
    # Most dispatches find no mods at all; when there are some, walk a copy (listeners may append).
    if s.mods:
        for kind, _subject, fn, _exp in list(s.mods):
            if kind == "listener" and not s.over:
                fn(s, ev)
    if s.log is not None:                            # s.emit("event", ev), inlined
        s.log.append(("event", ev))


def ask(s: GameState, choice) -> None:
    from cptcg.core.steps import AskStep
    s.stack.append(AskStep(choice))


# ------------------------------------------------------------------- zones
def move(s: GameState, inst: int, zone: Zone, *, bottom: bool = False, host: int = NO_INST) -> None:
    """Move an instance (and any Gear equipped to it) to ``zone`` of its owner."""
    owner = s.i_owner[inst]
    old = s.i_zone[inst]
    gear_zone = zone
    if (s.cfg.legends_removed_when_leaving and zone not in (Zone.FIELD, Zone.LEGENDS, Zone.REMOVED)
            and s.card(inst).type is CardType.LEGEND):
        zone = Zone.REMOVED                          # CR 4.4.1; its Gear still goes where it was sent (4.12.2)
    s.z[owner * NZONE + old].remove(inst)
    dst = s.z[owner * NZONE + zone]
    if bottom:
        dst.insert(0, inst)
    else:
        dst.append(inst)
    s.i_zone[inst] = zone
    s.i_host[inst] = host
    s._active = None
    if zone is not Zone.FIELD and zone is not Zone.LEGENDS:
        s.i_spent[inst] = 0
        s.i_lag[inst] = 0
        s.i_faceup[inst] = 0
        s.i_flags[inst] = 0
        if s.temp_power:
            s.temp_power = [t for t in s.temp_power if t[0] != inst]   # CR 5.3.2.2
    for g in [i for i in s.z[owner * NZONE + old] if s.i_host[i] == inst]:
        move(s, g, gear_zone, bottom=bottom, host=inst if gear_zone in (Zone.FIELD, Zone.LEGENDS) else NO_INST)
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
        s.drawn.append(inst)
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


def top_cards(s: GameState, player: int, n: int) -> list[int]:
    deck = s.z[player * NZONE + Zone.DECK]
    return deck[-n:][::-1] if n > 0 else []


def bottom_deck(s: GameState, inst: int) -> None:
    move(s, inst, Zone.DECK, bottom=True)


def discard(s: GameState, inst: int) -> None:
    move(s, inst, Zone.TRASH)
    s.emit("discard", inst)


# ----------------------------------------------------------------- economy
def payable_sources(s: GameState, player: int, exclude: int = NO_INST) -> list[int]:
    """Ready sources of €$ in payment-priority order: Eddies, face-down Legends, face-up Legends."""
    spent = s.i_spent
    base = player * NZONE
    eddies = [i for i in s.z[base + Zone.EDDIES] if not spent[i]]
    legs = [i for i in s.legends(player) if not spent[i] and i != exclude]
    facedown = [i for i in legs if not s.i_faceup[i]]
    faceup = [i for i in legs if s.i_faceup[i] and s.card(i).sell_tag]   # CR 5.7.2.2
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
        spend(s, inst)
    s.emit("pay", player, amount)


def spend(s: GameState, inst: int) -> None:
    if s.i_spent[inst]:
        return
    s.i_spent[inst] = 1
    if s.i_zone[inst] in (Zone.FIELD, Zone.LEGENDS) and s.card(inst).type is not CardType.GEAR:
        dispatch(s, ("spent", inst))


def ready(s: GameState, inst: int) -> None:
    s.i_spent[inst] = 0


def ready_eddies(s: GameState, player: int, n: int) -> int:
    k = 0
    for i in s.z[player * NZONE + Zone.EDDIES]:
        if k >= n:
            break
        if s.i_spent[i]:
            s.i_spent[i] = 0
            k += 1
    return k


def play_cost(s: GameState, player: int, inst: int, go_solo: bool = False) -> int:
    """Cost to play ``inst`` from hand (or GO SOLO a Legend), after every modifier in play."""
    d = s.card(inst)
    base = d.cost or 0
    sc = d.script
    if sc is not None and sc.self_cost is not None and not go_solo:
        base = sc.self_cost(_ctx(s, inst), player, base)
    delta = 0
    for i, hook in _active(s)[3]:
        delta += hook(_ctx(s, i), player, inst, go_solo)
    if go_solo:
        for v in s.mod_values("cost_go_solo", player):
            delta += v
    elif d.type is CardType.PROGRAM:
        for v in s.mod_values("cost_next_program", player):
            delta += v
    total = base + delta
    if delta < 0 and base >= 1:
        total = max(1, total)          # every printed reduction says "to a minimum of 1 €$"
    return max(0, total)


def consume_cost_mods(s: GameState, player: int, inst: int, go_solo: bool) -> None:
    kind = "cost_go_solo" if go_solo else ("cost_next_program" if s.card(inst).type is CardType.PROGRAM else None)
    if kind:
        s.mods = [m for m in s.mods if not (m[0] == kind and m[1] == player)]


# ------------------------------------------------------------------- power
def has_keyword(s: GameState, inst: int, kw: Keyword) -> bool:
    """Printed on the card, printed on equipped Gear, or granted this turn."""
    if kw in s.card(inst).keywords:
        return True
    defs = s.reg.defs
    zone = s.i_zone[inst]
    if zone is Zone.FIELD or zone is Zone.LEGENDS:
        gear = _active(s)[5].get(inst, ())
    else:
        owner = s.i_owner[inst]
        gear = [g for g in s.z[owner * NZONE + zone] if s.i_host[g] == inst]
    for g in gear:
        if kw in defs[s.i_card[g]].keywords:
            return True
    return bool(s.mods) and s.has_mod("kw", inst) and kw in s.mod_values("kw", inst)


def power(s: GameState, inst: int, sit: int = 0) -> int:
    """Effective power in a situation: printed + Gear + temporary mods + static auras. Never cached."""
    defs = s.reg.defs
    p = defs[s.i_card[inst]].power or 0
    act = _active(s)
    zone = s.i_zone[inst]
    if zone is Zone.FIELD or zone is Zone.LEGENDS:
        gear = act[5].get(inst, ())
    else:
        owner = s.i_owner[inst]
        gear = [g for g in s.z[owner * NZONE + zone] if s.i_host[g] == inst]
    for g in gear:
        p += defs[s.i_card[g]].power or 0
    if s.temp_power:
        for target, delta, cond in s.temp_power:
            if target == inst and (cond == 0 or sit & cond == cond):
                p += delta
    if act[2]:
        ctxs = s._ctxs
        for i, hook in act[2]:
            c = ctxs.get(i)
            if c is None:
                c = _ctx(s, i)
            p += hook(c, inst, sit)
    return p if p > 0 else 0                           # ruling 029: power never drops below 0


def add_temp_power(s: GameState, inst: int, delta: int, cond: int = 0) -> None:
    s.temp_power.append((inst, delta, cond))


def steal_count(pwr: int) -> int:
    """Gigs stolen by a Gig-area attack: 0 at power 0, one more per 10 power above that."""
    return 0 if pwr <= 0 else 1 + pwr // 10


# ------------------------------------------------------------------ combat
def defeat(s: GameState, inst: int, *, allow_replace: bool = True) -> bool:
    """Send a card in play to the trash (or out of the game for a GO SOLO Legend).
    Returns False if a replacement effect took over."""
    if s.i_zone[inst] not in (Zone.FIELD, Zone.LEGENDS):
        return False
    owner = s.i_owner[inst]
    if allow_replace:
        act = s._active
        if act is None:
            act = _rebuild_active(s)
        wd = act[8]
        # The owner's replacement effects first; the tuples are a snapshot, so a hook that moves
        # cards can't disturb the walk (same as the old active_cards() list).
        for i, h in wd[owner] + wd[1 - owner]:
            if h(_ctx(s, i), inst):
                return False
    d = s.reg.defs[s.i_card[inst]]
    dest = Zone.REMOVED if s.i_flags[inst] & F_GO_SOLO else Zone.TRASH
    s.emit("defeated", inst)
    gear = s.gear_on(inst)
    move(s, inst, dest)
    if d.type is CardType.UNIT or d.type is CardType.LEGEND:
        for g in gear:                                  # Gear DEFEATED triggers refer to the host
            s.add_mod("was_host", g, inst)
            push_trigger(s, Trigger.DEFEATED, g)
        push_trigger(s, Trigger.DEFEATED, inst)
        dispatch(s, ("defeated", inst, owner, bool(gear)))
    return True


# -------------------------------------------------------------------- dice
def gain_gig(s: GameState, player: int, sides: int) -> int:
    """Take ``sides`` from the fixer area, roll it, put it in the Gig area. Returns the value."""
    s.fixer[player].remove(sides)
    value = s.rng.die(sides)
    s.gig[player].append((sides, value))
    s.emit("gig", player, sides, value)
    dispatch(s, ("gig_rolled", player, sides, value))
    return value


def steal_gig(s: GameState, thief: int, index: int) -> tuple[int, int]:
    victim = 1 - thief
    die = s.gig[victim].pop(index)
    if s.cfg.reroll_stolen_dice:
        die = (die[0], s.rng.die(die[0]))
    s.gig[thief].append(die)
    s.emit("steal", thief, die)
    return die


def adjust_gig(s: GameState, actor: int, owner: int, index: int, delta: int) -> None:
    if index >= len(s.gig[owner]):
        return                                          # the die moved before the choice resolved
    sides, value = s.gig[owner][index]
    if s.cfg.set_gig_off_face_fails and not 1 <= value + delta <= sides:
        return                                          # CR 6.4.4: not a face of the die — the effect fails
    nv = max(1, min(sides, value + delta))
    if nv == value:
        return
    s.gig[owner][index] = (sides, nv)
    s.emit("adjust", owner, index, value, nv)
    dispatch(s, ("gig_changed", actor, owner, index))


def set_gig(s: GameState, actor: int, owner: int, index: int, value: int) -> None:
    if index >= len(s.gig[owner]):
        return
    sides, old = s.gig[owner][index]
    if s.cfg.set_gig_off_face_fails and not 1 <= value <= sides:
        return                                          # CR 6.4.4
    nv = max(1, min(sides, value))
    if nv == old:
        return                                          # CR 6.4.5: already that value — the effect fails
    s.gig[owner][index] = (sides, nv)
    s.emit("adjust", owner, index, old, nv)
    dispatch(s, ("gig_changed", actor, owner, index))


def swap_gigs(s: GameState, actor: int, mine: int, theirs: int) -> None:
    if mine >= len(s.gig[actor]) or theirs >= len(s.gig[1 - actor]):
        return
    a, b = s.gig[actor][mine], s.gig[1 - actor][theirs]
    s.gig[actor][mine], s.gig[1 - actor][theirs] = b, a
    s.emit("swap", actor, mine, theirs)
    dispatch(s, ("gig_changed", actor, 1 - actor, theirs))


def reroll_gig(s: GameState, player: int, index: int) -> int:
    if index >= len(s.gig[player]):
        return 0
    sides, _ = s.gig[player][index]
    v = s.rng.die(sides)
    s.gig[player][index] = (sides, v)
    s.emit("reroll", player, index, v)
    return v


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
    s._active = None
    s.i_known[inst] = 0b11
    s.once[player] |= ONCE_CALLED
    s.emit("call", player, inst)
    push_trigger(s, Trigger.CALL, inst)
    dispatch(s, ("called", inst, player))


def can_call_free(s: GameState, player: int) -> bool:
    return not s.once[player] & ONCE_CALLED and any(not s.i_faceup[i] for i in s.legends(player))


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
