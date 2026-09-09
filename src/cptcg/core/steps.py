"""The step machine.

The engine never blocks inside a Python call: work is queued as ``Step`` objects on
``state.stack`` and a step that needs a player decision sets ``state.pending`` and returns. That
keeps the whole game a pure state machine, clonable at every decision point — which is exactly
what a search agent needs. Steps are immutable, so cloning a state shares them.
"""

from __future__ import annotations

from itertools import combinations

from cptcg.core.actions import Choice, ChoiceKind, Mulligan, Pass, Pick, TakeGigDie, Target
from cptcg.core.enums import (F_NO_READY_NEXT, NZONE, TARGET_GIG, TARGET_UNIT, EndReason,
                              Zone)
from cptcg.core.legal import attack_targets, gig_die_options, main_menu, reaction_menu
from cptcg.core.ops import (defeat, draw, end_game, gain_gig, power, steal_count, steal_gig)
from cptcg.core.state import GameState


class Step:
    __slots__ = ()

    def run(self, s: GameState) -> None:  # pragma: no cover - interface
        raise NotImplementedError


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
    s.stack.append(EndTurnStep())
    s.stack.append(MainPhaseStep())
    s.stack.append(GainGigStep())
    s.stack.append(DrawStep())
    s.stack.append(ReadyStep())
    s.stack.append(WinCheckStep())


class WinCheckStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        s.emit("turn", s.turn, s.active)
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


class MainPhaseStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        s.pending = Choice(ChoiceKind.MAIN, s.active, tuple(main_menu(s)), prompt="Main phase")


class EndTurnStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        p = s.active
        for i in range(len(s.i_lag)):
            s.i_lag[i] = 0
        s.temp_power.clear()
        s.once[0] = s.once[1] = 0
        s.turns_taken[p] += 1
        if min(s.turns_taken) >= s.cfg.overtime_after_turn and not s.overtime:
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


def set_target(s: GameState, t: Target) -> None:
    s.atk.target_kind = t.kind
    s.atk.target = t.inst
    s.emit("target", t.kind, t.inst)


class ReactionWindowStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        atk = s.atk
        if atk.fizzled:
            return
        opts = reaction_menu(s)
        if len(opts) == 1:                                 # only Pass: no real decision
            return
        s.pending = Choice(ChoiceKind.REACTION, 1 - atk.attacker_ctrl, tuple(opts),
                           prompt="React?")


class ResolveAttackStep(Step):
    __slots__ = ()

    def run(self, s: GameState) -> None:
        atk = s.atk
        if atk.fizzled or s.i_zone[atk.attacker] is not Zone.FIELD:
            return
        a = atk.attacker
        if atk.target_kind == TARGET_UNIT:
            t = atk.target
            if s.i_zone[t] is not Zone.FIELD:
                return                                     # target left play; no fight, no steal
            pa, pt = power(s, a), power(s, t)
            s.emit("fight", a, t, pa, pt)
            if pa > pt:
                defeat(s, t)
            elif pt > pa:
                defeat(s, a)
            else:
                defeat(s, t)
                defeat(s, a)
        elif atk.target_kind == TARGET_GIG and atk.gig_steal_allowed:
            thief = atk.attacker_ctrl
            victim = 1 - thief
            n = steal_count(power(s, a))
            k = len(s.gig[victim])
            if n <= 0 or k == 0:
                return
            if n >= k:
                for _ in range(k):
                    steal_gig(s, thief, 0)
                return
            if n == 1:
                opts = tuple(Pick((i,)) for i in range(k))
            else:
                opts = tuple(Pick(c) for c in combinations(range(k), n))

            def cont(st: GameState, act: Pick, thief=thief) -> None:
                for i in sorted(act.picks, reverse=True):
                    steal_gig(st, thief, i)

            s.pending = Choice(ChoiceKind.PICK, thief, opts, cont, prompt="Steal which Gig(s)?")


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
        from cptcg.core.effects import EffectCtx
        self.hook(EffectCtx(s, self.inst))


class TrashStep(Step):
    __slots__ = ("inst",)

    def __init__(self, inst: int) -> None:
        self.inst = inst

    def run(self, s: GameState) -> None:
        from cptcg.core.ops import move
        if s.i_zone[self.inst] is Zone.HAND:
            move(s, self.inst, Zone.TRASH)


__all__ = ["Step", "MulliganStep", "StartGameStep", "push_turn", "WinCheckStep", "ReadyStep",
           "DrawStep", "GainGigStep", "MainPhaseStep", "EndTurnStep", "DeclareTargetStep",
           "ReactionWindowStep", "ResolveAttackStep", "EndAttackStep", "HookStep", "TrashStep",
           "set_target", "Pass"]
