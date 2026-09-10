"""Golden replays: seeded games must stay byte-identical across engine and agent changes.
Regenerate deliberately with `python tools/bench.py record` when a rule or the heuristic changes."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import bench  # noqa: E402


def test_golden_games_are_identical():
    golden = json.loads(bench.GOLDEN.read_text(encoding="utf-8"))
    now = bench.play_all()
    for key, games in golden.items():
        assert now[key] == games, f"{key} diverged"
