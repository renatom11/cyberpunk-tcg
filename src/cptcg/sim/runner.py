"""Play games and matches.

Mirrored seed pairing: each seed is played twice with the decks' seats swapped, so first-player
advantage and shuffle luck cancel between the two decks. Results are reproducible from the seed
regardless of how many worker processes ran them.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

from cptcg.agents.base import make_agent
from cptcg.cards.registry import Registry, load_default
from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.deck.decklist import Decklist
from cptcg.sim.record import Replay


@dataclass(frozen=True, slots=True)
class GameResult:
    seed: int
    deck_a_seat: int          # which seat (0/1) deck A sat in
    winner_deck: str          # "A" | "B"
    end_reason: str
    turns: int
    first_deck: str           # which deck went first
    replay: Replay | None = None
    drawn_a: frozenset = frozenset()   # card ids deck A drew this game
    drawn_b: frozenset = frozenset()


@dataclass
class MatchSummary:
    deck_a: str
    deck_b: str
    agent_a: str
    agent_b: str
    results: list[GameResult] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.results)

    @property
    def a_wins(self) -> int:
        return sum(1 for r in self.results if r.winner_deck == "A")

    def split(self):
        """(A wins when A first, games A first, A wins when B first, games B first)."""
        af = [r for r in self.results if r.first_deck == "A"]
        bf = [r for r in self.results if r.first_deck == "B"]
        return (sum(r.winner_deck == "A" for r in af), len(af),
                sum(r.winner_deck == "A" for r in bf), len(bf))

    def reasons(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.results:
            out[r.end_reason] = out.get(r.end_reason, 0) + 1
        return out

    def avg_turns(self) -> float:
        return sum(r.turns for r in self.results) / max(1, self.n)


def play_game(reg: Registry, decks: tuple[Decklist, Decklist], agent_names: tuple[str, str],
              seed: int, cfg: RulesConfig = DEFAULT_CONFIG, record: bool = False, max_actions: int = 50_000):
    agents = [make_agent(n, seed * 2 + i) for i, n in enumerate(agent_names)]
    s = new_game(reg, decks, seed, cfg, record=record)
    for p, a in enumerate(agents):
        a.new_game(seed, p)
    n = 0
    while not s.over:
        legal_actions(s)
        ch = s.pending
        apply(s, agents[ch.player].act(s, ch))
        n += 1
        if n > max_actions:
            # Name the game, not just the seed. A seed alone is not enough to replay this: the same
            # number is reused across pairings and across both seat assignments, and re-deriving
            # which one it was from an arena traceback means guessing at the seed arithmetic. This
            # ceiling means an agent is cycling, and the only way to find out which one is to be
            # able to play the exact game again.
            raise RuntimeError(
                f"game {seed} exceeded {max_actions} actions: "
                f"{decks[0].name!r} ({agent_names[0]}) vs {decks[1].name!r} ({agent_names[1]}), "
                f"turn {s.turn}, active {s.active}, pending {getattr(s.pending, 'kind', None)}")
    return s


# --- worker plumbing -------------------------------------------------------------
_REG: Registry | None = None

# Every finished game is counted here, whichever executor ran it, so a long job can report
# progress and an ETA.
GAMES_PLAYED = 0

# A pluggable executor for environments without processes (the browser build): called with the
# list of chunk jobs as JSON (see jobs_to_json) and must return the results as JSON, in order.
EXECUTOR = None


def _cfg_to_json(cfg: RulesConfig) -> dict:
    return asdict(cfg)


def _cfg_from_json(d: dict) -> RulesConfig:
    return DEFAULT_CONFIG if d == asdict(DEFAULT_CONFIG) else RulesConfig(**d)


def _deck_to_json(d: Decklist) -> dict:
    return {"name": d.name, "legends": list(d.legends), "main": list(d.main), "meta": dict(d.meta)}


def _deck_from_json(d: dict) -> Decklist:
    return Decklist(d["name"], tuple(d["legends"]), tuple(d["main"]), dict(d.get("meta", {})))


def jobs_to_json(jobs: list) -> str:
    return json.dumps([{"deck_a": _deck_to_json(a), "deck_b": _deck_to_json(b), "agent_a": aa, "agent_b": ab,
                        "seeds": list(seeds), "cfg": _cfg_to_json(cfg), "record": record}
                       for a, b, aa, ab, seeds, cfg, record in jobs])


def result_to_json(r: GameResult) -> dict:
    return {"seed": r.seed, "deck_a_seat": r.deck_a_seat, "winner_deck": r.winner_deck, "end_reason": r.end_reason,
            "turns": r.turns, "first_deck": r.first_deck, "replay": asdict(r.replay) if r.replay else None,
            "drawn_a": sorted(r.drawn_a), "drawn_b": sorted(r.drawn_b)}


def result_from_json(d: dict) -> GameResult:
    rep = d.get("replay")
    if rep is not None:
        rep = Replay(**dict(rep, decks=tuple(rep["decks"]), agents=tuple(rep["agents"])))
    return GameResult(d["seed"], d["deck_a_seat"], d["winner_deck"], d["end_reason"], d["turns"], d["first_deck"],
                      rep, frozenset(d["drawn_a"]), frozenset(d["drawn_b"]))


def run_chunk_json(job_json: str) -> str:
    """Entry point for an external worker: one chunk job in, its results out (both JSON)."""
    j = json.loads(job_json)
    args = (_deck_from_json(j["deck_a"]), _deck_from_json(j["deck_b"]), j["agent_a"], j["agent_b"],
            j["seeds"], _cfg_from_json(j["cfg"]), bool(j["record"]))
    return json.dumps([result_to_json(r) for r in _run_chunk(args)])


def _worker_init() -> None:
    global _REG
    _REG = load_default()


load_registry = _worker_init     # external workers warm the card registry once


def _run_chunk(args) -> list[GameResult]:
    deck_a, deck_b, agent_a, agent_b, seeds, cfg, record = args
    reg = _REG or load_default()
    out = []
    for seed in seeds:
        for a_seat in (0, 1):
            decks = (deck_a, deck_b) if a_seat == 0 else (deck_b, deck_a)
            names = (agent_a, agent_b) if a_seat == 0 else (agent_b, agent_a)
            s = play_game(reg, decks, names, seed, cfg, record=record)
            winner_deck = "A" if s.winner == a_seat else "B"
            first_deck = "A" if s.first_player == a_seat else "B"
            rep = Replay.from_game(s, decks, names) if record else None
            drawn = ([], [])
            for inst in s.drawn:
                drawn[s.i_owner[inst]].append(s.card(inst).id)
            out.append(GameResult(seed, a_seat, winner_deck, s.end_reason.name, s.turn, first_deck, rep,
                                  frozenset(drawn[a_seat]), frozenset(drawn[1 - a_seat])))
    return out


def run_match(deck_a: Decklist, deck_b: Decklist, agent_a: str, agent_b: str, n_games: int,
              seed: int = 0, cfg: RulesConfig = DEFAULT_CONFIG, workers: int | None = None,
              record: bool = False, progress=None) -> MatchSummary:
    """Play ``n_games`` (rounded up to even) as mirrored pairs, in parallel."""
    pairs = max(1, (n_games + 1) // 2)
    seeds = [seed + i for i in range(pairs)]
    workers = workers or max(1, os.cpu_count() or 1)
    chunk = max(1, pairs // (workers * 4))
    chunks = [seeds[i:i + chunk] for i in range(0, pairs, chunk)]
    summary = MatchSummary(deck_a.name, deck_b.name, agent_a, agent_b)
    jobs = [(deck_a, deck_b, agent_a, agent_b, c, cfg, record) for c in chunks]
    global GAMES_PLAYED
    if EXECUTOR is not None and workers > 1 and len(jobs) > 1:
        for chunk_json in json.loads(EXECUTOR(jobs_to_json(jobs))):
            res = [result_from_json(d) for d in chunk_json]
            summary.results += res
            GAMES_PLAYED += len(res)
            if progress:
                progress(summary.n)
    elif workers == 1 or EXECUTOR is not None:
        _worker_init()
        for j in jobs:
            res = _run_chunk(j)
            summary.results += res
            GAMES_PLAYED += len(res)
            if progress:
                progress(summary.n)
    else:
        from concurrent.futures import ProcessPoolExecutor   # lazily: the browser build has no processes
        with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as ex:
            for res in ex.map(_run_chunk, jobs):
                summary.results += res
                GAMES_PLAYED += len(res)
                if progress:
                    progress(summary.n)
    summary.results.sort(key=lambda r: (r.seed, r.deck_a_seat))
    return summary
