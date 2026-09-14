"""Batch A08 — the cards the audit suspected and the engine got right.

The audit reads a card, forms an expectation, and writes the test. When the test *passes*, the
finding dies and something else survives: a scenario the pool did not previously have, paid for out
of the audit. The plan calls this class S-SUSPICION and calls it the most dangerous to act on — an
agent that "knows" a card is wrong and cannot make it fail will reach for the engine next — which is
exactly why it is worth writing the passing test down instead of discarding it.

Kept in a ``test_confirmed_*`` file rather than beside the findings so that "this is how it behaves"
and "this is how it should behave" never sit unlabelled in the same directory;
``tests/cards/test_audit_shape.py`` enforces the split.

Cards: kiroshi-optics, dying-night-vs-pistol, the-relic-experimental-biochip.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conftest import Side, board, do, find                       # noqa: E402
from cptcg.core.actions import Attack, Pick, Target              # noqa: E402
from cptcg.core.enums import TARGET_UNIT, Zone                   # noqa: E402
from cptcg.core.view import knows_identity                       # noqa: E402


def test_kiroshi_optics_looks_at_a_friendly_face_down_legend(pool):
    """'ATTACK: Look at a friendly face-down Legend.'

    "Look at" is one-sided: the controller learns the identity and the rival does not. Asserted
    through ``view.knows_identity``, which is the same question the redaction layer asks when it
    decides what each seat may see — rather than through the ``i_known`` bitmask, which is an
    engine internal and would make this test unreviewable against the card.
    """
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["kiroshi-optics"]})],
                         legends=["padre-man-of-the-cross", "wakako-okada-peace-and-harmony",
                                  "muamar-reyes-el-capitan"]),
              Side(gig=[(4, 1)]))
    looked = s.legends(0)[1]
    assert not knows_identity(s, 0, looked) and not knows_identity(s, 1, looked)
    do(s, Attack(find(s, "psycho-squad")))
    do(s, Pick((1,)))
    assert knows_identity(s, 0, looked), "the controller looked and did not learn it"
    assert not knows_identity(s, 1, looked), "the rival learned a card nobody showed them"


def test_dying_night_attack_decreases_either_players_gig_by_up_to_2(pool):
    """'ATTACK: Decrease a Gig by up to 2.'

    Unqualified "a Gig" means either player's. This set says *friendly* when it means friendly —
    Jackie Welles — Pour One Out For Me reads "decrease a friendly Gig by up to 2" with the same
    verb and the same number — so the absence of the word here is the card speaking, not an
    omission. One d8 and one d6, two legal amounts each, plus the decline the "up to" implies.
    """
    s = board(pool, Side(field=[("v-roamer-of-the-badlands", {"gear": ["dying-night-vs-pistol"]})],
                         gig=[(8, 5)], deck=["floor-it"]),
              Side(gig=[(6, 3)], deck=["floor-it"]))
    do(s, Attack(find(s, "v-roamer-of-the-badlands")))
    picks = {tuple(o.picks) for o in s.pending.options}
    assert len(picks) == 5 and () in picks


def test_the_relic_cannot_recur_its_own_host(pool):
    """'DEFEATED: Play another Unit with cost 9 or less from your trash for free. Then, bottom-deck
    this Unit.'

    "Another" excludes the Unit this Gear was equipped to — which matters because that Unit is on
    its way to the trash as this resolves, and a reading that let it pick itself would make the
    Gear a repeatable loop rather than a one-shot.
    """
    s = board(pool, Side(field=["animals-wrecker"]),
              Side(field=[("corpo-security", {"spent": True,
                                              "gear": ["the-relic-experimental-biochip"]})],
                   trash=["psycho-squad"], deck=["floor-it"]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Target(TARGET_UNIT, find(s, "corpo-security")))
    assert s.i_zone[find(s, "psycho-squad")] == Zone.FIELD   # the other Unit came back
    assert s.i_zone[find(s, "corpo-security")] == Zone.DECK  # the host went to the deck, not back
