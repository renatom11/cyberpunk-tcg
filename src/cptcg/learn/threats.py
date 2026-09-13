"""Threat counts over the rival's still-possible card pool. **Generated — do not edit.**

Rebuild with ``python tools/build_threat_table.py`` after any change to
``data/strategy/graph.json``; ``tests/learn/test_opponent.py`` fails if this disagrees with
the graph. See that tool's docstring for why this is a literal rather than a lookup.

Generated 2026-09-13 11:24 UTC.
"""

from __future__ import annotations

#: Non-Legend cards in the set. The denominator for 'how much of their deck is still open'.
POOL = 124

#: RAM on a Legend, and so the step between caps. Index a row with ``cap // RAM``.
RAM = 2

#: ``THREAT_TABLE[token][colour][cap // RAM]`` — cards of that colour carrying that threat
#: whose RAM fits under that cap. Colour index is ``core.enums.Color``.
THREAT_TABLE = {
    'unit.spend_rival': [
        [0, 0, 0, 0],    # RED
        [0, 3, 4, 4],    # GREEN
        [0, 1, 1, 1],    # BLUE
        [0, 2, 2, 2],    # YELLOW
    ],
    'unit.defeat_rival': [
        [0, 3, 5, 5],    # RED
        [0, 1, 4, 4],    # GREEN
        [0, 0, 0, 0],    # BLUE
        [0, 2, 4, 5],    # YELLOW
    ],
    'unit.power_zero': [
        [0, 1, 1, 1],    # RED
        [0, 2, 2, 2],    # GREEN
        [0, 1, 3, 3],    # BLUE
        [0, 2, 2, 2],    # YELLOW
    ],
    'discard.rival': [
        [0, 0, 0, 0],    # RED
        [0, 0, 0, 0],    # GREEN
        [0, 0, 0, 0],    # BLUE
        [0, 3, 3, 3],    # YELLOW
    ],
    'gig.decrease': [
        [0, 0, 0, 0],    # RED
        [0, 0, 0, 0],    # GREEN
        [0, 2, 2, 2],    # BLUE
        [0, 1, 1, 1],    # YELLOW
    ],
}

#: ``POOL_TABLE[colour][cap // RAM]`` — non-Legend cards of that colour that fit
#: under that cap. Summed over colours this is the size of the rival's live pool.
POOL_TABLE = [
    [0, 22, 31, 31],    # RED
    [0, 21, 31, 31],    # GREEN
    [0, 22, 30, 31],    # BLUE
    [0, 23, 30, 31],    # YELLOW
]

#: The order the feature vector emits them in. Fixed here so a dict reordering
#: cannot silently permute fifteen features under a fitted model.
THREAT_ORDER = ('unit.spend_rival', 'unit.defeat_rival', 'unit.power_zero', 'discard.rival', 'gig.decrease',)
