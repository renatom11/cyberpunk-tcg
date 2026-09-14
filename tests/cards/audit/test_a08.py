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
def test_kiroshi_optics_equips_friendly_only_like_every_other_gear(pool):
    """Withdrawn: AUD-kiroshi-optics-1 was a false positive, and this is what it leaves behind.

    The finding read Kiroshi's "(Equip to a Unit or friendly face-up Legend.)" as unqualified,
    since the other nine Gear print "(Equip to a **friendly** Unit or face-up Legend.)". Killed on
    the parse: taking "friendly" as conjunct-local here, but as distributing on the other nine,
    is inconsistent — and the conjunct-local reading would also let those nine equip a *rival*
    face-up Legend, which nobody filed and nobody believes. docs/rules.md fixes the template as
    "a friendly Unit or Legend", and seven Gear print no equip line at all yet host identically,
    so the parenthetical is reminder text. Reminder text nowhere in this set grants an exception.

    The residue is a transcription doubt, not a script defect: Kiroshi's word order differs from
    every sibling, which is what a slip looks like. Settling it needs the card face, so it is
    recorded in data/COVERAGE.md rather than guessed at here.
    """
    s = board(pool, Side(hand=["kiroshi-optics"], field=["psycho-squad"], eddies=9),
              Side(field=["corpo-security"]))
    k = find(s, "kiroshi-optics")
    mine = find(s, "psycho-squad", Zone.FIELD, 0)
    theirs = find(s, "corpo-security", Zone.FIELD, 1)
    opts = options(s)
    assert Play(k, mine) in opts, "a friendly Unit is a legal host"
    assert Play(k, theirs) not in opts, "a rival Unit is not, here or on any other Gear"


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

