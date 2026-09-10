"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from cptcg.cards.registry import load_default
from cptcg.cli.render import describe, render
from cptcg.deck.decklist import Decklist
from cptcg.deck.validate import validate
from cptcg.sim.record import Replay
from cptcg.sim.runner import run_match
from cptcg.sim.stats import fmt_rate, games_for_half_width, wilson


def _load_deck(reg, path: str, allow_unverified: bool, allow_unscripted: bool) -> Decklist:
    deck = Decklist.load(path)
    v = validate(deck, reg, allow_unverified=allow_unverified, allow_unscripted=allow_unscripted)
    if not v.ok:
        sys.exit(f"{path}: illegal deck\n{v}")
    for w in v.warnings:
        print(f"warning: {path}: {w}", file=sys.stderr)
    return deck


def cmd_sim(args) -> None:
    reg = load_default()
    a = _load_deck(reg, args.deck_a, args.allow_unverified, args.allow_unscripted)
    b = _load_deck(reg, args.deck_b, args.allow_unverified, args.allow_unscripted)
    t = time.perf_counter()
    last = [0]

    def progress(n):
        if n - last[0] >= 200:
            last[0] = n
            print(f"  {n} games...", file=sys.stderr)

    m = run_match(a, b, args.agent_a, args.agent_b, args.games, seed=args.seed, workers=args.jobs,
                  record=bool(args.replays), progress=progress)
    dt = time.perf_counter() - t
    k, n = m.a_wins, m.n
    lo, hi = wilson(k, n)
    af_k, af_n, bf_k, bf_n = m.split()
    print(f"\n{a.name} ({args.agent_a})  vs  {b.name} ({args.agent_b})   —  {n} games, seed {args.seed}, {dt:.1f}s")
    print(f"  {a.name:<24} {fmt_rate(k, n)}")
    print(f"  {b.name:<24} {fmt_rate(n - k, n)}")
    print(f"  95% half-width ±{100 * (hi - lo) / 2:.1f}%  (±3% needs {games_for_half_width(0.03)} games, "
          f"±1% needs {games_for_half_width(0.01)})")
    print(f"  {a.name} on the play: {fmt_rate(af_k, af_n)}    on the draw: {fmt_rate(bf_k, bf_n)}")
    first_wins = sum(1 for r in m.results if r.winner_deck == r.first_deck)
    print(f"  first player wins: {fmt_rate(first_wins, n)}")
    print(f"  avg turns {m.avg_turns():.1f};  end reasons: " + ", ".join(f"{r} {c}" for r, c in sorted(m.reasons().items())))
    if lo > 0.5:
        print(f"  => {a.name} is favoured (interval excludes 50%)")
    elif hi < 0.5:
        print(f"  => {b.name} is favoured (interval excludes 50%)")
    else:
        print("  => no significant difference at this sample size")
    if args.replays:
        out = Path(args.replays)
        out.mkdir(parents=True, exist_ok=True)
        for r in m.results:
            r.replay.save(out / f"g{r.seed:06d}_{r.deck_a_seat}.json")
        print(f"  replays written to {out}/")


def cmd_validate(args) -> None:
    reg = load_default()
    for path in args.decks:
        v = validate(Decklist.load(path), reg, allow_unverified=True, allow_unscripted=True)
        print(f"{path}: {'OK' if v.ok else 'ILLEGAL'}\n{v}")


def cmd_replay(args) -> None:
    reg = load_default()
    rep = Replay.load(args.file)
    for s, idx in rep.steps(reg):
        if args.step or idx is None:
            print(render(s, perspective=args.perspective))
        if idx is not None:
            print(">> " + describe(s, s.pending, idx))
        if args.step and idx is not None:
            input()
    if not args.step:
        print(render(rep.final_state(reg)))


def cmd_cards(args) -> None:
    reg = load_default()
    if args.unimplemented:
        for d in reg.unimplemented():
            print(d.id)
        return
    for d in reg.defs:
        flag = "" if d.verified else "  [UNVERIFIED]"
        print(f"{d.id:<44} {d.type.name.title():<8} {d.color.name.title():<7} RAM {d.ram}  cost {d.cost}  pwr {d.power}{flag}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="cptcg", description="Cyberpunk TCG simulator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sim", help="play N games between two decks and report win rates")
    p.add_argument("--deck-a", required=True)
    p.add_argument("--deck-b", required=True)
    p.add_argument("-n", "--games", type=int, default=200)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--agent-a", default="heuristic")
    p.add_argument("--agent-b", default="heuristic")
    p.add_argument("-j", "--jobs", type=int, default=None)
    p.add_argument("--replays", help="directory to write one replay per game")
    p.add_argument("--allow-unverified", action="store_true")
    p.add_argument("--allow-unscripted", action="store_true")
    p.set_defaults(fn=cmd_sim)

    p = sub.add_parser("validate", help="check deck legality")
    p.add_argument("decks", nargs="+")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("replay", help="watch a replay")
    p.add_argument("file")
    p.add_argument("--step", action="store_true", help="pause after each action")
    p.add_argument("--perspective", type=int, default=None, help="hide the other player's hidden info")
    p.set_defaults(fn=cmd_replay)

    p = sub.add_parser("cards", help="list the card pool")
    p.add_argument("--unimplemented", action="store_true")
    p.set_defaults(fn=cmd_cards)

    args = ap.parse_args(argv)
    args.fn(args)
