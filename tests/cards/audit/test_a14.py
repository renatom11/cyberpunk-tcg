"""Batch A14 audit — Legends (part 2/2), wnc.py lines 1270-1412.

Cards: panam-palmer-nomad-cavalry, johnny-silverhand-rocking-renegade,
judy-alvarez-braindance-maestro, alt-cunningham-soulkiller-architect,
jackie-welles-mamas-favorite, jackie-welles-pour-one-out-for-me,
rogue-amendiares-preem-solo, goro-takemura-vengeful-bodyguard,
yorinobu-arasaka-embracing-destruction, sasha-yakovleva-wont-let-you-down.

Every test here asserts printed card text (data/cards/wnc.json), not engine behaviour.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conftest import Side, board, defeat_now, do, find            # noqa: E402
from cptcg.core.actions import ChoiceKind, GoSolo, Pick           # noqa: E402
from cptcg.core.enums import Zone                                 # noqa: E402

E = 9
#: Three Legends with no CALL trigger, so a board that needs Legends in reserve does not fire one.
NOCALL = ["saburo-arasaka-stubborn-patriarch", "kerry-eurodyne-axe-attitude-audience",
          "river-ward-detective-on-the-hunt"]
JACKIE = "jackie-welles-mamas-favorite"


def _take_the_offer(s):
    """Accept the 'Pay 1 €$: defeat Jackie instead?' question if the engine asks it."""
    if s.pending is not None and s.pending.kind is ChoiceKind.PICK:
        do(s, Pick((0,)))


# ------------------------------------------------------- jackie-welles-mamas-favorite
def test_jackie_offers_the_swap_for_an_ordinary_unit(pool):
    """Control for AUD-jackie-welles-mamas-favorite-1 and -2: the same board, the same helper and
    the same question, with a plain Unit being defeated and Jackie in the Legends area. It passes,
    so the two xfails below are about *which* cards count, not about a broken board."""
    s = board(pool, Side(legends=[(JACKIE, {"faceup": True})] + NOCALL[:2],
                         field=["psycho-squad"], eddies=E), Side())
    jackie = find(s, JACKIE)
    u = find(s, "psycho-squad", Zone.FIELD, 0)
    defeat_now(s, u)
    _take_the_offer(s)
    assert s.i_zone[u] == Zone.FIELD                   # the Unit was saved ...
    assert s.i_zone[jackie] == Zone.REMOVED            # ... and Jackie left the game instead


@pytest.mark.xfail(strict=True, reason="AUD-jackie-welles-mamas-favorite-1: the replacement is gated on card type UNIT, so it never offers to save a Legend played as a Unit with GO SOLO")
def test_jackie_can_save_a_legend_played_as_a_unit(pool):
    """'If a friendly Unit would be defeated, you may pay 1 €$ to defeat this Legend instead.'

    A Legend played with GO SOLO is on the field as a Unit — rules.md: 'Pay this Legend's cost to
    play it as a ready Unit'; ruling 015: 'it is a Unit now'. Sasha here is exactly that, so the
    offer is due before she is defeated."""
    s = board(pool, Side(legends=[(JACKIE, {"faceup": True}),
                                  ("sasha-yakovleva-wont-let-you-down", {"faceup": True}),
                                  NOCALL[0]], eddies=E, deck=["floor-it"]),
              Side())
    jackie = find(s, JACKIE)
    sasha = find(s, "sasha-yakovleva-wont-let-you-down")
    do(s, GoSolo(sasha))
    assert s.i_zone[sasha] == Zone.FIELD               # she is a Unit on the field now
    defeat_now(s, sasha)
    _take_the_offer(s)
    assert s.i_zone[sasha] == Zone.FIELD
    assert s.i_zone[jackie] == Zone.REMOVED


@pytest.mark.xfail(strict=True, reason="AUD-jackie-welles-mamas-favorite-2: the replacement is gated on Jackie sitting in the Legends area, so it switches off once she GOES SOLO")
def test_jackie_still_protects_after_she_goes_solo(pool):
    """'If a friendly Unit would be defeated, you may pay 1 €$ to defeat this Legend instead.'

    Nothing in the text limits the replacement to the Legends area, and a Legend on the field
    through GO SOLO keeps its text (ruling 032: its PLAY trigger fires there)."""
    s = board(pool, Side(legends=[(JACKIE, {"faceup": True})] + NOCALL[:2],
                         field=["psycho-squad"], eddies=E), Side())
    jackie = find(s, JACKIE)
    u = find(s, "psycho-squad", Zone.FIELD, 0)
    do(s, GoSolo(jackie))
    assert s.i_zone[jackie] == Zone.FIELD
    defeat_now(s, u)
    _take_the_offer(s)
    assert s.i_zone[u] == Zone.FIELD
    assert s.i_zone[jackie] == Zone.REMOVED
