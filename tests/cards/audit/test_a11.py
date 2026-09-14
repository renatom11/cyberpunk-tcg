"""Batch A11 audit — Units: static effects, restrictions, cost modifiers (part 3/3).

Cards: maxtac-squadron, delamain-cab, v-roamer-of-the-badlands, wraith-marauders,
6th-street-recruits, maelstrom-goons, maelstrom-zealots, la-llorona-ghost-of-the-past,
augmented-negotiators, rita-wheeler-no-stupid-questions, alt-cunningham-mother-of-daemons.

Every test here asserts printed card text (data/cards/wnc.json), not engine behaviour.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conftest import Side, board, do, find                    # noqa: E402
from cptcg.core.actions import Attack, GoSolo, Target         # noqa: E402
from cptcg.core.enums import Zone                             # noqa: E402

TARGET_UNIT = 0
E = 9


# ------------------------------------------------------------ 6th-street-recruits
@pytest.mark.xfail(strict=True, reason="AUD-6th-street-recruits-1: a GO SOLO Legend on the field is "
                                       "'a friendly Unit' (GO SOLO: 'play it as a ready Unit'), but the "
                                       "script gates on CardDef.type is UNIT and never fires for it")
def test_6th_street_recruits_fires_when_a_go_solo_legend_steals_a_d6(pool):
    """'When a friendly Unit steals a d6, increase a Gig by up to 6.'

    GO SOLO (docs/rules.md line 90, and printed in full on v-corporate-exile) reads
    "Pay this Legend's cost to play it as a ready Unit"; ruling 015 spells the consequence out
    as "(it is a Unit now)". The engine agrees: s.units(0) lists the solo'd Legend. So a d6
    stolen by Goro Takemura on the field is a d6 stolen by a friendly Unit, and 6th Street
    Recruits must offer its increase.
    """
    s = board(pool, Side(field=["6th-street-recruits"], eddies=E,
                         legends=[("goro-takemura-hands-unclean", {"faceup": True})]),
              Side(gig=[(6, 3)]))
    goro = find(s, "goro-takemura-hands-unclean")
    do(s, GoSolo(goro))
    assert goro in s.units(0)                       # the engine already calls it a friendly Unit
    do(s, Attack(goro))                             # power 7: steals the d6
    assert s.gig[0] == [(6, 3)]
    # +1..+3 on the stolen d6 (it caps at 6), plus the "up to" decline.
    assert [getattr(o, "picks", o) for o in s.pending.options] == [(0,), (1,), (2,), ()]


def test_6th_street_recruits_fires_for_a_plain_friendly_unit(pool):
    """Control for the xfail above: the same board with a Unit thief does offer the increase."""
    s = board(pool, Side(field=["6th-street-recruits", "psycho-squad"]), Side(gig=[(6, 3)]))
    do(s, Attack(find(s, "psycho-squad")))
    assert [o.picks for o in s.pending.options] == [(0,), (1,), (2,), ()]


# -------------------------------------------------------------- maelstrom-zealots
def test_maelstrom_zealots_defeats_the_winner_of_a_tied_fight(pool):
    """'When this Unit loses a fight, defeat the opposing rival Unit.'

    Zealots is power 0, so a 0-power rival Unit ties it. Ruling 010: "Ties: both lose and both
    are defeated"; docs/rules.md: "on a tie they defeat each other". Zealots lost that fight, so
    its trigger must defeat the opposing Unit — which matters here precisely because ruling 010
    also stops the tie itself from defeating either 0-power Unit.

    Fixed: AUD-maelstrom-zealots-1.
    """
    s = board(pool, Side(field=["maelstrom-zealots"]),
              Side(field=[("delamain-rideshare-ai", {"spent": True})], gig=[(4, 1)]))
    do(s, Attack(find(s, "maelstrom-zealots")))
    do(s, Target(TARGET_UNIT, find(s, "delamain-rideshare-ai")))
    assert s.i_zone[find(s, "delamain-rideshare-ai")] == Zone.TRASH


def test_maelstrom_zealots_defeats_the_winner_of_a_decisive_loss(pool):
    """Control for the xfail above: a fight Zealots decisively loses does defeat the winner."""
    s = board(pool, Side(field=["maelstrom-zealots"]),
              Side(field=[("psycho-squad", {"spent": True})], gig=[(4, 1)]))
    do(s, Attack(find(s, "maelstrom-zealots")))
    do(s, Target(TARGET_UNIT, find(s, "psycho-squad")))
    assert s.i_zone[find(s, "psycho-squad")] == Zone.TRASH
    assert s.i_zone[find(s, "maelstrom-zealots")] == Zone.TRASH
