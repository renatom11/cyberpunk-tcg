"""Batch B02 confirmations — mod-family behaviour the audit suspected and found correct.

Three cases where reading one mod across the whole pool raised a question about a card, the test
was written, and the engine turned out to be right. They are kept because they are coverage the
pool did not have: each pins a reading that the next reader of these cards will otherwise have to
re-derive. Reasoning: `out/audit/b02/findings.md` §5.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conftest import Side, board, do, find                                   # noqa: E402
from cptcg.core.actions import Attack, EndTurn, GoSolo, Play, TakeGigDie     # noqa: E402
from cptcg.core.enums import Zone                                            # noqa: E402

E = 9


def test_chrome_fang_stops_a_rival_go_solo_legend_on_the_rivals_turn(pool):
    """Chrome Fang: 'PLAY: Until your next turn, rival Units can't steal friendly Gigs with value
    higher than their power.'

    Two questions at once. (1) Scope: `steps.stealable` applies `protect_gt_power` to any thief,
    while its sibling Westbrook Netrunner gates its own protection on the thief being a Legend —
    so does Chrome Fang over-reach when a Legend steals? No: the only way a Legend steals is by
    standing on the field, and ruling 015 says a GO SOLO Legend there "is a Unit now", so the
    unqualified read is the printed one. (2) Duration: 'until your next turn' has to survive the
    whole of the rival's turn, which is the only turn on which a rival can attack at all.

    Goro Takemura solos at power 7 and attacks the Gig area: the d6 showing 3 is fair game, the
    d10 showing 8 is not.
    """
    s = board(pool, Side(hand=["chrome-fang"], eddies=E, gig=[(10, 8), (6, 3)], deck=["floor-it"]),
              Side(legends=[("goro-takemura-hands-unclean", {"faceup": True})], eddies=E,
                   deck=["floor-it", "floor-it"]))
    do(s, Play(find(s, "chrome-fang", Zone.HAND)))
    do(s, EndTurn())
    do(s, TakeGigDie(4))                                  # the rival's start-of-turn Gig roll
    goro = find(s, "goro-takemura-hands-unclean")
    do(s, GoSolo(goro))
    assert goro in s.units(1)                             # ruling 015: it is a Unit now
    do(s, Attack(goro))                                   # power 7: one steal, one legal die
    assert s.gig[0] == [(10, 8)]                          # the over-power Gig stayed home
    assert (6, 3) in s.gig[1]


def test_maxtac_suppression_team_beats_adrenaline(pool):
    """MaxTac Suppression Team: 'Rival Units can't attack the turn they're played.'

    ADRENALINE prints the opposite permission ('This Unit can attack the turn it's played'), and
    `legal.attack_permission` checks the suppression before it checks ADRENALINE or any
    `attack_units_now` grant. The prohibition winning is the reading this set uses elsewhere, and
    the second half of the test shows the same Unit attacking freely with MaxTac off the board —
    so the first half is about MaxTac, not about Lag.
    """
    def kusanagi_turn(with_maxtac):
        s = board(pool, Side(field=(["maxtac-suppression-team"] if with_maxtac else []),
                             gig=[(6, 3)], deck=["floor-it"]),
                  Side(hand=["modded-kusanagi"], eddies=E, gig=[(6, 3)],
                       deck=["floor-it", "floor-it"]), active=1)
        do(s, Play(find(s, "modded-kusanagi", Zone.HAND, 1)))
        return s, find(s, "modded-kusanagi")

    s, k = kusanagi_turn(True)
    assert Attack(k) not in s.pending.options
    s, k = kusanagi_turn(False)
    assert Attack(k) in s.pending.options


def test_chrome_reverie_still_offers_the_free_call_with_no_rival_unit(pool):
    """Chrome Reverie: 'A rival Unit can't attack until your next turn. If you control a min Gig,
    you may Call a Legend for free.'

    Two sentences with two separate conditions: the second must not be hostage to the first. With
    the rival controlling no Unit at all the first sentence has nothing to name, and the free Call
    is still offered on the strength of the d4 showing 1.
    """
    s = board(pool, Side(hand=["chrome-reverie"], eddies=E, gig=[(4, 1)],
                         legends=["goro-takemura-hands-unclean"]), Side())
    do(s, Play(find(s, "chrome-reverie", Zone.HAND)))
    assert s.pending is not None and s.pending.prompt == "Call a Legend for free?"
    goro = find(s, "goro-takemura-hands-unclean")
    do(s, s.pending.options[0])                           # accept the free Call
    assert s.i_faceup[goro] == 1 and len(s.zone(0, Zone.EDDIES)) == E   # free: nothing was spent
