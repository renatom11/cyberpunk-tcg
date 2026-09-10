"""Turn the engine's event log into sentences, like the game log panel of the online sim."""

from __future__ import annotations

from cptcg.core.actions import (Activate, Attack, Block, CallLegend, ChoiceKind, ChooseOrder, EndTurn,
                                GoSolo, Mulligan, Pass, Pick, Play, Sell, TakeGigDie, Target)
from cptcg.core.enums import TARGET_GIG, CardType, EndReason, Zone
from cptcg.core.state import GameState


def _name(s: GameState, inst: int) -> str:
    d = s.card(inst)
    return d.name + (f" — {d.subtitle}" if d.subtitle else "")


def narrate(s: GameState, events: list, names: tuple[str, str]) -> list[str]:
    """Sentences for a slice of ``s.log``. Card names are resolved against the *current* state,
    which is fine: identities never change."""
    out: list[str] = []
    P = lambda p: names[p]  # noqa: E731
    for ev in events:
        k = ev[0]
        if k == "turn":
            out.append(f"— Turn {ev[1]}: {P(ev[2])} —")
        elif k == "roll_off":
            out.append(f"Roll-off: {P(0)} rolled {ev[1]}, {P(1)} rolled {ev[2]}. {P(ev[3])} chooses.")
        elif k == "first":
            out.append(f"{P(ev[1])} goes first (2 leftmost Legends start spent). Both draw 6.")
        elif k == "mulligan":
            out.append(f"{P(ev[1])} mulligans.")
        elif k == "gig":
            out.append(f"{P(ev[1])} rolls d{ev[2]} for {ev[3]} and adds it to the Gig area.")
        elif k == "action":
            kind, p, a = ev[1], ev[2], ev[3]
            if isinstance(a, Mulligan):
                if a.keep:
                    out.append(f"{P(p)} keeps the opening hand.")
            elif isinstance(a, ChooseOrder):
                out.append(f"{P(p)} chooses to go {'first' if a.go_first else 'second'}.")
            elif isinstance(a, Sell):
                out.append(f"{P(p)} sells {_name(s, a.inst)} for an Eddie.")
            elif isinstance(a, Play):
                d = s.card(a.inst)
                host = f" on {_name(s, a.host)}" if a.host >= 0 else ""
                out.append(f"{P(p)} plays {_name(s, a.inst)} ({d.type.name.title()}){host}.")
            elif isinstance(a, GoSolo):
                out.append(f"{P(p)}: {_name(s, a.inst)} GOES SOLO onto the field.")
            elif isinstance(a, CallLegend):
                out.append(f"{P(p)} Calls a Legend: {_name(s, a.inst)} is revealed.")
            elif isinstance(a, Activate):
                sc = s.card(a.inst).script
                label = sc.abilities[a.ability].label if sc and sc.abilities else "ability"
                out.append(f"{P(p)} activates {_name(s, a.inst)}: {label}.")
            elif isinstance(a, Attack):
                out.append(f"{P(p)} attacks with {_name(s, a.inst)}.")
            elif isinstance(a, Target):
                out.append("  → targeting the Gig area." if a.kind == TARGET_GIG else f"  → targeting {_name(s, a.inst)}.")
            elif isinstance(a, Block):
                out.append(f"{P(p)} BLOCKS with {_name(s, a.inst)}.")
            elif isinstance(a, Pass):
                out.append(f"{P(p)} does not react.")
            elif isinstance(a, TakeGigDie):
                pass  # the 'gig' event narrates the roll
            elif isinstance(a, EndTurn):
                out.append(f"{P(p)} ends the turn.")
            elif isinstance(a, Pick):
                if kind is ChoiceKind.PICK and not a.picks:
                    out.append(f"{P(p)} declines.")
        elif k == "fight":
            out.append(f"Fight: {_name(s, ev[1])} ({ev[3]}) vs {_name(s, ev[2])} ({ev[4]}).")
        elif k == "defeated":
            out.append(f"{_name(s, ev[1])} is defeated.")
        elif k == "steal":
            out.append(f"{P(ev[1])} steals a d{ev[2][0]} showing {ev[2][1]}.")
        elif k == "adjust":
            out.append(f"{P(ev[1])}'s Gig changes from {ev[3]} to {ev[4]}.")
        elif k == "swap":
            out.append(f"{P(ev[1])} swaps a Gig with the rival.")
        elif k == "reroll":
            out.append(f"{P(ev[1])} rerolls a Gig: {ev[3]}.")
        elif k == "draw":
            if ev[2] > 1:
                out.append(f"{P(ev[1])} draws {ev[2]} cards.")
            elif ev[2] == 1:
                out.append(f"{P(ev[1])} draws a card.")
        elif k == "discard":
            out.append(f"{P(s.i_owner[ev[1]])} discards {_name(s, ev[1])}.")
        elif k == "look":
            out.append(f"{P(ev[1])} looks at a face-down Legend.")
        elif k == "overtime":
            out.append("OVERTIME begins: a majority of Gigs wins instantly.")
        elif k == "end":
            reason = {EndReason.SEVEN_GIGS: "by holding 7 Gigs", EndReason.DECKOUT: "by deckout",
                      EndReason.OVERTIME: "on Overtime majority", EndReason.CONCEDE: "by concession"}[ev[2]]
            out.append(f"GAME OVER — {P(ev[1])} wins {reason}.")
    return out
