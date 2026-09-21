"""The delayed-reward suite: every stored claim, re-derived.

The suite is the falsifiability instrument for the training loop, so a stored position that has
quietly stopped being a delayed-reward position would be worse than no suite at all. These tests
rebuild every position from the data file and check all three parts of its claim from scratch: the
winning line still wins inside the position's horizon, the frozen heuristic still misses it, and
uniform random play still does not stumble into it more often than the file says.
"""

import pytest

from cptcg.cards.registry import cards_digest
from cptcg.core.config import DEFAULT_CONFIG
from cptcg.core.engine import legal_actions
from cptcg.core.view import info_key
from cptcg.learn import delayed

from tests.conftest import Side, board


@pytest.fixture(scope="module")
def suite():
    return delayed.load_suite()


def _authored(e) -> bool:
    """A position someone wrote, as opposed to one found in a real game.

    The two are both ``kind: board`` now — the five mined entries were frozen from their replays,
    because a replay is a list of action indices and stops rebuilding the moment a card in its
    prefix gains or loses a prompt. The rules below are sanity checks on *authored* boards (three
    Legends a side, a solver that exhausts its search), and a real game legitimately breaks them: a
    Legend can have been spent as an Eddie and gone, and a real mid-game board is wide enough that
    the node cap bites before the search is exhausted.
    """
    return not str(e.get("source", "")).startswith("mined")

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


def test_the_suite_was_qualified_against_this_build_of_the_cards(suite):
    """The other half of the staleness contract, and the half that was missing.

    Every stored line is a list of action *indices* into the solver's own tree. A card script that
    gains or loses a prompt renumbers those indices, exactly as a changed ruling does — and for most
    of this project's life the file recorded only the ruleset, so a card fix could quietly turn a
    stored winning line into a different line in a different game with nothing raising.

    The repair is `python tools/arena.py delayed --requalify`, about half a minute for the whole
    suite, which re-derives every block and re-stamps both digests.
    """
    assert suite.get("cards") == cards_digest(), (
        "the suite was qualified against another build of the card scripts; re-qualify it with "
        "`tools/arena.py delayed --requalify`")


def test_load_suite_can_refuse_a_stale_card_set(tmp_path):
    """The refusal is available but off by default: the digest covers all 140 scripts, and most
    fixes cannot touch a given position — so an unconditional refusal would cry wolf. Passing
    `cards=` is how a caller that cares asks for it."""
    import json

    p = tmp_path / "suite.json"
    p.write_text(json.dumps({"rules": DEFAULT_CONFIG.digest(), "cards": "deadbeef",
                             "positions": []}), encoding="utf-8")
    delayed.load_suite(p)                                     # the default reads it happily
    with pytest.raises(ValueError, match="card set"):
        delayed.load_suite(p, cards=cards_digest())


def test_the_suite_covers_both_horizons(suite):
    """The instrument only tests the plan's claim if some position pays off *after* the turn.

    Without a horizon-2 position the suite measures within-turn sequencing only, which is a
    different and narrower claim than the one the loop is being held to.
    """
    horizons = {delayed.entry_horizon(p) for p in suite["positions"]}
    assert 1 in horizons, "no within-turn positions left"
    assert max(horizons) >= 2, (
        "every position is won inside the searched turn: the suite cannot test a delayed reward")


def test_hand_built_positions_look_like_real_games(pool, suite):
    """A value head reads list size, undrawn fraction and Legend RAM.

    A three-card deck and two Legends are outside anything training will have seen, so a
    generation could score badly here for reasons that have nothing to do with planning.
    """
    for e in suite["positions"]:
        if not _authored(e):
            continue
        for side in e["spec"]["sides"]:
            # A Legend that went solo stands on the field and is still one of the deck's three.
            solo = sum(1 for item in side.get("field", ())
                       if isinstance(item, list) and pool.get(item[0]).type.name == "LEGEND")
            assert len(side.get("legends", ())) + solo == 3, f"{e['id']}: {len(side.get('legends', ()))} Legends"
            assert len(side["deck"]) >= 20, f"{e['id']}: {len(side['deck'])} cards left in deck"


def test_every_stored_position_still_has_its_winning_line(pool, suite):
    """Half one of the claim: the stored line, replayed, really wins the game."""
    for e in suite["positions"]:
        s = delayed.build_entry(pool, e)
        me = e["player"]
        assert s.pending is not None and s.pending.player == me
        line = e["verified"]["line"]
        assert line, e["id"]
        assert delayed.replay_line(s, me, line, max_turns=delayed.entry_horizon(e)), (
            f"{e['id']}: the stored line no longer wins")


def test_the_frozen_heuristic_still_misses_every_position(pool, suite):
    """Half two: a position only belongs here while the greedy agent cannot find the win."""
    for e in suite["positions"]:
        s = delayed.build_entry(pool, e)
        for seed in e["verified"]["heuristic_seeds"]:
            won, _line = delayed.play_turn(s, e["player"], "heuristic", seed=seed,
                                           max_turns=delayed.entry_horizon(e))
            assert not won, f"{e['id']}: the heuristic now wins it on seed {seed}"
        assert set(delayed.SCORE_SEEDS) <= set(e["verified"]["heuristic_seeds"]), (
            f"{e['id']}: the heuristic was never checked on the seeds agents are scored on")


def test_every_stored_floor_is_low_and_still_the_number_in_the_file(pool, suite):
    """Part three: what uniform random play scores, which is what "solved N of M" is read against.

    A position several lines win is a coin toss dressed as a planning test. The stored floor is
    re-derived rather than trusted, because a rules change moves it silently.
    """
    for e in suite["positions"]:
        s = delayed.build_entry(pool, e)
        v = e["verified"]
        wins, trials = delayed.floor_rate(s, e["player"], seeds=v["floor_seeds"],
                                          agent=v["floor_agent"],
                                          max_turns=delayed.entry_horizon(e))
        assert trials == v["floor_trials"] and wins == v["floor_wins"], (
            f"{e['id']}: the random floor moved from {v['floor_wins']} to {wins} of {trials}")
        assert wins <= delayed.MAX_FLOOR * trials, (
            f"{e['id']}: random play wins {wins} of {trials} — that is not a planning test")


def test_verify_suite_agrees_with_the_two_halves(pool, suite):
    rows = delayed.verify_suite(pool, suite)
    assert len(rows) == len(suite["positions"])
    assert all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]


def test_scoring_the_frozen_heuristic_gives_zero(pool, suite):
    """Today's shipping agent scores nothing here — *by construction*, not by measurement.

    A position is in the suite only because the heuristic missed it on exactly these seeds, so this
    zero is a definition. It is worth pinning anyway: if it ever stops holding, a stored position
    has drifted. The number that is measured is the floor, and it is printed beside it.
    """
    out = delayed.score_agent(pool, suite, "heuristic")
    assert out["solved"] == 0 and out["trial_wins"] == 0
    assert out["positions"] == len(suite["positions"])
    text = delayed.render_score(out)
    assert f"Solved 0 of {out['positions']}" in text
    assert "floor" in text and str(out["floor_trials"]) in text


def test_the_score_report_prints_the_floor_beside_the_score(pool, suite):
    """"Solved N of M" is unreadable as progress unless the floor is next to it."""
    out = delayed.score_agent(pool, suite, "random")
    assert out["floor_trials"] == len(suite["positions"]) * len(delayed.SCORE_SEEDS)
    for r in out["rows"]:
        assert r["floor_wins"] is not None and r["floor_trials"], r["id"]
        assert f"{r['floor_wins']}/{r['floor_trials']}" in delayed.render_score(out)


def test_scoring_seeds_are_not_the_seeds_a_position_was_hand_picked_on(suite):
    """Selection and measurement must not share seeds, or the suite grades its own homework."""
    assert not (set(delayed.TRIAL_SEEDS) & set(delayed.SCORE_SEEDS))
    assert len(delayed.SCORE_SEEDS) >= 16, (
        "too few scoring seeds: a position random play wins now and then passes by luck")


def test_a_delayed_position_really_is_delayed(pool, suite):
    """The sharpest thing the suite can be asked, and the one the first version could not answer.

    A horizon-2 position's own winning line must **not** win inside the searched turn. If it did,
    the position would be a within-turn puzzle wearing a "delayed" label, and a generation that
    learned nothing about setup could score on it.
    """
    late = [e for e in suite["positions"] if delayed.entry_horizon(e) > 1]
    assert late, "no position with a horizon past this turn"
    for e in late:
        s = delayed.build_entry(pool, e)
        line = e["verified"]["line"]
        assert not delayed.replay_line(s, e["player"], line, max_turns=1), (
            f"{e['id']}: the line wins inside the turn, so its reward is not delayed at all")
        assert delayed.replay_line(s, e["player"], line,
                                   max_turns=delayed.entry_horizon(e)), e["id"]


def test_the_horizon_is_counted_in_my_own_turns(pool, suite):
    """``confirmed_win`` at a wider horizon must be a superset of the narrower one, never a
    different question: anything won by the next turn is still won two turns out."""
    e = next(p for p in suite["positions"] if delayed.entry_horizon(p) == 1)
    s = delayed.build_entry(pool, e)
    me = e["player"]
    line = e["verified"]["line"]
    assert delayed.replay_line(s, me, line, max_turns=1)
    assert delayed.replay_line(s, me, line, max_turns=2)
    assert delayed.replay_line(s, me, line, max_turns=3)


# ------------------------------------------------------------------ the solver
def test_the_solver_rediscovers_a_win_in_every_hand_built_position(pool, suite):
    for e in suite["positions"]:
        if not _authored(e):
            continue                              # mined positions are covered by their stored line
        s = delayed.build_position(pool, e["spec"])
        h = delayed.entry_horizon(e)
        sol = delayed.turn_search(s, e["player"], max_nodes=delayed.MAX_NODES, max_turns=h)
        assert sol.won and sol.exhausted, e["id"]
        assert delayed.replay_line(s, e["player"], sol.line, max_turns=h), e["id"]


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
    """The solver's cheap goal test at a horizon of one, stated as a property.

    It is a *precondition* for a within-turn win only. Past that horizon the whole point is that
    the board does not show the win yet, so ``confirmed_win`` must not consult it — checked here by
    a position whose reward is late passing the wide test and failing the narrow one.
    """
    e = suite["positions"][0]
    s = delayed.build_entry(pool, e)
    assert not delayed.could_win(s, e["player"])
    s.gig[e["player"]] += [(4, 1)] * DEFAULT_CONFIG.gigs_to_win
    assert delayed.could_win(s, e["player"])

    late = next(p for p in suite["positions"] if delayed.entry_horizon(p) > 1)
    s = delayed.build_entry(pool, late)
    end = delayed.replay_to_end_of_turn(s, late["player"], late["verified"]["line"])
    assert not delayed.could_win(end, late["player"]), (
        f"{late['id']}: the winning Gig count is already on the board at the end of the turn")
    assert not delayed.confirmed_win(end, late["player"], max_turns=1)
    assert delayed.confirmed_win(end, late["player"], max_turns=delayed.entry_horizon(late))


def test_the_rival_policy_is_a_pure_function_of_the_position(pool, suite):
    """Called twice on the same state it must answer the same way, or a stored line stops
    reproducing as soon as the traversal order changes."""
    s = delayed.build_entry(pool, suite["positions"][0])
    legal_actions(s)
    policy = delayed.fixed_policy()
    assert policy(s, s.pending) == policy(s, s.pending)


# ------------------------------------------------------------ Stage 0: defender positions
def test_a_defend_position_is_judged_by_the_rival_not_reaching_the_count(pool):
    """``mode: "defend"``: the player is the defender, the rival is active and one Gig from the
    count, and the goal is that the rival's turn ends short of it. Here the rival has one
    attacker and the defender one ready BLOCKER-less Unit, so every line the defender has
    (block with it or pass) decides whether the Gig is stolen. The machinery is what is pinned:
    the solver, the trials and the floor all use ``held`` rather than a win for the mover, and
    the verdict is a dict with the same keys as a mover position."""
    spec = {"turn": 8, "active": 1, "first_player": 0, "turns_taken": [4, 3], "sides": [
        {"field": [["corpo-security", {}]], "eddies": 0,
         "legends": ["goro-takemura-hands-unclean", "v-corporate-exile", "hanako-arasaka-daughter-of-the-emperor"],
         "deck": ["floor-it", "mantis-blades", "psycho-squad", "corpo-security", "riot-shield", "field-operator"],
         "gig": [[4, 2], [6, 3]], "fixer": [8, 10, 12, 20]},
        {"field": [["psycho-squad", {}]], "eddies": 0,
         "legends": ["royce-psycho-on-the-edge", "goro-takemura-hands-unclean", "v-corporate-exile"],
         "deck": ["floor-it", "mantis-blades", "psycho-squad", "corpo-security", "riot-shield", "field-operator"],
         "gig": [[4, 1], [6, 2], [8, 3], [10, 4], [12, 5], [20, 6]], "fixer": [4]}]}
    entry = {"id": "defend-test", "kind": "board", "mode": "defend", "player": 0, "spec": spec}
    v = delayed.qualify(pool, entry, max_nodes=2000)
    assert v["mode"] == "defend" and v["max_turns"] == 1 and v["player"] == 0
    for k in ("solver_found_win", "heuristic_wins", "floor_wins", "floor_trials", "ok"):
        assert k in v
    # the goal itself: held is about the rival's count, not the defender's
    s = delayed.build_position(pool, spec)
    assert delayed.held(s, 0) is True
    s.gig[1].append((4, 4))
    assert delayed.held(s, 0) is False
    bad = dict(entry, player=1)
    with pytest.raises(ValueError):
        delayed.qualify(pool, bad, max_nodes=200)
