"""Generate two legal sample decks from the real pool for testing.

These are NOT the retail starter decks (their contents aren't known yet); they're RAM-legal
40-card lists built from the transcribed pool, so the pipeline can be exercised end to end.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.enums import CardType, Color  # noqa: E402
from cptcg.deck.decklist import Decklist  # noqa: E402
from cptcg.deck.validate import ram_limits, validate  # noqa: E402

reg = load_default()


def build(name, legend_ids, prefer_tags=(), size=40):
    legends = [reg.get(l) for l in legend_ids]
    limits = ram_limits(legends)
    pool = [d for d in reg.defs if d.type is not CardType.LEGEND and d.verified
            and d.ram <= limits[d.color] and limits[d.color] > 0]
    # Prefer on-theme cards, then cheap ones, for a plausible curve.
    pool.sort(key=lambda d: (-(bool(d.tags & set(prefer_tags))), d.cost or 0, d.id))
    counts = {}
    # Aim for ~24 units, ~10 programs, ~6 gear.
    quota = {CardType.UNIT: 24, CardType.PROGRAM: 10, CardType.GEAR: 6}
    for d in pool:
        if sum(counts.values()) >= size:
            break
        if quota[d.type] <= 0:
            continue
        n = min(3, quota[d.type], size - sum(counts.values()))
        counts[d.id] = n
        quota[d.type] -= n
    deck = Decklist.from_counts(name, list(legend_ids), counts,
                                note="Generated sample deck, not a retail starter list.")
    v = validate(deck, reg, allow_unscripted=True)
    assert v.ok, v
    return deck


arasaka = build("Sample Arasaka", ["goro-takemura-hands-unclean", "saburo-arasaka-stubborn-patriarch",
                                   "yorinobu-arasaka-embracing-destruction"], ("ARASAKA", "CORPO"))
mercs = build("Sample Mercs", ["v-streetkid", "dexter-deshawn-off-the-grid", "rogue-amendiares-preem-solo"],
              ("MERC", "ROCKER"))
for d, fn in ((arasaka, "sample_arasaka.json"), (mercs, "sample_mercs.json")):
    d.save(ROOT / "data" / "decks" / fn)
    print(fn, len(d.main), "cards;", ram_limits([reg.get(l) for l in d.legends]))
