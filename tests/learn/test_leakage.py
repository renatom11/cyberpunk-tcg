"""The leakage instrument: the rival's reading of a seat only sharpens as evidence accumulates."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import leakage as L  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402

SAMPLE = ROOT / "data" / "experience" / "bootstrap-sample.jsonl.gz"


@pytest.mark.skipif(not SAMPLE.exists(), reason="no bootstrap sample")
def test_pool_never_grows_and_the_proven_turn_is_consistent():
    reg = load_default()
    for gi, rec in enumerate(read_games(SAMPLE)):
        if gi == 4:
            break
        r = L.game_readings(reg, rec)
        for seat in (0, 1):
            pools = [p for p, _ in r[seat]["turns"]]
            assert pools, "every seat takes at least one turn"
            assert all(b <= a for a, b in zip(pools, pools[1:])), pools
            assert all(0 <= p <= 124 for p in pools)
            proven = r[seat]["proven"]
            assert proven is None or 1 <= proven <= len(pools)
