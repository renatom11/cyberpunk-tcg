"""Read a stored game out loud, and measure what storage costs.

    python tools/dump.py FILE [--game N]     # one game, decision by decision, options in words
    python tools/dump.py FILE --stats        # bytes per decision and per game, raw and gzipped
    python tools/dump.py FILE --list         # one line per game in the file
    python tools/dump.py --sample OUT -n 20  # play N heuristic games and store them, to have
                                             # something real to read and to measure
    python tools/dump.py FILE --pay-events   # kill test 4: how often a payment had a choice with
                                             # strategic content (ruling 025 gate, Stage 0)

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


def cmd_pay_events(a) -> None:
    """Kill test 4 (unified design, Part 6): of every payment the corpus made, how many were a
    *choice* with strategic content?

    A payment has a choice when more sources are ready than the cost needs. It has strategic
    content when one of the sources in play (spent or spared by the auto-payer) is a Legend that
    (a) hosts a Gear with a spend trigger, (b) has an activated ability usable this turn, or
    (c) is the last ready face-down Legend while a Call is still available this turn, or (d) is
    face-up with a Sell Tag when a face-down alternative existed — the cases where *which* source
    pays changes what happens next. Ruling 025 auto-pays; the design wires ``the payment Pick (E12)``
    only if this share is at least 2%.
    """
    from cptcg.core.actions import Activate, CallLegend, GoSolo, Play
    from cptcg.core.engine import apply, legal_actions, new_game
    from cptcg.core.enums import CardType, Zone
    from cptcg.core.legal import ability_options
    from cptcg.core.ops import ONCE_CALLED, payable_sources, play_cost
    from cptcg.core.state import ONCE_CALLED as _OC
    reg = load_default()
    n_games = payments = with_choice = strategic = 0
    cats = {"spend_gear": 0, "ability": 0, "last_facedown": 0, "faceup_vs_facedown": 0}
    legend_payments = 0
    for rec in read_games(a.file, rules=None if a.any_rules else DEFAULT_CONFIG.digest()):
        if a.n and n_games >= a.n:
            break
        n_games += 1
        s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
        for idx in rec.actions:
            legal_actions(s)
            ch = s.pending
            act = ch.options[idx]
            p = ch.player
            cost = 0
            excl = -1
            if isinstance(act, Play):
                cost = play_cost(s, p, act.inst)
            elif isinstance(act, GoSolo):
                cost = play_cost(s, p, act.inst, go_solo=act.keyword)
            elif isinstance(act, CallLegend):
                cost = 1
            elif isinstance(act, Activate):
                ab = s.card(act.inst).script.abilities[act.ability]
                from cptcg.core.ops import _ctx
                cost = ab.cost(_ctx(s, act.inst)) if callable(ab.cost) else ab.cost
                if ab.self_spend and s.card(act.inst).type is CardType.LEGEND:
                    excl = act.inst
            if cost > 0:
                payments += 1
                srcs = payable_sources(s, p, excl) if excl >= 0 else payable_sources(s, p)
                legs = [i for i in srcs if s.i_zone[i] == Zone.LEGENDS]
                taken = srcs[:cost]
                spent_legs = [i for i in taken if s.i_zone[i] == Zone.LEGENDS]
                if len(srcs) > cost and spent_legs:
                    # The design's count: a Legend with content was SPENT while another source
                    # was left unspent -- the auto-payer made a choice a player might have made
                    # differently. A Legend with content merely sitting in the list is not one.
                    with_choice += 1
                    legend_payments += 1
                    flags = set()
                    facedown_ready = [i for i in legs if not s.i_faceup[i]]
                    usable = {o.inst for o in ability_options(s, p, quick_only=False)}
                    spare = [i for i in srcs[cost:]]
                    for i in spent_legs:
                        gear = s.gear_on(i)
                        if any(getattr(s.card(g).script, "events", None) and "spent" in s.card(g).script.events for g in gear):
                            flags.add("spend_gear")
                        if i in usable:
                            flags.add("ability")
                        if (not s.i_faceup[i] and len(facedown_ready) == 1 and not (s.once[p] & _OC)
                                and any(s.i_faceup[j] for j in spare)):
                            flags.add("last_facedown")   # a face-up alternative would have kept the Call source
                    if any(s.i_faceup[i] for i in spent_legs) and any(not s.i_faceup[j] for j in spare):
                        flags.add("faceup_vs_facedown")   # cannot happen under PAY_PREF order; kept as a check
                    if flags:
                        strategic += 1
                        for f in flags:
                            cats[f] += 1
            apply(s, idx)
    print(f"games {n_games}  payments {payments}  a Legend spent with another source left unspent {with_choice}")
    print(f"strategic content: {strategic} = {100.0 * strategic / max(payments, 1):.2f}% of payments "
          f"({100.0 * strategic / max(with_choice, 1):.1f}% of the choices)")
    for k, v in cats.items():
        print(f"  {k:20s} {v}")
    print("gate: wire the payment Pick (E12) only if >= 2% of payments" +
          ("  -> WIRE" if strategic >= 0.02 * max(payments, 1) else "  -> leave auto-payment"))


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
    ap.add_argument("--pay-events", action="store_true", help="kill test 4: payment choices with content")
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
    if a.pay_events:
        cmd_pay_events(a)
        return
    rules = None if a.any_rules else DEFAULT_CONFIG.digest()
    try:
        print(render_game(load_game(a.file, a.game, rules=rules), load_default()))
    except ValueError as e:      # a ruleset mismatch, on read or on replay
        sys.exit(str(e))


if __name__ == "__main__":
    main()
