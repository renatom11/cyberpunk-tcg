"""The hall of fame: the best decks the lab has found, kept as future opponents.

A league only ever measures its decks against each other, so a population can drift into a
local fashion — every deck tuned to beat this generation's field and nothing else. Keeping
past champions around and adding them to the field the builders climb against anchors each
league to what has actually won before, and records which archetype produced it.

Ranking is by Bradley–Terry strength, which ``sim.stats.bradley_terry`` normalises to mean 1
within a tournament; the field win rate is stored alongside as a second opinion, since BT
values from leagues of very different sizes are only roughly comparable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from cptcg.deck.decklist import Decklist

DEFAULT_PATH = Path("out") / "hall_of_fame.json"


def deck_kind(deck: Decklist) -> str:
    """What built a deck: its learned archetype, an older builder label, or ``?``."""
    return deck.meta.get("archetype") or deck.meta.get("strategy") or "?"


def deck_signature(deck: Decklist) -> str:
    """Same Legends and same card counts = same deck, whatever it was called."""
    counts = ",".join(f"{cid}x{n}" for cid, n in sorted(deck.counts().items()))
    return "|".join(sorted(deck.legends)) + "::" + counts


@dataclass
class Champion:
    deck: Decklist
    archetype: str
    bt: float
    field_rate: float = 0.5
    games: int = 0
    generation: int = 0
    source: str = ""

    @property
    def signature(self) -> str:
        return deck_signature(self.deck)

    def to_json(self) -> dict:
        return {"name": self.deck.name, "legends": list(self.deck.legends), "main": self.deck.counts(),
                "meta": dict(self.deck.meta), "archetype": self.archetype, "bt": self.bt,
                "field_rate": self.field_rate, "games": self.games, "generation": self.generation,
                "source": self.source}

    @classmethod
    def from_json(cls, raw: dict) -> "Champion":
        deck = Decklist.from_counts(raw["name"], raw["legends"], raw["main"], **raw.get("meta", {}))
        kind = raw.get("archetype") or raw.get("strategy") or deck_kind(deck)
        return cls(deck, kind, float(raw["bt"]),
                   float(raw.get("field_rate", 0.5)), int(raw.get("games", 0)),
                   int(raw.get("generation", 0)), raw.get("source", ""))


@dataclass
class HallOfFame:
    path: Path | None = None
    capacity: int = 12
    entries: list[Champion] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path | None = DEFAULT_PATH, capacity: int = 12) -> "HallOfFame":
        hof = cls(Path(path) if path else None, capacity)
        if hof.path and hof.path.exists():
            with open(hof.path, encoding="utf-8") as f:
                raw = json.load(f)
            hof.entries = [Champion.from_json(e) for e in raw.get("entries", [])]
            hof._trim()
        return hof

    def save(self, path: str | Path | None = None) -> None:
        p = Path(path) if path else self.path
        if p is None:
            raise ValueError("no path to save the hall of fame to")
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "capacity": self.capacity,
                       "entries": [e.to_json() for e in self.entries]}, f, indent=1)
            f.write("\n")

    # ---------------------------------------------------------------- membership
    def _trim(self) -> None:
        self.entries.sort(key=lambda e: (-e.bt, -e.field_rate, -e.games))
        del self.entries[self.capacity:]

    def add(self, deck: Decklist, bt: float, field_rate: float = 0.5, games: int = 0,
            generation: int = 0, source: str = "", archetype: str | None = None) -> bool:
        """Induct a deck if it ranks inside ``capacity``. A deck already present keeps its best
        record. Returns whether the deck is in the hall afterwards."""
        archetype = archetype or deck_kind(deck)
        sig = deck_signature(deck)
        for e in self.entries:
            if e.signature == sig:
                if bt > e.bt:
                    e.bt, e.field_rate, e.games, e.generation, e.source = bt, field_rate, games, generation, source
                self._trim()
                return any(x.signature == sig for x in self.entries)
        self.entries.append(Champion(deck, archetype, bt, field_rate, games, generation, source))
        self._trim()
        return any(e.signature == sig for e in self.entries)

    def update_from_tournament(self, t, generation: int = 0, source: str = "", top: int = 2) -> list[Champion]:
        """Offer the top ``top`` decks of a tournament; returns those that got in."""
        bt = t.bt()
        rates = t.field_rates()
        inducted = []
        for i in t.standings()[:top]:
            k, g = rates[i]
            if self.add(t.decks[i], bt[i], k / g if g else 0.5, g, generation, source):
                inducted.append(next(e for e in self.entries if e.signature == deck_signature(t.decks[i])))
        return inducted

    def opponents(self, n: int = 2, exclude: set[str] | None = None) -> list[Decklist]:
        """The strongest champions as field opponents, renamed ``hof1-<archetype>`` so a report
        shows where they came from. ``exclude`` skips decks already in the field by signature."""
        exclude = exclude or set()
        out = []
        for e in self.entries:
            if e.signature in exclude:
                continue
            out.append(Decklist(f"hof{len(out) + 1}-{_slug(e.archetype)}", e.deck.legends, e.deck.main,
                                {**e.deck.meta, "archetype": e.archetype, "hall_of_fame": True}))
            if len(out) >= n:
                break
        return out

    def by_archetype(self) -> dict[str, int]:
        """How many champions each archetype has produced."""
        out: dict[str, int] = {}
        for e in self.entries:
            out[e.archetype] = out.get(e.archetype, 0) + 1
        return out


def _slug(text: str) -> str:
    s = "".join(ch if ch.isalnum() else "-" for ch in text.strip().lower()).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    return s or "deck"
