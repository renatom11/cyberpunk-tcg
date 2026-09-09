from pathlib import Path

import pytest

from cptcg.cards.registry import load_default
from cptcg.core.enums import Color
from cptcg.deck.decklist import Decklist
from cptcg.deck.validate import ram_limits, validate

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def pool():
    return load_default()


def test_pool_loads_151_cards(pool):
    assert len(pool) == 151


def test_ram_limits_follow_the_rulebook_example(pool):
    legs = [pool.get("goro-takemura-hands-unclean"), pool.get("saburo-arasaka-stubborn-patriarch"),
            pool.get("yorinobu-arasaka-embracing-destruction")]
    lim = ram_limits(legs)
    assert lim[Color.GREEN] == 4 and lim[Color.RED] == 2 and lim[Color.BLUE] == 0


def test_sample_decks_are_legal(pool):
    for fn in ("sample_arasaka.json", "sample_mercs.json"):
        deck = Decklist.load(ROOT / "data/decks" / fn)
        v = validate(deck, pool, allow_unscripted=True)
        assert v.ok, v


def test_ram_violation_is_rejected(pool):
    deck = Decklist.load(ROOT / "data/decks/sample_arasaka.json")
    bad = Decklist.from_counts("bad", list(deck.legends), {**deck.counts(), "towerfall": 1})  # Blue 4
    v = validate(bad, pool, allow_unscripted=True)
    assert any("towerfall" in e and "Blue RAM 4 exceeds limit 0" in e for e in v.errors)


def test_copy_limit_size_and_legend_rules(pool):
    deck = Decklist.load(ROOT / "data/decks/sample_mercs.json")
    counts = deck.counts()
    first = next(iter(counts))
    too_many = Decklist.from_counts("x", list(deck.legends), {**counts, first: 4})
    assert any("4 copies" in e for e in validate(too_many, pool, allow_unscripted=True).errors)
    dup = Decklist.from_counts("x", [deck.legends[0], deck.legends[0], deck.legends[1]], counts)
    assert any("unique" in e for e in validate(dup, pool, allow_unscripted=True).errors)
    small = Decklist.from_counts("x", list(deck.legends), {first: 3})
    assert any("40-50" in e for e in validate(small, pool, allow_unscripted=True).errors)


def test_unscripted_and_unverified_cards_are_refused_by_default(pool):
    deck = Decklist.load(ROOT / "data/decks/sample_mercs.json")
    v = validate(deck, pool)
    assert not v.ok and any("no script" in e for e in v.errors)
    with_placeholder = Decklist.from_counts("x", list(deck.legends),
                                            {**deck.counts(), "adam-smasher-metal-over-meat": 1})
    v = validate(with_placeholder, pool, allow_unscripted=True)
    assert any("not verified" in e for e in v.errors)
    assert validate(with_placeholder, pool, allow_unscripted=True, allow_unverified=True).errors == [
        e for e in validate(with_placeholder, pool, allow_unscripted=True, allow_unverified=True).errors
        if "RAM" in e]
