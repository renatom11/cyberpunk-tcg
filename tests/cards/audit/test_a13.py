"""Batch A13 audit — Legends (part 1/2), ``src/cptcg/cards/sets/wnc.py`` lines 1133-1256.

Cards: v-streetkid, wakako-okada-peace-and-harmony, dexter-deshawn-off-the-grid,
padre-man-of-the-cross, muamar-reyes-el-capitan, viktor-vektor-sit-down-and-relax,
dum-dum-maelstrom-triggerman, river-ward-detective-on-the-hunt,
kerry-eurodyne-axe-attitude-audience, evelyn-parker-beautiful-enigma,
hanako-arasaka-daughter-of-the-emperor.

Every test asserts printed card text (``data/cards/wnc.json``), never a script internal.
Unmarked tests are controls: they pin the half of each card that is already right, so the
xfail next to them is measuring the clause named in its reason and nothing else.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conftest import Side, board, defeat_now, do, during_main, find     # noqa: E402
from cptcg.core.actions import Activate, Attack, Pick                   # noqa: E402
from cptcg.core.enums import Zone                                       # noqa: E402
from cptcg.core.ops import gain_gig                                     # noqa: E402


class _Rolls:
    """A scripted stand-in for the engine RNG, so a die result is stated rather than seed-hunted."""

    def __init__(self, seq):
        self.seq = list(seq)

    def die(self, sides):
        return self.seq.pop(0)

    def below(self, n):
        return 0

    def shuffle(self, lst):
        pass

    def copy(self):
        return _Rolls(self.seq)


def _ready_eddies(s, p):
    return sum(1 for i in s.zone(p, Zone.EDDIES) if not s.i_spent[i])


# ----------------------------------------------------------------- evelyn-parker
def test_evelyn_readies_an_eddie_when_a_ganger_steals(pool):
    """Control for the finding below. 'When a friendly CORPO or GANGER Unit steals 1 or more
    Gigs, ready 1 Eddie.' Animals Wrecker is a GANGER; one die in the rival Gig area, so it
    steals exactly one and one Eddie readies."""
    s = board(pool, Side(legends=[("evelyn-parker-beautiful-enigma", {"faceup": True})],
                         field=["animals-wrecker"], eddies=4, spent_eddies=4),
              Side(gig=[(4, 1)]))
    assert _ready_eddies(s, 0) == 0
    do(s, Attack(find(s, "animals-wrecker")))
    assert s.gig[1] == [] and s.gig[0] == [(4, 1)]
    assert _ready_eddies(s, 0) == 1


def test_evelyn_readies_one_eddie_for_a_multi_die_steal(pool):
    """'When a friendly CORPO or GANGER Unit steals 1 or more Gigs, ready 1 Eddie.'

    Animals Wrecker is a GANGER with power 10, so one attack on the Gig area steals two dice
    (``ops.steal_count`` is ``1 + power // 10``). 'steals 1 or more Gigs' is one trigger for the
    whole steal — that phrase is there precisely to make the count irrelevant — so exactly one
    Eddie readies, not one per die.

    Fixed: AUD-evelyn-parker-beautiful-enigma-1.
    """
    s = board(pool, Side(legends=[("evelyn-parker-beautiful-enigma", {"faceup": True})],
                         field=["animals-wrecker"], eddies=4, spent_eddies=4),
              Side(gig=[(4, 1), (4, 2)]))
    assert _ready_eddies(s, 0) == 0
    do(s, Attack(find(s, "animals-wrecker")))
    assert s.gig[1] == [] and len(s.gig[0]) == 2         # both dice taken in the one attack
    assert _ready_eddies(s, 0) == 1


# ---------------------------------------------------------------- kerry-eurodyne
def test_kerry_draws_on_a_minimum_the_reroll_is_declined_on(pool):
    """Control. 'When you roll a min or max value on a Gig, draw 1.' The d6 shows a 1, the
    reroll is declined, so that 1 is the Gig's value: one card."""
    s = board(pool, Side(legends=[("kerry-eurodyne-axe-attitude-audience", {"faceup": True})],
                         deck=["floor-it"] * 6, fixer=[6]), Side())
    s.rng = _Rolls([1])
    during_main(s, lambda st: gain_gig(st, 0, 6))
    do(s, Pick(()))                                      # no: the 1 stands
    assert s.gig[0] == [(6, 1)]
    assert len(s.zone(0, Zone.HAND)) == 1


def test_kerry_draws_nothing_for_a_result_that_was_ignored(pool):
    """'When you roll in a Gig from your fixer area, you may ignore the result and reroll it
    once. When you roll a min or max value on a Gig, draw 1.'

    The d6 shows a 1; the reroll is taken and lands on 3. The 1 was *ignored* — the Gig never
    holds it — and the 3 is neither min nor max, so nothing is drawn. (The script's own comment,
    'if declined, the original roll stands: check min/max on it', reads the card the same way;
    its guard for that, ``has_mod("rerolled", ...)``, is never set anywhere in ``src``.)

    Fixed: AUD-kerry-eurodyne-axe-attitude-audience-1.
    """
    s = board(pool, Side(legends=[("kerry-eurodyne-axe-attitude-audience", {"faceup": True})],
                         deck=["floor-it"] * 6, fixer=[6]), Side())
    s.rng = _Rolls([1, 3])
    during_main(s, lambda st: gain_gig(st, 0, 6))
    do(s, Pick((0,)))                                    # yes: ignore the 1 and reroll
    assert s.gig[0] == [(6, 3)]
    assert len(s.zone(0, Zone.HAND)) == 0


# ------------------------------------------------------------------- river-ward
def test_river_ward_searches_when_an_equipped_unit_dies(pool):
    """Control. 'When a friendly equipped Unit is defeated, search the top 2 cards of your deck
    and trash 1.' One card in the deck, so the search has a single answer and resolves itself."""
    s = board(pool, Side(legends=[("river-ward-detective-on-the-hunt", {"faceup": True})],
                         field=[("psycho-squad", {"gear": ["mantis-blades"]})],
                         deck=["animals-wrecker"]), Side())
    defeat_now(s, find(s, "psycho-squad", Zone.FIELD, 0))
    assert s.i_zone[find(s, "animals-wrecker")] == Zone.TRASH


@pytest.mark.xfail(strict=True, reason="AUD-river-ward-detective-on-the-hunt-1: the trigger tests CardType.UNIT, so an equipped Legend on the field — a Unit by ruling 015 — never fires it")
def test_river_ward_searches_when_an_equipped_legend_on_the_field_dies(pool):
    """A Legend on the field has been played as a Unit: ruling 027 ('play it as a ready Unit')
    and ruling 015 ('it is a Unit now' — which is why it stops being spendable as an Eddie).
    ``GameState.units`` lists it, attacks target it as a Unit, and it fights as one. So an
    equipped V *Streetkid* dying on the field is 'a friendly equipped Unit is defeated' and
    River Ward should search.
    """
    s = board(pool, Side(legends=[("river-ward-detective-on-the-hunt", {"faceup": True})],
                         field=[("v-streetkid", {"faceup": True, "gear": ["mantis-blades"]})],
                         deck=["animals-wrecker"]), Side())
    defeat_now(s, find(s, "v-streetkid", Zone.FIELD, 0))
    assert s.i_zone[find(s, "animals-wrecker")] == Zone.TRASH


# ----------------------------------------------------------------- muamar-reyes
def test_wakako_up_to_2_may_be_declined(pool):
    """Control, and the contrast that makes the finding below readable.
    '⊡: Decrease a Gig by up to 2.' 'Up to' includes zero, so a decline belongs on the menu."""
    s = board(pool, Side(legends=[("wakako-okada-peace-and-harmony", {"faceup": True})],
                         gig=[(6, 3)]), Side())
    do(s, Activate(find(s, "wakako-okada-peace-and-harmony"), 0))
    assert Pick(()) in s.pending.options
    do(s, Pick(()))
    assert s.gig[0] == [(6, 3)]                          # declining is a legal answer here


def test_muamar_adjust_a_gig_by_1_is_not_optional(pool):
    """'⊡: Adjust a Gig by 1.' Muamar is the only adjust effect in the pool that omits 'up to':
    afterparty-at-lizzies, dexter-deshawn-one-last-chance and zetatech-faceplate all print 'up
    to 1', and the two Legends either side of Muamar in this very file print 'up to 2'. Once
    this ability is activated a die moves by 1; there is no do-nothing answer.

    Fixed: AUD-muamar-reyes-el-capitan-1.
    """
    s = board(pool, Side(legends=[("muamar-reyes-el-capitan", {"faceup": True})], gig=[(6, 3)]),
              Side())
    do(s, Activate(find(s, "muamar-reyes-el-capitan"), 0))
    assert Pick(()) not in s.pending.options             # the 3 must become a 2 or a 4
