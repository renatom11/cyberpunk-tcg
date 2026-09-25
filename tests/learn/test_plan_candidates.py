from cptcg.agents.base import make_agent
from cptcg.cards.registry import load_default
from cptcg.core.actions import ChoiceKind
from cptcg.core.config import DEFAULT_CONFIG
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import Pcg32
from cptcg.learn.decks import sample_pair
from cptcg.sim import runner


def _to_main(seed: int, turns: int):
    reg = load_default()
    a, b = sample_pair(reg, Pcg32(seed, seq=1))
    s = new_game(reg, (a, b), seed, DEFAULT_CONFIG)
    h = [make_agent("heuristic", seed * 2 + k) for k in (0, 1)]
    for p, ag in enumerate(h):
        ag.new_game(seed, p)
    while not s.over:
        legal_actions(s)
        ch = s.pending
        if ch.kind is ChoiceKind.MAIN and s.turn >= turns and len(ch.options) > 2:
            return s
        apply(s, h[ch.player].act(s, ch))
    return None


def test_the_plan_stage_boosts_the_first_actions_of_its_lines():
    s = _to_main(21, 3)
    assert s is not None
    ag = make_agent("ismcts-plan:16", 5)
    ag.new_game(21, s.pending.player)
    first = ag._plan_first_actions(s, s.pending)
    assert first and first <= set(s.pending.options) and len(first) <= 3
    seen = {}
    orig = ag._select

    def spy(node, w, ch):
        i = orig(node, w, ch)
        if node.boost and node.prior is not None:
            seen.update(node.prior)
            seen["_boost"] = node.boost
        return i

    ag._select = spy
    ag._planned_turn = -1
    ag.act(s.clone(), s.pending)
    boost = seen.pop("_boost")
    assert abs(sum(seen.values()) - 1.0) < 1e-6
    assert min(seen[a] for a in boost) >= ag.plan_mass / len(boost) - 1e-12


def test_plan_agents_finish_games_and_plain_ismcts_has_no_boost():
    reg = load_default()
    a, b = sample_pair(reg, Pcg32(3, seq=1))
    s = runner.play_game(reg, (a, b), ("ismcts-explore-plan:8", "heuristic"), 3, DEFAULT_CONFIG)
    assert s.over
    assert make_agent("ismcts", 1).plan_candidates == 0
