"""The active-card index (ops._rebuild_active) against a reference rebuild and brute force.

Slots 0-6 must match the previous implementation exactly (the heuristic, gear_on and play_cost
read them); slots 7-10 must match what a scan of active_cards() + the card scripts yields; and
ability_options must return the same menu as the previous scan-based implementation.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from smoke_random import play_random, reg as test_reg  # noqa: E402,F401

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.actions import Activate, EndTurn  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.enums import NO_INST, NZONE, CardType, Zone  # noqa: E402
from cptcg.core.legal import ability_options  # noqa: E402
from cptcg.core.ops import _ctx, _rebuild_active, active_cards, available  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.deck.decklist import Decklist  # noqa: E402
from conftest import blue_deck, red_deck  # noqa: E402


# ------------------------------------------------------- reference implementations
def _ref_rebuild(s):
    """The previous _rebuild_active, verbatim: slots 0-6 of the new index must equal this."""
    per = ([], [])
    pm, cm, ev = [], [], []
    gear_of: dict[int, tuple] = {}
    defs = s.reg.defs
    i_host = s.i_host
    for p in (0, 1):
        base = p * NZONE
        lst = per[p]
        lst += s.z[base + Zone.FIELD]
        for i in s.z[base + Zone.LEGENDS]:
            if s.i_faceup[i] or (i_host[i] != NO_INST and s.i_faceup[i_host[i]]):
                lst.append(i)
        for zone in (Zone.FIELD, Zone.LEGENDS):
            for g in s.z[base + zone]:
                h = i_host[g]
                if h != NO_INST:
                    gear_of[h] = gear_of.get(h, ()) + (g,)
        for i in lst:
            sc = defs[s.i_card[i]].script
            if sc is None:
                continue
            if sc.power_mod is not None:
                pm.append((i, sc.power_mod))
            if sc.cost_mod is not None:
                cm.append((i, sc.cost_mod))
            if sc.on_event is not None:
                ev.append((i, sc.on_event))
    ev = tuple(ev)
    owner = s.i_owner
    # event hooks in both delivery orders (active player's cards first), precomputed once
    ev1 = tuple(h for h in ev if owner[h[0]] == 1) + tuple(h for h in ev if owner[h[0]] == 0)
    cache = (tuple(per[0]), tuple(per[1]), tuple(pm), tuple(cm), ev, gear_of, (ev, ev1))
    s._active = cache
    return cache


def _ref_ability_options(s, player, quick_only):
    """The previous scan-based ability_options, verbatim."""
    out = []
    for inst in active_cards(s, first=player):
        if s.i_owner[inst] != player:
            continue
        sc = s.card(inst).script
        if sc is None or not sc.abilities:
            continue
        d = s.card(inst)
        for k, ab in enumerate(sc.abilities):
            if quick_only and not ab.quick:
                continue
            if ab.self_spend:
                if s.i_spent[inst]:
                    continue
                if d.type is CardType.UNIT and s.i_lag[inst]:
                    continue                     # Lag: no self-spend effects
            excl = inst if (ab.self_spend and d.type is CardType.LEGEND) else NO_INST
            cost = ab.cost(_ctx(s, inst)) if callable(ab.cost) else ab.cost
            if available(s, player, exclude=excl) < cost:
                continue
            if ab.legal is not None and not ab.legal(_ctx(s, inst)):
                continue
            out.append(Activate(inst, k))
    return out


def _brute_slots(s):
    """Slots 7-10 rebuilt by brute force from active_cards() and the card scripts."""
    ws, wd, ab, sup = [], [], [], []
    for p in (0, 1):
        mine = [i for i in active_cards(s, first=p) if s.i_owner[i] == p]
        scripts = [(i, s.card(i).script) for i in mine]
        ws.append(tuple((i, sc.would_steal) for i, sc in scripts if sc is not None and sc.would_steal is not None))
        wd.append(tuple((i, sc.would_defeat) for i, sc in scripts if sc is not None and sc.would_defeat is not None))
        ab.append(tuple((i, sc) for i, sc in scripts if sc is not None and sc.abilities))
        sup.append(any(sc is not None and bool(sc.extra.get("suppress_new_units")) for _i, sc in scripts))
    return tuple(ws), tuple(wd), tuple(ab), tuple(sup)


def _pairs(hooks):
    """Event-hook entries are (inst, on_event, events) now; the reference had (inst, on_event)."""
    return tuple((i, h) for i, h, _kinds in hooks)


def _check_state(s):
    a = _rebuild_active(s.clone())
    b = _ref_rebuild(s.clone())
    assert len(a) == 11
    assert a[:4] == b[:4] and a[5] == b[5]
    assert _pairs(a[4]) == b[4]
    assert (_pairs(a[6][0]), _pairs(a[6][1])) == b[6]
    for i, _h, kinds in a[4]:
        assert kinds == s.card(i).script.events
    assert a[7:] == _brute_slots(s)
    for p in (0, 1):
        for q in (False, True):
            assert ability_options(s, p, q) == _ref_ability_options(s, p, q)


# ------------------------------------------------------------------- drivers
@pytest.mark.parametrize("seed", range(6))
def test_index_matches_reference_on_test_cards(seed):
    s = new_game(test_reg, (red_deck(), blue_deck()), seed)
    r = Pcg32(seed ^ 0xABCDEF)
    steps = 0
    while not s.over:
        _check_state(s)
        opts = legal_actions(s)
        if len(opts) > 1 and isinstance(opts[0], EndTurn) and r.below(10) < 9:
            idx = 1 + r.below(len(opts) - 1)
        else:
            idx = r.below(len(opts))
        apply(s, idx)
        steps += 1
        assert steps < 5000
    _check_state(s)


def test_play_random_smoke_still_runs():
    s, _steps = play_random(3)
    assert s.over
    _check_state(s)


_POOL_MATCHUPS = [("the_heist", "embracing_power"), ("sample_arasaka", "sample_fixers"),
                  ("sample_corpos", "sample_nomads"), ("sample_gangers", "sample_netrunners"),
                  ("sample_mercs", "sample_ripperdocs")]


@pytest.mark.parametrize("seed", range(len(_POOL_MATCHUPS)))
def test_index_matches_reference_on_the_pool(pool, seed):
    a, b = _POOL_MATCHUPS[seed]
    decks = (Decklist.load(ROOT / "data" / "decks" / f"{a}.json"),
             Decklist.load(ROOT / "data" / "decks" / f"{b}.json"))
    s = new_game(pool, decks, seed)
    r = Pcg32(seed * 7 + 1)
    steps = 0
    while not s.over:
        _check_state(s)
        opts = legal_actions(s)
        if len(opts) > 1 and isinstance(opts[0], EndTurn) and r.below(10) < 9:
            idx = 1 + r.below(len(opts) - 1)
        else:
            idx = r.below(len(opts))
        apply(s, idx)
        steps += 1
        assert steps < 5000
    _check_state(s)


def test_registry_hook_table_matches_scripts(pool):
    """reg.hooks[idx] is None exactly for cards with no in-play hook, else mirrors the script."""
    for d in pool.defs:
        row = pool.hooks[d.idx]
        sc = d.script
        if sc is None or (sc.power_mod is None and sc.cost_mod is None and sc.on_event is None
                          and sc.would_steal is None and sc.would_defeat is None and not sc.abilities
                          and not sc.extra.get("suppress_new_units")):
            assert row is None, d.id
            continue
        assert row == (sc.power_mod, sc.cost_mod, sc.on_event, sc.events, sc.would_steal,
                       sc.would_defeat, sc if sc.abilities else None,
                       bool(sc.extra.get("suppress_new_units"))), d.id
