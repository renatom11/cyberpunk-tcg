"""Bulk deck generation: many legal, distinct decks; screening ranks them."""
import pytest

from cptcg.cards.registry import load_default
from cptcg.core.rng import Pcg32
from cptcg.deck.archetypes import ArchetypeStore
from cptcg.deck.generate import generate_decks, screen_decks, similarity
from cptcg.deck.strategies import Explorer
from cptcg.deck.validate import validate


@pytest.fixture(scope="module")
def store(pool):
    """A store with learned archetypes, from Explorer decks given made-up records."""
    rng = Pcg32(17)
    st = ArchetypeStore(reg=pool)
    for i in range(12):
        st.add(Explorer().build(pool, None, rng, name=f"s{i}"), None, games=30, wins=8 + i, bt=0.9 + 0.02 * i)
    assert st.refit()
    return st


def test_generate_many_distinct_legal_decks(pool):
    reg = pool
    batch = generate_decks(reg, 18, seed=7)
    decks = batch.decks
    assert len(decks) == 18
    assert all(validate(d, reg).ok for d in decks)
    assert len({d.name for d in decks}) == 18
    # Without a store every deck explores, and the batch spreads over the Legend space.
    assert {d.meta["archetype"] for d in decks} == {"exploring"}
    assert len(batch.triples) >= 10
    for i, a in enumerate(decks):
        for b in decks[i + 1:]:
            assert similarity(a, b) <= 0.7, (a.name, b.name)


def test_generate_pinned_legends_and_subset(pool, store):
    reg = pool
    legends = ["goro-takemura-hands-unclean", "saburo-arasaka-stubborn-patriarch", "yorinobu-arasaka-embracing-destruction"]
    a = store.ranked()[0]
    batch = generate_decks(reg, 4, archetypes=["explorer", a.id], seed=1, legends=legends, store=store)
    assert all(list(d.legends) == legends for d in batch.decks)
    assert [d.meta["archetype"] for d in batch.decks] == ["exploring", a.name, "exploring", a.name]
    assert batch.decks[0].name.startswith("gen001-explorer-goro-saburo-yorinobu")
    assert batch.decks[1].name.startswith(f"gen002-{a.id}-goro-saburo-yorinobu")


def test_generate_cycles_every_learned_archetype_plus_an_explorer(pool, store):
    n = len(store.archetypes) + 1
    batch = generate_decks(pool, n, seed=3, store=store)
    kinds = [d.meta["archetype"] for d in batch.decks]
    assert set(kinds) == {a.name for a in store.archetypes} | {"exploring"}
    assert all(validate(d, pool).ok for d in batch.decks)


def test_screen_ranks_by_win_rate(pool):
    reg = pool
    batch = generate_decks(reg, 3, archetypes=["explorer"], seed=2)
    ranked = screen_decks(reg, batch.decks, batch.decks[:2], games_per_opponent=4, agent="random", seed=1, workers=1)
    assert len(ranked) == 3
    assert [r.rate for r in ranked] == sorted((r.rate for r in ranked), reverse=True)
    assert ranked[-1].games > 0 and all(0 <= r.rate <= 1 for r in ranked)
