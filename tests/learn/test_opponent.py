"""Reading the rival's Legends off what they have played.

The deduction is exact, so these tests are about arithmetic and about information hygiene rather
than about a model being roughly right. Every Legend in the set is 2 RAM and RAM counts only toward
its own colour, so a rival card of colour X and RAM r proves at least ceil(r / 2) Legends of colour
X — and with only three Legends, one colour's evidence is another colour's exclusion.
"""
import json
import sys
from pathlib import Path

import pytest
from conftest import Side, board

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cptcg.core.enums import Color  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.core.view import determinize  # noqa: E402
from cptcg.learn.opponent import (  # noqa: E402
    LEGEND_SLOTS, THREATS, colour_bounds, excluded_colours, legend_ram, max_ram, possible_pool,
    threat_pool,
)

GRAPH = Path("data/strategy/graph.json")


def test_every_legend_is_two_ram_or_the_deduction_is_invalid(pool):
    """The bound divides by this. A set that shipped a 3-RAM Legend would not break anything
    visibly — it would just make every bound wrong — so it raises instead."""
    assert legend_ram(pool) == 2


@pytest.mark.parametrize("bounds,expected", [
    ([0, 0, 0, 0], [6, 6, 6, 6]),        # nothing shown: any colour could still be all three
    ([0, 0, 1, 0], [4, 4, 6, 4]),        # one Blue proven: two slots left for anyone else
    ([0, 0, 2, 0], [2, 2, 6, 2]),        # two Blue: every other colour is capped at 2 RAM
    ([0, 0, 3, 0], [0, 0, 6, 0]),        # mono-Blue: every other colour is impossible
    ([1, 0, 2, 0], [2, 0, 4, 0]),        # slots all spoken for: Green and Yellow excluded
])
def test_the_slots_compete(bounds, expected):
    """One colour's evidence is another colour's cap. This is the half of the deduction that turns
    'they have shown two Blue' into 'a 3-RAM Red card is impossible' — not unlikely, impossible."""
    assert max_ram(bounds) == expected
    assert sum(bounds) <= LEGEND_SLOTS


def test_the_pool_shrinks_by_a_quarter_for_each_colour_ruled_out(pool):
    """The non-Legend pool is an even 31 cards per colour, 124 in all."""
    assert len(possible_pool(pool, [0, 0, 0, 0])) == 124
    assert len(possible_pool(pool, [0, 0, 3, 0])) == 31          # mono-Blue: exactly one quarter
    # Two Blue excludes no colour outright — a third Legend could still be any of them — so a pure
    # colour filter would cut nothing at all here. The RAM cap cuts 27 cards anyway, which is the
    # sharper half of the deduction and the half a colour filter cannot express.
    assert excluded_colours([0, 0, 2, 0]) == frozenset()
    assert len(possible_pool(pool, [0, 0, 2, 0])) == 97
    assert excluded_colours([0, 0, 3, 0]) == frozenset({Color.RED, Color.GREEN, Color.YELLOW})
    assert excluded_colours([0, 0, 0, 0]) == frozenset()


def test_a_played_card_proves_its_colour(reg):
    """A rival card on the board is public, so its colour and RAM are evidence.

    ``T-U8`` is Red at 4 RAM, which needs two Red Legends to be legal at all, so seeing one played
    proves two — and by the slot arithmetic it caps every other colour at a single Legend.
    """
    quiet = colour_bounds(board(reg, Side(), Side()), 0)
    assert quiet == [0, 0, 0, 0], "an empty board proves nothing"

    s = board(reg, Side(), Side(field=["T-U8"]))         # Red, 4 RAM
    bounds = colour_bounds(s, 0)
    assert bounds[int(Color.RED)] == 2
    assert sum(bounds) <= LEGEND_SLOTS
    assert max_ram(bounds)[int(Color.BLUE)] == 2         # one slot left, so 2 RAM at most

    s = board(reg, Side(), Side(field=["T-U6"]))         # Blue, 1 RAM
    assert colour_bounds(s, 0)[int(Color.BLUE)] == 1


def test_my_own_cards_are_not_evidence_about_the_rival(reg):
    """The bounds are about the seat across the table. A board where *I* have played every colour
    says nothing about what they are holding, and a version that read the wrong owner would sail
    through every other test in this file."""
    s = board(reg, Side(field=["T-U8", "T-U6"]), Side())
    assert colour_bounds(s, 0) == [0, 0, 0, 0]


def test_a_permuted_world_cannot_move_the_bounds(reg):
    """The hygiene property, and the reason this reads the public record rather than the state.

    ``determinize`` preserves the rival's true deck *multiset* — a sampled world knows their
    decklist, which is more than a person ever gets. If the bounds moved under permutation they
    would be reading that leak, and they would not generalise to an opponent whose deck the agent
    has never seen.
    """
    s = board(reg, Side(hand=["T-U4"], field=["T-U1"]), Side(field=["T-U3"], gig=[(6, 3)]))
    before = colour_bounds(s, 0)
    for seed in (1, 2, 3, 4, 5):
        w = determinize(s, 0, Pcg32(seed, seq=5))
        assert colour_bounds(w, 0) == before


def test_threats_are_counted_only_over_what_is_still_possible(pool):
    """The interaction map turns 'these cards are possible' into 'one of them beats this board'."""
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    open_board = threat_pool(pool, graph, [0, 0, 0, 0])
    mono_blue = threat_pool(pool, graph, [0, 0, 3, 0])
    mono_red = threat_pool(pool, graph, [3, 0, 0, 0])

    assert set(open_board) == set(THREATS)
    # Ruling out three colours can only ever reduce a count, never raise one.
    assert all(mono_blue[t] <= open_board[t] for t in THREATS)
    assert all(mono_red[t] <= open_board[t] for t in THREATS)
    # And it has to actually bite, or the pool filter is doing nothing.
    assert sum(mono_blue.values()) < sum(open_board.values())
    # Chrome Reverie is Blue, so a proven-Blue rival still threatens an attacker; a proven-Red one
    # cannot hold it at all. This is the worked example the module exists for.
    assert mono_blue["unit.spend_rival"] >= 1
    assert mono_red["unit.spend_rival"] == 0


def test_an_impossible_board_is_clamped_rather_than_fatal(reg):
    """A hand-built position need not be deck-legal, and a feature vector has to be total.

    The deduction rests on RAM limits, which are a *deck-building* rule — so in a real game the
    evidence can never demand a fourth Legend. ``learn/delayed.build_position`` places cards
    directly and is bound by no such rule, and the delayed suite holds a position whose rival board
    reads as ``[2, 1, 1, 0]``: four Legends' worth of proof. The first version raised, which killed
    an arena run mid-flight and taught the difference between an engine invariant and a feature.
    """
    s = board(reg, Side(), Side(field=["T-U8", "T-U6"], trash=["T-U5"]))
    bounds = colour_bounds(s, 0)
    assert sum(bounds) <= LEGEND_SLOTS, f"{bounds} needs more than {LEGEND_SLOTS} Legends"
    # Clamping is weakest-first, so the strongest claim survives: T-U8 is Red at 4 RAM.
    assert bounds[int(Color.RED)] == 2
