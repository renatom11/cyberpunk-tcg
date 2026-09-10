"""Authoring helpers for card scripts.

The one rule (see docs/effects-authoring.md): a continuation must use the ctx it is *given*,
never the one from the enclosing scope — the enclosing ctx is bound to whichever state existed
when the choice was created, and a search agent will resolve the same choice on clones.
"""

from __future__ import annotations

from typing import Callable

from cptcg.cards.registry import Ability, CardScript
from cptcg.core.effects import EffectCtx
from cptcg.core.enums import CardType, Keyword
from cptcg.core.ops import ATTACKING, FIGHTING, VS_LEGEND, VS_UNIT  # re-exported for scripts

UNIT, PROGRAM, GEAR, LEGEND = CardType.UNIT, CardType.PROGRAM, CardType.GEAR, CardType.LEGEND
ADRENALINE, GO_SOLO, QUICK, BLOCKER = Keyword.ADRENALINE, Keyword.GO_SOLO, Keyword.QUICK, Keyword.BLOCKER

__all__ = ["Ability", "CardScript", "EffectCtx", "UNIT", "PROGRAM", "GEAR", "LEGEND", "ADRENALINE",
           "GO_SOLO", "QUICK", "BLOCKER", "ATTACKING", "FIGHTING", "VS_LEGEND", "VS_UNIT",
           "power_le", "cost_le", "has_tag", "is_type", "defeat_one", "bottom_deck_one",
           "spend_one", "temp_power_one", "discard_rival", "gigs_8plus", "first_each_turn",
           "self_units_of", "hand_of_type"]


# ------------------------------------------------------------------ predicates
def power_le(c: EffectCtx, n: int) -> Callable[[int], bool]:
    return lambda u: c.power(u) <= n


def cost_le(c: EffectCtx, n: int) -> Callable[[int], bool]:
    return lambda u: (c.d(u).cost or 0) <= n


def has_tag(c: EffectCtx, tag: str) -> Callable[[int], bool]:
    return lambda u: tag in c.d(u).tags


def is_type(c: EffectCtx, t: CardType) -> Callable[[int], bool]:
    return lambda u: c.d(u).type is t


def gigs_8plus(c: EffectCtx, player: int | None = None) -> int:
    return sum(1 for v in c.gig_values(player) if v >= 8)


def self_units_of(c: EffectCtx, player: int, tag: str) -> list[int]:
    return [u for u in c.units(player) if tag in c.d(u).tags]


def hand_of_type(c: EffectCtx, t: CardType, player: int | None = None) -> list[int]:
    return [i for i in c.hand(player) if c.d(i).type is t]


def first_each_turn(c: EffectCtx, key: str) -> bool:
    return c.once(key)


# ------------------------------------------------------------------ one-target effects
def defeat_one(c: EffectCtx, cands, *, optional: bool = False, prompt: str = "Defeat") -> None:
    c.choose(list(cands), lambda c2, u: c2.defeat(u), prompt=prompt, optional=optional)


def bottom_deck_one(c: EffectCtx, cands, *, optional: bool = False, then: Callable | None = None) -> None:
    def _do(c2: EffectCtx, u: int) -> None:
        c2.bottom_deck(u)
        if then is not None:
            then(c2, u)
    c.choose(list(cands), _do, prompt="Bottom-deck", optional=optional)


def spend_one(c: EffectCtx, cands, *, optional: bool = False, then: Callable | None = None) -> None:
    def _do(c2: EffectCtx, u: int) -> None:
        c2.spend(u)
        if then is not None:
            then(c2, u)
    c.choose(list(cands), _do, prompt="Spend", optional=optional)


def temp_power_one(c: EffectCtx, cands, delta: int, cond: int = 0, *, optional: bool = False,
                   prompt: str = "") -> None:
    c.choose(list(cands), lambda c2, u: c2.temp_power(u, delta, cond),
             prompt=prompt or f"{delta:+d} power", optional=optional)


def discard_rival(c: EffectCtx, n: int = 1, cont: Callable | None = None) -> None:
    c.discard(n, player=c.rival, cont=cont)
