"""The belief log-likelihood instrument: finite, above the uniform baseline on real games, and
never assigning zero probability to a truth (the colour bounds are sound)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
SAMPLE = ROOT / "data" / "experience" / "bootstrap-sample.jsonl.gz"


@pytest.mark.skipif(not SAMPLE.exists(), reason="no bootstrap sample")
def test_belief_beats_uniform_and_never_rules_out_the_truth(tmp_path):
    import belief_ll as B
    out = tmp_path / "b.json"
    B.main([str(SAMPLE), "--games", "4", "--every", "15", "--out", str(out)])
    d = json.loads(out.read_text())
    assert d["games"] == 4 and d["hidden_cards_scored"] > 0
    assert d["zero_probability_truths"] == 0
    assert d["gain_nats_per_card"] > 0.0
    assert d["gain_ci95"][0] <= d["gain_nats_per_card"] <= d["gain_ci95"][1]
