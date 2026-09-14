"""Write data/COVERAGE.md: what is transcribed, verified and scripted -- and what that does not mean.

The table this writes has always reported "rules text not yet scripted: 0", and that zero was read
for a long time as coverage. It is not. It is derived from ``CardDef.needs_script``, which asks
whether the printed text implies an effect and no script exists, so it detects a **missing** script
and is structurally blind to a wrong or partial one. A card with a script that implements the wrong
half of its text scores exactly the same as a perfect one.

So the file now carries a second table beside the first, counting the things that can actually go
wrong: scripted cards no test names, open audit findings, and whether the pool-wide behaviour lints
pass. Those numbers move when correctness moves; the first table does not.
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402

reg = load_default()
defs = reg.defs
unverified = [d for d in defs if not d.verified]
unscripted = [d for d in defs if d.needs_script]
vanilla = [d for d in defs if d.verified and not d.needs_script and d.script is None]
scripted = [d for d in defs if d.script is not None]

lines = ["# Card data coverage", "",
         f"Pool: **{len(defs)} cards** (Welcome to Night City + starter sets).", "",
         "| | Count |", "|---|---|",
         f"| Transcribed and verified against the card face | {len(defs) - len(unverified)} |",
         f"| Needing a card-face screenshot | {len(unverified)} |",
         f"| Vanilla (no rules text — need no script) | {len(vanilla)} |",
         f"| Scripted | {len(scripted)} |",
         f"| Rules text not yet scripted | {len(unscripted)} |", ""]
lines += ["## Needs a card-face screenshot", "",
          "These have placeholder or partial data. Decks containing them are refused unless "
          "`--allow-unverified` is passed.", ""]
for d in unverified:
    note = getattr(d, "notes", None)
    raw = next(c for c in __import__("json").load(open(ROOT / "data/cards/wnc.json"))["cards"] if c["id"] == d.id)
    lines.append(f"- **{d.name}**" + (f" — {d.subtitle}" if d.subtitle else "") + f" (`{d.id}`): {raw.get('notes', '')}")
lines += ["", "## Rules text not yet scripted", "",
          "Transcribed, but the effect is not implemented. Decks containing them are refused "
          "unless `--allow-unscripted` is passed (the card would play as vanilla).", ""]
by_type = Counter(d.type.name.title() for d in unscripted)
lines.append(", ".join(f"{k}: {v}" for k, v in sorted(by_type.items())))
lines.append("")
for d in sorted(unscripted, key=lambda d: d.id):
    lines.append(f"- `{d.id}`")
# ---------------------------------------------------------------- what is *checked*
import ast
import re

TESTS = ROOT / "tests"


def _named_by_a_test() -> set:
    """Card ids some test module mentions. Naming is a floor, not proof of exercise — see
    tests/cards/test_coverage.py, which enforces it. Golden replays and fixtures are excluded
    because they name almost a hundred cards as a side effect of eight decks."""
    blob = []
    for p in sorted(TESTS.rglob("*.py")):
        if "golden" in p.parts or "fixtures" in p.parts:
            continue
        blob.append(p.read_text(encoding="utf-8"))
    text = "\n".join(blob)
    return {d.id for d in defs if d.id in text}


def _open_findings() -> list:
    """Finding ids from the strict-xfail markers under tests/cards/audit/."""
    out = []
    for p in sorted((TESTS / "cards" / "audit").glob("test_*.py")):
        for m in re.finditer(r'reason=\(?\s*["\']([^"\']*)', p.read_text(encoding="utf-8")):
            if m.group(1).startswith("AUD-"):
                out.append(m.group(1).split(":")[0].strip())
    return sorted(set(out))


named = _named_by_a_test()
findings = _open_findings()
uncovered = sorted(d.id for d in scripted if d.id not in named)
lines += ["", "## What is *checked*", "",
          "The table above counts what exists. This one counts what has been verified, which is a "
          "different question and the one that decides whether a simulation result means anything. "
          "`needs_script` reads 0 for every card in the pool and is blind to a script that is "
          "wrong rather than missing.", "",
          "| | Count |", "|---|---|",
          f"| Scripted cards | {len(scripted)} |",
          f"| ... named by at least one test | {len(scripted) - len(uncovered)} |",
          f"| ... named by no test at all | {len(uncovered)} |",
          f"| Open audit findings (failing tests, awaiting a fix) | {len(findings)} |", ""]
if uncovered:
    lines += ["Not named by any test: " + ", ".join(f"`{c}`" for c in uncovered), ""]
if findings:
    lines += ["Open findings — each is a `xfail(strict=True)` test under `tests/cards/audit/`, so "
              "the suite stays green until a fix makes one pass and pytest reports XPASS:", ""]
    lines += [f"- `{f}`" for f in findings]
    lines += [""]
lines += ["See [docs/verification.md](../docs/verification.md) for what each kind of check can and "
          "cannot prove.", ""]

(ROOT / "data" / "COVERAGE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"verified {len(defs) - len(unverified)}/{len(defs)}, unscripted {len(unscripted)}, "
      f"vanilla {len(vanilla)}, scripted {len(scripted)}; "
      f"{len(uncovered)} scripted cards named by no test, {len(findings)} open findings")
