"""Propose a tactics-suite position; let the exhaustive solver decide whether it is one.

    python tools/propose_positions.py check out/positions/my-idea.json
    python tools/propose_positions.py check out/positions/*.json --quiet
    python tools/propose_positions.py template            # a skeleton spec to start from
    python tools/propose_positions.py merge out/positions/*.verified.json [--apply]

Why this exists
---------------
``data/arena/delayed.json`` held **8** positions for most of this project's life, and every agent
comparison was bottlenecked by that number: "4 of 8" against "6 of 8" is a two-position difference
on a tiny sample. Growing the suite is the cheapest way to make every future measurement more
sensitive. It is 21 as of the first merge through this tool.

The loop is propose-and-verify, and the verifier is not a matter of opinion. ``learn.delayed.qualify``
runs an **exhaustive** ``turn_search`` over the acting player's own decisions and requires all of:

* the solver *proves* a winning line exists inside the horizon;
* the frozen one-ply heuristic misses it on **every** qualifying seed;
* uniform random play wins at most ``MAX_FLOOR`` (25%) of the scoring seeds;
* at horizon 2, the winning Gig count is still off the board when the searched turn ends — otherwise
  it is a within-turn puzzle wearing a "delayed" label.

So a bad proposal cannot enter the suite. It comes back ``ok: false`` with the reason, and the only
cost of a wrong idea is the seconds the solver spent refuting it. That is the property worth having:
this tool's output is correct by construction, and the only open question is yield.

Writing a spec
--------------
A spec is the same shape ``tests/conftest.board`` builds, as JSON — see ``learn.delayed.build_position``.
Both sides need a plausible mid-game board: three Legends, a real remaining deck, Eddies, a Gig area
and a fixer. The **last** card of a ``deck`` list is the top of the deck (``ops.draw`` and the peeks
take ``deck[-1]``), so a card a line must draw or reveal goes at the end of the list. Positions with a bare board are not wrong, but a value head reading list size, undrawn
fraction and Legend RAM is extrapolating on them, and the suite is supposed to measure play rather
than extrapolation.

What makes a *good* proposal, as opposed to a legal one: the winning line must be worth nothing on
the board until its last move. If attacking immediately is close to as good, the heuristic will find
it and the position will be refuted for that reason — which is the check doing its job.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import cards_digest, load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.learn.delayed import entry_horizon, qualify  # noqa: E402

TEMPLATE = {
    "id": "my-position-id",
    "kind": "board",
    "player": 0,
    "max_turns": 1,
    "source": "proposed",
    "why": "One paragraph: what the greedy line is, what the winning line is, and why the winning "
           "line looks worth nothing until its last move.",
    "spec": {
        "turn": 9, "active": 0, "seed": 7, "turns_taken": [4, 4],
        "sides": [
            {"field": [["rockn-rockerboy", {}]], "hand": ["mantis-blades"],
             "legends": ["goro-takemura-hands-unclean", "v-corporate-exile",
                         "hanako-arasaka-daughter-of-the-emperor"],
             "deck": ["field-operator", "corpo-security"],
             "eddies": 2, "gig": [[4, 3], [6, 2], [8, 5], [10, 7], [12, 1]], "fixer": [20]},
            {"legends": ["goro-takemura-hands-unclean", "v-corporate-exile",
                         "royce-psycho-on-the-edge"],
             "deck": ["mox-inciters", "ruthless-lowlife"],
             "eddies": 1, "gig": [[4, 2], [6, 5], [8, 3]], "fixer": [10, 12, 20]},
        ],
    },
}


def _why(v: dict) -> str:
    """The one-line reason a candidate was refused, in the order the definition applies."""
    if not v.get("solver_found_win"):
        return ("no winning line exists inside the horizon"
                + ("" if v.get("exhausted") else " (and the search ran out of budget, so this is "
                                                  "'not found', not 'not there')"))
    if v.get("heuristic_wins"):
        return (f"the frozen heuristic finds it too, on {v['heuristic_wins']} of "
                f"{len(v.get('heuristic_seeds') or ())} seeds — a position the greedy agent solves "
                f"is not measuring anything")
    if v.get("floor_rate", 0) > v.get("max_floor", 0.25):
        return (f"uniform random wins {v['floor_wins']}/{v['floor_trials']} "
                f"({v['floor_rate']:.0%}) — above the {v['max_floor']:.0%} floor, so it is winnable "
                f"by too many lines to be one line")
    if not v.get("reward_is_late"):
        return ("the payoff is already on the board when the turn ends, so a one-ply agent scoring "
                "its own end-of-turn board would see it — a within-turn puzzle labelled delayed")
    return "unknown"


SUITE = ROOT / "data" / "arena" / "delayed.json"


def _signature(entry: dict) -> tuple:
    """What makes a position *this* position: both boards, the Gigs, and whose turn it is.

    A re-skin of an existing entry qualifies just as happily as a new idea — the solver has no
    opinion about novelty — so duplicates have to be caught here or the suite grows without getting
    any more informative. Deck order is excluded: the same board with a shuffled remainder is the
    same tactical problem.
    """
    spec = entry.get("spec") or {}
    sides = []
    for side in spec.get("sides", ()):
        sides.append((
            tuple(sorted(json.dumps(x, sort_keys=True) for x in side.get("field", ()))),
            tuple(sorted(json.dumps(x, sort_keys=True) for x in side.get("hand", ()))),
            tuple(sorted(json.dumps(x, sort_keys=True) for x in side.get("legends", ()))),
            tuple(sorted(tuple(g) for g in side.get("gig", ()))),
            side.get("eddies", 0),
        ))
    return (spec.get("active", 0), entry.get("player", 0), tuple(sides))


def _existing() -> dict:
    if not SUITE.exists():
        return {}
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    out = {}
    for e in suite.get("positions", ()):
        if e.get("kind") == "board":
            out[_signature(e)] = e["id"]
    return out


def check(paths: list[str], quiet: bool) -> int:
    reg = load_default()
    seen = _existing()
    ok, bad = [], []
    for path in paths:
        entry = json.loads(Path(path).read_text(encoding="utf-8"))
        sig = _signature(entry)
        if sig in seen:
            bad.append((entry.get("id", path), f"duplicate board of {seen[sig]!r}"))
            print(f"  REFUSED  {entry.get('id', path)}  same board as existing {seen[sig]!r}")
            continue
        seen[sig] = entry.get("id", path)
        t0 = time.perf_counter()
        try:
            v = qualify(reg, entry, cfg=DEFAULT_CONFIG)
        except Exception as e:                       # an unbuildable spec is a refusal, not a crash
            bad.append((entry.get("id", path), f"spec did not build: {type(e).__name__}: {e}"))
            print(f"  REFUSED  {entry.get('id', path)}  spec did not build: {e}")
            continue
        dt = time.perf_counter() - t0
        if v["ok"]:
            ok.append((path, entry, v))
            print(f"  QUALIFIED  {entry['id']}  horizon {entry_horizon(entry)}  "
                  f"line {v['line']}  nodes {v['nodes']}  "
                  f"floor {v['floor_wins']}/{v['floor_trials']}  {dt:.1f}s")
        else:
            bad.append((entry.get("id", path), _why(v)))
            print(f"  REFUSED  {entry.get('id', path)}  {_why(v)}  ({dt:.1f}s)")
        if not quiet and v["ok"]:
            out = Path(path).with_suffix(".verified.json")
            entry["verified"] = v
            out.write_text(json.dumps(entry, indent=1) + "\n", encoding="utf-8")
            print(f"             -> {out}")
    print(f"\n{len(ok)} qualified, {len(bad)} refused, of {len(paths)}")
    return 0


#: A ``why`` that says nothing. The suite's eight originals each carry a paragraph explaining what
#: the greedy line is, what the winning line is, and why the winning line looks worth nothing until
#: its last move -- and that paragraph is most of what makes the suite readable a month later. A
#: position that qualifies but arrives undocumented is a correct row nobody can check, so merge
#: refuses it rather than letting the file fill up with verified mysteries.
_EMPTY_WHY = ("", "placeholder", "todo", "tbd", "n/a", "none")
MIN_WHY = 200


def merge(paths: list[str], apply: bool) -> int:
    """Fold verified candidates into ``data/arena/delayed.json``, refusing anything unchecked.

    Everything here is a refusal the suite would otherwise have to trust a proposer about: the
    verification block must be present and ``ok``; it must have been produced under the ruleset the
    suite is stamped with, or the stored claim is about a different game; the board must not repeat
    one already in the file; and the position must explain itself.
    """
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    seen = _existing()
    ids = {e["id"] for e in suite["positions"]}
    added, refused = [], []
    for path in paths:
        entry = json.loads(Path(path).read_text(encoding="utf-8"))
        cid = entry.get("id", path)
        v = entry.get("verified") or {}
        why = (entry.get("why") or "").strip()
        if not v.get("ok"):
            refused.append((cid, "no verification block, or it did not qualify"))
        elif v.get("rules") != suite.get("rules"):
            refused.append((cid, f"verified under ruleset {v.get('rules')!r}, suite is "
                                 f"{suite.get('rules')!r} — the claim is about a different game"))
        elif v.get("cards") != cards_digest():
            refused.append((cid, f"verified against card set {v.get('cards')!r}, this build is "
                                 f"{cards_digest()!r} — re-run `check` on the spec; a stored line "
                                 f"is action indices, and a fixed card renumbers them"))
        elif cid in ids:
            refused.append((cid, "an entry with this id is already in the suite"))
        elif _signature(entry) in seen:
            refused.append((cid, f"same board as existing {seen[_signature(entry)]!r}"))
        elif why.lower() in _EMPTY_WHY or len(why) < MIN_WHY:
            refused.append((cid, f"why is {len(why)} characters; the suite documents its positions"))
        else:
            seen[_signature(entry)] = cid
            ids.add(cid)
            added.append(entry)
    for cid, reason in refused:
        print(f"  REFUSED  {cid}  {reason}")
    for e in added:
        print(f"  MERGED   {e['id']}  horizon {entry_horizon(e)}  "
              f"floor {e['verified']['floor_wins']}/{e['verified']['floor_trials']}")
    print(f"\n{len(added)} merged, {len(refused)} refused; suite goes "
          f"{len(suite['positions'])} -> {len(suite['positions']) + len(added)}")
    if not apply:
        print("dry run — pass --apply to write the file")
        return 0
    suite["positions"].extend(added)
    SUITE.write_text(json.dumps(suite, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {SUITE.relative_to(ROOT)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/propose_positions.py",
                                 description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="run the solver over candidate spec files")
    c.add_argument("paths", nargs="+")
    c.add_argument("--quiet", action="store_true", help="do not write .verified.json beside a pass")
    sub.add_parser("template", help="print a skeleton spec")
    m = sub.add_parser("merge", help="fold verified candidates into the committed suite")
    m.add_argument("paths", nargs="+")
    m.add_argument("--apply", action="store_true", help="write the file (default: dry run)")
    a = ap.parse_args(argv)
    if a.cmd == "template":
        print(json.dumps(TEMPLATE, indent=1))
        return 0
    paths = [p for pat in a.paths for p in sorted(glob.glob(pat))] or a.paths
    if a.cmd == "merge":
        return merge(paths, a.apply)
    return check(paths, a.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
