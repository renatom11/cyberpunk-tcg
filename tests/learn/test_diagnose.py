"""The representation diagnostic must be able to fail, and must not lie about duplicates.

``tools/diagnose_features.py`` was written to test a hypothesis — that gen-1 sits at the ceiling of
what 114 aggregate features can express, so the winning move in the positions the agent fails should
be *indistinguishable* from the losing moves. The diagnostic refuted it: solved and unsolved
positions separate identically. Keeping it honest matters more than keeping it, so these tests pin
the two ways it lied or could lie.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from cptcg.learn.model import WEIGHTS_PATH  # noqa: E402

pytestmark = pytest.mark.skipif(not (ROOT / "out/learn/gen-001/weights.json").exists(),
                                reason="gen-1 weights are not in this checkout")


@pytest.fixture(scope="module")
def rows():
    import diagnose_features
    return diagnose_features.run("ismcts", "out/learn/gen-001/weights.json")


#: The four the gen-1 agent solved when this diagnostic was written and the suite was eight
#: positions. It is a fixed historical set, not a live score: the suite has grown since, and
#: re-measuring which positions the agent solves is the arena's job, not this file's.
SOLVED = {"gear-before-the-raid", "sell-to-afford-the-raid", "mined-23767-79",
          "mined-166302-115"}


def _suite_size() -> int:
    import json
    suite = json.loads((ROOT / "data/arena/delayed.json").read_text(encoding="utf-8"))
    return len(suite["positions"])


def test_it_covers_every_verified_position(rows):
    """Both kinds — hand-built board specs and mined replay prefixes. The first version read
    ``entry["spec"]`` and silently skipped the five replay positions, which would have drawn a
    conclusion from three.

    Counted against the suite file rather than a literal, because the suite grows: a hard-coded
    eight turns every future position added into a failing test here, which trains whoever adds
    one to edit this number instead of asking whether the diagnostic still covers everything.
    """
    assert len(rows) == _suite_size(), [r["id"] for r in rows]


def test_duplicate_copies_of_a_card_are_deduped_like_the_search_does(rows):
    """``ismcts._root_actions`` collapses options that differ only in *which copy* of a card they
    name, so a diagnostic that does not is measuring options the agent never sees separately.

    Before this, three of four reported "the winning move is feature-identical to another option"
    findings were two copies of the same card — true, correct, and not a failure of anything. The
    surviving genuine case is ``sell-to-afford-the-raid``: selling Mandibular Upgrade versus Mantis
    Blades, two *different* cards, identical feature vectors, because the hand is described only in
    aggregate and both are 1-cost Gear.
    """
    exact = [r["id"] for r in rows if r["nearest"] == 0.0]
    assert exact == ["sell-to-afford-the-raid"], (
        f"expected exactly one genuine feature collision, got {exact}. More than one usually means "
        f"the dedup regressed and same-card copies are being counted as collisions.")


def test_the_control_can_distinguish_the_two_groups_if_there_is_anything_to_distinguish(rows):
    """The diagnostic's own control. Solved and unsolved positions must be *measured*, not assumed,
    and both groups must be non-empty and produce finite numbers — otherwise the comparison at the
    bottom of the report means nothing.

    Deliberately not asserting a direction: the hypothesis predicted the unsolved group would show
    less separation, and it did not (median ratio 0.25 vs 0.24). Pinning the prediction here would
    have turned a refutation into a failing test.
    """
    solved = [r for r in rows if r["id"] in SOLVED]
    unsolved = [r for r in rows if r["id"] not in SOLVED]
    assert len(solved) == len(SOLVED), [r["id"] for r in solved]
    assert len(unsolved) == len(rows) - len(SOLVED) and unsolved
    for r in rows:
        assert r["ratio"] >= 0.0 and r["options"] > 1
        assert 1 <= r["value_rank"] <= r["options"]
