"""The oracle set: sampled boards survive a round trip, labels are win probabilities, and the
agreement statistic is a rank correlation with an interval."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import oracle as O  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import legal_actions  # noqa: E402
from cptcg.learn.delayed import build_position  # noqa: E402

SAMPLE = ROOT / "data" / "experience" / "bootstrap-sample.jsonl.gz"


@pytest.mark.skipif(not SAMPLE.exists(), reason="no bootstrap sample")
def test_sample_label_and_agree_round_trip(tmp_path, monkeypatch):
    out = tmp_path / "oracle.json"
    O.main(["sample", str(SAMPLE), "--n", "4", "--seed", "3", "--out", str(out)])
    data = json.loads(out.read_text())
    assert data["rules"] == DEFAULT_CONFIG.digest() and len(data["positions"]) == 4
    reg = load_default()
    for p in data["positions"]:
        s = build_position(reg, p["spec"], DEFAULT_CONFIG)
        legal_actions(s)
        assert s.pending.player == p["mover"] and len(s.pending.options) > 1
    O.main(["label", str(out), "--budget", "4", "--plan", "plan-deep:2", "--workers", "1"])
    data = json.loads(out.read_text())
    for p in data["positions"]:
        lab = p["labels"]
        assert 0.0 <= lab["cheat_value"] <= 1.0
        assert lab["plan_score"] is None or isinstance(lab["plan_score"], float)
    O.main(["agree", str(out), "--out", str(tmp_path / "agree.json")])
    ag = json.loads((tmp_path / "agree.json").read_text())
    assert ag["positions"] == 4 and -1.0 <= ag["spearman_vs_cheat"] <= 1.0
    assert 0.0 <= ag["brier_vs_cheat"] <= 1.0


def test_spearman_handles_ties_and_perfect_order():
    assert abs(O._spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-12
    assert abs(O._spearman([1, 2, 3, 4], [40, 30, 20, 10]) + 1.0) < 1e-12
    assert abs(O._spearman([1, 1, 2, 2], [1, 1, 2, 2]) - 1.0) < 1e-12


@pytest.mark.skipif(not SAMPLE.exists(), reason="no bootstrap sample")
def test_playout_labels_are_independent_of_any_head(tmp_path):
    out = tmp_path / "oracle.json"
    O.main(["sample", str(SAMPLE), "--n", "3", "--seed", "5", "--out", str(out)])
    O.main(["playouts", str(out), "--n", "4", "--workers", "1"])
    data = json.loads(out.read_text())
    assert data["playout_labels"]["playouts"] == 4
    for p in data["positions"]:
        po = p["playout"]
        assert 0.0 <= po["playout_value"] <= 1.0 and po["playouts"] == 4
        assert abs((po["half_a"] + po["half_b"]) / 2 - po["playout_value"]) < 1e-9
    O.main(["agree", str(out), "--independent", "--out", str(tmp_path / "ag.json")])
    ag = json.loads((tmp_path / "ag.json").read_text())
    assert ag["label"].startswith("heuristic playouts") and ag["positions"] == len(data["positions"]) >= 1
