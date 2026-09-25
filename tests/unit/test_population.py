"""The deck population tool: seeding and bootstrap Bradley-Terry ratings."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import population as P  # noqa: E402


def test_bootstrap_ranks_a_dominant_deck_first_and_brackets_its_point():
    # deck 0 beats 1 and 2 most of the time; 1 and 2 are even
    cells = [(0, 1, 16, 20), (0, 2, 15, 20), (1, 2, 10, 20)]
    point, lo, hi = P.bootstrap_bt(cells, 3, resamples=200)
    assert point.argmax() == 0
    assert np.isclose(np.exp(np.log(point).mean()), 1.0)
    assert all(lo[i] <= point[i] <= hi[i] for i in range(3))
    assert lo[0] > hi[1] or lo[0] > hi[2]      # the dominant deck is separated from at least one


def test_init_and_rate_round_trip(tmp_path):
    decks = sorted((ROOT / "data" / "decks").glob("*.json"))[:3]
    pop = tmp_path / "population.json"
    P.main(["init", "--out", str(pop)] + [str(d) for d in decks])
    names = [json.loads(d.read_text())["name"] for d in decks]
    t = {"decks": [{"name": n} for n in names], "rules": "x", "list_mode": "inferred",
         "cells": [{"i": 0, "j": 1, "wins_i": 12, "n": 20}, {"i": 0, "j": 2, "wins_i": 14, "n": 20},
                   {"i": 1, "j": 2, "wins_i": 9, "n": 20}]}
    tj = tmp_path / "t.json"
    tj.write_text(json.dumps(t))
    P.main(["rate", str(pop), "--player", "p1", "--tourney", str(tj), "--resamples", "50"])
    P.main(["rate", str(pop), "--player", "p2", "--tourney", str(tj), "--resamples", "50"])
    d = json.loads(pop.read_text())
    assert [m["name"] for m in d["members"]] == names
    for m in d["members"]:
        assert set(m["ratings"]) == {"p1", "p2"} and m["ratings"]["p1"]["games"] == 40
        assert m["player_dependent"] == []          # identical ratings are never player-dependent
        assert m["class"] in ("mono", "two-plus-one", "one-of-each")
    assert (tmp_path / "matrix_p1.json").exists()


def test_report_computes_the_g6_numbers(tmp_path):
    decks = sorted((ROOT / "data" / "decks").glob("*.json"))[:4]
    pop = tmp_path / "population.json"
    P.main(["init", "--out", str(pop)] + [str(d) for d in decks])
    names = [json.loads(d.read_text())["name"] for d in decks]
    cells = [{"i": i, "j": j, "wins_i": 10 + 2 * (j - i), "n": 20} for i in range(4) for j in range(i + 1, 4)]
    tj = tmp_path / "t.json"
    tj.write_text(json.dumps({"decks": [{"name": n} for n in names], "cells": cells}))
    for p in ("p1", "p2"):
        P.main(["rate", str(pop), "--player", p, "--tourney", str(tj), "--resamples", "50"])
    out = tmp_path / "report.json"
    P.main(["report", str(pop), "--previous", str(pop), "--draws", "20", "--resamples", "50",
            "--out", str(out)])
    r = json.loads(out.read_text())
    (ag,) = r["agreement"]
    assert ag["spearman"] == 1.0                    # the same matrix under both players
    assert r["stability"] == {"p1": 1.0, "p2": 1.0}
    assert r["diversity"]["distinct_triples"] == len({tuple(sorted(json.loads(d.read_text())["legends"]))
                                                      for d in decks})
    assert set(r["per_player"]) == {"p1", "p2"} and r["exploitability"] is None
    assert 0.0 < r["diversity"]["mean_list_similarity"] <= 1.0


def test_list_similarity_is_multiset_jaccard():
    assert P.list_similarity(["a", "a", "b"], ["a", "b", "b"]) == 2 / 4
    assert P.list_similarity(["a"], ["a"]) == 1.0
