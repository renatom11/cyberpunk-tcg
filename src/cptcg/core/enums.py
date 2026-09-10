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

# Attack target kinds
TARGET_UNIT = 0
TARGET_GIG = 1

NO_INST = -1
