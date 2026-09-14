"""The sixth instance, found by the detector rather than by reading.

Four of batch A04's findings and one of A01's are the same bug wearing five different card names:
a card prints two sentences, the second is a separate state-based clause, and the script implements
it *inside the continuation* of the first — so declining the first sentence, or having no legal way
to perform it, silently skips the second.

That is the Chrome Reverie question answered yes: the error is mechanically detectable from printed
text across the whole pool. The detector is
``tests/cards/test_script_lints.py::test_a_state_based_tail_clause_is_not_trapped_in_a_continuation``,
and running it over all 151 cards turned up one card no auditor had been assigned. This is its
scenario test.
"""
import pytest
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, Pick
from cptcg.core.enums import Zone


@pytest.mark.xfail(strict=True, reason="AUD-zetatech-faceplate-1: the draw is nested in the adjust continuation, so declining the 'up to 1' skips the separate different-values draw clause")
def test_zetatech_faceplate_draws_when_the_adjust_is_declined(pool):
    """'... adjust a Gig by up to 1. Then, if you control 3 or more Gigs with different values,
    draw 1.'

    Three friendly Gigs already show 1, 2 and 7 — three different values before anything moves.
    'Up to 1' includes 0 and the engine offers the decline explicitly; 'Then' sequences the two
    sentences, it does not make the draw conditional on a die having moved. Compare the passing
    ``tests/cards/test_statics.py::test_zetatech_faceplate_on_spend``, which takes the adjust and
    therefore never exercises this path.
    """
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["zetatech-faceplate"]})],
                         gig=[(4, 1), (6, 2), (10, 7)], deck=["floor-it"]),
              Side(gig=[(8, 3)]))
    do(s, Attack(find(s, "psycho-squad")))
    do(s, Pick(()))                                          # decline: adjust by 0
    assert s.gig[0] == [(4, 1), (6, 2), (10, 7)]             # nothing moved
    assert len(s.zone(0, Zone.HAND)) == 1                    # ... and the draw still happens
