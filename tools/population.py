"""The deck population (Stage 1 FAIL plan §2.6; design Part 4): members with identities, rated under
more than one player, with bootstrap intervals. No training loop.

    python tools/population.py init --out data/population/population.json \\
        out/s0/panel_decks/*.json data/decks/*.json
    python tools/population.py rate data/population/population.json --player heuristic \\
        --tourney out/s0/kt2/heuristic/tournament.json [--resamples 1000]

``init`` writes the members: id, name, Legends, main list, colour class, origin, and whether the
deck is a held-out retail starter (evaluation-only: never a training deck). ``rate`` reads a
round robin written by ``cptcg tourney`` over exactly these decks, fits Bradley–Terry strengths
(``sim.tournament.bradley_terry``, normalised to a geometric mean of 1) and a 95% interval per deck
from resampling the games inside every matchup, and stores them under the player's name, beside
the matchup cells (``matrix_<player>.json``). After two or more players it flags every deck whose
interval under one player excludes its point estimate under another as *player-dependent*.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import cards_digest, load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.sim.tournament import bradley_terry  # noqa: E402

#: The two retail starters: held out of every training corpus, so their ratings stay clean.
STARTERS = ("Embracing Power", "The Heist")


def colour_class(reg, legends: list[str]) -> str:
    by = {d.id: d for d in reg.defs}
    cols = sorted(by[l].color.name for l in legends)
    counts = sorted((cols.count(c) for c in set(cols)), reverse=True)
    return {(3,): "mono", (2, 1): "two-plus-one", (1, 1, 1): "one-of-each"}[tuple(counts)]


def cmd_init(a) -> int:
    reg = load_default()
    members = []
    for p in a.decks:
        d = json.loads(Path(p).read_text())
        name = d.get("name") or Path(p).stem
        members.append({"id": Path(p).stem, "name": name, "legends": d["legends"], "main": d["main"],
                        "class": colour_class(reg, d["legends"]), "origin": "seed:kt2", "source": str(p),
                        "evaluation_only": name in STARTERS, "ratings": {}})
    out = {"format": 1, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "rules": DEFAULT_CONFIG.digest(), "cards": cards_digest(), "members": members}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(members)} members -> {a.out}")
    return 0


def _normalise(s: list[float]) -> np.ndarray:
    v = np.array(s, dtype=float)
    return v / math.exp(np.log(v).mean())


def bootstrap_bt(cells: list[tuple[int, int, int, int]], n: int, resamples: int, seed: int = 20260925):
    """``cells``: (i, j, wins of i, games). Point strengths and 95% intervals (normalised)."""
    def fit(cs):
        w = [[0.0] * n for _ in range(n)]
        for i, j, k, g in cs:
            w[i][j] += k
            w[j][i] += g - k
        return _normalise(bradley_terry(w))
    point = fit(cells)
    rng = np.random.default_rng(seed)
    draws = np.empty((resamples, n))
    for r in range(resamples):
        draws[r] = fit([(i, j, int(rng.binomial(g, k / g)) if g else 0, g) for i, j, k, g in cells])
    lo, hi = np.percentile(draws, [2.5, 97.5], axis=0)
    return point, lo, hi


def cmd_rate(a) -> int:
    pop = json.loads(Path(a.population).read_text())
    t = json.loads(Path(a.tourney).read_text())
    names = [d["name"] for d in t["decks"]]
    idx = {}
    for k, m in enumerate(pop["members"]):
        if m["name"] not in names:
            raise SystemExit(f"{m['name']} is not in {a.tourney}")
        idx[names.index(m["name"])] = k
    cells = [(c["i"], c["j"], c["wins_i"], c["n"]) for c in t["cells"]]
    point, lo, hi = bootstrap_bt(cells, len(names), a.resamples)
    games = {i: 0 for i in range(len(names))}
    wins = {i: 0 for i in range(len(names))}
    for i, j, k, g in cells:
        games[i] += g; games[j] += g; wins[i] += k; wins[j] += g - k
    for ti, mk in idx.items():
        pop["members"][mk]["ratings"][a.player] = {
            "bt": float(point[ti]), "ci95": [float(lo[ti]), float(hi[ti])], "games": games[ti],
            "win_rate": wins[ti] / games[ti] if games[ti] else None, "tourney": str(a.tourney),
            "rules": t.get("rules"), "list_mode": t.get("list_mode")}
    players = sorted({p for m in pop["members"] for p in m["ratings"]})
    for m in pop["members"]:
        flags = []
        for p in players:
            for q in players:
                if p == q or p not in m["ratings"] or q not in m["ratings"]:
                    continue
                lo_p, hi_p = m["ratings"][p]["ci95"]
                if not lo_p <= m["ratings"][q]["bt"] <= hi_p:
                    flags.append(f"{q} outside {p}")
        m["player_dependent"] = flags
    pop["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Path(a.population).write_text(json.dumps(pop, indent=1) + "\n")
    safe = a.player.replace("/", "_").replace("@", "_").replace(":", "_")
    mat = {"player": a.player, "tourney": str(a.tourney), "decks": names, "cells": t["cells"],
           "residuals": t.get("residuals"), "nash": t.get("nash")}
    (Path(a.population).parent / f"matrix_{safe}.json").write_text(json.dumps(mat) + "\n")
    order = sorted(idx, key=lambda i: -point[i])
    for i in order:
        print(f"{names[i]:20s} {point[i]:.2f} [{lo[i]:.2f}, {hi[i]:.2f}]")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("decks", nargs="+")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_init)
    r = sub.add_parser("rate")
    r.add_argument("population")
    r.add_argument("--player", required=True)
    r.add_argument("--tourney", required=True)
    r.add_argument("--resamples", type=int, default=1000)
    r.set_defaults(fn=cmd_rate)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
