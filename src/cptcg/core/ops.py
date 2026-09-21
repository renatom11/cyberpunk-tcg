"""State-mutation primitives.

Everything that changes a GameState goes through here — the engine, the effect atoms and the
tests all use the same handful of verbs, so an invariant (a card is in exactly one zone, Gear
travels with its host, dice are conserved) is enforced in one place.

Rule for anything that needs a player decision: push an AskStep (see ``ask``). Never set
``s.pending`` from inside a hook — two hooks in one dispatch would trample each other.
"""

from __future__ import annotations

from cptcg.core.enums import (F_CANT_READY, F_GO_SOLO, NO_INST, NZONE, CardType, EndReason, Keyword,
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
      11    ((inst, kw_mod), ...)             conditional keyword grants (see has_keyword)

    Per-player slots list player p's cards in slot-p order. Slots 2-4, 6 and 11 list player 0's
    cards then player 1's, which is also ownership order: an instance only ever sits in its
    owner's zones.
    """
    per = ([], [])
    pm, cm, kwm = [], [], []
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
                ev_p.append((i, hk[2], hk[3], hk[9]))    # (inst, on_event, event kinds or None, wants)
            if hk[4] is not None:
                ws_p.append((i, hk[4]))
            if hk[5] is not None:
                wd_p.append((i, hk[5]))
            if hk[6] is not None:
                ab_p.append((i, hk[6]))
            if hk[7]:
                sup[p] = True
            if hk[8] is not None:
                kwm.append((i, hk[8]))
    ev0, ev1 = tuple(evs[0]), tuple(evs[1])
    ev = ev0 + ev1
    cache = (tuple(per[0]), tuple(per[1]), tuple(pm), tuple(cm), ev, gear_of, (ev, ev1 + ev0),
             (tuple(ws[0]), tuple(ws[1])), (tuple(wd[0]), tuple(wd[1])), (tuple(ab[0]), tuple(ab[1])),
             (sup[0], sup[1]), tuple(kwm))
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


# Bound by effects.py when it is imported (effects imports ops, so ops cannot import it at module
# level without a cycle). _ctx falls back to a local import if a bare registry uses ops before
# effects was ever imported; that import binds this global too, so the fallback runs at most once.
_EffectCtx = None


def _ctx(s: GameState, inst: int):
    c = s._ctxs.get(inst)
    if c is None:
        cls = _EffectCtx
        if cls is None:
            from cptcg.core.effects import EffectCtx as cls   # also binds ops._EffectCtx
        c = s._ctxs[inst] = cls(s, inst)
    return c


def dispatch(s: GameState, ev: tuple) -> None:
    """Deliver an event to every active card with an ``on_event`` hook, and to the listeners.

    Hooks are called immediately (they never block). Because a hook that needs a decision pushes
    a step, and the stack is LIFO, hooks are called in reverse so the first card's question
    surfaces first. Two exceptions: when one player owns two or more distinct triggers on this
    event (ruling 046, ``needs_ordering``) the group moves to ``OrderTriggersStep`` and that
    player orders it; and inside a ``deferring`` block nothing runs at all -- the matched hooks
    and listeners are collected for the caller, which is how a cost's spend triggers are held
    until the play or the activated effect they paid for has resolved (Stage 0 E9).
    """
    s.turn_events.append(ev)                         # "the first time ... each turn" reads this
    if s.deferred is not None:
        s.deferred.append(_collect(s, ev))
        if s.log is not None:
            s.log.append(("event", ev))
        return
    act = s._active
    if act is None:
        act = _rebuild_active(s)
    hooks = act[6][s.active]                         # active player's cards first
    kind = ev[0]
    matched = _matched(s, hooks, ev) if hooks else []
    listeners = _listeners(s, kind) if s.mods else []
    if needs_ordering(s, matched + listeners):
        from cptcg.core.steps import OrderTriggersStep
        s.stack.append(OrderTriggersStep(kind, tuple(_bound(ev, matched, listeners))))
    else:
        for inst, h in reversed(matched):
            # The game-over test stays ahead of the hook call: a skipped hook is one that
            # would have returned without doing anything, so the early return happens at
            # exactly the same hook as it would without the kind filter.
            if s.over:
                return
            h(_ctx(s, inst), ev)
        # Temporary listeners registered by effects ("the next time ... this turn"): (s, ev)
        # callables. Most dispatches find no mods at all; a listener may append to s.mods, so
        # the list above is a snapshot.
        for _sub, fn in listeners:
            if s.over:
                return
            fn(s, ev)
    if s.log is not None:                            # s.emit("event", ev), inlined
        s.log.append(("event", ev))


def _collect(s: GameState, ev: tuple) -> tuple:
    """What ``dispatch`` would have run for ``ev``: ``(ev, matched hooks, listeners)``, unrun."""
    act = s._active
    if act is None:
        act = _rebuild_active(s)
    hooks = act[6][s.active]
    matched = _matched(s, hooks, ev) if hooks else []
    listeners = _listeners(s, ev[0]) if s.mods else []
    return (ev, matched, listeners)


def _matched(s: GameState, hooks: tuple, ev: tuple) -> list:
    """The hooks that will act on ``ev``: the kind filter, then the script's ``wants`` where it
    declares one. Only hooks that would act are pending triggers (ruling 046 ordering)."""
    kind = ev[0]
    out = []
    for i, h, kinds, wants in hooks:
        if kinds is not None and kind not in kinds:
            continue
        if wants is not None and not wants(_ctx(s, i), ev):
            continue
        out.append((i, h))
    return out


def _listeners(s: GameState, kind: str) -> list:
    """The temporary listeners that want this event kind: ``(subject, fn)`` pairs.

    A listener is a ``("listener", inst, fn, expiry)`` mod; ``fn(s, ev)`` may carry a ``kinds``
    attribute naming the event kinds it acts on (``listen.kinds = frozenset({...})``), and one
    without it hears everything. The filter matters beyond speed: ruling 046's ordering counts a
    listener as a trigger on the event, so one that would ignore the event must not be offered
    for ordering against a hook.
    """
    out = []
    for k, sub, fn, _e in s.mods:
        if k == "listener":
            kinds = getattr(fn, "kinds", None)
            if kinds is None or kind in kinds:
                out.append((sub, fn))
    return out


def _bound(ev: tuple, matched: list, listeners: list) -> list:
    """Trigger entries ``(inst, fn(ctx))`` for a collected event, in resolution order: the
    matched hooks as dispatch ordered them, then the listeners (whose ``inst`` is the card that
    registered them, so ownership and card identity read the same way as a hook's)."""
    out = [(i, (lambda c, h=h, ev=ev: h(c, ev))) for i, h in matched]
    out += [(sub, (lambda c, fn=fn, ev=ev: fn(c.s, ev))) for sub, fn in listeners]
    return out


class _Deferring:
    __slots__ = ("s", "prev", "pend")

    def __init__(self, s: GameState) -> None:
        self.s = s

    def __enter__(self) -> list:
        self.prev = self.s.deferred
        self.pend = []
        self.s.deferred = self.pend
        return self.pend

    def __exit__(self, *_exc) -> None:
        self.s.deferred = self.prev


def deferring(s: GameState) -> _Deferring:
    """``with deferring(s) as pend:`` -- every ``dispatch`` inside collects into ``pend`` instead
    of running. The caller then either runs them the way dispatch would have (``run_deferred``) or
    folds them into an ordering group (``deferred_entries`` + ``OrderTriggersStep``)."""
    return _Deferring(s)


def run_deferred(s: GameState, pend: list) -> None:
    """Run collected events exactly as an undeferred ``dispatch`` would have."""
    for ev, matched, listeners in pend:
        for inst, h in reversed(matched):
            if s.over:
                return
            h(_ctx(s, inst), ev)
        for _sub, fn in listeners:
            if s.over:
                return
            fn(s, ev)


def deferred_entries(pend: list) -> list:
    out = []
    for ev, matched, listeners in pend:
        out += _bound(ev, matched, listeners)
    return out


def resolve_triggers(s: GameState, tag: str, entries: list) -> None:
    """Queue trigger entries to resolve after the current effect, in listed order, asking the
    controller which goes first when one player owns two distinct cards among them."""
    if entries:
        from cptcg.core.steps import OrderTriggersStep
        s.stack.append(OrderTriggersStep(tag, tuple(entries)))


def needs_ordering(s: GameState, matched: list) -> bool:
    """Ruling 046: does one player own two or more of the triggers this event just matched?

    The FAQ grants the controller the choice of order in exactly that case — *"When I have
    mulitple ATTACK effects that activate and go into pending at the same time. Can I choose any
    order to resolve them? **Yes**"*, and again for a trigger meeting a differently-worded one.
    Across players there is no choice to make: the turn player's resolve first, which is the order
    the hook list is already in.

    **Distinct cards only**, and that restriction is measured rather than assumed. Over 287,247
    dispatched events in 240 golden-deck games, 4.8% matched two of one player's hooks — but a
    third of those were two or three copies of the SAME card (Rita Wheeler beside Rita Wheeler,
    Meredith Stout beside Meredith Stout). Ordering two identical effects is a choice whose
    branches cannot be told apart: it would put a meaningless prompt in front of the player
    thousands of times and hand the search a branching factor for nothing. Requiring two distinct
    cards takes it to 3.2%, and every one of those is a real decision.
    """
    if len(matched) < 2:
        return False
    seen = ({}, {})
    for inst, *_rest in matched:
        by = seen[s.i_owner[inst]]
        by[s.i_card[inst]] = True
        if len(by) >= 2:
            return True
    return False


def ask(s: GameState, choice) -> None:
    from cptcg.core.steps import AskStep
    s.stack.append(AskStep(choice))


# ------------------------------------------------------------------- zones
_PLAY = (Zone.FIELD, Zone.LEGENDS)


def move(s: GameState, inst: int, zone: Zone, *, bottom: bool = False, host: int = NO_INST) -> None:
    """Move an instance (and any Gear equipped to it) to ``zone`` of its owner.

    The active-card cache (see _rebuild_active) depends only on the FIELD and LEGENDS lists and on
    i_host/i_faceup of the cards in them, so a move between two other zones (a draw, a discard, a
    sell, a mulligan) leaves it valid. Anything that sets i_host/i_faceup or edits a play-zone list
    without going through move() must set ``s._active = None`` itself (call_legend and go_solo do).
    """
    owner = s.i_owner[inst]
    old = s.i_zone[inst]
    gear_zone = zone
    new_play = zone in _PLAY                         # unchanged by the Legend redirect below (REMOVED is not in play)
    if (not new_play and zone != Zone.REMOVED and s.cfg.legends_removed_when_leaving
            and s.reg.defs[s.i_card[inst]].type is CardType.LEGEND):
        zone = Zone.REMOVED                          # CR 4.4.1; its Gear still goes where it was sent (4.12.2)
    z = s.z
    base = owner * NZONE
    src = z[base + old]
    if src[-1] == inst:                              # top card (every draw); ids are unique per list, so pop() is exact
        src.pop()
    else:
        src.remove(inst)
    dst = z[base + zone]
    if bottom:
        dst.insert(0, inst)
    else:
        dst.append(inst)
    s.i_zone[inst] = zone
    s.i_host[inst] = host
    old_play = old in _PLAY
    if old_play or new_play:
        s._active = None
    if not new_play:
        s.i_spent[inst] = 0
        s.i_lag[inst] = 0
        s.i_faceup[inst] = 0
        s.i_flags[inst] = 0
        if s.temp_power:
            s.temp_power = [t for t in s.temp_power if t[0] != inst]   # CR 5.3.2.2
    if old_play:                                     # Gear is only ever attached while in play (invariants.check)
        i_host = s.i_host
        for g in [i for i in src if i_host[i] == inst]:
            move(s, g, gear_zone, bottom=bottom, host=inst if gear_zone in _PLAY else NO_INST)
    if s.log is not None:                            # s.emit("move", inst, old, zone), inlined
        s.log.append(("move", inst, old, zone))


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
# Ruling 025 auto-pays, because making payment an engine decision multiplies the search branching
# factor for almost no strategic content. A person at a table does get to choose, though, so an
# interactive front end may set this around a single apply() to name the sources that player wants
# spent first. Nothing inside the engine ever writes it, so simulated games are unaffected. The
# id(state) in the token keeps one game's preference from reaching another game running in a sibling
# thread; the caller holds a reference to that state for the whole apply, so the id cannot be reused.
PAY_PREF: tuple[int, int, tuple[int, ...]] | None = None


def payable_sources(s: GameState, player: int, exclude: int = NO_INST) -> list[int]:
    """Ready sources of €$ in payment-priority order: Eddies, face-down Legends, face-up Legends."""
    spent = s.i_spent
    base = player * NZONE
    eddies = [i for i in s.z[base + Zone.EDDIES] if not spent[i]]
    legs = [i for i in s.legends(player) if not spent[i] and i != exclude]
    facedown = [i for i in legs if not s.i_faceup[i]]
    faceup = [i for i in legs if s.i_faceup[i] and s.card(i).sell_tag]   # CR 5.7.2.2
    srcs = eddies + facedown + faceup
    plan = s.pay_plan
    if plan is not None:
        # Chosen by the payment PICK (E12): the named Legends first, the rest in the usual order.
        first = [i for i in plan if i in srcs]
        return first + [i for i in srcs if i not in first]
    pref = PAY_PREF
    if pref is not None and pref[1] == player and pref[0] == id(s):
        # Only sources that are still legal right now; the rest keep their usual order behind them,
        # so an under-filled or stale choice still pays rather than raising.
        first = [i for i in pref[2] if i in srcs]
        if first:
            return first + [i for i in srcs if i not in first]
    return srcs


class PayPlan(tuple):
    """The Legend instances one payment plan spends. A tuple subclass so a PICK's value list
    can be told apart from the other tuple shapes the views describe."""
    __slots__ = ()


def payment_plans(s: GameState, player: int, amount: int, exclude: int = NO_INST) -> list[PayPlan]:
    """The distinct ways to pay ``amount`` (Stage 0 E12, ruling 025 revised).

    Ready Eddies are interchangeable and always spent first: no card reads an Eddie's identity,
    and keeping an Eddie back to spend a Legend instead is a plan the measurement found in 0.02%
    of payments (a Legend whose spend has a trigger). What is left to decide is *which* Legends
    cover the remainder when the Eddies do not, and every subset is a different plan: a face-down
    Legend kept ready can still be Called, a face-up one can still use its ability, one may host
    Gear. Plans are listed with the automatic order first (``payable_sources``'s priority), so
    the first plan is what the engine used to pay before it asked. One plan means no question.
    """
    if amount <= 0:
        return [PayPlan()]
    srcs = payable_sources(s, player, exclude)
    if len(srcs) < amount:
        return []
    base = player * NZONE
    eddies = [i for i in srcs if s.i_zone[i] == Zone.EDDIES]
    legs = [i for i in srcs if s.i_zone[i] != Zone.EDDIES]
    need = amount - len(eddies)
    if need <= 0 or need >= len(legs):
        return [PayPlan(legs[:max(0, need)])]
    from itertools import combinations
    return [PayPlan(c) for c in combinations(legs, need)]


def available(s: GameState, player: int, exclude: int = NO_INST) -> int:
    return len(payable_sources(s, player, exclude))


def pay(s: GameState, player: int, amount: int, exclude: int = NO_INST) -> None:
    if amount <= 0:
        return
    srcs = payable_sources(s, player, exclude)
    if len(srcs) < amount:
        raise RuntimeError(f"player {player} cannot pay {amount} (has {len(srcs)})")
    taken = srcs[:amount]
    for inst in taken:
        spend(s, inst)
    if s.log is None:
        s.emit("pay", player, amount)
    else:
        # What was actually spent, so the log can say it. Only counted when the game is recording:
        # a rollout emits nothing and must not pay for the arithmetic.
        legends = sum(1 for i in taken if s.i_zone[i] == Zone.LEGENDS)
        s.emit("pay", player, amount, amount - legends, legends)


def spend(s: GameState, inst: int) -> None:
    if s.i_spent[inst]:
        return
    s.i_spent[inst] = 1
    if s.i_zone[inst] in (Zone.FIELD, Zone.LEGENDS) and s.card(inst).type is not CardType.GEAR:
        dispatch(s, ("spent", inst))


def ready(s: GameState, inst: int) -> None:
    """Ready a card, unless something has said it may not.

    "It can't ready until your next turn" is a prohibition on the card, and a prohibition has to be
    checked wherever the thing it forbids can happen. It used to be checked only in the Ready step,
    so Memory Relapse's rider held against the rival's own start of turn and not against any of the
    nine card effects that ready -- including the named Unit's own "the first time this Unit wins a
    fight each turn, ready it", on the very turn the rider was applied.
    """
    if s.i_flags[inst] & F_CANT_READY:
        return
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
    if s.mods and s.has_mod("kw", inst) and kw in s.mod_values("kw", inst):
        return True
    kwm = _active(s)[11]                   # conditional grants: one truthiness test when unused
    if kwm:
        for i, hook in kwm:
            if hook(_ctx(s, i), inst, kw):
                return True
    return False


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


def steal_reduction(s: GameState, unit: int) -> int:
    """How many fewer Gigs ``unit`` steals this turn (Take Control: "A rival Unit steals 1 fewer
    Gig this turn"). The FAQ applies it to every steal the Unit makes, by attack or by effect --
    *"Does this apply to Units stealing Gigs through effects outside of attacking? **Yes**"* --
    so both paths subtract it, and a steal reduced to nothing emits no ``steal`` event, which is
    why Gorilla Arms cannot fire off it (*"0 Gigs ... Gorilla Arms does not activate"*)."""
    return sum(s.mod_values("steal_fewer", unit)) if s.mods else 0


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
    solo = bool(s.i_flags[inst] & F_GO_SOLO)
    dest = Zone.REMOVED if solo else Zone.TRASH
    # Ruling 044: was this card a *Unit*? It has to be answered here, before the move, and carried
    # in the event. `move` clears i_flags for anything leaving play, and it is F_GO_SOLO that marks
    # a Legend which was standing on the field as a Unit — so by the time a listener runs there is
    # neither a zone nor a flag left to read, and a listener testing CardDef.type would answer No
    # for exactly the case the FAQ says is Yes. River Ward *Detective on the Hunt* is the card this
    # matters to; the field is appended, so every existing listener indexes as it did.
    was_unit = d.type is CardType.UNIT or solo
    s.emit("defeated", inst)
    gear = s.gear_on(inst)
    move(s, inst, dest)
    if d.type is CardType.UNIT or d.type is CardType.LEGEND:
        for g in gear:                                  # Gear DEFEATED triggers refer to the host
            s.add_mod("was_host", g, inst)
        with deferring(s) as pend:
            dispatch(s, ("defeated", inst, owner, bool(gear), was_unit))
        # The dead card's own "when ... is defeated" listener hears its death too. It has left
        # play by now, so dispatch no longer finds it; the FAQ says it counts -- Yorinobu Arasaka
        # *Steel Dragon* "counts itself for 'the first time an ARASAKA Unit is defeated each turn'".
        # It is handed the very event object dispatch logged, so `first_this_turn` can place it.
        own = []
        hk = s.reg.hooks[s.i_card[inst]]
        if hk is not None and hk[2] is not None and (hk[3] is None or "defeated" in hk[3]):
            ev = pend[0][0]
            if hk[9] is None or hk[9](_ctx(s, inst), ev):
                own.append((inst, (lambda c, h=hk[2], ev=ev: h(c, ev))))
        printed = [(inst, d.script.on_defeated)] if d.script is not None and d.script.on_defeated is not None else []
        for g in gear:
            gsc = s.card(g).script
            if gsc is not None and gsc.on_defeated is not None:
                printed.append((g, gsc.on_defeated))
        # Ruling 046 over every queue (Stage 0 E8): the event's hooks and listeners, the dead
        # card's own listener and the printed DEFEATED triggers of the host and its Gear land
        # together; one owner with two distinct cards among them chooses the order.
        entries = deferred_entries(pend) + own + printed
        if needs_ordering(s, entries):
            resolve_triggers(s, "defeated", entries)
        else:
            for g in gear:
                push_trigger(s, Trigger.DEFEATED, g)
            push_trigger(s, Trigger.DEFEATED, inst)
            run_deferred(s, pend)
            for i, fn in own:
                if not s.over:
                    fn(_ctx(s, i))
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
def call_legend(s: GameState, player: int, inst: int, pend_pay: list | None = None) -> None:
    """Flip a Legend face-up. ``pend_pay`` holds the spend triggers collected while its Call was
    paid for; they resolve after the Call (FAQ: "After. Play the card first"), ordered with the
    CALL trigger when the controller has a choice (Stage 0 E8/E9)."""
    s.i_faceup[inst] = 1
    s._active = None
    s.i_known[inst] = 0b11
    s.once[player] |= ONCE_CALLED
    s.played_log.append((inst, player))           # a Called Legend entered play by a player's act
    s.emit("call", player, inst)
    sc = s.card(inst).script
    printed = (inst, sc.on_call) if sc is not None and sc.on_call is not None else None
    with deferring(s) as pend:
        dispatch(s, ("called", inst, player))
    settle_entry(s, "call", pend, printed, pend_pay or [])


def settle_entry(s: GameState, tag: str, pend_after: list, printed, pend_pay: list) -> None:
    """Resolve what a card entering play set off: the event it dispatched (``pend_after``), its
    printed trigger, and the spend triggers of whatever paid for it (``pend_pay``).

    Default order, when nobody has a choice: the event's hooks run now (as dispatch would), the
    printed trigger next, and the spend triggers last -- "If I spend a Legend equipped with
    Netwatch Netdriver to pay a card's cost, do I resolve Netwatch Netdriver's effect before or
    after I play the card? **After.**" When one player owns two distinct cards among all of them
    ("I have a Unit with PLAY and a Unit with 'When a friendly Legend is spent. Draw 1'. Will I
    be able to choose the order to resolve them? **Yes**"), that player orders the whole group.
    """
    after = deferred_entries(pend_after)
    spent = deferred_entries(pend_pay)
    entries = after + ([printed] if printed else []) + spent
    if needs_ordering(s, entries):
        resolve_triggers(s, tag, entries)
        return
    resolve_triggers(s, "spent", spent)               # under the printed trigger: runs after it
    if printed:
        from cptcg.core.steps import HookStep
        s.stack.append(HookStep(printed[1], printed[0]))
    run_deferred(s, pend_after)


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
