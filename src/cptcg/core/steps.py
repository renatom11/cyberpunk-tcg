"""The step machine.

The engine never blocks inside a Python call: work is queued as ``Step`` objects on
``state.stack`` and a step that needs a player decision sets ``state.pending`` and returns —
and only as its final act. That keeps the whole game a pure state machine, clonable at every
decision point. Steps are immutable, so cloning a state shares them.
"""

from __future__ import annotations

from itertools import combinations

from cptcg.core.actions import Choice, ChoiceKind, Mulligan, Pick, TakeGigDie, Target
from cptcg.core.enums import (F_NO_READY_NEXT, NO_INST, NZONE, TARGET_GIG, TARGET_UNIT, CardType,
                              EndReason, Trigger, Zone)
from cptcg.core.legal import attack_targets, gig_die_options, main_menu, reaction_menu
from cptcg.core.ops import (ATTACKING, FIGHTING, VS_LEGEND, VS_UNIT, _ctx, _rebuild_active,
                            active_cards, ask, defeat, dispatch, draw, end_game, gain_gig, power,
                            push_trigger, spend, steal_count, steal_gig)
from cptcg.core.state import GameState


class Step:
    __slots__ = ()

    def run(self, s: GameState) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class AskStep(Step):
    """Present a choice. The only way effects ask questions."""
    __slots__ = ("choice",)

    def __init__(self, choice: Choice) -> None:
        self.choice = choice

    def run(self, s: GameState) -> None:
        if len(self.choice.options) == 1 and self.choice.cont is not None:
            self.choice.cont(s, self.choice.options[0])      # no real decision: resolve inline
            return
        s.pending = self.choice


# ----------------------------------------------------------------- setup
class MulliganStep(Step):
    __slots__ = ("player",)

    def __init__(self, player: int) -> None:
        self.player = player

    def run(self, s: GameState) -> None:
        s.pending = Choice(ChoiceKind.MULLIGAN, self.player,
                           (Mulligan(True), Mulligan(False)), prompt="Keep or mulligan?")


class StartGameStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        s.turn = 1
        s.active = s.first_player
        push_turn(s)


# ------------------------------------------------------------ turn phases
def push_turn(s: GameState) -> None:
    """Queue one full turn for ``s.active``: start-phase steps, the main phase, then end of turn."""
    # CR 8.6: win check, start-of-turn effects, ready, draw, roll in a Gig (LIFO: pushed last runs first).
    s.stack.append(EndTurnStep())
    s.stack.append(MainPhaseStep())
    s.stack.append(GainGigStep())
    s.stack.append(DrawStep())
    s.stack.append(ReadyStep())
    s.stack.append(StartTurnEventsStep())
    s.stack.append(WinCheckStep())


class WinCheckStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        s.emit("turn", s.turn, s.active)
        if not s.fixer[s.active]:
            s.empty_starts |= 1 << s.active           # CR 1.11.1: Overtime starts once both have
        if len(s.gig[s.active]) >= s.cfg.gigs_to_win:
            end_game(s, s.active, EndReason.SEVEN_GIGS)


class ReadyStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        p = s.active
        zones = (Zone.FIELD, Zone.LEGENDS) + ((Zone.EDDIES,) if s.cfg.eddies_ready else ())
        for zone in zones:
            for i in s.z[p * NZONE + zone]:
                if s.i_flags[i] & F_NO_READY_NEXT:
                    s.i_flags[i] &= ~F_NO_READY_NEXT
                else:
                    s.i_spent[i] = 0


class DrawStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        draw(s, s.active, 1)


class GainGigStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        opts = gig_die_options(s, s.active)
        if not opts:
            return                                   # ruling 004: empty fixer, skip
        if len(opts) == 1:
            gain_gig(s, s.active, opts[0])
            return
        s.pending = Choice(ChoiceKind.GIG_DIE, s.active,
                           tuple(TakeGigDie(d) for d in opts), prompt="Take a Gig")


class StartTurnEventsStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        dispatch(s, ("start_turn", s.active))


# Choice is a frozen dataclass and legal_actions() always replaces the lazy one with a materialised
# Choice, so the two main-menu placeholders can be shared by every turn and preview.
_MAIN_CHOICE = (Choice(ChoiceKind.MAIN, 0, (), prompt="Main phase", lazy=True),
                Choice(ChoiceKind.MAIN, 1, (), prompt="Main phase", lazy=True))


class MainPhaseStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        s.pending = _MAIN_CHOICE[s.active]


class EndTurnStep(Step):
    """End-of-turn triggers first (they may ask questions), then the cleanup step below them."""
    __slots__ = ()

    def run(self, s: GameState) -> None:
        s.stack.append(EndTurnCleanupStep())
        for inst in [i for k, i, _v, _e in s.mods if k == "defeat_at_end"]:
            defeat(s, inst)
        dispatch(s, ("end_turn", s.active))


class EndTurnCleanupStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        p = s.active
        for i in range(len(s.i_lag)):
            s.i_lag[i] = 0
        s.temp_power.clear()
        s.mods = [m for m in s.mods if m[3] > s.turn]
        s.used.clear()
        s.played.clear()
        s.once[0] = s.once[1] = 0
        s.turns_taken[p] += 1
        if not s.overtime:                            # CR 8.17: checked as the turn ends
            if s.cfg.overtime_start == "empty_fixers":
                begin = s.empty_starts == 0b11
            else:
                begin = min(s.turns_taken) >= 7
            if begin:
                s.overtime = True
                s.emit("overtime")
        s.turn += 1
        if s.turn > s.cfg.max_turns:
            raise RuntimeError(f"game exceeded {s.cfg.max_turns} turns — rules bug?")
        s.active = 1 - p
        push_turn(s)


# ------------------------------------------------------------------ attack
class DeclareTargetStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        atk = s.atk
        if s.i_zone[atk.attacker] is not Zone.FIELD:   # an ATTACK trigger removed it
            atk.fizzled = True
            return
        opts = attack_targets(s, atk.attacker)
        if not opts:
            atk.fizzled = True
            return
        if len(opts) == 1:
            set_target(s, opts[0])
            return
        s.pending = Choice(ChoiceKind.TARGET, atk.attacker_ctrl, tuple(opts),
                           prompt="Declare a target")


def attack_triggers(s: GameState, unit: int) -> None:
    """Spend the attacker; ATTACK and 'when spent' effects become pending together (CR 11.21.2)."""
    for g in s.gear_on(unit):
        push_trigger(s, Trigger.ATTACK, g)
    push_trigger(s, Trigger.ATTACK, unit)
    spend(s, unit)
    dispatch(s, ("attack", unit, s.atk.attacker_ctrl))


class AttackDeclaredStep(Step):
    """CR 9.3.3-9.5: after the target is declared, spend the attacker and resolve its triggers."""
    __slots__ = ()

    def run(self, s: GameState) -> None:
        if s.atk.fizzled or s.over:
            return
        attack_triggers(s, s.atk.attacker)


def set_target(s: GameState, t: Target) -> None:
    s.atk.target_kind = t.kind
    s.atk.target = t.inst
    s.emit("target", t.kind, t.inst)


class ReactionWindowStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        atk = s.atk
        if atk.fizzled or s.over:
            return
        # CR 9.6 / 9.13: the attack ends if the attacker or the defending Unit has left the field.
        if s.i_zone[atk.attacker] is not Zone.FIELD or (
                atk.target_kind == TARGET_UNIT and s.i_zone[atk.target] is not Zone.FIELD):
            atk.fizzled = True
            return
        opts = reaction_menu(s)
        if len(opts) == 1:                                 # only Pass: no real decision
            return
        s.pending = Choice(ChoiceKind.REACTION, 1 - atk.attacker_ctrl, tuple(opts),
                           prompt="React?")


def stealable(s: GameState, thief_unit: int, victim: int) -> list[int]:
    """Indices of the victim's dice this attacker may steal, after protection effects."""
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


def push_steals(s: GameState, thief_unit: int, indices) -> None:
    """Queue stealing the given dice (indices of the victim's Gig area), one step per die."""
    thief = s.i_owner[thief_unit]
    for i in sorted(indices):                            # LIFO: highest index steals first
        s.stack.append(StealOneStep(thief_unit, thief, i))


class StealOneStep(Step):
    __slots__ = ("unit", "thief", "index")

    def __init__(self, unit: int, thief: int, index: int) -> None:
        self.unit, self.thief, self.index = unit, thief, index

    def run(self, s: GameState) -> None:
        victim = 1 - self.thief
        if self.index >= len(s.gig[victim]) or s.over:
            return
        act = s._active
        if act is None:
            act = _rebuild_active(s)
        ws = act[7]
        # The victim's replacement effects first; the tuples are a snapshot of the index.
        for i, h in ws[victim] + ws[1 - victim]:
            if h(_ctx(s, i), self.unit, victim, self.index):
                return
        do_steal(s, self.unit, self.thief, self.index)


def do_steal(s: GameState, unit: int, thief: int, index: int) -> None:
    sides, value = steal_gig(s, thief, index)
    s.used.add(("stole", unit))
    dispatch(s, ("steal", unit, thief, sides, value))


class ResolveAttackStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        atk = s.atk
        if atk.fizzled or s.over or s.i_zone[atk.attacker] is not Zone.FIELD:
            return
        a = atk.attacker
        if atk.target_kind == TARGET_UNIT:
            t = atk.target
            if s.i_zone[t] is not Zone.FIELD:
                return                                     # target left play; no fight, no steal
            if not atk.redirects and Target(TARGET_UNIT, t) not in attack_targets(s, a):
                return                                     # CR 9.26.3: no longer a legal target
            fight(s, a, t)
        elif atk.target_kind == TARGET_GIG and atk.gig_steal_allowed:
            thief = atk.attacker_ctrl
            victim = 1 - thief
            n = steal_count(power(s, a, ATTACKING))
            for v in s.mod_values("steal_fewer", a):
                n -= v
            cands = stealable(s, a, victim)
            if n <= 0 or not cands:
                return
            if n >= len(cands):
                push_steals(s, a, cands)
                return
            opts = tuple(Pick(c) for c in (combinations(cands, n) if n > 1 else [(i,) for i in cands]))

            def cont(st: GameState, act: Pick, unit=a) -> None:
                push_steals(st, unit, act.picks)

            ask(s, Choice(ChoiceKind.PICK, thief, opts, cont, prompt="Steal which Gig(s)?"))


def fight(s: GameState, a: int, t: int) -> None:
    """Resolve a fight between attacker ``a`` and defender ``t`` (both on the field)."""
    ta = VS_LEGEND if s.card(t).type is CardType.LEGEND else VS_UNIT
    tt = VS_LEGEND if s.card(a).type is CardType.LEGEND else VS_UNIT
    pa = power(s, a, ATTACKING | FIGHTING | ta)
    pt = power(s, t, FIGHTING | tt)
    a_wins, t_wins = pa > pt, pt > pa
    for x, y, flag in ((a, t, "a"), (t, a, "t")):
        sc = s.card(x).script
        tag = sc.extra.get("wins_vs_tag") if sc is not None else None
        if tag and tag in s.card(y).tags:
            a_wins, t_wins = (True, False) if flag == "a" else (False, True)
    s.emit("fight", a, t, pa, pt)
    oa, ot = s.i_owner[a], s.i_owner[t]
    defeat_t = a_wins or not t_wins
    defeat_a = t_wins or not a_wins
    if s.has_mod("no_defeat_in_fight", t):
        defeat_t = False
    if s.has_mod("no_defeat_in_fight", a):
        defeat_a = False
    if s.cfg.zero_power_cannot_defeat:                     # CR 9.19.2
        if pa <= 0:
            defeat_t = False
        if pt <= 0:
            defeat_a = False
    # Reboot Optics: the next time a rival Unit fights this turn, it doesn't defeat our Unit.
    if defeat_t and s.has_mod("next_fight_no_defeat", ot):
        defeat_t = False
        s.mods = [m for m in s.mods if not (m[0] == "next_fight_no_defeat" and m[1] == ot)]
    if defeat_a and s.has_mod("next_fight_no_defeat", oa):
        defeat_a = False
        s.mods = [m for m in s.mods if not (m[0] == "next_fight_no_defeat" and m[1] == oa)]
    if a_wins:
        dispatch(s, ("fight_won", a, t, pa - pt))
        dispatch(s, ("fight_lost", t, a))
    elif t_wins:
        dispatch(s, ("fight_won", t, a, pt - pa))
        dispatch(s, ("fight_lost", a, t))
    # Safety Override: the next time a friendly Unit loses a fight, defeat the opposing Unit.
    if a_wins and s.has_mod("next_loss_defeats_winner", ot):
        s.mods = [m for m in s.mods if not (m[0] == "next_loss_defeats_winner" and m[1] == ot)]
        defeat_a = True
    if t_wins and s.has_mod("next_loss_defeats_winner", oa):
        s.mods = [m for m in s.mods if not (m[0] == "next_loss_defeats_winner" and m[1] == oa)]
        defeat_t = True
    if defeat_t:
        defeat(s, t)
    if defeat_a:
        defeat(s, a)


class EndAttackStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        s.atk = None


# --------------------------------------------------------------- effects
class HookStep(Step):
    """Run a card script hook. The hook receives an EffectCtx and must not block."""
    __slots__ = ("hook", "inst")

    def __init__(self, hook, inst: int) -> None:
        self.hook = hook
        self.inst = inst

    def run(self, s: GameState) -> None:
        if s.over:
            return
        self.hook(_ctx(s, self.inst))


class FnStep(Step):
    """Run an arbitrary fn(state) later — used to sequence effects after a choice resolves."""
    __slots__ = ("fn",)

    def __init__(self, fn) -> None:
        self.fn = fn

    def run(self, s: GameState) -> None:
        if not s.over:
            self.fn(s)


__all__ = ["Step", "AskStep", "MulliganStep", "StartGameStep", "push_turn", "WinCheckStep",
           "ReadyStep", "DrawStep", "GainGigStep", "StartTurnEventsStep", "MainPhaseStep",
           "EndTurnStep", "EndTurnCleanupStep", "DeclareTargetStep", "ReactionWindowStep",
           "ResolveAttackStep", "EndAttackStep", "HookStep", "FnStep", "set_target", "fight",
           "push_steals", "stealable", "do_steal", "StealOneStep"]
