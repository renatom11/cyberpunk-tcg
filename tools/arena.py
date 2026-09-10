"""The gate. Nothing about this project's AI may be claimed without a number from here.

    python tools/arena.py a-vs-b AGENT_A AGENT_B     # paired seeds, mirrored seats, SPRT, Wilson
    python tools/arena.py panel AGENT                # the frozen benchmark panel
    python tools/arena.py exploit AGENT              # the cheating upper bound
    python tools/arena.py delayed [AGENT]            # the delayed-reward suite: solved N of M
    python tools/arena.py generalisation AGENT       # training decks vs the held-out starters

Every command writes JSON under ``out/arena/`` and appends a section to ``docs/learning.md``
(``--no-docs`` to suppress). Every match is played over freshly sampled deck pairs with the seats
mirrored *and* the deck assignments swapped, so neither seat order nor deck strength can be
mistaken for agent strength; see ``cptcg.learn.arena`` for the design and its reasoning.

The commands live in ``cptcg.cli.arena`` so that ``cptcg arena`` is the same command; this file is
the standalone entry point, which is what a session without the package installed reaches for.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cli.arena import add_arguments  # noqa: E402


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="tools/arena.py", description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n".join(__doc__.splitlines()[2:8]))
    add_arguments(ap)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
