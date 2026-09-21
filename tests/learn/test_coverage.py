"""Decision coverage (Stage 0): what was offered, what was chosen, counted by card id and
action kind so it is independent of replay and of the action index."""

import json

from cptcg.agents.base import make_agent
from cptcg.core.actions import ChoiceKind
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import Pcg32
from cptcg.learn.coverage import Coverage, decision_record, option_key, starvation
from cptcg.learn.decks import sample_pair


def _play(pool, seed, cov, hand_count):
    s = new_game(pool, sample_pair(pool, Pcg32(seed)), seed)
    ags = [make_agent("heuristic", seed * 2 + i) for i in (0, 1)]
    for p, a in enumerate(ags):
        a.new_game(seed, p)
    while not s.over:
        legal_actions(s)
        ch = s.pending
        if ch is None:
            break
        i = ags[ch.player].act(s, ch)
        rec = decision_record(s, ch, i)
        cov.add(rec)
        hand_count["decisions"] += 1
        hand_count["offered"] += len(ch.options)
        if ch.kind is ChoiceKind.MAIN:
            hand_count["main"] += 1
        apply(s, i)
    return s


def test_counts_equal_a_hand_count_over_two_games(pool):
    cov = Coverage()
    hand = {"decisions": 0, "offered": 0, "main": 0}
    for seed in (5, 6):
        _play(pool, seed, cov, hand)
    assert cov.decisions == hand["decisions"]
    assert sum(cov.offered.values()) == hand["offered"]
    assert sum(cov.chosen.values()) == hand["decisions"]
    assert cov.kind_decisions[int(ChoiceKind.MAIN)] == hand["main"]
    for key, n in cov.chosen.items():
        assert n <= cov.offered[key], "chosen more often than offered"


def test_json_round_trip_and_merge(pool):
    a, b = Coverage(), Coverage()
    hand = {"decisions": 0, "offered": 0, "main": 0}
    _play(pool, 7, a, hand)
    _play(pool, 8, b, hand)
    d = json.loads(json.dumps(a.to_json()))
    back = Coverage.from_json(d)
    assert back.offered == a.offered and back.chosen == a.chosen and back.decisions == a.decisions
    a.merge(b)
    assert a.decisions == hand["decisions"]
    assert sum(a.offered.values()) == hand["offered"]


def test_option_keys_carry_card_ids_and_kinds_not_indices(pool):
    s = new_game(pool, sample_pair(pool, Pcg32(3)), 3)
    legal_actions(s)
    ch = s.pending
    keys = [option_key(s, ch, a) for a in ch.options]
    for k in keys:
        assert len(k) == 3 and isinstance(k[1], str)
    kinds = {k[1] for k in keys}
    assert kinds, kinds


def test_starvation_lists_offered_but_never_chosen():
    cov = Coverage()
    cov.offered[("x", "Play", "")] = 30
    cov.offered[("y", "Play", "")] = 30
    cov.chosen[("y", "Play", "")] = 5
    cov.offered[("z", "Play", "")] = 3
    out = starvation(cov, min_offered=20, max_chosen=0)
    assert out == [(("x", "Play", ""), 30, 0)]
