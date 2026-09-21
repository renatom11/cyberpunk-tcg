"""The remaining Stage 0 instruments run end to end on the bootstrap sample and give numbers of
the right shape: monotonicity (violation rates in [0, 1]) and plan regret (a finite regret and
a share in [0, 1])."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
SAMPLE = ROOT / "data" / "experience" / "bootstrap-sample.jsonl.gz"


@pytest.mark.skipif(not SAMPLE.exists(), reason="no bootstrap sample")
def test_monotonicity_reports_rates_per_perturbation(tmp_path):
    import monotonicity as M
    out = tmp_path / "m.json"
    M.main([str(SAMPLE), "--positions", "6", "--out", str(out)])
    d = json.loads(out.read_text())
    assert d["positions"] == 6
    assert set(d["perturbations"]) == {"+gig", "-gig", "+ready", "-unit"}
    assert 0.0 <= d["overall_violation_rate"] <= 1.0
    assert d["perturbations"]["+gig"]["n"] == 6


@pytest.mark.skipif(not SAMPLE.exists(), reason="no bootstrap sample")
def test_plan_regret_scores_both_turns(tmp_path):
    import plan_regret as P
    out = tmp_path / "p.json"
    P.main([str(SAMPLE), "--turns", "2", "--search", "ismcts:2", "--plan", "plan-deep:2", "--workers", "1",
            "--out", str(out)])
    d = json.loads(out.read_text())
    assert d["turns"] == 2
    assert -1.0 <= d["mean_regret"] <= 1.0
    assert 0.0 <= d["search_at_least_plan"] <= 1.0
    assert d["seconds_per_turn"]["search"] > 0 and d["seconds_per_turn"]["plan"] > 0
