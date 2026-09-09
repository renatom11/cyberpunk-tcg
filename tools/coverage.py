"""Write data/COVERAGE.md: what is transcribed, verified and scripted, and what is missing."""
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
(ROOT / "data" / "COVERAGE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"verified {len(defs) - len(unverified)}/{len(defs)}, unscripted {len(unscripted)}, "
      f"vanilla {len(vanilla)}, scripted {len(scripted)}")
