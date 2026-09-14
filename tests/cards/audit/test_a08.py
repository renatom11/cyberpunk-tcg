"""Batch A08 audit — Gear with ATTACK / DEFEATED triggers (fire for the host).

Cards: dying-night-vs-pistol, kiroshi-optics, the-relic-experimental-biochip.
Every test here asserts printed card text (data/cards/wnc.json), not engine behaviour.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conftest import Side, board, do, find, options            # noqa: E402
from cptcg.core.actions import Attack, EndTurn, Play, Target    # noqa: E402
from cptcg.core.enums import Zone                               # noqa: E402
from cptcg.core.ops import available                            # noqa: E402

TARGET_UNIT = 0


# --------------------------------------------------------------- kiroshi-optics
@pytest.mark.xfail(strict=True, reason="AUD-kiroshi-optics-1: text allows equipping to any Unit (incl. rival); legal.gear_hosts offers friendly Units only")
def test_kiroshi_optics_may_equip_to_any_unit(pool):
    """'(Equip to a Unit or friendly face-up Legend.)' — 'a Unit' is unqualified, unlike the
    other 9 Gear in the set, which all read '(Equip to a friendly Unit or face-up Legend.)'."""
    s = board(pool, Side(hand=["kiroshi-optics"], field=["psycho-squad"], eddies=9),
              Side(field=["corpo-security"]))
    k = find(s, "kiroshi-optics")
    mine = find(s, "psycho-squad", Zone.FIELD, 0)
    theirs = find(s, "corpo-security", Zone.FIELD, 1)
    opts = options(s)
    assert Play(k, mine) in opts                       # friendly Unit: offered
    assert Play(k, theirs) in opts                     # rival Unit: the card text allows it


def test_kiroshi_optics_looks_at_a_friendly_face_down_legend(pool):
    """ATTACK: Look at a friendly face-down Legend."""
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["kiroshi-optics"]})],
                         legends=["padre-man-of-the-cross", "wakako-okada-peace-and-harmony",
                                  "muamar-reyes-el-capitan"]),
              Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "psycho-squad")))
    do(s, __import__("cptcg.core.actions", fromlist=["Pick"]).Pick((1,)))
    assert s.i_known[s.legends(0)[1]] & 1               # p0 has seen it
    assert not (s.i_known[s.legends(0)[1]] & 2)         # and the rival has not


# ---------------------------------------------------------- dying-night-vs-pistol
@pytest.mark.xfail(strict=True, reason="AUD-dying-night-vs-pistol-1: readies 2 Eddies for a face-up Legend host named V, but the text says 'this Unit'")
def test_dying_night_ready_2_only_when_the_host_is_a_unit(pool):
    """'At the end of your turn, if this Unit is named "V", ready 2 Eddies.'
    A face-up Legend in the Legends area is not a Unit (cf. zetatech-faceplate, which spells
    out 'this Unit or Legend' when it means both)."""
    s = board(pool, Side(legends=[("v-streetkid", {"faceup": True,
                                                   "gear": ["dying-night-vs-pistol"]}),
                                  "padre-man-of-the-cross", "wakako-okada-peace-and-harmony"],
                         eddies=2, spent_eddies=2, deck=["floor-it"]),
              Side(deck=["floor-it", "floor-it"]))
    assert available(s, 0) == 3                        # 0 ready Eddies + 3 payable Legends
    do(s, EndTurn())
    assert available(s, 0) == 3                        # the host is a Legend, not a Unit


def test_dying_night_attack_decreases_a_gig_by_up_to_2(pool):
    """ATTACK: Decrease a Gig by up to 2 — either player's Gig ('a friendly Gig' is how this
    set says friendly, cf. jackie-welles-pour-one-out-for-me)."""
    s = board(pool, Side(field=[("v-roamer-of-the-badlands", {"gear": ["dying-night-vs-pistol"]})],
                         gig=[(8, 5)], deck=["floor-it"]),
              Side(gig=[(6, 3)], deck=["floor-it"]))
    do(s, Attack(find(s, "v-roamer-of-the-badlands")))
    picks = {tuple(o.picks) for o in s.pending.options}
    # 2 own-die amounts + 2 rival-die amounts + decline
    assert len(picks) == 5


# ------------------------------------------------- the-relic-experimental-biochip
@pytest.mark.xfail(strict=True, reason="AUD-the-relic-experimental-biochip-1: 'Then, bottom-deck this Unit' is skipped when the trash holds no eligible Unit")
def test_the_relic_bottom_decks_the_host_with_no_unit_to_recur(pool):
    """'Play another Unit with cost 9 or less from your trash for free. Then, bottom-deck this
    Unit.' With nothing to play the first sentence does nothing; the second still happens."""
    s = board(pool, Side(field=["animals-wrecker"]),
              Side(field=[("corpo-security", {"spent": True,
                                              "gear": ["the-relic-experimental-biochip"]})],
                   trash=[], deck=["floor-it"]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Target(TARGET_UNIT, find(s, "corpo-security")))
    assert s.i_zone[find(s, "corpo-security")] == Zone.DECK


def test_the_relic_cannot_recur_its_own_host(pool):
    """'another Unit' excludes the Unit this Gear was equipped to."""
    s = board(pool, Side(field=["animals-wrecker"]),
              Side(field=[("corpo-security", {"spent": True,
                                              "gear": ["the-relic-experimental-biochip"]})],
                   trash=["psycho-squad"], deck=["floor-it"]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Target(TARGET_UNIT, find(s, "corpo-security")))
    assert s.i_zone[find(s, "psycho-squad")] == Zone.FIELD
    assert s.i_zone[find(s, "corpo-security")] == Zone.DECK
