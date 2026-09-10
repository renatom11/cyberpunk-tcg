"""Round-robin tournaments with honest statistics.

Every unordered pair of decks is one match cell, played as mirrored seed pairs in batches.
With SPRT on, a cell stops as soon as the evidence settles (a lopsided matchup takes a few
dozen games) so the budget goes to the close ones; the stopping n is recorded per cell.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.deck.decklist import Decklist
from cptcg.sim.runner import GameResult, run_match
from cptcg.sim.stats import (SPRT, bh_fdr, binomial_p_two_sided, bradley_terry, bt_predicted,
                             nash_fictitious_play, wilson)


@dataclass
class Cell:
    i: int
    j: int
    wins_i: int = 0
    n: int = 0
    verdict: str = "continue"          # SPRT verdict when stopped
    i_first_wins: int = 0              # wins for i when i went first
    i_first_n: int = 0
    turns: int = 0
    results: list[GameResult] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.wins_i / self.n if self.n else 0.5

    def add(self, results: list[GameResult]) -> None:
        for r in results:
            self.n += 1
            self.turns += r.turns
            if r.winner_deck == "A":
                self.wins_i += 1
            if r.first_deck == "A":
                self.i_first_n += 1
                if r.winner_deck == "A":
                    self.i_first_wins += 1
        self.results += results


@dataclass
class CardStat:
    drawn_games: int = 0
    drawn_wins: int = 0
    other_games: int = 0
    other_wins: int = 0

    @property
    def gih(self) -> float | None:
        return self.drawn_wins / self.drawn_games if self.drawn_games else None

    @property
    def gnd(self) -> float | None:
        return self.other_wins / self.other_games if self.other_games else None

    @property
    def iwd(self) -> float | None:
        return None if self.gih is None or self.gnd is None else self.gih - self.gnd


@dataclass
class Tournament:
    decks: list[Decklist]
    agent: str
    seed: int
    cells: dict[tuple[int, int], Cell]
    card_stats: list[dict[str, CardStat]]      # per deck: card id -> stats
    info: dict = field(default_factory=dict)   # how the run was made: caps, test, time, league context
    paths: list = field(default_factory=list)  # per deck: where its file was saved (None = unknown)

    JSON_VERSION = 2

    # ---------------------------------------------------------- derived
    def n(self) -> int:
        return len(self.decks)

    def wins_matrix(self) -> list[list[int]]:
        n = self.n()
        w = [[0] * n for _ in range(n)]
        for (i, j), c in self.cells.items():
            w[i][j] = c.wins_i
            w[j][i] = c.n - c.wins_i
        return w

    def rate(self, i: int, j: int) -> tuple[int, int]:
        """(wins, games) of i against j."""
        if i == j:
            return 0, 0
        c = self.cells.get((min(i, j), max(i, j)))
        if c is None:
            return 0, 0
        return (c.wins_i, c.n) if i < j else (c.n - c.wins_i, c.n)

    def field_rates(self) -> list[tuple[int, int]]:
        n = self.n()
        out = []
        for i in range(n):
            k = g = 0
            for j in range(n):
                a, b = self.rate(i, j)
                k += a
                g += b
            out.append((k, g))
        return out

    def qvalues(self) -> dict[tuple[int, int], float]:
        keys = list(self.cells)
        ps = [binomial_p_two_sided(self.cells[k].wins_i, self.cells[k].n) for k in keys]
        return dict(zip(keys, bh_fdr(ps)))

    def bt(self) -> list[float]:
        return bradley_terry(self.wins_matrix())

    def residuals(self) -> list[list[float]]:
        n = self.n()
        pred = bt_predicted(self.bt())
        res = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                k, g = self.rate(i, j)
                if g:
                    res[i][j] = k / g - pred[i][j]
        return res

    def nash(self) -> list[float]:
        n = self.n()
        pay = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                k, g = self.rate(i, j)
                pay[i][j] = (k / g - 0.5) if g else 0.0
        return nash_fictitious_play(pay)

    def standings(self) -> list[int]:
        bt = self.bt()
        return sorted(range(self.n()), key=lambda i: -bt[i])

    def deck_path(self, i: int):
        return self.paths[i] if i < len(self.paths) else None

    def to_json(self, reg=None) -> dict:
        """Everything a report needs, computed once. ``reg`` (default: the standard registry)
        resolves card names for the summary sentences and the deck profiles."""
        from cptcg.sim.report import deck_profile_json, profile_sentence, registry, summarize
        reg = registry(reg)
        n = self.n()
        bt = self.bt()
        nash = self.nash()
        q = self.qvalues()
        profiles = [deck_profile_json(d, reg) for d in self.decks]
        return {
            "version": self.JSON_VERSION,
            "agent": self.agent, "seed": self.seed, "rules": DEFAULT_CONFIG.digest(),
            "info": dict(self.info),
            "decks": [{"name": d.name, "legends": list(d.legends), "main": d.counts(),
                       "meta": dict(d.meta), "profile": profiles[i],
                       "shape": profile_sentence(profiles[i]) if profiles[i] else None, "path": self.deck_path(i)}
                      for i, d in enumerate(self.decks)],
            "cells": [{"i": c.i, "j": c.j, "wins_i": c.wins_i, "n": c.n, "verdict": c.verdict,
                       "wilson": list(wilson(c.wins_i, c.n)), "q": q[(c.i, c.j)],
                       "i_first": [c.i_first_wins, c.i_first_n], "avg_turns": c.turns / max(1, c.n)}
                      for c in self.cells.values()],
            "field": [{"wins": k, "games": g} for k, g in self.field_rates()],
            "bradley_terry": bt, "residuals": self.residuals(), "nash": nash,
            "standings": self.standings(),
            "summary": summarize(self, reg, bt=bt, nash=nash, q=q),
            "cards": [{cid: {"drawn_games": s.drawn_games, "drawn_wins": s.drawn_wins,
                             "other_games": s.other_games, "other_wins": s.other_wins}
                       for cid, s in stats.items()} for stats in self.card_stats],
        }

    def save(self, path: str | Path, reg=None) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(reg), f, indent=1)

    @classmethod
    def from_json(cls, data: dict) -> "Tournament":
        """Rebuild a tournament from a saved file (version 1 or 2). The per-game results are not
        stored, so ``cells[...].results`` is empty; every rating is recomputed from the counts."""
        decks = [Decklist.from_counts(d["name"], d["legends"], d["main"], **dict(d.get("meta") or {}))
                 for d in data["decks"]]
        cells: dict[tuple[int, int], Cell] = {}
        for c in data["cells"]:
            cell = Cell(c["i"], c["j"], c["wins_i"], c["n"], c.get("verdict", "continue"))
            first = c.get("i_first") or [0, 0]
            cell.i_first_wins, cell.i_first_n = int(first[0]), int(first[1])
            cell.turns = int(round(float(c.get("avg_turns", 0.0)) * cell.n))
            cells[(cell.i, cell.j)] = cell
        card_stats = [{cid: CardStat(s["drawn_games"], s["drawn_wins"], s["other_games"], s["other_wins"])
                       for cid, s in stats.items()} for stats in data.get("cards", [])]
        while len(card_stats) < len(decks):
            card_stats.append({})
        info = dict(data.get("info") or {})
        paths = [d.get("path") for d in data["decks"]]
        return cls(decks, data.get("agent", "heuristic"), int(data.get("seed", 0)), cells, card_stats, info, paths)

    @classmethod
    def load(cls, path: str | Path) -> "Tournament":
        with open(path, encoding="utf-8") as f:
            return cls.from_json(json.load(f))


def _update_card_stats(stats: dict[str, CardStat], deck: Decklist, drawn: frozenset, won: bool) -> None:
    for cid in set(deck.main):
        st = stats.setdefault(cid, CardStat())
        if cid in drawn:
            st.drawn_games += 1
            st.drawn_wins += won
        else:
            st.other_games += 1
            st.other_wins += won


def run_tournament(decks: list[Decklist], agent: str = "heuristic", games_per_pair: int = 200,
                   seed: int = 0, workers: int | None = None, sprt: SPRT | None = None,
                   batch: int = 40, cfg: RulesConfig = DEFAULT_CONFIG, progress=None) -> Tournament:
    """Round robin. ``games_per_pair`` is the cap per cell; with ``sprt`` a cell may stop earlier.
    Cells are played in batches of ``batch`` games (mirrored pairs) so the test is checked
    between batches. The result is identical for any worker count."""
    n = len(decks)
    cells = {(i, j): Cell(i, j) for i in range(n) for j in range(i + 1, n)}
    card_stats = [dict() for _ in range(n)]
    active = list(cells)
    offset = 0
    t0 = time.perf_counter()
    while active:
        still = []
        for key in active:
            c = cells[key]
            take = min(batch, games_per_pair - c.n)
            if take <= 0:
                continue
            m = run_match(decks[c.i], decks[c.j], agent, agent, take, seed=seed + offset + 100_000 * (c.i * n + c.j),
                          cfg=cfg, workers=workers)
            c.add(m.results)
            for r in m.results:
                _update_card_stats(card_stats[c.i], decks[c.i], r.drawn_a, r.winner_deck == "A")
                _update_card_stats(card_stats[c.j], decks[c.j], r.drawn_b, r.winner_deck == "B")
            if sprt is not None:
                c.verdict = sprt.test(c.wins_i, c.n)
            if progress:
                progress(decks[c.i].name, decks[c.j].name, c.wins_i, c.n, c.verdict)
            if c.n < games_per_pair and (sprt is None or c.verdict == "continue"):
                still.append(key)
        active = still
        offset += batch
    info = {"games_per_pair": games_per_pair, "batch": batch,
            "sprt": None if sprt is None else {"delta": sprt.delta, "alpha": sprt.alpha, "beta": sprt.beta},
            "total_games": sum(c.n for c in cells.values()),
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "title": None}
    return Tournament(decks, agent, seed, cells, card_stats, info)
