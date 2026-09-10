"""Fuzz the whole pool: random RAM-legal decks, random or heuristic bots, invariants on."""
import collections
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core import invariants  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.deck.builder import heuristic_deck, random_deck  # noqa: E402
from cptcg.agents.base import make_agent  # noqa: E402

reg = load_default()


def play(seed, agent_name, check=True):
    rng = Pcg32(seed, seq=3)
    decks = (heuristic_deck(reg, None, rng, name="a") if seed % 2 else random_deck(reg, rng, name="a"),
             heuristic_deck(reg, None, rng, name="b") if seed % 3 else random_deck(reg, rng, name="b"))
    agents = [make_agent(agent_name, seed * 2 + i) for i in range(2)]
    s = new_game(reg, decks, seed)
    for p, a in enumerate(agents):
        a.new_game(seed, p)
    n = 0
    while not s.over:
        legal_actions(s)
        apply(s, agents[s.pending.player].act(s, s.pending))
        if check:
            invariants.check(s)
        n += 1
        if n > 20000:
            raise RuntimeError("runaway")
    return s, decks


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    agent = sys.argv[2] if len(sys.argv) > 2 else "random"
    t = time.perf_counter()
    fails, first = collections.Counter(), {}
    seen = set()
    for seed in range(n):
        try:
            s, decks = play(seed, agent)
            seen |= set(decks[0].main) | set(decks[1].main) | set(decks[0].legends) | set(decks[1].legends)
        except Exception as e:  # noqa: BLE001
            key = f"{type(e).__name__}: {str(e)[:60]}"
            fails[key] += 1
            first.setdefault(key, (seed, traceback.format_exc()))
    print(f"{n} games ({agent}) in {time.perf_counter() - t:.1f}s; cards exercised {len(seen)}/{len(reg)}; failures {sum(fails.values())}")
    for key, cnt in fails.most_common():
        seed, tb = first[key]
        lines = [l for l in tb.strip().splitlines() if "cptcg" in l or "Error" in l]
        print(f"\n[{cnt}x] {key} (seed {seed})\n" + "\n".join(lines[-8:]))
