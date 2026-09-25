"""Context play rates and synergy realisation (design Part 5, C4): does a player use a card when it
should, and does it assemble the pairs the strategy graph says belong together?

    python tools/card_context.py CORPUS [CORPUS ...] [--games 500] [--min 20] [--out J]

Unit of account: one **seat-turn** (one player's main phase). During it a card is *offered* if any
main-phase or reaction menu of that seat held a Play, GO SOLO or Call of it, and *played* if one of
those options was taken. Counting per turn rather than per menu stops a card that sits in hand
through ten menus from counting ten refusals.

* **Context play rate**: per card, played / offered, split by the context at the first menu of the
  turn — the rival's field size (0, 1, 2+ Units), the Street Cred race (behind, level, ahead) and
  the stage (turns 1-3, 4-6, 7+). A card whose rate barely moves across contexts is being played
  on availability, not on reading the board.
* **Synergy realisation**: for each ``direct`` edge of ``data/strategy/graph.json`` (A produces what
  B rewards), among seat-turns where both were offered, the share where both were played, against
  the share expected if the two were played independently at their own rates on those same turns.
  lift = observed / expected; a player who assembles the pair on purpose shows lift above 1.

Identities are read omnisciently (this is accounting about cards, it never feeds an agent).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.actions import CallLegend, GoSolo, Play  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402

PLAYS = (Play, GoSolo, CallLegend)


def context(s, seat: int) -> dict:
    rival = 1 - seat
    n = len(s.units(rival))
    diff = s.street_cred(seat) - s.street_cred(rival)
    return {"rival_field": "0" if n == 0 else "1" if n == 1 else "2+",
            "cred": "behind" if diff < 0 else "level" if diff == 0 else "ahead",
            "stage": "t1-3" if s.turn <= 3 else "t4-6" if s.turn <= 6 else "t7+"}


def seat_turns(reg, rec) -> list[dict]:
    """Per seat-turn of one game: {seat, turn, ctx, offered: set, played: set}."""
    s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
    out: list[dict] = []
    cur: dict | None = None
    for idx in rec.actions:
        opts = legal_actions(s)
        ch = s.pending
        key = (ch.player, s.turn)
        playable = [(k, a) for k, a in enumerate(opts) if isinstance(a, PLAYS)]
        if playable and ch.player == s.active:
            if cur is None or (cur["seat"], cur["turn"]) != key:
                cur = {"seat": ch.player, "turn": s.turn, "ctx": context(s, ch.player),
                       "offered": set(), "played": set()}
                out.append(cur)
            for k, a in playable:
                cid = s.card(a.inst).id
                cur["offered"].add(cid)
                if k == idx:
                    cur["played"].add(cid)
        apply(s, idx)
    return out


def direct_edges(graph: dict) -> list[tuple[str, str, str]]:
    seen = set()
    out = []
    for e in graph["edges"]:
        if e["kind"] != "direct" or e["from"] == e["to"]:
            continue
        k = (e["from"], e["to"])
        if k not in seen:
            seen.add(k)
            out.append((e["from"], e["to"], e["token"]))
    return out


def summarise(turns: list[dict], edges, min_n: int) -> dict:
    by_card: dict = defaultdict(lambda: {"offered": 0, "played": 0,
                                         "ctx": defaultdict(lambda: [0, 0])})
    for t in turns:
        for cid in t["offered"]:
            d = by_card[cid]
            d["offered"] += 1
            p = cid in t["played"]
            d["played"] += p
            for dim, val in t["ctx"].items():
                cell = d["ctx"][f"{dim}={val}"]
                cell[0] += 1
                cell[1] += p
    cards = {}
    for cid, d in sorted(by_card.items()):
        if d["offered"] < min_n:
            continue
        rates = {k: (v[1] / v[0], v[0]) for k, v in sorted(d["ctx"].items()) if v[0] >= min_n}
        spread = {}
        for dim in ("rival_field", "cred", "stage"):
            rs = [r for k, (r, _) in rates.items() if k.startswith(dim + "=")]
            spread[dim] = max(rs) - min(rs) if len(rs) >= 2 else None
        cards[cid] = {"offered": d["offered"], "played": d["played"],
                      "rate": d["played"] / d["offered"],
                      "by_context": {k: {"rate": r, "n": n} for k, (r, n) in rates.items()},
                      "spread": spread}
    pairs = []
    for a, b, token in edges:
        both = [t for t in turns if a in t["offered"] and b in t["offered"]]
        if len(both) < min_n:
            continue
        pa = sum(a in t["played"] for t in both) / len(both)
        pb = sum(b in t["played"] for t in both) / len(both)
        obs = sum(a in t["played"] and b in t["played"] for t in both) / len(both)
        exp = pa * pb
        pairs.append({"from": a, "to": b, "token": token, "turns": len(both), "p_from": pa,
                      "p_to": pb, "both": obs, "expected": exp,
                      "lift": obs / exp if exp > 0 else None})
    pairs.sort(key=lambda p: -p["turns"])
    # pooled over pairs, weighted by turns: one number that small per-pair samples cannot swing
    w_obs = sum(p["both"] * p["turns"] for p in pairs)
    w_exp = sum(p["expected"] * p["turns"] for p in pairs)
    return {"cards": cards, "pairs": pairs, "pooled_lift": w_obs / w_exp if w_exp > 0 else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpora", nargs="+")
    ap.add_argument("--games", type=int, default=500, help="per corpus")
    ap.add_argument("--min", type=int, default=20, help="least seat-turns for a rate to be reported")
    ap.add_argument("--graph", default=str(ROOT / "data" / "strategy" / "graph.json"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    reg = load_default()
    edges = direct_edges(json.loads(Path(a.graph).read_text()))
    report = {"corpora": a.corpora, "games": a.games, "min": a.min, "by_agent": {}}
    per_agent: dict = defaultdict(list)
    for src in a.corpora:
        for gi, rec in enumerate(read_games(src)):
            if gi >= a.games:
                break
            for t in seat_turns(reg, rec):
                agent = rec.agents[t["seat"]] if rec.agents else "?"
                per_agent[agent].append(t)
    for agent, turns in sorted(per_agent.items()):
        r = summarise(turns, edges, a.min)
        r["seat_turns"] = len(turns)
        report["by_agent"][agent] = r
        lifts = [p["lift"] for p in r["pairs"] if p["lift"] is not None]
        flat = [c for c, d in r["cards"].items()
                if all(v is not None and v < 0.1 for v in d["spread"].values())]
        med = sorted(lifts)[len(lifts) // 2] if lifts else float("nan")
        print(f"{agent:16s} seat-turns {len(turns):6d}  cards rated {len(r['cards']):3d}  "
              f"context-flat (<0.10 on every axis) {len(flat):3d}  "
              f"pairs {len(r['pairs']):4d}  median lift {med:.2f}  pooled {r['pooled_lift'] or float('nan'):.2f}  "
              f"lift>1 {sum(x > 1 for x in lifts)}/{len(lifts)}")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
