"""Which cards any test has ever looked at.

`CardDef.needs_script` reads 0 for all 151 cards, and that 0 has always been the project's only
card-correctness signal. It is derived from "the printed text implies an effect and there is no
script", so it detects a **missing** script and is structurally blind to a wrong or partial one.
Nothing has ever tracked whether a card that *has* a script was ever exercised by a test.

This is the floor under that: a scripted card must at least be named by some test module. Naming is
a weaker claim than exercising — a card mentioned in a deck list inside a test is named without
being tested — so this is a coverage *floor*, not proof of coverage. It is still the check that
would have caught the hole it was written for: eight scripted cards, six of them Legends, that no
test in the repository had ever mentioned.

``tests/golden`` and ``tests/fixtures`` are excluded on purpose. The golden replays name almost a
hundred cards as a side effect of the eight decks they were recorded from, which would let the
count look healthy while nobody had written a line about any of them.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

TESTS = Path(__file__).resolve().parents[1]

#: Scripted cards no test module names yet. Empty, and it should stay that way: the eight cards that
#: were on this list — six of them Legends, which is not a coincidence, since a Legend is never drawn
#: and so falls out of every draw-conditioned measurement too — now have scenario tests in
#: ``tests/cards/test_uncovered.py``. A card added without one fails the test below.
UNCOVERED: set[str] = set()


def _test_sources() -> str:
    """Every test module except this one.

    Excluding itself is not tidiness — ``UNCOVERED`` below names all eight cards, so counting this
    file would report full coverage on the strength of the list of cards that have none.
    """
    me = Path(__file__).resolve()
    out = []
    for p in sorted(TESTS.rglob("*.py")):
        if "golden" in p.parts or "fixtures" in p.parts or p.resolve() == me:
            continue
        out.append(p.read_text(encoding="utf-8"))
    return "\n".join(out)


def test_every_scripted_card_is_named_by_some_test(pool):
    blob = _test_sources()
    scripted = {d.id for d in pool.defs if d.script is not None}
    unnamed = {c for c in scripted if c not in blob}
    new = unnamed - UNCOVERED
    assert not new, ("a scripted card no test mentions, and it is not on the known list:\n  "
                     + "\n  ".join(sorted(new)))
    stale = UNCOVERED - unnamed
    assert not stale, ("these now have tests — delete them from UNCOVERED so the floor rises:\n  "
                       + "\n  ".join(sorted(stale)))
