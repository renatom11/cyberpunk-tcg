"""main_menu / reaction_menu call available() once per menu and derive every per-Legend
``available(s, p, exclude=i)`` arithmetically (see payable_sources). These tests pin the fast
menus to straightforward reference versions - the pre-optimisation code, pasted verbatim - at
every decision of random games on the test card set and on the whole pool, and on hand-built
boards that isolate each branch of the arithmetic."""
import json
from collections import Counter
from pathlib import Path

import pytest
from conftest import FIXTURES, Side, blue_deck, board, find, options, red_deck

from cptcg.agents.base import make_agent
from cptcg.cards.registry import Registry
from cptcg.core.actions import (Attack, Block, CallLegend, ChoiceKind, EndTurn, GoSolo, Pass, Play,
                                Sell, Target)
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.enums import NZONE, TARGET_GIG, CardType, Keyword, Zone
from cptcg.core.legal import ability_options, can_attack, gear_hosts, main_menu, reaction_menu
from cptcg.core.ops import _ctx, available, has_keyword, payable_sources, play_cost
from cptcg.core.rng import Pcg32
from cptcg.core.state import ONCE_CALLED, ONCE_SOLD
from cptcg.deck.decklist import Decklist

ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------ reference menus
def _ref_main_menu(s):
    p = s.active
    base = p * NZONE
    opts = [EndTurn()]
    avail = available(s, p)
    once = s.once[p]

    if not once & ONCE_SOLD:
        opts += [Sell(i) for i in s.z[base + Zone.HAND] if s.card(i).sell_tag]

    hosts = None
    field_full = (s.cfg.field_limit is not None and len(s.units(p)) >= s.cfg.field_limit)
    for i in s.z[base + Zone.HAND]:
        d = s.card(i)
        if d.cost is None or play_cost(s, p, i) > avail:
            continue
        if d.type is CardType.UNIT:
            if not field_full:
                opts.append(Play(i))
        elif d.type is CardType.PROGRAM:
            opts.append(Play(i))
        elif d.type is CardType.GEAR:
            if hosts is None:
                hosts = gear_hosts(s, p)
            opts += [Play(i, h) for h in hosts]

    for i in s.legends(p):
        d = s.card(i)
        if s.i_faceup[i]:
            if (Keyword.GO_SOLO in d.keywords and d.cost is not None and not field_full
                    and (not s.cfg.go_solo_requires_ready or not s.i_spent[i])
                    and available(s, p, exclude=i) >= play_cost(s, p, i, go_solo=True)):
                opts.append(GoSolo(i))
        elif not once & ONCE_CALLED and available(s, p, exclude=i) >= 1:
            opts.append(CallLegend(i))

    opts += ability_options(s, p, quick_only=False)
    opts += [Attack(u) for u in s.units(p) if can_attack(s, u)]
    return opts


def _ref_reaction_menu(s):
    atk = s.atk
    d = 1 - atk.attacker_ctrl
    opts = [Pass()]
    if not s.once[d] & ONCE_CALLED:
        opts += [CallLegend(i) for i in s.legends(d)
                 if not s.i_faceup[i] and available(s, d, exclude=i) >= 1]
    asc = s.card(atk.attacker).script
    unblockable = asc is not None and asc.unblockable is not None and asc.unblockable(_ctx(s, atk.attacker))
    if not unblockable and atk.redirects < s.cfg.max_redirects_per_attack and (
            atk.target_kind == TARGET_GIG or s.cfg.blocker_redirects_unit_attacks):
        for u in s.units(d):
            if (u != atk.target and not s.i_spent[u]
                    and (s.cfg.lagged_units_can_block or not s.i_lag[u])
                    and has_keyword(s, u, Keyword.BLOCKER)):
                opts.append(Block(u))
    avail = available(s, d)
    for i in s.z[d * NZONE + Zone.HAND]:
        c = s.card(i)
        if c.type is CardType.PROGRAM and Keyword.QUICK in c.keywords and play_cost(s, d, i) <= avail:
            opts.append(Play(i))
    opts += ability_options(s, d, quick_only=True)
    return opts


# ------------------------------------------------------------------ helpers
def _check_exclusion_arithmetic(s):
    """available(s, p, exclude=i) is available(s, p) minus one iff Legend i is a payable source."""
    for p in (0, 1):
        base = available(s, p)
        srcs = payable_sources(s, p)
        for i in s.legends(p):
            excl = available(s, p, exclude=i)
            assert excl == base - (1 if i in srcs else 0)
            if s.i_faceup[i]:
                assert excl == base - (1 if (not s.i_spent[i] and s.card(i).sell_tag) else 0)
            else:
                assert excl == base - (0 if s.i_spent[i] else 1)


def _check_decision(s, stats):
    _check_exclusion_arithmetic(s)
    ch = s.pending
    if ch.kind is ChoiceKind.MAIN:
        ref = _ref_main_menu(s)
        assert main_menu(s) == ref
        assert list(legal_actions(s)) == ref
        stats["main"] += 1
    elif ch.kind is ChoiceKind.REACTION and s.atk is not None:
        ref = _ref_reaction_menu(s)
        assert reaction_menu(s) == ref
        assert list(ch.options) == ref
        stats["reaction"] += 1


def _finish(s, stats):
    stats["legend_removed"] += any(s.i_zone[i] is Zone.REMOVED and s.card(i).type is CardType.LEGEND
                                   for i in range(len(s.i_card)))


# -------------------------------------------------------------------- games
def test_menus_match_reference_in_random_games_on_test_set(reg):
    """The tools/smoke_random.py loop, checked at every decision."""
    stats = Counter()
    for seed in range(10):
        s = new_game(reg, (red_deck(), blue_deck()), seed)
        r = Pcg32(seed ^ 0xABCDEF)
        steps = 0
        while not s.over:
            opts = legal_actions(s)
            _check_decision(s, stats)
            if len(opts) > 1 and isinstance(opts[0], EndTurn) and r.below(10) < 9:
                idx = 1 + r.below(len(opts) - 1)
            else:
                idx = r.below(len(opts))
            stats[type(opts[idx]).__name__] += 1
            apply(s, idx)
            steps += 1
            assert steps <= 5000, "runaway game"
        _finish(s, stats)
    assert stats["main"] > 100 and stats["reaction"] > 10
    assert stats["CallLegend"] and stats["GoSolo"] and stats["Block"]


POOL_MATCHUPS = [("sample_corpos", "sample_mercs"), ("sample_gangers", "sample_nomads"),
                 ("the_heist", "embracing_power"), ("sample_arasaka", "sample_ripperdocs")]


def test_menus_match_reference_in_random_games_on_pool(pool):
    """Random agent on real decks: GO SOLO Legends, QUICK Programs, cost modifiers, unblockable
    attackers and Legends removed when they leave play (cfg.legends_removed_when_leaving)."""
    stats = Counter()
    for k, (a, b) in enumerate(POOL_MATCHUPS):
        seed = 3000 + k
        decks = (Decklist.load(ROOT / "data" / "decks" / f"{a}.json"),
                 Decklist.load(ROOT / "data" / "decks" / f"{b}.json"))
        agents = [make_agent("random", seed * 2 + i) for i in range(2)]
        s = new_game(pool, decks, seed)
        for p, ag in enumerate(agents):
            ag.new_game(seed, p)
        n = 0
        while not s.over:
            legal_actions(s)
            _check_decision(s, stats)
            idx = agents[s.pending.player].act(s, s.pending)
            stats[type(s.pending.options[idx]).__name__] += 1
            apply(s, idx)
            n += 1
            assert n <= 20_000, "runaway game"
        _finish(s, stats)
    assert stats["main"] > 100 and stats["reaction"] > 10
    assert stats["CallLegend"] and stats["GoSolo"] and stats["legend_removed"]


# ----------------------------------------------------------- hand-built boards
@pytest.fixture(scope="module")
def reg_untagged_legend(tmp_path_factory):
    """The test set with T-L1's sell tag removed (every Legend in both sets carries one)."""
    raw = json.loads((FIXTURES / "cards_test.json").read_text(encoding="utf-8"))
    for c in raw["cards"]:
        if c["id"] == "T-L1":
            c["sell_tag"] = False
    path = tmp_path_factory.mktemp("cards") / "cards_untagged_legend.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return Registry.from_files(path)


def _same_main_menu(s):
    _check_exclusion_arithmetic(s)
    ref = _ref_main_menu(s)
    assert main_menu(s) == ref and list(options(s)) == ref
    return ref


def test_go_solo_face_up_legend_with_sell_tag_cannot_pay_for_itself(reg):
    # T-L1: GO SOLO 5, sell tag. Ready and face-up it is a payable source - but not for its own cost.
    s = board(reg, Side(legends=[("T-L1", {"faceup": True})], eddies=5), Side())
    l1 = find(s, "T-L1")
    assert available(s, 0) == 6 and available(s, 0, exclude=l1) == 5
    assert GoSolo(l1) in _same_main_menu(s)

    s = board(reg, Side(legends=[("T-L1", {"faceup": True})], eddies=4), Side())
    assert GoSolo(find(s, "T-L1")) not in _same_main_menu(s)

    # Spent, it is no source at all; the 5 Eddies still pay (go_solo_requires_ready is off).
    s = board(reg, Side(legends=[("T-L1", {"faceup": True, "spent": True})], eddies=5), Side())
    l1 = find(s, "T-L1")
    assert available(s, 0) == available(s, 0, exclude=l1) == 5
    assert GoSolo(l1) in _same_main_menu(s)


def test_go_solo_face_up_legend_without_sell_tag_is_not_a_source(reg_untagged_legend):
    reg = reg_untagged_legend
    s = board(reg, Side(legends=[("T-L1", {"faceup": True})], eddies=5), Side())
    l1 = find(s, "T-L1")
    assert available(s, 0) == available(s, 0, exclude=l1) == 5
    assert GoSolo(l1) in _same_main_menu(s)

    s = board(reg, Side(legends=[("T-L1", {"faceup": True})], eddies=4), Side())
    assert GoSolo(find(s, "T-L1")) not in _same_main_menu(s)


def test_call_legend_with_a_spent_face_down_legend(reg):
    # The only ready source is T-L4 itself: it can pay to call T-L2 but not to call itself.
    s = board(reg, Side(legends=[("T-L2", {"spent": True}), "T-L4"], eddies=0), Side())
    l2, l4 = find(s, "T-L2"), find(s, "T-L4")
    assert available(s, 0) == 1
    opts = _same_main_menu(s)
    assert CallLegend(l2) in opts and CallLegend(l4) not in opts

    # One Eddie: both calls are affordable.
    s = board(reg, Side(legends=[("T-L2", {"spent": True}), "T-L4"], eddies=1), Side())
    opts = _same_main_menu(s)
    assert CallLegend(find(s, "T-L2")) in opts and CallLegend(find(s, "T-L4")) in opts


def _reaction_board(pool, defender):
    """A vanilla attacker hits the defender's Gig area; a Blocker keeps the window open."""
    s = board(pool, Side(field=["psycho-squad"]), defender)
    attacker = find(s, "psycho-squad")
    assert Attack(attacker) in options(s)
    apply(s, s.pending.index_of(Attack(attacker)))
    if s.pending.kind is ChoiceKind.TARGET:
        apply(s, s.pending.index_of(Target(TARGET_GIG)))
    assert s.pending.kind is ChoiceKind.REACTION and s.atk is not None
    _check_exclusion_arithmetic(s)
    ref = _ref_reaction_menu(s)
    assert reaction_menu(s) == ref and list(s.pending.options) == ref
    return s, ref


def test_reaction_quick_program_needs_a_ready_source(pool):
    defender = dict(field=["secondhand-bombus"], hand=["floor-it"], gig=[(6, 3)],
                    legends=[("v-streetkid", {"spent": True}), "rogue-amendiares-preem-solo"])
    # No Eddies: the ready face-down Legend can pay to call the spent one, not itself nor the Program.
    s, ref = _reaction_board(pool, Side(eddies=0, **defender))
    prog, spent_leg, ready_leg = (find(s, "floor-it", Zone.HAND), find(s, "v-streetkid"),
                                  find(s, "rogue-amendiares-preem-solo"))
    assert Block(find(s, "secondhand-bombus")) in ref
    assert CallLegend(spent_leg) in ref and CallLegend(ready_leg) not in ref
    assert Play(prog) in ref                                   # cost 1: the ready Legend pays

    both_spent = dict(defender, legends=[("v-streetkid", {"spent": True}),
                                         ("rogue-amendiares-preem-solo", {"spent": True})])
    s, ref = _reaction_board(pool, Side(eddies=0, **both_spent))
    assert Play(find(s, "floor-it", Zone.HAND)) not in ref     # no ready source at all
    assert not any(isinstance(a, CallLegend) for a in ref)

    s, ref = _reaction_board(pool, Side(eddies=2, spent_eddies=1, **defender))
    assert Play(find(s, "floor-it", Zone.HAND)) in ref
    assert ref[0] == Pass()
