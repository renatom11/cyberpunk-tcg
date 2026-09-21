"""Decision-space coverage report: the offered/chosen matrix, per-kind entropy, the starved list.

    python tools/decision_coverage.py report OUT.harvest.json [...] [--min-offered 20] [--max-chosen 0]
    python tools/decision_coverage.py replay  GAMES.jsonl.gz [--max-games N]     # rebuild from replays

``report`` reads the ``coverage`` block that ``tools/harvest.py play`` writes into a harvest
sidecar (materialised at harvest time, so it survives engine changes). ``replay`` rebuilds the
same block from a corpus that still replays under the current engine, for corpora recorded before
the sidecar existed. The starved list is the design's detector: every ``(card, kind, sub-mode)``
offered at least ``--min-offered`` times and chosen at most ``--max-chosen`` times, with the
shipped value head's mean one-ply margin against the best option where the corpus replays
(``--margins``), so a mode the agent never takes can be told apart from one it rightly refuses.

This file is named ``decision_coverage`` because ``tools/coverage.py`` already means test coverage
of the card scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.learn.coverage import Coverage, decision_record, starvation  # noqa: E402


def _load(paths: list[str]) -> Coverage:
    cov = Coverage()
    for p in paths:
        man = json.loads(Path(p).read_text(encoding="utf-8"))
        block = man.get("coverage")
        if block is None:
            raise SystemExit(f"{p} has no coverage block; harvest it again or use `replay`")
        cov.merge(Coverage.from_json(block))
        cov.decisions = cov.decisions  # merged above
    return cov


def cmd_report(a) -> None:
    cov = _load(a.sidecars)
    print(f"decisions {cov.decisions}; distinct (card, kind, sub-mode) offered {len(cov.offered)}, "
          f"chosen {sum(1 for k in cov.offered if cov.chosen.get(k, 0))}")
    kinds = cov.to_json()["kinds"] if cov.kind_decisions else {}
    if kinds:
        print("\n| kind | decisions | mean options | searched | mean visit entropy |")
        print("|---|---|---|---|---|")
        for k, v in kinds.items():
            ent = "—" if v["mean_visit_entropy"] is None else f"{v['mean_visit_entropy']:.3f}"
            print(f"| {k} | {v['decisions']} | {v['mean_options']:.2f} | {v['searched']} | {ent} |")
    by_kind: dict = {}
    for key, n in cov.offered.items():
        by_kind.setdefault(key[1], [0, 0])
        by_kind[key[1]][0] += n
        by_kind[key[1]][1] += cov.chosen.get(key, 0)
    print("\n| action kind | offered | chosen | chosen share |")
    print("|---|---|---|---|")
    for k, (o, c) in sorted(by_kind.items(), key=lambda kv: -kv[1][0]):
        print(f"| {k} | {o} | {c} | {100 * c / o:.1f}% |")
    starved = starvation(cov, min_offered=a.min_offered, max_chosen=a.max_chosen)
    print(f"\nstarved: {len(starved)} triples offered >= {a.min_offered} and chosen <= {a.max_chosen}")
    print("| card | kind | sub-mode | offered | chosen |")
    print("|---|---|---|---|---|")
    for (card, kind, sub), n, c in starved[:a.top]:
        print(f"| {card or '—'} | {kind} | {sub or '—'} | {n} | {c} |")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps({"coverage": cov.to_json(),
                                           "starved": [[list(k), n, c] for k, n, c in starved],
                                           "min_offered": a.min_offered, "max_chosen": a.max_chosen},
                                          indent=1), encoding="utf-8")
        print(f"wrote {a.out}")


def cmd_replay(a) -> None:
    from cptcg.cards.registry import load_default
    from cptcg.core.engine import apply, legal_actions
    from cptcg.learn.experience import read_games
    reg = load_default()
    cov = Coverage()
    games = 0
    from cptcg.core.engine import new_game
    for rec in read_games(a.games):
        s = new_game(reg, rec.replay().decklists(), rec.seed)
        for k, idx in enumerate(rec.actions):
            legal_actions(s)
            ch = s.pending
            v = rec.visits[k] if rec.visits and k < len(rec.visits) and rec.visits[k] else None
            cov.add(decision_record(s, ch, idx, v))
            apply(s, idx)
        games += 1
        if a.max_games and games >= a.max_games:
            break
    print(f"rebuilt coverage from {games} games, {cov.decisions} decisions")
    out = a.out or (str(a.games) + ".coverage.json")
    Path(out).write_text(json.dumps({"coverage": cov.to_json(), "games": games}, indent=1), encoding="utf-8")
    print(f"wrote {out}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("sidecars", nargs="+", help="harvest sidecars (.harvest.json) or coverage JSON files")
    r.add_argument("--min-offered", type=int, default=20)
    r.add_argument("--max-chosen", type=int, default=0)
    r.add_argument("--top", type=int, default=60)
    r.add_argument("--out", default=None)
    r.set_defaults(fn=cmd_report)
    p = sub.add_parser("replay")
    p.add_argument("games", help="an experience .jsonl or .jsonl.gz that replays under this engine")
    p.add_argument("--max-games", type=int, default=0)
    p.add_argument("--out", default=None)
    p.set_defaults(fn=cmd_replay)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
