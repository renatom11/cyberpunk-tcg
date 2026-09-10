"""Opinionated deck-building personalities.

``builder.heuristic_deck`` is one hand-weighted opinion about what a good deck looks like. A
*strategy* is a different opinion with a name: it ranks the legal pool by its own beliefs
about how games are won, picks Legends that suit it, and — when a ``Knowledge`` store is
supplied — blends in what measured play has shown about each card. All personalities share
the same greedy filler (curve, type quotas, sell-tag floor), so the decks differ because the
*scoring* differs, not because of a different construction algorithm.

Why feature extraction rather than card lists: the pool is 146 cards today and will grow. Each
card's rules text is reduced once to a small ``Features`` vector (does it remove Units? move
Gigs? ready Eddies?) and every personality is a set of weights over those features, so a new
set gets a first-cut evaluation for free and a personality is a dozen readable numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from cptcg.cards.registry import CardDef, Registry
from cptcg.core.enums import CardType, Keyword
from cptcg.core.rng import Pcg32
from cptcg.deck.builder import BuildPrefs, card_score, heuristic_deck, legal_pool, random_legends
from cptcg.deck.decklist import Decklist

UNIT, PROGRAM, GEAR = CardType.UNIT, CardType.PROGRAM, CardType.GEAR

# ------------------------------------------------------------------ card features
_REMINDER = re.compile(r"\(.*?\)", re.S)
_CAPS = re.compile(r"\b[A-Z][A-Z']{2,}(?: [A-Z]{3,})?\b")
_NOT_TAGS = {"PLAY", "CALL", "ATTACK", "DEFEATED", "ADRENALINE", "GO SOLO", "SOLO", "QUICK",
             "BLOCKER", "RAM", "DEADMAN TRANSMITTER", "DEADMAN"}

_RE = {
    # removes or neutralises a rival Unit: defeat / bottom-deck / spend it
    "removal": r"\b(defeat|bottom-deck|spend)s?\b (a |all |2 |the opposing |up to \d )?(spent |unequipped |ready )?(rival|unit)",
    # makes a rival Unit worse without removing it
    "debuff": r"rival units? (-\d|can't|loses|steals 1 fewer)|a unit can't attack|all rival units -\d",
    # keeps our Gigs or Units where they are
    "protect": r"can't steal|isn't stolen|steals 1 fewer|blocker this turn|can't be defeated|doesn't defeat|would be defeated, you may",
    # changes a die's value: adjust / increase / decrease / swap / set / reroll
    "gig_move": r"\b(adjust|increase|decrease|swap|set)\b[^.]{0,40}\bgigs?\b|\bgig\b[^.]{0,25}\b(increase|decrease|adjust) it\b|reroll",
    # rewards a particular die configuration
    "gig_payoff": r"value-pair|min gig|max gig|8\+ value|different values|equal to (any friendly gig|the value of a friendly gig|that gig's value)|equals the value of a friendly gig|value of a friendly (d20|max gig)|(even|odd) value|value is (even|odd)|gig with an (even|odd)|cost equal to any friendly gig|the discarded card's cost",
    # steals more than the base rate, or rewards stealing
    "gig_steal": r"(?<!would )steals? (a|1 or more|a rival) gigs?|also steals a gig|attack their gig area",
    "cred": r"★",
    "draw": r"\bdraw (\d|1 for each)",
    "eddies": r"ready (\d) eddies?",
    "call": r"call (a legend|it) for free|may call a legend",
    "discount": r"for -\d €\$|for free|play this (program|unit|gear) for \d €\$",
    "haste": r"can attack (rival units |their gig area |spent rival units )?(the turn it's played|this turn)|adrenaline this turn",
    "pump": r"\+\d power|gains power|has \+\d power",
    "ready": r"ready (this unit|another friendly unit|up to \d friendly units|that unit|a friendly face-up legend|up to \d merc legends|it\b)",
    "cant_attack": r"this unit can't attack(?! unless)|can only attack rival units",
    "unblockable": r"can't be blocked|may attack ready units|attack ready units",
}
_COMPILED = {k: re.compile(v) for k, v in _RE.items()}


@dataclass(frozen=True, slots=True)
class Features:
    """What a card's rules text *does*, as small counts. Zero everywhere for a vanilla card."""
    removal: int = 0
    debuff: int = 0
    protect: int = 0
    gig_move: int = 0
    gig_payoff: int = 0
    gig_steal: int = 0
    cred: int = 0
    draw: int = 0
    eddies: int = 0          # total Eddies readied by the text
    call: int = 0
    discount: int = 0
    haste: int = 0
    pump: int = 0
    ready: int = 0
    cant_attack: bool = False
    unblockable: bool = False
    tag_refs: frozenset = frozenset()   # tags the text names (ARASAKA in "friendly ARASAKA Units")

    @property
    def gig(self) -> int:
        """Anything Gig-shaped: the GigManipulation personality's whole world view."""
        return self.gig_move + self.gig_payoff + self.gig_steal


def rules_text(d: CardDef) -> str:
    """Card text with reminder parentheticals removed, lower-cased for matching."""
    return _REMINDER.sub("", d.text).lower()


@lru_cache(maxsize=4096)
def _features_of(card_id: str, text: str, keywords: frozenset) -> Features:
    t = _REMINDER.sub("", text).lower()
    n = {k: len(rx.findall(t)) for k, rx in _COMPILED.items()}
    eddies = sum(int(m) for m in _COMPILED["eddies"].findall(t))
    refs = frozenset(w for w in _CAPS.findall(_REMINDER.sub("", text)) if w not in _NOT_TAGS)
    return Features(
        removal=n["removal"], debuff=n["debuff"],
        protect=n["protect"] + (1 if Keyword.BLOCKER in keywords else 0),
        gig_move=n["gig_move"], gig_payoff=n["gig_payoff"], gig_steal=n["gig_steal"], cred=n["cred"],
        draw=n["draw"], eddies=eddies, call=n["call"], discount=n["discount"],
        haste=n["haste"] + (1 if Keyword.ADRENALINE in keywords else 0) + (1 if Keyword.GO_SOLO in keywords else 0),
        pump=n["pump"], ready=n["ready"], cant_attack=bool(n["cant_attack"]), unblockable=bool(n["unblockable"]),
        tag_refs=refs,
    )


def features(d: CardDef) -> Features:
    return _features_of(d.id, d.text, d.keywords)


def context_key(reg: Registry, legends) -> str:
    """The Legend colour set, e.g. ``"GREEN|RED"`` — the bucket learned card values live in.
    Colour is the right granularity: it fixes which cards are even legal together, and there
    are few enough combinations that each bucket collects evidence quickly."""
    return "|".join(sorted({reg.get(l).color.name for l in legends}))


# ------------------------------------------------------------------ build context
@dataclass
class BuildCtx:
    """Everything a strategy may look at while scoring one card for one deck."""
    reg: Registry
    legends: list[CardDef]
    pool: list[CardDef]
    ltags: frozenset
    theme: dict = field(default_factory=dict)     # tag -> weight, for tag-synergy scoring
    knowledge: object | None = None
    context: str | None = None
    tag_depth: dict = field(default_factory=dict)  # tag -> cards in the legal pool carrying it


def _cost(d: CardDef) -> int:
    return d.cost or 1


def _ppc(d: CardDef) -> float:
    """Power per Eddie — the crude unit of tempo."""
    return (d.power or 0) / _cost(d)


# ------------------------------------------------------------------ the interface
class BuilderStrategy:
    """A named opinion about deck construction. Subclasses set ``prefs`` (the filler's shape
    targets) and override ``score_card`` and ``legend_fit``; everything else is shared."""

    name: str = "base"
    prefs: BuildPrefs = BuildPrefs()
    knowledge_w: float = 6.0     # IWD is ±0.1-0.3 once shrunk; static scores are ~0-6
    noise: float = 0.35

    def describe(self) -> str:
        return (self.__doc__ or "").strip()

    def score_card(self, d: CardDef, ctx: BuildCtx) -> float:  # pragma: no cover - abstract
        raise NotImplementedError

    def legend_fit(self, legends: list[CardDef], reg: Registry) -> float:
        """How much this personality likes a Legend triple, before looking at the pool."""
        return 0.0

    # -------------------------------------------------------------- shared machinery
    def make_ctx(self, reg: Registry, legends: list[str], knowledge=None) -> BuildCtx:
        ldefs = [reg.get(l) for l in legends]
        pool = legal_pool(reg, legends)
        depth: dict = {}
        for d in pool:
            for t in d.tags:
                depth[t] = depth.get(t, 0) + 1
        ctx = BuildCtx(reg, ldefs, pool, frozenset().union(*(l.tags for l in ldefs)),
                       knowledge=knowledge, context=context_key(reg, legends), tag_depth=depth)
        ctx.theme = theme_tags(ctx)
        return ctx

    def scorer(self, ctx: BuildCtx, rng: Pcg32):
        """The full per-card score: belief + learned value + a little noise so two builds of
        the same personality on the same Legends are not identical."""
        kn = ctx.knowledge

        def score(d: CardDef) -> float:
            s = self.score_card(d, ctx)
            if kn is not None:
                v = kn.value(d.id, ctx.context)
                if v is not None:
                    s += self.knowledge_w * v
            return s + self.noise * (rng.below(1000) / 1000 - 0.5)
        return score

    def build(self, reg: Registry, legends: list[str] | None, rng: Pcg32, knowledge=None,
              name: str | None = None) -> Decklist:
        legends = legends or self.choose_legends(reg, rng)
        ctx = self.make_ctx(reg, legends, knowledge)
        return heuristic_deck(reg, legends, rng, self.prefs, name=name or self.name,
                              score_fn=self.scorer(ctx, rng), generated="strategy",
                              strategy=self.name, context=ctx.context)

    def pool_quality(self, reg: Registry, legends: list[str], top: int = 24) -> float:
        """Mean static score of the best ``top`` legal cards: a Legend triple is only as good
        as the deck it lets this personality build."""
        ctx = self.make_ctx(reg, legends)
        scores = sorted((self.score_card(d, ctx) for d in ctx.pool), reverse=True)
        if not scores:
            return -10.0
        scores = scores[:top]
        return sum(scores) / len(scores)

    def choose_legends(self, reg: Registry, rng: Pcg32, samples: int = 40) -> list[str]:
        """Sample Legend triples and keep the one with the best ``legend_fit`` + pool quality.
        Sampling (not enumeration) keeps this fast and keeps the league varied."""
        best, best_fit = None, -1e9
        for _ in range(samples):
            ids = random_legends(reg, rng)
            fit = (legend_fit(self, [reg.get(i) for i in ids], reg) + self.pool_quality(reg, ids)
                   + 0.4 * rng.below(1000) / 1000)
            if fit > best_fit:
                best, best_fit = ids, fit
        return list(best)


def legend_fit(strategy: BuilderStrategy, legends: list[CardDef], reg: Registry | None = None) -> float:
    """Module-level spelling of ``strategy.legend_fit`` (the personality's Legend preference)."""
    return strategy.legend_fit(legends, reg)


def theme_tags(ctx: BuildCtx) -> dict[str, float]:
    """Tag weights for tag-synergy scoring. A Legend's own tags count; a tag a Legend's text
    *names* counts more (Saburo makes every ARASAKA Unit better); and a tag is discounted when
    the legal pool is too shallow to build around it."""
    theme: dict[str, float] = {}
    all_tags = {t for d in ctx.pool for t in d.tags} | ctx.ltags
    for l in ctx.legends:
        for t in l.tags:
            theme[t] = theme.get(t, 0.0) + 1.0
        for t in features(l).tag_refs & all_tags:
            theme[t] = theme.get(t, 0.0) + 1.5
    for t in list(theme):
        depth = ctx.tag_depth.get(t, 0)
        theme[t] *= 0.4 + 0.6 * min(1.0, depth / 8)
    # Normalise so the strongest theme weighs 2.0: three ARASAKA Legends should build a tighter
    # deck than one, not a deck whose scores dwarf the learned values blended in later.
    top = max(theme.values(), default=0.0)
    if top > 0:
        theme = {t: 2.0 * w / top for t, w in theme.items()}
    return theme


# ------------------------------------------------------------------ personalities
class Aggro(BuilderStrategy):
    """Race. The game is decided by Gig steals and a Unit steals two at power 10, so the deck
    wants cheap power on the field early, ways to attack the turn a Unit lands, and nothing
    that sits around. Blockers and card draw are someone else's problem."""

    name = "aggro"
    prefs = BuildPrefs(unit_share=0.65, program_share=0.15, gear_share=0.20, sell_min=0.35,
                       curve=(0.16, 0.30, 0.26, 0.14, 0.08, 0.04, 0.02))

    def score_card(self, d: CardDef, ctx: BuildCtx) -> float:
        f = features(d)
        cost = _cost(d)
        s = 0.3 * f.draw + 0.2 * len(d.tags & ctx.ltags) + 1.0 * f.haste + 0.6 * f.ready + 0.5 * f.unblockable
        if d.type is UNIT:
            s += 1.6 * _ppc(d) - 0.45 * max(0, cost - 3)     # a 6-drop lands on turn 6 at best
            if (d.power or 0) >= 10:
                s += 1.0                                      # steals two Gigs per swing
            if cost <= 3:
                s += 0.5
            if not d.power:
                s -= 1.5
            if f.cant_attack:
                s -= 1.5
        elif d.type is GEAR:
            s += 1.0 * _ppc(d) + 0.2 + (0.4 if (d.power or 0) >= 2 and cost <= 2 else 0)
        else:
            s += 0.3 + 0.8 * f.pump + 0.4 * f.gig_steal + 0.3 * f.removal - 0.4 * max(0, cost - 3)
        return s

    def legend_fit(self, legends: list[CardDef], reg: Registry) -> float:
        fit = 0.0
        for l in legends:
            f = features(l)
            if Keyword.GO_SOLO in l.keywords and l.cost is not None:
                fit += (2.0 if l.cost <= 6 else 1.0) + _ppc(l)
            fit += 0.7 * (f.pump + f.haste - (1 if Keyword.GO_SOLO in l.keywords else 0))
        return fit


class Control(BuilderStrategy):
    """Deny. Ready Units can't be attacked and only BLOCKER/QUICK interrupt a steal, so the deck
    wants blockers, removal and reactions to keep its Gigs, then wins in Overtime by holding
    the majority when the 14th turn ends — or with a late bomb once the board is clear."""

    name = "control"
    prefs = BuildPrefs(unit_share=0.45, program_share=0.35, gear_share=0.20, sell_min=0.50,
                       curve=(0.06, 0.18, 0.24, 0.20, 0.14, 0.10, 0.08))

    def score_card(self, d: CardDef, ctx: BuildCtx) -> float:
        f = features(d)
        cost = _cost(d)
        blocker = Keyword.BLOCKER in d.keywords
        quick = Keyword.QUICK in d.keywords
        s = 0.4 * f.draw + 0.2 * len(d.tags & ctx.ltags) + 1.2 * f.removal + 0.8 * f.debuff + 0.8 * f.protect
        if d.type is UNIT:
            s += 0.8 * _ppc(d) + (1.5 if blocker else 0) + (1.0 if quick else 0)
            s += 0.15 * min(cost, 7)                          # big bodies win Overtime fights
            if (d.power or 0) >= 8 and cost >= 6:
                s += 0.5                                      # the finisher
            if not d.power and not blocker and not f.removal:
                s -= 0.8
            if f.cant_attack and not blocker:
                s -= 0.5
        elif d.type is PROGRAM:
            s += 0.6 + (0.8 if quick else 0)
        else:
            s += 0.5 * _ppc(d) + (1.2 if blocker else 0) + (0.8 if quick else 0)
        return s

    def legend_fit(self, legends: list[CardDef], reg: Registry) -> float:
        fit = 0.0
        for l in legends:
            f = features(l)
            fit += 1.5 * ((Keyword.QUICK in l.keywords) + (Keyword.BLOCKER in l.keywords))
            fit += 1.0 * (f.removal + f.debuff) + 0.7 * f.protect + 0.5 * f.draw
        return fit


class Economy(BuilderStrategy):
    """Eddies win. Selling one card a turn is the only engine, so every card should be
    sellable (Programs and Gear all are; almost no Unit is), and the few Units should be bombs
    the extra Eddies pay for. Anything that readies an Eddie, calls a Legend for free or plays
    for a discount is a second income."""

    name = "economy"
    prefs = BuildPrefs(unit_share=0.35, program_share=0.40, gear_share=0.25, sell_min=0.60,
                       curve=(0.14, 0.20, 0.16, 0.12, 0.12, 0.14, 0.12))

    def score_card(self, d: CardDef, ctx: BuildCtx) -> float:
        f = features(d)
        cost = _cost(d)
        s = (1.5 if d.sell_tag else 0) + 1.2 * f.eddies + 1.0 * f.call + 0.9 * f.discount + 0.7 * f.draw
        s += 0.2 * len(d.tags & ctx.ltags)
        if d.type is UNIT:
            s += 0.7 * _ppc(d)
            if cost >= 6 and (d.power or 0) >= 8:
                s += 1.2 + (0.3 if cost >= 7 else 0)          # what the money is for
            if cost <= 2:
                s -= 0.3
            if not d.power and not (f.eddies or f.draw or f.call):
                s -= 0.8
        elif d.type is PROGRAM:
            s += 0.4
        else:
            s += 0.3 + 0.4 * _ppc(d)
        return s

    def legend_fit(self, legends: list[CardDef], reg: Registry) -> float:
        fit = 0.0
        for l in legends:
            f = features(l)
            if "call:" in rules_text(l):
                fit += 1.5                                    # a cheap, useful CALL
            fit += 1.5 * f.eddies + 1.0 * f.discount + 0.8 * f.call + 0.5 * f.draw
        return fit


class GigManipulation(BuilderStrategy):
    """The dice are the game. Street Cred, value-pairs, min/max Gigs and 8+ values all key off
    die faces you can adjust, swap or set, and several cards steal an extra Gig or draw when the
    faces line up. The deck stacks movers and payoffs and lets the Units be average."""

    name = "gig"
    prefs = BuildPrefs(unit_share=0.50, program_share=0.30, gear_share=0.20, sell_min=0.45)

    def score_card(self, d: CardDef, ctx: BuildCtx) -> float:
        f = features(d)
        s = 1.5 * f.gig_move + 1.2 * f.gig_payoff + 1.3 * f.gig_steal + 0.5 * f.cred + 0.4 * f.draw
        s += 0.2 * len(d.tags & ctx.ltags)
        if d.type is UNIT:
            s += 0.8 * _ppc(d) + (0.8 if (d.power or 0) >= 10 else 0)
            if not d.power and not f.gig:
                s -= 0.8
            if f.cant_attack:
                s -= 0.8
        elif d.type is PROGRAM:
            s += 0.4
        else:
            s += 0.3 + 0.4 * _ppc(d)
        return s

    def legend_fit(self, legends: list[CardDef], reg: Registry) -> float:
        return sum(2.0 * features(l).gig_move + 1.5 * features(l).gig_payoff + 1.5 * features(l).gig_steal
                   + 0.5 * features(l).cred for l in legends)


class Synergy(BuilderStrategy):
    """Tribes. Legends and cards name tags — ARASAKA Units attack harder under Saburo, BRAINDANCE
    Programs pump under Judy, CYBERWARE Gear is cheap under Viktor — so the deck maximises tag
    overlap with its Legends and between its own cards, and picks Legends that share tags."""

    name = "synergy"
    prefs = BuildPrefs(unit_share=0.55, program_share=0.25, gear_share=0.20, sell_min=0.40)

    def score_card(self, d: CardDef, ctx: BuildCtx) -> float:
        f = features(d)
        theme = ctx.theme
        s = 1.2 * sum(theme.get(t, 0.0) for t in d.tags) + 1.5 * sum(theme.get(t, 0.0) for t in f.tag_refs)
        s += 0.3 * f.draw
        if d.type is UNIT:
            s += 0.8 * _ppc(d) - (0.6 if not d.power else 0) - (0.6 if f.cant_attack else 0)
        elif d.type is PROGRAM:
            s += 0.5
        else:
            s += 0.3 + 0.4 * _ppc(d)
        return s

    def legend_fit(self, legends: list[CardDef], reg: Registry) -> float:
        fit = 0.0
        for i in range(3):
            for j in range(i + 1, 3):
                a, b = legends[i], legends[j]
                fit += 1.5 * len(a.tags & b.tags) + (0.8 if a.color is b.color else 0)
                fit += 1.0 * (len(features(a).tag_refs & b.tags) + len(features(b).tag_refs & a.tags))
        return fit


class Balanced(BuilderStrategy):
    """The original hand-weighted heuristic, kept as the control group: a bit of everything,
    no thesis. If a personality can't beat this, its thesis is wrong."""

    name = "balanced"
    prefs = BuildPrefs()

    def score_card(self, d: CardDef, ctx: BuildCtx) -> float:
        prefs = BuildPrefs(noise=0.0)
        return card_score(d, ctx.legends, prefs, Pcg32(0))


PERSONALITIES: dict[str, type[BuilderStrategy]] = {
    cls.name: cls for cls in (Aggro, Control, Economy, GigManipulation, Synergy, Balanced)
}


def blurb(text: str, sentences: int = 2) -> str:
    """The first ``sentences`` of a wrapped docstring on one line."""
    flat = " ".join(text.split())
    parts = flat.split(". ")
    out = ". ".join(parts[:sentences])
    return out if out.endswith(".") or len(parts) <= sentences else out + "."


def all_strategies() -> list[BuilderStrategy]:
    return [cls() for cls in PERSONALITIES.values()]


def get_strategy(spec: str | BuilderStrategy) -> BuilderStrategy:
    if isinstance(spec, BuilderStrategy):
        return spec
    try:
        return PERSONALITIES[spec.lower()]()
    except KeyError:
        raise KeyError(f"unknown strategy {spec!r}; choose from {', '.join(PERSONALITIES)}") from None


# ------------------------------------------------------------------ describing a deck
def deck_profile(deck: Decklist, reg: Registry) -> dict[str, float]:
    """Shape numbers a report or a test can compare across personalities."""
    defs = [reg.get(c) for c in deck.main]
    n = max(1, len(defs))
    units = [d for d in defs if d.type is UNIT]
    return {
        "mean_cost": sum(_cost(d) for d in defs) / n,
        "sell_share": sum(1 for d in defs if d.sell_tag) / n,
        "unit_share": len(units) / n,
        "mean_unit_power": sum(d.power or 0 for d in units) / max(1, len(units)),
        "blockers": sum(1 for d in defs if Keyword.BLOCKER in d.keywords),
        "quick": sum(1 for d in defs if Keyword.QUICK in d.keywords),
        "removal": sum(features(d).removal for d in defs),
        "gig_cards": sum(1 for d in defs if features(d).gig),
        "haste": sum(features(d).haste for d in defs),
        "economy": sum(features(d).eddies + features(d).call + features(d).discount for d in defs),
        "tag_overlap": sum(len(d.tags & frozenset().union(*(reg.get(l).tags for l in deck.legends)))
                           for d in defs) / n,
    }
