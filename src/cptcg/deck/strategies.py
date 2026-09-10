"""Deck builders that learn what a deck is from play.

``builder.heuristic_deck`` is one hand-weighted opinion about what a good deck looks like. The
builders here have no opinion of their own about how the game is won: they build toward a
*target fingerprint* — the shape numbers of ``deck/archetypes.py`` (average cost, type shares,
sell share, counts of blockers / removal / Gig cards / economy effects, ...) — and blend in what
measured play has shown about each card when a ``Knowledge`` store is supplied.

- ``Explorer`` draws its target at random inside the range the legal pool allows. It is what a
  league runs while no archetypes have been learned yet, and one builder in four keeps
  exploring afterwards so new kinds of deck can still appear.
- ``Learned`` targets the centre of an archetype the store found among decks that have
  actually played, and chooses Legends among that archetype's members, weighted by how they
  did.

Why feature extraction rather than card lists: the pool is 146 cards today and will grow. Each
card's rules text is reduced once to a small ``Features`` vector (does it remove Units? move
Gigs? ready Eddies?), so the fingerprint of a deck — and a new set's cards — come for free.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

from cptcg.cards.registry import CardDef, Registry
from cptcg.core.enums import CardType, Keyword
from cptcg.core.rng import Pcg32
from cptcg.deck.builder import legal_pool, random_legends
from cptcg.deck.decklist import Decklist
from cptcg.deck.validate import validate

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
        """Anything Gig-shaped: moves a die, pays off a die value, or steals extra."""
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
    """Everything a builder may look at while scoring one card for one deck."""
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


# ------------------------------------------------------------------ the shared machinery
class BuilderStrategy:
    """What every builder shares: the build context (legal pool, Legend tags, theme weights,
    learned values), the blend of learned card value and tag theme into a per-card score, and
    the greedy fill toward a target fingerprint. Subclasses decide the target and the Legends."""

    name: str = "base"
    knowledge_w: float = 6.0     # shrunk IWD is ±0.1-0.3; closeness gains are ~0-2
    theme_w: float = 0.25        # a card sharing a tag its Legends care about, per weighted tag
    closeness_w: float = 4.0     # squared distance to the target in SD-like units, scaled by deck size so far
    noise: float = 0.35
    generated: str = "builder"

    def describe(self) -> str:
        return (self.__doc__ or "").strip()

    # -------------------------------------------------------------- context
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

    def static_score(self, d: CardDef, ctx: BuildCtx) -> float:
        """The part of a card's score that does not depend on what is already in the deck:
        learned value (when the store knows the card) plus tag theme."""
        s = self.theme_w * (sum(ctx.theme.get(t, 0.0) for t in d.tags) + sum(ctx.theme.get(t, 0.0) for t in features(d).tag_refs))
        kn = ctx.knowledge
        if kn is not None:
            v = kn.value(d.id, ctx.context)
            if v is not None:
                s += self.knowledge_w * v
        return s

    # -------------------------------------------------------------- the fill
    def fill_toward(self, ctx: BuildCtx, target: dict[str, float], scale: dict[str, float], rng: Pcg32,
                    size: int = 40) -> dict[str, int]:
        """Greedy: add the card (at most three copies) that leaves the projected fingerprint
        closest to ``target`` — squared distance, each feature in units of ``scale`` — plus its
        static score and a little noise so two builds differ. Returns card counts."""
        from cptcg.deck.archetypes import FILL_FEATURES, _IDX_POWER, _IDX_UNIT, _KIND, _VEC, _VEC_OF, card_vector
        pool = ctx.pool
        vecs = [card_vector(d, ctx.ltags) for d in pool]
        static = [self.static_score(d, ctx) for d in pool]
        keys = list(FILL_FEATURES)
        tgt = [target.get(k, 0.0) for k in keys]
        sc = [max(scale.get(k, 1.0), 1e-6) for k in keys]
        kind = [_KIND[k] for k in keys]
        col = [_VEC_OF[k] for k in keys]
        totals = [0.0] * len(_VEC)
        counts: dict[str, int] = {}
        n = 0
        while n < size:
            best, best_s = -1, -1e18
            m = n + 1
            for j, d in enumerate(pool):
                if counts.get(d.id, 0) >= 3:
                    continue
                v = vecs[j]
                units = totals[_IDX_UNIT] + v[_IDX_UNIT]
                dist = 0.0
                for i, k in enumerate(kind):
                    if k == "mean":
                        val = (totals[col[i]] + v[col[i]]) / m
                    elif k == "count":
                        val = (totals[col[i]] + v[col[i]]) * size / m
                    else:
                        val = (totals[_IDX_POWER] + v[_IDX_POWER]) / units if units else tgt[i]
                    dist += ((val - tgt[i]) / sc[i]) ** 2
                # One card moves a deck of m cards by ~1/m, so the squared distance is scaled by m
                # to keep the closeness term the same size from the first pick to the last.
                s = -self.closeness_w * m * dist + static[j] + self.noise * (rng.below(1000) / 1000 - 0.5)
                if s > best_s:
                    best, best_s = j, s
            if best < 0:
                break
            d = pool[best]
            counts[d.id] = counts.get(d.id, 0) + 1
            for i, x in enumerate(vecs[best]):
                totals[i] += x
            n += 1
        return counts

    def target_for(self, ctx: BuildCtx, rng: Pcg32) -> tuple[dict[str, float], dict[str, float]]:  # pragma: no cover
        raise NotImplementedError

    def meta(self, ctx: BuildCtx) -> dict:
        return {"generated": self.generated, "archetype": "exploring", "context": ctx.context}

    def build(self, reg: Registry, legends: list[str] | None, rng: Pcg32, knowledge=None,
              name: str | None = None, used=None) -> Decklist:
        """A legal deck. ``legends`` pins the triple (a hand-picked one from the BUILD page);
        otherwise ``choose_legends`` picks, with ``used`` (an object with ``triples`` and
        ``legends`` use counts, e.g. ``generate.Batch``) as a novelty penalty."""
        legends = legends or self.choose_legends(reg, rng, used)
        ctx = self.make_ctx(reg, legends, knowledge)
        target, scale = self.target_for(ctx, rng)
        counts = self.fill_toward(ctx, target, scale, rng)
        deck = Decklist.from_counts(name or self.name, legends, counts, **self.meta(ctx))
        v = validate(deck, reg)
        if not v.ok:
            raise RuntimeError(f"builder produced an illegal deck: {v}")
        return deck

    def choose_legends(self, reg: Registry, rng: Pcg32, used=None, samples: int = 6) -> list[str]:
        """A random Legend triple with a deep pool, avoiding the triples and Legends ``used``
        already counts (so a batch spreads over the Legend space)."""
        best, best_pen = None, 1e9
        for _ in range(samples):
            ids = random_legends(reg, rng)
            pen = _novelty_penalty(ids, used) + rng.below(1000) / 1000
            if pen < best_pen:
                best, best_pen = ids, pen
        return list(best)


def _novelty_penalty(ids: list[str], used) -> float:
    if used is None:
        return 0.0
    key = "|".join(sorted(ids))
    return 2.0 * used.triples.get(key, 0) + 0.35 * sum(used.legends.get(i, 0) for i in ids)


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


# ------------------------------------------------------------------ the builders
class Explorer(BuilderStrategy):
    """Explores: draws a random target shape — each feature sampled inside the range the legal
    pool allows — and builds toward it, so a batch of Explorers spreads over the space of
    possible decks. This is what a league runs before any archetype has been learned, and one
    builder in four keeps exploring afterwards so new kinds of deck can still appear."""

    name = "explorer"
    generated = "explorer"
    margin = 0.1     # stay away from the unreachable corners of the range
    focus = 5        # features this build really pushes on; the rest are held loosely
    loose = 0.15     # weight of a non-focus feature in the distance

    def target_for(self, ctx: BuildCtx, rng: Pcg32) -> tuple[dict[str, float], dict[str, float]]:
        """Every feature uniform inside the pool's range, except that the features which cannot
        disagree are drawn together: one "cost tilt" sets average cost, the cheap share and the
        expensive share, and the three type shares are one random composition that sums to 1.
        Seventeen independent targets mostly contradict each other and a least-squares fill
        would settle in the middle of everything, so each build picks ``focus`` features to
        push on at full weight and holds the others loosely."""
        from cptcg.deck.archetypes import FILL_FEATURES, pool_ranges
        lo, hi = pool_ranges(ctx.pool, ctx.ltags)
        m = self.margin
        u = {k: m + (1 - 2 * m) * rng.below(1000) / 1000 for k in lo}
        tilt = u["mean_cost"]
        u["top_share"], u["cheap_share"] = tilt, 1.0 - tilt
        mix = [rng.below(1000) + 1 for _ in range(3)]
        tot = sum(mix)
        groups = {"mean_cost": "cost", "cheap_share": "cost", "top_share": "cost",
                  "unit_share": "types", "program_share": "types", "gear_share": "types"}
        names = sorted({groups.get(k, k) for k in FILL_FEATURES})
        chosen: set[str] = set()
        while len(chosen) < min(self.focus, len(names)):
            chosen.add(names[rng.below(len(names))])
        target, scale = {}, {}
        for k in lo:
            span = hi[k] - lo[k]
            target[k] = lo[k] + u[k] * span
            weight = 1.0 if groups.get(k, k) in chosen else self.loose
            scale[k] = max(span, 1e-6) / weight
        for k, w in zip(("unit_share", "program_share", "gear_share"), mix):
            target[k] = min(hi[k], max(lo[k], w / tot))
        return target, scale


class Learned(BuilderStrategy):
    """Builds toward an archetype the store learned from play: the card score is its learned
    value plus how much it moves the deck toward the archetype's centre, and the Legends come
    from the archetype's own members, weighted by how those decks did."""

    generated = "learned"
    mutate_rate = 0.2    # one Legend of a member triple swapped for a fresh one, so nearby triples get tried

    def __init__(self, archetype, store) -> None:
        self.archetype = archetype
        self.store = store
        self.name = archetype.id

    def describe(self) -> str:
        return self.archetype.description

    def target_for(self, ctx: BuildCtx, rng: Pcg32) -> tuple[dict[str, float], dict[str, float]]:
        from cptcg.deck.archetypes import FILL_FEATURES
        return {k: self.archetype.centroid.get(k, 0.0) for k in FILL_FEATURES}, self.store.scale()

    def meta(self, ctx: BuildCtx) -> dict:
        return {"generated": self.generated, "archetype": self.archetype.name, "archetype_id": self.archetype.id,
                "context": ctx.context}

    def choose_legends(self, reg: Registry, rng: Pcg32, used=None, samples: int = 6) -> list[str]:
        """A member triple, drawn with probability proportional to its win rate (Laplace-smoothed)
        and divided by how often the batch has used it; sometimes with one Legend swapped."""
        records: dict[str, dict] = {}
        for d in self.store.members(self.archetype):
            key = "|".join(sorted(d.legends))
            r = records.setdefault(key, {"legends": list(d.legends), "wins": 0, "games": 0})
            r["wins"] += d.wins
            r["games"] += d.games
        if not records:
            return super().choose_legends(reg, rng, used, samples)
        keys = sorted(records)
        weights = []
        for k in keys:
            r = records[k]
            w = (r["wins"] + 1) / (r["games"] + 2)
            weights.append(w / (1.0 + _novelty_penalty(r["legends"], used)))
        total = sum(weights)
        pick = rng.below(1_000_000) / 1_000_000 * total
        acc, chosen = 0.0, keys[-1]
        for k, w in zip(keys, weights):
            acc += w
            if acc >= pick:
                chosen = k
                break
        legends = list(records[chosen]["legends"])
        if rng.below(1000) < self.mutate_rate * 1000:
            legends = _swap_one_legend(reg, legends, rng) or legends
        return legends


def _swap_one_legend(reg: Registry, legends: list[str], rng: Pcg32) -> list[str] | None:
    """One Legend replaced by another (unique names kept) when the pool stays deep enough."""
    from cptcg.deck.builder import usable
    legs = [d for d in usable(reg) if d.type is CardType.LEGEND]
    slot = rng.below(3)
    others = {reg.get(l).name for i, l in enumerate(legends) if i != slot}
    cands = [d for d in legs if d.name not in others and d.id != legends[slot]]
    for _ in range(10):
        new = list(legends)
        new[slot] = rng.choice(cands).id
        if len(legal_pool(reg, new)) >= 20:
            return new
    return None


# ------------------------------------------------------------------ choosing builders
EXPLORER_EVERY = 4       # in an automatic league one builder in four explores


def get_builder(spec, store=None) -> BuilderStrategy:
    """``"explorer"`` (or an ``Explorer``/``Learned`` object) or the id / name of an archetype
    in ``store``."""
    if isinstance(spec, BuilderStrategy):
        return spec
    key = str(spec).strip().lower()
    if key in ("explorer", "exploring", ""):
        return Explorer()
    arch = store.get(key) if store is not None else None
    if arch is None:
        known = ", ".join(a.id for a in store.archetypes) if store is not None and store.archetypes else "none learned yet"
        raise KeyError(f"unknown archetype {spec!r}; choose 'explorer' or one of: {known}")
    return Learned(arch, store)


def builders_for(store, n: int, every: int = EXPLORER_EVERY) -> list[BuilderStrategy]:
    """The automatic line-up of a league: archetypes by win rate, cycled, with every
    ``every``-th builder an Explorer; all Explorers while the store has no clusters."""
    ranked = store.ranked() if store is not None else []
    out: list[BuilderStrategy] = []
    j = 0
    for i in range(n):
        if not ranked or (every and (i + 1) % every == 0):
            out.append(Explorer())
        else:
            out.append(Learned(ranked[j % len(ranked)], store))
            j += 1
    return out


def blurb(text: str, sentences: int = 2) -> str:
    """The first ``sentences`` of a wrapped docstring on one line."""
    flat = " ".join(text.split())
    parts = flat.split(". ")
    out = ". ".join(parts[:sentences])
    return out if out.endswith(".") or len(parts) <= sentences else out + "."


# ------------------------------------------------------------------ describing a deck
def deck_profile(deck: Decklist, reg: Registry) -> dict[str, float]:
    """Shape numbers a report or a test can compare across decks (a subset of
    ``archetypes.fingerprint``, computed the same way)."""
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
