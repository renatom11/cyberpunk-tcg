"""Learned card values: what measured play has shown about each card.

Every game reports which cards each deck drew and who won, so per card we can keep the four
counts behind IWD (win rate when drawn minus when not drawn). A persistent store accumulates
that evidence across tournaments and leagues, bucketed by the deck's Legend colour set, so a
builder can ask "how has this card done in decks like the one I'm building?" and get a number
that is honest about how little we may know:

    value = iwd * n / (n + k)

shrinks a noisy estimate toward zero (globally) or toward the global estimate (within a colour
context) until the sample earns its opinion. IWD is correlational — draw order confounds it —
but as a *prior* fed into a static score it is the cheapest possible feedback loop: the lab
runs, the store fills, and the next generation of builders starts smarter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from cptcg.cards.registry import Registry
from cptcg.deck.decklist import Decklist
from cptcg.deck.strategies import context_key

DEFAULT_K = 30.0
DEFAULT_PATH = Path("out") / "knowledge.json"


@dataclass
class Evidence:
    """The four counts behind IWD for one card in one bucket."""
    drawn_games: int = 0
    drawn_wins: int = 0
    other_games: int = 0
    other_wins: int = 0

    def add(self, drawn: bool, won: bool) -> None:
        if drawn:
            self.drawn_games += 1
            self.drawn_wins += int(won)
        else:
            self.other_games += 1
            self.other_wins += int(won)

    def merge(self, dg: int, dw: int, og: int, ow: int) -> None:
        self.drawn_games += dg
        self.drawn_wins += dw
        self.other_games += og
        self.other_wins += ow

    @property
    def gih(self) -> float | None:
        return self.drawn_wins / self.drawn_games if self.drawn_games else None

    @property
    def iwd(self) -> float | None:
        if not self.drawn_games or not self.other_games:
            return None
        return self.drawn_wins / self.drawn_games - self.other_wins / self.other_games

    @property
    def n_eff(self) -> float:
        """Effective sample size of a difference of two proportions: the variance of IWD is
        proportional to 1/dg + 1/og, so the harmonic combination is the honest n."""
        dg, og = self.drawn_games, self.other_games
        return dg * og / (dg + og) if dg and og else 0.0

    def to_list(self) -> list[int]:
        return [self.drawn_games, self.drawn_wins, self.other_games, self.other_wins]

    @classmethod
    def from_list(cls, v: list[int]) -> "Evidence":
        return cls(*v)


@dataclass
class Knowledge:
    """Per-card evidence, globally and per Legend-colour context, plus pairwise co-draw counts."""
    path: Path | None = None
    reg: Registry | None = None
    k: float = DEFAULT_K
    track_pairs: bool = True
    cards: dict[str, Evidence] = field(default_factory=dict)
    contexts: dict[str, dict[str, Evidence]] = field(default_factory=dict)
    pairs: dict[str, list[int]] = field(default_factory=dict)    # "a|b" -> [games both drawn, wins]
    games: int = 0
    tournaments: int = 0

    # ---------------------------------------------------------------- persistence
    @classmethod
    def load(cls, path: str | Path | None = DEFAULT_PATH, reg: Registry | None = None,
             k: float = DEFAULT_K) -> "Knowledge":
        """A store at ``path``; an empty one if the file doesn't exist yet."""
        kn = cls(Path(path) if path else None, reg, k)
        if kn.path and kn.path.exists():
            with open(kn.path, encoding="utf-8") as f:
                raw = json.load(f)
            kn.cards = {cid: Evidence.from_list(v) for cid, v in raw.get("cards", {}).items()}
            kn.contexts = {ctx: {cid: Evidence.from_list(v) for cid, v in d.items()}
                           for ctx, d in raw.get("contexts", {}).items()}
            kn.pairs = {key: list(v) for key, v in raw.get("pairs", {}).items()}
            kn.games = int(raw.get("games", 0))
            kn.tournaments = int(raw.get("tournaments", 0))
        return kn

    def to_json(self) -> dict:
        return {"version": 1, "k": self.k, "games": self.games, "tournaments": self.tournaments,
                "cards": {cid: e.to_list() for cid, e in sorted(self.cards.items())},
                "contexts": {ctx: {cid: e.to_list() for cid, e in sorted(d.items())}
                             for ctx, d in sorted(self.contexts.items())},
                "pairs": {key: v for key, v in sorted(self.pairs.items())}}

    def save(self, path: str | Path | None = None) -> None:
        p = Path(path) if path else self.path
        if p is None:
            raise ValueError("no path to save the knowledge store to")
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, separators=(",", ":"))
            f.write("\n")

    # ---------------------------------------------------------------- recording
    def bucket(self, deck: Decklist) -> str | None:
        """The context a deck's games count toward: its Legend colour set. Strategy-built decks
        carry it in ``meta['context']``; otherwise it needs the registry to look colours up."""
        ctx = deck.meta.get("context")
        if ctx is None and self.reg is not None:
            ctx = context_key(self.reg, deck.legends)
        return ctx

    def record_game(self, deck: Decklist, drawn: frozenset, won: bool) -> None:
        ctx = self.bucket(deck)
        by_ctx = self.contexts.setdefault(ctx, {}) if ctx else None
        for cid in set(deck.main):
            was = cid in drawn
            self.cards.setdefault(cid, Evidence()).add(was, won)
            if by_ctx is not None:
                by_ctx.setdefault(cid, Evidence()).add(was, won)
        if self.track_pairs:
            seen = sorted(drawn)
            for i, a in enumerate(seen):
                for b in seen[i + 1:]:
                    p = self.pairs.setdefault(f"{a}|{b}", [0, 0])
                    p[0] += 1
                    p[1] += int(won)
        self.games += 1

    def update_from_results(self, deck: Decklist, results: list, side: str = "A") -> None:
        """Games from ``run_match`` where ``deck`` was side ``"A"`` or ``"B"``."""
        for r in results:
            drawn = r.drawn_a if side == "A" else r.drawn_b
            self.record_game(deck, drawn, r.winner_deck == side)

    def update_from_tournament(self, t) -> None:
        """Every game of every cell, for both decks. Falls back to the per-deck ``card_stats``
        (no contexts or pairs) when a loaded tournament carries no per-game results."""
        any_results = any(c.results for c in t.cells.values())
        if any_results:
            for c in t.cells.values():
                self.update_from_results(t.decks[c.i], c.results, "A")
                self.update_from_results(t.decks[c.j], c.results, "B")
        else:
            for deck, stats in zip(t.decks, t.card_stats):
                ctx = self.bucket(deck)
                for cid, s in stats.items():
                    self.cards.setdefault(cid, Evidence()).merge(s.drawn_games, s.drawn_wins, s.other_games, s.other_wins)
                    if ctx:
                        self.contexts.setdefault(ctx, {}).setdefault(cid, Evidence()).merge(
                            s.drawn_games, s.drawn_wins, s.other_games, s.other_wins)
        self.tournaments += 1

    # ---------------------------------------------------------------- estimates
    def value(self, card_id: str, context: str | None = None) -> float | None:
        """Shrunk IWD. Globally: ``iwd * n/(n+k)`` toward 0. In a context: the context's IWD
        shrunk toward the *global* estimate, so a card with plenty of global evidence but a
        thin record in this colour combination inherits its overall reputation."""
        g = self.cards.get(card_id)
        if g is None or g.iwd is None:
            return None
        global_est = g.iwd * g.n_eff / (g.n_eff + self.k)
        if context is None:
            return global_est
        c = self.contexts.get(context, {}).get(card_id)
        if c is None or c.iwd is None:
            return global_est
        return (c.iwd * c.n_eff + global_est * self.k) / (c.n_eff + self.k)

    def sample_size(self, card_id: str, context: str | None = None) -> float:
        e = (self.contexts.get(context, {}) if context else self.cards).get(card_id)
        return e.n_eff if e else 0.0

    def synergy(self, a: str, b: str) -> float | None:
        """How much better games go when both cards are drawn than their individual records
        predict, shrunk by the number of co-draws. Cheap and crude: no context bucket."""
        key = f"{min(a, b)}|{max(a, b)}"
        p = self.pairs.get(key)
        ea, eb = self.cards.get(a), self.cards.get(b)
        if not p or not p[0] or ea is None or eb is None or ea.gih is None or eb.gih is None:
            return None
        expected = (ea.gih + eb.gih) / 2
        return (p[1] / p[0] - expected) * p[0] / (p[0] + self.k)

    def top(self, n: int = 10, context: str | None = None, worst: bool = False) -> list[tuple[str, float, float]]:
        """(card, value, effective n) for the strongest (or weakest) cards on record."""
        rows = []
        for cid in self.cards:
            v = self.value(cid, context)
            if v is not None:
                rows.append((cid, v, self.sample_size(cid, context)))
        rows.sort(key=lambda r: r[1], reverse=not worst)
        return rows[:n]

    def summary(self) -> str:
        return (f"{len(self.cards)} cards, {len(self.contexts)} contexts, {self.games} games, "
                f"{self.tournaments} tournaments")
