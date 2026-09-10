"""Read a stored game out loud, and measure what storage costs.

    python tools/dump.py FILE [--game N]     # one game, decision by decision, options in words
    python tools/dump.py FILE --stats        # bytes per decision and per game, raw and gzipped
    python tools/dump.py FILE --list         # one line per game in the file
    python tools/dump.py --sample OUT -n 20  # play N heuristic games and store them, to have
                                             # something real to read and to measure

The rendering lives in ``cptcg.learn.dump`` so that ``cptcg dump`` is the same command; this file
is the standalone entry point and the sample generator, neither of which belongs in the package.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.learn.decks import sample_pair  # noqa: E402
from cptcg.learn.dump import load_game, render_game  # noqa: E402
from cptcg.learn.experience import (GameRecord, format_size_stats,  # noqa: E402
                                    read_games, size_stats, write_games)
from cptcg.sim.record import Replay  # noqa: E402
from cptcg.sim.runner import play_game  # noqa: E402


def cmd_sample(a) -> None:
    """Play heuristic self-play games over freshly sampled deck pairs and store them.

    No search agent exists yet, so these records carry no visit counts — which is the point: the
    format has to work end to end today, with the search output simply absent.
    """
    reg = load_default()
    rng = Pcg32(a.seed, seq=77)
    t = time.perf_counter()
    records = []
    for i in range(a.n):
        decks = sample_pair(reg, rng)
        s = play_game(reg, decks, ("heuristic", "heuristic"), seed=a.seed + i, record=True)
        rep = Replay.from_game(s, decks, ("heuristic", "heuristic"))
        records.append(GameRecord.from_replay(rep, meta={"source": "bootstrap"}))
    n = write_games(a.sample, records, append=False)
    dt = time.perf_counter() - t
    print(f"wrote {n} games to {a.sample} in {dt:.1f}s")
    print(format_size_stats(size_stats(a.sample)))


def cmd_list(a) -> None:
    rules = None if a.any_rules else DEFAULT_CONFIG.digest()
    for i, r in enumerate(read_games(a.file, rules=rules)):
        search = (f"{len(r.visits)} searched decisions" if r.visits is not None
                  else "no search output")
        print(f"[{i:>5}] seed {r.seed:<10} {r.decks[0]['name']:<20} vs {r.decks[1]['name']:<20} "
              f"P{r.winner} wins by {r.end_reason} in {r.turns} turns, "
              f"{r.n_decisions} decisions, {search}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="tools/dump.py", description=__doc__.splitlines()[0])
    ap.add_argument("file", nargs="?", help="an experience .jsonl or .jsonl.gz")
    ap.add_argument("--game", type=int, default=0,
                    help="which record to render (default: the first)")
    ap.add_argument("--stats", action="store_true", help="print the size budget for the file")
    ap.add_argument("--list", action="store_true", help="one summary line per game")
    ap.add_argument("--any-rules", action="store_true",
                    help="read records from another ruleset too")
    ap.add_argument("--sample", help="write N heuristic games here instead of reading")
    ap.add_argument("-n", type=int, default=20, help="games for --sample")
    ap.add_argument("--seed", type=int, default=1, help="seed for --sample")
    a = ap.parse_args(argv)

    if a.sample:
        cmd_sample(a)
        return
    if not a.file:
        ap.error("give a file to read, or --sample OUT to make one")
    if a.stats:
        print(format_size_stats(size_stats(a.file)))
        return
    if a.list:
        cmd_list(a)
        return
    rules = None if a.any_rules else DEFAULT_CONFIG.digest()
    try:
        print(render_game(load_game(a.file, a.game, rules=rules), load_default()))
    except ValueError as e:      # a ruleset mismatch, on read or on replay
        sys.exit(str(e))


if __name__ == "__main__":
    main()
