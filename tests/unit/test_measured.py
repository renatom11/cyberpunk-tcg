"""The published measurement: well formed, about real cards, and honest about being stale.

``data/strategy/measured.json`` is the first thing this project has put on the website that is a
*number about the game* rather than a description of it, and the card guide renders it directly
beside the hand-written notes. That makes two failure modes worth a test. A malformed or mislabelled
row would show a confident percentage about a card that does not exist. And a run that predates a
card fix would show rates measured under behaviour the engine no longer has — which is precisely
what the cards digest was introduced to make visible, so it has to actually be checked somewhere.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import cards_digest, load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402

PATH = ROOT / "data" / "strategy" / "measured.json"

pytestmark = pytest.mark.skipif(not PATH.exists(), reason="no measurement run in this checkout")


@pytest.fixture(scope="module")
def data():
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_every_row_is_a_real_card_with_coherent_counts(data):
    reg = load_default()
    ids = {d.id for d in reg.defs}
    for cid, m in data["cards"].items():
        assert cid in ids, f"{cid} is not a card in the pool"
        d = reg.get(cid)
        assert m["drawn"] >= 0 and m["played"] >= 0
        for key in ("gih", "gip", "play_rate"):
            if m[key] is not None:
                assert 0.0 <= m[key] <= 1.0, f"{cid}: {key} is {m[key]}"
        if m["iwd"] is not None:
            assert -1.0 <= m["iwd"] <= 1.0
        if d.is_legend:
            # A Legend is never drawn, so it has play counters and nothing else. This is the whole
            # reason the file exists: before play was instrumented these rows could not have existed.
            assert m["drawn"] == 0 and m["gih"] is None and m["iwd"] is None
        else:
            assert m["played"] <= m["drawn"], f"{cid}: played {m['played']} of {m['drawn']} draws"


def test_it_records_what_game_it_was_measured_on(data):
    assert data["rules"] and data["cards_digest"], "a rate with no provenance is not a measurement"
    assert data["games"] > 0 and data["agent"]
    assert data["note"], "the note is what stops a conditional rate being read as a power ranking"


def test_the_page_is_told_when_the_measurement_is_stale(data):
    """Not an assertion that it *is* current — a card fix legitimately makes it stale, and failing
    the suite for that would make the fix phase fight this file. What must hold is that the guide
    finds out: the API computes staleness from the digests, and the panel says so.
    """
    from cptcg.web import backend
    _, links = backend.dispatch("GET", "/api/cardlinks", {}, None)
    assert "measured_stale" in links
    assert links["measured_stale"] == (data["cards_digest"] != cards_digest())
    if links["measured_stale"]:
        pytest.skip(f"measurement predates the current cards ({data['cards_digest']} vs "
                    f"{cards_digest()}) — the guide says so; re-run tools/playtest.py")
    assert data["rules"] == DEFAULT_CONFIG.digest()
