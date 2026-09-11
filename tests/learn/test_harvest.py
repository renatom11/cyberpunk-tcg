"""The cheap bootstrap: what a harvest must guarantee before anything trains on it.

Four claims, and every one of them is a claim a loss curve could not tell you was false:

1. a harvested replay replays to exactly the game it says it was;
2. an example row is the *same* float vector the live game would have produced, with the label of
   whoever eventually won;
3. no harvested deck is a held-out retail starter — checked by contents, not by trusting the
   sampler's name filter, because the whole generalisation gap rests on this;
4. an interrupted harvest resumes without duplicating or dropping a game, and refuses to resume
   into a different distribution.

Kept to a couple of dozen games so the suite stays near its current runtime.
"""

import gzip
import json
import sys
from array import array
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import harvest  # noqa: E402

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.deck.decklist import Decklist  # noqa: E402
from cptcg.learn import decks as D  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402
from cptcg.learn.features import NFEAT, features  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "experience" / "bootstrap-sample.jsonl.gz"


def play(argv):
    assert harvest.main(argv) == 0


def rows_of(prefix: Path) -> list[tuple[float, ...]]:
    """The float32 rows of an example file, read back through its own header."""
    head = json.loads(Path(str(prefix) + ".json").read_text(encoding="utf-8"))
    cols = head["cols"]
    a = array("f")
    with open(str(prefix) + ".f32", "rb") as f:
        a.fromfile(f, head["rows"] * cols)
    if sys.byteorder != "little":
        a.byteswap()
    return [tuple(a[i:i + cols]) for i in range(0, len(a), cols)]


def live_game(reg, seed: int, i: int, agents=("heuristic", "heuristic")):
    """Play harvest game ``i`` live, capturing (features, player) at every decision.

    Deliberately re-implements ``runner.play_game``'s loop rather than replaying the record, so
    that test 2 compares the harvest against the engine and not against itself.
    """
    a, b = D.sample_pair(reg, harvest.pair_rng(seed, i))
    gs = harvest.game_seed(seed, i)
    ags = [make_agent(n, gs * 2 + p) for p, n in enumerate(agents)]
    s = new_game(reg, (a, b), gs, DEFAULT_CONFIG, record=True)
    for p, ag in enumerate(ags):
        ag.new_game(gs, p)
    out = []
    while not s.over:
        legal_actions(s)
        ch = s.pending
        out.append((features(s, ch.player), ch.player))
        apply(s, ags[ch.player].act(s, ch))
    return out, s


# ------------------------------------------------------------------ 1. replay fidelity
@pytest.fixture(scope="module")
def harvested(tmp_path_factory, pool):
    """Six heuristic games, harvested once for the whole module."""
    out = tmp_path_factory.mktemp("harvest") / "h.jsonl.gz"
    play(["play", "--games", "6", "--seed", "21", "--workers", "1", "--out", str(out), "--fresh"])
    return out


def test_a_harvested_replay_replays_to_its_recorded_outcome(harvested, pool):
    n = 0
    for rec in read_games(harvested):
        s = rec.replay().final_state(pool)
        assert s.over
        assert s.winner == rec.winner
        assert s.end_reason.name == rec.end_reason
        assert s.turn == rec.turns
        assert len(s.actions) == rec.n_decisions
        n += 1
    assert n == 6


def test_every_record_carries_its_game_index(harvested):
    assert [r.meta["i"] for r in read_games(harvested)] == list(range(6))


def test_the_deck_pair_is_a_pure_function_of_the_game_index(harvested, pool, tmp_path):
    """Game *i* is the same game in every run with the same seed, whatever else was played.

    This is the property that makes sharding and exact resume possible at all: a shorter run is a
    prefix of a longer one, and the decks come from the index rather than from a sequential stream.
    """
    out = tmp_path / "prefix.jsonl.gz"
    play(["play", "--games", "4", "--seed", "21", "--workers", "1", "--out", str(out), "--fresh"])
    assert [r.to_json() for r in read_games(out)] == \
           [r.to_json() for r in read_games(harvested)][:4]
    # and the pair really is drawn by the index, not by the harvest's own bookkeeping
    for i, rec in enumerate(read_games(out)):
        a, _b = D.sample_pair(pool, harvest.pair_rng(21, i))
        assert rec.decks[0]["name"] == a.name and rec.decks[0]["legends"] == list(a.legends)


# ------------------------------------------------------------------ 2. examples
def test_examples_are_the_features_the_live_game_produced(tmp_path, pool):
    out = tmp_path / "one.jsonl.gz"
    play(["play", "--games", "1", "--seed", "33", "--workers", "1", "--out", str(out), "--fresh"])
    prefix = tmp_path / "ex"
    play(["examples", "--in", str(out), "--out", str(prefix), "--rate", "1.0", "--workers", "1"])

    live, s = live_game(pool, 33, 0)
    got = rows_of(prefix)
    assert len(got) == len(live)
    for ply, (row, (f, me)) in enumerate(zip(got, live)):
        want = array("f", f)                       # what float32 storage does to a Python float
        assert tuple(row[:NFEAT]) == tuple(want), f"decision {ply}"
        label = 0.5 if s.winner is None else (1.0 if s.winner == me else 0.0)
        assert row[NFEAT] == pytest.approx(label)
        assert row[NFEAT + 1] == 0.0               # game index
        assert row[NFEAT + 2] == float(ply)        # ply


def test_the_default_rate_keeps_a_reproducible_subset(harvested, tmp_path):
    full, quarter, again = tmp_path / "f", tmp_path / "q", tmp_path / "q2"
    for prefix, rate in ((full, "1.0"), (quarter, "0.25"), (again, "0.25")):
        play(["examples", "--in", str(harvested), "--out", str(prefix), "--rate", rate,
              "--workers", "1"])
    all_rows, q_rows = rows_of(full), rows_of(quarter)
    assert set(q_rows) <= set(all_rows)
    assert 0 < len(q_rows) < len(all_rows)
    assert q_rows == rows_of(again)                # the draw is seeded from each record's own seed


def test_the_header_names_the_columns_and_is_written_last(harvested, tmp_path):
    prefix = tmp_path / "hdr"
    play(["examples", "--in", str(harvested), "--out", str(prefix), "--workers", "1"])
    head = json.loads(Path(str(prefix) + ".json").read_text(encoding="utf-8"))
    assert head["columns"][-3:] == ["label", "game", "ply"]
    assert head["cols"] == NFEAT + 3
    assert head["bytes"] == head["rows"] * head["cols"] * 4
    assert head["rules"] == DEFAULT_CONFIG.digest()
    assert all(head["decorrelation_l2"][str(k)] is not None for k in harvest.GAPS)


# ------------------------------------------------------------------ 3. the held-out starters
def test_the_held_out_starters_never_appear_in_a_harvest(tmp_path):
    out = tmp_path / "rand.jsonl.gz"
    play(["play", "--games", "40", "--agent", "random", "--seed", "8", "--workers", "1",
          "--out", str(out), "--fresh"])
    n = 0
    for rec in read_games(out):
        for d in rec.decks:
            assert d["name"] not in D.HOLDOUT
            deck = Decklist.from_counts(d["name"], d["legends"], d["main"])
            assert not D.is_holdout(deck), f"{d['name']} is a held-out starter by contents"
            n += 1
    assert n == 80


# ------------------------------------------------------------------ 4. resume
def test_resume_neither_duplicates_nor_drops(tmp_path):
    straight = tmp_path / "straight.jsonl.gz"
    play(["play", "--games", "8", "--agent", "random", "--seed", "5", "--workers", "1",
          "--out", str(straight), "--fresh"])
    want = [r.to_json() for r in read_games(straight)]

    torn = tmp_path / "torn.jsonl.gz"
    play(["play", "--games", "4", "--agent", "random", "--seed", "5", "--workers", "1",
          "--out", str(torn), "--fresh"])
    with open(torn, "ab") as f:                    # an interrupt mid-write: a torn gzip member
        f.write(gzip.compress(b'{"format":1,"seed":')[:17])
    play(["play", "--games", "8", "--agent", "random", "--seed", "5", "--workers", "1",
          "--out", str(torn), "--resume"])

    got = [r.to_json() for r in read_games(torn)]
    assert [r["meta"]["i"] for r in got] == list(range(8))
    assert got == want
    man = harvest.read_manifest(torn)
    assert man["games_done"] == 8 and man["bytes"] == torn.stat().st_size


def test_a_resume_into_a_different_distribution_is_refused(tmp_path):
    out = tmp_path / "d.jsonl.gz"
    play(["play", "--games", "2", "--agent", "random", "--seed", "5", "--workers", "1",
          "--out", str(out), "--fresh"])
    for change in (["--seed", "6"], ["--agent", "heuristic"], ["--mix", "random=1"]):
        argv = ["play", "--games", "4", "--agent", "random", "--seed", "5", "--workers", "1",
                "--out", str(out), "--resume"] + change
        with pytest.raises(ValueError, match="refusing to resume"):
            harvest.main(argv)


def test_an_existing_harvest_is_never_silently_overwritten(tmp_path):
    out = tmp_path / "e.jsonl.gz"
    play(["play", "--games", "2", "--agent", "random", "--seed", "5", "--workers", "1",
          "--out", str(out), "--fresh"])
    with pytest.raises(SystemExit, match="--resume"):
        harvest.main(["play", "--games", "2", "--agent", "random", "--seed", "5", "--workers", "1",
                      "--out", str(out)])


def test_compaction_keeps_every_record_and_the_manifest_in_step(tmp_path):
    """Appending costs space — one gzip member per chunk — and compaction buys it back without
    changing a single record or breaking the byte-offset resume."""
    out = tmp_path / "c.jsonl.gz"
    play(["play", "--games", "8", "--agent", "random", "--seed", "5", "--workers", "1",
          "--out", str(out), "--fresh"])
    want = [r.to_json() for r in read_games(out)]
    before = out.stat().st_size
    play(["compact", str(out)])
    assert out.stat().st_size < before
    assert [r.to_json() for r in read_games(out)] == want
    man = harvest.read_manifest(out)
    assert man["bytes"] == out.stat().st_size and "compacted" in man
    # a resume against the compacted file is a no-op rather than a corruption
    play(["play", "--games", "8", "--agent", "random", "--seed", "5", "--workers", "1",
          "--out", str(out), "--resume"])
    assert [r.to_json() for r in read_games(out)] == want


def test_an_unfinished_harvest_is_not_compacted(tmp_path):
    out = tmp_path / "u.jsonl.gz"
    play(["play", "--games", "2", "--agent", "random", "--seed", "5", "--workers", "1",
          "--out", str(out), "--fresh"])
    man = harvest.read_manifest(out)
    man["games_target"] = 99
    harvest.write_manifest(out, man)
    with pytest.raises(SystemExit, match="finish it"):
        harvest.main(["compact", str(out)])


# ------------------------------------------------------------------ 5. the committed sample
def test_the_committed_sample_still_replays(pool):
    """The staleness alarm. If a ruling changes, this fails loudly and the sample is regenerated —
    the same contract ``tests/golden/games.json`` has."""
    assert SAMPLE.exists(), f"{SAMPLE} is missing; regenerate it with tools/harvest.py play"
    n = 0
    for rec in read_games(SAMPLE):
        s = rec.replay().final_state(pool)
        assert (s.winner, s.end_reason.name, s.turn) == (rec.winner, rec.end_reason, rec.turns)
        n += 1
    assert n == 100


def test_the_committed_sample_has_no_held_out_deck(pool):
    for rec in read_games(SAMPLE):
        for d in rec.decks:
            assert not D.is_holdout(Decklist.from_counts(d["name"], d["legends"], d["main"]))


# ------------------------------------------------------------------ odds and ends
def test_the_mix_is_validated_before_a_single_game_is_played():
    with pytest.raises(ValueError):
        harvest.parse_mix("randmo=1")
    assert harvest.parse_mix("random=.5,sample=.5") == {"random": 0.5, "sample": 0.5}
    assert harvest.parse_mix(None) is None


def test_deck_source_tallies_the_samplers_own_names():
    assert harvest.deck_source("random") == "random"
    assert harvest.deck_source("random-b") == "random"
    assert harvest.deck_source("built") == "heuristic"
    assert harvest.deck_source("explorer-b") == "explorer"
    assert harvest.deck_source(D.training_decks()[0].name) == "sample"


def test_the_default_output_is_never_inside_the_repository():
    assert ROOT not in harvest.default_out("heuristic", "heuristic", 7).parents
