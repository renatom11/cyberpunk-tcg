"""Game budgets as (min, max) ranges and the Tracker that keeps them honest while a job runs."""
import pytest

from cptcg.cards.registry import load_default
from cptcg.deck.builder import league
from cptcg.sim.budget import (Tracker, climb_budget, climb_step_budget, generate_budget, league_budget, pairs,
                              tourney_budget)


@pytest.fixture(scope="module")
def reg():
    return load_default()


# ---------------------------------------------------------------- budgets
def test_tourney_budget_is_one_batch_to_the_cap_per_pair():
    assert pairs(4) == 6
    assert tourney_budget(4, 200) == (6 * 40, 6 * 200)
    assert tourney_budget(4, 20) == (6 * 20, 6 * 20)            # a cap below one batch: nothing to save
    assert tourney_budget(4, 200, sprt=False) == (6 * 200, 6 * 200)
    assert tourney_budget(1, 200) == (0, 0)


def test_climb_step_budget_counts_both_seats_and_the_field():
    g = 2 * 20 * 5                                                # one batch: 20 seeds, 2 seats, 5 opponents
    assert climb_step_budget(5, first=True) == (2 * g, 2 * 3 * g)     # champion and challenger both play
    assert climb_step_budget(5) == (g, (2 * 3 - 1) * g)               # champion's first batch is cached
    lo, hi = climb_budget(5, 4)
    assert lo == 2 * g + 3 * g and hi == 6 * g + 3 * 5 * g
    assert climb_budget(5, 0) == (0, 0)


def test_league_budget_adds_climbs_and_round_robins_per_generation():
    lo, hi = league_budget(6, 3, 5, 60)
    c_lo, c_hi = climb_budget(5, 5)
    t_lo, t_hi = tourney_budget(6, 60)
    assert (lo, hi) == (3 * (6 * c_lo + t_lo), 3 * (6 * c_hi + t_hi))
    assert lo <= hi
    # two hall-of-fame opponents widen every builder's field
    assert league_budget(6, 3, 5, 60, field=7)[1] > hi
    assert generate_budget(24, 10, 4) == (960, 960)
    assert generate_budget(24, 0, 4) == (0, 0)


# ---------------------------------------------------------------- tracker: tournament
def test_tracker_tourney_shrinks_max_as_cells_settle():
    t = Tracker.for_tourney(3, 200)
    assert t.to_json() == {"phase": "starting", "step": 0, "steps": 3, "unit": "matchups", "done": 0,
                           "remaining_min": 120, "remaining_max": 600}
    # an unsettled cell after its first batch: one more batch at least, the rest of the cap at most
    t.cell("a", "b", 40, "continue")
    assert (t.done, t.remaining_min, t.remaining_max) == (40, 40 + 40 + 40, 160 + 200 + 200)
    assert t.step == 0
    # the same cell settles at 80 games: its remaining games vanish, the counter moves
    t.cell("a", "b", 80, "high")
    assert (t.done, t.remaining_min, t.remaining_max, t.step) == (80, 80, 400, 1)
    # a cell that runs to the cap without a verdict is settled too
    t.cell("a", "c", 200, "continue")
    assert (t.remaining_min, t.remaining_max, t.step) == (40, 200, 2)
    t.cell("b", "c", 40, "low")
    assert (t.remaining_min, t.remaining_max, t.step, t.done) == (0, 0, 3, 320)


def test_tracker_max_never_grows_over_a_simulated_tournament():
    t = Tracker.for_tourney(4, 120)
    maxes = [t.remaining_max]
    for a, b in (("a", "b"), ("a", "c"), ("a", "d"), ("b", "c"), ("b", "d"), ("c", "d")):
        for n in (40, 80, 120):
            t.cell(a, b, n, "continue")
            maxes.append(t.remaining_max)
            assert t.remaining_min <= t.remaining_max
    assert all(x >= y for x, y in zip(maxes, maxes[1:]))
    assert t.remaining_max == 0 and t.step == t.steps == 6 and t.done == 720


# ---------------------------------------------------------------- tracker: league
def test_tracker_league_rebudgets_a_wider_field_and_settles_skipped_steps():
    t = Tracker.for_league(3, 2, 2, 20)                             # field assumed: 2 other builders
    lo, hi = league_budget(3, 2, 2, 20)
    assert (t.remaining_min, t.remaining_max, t.steps) == (lo, hi, 2 * (3 * 2 + 3))
    # the hall of fame lends two champions: this builder's steps cost more than budgeted
    t.climb_start("builder1", field=4, steps=2, gen=1)
    grow = sum(a for a, _ in (climb_step_budget(4, first=True), climb_step_budget(4))) - \
        sum(a for a, _ in (climb_step_budget(2, first=True), climb_step_budget(2)))
    assert t.remaining_min == lo + grow and t.remaining_max > hi
    # one step played, one skipped (no legal swap): climb_done settles it at zero games
    t.climb_step("builder1", 1, 320, gen=1)
    assert t.step == 1 and t.done == 320
    t.climb_done("builder1", gen=1)
    assert t.step == 2
    # the other builders keep the assumed field
    for name in ("builder2", "builder3"):
        t.climb_start(name, field=2, steps=2, gen=1)
        t.climb_step(name, 1, 160, gen=1)
        t.climb_step(name, 2, 80, gen=1)
        t.climb_done(name, gen=1)
    assert t.step == 6
    for a, b in (("builder1", "builder2"), ("builder1", "builder3"), ("builder2", "builder3")):
        t.cell(a, b, 20, "continue", 20, gen=1)
    t.gen_done(1)
    assert t.step == 9
    # exactly the second generation's budget remains
    lo2, hi2 = league_budget(3, 1, 2, 20)
    assert (t.remaining_min, t.remaining_max) == (lo2, hi2)
    t.finish("done")
    assert t.to_json()["remaining_max"] == 0 and t.step == t.steps and t.phase == "done"


def test_tracker_generate_counts_decks_built_and_screened():
    t = Tracker.for_generate(3, 2, 4)
    assert (t.steps, t.remaining_min, t.remaining_max, t.unit) == (6, 24, 24, "decks")
    t.built(1); t.built(2); t.built(3)
    assert t.step == 3 and t.remaining_max == 24
    t.screened(1)
    assert (t.step, t.done, t.remaining_max) == (4, 8, 16)
    t.screened(2); t.screened(3)
    assert (t.step, t.done, t.remaining_min, t.remaining_max) == (6, 24, 0, 0)
    assert Tracker.for_generate(3, 0, 4).steps == 3               # no screen: nothing to screen


def test_league_events_drive_a_tracker_to_zero(reg, tmp_path):
    """The events league() emits account for every unit the budget planned: fed to a Tracker
    built from the same parameters, the run ends with nothing remaining and every step counted."""
    n_b, gens, steps, cap = 2, 1, 2, 2
    t = Tracker.for_league(n_b, gens, steps, cap, seeds_per_batch=2, max_batches=1)
    kinds = []

    def on_event(kind, **e):
        kinds.append(kind)
        if kind == "climb_start":
            assert e["field"] == n_b - 1 and e["builder"].startswith("builder")
            t.climb_start(e["builder"], e["field"], e["steps"], gen=e["gen"])
        elif kind == "climb_step":
            assert e["proposal"]["kind"] in ("card", "legend") and set(e["proposal"]) == {"out", "in", "kind"}
            t.climb_step(e["builder"], e["step"], e["games"], gen=e["gen"])
        elif kind == "climb_done":
            t.climb_done(e["builder"], gen=e["gen"])
        elif kind == "tourney_cell":
            t.cell(e["a"], e["b"], e["n"], e["verdict"], e["cap"], gen=e["gen"])
        elif kind == "gen_done":
            assert len(e["standings"]) == n_b and e["replaced"] is None
            t.gen_done(e["gen"])
        assert t.remaining_min <= t.remaining_max

    runs = list(league(reg, n_builders=n_b, generations=gens, steps=steps, seed=2, agent="random", workers=1,
                       games_per_pair=cap, archetypes="legacy", seeds_per_batch=2, max_batches=1, on_event=on_event))
    assert len(runs) == gens
    assert kinds[0] == "climb_start" and kinds[-1] == "gen_done"
    assert kinds.count("climb_start") == kinds.count("climb_done") == n_b * gens
    assert "tourney_cell" in kinds
    assert t.step == t.steps and t.remaining_min == 0 and t.remaining_max == 0
    assert t.done > 0
