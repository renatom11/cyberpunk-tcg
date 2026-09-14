"""Batch A05 — Units: PLAY triggers (part 1/2).

Audit of src/cptcg/cards/sets/wnc.py lines 385-480 against the printed text in
data/cards/wnc.json. Every test here asserts a printed-text outcome only (Gig areas, zones,
hand size, power), never script internals.
"""
import pytest
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, EndTurn, Play, TakeGigDie
from cptcg.core.enums import NO_INST, Zone

E = 9  # plenty of eddies


def play(s, cid):
    do(s, Play(find(s, cid, Zone.HAND), NO_INST))
    return s


def test_chrome_fang_stops_every_steal_of_a_gig_above_the_thiefs_power(pool):
    """'PLAY: Until your next turn, rival Units can't steal friendly Gigs with value higher
    than their power.'

    The prohibition is unqualified — it is about *stealing*, not about the attack step that
    usually causes one. Psycho Squad (power 6) wears Gorilla Arms (+3 power, and 'the first
    time this Unit steals 1 or more Gigs each turn, steal a rival Gig with a value not shared
    by a friendly Gig'), so the thief's power is 9. Its attack legitimately takes the d4
    showing 2; Gorilla Arms then hands it the d12 showing 11, which is higher than 9 and which
    Chrome Fang says it can't steal.

    Fixed: AUD-chrome-fang-1.
    """
    s = board(pool, Side(hand=["chrome-fang"], eddies=E, gig=[(4, 2), (12, 11)],
                         deck=["floor-it"] * 8),
              Side(field=[("psycho-squad", {"gear": ["gorilla-arms"]})], deck=["floor-it"] * 8))
    play(s, "chrome-fang")
    do(s, EndTurn())
    do(s, TakeGigDie(4))
    do(s, Attack(find(s, "psycho-squad", player=1)))
    assert (12, 11) in s.gig[0]                 # 11 > 9: protected against every steal
    assert (12, 11) not in s.gig[1]


def test_westbrook_stops_every_steal_of_a_gig_below_the_legends_power(pool):
    """'PLAY: Until your next turn, rival Legends can't steal friendly Gigs with value less
    than their power.'

    V (power 6) is on the field wearing Gorilla Arms (+3 power), so the Legend's power is 9.
    Its attack legitimately takes the d12 showing 11 (11 is not less than 9). Gorilla Arms
    then hands it the d6 showing 3, which is less than 9 and which Westbrook says it can't
    steal.

    Fixed: AUD-westbrook-netrunner-1.
    """
    s = board(pool, Side(hand=["westbrook-netrunner"], eddies=E, gig=[(6, 3), (12, 11)],
                         deck=["floor-it"] * 8),
              Side(field=[("v-streetkid", {"faceup": True, "gear": ["gorilla-arms"]})],
                   deck=["floor-it"] * 8))
    play(s, "westbrook-netrunner")
    do(s, EndTurn())
    do(s, TakeGigDie(4))
    do(s, Attack(find(s, "v-streetkid", player=1)))
    assert (6, 3) in s.gig[0]                   # 3 < 9: protected against every steal
    assert (6, 3) not in s.gig[1]
