"""Read a tactics-suite position out loud: the board, the winning line, and what the agent does.

    python tools/explain_position.py data/arena/delayed.json --id gear-before-the-raid
    python tools/explain_position.py out/positions/legend-call-reverie-free-flip.verified.json

``learn.delayed.qualify`` decides whether a position belongs in the suite, and it is not a matter of
opinion: an exhaustive turn search must prove a winning line exists, the frozen heuristic must miss
it on every scored seed, and random must not stumble into it. What ``qualify`` cannot do is say
*why* — it stores a winning line as a list of action indices, which is exactly as readable as it
sounds.

That gap has a cost. The suite's committed entries carry a paragraph explaining what the greedy line
is, what the winning line is, and why the winning line looks worth nothing until its last move, and
that paragraph is most of what makes the file readable a month later. Positions that arrive with a
verification block and no paragraph are correct rows nobody can check, so the merge step refuses
them — and this tool is how the paragraph gets written without reverse-engineering integers.

It prints three things: the starting board as a person would read it, the solver's line narrated
move by move with the board it leaves at the end of the turn, and the frozen heuristic's line from
the same position for contrast. The difference between those last two *is* the position.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.enums import Zone  # noqa: E402
from cptcg.core.engine import apply  # noqa: E402
from cptcg.learn.delayed import (POLICY_AGENT, _materialise, build_entry, entry_horizon,
                                 confirmed_win, fixed_policy, play_turn)  # noqa: E402
from cptcg.sim.narrate import narrate  # noqa: E402

NAMES = ("the player to move", "the rival")


def _side(s, p: int) -> list[str]:
    def names(zone):
        return [s.card(i).name + (f" [{s.card(i).subtitle}]" if s.card(i).subtitle else "")
                for i in s.zone(p, zone)]
    field = []
    for i in s.zone(p, Zone.FIELD):
        if s.i_host[i] != -1 and s.card(i).type.name == "GEAR":
            continue
        gear = [s.card(g).name for g in s.zone(p, Zone.FIELD) if s.i_host[g] == i]
        from cptcg.core.ops import power
        mark = " (spent)" if s.i_spent[i] else (" (lagged)" if s.i_lag[i] else "")
        field.append(f"{s.card(i).name} {power(s, i)} power{mark}" +
                     (f" + {', '.join(gear)}" if gear else ""))
    legends = [f"{s.card(i).name}{' face-up' if s.i_faceup[i] else ' face-down'}"
               f"{' (spent)' if s.i_spent[i] else ''}" for i in s.zone(p, Zone.LEGENDS)]
    from cptcg.core.ops import available
    return [
        f"  Gigs:    {', '.join(f'd{d}={v}' for d, v in s.gig[p]) or '(none)'}"
        f"   ★ {s.street_cred(p)}",
        f"  Fixer:   {', '.join('d' + str(d) for d in s.fixer[p]) or '(empty)'}",
        # available() is everything that can pay this turn -- ready Eddie cards, a sale, a ready
        # Legend -- which is larger than the Eddies row and is the number a player actually has.
        f"  Can pay:  {available(s, p)}  ({len(s.zone(p, Zone.EDDIES))} cards in the Eddies row)",
        f"  Field:   {'; '.join(field) or '(empty)'}",
        f"  Legends: {'; '.join(legends) or '(none)'}",
        f"  Hand:    {', '.join(names(Zone.HAND)) or '(empty)'}",
        f"  Trash:   {', '.join(names(Zone.TRASH)) or '(empty)'}",
        f"  Deck:    {len(s.zone(p, Zone.DECK))} cards",
    ]


def _narrate_line(reg, entry, me, line, label, cfg):
    """Replay one line with the event log on.

    ``delayed.replay_to_end_of_turn`` cannot be reused here: it clones the state, and ``clone()``
    drops ``log`` by design, because recording inside a search that clones millions of states would
    be ruinous. So the loop is repeated here over a state built with logging from the start -- those
    fifteen lines are the price of the narration this whole tool exists to print.
    """
    c = build_entry(reg, entry, cfg)
    c.log = []
    policy = fixed_policy()
    start_turn, it, guard = c.turn, iter(line), 0
    while not c.over and c.pending is not None and c.turn == start_turn and guard < 400:
        guard += 1
        ch = _materialise(c)
        if ch.player == me:
            nxt = next(it, None)
            if nxt is None:
                break
            apply(c, nxt)
        else:
            apply(c, policy(c, ch))
    print(f"\n--- {label} ({len(line)} own decisions)")
    for ln in narrate(c, c.log or [], NAMES if me == 0 else NAMES[::-1]):
        print(f"    {ln}")
    print(f"    -> the turn ends with Gigs {c.gig[me]} (\u2605 {c.street_cred(me)}) against "
          f"{c.gig[1 - me]} (\u2605 {c.street_cred(1 - me)})")
    print(f"       and inside the horizon that "
          f"{'wins' if confirmed_win(c, me, policy=policy, max_turns=entry_horizon(entry)) else 'does not win'}")
    return c



def run(a) -> int:
    reg = load_default()
    raw = json.loads(Path(a.path).read_text(encoding="utf-8"))
    entries = raw["positions"] if isinstance(raw, dict) and "positions" in raw else [raw]
    if a.id:
        entries = [e for e in entries if e["id"] == a.id]
    if not entries:
        print(f"no position with id {a.id!r} in {a.path}")
        return 1
    for entry in entries:
        v = entry.get("verified") or {}
        me = entry.get("player", 0)
        print("=" * 100)
        print(f"{entry['id']}   horizon {entry_horizon(entry)}   player {me}")
        if v:
            print(f"solver: {v['nodes']} nodes{' (exhaustive)' if v.get('exhausted') else ''}; "
                  f"heuristic won {v['heuristic_wins']}/{len(v.get('heuristic_seeds') or ())}; "
                  f"random won {v.get('floor_wins')}/{v.get('floor_trials')}")
        if (entry.get("why") or "").strip().lower() not in ("", "placeholder"):
            print(f"\nwhy: {entry['why']}")
        s = build_entry(reg, entry, DEFAULT_CONFIG)
        mover = "the player to move" if s.active == me else "the rival"
        print(f"\nBOARD at turn {s.turn} — {mover} has the turn")
        print(f"\n  == the player to move (seat {me}) ==")
        for ln in _side(s, me):
            print(ln)
        print(f"\n  == the rival (seat {1 - me}) ==")
        for ln in _side(s, 1 - me):
            print(ln)
        if v.get("line"):
            _narrate_line(reg, entry, me, v["line"], "THE WINNING LINE the solver proved", DEFAULT_CONFIG)
        # The heuristic's own line, replayed rather than stored, so the contrast is against what the
        # frozen agent does *now* rather than what it did when the position was first qualified.
        won, hline = play_turn(build_entry(reg, entry, DEFAULT_CONFIG), me, POLICY_AGENT, seed=1)
        _narrate_line(reg, entry, me, hline, f"WHAT THE FROZEN HEURISTIC DOES INSTEAD "
                                             f"({'wins' if won else 'does not win'})", DEFAULT_CONFIG)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/explain_position.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("path", help="a suite file or a single position/.verified.json")
    ap.add_argument("--id", default="", help="one position id from a suite file")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
