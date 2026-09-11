"""No name a player may not know may appear anywhere in the view they are sent.

This file exists because a spot check did not catch a real leak. ``test_web`` asserted the rival's
hand came back as ``None``, which was true, while the payment picker was listing the player's own
**face-down Legends by name** — a fact the rules withhold even from their controller, who learns a
slot's identity only by Calling it or by an effect that looks at it.

So the test is not a list of fields. It walks real games, asks ``core.view.knows_identity`` which
instances a seat may identify, and searches the whole serialised view for the name of anything it
may not. A new field that leaks fails here without anyone remembering to add it.
"""

import json

import pytest

from cptcg.agents.base import make_agent
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import Pcg32
from cptcg.core.view import knows_identity
from cptcg.learn.decks import sample_pair
from cptcg.web.view import view_state


def forbidden_names(s, me: int) -> set[str]:
    """Names this seat must not be shown.

    A name is only forbidden when **no** instance carrying it is knowable: the same card can sit
    face-down in a Legend slot and face-up in the trash, and the trash copy makes the name public.
    Subtracting the knowable set is what keeps this from failing on a legitimate duplicate.
    """
    hidden, known = set(), set()
    for inst in range(len(s.i_card)):
        (known if knows_identity(s, me, inst) else hidden).add(s.card(inst).name)
    return hidden - known


def walk(pool, seed: int, turns: int):
    """Play a real game, yielding each seat's view at every decision."""
    decks = sample_pair(pool, Pcg32(seed))
    s = new_game(pool, decks, seed)
    agents = [make_agent("heuristic", seed * 2 + i) for i in (0, 1)]
    for p, a in enumerate(agents):
        a.new_game(seed, p)
    for _ in range(turns):
        if s.over:
            break
        legal_actions(s)
        ch = s.pending
        for me in (0, 1):
            yield s, me, view_state(s, me, ("P0", "P1"), [])
        apply(s, agents[ch.player].act(s, ch))


@pytest.mark.parametrize("seed", [3, 11, 29])
def test_no_view_names_a_card_the_seat_may_not_identify(pool, seed):
    for s, me, v in walk(pool, seed, 90):
        blob = json.dumps(v)
        leaked = sorted(n for n in forbidden_names(s, me) if n and f'"{n}"' in blob)
        assert not leaked, (
            f"seat {me} was sent {leaked} on turn {s.turn}; "
            f"knows_identity says it may not read them")


def test_a_face_down_legend_is_anonymous_in_its_own_controllers_pay_sources(pool):
    """The exact leak, pinned: the picker offered 'LEGEND (face-down) - Viktor Vektor'."""
    saw_face_down = False
    for s, me, v in walk(pool, 11, 120):
        for src in v["players"][me]["pay_sources"] or ():
            if src["where"] != "Legend" or src["faceup"]:
                continue
            if knows_identity(s, me, src["inst"]):
                continue
            saw_face_down = True
            assert src["name"] is None, src
            assert 0 <= src["slot"] < 3, src        # still pickable: the slot is on the table
    assert saw_face_down, "no face-down Legend was ever a payment source, so nothing was tested"


def test_the_omniscient_view_still_sees_everything(pool):
    """``perspective=None`` is the replay/debug view and must NOT be redacted, or WATCH goes blank."""
    for s, _, _ in walk(pool, 7, 12):
        v = view_state(s, None, ("P0", "P1"), [])
        assert v["players"][0]["hand"] is not None and v["players"][1]["hand"] is not None
        break
