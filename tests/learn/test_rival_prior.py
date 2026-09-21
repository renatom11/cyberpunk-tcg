"""The inferred-list sampler (Stage 0, decision 3): worlds drawn from public evidence only.

``RivalPrior`` reads what ``me`` may know and draws an identity for every rival instance it may
not: face-down Legends from the Legends whose colour still fits, hidden hand and deck from the
possible pool at most three copies apiece. The search agents use it by default, and
``CPTCG_KNOWN_LIST=1`` restores the sampler that permuted the rival's true list.
"""

import pytest

from cptcg.agents.base import make_agent
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.enums import CardType, Zone
from cptcg.core.rng import Pcg32
from cptcg.core.view import determinize, info_key, knows_identity, unknown_to
from cptcg.learn.decks import sample_pair
from cptcg.learn.opponent import RivalPrior, colour_bounds, max_ram, possible_pool


def _mid_game(pool, seed=11, decisions=40):
    s = new_game(pool, sample_pair(pool, Pcg32(seed)), seed)
    ags = [make_agent("heuristic", seed * 2 + i) for i in (0, 1)]
    for p, a in enumerate(ags):
        a.new_game(seed, p)
    for _ in range(decisions):
        if s.over:
            break
        legal_actions(s)
        ch = s.pending
        if ch is None:
            break
        apply(s, ags[ch.player].act(s, ch))
    legal_actions(s)
    return s


def _snapshot(s):
    return (s.turn, s.active, list(s.i_zone), bytes(s.i_spent), bytes(s.i_lag), bytes(s.i_faceup),
            list(s.i_host), list(s.i_flags), [list(z) for z in s.z], [list(g) for g in s.gig],
            [list(f) for f in s.fixer], s.over, s.winner)


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_sampled_identities_are_legal_for_the_rivals_colour_class(pool, seed):
    s = _mid_game(pool, seed)
    for me in (0, 1):
        prior = RivalPrior(s, me)
        rival = 1 - me
        bounds = colour_bounds(s, me)
        caps = max_ram(bounds)
        pool_ids = possible_pool(pool, bounds)
        for k in range(5):
            ids = prior.sample(Pcg32(100 * seed + k, seq=7))
            names = set()
            counts: dict = {}
            for inst, cid in ids.items():
                assert s.i_owner[inst] == rival
                assert not knows_identity(s, me, inst), "a known card was re-identified"
                d = pool.defs[cid]
                if s.i_zone[inst] == Zone.LEGENDS:
                    assert d.type is CardType.LEGEND
                    assert caps[d.color] >= d.ram, "a Legend the colour caps exclude"
                    assert d.name not in names, "two face-down slots with one Legend"
                    names.add(d.name)
                else:
                    assert d.type is not CardType.LEGEND
                    assert d.id in pool_ids, "a card outside the possible pool"
                    counts[cid] = counts.get(cid, 0) + 1
            for cid, n in counts.items():
                assert n <= prior.allow[cid], "more copies than the seen count allows"
            # every hidden rival instance gets an identity unless the pool ran dry
            hidden = [i for i in unknown_to(s, me) if s.i_owner[i] == rival]
            assert set(ids) <= set(hidden)


@pytest.mark.parametrize("seed", [11, 12])
def test_an_inferred_world_keeps_the_public_state_and_the_coarse_key(pool, seed):
    s = _mid_game(pool, seed)
    me = s.pending.player
    prior = RivalPrior(s, me)
    for k in range(4):
        rng = Pcg32(seed + k, seq=3)
        w = determinize(s, me, rng, known_opponent_deck=False, identities=prior.sample(rng))
        assert _snapshot(w) == _snapshot(s), "a sampled world moved something public"
        assert info_key(w, me, known_opponent_deck=False) == info_key(s, me, known_opponent_deck=False)
        for inst in range(len(s.i_card)):
            if knows_identity(s, me, inst):
                assert w.i_card[inst] == s.i_card[inst], "a card I can identify changed"


def test_the_switch_is_read_from_the_environment(monkeypatch):
    import importlib
    import cptcg.agents.search.ismcts as I
    import cptcg.agents.search.plan as P
    monkeypatch.setenv("CPTCG_KNOWN_LIST", "1")
    importlib.reload(I)
    importlib.reload(P)
    assert I.IsmctsAgent.known_opponent_deck is True and P.PlanAgent.known_opponent_deck is True
    monkeypatch.setenv("CPTCG_KNOWN_LIST", "0")
    importlib.reload(I)
    importlib.reload(P)
    assert I.IsmctsAgent.known_opponent_deck is False and P.PlanAgent.known_opponent_deck is False


def test_the_search_samples_from_the_prior_unless_told_the_list_is_known(pool, monkeypatch):
    import cptcg.agents.search.ismcts as I
    monkeypatch.setattr(I.IsmctsAgent, "iterations", 12)
    seen = []
    real = I.determinize

    def spy(*a, **k):
        seen.append(k.get("identities") is not None)
        return real(*a, **k)
    monkeypatch.setattr(I, "determinize", spy)
    s = _mid_game(pool)
    me = s.pending.player
    monkeypatch.setattr(I.IsmctsAgent, "known_opponent_deck", False)
    ag = make_agent("ismcts", 3)
    ag.new_game(3, me)
    ag.act(s, s.pending)
    assert seen and all(seen), "the inferred mode did not pass sampled identities"
    seen.clear()
    monkeypatch.setattr(I.IsmctsAgent, "known_opponent_deck", True)
    ag = make_agent("ismcts", 3)
    ag.new_game(3, me)
    ag.act(s, s.pending)
    assert seen and not any(seen), "the known-list mode sampled from the prior"
