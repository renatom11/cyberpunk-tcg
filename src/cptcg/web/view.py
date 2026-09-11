"""JSON view of a game state from one player's perspective (or omniscient with None)."""

from __future__ import annotations

from cptcg.core.actions import (Activate, Attack, Block, CallLegend, ChoiceKind, ChooseOrder, EndTurn,
                                GoSolo, Mulligan, Pass, Pick, Play, Sell, TakeGigDie, Target)
from cptcg.core.engine import legal_actions
from cptcg.core.legal import attack_permission
from cptcg.core.enums import NO_INST, NZONE, TARGET_GIG, CardType, Keyword, Zone
from cptcg.core.ops import ATTACKING, available, has_keyword, payable_sources, play_cost, power
from cptcg.core.state import GameState
from cptcg.core.view import hand_visible, legend_identity_known


def card_json(s: GameState, inst: int) -> dict:
    d = s.card(inst)
    return {"inst": inst, "id": d.id, "name": d.name, "subtitle": d.subtitle, "type": d.type.name.title(),
            "color": d.color.name.title(), "cost": d.cost, "power": (f"{d.power}+" if d.power_variable else d.power),
            "ram": d.ram, "sell_tag": d.sell_tag, "tags": sorted(d.tags),
            "keywords": [k.name.replace("_", " ") for k in d.keywords], "text": d.text}


def _in_play(s: GameState, inst: int) -> dict:
    j = card_json(s, inst)
    # A GO SOLO Legend arrives Lagged (CR 4.5.2) but its keyword lets it attack anyway, and
    # ADRENALINE does the same. The rules state and what the player can actually do therefore come
    # apart, so the board sends both: `lag` is the rule, `lag_blocks` is whether it is stopping
    # anything. The badge reads the second, or it tells the player a card is stuck when it is not.
    lag = bool(s.i_lag[inst])
    j.update({"power_now": power(s, inst, ATTACKING), "spent": bool(s.i_spent[inst]), "lag": lag,
              "lag_blocks": lag and not any(attack_permission(s, inst)),
              "blocker": has_keyword(s, inst, Keyword.BLOCKER),
              "gear": [dict(card_json(s, g), spent=bool(s.i_spent[g])) for g in s.gear_on(inst)]})
    return j


def _label(s: GameState, a) -> tuple[str, str, int | None]:
    """(label, kind, inst) for an action."""
    n = lambda i: s.card(i).name + (f" ({s.card(i).subtitle})" if s.card(i).subtitle else "")  # noqa: E731
    if isinstance(a, EndTurn):
        return "End turn", "EndTurn", None
    if isinstance(a, Mulligan):
        return ("Keep", "Keep", None) if a.keep else ("Mulligan", "Mulligan", None)
    if isinstance(a, ChooseOrder):
        return ("Go first", "GoFirst", None) if a.go_first else ("Go second", "GoSecond", None)
    if isinstance(a, TakeGigDie):
        return f"Roll d{a.sides}", "Die", a.sides
    if isinstance(a, Sell):
        return f"Sell {n(a.inst)}", "Sell", a.inst
    if isinstance(a, Play):
        if a.host >= 0:
            return f"Play {n(a.inst)} on {n(a.host)}", "Play", a.inst
        return f"Play {n(a.inst)}", "Play", a.inst
    if isinstance(a, GoSolo):
        return f"GO SOLO: {n(a.inst)}", "GoSolo", a.inst
    if isinstance(a, CallLegend):
        return "Call a Legend (1 €$)", "Call", a.inst
    if isinstance(a, Activate):
        sc = s.card(a.inst).script
        lab = sc.abilities[a.ability].label if sc and sc.abilities else "ability"
        return f"{n(a.inst)}: {lab}", "Activate", a.inst
    if isinstance(a, Attack):
        return f"Attack with {n(a.inst)}", "Attack", a.inst
    if isinstance(a, Target):
        return ("Attack the Gig area", "TargetGig", None) if a.kind == TARGET_GIG else (f"Attack {n(a.inst)}", "Target", a.inst)
    if isinstance(a, Block):
        return f"Block with {n(a.inst)}", "Block", a.inst
    if isinstance(a, Pass):
        return "Pass", "Pass", None
    if isinstance(a, Pick):
        return ("Decline" if not a.picks else "Choose " + ", ".join(str(p) for p in a.picks)), "Pick", None
    return repr(a), "Other", None


def _cost(s: GameState, player: int, a) -> int:
    """€$ this action spends. 0 for everything that costs nothing, so the client can ignore it."""
    if isinstance(a, Play):
        return play_cost(s, player, a.inst)
    if isinstance(a, GoSolo):
        return play_cost(s, player, a.inst, go_solo=True)
    if isinstance(a, CallLegend):
        return 1
    if isinstance(a, Activate):
        sc = s.card(a.inst).script
        ab = sc.abilities[a.ability]
        try:
            return int(ab.cost(_ctx_for(s, a.inst)) if callable(ab.cost) else ab.cost)
        except Exception:      # noqa: BLE001  a cost that needs a live context is not worth a crash here
            return 0
    return 0


def _ctx_for(s: GameState, inst: int):
    from cptcg.core.ops import _ctx
    return _ctx(s, inst)


def _pick_labels(s: GameState) -> list[str] | None:
    """For PICK choices, try to describe each option using the continuation's captured values."""
    ch = s.pending
    cont = ch.cont
    try:
        cells = cont.__closure__ or ()
        names = cont.__code__.co_freevars
        env = {nm: c.cell_contents for nm, c in zip(names, cells)}
    except Exception:  # noqa: BLE001
        return None
    vals = env.get("vals")
    if vals is None:
        if "Steal" in (ch.prompt or ""):                      # steal picks index the victim's Gig area
            victim = 1 - ch.player
            out = []
            for o in ch.options:
                out.append(", ".join(f"rival d{s.gig[victim][i][0]}={s.gig[victim][i][1]}" for i in o.picks
                                     if i < len(s.gig[victim])) or "Decline")
            return out
        return None
    out = []
    for o in ch.options:
        if not o.picks:
            out.append("Decline")
            continue
        parts = []
        for i in o.picks:
            v = vals[i] if i < len(vals) else i
            parts.append(_describe_value(s, v))
        out.append(", ".join(parts))
    return out


def _describe_value(s: GameState, v) -> str:
    if isinstance(v, int) and 0 <= v < len(s.i_card) and not isinstance(v, bool):
        d = s.card(v)
        return d.name + (f" ({d.subtitle})" if d.subtitle else "")
    if isinstance(v, tuple):
        if len(v) == 5 and all(isinstance(x, int) for x in v):        # (owner, index, amount, sides, value)
            o, i, a, k, val = v
            return f"{'your' if o == s.pending.player else 'rival'} d{k}={val} {a:+d}"
        if len(v) == 4 and all(isinstance(x, int) for x in v):        # (owner, index, sides, value)
            o, i, k, val = v
            return f"{'your' if o == s.pending.player else 'rival'} d{k}={val}"
        if len(v) == 2 and isinstance(v[0], str):
            return v[0]
        if len(v) == 2 and all(isinstance(x, int) for x in v) and 0 <= v[0] <= 1:
            o, i = v
            gigs = s.gig[o]
            if i < len(gigs):
                return f"{'your' if o == s.pending.player else 'rival'} d{gigs[i][0]}={gigs[i][1]}"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if hasattr(v, "name"):
        return str(v.name).title()
    return str(v)


def view_state(s: GameState, perspective: int | None, names: tuple[str, str], log: list[str]) -> dict:
    legal_actions(s)
    players = []
    for p in (0, 1):
        base = p * NZONE
        # Redaction rules live in core/view.py; this module only renders them.
        visible = hand_visible(s, perspective, p)
        legends = []
        for i in s.legends(p):
            known = legend_identity_known(s, perspective, i)
            j = {"inst": i, "faceup": bool(s.i_faceup[i]), "spent": bool(s.i_spent[i]),
                 "gear": [card_json(s, g) for g in s.gear_on(i)]}
            if s.i_faceup[i] or known:
                j.update(card_json(s, i))
                j["known_only"] = not s.i_faceup[i]
            legends.append(j)
        hand = s.z[base + Zone.HAND]
        pj = {
            "name": names[p], "seat": p,
            "hand": [dict(card_json(s, i), cost_now=play_cost(s, p, i)) for i in hand] if visible else None,
            "hand_count": len(hand),
            "field": [_in_play(s, i) for i in s.units(p)],
            "legends": legends,
            # Sold cards were revealed when sold, so their identities are public (ruling 002).
            "eddies": {"ready": available(s, p), "cards": len(s.z[base + Zone.EDDIES]),
                       "total": len(s.z[base + Zone.EDDIES]) + len(s.legends(p)),
                       "list": [dict(card_json(s, i), spent=bool(s.i_spent[i])) for i in s.z[base + Zone.EDDIES]]},
            # What this player could spend to pay a cost, in the order the engine would pick if left
            # alone. The client offers a choice from this; ruling 025 otherwise decides silently.
            "pay_sources": [{"inst": i, "name": s.card(i).name,
                             "where": "Legend" if s.i_zone[i] == Zone.LEGENDS else "Eddie",
                             "faceup": bool(s.i_faceup[i]) and s.i_zone[i] == Zone.LEGENDS}
                            for i in payable_sources(s, p)] if p == perspective else None,
            "deck": len(s.z[base + Zone.DECK]),
            "trash": [card_json(s, i) for i in s.z[base + Zone.TRASH]],
            "removed": [card_json(s, i) for i in s.z[base + Zone.REMOVED]],
            "gigs": [list(g) for g in s.gig[p]], "fixer": list(s.fixer[p]), "cred": s.street_cred(p),
        }
        players.append(pj)
    pending = None
    if s.pending is not None and not s.over:
        ch = s.pending
        pick_labels = _pick_labels(s) if ch.kind is ChoiceKind.PICK else None
        opts = []
        for idx, a in enumerate(ch.options):
            label, kind, inst = _label(s, a)
            if pick_labels and idx < len(pick_labels):
                label = pick_labels[idx]
            opts.append({"index": idx, "label": label, "kind": kind, "inst": inst,
                         "cost": _cost(s, ch.player, a),
                         "host": getattr(a, "host", -1) if isinstance(a, Play) else -1})
        phase = {ChoiceKind.MULLIGAN: "Opening hand", ChoiceKind.ORDER: "Turn order", ChoiceKind.GIG_DIE: "Start phase",
                 ChoiceKind.MAIN: "Main phase", ChoiceKind.TARGET: "Attack", ChoiceKind.REACTION: "Rival reacts",
                 ChoiceKind.PICK: "Choose"}[ch.kind]
        pending = {"kind": ch.kind.name, "player": ch.player, "prompt": ch.prompt, "phase": phase, "options": opts}
    return {"turn": s.turn, "active": s.active, "first_player": s.first_player, "overtime": s.overtime,
            "over": s.over, "winner": s.winner if s.over else None,
            "end_reason": s.end_reason.name if s.over else None, "perspective": perspective,
            "players": players, "pending": pending, "log": log, "atk": _atk(s)}


def _atk(s: GameState) -> dict | None:
    a = s.atk
    if a is None:
        return None
    return {"attacker": a.attacker, "target_kind": a.target_kind, "target": a.target}
