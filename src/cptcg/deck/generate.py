"""Bulk deck generation: many *different* decks, each built on purpose.

Every deck comes from a builder (deck/strategies.py): an Explorer that invents a deck shape,
or a Learned builder that targets an archetype the store learned from play, both blending in
the learned card values of the knowledge store. Three things keep a big batch varied rather
than 200 copies of one favourite:

- a **novelty penalty** on Legend triples and on individual Legends already used in the batch,
  so the population spreads across the Legend space instead of piling onto one triple;
- a **distance floor**: a candidate whose main deck overlaps an accepted deck too much
  (Jaccard similarity over card copies above ``max_similarity``) is rejected and rebuilt;
- the builder's own build noise, so two decks on the same Legends still differ.

An optional **screen** then plays every deck against a panel (the sample decks, or the hall of
fame) and ranks them by win rate, so "generate 200, keep the best 20" is one command.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from cptcg.cards.registry import Registry
from cptcg.core.rng import Pcg32
from cptcg.deck.decklist import Decklist
from cptcg.deck.strategies import BuilderStrategy, Explorer, get_builder
from cptcg.deck.validate import validate


def similarity(a: Decklist, b: Decklist) -> float:
    """Jaccard similarity of the two main decks as multisets (Legends ignored)."""
    ca, cb = a.counts(), b.counts()
    inter = sum(min(ca.get(k, 0), cb.get(k, 0)) for k in ca)
    union = sum(max(ca.get(k, 0), cb.get(k, 0)) for k in set(ca) | set(cb))
    return inter / union if union else 1.0


@dataclass
class Batch:
    decks: list[Decklist] = field(default_factory=list)
    triples: dict[str, int] = field(default_factory=dict)     # sorted legend ids -> uses
    legends: dict[str, int] = field(default_factory=dict)     # legend id -> uses
    rejected_similar: int = 0

    def note(self, deck: Decklist) -> None:
        self.decks.append(deck)
        key = "|".join(sorted(deck.legends))
        self.triples[key] = self.triples.get(key, 0) + 1
        for l in deck.legends:
            self.legends[l] = self.legends.get(l, 0) + 1


def short_name(reg: Registry, legends: list[str]) -> str:
    return "-".join(reg.get(l).name.split()[0].lower().strip(":,'") for l in legends)


def builder_cycle(store, archetypes=None) -> list[BuilderStrategy]:
    """The builders a batch cycles through: the ids/names asked for (``"explorer"`` allowed),
    or every archetype of the store by win rate plus one Explorer — only Explorers while the
    store has no clusters."""
    if archetypes:
        return [get_builder(a, store) for a in archetypes]
    from cptcg.deck.strategies import Learned
    ranked = store.ranked() if store is not None else []
    return [Learned(a, store) for a in ranked] + [Explorer()]


def generate_decks(reg: Registry, count: int, archetypes=None, seed: int = 0, knowledge=None,
                   legends: list[str] | None = None, max_similarity: float = 0.7, attempts: int = 6,
                   prefix: str = "gen", novelty: float = 1.0, progress=None, store=None) -> Batch:
    """``count`` distinct, legal decks. ``archetypes``: builder specs to cycle (None = every
    archetype in ``store`` plus an Explorer; Explorers only without a store). ``legends`` pins
    every deck to one triple (then only the distance floor keeps them apart)."""
    cycle = builder_cycle(store, archetypes)
    rng = Pcg32(seed, seq=33)
    batch = Batch()
    k = 0
    while len(batch.decks) < count:
        b = cycle[k % len(cycle)]
        k += 1
        deck = None
        for attempt in range(attempts):
            legs = list(legends) if legends else b.choose_legends(reg, rng, batch if novelty else None)
            name = f"{prefix}{len(batch.decks) + 1:03d}-{b.name}-{short_name(reg, legs)}"
            cand = b.build(reg, legs, rng, knowledge=knowledge, name=name)
            if not validate(cand, reg).ok:
                continue
            if any(similarity(cand, d) > max_similarity for d in batch.decks):
                batch.rejected_similar += 1
                continue
            deck = cand
            break
        if deck is None:      # the pool under these Legends is too narrow to differ: accept anyway
            deck = cand
        deck = Decklist(deck.name, deck.legends, deck.main, dict(deck.meta, seed=seed, batch_index=len(batch.decks)))
        batch.note(deck)
        if progress:
            progress(f"{deck.name}  [{deck.meta.get('archetype', b.name)}]")
    return batch


@dataclass
class Screened:
    deck: Decklist
    wins: int
    games: int

    @property
    def rate(self) -> float:
        return self.wins / self.games if self.games else 0.0


def screen_decks(reg: Registry, decks: list[Decklist], panel: list[Decklist], games_per_opponent: int = 10,
                 agent: str = "heuristic", seed: int = 0, workers: int | None = None,
                 progress=None) -> list[Screened]:
    """Every deck plays mirrored games against every panel deck on the same seeds; ranked by
    pooled win rate. A screen, not a tournament: it is cheap enough for hundreds of decks and
    good enough to throw away the bottom half."""
    from cptcg.sim.runner import run_match
    out = []
    for i, d in enumerate(decks):
        wins = games = 0
        for j, p in enumerate(panel):
            if p.name == d.name:
                continue
            m = run_match(d, p, agent, agent, games_per_opponent, seed=seed + 1000 * j, workers=workers)
            wins += sum(1 for r in m.results if r.winner_deck == "A")
            games += len(m.results)
        out.append(Screened(d, wins, games))
        if progress:
            progress(f"screened {d.name}: {wins}/{games} ({i + 1}/{len(decks)})")
    out.sort(key=lambda s: (-s.rate, s.deck.name))
    return out


def save_batch(decks: list[Decklist], out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for d in decks:
        p = out / f"{d.name}.json"
        d.save(p)
        paths.append(p)
    return paths
