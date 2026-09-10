"""Actions and choices.

Every stop of the engine is a ``Choice``: whose decision it is and the legal ``Action`` options.
Actions are frozen slotted dataclasses so they are hashable (search trees key on them) and cheap.
Agents return an *index* into ``choice.options``; that keeps replay logs tiny and dodges any
object-identity questions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

from cptcg.core.enums import NO_INST


class ChoiceKind(IntEnum):
    MULLIGAN = 0     # keep or mulligan the opening hand
    ORDER = 1        # d20 winner chooses to go first or second
    GIG_DIE = 2      # start phase: which fixer die to roll
    MAIN = 3         # main-phase menu
    TARGET = 4       # attacker declares a target
    REACTION = 5     # defender's reaction window
    PICK = 6         # generic effect choice; resolved by a continuation


class Action:
    __slots__ = ()


@dataclass(frozen=True, slots=True)
class Mulligan(Action):
    keep: bool


@dataclass(frozen=True, slots=True)
class ChooseOrder(Action):
    go_first: bool


@dataclass(frozen=True, slots=True)
class TakeGigDie(Action):
    sides: int


@dataclass(frozen=True, slots=True)
class EndTurn(Action):
    pass


@dataclass(frozen=True, slots=True)
class Sell(Action):
    inst: int


@dataclass(frozen=True, slots=True)
class Play(Action):
    inst: int
    host: int = NO_INST      # Gear only: the Unit or face-up Legend it equips


@dataclass(frozen=True, slots=True)
class GoSolo(Action):
    inst: int                # the face-up Legend instance


@dataclass(frozen=True, slots=True)
class CallLegend(Action):
    inst: int                # the face-down Legend slot to flip


@dataclass(frozen=True, slots=True)
class Activate(Action):
    inst: int
    ability: int             # index into the card script's abilities


@dataclass(frozen=True, slots=True)
class Attack(Action):
    inst: int                # target is declared separately, after ATTACK triggers


@dataclass(frozen=True, slots=True)
class Target(Action):
    kind: int                # TARGET_UNIT | TARGET_GIG
    inst: int = NO_INST


@dataclass(frozen=True, slots=True)
class Block(Action):
    inst: int


@dataclass(frozen=True, slots=True)
class Pass(Action):
    pass


@dataclass(frozen=True, slots=True)
class Pick(Action):
    picks: tuple[int, ...]   # whatever the continuation asked for: instances, dice indices...


@dataclass(frozen=True, slots=True)
class Choice:
    kind: ChoiceKind
    player: int
    options: tuple[Action, ...]
    cont: Callable | None = None   # PICK only: cont(state, action) resolves the choice
    prompt: str = ""
    lazy: bool = False             # options not computed yet (see engine.legal_actions)

    def index_of(self, action: Action) -> int:
        return self.options.index(action)
