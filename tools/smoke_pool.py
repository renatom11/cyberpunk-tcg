"""Random-bot fuzz on the REAL card pool with invariant checks: shakes out script crashes."""
import collections
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core import invariants  # noqa: E402
from cptcg.core.actions import EndTurn  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.deck.decklist import Decklist  # noqa: E402

reg = load_default()
DECKS = [Decklist.load(p) for p in sorted((ROOT / "data/decks").glob("*.json"))]


def play(seed, decks, check=True, record=False):
    s = new_game(reg, decks, seed, record=record)
    r = Pcg32(seed ^ 0x5EED)
    n = 0
    while not s.over:
        opts = legal_actions(s)
        if len(opts) > 1 and isinstance(opts[0], EndTurn) and r.below(10) < 9:
            idx = 1 + r.below(len(opts) - 1)
        else:
            idx = r.below(len(opts))
        apply(s, idx)
        if check:
            invariants.check(s)
        n += 1
        if n > 20000:
            raise RuntimeError("runaway game")
    return s, n


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    t = time.perf_counter()
    reasons, winners, turns, fails = collections.Counter(), collections.Counter(), [], collections.Counter()
    first_tb = {}
    for seed in range(n):
        decks = (DECKS[seed % len(DECKS)], DECKS[(seed // len(DECKS)) % len(DECKS)])
        try:
            s, k = play(seed, decks)
            reasons[s.end_reason.name] += 1
            winners[s.winner] += 1
            turns.append(s.turn)
        except Exception as e:  # noqa: BLE001
            key = f"{type(e).__name__}: {str(e)[:70]}"
            fails[key] += 1
            first_tb.setdefault(key, (seed, traceback.format_exc()))
    dt = time.perf_counter() - t
    print(f"{n} games in {dt:.1f}s ({dt / n * 1000:.1f} ms/game); end reasons {dict(reasons)}; winners {dict(winners)}")
    if turns:
        print(f"avg turns {sum(turns) / len(turns):.1f}  max {max(turns)}")
    for key, cnt in fails.most_common():
        seed, tb = first_tb[key]
        print(f"\n[{cnt}x] {key}  (first seed {seed})\n" + "\n".join(tb.strip().splitlines()[-6:]))
