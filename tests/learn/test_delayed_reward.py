"""The delayed-reward suite: every stored claim, re-derived.

The suite is the falsifiability instrument for the training loop, so a stored position that has
quietly stopped being a delayed-reward position would be worse than no suite at all. These tests
rebuild every position from the data file and check both halves of its claim from scratch: the
winning line still wins, and the frozen heuristic still misses it.
"""

import pytest

from cptcg.core.config import DEFAULT_CONFIG
from cptcg.core.engine import legal_actions
from cptcg.core.view import info_key
from cptcg.learn import delayed

from tests.conftest import Side, board


@pytest.fixture(scope="module")
def suite():
    return delayed.load_suite()


# --------------------------------------------------- the position builder is the test helper
def test_build_position_matches_the_conftest_board_helper(pool):
    """A stored position must be exactly the state ``tests/conftest.board`` would have built.

    The suite is data and the builder lives in the package, so nothing stops the two drifting
    apart except this: build the same board both ways and compare the omniscient information key,
    which covers every zone, every instance flag, the dice and the pending menu.
    """
    spec = {"turn": 9, "active": 0, "seed": 7, "turns_taken": [4, 4], "sides": [
        {"field": [["rockn-rockerboy", {}]], "hand": ["mantis-blades"],
         "legends": [["v-corporate-exile", {"spent": True}]],
         "deck": ["psycho-squad"], "eddies": 2, "spent_eddies": 1,
         "gig": [[4, 3], [6, 2]], "fixer": [8, 20]},
        {"field": [["secondhand-bombus", {"gear": ["mantis-blades"]}]],
         "legends": ["goro-takemura-hands-unclean"], "deck": ["emergency-atlus"],
         "eddies": 1, "gig": [[10, 7]], "fixer": [12, 20]}]}
    mine = delayed.build_position(pool, spec)
    theirs = board(
        pool,
        Side(field=[("rockn-rockerboy", {})], hand=["mantis-blades"],
             legends=[("v-corporate-exile", {"spent": True})], deck=["psycho-squad"],
             eddies=2, spent_eddies=1, gig=[(4, 3), (6, 2)], fixer=[8, 20]),
        Side(field=[("secondhand-bombus", {"gear": ["mantis-blades"]})],
             legends=["goro-takemura-hands-unclean"], deck=["emergency-atlus"],
             eddies=1, gig=[(10, 7)], fixer=[12, 20]),
        active=0, turn=9, seed=7, turns_taken=[4, 4])
    assert info_key(mine, 0) == info_key(theirs, 0)
    assert info_key(mine, 1) == info_key(theirs, 1)


# ------------------------------------------------------------------ the stored suite
def test_the_suite_is_not_empty_and_is_for_this_ruleset(suite):
    assert suite["positions"], "the delayed-reward suite is empty"
    assert suite["rules"] == DEFAULT_CONFIG.digest(), (
        "the suite was verified under another ruleset; re-verify it and update 'rules'")
    ids = [p["id"] for p in suite["positions"]]
    assert len(ids) == len(set(ids))
    assert any(p["source"] == "hand-built" for p in suite["positions"])


def test_every_stored_position_still_has_its_winning_line(pool, suite):
    """Half one of the claim: the stored line, replayed, really wins the game."""
    for e in suite["positions"]:
        s = delayed.build_entry(pool, e)
        me = e["player"]
        assert s.pending is not None and s.pending.player == me
        line = e["verified"]["line"]
        assert line, e["id"]
        assert delayed.replay_line(s, me, line), f"{e['id']}: the stored line no longer wins"


def test_the_frozen_heuristic_still_misses_every_position(pool, suite):
    """Half two: a position only belongs here while the greedy agent cannot find the win."""
    for e in suite["positions"]:
        s = delayed.build_entry(pool, e)
        for seed in e["verified"]["heuristic_seeds"]:
            won, _line = delayed.play_turn(s, e["player"], "heuristic", seed=seed)
            assert not won, f"{e['id']}: the heuristic now wins it on seed {seed}"


def test_verify_suite_agrees_with_the_two_halves(pool, suite):
    rows = delayed.verify_suite(pool, suite)
    assert len(rows) == len(suite["positions"])
    assert all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]


def test_scoring_the_frozen_heuristic_gives_zero(pool, suite):
    """The suite is calibrated so that today's shipping agent scores nothing on it.

    That is the baseline every future generation is measured against: any rise is real.
    """
    out = delayed.score_agent(pool, suite, "heuristic")
    assert out["solved"] == 0 and out["trial_wins"] == 0
    assert out["positions"] == len(suite["positions"])
    assert f"Solved 0 of {out['positions']}" in delayed.render_score(out)


# ------------------------------------------------------------------ the solver
def test_the_solver_rediscovers_a_win_in_every_hand_built_position(pool, suite):
    for e in suite["positions"]:
        if e["kind"] != "board":
            continue                              # mined positions are covered by their stored line
        s = delayed.build_position(pool, e["spec"])
        sol = delayed.turn_search(s, e["player"], max_nodes=delayed.MAX_NODES)
        assert sol.won and sol.exhausted, e["id"]
        assert delayed.replay_line(s, e["player"], sol.line), e["id"]


def test_a_node_cap_reports_that_it_proved_nothing(pool, suite):
    """A search that ran out of budget must not read as 'there is no win here'."""
    e = next(p for p in suite["positions"] if p["kind"] == "board")
    s = delayed.build_position(pool, e["spec"])
    sol = delayed.turn_search(s, e["player"], max_nodes=1)
    assert sol.won is False and sol.exhausted is False and sol.nodes <= 1


def test_the_solver_finds_nothing_where_there_is_nothing(pool):
    """A quiet board with no Gigs in reach: an exhaustive turn search must come back empty."""
    s = delayed.build_position(pool, {"turn": 5, "active": 0, "seed": 3, "sides": [
        {"field": [["rockn-rockerboy", {}]], "hand": ["mantis-blades"],
         "legends": ["v-corporate-exile"], "deck": ["psycho-squad", "emergency-atlus"],
         "eddies": 2, "gig": [[4, 3]], "fixer": [6, 8, 10, 12, 20]},
        {"legends": ["goro-takemura-hands-unclean"], "deck": ["psycho-squad", "emergency-atlus"],
         "eddies": 1, "gig": [[6, 4]], "fixer": [4, 8, 10, 12, 20]}]})
    sol = delayed.turn_search(s, 0, max_nodes=4_000)
    assert sol.won is False and sol.exhausted is True


def test_could_win_is_the_gig_count_or_a_finished_game(pool, suite):
    """The solver's cheap goal test, stated as a property rather than left to the leaves."""
    e = suite["positions"][0]
    s = delayed.build_entry(pool, e)
    assert not delayed.could_win(s, e["player"])
    s.gig[e["player"]] += [(4, 1)] * DEFAULT_CONFIG.gigs_to_win
    assert delayed.could_win(s, e["player"])


def test_the_rival_policy_is_a_pure_function_of_the_position(pool, suite):
    """Called twice on the same state it must answer the same way, or a stored line stops
    reproducing as soon as the traversal order changes."""
    s = delayed.build_entry(pool, suite["positions"][0])
    legal_actions(s)
    policy = delayed.fixed_policy()
    assert policy(s, s.pending) == policy(s, s.pending)
