"""Card definitions.

Static card data (``CardDef``) is loaded from JSON. Card *behaviour* is Python, registered by
card id with ``@script`` and joined to the ``CardDef`` when the registry is built. The engine only
ever sees ``DEFS[idx]`` — one list index, no dict lookups in the hot path.

Cards whose printed text implies an effect but have no registered script are marked
``needs_script``; deck validation refuses them unless explicitly allowed, so an unimplemented card
can never silently play as vanilla.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from cptcg.core.enums import CardType, Color, Keyword

_TYPE = {"Legend": CardType.LEGEND, "Unit": CardType.UNIT,
         "Program": CardType.PROGRAM, "Gear": CardType.GEAR}
_COLOR = {"Red": Color.RED, "Green": Color.GREEN, "Blue": Color.BLUE, "Yellow": Color.YELLOW}
_KEYWORD = {"ADRENALINE": Keyword.ADRENALINE, "GO SOLO": Keyword.GO_SOLO,
            "QUICK": Keyword.QUICK, "BLOCKER": Keyword.BLOCKER}

# Text that is *only* a keyword reminder (or flavour) carries no effect of its own.
_REMINDER = re.compile(
    r"\(.*?\)"                      # parenthesised reminder text
    r"|\b(ADRENALINE|GO SOLO|QUICK|BLOCKER)\b"
    r"|\"[^\"]*\""                  # quoted flavour text
    r"|[\s.]"
)


@dataclass(frozen=True, slots=True)
class CardDef:
    idx: int                      # position in DEFS; stable for the life of the registry
    id: str                       # e.g. "WNC-005"
    name: str
    subtitle: str | None
    type: CardType
    color: Color
    ram: int
    cost: int | None              # None = printed "—" (a Legend that can't GO SOLO)
    power: int | None             # printed power; None for Programs
    power_variable: bool          # printed as "N+" — real power depends on board state
    sell_tag: bool
    tags: frozenset[str]
    keywords: frozenset[Keyword]
    text: str
    set_code: str
    number: int
    rarity: str | None
    verified: bool                # transcription checked against the card image
    script: "CardScript | None"   # behaviour, bound by id; None = vanilla
    needs_script: bool            # printed text implies an effect but no script exists

    @property
    def is_legend(self) -> bool:
        return self.type is CardType.LEGEND

    @property
    def is_unit(self) -> bool:
        return self.type is CardType.UNIT

    def has(self, kw: Keyword) -> bool:
        return kw in self.keywords


@dataclass(frozen=True, slots=True)
class Ability:
    """An activated ability. ``effect(ctx)`` runs after the costs are paid."""

    effect: Callable
    cost: int | Callable = 0      # €$ to pay, or cost(ctx) -> int
    self_spend: bool = False      # the ⊡ symbol: spend this card
    quick: bool = False           # may also be used as a reaction when a rival Unit attacks
    legal: Callable | None = None # extra precondition, legal(ctx) -> bool
    label: str = ""


@dataclass(frozen=True, slots=True)
class CardScript:
    """Behaviour hooks for one card. Every field is optional; see docs/effects-authoring.md.

    Hooks receive an EffectCtx for the card they belong to. They must never block: anything
    that needs a decision goes through ctx.ask()/ctx.choose(), which queue a step.
    """

    on_play: Callable | None = None       # PLAY trigger (Units, Programs, Gear)
    on_call: Callable | None = None       # CALL trigger (Legends)
    on_attack: Callable | None = None     # ATTACK trigger, before the target is declared
    on_defeated: Callable | None = None   # DEFEATED trigger
    on_event: Callable | None = None      # on_event(ctx, ev) for any card in play; ev is a tuple
    power_mod: Callable | None = None     # power_mod(ctx, unit, situation) -> delta, for any unit
    cost_mod: Callable | None = None      # cost_mod(ctx, player, inst, go_solo) -> delta
    self_cost: Callable | None = None     # self_cost(ctx, player, base) -> cost to play this card
    attack_perm: Callable | None = None   # attack_perm(ctx, (units_ok, gigs_ok)) -> new pair or None
    would_defeat: Callable | None = None  # would_defeat(ctx, inst) -> True if replaced
    would_steal: Callable | None = None   # would_steal(ctx, thief, victim, index) -> True if handled
    unblockable: Callable | None = None   # unblockable(ctx) -> bool, for this attacking Unit
    abilities: tuple = ()
    extra: dict = field(default_factory=dict)


SCRIPTS: dict[str, CardScript] = {}


def script(card_id: str):
    """Register behaviour for a card id: ``@script("WNC-005")`` above a CardScript-returning fn."""

    def deco(fn: Callable[[], CardScript]):
        SCRIPTS[card_id] = fn()
        return fn

    return deco


def _text_implies_effect(text: str) -> bool:
    return bool(_REMINDER.sub("", text).strip())


def parse_card(raw: dict[str, Any], idx: int) -> CardDef:
    power_raw = raw.get("power")
    power_variable = isinstance(power_raw, str) and power_raw.endswith("+")
    power = int(str(power_raw).rstrip("+")) if power_raw is not None else None
    cost_raw = raw.get("cost")
    cost = None if cost_raw in (None, "-", "—") else int(cost_raw)
    text = raw.get("text") or ""
    sc = SCRIPTS.get(raw["id"])
    return CardDef(
        idx=idx,
        id=raw["id"],
        name=raw["name"],
        subtitle=raw.get("subtitle"),
        type=_TYPE[raw["type"]],
        color=_COLOR[raw["color"]],
        ram=int(raw["ram"]),
        cost=cost,
        power=power,
        power_variable=power_variable,
        sell_tag=bool(raw.get("sell_tag", False)),
        tags=frozenset(t.upper() for t in raw.get("tags", ())),
        keywords=frozenset(_KEYWORD[k] for k in raw.get("keywords", ())),
        text=text,
        set_code=raw.get("set", ""),
        number=int(raw.get("number", 0)),
        rarity=raw.get("rarity"),
        verified=bool(raw.get("verified", False)),
        script=sc,
        needs_script=sc is None and _text_implies_effect(text),
    )


class Registry:
    """The card pool in use. Built once per process; the engine indexes ``defs`` by CardIdx."""

    __slots__ = ("defs", "by_id", "by_name")

    def __init__(self, raws: list[dict[str, Any]]) -> None:
        self.defs: list[CardDef] = []
        self.by_id: dict[str, CardDef] = {}
        self.by_name: dict[str, list[CardDef]] = {}
        for raw in raws:
            if raw["id"] in self.by_id:
                raise ValueError(f"duplicate card id {raw['id']}")
            d = parse_card(raw, len(self.defs))
            self.defs.append(d)
            self.by_id[d.id] = d
            self.by_name.setdefault(d.name.lower(), []).append(d)

    def __len__(self) -> int:
        return len(self.defs)

    def __getitem__(self, idx: int) -> CardDef:
        return self.defs[idx]

    def get(self, card_id: str) -> CardDef:
        try:
            return self.by_id[card_id]
        except KeyError:
            raise KeyError(f"unknown card id {card_id!r}") from None

    def find(self, name: str, subtitle: str | None = None) -> CardDef:
        cands = self.by_name.get(name.lower(), [])
        if subtitle is not None:
            cands = [c for c in cands if (c.subtitle or "").lower() == subtitle.lower()]
        if len(cands) != 1:
            raise KeyError(f"{len(cands)} cards match {name!r}/{subtitle!r}")
        return cands[0]

    @classmethod
    def from_files(cls, *paths: str | Path) -> "Registry":
        raws: list[dict[str, Any]] = []
        for p in paths:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            raws.extend(data["cards"] if isinstance(data, dict) else data)
        return cls(raws)

    def unimplemented(self) -> list[CardDef]:
        return [d for d in self.defs if d.needs_script]


DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "cards"


def load_default(load_scripts: bool = True) -> Registry:
    """Load every JSON file under data/cards, after importing the card scripts."""
    if load_scripts:
        import cptcg.cards.sets  # noqa: F401  registers scripts as a side effect
    return Registry.from_files(*sorted(DATA_DIR.glob("*.json")))
