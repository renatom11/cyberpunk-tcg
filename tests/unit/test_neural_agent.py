"""The learned-value agent: same search as the frozen heuristic, different scorer.

The point of these tests is the word *same*. If ``neural`` ever stops inheriting the heuristic's
dispatch, its mulligan rule or its preview policy, then an arena result between the two stops
being a measurement of the value function and starts being a measurement of two different agents —
and nothing in a win rate would say so.
"""

import random

import pytest

from cptcg.agents import heuristic as H
from cptcg.agents import neural as N
from cptcg.agents.base import AGENTS, make_agent
from cptcg.agents.neural import NeuralAgent
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import Pcg32
from cptcg.learn.decks import sample_pair
from cptcg.learn.features import NFEAT, features
from cptcg.learn.model import ValueModel


@pytest.fixture(scope="module")
def toy(tmp_path_factory):
    """A small random value head. Random is enough: every property here is about *plumbing*, and
    a fitted model would make these tests depend on a training run."""
    rng = random.Random(17)
    hidden = 8
    m = ValueModel(
        hidden=hidden,
        w1=tuple(tuple(rng.uniform(-0.5, 0.5) for _ in range(NFEAT)) for _ in range(hidden)),
        b1=tuple(rng.uniform(-0.2, 0.2) for _ in range(hidden)),
        w2=tuple(rng.uniform(-1.0, 1.0) for _ in range(hidden)),
        b2=0.1, header={"run": {"name": "toy"}})
    return m.save(tmp_path_factory.mktemp("w") / "toy.json")


@pytest.fixture
def agent(toy):
    class Toy(NeuralAgent):
        name = "neural-toy"
        weights_path = toy
    return Toy


# ------------------------------------------------------------------ registration
def test_make_agent_builds_it_and_base_lists_it():
    a = make_agent("neural", 3)
    assert isinstance(a, NeuralAgent) and a.name == "neural"
    assert "neural" in AGENTS
    from cptcg.learn.arena import known_agents
    assert "neural" in known_agents()


def test_it_does_not_claim_to_sample_hidden_information():
    """``arena exploit`` measures what determinization costs, and refuses an agent that does not
    do any. Claiming otherwise here would produce a meaningless exploit number."""
    assert make_agent("neural").uses_determinization is False


# ------------------------------------------------------------------ same search
@pytest.mark.parametrize("name", ["act", "_keep", "_resolve"])
def test_the_search_is_the_frozen_heuristics_own_code(name):
    assert getattr(NeuralAgent, name) is getattr(H.HeuristicAgent, name)


def test_only_the_scoring_line_differs():
    """``_greedy`` is the one method that is a copy rather than an inheritance, and the copy must
    stay line-for-line the heuristic's except for the score."""
    import inspect

    def code(fn):
        out = []
        for ln in inspect.getsource(fn).splitlines():
            ln = ln.split("#")[0].strip()        # inline comments and noqa markers differ
            if ln and not ln.startswith('"'):
                out.append(ln)
        return out

    a_code, b_code = code(H.HeuristicAgent._greedy), code(NeuralAgent._greedy)
    # the docstrings differ and the scoring line differs; the loop body must not
    for marker in ("c = s.clone()", "c.rng = Pcg32(rng.next_u32(), seq=3)", "apply(c, i)",
                   "self._resolve(c, depth)", "if v > best_v:", "best_i, best_v = i, v",
                   "key = _equiv_key(s, options[i])", "seen.add(key)", "best_i, best_v = 0, -1e18",
                   "for i in range(len(options)):", "return best_i"):
        assert marker in a_code and marker in b_code, marker
    assert sum(1 for ln in a_code if "evaluate(" in ln) == 1
    assert sum(1 for ln in b_code if "self._value(" in ln) == 1


# ------------------------------------------------------------------ it plays
def test_it_plays_a_whole_game_against_the_heuristic(pool, agent):
    from cptcg.core.config import DEFAULT_CONFIG

    decks = sample_pair(pool, Pcg32(101))
    s = new_game(pool, decks, 55, DEFAULT_CONFIG)
    ags = [agent(1), make_agent("heuristic", 2)]
    for p, ag in enumerate(ags):
        ag.new_game(55, p)
    guard = 0
    while not s.over and guard < 4000:
        guard += 1
        legal_actions(s)
        ch = s.pending
        apply(s, ags[ch.player].act(s, ch))
    assert s.over and s.turn > 1


def play_actions(pool, agent_cls, seed: int) -> list[int]:
    from cptcg.core.config import DEFAULT_CONFIG

    decks = sample_pair(pool, Pcg32(202))
    s = new_game(pool, decks, seed, DEFAULT_CONFIG)
    ags = [agent_cls(seed * 2 + p) for p in (0, 1)]
    for p, ag in enumerate(ags):
        ag.new_game(seed, p)
    out = []
    guard = 0
    while not s.over and guard < 4000:
        guard += 1
        legal_actions(s)
        ch = s.pending
        i = ags[ch.player].act(s, ch)
        out.append(i)
        apply(s, i)
    return out


def test_it_is_deterministic_from_its_seed(pool, agent):
    assert play_actions(pool, agent, 31) == play_actions(pool, agent, 31)
    assert play_actions(pool, agent, 31) != play_actions(pool, agent, 32)


# ------------------------------------------------------------------ scoring
def test_a_decided_preview_short_circuits_before_the_model_is_consulted(agent):
    """A finished game is worth ``+-WIN`` whatever the model thinks, and the model is not asked.

    ``evaluate()`` does the same with ``w["win"]``. A model that has never been shown a terminal
    position should not be invited to express an opinion about one.
    """
    class Explode:
        def raw(self, _x):
            raise AssertionError("the model was consulted about a finished game")

    class Fake:
        over = True
        winner = 1

    a = agent(0)
    a.me = 1
    assert a._value(Fake(), Explode()) == N.WIN
    Fake.winner = 0
    assert a._value(Fake(), Explode()) == -N.WIN


def test_the_score_is_invariant_under_determinization(pool, agent):
    """The new code in this agent is ``features() -> ValueModel.raw``. ``features`` is proven not
    to read hidden identities (``tests/learn/test_features.py``); this checks that the model on top
    of it cannot reintroduce a leak."""
    determinize = pytest.importorskip("cptcg.core.view").determinize
    from cptcg.core.config import DEFAULT_CONFIG

    decks = sample_pair(pool, Pcg32(7))
    s = new_game(pool, decks, 8, DEFAULT_CONFIG)
    a = agent(0)
    checked = 0
    for step in range(60):
        legal_actions(s)
        if s.over:
            break
        ch = s.pending
        a.me = ch.player
        if step % 3 == 0:
            base = a._value(s, a.model)
            for t in range(2):
                c = determinize(s, ch.player, Pcg32(step * 13 + t))
                assert a._value(c, a.model) == base
                checked += 1
        apply(s, a._greedy(s, ch, 1) if len(ch.options) > 1 else 0)
    assert checked >= 20


@pytest.mark.skipif(not N.WEIGHTS_PATH.exists(), reason="no weights have been fitted")
def test_the_tie_break_noise_is_small_beside_the_logit_it_actually_perturbs(pool):
    """The heuristic's noise reaches 0.0999 on a score whose median spread across one decision's
    options is 7.40 points — 1.35% of it. A win probability lives in [0, 1] and the *shipped*
    model's logit spread over the same decisions is about 0.6, so copying the heuristic's constant
    would swamp the signal and this agent would play at random.

    The constant is therefore in log-odds and set from that measurement
    (``tools/fit_eval.py diagnose``). This test re-measures the spread on the real weights — the
    only model whose spread the constant is allowed to be justified by — and fails if the ratio
    ever climbs above the heuristic's own.
    """
    a = make_agent("neural", 0)
    decks = sample_pair(pool, Pcg32(9))
    s = new_game(pool, decks, 21)
    spreads = []
    for _ in range(80):
        legal_actions(s)
        if s.over:
            break
        ch = s.pending
        a.me = ch.player
        vals = []
        for i in range(min(8, len(ch.options))):
            c = s.clone()
            c.rng = Pcg32(i + 1, seq=3)
            apply(c, i)
            a._resolve(c, 1)
            if not c.over:
                vals.append(a.model.raw(features(c, ch.player)))
        if len(vals) > 1:
            spreads.append(max(vals) - min(vals))
        apply(s, 0)
    spreads.sort()
    median = spreads[len(spreads) // 2]
    assert median > 0.05, median                       # the argmax has something to rank on at all
    assert NeuralAgent.noise * 999 < median / 50, (NeuralAgent.noise, median)


# ------------------------------------------------------------------ the shipped weights
@pytest.mark.skipif(not N.WEIGHTS_PATH.exists(), reason="no weights have been fitted")
def test_the_shipped_agent_plays_with_the_shipped_weights(pool):
    from cptcg.core.config import DEFAULT_CONFIG

    decks = sample_pair(pool, Pcg32(303))
    s = new_game(pool, decks, 12, DEFAULT_CONFIG)
    ags = [make_agent("neural", 1), make_agent("heuristic", 2)]
    for p, ag in enumerate(ags):
        ag.new_game(12, p)
    guard = 0
    while not s.over and guard < 4000:
        guard += 1
        legal_actions(s)
        ch = s.pending
        apply(s, ags[ch.player].act(s, ch))
    assert s.over
