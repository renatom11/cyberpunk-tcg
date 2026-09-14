"""Batch A09 — Units: static effects, restrictions, cost modifiers (part 1/3).

Audit of src/cptcg/cards/sets/wnc.py lines 739-805 against the printed ``text`` in
data/cards/wnc.json. Every test here is a finding: it asserts what the card *says*, so it fails
against the script as written. See out/audit/a09/findings.md for the clause maps.
"""
import pytest
from conftest import Side, board, do, find

from cptcg.core import view
from cptcg.core.actions import EndTurn, Pick
from cptcg.core.enums import Zone


# ------------------------------------------------------------------- AUD-misty-olszewski-1
@pytest.mark.xfail(strict=True, reason=(
    "AUD-misty-olszewski-mender-of-broken-spirits-1: 'reveal the top card of your deck' is never "
    "implemented — on the match branch the card goes deck -> hand and the Rival never sees it"))
def test_misty_reveals_the_top_card_to_the_rival(pool):
    """"... choose a card type. Then, **reveal** the top card of your deck. If it's the chosen
    type, add it to your hand and ready 1 Eddie. Otherwise, trash it."

    A printed "reveal" is public: both players see the card. The set distinguishes the two
    explicitly — Kiroshi Optics reads "Look at a friendly face-down Legend. *(Don't reveal it.)*"
    — and ruling 002 rests on exactly this ("Selling requires revealing the card; both players
    saw it"). The script reads the card into a Python list (``top = c2.top(1)``) and moves it, so
    on the *match* branch it travels deck -> hand and the Rival never learns what it was. The
    mismatch branch only looks right by accident: the trash is a public zone.
    """
    s = board(pool, Side(field=["misty-olszewski-mender-of-broken-spirits"], eddies=1,
                         spent_eddies=1, deck=["floor-it", "psycho-squad"]),
              Side(deck=["floor-it"]))
    do(s, EndTurn())
    do(s, Pick((0,)))                                  # choose Unit; top is Psycho Squad, a Unit
    top = find(s, "psycho-squad", Zone.HAND, 0)        # added to hand, as the card says
    assert view.knows_identity(s, 1, top), "the Rival was never shown the revealed card"
