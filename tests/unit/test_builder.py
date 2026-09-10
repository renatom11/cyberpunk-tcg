import pytest

from cptcg.cards.registry import load_default
from cptcg.core.enums import CardType
from cptcg.core.rng import Pcg32
from cptcg.deck.builder import (BuildPrefs, hill_climb, heuristic_deck, legend_triples, mutate,
                                random_deck, random_legends, usable)
from cptcg.deck.decklist import Decklist
from cptcg.deck.validate import validate


@pytest.fixture(scope="module")
def reg():
    return load_default()


def test_playable_pool_is_150_of_151(reg):
    """Every card but Rebecca is transcribed from its face and scripted, so the deck builder
    can reach all of them; her ability has never been revealed."""
    assert len(usable(reg)) == 150
    assert [d.id for d in reg.defs if not d.verified] == ["rebecca-having-a-moment"]
    assert [d.id for d in reg.unimplemented()] == []


def test_many_legend_triples(reg):
    assert len(legend_triples(reg)) > 1500


def test_random_decks_are_legal(reg):
    rng = Pcg32(1)
    for _ in range(100):
        d = random_deck(reg, rng)
        assert validate(d, reg).ok and len(d.main) == 40


def test_heuristic_decks_meet_targets(reg):
    rng = Pcg32(7)
    for _ in range(20):
        legs = random_legends(reg, rng)
        d = heuristic_deck(reg, legs, rng)
        assert validate(d, reg).ok
        sell = sum(1 for c in d.main if reg.get(c).sell_tag) / len(d.main)
        assert sell >= 0.40
        units = sum(1 for c in d.main if reg.get(c).type is CardType.UNIT) / len(d.main)
        assert 0.35 <= units <= 0.75
        assert max(d.counts().values()) <= 3


def test_mutation_keeps_decks_legal(reg):
    rng = Pcg32(3)
    d = heuristic_deck(reg, None, rng)
    for _ in range(150):
        d, desc = mutate(reg, d, rng, legend_swap_rate=0.3)
        assert validate(d, reg).ok, desc
        assert len(d.main) == 40


def test_hill_climb_runs_and_logs(reg, tmp_path):
    rng = Pcg32(5)
    d = heuristic_deck(reg, None, rng, name="hc")
    field = [heuristic_deck(reg, None, rng, name="f1")]
    with open(tmp_path / "log.jsonl", "w") as log:
        best, hist = hill_climb(reg, d, field, steps=2, seed=1, agent="random", workers=1,
                                seeds_per_batch=3, max_batches=1, log=log)
    assert validate(best, reg).ok and len(hist) <= 2
    assert (tmp_path / "log.jsonl").read_text().count("\n") == len(hist)


def test_mutation_swaps_in_place(reg):
    rng = Pcg32(11)
    d = heuristic_deck(reg, None, rng)
    for _ in range(30):
        m, desc = mutate(reg, d, rng, legend_swap_rate=0.0)
        if desc == "no-op":
            continue
        diff = [i for i in range(40) if m.main[i] != d.main[i]]
        assert len(diff) == 1, desc
        d = m
