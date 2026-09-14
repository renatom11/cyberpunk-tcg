"""Batch A01 — Programs: removal, card flow, tempo (part 1/3).

Audit of src/cptcg/cards/sets/wnc.py lines 16-95 against the printed text in data/cards/wnc.json.
Every test here asserts a printed-text outcome only (zones, hand size), never script internals.
"""
import pytest
from conftest import Side, board, find

from cptcg.core.actions import Play
from cptcg.core.enums import Zone

E = 9  # plenty of eddies


def play(s, cid):
    from conftest import do
    do(s, Play(find(s, cid, Zone.HAND)))
    return s


@pytest.mark.xfail(strict=True, reason="AUD-memory-relapse-1: the even-Street-Cred draw is nested in the spend's continuation, so it never happens when the rival has no Unit to spend")
def test_memory_relapse_draws_on_even_cred_with_no_rival_units(pool):
    """'Spend a rival Unit. It can't ready until your next turn. If your * (Street Cred) is an
    even number, draw 1.' — the draw is its own sentence: it does not depend on a Unit being
    there to spend. Street Cred here is 4 (even)."""
    s = board(pool, Side(hand=["memory-relapse"], eddies=E, gig=[(6, 4)], deck=["floor-it"]),
              Side(field=[], deck=["floor-it"]))
    play(s, "memory-relapse")
    assert len(s.zone(0, Zone.HAND)) == 1


def test_bonnie_and_clyde_defeat_is_not_optional(pool):
    """'Defeat a rival Unit with power 4 or less. You may defeat 2 instead if a Rival controls at
    least 2 Gigs more than you.' — the 'may' buys the second Unit only; defeating one is
    mandatory. With equal Gigs and exactly one legal target there is nothing to decide."""
    s = board(pool, Side(hand=["bonnie-and-clyde"], eddies=E),
              Side(field=["corpo-security"]))
    play(s, "bonnie-and-clyde")
    assert s.i_zone[find(s, "corpo-security")] == Zone.TRASH


@pytest.mark.xfail(strict=True, reason="AUD-unlikely-bond-1: the friendly bottom-deck is scripted optional=True, but the card prints no 'may'")
def test_unlikely_bond_first_bottom_deck_is_not_optional(pool):
    """'Bottom-deck a ready friendly Unit. If you do, bottom-deck a spent rival Unit.' — no
    printed 'may' (every other card in the set prints 'You may X. If you do, ...'), so with one
    ready friendly Unit on the board the bottom-deck happens without asking."""
    s = board(pool, Side(hand=["unlikely-bond"], eddies=E, field=["psycho-squad"]),
              Side(field=[("corpo-security", {"spent": True})]))
    play(s, "unlikely-bond")
    assert s.i_zone[find(s, "psycho-squad")] == Zone.DECK
    assert s.i_zone[find(s, "corpo-security")] == Zone.DECK
