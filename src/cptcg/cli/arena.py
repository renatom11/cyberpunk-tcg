"""``cptcg arena`` — the gate, as a command line.

The measuring instruments live in :mod:`cptcg.learn.arena` and :mod:`cptcg.learn.delayed`; this
module is only their front end, shared by ``cptcg arena`` and the standalone ``tools/arena.py`` so
that the two can never drift apart.

Every command writes a machine-readable JSON result and, unless ``--no-docs`` is given, appends a
human-readable section to ``docs/learning.md``. The plan says every generation is reported there
whether or not the numbers flatter the run, so appending is the default and suppressing it is the
flag.
"""

from __future__ import annotations

import argparse
import functools
import sys
from pathlib import Path

from cptcg.cards.registry import load_default
from cptcg.core.config import DEFAULT_CONFIG
from cptcg.learn import arena, delayed
from cptcg.sim.stats import SPRT

GAMES_PER_SEED = arena.GAMES_PER_SEED


def _per_pairing(games: int, pairings: int) -> int:
    """Games per deck pairing, rounded up to a whole number of seeds (four games each)."""
    per = max(1, -(-games // max(1, pairings)))
    return -(-per // GAMES_PER_SEED) * GAMES_PER_SEED


def _emit(args, name: str, data: dict, section: str) -> None:
    path = Path(args.out) / f"{name}.json"
    arena.write_json(path, data)
    print(f"\nwritten to {path}", file=sys.stderr)
    if args.docs:
        arena.append_section(args.docs, section)
        print(f"appended a section to {args.docs}", file=sys.stderr)
    print(section)


def _h2h_progress(label: str = ""):
    def progress(res, row):
        print(f"  {label}{row.deck_a} vs {row.deck_b}: {row.a_wins}/{row.games} — running "
              f"{100 * res.rate:.1f}% of {res.games}, paired {res.pair_wins}/{res.discordant} "
              f"[{res.verdict}]", file=sys.stderr)
    return progress


def _guard(fn):
    """Turn the deliberate refusals — an unknown agent, a tampered panel, an agent with nothing to
    cheat with, a suite from another ruleset — into a message and an exit code, not a traceback."""
    @functools.wraps(fn)
    def wrapper(args):
        try:
            return fn(args)
        except (KeyError, ValueError) as e:
            sys.exit(str(e).strip('"'))
    return wrapper


# ------------------------------------------------------------------ commands
@_guard
def cmd_a_vs_b(args) -> None:
    reg = load_default()
    pairings = arena.sampled_pairings(reg, args.decks, deck_seed=args.deck_seed)
    res = arena.head_to_head(
        reg, args.agent_a, args.agent_b, pairings,
        games_per_pairing=_per_pairing(args.games, args.decks), seed=args.seed,
        workers=args.jobs, sprt=None if args.no_sprt else SPRT(delta=args.delta),
        min_games=args.min_games, deck_seed=args.deck_seed, swap_decks=not args.no_swap,
        progress=_h2h_progress())
    note = (f"`arena a-vs-b {args.agent_a} {args.agent_b}"
            + (" --no-swap" if args.no_swap else "")
            + (" --no-sprt" if args.no_sprt else "")
            + f"` over {args.decks} deck pairings sampled from deck seed {args.deck_seed}"
            + ("" if args.no_sprt else f", SPRT at delta {args.delta}") + ".")
    _emit(args, f"a-vs-b_{args.agent_a}_vs_{args.agent_b}".replace(":", "-"), res.to_json(),
          arena.render_head_to_head(res, note=note))


@_guard
def cmd_panel(args) -> None:
    reg = load_default()
    panel = arena.load_panel(args.panel)

    def progress(member, res):
        if res is None:
            print(f"  {member}: not available in this build", file=sys.stderr)
        else:
            print(f"  {member}: {100 * res.rate:.1f}% of {res.games}", file=sys.stderr)

    out = arena.run_panel(reg, args.agent, panel, workers=args.jobs, progress=progress)
    _emit(args, f"panel_{args.agent}".replace(":", "-"), out, arena.render_panel(out))


@_guard
def cmd_exploit(args) -> None:
    reg = load_default()
    out = arena.run_exploit(reg, args.agent, deck_pairs=args.decks,
                            games_per_pairing=_per_pairing(args.games, args.decks),
                            seed=args.seed, deck_seed=args.deck_seed, workers=args.jobs,
                            reference=args.vs,
                            progress=lambda what, res: print(
                                f"  {what}: {100 * res.rate:.1f}% of {res.games}", file=sys.stderr))
    _emit(args, f"exploit_{args.agent}".replace(":", "-"), out, arena.render_exploit(out))


@_guard
def cmd_generalisation(args) -> None:
    reg = load_default()
    out = arena.run_generalisation(
        reg, args.agent, baseline=args.baseline, deck_pairs=args.decks,
        games_per_pairing=_per_pairing(args.games, args.decks), seed=args.seed,
        workers=args.jobs,
        progress=lambda name, res: print(f"  {name}: {100 * res.rate:.1f}% of {res.games}",
                                         file=sys.stderr))
    _emit(args, f"generalisation_{args.agent}".replace(":", "-"), out,
          arena.render_generalisation(out))


@_guard
def cmd_delayed(args) -> None:
    reg = load_default()
    # Verifying and mining are how a suite gets repaired, so they may read one from another
    # ruleset; scoring an agent against a stale suite may not.
    suite = delayed.load_suite(
        args.suite,
        rules=None if (args.verify or args.mine or args.requalify) else DEFAULT_CONFIG.digest())
    if args.mine:
        found = delayed.mine(reg, games=args.mine, seed=args.seed, max_nodes=args.max_nodes,
                             limit=args.limit,
                             progress=lambda e, info: print(
                                 f"  {'FOUND ' + e['id'] if e else info}", file=sys.stderr))
        have = {p["id"] for p in suite["positions"]}
        added = [e for e in found if e["id"] not in have]
        suite["positions"] += added
        suite["rules"] = DEFAULT_CONFIG.digest()
        delayed.save_suite(suite, args.suite)
        print(f"mined {len(found)} qualifying positions, {len(added)} new; suite now has "
              f"{len(suite['positions'])} (written to {args.suite})", file=sys.stderr)
        return
    if args.requalify:
        suite, dropped = delayed.requalify_suite(
            reg, suite, progress=lambda e, v: print(
                f"  {e['id']}: line {v['line']} in {v['nodes']} nodes "
                f"(exhausted={v['exhausted']}), heuristic wins {v['heuristic_wins']} -> "
                f"{'ok' if v['ok'] else 'NO LONGER QUALIFIES'}"))
        delayed.save_suite(suite, args.suite)
        print(f"re-derived {len(suite['positions'])} positions into {args.suite}"
              + (f"; {len(dropped)} no longer qualify: {dropped}" if dropped else ""))
        sys.exit(1 if dropped else 0)
    if args.verify:
        rows = delayed.verify_suite(reg, suite)
        bad = [r for r in rows if not r["ok"]]
        for r in rows:
            print(f"  {r['id']}: line wins {r['stored_line_wins']}, heuristic wins "
                  f"{r['heuristic_wins']} -> {'ok' if r['ok'] else 'FAILED'}")
        print(f"{len(rows) - len(bad)} of {len(rows)} positions still verify")
        sys.exit(1 if bad else 0)
    out = delayed.score_agent(reg, suite, args.agent,
                              progress=lambda r: print(f"  {r['id']}: {r['wins']}/{r['trials']}",
                                                       file=sys.stderr))
    _emit(args, f"delayed_{args.agent}".replace(":", "-"), out, delayed.render_score(out))


# -------------------------------------------------------------------- parsing
def add_arguments(ap: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Attach the arena subcommands to ``ap``. Shared by the package CLI and ``tools/arena.py``."""
    sub = ap.add_subparsers(dest="arena_cmd", required=True)

    def common(p, *, games=360, decks=6, seed=4242, deck_seed=20260910):
        p.add_argument("-n", "--games", type=int, default=games,
                       help=f"total games, split over the deck pairings (default {games})")
        p.add_argument("--decks", type=int, default=decks,
                       help=f"how many deck pairings to sample (default {decks})")
        p.add_argument("--deck-seed", type=int, default=deck_seed,
                       help="seed of the deck sampler: the same seed always gives the same decks")
        p.add_argument("--seed", type=int, default=seed, help="game seed base")
        p.add_argument("-j", "--jobs", type=int, default=None, help="worker processes")
        p.add_argument("--out", default=str(arena.OUT_DIR), help="directory for the JSON result")
        p.add_argument("--docs", default=str(arena.DOCS_PATH),
                       help="Markdown file to append the report section to")
        p.add_argument("--no-docs", dest="docs", action="store_const", const=None,
                       help="do not append to the Markdown report")
        return p

    p = sub.add_parser("a-vs-b", help="two agents head to head: paired seeds, mirrored seats, SPRT")
    p.add_argument("agent_a")
    p.add_argument("agent_b")
    common(p)
    p.add_argument("--delta", type=float, default=0.05, help="SPRT effect size")
    p.add_argument("--no-sprt", action="store_true", help="play every game; no early stopping")
    p.add_argument("--min-games", type=int, default=0, help="games before the SPRT may stop the run")
    p.add_argument("--no-swap", action="store_true",
                   help="do not swap the deck assignments: agent A holds deck A in every game. "
                        "The older, unbalanced measurement; here only so the difference can be "
                        "re-derived")
    p.set_defaults(fn=cmd_a_vs_b)

    p = sub.add_parser("panel", help="the frozen benchmark panel: comparable across every generation")
    p.add_argument("agent")
    p.add_argument("--panel", default=str(arena.PANEL_PATH), help="the frozen panel definition")
    p.add_argument("-j", "--jobs", type=int, default=None)
    p.add_argument("--out", default=str(arena.OUT_DIR))
    p.add_argument("--docs", default=str(arena.DOCS_PATH))
    p.add_argument("--no-docs", dest="docs", action="store_const", const=None)
    p.set_defaults(fn=cmd_panel)

    p = sub.add_parser("exploit", help="the cheating upper bound: the cost of hidden information")
    p.add_argument("agent")
    common(p, games=240, seed=909, deck_seed=77)
    p.add_argument("--vs", default=None, help="also measure both variants against this agent")
    p.set_defaults(fn=cmd_exploit)

    p = sub.add_parser("generalisation",
                       help="win rate on training decks vs the held-out starters vs fresh decks")
    p.add_argument("agent")
    p.add_argument("--baseline", default="heuristic", help="the fixed opponent for every population")
    common(p, games=360, seed=5150)
    p.set_defaults(fn=cmd_generalisation)

    p = sub.add_parser("delayed", help="the delayed-reward suite: solved N of M")
    p.add_argument("agent", nargs="?", default="heuristic")
    p.add_argument("--suite", default=str(delayed.SUITE_PATH))
    p.add_argument("--verify", action="store_true",
                   help="re-derive every stored claim instead of scoring an agent")
    p.add_argument("--requalify", action="store_true",
                   help="rewrite every stored verification block with this build's numbers")
    p.add_argument("--mine", type=int, default=0, metavar="GAMES",
                   help="scan this many self-play games for new positions and add them")
    p.add_argument("--limit", type=int, default=None, help="stop mining after this many positions")
    p.add_argument("--max-nodes", type=int, default=4_000, help="solver node cap while mining")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=str(arena.OUT_DIR))
    p.add_argument("--docs", default=str(arena.DOCS_PATH))
    p.add_argument("--no-docs", dest="docs", action="store_const", const=None)
    p.set_defaults(fn=cmd_delayed)
    return ap


def run(args) -> None:
    args.fn(args)
