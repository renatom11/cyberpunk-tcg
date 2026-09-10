"""Archetypes learned from play.

An archetype is not a thesis anybody wrote down: it is a cluster of decks that have actually
played in a tournament or league, described by the shape numbers every deck has — average cost,
the share of Units, how many removal effects, how sellable it is, and so on. Nothing is named in
advance. After every tournament the decks that played are added to a store, the store
re-clusters them (k-means on standardised fingerprints, k chosen by a silhouette-style score),
and every cluster gets a name generated from the two features that set it apart from the rest
("Low-curve swarm", "Removal wall"), a plain-English description, and a pooled win rate — so the
reader can judge whether the group is real and whether it wins.

The whole module is deterministic: the same decks in any insertion order produce the same
clusters and the same names, so a name a reader saw last week still means the same thing.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from cptcg.cards.registry import CardDef, Registry
from cptcg.core.enums import CardType, Color, Keyword
from cptcg.core.rng import Pcg32
from cptcg.deck.decklist import Decklist
from cptcg.deck.strategies import features

DEFAULT_PATH = Path("out") / "archetypes.json"
MIN_DECKS = 8            # below this the store has no clusters and every deck is "exploring"
MAX_DECKS = 240          # the store keeps the most recent decks; k-means must stay quick in a browser
MAX_K = 6
COLOUR_WEIGHT = 0.5      # the Legend colours count half as much as a play-style feature when clustering
DECK_SIZE = 40

UNIT, PROGRAM, GEAR = CardType.UNIT, CardType.PROGRAM, CardType.GEAR
COLOURS = tuple(c.name.lower() for c in Color)

# ------------------------------------------------------------------ the vector
# Per-card contributions, in this order. A deck's fingerprint is a function of the totals.
_MEAN = ("mean_cost", "sell_share", "unit_share", "program_share", "gear_share", "cheap_share", "top_share")
_COUNT = ("blockers", "quick", "removal", "gig_cards", "haste", "economy", "steal", "draw")
_VEC = _MEAN + ("unit_power",) + _COUNT + ("tag_overlap",)
FILL_FEATURES = _MEAN + ("mean_unit_power",) + _COUNT + ("tag_overlap",)   # what a builder can steer
FEATURES = FILL_FEATURES + tuple(f"colour_{c}" for c in COLOURS)          # what the store clusters on
_I = {k: i for i, k in enumerate(_VEC)}
_IDX_UNIT, _IDX_POWER = _I["unit_share"], _I["unit_power"]
_KIND = ({k: "mean" for k in _MEAN} | {"mean_unit_power": "power"} | {k: "count" for k in _COUNT}
         | {"tag_overlap": "mean"})
_VEC_OF = {f: _I[f] for f in FILL_FEATURES if f != "mean_unit_power"} | {"mean_unit_power": _IDX_POWER}


def card_vector(d: CardDef, ltags: frozenset) -> tuple:
    """What one copy of a card adds to a deck's totals."""
    f = features(d)
    cost = d.cost or 1
    return (cost, 1.0 if d.sell_tag else 0.0, 1.0 if d.type is UNIT else 0.0, 1.0 if d.type is PROGRAM else 0.0,
            1.0 if d.type is GEAR else 0.0, 1.0 if cost <= 2 else 0.0, 1.0 if cost >= 5 else 0.0,
            float(d.power or 0) if d.type is UNIT else 0.0,
            1.0 if Keyword.BLOCKER in d.keywords else 0.0, 1.0 if Keyword.QUICK in d.keywords else 0.0,
            float(f.removal), 1.0 if f.gig else 0.0, float(f.haste), float(f.eddies + f.call + f.discount),
            float(f.gig_steal), float(f.draw), float(len(d.tags & ltags)))


def project(totals: list, n: int, size: int = DECK_SIZE) -> dict[str, float]:
    """The fingerprint of a deck with these totals over ``n`` cards, counts scaled to a deck of
    ``size`` cards (so a half-built deck is compared to a target at full size)."""
    if n <= 0:
        return {k: 0.0 for k in FILL_FEATURES}
    units = totals[_IDX_UNIT]
    out = {}
    for k in FILL_FEATURES:
        kind = _KIND[k]
        if kind == "mean":
            out[k] = totals[_VEC_OF[k]] / n
        elif kind == "count":
            out[k] = totals[_VEC_OF[k]] * size / n
        else:
            out[k] = totals[_IDX_POWER] / units if units else 0.0
    return out


def legend_tags(reg: Registry, legends) -> frozenset:
    return frozenset().union(*(reg.get(l).tags for l in legends)) if legends else frozenset()


def fingerprint(reg: Registry, deck: Decklist) -> dict[str, float]:
    """The numbers that describe a deck: average cost, type and cost-band shares, sell share,
    Unit power, counts of blockers / Quick cards / removal / Gig cards / haste / economy /
    extra-steal / draw effects, tag overlap with the Legends, and one 0/1 flag per Legend
    colour. Raises KeyError for a card the registry does not know."""
    ltags = legend_tags(reg, deck.legends)
    totals = [0.0] * len(_VEC)
    for cid in deck.main:
        for i, v in enumerate(card_vector(reg.get(cid), ltags)):
            totals[i] += v
    fp = project(totals, len(deck.main), len(deck.main))
    colours = {reg.get(l).color.name.lower() for l in deck.legends}
    for c in COLOURS:
        fp[f"colour_{c}"] = 1.0 if c in colours else 0.0
    return fp


def pool_ranges(pool: list[CardDef], ltags: frozenset, size: int = DECK_SIZE) -> tuple[dict, dict]:
    """The lowest and highest value each steerable feature can reach with ``size`` cards from
    ``pool`` (three copies each): the space an Explorer draws its targets from."""
    vecs = [card_vector(d, ltags) for d in pool]
    lo, hi = {}, {}
    for k in FILL_FEATURES:
        i = _VEC_OF[k]
        if k == "mean_unit_power":
            powers = [v[i] for v in vecs if v[_IDX_UNIT]]
            lo[k], hi[k] = (min(powers), max(powers)) if powers else (0.0, 0.0)
            continue
        copies = sorted(v[i] for v in vecs for _ in range(3))
        take = min(size, len(copies))
        low, high = copies[:take], copies[-take:]
        if _KIND[k] == "count":
            lo[k], hi[k] = sum(low), sum(high)
        else:
            lo[k], hi[k] = sum(low) / take, sum(high) / take
    return lo, hi


# ------------------------------------------------------------------ words
_COUNT_WORDS = (("blockers", "blocker"), ("removal", "removal effect"), ("gig_cards", "Gig-manipulation card"),
                ("haste", "haste effect"), ("economy", "economy effect"), ("steal", "extra-steal effect"),
                ("draw", "draw effect"), ("quick", "Quick card"))


def _cost_word(mean_cost: float) -> str:
    if mean_cost < 2.8:
        return "cheap curve"
    if mean_cost < 3.6:
        return "middling curve"
    return "top-heavy curve"


def describe_fingerprint(fp: dict | None) -> str:
    """One line a reader can picture: ``cheap curve (average cost 2.4), 65% Units, 42% sellable,
    9 removal effects, 6 Gig-manipulation cards``. Works for a deck or a cluster centre."""
    if not fp:
        return ""
    parts = [f"{_cost_word(fp['mean_cost'])} (average cost {fp['mean_cost']:.1f})",
             f"{100 * fp.get('unit_share', 0):.0f}% Units", f"{100 * fp.get('sell_share', 0):.0f}% sellable"]
    for key, word in _COUNT_WORDS:
        v = int(round(fp.get(key, 0) or 0))
        if v:
            parts.append(f"{v} {word}{'s' if v != 1 else ''}")
    return ", ".join(parts)


# feature -> ((adjective, noun) when the cluster is high on it, (adjective, noun) when low)
NAMING = {
    "mean_cost": (("Top-heavy", "haymakers"), ("Cheap", "curve")),
    "cheap_share": (("Low-curve", "rush"), ("Slow", "midrange")),
    "top_share": (("Big-money", "bombs"), ("Lean", "tempo")),
    "sell_share": (("Sell-everything", "economy"), ("All-in", "board")),
    "unit_share": (("Unit-heavy", "swarm"), ("Spell-heavy", "toolbox")),
    "program_share": (("Program", "quickhacks"), ("Hardware", "muscle")),
    "gear_share": (("Chromed-up", "gear"), ("Bare-knuckle", "bodies")),
    "mean_unit_power": (("Heavy-hitter", "muscle"), ("Utility", "chaff")),
    "blockers": (("Blocker", "wall"), ("No-blocker", "race")),
    "quick": (("Reactive", "tricks"), ("Straightforward", "plan")),
    "removal": (("Removal", "control"), ("Hands-off", "race")),
    "gig_cards": (("Gig-value", "dice"), ("No-dice", "beatdown")),
    "haste": (("Haste", "rush"), ("Patient", "grind")),
    "economy": (("Eddies", "engine"), ("Broke", "beatdown")),
    "tag_overlap": (("Tribal", "synergy"), ("Goodstuff", "pile")),
    "steal": (("Gig-steal", "heist"), ("Single-steal", "beatdown")),
    "draw": (("Card-draw", "value"), ("Draw-light", "tempo")),
}
DISTINCT_Z = 0.3         # a feature names a cluster only when its centre is this many SDs from the mean


def _inherited_name(members: set[str], previous: list[tuple[str, set[str]]], taken: set[str]) -> str | None:
    """The previous name of the cluster this one continues — the one sharing a majority of
    members both ways — so a name a reader followed across generations keeps meaning the same
    group. The description always prints the group's current numbers."""
    best = None
    for name, old in previous:
        if name in taken or not old:
            continue
        shared = len(members & old)
        if 2 * shared >= len(members) and 2 * shared >= len(old) and (best is None or shared > best[0]):
            best = (shared, name)
    return best[1] if best else None


def slug(text: str) -> str:
    s = "".join(ch if ch.isalnum() else "-" for ch in text.strip().lower()).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    return s or "archetype"


def name_from_z(z: dict[str, float], taken: set[str] | None = None) -> str:
    """A name from the two most distinctive standardised features: the first gives the
    adjective, the second the noun ("Low-curve swarm"). Ties break in feature order; a name
    already ``taken`` moves on to the next noun, then gains a numeral."""
    taken = taken or set()
    ranked = sorted((k for k in NAMING if k in z), key=lambda k: (-abs(z[k]), FILL_FEATURES.index(k)))
    words = [(NAMING[k][0] if z[k] > 0 else NAMING[k][1]) for k in ranked if abs(z[k]) >= DISTINCT_Z]
    if not words:
        base = "Balanced midrange"
    else:
        adj = words[0][0]
        nouns = [w[1] for w in words[1:] if w[1].lower() != adj.lower()] or ["decks"]
        base = next((f"{adj} {noun}" for noun in nouns if f"{adj} {noun}" not in taken), f"{adj} {nouns[0]}")
    name, k = base, 2
    while name in taken:
        name, k = f"{base} {k}", k + 1
    return name


# ------------------------------------------------------------------ the store
@dataclass
class SeenDeck:
    """One deck that has played, with its record."""
    signature: str
    name: str
    legends: list[str]
    main: dict[str, int]
    fingerprint: dict[str, float]
    games: int = 0
    wins: int = 0
    bt: float = 1.0
    source: str = ""
    generation: int = 0
    seen: int = 0                      # insertion counter, so the oldest can be dropped
    archetype: str | None = None       # id assigned at the last refit

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.5

    def to_json(self) -> dict:
        return {"signature": self.signature, "name": self.name, "legends": list(self.legends), "main": dict(self.main),
                "fingerprint": {k: round(float(v), 4) for k, v in self.fingerprint.items()}, "games": self.games,
                "wins": self.wins, "bt": round(self.bt, 4), "source": self.source, "generation": self.generation,
                "seen": self.seen, "archetype": self.archetype}

    @classmethod
    def from_json(cls, raw: dict) -> "SeenDeck":
        return cls(raw["signature"], raw.get("name", ""), list(raw.get("legends", [])), dict(raw.get("main", {})),
                   {k: float(v) for k, v in raw.get("fingerprint", {}).items()}, int(raw.get("games", 0)),
                   int(raw.get("wins", 0)), float(raw.get("bt", 1.0)), raw.get("source", ""),
                   int(raw.get("generation", 0)), int(raw.get("seen", 0)), raw.get("archetype"))


@dataclass
class Archetype:
    id: str
    name: str
    centroid: dict[str, float]         # in the fingerprint's own units, so it reads like a deck
    members: list[str]                 # deck signatures
    games: int = 0
    wins: int = 0
    bt: float = 1.0
    description: str = ""

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.5

    def to_json(self) -> dict:
        return {"id": self.id, "name": self.name, "centroid": {k: round(float(v), 4) for k, v in self.centroid.items()},
                "members": list(self.members), "decks": len(self.members), "games": self.games, "wins": self.wins,
                "win_rate": round(self.win_rate, 4), "bt": round(self.bt, 4), "description": self.description}

    @classmethod
    def from_json(cls, raw: dict) -> "Archetype":
        return cls(raw["id"], raw["name"], {k: float(v) for k, v in raw.get("centroid", {}).items()},
                   list(raw.get("members", [])), int(raw.get("games", 0)), int(raw.get("wins", 0)),
                   float(raw.get("bt", 1.0)), raw.get("description", ""))


def deck_signature(deck: Decklist) -> str:
    counts = ",".join(f"{cid}x{n}" for cid, n in sorted(deck.counts().items()))
    return "|".join(sorted(deck.legends)) + "::" + counts


@dataclass
class ArchetypeStore:
    """Every deck that has finished a tournament, the clusters found among them, and the
    scale (mean and standard deviation per feature) the clusters were fitted in."""
    path: Path | None = None
    reg: Registry | None = None
    decks: list[SeenDeck] = field(default_factory=list)
    archetypes: list[Archetype] = field(default_factory=list)
    mean: dict[str, float] = field(default_factory=dict)
    std: dict[str, float] = field(default_factory=dict)
    tournaments: int = 0
    seen: int = 0

    # ---------------------------------------------------------------- persistence
    @classmethod
    def load(cls, path: str | Path | None = DEFAULT_PATH, reg: Registry | None = None) -> "ArchetypeStore":
        st = cls(Path(path) if path else None, reg)
        if st.path and st.path.exists():
            with open(st.path, encoding="utf-8") as f:
                raw = json.load(f)
            st.decks = [SeenDeck.from_json(d) for d in raw.get("decks", [])]
            st.archetypes = [Archetype.from_json(a) for a in raw.get("archetypes", [])]
            st.mean = {k: float(v) for k, v in raw.get("scale", {}).get("mean", {}).items()}
            st.std = {k: float(v) for k, v in raw.get("scale", {}).get("std", {}).items()}
            st.tournaments = int(raw.get("tournaments", 0))
            st.seen = max([d.seen for d in st.decks] + [int(raw.get("seen", 0))])
        return st

    def to_json(self) -> dict:
        return {"version": 1, "min_decks": MIN_DECKS, "tournaments": self.tournaments, "seen": self.seen,
                "decks": [d.to_json() for d in self.decks],
                "archetypes": [a.to_json() for a in self.archetypes],
                "scale": {"mean": {k: round(v, 5) for k, v in self.mean.items()},
                          "std": {k: round(v, 5) for k, v in self.std.items()}}}

    def save(self, path: str | Path | None = None) -> None:
        p = Path(path) if path else self.path
        if p is None:
            raise ValueError("no path to save the archetype store to")
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=1)
            f.write("\n")

    def registry(self) -> Registry:
        if self.reg is None:
            from cptcg.cards.registry import load_default
            self.reg = load_default()
        return self.reg

    # ---------------------------------------------------------------- recording
    def add(self, deck: Decklist, fp: dict[str, float] | None = None, games: int = 0, wins: int = 0, bt: float = 1.0,
            source: str = "", generation: int = 0) -> SeenDeck:
        """Record a deck's result; a deck seen before (same Legends and counts) pools its games
        and averages its strength by games. Oldest decks fall out beyond ``MAX_DECKS``."""
        fp = {k: float(v) for k, v in (fp or fingerprint(self.registry(), deck)).items()}
        sig = deck_signature(deck)
        for d in self.decks:
            if d.signature == sig:
                tot = d.games + games
                d.bt = (d.bt * d.games + bt * games) / tot if tot else bt
                d.games, d.wins = tot, d.wins + wins
                d.name, d.source, d.generation = deck.name, source or d.source, generation or d.generation
                d.fingerprint = fp
                return d
        self.seen += 1
        rec = SeenDeck(sig, deck.name, list(deck.legends), deck.counts(), fp, games, wins, bt, source, generation,
                       self.seen)
        self.decks.append(rec)
        if len(self.decks) > MAX_DECKS:
            self.decks.sort(key=lambda d: d.seen)
            del self.decks[: len(self.decks) - MAX_DECKS]
        return rec

    def update_from_tournament(self, t, source: str = "", generation: int = 0) -> int:
        """Every deck of a finished tournament, with its field record and strength."""
        reg = self.registry()
        bt = t.bt()
        rates = t.field_rates()
        n = 0
        for i, deck in enumerate(t.decks):
            try:
                fp = fingerprint(reg, deck)
            except KeyError:
                continue
            k, g = rates[i]
            self.add(deck, fp, g, k, bt[i], source, generation)
            n += 1
        self.tournaments += 1
        return n

    # ---------------------------------------------------------------- geometry
    def _fit_scale(self) -> None:
        n = len(self.decks)
        self.mean, self.std = {}, {}
        for k in FEATURES:
            vals = [d.fingerprint.get(k, 0.0) for d in self.decks]
            m = sum(vals) / n
            var = sum((v - m) ** 2 for v in vals) / n
            self.mean[k], self.std[k] = m, math.sqrt(var)

    def standardise(self, fp: dict[str, float]) -> list[float]:
        """The fingerprint in the store's units: (value − mean) / SD per feature, constant
        features dropped to 0, Legend colours down-weighted."""
        out = []
        for k in FEATURES:
            sd = self.std.get(k, 0.0)
            z = (fp.get(k, 0.0) - self.mean.get(k, 0.0)) / sd if sd > 1e-9 else 0.0
            out.append(z * COLOUR_WEIGHT if k.startswith("colour_") else z)
        return out

    def distance(self, fp: dict[str, float], arch: Archetype) -> float:
        a, b = self.standardise(fp), self.standardise(arch.centroid)
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    def scale(self) -> dict[str, float]:
        """One SD per steerable feature (a small floor for constant ones): the unit a builder
        measures its closeness to a centroid in."""
        return {k: max(self.std.get(k, 0.0), 1e-6) for k in FILL_FEATURES}

    # ---------------------------------------------------------------- clustering
    def refit(self, k: int | None = None) -> bool:
        """Re-cluster the stored decks. Returns whether the store now has archetypes (it needs
        at least ``MIN_DECKS`` decks; below that every deck stays "exploring")."""
        self.decks.sort(key=lambda d: d.signature)     # insertion order must not change the result
        if len(self.decks) < MIN_DECKS:
            self.archetypes = []
            for d in self.decks:
                d.archetype = None
            return False
        self._fit_scale()
        pts = [self.standardise(d.fingerprint) for d in self.decks]
        if k is None:
            best = None
            for kk in range(2, min(MAX_K, len(pts) // 4) + 1):
                labels, centres, inertia = _kmeans(pts, kk)
                score = _silhouette(pts, labels, centres)
                if best is None or score > best[0] + 1e-12:
                    best = (score, kk, labels, centres)
            _, k, labels, centres = best
        else:
            labels, centres, _ = _kmeans(pts, max(1, min(k, len(pts))))
        groups: list[list[int]] = [[] for _ in range(len(centres))]
        for i, lab in enumerate(labels):
            groups[lab].append(i)
        previous = [(a.name, set(a.members)) for a in self.archetypes]
        # Name the biggest cluster first so a stable name goes to the group it has always meant.
        order = sorted(range(len(groups)), key=lambda g: (-len(groups[g]), g))
        taken: set[str] = set()
        out: list[Archetype] = []
        for g in order:
            members = groups[g]
            if not members:
                continue
            centroid = {kf: sum(self.decks[i].fingerprint.get(kf, 0.0) for i in members) / len(members) for kf in FEATURES}
            z = {kf: (centroid[kf] - self.mean[kf]) / self.std[kf] if self.std[kf] > 1e-9 else 0.0 for kf in FILL_FEATURES}
            name = _inherited_name({self.decks[i].signature for i in members}, previous, taken) or name_from_z(z, taken)
            taken.add(name)
            games = sum(self.decks[i].games for i in members)
            wins = sum(self.decks[i].wins for i in members)
            bt = sum(self.decks[i].bt for i in members) / len(members)
            arch = Archetype(slug(name), name, centroid, [self.decks[i].signature for i in members], games, wins, bt)
            arch.description = self.describe(arch, z)
            out.append(arch)
            for i in members:
                self.decks[i].archetype = arch.id
        self.archetypes = out
        return True

    def describe(self, arch: Archetype, z: dict[str, float] | None = None) -> str:
        """Plain words: what sets the group apart, what its decks look like, how it has done."""
        n = len(arch.members)
        colours = [c for c in COLOURS if arch.centroid.get(f"colour_{c}", 0.0) >= 0.6]
        parts = [f"{n} deck{'s' if n != 1 else ''} in this group; typically {describe_fingerprint(arch.centroid)}"]
        if colours:
            parts.append("mostly " + "/".join(c.title() for c in colours) + " Legends")
        if arch.games:
            parts.append(f"won {100 * arch.win_rate:.0f}% of {arch.games} games, average strength {arch.bt:.2f}")
        else:
            parts.append("no games recorded yet")
        return "; ".join(parts) + "."

    # ---------------------------------------------------------------- queries
    def ranked(self) -> list[Archetype]:
        """Archetypes by pooled win rate (ties: more games, then name)."""
        return sorted(self.archetypes, key=lambda a: (-a.win_rate, -a.games, a.name))

    def get(self, key: str) -> Archetype | None:
        """By id, name (case-insensitive) or slug of the name."""
        k = (key or "").strip().lower()
        for a in self.archetypes:
            if a.id == k or a.name.lower() == k or slug(k) == a.id:
                return a
        return None

    def members(self, arch: Archetype) -> list[SeenDeck]:
        want = set(arch.members)
        return [d for d in self.decks if d.signature in want]

    def assign(self, fp: dict[str, float]) -> str | None:
        """The nearest archetype id for a fingerprint, or None while the store has no clusters."""
        if not self.archetypes:
            return None
        return min(self.archetypes, key=lambda a: (self.distance(fp, a), a.id)).id

    def label(self, deck: Decklist) -> str | None:
        """``assign`` for a deck (None for a deck with an unknown card)."""
        try:
            return self.assign(fingerprint(self.registry(), deck))
        except KeyError:
            return None

    def summary(self) -> str:
        if not self.archetypes:
            need = max(0, MIN_DECKS - len(self.decks))
            return (f"{len(self.decks)} decks recorded, no archetypes yet"
                    + (f" ({need} more deck{'s' if need != 1 else ''} needed)" if need else ""))
        return f"{len(self.decks)} decks in {len(self.archetypes)} archetypes: " + ", ".join(
            f"{a.name} ({100 * a.win_rate:.0f}% of {a.games})" for a in self.ranked())


# ------------------------------------------------------------------ k-means
def _sqdist(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _kmeans(pts: list[list[float]], k: int, seed: int = 0, iters: int = 50) -> tuple[list[int], list[list[float]], float]:
    """Seeded k-means++ then Lloyd iterations; an emptied cluster is re-seeded with the point
    farthest from its centre. Returns (labels, centres, inertia)."""
    rng = Pcg32(seed, seq=77)
    n, dims = len(pts), len(pts[0])
    centres = [list(pts[rng.below(n)])]
    d2 = [_sqdist(p, centres[0]) for p in pts]
    while len(centres) < k:
        total = sum(d2)
        if total <= 1e-12:
            centres.append(list(pts[len(centres) % n]))
        else:
            r = rng.below(1_000_000) / 1_000_000 * total
            acc, pick = 0.0, n - 1
            for i, w in enumerate(d2):
                acc += w
                if acc >= r:
                    pick = i
                    break
            centres.append(list(pts[pick]))
        d2 = [min(x, _sqdist(p, centres[-1])) for x, p in zip(d2, pts)]
    labels = [-1] * n
    for _ in range(iters):
        new = [min(range(k), key=lambda c, p=p: (_sqdist(p, centres[c]), c)) for p in pts]
        if new == labels:
            break
        labels = new
        for c in range(k):
            members = [pts[i] for i in range(n) if labels[i] == c]
            if members:
                centres[c] = [sum(m[j] for m in members) / len(members) for j in range(dims)]
            else:
                far = max(range(n), key=lambda i: (_sqdist(pts[i], centres[labels[i]]), -i))
                centres[c] = list(pts[far])
                labels[far] = c
    inertia = sum(_sqdist(p, centres[c]) for p, c in zip(pts, labels))
    return labels, centres, inertia


def _silhouette(pts: list[list[float]], labels: list[int], centres: list[list[float]]) -> float:
    """Simplified silhouette: per point (b − a) / max(a, b) with a = distance to its own centre
    and b = distance to the nearest other centre; averaged. Higher = cleaner clusters."""
    if len(centres) < 2:
        return -1.0
    total = 0.0
    for p, lab in zip(pts, labels):
        a = math.sqrt(_sqdist(p, centres[lab]))
        b = min(math.sqrt(_sqdist(p, c)) for i, c in enumerate(centres) if i != lab)
        m = max(a, b)
        total += (b - a) / m if m > 1e-12 else 0.0
    return total / len(pts)
