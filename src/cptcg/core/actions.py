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
    """Play a face-up Legend to the field. Two ways, and ruling 047 is that they are different.

    ``keyword=True`` is GO SOLO itself: it arrives as a ready Unit (CR 11.25.1) and the keyword
    lets it attack through its Lag. ``keyword=False`` is the plain play the FAQ describes — *"Can I
    play a Legend to the field from the Legends area without using GO SOLO? **Yes**, as long as the
    Legend has a numeric cost value… It enters the field **with lag**, and **in the same
    orientation** it was in the Legends area."* — so it keeps its orientation and cannot attack
    this turn.

    A FIELD on the existing class rather than a new Action class, deliberately.
    ``learn.policy.KINDS`` is a tuple of Action *classes* that ``_SPEC`` one-hots over, so adding
    ``PlayLegend`` would move ``action_feature_digest()`` and every fitted policy head would be
    rejected on load. The default keeps every existing ``GoSolo(i)`` comparison working.
    """

    inst: int                # the face-up Legend instance
    keyword: bool = True     # False: pay the printed cost without using GO SOLO (ruling 047)


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


def call_site(fn) -> str:
    """``file:line`` of ``fn`` — a stable name for the code that asked a question.

    ``prompt`` is player-facing text and shipped cards build it by formatting a card name
    (``f"Trash {c.d(top[0]).name}?"``), so it is unsafe as an identity: anything that keys on a
    prompt hands that card name to whoever holds the key, including a seat that may not see the
    card (``view._pending_key``). A call site draws the same distinction — this card, this
    question — and carries no card text at all.
    """
    code = getattr(fn, "__code__", None)
    if code is None:
        return ""
    return f"{code.co_filename.rpartition('/')[2]}:{code.co_firstlineno}"


@dataclass(frozen=True, slots=True)
class Choice:
    kind: ChoiceKind
    player: int
    options: tuple[Action, ...]
    cont: Callable | None = None   # PICK only: cont(state, action) resolves the choice
    prompt: str = ""               # player-facing text; may name a hidden card, so never a key
    lazy: bool = False             # options not computed yet (see engine.legal_actions)
    #: Identity of the question, safe to key on: ``"<asking instance>@<call site>"``. Empty for the
    #: fixed-kind choices (MAIN, REACTION, ...), whose ``kind`` already identifies them.
    tag: str = ""
    #: Instances this choice has *shown* to ``player`` — the top cards of a deck a peek looked at
    #: before asking. Declared by the effect, never guessed: ``view`` pins exactly these while the
    #: choice is open, and pins nothing otherwise.
    revealed: tuple[int, ...] = ()

    def index_of(self, action: Action) -> int:
        return self.options.index(action)
