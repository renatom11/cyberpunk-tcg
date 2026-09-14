"""Batch A04 — Programs: Gig manipulation.

Audit of src/cptcg/cards/sets/wnc.py lines 337-367 (afterparty-at-lizzies, industrial-assembly,
trust-no-one, peace-offering) against the printed text in data/cards/wnc.json.
Every test here asserts a printed-text outcome only (gig values, hand size), never internals.
"""
import pytest
from conftest import Side, board, do, find

from cptcg.core.actions import Pick, Play
from cptcg.core.enums import Zone

E = 9  # plenty of eddies


def play(s, cid):
    do(s, Play(find(s, cid, Zone.HAND)))
    return s


@pytest.mark.xfail(strict=True, reason="AUD-afterparty-at-lizzies-1: the draw is nested in the adjust continuation, so declining the 'up to 1' (or having no legal adjustment) skips the separate different-values draw clause")
def test_afterparty_draws_when_the_adjust_is_declined(pool):
    """'Adjust a Gig by up to 1. If you control 2 or more Gigs with different values, draw 1.'
    'Up to 1' includes 0 — the engine itself offers a decline option. The second sentence is a
    separate, state-based clause: two Gigs showing 3 and 4 are two Gigs with different values
    whether or not a die was moved."""
    s = board(pool, Side(hand=["afterparty-at-lizzies"], eddies=E, gig=[(6, 3), (8, 4)],
                         deck=["floor-it"]), Side())
    play(s, "afterparty-at-lizzies")
    do(s, Pick(()))                                          # decline: adjust by 0
    assert s.gig[0] == [(6, 3), (8, 4)]                      # nothing moved
    assert len(s.zone(0, Zone.HAND)) == 1                    # ... and the draw still happens


@pytest.mark.xfail(strict=True, reason="AUD-industrial-assembly-1: the draw is nested in the adjust continuation, so when no increase is legal the separate 8+-value draw clause never runs")
def test_industrial_assembly_draws_when_no_gig_can_be_increased(pool):
    """'Increase a Gig by up to 4. If you control a Gig with 8+ value, draw 1.' The only Gig in
    play is a d10 already showing 10, so no increase is legal (CR 6.4.4 / ruling 037) and the
    first sentence simply does nothing. The d10 still has value 10, so the second sentence —
    its own sentence, with its own condition — is satisfied."""
    s = board(pool, Side(hand=["industrial-assembly"], eddies=E, gig=[(10, 10)],
                         deck=["floor-it"]), Side())
    play(s, "industrial-assembly")
    assert s.gig[0] == [(10, 10)]
    assert len(s.zone(0, Zone.HAND)) == 1


@pytest.mark.xfail(strict=True, reason="AUD-trust-no-one-1: the draw is nested in the adjust continuation, so when no decrease is legal the separate min-Gig draw clause never runs")
def test_trust_no_one_draws_when_no_gig_can_be_decreased(pool):
    """'Decrease a Gig by up to 3. Then, if you control a min Gig, draw 1.' The only Gig is a d4
    already showing its minimum face, so no decrease is legal; 'Then' sequences the clauses, it
    does not make the draw conditional on a die having moved. A min Gig is controlled."""
    s = board(pool, Side(hand=["trust-no-one"], eddies=E, gig=[(4, 1)], deck=["floor-it"]),
              Side())
    play(s, "trust-no-one")
    assert s.gig[0] == [(4, 1)]
    assert len(s.zone(0, Zone.HAND)) == 1


@pytest.mark.xfail(strict=True, reason="AUD-peace-offering-1: the draw is nested inside the optional set, so declining the 'may' skips the separate value-pair draw clause")
def test_peace_offering_draws_when_the_set_is_declined(pool):
    """'You may set a Gig's value to the value of another Gig. Then, if you control a
    value-pair, draw 1.' The 'may' covers the set only. Declining it leaves the two d-values at
    2 and 2 — a value-pair the player already controls — so the second sentence still draws."""
    s = board(pool, Side(hand=["peace-offering"], eddies=E, gig=[(6, 2), (8, 2)],
                         deck=["floor-it"]), Side())
    play(s, "peace-offering")
    do(s, Pick(()))                                          # decline the optional set
    assert s.gig[0] == [(6, 2), (8, 2)]
    assert len(s.zone(0, Zone.HAND)) == 1
