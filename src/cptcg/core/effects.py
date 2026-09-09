"""Effect context: the API card scripts use to change the game.

Card scripts only touch state through these atoms. Atoms either mutate immediately or queue
Steps / a PICK choice — they never wait for input inside a Python call. Phase 3 fills this out;
this is the stable core interface.
"""

from __future__ import annotations

from cptcg.core import ops
from cptcg.core.state import GameState


class EffectCtx:
    __slots__ = ("s", "inst", "player")

    def __init__(self, s: GameState, inst: int) -> None:
        self.s = s
        self.inst = inst
        self.player = s.i_owner[inst]

    @property
    def rival(self) -> int:
        return 1 - self.player

    def draw(self, n: int = 1, player: int | None = None) -> int:
        return ops.draw(self.s, self.player if player is None else player, n)

    def trash_top(self, n: int, player: int | None = None) -> list[int]:
        return ops.trash_top(self.s, self.player if player is None else player, n)

    def add_temp_power(self, inst: int, delta: int) -> None:
        ops.add_temp_power(self.s, inst, delta)

    def defeat(self, inst: int) -> None:
        ops.defeat(self.s, inst)

    def ready(self, inst: int) -> None:
        ops.ready(self.s, inst)

    def spend(self, inst: int) -> None:
        ops.spend(self.s, inst)

    def adjust_gig(self, player: int, index: int, delta: int) -> None:
        ops.adjust_gig(self.s, player, index, delta)
