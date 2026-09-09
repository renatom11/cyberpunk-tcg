"""Deck legality: docs/rules.md 'Deck building & RAM'."""

from __future__ import annotations

from dataclasses import dataclass, field

from cptcg.cards.registry import CardDef, Registry
from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.core.enums import CardType, Color
from cptcg.deck.decklist import Decklist


@dataclass
class Validation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ram_limits: dict[Color, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        lines = [f"RAM limits: " + ", ".join(f"{c.name.title()} {v}" for c, v in self.ram_limits.items())]
        lines += [f"ERROR: {e}" for e in self.errors] + [f"warning: {w}" for w in self.warnings]
        return "\n".join(lines)


def ram_limits(legends: list[CardDef]) -> dict[Color, int]:
    out: dict[Color, int] = {c: 0 for c in Color}
    for l in legends:
        out[l.color] += l.ram
    return out


def validate(deck: Decklist, reg: Registry, cfg: RulesConfig = DEFAULT_CONFIG,
             allow_unverified: bool = False, allow_unscripted: bool = False) -> Validation:
    v = Validation()
    try:
        legends = [reg.get(c) for c in deck.legends]
        main = [reg.get(c) for c in deck.main]
    except KeyError as e:
        v.errors.append(str(e))
        return v

    # Exactly 3 Legends with unique names.
    if len(legends) != 3:
        v.errors.append(f"needs exactly 3 Legends, has {len(legends)}")
    for l in legends:
        if l.type is not CardType.LEGEND:
            v.errors.append(f"{l.id} is a {l.type.name.title()}, not a Legend")
    names = [l.name for l in legends]
    if len(set(names)) != len(names):
        v.errors.append(f"Legend names must be unique: {names}")

    # 40-50 main-deck cards, no Legends among them, max 3 copies.
    if not cfg.deck_min <= len(main) <= cfg.deck_max:
        v.errors.append(f"main deck must have {cfg.deck_min}-{cfg.deck_max} cards, has {len(main)}")
    for d in main:
        if d.type is CardType.LEGEND:
            v.errors.append(f"{d.id} is a Legend and can't be in the main deck")
    for cid, n in deck.counts().items():
        if n > cfg.max_copies:
            v.errors.append(f"{cid}: {n} copies (max {cfg.max_copies})")

    # RAM: a card is legal iff its RAM <= the total RAM of your Legends of its colour.
    v.ram_limits = ram_limits([l for l in legends if l.type is CardType.LEGEND])
    for cid in sorted(set(deck.main)):
        d = reg.get(cid)
        limit = v.ram_limits.get(d.color, 0)
        if d.ram > limit:
            v.errors.append(f"{cid}: {d.color.name.title()} RAM {d.ram} exceeds limit {limit}")

    # Data quality gates: a sim on an unverified or unscripted card silently lies.
    for d in legends + sorted({reg.get(c) for c in deck.main}, key=lambda d: d.id):
        if not d.verified:
            (v.warnings if allow_unverified else v.errors).append(
                f"{d.id}: transcription not verified against the card image")
        if d.needs_script:
            (v.warnings if allow_unscripted else v.errors).append(
                f"{d.id}: rules text has no script yet (would play as vanilla)")
    return v
