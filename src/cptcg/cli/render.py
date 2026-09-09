"""Plain-text board renderer, for the CLI replay viewer and debugging."""

from __future__ import annotations

from cptcg.core.actions import Choice
from cptcg.core.enums import NZONE, CardType, Zone
from cptcg.core.ops import available, power
from cptcg.core.state import GameState


def _card(s: GameState, inst: int, show_hidden: bool = True) -> str:
    d = s.card(inst)
    flags = ""
    if s.i_spent[inst]:
        flags += "~"
    if s.i_lag[inst]:
        flags += "z"
    name = d.name + (f" ({d.subtitle})" if d.subtitle else "")
    if d.type is CardType.UNIT or (d.type is CardType.LEGEND and s.i_zone[inst] is Zone.FIELD):
        gear = s.gear_on(inst)
        g = "" if not gear else " +" + "/".join(s.card(x).name for x in gear)
        return f"{flags}{name} [{power(s, inst)}]{g}"
    if d.type is CardType.LEGEND:
        return f"{flags}{name if s.i_faceup[inst] or show_hidden else '???'}"
    return f"{flags}{name}"


def _dice(dice) -> str:
    return " ".join(f"d{k}={v}" for k, v in dice) or "-"


def render(s: GameState, perspective: int | None = None) -> str:
    out = []
    out.append(f"turn {s.turn}  active P{s.active}" + ("  OVERTIME" if s.overtime else ""))
    for p in (1, 0) if perspective in (None, 0) else (0, 1):
        base = p * NZONE
        out.append(f"--- P{p} ---")
        out.append(f"  gigs ({len(s.gig[p])}/7, cred {s.street_cred(p)}): {_dice(s.gig[p])}"
                   f"    fixer: {' '.join(f'd{k}' for k in s.fixer[p]) or '-'}")
        out.append(f"  eddies {available(s, p)} ready / {len(s.z[base + Zone.EDDIES])} cards"
                   f"    deck {len(s.z[base + Zone.DECK])}  trash {len(s.z[base + Zone.TRASH])}")
        out.append("  legends: " + ", ".join(_card(s, i, show_hidden=perspective is None) for i in s.legends(p)))
        out.append("  field: " + (", ".join(_card(s, i) for i in s.units(p)) or "-"))
        hidden = perspective is not None and perspective != p
        hand = s.z[base + Zone.HAND]
        out.append("  hand: " + (f"{len(hand)} cards" if hidden else ", ".join(_card(s, i) for i in hand)))
    if s.over:
        out.append(f"GAME OVER: P{s.winner} wins by {s.end_reason.name}")
    elif s.pending is not None:
        out.append(f"P{s.pending.player} to choose: {s.pending.prompt}")
    return "\n".join(out)


def describe(s: GameState, choice: Choice, idx: int) -> str:
    """One-line description of an action for a replay log."""
    a = choice.options[idx]
    name = type(a).__name__
    inst = getattr(a, "inst", None)
    if inst is not None and inst >= 0:
        return f"P{choice.player} {name} {s.card(inst).name}"
    return f"P{choice.player} {name} {a}"
