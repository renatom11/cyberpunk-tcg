"""The deck-pair sampler: legality, spread, determinism, and the held-out starters."""

import pytest

from cptcg.core.enums import CardType
from cptcg.core.rng import Pcg32
from cptcg.deck.builder import usable
from cptcg.deck.strategies import deck_profile
from cptcg.deck.validate import validate
from cptcg.learn.decks import (DEFAULT_MIX, HOLDOUT, SOURCES, holdout_decks, holdout_pairs,
                               is_holdout, normalised_mix, pick_source, sample_deck, sample_pair,
                               training_decks)


def sample_many(pool, n, seed=1234):
    rng = Pcg32(seed)
    return [sample_deck(pool, rng) for _ in range(n)]


# ------------------------------------------------------------------ legality
def test_every_sampled_deck_is_legal(pool):
    for d in sample_many(pool, 60):
        v = validate(d, pool)
        assert v.ok, f"{d.name}: {v}"


def test_every_sampled_pair_is_legal_and_distinctly_named(pool):
    rng = Pcg32(9)
    for _ in range(20):
        a, b = sample_pair(pool, rng)
        assert validate(a, pool).ok and validate(b, pool).ok
        assert a.name != b.name


def test_the_fixed_lists_are_legal(pool):
    for d in training_decks() + holdout_decks():
        assert validate(d, pool).ok, d.name


# ------------------------------------------------------------------ the held-out starters
def test_starters_never_appear_in_training_samples(pool):
    starters = {(tuple(sorted(d.legends)), tuple(sorted(d.main))) for d in holdout_decks()}
    names = {d.name for d in holdout_decks()} | set(HOLDOUT)
    for d in sample_many(pool, 250, seed=77):
        assert d.name not in names
        assert (tuple(sorted(d.legends)), tuple(sorted(d.main))) not in starters
        assert not is_holdout(d)


def test_the_sample_source_excludes_the_starters(pool):
    got = {d.name for d in training_decks()}
    assert got, "no sample_*.json decks found"
    assert not got & {d.name for d in holdout_decks()}
    for stem in HOLDOUT:
        assert stem not in got


def test_holdout_pairs_are_the_starters_in_both_seats(pool):
    pairs = holdout_pairs(pool)
    a, b = holdout_decks()
    assert pairs == ((a, b), (b, a))
    for x, y in pairs:
        assert validate(x, pool).ok and validate(y, pool).ok
    assert is_holdout(a) and is_holdout(b)


# ------------------------------------------------------------------ determinism
def test_the_same_seed_gives_the_same_pair(pool):
    def once():
        rng = Pcg32(31337)
        return [sample_pair(pool, rng) for _ in range(6)]
    left, right = once(), once()
    assert [(a.name, a.legends, a.main, b.name, b.legends, b.main) for a, b in left] == \
           [(a.name, a.legends, a.main, b.name, b.legends, b.main) for a, b in right]


def test_different_seeds_give_different_pairs(pool):
    a = sample_pair(pool, Pcg32(1))
    b = sample_pair(pool, Pcg32(2))
    assert (a[0].main, a[1].main) != (b[0].main, b[1].main)


# ------------------------------------------------------------------ the mix
def test_mix_is_named_normalised_and_checked():
    table = normalised_mix()
    assert [k for k, _ in table] == list(SOURCES)
    assert table[-1][1] == 1.0
    assert sorted(DEFAULT_MIX) == sorted(SOURCES)
    with pytest.raises(ValueError):
        normalised_mix({"heruistic": 1.0})
    with pytest.raises(ValueError):
        normalised_mix({"random": 0.0})


def test_every_source_is_actually_drawn(pool):
    rng = Pcg32(5)
    seen = {}
    for _ in range(600):
        src = pick_source(rng)
        seen[src] = seen.get(src, 0) + 1
    assert set(seen) == set(SOURCES)
    for k, w in DEFAULT_MIX.items():           # within a wide band: this is a smoke test, not a fit
        assert 0.5 * w < seen[k] / 600 < 2.0 * w


def test_a_narrowed_mix_only_draws_what_it_names(pool):
    rng = Pcg32(6)
    for _ in range(15):
        d = sample_deck(pool, rng, mix={"sample": 1.0})
        assert d.name in {x.name for x in training_decks()}


# ------------------------------------------------------------------ spread
def test_samples_cover_a_wide_spread_of_the_card_pool(pool):
    decks = sample_many(pool, 90, seed=4242)
    main_pool = {d.id for d in usable(pool) if d.type is not CardType.LEGEND}
    legend_pool = {d.id for d in usable(pool) if d.type is CardType.LEGEND}
    cards = set()
    legends = set()
    triples = set()
    for d in decks:
        cards |= set(d.main)
        legends |= set(d.legends)
        triples.add(tuple(sorted(d.legends)))
    assert len(cards) / len(main_pool) > 0.75, f"{len(cards)}/{len(main_pool)} of the pool"
    assert len(legends) / len(legend_pool) > 0.7, f"{len(legends)}/{len(legend_pool)} Legends"
    assert len(triples) > 0.6 * len(decks), f"{len(triples)} triples in {len(decks)} decks"


def test_samples_cover_a_wide_spread_of_deck_shape(pool):
    """Nominal variety is easy; ``deck_profile`` is what says the *shapes* really differ."""
    profiles = [deck_profile(d, pool) for d in sample_many(pool, 90, seed=808)]
    span = {k: (min(p[k] for p in profiles), max(p[k] for p in profiles)) for k in profiles[0]}
    lo, hi = span["mean_cost"]
    assert lo < 3.0 and hi > 4.0, span["mean_cost"]
    lo, hi = span["unit_share"]
    assert lo < 0.40 and hi > 0.70, span["unit_share"]
    lo, hi = span["sell_share"]
    assert lo < 0.30 and hi > 0.70, span["sell_share"]
    lo, hi = span["mean_unit_power"]
    assert lo < 3.5 and hi > 7.0, span["mean_unit_power"]
    lo, hi = span["blockers"]
    assert lo <= 1 and hi >= 6, span["blockers"]
    lo, hi = span["removal"]
    assert lo <= 2 and hi >= 12, span["removal"]
    sizes = {len(d.main) for d in sample_many(pool, 60, seed=808)}
    assert len(sizes) > 1, sizes


def test_deck_sizes_stay_legal(pool):
    for d in sample_many(pool, 40, seed=17):
        assert 40 <= len(d.main) <= 50
