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
import time
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
                   name: str = "built", score_fn=None, generated: str = "heuristic", **meta) -> Decklist:
    """Greedy filler: rank the legal pool by a score, then fill type quotas along the curve and
    top up the sell-tag density. ``score_fn(d) -> float`` replaces the default ``card_score`` so
    a caller can bring its own opinion while reusing the filler; extra ``meta`` is recorded on
    the Decklist."""
    prefs = prefs or BuildPrefs()
    legends = legends or random_legends(reg, rng)
    ldefs = [reg.get(l) for l in legends]
    pool = legal_pool(reg, legends)
    if score_fn is None:
        score_fn = lambda d: card_score(d, ldefs, prefs, rng)  # noqa: E731
    scored = sorted(pool, key=lambda d: -score_fn(d))
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
    deck = Decklist.from_counts(name, legends, dict(counts), generated=generated, **meta)
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
           out_dir: str | Path | None = None, progress=None, archetypes=None,
           knowledge_path: str | Path | None = None, hall_of_fame_path: str | Path | None = None,
           hof_opponents: int = 2, seeds_per_batch: int = 20, max_batches: int = 3, on_event=None,
           archetypes_path: str | Path | None = None):
    """N builders invent decks, improve them against the current population, then play a round
    robin; the worst is replaced by a fresh build each generation. Yields (generation, Tournament,
    decks) so callers can report as it runs.

    ``progress`` receives one text line per stage; ``on_event(kind, **fields)`` receives the
    structured version for progress tracking: ``climb_start`` (gen, generations, builder, index,
    field, steps), ``climb_step`` (gen, builder, step, steps, games, discordant, challenger_wins,
    verdict, accepted, proposal, champion_rate), ``climb_done`` (gen, builder, steps_done,
    accepted), ``tourney_cell`` (gen, a, b, wins, n, verdict, cap) after every batch of a
    round-robin cell, and ``gen_done`` (gen, generations, standings, replaced).

    With ``out_dir`` every generation writes ``genK/tournament.json`` (with the hill-climb history
    of each deck in ``info["climb"]`` and the builders rebuilt this generation in
    ``info["fresh"]``), ``genK/report.md``, one deck file per builder, and a cumulative
    ``league.json`` series (standings per generation, each row with its strength and the win
    rate that strength predicts against that generation's field) for charts. Fresh decks are
    built with the current line-up as a novelty context and rebuilt when their list is more
    than 70% the same as a deck already in the league.

    Builders come from deck/strategies.py and every deck records what built it in
    ``deck.meta["archetype"]``: the name of a learned archetype, or ``"exploring"`` for an
    Explorer. ``archetypes=None`` is automatic: the archetypes of the store at
    ``archetypes_path`` (``out/archetypes.json``; an in-memory store when None) by win rate,
    one Explorer in every four builders, and all Explorers while the store has no clusters yet.
    A list of archetype ids/names (``"explorer"`` allowed) is cycled instead; ``"legacy"``
    restores the original unopinionated ``heuristic_deck``. After every generation the store
    records the decks that played and re-clusters, and the replaced builder is rebuilt with the
    archetype that wins least often among the survivors (or as an Explorer when the Explorer
    quota is short), so the league keeps testing ideas instead of converging on one.
    With ``knowledge_path`` every generation's tournament feeds the Knowledge store, which the
    builders read when they construct. With ``hall_of_fame_path`` past champions join the field
    the builders climb against (``hof_opponents`` of them) and each generation's best are
    offered to the hall."""
    from cptcg.deck.archetypes import ArchetypeStore
    from cptcg.deck.generate import Batch, similarity
    from cptcg.deck.strategies import Explorer, Learned, builders_for, explorer_quota, get_builder
    from cptcg.sim.report import label_nearest, render_report
    from cptcg.sim.tournament import run_tournament
    rng = Pcg32(seed, seq=5)
    out = Path(out_dir) if out_dir else None
    max_similarity = 0.7      # a fresh deck this close to one already in the league is rebuilt

    knowledge = hof = None
    if knowledge_path is not None:
        from cptcg.deck.knowledge import Knowledge
        knowledge = Knowledge.load(knowledge_path, reg)
    if hall_of_fame_path is not None:
        from cptcg.deck.hall_of_fame import HallOfFame, deck_signature
        hof = HallOfFame.load(hall_of_fame_path)
    store = ArchetypeStore.load(archetypes_path, reg) if archetypes_path is not None else ArchetypeStore(reg=reg)

    legacy = archetypes == "legacy"
    cycle = None if legacy or archetypes is None else [get_builder(a, store) for a in archetypes]
    line_up = builders_for(store, n_builders) if cycle is None and not legacy else None

    def replacement(survivors: list[Decklist]):
        """The builder for the slot a league frees: keep the Explorer quota, else re-test the
        surviving archetype that wins least often. A survivor whose archetype id has since
        been renamed is resolved through the store; one that no longer matches anything is
        labelled by its nearest current group; when nothing resolves, an Explorer."""
        if not store.archetypes:
            return Explorer()
        explorers = sum(1 for d in survivors if d.meta.get("archetype_id") is None)
        if explorers < explorer_quota(n_builders):
            return Explorer()
        carried = []
        for d in survivors:
            if not d.meta.get("archetype_id"):
                continue
            a = store.get(d.meta["archetype_id"])
            if a is None:
                nearest = store.label(d)
                a = store.get(nearest) if nearest else None
            if a is not None:
                carried.append(a)
        if carried:
            return Learned(min(carried, key=lambda a: (a.smoothed_rate, a.games, a.id)), store)
        if not any(d.meta.get("archetype_id") for d in survivors):
            return Learned(store.ranked()[0], store)     # cold start: nobody targets a group yet, try the best one
        return Explorer()

    def fresh(i: int, survivors: list[Decklist] | None = None, others: list[Decklist] = ()) -> Decklist:
        """A new deck for slot ``i``; ``others`` are the decks already in the league, which the
        new one must not copy (novelty penalty on Legends, similarity floor on the list)."""
        name = f"builder{i + 1}"
        if legacy:
            return heuristic_deck(reg, None, rng, name=name)
        if cycle is not None:
            b = cycle[i % len(cycle)]
        elif survivors is None:
            b = line_up[i]
        else:
            b = replacement(survivors)
        used = Batch()
        for d in others:
            used.note(d)
        deck = None
        for _attempt in range(6):
            deck = b.build(reg, None, rng, knowledge=knowledge, name=name, used=used)
            if not any(similarity(deck, d) > max_similarity for d in others):
                break
        return deck

    decks: list[Decklist] = []
    for i in range(n_builders):
        decks.append(fresh(i, others=decks))
    fresh_idx = set(range(n_builders))                       # builders rebuilt for this generation
    series: list[dict] = []
    for gen in range(1, generations + 1):
        gen_t0 = time.perf_counter()
        extra = []
        if hof is not None:
            extra = hof.opponents(hof_opponents, exclude={deck_signature(d) for d in decks})
        improved = []
        climb: list[list[dict]] = []
        for i, d in enumerate(decks):
            field_decks = [o for j, o in enumerate(decks) if j != i] + extra
            if progress:
                progress(f"gen {gen}: improving {d.name}" + (f" [{d.meta['archetype']}]" if "archetype" in d.meta else ""))
            step_cb = None
            if on_event:
                on_event("climb_start", gen=gen, generations=generations, builder=d.name, index=i,
                         field=len(field_decks), steps=steps)

                def step_cb(rec, name=d.name, gen=gen):
                    on_event("climb_step", gen=gen, builder=name, step=rec.step, steps=steps, games=rec.games,
                             discordant=rec.discordant, challenger_wins=rec.challenger_wins, verdict=rec.verdict,
                             accepted=rec.accepted, proposal=parse_proposal(rec.proposal),
                             champion_rate=rec.champion_rate)
            best, hist = hill_climb(reg, d, field_decks, steps=steps, seed=seed * 100 + gen * 10 + i,
                                    agent=agent, workers=workers, seeds_per_batch=seeds_per_batch,
                                    max_batches=max_batches, progress=step_cb)
            if on_event:
                on_event("climb_done", gen=gen, builder=d.name, steps_done=len(hist),
                         accepted=sum(1 for h in hist if h.accepted))
            improved.append(best)
            climb.append([step_json(h) for h in hist])
        decks = improved
        cell_cb = None
        if on_event:
            def cell_cb(a, b, k, n, verdict, gen=gen):
                on_event("tourney_cell", gen=gen, a=a, b=b, wins=k, n=n, verdict=verdict, cap=games_per_pair)
        t = run_tournament(decks, agent, games_per_pair, seed=seed * 1000 + gen, workers=workers, sprt=SPRT(0.08),
                           progress=cell_cb)
        worst = t.standings()[-1]
        if on_event:
            on_event("gen_done", gen=gen, generations=generations, standings=[decks[i].name for i in t.standings()],
                     replaced=decks[worst].name if gen < generations else None)
        t.info.update(title=f"League generation {gen}", generation=gen, generations=generations, steps=steps,
                      league_seed=seed, replaced=decks[worst].name if gen < generations else None, climb=climb,
                      fresh=[decks[i].name for i in sorted(fresh_idx)],
                      # the round robin's own elapsed_s is a fraction of this: the card-swap tests
                      # played most of the generation's games
                      gen_elapsed_s=round(time.perf_counter() - gen_t0, 3))
        bt = t.bt()
        expected = t.expected_rates()
        series.append({"gen": gen, "standings": [
            {"name": d.name, "archetype": d.meta.get("archetype") or d.meta.get("strategy"), "bt": bt[i],
             "expected": expected[i], "wins": k, "games": g, "fresh": i in fresh_idx,
             "replaced": i == worst and gen < generations}
            for i, (d, (k, g)) in enumerate(zip(decks, t.field_rates()))]})
        if knowledge is not None:
            knowledge.update_from_tournament(t)
            if knowledge.path:
                knowledge.save()
        if hof is not None:
            hof.update_from_tournament(t, generation=gen, source=f"league seed {seed}")
            if hof.path:
                hof.save()
        if not legacy:
            store.update_from_tournament(t, source=f"league seed {seed}", generation=gen)
            store.refit()
            if store.path:
                store.save()
            label_nearest(t, store)          # Explorer decks (and stale labels) get their nearest current group
        if out:
            (out / f"gen{gen}").mkdir(parents=True, exist_ok=True)
            t.paths = []
            for d in decks:
                path = out / f"gen{gen}" / f"{d.name}.json"
                d.save(path)
                t.paths.append(_display_path(path))
            t.save(out / f"gen{gen}" / "tournament.json", reg)
            (out / f"gen{gen}" / "report.md").write_text(render_report(t, f"League generation {gen}", reg), encoding="utf-8")
            with open(out / "league.json", "w", encoding="utf-8") as f:
                json.dump({"generations": series}, f, indent=1)
        yield gen, t, list(decks)
        if gen < generations:
            survivors = [d for i, d in enumerate(decks) if i != worst]
            decks[worst] = fresh(worst, survivors, others=survivors)
            fresh_idx = {worst}


def parse_proposal(desc: str) -> dict:
    """``mutate()``'s swap text as ``{"out", "in", "kind"}`` (kind: ``card`` or ``legend``)."""
    kind = "card"
    if desc.startswith("legend "):
        kind, desc = "legend", desc[len("legend "):]
    a, _, b = desc.partition(" -> ")
    return {"out": a.strip(), "in": b.strip(), "kind": kind}


def step_json(h: Step) -> dict:
    """One hill-climb step as the report stores it."""
    return {"step": h.step, "proposal": parse_proposal(h.proposal), "games": h.games, "discordant": h.discordant,
            "challenger_wins": h.challenger_wins, "verdict": h.verdict, "accepted": h.accepted,
            "champion_rate": h.champion_rate}


def _display_path(path: Path) -> str:
    """A deck path as the web client and the report show it: relative to the working directory
    when it lies under it (``out/league/gen2/builder1.json``), else absolute."""
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)
