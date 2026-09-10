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
from cptcg.sim.stats import SPRT, fmt_rate, games_for_half_width, wilson


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


def cmd_tourney(args) -> None:
    from cptcg.sim.report import render_report
    from cptcg.sim.tournament import run_tournament
    reg = load_default()
    decks = [_load_deck(reg, p, args.allow_unverified, args.allow_unscripted) for p in args.decks]
    if len(decks) < 2:
        sys.exit("need at least two decks")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    def progress(a, b, k, n, verdict):
        print(f"  {a} vs {b}: {k}/{n} {'' if verdict == 'continue' else '[' + verdict + ']'}", file=sys.stderr)

    t = run_tournament(decks, args.agent, args.games, seed=args.seed, workers=args.jobs,
                       sprt=None if args.no_sprt else SPRT(args.delta), batch=args.batch, progress=progress)
    t.save(out / "tournament.json")
    report = render_report(t, args.title or f"Tournament: {len(decks)} decks")
    (out / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"({time.perf_counter() - t0:.0f}s; written to {out}/)")


def cmd_build(args) -> None:
    from cptcg.core.rng import Pcg32
    from cptcg.deck.builder import heuristic_deck, hill_climb
    reg = load_default()
    rng = Pcg32(args.seed, seq=9)
    legends = args.legends.split(",") if args.legends else None
    if args.strategy == "legacy":
        deck = heuristic_deck(reg, legends, rng, name=args.name)
    else:
        from cptcg.deck.strategies import get_strategy
        knowledge = None
        if args.knowledge:
            from cptcg.deck.knowledge import Knowledge
            knowledge = Knowledge.load(args.knowledge, reg)
        deck = get_strategy(args.strategy).build(reg, legends, rng, knowledge=knowledge, name=args.name)
    print(f"start: {deck.name}  legends {list(deck.legends)}")
    for cid, n in sorted(deck.counts().items()):
        print(f"  {n}x {cid}")
    field = [_load_deck(reg, p, True, True) for p in args.field] if args.field else         [Decklist.load(p) for p in sorted((Path(__file__).resolve().parents[3] / "data/decks").glob("sample_*.json"))[:4]]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    log = open(out.with_suffix(".build.jsonl"), "w", encoding="utf-8")

    def progress(rec):
        mark = "ACCEPT" if rec.accepted else "reject"
        print(f"  step {rec.step}: {rec.proposal}: {rec.challenger_wins}/{rec.discordant} discordant "
              f"({rec.games} games) -> {mark}   champion vs field {100 * rec.champion_rate:.0f}%", file=sys.stderr)

    best, hist = hill_climb(reg, deck, field, steps=args.steps, seed=args.seed, agent=args.agent,
                            workers=args.jobs, seeds_per_batch=args.seeds, max_batches=args.batches,
                            sprt=SPRT(args.delta), log=log, progress=progress)
    best.save(out)
    acc = sum(1 for h in hist if h.accepted)
    print(f"\n{acc} of {len(hist)} proposals accepted. Saved {out}")
    for cid, n in sorted(best.counts().items()):
        print(f"  {n}x {cid}")


def cmd_league(args) -> None:
    from cptcg.deck.builder import league
    reg = load_default()
    t0 = time.perf_counter()
    strategies = args.strategies.split(",") if args.strategies else None
    for gen, t, decks in league(reg, args.builders, args.generations, args.steps, seed=args.seed,
                                agent=args.agent, workers=args.jobs, games_per_pair=args.games,
                                out_dir=args.out, progress=lambda m: print("  " + m, file=sys.stderr),
                                strategies=strategies, knowledge_path=args.knowledge,
                                hall_of_fame_path=args.hof, hof_opponents=args.hof_opponents):
        order = t.standings()
        bt = t.bt()
        print(f"generation {gen} ({time.perf_counter() - t0:.0f}s): " +
              ", ".join(f"{decks[i].name} {bt[i]:.2f}" for i in order))
    print(f"reports in {args.out}/genN/report.md")


def cmd_strategies(args) -> None:
    from cptcg.deck.strategies import all_strategies, blurb
    for st in all_strategies():
        print(f"{st.name:9s} {blurb(st.describe())}")
    print(f"{'legacy':9s} The original unopinionated builder: curve, type mix and sell-tag floor only.")
    if args.knowledge:
        from cptcg.deck.knowledge import Knowledge
        print()
        print(Knowledge.load(args.knowledge, load_default()).summary())


def cmd_serve(args) -> None:
    from cptcg.web.server import serve
    serve(args.host, args.port)


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

    p = sub.add_parser("tourney", help="round-robin tournament with ratings and a report")
    p.add_argument("decks", nargs="+")
    p.add_argument("-n", "--games", type=int, default=200, help="cap per pair")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--agent", default="heuristic")
    p.add_argument("-j", "--jobs", type=int, default=None)
    p.add_argument("--out", default="out/tourney")
    p.add_argument("--title")
    p.add_argument("--no-sprt", action="store_true")
    p.add_argument("--delta", type=float, default=0.05, help="SPRT effect size")
    p.add_argument("--batch", type=int, default=40)
    p.add_argument("--allow-unverified", action="store_true")
    p.add_argument("--allow-unscripted", action="store_true")
    p.set_defaults(fn=cmd_tourney)

    p = sub.add_parser("build", help="AI-build a deck and improve it by measured play")
    p.add_argument("--legends", help="comma-separated Legend ids (default: random)")
    p.add_argument("--name", default="built")
    p.add_argument("--field", nargs="*", help="reference decks to optimise against (default: 4 samples)")
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--agent", default="heuristic")
    p.add_argument("-j", "--jobs", type=int, default=None)
    p.add_argument("--seeds", type=int, default=20, help="seeds per batch (x2 games x field size)")
    p.add_argument("--batches", type=int, default=3)
    p.add_argument("--delta", type=float, default=0.1)
    p.add_argument("--out", default="out/built.json")
    p.add_argument("--strategy", default="balanced",
                   help="builder personality: aggro, control, economy, gig, synergy, balanced, or legacy")
    p.add_argument("--knowledge", help="learned card values (out/knowledge.json from a league) to build with")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("league", help="N AI builders evolve decks against each other")
    p.add_argument("--builders", type=int, default=6)
    p.add_argument("--generations", type=int, default=3)
    p.add_argument("--steps", type=int, default=5)
    p.add_argument("-n", "--games", type=int, default=60, help="cap per pair in each generation's tournament")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--agent", default="heuristic")
    p.add_argument("-j", "--jobs", type=int, default=None)
    p.add_argument("--out", default="out/league")
    p.add_argument("--strategies", help="comma-separated personalities to cycle (default: all)")
    p.add_argument("--knowledge", help="path of the learned card-value store to read and update")
    p.add_argument("--hof", help="path of the hall of fame; champions of past leagues join the field")
    p.add_argument("--hof-opponents", type=int, default=2)
    p.set_defaults(fn=cmd_league)

    p = sub.add_parser("strategies", help="list the deck-builder personalities")
    p.add_argument("--knowledge", help="also summarise a learned card-value store")
    p.set_defaults(fn=cmd_strategies)

    p = sub.add_parser("serve", help="web client: play vs AI, watch replays, browse the lab")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("cards", help="list the card pool")
    p.add_argument("--unimplemented", action="store_true")
    p.set_defaults(fn=cmd_cards)

    args = ap.parse_args(argv)
    args.fn(args)
