"""What an agent *name* can carry, and what it refuses to carry.

The arena and the harvester both build their agents inside worker processes, so anything the
parent wants to configure has to travel inside the name string. Three things do: ``cheat:``,
``@weights`` and now ``:iterations``. They compose, and the order they are peeled off in matters —
a weights path may contain a colon, so the budget must be split off *after* the path is removed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cptcg.agents.base import BUDGET_SEP, CHEAT_PREFIX, WEIGHTS_SEP, make_agent  # noqa: E402


def test_a_searching_agent_takes_an_iteration_budget_from_its_name():
    assert make_agent("ismcts:32").iterations == 32
    assert make_agent("ismcts-explore:7").iterations == 7


def test_the_default_budget_is_left_alone_when_none_is_given():
    plain = make_agent("ismcts")
    assert plain.iterations == type(plain).iterations


def test_budget_composes_with_weights_and_with_cheating():
    a = make_agent(f"{CHEAT_PREFIX}ismcts{BUDGET_SEP}64{WEIGHTS_SEP}some/where/weights.json")
    assert a.iterations == 64
    assert a.weights_path == "some/where/weights.json"
    assert a.cheating is True


def test_a_windows_style_weights_path_is_not_mistaken_for_a_budget():
    """The weights split happens first, so a colon inside the path never reaches the budget parse.

    Without that ordering ``ismcts@C:/x/weights.json`` would try to read ``/x/weights.json`` as a
    number of iterations, and the failure would be a confusing error on a path that is fine.
    """
    a = make_agent(f"ismcts{WEIGHTS_SEP}C:/x/weights.json")
    assert a.weights_path == "C:/x/weights.json"
    assert a.iterations == type(a).iterations


def test_the_budget_is_an_instance_attribute_so_one_spec_cannot_change_another():
    make_agent("ismcts:3")
    assert make_agent("ismcts").iterations == 200


@pytest.mark.parametrize("spec, wanted", [
    ("heuristic:32", "does not search"),
    ("random:8", "does not search"),
    ("ismcts:0", "at least 1"),
    ("ismcts:-4", "at least 1"),
    ("ismcts:many", "not a whole number"),
    ("ismcts:", "no number after it"),
    ("ismcts@", "no path after it"),
])
def test_a_budget_that_means_nothing_is_refused_with_a_reason(spec, wanted):
    """Silently ignoring a budget is the failure mode that matters: a nine-hour generation would
    run at the default 200 and be twenty times slower than the operator believed."""
    with pytest.raises((ValueError, KeyError)) as e:
        make_agent(spec)
    assert wanted in str(e.value)
