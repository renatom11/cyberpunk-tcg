"""The agent interface.

An agent answers each ``Choice`` with an index into ``choice.options``. It receives the full
GameState for now; the heuristic agent is written to read only public information and its own
hand (a redacting view and a paranoid check come with the search agent).
"""

from __future__ import annotations

from cptcg.core.actions import Choice
from cptcg.core.rng import Pcg32
from cptcg.core.state import GameState


class Agent:
    name = "agent"

    def __init__(self, seed: int = 0) -> None:
        self.rng = Pcg32(seed, seq=7)
        self.me = -1

    def new_game(self, seed: int, me: int) -> None:
        self.rng = Pcg32(seed ^ 0xA6E17, seq=11 + me)
        self.me = me

    def act(self, s: GameState, choice: Choice) -> int:  # pragma: no cover - interface
        raise NotImplementedError


AGENTS: dict[str, type[Agent]] = {}


def register(cls: type[Agent]) -> type[Agent]:
    AGENTS[cls.name] = cls
    return cls


def make_agent(name: str, seed: int = 0) -> Agent:
    import cptcg.agents.random_agent  # noqa: F401
    import cptcg.agents.heuristic  # noqa: F401
    try:
        return AGENTS[name](seed)
    except KeyError:
        raise KeyError(f"unknown agent {name!r}; known: {sorted(AGENTS)}") from None
