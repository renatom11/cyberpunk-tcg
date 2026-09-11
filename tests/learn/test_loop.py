"""The generational loop's rules: the ledger, the opponent pool, promotion, and the drift check.

None of these play a game. They are the decisions the loop makes *around* the games, which is
exactly the part that has to be right before a run is worth 35 hours of compute.
"""
import json

import pytest

from cptcg.agents.base import WEIGHTS_SEP, make_agent
from cptcg.learn import loop
from cptcg.learn.loop import (
    ANCHOR, FLOOR, SCHEDULE, GateResult, GenerationRecord, Ledger, decide, drift_report,
    opponent_schedule, pick_past,
)


# ------------------------------------------------------------------ the ledger
def test_ledger_round_trips_and_names_the_incumbent(tmp_path):
    led = Ledger(tmp_path)
    assert led.best() is None and led.next_n() == 0
    led.add(GenerationRecord(n=0, seed=1, status="rejected"))
    led.add(GenerationRecord(n=1, seed=2, status="promoted", weights="w1.json"))
    led.add(GenerationRecord(n=2, seed=3, status="rejected"))
    assert led.next_n() == 3

    again = Ledger(tmp_path)
    assert [g.n for g in again.gens] == [0, 1, 2]
    assert again.best().n == 1                      # the newest *promoted* one, not the newest
    assert again.unfinished() is None


def test_ledger_finds_the_generation_an_interrupt_left_behind(tmp_path):
    led = Ledger(tmp_path)
    led.add(GenerationRecord(n=0, seed=1, status="promoted", weights="w.json"))
    led.add(GenerationRecord(n=1, seed=2, status="fitting"))
    assert Ledger(tmp_path).unfinished().n == 1


def test_a_torn_write_cannot_corrupt_the_history(tmp_path):
    """The ledger is written beside and renamed, so an interrupt leaves the old file intact."""
    led = Ledger(tmp_path)
    led.add(GenerationRecord(n=0, seed=1, status="promoted", weights="w.json"))
    before = led.path.read_text(encoding="utf-8")
    (tmp_path / "ledger.json.tmp").write_text("{ this is half a write", encoding="utf-8")
    assert led.path.read_text(encoding="utf-8") == before
    assert Ledger(tmp_path).best().n == 0


# -------------------------------------------------------------- the opponent pool
def test_the_schedule_spends_every_game_and_keeps_the_pool_wide():
    plan = opponent_schedule(1000, past=3)
    assert sum(plan.values()) == 1000
    assert set(plan) == {"self", "past", ANCHOR, FLOOR}
    assert plan["self"] > plan["past"] > plan[ANCHOR] > plan[FLOOR]
    # the whole point: self-play is the majority and is nowhere near all of it
    assert 0.5 < plan["self"] / 1000 < 0.75


def test_with_no_ancestors_the_past_share_folds_into_self_play():
    plan = opponent_schedule(1000, past=0)
    assert "past" not in plan
    assert sum(plan.values()) == 1000
    assert plan["self"] == 1000 - plan[ANCHOR] - plan[FLOOR]


def test_the_schedule_is_the_written_down_one():
    """If these proportions change it should be a visible act, not a drift."""
    assert dict(SCHEDULE)["self"] == 0.60
    assert sum(w for _, w in SCHEDULE) == pytest.approx(1.0)


def test_picking_an_ancestor_is_a_pure_function_of_seed_and_index():
    gens = [GenerationRecord(n=i, seed=0) for i in range(5)]
    a = [pick_past(gens, 99, i).n for i in range(40)]
    b = [pick_past(gens, 99, i).n for i in range(40)]
    assert a == b                                   # reproducible, and reachable without the ones before
    assert len(set(a)) > 1                          # and it actually varies
    assert pick_past([], 99, 0) is None


# -------------------------------------------------------------------- promotion
def _gate(**kw) -> GateResult:
    base = dict(sprt="high", win_rate=58.0, pairing_lo=53.0, panel=76.0, panel_incumbent=75.0,
                delayed=4, delayed_incumbent=4)
    base.update(kw)
    return GateResult(**base)


def test_a_candidate_that_wins_everywhere_is_promoted():
    ok, why = decide(_gate())
    assert ok and "58.0%" in why


def test_losing_the_head_to_head_ends_it():
    ok, why = decide(_gate(sprt="low", win_rate=44.0))
    assert not ok and "did not beat the incumbent" in why


def test_a_win_that_does_not_clear_the_deck_population_band_is_not_a_win():
    ok, why = decide(_gate(pairing_lo=48.0))
    assert not ok and "even money" in why


def test_beating_the_incumbent_while_regressing_against_the_frozen_anchor_is_rejected():
    """The drift signature: the pair of them moved together and away from something fixed."""
    ok, why = decide(_gate(panel=70.0, panel_incumbent=76.0))
    assert not ok and "drift" in why


def test_a_small_panel_wobble_is_tolerated():
    ok, _ = decide(_gate(panel=73.5, panel_incumbent=76.0))
    assert ok                                        # 2.5 points is inside the stated tolerance


def test_solving_fewer_verified_positions_is_ability_lost():
    ok, why = decide(_gate(delayed=2, delayed_incumbent=4))
    assert not ok and "verified" in why


def test_solving_more_is_fine():
    ok, _ = decide(_gate(delayed=6, delayed_incumbent=4))
    assert ok


# ----------------------------------------------------------------------- drift
def test_a_straight_ladder_passes():
    ok, bad = drift_report({1: 70.0, 2: 65.0, 3: 58.0})
    assert ok and bad == []


def test_losing_to_an_ancestor_is_reported():
    ok, bad = drift_report({1: 47.0, 2: 65.0, 3: 58.0})
    assert not ok and any("ancestor" in b for b in bad)


def test_a_rock_paper_scissors_inversion_is_reported():
    """Beating an *older* generation by less than a newer one: the ladder has become a circle."""
    ok, bad = drift_report({1: 55.0, 2: 66.0})
    assert not ok and any("straight line" in b for b in bad)


# ------------------------------------------------- pointing an agent at a generation
def test_an_agent_name_can_carry_which_weights_it_plays_with():
    a = make_agent(f"ismcts{WEIGHTS_SEP}src/cptcg/agents/weights.json", 3)
    assert a.name == "ismcts" and str(a.weights_path).endswith("weights.json")
    assert a.model.hidden > 0                        # and it actually loads them


def test_cheating_and_weights_compose():
    a = make_agent(f"cheat:ismcts{WEIGHTS_SEP}src/cptcg/agents/weights.json", 3)
    assert a.cheating and str(a.weights_path).endswith("weights.json")


def test_an_agent_with_no_weights_refuses_the_suffix():
    with pytest.raises(ValueError, match="no weights"):
        make_agent(f"heuristic{WEIGHTS_SEP}anywhere.json")


def test_the_explorer_is_the_generator_and_differs_only_in_exploration():
    """The two settings that must never be swapped: noisy games make better data and a worse
    measurement."""
    quiet = make_agent("ismcts", 1)
    noisy = make_agent("ismcts-explore", 1)
    assert quiet.root_noise_alpha == 0.0 and quiet.temperature == 0.0
    assert noisy.root_noise_alpha > 0.0 and noisy.temperature > 0.0
    for k in ("iterations", "c_puct", "prior_temp", "max_depth", "prior_settle"):
        assert getattr(quiet, k) == getattr(noisy, k), k


def test_root_noise_moves_the_prior_without_leaving_a_distribution():
    a = make_agent("ismcts-explore", 5)
    prior = {"x": 0.7, "y": 0.2, "z": 0.1}
    out = a._with_root_noise(prior)
    assert set(out) == set(prior)
    assert sum(out.values()) == pytest.approx(1.0)
    assert out != prior
    # a single-option prior has nothing to explore, and must come back untouched
    assert a._with_root_noise({"only": 1.0}) == {"only": 1.0}


def test_the_noise_is_reproducible_from_the_agents_seed():
    p = {"x": 0.5, "y": 0.3, "z": 0.2}
    one = make_agent("ismcts-explore", 11)._with_root_noise(p)
    two = make_agent("ismcts-explore", 11)._with_root_noise(p)
    assert one == two


# ---------------------------------------------------------------- the seed corpus in the window
def test_a_generation_with_no_data_of_its_own_keeps_the_seed():
    """The case that matters: generation 1 has just been harvested and is being fitted for the
    first time. Without the seed it is fitted on its own games alone, which is what produced a 10%
    gate score at generation 0 on 6,900 rows against an incumbent fitted on 1,453,992."""
    assert loop.seed_in_window(1_453_992, 0)


def test_the_seed_retires_once_self_play_outweighs_it():
    seed = 1_000
    assert loop.seed_in_window(seed, int(loop.SEED_RETIRE_RATIO * seed) - 1)
    assert not loop.seed_in_window(seed, int(loop.SEED_RETIRE_RATIO * seed))
    assert not loop.seed_in_window(seed, 10 * seed)


def test_no_seed_corpus_means_no_seed_in_the_window():
    """A run started without one must not claim to have kept something it never had."""
    assert not loop.seed_in_window(0, 0)
    assert not loop.seed_in_window(0, 5_000)


def test_the_ratio_is_a_knob_and_the_rule_follows_it():
    assert loop.seed_in_window(100, 500, ratio=10.0)
    assert not loop.seed_in_window(100, 500, ratio=2.0)
