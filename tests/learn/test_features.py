"""The state description: shape, bounds, and that it reads nothing hidden."""

import math

import pytest

from cptcg.agents.base import make_agent
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import Pcg32
from cptcg.core.state import GameState
from cptcg.learn.decks import sample_pair
from cptcg.learn.features import FEATURE_NAMES, FEATURE_SCALING, NFEAT, features

from tests.conftest import Side, board


# ------------------------------------------------------------------ helpers
def play(reg, decks, agent: str, seed: int):
    """Yield every decision state of one game (the state before each action)."""
    s = new_game(reg, decks, seed)
    agents = [make_agent(agent, seed * 2 + i) for i in (0, 1)]
    for p, a in enumerate(agents):
        a.new_game(seed, p)
    guard = 0
    while not s.over and guard < 3000:
        guard += 1
        legal_actions(s)
        ch = s.pending
        yield s
        apply(s, agents[ch.player].act(s, ch))
    yield s


def game_states(pool, n_random: int = 16, n_heuristic: int = 5, seed: int = 4242):
    rng = Pcg32(seed)
    for agent, n in (("random", n_random), ("heuristic", n_heuristic)):
        for k in range(n):
            decks = sample_pair(pool, rng)
            for s in play(pool, decks, agent, seed + k):
                yield s


def named(s: GameState, me: int) -> dict:
    return dict(zip(FEATURE_NAMES, features(s, me)))


# ------------------------------------------------------------------ the table itself
def test_names_are_unique_and_documented():
    assert len(FEATURE_NAMES) == NFEAT == len(set(FEATURE_NAMES))
    for n in FEATURE_NAMES:
        assert FEATURE_SCALING[n].strip(), f"{n} has no documented scaling"


def test_vector_matches_the_names(pool):
    rng = Pcg32(1)
    decks = sample_pair(pool, rng)
    s = new_game(pool, decks, 7)
    assert len(features(s, 0)) == NFEAT
    assert len(features(s, 1)) == NFEAT


# ------------------------------------------------------------------ bounds
def test_no_feature_is_ever_nan_or_unbounded(pool):
    """Thousands of real game states, both seats: everything finite and inside [-1, 1]."""
    n = 0
    for s in game_states(pool):
        for me in (0, 1):
            f = features(s, me)
            n += 1
            for i, v in enumerate(f):
                assert isinstance(v, float), (FEATURE_NAMES[i], v)
                assert not math.isnan(v) and math.isfinite(v), (FEATURE_NAMES[i], v)
                assert -1.0 <= v <= 1.0, (FEATURE_NAMES[i], v)
    assert n >= 3000, f"only {n} states sampled; the bounds check needs a real spread"


def test_unsigned_features_never_go_negative(pool):
    """Only the documented signed differences may be below zero."""
    signed = {n for n in FEATURE_NAMES if "diff" in n or "_vs_" in n}
    for s in game_states(pool, n_random=3, n_heuristic=1, seed=99):
        for me in (0, 1):
            for name, v in zip(FEATURE_NAMES, features(s, me)):
                if name not in signed:
                    assert v >= 0.0, (name, v)


# ------------------------------------------------------------------ hidden information
def test_features_ignore_hidden_identities(pool):
    """``core.view.determinize`` resamples every identity ``me`` may not see. The features of a
    resampled world must be bit-identical: anything else is a leak."""
    determinize = pytest.importorskip("cptcg.core.view").determinize
    rng = Pcg32(5)
    checked = 0
    for k in range(6):
        decks = sample_pair(pool, rng)
        for i, s in enumerate(play(pool, decks, "heuristic", 500 + k)):
            if i % 4:
                continue
            for me in (0, 1):
                base = features(s, me)
                for t in range(2):
                    c = determinize(s, me, Pcg32(k * 100 + i * 7 + t))
                    assert features(c, me) == base, (k, i, me)
                    checked += 1
    assert checked > 200


def test_permuting_the_rivals_hand_and_deck_changes_nothing(pool):
    """The same property without ``core.view``: permute, by hand, exactly the identities the
    module docstring promises are never read."""
    rng = Pcg32(11)
    decks = sample_pair(pool, rng)
    states = list(play(pool, decks, "heuristic", 77))
    s = states[len(states) // 2]
    from cptcg.core.enums import NZONE, Zone
    for me in (0, 1):
        r = 1 - me
        base = features(s, me)
        c = s.clone()
        c.i_card = s.i_card[:]
        shuffler = Pcg32(3)
        groups = [
            list(c.z[me * NZONE + Zone.DECK]),
            list(c.z[r * NZONE + Zone.HAND]) + list(c.z[r * NZONE + Zone.DECK]),
            [i for i in c.legends(0) if not c.i_faceup[i]],
            [i for i in c.legends(1) if not c.i_faceup[i]],
        ]
        moved = 0
        for g in groups:
            ids = [c.i_card[i] for i in g]
            shuffler.shuffle(ids)
            for inst, cid in zip(g, ids):
                moved += c.i_card[inst] != cid
                c.i_card[inst] = cid
        c.invalidate()
        c._ctxs = {}
        assert moved > 0, "the permutation moved nothing, so it proves nothing"
        assert features(c, me) == base


# ------------------------------------------------------------------ it does read my own list
def test_features_read_my_own_undrawn_deck(reg):
    """The positive control: the same board with a different remainder in my deck reads
    differently. Without this, the invariance test above would pass on a constant vector."""
    def with_deck(cid):
        return board(reg,
                     Side(hand=["T-U2"], legends=["T-L1", "T-L2", "T-L5"], deck=[cid] * 12),
                     Side(legends=["T-L3", "T-L4", "T-L6"], deck=["T-U1"] * 12))
    cheap = named(with_deck("T-U1"), 0)          # cost 1
    dear = named(with_deck("T-U8"), 0)           # cost 5
    assert cheap["undrawn_mean_cost"] < dear["undrawn_mean_cost"]
    assert cheap["undrawn_cost1"] == 1.0 and dear["undrawn_cost1"] == 0.0
    assert dear["undrawn_cost5"] == 1.0
    assert cheap["hand_cost_vs_deck"] > dear["hand_cost_vs_deck"]


def test_features_read_my_legend_colours(reg):
    s = board(reg, Side(legends=["T-L1", "T-L2", "T-L5"], deck=["T-U1"] * 12),
              Side(legends=["T-L3", "T-L4", "T-L6"], deck=["T-U1"] * 12))
    f = named(s, 0)
    assert f["ram_red"] == pytest.approx(4 / 6)      # two Red Legends, 2 RAM each
    assert f["ram_green"] == pytest.approx(2 / 6)
    assert f["ram_blue"] == 0.0 and f["ram_yellow"] == 0.0
    colours = (f["legend_red"], f["legend_green"], f["legend_blue"], f["legend_yellow"])
    assert colours == (1.0, 1.0, 0.0, 0.0)
    g = named(s, 1)
    assert g["ram_blue"] == pytest.approx(4 / 6) and g["ram_yellow"] == pytest.approx(2 / 6)


# ------------------------------------------------------------------ names line up with values
def test_named_features_line_up(reg):
    """Every group of the vector checked against a hand-built board, which is what pins the
    names to the values: a misplaced entry moves everything after it."""
    me = Side(hand=["T-U2", "T-P2"], field=["T-U3"], legends=["T-L1", "T-L2", "T-L5"],
              eddies=2, deck=["T-U1"] * 10, gig=[(6, 4), (8, 7)], fixer=[4, 6, 8])
    rival = Side(field=["T-U4"], legends=["T-L3", "T-L4", "T-L6"], deck=["T-U1"] * 8,
                 gig=[(20, 13)], fixer=[10, 12, 20])
    s = board(reg, me, rival, active=0, turn=3)
    f = named(s, 0)
    # clock
    assert f["turn"] == pytest.approx(3 / 30)
    assert f["my_turn"] == 1.0 and f["to_move_me"] == 1.0 and f["first_player_me"] == 1.0
    assert f["overtime"] == 0.0 and f["empty_fixer_me"] == 0.0
    # the win condition
    assert f["gigs_me"] == pytest.approx(2 / 7) and f["gigs_rival"] == pytest.approx(1 / 7)
    assert f["gigs_diff"] == pytest.approx(1 / 7)
    assert f["to_seven_me"] == pytest.approx(5 / 7)
    assert f["at_six_me"] == 0.0
    assert f["cred_me"] == pytest.approx(11 / 70) and f["cred_rival"] == pytest.approx(13 / 70)
    assert f["cred_diff"] == pytest.approx(-2 / 70)
    assert f["gig_max_me"] == pytest.approx(7 / 20) and f["gig_min_me"] == pytest.approx(4 / 20)
    assert f["gig_mean_me"] == pytest.approx(5.5 / 20)
    assert f["gig_even_me"] == 0.5 and f["gig_even_rival"] == 0.0
    # fixer
    assert f["fixer_left_me"] == pytest.approx(3 / 6)
    assert f["fixer_best_me"] == pytest.approx(8 / 20)
    assert f["fixer_best_rival"] == 1.0
    # economy: 2 ready Eddies plus three ready face-down Legends
    assert f["eddies_me"] == pytest.approx(2 / 12) and f["ready_eddies_me"] == pytest.approx(5 / 12)
    assert f["eddies_rival"] == 0.0 and f["ready_eddies_rival"] == pytest.approx(3 / 12)
    # board
    assert f["units_me"] == pytest.approx(1 / 8) and f["units_rival"] == pytest.approx(1 / 8)
    assert f["power_ready_me"] == pytest.approx(5 / 60)
    assert f["power_ready_rival"] == pytest.approx(7 / 60)
    assert f["power_spent_me"] == 0.0
    assert f["power_best_me"] == pytest.approx(5 / 15)
    assert f["power_best_rival"] == pytest.approx(7 / 15)
    assert f["blockers_me"] == 0.0 and f["gear_me"] == 0.0 and f["lagged_me"] == 0.0
    assert f["threat"] == pytest.approx(1 / 7)          # one ready 7-power Unit steals one Gig
    assert f["threat_net"] == pytest.approx(1 / 7)
    assert f["steal_me"] == pytest.approx(1 / 7)
    # zones
    assert f["deck_me"] == pytest.approx(10 / 50) and f["deck_rival"] == pytest.approx(8 / 50)
    assert f["deck_low_me"] == 0.0
    assert f["hand_me"] == pytest.approx(2 / 10) and f["hand_rival"] == 0.0
    assert f["trash_me"] == 0.0 and f["removed_me"] == 0.0
    # Legends
    assert f["legends_me"] == 1.0 and f["faceup_me"] == 0.0
    # my list: 10 T-U1 + T-U2 + T-P2 + T-U3 + 2 Eddies (T-P1) = 15 cards
    assert f["list_size"] == 0.0                        # clipped: a 15-card test board is under 40
    assert f["list_cost1"] == pytest.approx(12 / 15)    # ten T-U1 and two T-P1
    assert f["list_cost2"] == pytest.approx(2 / 15)
    assert f["list_cost3"] == pytest.approx(1 / 15)
    assert f["list_unit_share"] == pytest.approx(12 / 15)
    assert f["list_program_share"] == pytest.approx(3 / 15)
    assert f["list_gear_share"] == 0.0
    assert f["list_sell_share"] == 1.0 and f["list_blocker_share"] == 0.0
    # what is left: ten copies of a 1-cost Unit
    assert f["undrawn_frac"] == pytest.approx(10 / 15)
    assert f["undrawn_cost1"] == 1.0 and f["undrawn_mean_cost"] == pytest.approx(1 / 7)
    assert f["undrawn_unit_share"] == 1.0 and f["undrawn_sell_share"] == 1.0
    # the hand against it
    assert f["hand_mean_cost"] == pytest.approx(2 / 7)
    assert f["hand_min_cost"] == pytest.approx(2 / 7)
    assert f["hand_cheap"] == pytest.approx(2 / 6) and f["hand_sellable"] == pytest.approx(2 / 6)
    assert f["hand_playable"] == pytest.approx(2 / 6) and f["hand_playable_share"] == 1.0
    assert f["hand_units"] == pytest.approx(1 / 6) and f["hand_programs"] == pytest.approx(1 / 6)
    assert f["hand_unit_power"] == pytest.approx(3 / 15)
    assert f["hand_cost_vs_deck"] == pytest.approx(1 / 7)
    assert f["hand_sell_vs_list"] == 0.0


def test_empty_zones_do_not_divide_by_zero(reg):
    """No Gigs, no hand, no deck: every ratio has to fall back to 0 rather than blow up."""
    s = board(reg, Side(legends=["T-L1", "T-L2", "T-L5"]), Side(legends=["T-L3", "T-L4", "T-L6"]))
    for me in (0, 1):
        f = features(s, me)
        assert len(f) == NFEAT
        assert all(math.isfinite(v) and -1.0 <= v <= 1.0 for v in f)


def test_features_do_not_disturb_the_state(pool):
    """A value function that mutates the position it scores would corrupt a search tree."""
    rng = Pcg32(2)
    decks = sample_pair(pool, rng)
    states = list(play(pool, decks, "heuristic", 21))
    s = states[len(states) // 2]
    before = (list(s.i_zone), bytes(s.i_spent), bytes(s.i_faceup), list(s.i_card),
              [list(x) for x in s.z], [list(g) for g in s.gig], s.rng.state)
    first = features(s, 0)
    after = (list(s.i_zone), bytes(s.i_spent), bytes(s.i_faceup), list(s.i_card),
             [list(x) for x in s.z], [list(g) for g in s.gig], s.rng.state)
    assert before == after
    assert features(s, 0) == first
