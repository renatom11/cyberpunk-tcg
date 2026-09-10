"""The inlined heuristic evaluator must be bit-identical to the reference implementation.

``evaluate`` inlines power()/has_keyword()/units()/legends()/street_cred()/steal_count() and hoists
its weights; ``_equiv_key`` dedups by type instead of class name. Both are replayed here against
verbatim copies of the originals over random games on the test card set and on the real pool.
"""

import struct
from pathlib import Path

from conftest import blue_deck, red_deck

from cptcg.agents.base import make_agent
from cptcg.agents.heuristic import W, _equiv_key, evaluate
from cptcg.core.actions import EndTurn
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.enums import NZONE, Keyword, Zone
from cptcg.core.ops import ATTACKING, _active, has_keyword, power, steal_count
from cptcg.core.rng import Pcg32
from cptcg.core.state import GameState
from cptcg.deck.decklist import Decklist

ROOT = Path(__file__).resolve().parents[2]


# ---- reference implementations (verbatim from the pre-inlining heuristic.py) --------------------
def _ref_evaluate(s: GameState, me: int, w: dict = W) -> float:
    """Board score from ``me``'s perspective. Reads only public zones and my own hand."""
    if s.over:
        return w["win"] if s.winner == me else -w["win"]
    r = 1 - me
    v = 0.0
    g_me, g_r = len(s.gig[me]), len(s.gig[r])
    v += w["gig"] * (g_me - g_r) + w["gig_sq"] * (g_me * g_me - g_r * g_r)
    if g_r >= 6:
        v += w["rival_six"]
    if g_me >= 6:
        v += w["my_six"]
    v += w["cred"] * (s.street_cred(me) - s.street_cred(r))
    gear_of = _active(s)[5]
    i_spent = s.i_spent
    threat = 0            # Gigs the rival's ready Units could steal next turn ...
    blockers = 0          # ... less what my ready Blockers can absorb
    for p, sign in ((me, 1.0), (r, -1.0)):
        base = p * NZONE
        for u in s.units(p):
            pw = power(s, u, ATTACKING)
            spent = i_spent[u]
            v += sign * (w["unit_spent"] if spent else w["unit_ready"]) * pw
            v += sign * w["unit_count"]
            ready_blocker = (not spent) and has_keyword(s, u, Keyword.BLOCKER)
            if ready_blocker:
                v += sign * w["blocker"]
            v += sign * w["gear"] * len(gear_of.get(u, ()))
            if p == r:
                if not spent:
                    threat += steal_count(pw)
            elif ready_blocker:
                blockers += 1
        legends = s.legends(p)
        v += sign * w["eddies"] * (len(s.z[base + Zone.EDDIES]) + len(legends))
        v += sign * w["faceup"] * sum(s.i_faceup[i] for i in legends)
        v += sign * w["removed"] * len(s.z[base + Zone.REMOVED])
        v += sign * w["deck"] * len(s.z[base + Zone.DECK])
    v += w["hand"] * len(s.z[me * NZONE + Zone.HAND])
    # Counted whoever's turn it is, so ending the turn isn't "safe".
    v += w["threat"] * max(0, min(threat, g_me) - blockers)
    return v


def _ref_key(s: GameState, a) -> tuple:
    """Options that differ only in *which copy* of a card they name are interchangeable."""
    inst = getattr(a, "inst", None)
    if inst is None or inst < 0 or a.__class__.__name__ == "Pick":
        return (a,)
    cid = s.i_card[inst]
    host = getattr(a, "host", -1)
    return (a.__class__.__name__, cid, s.i_zone[inst], s.i_card[host] if host >= 0 else -1,
            getattr(a, "ability", -1))


# ---- harness --------------------------------------------------------------------------------
def _bits(x: float) -> bytes:
    return struct.pack("<d", x)


def _kept(s: GameState, options, keyfn) -> set:
    """Indices a first-seen dedup with ``keyfn`` would preview (mirrors HeuristicAgent._greedy)."""
    seen, kept = set(), set()
    for i, o in enumerate(options):
        k = keyfn(s, o)
        if k not in seen:
            seen.add(k)
            kept.add(i)
    return kept


def _assert_same_eval(s: GameState, checked: list) -> None:
    for p in (0, 1):
        assert _bits(evaluate(s, p)) == _bits(_ref_evaluate(s, p)), (s.turn, p, s.pending)
        checked[0] += 1


def _check_decision(s: GameState, checked: list) -> None:
    """At a materialised menu: compare both players' scores on the live state, on a clone after
    taking option 0 (covers pending reactions, steps and finished games), and the dedup sets."""
    options = s.pending.options
    _assert_same_eval(s, checked)
    assert _kept(s, options, _equiv_key) == _kept(s, options, _ref_key)
    c = s.clone()
    apply(c, 0)
    _assert_same_eval(c, checked)
    if not c.over and c.pending is not None:
        legal_actions(c)
        _assert_same_eval(c, checked)


def _play_smoke_game(reg, seed: int, checked: list) -> None:
    """tools/smoke_random.play_random, with the evaluator checked at every decision."""
    s = new_game(reg, (red_deck(), blue_deck()), seed)
    r = Pcg32(seed ^ 0xABCDEF)
    steps = 0
    while not s.over:
        opts = legal_actions(s)
        _check_decision(s, checked)
        if len(opts) > 1 and isinstance(opts[0], EndTurn) and r.below(10) < 9:
            idx = 1 + r.below(len(opts) - 1)
        else:
            idx = r.below(len(opts))
        apply(s, idx)
        steps += 1
        assert steps <= 5000, "runaway game"
    _assert_same_eval(s, checked)


def _play_pool_game(reg, decks, seed: int, checked: list) -> None:
    agents = [make_agent("random", seed * 2 + i) for i in range(2)]
    s = new_game(reg, decks, seed)
    for p, a in enumerate(agents):
        a.new_game(seed, p)
    steps = 0
    while not s.over:
        legal_actions(s)
        _check_decision(s, checked)
        apply(s, agents[s.pending.player].act(s, s.pending))
        steps += 1
        assert steps <= 20_000, "runaway game"
    _assert_same_eval(s, checked)


# ---- tests ----------------------------------------------------------------------------------
def test_evaluate_matches_reference_on_test_cards(reg):
    checked = [0]
    for seed in range(3):
        _play_smoke_game(reg, seed, checked)
    assert checked[0] > 1000


def test_evaluate_matches_reference_on_real_pool(pool):
    checked = [0]
    matchups = [("the_heist", "embracing_power"), ("sample_gangers", "sample_netrunners")]
    for seed, (a, b) in enumerate(matchups, start=7):
        decks = (Decklist.load(ROOT / "data" / "decks" / f"{a}.json"),
                 Decklist.load(ROOT / "data" / "decks" / f"{b}.json"))
        _play_pool_game(pool, decks, seed, checked)
    assert checked[0] > 1000
