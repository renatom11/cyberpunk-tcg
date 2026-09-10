"""Archetypes learned from play.

An archetype is not a thesis anybody wrote down: it is a cluster of decks that have actually
played in a tournament or league, described by the shape numbers every deck has — average cost,
the share of Units, how many removal effects, how sellable it is, and so on. Nothing is named in
advance. After every tournament the decks that played are added to a store, the store
re-clusters them (k-means on standardised fingerprints, k chosen by a silhouette-style score),
and every cluster gets a name generated from the two features that set it apart from the rest
("Low-curve swarm", "Removal wall"), a plain-English description, and a pooled win rate — so the
reader can judge whether the group is real and whether it wins.

Honesty rules of the clustering: a group needs at least ``MIN_MEMBERS`` decks (an outlier is
never an archetype on its own); one-card variants of the same deck (same Legends, nearly the
same list) form a *lineage* that counts as one deck; and when the decks do not split cleanly
(the separation score is below ``SEPARATION_FLOOR``) the store keeps one group rather than
inventing two. Every archetype carries its separation score so a reader can see how provisional
it is.

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
MIN_DECKS = 8            # distinct lineages needed before the store clusters; below it every deck is "exploring"
MIN_MEMBERS = 3          # a cluster smaller than this is merged into its nearest neighbour
MAX_DECKS = 240          # the store keeps the most recent decks; k-means must stay quick in a browser
MAX_K = 6
COLOUR_WEIGHT = 0.5      # the Legend colours count half as much as a play-style feature when clustering
SEPARATION_FLOOR = 0.2   # below this simplified-silhouette score a split into groups is not believed
NOISE_MARGIN = 0.05      # ... and it must beat, by this much, what k-means finds in shapeless random decks
NOISE_DRAWS = 3          # random reference sets per k (seeded, so the fit stays deterministic)
MIN_CENTRE_GAP = 1.0     # standardised distance the two nearest group centres must keep
LINEAGE_JACCARD = 0.9    # same Legends and this much card overlap = the same deck's lineage
DECK_SIZE = 40
# sell_share is 1 − unit_share in this card set (one Unit in 73 has a sell tag, every Program
# and Gear does), so it is kept in the fingerprint but neither clustered on nor used for names.
CLUSTER_SKIP = frozenset({"sell_share"})

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
    """One line a reader can picture: ``cheap curve (average cost 2.4), 65% Units, 25% Programs,
    10% Gear, 9 removal effects, 6 Gig-manipulation cards``. Works for a deck or a cluster
    centre. The sellable share is not printed: in this card set every non-Unit card sells and
    (one card apart) no Unit does, so it would repeat the Unit share."""
    if not fp:
        return ""
    parts = [f"{_cost_word(fp['mean_cost'])} (average cost {fp['mean_cost']:.1f})",
             f"{100 * fp.get('unit_share', 0):.0f}% Units"]
    if "program_share" in fp or "gear_share" in fp:
        parts += [f"{100 * fp.get('program_share', 0):.0f}% Programs", f"{100 * fp.get('gear_share', 0):.0f}% Gear"]
    for key, word in _COUNT_WORDS:
        v = int(round(fp.get(key, 0) or 0))
        if v:
            parts.append(f"{v} {word}{'s' if v != 1 else ''}")
    return ", ".join(parts)


# feature -> ((adjective, noun) when the cluster is high on it, (adjective, noun) when low).
# The low side says what such a deck *does* (it races, it plays to the board) rather than what
# it lacks, and the adjectives are unique so a name can be traced back to its feature.
NAMING = {
    "mean_cost": (("Top-heavy", "haymakers"), ("Cheap", "curve")),
    "cheap_share": (("Low-curve", "rush"), ("Slow", "midrange")),
    "top_share": (("Big-money", "bombs"), ("Lean", "tempo")),
    "unit_share": (("Unit-heavy", "swarm"), ("Spell-heavy", "toolbox")),
    "program_share": (("Program", "quickhacks"), ("Hardware", "muscle")),
    "gear_share": (("Chromed-up", "gear"), ("Bare-knuckle", "bodies")),
    "mean_unit_power": (("Heavy-hitter", "muscle"), ("Utility", "bodies")),
    "blockers": (("Blocker", "wall"), ("No-blocker", "race")),
    "quick": (("Reactive", "tricks"), ("Straightforward", "plan")),
    "removal": (("Removal", "control"), ("Racing", "tempo")),
    "gig_cards": (("Gig-value", "dice"), ("Straight-up", "beatdown")),
    "haste": (("Haste", "rush"), ("Patient", "grind")),
    "economy": (("Eddies", "engine"), ("Board-first", "beatdown")),
    "tag_overlap": (("Tribal", "synergy"), ("Goodstuff", "pile")),
    "steal": (("Gig-steal", "heist"), ("Steady", "beatdown")),
    "draw": (("Card-draw", "value"), ("Draw-light", "tempo")),
}
DISTINCT_Z = 0.3         # a feature names a cluster only when its centre is this many SDs from the mean
NAME_RANK = 3            # a kept name's features must still rank among the top this many


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


def _distinct(z: dict[str, float]) -> list[str]:
    """The naming features by distinctiveness (|z| descending, ties in feature order), keeping
    only those at least ``DISTINCT_Z`` standard deviations from the mean."""
    ranked = sorted((k for k in NAMING if k in z), key=lambda k: (-abs(z[k]), FILL_FEATURES.index(k)))
    return [k for k in ranked if abs(z[k]) >= DISTINCT_Z]


def _word_clash(adj: str, noun: str) -> bool:
    """``Low-curve curve``: the noun repeats a word of the adjective."""
    return noun.lower() in adj.lower().replace("-", " ").split()


def name_from_z(z: dict[str, float], taken: set[str] | None = None) -> str:
    """A name from the two most distinctive standardised features: the first gives the
    adjective, the second the noun ("Low-curve swarm"). Ties break in feature order; when the
    top two are nearly tied the feature the group is *high* on gives the adjective; a noun that
    repeats a word of the adjective is skipped; a name already ``taken`` moves on to the next
    noun, then gains a numeral."""
    taken = taken or set()
    feats = _distinct(z)
    if len(feats) >= 2 and z[feats[0]] < 0 < z[feats[1]] and abs(z[feats[0]]) - abs(z[feats[1]]) < 0.1:
        feats[0], feats[1] = feats[1], feats[0]
    words = [(NAMING[k][0] if z[k] > 0 else NAMING[k][1]) for k in feats]
    if not words:
        base = "Balanced midrange"
    else:
        adj = words[0][0]
        nouns = [w[1] for w in words[1:] if not _word_clash(adj, w[1])] or ["decks"]
        base = next((f"{adj} {noun}" for noun in nouns if f"{adj} {noun}" not in taken), f"{adj} {nouns[0]}")
    name, k = base, 2
    while name in taken:
        name, k = f"{base} {k}", k + 1
    return name


def name_still_fits(name: str, z: dict[str, float]) -> bool:
    """Whether a name's two words still describe a group: the adjective's feature and a
    feature giving the noun must both be distinctive (right side of the mean) and rank among
    the top ``NAME_RANK``. "Balanced midrange" fits while nothing is distinctive."""
    if name == "Balanced midrange":
        return not _distinct(z)
    base = name.rsplit(" ", 1)
    if len(base) != 2:
        return False
    adj, noun = base[0], base[1].rstrip("0123456789").strip()
    top = _distinct(z)[:NAME_RANK]
    adj_feat = next((k for k in top if NAMING[k][0 if z[k] > 0 else 1][0] == adj), None)
    if adj_feat is None:
        return False
    return any(NAMING[k][0 if z[k] > 0 else 1][1] == noun for k in top if k != adj_feat)


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
    separation: float = 0.0            # mean silhouette of the members: how cleanly the group stands apart
    lineages: int = 0                  # distinct decks (one-card variants pooled)
    aliases: list[str] = field(default_factory=list)      # earlier names of this same group
    previous_ids: list[str] = field(default_factory=list)  # ids those names had

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.5

    @property
    def smoothed_rate(self) -> float:
        """The win rate shrunk toward 50% by 20 virtual games, so a handful of games cannot
        outrank hundreds when archetypes are ranked."""
        return (self.wins + 10) / (self.games + 20)

    @property
    def provisional(self) -> bool:
        return len(self.members) < 5 or self.separation < 0.25

    def separation_word(self) -> str:
        """``clearly separated`` (≥ 0.5), ``loosely grouped`` (0.25–0.5) or ``provisional``."""
        if self.separation >= 0.5:
            return "clearly separated"
        if self.separation >= 0.25:
            return "loosely grouped"
        return "provisional"

    def separation_phrase(self) -> str:
        """The separation word as a clause about the other groups."""
        if self.separation >= 0.5:
            return "clearly separated from the other groups"
        if self.separation >= 0.25:
            return "loosely grouped, overlapping the other groups"
        return "provisional, barely apart from the other groups"

    def to_json(self) -> dict:
        return {"id": self.id, "name": self.name, "centroid": {k: round(float(v), 4) for k, v in self.centroid.items()},
                "members": list(self.members), "decks": len(self.members), "lineages": self.lineages,
                "games": self.games, "wins": self.wins, "win_rate": round(self.win_rate, 4),
                "smoothed_rate": round(self.smoothed_rate, 4), "bt": round(self.bt, 4),
                "separation": round(self.separation, 3), "separation_word": self.separation_word(),
                "provisional": self.provisional, "aliases": list(self.aliases), "previous_ids": list(self.previous_ids),
                "description": self.description}

    @classmethod
    def from_json(cls, raw: dict) -> "Archetype":
        return cls(raw["id"], raw["name"], {k: float(v) for k, v in raw.get("centroid", {}).items()},
                   list(raw.get("members", [])), int(raw.get("games", 0)), int(raw.get("wins", 0)),
                   float(raw.get("bt", 1.0)), raw.get("description", ""), float(raw.get("separation", 0.0)),
                   int(raw.get("lineages", 0)), list(raw.get("aliases", [])), list(raw.get("previous_ids", [])))


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
    separation: float = 0.0            # simplified silhouette of the whole fit (0 with one group)
    noise_reference: float = 0.0       # what the same fit scores on shapeless random decks
    renamed: dict[str, str] = field(default_factory=dict)   # old archetype id -> the id it became

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
            st.separation = float(raw.get("separation", 0.0))
            st.noise_reference = float(raw.get("noise_reference", 0.0))
            st.renamed = {str(k): str(v) for k, v in (raw.get("renamed") or {}).items()}
        return st

    def to_json(self) -> dict:
        return {"version": 1, "min_decks": MIN_DECKS, "tournaments": self.tournaments, "seen": self.seen,
                "distinct": self.lineage_count(), "separation": round(self.separation, 3),
                "noise_reference": round(self.noise_reference, 3),
                "decks": [d.to_json() for d in self.decks],
                "archetypes": [a.to_json() for a in self.archetypes],
                "renamed": dict(self.renamed),
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
            z = (fp.get(k, 0.0) - self.mean.get(k, 0.0)) / sd if sd > 1e-9 and k not in CLUSTER_SKIP else 0.0
            out.append(z * COLOUR_WEIGHT if k.startswith("colour_") else z)
        return out

    # ---------------------------------------------------------------- lineages
    def lineages(self) -> list[list[int]]:
        """Indexes of ``self.decks`` grouped by lineage: decks on the same Legends whose card
        counts overlap by at least ``LINEAGE_JACCARD`` (one-card variants of one list). A
        lineage is one deck for the purposes of clustering and of ``MIN_DECKS``."""
        parent = list(range(len(self.decks)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        by_legends: dict[str, list[int]] = {}
        for i, d in enumerate(self.decks):
            by_legends.setdefault("|".join(sorted(d.legends)), []).append(i)
        for idxs in by_legends.values():
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    if _jaccard(self.decks[idxs[a]].main, self.decks[idxs[b]].main) >= LINEAGE_JACCARD:
                        parent[find(idxs[a])] = find(idxs[b])
        groups: dict[int, list[int]] = {}
        for i in range(len(self.decks)):
            groups.setdefault(find(i), []).append(i)
        return sorted(groups.values())

    def lineage_count(self) -> int:
        return len(self.lineages())

    def distance(self, fp: dict[str, float], arch: Archetype) -> float:
        a, b = self.standardise(fp), self.standardise(arch.centroid)
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    def scale(self) -> dict[str, float]:
        """One SD per steerable feature (a small floor for constant ones): the unit a builder
        measures its closeness to a centroid in."""
        return {k: max(self.std.get(k, 0.0), 1e-6) for k in FILL_FEATURES}

    # ---------------------------------------------------------------- clustering
    def refit(self, k: int | None = None) -> bool:
        """Re-cluster the stored decks. Returns whether the store now has archetypes: it needs
        ``MIN_DECKS`` distinct lineages, and below that every deck stays "exploring".

        k = 2 … 6 (never more than a quarter of the lineages) is tried and scored by a
        simplified silhouette; a fit with a group under ``MIN_MEMBERS`` decks has that group
        merged into its nearest neighbour first. The best split is kept only when its score
        reaches ``SEPARATION_FLOOR`` and its two nearest centres are at least ``MIN_CENTRE_GAP``
        apart in standardised units; otherwise the store has one archetype, "Balanced
        midrange", and says so. Decks of one lineage share one unit of weight so a lineage
        cannot manufacture a cluster on its own."""
        self.decks.sort(key=lambda d: d.signature)     # insertion order must not change the result
        lineages = self.lineages()
        if len(lineages) < MIN_DECKS:
            self.archetypes = []
            self.separation = 0.0
            for d in self.decks:
                d.archetype = None
            return False
        self._fit_scale()
        pts = [self.standardise(d.fingerprint) for d in self.decks]
        weights = [1.0] * len(pts)
        for group in lineages:
            for i in group:
                weights[i] = 1.0 / len(group)
        best = None
        self.noise_reference = 0.0
        ks = range(2, min(MAX_K, len(lineages) // 4) + 1) if k is None else [max(1, min(k, len(pts)))]
        scales = [COLOUR_WEIGHT if f.startswith("colour_") else 1.0 for f in FEATURES]
        for kk in ks:
            labels, centres, _ = _kmeans(pts, kk, weights=weights)
            labels, centres = _merge_small(pts, labels, centres, MIN_MEMBERS)
            score = _silhouette(pts, labels, centres, weights)
            # With a dozen decks in twenty dimensions k-means finds "groups" in pure noise too,
            # so a split only counts when it beats what shapeless random decks would score.
            ref = _noise_reference(len(pts), scales, kk) if k is None else -1.0
            gap = min((math.sqrt(_sqdist(a, b)) for i, a in enumerate(centres) for b in centres[i + 1:]), default=0.0)
            ok = k is not None or (len(centres) > 1 and score >= max(SEPARATION_FLOOR, ref + NOISE_MARGIN)
                                   and gap >= MIN_CENTRE_GAP)
            if ok and (best is None or score > best[0] + 1e-12):
                best = (score, labels, centres, ref)
        if best is None:
            labels, centres = [0] * len(pts), [_wmean(pts, weights)]
            score = 0.0
        else:
            score, labels, centres, self.noise_reference = best
        self.separation = score
        groups: list[list[int]] = [[] for _ in range(len(centres))]
        for i, lab in enumerate(labels):
            groups[lab].append(i)
        previous = [(a.name, set(a.members)) for a in self.archetypes]
        old_by_name = {a.name: a for a in self.archetypes}
        # Name the biggest cluster first so a stable name goes to the group it has always meant.
        order = sorted(range(len(groups)), key=lambda g: (-len(groups[g]), g))
        taken: set[str] = set()
        out: list[Archetype] = []
        for g in order:
            members = groups[g]
            if not members:
                continue
            centroid = {kf: sum(self.decks[i].fingerprint.get(kf, 0.0) for i in members) / len(members) for kf in FEATURES}
            z = {kf: (centroid[kf] - self.mean[kf]) / self.std[kf] if self.std[kf] > 1e-9 and kf not in CLUSTER_SKIP else 0.0
                 for kf in FILL_FEATURES}
            if len(groups) == 1:
                z = {kf: 0.0 for kf in FILL_FEATURES}
            inherited = _inherited_name({self.decks[i].signature for i in members}, previous, taken)
            aliases, previous_ids = [], []
            if inherited is not None:
                old = old_by_name[inherited]
                aliases, previous_ids = list(old.aliases), list(old.previous_ids)
                if name_still_fits(inherited, z):
                    name = inherited
                else:
                    # The group continues but its words no longer describe it: rename, and keep
                    # the old name as an alias so readers (and saved decks) can follow it.
                    name = name_from_z(z, taken | {inherited} | set(aliases))
                    aliases.append(inherited)
                    previous_ids.append(old.id)
            else:
                name = name_from_z(z, taken)
            taken.add(name)
            games = sum(self.decks[i].games for i in members)
            wins = sum(self.decks[i].wins for i in members)
            bt = sum(self.decks[i].bt for i in members) / len(members)
            arch = Archetype(slug(name), name, centroid, [self.decks[i].signature for i in members], games, wins, bt,
                             separation=_group_silhouette(pts, labels, centres, g),
                             lineages=sum(1 for group in lineages if any(i in members for i in group)),
                             aliases=aliases, previous_ids=[p for p in previous_ids if p != slug(name)])
            arch.description = self.describe(arch, z)
            out.append(arch)
            for i in members:
                self.decks[i].archetype = arch.id
        ids = {a.id for a in out}
        for a in out:
            for old_id in a.previous_ids:
                self.renamed[old_id] = a.id
        self.renamed = {o: n for o, n in self.renamed.items() if n in ids and o not in ids}
        self.archetypes = out
        return True

    def describe(self, arch: Archetype, z: dict[str, float] | None = None) -> str:
        """Plain words: what sets the group apart, what its decks look like, how it has done."""
        n = len(arch.members)
        colours = [c for c in COLOURS if arch.centroid.get(f"colour_{c}", 0.0) >= 0.6]
        count = f"{n} deck{'s' if n != 1 else ''}"
        if arch.lineages and arch.lineages < n:
            count += f" ({arch.lineages} distinct, the rest one-card variants)"
        if len(self.archetypes) <= 1 and (z is None or not _distinct(z)):
            parts = [f"the only group so far — the decks that have played do not split into kinds yet; {count}, "
                     f"typically {describe_fingerprint(arch.centroid)}"]
        else:
            parts = [f"{count} in this group, {arch.separation_phrase()}"
                     + (" (few decks, so treat it as provisional)" if n < 5 else "")
                     + f"; typically {describe_fingerprint(arch.centroid)}"]
        if colours:
            parts.append("mostly " + "/".join(c.title() for c in colours) + " Legends")
        if arch.games:
            parts.append(f"won {100 * arch.win_rate:.0f}% of {arch.games} games, average strength {arch.bt:.2f}")
        else:
            parts.append("no games recorded yet")
        if arch.aliases:
            parts.append("formerly " + ", ".join(arch.aliases))
        return "; ".join(parts) + "."

    # ---------------------------------------------------------------- queries
    def ranked(self) -> list[Archetype]:
        """Archetypes by smoothed win rate (20 virtual games at 50%, so eight games cannot
        outrank nine hundred; ties: more games, then name)."""
        return sorted(self.archetypes, key=lambda a: (-a.smoothed_rate, -a.games, a.name))

    def get(self, key: str) -> Archetype | None:
        """By id, name (case-insensitive) or slug of the name — including the earlier names and
        ids of a group that has since been renamed."""
        k = (key or "").strip().lower()
        for a in self.archetypes:
            if a.id == k or a.name.lower() == k or slug(k) == a.id:
                return a
        for a in self.archetypes:
            if slug(k) in a.previous_ids or any(al.lower() == k for al in a.aliases):
                return a
        seen = set()
        while k in self.renamed and k not in seen:
            seen.add(k)
            k = self.renamed[k]
            for a in self.archetypes:
                if a.id == k:
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
        distinct = self.lineage_count()
        if not self.archetypes:
            need = max(0, MIN_DECKS - distinct)
            return (f"{len(self.decks)} decks recorded ({distinct} distinct), no archetypes yet"
                    + (f" ({need} more distinct deck{'s' if need != 1 else ''} needed)" if need else ""))
        if len(self.archetypes) == 1:
            a = self.archetypes[0]
            return f"{len(self.decks)} decks ({distinct} distinct) in one group so far, {a.name} ({100 * a.win_rate:.0f}% of {a.games})"
        return (f"{len(self.decks)} decks ({distinct} distinct) in {len(self.archetypes)} archetypes "
                f"(separation {self.separation:.2f}): " + ", ".join(
                    f"{a.name} ({100 * a.win_rate:.0f}% of {a.games}, {a.separation_word()})" for a in self.ranked()))


# ------------------------------------------------------------------ k-means
def _sqdist(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _jaccard(a: dict[str, int], b: dict[str, int]) -> float:
    """Card-count overlap of two lists (Legends ignored)."""
    inter = sum(min(a.get(c, 0), b.get(c, 0)) for c in a)
    union = sum(max(a.get(c, 0), b.get(c, 0)) for c in set(a) | set(b))
    return inter / union if union else 1.0


def _wmean(pts: list[list[float]], weights: list[float]) -> list[float]:
    tot = sum(weights) or 1.0
    return [sum(w * p[j] for p, w in zip(pts, weights)) / tot for j in range(len(pts[0]))]


def _kmeans(pts: list[list[float]], k: int, seed: int = 0, iters: int = 50,
            weights: list[float] | None = None) -> tuple[list[int], list[list[float]], float]:
    """Seeded k-means++ then Lloyd iterations, each point counting ``weights`` (default 1); an
    emptied cluster is re-seeded with the point farthest from its centre. Returns (labels,
    centres, inertia)."""
    rng = Pcg32(seed, seq=77)
    n, dims = len(pts), len(pts[0])
    w = weights or [1.0] * n
    centres = [list(pts[rng.below(n)])]
    d2 = [_sqdist(p, centres[0]) for p in pts]
    while len(centres) < k:
        total = sum(x * wi for x, wi in zip(d2, w))
        if total <= 1e-12:
            centres.append(list(pts[len(centres) % n]))
        else:
            r = rng.below(1_000_000) / 1_000_000 * total
            acc, pick = 0.0, n - 1
            for i, x in enumerate(d2):
                acc += x * w[i]
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
            members = [i for i in range(n) if labels[i] == c]
            if members:
                centres[c] = _wmean([pts[i] for i in members], [w[i] for i in members])
            else:
                far = max(range(n), key=lambda i: (_sqdist(pts[i], centres[labels[i]]), -i))
                centres[c] = list(pts[far])
                labels[far] = c
    inertia = sum(wi * _sqdist(p, centres[c]) for p, c, wi in zip(pts, labels, w))
    return labels, centres, inertia


def _merge_small(pts: list[list[float]], labels: list[int], centres: list[list[float]],
                 min_members: int) -> tuple[list[int], list[list[float]]]:
    """Fold every cluster smaller than ``min_members`` into the nearest other centre (smallest
    first), recomputing centres, until every remaining cluster is big enough or one is left.
    Labels are renumbered 0 … k−1."""
    labels = list(labels)
    centres = [list(c) for c in centres]
    while len(centres) > 1:
        sizes = [sum(1 for lab in labels if lab == c) for c in range(len(centres))]
        small = min(range(len(centres)), key=lambda c: (sizes[c], c))
        if sizes[small] >= min_members:
            break
        others = [c for c in range(len(centres)) if c != small]
        for i, lab in enumerate(labels):
            if lab == small:
                labels[i] = min(others, key=lambda c: (_sqdist(pts[i], centres[c]), c))
        keep = [c for c in range(len(centres)) if c != small]
        remap = {c: j for j, c in enumerate(keep)}
        labels = [remap[lab] for lab in labels]
        centres = [[sum(pts[i][j] for i in range(len(pts)) if labels[i] == c) / max(1, sum(1 for lab in labels if lab == c))
                    for j in range(len(pts[0]))] for c in range(len(keep))]
    return labels, centres


def _noise_reference(n: int, scales: list[float], k: int) -> float:
    """The silhouette the same pipeline reaches on ``n`` shapeless points: standard-normal
    coordinates (each dimension scaled like the real one), averaged over ``NOISE_DRAWS`` seeded
    draws. A real split must beat this by ``NOISE_MARGIN``."""
    scores = []
    for b in range(NOISE_DRAWS):
        rng = Pcg32(1000 * k + b, seq=91)
        pts = []
        for _ in range(n):
            row = []
            for sc in scales:
                u1 = (rng.below(1_000_000) + 1) / 1_000_001
                u2 = rng.below(1_000_000) / 1_000_000
                row.append(sc * math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2))
            pts.append(row)
        labels, centres, _ = _kmeans(pts, k)
        labels, centres = _merge_small(pts, labels, centres, MIN_MEMBERS)
        if len(centres) > 1:                      # a draw that folded into one group says nothing
            scores.append(_silhouette(pts, labels, centres))
    return sum(scores) / len(scores) if scores else 0.0


def _point_silhouette(p: list[float], lab: int, centres: list[list[float]]) -> float:
    a = math.sqrt(_sqdist(p, centres[lab]))
    b = min(math.sqrt(_sqdist(p, c)) for i, c in enumerate(centres) if i != lab)
    m = max(a, b)
    return (b - a) / m if m > 1e-12 else 0.0


def _silhouette(pts: list[list[float]], labels: list[int], centres: list[list[float]],
                weights: list[float] | None = None) -> float:
    """Simplified silhouette: per point (b − a) / max(a, b) with a = distance to its own centre
    and b = distance to the nearest other centre; weighted average. Higher = cleaner clusters;
    −1 with a single centre (nothing to separate from)."""
    if len(centres) < 2:
        return -1.0
    w = weights or [1.0] * len(pts)
    total = sum(wi * _point_silhouette(p, lab, centres) for p, lab, wi in zip(pts, labels, w))
    return total / (sum(w) or 1.0)


def _group_silhouette(pts: list[list[float]], labels: list[int], centres: list[list[float]], group: int) -> float:
    """The mean silhouette of one cluster's members (0 when there is only one cluster)."""
    if len(centres) < 2:
        return 0.0
    vals = [_point_silhouette(p, lab, centres) for p, lab in zip(pts, labels) if lab == group]
    return sum(vals) / len(vals) if vals else 0.0
