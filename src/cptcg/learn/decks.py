"""The deck-pair sampler: what every self-play game is handed.

Training on one matchup produces a specialist that has memorised it. The model must play
whatever list it is given and get the most out of it, so **every self-play game draws a fresh
pair of decks** from a mix of sources:

===============  =============================================================================
``random``       any RAM-legal deck (``builder.random_deck``). Breadth: it reaches lists no
                 person would build, which is exactly the state space a greedy agent never
                 visits.
``heuristic``    ``builder.heuristic_deck`` with jittered ``BuildPrefs`` — a curve, a type mix
                 and a sell-tag floor, so the list looks like something someone would sleeve.
``explorer``     ``strategies.Explorer``: builds toward a deck *shape* drawn at random inside
                 the range the legal pool allows, which spreads over archetype space rather
                 than over card space. A ``Learned`` builder can be passed instead once an
                 ``ArchetypeStore`` exists; the sampler needs no store to run.
``sample``       the hand-built ``data/decks/sample_*.json`` lists.
===============  =============================================================================

**The two retail starters (``the_heist``, ``embracing_power``) are held out of training
entirely.** They are the test set: ``holdout_pairs`` returns them for evaluation, and no
training sample may ever contain them, so the generalisation gap measured on them is honest.

Sampling is a pure function of the ``Pcg32`` handed in: the same rng state gives the same pair,
which is what makes a self-play generation reproducible from its seed alone.
"""

from __future__ import annotations

from pathlib import Path

from cptcg.cards.registry import Registry
from cptcg.core.rng import Pcg32
from cptcg.deck.builder import BuildPrefs, heuristic_deck, random_deck
from cptcg.deck.decklist import Decklist
from cptcg.deck.strategies import BuilderStrategy, Explorer

DECK_DIR = Path(__file__).resolve().parents[3] / "data" / "decks"

#: The retail starter decks. Never sampled for training; see ``holdout_pairs``.
HOLDOUT = ("the_heist", "embracing_power")

#: Where a sampled deck comes from, and how often. A named constant so it can be tuned in one
#: place and quoted in a training report. Weights need not sum to 1; they are normalised.
DEFAULT_MIX: dict[str, float] = {
    "random": 0.30,        # breadth of card combinations
    "heuristic": 0.35,     # plausible lists, curve and economy respected
    "explorer": 0.20,      # breadth of deck *shapes*
    "sample": 0.15,        # the hand-built lists people actually see
}

SOURCES = tuple(DEFAULT_MIX)

#: Main-deck sizes the ``random`` and ``heuristic`` sources draw from, weighted toward the 40-card
#: minimum because that is what almost every real list plays; the long tail teaches the model that
#: a deck can be thicker. ``explorer`` builds at the fill's own 40-card default and ``sample``
#: takes each list as written.
SIZES = (40, 40, 40, 40, 42, 45, 50)

# The two ends of the curve a jittered heuristic build interpolates between, by cost 1..7+.
_CHEAP_CURVE = (0.20, 0.28, 0.24, 0.14, 0.08, 0.04, 0.02)
_TOP_CURVE = (0.04, 0.10, 0.18, 0.20, 0.20, 0.16, 0.12)

_SAMPLE_CACHE: dict[Path, tuple[Decklist, ...]] = {}


# ------------------------------------------------------------------ the fixed lists
def _load_dir(folder: Path | None, pattern: str) -> tuple[Decklist, ...]:
    folder = DECK_DIR if folder is None else Path(folder)
    key = folder / pattern
    hit = _SAMPLE_CACHE.get(key)
    if hit is None:
        hit = tuple(Decklist.load(p) for p in sorted(folder.glob(pattern)) if p.stem not in HOLDOUT)
        _SAMPLE_CACHE[key] = hit
    return hit


def training_decks(folder: Path | None = None) -> tuple[Decklist, ...]:
    """The hand-built lists a training sample may draw from: ``data/decks/sample_*.json``,
    with the held-out starters filtered out by name whatever the glob matches."""
    return _load_dir(folder, "sample_*.json")


def holdout_decks(folder: Path | None = None) -> tuple[Decklist, ...]:
    """The two retail starters, in ``HOLDOUT`` order. Evaluation only."""
    folder = DECK_DIR if folder is None else Path(folder)
    key = folder / "|holdout"
    hit = _SAMPLE_CACHE.get(key)
    if hit is None:
        hit = tuple(Decklist.load(folder / f"{n}.json") for n in HOLDOUT)
        _SAMPLE_CACHE[key] = hit
    return hit


def holdout_pairs(reg: Registry,
                  folder: Path | None = None) -> tuple[tuple[Decklist, Decklist], ...]:
    """The held-out matchup in both seat orders, so an evaluation over it is already mirrored.

    ``reg`` is accepted (and the decks are looked up in it) so a caller gets a clear KeyError
    here rather than a confusing one mid-game if the registry does not know a starter's cards.
    """
    a, b = holdout_decks(folder)
    for d in (a, b):
        for cid in d.legends + d.main:
            reg.get(cid)
    return ((a, b), (b, a))


def is_holdout(deck: Decklist) -> bool:
    """True if ``deck`` is one of the retail starters, by name or by contents."""
    if deck.name in HOLDOUT:
        return True
    mine = (tuple(sorted(deck.legends)), tuple(sorted(deck.main)))
    for h in holdout_decks():
        if mine == (tuple(sorted(h.legends)), tuple(sorted(h.main))):
            return True
    return False


# ------------------------------------------------------------------ the sampler
def normalised_mix(mix: dict[str, float] | None = None) -> tuple[tuple[str, float], ...]:
    """``mix`` as ((source, cumulative weight), ...) with the weights summing to 1.

    Raises ValueError for an unknown source or a mix that is empty or all-zero, because a typo
    in a training config that silently trained on one source would be invisible for days.
    """
    mix = DEFAULT_MIX if mix is None else mix
    bad = [k for k in mix if k not in DEFAULT_MIX]
    if bad:
        raise ValueError(f"unknown deck source(s): {sorted(bad)}; known: {sorted(DEFAULT_MIX)}")
    total = sum(max(0.0, w) for w in mix.values())
    if total <= 0:
        raise ValueError("deck source mix has no positive weight")
    out = []
    acc = 0.0
    for k in SOURCES:                       # fixed order: the mix is a dict, sampling is not
        w = max(0.0, mix.get(k, 0.0))
        if w <= 0:
            continue
        acc += w / total
        out.append((k, acc))
    out[-1] = (out[-1][0], 1.0)
    return tuple(out)


def pick_source(rng: Pcg32, mix: dict[str, float] | None = None) -> str:
    """Draw one source name from the mix."""
    u = rng.below(10_000) / 10_000
    table = normalised_mix(mix)
    for name, cum in table:
        if u < cum:
            return name
    return table[-1][0]


def random_prefs(rng: Pcg32, size: int) -> BuildPrefs:
    """Jittered build preferences: one random type composition, one cost tilt interpolating
    between a cheap and a top-heavy curve, and a sell-tag floor between 0.25 and 0.60. Without
    the jitter every ``heuristic`` deck would be the same shape on different Legends."""
    u = 0.35 + rng.below(35) / 100.0                    # 0.35 - 0.69 Units
    p = 0.10 + rng.below(30) / 100.0                    # 0.10 - 0.39 Programs
    g = max(0.05, 1.0 - u - p)
    tot = u + p + g
    tilt = rng.below(1000) / 1000.0
    curve = tuple(a * (1.0 - tilt) + b * tilt for a, b in zip(_CHEAP_CURVE, _TOP_CURVE))
    return BuildPrefs(size=size, unit_share=u / tot, program_share=p / tot, gear_share=g / tot,
                      sell_min=0.25 + rng.below(36) / 100.0, curve=curve,
                      noise=0.2 + rng.below(50) / 100.0)


def _draw(reg: Registry, rng: Pcg32, mix, builder, name: str | None) -> Decklist:
    src = pick_source(rng, mix)
    size = SIZES[rng.below(len(SIZES))]
    if src == "sample":
        decks = training_decks()
        if decks:
            return decks[rng.below(len(decks))]
        src = "heuristic"                                # no data directory: fall back, never fail
    if src == "random":
        return random_deck(reg, rng, size=size, name=name or "random")
    if src == "heuristic":
        return heuristic_deck(reg, None, rng, random_prefs(rng, size), name=name or "built")
    b = builder or Explorer()
    return b.build(reg, None, rng, name=name or b.name)


def sample_deck(reg: Registry, rng: Pcg32, *, mix: dict[str, float] | None = None,
                builder: BuilderStrategy | None = None, name: str | None = None) -> Decklist:
    """One deck from the mix.

    ``builder`` replaces the ``explorer`` source: pass a ``strategies.Learned`` to sample
    archetype-shaped decks once an ``ArchetypeStore`` exists.

    A generated deck is checked against the held-out starters and redrawn if it happens to match
    one. Rebuilding a starter card for card is vanishingly unlikely, but "never returns a starter"
    is the property the generalisation gap rests on, so it is enforced rather than assumed.
    """
    for _ in range(4):
        d = _draw(reg, rng, mix, builder, name)
        if not is_holdout(d):
            return d
    raise RuntimeError("the deck sampler kept drawing a held-out starter")


def sample_pair(reg: Registry, rng: Pcg32, *, mix: dict[str, float] | None = None,
                builder: BuilderStrategy | None = None) -> tuple[Decklist, Decklist]:
    """A fresh deck pair for one self-play game, drawn independently from the mix.

    A mirror of two *generated* decks is vanishingly unlikely and harmless, but the fixed sample
    lists are few, so an identical sample-vs-sample pair is redrawn a few times before being
    accepted. Names are made distinct, because a match summary keys on them.
    """
    a = sample_deck(reg, rng, mix=mix, builder=builder)
    b = sample_deck(reg, rng, mix=mix, builder=builder)
    for _ in range(3):
        if not (b.legends == a.legends and b.main == a.main):
            break
        b = sample_deck(reg, rng, mix=mix, builder=builder)
    if b.name == a.name:
        b = Decklist(b.name + "-b", b.legends, b.main, dict(b.meta))
    return a, b
