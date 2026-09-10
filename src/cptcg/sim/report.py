"""Plain-English reports for a tournament.

Everything a reader sees is produced here, once, in Python: the summary sentences
(``summarize``), the significance wording (``sig_word``), the deck shape numbers
(``deck_profile_json``) and the Markdown document (``render_report``). The web page prints the
same sentences from the JSON, so the words are unit-tested and never duplicated in JavaScript.

Statistics are described honestly: an interval is a range of plausible values, "statistically
solid" means the false-discovery-adjusted q is below 0.05, and the card table is correlational.
"""

from __future__ import annotations

from cptcg.sim.stats import wilson
from cptcg.sim.tournament import CardStat, Tournament

_REG = None


# ------------------------------------------------------------------ shared helpers
def registry(reg=None):
    """``reg`` itself, or the standard card registry loaded once per process."""
    global _REG
    if reg is not None:
        return reg
    if _REG is None:
        from cptcg.cards.registry import load_default
        _REG = load_default()
    return _REG


def card_name(reg, cid: str) -> str:
    """Human name: ``Name — Subtitle`` when the card has a subtitle (three Legends share names),
    the raw id when the registry does not know the card."""
    try:
        d = reg.get(cid)
    except KeyError:
        return cid
    return f"{d.name} — {d.subtitle}" if d.subtitle else d.name


def deck_kind(deck) -> str | None:
    """The kind of deck a builder labelled it with: the learned archetype it was built toward
    (``"exploring"`` for an Explorer), or the builder label of an older file."""
    meta = getattr(deck, "meta", None) or {}
    return meta.get("archetype") or meta.get("strategy") or None


def deck_profile_json(deck, reg) -> dict | None:
    """Shape numbers of a deck list for the JSON: the archetype fingerprint (``deck_profile``'s
    numbers plus type and cost-band shares, extra-steal and draw counts, Legend colour flags)
    plus a cost curve (cards costing 1 … 7+), type counts, sell-tag count and size. None if a
    card is unknown."""
    from cptcg.deck.archetypes import fingerprint
    try:
        defs = [reg.get(c) for c in deck.main]
        prof = fingerprint(reg, deck)
    except KeyError:
        return None
    curve = [0] * 7
    types = {"Unit": 0, "Program": 0, "Gear": 0}
    for d in defs:
        curve[min(6, max(0, (d.cost or 1) - 1))] += 1
        key = d.type.name.title()
        types[key] = types.get(key, 0) + 1
    out = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in prof.items()}
    out.update(curve=curve, types=types, sell_tags=sum(1 for d in defs if d.sell_tag), cards=len(defs))
    return out


def profile_sentence(prof: dict | None) -> str:
    """One line a reader can picture — ``archetypes.describe_fingerprint``: the curve, the share
    of Units and of sellable cards, and the counts of the effects the list carries."""
    from cptcg.deck.archetypes import describe_fingerprint
    return describe_fingerprint(prof)


def _pct(k: int, n: int) -> str:
    return f"{100 * k / n:.0f}%" if n else "—"


def _sig_parts(q: float, n: int) -> tuple[str, str]:
    if q < 0.01:
        word = "very solid"
    elif q < 0.05:
        word = "solid"
    elif q < 0.2:
        word = "suggestive"
    else:
        word = "not established"
    return word, (f"only {n} games" if n < 30 else "")


def sig_word(q: float, n: int) -> str:
    """How much to trust a matchup result: ``very solid`` (q < 0.01), ``solid`` (q < 0.05),
    ``suggestive`` (q < 0.2) or ``not established``, with ``(only N games)`` under 30 games.
    q is the false-discovery-adjusted p-value of the cell (Benjamini–Hochberg)."""
    word, note = _sig_parts(q, n)
    return word + (f" ({note})" if note else "")


def top_and_bottom(items: list, top: int = 5, bottom: int = 3, keep_all: int = 8) -> list:
    """The first ``top`` and last ``bottom`` of a sorted list without printing any item twice:
    when there are at most ``keep_all`` items every one is returned, otherwise the two ends are
    separated by a single ``None`` (rendered as an ellipsis)."""
    if len(items) <= keep_all:
        return list(items)
    return list(items[:top]) + [None] + list(items[-bottom:])


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _fmt_seconds(s: float | None) -> str:
    if s is None:
        return ""
    s = float(s)
    if s < 90:
        return f"{s:.0f} s"
    if s < 3600:
        return f"{s / 60:.0f} min"
    return f"{s / 3600:.1f} h"


# ------------------------------------------------------------------ the summary in words
def summarize(t: Tournament, reg=None, *, bt=None, nash=None, q=None) -> list[str]:
    """The plain-English summary: who won and how convincingly, whether the matchups form a
    rock–paper–scissors pattern, and what a player picking blind should bring. Each entry is
    one sentence; both the Markdown and the web page print them verbatim."""
    reg = registry(reg)
    n = t.n()
    if n == 0:
        return []
    bt = bt if bt is not None else t.bt()
    nash = nash if nash is not None else t.nash()
    q = q if q is not None else t.qvalues()
    names = [d.name for d in t.decks]
    order = sorted(range(n), key=lambda i: -bt[i])
    top = order[0]
    field = t.field_rates()
    total = sum(c.n for c in t.cells.values())
    out: list[str] = []

    kind = deck_kind(t.decks[top])
    label = f"{names[top]} ({kind})" if kind else names[top]
    k, g = field[top]
    beaten, lost, even = [], [], []
    for j in order[1:]:
        w, m = t.rate(top, j)
        if m == 0:
            continue
        (beaten if 2 * w > m else lost if 2 * w < m else even).append(j)
    if g == 0:
        out.append(f"{label} is rated strongest, but no games were played, so nothing here is established.")
        return out
    s = f"{label} is the strongest deck in this run: it won {_pct(k, g)} of its {g} games"
    if not lost and not even:
        s += " and beat every other deck."
    else:
        s += f", beating {len(beaten)} of the other {n - 1} decks"
        if lost:
            s += f"; it lost to {_join([names[j] for j in lost])}"
        if even:
            s += f"; it split the games evenly with {_join([names[j] for j in even])}"
        s += "."
    out.append(s)

    # How much to trust each of the top deck's matchups, grouped by how settled they are.
    def cell_q(i, j):
        return q.get((min(i, j), max(i, j)), 1.0)

    def result(j):
        w, m = t.rate(top, j)
        return f"{names[j]} ({_pct(w, m)} of {m} games)"

    groups = {"very solid": [], "solid": [], "suggestive": [], "not established": []}
    for j in beaten:
        groups[_sig_parts(cell_q(top, j), t.rate(top, j)[1])[0]].append(j)
    solid = groups["very solid"] + groups["solid"]
    small = any(t.rate(top, j)[1] < 30 for j in solid)
    if solid:
        strength = "very solid" if not groups["solid"] else "solid"
        out.append(f"Its {'win' if len(solid) == 1 else 'wins'} over {_join([result(j) for j in solid])} "
                   f"{'is' if len(solid) == 1 else 'are'} statistically {strength} — unlikely to be luck"
                   + (", though some rest on fewer than 30 games, so keep some doubt." if small else "."))
    if groups["suggestive"]:
        js = groups["suggestive"]
        out.append(f"Its edge over {_join([result(j) for j in js])} is suggestive but not settled — "
                   "more games could still change it.")
    if groups["not established"]:
        js = groups["not established"]
        out.append(f"Its {'result' if len(js) == 1 else 'results'} against {_join([result(j) for j in js])} "
                   f"{'is' if len(js) == 1 else 'are'} not established — {'it' if len(js) == 1 else 'they'} could easily be noise.")
    for j in lost:
        word, note = _sig_parts(cell_q(top, j), t.rate(top, j)[1])
        if word in ("very solid", "solid"):
            tail = f"a statistically {word} loss"
        elif word == "suggestive":
            tail = "a suggestive but unsettled loss"
        else:
            tail = "a loss that is not established and may be noise"
        out.append(f"It lost to {result(j)} — {tail}" + (f" ({note})." if note else "."))
    for j in even:
        w, m = t.rate(top, j)
        out.append(f"It split its games evenly with {names[j]} ({w} of {m}).")

    # Rock–paper–scissors: a matchup far from what the strengths predict.
    res = t.residuals()
    best = None
    for i in range(n):
        for j in range(n):
            if i != j and t.rate(i, j)[1] and (best is None or res[i][j] > res[best[0]][best[1]]):
                best = (i, j)
    if best is not None and res[best[0]][best[1]] > 0.12:
        i, j = best
        out.append(f"Not every matchup follows the ranking: {names[i]} beats {names[j]} about "
                   f"{100 * res[i][j]:.0f} points more often than their strengths predict — a rock–paper–scissors "
                   "pattern, so the best deck depends on what it faces.")

    # What a player who has to pick blind should bring.
    support = sorted([i for i in range(n) if nash[i] >= 0.05], key=lambda i: -nash[i])
    if len(support) > 1:
        mix = _join([f"{names[i]} {100 * nash[i]:.0f}% of the time" for i in support])
        out.append(f"If you had to pick a deck blind for this field, bring {mix}: no single deck is safe against all the others.")
    elif support:
        i = support[0]
        holds = all(2 * t.rate(i, j)[0] >= t.rate(i, j)[1] for j in range(n) if j != i and t.rate(i, j)[1])
        out.append(f"If you had to pick a deck blind for this field, bring {names[i]} every time"
                   + (" — it holds at least even against every other deck." if holds else "."))

    if t.cells and total < 40 * len(t.cells):
        out.append(f"This was a small run ({total} games in all, under 40 per matchup): treat every number as a "
                   "first look, not a verdict.")
    return out


# ------------------------------------------------------------------ the Markdown document
def _deck_list_lines(deck, reg) -> list[str]:
    """The list grouped Units / Programs / Gear, each sorted by cost then name."""
    groups: dict[str, list[tuple[int, str, int, str]]] = {"Units": [], "Programs": [], "Gear": [], "Other": []}
    for cid, cnt in deck.counts().items():
        try:
            d = reg.get(cid)
        except KeyError:
            groups["Other"].append((0, cid, cnt, f"{cnt}× {cid}"))
            continue
        cost = d.cost if d.cost is not None else 0
        stat = f"cost {cost}" + (f", power {d.power}{'+' if d.power_variable else ''}" if d.power is not None else "")
        key = {"UNIT": "Units", "PROGRAM": "Programs", "GEAR": "Gear"}.get(d.type.name, "Other")
        groups[key].append((cost, d.name, cnt, f"{cnt}× {card_name(reg, cid)} ({stat})"))
    lines = []
    for label, items in groups.items():
        if not items:
            continue
        items.sort()
        lines.append(f"- {label} ({sum(x[2] for x in items)}): " + "; ".join(x[3] for x in items))
    return lines


def _swap_text(prop: dict, reg) -> str:
    a, b = card_name(reg, prop.get("out", "?")), card_name(reg, prop.get("in", "?"))
    return ("Legend " if prop.get("kind") == "legend" else "") + f"{a} → {b}"


def _changes_lines(hist: list[dict], reg) -> list[str]:
    if not hist:
        return ["- Changes this generation: no card swap was tried."]
    acc = [h for h in hist if h.get("accepted")]
    rej = len(hist) - len(acc)
    if not acc:
        return [f"- Changes this generation: none — all {rej} proposed swap{'s' if rej != 1 else ''} "
                f"{'were' if rej != 1 else 'was'} rejected by the swap test, so the list is unchanged."]
    parts = []
    for h in acc:
        disc, wins, games = int(h.get("discordant", 0)), int(h.get("challenger_wins", 0)), int(h.get("games", 0))
        what = "Legend" if (h.get("proposal") or {}).get("kind") == "legend" else "card"
        parts.append(f"{_swap_text(h.get('proposal') or {}, reg)} (the new {what} won {_pct(wins, disc)} of the {disc} "
                     f"games that differed, {games} games played)")
    return [f"- Changes this generation: accepted {'; '.join(parts)}"
            + (f"; {rej} other proposal{'s were' if rej != 1 else ' was'} rejected." if rej else ".")]


def render_report(t: Tournament, title: str | None = None, reg=None) -> str:
    """The full Markdown report: what was run, the summary in words, standings, head-to-head,
    every deck list, the cards that helped and hurt, and a glossary."""
    reg = registry(reg)
    info = t.info or {}
    title = title or info.get("title") or "Tournament"
    n = t.n()
    names = [d.name for d in t.decks]
    bt = t.bt()
    nash = t.nash()
    q = t.qvalues()
    field = t.field_rates()
    order = t.standings()
    kinds = [deck_kind(d) for d in t.decks]
    show_kind = any(kinds)
    total = sum(c.n for c in t.cells.values())
    cap = info.get("games_per_pair")
    sprt = info.get("sprt")

    # ---- what was run
    facts = [f"{n} decks"]
    if cap:
        facts.append(f"up to {cap} games per pair")
    facts += [f"{total} games played", f"`{t.agent}` agents on both sides", f"seed {t.seed}"]
    if info.get("elapsed_s") is not None:
        facts.append(f"run time {_fmt_seconds(info['elapsed_s'])}")
    if info.get("finished_at"):
        facts.append(f"finished {info['finished_at']}")
    out = [f"# {title}", "", "## What was run", "", " · ".join(facts), ""]
    if info.get("generation"):
        gens = info.get("generations")
        out.append(f"Generation {info['generation']}" + (f" of {gens}" if gens else "") + " of a league"
                   + (f" (seed {info['league_seed']}" if info.get("league_seed") is not None else "(")
                   + (f", {info['steps']} improvement steps per builder)" if info.get("steps") is not None else ")")
                   + ": each builder improved its deck by measured card swaps, then everyone played a round robin.")
        out.append("")
    out.append("Every pair of decks played mirrored games: each random seed is played twice with the seats swapped, "
               "so going first evens out.")
    if sprt:
        out.append(f"A matchup stopped early as soon as one deck was clearly ahead, or the two were clearly within "
                   f"{100 * float(sprt.get('delta', 0)):.0f} points of even, so the number of games differs per matchup; "
                   "lopsided matchups needed few games, close ones ran to the cap.")
    elif cap:
        out.append(f"Every matchup played the full {cap} games.")
    out.append("")

    # ---- summary
    out += ["## Summary", ""]
    out += [f"- {s}" for s in summarize(t, reg, bt=bt, nash=nash, q=q)]
    out.append("")

    # ---- standings
    out += ["## Standings", "",
            "Win rate is over every opponent, with the 95% range of plausible values and the games it rests on. "
            "Strength is a rating fitted to all matchups at once (1.0 = average deck here; 2.0 ≈ 67% expected against an average deck). "
            "Bring it? is how often a player picking blind for this field should bring the deck.", "",
            "| # | Deck | " + ("Archetype | " if show_kind else "") + "Win rate (95% range, games) | Strength | Bring it? |",
            "|---|---|" + ("---|" if show_kind else "") + "---|---|---|"]
    for rank, i in enumerate(order, 1):
        k, g = field[i]
        lo, hi = wilson(k, g)
        expected = bt[i] / (bt[i] + 1)
        out.append(f"| {rank} | {names[i]} | " + (f"{kinds[i] or '—'} | " if show_kind else "")
                   + f"{_pct(k, g)} ({100 * lo:.0f}–{100 * hi:.0f}%, {g}) | "
                   f"{bt[i]:.2f} ({100 * expected:.0f}% vs average) | {100 * nash[i]:.0f}% |")
    out.append("")

    if show_kind:
        groups: dict[str, list[int]] = {}
        for i in range(n):
            groups.setdefault(kinds[i] or "—", []).append(i)
        rows = sorted(groups.items(), key=lambda kv: -sum(bt[i] for i in kv[1]) / len(kv[1]))
        out += ["## Archetypes in this run", "",
                "The same numbers pooled by kind of deck, so a building idea is judged by all the decks it produced, "
                "not by its single best one.", "",
                "| Archetype | Decks | Average strength | Win rate (games) | Best deck |", "|---|---|---|---|---|"]
        for kind, idxs in rows:
            k = sum(field[i][0] for i in idxs)
            g = sum(field[i][1] for i in idxs)
            best = max(idxs, key=lambda i: bt[i])
            out.append(f"| {kind} | {len(idxs)} | {sum(bt[i] for i in idxs) / len(idxs):.2f} | "
                       f"{_pct(k, g)} ({g}) | {names[best]} |")
        out.append("")

    # ---- head-to-head
    out += ["## Head-to-head", "",
            "Read across: the row deck's win rate against the column deck, with the games in brackets. "
            "Bold marks a result that is statistically solid (see the glossary).", "",
            "| | " + " | ".join(names[i] for i in order) + " |",
            "|---|" + "---|" * n]
    for i in order:
        row = [names[i]]
        for j in order:
            if i == j:
                row.append("·")
                continue
            k, g = t.rate(i, j)
            sig = "**" if q.get((min(i, j), max(i, j)), 1.0) < 0.05 and g else ""
            row.append(f"{sig}{_pct(k, g)}{sig} ({g})")
        out.append("| " + " | ".join(row) + " |")
    out.append("")

    # ---- the decks
    climb = info.get("climb") or []
    out += ["## The decks", ""]
    for rank, i in enumerate(order, 1):
        d = t.decks[i]
        head = f"### {rank}. {names[i]}" + (f" — {kinds[i]}" if kinds[i] else "")
        out += [head, ""]
        out.append("- Legends: " + ", ".join(card_name(reg, l) for l in d.legends))
        prof = deck_profile_json(d, reg)
        if prof:
            out.append(f"- Shape: {profile_sentence(prof)}")
            out.append("- Cost curve (cards costing 1, 2, 3, 4, 5, 6, 7+): " + " · ".join(str(c) for c in prof["curve"]))
        out += _deck_list_lines(d, reg)
        if climb and i < len(climb) and climb[i] is not None:
            out += _changes_lines(climb[i], reg)
        if info.get("replaced") == names[i]:
            out.append("- This builder is replaced by a fresh deck next generation.")
        out.append("")

    # ---- cards that helped and hurt
    out += ["## Cards that helped and hurt", "",
            "Per deck: the win rate in games where the card was drawn at least once, the win rate in games where it "
            "stayed in the deck, and the difference in percentage points. Only cards drawn in at least 10 games are listed. "
            "This is correlation, not proof: the card was drawn in particular games, next to particular cards, against "
            "particular opponents. The hill-climb's swap test, which plays the same games with and without a card, is the causal check.", ""]
    for i in order:
        rows = [(cid, s) for cid, s in t.card_stats[i].items() if s.iwd is not None and s.drawn_games >= 10]
        rows.sort(key=lambda x: (-x[1].iwd, x[0]))
        if not rows:
            continue
        out += [f"**{names[i]}**", "",
                "| Card | Won when drawn | Won when not drawn | Difference | Games drawn |", "|---|---|---|---|---|"]
        for row in top_and_bottom(rows):
            if row is None:
                out.append("| … | | | | |")
                continue
            cid, s = row
            out.append(f"| {card_name(reg, cid)} | {100 * s.gih:.0f}% | {100 * s.gnd:.0f}% | "
                       f"{100 * s.iwd:+.0f} | {s.drawn_games} |")
        out.append("")

    out += GLOSSARY
    return "\n".join(out) + "\n"


GLOSSARY = [
    "## How to read this report", "",
    "- **Win rate** — games won divided by games played, against every opponent. The range in brackets is a 95% "
    "confidence interval: the values the deck's true win rate could plausibly have, given this many games. Fewer games "
    "make the range wider; when two decks' ranges overlap heavily, the games have not separated them.",
    "- **Strength** — a Bradley–Terry rating fitted to all matchups at once. 1.0 is an average deck in this field; a deck "
    "rated 2.0 is expected to win about 67% of its games against an average deck (2 ÷ (2 + 1)), one rated 0.5 about 33%. "
    "Unlike the plain win rate it accounts for who each deck actually played.",
    "- **Bring it?** — how often a player who must pick a deck blind for exactly this field should bring it: the mix "
    "(a Nash equilibrium of the head-to-head results) that no other mix beats. 100% on one deck means nothing here beats "
    "it; a split means the decks counter each other.",
    "- **Statistically solid** — a matchup result far enough from 50–50 that luck alone would rarely produce it. The "
    "test is corrected for looking at many matchups at once (Benjamini–Hochberg false-discovery rate): \"solid\" means the "
    "adjusted value q is below 0.05, so among all results marked solid we expect fewer than one in twenty to be flukes; "
    "\"very solid\" is q below 0.01, \"suggestive\" is q below 0.2, and everything else is \"not established\". Results "
    "resting on fewer than 30 games are flagged, because small samples swing.",
    "- **Games differ per matchup** — a matchup stopped as soon as a sequential test (an SPRT) found one deck clearly "
    "ahead, or the two clearly even, so lopsided matchups used few games and close ones ran to the cap.",
    "- **Won when drawn / when not drawn** — of the games in which the deck drew a card at least once, the share it won; "
    "and the same for the games where the card stayed in the deck. **Difference** is the first minus the second, in "
    "percentage points. It is correlational, so a large number is a lead to test, not a proof.",
    "- **Archetype** — a kind of deck learned from play, not written down in advance: the lab groups every deck that "
    "has played by its shape numbers (average cost, share of Units, removal, Gig cards, economy, …) and names each "
    "group after the two features that set it apart, such as \"Low-curve swarm\". A builder labelled \"exploring\" "
    "was not aiming at any group: it invented a shape at random, which is how new archetypes get found. The "
    "Archetypes table pools the decks of each group so a group can be judged as a whole.",
    "- **Shape** — a few numbers that describe the list itself: the curve (average cost), the share of Units, the "
    "share of cards with a sell tag, and how many blockers, removal effects, Gig-manipulation cards, haste, economy, "
    "extra-steal and draw effects it runs. These are the numbers archetypes are learned from.",
    "- **Changes this generation** — in a league each builder tries single-card swaps, playing the same games with the "
    "old and the new card; a swap is accepted only when the new card wins clearly more of the games that came out "
    "differently.",
    "- **Mirrored games** — every random seed is played twice with the seats swapped, so neither deck gains from going "
    "first more often.",
]
