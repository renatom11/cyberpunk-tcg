"""What did an engine change do to how the frozen agent plays? Same decks, same seeds, two builds.

    # in a worktree at the old commit
    python tools/engine_ab.py measure --out /tmp/old.json
    # in the current tree
    python tools/engine_ab.py measure --out /tmp/new.json
    python tools/engine_ab.py compare /tmp/old.json /tmp/new.json

Why this exists
---------------
The obvious way to ask "did the card fixes change anything?" is to run ``tools/playtest.py`` before
and after and difference the play rates. That comparison is **not** paired: the sweep builds decks
adaptively from its own coverage table, so two runs see different decks, and the seed differs too.
Doing exactly that suggested three of the fixed cards had gained 4 to 7 points of play rate. Run
paired, on fixed decks and fixed seeds, the same three cards move by 0.2, 0.0 and −1.2 points. The
difference between those two answers is the difference between a contrast and two levels.

So this tool fixes everything the engine does not own: the decks come from one seed with
``random_deck``, every pairing is played from both seats, and nothing adapts to what happened. Run
the identical file in two checkouts and the remaining difference is the engine's.

**What it is not.** Seeds are shared, but games are not: the moment behaviour diverges the two
trajectories separate, so a card's delta includes everything downstream of the first change. This
measures the *total* effect of a build difference on the frozen agent's behaviour over a fixed
panel, not a per-card isolation. For one card in isolation, the scenario test is the instrument.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.agents.base import make_agent          # noqa: E402
from cptcg.cards.registry import cards_digest, load_default  # noqa: E402
from cptcg.core.actions import CallLegend, GoSolo, Play      # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.rng import Pcg32                  # noqa: E402
from cptcg.deck.builder import random_deck        # noqa: E402

DECK_SEED = 20260914


def measure(a) -> int:
    reg = load_default()
    rng = Pcg32(DECK_SEED, seq=11)
    decks = [random_deck(reg, rng, name=f"d{i}") for i in range(a.decks)]
    drawn: dict = defaultdict(int)
    played: dict = defaultdict(int)
    games = 0
    for i in range(0, a.decks - 1, 2):
        for s_i in range(a.seeds):
            for pair in ((decks[i], decks[i + 1]), (decks[i + 1], decks[i])):
                seed = 900_000 + i * 1000 + s_i
                agents = [make_agent(a.agent, seed * 2 + k) for k in range(2)]
                s = new_game(reg, pair, seed, record=True)
                for p, ag in enumerate(agents):
                    ag.new_game(seed, p)
                cast, n = set(), 0
                while not s.over and n < 20_000:
                    opts = legal_actions(s)
                    idx = agents[s.pending.player].act(s, s.pending)
                    act = opts[idx] if idx < len(opts) else None
                    if isinstance(act, (Play, GoSolo, CallLegend)):
                        cast.add((s.i_owner[act.inst], s.card(act.inst).id))
                    apply(s, idx)
                    n += 1
                games += 1
                for _owner, cid in {(s.i_owner[i2], s.card(i2).id) for i2 in s.drawn}:
                    drawn[cid] += 1
                for _owner, cid in cast:
                    played[cid] += 1
    out = {"games": games, "decks": a.decks, "seeds": a.seeds, "agent": a.agent,
           "deck_seed": DECK_SEED, "cards_digest": cards_digest(),
           "drawn": dict(drawn), "played": dict(played)}
    Path(a.out).write_text(json.dumps(out), encoding="utf-8")
    print(f"{games} games, {len(drawn)} cards drawn, {len(played)} cards played -> {a.out}")
    return 0


def compare(a) -> int:
    o, n = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (a.old, a.new))
    for key in ("games", "decks", "seeds", "agent", "deck_seed"):
        if o[key] != n[key]:
            raise SystemExit(f"not a paired comparison: {key} is {o[key]!r} and {n[key]!r}")
    print(f"{o['games']} games per side, {o['decks']} decks, agent {o['agent']}")
    print(f"cards {o.get('cards_digest')} -> {n.get('cards_digest')}")
    rows = []
    for cid in set(o["played"]) | set(n["played"]):
        po, pn = o["played"].get(cid, 0), n["played"].get(cid, 0)
        rows.append((pn - po, cid, po, pn, o["drawn"].get(cid, 0), n["drawn"].get(cid, 0)))
    rows.sort()
    moved = sum(1 for r in rows if r[0])
    print(f"\n{moved} of {len(rows)} cards changed how often the agent played them; "
          f"total plays {sum(o['played'].values())} -> {sum(n['played'].values())}")
    for label, part in (("largest drops", rows[:a.top]), ("largest rises", rows[-a.top:])):
        print(f"\n{label}:")
        for d, cid, po, pn, do_, dn in part:
            print(f"  {cid:42s} played {po:4d} -> {pn:4d} ({d:+d})   drawn {do_:4d} -> {dn:4d}")
    if a.cards:
        print("\nnamed cards:")
        for cid in a.cards:
            po, pn = o["played"].get(cid, 0), n["played"].get(cid, 0)
            do_, dn = o["drawn"].get(cid, 0), n["drawn"].get(cid, 0)
            rate = (f"{po / do_:.3f} -> {pn / dn:.3f}" if do_ and dn else "no drawn denominator")
            print(f"  {cid:42s} played {po:4d} -> {pn:4d}   drawn {do_:4d} -> {dn:4d}   rate {rate}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/engine_ab.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure", help="play the fixed panel with this build")
    m.add_argument("--decks", type=int, default=40)
    m.add_argument("--seeds", type=int, default=20, help="seeds per deck pairing, each played twice")
    m.add_argument("--agent", default="heuristic")
    m.add_argument("--out", required=True)
    m.set_defaults(fn=measure)
    c = sub.add_parser("compare", help="difference two measure outputs")
    c.add_argument("old")
    c.add_argument("new")
    c.add_argument("--top", type=int, default=8)
    c.add_argument("--cards", nargs="*", default=[], help="also report these by name")
    c.set_defaults(fn=compare)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
