"""Who decides which €$ get spent.

Ruling 025 auto-pays, because making payment an engine decision multiplies the search branching
factor for almost no strategic content. A person at a table does choose, though, so ``ops.PAY_PREF``
lets an interactive front end say. These tests pin the two halves of that bargain: the override does
what it says, and nothing inside the engine ever reaches for it.
"""

import pytest

from cptcg.core import ops
from cptcg.core.enums import NZONE, Zone
from tests.conftest import Side, board


@pytest.fixture(autouse=True)
def _clean():
    """Never leak a preference into another test: it is process-global by design."""
    ops.PAY_PREF = None
    yield
    ops.PAY_PREF = None


def eddies(s, p):
    return list(s.z[p * NZONE + Zone.EDDIES])


def test_without_a_preference_the_engine_pays_from_eddies_first(pool):
    s = board(pool, Side(eddies=3, legends=["goro-takemura-hands-unclean"]), Side(), active=0)
    ops.pay(s, 0, 2)
    assert [bool(s.i_spent[i]) for i in eddies(s, 0)] == [True, True, False]
    assert not any(s.i_spent[i] for i in s.legends(0))


def test_a_preference_spends_exactly_what_was_chosen(pool):
    s = board(pool, Side(eddies=3, legends=["goro-takemura-hands-unclean"]), Side(), active=0)
    third = eddies(s, 0)[2]
    leg = s.legends(0)[0]
    ops.PAY_PREF = (id(s), 0, (leg, third))
    ops.pay(s, 0, 2)
    assert bool(s.i_spent[leg]) and bool(s.i_spent[third])
    assert [bool(s.i_spent[i]) for i in eddies(s, 0)] == [False, False, True]


def test_a_short_preference_is_topped_up_in_the_usual_order(pool):
    """An under-filled choice still pays rather than raising; the rest keeps its default order."""
    s = board(pool, Side(eddies=3), Side(), active=0)
    third = eddies(s, 0)[2]
    ops.PAY_PREF = (id(s), 0, (third,))
    ops.pay(s, 0, 2)
    assert [bool(s.i_spent[i]) for i in eddies(s, 0)] == [True, False, True]


def test_a_preference_naming_something_unspendable_is_ignored(pool):
    s = board(pool, Side(eddies=2), Side(), active=0)
    mine = eddies(s, 0)
    s.i_spent[mine[0]] = 1                       # already spent: not a legal source any more
    ops.PAY_PREF = (id(s), 0, (mine[0],))
    ops.pay(s, 0, 1)
    assert [bool(s.i_spent[i]) for i in mine] == [True, True]


def test_a_preference_does_not_reach_another_players_payment(pool):
    s = board(pool, Side(eddies=2), Side(eddies=2), active=0)
    ops.PAY_PREF = (id(s), 0, (eddies(s, 0)[1],))
    ops.pay(s, 1, 1)
    assert [bool(s.i_spent[i]) for i in eddies(s, 1)] == [True, False]


def test_a_preference_does_not_reach_another_game(pool):
    """The token carries the state's identity, so a sibling thread's choice cannot cross over."""
    a = board(pool, Side(eddies=3), Side(), active=0)
    b = board(pool, Side(eddies=3), Side(), active=0)
    ops.PAY_PREF = (id(a), 0, (eddies(a, 0)[2],))
    ops.pay(b, 0, 1)
    assert [bool(s) for s in (b.i_spent[i] for i in eddies(b, 0))] == [True, False, False]


def test_the_engine_itself_never_sets_a_preference():
    """A grep, deliberately: the override exists for front ends, and a rollout that quietly picked
    its own payment order would make simulated games disagree with the golden replays."""
    import pathlib
    root = pathlib.Path(ops.__file__).resolve().parents[1]
    writers = []
    for path in sorted(root.rglob("*.py")):
        if path.parts[len(root.parts)] == "web":      # the web client is the front end this is for
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("PAY_PREF =", "ops.PAY_PREF =")) and "None" not in stripped:
                writers.append(f"{path.relative_to(root)}:{n}")
    assert writers == [], f"only a front end may set PAY_PREF, but {writers} does"
