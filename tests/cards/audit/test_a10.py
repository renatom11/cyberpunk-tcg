"""Batch A10 — Units: static effects, restrictions, cost modifiers (part 2/3).

Findings from auditing wnc.py lines 810-892 against the printed text in data/cards/wnc.json.
Each test asserts a printed-text outcome only (power, cost paid, zones).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conftest import Side, board, do, find   # noqa: E402
from cptcg.core.actions import GoSolo, Play  # noqa: E402
from cptcg.core.enums import Zone  # noqa: E402
from cptcg.core.ops import ATTACKING, available, play_cost, power  # noqa: E402

E = 9


@pytest.mark.xfail(strict=True, reason="AUD-viktor-vektor-drop-your-illusions-1: the -3 goes to the first CYBERWARE Gear played while Viktor is in play, not to your first CYBERWARE Gear of the turn")
def test_viktor_discounts_only_the_first_cyberware_gear_of_the_turn(pool):
    """'Play your first CYBERWARE Gear each turn for -3 €$, to a minimum of 1 €$.'

    Mantis Blades (CYBERWARE Gear) is played first, before Viktor hits the field. Gorilla Arms is
    then the *second* CYBERWARE Gear played this turn, so it costs its printed 4 €$. The script
    only counts CYBERWARE Gear played while Viktor is already in play, so it hands the discount to
    the second one.
    """
    s = board(pool, Side(hand=["mantis-blades", "viktor-vektor-drop-your-illusions", "gorilla-arms"],
                         field=["psycho-squad"], eddies=20), Side())
    do(s, Play(find(s, "mantis-blades", Zone.HAND), find(s, "psycho-squad")))     # 1 €$
    do(s, Play(find(s, "viktor-vektor-drop-your-illusions", Zone.HAND)))          # 5 €$
    g = find(s, "gorilla-arms", Zone.HAND)
    assert play_cost(s, 0, g) == 4
    do(s, Play(g, find(s, "psycho-squad")))
    assert available(s, 0) == 20 - 1 - 5 - 4


def test_saburo_aura_reaches_an_arasaka_legend_that_went_solo(pool):
    """'Friendly ARASAKA Units have +1 power while attacking.'

    GO SOLO (docs/rules.md): 'Pay this Legend's cost to play it as a ready Unit'; ruling 015's
    default says the Legend on the field 'is a Unit now'. Goro Takemura (Hands Unclean) is
    ARASAKA and friendly, so while attacking he is 7 + 1 = 8.

    Fixed: AUD-saburo-arasaka-stubborn-patriarch-1, by ruling 044 — settled by the FAQ, which says a Legend played to the
    field with GO SOLO is BOTH a Unit and a Legend, so Unit-hood is answered by the zone
    and never by the printed card type. Held as a strict xfail until the FAQ arrived; the
    deleted marker is the red-to-green record.
    """
    s = board(pool, Side(legends=[("saburo-arasaka-stubborn-patriarch", {"faceup": True}),
                                  ("goro-takemura-hands-unclean", {"faceup": True})], eddies=E),
              Side())
    g = find(s, "goro-takemura-hands-unclean")
    do(s, GoSolo(g))
    assert s.i_zone[g] == Zone.FIELD
    assert power(s, g, ATTACKING) == 8


def test_royce_gear_bonus_applies_in_the_legends_area(pool):
    """'During your turn, this Legend has +2 power for each of its equipped Gear.'

    Gear legally equips to a face-up Legend in the Legends area (docs/rules.md, 'Gear — pay its
    cost and equip it to a friendly Unit or Legend'; core.legal.gear_hosts). The text puts no zone
    condition on the bonus, so a face-up Royce holding two Gear is 6 + 4 (printed Gear power) + 4
    during his controller's turn.

    Fixed: AUD-royce-psycho-on-the-edge-1.
    """
    s = board(pool, Side(legends=[("royce-psycho-on-the-edge",
                                   {"faceup": True, "gear": ["mantis-blades", "satori-sword-of-saburo"]})]),
              Side())
    r = find(s, "royce-psycho-on-the-edge")
    assert power(s, r) == 6 + 4 + 4
