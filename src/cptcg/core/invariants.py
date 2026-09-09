"""Structural invariants, checked in tests and fuzz runs after every action."""

from __future__ import annotations

from cptcg.core.enums import DICE, NO_INST, NZONE, CardType, Zone
from cptcg.core.state import GameState


def check(s: GameState) -> None:
    n = len(s.i_card)
    seen = [0] * n
    for p in (0, 1):
        for zone in Zone:
            for inst in s.z[p * NZONE + zone]:
                assert s.i_owner[inst] == p, f"inst {inst} in player {p}'s zone but owned by other"
                assert s.i_zone[inst] == zone, f"inst {inst} zone mismatch"
                seen[inst] += 1
    assert all(c == 1 for c in seen), f"instances not in exactly one zone: {seen}"
    # dice conservation
    all_dice = sorted(s.fixer[0] + s.fixer[1] + [d for d, _ in s.gig[0]] + [d for d, _ in s.gig[1]])
    assert all_dice == sorted(DICE * 2), f"dice not conserved: {all_dice}"
    for p in (0, 1):
        for sides, value in s.gig[p]:
            assert 1 <= value <= sides, f"die {sides} shows {value}"
    # gear/host consistency
    for inst in range(n):
        h = s.i_host[inst]
        if h != NO_INST:
            assert s.card(inst).type is CardType.GEAR, f"non-gear {inst} has a host"
            assert s.i_zone[h] == s.i_zone[inst], f"gear {inst} not with host {h}"
            assert s.i_owner[h] == s.i_owner[inst]
        elif s.card(inst).type is CardType.GEAR:
            assert s.i_zone[inst] not in (Zone.FIELD, Zone.LEGENDS), f"orphan gear {inst} in play"
        if s.i_zone[inst] not in (Zone.FIELD, Zone.LEGENDS, Zone.EDDIES):
            assert not s.i_spent[inst], f"out-of-play inst {inst} is spent"
        if s.i_zone[inst] is not Zone.FIELD:
            assert not s.i_lag[inst], f"inst {inst} lagged outside the field"
    # legends area holds legends plus gear equipped to them (GO SOLO legends live on the field)
    for p in (0, 1):
        for inst in s.z[p * NZONE + Zone.LEGENDS]:
            t = s.card(inst).type
            assert t is CardType.LEGEND or (t is CardType.GEAR and s.i_host[inst] != NO_INST), \
                f"inst {inst} ({t.name}) in legends area"
        assert all(s.card(i).type is CardType.LEGEND for i in s.legends(p))
    if s.over:
        assert s.winner in (0, 1)
    else:
        assert s.pending is not None or s.stack, "live game with nothing to do"
