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
    assert set(d["perturbations"]) == {"+gig", "-gig", "+ready", "-unit", "+die", "-die"}
    assert d["counted"] == ["+gig", "-gig", "+ready", "-unit"] and d["reported_only"] == ["+die", "-die"]
    assert 0.0 <= d["overall_violation_rate"] <= 1.0
    assert d["perturbations"]["+ready"]["n"] <= 6


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


@pytest.mark.skipif(not SAMPLE.exists(), reason="no bootstrap sample")
def test_perturbations_conserve_the_dice():
    """Every perturbation is a state a game can reach: the dice of the game are conserved. The
    first version added a die to the Gig area while the fixer kept it, and the card-aware head
    answered that impossible state with a 22% violation rate the legal version does not show."""
    import monotonicity as M
    from cptcg.cards.registry import load_default
    reg = load_default()
    positions = M.sample_positions(reg, str(SAMPLE), 12, 3)
    assert positions
    for s in positions:
        me = s.pending.player
        before = M.dice_multiset(s)
        for kind, _ in M.COUNTED + M.REPORTED:
            c = M.perturb(s, me, kind)
            if c is None:
                continue
            assert M.dice_multiset(c) == before, (kind, before, M.dice_multiset(c))
            assert c.pending is None
