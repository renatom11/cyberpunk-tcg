"""Legal-move generation for each kind of decision."""

from __future__ import annotations

from cptcg.core.actions import (Activate, Attack, Block, CallLegend, EndTurn, GoSolo, Pass, Play,
                                Sell, Target)
from cptcg.core.enums import (NO_INST, NZONE, TARGET_GIG, TARGET_UNIT, CardType, Keyword, Zone)
from cptcg.core.ops import _ctx, active_cards, available, has_keyword, play_cost
from cptcg.core.state import ONCE_CALLED, ONCE_SOLD, GameState


def gig_die_options(s: GameState, player: int) -> list[int]:
    dice = s.fixer[player]
    non20 = [d for d in dice if d != 20]
    return sorted(set(non20)) if non20 else sorted(set(dice))


def gear_hosts(s: GameState, player: int) -> list[int]:
    """Legal Gear hosts: friendly Units on the field, and face-up Legends in the Legends area."""
    return s.units(player) + [i for i in s.legends(player) if s.i_faceup[i]]


# ------------------------------------------------------------------ attacking
def attack_permission(s: GameState, unit: int) -> tuple[bool, bool]:
    """(may attack Units, may attack the Gig area) for a Unit. Does not check ready/spent:
    the attacker is already spent by the time its target is declared."""
    if s.has_mod("cant_attack", unit):
        return False, False
    d = s.card(unit)
    if d.script is not None and d.script.extra.get("cant_attack"):
        return False, False
    units_ok = gigs_ok = True
    if s.i_lag[unit]:
        rival = 1 - s.i_owner[unit]
        # MaxTac Suppression Team: rival Units can't attack the turn they're played, full stop.
        suppressed = any(s.card(i).script is not None and s.card(i).script.extra.get("suppress_new_units")
                         for i in active_cards(s, first=rival) if s.i_owner[i] == rival)
        if suppressed:
            return False, False
        if not (has_keyword(s, unit, Keyword.ADRENALINE) or has_keyword(s, unit, Keyword.GO_SOLO)):
            units_ok = s.has_mod("attack_units_now", unit)
            gigs_ok = s.has_mod("attack_gigs_now", unit)
    if d.script is not None and d.script.attack_perm is not None:
        r = d.script.attack_perm(_ctx(s, unit), (units_ok, gigs_ok))
        if r is not None:
            units_ok, gigs_ok = r
    return units_ok, gigs_ok


def attack_targets(s: GameState, attacker: int) -> list[Target]:
    p = s.i_owner[attacker]
    r = 1 - p
    units_ok, gigs_ok = attack_permission(s, attacker)
    out: list[Target] = []
    if units_ok:
        ready_ok = s.has_mod("attack_ready_units", attacker)
        sc = s.card(attacker).script
        ready_blockers_ok = sc is not None and sc.extra.get("attack_ready_blockers_if_more_cred") \
            and s.street_cred(p) > s.street_cred(r)
        for u in s.units(r):
            if s.i_spent[u] or ready_ok or (ready_blockers_ok and has_keyword(s, u, Keyword.BLOCKER)):
                out.append(Target(TARGET_UNIT, u))
    if gigs_ok and (s.cfg.allow_empty_gig_attack or s.gig[r]):
        out.append(Target(TARGET_GIG))
    return out


def can_attack(s: GameState, inst: int) -> bool:
    return not s.i_spent[inst] and bool(attack_targets(s, inst))


# ------------------------------------------------------------------ abilities
def ability_options(s: GameState, player: int, quick_only: bool) -> list[Activate]:
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


# ------------------------------------------------------------------ main menu
def main_menu(s: GameState) -> list:
    p = s.active
    base = p * NZONE
    opts: list = [EndTurn()]
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


# ------------------------------------------------------------------ reactions
def reaction_menu(s: GameState) -> list:
    """The defender's options while a rival Unit is attacking."""
    atk = s.atk
    d = 1 - atk.attacker_ctrl
    opts: list = [Pass()]
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
