"""Game setup, the action loop, and the main-phase/reaction action handlers."""

from __future__ import annotations

from cptcg.cards.registry import Registry
from cptcg.core.actions import (Action, Activate, Attack, Block, CallLegend, Choice, ChoiceKind,
                                ChooseOrder, EndTurn, GoSolo, Pass, Play, Sell)
from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.core.enums import (DICE, F_GO_SOLO, F_NO_READY_NEXT, NO_INST, TARGET_UNIT, CardType,
                              EndReason, Keyword, Trigger, Zone)
from cptcg.core.ops import (_ctx, call_legend, consume_cost_mods, dispatch, draw, end_game,
                            gain_gig, move, pay, play_cost, push_trigger, shuffle_deck, spend)
from cptcg.core.state import ONCE_SOLD, AttackContext, GameState
from cptcg.core.steps import (DeclareTargetStep, EndAttackStep, HookStep, MainPhaseStep,
                              MulliganStep, ReactionWindowStep, ResolveAttackStep, StartGameStep,
                              set_target)
from cptcg.deck.decklist import Decklist


# ------------------------------------------------------------------- setup
def new_game(reg: Registry, decks: tuple[Decklist, Decklist], seed: int,
             cfg: RulesConfig = DEFAULT_CONFIG, record: bool = False) -> GameState:
    """Build a game and run it to the first decision (the d20 winner's order choice, or the
    first mulligan)."""
    s = GameState(cfg, reg, seed)
    if record:
        s.log = []
        s.actions = []
    for p, deck in enumerate(decks):
        for card_id in deck.main:
            s.new_instance(reg.get(card_id).idx, p, Zone.DECK)
        shuffle_deck(s, p)
        legs = [reg.get(c).idx for c in deck.legends]
        s.rng.shuffle(legs)                          # random order, face-down: nobody knows which is where
        for idx in legs:
            s.new_instance(idx, p, Zone.LEGENDS)
        s.fixer[p] = list(DICE)
    while True:
        r0, r1 = s.rng.die(20), s.rng.die(20)
        if r0 != r1:
            break
    winner = 0 if r0 > r1 else 1
    s.emit("roll_off", r0, r1, winner)
    if cfg.first_player_choice:
        s.pending = Choice(ChoiceKind.ORDER, winner, (ChooseOrder(True), ChooseOrder(False)),
                           prompt="Go first or second?")
    else:
        _set_order(s, winner)
        advance(s)
    return s


def _set_order(s: GameState, first: int) -> None:
    s.first_player = first
    s.emit("first", first)
    for i in s.legends(first)[:2]:                   # first-player handicap
        s.i_spent[i] = 1
        s.i_flags[i] |= F_NO_READY_NEXT
    for p in (0, 1):
        draw(s, p, s.cfg.opening_hand)
    second = 1 - first
    s.stack.append(StartGameStep())
    s.stack.append(MulliganStep(second))
    s.stack.append(MulliganStep(first))


# -------------------------------------------------------------------- loop
def legal_actions(s: GameState) -> tuple[Action, ...]:
    return s.pending.options if s.pending is not None else ()


def advance(s: GameState) -> None:
    """Run steps until the next decision or the end of the game."""
    while not s.over:
        if s.overtime and _overtime_check(s):
            return
        if s.pending is not None:
            return
        if not s.stack:
            raise RuntimeError("engine stalled: nothing pending and empty stack")
        s.stack.pop().run(s)


def _overtime_check(s: GameState) -> bool:
    total = len(s.gig[0]) + len(s.gig[1])
    for p in (0, 1):
        if 2 * len(s.gig[p]) > total:
            end_game(s, p, EndReason.OVERTIME)
            return True
    return False


def apply(s: GameState, index: int) -> None:
    """Apply the ``index``-th legal action of the pending choice, then advance."""
    ch = s.pending
    if ch is None:
        raise RuntimeError("no pending choice")
    action = ch.options[index]
    s.pending = None
    if s.actions is not None:
        s.actions.append(index)
    s.emit("action", ch.kind, ch.player, action)
    kind = ch.kind
    if kind is ChoiceKind.MAIN:
        if not isinstance(action, EndTurn):
            s.stack.append(MainPhaseStep())            # come back to the menu afterwards
            _main_action(s, ch.player, action)
    elif kind is ChoiceKind.REACTION:
        if not isinstance(action, Pass):
            s.stack.append(ReactionWindowStep())       # the window stays open
            _reaction(s, ch.player, action)
    elif kind is ChoiceKind.PICK:
        ch.cont(s, action)
    elif kind is ChoiceKind.TARGET:
        set_target(s, action)
    elif kind is ChoiceKind.GIG_DIE:
        gain_gig(s, ch.player, action.sides)
    elif kind is ChoiceKind.MULLIGAN:
        if not action.keep:
            p = ch.player
            for i in list(s.zone(p, Zone.HAND)):
                move(s, i, Zone.DECK)
            shuffle_deck(s, p)
            draw(s, p, s.cfg.opening_hand)
            s.emit("mulligan", p)
    elif kind is ChoiceKind.ORDER:
        _set_order(s, ch.player if action.go_first else 1 - ch.player)
    advance(s)


# ---------------------------------------------------------- main actions
def _main_action(s: GameState, p: int, a: Action) -> None:
    if isinstance(a, Play):
        play_card(s, p, a.inst, a.host, cost=play_cost(s, p, a.inst))
    elif isinstance(a, Attack):
        _attack(s, p, a.inst)
    elif isinstance(a, Sell):
        move(s, a.inst, Zone.EDDIES)
        s.once[p] |= ONCE_SOLD
        s.emit("sell", p, a.inst)
    elif isinstance(a, CallLegend):
        pay(s, p, 1, exclude=a.inst)
        call_legend(s, p, a.inst)
    elif isinstance(a, GoSolo):
        go_solo(s, p, a.inst, cost=play_cost(s, p, a.inst, go_solo=True))
    elif isinstance(a, Activate):
        activate(s, p, a.inst, a.ability)
    else:
        raise RuntimeError(f"unhandled main action {a!r}")


def play_card(s: GameState, p: int, inst: int, host: int = NO_INST, cost: int = 0) -> None:
    """Play ``inst`` from wherever it is (hand, or trash via an effect), paying ``cost``."""
    d = s.card(inst)
    if cost:
        pay(s, p, cost)
    consume_cost_mods(s, p, inst, False)
    s.emit("play", p, inst)
    s.played.append(inst)
    if d.type is CardType.UNIT:
        move(s, inst, Zone.FIELD)
        s.i_lag[inst] = 0 if Keyword.ADRENALINE in d.keywords else 1
        push_trigger(s, Trigger.PLAY, inst)
    elif d.type is CardType.PROGRAM:
        # Pay, resolve, trash. We trash first and then resolve: with no priority stack the
        # only observable difference is what "your trash" contains mid-resolution.
        move(s, inst, Zone.TRASH)
        push_trigger(s, Trigger.PLAY, inst)
    elif d.type is CardType.GEAR:
        if host == NO_INST:
            raise RuntimeError("Gear needs a host")
        move(s, inst, Zone(s.i_zone[host]), host=host)
        push_trigger(s, Trigger.PLAY, inst)
    else:
        raise RuntimeError(f"cannot play a {d.type.name}")
    dispatch(s, ("played", inst, p))


def go_solo(s: GameState, p: int, inst: int, cost: int) -> None:
    pay(s, p, cost, exclude=inst)
    consume_cost_mods(s, p, inst, True)
    move(s, inst, Zone.FIELD)
    s.i_spent[inst] = 0
    s.i_lag[inst] = 0
    s.i_faceup[inst] = 1
    s.i_flags[inst] |= F_GO_SOLO
    s.emit("go_solo", p, inst)
    dispatch(s, ("played", inst, p))


def activate(s: GameState, p: int, inst: int, k: int) -> None:
    ab = s.card(inst).script.abilities[k]
    excl = inst if (ab.self_spend and s.card(inst).type is CardType.LEGEND) else NO_INST
    pay(s, p, ab.cost, exclude=excl)
    if ab.self_spend:
        spend(s, inst)
    s.emit("activate", p, inst, k)
    s.stack.append(HookStep(ab.effect, inst))


def _attack(s: GameState, p: int, unit: int) -> None:
    spend(s, unit)
    s.atk = AttackContext(unit, p)
    s.emit("attack", p, unit)
    # Stack is LIFO: pushed last runs first. Rulebook order is triggers -> target -> react -> resolve.
    s.stack.append(EndAttackStep())
    s.stack.append(ResolveAttackStep())
    s.stack.append(ReactionWindowStep())
    s.stack.append(DeclareTargetStep())
    push_trigger(s, Trigger.ATTACK, unit)
    dispatch(s, ("attack", unit, p))


def _reaction(s: GameState, d: int, a: Action) -> None:
    atk = s.atk
    if isinstance(a, Block):
        spend(s, a.inst)
        atk.target_kind = TARGET_UNIT
        atk.target = a.inst
        atk.gig_steal_allowed = False
        atk.redirects += 1
        s.emit("block", d, a.inst)
        dispatch(s, ("blocked", a.inst, atk.attacker))
    elif isinstance(a, CallLegend):
        pay(s, d, 1, exclude=a.inst)
        call_legend(s, d, a.inst)
    elif isinstance(a, Play):
        play_card(s, d, a.inst, cost=play_cost(s, d, a.inst))
    elif isinstance(a, Activate):
        activate(s, d, a.inst, a.ability)
    else:
        raise RuntimeError(f"unhandled reaction {a!r}")
