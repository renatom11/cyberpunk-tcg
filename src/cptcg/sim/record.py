"""Replays.

A game is fully determined by (ruleset digest, decklists, seed, action indices), so a replay is
tiny and *exact*: re-running it reproduces every draw, roll and decision. That is what powers the
watch-back viewer, UNDO (replay to n-1), and bug reports from mass simulation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

from cptcg.cards.registry import Registry
from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.core.engine import apply, new_game
from cptcg.core.state import GameState
from cptcg.deck.decklist import Decklist

FORMAT = 1


@dataclass
class Replay:
    seed: int
    decks: tuple[dict, dict]              # serialised Decklists
    actions: list[int]
    rules: str = DEFAULT_CONFIG.digest()
    agents: tuple[str, str] = ("?", "?")
    winner: int | None = None
    end_reason: str | None = None
    turns: int | None = None
    format: int = FORMAT
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_game(cls, s: GameState, decks: tuple[Decklist, Decklist],
                  agents: tuple[str, str] = ("?", "?")) -> "Replay":
        if s.actions is None:
            raise ValueError("game was not recorded (new_game(record=True))")
        return cls(seed=s.seed, decks=(_deck(decks[0]), _deck(decks[1])),
                   actions=list(s.actions), rules=s.cfg.digest(), agents=agents,
                   winner=s.winner if s.over else None,
                   end_reason=s.end_reason.name if s.over else None, turns=s.turn)

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, separators=(",", ":"))
            f.write("\n")

    @classmethod
    def load(cls, path: str | Path) -> "Replay":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        raw["decks"] = tuple(raw["decks"])
        raw["agents"] = tuple(raw["agents"])
        return cls(**raw)

    def decklists(self) -> tuple[Decklist, Decklist]:
        return (_undeck(self.decks[0]), _undeck(self.decks[1]))

    def steps(self, reg: Registry, cfg: RulesConfig = DEFAULT_CONFIG) -> Iterator[tuple[GameState, int | None]]:
        """Yield (state, next_action_index) before each action, then (final_state, None)."""
        if cfg.digest() != self.rules:
            raise ValueError(f"replay was recorded under ruleset {self.rules}, current is {cfg.digest()}")
        s = new_game(reg, self.decklists(), self.seed, cfg, record=True)
        for idx in self.actions:
            yield s, idx
            apply(s, idx)
        yield s, None

    def final_state(self, reg: Registry, cfg: RulesConfig = DEFAULT_CONFIG) -> GameState:
        s = None
        for s, _ in self.steps(reg, cfg):
            pass
        return s


def _deck(d: Decklist) -> dict:
    return {"name": d.name, "legends": list(d.legends), "main": d.counts()}


def _undeck(raw: dict) -> Decklist:
    return Decklist.from_counts(raw["name"], raw["legends"], raw["main"])
