"""Legal-move generation for each kind of decision."""

from __future__ import annotations

from cptcg.core.actions import (Attack, Block, CallLegend, EndTurn, GoSolo, Pass, Play, Sell,
                                Target)
from cptcg.core.enums import (F_CANT_ATTACK, NO_INST, NZONE, TARGET_GIG, TARGET_UNIT, CardType,
                              Keyword, Zone)
from cptcg.core.ops import available
from cptcg.core.state import ONCE_CALLED, ONCE_SOLD, GameState


def gig_die_options(s: GameState, player: int) -> list[int]:
    dice = s.fixer[player]
    non20 = [d for d in dice if d != 20]
    return sorted(set(non20)) if non20 else sorted(set(dice))


def gear_hosts(s: GameState, player: int) -> list[int]:
    """Legal Gear hosts: friendly Units on the field, and face-up Legends in the Legends area."""
    hosts = s.units(player)
    hosts += [i for i in s.legends(player) if s.i_faceup[i]]
    return hosts


def attack_targets(s: GameState, attacker: int) -> list[Target]:
    p = s.i_owner[attacker]
    r = 1 - p
    out = [Target(TARGET_UNIT, u) for u in s.units(r) if s.i_spent[u]]
    if s.cfg.allow_empty_gig_attack or s.gig[r]:
        out.append(Target(TARGET_GIG))
    return out


def can_attack(s: GameState, inst: int) -> bool:
    if s.i_spent[inst] or s.i_lag[inst] or s.i_flags[inst] & F_CANT_ATTACK:
        return False
    return bool(attack_targets(s, inst))


def main_menu(s: GameState) -> list:
    p = s.active
    base = p * NZONE
    opts: list = [EndTurn()]
    avail = available(s, p)
    once = s.once[p]

    # Sell for Eddie (once per turn)
    if not once & ONCE_SOLD:
        opts += [Sell(i) for i in s.z[base + Zone.HAND] if s.card(i).sell_tag]

    # Play a card from hand
    hosts = None
    field_full = (s.cfg.field_limit is not None and len(s.units(p)) >= s.cfg.field_limit)
    for i in s.z[base + Zone.HAND]:
        d = s.card(i)
        if d.cost is None or d.cost > avail:
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

    # Legends: GO SOLO a face-up one, or Call a face-down one
    for i in s.legends(p):
        d = s.card(i)
        if s.i_faceup[i]:
            if (Keyword.GO_SOLO in d.keywords and d.cost is not None and not field_full
                    and (not s.cfg.go_solo_requires_ready or not s.i_spent[i])
                    and available(s, p, exclude=i) >= d.cost):
                opts.append(GoSolo(i))
        elif not once & ONCE_CALLED and available(s, p, exclude=i) >= 1:
            opts.append(CallLegend(i))

    # Attack
    opts += [Attack(u) for u in s.units(p) if can_attack(s, u)]
    return opts


def reaction_menu(s: GameState) -> list:
    """The defender's options while a rival Unit is attacking."""
    atk = s.atk
    d = 1 - atk.attacker_ctrl
    opts: list = [Pass()]
    if not s.once[d] & ONCE_CALLED:
        opts += [CallLegend(i) for i in s.legends(d)
                 if not s.i_faceup[i] and available(s, d, exclude=i) >= 1]
    if atk.redirects < s.cfg.max_redirects_per_attack and (
            atk.target_kind == TARGET_GIG or s.cfg.blocker_redirects_unit_attacks):
        for u in s.units(d):
            if (u != atk.target and not s.i_spent[u]
                    and (s.cfg.lagged_units_can_block or not s.i_lag[u])
                    and Keyword.BLOCKER in s.card(u).keywords):
                opts.append(Block(u))
    return opts
