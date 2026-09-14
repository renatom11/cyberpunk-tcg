"""Give every card in the set a measured record, including the Legends.

    python tools/playtest.py --target 400 --games 40 --out out/playtest

The user's original ask for this project was "a simulator for play-testing all of the cards", and
until now it has not been that. ``out/knowledge.json`` covers **76 of 151 cards and zero Legends**
out of 1,440 games, and the only statistic in it is a win rate conditioned on *drawing* a card.
Three separate holes, and this closes all three:

* **Zero Legends.** ``record_game`` walked ``deck.main``, which excludes Legends by construction.
  Now that the engine logs what was played, a Legend has a record the moment it is Called or sent
  GO SOLO — which is also the only sense in which a Legend can be said to have done anything.
* **48 of 124 non-Legend cards with no rows at all.** Sampled decks simply never contained them.
  Sampling harder does not fix that; it is a coverage problem, so this drives deck construction
  *from* the coverage table: each round builds decks around the cards with the fewest games, so the
  sweep converges on the tail instead of re-measuring the same popular staples.
* **Draw-conditioned only.** Every deck now also reports how often a drawn card was actually
  played, and how those games went. A card with a strong win-rate-when-drawn and a low play rate is
  not winning games; it is riding along in decks that win.

Deck legality is real legality: three Legends, 40 cards, at most three copies, and a card's RAM
within its colour's cumulative Legend RAM. The RAM rule is what makes coverage hard and is why the
Legends are chosen *after* the needy cards rather than before — a needy 4-RAM Red card is only
reachable from a deck with two Red Legends, and picking Legends first leaves most of the tail
unreachable forever.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.enums import CardType, Color  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.deck.decklist import Decklist  # noqa: E402
from cptcg.deck.knowledge import Knowledge  # noqa: E402
from cptcg.deck.validate import validate  # noqa: E402
from cptcg.sim.runner import run_match  # noqa: E402

DECK_SIZE = 40
MAX_COPIES = 3
LEGEND_SLOTS = 3


def _playable(reg):
    """Cards a legal deck may contain, and the Legends it may be built on."""
    main = [d for d in reg.defs if d.type is not CardType.LEGEND and d.verified and not d.needs_script]
    legends = [d for d in reg.defs if d.type is CardType.LEGEND and d.verified and not d.needs_script]
    return main, legends


def _coverage(kn: Knowledge, ids) -> dict[str, int]:
    return {c: (kn.cards[c].played_games if c in kn.cards else 0) for c in ids}


def _pick_legends(legends, want, rng: Pcg32, cover) -> list:
    """Three Legends chosen to make ``want`` legal, then to cover the neediest Legends.

    ``want`` is the slice of neediest main-deck cards this deck is being built for. A colour needs
    ``ceil(ram / 2)`` Legend slots to admit a card of that RAM, so the demand is summed per colour
    and the scarcest slots are allocated first; whatever is left over goes to the Legends with the
    fewest games of their own, which is how a Legend ever gets measured at all.
    """
    need = Counter()
    for d in want:
        if d.ram:
            need[d.color] = max(need[d.color], -(-d.ram // 2))
    chosen, used = [], Counter()
    for colour, slots in sorted(need.items(), key=lambda kv: -kv[1]):
        for _ in range(slots):
            if len(chosen) >= LEGEND_SLOTS:
                break
            pool = [l for l in legends if l.color is colour and l not in chosen]
            if not pool:
                break
            pool.sort(key=lambda l: (cover.get(l.id, 0), rng.below(1000)))
            chosen.append(pool[0])
            used[colour] += 1
    while len(chosen) < LEGEND_SLOTS:
        pool = [l for l in legends if l not in chosen and
                l.name not in {c.name for c in chosen}]
        pool.sort(key=lambda l: (cover.get(l.id, 0), rng.below(1000)))
        if not pool:
            break
        chosen.append(pool[0])
    return chosen


def build_deck(reg, kn: Knowledge, rng: Pcg32, name: str, slice_size: int = 6,
               avoid: frozenset = frozenset()) -> Decklist | None:
    """One legal deck aimed at the least-measured cards in the set.

    ``avoid`` holds the cards the round's *other* deck already took, so the two decks in a match
    chase different parts of the tail instead of both converging on the single neediest slice. They
    are only deprioritised, never forbidden: with a narrow RAM window there may be nothing else
    legal, and a deck that cannot be filled measures nothing at all.
    """
    main_pool, legend_pool = _playable(reg)
    cover = _coverage(kn, [d.id for d in reg.defs])
    ranked = sorted(main_pool, key=lambda d: (d.id in avoid, cover.get(d.id, 0), rng.below(1000)))
    want = ranked[:slice_size]
    legends = _pick_legends(legend_pool, want, rng, cover)
    if len(legends) != LEGEND_SLOTS:
        return None
    limits = Counter()
    for l in legends:
        limits[l.color] += l.ram

    def legal(d):
        return d.ram <= limits.get(d.color, 0)

    # The needy slice goes in at three copies, so those cards are reliably drawn and reliably get
    # a measurement out of this round. The rest of the deck is filled two copies at a time, which
    # buys breadth: a 40-card deck of fourteen three-ofs measures fourteen cards in a shape no
    # human would build, and every number it produces is partly about that shape.
    counts: dict[str, int] = {}
    total = 0
    for d, copies in [(x, MAX_COPIES) for x in want if legal(x)] + \
                     [(x, 2) for x in ranked if legal(x)]:
        if total >= DECK_SIZE:
            break
        if counts.get(d.id):
            continue
        take = min(copies, DECK_SIZE - total)
        counts[d.id] = take
        total += take
    if total < DECK_SIZE:
        return None
    deck = Decklist.from_counts(name, [l.id for l in legends], counts,
                                context="playtest", archetype="coverage")
    return deck if validate(deck, reg).ok else None


def run(a) -> int:
    reg = load_default()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    store = out / "knowledge.json"
    kn = Knowledge.load(store if store.exists() else None, reg=reg)
    kn.path = store
    main_pool, legend_pool = _playable(reg)
    everything = [d.id for d in main_pool + legend_pool]

    rng = Pcg32(a.seed)
    t0 = time.perf_counter()
    rounds, best_done, stalled = 0, -1, 0
    while rounds < a.max_rounds:
        cover = _coverage(kn, everything)
        worst = min(cover.values())
        done = sum(1 for v in cover.values() if v >= a.target)
        if worst >= a.target:
            break
        # Some cards cannot be driven to target by building more decks, because the agent has them
        # in hand and declines to play them. More rounds only re-measure everything else, so the
        # sweep stops and says so rather than spinning; the shortfall list below tells them apart.
        if done > best_done:
            best_done, stalled = done, 0
        else:
            stalled += 1
            if stalled >= a.patience:
                print(f"coverage stopped improving after {rounds} rounds at {done}/{len(everything)}")
                break
        decks, taken = [], frozenset()
        for k in range(2):
            d = build_deck(reg, kn, rng, f"cov{rounds}_{k}", a.slice, avoid=taken)
            if d is None:
                break
            decks.append(d)
            taken = frozenset(set(d.main) | set(d.legends))
        if len(decks) != 2:
            rng = Pcg32(rng.below(1 << 30) ^ 0x9E3779B1)
            rounds += 1
            continue
        m = run_match(decks[0], decks[1], a.agent, a.agent, a.games,
                      seed=a.seed + rounds * 7919, workers=a.workers)
        kn.update_from_results(decks[0], m.results, "A")
        kn.update_from_results(decks[1], m.results, "B")
        rounds += 1
        if rounds % a.report_every == 0:
            kn.save()
            print(f"round {rounds:>4}  games {kn.games:>7,}  covered>={a.target}: {done}/{len(everything)}"
                  f"  worst {worst}  {time.perf_counter() - t0:6.1f}s", flush=True)

    kn.save()
    cover = _coverage(kn, everything)
    missing = sorted(c for c, v in cover.items() if v < a.target)
    print(f"\n{kn.games:,} games over {rounds} rounds in {time.perf_counter() - t0:.1f}s")
    print(f"cards with >= {a.target} games played: {len(everything) - len(missing)}/{len(everything)}")
    if missing:
        # Two very different reasons to be short, and the difference is the whole point of having
        # a play counter at all. "never in a deck" is a coverage failure this loop can fix by
        # building more decks. "drawn N times, played 3" is not: the agent had the card in hand and
        # chose something else, every time. That is a statement about the card, or about the agent.
        print(f"\nstill short ({len(missing)}) — drawn vs played says which kind of short:")
        for c in missing:
            e = kn.cards.get(c)
            dg = e.drawn_games if e else 0
            pg = e.played_games if e else 0
            why = "never in a deck" if dg == 0 and pg == 0 else \
                  ("never drawn (Legend: only Called or GO SOLO counts)" if dg == 0 else
                   f"drawn {dg}, played {pg} — the agent declines it")
            print(f"  {c:44s} {why}")
    _report(reg, kn, out / "playtest.json", a.target)
    if a.publish:
        _publish(reg, kn, a)
    return 0


PUBLISHED = ROOT / "data" / "strategy" / "measured.json"

NOTE = (
    "Measured by tools/playtest.py: legal decks built from the coverage table so that every card in "
    "the set gets games, then heuristic self-play. Read these as facts about how the frozen "
    "one-ply agent plays the card, not as a power ranking. 'played' counts the games where this "
    "deck's copy actually reached the table -- cast, replayed from the trash, or for a Legend "
    "Called or sent GO SOLO -- which is why a Legend has numbers here for the first time. "
    "'play rate' is of the games where it was drawn; a low one means the agent had it in hand and "
    "chose something else. 'when played' has no 'not drawn' arm to difference against, so it is a "
    "level rather than a contrast and is partly a fact about the decks the card appeared in; "
    "tools/legend_swap.py is the paired instrument for that question. IWD is the contrast and is "
    "the more trustworthy of the two, but draw order confounds it too."
)


def _publish(reg, kn: Knowledge, a) -> None:
    """A small file the card guide can render beside the hand-written notes.

    Deliberately carries its own provenance -- how many games, which agent, and both digests. A
    measurement on the site with no statement of what produced it is the kind of number that
    outlives the run that made it and gets quoted years later as if it were a rule of the game.
    """
    from cptcg.cards.registry import cards_digest
    from cptcg.core.config import DEFAULT_CONFIG
    cards = {}
    for d in reg.defs:
        e = kn.cards.get(d.id)
        if e is None or not (e.drawn_games or e.played_games):
            continue
        cards[d.id] = {"drawn": e.drawn_games, "played": e.played_games,
                       "gih": round(e.gih, 4) if e.gih is not None else None,
                       "gip": round(e.gip, 4) if e.gip is not None else None,
                       "play_rate": round(e.play_rate, 4) if e.play_rate is not None else None,
                       "iwd": round(e.iwd, 4) if e.iwd is not None else None}
    PUBLISHED.write_text(json.dumps(
        {"version": 1, "games": kn.games, "agent": a.agent, "target": a.target,
         "rules": DEFAULT_CONFIG.digest(), "cards_digest": cards_digest(),
         "note": NOTE, "cards": cards}, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {PUBLISHED.relative_to(ROOT)}: {len(cards)} cards, {kn.games:,} games")


def _report(reg, kn: Knowledge, path: Path, target: int) -> None:
    rows = []
    for d in reg.defs:
        e = kn.cards.get(d.id)
        if e is None:
            continue
        rows.append({"id": d.id, "name": d.name, "type": d.type.name, "color": d.color.name,
                     "cost": d.cost, "ram": d.ram,
                     "drawn_games": e.drawn_games, "played_games": e.played_games,
                     "gih": e.gih, "gip": e.gip, "play_rate": e.play_rate, "iwd": e.iwd})
    path.write_text(json.dumps({"target": target, "games": kn.games, "cards": rows}, indent=1),
                    encoding="utf-8")
    print(f"wrote {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/playtest.py", description=__doc__.splitlines()[0])
    ap.add_argument("--target", type=int, default=200, help="games played per card to aim for")
    ap.add_argument("--games", type=int, default=40, help="games per round (mirrored pairs)")
    ap.add_argument("--slice", type=int, default=6, help="neediest cards each deck is built around")
    ap.add_argument("--max-rounds", type=int, default=2000)
    ap.add_argument("--report-every", type=int, default=10)
    ap.add_argument("--patience", type=int, default=60,
                    help="stop after this many rounds with no new card reaching the target")
    ap.add_argument("--agent", default="heuristic")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--out", default="out/playtest")
    ap.add_argument("--publish", action="store_true",
                    help="also write data/strategy/measured.json for the card guide")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
