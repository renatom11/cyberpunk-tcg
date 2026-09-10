"""Uniform-random legal play, lightly biased away from ending the turn with things to do."""

from __future__ import annotations

from cptcg.agents.base import Agent, register
from cptcg.core.actions import Choice, ChoiceKind, EndTurn
from cptcg.core.state import GameState


@register
class RandomAgent(Agent):
    name = "random"

    def act(self, s: GameState, choice: Choice) -> int:
        opts = choice.options
        if choice.kind is ChoiceKind.MAIN and len(opts) > 1 and isinstance(opts[0], EndTurn) \
                and self.rng.below(10) < 9:
            return 1 + self.rng.below(len(opts) - 1)
        return self.rng.below(len(opts))
