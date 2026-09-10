"""AI deck construction.

Three layers, each usable alone:
  random_deck     — any RAM-legal deck (uniform-ish sampling)
  heuristic_deck  — a *plausible* deck: curve, type mix, sell-tag density, tag synergy
  hill_climb      — improve a deck by measured play against a field, one card swap at a time,
                    accepting swaps only when a paired SPRT says the challenger is better
  league          — N builders evolve against each other with a tournament each generation
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from cptcg.cards.registry import CardDef, Registry
from cptcg.core.enums import CardType, Color, Keyword
from cptcg.core.rng import Pcg32
from cptcg.deck.decklist import Decklist
from cptcg.deck.validate import ram_limits, validate
from cptcg.sim.runner import run_match
from cptcg.sim.stats import SPRT

UNIT, PROGRAM, GEAR, LEGEND = CardType.UNIT, CardType.PROGRAM, CardType.GEAR, CardType.LEGEND


# ------------------------------------------------------------------ pool helpers
def usable(reg: Registry) -> list[CardDef]:
    return [d for d in reg.defs if d.verified and not d.needs_script]


def legend_triples(reg: Registry) -> list[tuple[str, str, str]]:
    legs = [d for d in usable(reg) if d.type is LEGEND]
    out = []
    for a, b, c in combinations(legs, 3):
        if len({a.name, b.name, c.name}) == 3:
            out.append((a.id, b.id, c.id))
    return out


def legal_pool(reg: Registry, legends: list[str]) -> list[CardDef]:
    lim = ram_limits([reg.get(l) for l in legends])
    return [d for d in usable(reg) if d.type is not LEGEND and d.ram <= lim.get(d.color, 0)]


def random_legends(reg: Registry, rng: Pcg32) -> list[str]:
    """Three Legends with unique names, biased toward sharing colours (so the pool is deep)."""
    legs = [d for d in usable(reg) if d.type is LEGEND]
    for _ in range(200):
        pick = [rng.choice(legs)]
        cands = [d for d in legs if d.name != pick[0].name]
        if rng.below(3):                                     # 2/3: second Legend shares a colour
            same = [d for d in cands if d.color is pick[0].color]
            cands = same or cands
        pick.append(rng.choice(cands))
        cands = [d for d in legs if d.name not in {pick[0].name, pick[1].name}]
        if rng.below(2):
            same = [d for d in cands if d.color in (pick[0].color, pick[1].color)]
            cands = same or cands
        pick.append(rng.choice(cands))
        ids = [d.id for d in pick]
        if len(legal_pool(reg, ids)) >= 20:
            return ids
    raise RuntimeError("could not find a Legend triple with a usable pool")


def random_deck(reg: Registry, rng: Pcg32, legends: list[str] | None = None, size: int = 40,
                name: str = "random") -> Decklist:
    legends = legends or random_legends(reg, rng)
    pool = legal_pool(reg, legends)
    counts: Counter = Counter()
    while sum(counts.values()) < size:
        d = rng.choice(pool)
        if counts[d.id] < 3:
            counts[d.id] += 1
    deck = Decklist.from_counts(name, legends, dict(counts), generated="random")
    _assert_legal(deck, reg)
    return deck


# ------------------------------------------------------------------ heuristic build
@dataclass
class BuildPrefs:
    size: int = 40
    unit_share: float = 0.55
    program_share: float = 0.25
    gear_share: float = 0.20
    sell_min: float = 0.40                # sell-tag density floor — the economy has no other engine
    curve: tuple = (0.10, 0.22, 0.24, 0.18, 0.12, 0.08, 0.06)   # target share by cost 1..7+
    synergy_w: float = 1.0
    stat_w: float = 1.0
    noise: float = 0.35


def card_score(d: CardDef, legends: list[CardDef], prefs: BuildPrefs, rng: Pcg32) -> float:
    """Static desirability. Deliberately crude: measured play refines it."""
    cost = d.cost or 1
    s = 0.0
    if d.type is UNIT:
        s += (d.power or 0) / cost * 1.2
        if Keyword.BLOCKER in d.keywords:
            s += 0.8
        if Keyword.ADRENALINE in d.keywords:
            s += 0.5
        if d.power == 0:
            s -= 0.6
    elif d.type is GEAR:
        s += (d.power or 0) / cost * 0.8 + 0.4
    else:
        s += 0.9 + (0.4 if Keyword.QUICK in d.keywords else 0)
    if d.script is not None:                                 # has text = does something
        s += 0.6
    if d.sell_tag:
        s += 0.5
    ltags = set().union(*(l.tags for l in legends))
    s += prefs.synergy_w * 0.5 * len(d.tags & ltags)
    return prefs.stat_w * s + prefs.noise * (rng.below(1000) / 1000 - 0.5)


def heuristic_deck(reg: Registry, legends: list[str] | None, rng: Pcg32, prefs: BuildPrefs | None = None,
                   name: str = "built") -> Decklist:
    prefs = prefs or BuildPrefs()
    legends = legends or random_legends(reg, rng)
    ldefs = [reg.get(l) for l in legends]
    pool = legal_pool(reg, legends)
    scored = sorted(pool, key=lambda d: -card_score(d, ldefs, prefs, rng))
    quota = {UNIT: round(prefs.size * prefs.unit_share), PROGRAM: round(prefs.size * prefs.program_share)}
    quota[GEAR] = prefs.size - quota[UNIT] - quota[PROGRAM]
    curve_target = [round(prefs.size * c) for c in prefs.curve]
    counts: Counter = Counter()
    curve_have = [0] * 7

    def bucket(d):
        return min(6, max(0, (d.cost or 1) - 1))

    # pass 1: fill by score, respecting type quotas and curve targets
    for d in scored:
        if sum(counts.values()) >= prefs.size:
            break
        if quota[d.type] <= 0 or curve_have[bucket(d)] >= curve_target[bucket(d)] + 1:
            continue
        n = min(3, quota[d.type], prefs.size - sum(counts.values()))
        counts[d.id] += n
        quota[d.type] -= n
        curve_have[bucket(d)] += n
    # pass 2: top up ignoring the curve
    for d in scored:
        if sum(counts.values()) >= prefs.size:
            break
        room = 3 - counts[d.id]
        if room > 0 and quota[d.type] > 0:
            n = min(room, quota[d.type], prefs.size - sum(counts.values()))
            counts[d.id] += n
            quota[d.type] -= n
    for d in scored:                                         # pass 3: anything
        if sum(counts.values()) >= prefs.size:
            break
        room = 3 - counts[d.id]
        if room > 0:
            n = min(room, prefs.size - sum(counts.values()))
            counts[d.id] += n
    # pass 4: enforce sell-tag density by swapping in sellable cards for the weakest unsellable
    def sell_share():
        return sum(n for cid, n in counts.items() if reg.get(cid).sell_tag) / max(1, sum(counts.values()))
    sellable = [d for d in scored if d.sell_tag]
    unsellable = [d for d in reversed(scored) if not d.sell_tag]
    while sell_share() < prefs.sell_min:
        victim = next((d for d in unsellable if counts[d.id] > 0), None)
        gain = next((d for d in sellable if counts[d.id] < 3), None)
        if victim is None or gain is None:
            break
        counts[victim.id] -= 1
        counts[gain.id] += 1
    counts = Counter({k: v for k, v in counts.items() if v > 0})
    deck = Decklist.from_counts(name, legends, dict(counts), generated="heuristic")
    _assert_legal(deck, reg)
    return deck


def _assert_legal(deck: Decklist, reg: Registry) -> None:
    v = validate(deck, reg)
    if not v.ok:
        raise RuntimeError(f"builder produced an illegal deck: {v}")


# ------------------------------------------------------------------ mutation
def mutate(reg: Registry, deck: Decklist, rng: Pcg32, legend_swap_rate: float = 0.1,
           remove_bias: dict[str, float] | None = None) -> tuple[Decklist, str]:
    """One card swap for a legal alternative (biased to the same type and cost band); sometimes
    a Legend swap with RAM repair. The replacement takes the removed card's exact position in
    the list, so the shuffle maps identically and champion and challenger differ in one slot —
    otherwise a paired comparison measures the reshuffle, not the card."""
    main = list(deck.main)
    counts = Counter(main)
    legends = list(deck.legends)
    if rng.below(1000) < legend_swap_rate * 1000:
        legs = [d for d in usable(reg) if d.type is LEGEND]
        slot = rng.below(3)
        others = {reg.get(l).name for i, l in enumerate(legends) if i != slot}
        cands = [d for d in legs if d.name not in others and d.id != legends[slot]]
        new = rng.choice(cands)
        old = legends[slot]
        legends[slot] = new.id
        pool = legal_pool(reg, legends)
        if not pool:
            return deck, "no-op"
        pool_ids = {d.id for d in pool}
        for idx, cid in enumerate(main):                     # repair illegal cards in place
            if cid not in pool_ids:
                for _try in range(50):
                    d = rng.choice(pool)
                    if counts[d.id] < 3:
                        counts[cid] -= 1
                        counts[d.id] += 1
                        main[idx] = d.id
                        break
        return Decklist(deck.name, tuple(legends), tuple(main), dict(deck.meta)), f"legend {old} -> {new.id}"
    pool = legal_pool(reg, legends)
    idx = rng.below(len(main))
    if remove_bias:
        # Pick the removal from the worst-IWD cards most of the time: weight = rank from the bottom.
        ranked = sorted(remove_bias, key=lambda c: remove_bias[c])
        worst = ranked[: max(3, len(ranked) // 4)]
        if worst and rng.below(4):
            target = rng.choice(worst)
            idxs = [i for i, c in enumerate(main) if c == target]
            if idxs:
                idx = rng.choice(idxs)
    out_id = main[idx]
    out = reg.get(out_id)
    cands = [d for d in pool if d.id != out_id and counts[d.id] < 3]
    same = [d for d in cands if d.type is out.type and abs((d.cost or 0) - (out.cost or 0)) <= 1]
    if same and rng.below(4):
        cands = same
    if not cands:
        return deck, "no-op"
    inn = rng.choice(cands)
    main[idx] = inn.id
    return Decklist(deck.name, tuple(legends), tuple(main), dict(deck.meta)), f"{out_id} -> {inn.id}"


# ------------------------------------------------------------------ measured improvement
@dataclass
class FieldEvaluator:
    """Win/loss per (opponent, seed, seat) for a deck against a field, on shared seeds so two
    decks can be compared game by game. Results are cached per deck signature."""
    reg: Registry
    field: list[Decklist]
    agent: str = "heuristic"
    workers: int | None = None
    _cache: dict = field(default_factory=dict)
    _drawn: dict = field(default_factory=dict)

    def outcomes(self, deck: Decklist, seeds: list[int]) -> dict[tuple, bool]:
        sig = (tuple(deck.legends), tuple(sorted(deck.counts().items())))
        cache = self._cache.setdefault(sig, {})
        missing = [s for s in seeds if (0, s, 0) not in cache]
        if missing:
            for oi, opp in enumerate(self.field):
                for s0 in missing:
                    m = run_match(deck, opp, self.agent, self.agent, 2, seed=s0, workers=self.workers)
                    for r in m.results:
                        cache[(oi, r.seed, r.deck_a_seat)] = r.winner_deck == "A"
        return {k: v for k, v in cache.items() if k[1] in set(seeds)}

    def outcomes_parallel(self, deck: Decklist, seeds: list[int]) -> dict[tuple, bool]:
        """Same as outcomes() but runs all opponents' games as one batched match per opponent."""
        sig = (tuple(deck.legends), tuple(sorted(deck.counts().items())))
        cache = self._cache.setdefault(sig, {})
        drawn = self._drawn.setdefault(sig, {})
        missing = [s for s in seeds if (0, s, 0) not in cache]
        if missing:
            lo, hi = min(missing), max(missing)
            for oi, opp in enumerate(self.field):
                m = run_match(deck, opp, self.agent, self.agent, 2 * (hi - lo + 1), seed=lo, workers=self.workers)
                for r in m.results:
                    cache[(oi, r.seed, r.deck_a_seat)] = r.winner_deck == "A"
                    drawn[(oi, r.seed, r.deck_a_seat)] = r.drawn_a
        want = set(seeds)
        return {k: v for k, v in cache.items() if k[1] in want}

    def iwd(self, deck: Decklist, seeds: list[int]) -> dict[str, float]:
        """Per-card IWD (win rate when drawn minus when not) over the cached games on ``seeds``."""
        sig = (tuple(deck.legends), tuple(sorted(deck.counts().items())))
        cache, drawn = self._cache.get(sig, {}), self._drawn.get(sig, {})
        want = set(seeds)
        out = {}
        for cid in set(deck.main):
            dw = dg = ow = og = 0
            for k, won in cache.items():
                if k[1] not in want:
                    continue
                if cid in drawn.get(k, ()):
                    dg += 1
                    dw += won
                else:
                    og += 1
                    ow += won
            if dg >= 5 and og >= 5:
                out[cid] = dw / dg - ow / og
        return out


@dataclass
class Step:
    step: int
    proposal: str
    challenger_wins: int          # discordant games won by the challenger
    discordant: int
    games: int
    verdict: str
    accepted: bool
    champion_rate: float


def hill_climb(reg: Registry, deck: Decklist, field_decks: list[Decklist], steps: int = 20, seed: int = 0,
               agent: str = "heuristic", workers: int | None = None, seeds_per_batch: int = 20,
               max_batches: int = 3, sprt: SPRT | None = None, log=None, progress=None) -> tuple[Decklist, list[Step]]:
    """Improve ``deck`` by single-card swaps. Each proposal is played against the same opponents
    on the same seeds as the champion; the paired SPRT runs on the discordant games (where exactly
    one of the two won). A step accepts only on 'high'."""
    sprt = sprt or SPRT(delta=0.1)
    rng = Pcg32(seed, seq=21)
    ev = FieldEvaluator(reg, field_decks, agent, workers)
    champ = deck
    history: list[Step] = []
    for step in range(1, steps + 1):
        base_seeds = [seed * 1000 + k for k in range(seeds_per_batch * max_batches)]
        bias = ev.iwd(champ, base_seeds)
        cand, desc = mutate(reg, champ, rng, remove_bias=bias or None)
        if desc == "no-op":
            continue
        wins = disc = games = 0
        verdict = "continue"
        for b in range(max_batches):
            seeds = [seed * 1000 + b * seeds_per_batch + k for k in range(seeds_per_batch)]
            base = ev.outcomes_parallel(champ, seeds)
            new = ev.outcomes_parallel(cand, seeds)
            games += len(new)
            for key, won in new.items():
                if won != base.get(key, won):
                    disc += 1
                    wins += won
            verdict = sprt.test(wins, disc) if disc else "continue"
            if verdict != "continue":
                break
        # Accept on SPRT "high", or when the budget is spent and the challenger is clearly ahead
        # in the discordant games (one-sided z >= 1.28, ~90%). A hill-climb tolerates a few false
        # accepts; it can't afford to stall on true improvements the SPRT didn't settle in time.
        z = (wins - disc / 2) / math.sqrt(disc / 4) if disc >= 10 else 0.0
        accepted = verdict == "high" or (verdict == "continue" and z >= 1.28)
        c_all = ev.outcomes_parallel(champ, [seed * 1000 + k for k in range(seeds_per_batch)])
        champ_rate = sum(c_all.values()) / max(1, len(c_all))
        rec = Step(step, desc, wins, disc, games, verdict, accepted, champ_rate)
        history.append(rec)
        if log is not None:
            log.write(json.dumps(rec.__dict__) + "\n")
            log.flush()
        if progress:
            progress(rec)
        if accepted:
            champ = Decklist(champ.name, cand.legends, cand.main, {**cand.meta, "steps": step})
    return champ, history


# ------------------------------------------------------------------ league
def league(reg: Registry, n_builders: int = 6, generations: int = 3, steps: int = 5, seed: int = 0,
           agent: str = "heuristic", workers: int | None = None, games_per_pair: int = 60,
           out_dir: str | Path | None = None, progress=None):
    """N builders invent decks, improve them against the current population, then play a round
    robin; the worst is replaced by a fresh build each generation. Yields (generation, Tournament,
    decks) so callers can report as it runs."""
    from cptcg.sim.report import render_report
    from cptcg.sim.tournament import run_tournament
    rng = Pcg32(seed, seq=5)
    decks = [heuristic_deck(reg, None, rng, name=f"builder{i + 1}") for i in range(n_builders)]
    out = Path(out_dir) if out_dir else None
    for gen in range(1, generations + 1):
        improved = []
        for i, d in enumerate(decks):
            field_decks = [o for j, o in enumerate(decks) if j != i]
            if progress:
                progress(f"gen {gen}: improving {d.name}")
            best, _hist = hill_climb(reg, d, field_decks, steps=steps, seed=seed * 100 + gen * 10 + i,
                                     agent=agent, workers=workers)
            improved.append(best)
        decks = improved
        t = run_tournament(decks, agent, games_per_pair, seed=seed * 1000 + gen, workers=workers, sprt=SPRT(0.08))
        if out:
            (out / f"gen{gen}").mkdir(parents=True, exist_ok=True)
            t.save(out / f"gen{gen}" / "tournament.json")
            (out / f"gen{gen}" / "report.md").write_text(render_report(t, f"League generation {gen}"), encoding="utf-8")
            for d in decks:
                d.save(out / f"gen{gen}" / f"{d.name}.json")
        yield gen, t, decks
        worst = t.standings()[-1]
        decks[worst] = heuristic_deck(reg, None, rng, name=f"builder{worst + 1}")
