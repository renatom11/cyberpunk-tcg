"""Token view for the card-aware model (Stage 0): stdlib, seat-relative, and invariant under
a determinization of what the seat cannot see."""

from cptcg.agents.base import make_agent
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import Pcg32
from cptcg.core.view import determinize, knows_identity
from cptcg.learn import tokens as T
from cptcg.learn.decks import sample_pair
from cptcg.learn.policy import NAFEAT


def _mid(pool, seed=21, decisions=30):
    s = new_game(pool, sample_pair(pool, Pcg32(seed)), seed)
    ags = [make_agent("heuristic", seed * 2 + i) for i in (0, 1)]
    for p, a in enumerate(ags):
        a.new_game(seed, p)
    for _ in range(decisions):
        legal_actions(s)
        ch = s.pending
        if s.over or ch is None:
            break
        apply(s, ags[ch.player].act(s, ch))
    legal_actions(s)
    return s


def test_the_layout_digest_is_pinned():
    assert T.tokens_digest() == "1c4b67e7c9000efc", "token layout moved: bump the pin and refit"


def test_shapes(pool):
    s = _mid(pool)
    me = s.pending.player
    d = T.decision_tokens(s, me, s.pending)
    assert all(len(t) == len(T.CARD_TOKEN) for t in d["cards"])
    assert all(len(t) == len(T.DIE_TOKEN) for t in d["dice"])
    assert len(d["context"]) == len(T.CONTEXT)
    assert len(d["aggregates"]) == 114
    assert len(d["belief_deck"]) == 124 and len(d["belief_legends"]) == 27
    assert len(d["options"]) == len(s.pending.options)
    assert all(len(o) == len(T.OPTION_TOKEN) + NAFEAT for o in d["options"])


def test_only_identifiable_cards_are_tokens_and_hidden_ones_are_not(pool):
    s = _mid(pool)
    me = s.pending.player
    toks = T.card_tokens(s, me)
    rival = 1 - me
    hidden_rival = sum(1 for i in range(len(s.i_card)) if s.i_owner[i] == rival and not knows_identity(s, me, i))
    assert hidden_rival > 0
    n_known_rival = sum(1 for i in range(len(s.i_card)) if s.i_owner[i] == rival and knows_identity(s, me, i))
    assert sum(1 for t in toks if t[2] == 1) == n_known_rival


def test_tokens_are_invariant_under_determinization(pool):
    for seed in (21, 22, 23):
        s = _mid(pool, seed)
        me = s.pending.player
        d = T.decision_tokens(s, me, s.pending)
        for k in range(3):
            w = determinize(s, me, Pcg32(seed * 10 + k, seq=3))
            d2 = T.decision_tokens(w, me, w.pending)
            assert sorted(d2["cards"]) == sorted(d["cards"])
            assert d2["dice"] == d["dice"] and d2["context"] == d["context"]
            assert d2["belief_deck"] == d["belief_deck"] and d2["belief_legends"] == d["belief_legends"]
            assert d2["options"] == d["options"]


def test_belief_counts_cannot_exceed_three_and_exclude_seen_copies(pool):
    s = _mid(pool)
    me = s.pending.player
    deck, legs = T.belief(s, me)
    assert max(deck) <= 3 and min(deck) >= 0
    assert set(legs) <= {0, 1}
    rival = 1 - me
    for i in range(len(s.i_card)):
        if s.i_owner[i] == rival and knows_identity(s, me, i):
            d = pool.defs[s.i_card[i]]
            if d.type.name == "LEGEND":
                assert legs[[x for x in pool.defs if x.type.name == "LEGEND"].index(d)] == 0
