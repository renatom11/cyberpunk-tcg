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
def test_misty_adds_the_revealed_card_and_readies_an_eddie_on_a_match(pool):
    """"... choose a card type. Then, reveal the top card of your deck. If it's the chosen type, add
    it to your hand and ready 1 Eddie. Otherwise, trash it."

    **Withdrawn: AUD-misty-olszewski-mender-of-broken-spirits-1.** The finding was that a printed
    "reveal" is public — the set distinguishes the two explicitly, Kiroshi Optics reading "Look at a
    friendly face-down Legend. *(Don't reveal it.)*" — and that on the match branch the card travels
    deck → hand with the Rival never learning what it was. The killer conceded; the blind reader,
    which was never shown the finding, read the same clause and reached the opposite conclusion:
    the engine has no persistent "publicly known" ledger for a card in hand, every reveal-to-hand
    card in the set behaves identically, and `view.py` documents over-hiding as the safe direction.
    A set-wide modelling convention, not a Misty deviation — and a finding an independent reader
    contradicts is not a finding.

    So what is left is the card's own outcome, which is right: the match branch adds the card and
    readies an Eddie. The information question is recorded in docs/verification.md as a modelling
    limitation rather than pinned here as a bug.
    """
    s = board(pool, Side(field=["misty-olszewski-mender-of-broken-spirits"], eddies=1,
                         spent_eddies=1, deck=["floor-it", "psycho-squad"]),
              Side(deck=["floor-it"]))
    assert sum(1 for i in s.zone(0, Zone.EDDIES) if not s.i_spent[i]) == 0
    do(s, EndTurn())
    do(s, Pick((0,)))                                  # choose Unit; top is Psycho Squad, a Unit
    assert find(s, "psycho-squad", Zone.HAND, 0) >= 0  # added to hand, as the card says
    assert sum(1 for i in s.zone(0, Zone.EDDIES) if not s.i_spent[i]) == 1
