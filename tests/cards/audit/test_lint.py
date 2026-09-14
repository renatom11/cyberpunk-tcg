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
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, Pick, Target
from cptcg.core.enums import TARGET_UNIT, Zone


def test_zetatech_faceplate_draws_when_the_adjust_is_declined(pool):
    """'... adjust a Gig by up to 1. Then, if you control 3 or more Gigs with different values,
    draw 1.'

    Three friendly Gigs already show 1, 2 and 7 — three different values before anything moves.
    'Up to 1' includes 0 and the engine offers the decline explicitly; 'Then' sequences the two
    sentences, it does not make the draw conditional on a die having moved. Compare the passing
    ``tests/cards/test_statics.py::test_zetatech_faceplate_on_spend``, which takes the adjust and
    therefore never exercises this path.

    Fixed: AUD-zetatech-faceplate-1.
    """
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["zetatech-faceplate"]})],
                         gig=[(4, 1), (6, 2), (10, 7)], deck=["floor-it"]),
              Side(gig=[(8, 3)], field=[("corpo-security", {"spent": True})]))
    do(s, Attack(find(s, "psycho-squad")))
    do(s, Target(TARGET_UNIT, find(s, "corpo-security", Zone.FIELD, 1)))
    do(s, Pick(()))                                          # decline: adjust by 0
    # Attacking a Unit rather than the Gig area on purpose. An attack on the Gig area *steals*, and
    # an earlier version of this test asserted the Gig area was unchanged and so failed on the
    # steal rather than on the missing draw. A strict xfail proves a test fails; it does not prove
    # it fails for the reason in its reason string, and that is the one thing the marker cannot
    # check for you.
    assert s.gig[0] == [(4, 1), (6, 2), (10, 7)], "nothing moved"
    assert len(s.zone(0, Zone.HAND)) == 1, "and the draw still happens"
