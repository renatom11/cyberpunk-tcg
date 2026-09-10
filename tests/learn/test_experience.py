"""Experience files: exact round trips, exact replays, a refused ruleset, and a readable dump."""

import gzip
import json

import pytest

from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.learn.dump import load_game, render_game
from cptcg.learn.experience import (FORMAT, GameRecord, dequantise_value, format_size_stats,
                                    outcome, quantise_value, quantise_visits, read_games,
                                    replay_features, size_stats, visit_policy, write_games)
from cptcg.sim.record import Replay
from cptcg.sim.runner import play_game


# ------------------------------------------------------------------ helpers
def a_game(reg, decks, seed=11, agents=("heuristic", "heuristic")) -> Replay:
    s = play_game(reg, decks, agents, seed=seed, record=True)
    return Replay.from_game(s, decks, agents)


def fake_search(record, reg, rng_seed=3):
    """Plausible visit counts and values, one row per decision, sized to the legal option lists."""
    import random
    rng = random.Random(rng_seed)
    widths = [len(s.pending.options) for s, *_ in replay_features(record, reg)]
    visits = []
    for w in widths:
        row = [rng.randrange(0, 20) for _ in range(w)]
        row[rng.randrange(w)] = 200
        visits.append(row)
    return visits, [rng.random() for _ in widths]


@pytest.fixture
def record(reg, decks):
    return GameRecord.from_replay(a_game(reg, decks), meta={"source": "test"})


# ------------------------------------------------------------------ quantisation
def test_visits_normalise_to_the_maximum_and_keep_the_argmax():
    assert quantise_visits([200, 100, 0]) == [255, 128, 0]
    assert quantise_visits([1, 3]) == [85, 255]
    assert quantise_visits([]) == []
    assert quantise_visits([0, 0]) == [0, 0]
    for counts in ([7, 3, 99, 1], [1, 1, 2], [500, 499]):
        q = quantise_visits(counts)
        assert max(q) == 255
        assert q.index(max(q)) == counts.index(max(counts))


def test_visit_policy_is_a_distribution():
    p = visit_policy(quantise_visits([200, 100, 0]))
    assert abs(sum(p) - 1.0) < 1e-9 and p[0] > p[1] > p[2]
    assert visit_policy([0, 0, 0, 0]) == [0.25] * 4          # unsearched: no opinion
    assert visit_policy([]) == []


def test_values_survive_quantisation_to_within_a_half_step():
    for v in (0.0, 0.001, 0.5, 0.61, 0.999, 1.0):
        assert abs(dequantise_value(quantise_value(v)) - v) <= 1 / 510 + 1e-12
    assert quantise_value(-2.0) == 0 and quantise_value(9.0) == 255      # clipped, never wrapped


# ------------------------------------------------------------------ round trip
def test_round_trip_preserves_every_field(reg, decks, tmp_path):
    rec = GameRecord.from_replay(a_game(reg, decks), meta={"generation": 2, "note": "hello"})
    v, val = fake_search(rec, reg)
    rec = GameRecord.from_replay(rec.replay(), visits=v, values=val, sims=200,
                                 meta={"generation": 2, "note": "hello"})
    p = tmp_path / "gen.jsonl"
    assert write_games(p, [rec], append=False) == 1
    back = list(read_games(p))
    assert len(back) == 1
    got = back[0]
    for f in ("seed", "decks", "actions", "rules", "agents", "winner", "end_reason", "turns",
              "visits", "values", "sims", "format", "meta"):
        assert getattr(got, f) == getattr(rec, f), f
    assert got == rec


def test_round_trip_without_search_output(record, tmp_path):
    p = tmp_path / "gen.jsonl"
    write_games(p, [record], append=False)
    got = next(iter(read_games(p)))
    assert got == record
    assert got.visits is None and got.values is None and got.sims is None


def test_gzip_and_appending(record, reg, decks, tmp_path):
    p = tmp_path / "gen.jsonl.gz"
    write_games(p, [record], append=False)
    write_games(p, [GameRecord.from_replay(a_game(reg, decks, seed=12))])       # a second member
    write_games(p, [GameRecord.from_replay(a_game(reg, decks, seed=13))])
    got = list(read_games(p))
    assert [r.seed for r in got] == [11, 12, 13]
    assert gzip.open(p, "rt", encoding="utf-8").read().count("\n") == 3
    plain = tmp_path / "gen.jsonl"
    write_games(plain, got[:2], append=False)
    write_games(plain, got[2:])
    assert [r.seed for r in read_games(plain)] == [11, 12, 13]


def test_from_replay_checks_the_width_of_the_search_output(record, reg):
    v, val = fake_search(record, reg)
    with pytest.raises(ValueError, match="decisions"):
        GameRecord.from_replay(record.replay(), visits=v[:-1])
    with pytest.raises(ValueError, match="decisions"):
        GameRecord.from_replay(record.replay(), values=val + [0.5])


# ------------------------------------------------------------------ exactness
def test_a_stored_game_replays_to_exactly_the_recorded_outcome(reg, decks, tmp_path):
    s = play_game(reg, decks, ("heuristic", "heuristic"), seed=31, record=True)
    rec = GameRecord.from_replay(Replay.from_game(s, decks, ("heuristic", "heuristic")))
    p = tmp_path / "gen.jsonl.gz"
    write_games(p, [rec], append=False)
    got = next(iter(read_games(p)))

    final = got.replay().final_state(reg)
    assert final.over
    assert final.winner == got.winner == s.winner
    assert final.end_reason.name == got.end_reason == s.end_reason.name
    assert final.turn == got.turns == s.turn
    assert final.actions == got.actions == s.actions
    assert len(list(replay_features(got, reg))) == len(s.actions)


def test_replay_features_walks_the_decisions_in_order(record, reg):
    seen = []
    for s, chosen, visits, value in replay_features(record, reg):
        assert s.pending is not None and not s.over
        assert 0 <= chosen < len(s.pending.options)
        assert visits is None and value is None            # this game carried no search output
        seen.append(chosen)
    assert seen == record.actions


def test_replay_features_hands_back_the_search_output(record, reg):
    v, val = fake_search(record, reg)
    rec = GameRecord.from_replay(record.replay(), visits=v, values=val, sims=64)
    for i, (s, chosen, visits, value) in enumerate(replay_features(rec, reg)):
        assert len(visits) == len(s.pending.options)
        assert max(visits) == 255 and visits.index(255) == v[i].index(max(v[i]))
        assert abs(value - val[i]) <= 1 / 510 + 1e-12


def test_a_visit_row_that_does_not_fit_the_position_is_an_error(record, reg):
    v, _ = fake_search(record, reg)
    rec = GameRecord.from_replay(record.replay(), visits=v)
    rec.visits[3] = rec.visits[3] + [7]                    # one option too many
    with pytest.raises(ValueError, match="legal options"):
        list(replay_features(rec, reg))


def test_outcome_is_the_value_label(record):
    assert outcome(record, record.winner) == 1.0
    assert outcome(record, 1 - record.winner) == 0.0
    assert outcome(GameRecord(seed=1, decks=({}, {}), actions=[]), 0) == 0.5


# ------------------------------------------------------------------ the ruleset gate
def test_a_record_from_another_ruleset_is_refused_on_read(record, tmp_path):
    other = RulesConfig(gigs_to_win=5)
    assert other.digest() != DEFAULT_CONFIG.digest()
    p = tmp_path / "gen.jsonl"
    write_games(p, [record], append=False)
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["rules"] = other.digest()
    p.write_text(json.dumps(raw) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as e:
        list(read_games(p))
    msg = str(e.value)
    assert other.digest() in msg and DEFAULT_CONFIG.digest() in msg
    assert "ruleset" in msg and "gen.jsonl:1" in msg

    # ...but a reader who asks for that ruleset, or for none, still gets the game.
    assert len(list(read_games(p, rules=other.digest()))) == 1
    assert len(list(read_games(p, rules=None))) == 1


def test_an_unknown_format_is_refused(record, tmp_path):
    p = tmp_path / "gen.jsonl"
    write_games(p, [record], append=False)
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["format"] = FORMAT + 1
    p.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="format"):
        list(read_games(p))


# ------------------------------------------------------------------ the size budget
def test_size_stats_describe_a_real_file(reg, decks, tmp_path):
    p = tmp_path / "gen.jsonl"
    write_games(p, [GameRecord.from_replay(a_game(reg, decks, seed=s)) for s in range(6)],
                append=False)
    st = size_stats(p)
    assert st["games"] == 6 and st["with_search"] == 0
    assert st["decisions"] > 6 * 20
    assert st["bytes_per_decision"] == pytest.approx(st["bytes"] / st["decisions"])
    assert st["gz_bytes"] < st["bytes"]
    # The budget the plan sets: a replay-only record is single-digit bytes per decision gzipped.
    assert st["gz_bytes_per_decision"] < 10
    assert "bytes/decision" in format_size_stats(st)


# ------------------------------------------------------------------ the dump
def test_the_dump_reads_back_the_game_a_person_can_follow(reg, decks, tmp_path):
    s = play_game(reg, decks, ("heuristic", "heuristic"), seed=77, record=True)
    rep = Replay.from_game(s, decks, ("heuristic", "heuristic"))
    rec = GameRecord.from_replay(rep, meta={"source": "test"})
    v, val = fake_search(rec, reg)
    rec = GameRecord.from_replay(rep, visits=v, values=val, sims=128, meta={"source": "test"})
    p = tmp_path / "gen.jsonl.gz"
    write_games(p, [rec], append=False)

    text = render_game(load_game(p, 0, rules=DEFAULT_CONFIG.digest()), reg)

    # the header: who played, with what, under which ruleset
    assert f"seed {rec.seed}" in text and rec.rules in text
    assert "heuristic vs heuristic" in text
    for d in decks:
        assert d.name in text
        for lid in d.legends:
            assert reg.get(lid).name in text
    assert "128 search iterations per decision" in text and "source=test" in text

    # every card the game actually touched is named in the dump, in words
    touched = set()
    for st, idx in rep.steps(reg):
        if idx is None:
            break
        inst = getattr(st.pending.options[idx], "inst", None)
        if inst is not None and inst >= 0:
            touched.add(st.card(inst).name)
    assert touched, "the game played no cards at all"
    for name in touched:
        assert name in text, name

    # the decisions: every one there, with its options, the choice marked and the numbers
    for i, (st, chosen, visits, value) in enumerate(replay_features(rec, reg)):
        assert f"#{i} " in text or f"#{i:<4}" in text
    assert text.count("->") >= rec.n_decisions
    assert "search value" in text and "255" in text

    # and the result
    assert f"RESULT: P{rec.winner}" in text
    assert rec.decks[rec.winner]["name"] in text and rec.end_reason in text


def test_the_dump_says_when_there_was_no_search(record, reg, tmp_path):
    p = tmp_path / "gen.jsonl"
    write_games(p, [record], append=False)
    text = render_game(load_game(p, 0), reg)
    assert "no search output" in text and "search value" not in text


def test_load_game_picks_the_right_record(reg, decks, tmp_path):
    p = tmp_path / "gen.jsonl"
    write_games(p, [GameRecord.from_replay(a_game(reg, decks, seed=s)) for s in (5, 6, 7)],
                append=False)
    assert [load_game(p, i).seed for i in range(3)] == [5, 6, 7]
    with pytest.raises(IndexError):
        load_game(p, 3)
