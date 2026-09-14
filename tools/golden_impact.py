"""Before and after a card fix: which golden games may change, and did only those change?

    python tools/golden_impact.py predict zetatech-faceplate
    python tools/golden_impact.py verify  zetatech-faceplate

``tests/golden/games.json`` pins 224 games as exact action-index streams, and a genuine card fix
will legitimately change some of them. The danger is not the change; it is regenerating the golden
file on a diff nobody localised, which converts "the fix worked" into "the fix and whatever else
was on the tree at the time". The file's history has exactly one deliberate regeneration in it, and
that is the standard worth keeping.

Two facts make this cheap. ``bench.py check`` is about seven seconds, so gating every fix
individually costs nothing. And the eight golden decks between them reach only 95 of the 151 cards —
so **54 scripted cards cannot appear in any golden game at all**, and a fix to one of those must
leave ``check`` IDENTICAL. If it does not, the edit escaped its card, which is a bug in the fix.

    tier G0   no golden deck contains the card    check MUST stay IDENTICAL
    tier G1   some golden deck contains it        only keys whose decks contain it may differ

``predict`` is evidence 1 of the protocol: write down the key set that *may* change, from deck
membership alone, before touching anything. ``verify`` runs the check, and refuses the result when
an observed key is outside that prediction — the hard stop. It also prints evidence 2 (the replay
around the first divergence, in which the fixed card must actually appear) and evidence 4 (the
aggregate: games changed, winner flips, end-reason changes, mean turn delta).

Evidence 3 (revert the script hunk, keep the new golden, and check the same keys go DIFFERENT) and
evidence 5 (``bench.py fuzz`` must move for a G0 fix, since the golden cannot see those 54 cards)
stay manual, because both are about what you do next rather than about this run.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from bench import GOLDEN, MATCHUPS, _deck, play_all  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.core.engine import apply, legal_actions  # noqa: E402
from cptcg.sim.narrate import narrate  # noqa: E402
from cptcg.sim.runner import new_game  # noqa: E402

AGENTS = ("heuristic", "random")


def deck_cards(name: str) -> set[str]:
    d = _deck(name)
    return set(d.main) | set(d.legends)


def predict(cards: list[str]) -> tuple[set[str], dict[str, set[str]]]:
    """``(keys that may change, which named card put each matchup on the list)``."""
    want = set(cards)
    keys, why = set(), {}
    for a, b in MATCHUPS:
        hit = (deck_cards(a) | deck_cards(b)) & want
        if hit:
            why[f"{a}~{b}"] = hit
            for agent in AGENTS:
                keys.add(f"{a}~{b}~{agent}")
    return keys, why


def _narrate_new_game(key: str, game: dict, window: int, cards: set):
    """The game as the **current** engine plays it, told as sentences, ending at the divergence.

    The obvious implementation is wrong and was shipped wrong for one commit: replay the *golden*
    action indices on the fixed engine and narrate that. It reads as sound -- the streams agree up
    to the divergence, so surely the board does too -- and it is not. An action index identifies a
    position in an option list, not a move. A fix that removes an option changes what index *i*
    means, and a fix that removes a whole decision (``AskStep`` resolves a one-option choice inline,
    so dropping ``optional=True`` can delete a question entirely) shifts every index after it. The
    replay then keeps succeeding, because the shifted indices stay in range, and narrates a game
    that never happened. The Unlikely Bond fix produced exactly that: a plausible window with no
    mention of the card, which read as a hard stop and was an artefact of the instrument.

    So this narrates the game the current engine actually plays, which needs no such assumption.
    The evidence it supports is correspondingly narrower and still the evidence that matters: the
    fixed card has to appear in the run-up to the point where the two games part company.
    """
    a, b, agent = key.split("~")
    da, db = _deck(a), _deck(b)
    decks = (da, db) if game["seat"] == 0 else (db, da)
    reg = load_default()
    s = new_game(reg, decks, game["seed"], record=True)
    ags = [make_agent(agent, game["seed"] * 2 + i) for i in (0, 1)]
    for p, ag in enumerate(ags):
        ag.new_game(game["seed"], p)
    played, first_offered = [], None
    while not s.over and len(played) < len(game["actions"]) + 200:
        legal_actions(s)
        ch = s.pending
        if ch is None:
            break
        if first_offered is None and _offers(s, ch, cards):
            first_offered = len(played)
        i = ags[ch.player].act(s, ch)
        played.append(i)
        apply(s, i)
        if len(played) <= len(game["actions"]) and played[-1] != game["actions"][len(played) - 1]:
            break                                   # the first index at which the two games part
    names = (f"{a} (seat 0)", f"{b} (seat 1)") if game["seat"] == 0 else \
            (f"{b} (seat 0)", f"{a} (seat 1)")
    return narrate(s, s.log or [], names)[-window:], first_offered, len(played) - 1


def _offers(s, ch, cards: set) -> bool:
    """Was one of the fixed cards an option the agent had to weigh at this decision?

    Not "was it played" — that rule is too narrow and reads a real change as unexplained. The
    frozen heuristic scores candidate actions by resolving them a ply deep, so a card sitting in
    hand as a legal Play changes what the agent *thinks the board is worth* whether or not it ends
    up being cast. Unlikely Bond first became playable eight decisions before the game diverged and
    was never actually played in it: the fix changed the preview, the preview changed a later
    tie-break, and the card never touched the table. "Present and actionable" is the claim the
    evidence can support, so it is the claim this reports.
    """
    from cptcg.core.actions import Activate, Attack, CallLegend, GoSolo, Play
    for o in ch.options:
        inst = getattr(o, "inst", None)
        if inst is not None and isinstance(o, (Play, Attack, Activate, CallLegend, GoSolo)) \
                and s.card(inst).id in cards:
            return True
    return False


def cmd_predict(a) -> int:
    keys, why = predict(a.cards)
    print(f"cards: {', '.join(a.cards)}")
    if not keys:
        print("\ntier G0 — no golden deck contains any of these cards.")
        print("`bench.py check` MUST print IDENTICAL. If it does not, the edit escaped its card.")
        print("`bench.py fuzz` MUST move, or the fix is a no-op the golden cannot see.")
        return 0
    print("\ntier G1 — these matchups contain the card(s):")
    for pair, hit in sorted(why.items()):
        print(f"  {pair:40s} via {', '.join(sorted(hit))}")
    print(f"\n{len(keys)} key(s) may differ, and no others:")
    for k in sorted(keys):
        print(f"  {k}")
    return 0


def cmd_verify(a) -> int:
    predicted, _ = predict(a.cards)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    now = play_all()

    observed, detail = set(), {}
    for key, games in golden.items():
        got = now.get(key) or []
        diffs = [(i, x, y) for i, (x, y) in enumerate(zip(games, got)) if x != y]
        if diffs:
            observed.add(key)
            detail[key] = diffs

    print(f"cards: {', '.join(a.cards)}")
    print(f"predicted {len(predicted)} key(s) may change; {len(observed)} changed.\n")

    escaped = observed - predicted
    if escaped:
        print("HARD STOP — these keys changed but their decks contain none of the named cards:")
        for k in sorted(escaped):
            print(f"  {k}")
        print("\nThe edit escaped its card. Do not regenerate the golden; fix the fix.")
        return 1
    if not observed:
        print("IDENTICAL. For a G0 card that is the expected result — now run `bench.py fuzz` on"
              "\nthis branch and on the parent commit; the digest must differ, or the fix is a no-op.")
        return 0

    print("Every changed key was predicted. Aggregate:")
    for key in sorted(observed):
        diffs = detail[key]
        total = len(golden[key])
        flips = sum(1 for _, x, y in diffs if x["winner"] != y["winner"])
        ends = sum(1 for _, x, y in diffs if x["end"] != y["end"])
        dt = statistics.fmean([y["turns"] - x["turns"] for _, x, y in diffs])
        print(f"  {key:44s} {len(diffs):>3}/{total} games  winner flips {flips:>2}  "
              f"end-reason {ends:>2}  mean turn delta {dt:+.2f}")

    print("\nFirst divergence in each changed key — a named card must have been available before it:")
    for key in sorted(observed):
        i, x, y = detail[key][0]
        at = next((k for k, (p, q) in enumerate(zip(x["actions"], y["actions"])) if p != q),
                  min(len(x["actions"]), len(y["actions"])))
        lines, offered, where = _narrate_new_game(key, x, a.window, set(a.cards))
        print(f"\n  --- {key} game {i} (seed {x['seed']}, seat {x['seat']}), diverges at "
              f"decision {where} — shown as the CURRENT engine plays it")
        if offered is None:
            print(f"      NO NAMED CARD WAS EVER AN OPTION before the divergence. "
                  f"The change here is unexplained — stop.")
        else:
            print(f"      a named card first became a legal option at decision {offered}, "
                  f"{where - offered} before the divergence")
        for line in lines:
            print(f"      {line}")
    print("\nRead each window. A named card has to have been *available to the agent* before the"
          "\ndivergence — the line above each window says when it first was. It does not have to"
          "\nappear in the narration: the frozen heuristic scores candidate actions a ply deep, so a"
          "\ncard sitting in hand changes its arithmetic without ever being cast. If no named card"
          "\nwas ever an option, the change is unexplained and regenerating would freeze it in.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/golden_impact.py",
                                 description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("predict", help="which golden keys may change, from deck membership alone")
    p.add_argument("cards", nargs="+")
    p.set_defaults(fn=cmd_predict)
    v = sub.add_parser("verify", help="run the check and hold the result against the prediction")
    v.add_argument("cards", nargs="+")
    v.add_argument("--window", type=int, default=12, help="narration lines before the divergence")
    v.set_defaults(fn=cmd_verify)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
