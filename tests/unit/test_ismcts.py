"""The search agent: that it searches a sampled world rather than the real one, that it leaves the
game alone, and that it finds a line the greedy agent cannot.

The last one is the point of the whole stage. ``agents/neural.py`` is greedy per decision and the
preview it scores is forbidden from running past the end of the turn, so a line whose value only
appears once several of its moves are on the board is invisible to it at any strength of evaluation.
"""

import pytest

from cptcg.agents.base import CHEAT_PREFIX, make_agent
from cptcg.agents.search.ismcts import IsmctsAgent
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import Pcg32
from cptcg.core.view import determinize, info_key
from cptcg.learn.decks import sample_pair


def snapshot(s):
    """Every mutable array, as tests/props/test_determinization.py does it. ``i_card`` is excluded:
    it is the one list a sampled world is allowed to differ in."""
    return (s.turn, s.active, list(s.i_zone), bytes(s.i_spent), bytes(s.i_lag), bytes(s.i_faceup),
            list(s.i_host), list(s.i_flags), list(s.i_known), [list(z) for z in s.z],
            [list(f) for f in s.fixer], [list(g) for g in s.gig], list(s.temp_power), list(s.mods),
            set(s.used), list(s.played), list(s.drawn), list(s.once), list(s.turns_taken),
            s.over, s.winner)


def mid_game(pool, seed=11, decisions=40, fast=8):
    """A real position, with the search agent wired up cheaply."""
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


@pytest.fixture
def small(monkeypatch):
    """A search small enough for a unit test. The behaviour under test is not the strength."""
    monkeypatch.setattr(IsmctsAgent, "iterations", 24)
    return IsmctsAgent


# ------------------------------------------------------------------ the contract
def test_it_is_registered_and_can_be_asked_to_cheat(small):
    assert make_agent("ismcts").name == "ismcts"
    cheat = make_agent(CHEAT_PREFIX + "ismcts")
    assert cheat.cheating and cheat.uses_determinization
    assert not make_agent("ismcts").cheating


def test_it_returns_a_legal_index_at_every_decision_of_a_whole_game(pool, small):
    s = new_game(pool, sample_pair(pool, Pcg32(5)), 5)
    ags = [make_agent("ismcts", 1), make_agent("heuristic", 2)]
    for p, a in enumerate(ags):
        a.new_game(5, p)
    n = 0
    while not s.over and n < 400:
        legal_actions(s)
        ch = s.pending
        if ch is None:
            break
        i = ags[ch.player].act(s, ch)
        assert isinstance(i, int) and 0 <= i < len(ch.options), (i, len(ch.options))
        apply(s, i)
        n += 1
    assert s.over, "the game did not finish"


def test_searching_does_not_touch_the_game(pool, small):
    """The search runs on clones. If it mutated the live state the game would diverge from its own
    replay, which is the one failure the golden games cannot catch here."""
    s = mid_game(pool)
    before = snapshot(s)
    a = make_agent("ismcts", 3)
    a.new_game(3, s.pending.player)
    a.act(s, s.pending)
    assert snapshot(s) == before
    assert list(s.i_card) == list(s.i_card)          # identities untouched by the sampler


def test_the_same_seed_searches_the_same_way(pool, small):
    s = mid_game(pool)
    picks = []
    for _ in range(2):
        a = make_agent("ismcts", 9)
        a.new_game(9, s.pending.player)
        picks.append(a.act(s, s.pending))
    assert picks[0] == picks[1]


def test_a_sampled_world_is_in_the_same_information_set(pool, small):
    """What the agent actually searches. determinize's own properties are covered in
    tests/props/test_determinization.py; this pins that the agent uses it rather than the truth."""
    s = mid_game(pool)
    me = s.pending.player
    w = determinize(s, me, Pcg32(4))
    assert info_key(w, me) == info_key(s, me)
    assert w is not s and w.i_card is not s.i_card


def test_the_honest_agent_samples_a_world_and_the_cheat_reads_the_real_one(pool, small, monkeypatch):
    """The contract, tested where it lives rather than through the choice it produces.

    Asking instead for the two to *pick differently* is not a real test: at any budget they agree on
    most positions, because most positions do not turn on what the rival is holding. Counting the
    calls is exact — the honest agent samples once per iteration and the cheat never samples at all.
    """
    import cptcg.agents.search.ismcts as M
    calls = []
    real = M.determinize
    monkeypatch.setattr(M, "determinize", lambda *a, **k: (calls.append(1), real(*a, **k))[1])

    s = mid_game(pool)
    me = s.pending.player
    honest = make_agent("ismcts", 2)
    honest.new_game(2, me)
    honest.act(s, s.pending)
    assert len(calls) == M.IsmctsAgent.iterations, (len(calls), M.IsmctsAgent.iterations)

    calls.clear()
    cheat = make_agent(CHEAT_PREFIX + "ismcts", 2)
    cheat.new_game(2, me)
    cheat.act(s, s.pending)
    assert calls == [], "the cheating variant sampled a world instead of reading the true state"


# ------------------------------------------------------------------ the point of the stage
@pytest.mark.skipif(not IsmctsAgent.weights_path.exists(), reason="no weights have been fitted")
def test_it_plays_a_two_move_line_where_the_first_move_gains_nothing(pool):
    """``gear-before-the-raid`` is the smallest position that needs a *sequence*.

    Attacking now steals one Gig, which is the biggest thing on the board and what a one-ply agent
    takes. Equipping the +2 Gear first is worth almost nothing by itself, but it lifts the attacker
    to 10 power, and two Gigs is the game. The agent has to play both moves, in order, and the test
    asserts the line rather than the outcome so that a win by some other route does not pass it.

    This is deliberately **not** a claim that the search beats the greedy agent overall. It does not
    yet; the suite score and what it cost are in docs/learning.md.
    """
    from cptcg.learn import delayed
    suite = delayed.load_suite(delayed.SUITE_PATH)
    entry = next(e for e in suite["positions"] if e["id"] == "gear-before-the-raid")
    s = delayed.build_entry(pool, entry)
    me = entry.get("player", s.pending.player)
    horizon = delayed.entry_horizon(entry)
    for sd in delayed.SCORE_SEEDS[:3]:
        won, line = delayed.play_turn(s, me, "ismcts", seed=sd, max_turns=horizon)
        played = replay_labels(pool, entry, me, line)
        assert won, (sd, played)
        assert any("Mantis Blades" in x for x in played), (sd, played)      # the setup move
        assert any(x.startswith("Attack") for x in played), (sd, played)    # and the payoff
        assert next(i for i, x in enumerate(played) if "Mantis Blades" in x) \
             < next(i for i, x in enumerate(played) if x.startswith("Attack")), (sd, played)


def replay_labels(pool, entry, me, line):
    """The chosen line as readable actions, replayed against a fresh copy of the position."""
    from cptcg.learn import delayed
    from cptcg.web.view import _label
    c = delayed.build_entry(pool, entry)
    out = []
    for idx in line:
        legal_actions(c)
        if c.pending is None or c.pending.player != me:
            break
        out.append(_label(c, c.pending.options[idx])[0])
        apply(c, idx)
    return out
