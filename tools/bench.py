"""Speed and identity benchmark for the engine + heuristic agent.

    python tools/bench.py record      # write tests/golden/games.json from fixed seeds (do this once)
    python tools/bench.py check       # replay the same seeds; exit 1 if ANY game differs
    python tools/bench.py time [-n N] # ms/game, heuristic vs heuristic and random vs random
    python tools/bench.py fuzz [-n N] [--seed S] [--agent heuristic|random]
                                      # play N games between RANDOM RAM-legal decks (whole card pool,
                                      # invariants on) and print one digest line; run it on two
                                      # branches and compare — the digests must be equal

"Identical" means: same winner, end reason, turn count, action indices and cards drawn for every
seeded game. Any optimisation of the engine or the heuristic must keep `check` green.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.deck.decklist import Decklist  # noqa: E402
from cptcg.sim.runner import run_match  # noqa: E402

GOLDEN = ROOT / "tests" / "golden" / "games.json"
MATCHUPS = [("the_heist", "embracing_power"), ("sample_gangers", "sample_netrunners"), ("sample_arasaka", "sample_fixers"),
            ("sample_corpos", "sample_nomads")]
HEURISTIC_GAMES = 16
RANDOM_GAMES = 40


def _deck(name: str) -> Decklist:
    return Decklist.load(ROOT / "data" / "decks" / f"{name}.json")


def play_all() -> dict:
    out = {}
    for a, b in MATCHUPS:
        for agent, n in (("heuristic", HEURISTIC_GAMES), ("random", RANDOM_GAMES)):
            m = run_match(_deck(a), _deck(b), agent, agent, n, seed=11, workers=1, record=True)
            out[f"{a}~{b}~{agent}"] = [
                {"seed": r.seed, "seat": r.deck_a_seat, "winner": r.winner_deck, "end": r.end_reason, "turns": r.turns,
                 "actions": list(r.replay.actions), "drawn_a": sorted(r.drawn_a), "drawn_b": sorted(r.drawn_b)}
                for r in m.results]
    return out


def cmd_record(_a) -> None:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    data = play_all()
    GOLDEN.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"recorded {sum(len(v) for v in data.values())} games to {GOLDEN.relative_to(ROOT)}")


def cmd_check(_a) -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    now = play_all()
    bad = 0
    for key, games in golden.items():
        got = now.get(key)
        if got != games:
            bad += 1
            for i, (x, y) in enumerate(zip(games, got or [])):
                if x != y:
                    print(f"DIFFERENT: {key} game {i} (seed {x['seed']}, seat {x['seat']}): "
                          f"first divergence at action {next((k for k, (p, q) in enumerate(zip(x['actions'], y['actions'])) if p != q), 'end')}")
                    break
    print("IDENTICAL" if not bad else f"DIFFERENT in {bad} matchup(s)")
    sys.exit(1 if bad else 0)


def cmd_time(a) -> None:
    for agent in ("heuristic", "random"):
        n = a.n if agent == "heuristic" else a.n * 4
        t = time.perf_counter()
        games = 0
        for x, y in MATCHUPS[:2]:
            games += run_match(_deck(x), _deck(y), agent, agent, n, seed=21, workers=1).n
        dt = time.perf_counter() - t
        print(f"{agent:9s} {games:4d} games  {dt:6.2f}s  {dt / games * 1000:6.1f} ms/game  {games / dt:5.2f} games/s")


def cmd_fuzz(a) -> None:
    """Broad differential test: random decks from the whole pool, so card scripts the golden
    matchups never draw are exercised too. Prints a digest of every game's outcome and action
    list; identical engine behaviour ⇔ identical digest."""
    import hashlib
    from cptcg.agents.base import make_agent
    from cptcg.cards.registry import load_default
    from cptcg.core import invariants
    from cptcg.core.engine import apply, legal_actions, new_game
    from cptcg.core.rng import Pcg32
    from cptcg.deck.builder import heuristic_deck, random_deck

    reg = load_default()
    h = hashlib.sha256()
    t = time.perf_counter()
    actions = 0
    seen: set = set()
    for k in range(a.n):
        seed = a.seed * 100_003 + k
        rng = Pcg32(seed, seq=3)
        decks = (heuristic_deck(reg, None, rng, name="a") if k % 2 else random_deck(reg, rng, name="a"),
                 heuristic_deck(reg, None, rng, name="b") if k % 3 else random_deck(reg, rng, name="b"))
        for d in decks:
            seen.update(d.main)
            seen.update(d.legends)
        agents = [make_agent(a.agent, seed * 2 + i) for i in range(2)]
        s = new_game(reg, decks, seed, record=True)
        for p, ag in enumerate(agents):
            ag.new_game(seed, p)
        n = 0
        while not s.over:
            legal_actions(s)
            apply(s, agents[s.pending.player].act(s, s.pending))
            if a.invariants:
                invariants.check(s)
            n += 1
            if n > 20_000:
                raise RuntimeError(f"fuzz game {k} (seed {seed}) runaway")
        actions += n
        h.update(f"{k}:{s.winner}:{s.end_reason}:{s.turn}:{s.actions}:{sorted(s.drawn)}\n".encode())
    dt = time.perf_counter() - t
    print(f"fuzz {a.agent} n={a.n} seed={a.seed} cards={len(seen)}/{len(reg)} actions={actions} "
          f"time={dt:.1f}s digest={h.hexdigest()[:24]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("record").set_defaults(fn=cmd_record)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    p = sub.add_parser("time"); p.add_argument("-n", type=int, default=16); p.set_defaults(fn=cmd_time)
    p = sub.add_parser("fuzz")
    p.add_argument("-n", type=int, default=60)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--agent", default="heuristic", choices=("heuristic", "random"))
    p.add_argument("--no-invariants", dest="invariants", action="store_false")
    p.set_defaults(fn=cmd_fuzz)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
