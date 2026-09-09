"""Quick random-bot smoke run. Usage: python tools/smoke_random.py [n_games]"""
import collections
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from conftest import blue_deck, red_deck  # noqa: E402
from cptcg.cards.registry import Registry  # noqa: E402
from cptcg.core.actions import EndTurn  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402

reg = Registry.from_files(ROOT / "tests/fixtures/cards_test.json")


def play_random(seed, record=False):
    s = new_game(reg, (red_deck(), blue_deck()), seed, record=record)
    r = Pcg32(seed ^ 0xABCDEF)
    steps = 0
    while not s.over:
        opts = legal_actions(s)
        if len(opts) > 1 and isinstance(opts[0], EndTurn) and r.below(10) < 9:
            idx = 1 + r.below(len(opts) - 1)
        else:
            idx = r.below(len(opts))
        apply(s, idx)
        steps += 1
        if steps > 5000:
            raise RuntimeError("runaway game")
    return s, steps


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    t = time.perf_counter()
    reasons, winners, turns, nsteps = collections.Counter(), collections.Counter(), [], []
    for seed in range(n):
        s, k = play_random(seed)
        reasons[s.end_reason.name] += 1
        winners[s.winner] += 1
        turns.append(s.turn)
        nsteps.append(k)
    dt = time.perf_counter() - t
    print(f"{n} games in {dt:.2f}s  ({dt / n * 1000:.1f} ms/game)")
    print("end reasons", dict(reasons), " winners", dict(winners))
    print(f"avg turns {sum(turns) / n:.1f}  max {max(turns)}  avg decisions {sum(nsteps) / n:.0f}")
