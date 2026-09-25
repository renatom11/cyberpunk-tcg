"""The deck population (Stage 1 FAIL plan §2.6; design Part 4): members with identities, rated under
more than one player, with bootstrap intervals. No training loop.

    python tools/population.py init --out data/population/population.json \\
        out/s0/panel_decks/*.json data/decks/*.json
    python tools/population.py rate data/population/population.json --player heuristic \\
        --tourney out/s0/kt2/heuristic/tournament.json [--resamples 1000]
    python tools/population.py report data/population/population.json [--previous OLD.json] \\
        [--out data/population/report.json]

``init`` writes the members: id, name, Legends, main list, colour class, origin, and whether the
deck is a held-out retail starter (evaluation-only: never a training deck). ``rate`` reads a
round robin written by ``cptcg tourney`` over exactly these decks, fits Bradley–Terry strengths
(``sim.tournament.bradley_terry``, normalised to a geometric mean of 1) and a 95% interval per deck
from resampling the games inside every matchup, and stores them under the player's name, beside
the matchup cells (``matrix_<player>.json``). After two or more players it flags every deck whose
interval under one player excludes its point estimate under another as *player-dependent*.

``propose`` runs one round of proposals: for each training member (not evaluation-only), the paired
single-card swap hill climb (``deck.builder.hill_climb``, SPRT on discordant games) against a field
of other members under a named player; every improved list joins the population as a new member
with origin ``hill-climb:<parent id>`` and no rating yet, and every step (accepted or not) is
appended to ``archive.jsonl`` beside the population — the per-card swap evidence C4 reads.

``report`` computes the G6 numbers the plan asks for every generation, from the stored matrices:
per player the residual RMS against a permutation null and the Nash support (diagnostics of
cycling); for every pair of players the rank agreement (Spearman of BT strengths, 95% interval
from resampling decks); transfer (the top five under each player, their pooled win rate against
the evaluation-only starters and the six samples, under every player); diversity (distinct Legend
triples, colour classes, mean pairwise list similarity); and, given ``--previous``, rating
stability (Spearman between the two files' ratings under each player). Exploitability needs
proposals and is reported as absent until the loop makes them.
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

sys.path.insert(0, str(ROOT / "tools"))
from meta_report import nash_support, null_draws, residual_rms, wins_matrix  # noqa: E402

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


def _scale(members: list, player: str):
    """Mean and sd of log strength under ``player``: the common scale ratings are compared on."""
    logs = np.log([m["ratings"][player]["bt"] for m in members if player in m["ratings"]])
    sd = float(logs.std()) or 1.0
    return float(logs.mean()), sd


def flag_player_dependent(members: list) -> None:
    """Flag a deck whose standing differs between two players by more than both ratings' noise.

    Two corrections to the naive "one player's interval excludes the other's point":

    * **A common scale.** Each player's strengths are normalised to a geometric mean of 1 and a
      stronger player spreads the field wider, so raw strengths cannot be compared. Log strengths
      are standardised per player (mean 0, sd 1 over the decks it rated) and intervals are mapped
      the same way.
    * **Both sides' noise.** The difference of the two standardised log strengths is compared with
      1.96 times the root sum of the two standard errors (each read off its 95% interval), so a
      deck is not flagged because one rating is precise and the other is not.

    The flag names the pair; ``z`` per player is stored beside the rating.
    """
    players = sorted({p for m in members for p in m["ratings"]})
    sc = {p: _scale(members, p) for p in players}

    def z(p, v):
        mu, sd = sc[p]
        return (math.log(v) - mu) / sd

    for m in members:
        flags = []
        r = m["ratings"]
        for p in players:
            if p in r:
                r[p]["z"] = z(p, r[p]["bt"])
        for i, p in enumerate(players):
            for q in players[i + 1:]:
                if p not in r or q not in r:
                    continue
                se = [(z(x, r[x]["ci95"][1]) - z(x, r[x]["ci95"][0])) / 3.92 for x in (p, q)]
                if abs(r[p]["z"] - r[q]["z"]) > 1.96 * math.sqrt(se[0] ** 2 + se[1] ** 2):
                    flags.append(f"{p} vs {q}: z {r[p]['z']:+.2f} / {r[q]['z']:+.2f}")
        m["player_dependent"] = flags


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
    flag_player_dependent(pop["members"])
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


def _ranks(v: np.ndarray) -> np.ndarray:
    order = np.argsort(v, kind="stable")
    r = np.empty(len(v))
    r[order] = np.arange(len(v))
    for x in np.unique(v):                     # average ties
        m = v == x
        r[m] = r[m].mean()
    return r


def spearman(a, b) -> float:
    ra, rb = _ranks(np.asarray(a, float)), _ranks(np.asarray(b, float))
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def spearman_ci(a, b, resamples: int = 1000, seed: int = 20260925) -> list[float]:
    a, b = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(resamples):
        k = rng.integers(0, len(a), len(a))
        r = spearman(a[k], b[k])
        if r == r:
            draws.append(r)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return [float(lo), float(hi)]


def list_similarity(a: list[str], b: list[str]) -> float:
    """Multiset Jaccard of two main decks."""
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    inter = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return inter / union if union else 1.0


def _is_reference(m: dict) -> bool:
    return m["evaluation_only"] or m["name"].startswith("Sample ")


def cmd_report(a) -> int:
    pop = json.loads(Path(a.population).read_text())
    members = pop["members"]
    players = sorted({p for m in members for p in m["ratings"]})
    base = Path(a.population).parent
    out: dict = {"players": players, "members": len(members), "per_player": {}, "agreement": [],
                 "transfer": {}, "exploitability": None,
                 "exploitability_note": "needs proposals from the loop; none exist yet"}
    for p in players:
        safe = p.replace("/", "_").replace("@", "_").replace(":", "_")
        mat = json.loads((base / f"matrix_{safe}.json").read_text())
        w, g = wins_matrix(mat)
        rms = residual_rms(w, g)
        null = null_draws(w, g, a.draws, 1)
        x, sup = nash_support(w, g)
        out["per_player"][p] = {"residual_rms": rms, "null_mean": float(null.mean()),
                                "null_p": float((null >= rms).mean()),
                                "nash_support": [mat["decks"][i] for i in sup],
                                "nash_weights": {mat["decks"][i]: float(x[i]) for i in sup}}
    for i, p in enumerate(players):
        for q in players[i + 1:]:
            both = [m for m in members if p in m["ratings"] and q in m["ratings"]]
            va = [m["ratings"][p]["bt"] for m in both]
            vb = [m["ratings"][q]["bt"] for m in both]
            out["agreement"].append({"a": p, "b": q, "decks": len(both), "spearman": spearman(va, vb),
                                     "ci95": spearman_ci(va, vb, a.resamples)})
    refs = [m["name"] for m in members if _is_reference(m)]
    for p in players:
        cand = sorted((m for m in members if p in m["ratings"] and not _is_reference(m)),
                      key=lambda m: -m["ratings"][p]["bt"])[:5]
        top = [m["name"] for m in cand]
        row = {"top5": top, "vs_reference": {}}
        for q in players:
            safe = q.replace("/", "_").replace("@", "_").replace(":", "_")
            mat = json.loads((base / f"matrix_{safe}.json").read_text())
            names = mat["decks"]
            won = games = 0
            for c in mat["cells"]:
                ni, nj = names[c["i"]], names[c["j"]]
                if ni in top and nj in refs:
                    won += c["wins_i"]; games += c["n"]
                elif nj in top and ni in refs:
                    won += c["n"] - c["wins_i"]; games += c["n"]
            row["vs_reference"][q] = {"win_rate": won / games if games else None, "games": games}
        out["transfer"][p] = row
    triples = {tuple(sorted(m["legends"])) for m in members}
    sims = [list_similarity(members[i]["main"], members[j]["main"])
            for i in range(len(members)) for j in range(i + 1, len(members))]
    out["diversity"] = {"distinct_triples": len(triples),
                        "classes": {c: sum(m["class"] == c for m in members)
                                    for c in sorted({m["class"] for m in members})},
                        "mean_list_similarity": float(np.mean(sims)) if sims else None}
    if a.previous:
        prev = {m["name"]: m for m in json.loads(Path(a.previous).read_text())["members"]}
        stab = {}
        for p in players:
            both = [m for m in members if p in m["ratings"] and m["name"] in prev
                    and p in prev[m["name"]]["ratings"]]
            if len(both) >= 3:
                stab[p] = spearman([m["ratings"][p]["bt"] for m in both],
                                   [prev[m["name"]]["ratings"][p]["bt"] for m in both])
        out["stability"] = stab
    else:
        out["stability"] = None
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    for p, d in out["per_player"].items():
        print(f"{p:28s} residual RMS {d['residual_rms']:.3f} (null {d['null_mean']:.3f}, p {d['null_p']:.3f})"
              f"  Nash support {len(d['nash_support'])}")
    for r in out["agreement"]:
        print(f"agreement {r['a']} vs {r['b']}: {r['spearman']:.2f} [{r['ci95'][0]:.2f}, {r['ci95'][1]:.2f}]")
    for p, r in out["transfer"].items():
        print(f"transfer top5 under {p}: " + ", ".join(
            f"{q} {v['win_rate']:.3f} ({v['games']})" for q, v in r["vs_reference"].items() if v["games"]))
    d = out["diversity"]
    print(f"diversity: {d['distinct_triples']} triples, classes {d['classes']}, "
          f"mean list similarity {d['mean_list_similarity']:.3f}")
    return 0


def cmd_propose(a) -> int:
    from cptcg.core.rng import Pcg32
    from cptcg.deck.builder import hill_climb
    from cptcg.deck.decklist import Decklist
    reg = load_default()
    pop = json.loads(Path(a.population).read_text())
    members = pop["members"]
    archive = Path(a.population).parent / "archive.jsonl"
    rng = Pcg32(a.seed, seq=31)
    trainable = [m for m in members if not m["evaluation_only"]]
    if a.only:
        trainable = [m for m in trainable if m["id"] in set(a.only)]
    added = 0
    for m in trainable:
        others = [x for x in members if x["id"] != m["id"]]
        field = [others[rng.below(len(others))] for _ in range(a.field)]
        deck = Decklist.from_counts(m["name"], m["legends"], m["main"])
        fdecks = [Decklist.from_counts(x["name"], x["legends"], x["main"]) for x in field]
        champ, hist = hill_climb(reg, deck, fdecks, steps=a.steps, seed=a.seed + added,
                                 agent=a.player, workers=a.workers)
        with archive.open("a") as fh:
            for st in hist:
                fh.write(json.dumps({"parent": m["id"], "player": a.player, **st.__dict__}) + "\n")
        if champ.counts() != deck.counts() or list(champ.legends) != list(deck.legends):
            k = sum(1 for x in members if x["id"].startswith(m["id"] + "+hc"))
            nid = f"{m['id']}+hc{k + 1}"
            members.append({"id": nid, "name": f"{m['name']} +hc{k + 1}", "legends": list(champ.legends),
                            "main": champ.counts(), "class": colour_class(reg, list(champ.legends)),
                            "origin": f"hill-climb:{m['id']}", "source": a.player,
                            "evaluation_only": False, "ratings": {}})
            added += 1
        acc = sum(1 for st in hist if st.accepted)
        print(f"{m['name']:24s} {len(hist)} steps, {acc} accepted", flush=True)
    pop["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Path(a.population).write_text(json.dumps(pop, indent=1) + "\n")
    print(f"{added} new member(s); steps appended to {archive}")
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
    pr = sub.add_parser("propose")
    pr.add_argument("population")
    pr.add_argument("--player", default="heuristic")
    pr.add_argument("--steps", type=int, default=4)
    pr.add_argument("--field", type=int, default=6)
    pr.add_argument("--seed", type=int, default=20260925)
    pr.add_argument("--workers", type=int, default=4)
    pr.add_argument("--only", nargs="*", default=None, help="member ids to climb (default: all)")
    pr.set_defaults(fn=cmd_propose)
    q = sub.add_parser("report")
    q.add_argument("population")
    q.add_argument("--previous", default=None)
    q.add_argument("--draws", type=int, default=1000, help="permutation-null draws")
    q.add_argument("--resamples", type=int, default=1000)
    q.add_argument("--out", default=None)
    q.set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
