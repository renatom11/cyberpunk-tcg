"""Small integer enums. IntEnum so they index lists and compare cheaply in the hot path."""

from __future__ import annotations

from enum import IntEnum


class Zone(IntEnum):
    DECK = 0
    HAND = 1
    FIELD = 2
    EDDIES = 3
    TRASH = 4
    LEGENDS = 5
    REMOVED = 6
    LIMBO = 7          # a Program while it resolves: outside every area (CR 4.14.2)


NZONE = len(Zone)


class CardType(IntEnum):
    LEGEND = 0
    UNIT = 1
    PROGRAM = 2
    GEAR = 3


class Color(IntEnum):
    RED = 0
    GREEN = 1
    BLUE = 2
    YELLOW = 3


class Keyword(IntEnum):
    ADRENALINE = 0
    GO_SOLO = 1
    QUICK = 2
    BLOCKER = 3


class Trigger(IntEnum):
    PLAY = 0
    CALL = 1
    ATTACK = 2
    DEFEATED = 3


class EndReason(IntEnum):
    SEVEN_GIGS = 0
    DECKOUT = 1
    OVERTIME = 2
    CONCEDE = 3


# Die kinds are just their side counts; the fixer area is a list of these.
DICE = (4, 6, 8, 10, 12, 20)
D20 = 20

# Instance flag bits (state.i_flags)
F_GO_SOLO = 1 << 0        # a Legend played as a Unit; leaves the field -> removed from game
F_NO_READY_NEXT = 1 << 1  # skip this card at the next Ready step (first-player handicap etc.)
F_CANT_ATTACK = 1 << 2    # printed "this Unit can't attack"
F_MUST_ATTACK = 1 << 3    # "must attack next turn if it can"
#: "It can't ready until your next turn" -- a PROHIBITION, not a skipped Ready step. The two used to
#: share F_NO_READY_NEXT, which is why the prohibition was enforced in exactly one place: the Ready
#: step skipped the card and every card effect that readies (`ops.ready`, nine scripts) went straight
#: through it. The first-player handicap keeps F_NO_READY_NEXT, because that one really is only
#: about the next Ready step.
F_CANT_READY = 1 << 4
#: Ruling 047: this Legend reached the field by paying its printed cost, NOT by using GO SOLO, so
#: the keyword's permission to attack through Lag does not apply to it. It is a separate bit from
#: F_GO_SOLO because that one means "a Legend standing on the field", which is true of both plays
#: and is what sends it out of the game when it leaves (CR 4.4.1).
F_NO_SOLO_KEYWORD = 1 << 5

# Attack target kinds
TARGET_UNIT = 0
TARGET_GIG = 1

NO_INST = -1
