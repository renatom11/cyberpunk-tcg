"""Decklists: 3 Legends + 40–50 main-deck cards, referenced by card id."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Decklist:
    name: str
    legends: tuple[str, ...]
    main: tuple[str, ...]           # one entry per copy
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_counts(cls, name: str, legends: list[str], counts: dict[str, int], **meta) -> "Decklist":
        main = tuple(cid for cid, n in counts.items() for _ in range(n))
        return cls(name, tuple(legends), main, dict(meta))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.main:
            out[c] = out.get(c, 0) + 1
        return out

    @classmethod
    def load(cls, path: str | Path) -> "Decklist":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_counts(raw.get("name", Path(path).stem), raw["legends"], raw["main"],
                               **{k: v for k, v in raw.items() if k not in ("name", "legends", "main")})

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"name": self.name, "legends": list(self.legends), "main": self.counts(),
                       **self.meta}, f, indent=2)
            f.write("\n")
