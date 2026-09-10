"""Markdown report for a tournament."""

from __future__ import annotations

from cptcg.sim.stats import wilson
from cptcg.sim.tournament import Tournament


def _pct(k: int, n: int) -> str:
    return f"{100 * k / n:.0f}%" if n else "—"


def render_report(t: Tournament, title: str = "Tournament") -> str:
    n = t.n()
    names = [d.name for d in t.decks]
    bt = t.bt()
    nash = t.nash()
    q = t.qvalues()
    res = t.residuals()
    field = t.field_rates()
    order = t.standings()
    strategies = [d.meta.get("strategy") for d in t.decks]
    show_strategy = any(strategies)
    out = [f"# {title}", "",
           f"{n} decks, agent `{t.agent}`, seed {t.seed}. Every pair played as mirrored seed pairs; "
           "cells stopped early when an SPRT settled them, so sample sizes differ by cell.", "",
           "## Standings (Bradley–Terry)", "",
           "| # | Deck | " + ("Strategy | " if show_strategy else "") + "BT strength | vs field | 95% interval | Nash weight |",
           "|---|---|" + ("---|" if show_strategy else "") + "---|---|---|---|"]
    for rank, i in enumerate(order, 1):
        k, g = field[i]
        lo, hi = wilson(k, g)
        out.append(f"| {rank} | {names[i]} | " + (f"{strategies[i] or '—'} | " if show_strategy else "")
                   + f"{bt[i]:.2f} | {_pct(k, g)} ({g}) | "
                   f"{100 * lo:.0f}–{100 * hi:.0f}% | {100 * nash[i]:.0f}% |")
    if show_strategy:
        # Which philosophy is winning: mean strength per personality, so a builder's thesis can
        # be judged across the decks it produced rather than by its single best deck.
        groups: dict[str, list[int]] = {}
        for i in range(n):
            groups.setdefault(strategies[i] or "—", []).append(i)
        rows = sorted(groups.items(), key=lambda kv: -sum(bt[i] for i in kv[1]) / len(kv[1]))
        out += ["", "## Philosophies", "",
                "| Strategy | Decks | Mean BT | vs field | Best deck |", "|---|---|---|---|---|"]
        for name, idxs in rows:
            k = sum(field[i][0] for i in idxs)
            g = sum(field[i][1] for i in idxs)
            best = max(idxs, key=lambda i: bt[i])
            out.append(f"| {name} | {len(idxs)} | {sum(bt[i] for i in idxs) / len(idxs):.2f} | "
                       f"{_pct(k, g)} ({g}) | {names[best]} |")
    max_res = max((abs(res[i][j]) for i in range(n) for j in range(n)), default=0.0)
    out += ["", f"Intransitivity (largest |observed − BT-predicted|): **{100 * max_res:.0f} points**"
            + (" — a rock-paper-scissors relationship is present." if max_res > 0.12 else "."), ""]
    support = [i for i in range(n) if nash[i] >= 0.05]
    out += ["Nash support (what a rational field brings): " + ", ".join(f"{names[i]} {100 * nash[i]:.0f}%" for i in support), ""]

    out += ["## Head-to-head (row beats column)", "",
            "| | " + " | ".join(names[i][:14] for i in order) + " |",
            "|---|" + "---|" * n]
    for i in order:
        row = [names[i][:14]]
        for j in order:
            if i == j:
                row.append("·")
                continue
            k, g = t.rate(i, j)
            key = (min(i, j), max(i, j))
            sig = "**" if q.get(key, 1.0) < 0.05 else ""
            row.append(f"{sig}{_pct(k, g)}{sig} ({g})")
        out.append("| " + " | ".join(row) + " |")
    out += ["", "Bold = significant after Benjamini–Hochberg FDR at q < 0.05. (n) = games in the cell.", ""]

    out += ["## Cards that move the needle (per deck)", "",
            "IWD = win rate in games where the card was drawn minus games where it wasn't. "
            "Correlational — draw order confounds it; the causal check is a card-swap A/B.", ""]
    for i in order:
        stats = [(cid, s) for cid, s in t.card_stats[i].items() if s.iwd is not None and s.drawn_games >= 10]
        stats.sort(key=lambda x: -x[1].iwd)
        if not stats:
            continue
        out.append(f"**{names[i]}**")
        out.append("")
        out.append("| Card | GIH WR | GND WR | IWD | drawn |")
        out.append("|---|---|---|---|---|")
        for cid, s in stats[:5] + ([("…", None)] if len(stats) > 8 else []) + stats[-3:]:
            if s is None:
                out.append("| … | | | | |")
                continue
            out.append(f"| {cid} | {100 * s.gih:.0f}% | {100 * s.gnd:.0f}% | {100 * s.iwd:+.0f} | {s.drawn_games} |")
        out.append("")
    return "\n".join(out) + "\n"
