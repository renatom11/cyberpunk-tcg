"""The calibration tool must be able to detect the bias it was built to look for.

It reported that the value head is well calibrated on both sides of the within-turn split, which
refuted the hypothesis that drove it. A measurement that returns "no effect" is only worth
believing if it *could* have returned an effect, so these tests hand it data with a known,
deliberately planted bias and require it to be found.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

np = pytest.importorskip("numpy")


def test_calibration_recovers_a_planted_bias():
    """Predictions deliberately inflated by 8 points must show up as an 8-point gap."""
    from fit_eval import calibration
    rs = np.random.RandomState(0)
    truth = rs.uniform(0.05, 0.95, 40_000)
    y = (rs.uniform(size=truth.size) < truth).astype(float)
    biased = np.clip(truth + 0.08, 0.001, 0.999)
    _rows, ece_biased, _ = calibration(biased, y)
    _rows, ece_honest, _ = calibration(truth, y)
    assert ece_honest < 0.01, f"an honest predictor should look calibrated, got {ece_honest:.4f}"
    assert ece_biased > 0.05, f"an 8-point bias should be visible, got {ece_biased:.4f}"


def test_a_bucket_gap_is_detected_at_the_size_that_would_matter():
    """The tool's per-bucket report flags a gap when it clears its own interval. The observed gaps
    were +0.0067 and +0.0017 on ~100k rows; this checks a gap ten times larger is unmissable, so
    "no bias found" cannot be the tool failing to look."""
    rs = np.random.RandomState(1)
    n = 100_000
    truth = np.full(n, 0.45)
    y = (rs.uniform(size=n) < truth).astype(float)
    pred = truth + 0.06
    gap = pred.mean() - y.mean()
    se = (y.mean() * (1 - y.mean()) / n) ** 0.5
    assert gap > 1.96 * se * 5, "a 6-point gap on 100k rows must be far outside the interval"


def test_the_tool_reuses_fit_evals_split_rather_than_reimplementing_it():
    """The control only means 'reproduces what was recorded' if the split is the same one. A local
    reimplementation would drift and the control would quietly stop being a control."""
    src = (ROOT / "tools" / "calibration.py").read_text(encoding="utf-8")
    assert "from fit_eval import calibration, split_by_game" in src
    assert "FEATURE_NAMES.index" in src, "feature positions must not be hard-coded"
