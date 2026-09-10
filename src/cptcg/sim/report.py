"""Plain-English reports for a tournament.

Everything a reader sees is produced here, once, in Python: the summary sentences
(``summarize``), the significance wording (``sig_word``), how the games were played
(``how_played``), who played them and what that is worth (``disclosure``), the deck shape numbers
(``deck_profile_json``) and the Markdown document (``render_report``). The web page prints the
same sentences from the JSON, so the words are unit-tested and never duplicated in JavaScript.

Statistics are described honestly: an interval is a range of plausible values, "statistically
solid" means the false-discovery-adjusted q is below 0.05, a rock–paper–scissors pattern is only
asserted when the residual is at least two standard errors, and the card table is correlational.
"""

from __future__ import annotations

import math
from datetime import datetime

from cptcg.sim.stats import wilson
from cptcg.sim.tournament import CardStat, Tournament

_REG = None
THIN_GAMES = 20          # a card-table side resting on fewer games than this is marked "thin"
MIN_CARD_GAMES = 10      # a card is listed only when drawn, and not drawn, in at least this many games


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


def deck_label(t: Tournament, i: int) -> str | None:
    """What the tables print for a deck's archetype: the kind it was built toward, and — for a
    hand-built deck, an Explorer deck, or a deck whose archetype no longer exists in the store
    — the nearest current archetype, marked as such (``nearest: Removal wall``,
    ``exploring, nearest: Removal wall``, ``Old name, now nearest: Removal wall``)."""
    kind = deck_kind(t.decks[i])
    near = t.info.get("nearest") or []
    nearest = near[i] if i < len(near) else None
    if kind and nearest:
        meta = getattr(t.decks[i], "meta", None) or {}
        stale = bool(meta.get("archetype_id")) and kind != "exploring"     # built toward a group that is gone
        return f"{kind}, now nearest: {nearest}" if stale else f"{kind}, nearest: {nearest}"
    if kind:
        return kind
    return f"nearest: {nearest}" if nearest else None


def label_nearest(t: Tournament, store) -> list:
    """Fill ``t.info["nearest"]`` from an archetype store: the nearest archetype's name for every
    deck that was not built toward a current archetype (hand-built and Explorer decks, and decks
    whose archetype id has since vanished). None where the store has no clusters or the deck
    has an unknown card. Returns the list."""
    out = []
    for d in t.decks:
        meta = getattr(d, "meta", None) or {}
        name = None
        if store is not None and store.archetypes:
            aid = meta.get("archetype_id")
            if not aid or store.get(aid) is None or meta.get("archetype") == "exploring":
                lab = store.label(d)
                arch = store.get(lab) if lab else None
                name = arch.name if arch else None
        out.append(name)
    t.info["nearest"] = out
    return out


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
    """One line a reader can picture — ``archetypes.describe_fingerprint``: the curve, the type
    mix, and the counts of the effects the list carries."""
    from cptcg.deck.archetypes import describe_fingerprint
    return describe_fingerprint(prof)


def _pct(k: int, n: int) -> str:
    return f"{100 * k / n:.0f}%" if n else "—"


def _count(k: int, n: int) -> str:
    """``70% of 20 games``, or ``70% of only 20 games`` when the count is thin (under 30). The
    "only" replaces the separate ``(only N games)`` aside so no sentence prints the count twice."""
    return f"{_pct(k, n)} of {'only ' if 0 < n < 30 else ''}{n} games"


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


def card_rows(stats: dict) -> list:
    """The ``(card id, CardStat)`` rows of the card table, best difference first: cards drawn in
    at least ``MIN_CARD_GAMES`` games and left in the deck in at least as many."""
    rows = [(cid, s) for cid, s in stats.items()
            if s.iwd is not None and s.drawn_games >= MIN_CARD_GAMES and s.other_games >= MIN_CARD_GAMES]
    rows.sort(key=lambda x: (-x[1].iwd, x[0]))
    return rows


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


def fmt_when(iso: str | None) -> str:
    """``2026-09-10 14:17 UTC`` from the stored ISO timestamp (the raw text if it does not parse)."""
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    return d.strftime("%Y-%m-%d %H:%M") + (" UTC" if d.utcoffset() is not None and not d.utcoffset() else "")


def swap_games(info: dict) -> int:
    """Games the card-swap tests of a league generation played (the challenger's side; the
    champion played the same seeds), from ``info["climb"]``."""
    return sum(int(h.get("games", 0)) for hist in (info.get("climb") or []) if hist for h in hist)


# ------------------------------------------------------------------ how the games were played
def how_played(t: Tournament) -> str:
    """One or two sentences, computed from the cells, about how many games each matchup played
    and why: the early-stop test only shortens a matchup when the cap allows more than one
    batch, and it is described by what actually happened, not by what it could have done."""
    info = t.info or {}
    cap = info.get("games_per_pair")
    batch = int(info.get("batch") or 40)
    sprt = info.get("sprt")
    cells = list(t.cells.values())
    if not cells or not cap:
        return ""
    if not sprt:
        return f"Every matchup played the full {cap} games."
    if cap <= batch:
        return (f"Every matchup played its full {cap} games in one batch, so the early-stop test never had a "
                "chance to shorten one.")
    stopped = [c for c in cells if c.n < cap]
    ahead = [c for c in stopped if c.verdict in ("high", "low")]
    even = [c for c in stopped if c.verdict == "h0"]
    delta = f"{100 * float(sprt.get('delta', 0)):.0f}"
    head = f"Matchups were played in batches of {batch} games and checked between batches: "
    if not stopped:
        return head + f"none stopped before the cap of {cap}, so every matchup ran to the cap."
    ns = sorted({c.n for c in stopped})
    at = f"at {ns[0]} games" if len(ns) == 1 else f"at {ns[0]}–{ns[-1]} games"
    reasons = []
    if ahead:
        reasons.append(f"{len(ahead)} because one deck was clearly ahead")
    if even:
        reasons.append(f"{len(even)} because the two were clearly within {delta} points of even")
    rest = len(cells) - len(stopped)
    return (head + f"{len(stopped)} of {len(cells)} stopped before the cap of {cap} ({at}), "
            + _join(reasons) + (f"; the other {rest} ran to the cap." if rest else "."))


# ------------------------------------------------------------------ who played the games
# The honest disclosure that heads every report. It is written once here, in plain text with no
# Markdown, so the Markdown report, the web report (through ``/api/report``) and the GUIDE on the
# site all print exactly the same words. The measured figures are from 360 games per comparison
# over three deck pairings with the seats mirrored.
def disclosure(agent: str = "heuristic") -> str:
    """One paragraph naming the agent that played both sides and saying what that costs the
    reader: the ranking is conditional on that opponent, the agent's known limits, and the fact
    that nothing in this project is measured against human play."""
    never_human = ("No human games are recorded anywhere in this project, so nothing here is validated "
                   "against human play.")
    if agent == "heuristic":
        return (
            "Both sides of every game here were played by the heuristic agent, a one-ply greedy bot, so the "
            "ranking is conditional on that opponent: a deck can place highly because it exploits this bot "
            "rather than because it is good. The agent scores the board one ply ahead and cannot plan across "
            "turns; it never holds a Blocker back, because its preview assumes the rival passes on every "
            "reaction; and it always takes the largest Gig die and mulligans by a fixed rule. Over 360 games "
            "per comparison, on three deck pairings with the seats mirrored, it wins 98.6% against random play "
            "but loses 61.7% of its games to a two-ply version of itself and 59.4% to versions that never "
            "mulligan or that take the smallest die. It is a floor rather than a fraud: it plays a recognisable "
            "game, and every deck here met the same opponent, so the comparison between decks is fair \u2014 what "
            "is untested is how much of it survives a stronger player. " + never_human)
    if agent == "random":
        return (
            "Both sides of every game here were played by the random agent, which picks uniformly among the "
            "legal options and never tries to win, so these numbers say which deck wins when neither side is "
            "played at all. Read them as a check on the engine, not as a ranking of decks. " + never_human)
    return (
        f"Both sides of every game here were played by the {agent} agent, so the ranking is conditional on that "
        "opponent: a deck can place highly because it exploits that agent rather than because it is good, and a "
        "stronger opponent could order these decks differently. " + never_human)


# ------------------------------------------------------------------ the summary in words
def summarize(t: Tournament, reg=None, *, bt=None, nash=None, q=None) -> list[str]:
    """The plain-English summary: who won and how convincingly, whether its lead is established,
    whether the matchups form a rock–paper–scissors pattern, and what a player picking blind
    should bring. Each entry is one sentence; both the Markdown and the web page print them
    verbatim."""
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

    def cell_q(i, j):
        return q.get((min(i, j), max(i, j)), 1.0)

    def result(j):
        w, m = t.rate(top, j)
        return f"{names[j]} ({_pct(w, m)} of {m} games)"

    kind = deck_label(t, top)
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
    # The lead is established when the top deck beat the next-rated deck and that result is solid.
    second = order[1] if n > 1 else None
    w2, m2 = t.rate(top, second) if second is not None else (0, 0)
    established = second is not None and m2 > 0 and 2 * w2 > m2 and cell_q(top, second) < 0.05
    s = (f"{label} is the strongest deck in this run: " if established else f"{label} is rated highest in this run: ") \
        + f"it won {_pct(k, g)} of its {g} games"
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
    covered: set[int] = set()          # the next-rated deck, when the lead sentence already covers it
    if second is not None and not established and m2 > 0:
        word = _sig_parts(cell_q(top, second), m2)[0]
        detail = _count(w2, m2) + (f", {word}" if word != "not established" else "")
        if 2 * w2 > m2:
            covered.add(second)
            out.append(f"Its lead over {names[second]}, rated next, is not established ({detail}), so the top two "
                       "could swap places with more games.")
        elif 2 * w2 < m2:
            out.append(f"It is rated above {names[second]} despite losing to it ({_pct(w2, m2)} of {m2} games) "
                       "because it did better against the rest of the field; the order of the top two is not established.")
        else:
            out.append(f"It split its games evenly with {names[second]}, rated next ({w2} of {m2}), so the order of the "
                       "top two is not established.")

    # How much to trust each of the top deck's matchups, grouped by how settled they are.
    groups = {"very solid": [], "solid": [], "suggestive": [], "not established": []}
    for j in beaten:
        if j not in covered:
            groups[_sig_parts(cell_q(top, j), t.rate(top, j)[1])[0]].append(j)

    def small_note(js):
        if not any(t.rate(top, j)[1] < 30 for j in js):
            return ""
        return ("; it rests on fewer than 30 games, so keep some doubt" if len(js) == 1
                else "; some of these rest on fewer than 30 games, so keep some doubt")

    solid = groups["very solid"] + groups["solid"]
    if solid:
        strength = "very solid" if not groups["solid"] else "solid"
        out.append(f"Its {'win' if len(solid) == 1 else 'wins'} over {_join([result(j) for j in solid])} "
                   f"{'is' if len(solid) == 1 else 'are'} statistically {strength} — unlikely to be luck"
                   + ((", though it rests" if len(solid) == 1 else ", though some rest")
                      + " on fewer than 30 games, so keep some doubt." if small_note(solid) else "."))
    if groups["suggestive"]:
        js = groups["suggestive"]
        out.append(f"Its edge over {_join([result(j) for j in js])} is suggestive but not settled — "
                   "more games could still change it" + small_note(js) + ".")
    if groups["not established"]:
        js = groups["not established"]
        out.append(f"Its {'result' if len(js) == 1 else 'results'} against {_join([result(j) for j in js])} "
                   f"{'is' if len(js) == 1 else 'are'} not established — {'it' if len(js) == 1 else 'they'} could easily be noise"
                   + small_note(js) + ".")
    for j in lost:
        word = _sig_parts(cell_q(top, j), t.rate(top, j)[1])[0]
        if word in ("very solid", "solid"):
            tail = f"a statistically {word} loss"
        elif word == "suggestive":
            tail = "a suggestive but unsettled loss"
        else:
            tail = "a loss that is not established and may be noise"
        out.append(f"It lost to {names[j]} ({_count(*t.rate(top, j))}) — {tail}.")
    for j in even:
        w, m = t.rate(top, j)
        out.append(f"It split its games evenly with {names[j]} ({w} of {m}).")

    # Rock–paper–scissors: a matchup far from what the strengths predict — asserted only when
    # the gap is at least two standard errors of the observed cell, hedged otherwise.
    res = t.residuals()
    best = None
    for i in range(n):
        for j in range(n):
            if i != j and t.rate(i, j)[1] and (best is None or res[i][j] > res[best[0]][best[1]]):
                best = (i, j)
    if best is not None and res[best[0]][best[1]] > 0.12:
        i, j = best
        w, m = t.rate(i, j)
        p = w / m
        se = math.sqrt(max(p * (1 - p), 0.25 / m) / m)
        lead = (f"Not every matchup follows the ranking: {names[i]} beats {names[j]} about "
                f"{100 * res[i][j]:.0f} points more often than their strengths predict")
        if res[i][j] >= 2 * se:
            out.append(lead + " — a rock–paper–scissors pattern, so the best deck depends on what it faces.")
        else:
            out.append(lead + f", but on {m} games that could still be noise.")

    # What a player who has to pick blind should bring.
    support = sorted([i for i in range(n) if nash[i] >= 0.05], key=lambda i: -nash[i])
    if len(support) > 1:
        mix = _join([f"{names[i]} {100 * nash[i]:.0f}% of the time" for i in support])
        out.append(f"If you had to pick a deck blind for this field, bring {mix}: no single deck is safe against all the others.")
    elif support:
        i = support[0]
        holds = all(2 * t.rate(i, j)[0] >= t.rate(i, j)[1] for j in range(n) if j != i and t.rate(i, j)[1])
        s = f"If you had to pick a deck blind for this field, bring {names[i]} every time"
        if i == top:
            s += " — it holds at least even against every other deck." if holds else \
                 ": no other deck does better against this field as a whole."
        else:
            w, m = t.rate(i, top)
            word = _sig_parts(cell_q(i, top), m)[0]
            s += (f" — {names[top]} is rated higher, but {names[i]} is the only deck that held at least even against "
                  f"every other deck here, {names[top]} included ({_count(w, m)}, {word})." if holds else
                  f" — {names[top]} is rated higher, but {names[i]} does better against this field as a whole "
                  f"({_count(w, m)} against {names[top]}, {word}).")
        out.append(s)

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
                     f"games that differed, {games} games each side)")
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
    expected = t.expected_rates(bt)
    nash = t.nash()
    q = t.qvalues()
    field = t.field_rates()
    order = t.standings()
    kinds = [deck_label(t, i) for i in range(n)]
    show_kind = any(kinds)
    total = sum(c.n for c in t.cells.values())
    cap = info.get("games_per_pair")

    # ---- what was run
    facts = [f"{n} decks"]
    if cap:
        facts.append(f"up to {cap} games per pair")
    gen_of_league = bool(info.get("generation"))
    # In a league two seeds are in play — this round robin's and the league's — and the run time
    # below is the round robin alone, so both are labelled for what they are.
    facts += [f"{total} games played", f"`{t.agent}` agents on both sides",
              f"round-robin seed {t.seed}" if gen_of_league else f"seed {t.seed}"]
    if info.get("elapsed_s") is not None:
        rr = _fmt_seconds(info["elapsed_s"])
        gen_s = info.get("gen_elapsed_s")
        facts.append(f"round robin {rr} of {_fmt_seconds(gen_s)} for this generation" if gen_of_league and gen_s is not None
                     else f"round robin {rr}" if gen_of_league else f"run time {rr}")
    if info.get("finished_at"):
        facts.append(f"finished {fmt_when(info['finished_at'])}")
    out = [f"# {title}", "", "## What was run", "", " · ".join(facts), ""]
    if info.get("generation"):
        gens = info.get("generations")
        swaps = swap_games(info)
        out.append(f"Generation {info['generation']}" + (f" of {gens}" if gens else "") + " of a league"
                   + (f" (league seed {info['league_seed']}" if info.get("league_seed") is not None else "(")
                   + (f", {info['steps']} improvement steps per builder)" if info.get("steps") is not None else ")")
                   + ": each builder improved its deck by measured card swaps, then everyone played a round robin"
                   + (f" — the {total} games above are the round robin; the card-swap tests played another "
                      f"{swaps} challenger games (the champion played the same seeds)." if swaps else "."))
        out.append("")
    out.append("Every pair of decks played mirrored games: each random seed is played twice with the seats swapped, "
               "so going first evens out.")
    played = how_played(t)
    if played:
        out.append(played)
    out.append("")

    # ---- who played the games: the disclosure comes before any number a reader could take at
    # face value, because every number below is conditional on the agent that produced it.
    out += ["## Who played these games", "", disclosure(t.agent), ""]

    # ---- summary
    out += ["## Summary", ""]
    out += [f"- {s}" for s in summarize(t, reg, bt=bt, nash=nash, q=q)]
    out.append("")

    # ---- standings
    out += ["## Standings", "",
            "Win rate is over every opponent, with the 95% range of plausible values and the games it rests on. "
            "Strength is a rating fitted to all matchups at once, shown as the win rate that rating predicts against this "
            "field (the field averages 50%); the raw rating follows in brackets, where 1.0 is the field's mean rating. "
            "Bring it? is how often a player picking blind for this field should bring the deck.", "",
            "| # | Deck | " + ("Archetype | " if show_kind else "") + "Win rate (95% range, games) | Strength | Bring it? |",
            "|---|---|" + ("---|" if show_kind else "") + "---|---|---|"]
    for rank, i in enumerate(order, 1):
        k, g = field[i]
        lo, hi = wilson(k, g)
        out.append(f"| {rank} | {names[i]} | " + (f"{kinds[i] or '—'} | " if show_kind else "")
                   + f"{_pct(k, g)} ({100 * lo:.0f}–{100 * hi:.0f}%, {g}) | "
                   f"{100 * expected[i]:.0f}% expected vs this field (rating {bt[i]:.2f}) | {100 * nash[i]:.0f}% |")
    out.append("")

    if show_kind:
        groups: dict[str, list[int]] = {}
        for i in range(n):
            groups.setdefault(kinds[i] or "—", []).append(i)
        if len(groups) > 1:
            rows = sorted(groups.items(), key=lambda kv: -sum(expected[i] for i in kv[1]) / len(kv[1]))
            out += ["## Archetypes in this run", "",
                    "The same numbers pooled by kind of deck, so a building idea is judged by all the decks it produced, "
                    "not by its single best one. Strength is averaged over the group's decks and shown as an expected win "
                    "rate against this field.", "",
                    "| Archetype | Decks | Average strength | Win rate (games) | Best deck |", "|---|---|---|---|---|"]
            for kind, idxs in rows:
                k = sum(field[i][0] for i in idxs)
                g = sum(field[i][1] for i in idxs)
                best = max(idxs, key=lambda i: bt[i])
                out.append(f"| {kind} | {len(idxs)} | {100 * sum(expected[i] for i in idxs) / len(idxs):.0f}% "
                           f"(rating {sum(bt[i] for i in idxs) / len(idxs):.2f}) | {_pct(k, g)} ({g}) | {names[best]} |")
            out.append("")
        else:
            only = next(iter(groups))
            out.append(f"All {n} decks are {'Explorer builds' if only == 'exploring' else 'labelled ' + only}, so there is "
                       "no second archetype to compare them with in this run; a round robin's pooled win rate is always 50%.")
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
    fresh = set(info.get("fresh") or [])
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
        if (info.get("generation") or 0) > 1 and names[i] in fresh:
            out.append(f"- Built fresh this generation, replacing last generation's {names[i]}.")
        if climb and i < len(climb) and climb[i] is not None:
            out += _changes_lines(climb[i], reg)
        if info.get("replaced") == names[i]:
            out.append("- This builder is replaced by a fresh deck next generation.")
        out.append("")

    # ---- cards that helped and hurt
    out += ["## Cards that helped and hurt", "",
            "Per deck: the win rate in games where the card was drawn at least once, the win rate in games where it "
            f"stayed in the deck, the difference in percentage points, and the games behind each side. Only cards drawn in at "
            f"least {MIN_CARD_GAMES} games and left in the deck in at least {MIN_CARD_GAMES} are listed — the five that helped "
            "most and the three that hurt most (every card when a deck has eight or fewer); the … row stands for the cards in "
            "between. Three-of cards are drawn in most games, so the not-drawn side is often a handful of games: a difference "
            f"marked thin rests on fewer than {THIN_GAMES} games on one side and is noise until the swap test confirms it. "
            "All of it is correlation, not proof: the card was drawn in particular games, next to particular cards, against "
            "particular opponents. The hill-climb's swap test, which plays the same games with and without a card, is the causal check.", ""]
    for i in order:
        rows = card_rows(t.card_stats[i])
        if not rows:
            continue
        out += [f"**{names[i]}**", "",
                "| Card | Won when drawn | Won when not drawn | Difference | Games drawn / not drawn |", "|---|---|---|---|---|"]
        for row in top_and_bottom(rows):
            if row is None:
                out.append("| … | | | | |")
                continue
            cid, s = row
            thin = " (thin)" if min(s.drawn_games, s.other_games) < THIN_GAMES else ""
            out.append(f"| {card_name(reg, cid)} | {100 * s.gih:.0f}% | {100 * s.gnd:.0f}% | "
                       f"{100 * s.iwd:+.0f}{thin} | {s.drawn_games} / {s.other_games} |")
        out.append("")

    out += GLOSSARY
    return "\n".join(out) + "\n"


# The glossary: one (term, explanation) per entry. The Markdown prints it as a list under
# "How to read this report"; the web page prints the same entries from ``/api/report``.
GLOSSARY_ENTRIES = [
    ("Win rate", "games won divided by games played, against every opponent. The range in brackets is a 95% "
     "confidence interval: the values the deck's true win rate could plausibly have, given this many games. Fewer games "
     "make the range wider; when two decks' ranges overlap heavily, the games have not separated them."),
    ("Strength", "a Bradley–Terry rating fitted to all matchups at once, shown as the win rate that rating predicts "
     "against this field — the average, over the other decks, of rating ÷ (rating + the opponent's rating) — so the field "
     "always averages 50%. The raw rating is in brackets; 1.0 is the field's mean rating, and in a field with one dominant "
     "deck most ratings sit below it. The fit weighs a crushing loss less than the plain win rate does and copes with unequal "
     "game counts; when the two disagree, the win rate is the plain fact and the rating is the model's view."),
    ("Bring it?", "how often a player who must pick a deck blind for exactly this field should bring it: the mix "
     "(a Nash equilibrium of the head-to-head results) that no other mix beats. 100% on one deck means nothing here beats "
     "it; a split means the decks counter each other. It can disagree with the ranking: a deck that holds even against "
     "everyone is the safe pick even when another deck is rated higher on the whole."),
    ("Statistically solid", "a matchup result far enough from 50–50 that luck alone would rarely produce it. The "
     "test is corrected for looking at many matchups at once (Benjamini–Hochberg false-discovery rate): \"solid\" means the "
     "adjusted p-value q is below 0.05, so among all results marked solid we expect fewer than one in twenty to be flukes; "
     "\"very solid\" is q below 0.01, \"suggestive\" is q below 0.2, and everything else is \"not established\". The summary "
     "states the games behind every result and flags groups that rest on fewer than 30 games, because small samples swing."),
    ("Rock–paper–scissors", "a matchup whose result is far from what the two decks' strengths predict (more than 12 "
     "points). The summary asserts the pattern only when that gap is at least two standard errors of the observed result; "
     "on few games it says the gap could still be noise."),
    ("Games differ per matchup", "with the early-stop test on, a matchup is checked between batches of games and "
     "stops as soon as a sequential probability ratio test (SPRT) finds one deck clearly ahead, or the two clearly even; "
     "\"What was run\" says how many matchups actually stopped early and why. With a cap of one batch nothing can stop early."),
    ("Won when drawn / when not drawn", "of the games in which the deck drew a card at least once, the share it won; "
     "and the same for the games where the card stayed in the deck. **Difference** is the first minus the second, in "
     "percentage points, and the last column gives the games behind each side. A three-of is drawn in most games, so the "
     "not-drawn side is often thin; a difference marked thin rests on fewer than 20 games on one side. It is correlational, "
     "so a large number is a lead to test, not a proof."),
    ("Archetype", "a kind of deck learned from play, not written down in advance: the lab groups every deck that "
     "has played by its shape numbers (average cost, the type mix, removal, Gig cards, economy, …) and names each "
     "group after the two features that set it apart, such as \"Low-curve swarm\". A group is only kept when the decks "
     "really split (at least three decks each, separated more cleanly than random decks would be); until then there is one "
     "group, and every archetype carries a separation word — clearly separated, loosely grouped or provisional. A builder "
     "labelled \"exploring\" was not aiming at any group: it invented a shape at random, which is how new archetypes get "
     "found. \"nearest: X\" marks a deck that was not built toward an archetype (a hand-built or exploring deck) but whose "
     "list sits closest to X; \"now nearest\" marks a deck built toward a group that has since been renamed or merged. The "
     "Archetypes table pools the decks of each group so a group can be judged as a whole."),
    ("Shape", "a few numbers that describe the list itself: the curve (average cost), the type mix (Units, Programs, "
     "Gear — in this card set every non-Unit card can be sold, so the sellable share is the non-Unit share), and how many "
     "blockers, removal effects, Gig-manipulation cards, haste, economy, extra-steal and draw effects it runs. These are the "
     "numbers archetypes are learned from."),
    ("Changes this generation", "in a league each builder tries single-card swaps, playing the same games with the "
     "old and the new card; only the games that came out differently count. A swap is accepted when the new card wins "
     "clearly more of those — by the sequential test, or, when the game budget runs out, when it is ahead at about 90% "
     "confidence — so a few accepted swaps will be false positives. The games count is per side: the champion played the "
     "same seeds."),
    ("Mirrored games", "every random seed is played twice with the seats swapped, so neither deck gains from going "
     "first more often."),
]

GLOSSARY = ["## How to read this report", ""] + [f"- **{term}** — {text}" for term, text in GLOSSARY_ENTRIES]


def glossary_json() -> list[dict]:
    """The glossary as ``[{"term", "text"}]`` for the web page (plain text, no Markdown)."""
    return [{"term": term, "text": text.replace("**", "")} for term, text in GLOSSARY_ENTRIES]
