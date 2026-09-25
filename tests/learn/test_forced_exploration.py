import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import harvest  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.learn import decks as D  # noqa: E402
from cptcg.learn.experience import GameRecord  # noqa: E402
from cptcg.sim import runner  # noqa: E402


def test_the_harvest_loop_plays_the_runners_game():
    reg = load_default()
    a, b = D.sample_pair(reg, harvest.pair_rng(3, 0))
    gs = harvest.game_seed(3, 0)
    s = runner.play_game(reg, (a, b), ("heuristic", "random"), gs, DEFAULT_CONFIG, record=True)
    out = harvest.play_chunk((0, 1, 3, "heuristic", "random", None))
    rec = GameRecord.from_json(out["records"][0])
    assert list(rec.actions) == list(s.actions)
    assert out["games"] == 1 and out["forced"] == 0


def test_a_forced_game_replays_its_pair_up_to_the_forced_decision():
    out = harvest.play_chunk((0, 4, 5, "ismcts:4", "heuristic", None, 1.0, {}))
    recs = [GameRecord.from_json(r) for r in out["records"]]
    assert out["games"] == 4 and out["forced"] >= 3
    pairs = [(recs[k], recs[k + 1]) for k in range(len(recs) - 1)
             if "forced" in (recs[k + 1].meta or {}) and "forced" not in (recs[k].meta or {})]
    assert len(pairs) == out["forced"]
    for base, forced in pairs:
        f = forced.meta["forced"]
        assert base.meta["i"] == forced.meta["i"]
        ply = f["ply"]
        assert list(forced.actions[:ply]) == list(base.actions[:ply])
        assert forced.actions[ply] == f["forced"] != f["agent_choice"] == base.actions[ply]
        # the stored visits at the forced decision are the search's, taken before the override
        assert forced.visits[ply] == base.visits[ply]


def test_pick_forced_prefers_the_rarely_chosen():
    from cptcg.core.rng import Pcg32
    offered = [("x", "Play", ""), ("y", "Play", ""), ("z", "Play", "")]
    counts = {"x|Play|": 0, "y|Play|": 1000, "z|Play|": 0}
    rng = Pcg32(1, seq=1)
    got = [harvest.pick_forced(offered, 2, counts, rng) for _ in range(200)]
    assert 2 not in got and got.count(0) > 190
    assert harvest.pick_forced(offered[:1], 0, counts, rng) is None


def test_the_generator_searches_order_and_mulligan():
    from cptcg.agents.base import make_agent
    from cptcg.core.actions import ChoiceKind
    from cptcg.core.engine import apply, legal_actions, new_game
    reg = load_default()
    a, b = D.sample_pair(reg, harvest.pair_rng(9, 0))
    for name, searched in (("ismcts-explore:16", True), ("ismcts:16", False)):
        s = new_game(reg, (a, b), 77, DEFAULT_CONFIG)
        ag = make_agent(name, 1)
        ag.new_game(77, 0)
        seen = set()
        while s.turn == 0 or s.pending.kind in (ChoiceKind.ORDER, ChoiceKind.MULLIGAN):
            legal_actions(s)
            ch = s.pending
            if ch.kind not in (ChoiceKind.ORDER, ChoiceKind.MULLIGAN):
                break
            ag.me = ch.player
            idx = ag.act(s, ch)
            if len(ch.options) > 1:
                seen.add((ch.kind, bool(ag.last_visits)))
            apply(s, idx)
        assert seen and all(v is searched for _, v in seen)
