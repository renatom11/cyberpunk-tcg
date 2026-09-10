"""Bulk deck generation: many legal, distinct decks; screening ranks them."""
from cptcg.cards.registry import load_default
from cptcg.deck.generate import generate_decks, screen_decks, similarity
from cptcg.deck.validate import validate


def test_generate_many_distinct_legal_decks(pool):
    reg = pool
    batch = generate_decks(reg, 18, seed=7)
    decks = batch.decks
    assert len(decks) == 18
    assert all(validate(d, reg).ok for d in decks)
    assert len({d.name for d in decks}) == 18
    # All six personalities take part and the batch spreads over the Legend space.
    assert {d.meta["strategy"] for d in decks} == {"aggro", "control", "economy", "gig", "synergy", "balanced"}
    assert len(batch.triples) >= 10
    for i, a in enumerate(decks):
        for b in decks[i + 1:]:
            assert similarity(a, b) <= 0.7, (a.name, b.name)


def test_generate_pinned_legends_and_subset(pool):
    reg = pool
    legends = ["goro-takemura-hands-unclean", "saburo-arasaka-stubborn-patriarch", "yorinobu-arasaka-embracing-destruction"]
    batch = generate_decks(reg, 4, strategies=["aggro", "control"], seed=1, legends=legends)
    assert all(list(d.legends) == legends for d in batch.decks)
    assert [d.meta["strategy"] for d in batch.decks] == ["aggro", "control", "aggro", "control"]
    assert batch.decks[0].name.startswith("gen001-aggro-goro-saburo-yorinobu")


def test_screen_ranks_by_win_rate(pool):
    reg = pool
    batch = generate_decks(reg, 3, strategies=["aggro"], seed=2)
    ranked = screen_decks(reg, batch.decks, batch.decks[:2], games_per_opponent=4, agent="random", seed=1, workers=1)
    assert len(ranked) == 3
    assert [r.rate for r in ranked] == sorted((r.rate for r in ranked), reverse=True)
    assert ranked[-1].games > 0 and all(0 <= r.rate <= 1 for r in ranked)
