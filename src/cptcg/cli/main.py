"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from cptcg.cards.registry import load_default
from cptcg.cli.arena import add_arguments as add_arena_arguments
from cptcg.cli.render import describe, render
from cptcg.core.config import DEFAULT_CONFIG
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


def cmd_dump(args) -> None:
    from cptcg.learn.dump import load_game, render_game
    from cptcg.learn.experience import format_size_stats, size_stats
    if args.stats:
        print(format_size_stats(size_stats(args.file)))
        return
    reg = load_default()
    rules = None if args.any_rules else DEFAULT_CONFIG.digest()
    try:
        print(render_game(load_game(args.file, args.game, rules=rules), reg))
    except ValueError as e:      # a ruleset mismatch, on read or on replay
        sys.exit(str(e))


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
    title = args.title or f"Tournament: {len(decks)} decks"
    t.info["title"] = title
    t.paths = list(args.decks)
    t.save(out / "tournament.json", reg)
    report = render_report(t, title, reg)
    (out / "report.md").write_text(report, encoding="utf-8")
    if args.archetypes:
        from cptcg.deck.archetypes import ArchetypeStore
        from cptcg.sim.report import label_nearest
        store = ArchetypeStore.load(args.archetypes, reg)
        store.update_from_tournament(t, source=title)
        store.refit()
        store.save()
        label_nearest(t, store)                      # hand-built decks get their nearest archetype
        t.save(out / "tournament.json", reg)
        report = render_report(t, title, reg)
        (out / "report.md").write_text(report, encoding="utf-8")
        print(f"archetypes: {store.summary()}", file=sys.stderr)
    print(report)
    print(f"({time.perf_counter() - t0:.0f}s; written to {out}/)")


def cmd_report(args) -> None:
    """Re-render the Markdown report of a saved tournament (any file version)."""
    from cptcg.sim.report import render_report
    from cptcg.sim.tournament import Tournament
    reg = load_default()
    t = Tournament.load(args.file)
    report = render_report(t, args.title, reg)
    if args.write:
        out = Path(args.file).with_name("report.md")
        out.write_text(report, encoding="utf-8")
        print(f"written to {out}", file=sys.stderr)
    else:
        print(report)


def cmd_build(args) -> None:
    from cptcg.core.rng import Pcg32
    from cptcg.deck.builder import heuristic_deck, hill_climb
    reg = load_default()
    rng = Pcg32(args.seed, seq=9)
    legends = args.legends.split(",") if args.legends else None
    if args.archetype == "legacy":
        deck = heuristic_deck(reg, legends, rng, name=args.name)
    else:
        from cptcg.deck.archetypes import ArchetypeStore
        from cptcg.deck.strategies import get_builder
        knowledge = None
        if args.knowledge:
            from cptcg.deck.knowledge import Knowledge
            knowledge = Knowledge.load(args.knowledge, reg)
        store = ArchetypeStore.load(args.archetypes, reg) if args.archetypes else None
        try:
            builder = get_builder(args.archetype, store)
        except KeyError as e:
            sys.exit(str(e).strip('"'))
        deck = builder.build(reg, legends, rng, knowledge=knowledge, name=args.name)
    print(f"builder: {deck.meta.get('archetype', args.archetype)}")
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
    from cptcg.sim.report import deck_kind
    reg = load_default()
    t0 = time.perf_counter()
    archetypes = "legacy" if args.archetypes == "legacy" else (args.archetypes.split(",") if args.archetypes else None)
    runs = league(reg, args.builders, args.generations, args.steps, seed=args.seed,
                  agent=args.agent, workers=args.jobs, games_per_pair=args.games,
                  out_dir=args.out, progress=lambda m: print("  " + m, file=sys.stderr),
                  archetypes=archetypes, knowledge_path=args.knowledge,
                  hall_of_fame_path=args.hof, hof_opponents=args.hof_opponents,
                  archetypes_path=args.archetype_store or None)
    while True:
        try:
            gen, t, decks = next(runs)
        except StopIteration:
            break
        except KeyError as e:                        # an archetype id the store does not know
            sys.exit(str(e).strip('"'))
        order = t.standings()
        expected = t.expected_rates()
        print(f"generation {gen} ({time.perf_counter() - t0:.0f}s): " +
              ", ".join(f"{decks[i].name} ({deck_kind(decks[i]) or 'legacy'}) {100 * expected[i]:.0f}%" for i in order)
              + " expected win rate vs this field")
    print(f"reports in {args.out}/genN/report.md")
    if args.archetype_store:
        from cptcg.deck.archetypes import ArchetypeStore
        print(f"archetypes ({args.archetype_store}): {ArchetypeStore.load(args.archetype_store, reg).summary()}")


def cmd_generate(args) -> None:
    import json as _json
    from cptcg.deck.generate import generate_decks, save_batch, screen_decks
    reg = load_default()
    knowledge = None
    if args.knowledge:
        from cptcg.deck.knowledge import Knowledge
        knowledge = Knowledge.load(args.knowledge, reg)
    from cptcg.deck.archetypes import ArchetypeStore
    archetypes = args.archetypes.split(",") if args.archetypes else None
    legends = args.legends.split(",") if args.legends else None
    store = ArchetypeStore.load(args.archetype_store, reg) if args.archetype_store else None
    t0 = time.perf_counter()
    try:
        batch = generate_decks(reg, args.count, archetypes, seed=args.seed, knowledge=knowledge, legends=legends,
                               max_similarity=args.max_similarity, prefix=args.prefix,
                               progress=lambda m: print("  " + m, file=sys.stderr), store=store)
    except KeyError as e:                            # an archetype id the store does not know
        sys.exit(str(e).strip('"'))
    decks = batch.decks
    print(f"{len(decks)} decks, {len(batch.triples)} Legend triples, {len(batch.legends)} Legends used, "
          f"{batch.rejected_similar} near-duplicates rejected ({time.perf_counter() - t0:.0f}s)")
    if args.screen:
        panel = [_load_deck(reg, p, True, True) for p in args.panel] if args.panel else \
            [Decklist.load(p) for p in sorted((Path(__file__).resolve().parents[3] / "data/decks").glob("sample_*.json"))[:4]]
        ranked = screen_decks(reg, decks, panel, args.screen, agent=args.agent, seed=args.seed, workers=args.jobs,
                              progress=lambda m: print("  " + m, file=sys.stderr))
        for r in ranked:
            print(f"  {100 * r.rate:5.1f}%  {r.deck.name}")
        decks = [r.deck for r in ranked[:args.keep]] if args.keep else [r.deck for r in ranked]
        Path(args.out).mkdir(parents=True, exist_ok=True)
        with open(Path(args.out) / "screen.json", "w", encoding="utf-8") as f:
            _json.dump([{"name": r.deck.name, "wins": r.wins, "games": r.games, "archetype": r.deck.meta.get("archetype")}
                        for r in ranked], f, indent=1)
    paths = save_batch(decks, args.out)
    print(f"saved {len(paths)} decks to {args.out}/")


def cmd_archetypes(args) -> None:
    """List the archetypes learned from play so far, with their record."""
    from cptcg.deck.archetypes import MIN_DECKS, ArchetypeStore
    from cptcg.deck.strategies import Explorer, blurb
    reg = load_default()
    store = ArchetypeStore.load(args.store, reg)
    if not store.archetypes:
        print(f"{store.summary()}. Archetypes are learned from tournaments and leagues; the store needs "
              f"{MIN_DECKS} decks that have played (run `cptcg league` or `cptcg tourney --archetypes {args.store}`).")
    for a in store.ranked():
        print(f"{a.name} [{a.id}]  won {100 * a.win_rate:.0f}% of {a.games} games, strength {a.bt:.2f}, "
              f"{len(a.members)} decks, {a.separation_word()}" + (f" (formerly {', '.join(a.aliases)})" if a.aliases else ""))
        print(f"    {a.description}")
    print(f"{'explorer':9s} {blurb(Explorer().describe())}")
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
    p.add_argument("--archetypes", default="out/archetypes.json",
                   help="archetype store to teach with this run's decks ('' to skip)")
    p.set_defaults(fn=cmd_tourney)

    p = sub.add_parser("report", help="re-render the Markdown report of a saved tournament.json")
    p.add_argument("file", help="path of a tournament.json (any version)")
    p.add_argument("--title", help="report title (default: the one saved in the file)")
    p.add_argument("--write", action="store_true", help="write report.md next to the file instead of printing")
    p.set_defaults(fn=cmd_report)

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
    p.add_argument("--archetype", default="explorer",
                   help="what to build toward: 'explorer' (invent a shape), an archetype id from the store, or 'legacy'")
    p.add_argument("--archetypes", default="out/archetypes.json", help="archetype store the ids come from")
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
    p.add_argument("--archetypes", help="comma-separated archetype ids (or 'explorer') to cycle; default: automatic "
                   "from the store, one Explorer per four builders; 'legacy' = the old unopinionated builder")
    p.add_argument("--archetype-store", default="out/archetypes.json",
                   help="archetype store to read and teach ('' for an in-memory one)")
    p.add_argument("--knowledge", help="path of the learned card-value store to read and update")
    p.add_argument("--hof", help="path of the hall of fame; champions of past leagues join the field")
    p.add_argument("--hof-opponents", type=int, default=2)
    p.set_defaults(fn=cmd_league)

    p = sub.add_parser("generate", help="build many different decks, optionally screen them and keep the best")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--archetypes", help="comma-separated archetype ids (or 'explorer') to cycle "
                   "(default: every learned archetype plus an Explorer)")
    p.add_argument("--archetype-store", default="out/archetypes.json", help="archetype store the ids come from")
    p.add_argument("--legends", help="pin every deck to these three Legend ids")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--knowledge", help="learned card values to build with")
    p.add_argument("--max-similarity", type=float, default=0.7, help="reject a deck this similar to one already built")
    p.add_argument("--prefix", default="gen")
    p.add_argument("--screen", type=int, default=0, help="games per panel opponent; 0 = no screen")
    p.add_argument("--panel", nargs="*", help="screening opponents (default: 4 sample decks)")
    p.add_argument("--keep", type=int, default=0, help="after screening keep only the best N")
    p.add_argument("--agent", default="heuristic")
    p.add_argument("-j", "--jobs", type=int, default=None)
    p.add_argument("--out", default="data/decks/generated")
    p.set_defaults(fn=cmd_generate)

    p = sub.add_parser("archetypes", help="list the archetypes learned from play, with their win rates")
    p.add_argument("--store", default="out/archetypes.json", help="archetype store to read")
    p.add_argument("--knowledge", help="also summarise a learned card-value store")
    p.set_defaults(fn=cmd_archetypes)

    p = sub.add_parser("serve", help="web client: play vs AI, watch replays, browse the lab")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("dump", help="read one stored game from an experience file, decision by decision")
    p.add_argument("file", help="a .jsonl or .jsonl.gz written by learn.experience.write_games")
    p.add_argument("--game", type=int, default=0, help="which record in the file (default: the first)")
    p.add_argument("--stats", action="store_true", help="print the size budget instead of a game")
    p.add_argument("--any-rules", action="store_true",
                   help="read even if the record was played under a different ruleset")
    p.set_defaults(fn=cmd_dump)

    p = sub.add_parser("arena", help="the gate: measure an agent against agents, panels and positions")
    add_arena_arguments(p)

    p = sub.add_parser("cards", help="list the card pool")
    p.add_argument("--unimplemented", action="store_true")
    p.set_defaults(fn=cmd_cards)

    args = ap.parse_args(argv)
    args.fn(args)
