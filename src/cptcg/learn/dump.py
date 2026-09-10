"""One stored game, rendered for a person to read.

This is the archival half of ``learn/experience.py``. The file on disk is compact and dull on
purpose — indices and packed bytes — so something has to turn it back into sentences, or "we kept
the experience" quietly means "we kept numbers nobody will ever look at again". A later analyst
should be able to open a generation and read **what the AI considered and what it chose**, not
just who won.

So every decision is printed with all of its legal options in words, the search's visit share
beside each one, and a marker on the one that was played. The wording is not invented here: it
comes from ``web/view.view_state``, the same labelling the browser shows a human player, so the
dump and the UI can never drift apart and a Pick option gets the same careful description in both.

Optimised for reading, not for parsing: if a tool wants these numbers it should call
``experience.replay_features``, which hands them over as data.
"""

from __future__ import annotations

from pathlib import Path

from cptcg.cards.registry import Registry
from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.core.enums import NZONE, Zone
from cptcg.core.state import GameState
from cptcg.learn.experience import GameRecord, dequantise_value, read_games, visit_policy
from cptcg.web.view import view_state

BAR = 20          # widest visit bar, in characters
COL = 74          # column the visit numbers start in, so they line up down the page


def load_game(path: str | Path, index: int = 0, *, rules: str | None = None) -> GameRecord:
    """The ``index``-th record in an experience file. ``rules`` as in ``experience.read_games``."""
    for i, r in enumerate(read_games(path, rules=rules)):
        if i == index:
            return r
    raise IndexError(f"{path}: no game at index {index}")


def _deck_line(record: GameRecord, reg: Registry, p: int) -> str:
    d = record.decks[p]
    legends = ", ".join(reg.get(c).name for c in d["legends"])
    n = sum(d["main"].values()) if isinstance(d["main"], dict) else len(d["main"])
    return f"  P{p}  {d['name']:<24} {n} cards   Legends: {legends}"


def _score(s: GameState) -> str:
    """The running score, so a reader can see the game move without re-deriving it."""
    return (f"gigs {len(s.gig[0])}-{len(s.gig[1])}   "
            f"cred {s.street_cred(0)}-{s.street_cred(1)}   "
            f"units {len(s.units(0))}-{len(s.units(1))}   "
            f"hand {len(s.z[Zone.HAND])}-{len(s.z[NZONE + Zone.HAND])}")


def render_game(record: GameRecord, reg: Registry, cfg: RulesConfig = DEFAULT_CONFIG) -> str:
    """The whole game as text: header, every decision with its options, then the result."""
    rep = record.replay()
    names = (str(record.decks[0]["name"]), str(record.decks[1]["name"]))
    out: list[str] = []
    out.append(f"GAME  seed {record.seed}   ruleset {record.rules}   "
               f"agents {record.agents[0]} vs {record.agents[1]}")
    out.append(_deck_line(record, reg, 0))
    out.append(_deck_line(record, reg, 1))
    searched = record.visits is not None
    budget = f", {record.sims} search iterations per decision" if record.sims else ""
    out.append(f"  {record.n_decisions} decisions"
               + (f", with search visit counts{budget}" if searched
                  else ", no search output (the agent did not search)"))
    if record.meta:
        out.append("  meta: " + ", ".join(f"{k}={v}" for k, v in sorted(record.meta.items())))

    turn = active = None
    final: GameState | None = None
    for i, (s, idx) in enumerate(rep.steps(reg, cfg)):
        final = s
        if idx is None:
            break
        if (s.turn, s.active) != (turn, active):
            turn, active = s.turn, s.active
            head = "Setup" if s.turn == 0 else f"Turn {s.turn}, P{s.active} active"
            out.append("")
            out.append(f"--- {head} {'-' * max(4, 34 - len(head))}   {_score(s)}")
        out.extend(_decision(s, i, idx, record, names))

    out.append("")
    out.append(_result(record, final))
    return "\n".join(out)


def _decision(s: GameState, i: int, chosen: int, record: GameRecord,
              names: tuple[str, str]) -> list[str]:
    v = view_state(s, None, names, [])
    pend = v["pending"]
    if pend is None:                       # the game ended on the previous action
        return []
    who = pend["player"]
    head = f"  #{i:<4} P{who}  {pend['phase']}"
    if pend["prompt"] and pend["prompt"] != pend["phase"]:
        head += f" - {pend['prompt']}"
    if record.values is not None:
        head += f"    [search value {dequantise_value(record.values[i]):.3f} for P{who}]"
    lines = [head]

    visits = record.visits[i] if record.visits is not None else []
    share = visit_policy(visits) if visits else []
    for o in pend["options"]:
        k = o["index"]
        mark = "->" if k == chosen else "  "
        text = f"      {mark} [{k:>2}] {o['label']}"
        if visits and k < len(visits):
            bar = "#" * round(share[k] * BAR)
            text = f"{text:<{COL}}{visits[k]:>4}  {share[k] * 100:3.0f}%  {bar}"
        lines.append(text.rstrip())
    return lines


def _result(record: GameRecord, final: GameState | None) -> str:
    if record.winner is None:
        return f"RESULT: no winner ({record.end_reason}) after {record.turns} turns."
    name = record.decks[record.winner]["name"]
    line = (f"RESULT: P{record.winner} ({name}) wins by {record.end_reason} "
            f"on turn {record.turns}.")
    if final is not None and final.over and final.winner != record.winner:
        line += f"  [!] the replay ends with P{final.winner} winning: this record is corrupt."
    return line
