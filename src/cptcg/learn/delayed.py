"""The delayed-reward suite: positions where the greedy move is not the winning move.

This is the falsifiability instrument for the whole training loop. The claim the loop makes is
that a value function trained on outcomes learns to play a sequence whose *early* moves look
worthless — the plan's "A then B then C, low, low, high" against "X then Y then Z, medium, medium,
low". A one-ply agent compares A against X on immediate impact and takes X. If a generation cannot
raise its score here, the loop is not doing what the plan claims, and that has to be visible.

What a position is
------------------

A position qualifies only when **both** halves hold:

1. a winning line exists — an exhaustive search over the acting player's own decisions for this
   turn finds a sequence that wins the game, and
2. the frozen heuristic does **not** find it — playing the same turn with ``agents.heuristic``
   does not win, on every trial seed.

The second half is what makes the suite discriminating rather than merely hard. A position both
agents win is not evidence about planning; a position neither can win is not a target.

How "wins" is defined, precisely
--------------------------------

Reaching seven Gigs does not end the game where it happens: ``steps.WinCheckStep`` runs at the
*start* of a turn (CR 8.6), so a turn that gets to seven wins at the start of the player's next
turn — unless the rival takes the Gigs back or wins first in between. So the goal predicate here is
not "seven Gigs on the board" but the real thing: after the searched turn ends, the game is played
on with the **frozen heuristic in both seats** through the rival's whole turn, and the line counts
as a win only if the game then actually ends with the searched player as the winner
(:func:`confirmed_win`).

That makes the verification concrete and replayable, and it costs one honest caveat: the rival's
reply is one competent line and one sample of their Gig die, not a proof against every defence. A
position is a *witness* that a win was available against that defence, not a game-theoretic value.

The solver
----------

:func:`turn_search` is a depth-first search over the acting player's own decisions until the turn
passes, with the rival's decisions inside the turn answered by a fixed policy (the frozen
heuristic, rebuilt per decision so the answer is a pure function of the position and the traversal
order cannot change it). It is exhaustive **up to two stated limits**:

* a node cap (``max_nodes`` clones) and a depth cap (``max_depth`` of the player's own decisions
  in one turn); hitting either reports ``exhausted=False`` — a search that found nothing under a
  cap has proved nothing;
* the same option-equivalence the frozen agent uses (``heuristic._equiv_key``): two options that
  differ only in *which copy* of a card they name are treated as one.

It stops at the first win, because existence is all the suite needs.

Two ways in, one file
---------------------

*Hand-built* positions are written as a board spec — the same shape as ``tests/conftest.board`` —
and rebuilt by :func:`build_position`. *Mined* positions are found by :func:`mine`, which scans
self-play games for turns where the solver finds a win the heuristic misses, and stores them as a
replay prefix ``(seed, decks, actions so far)``, which reproduces the position exactly.

Both live in ``data/arena/delayed.json`` **with their verification**: the winning line, the node
count, and the heuristic's failure. :func:`verify_suite` re-derives all of it from scratch, so a
stored claim that stops being true is a test failure and not a silent lie.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cptcg.agents.base import make_agent
from cptcg.agents.heuristic import _equiv_key
from cptcg.cards.registry import Registry
from cptcg.core.actions import Choice, ChoiceKind
from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.enums import DICE, Zone
from cptcg.core.legal import main_menu
from cptcg.core.rng import Pcg32
from cptcg.core.state import GameState
from cptcg.core.steps import EndTurnStep
from cptcg.deck.decklist import Decklist
from cptcg.learn.decks import sample_pair

ROOT = Path(__file__).resolve().parents[3]

#: The stored suite. Data, not code: every position carries its own verification.
SUITE_PATH = ROOT / "data" / "arena" / "delayed.json"

#: Clones the solver may spend on one position before giving up. A search that hits this has
#: proved nothing, and says so (``Solution.exhausted``).
MAX_NODES = 30_000

#: How many of the acting player's own decisions one turn may contain in the search.
MAX_DEPTH = 14

#: Steps the win confirmation may play out after the searched turn ends.
MAX_FINISH = 400

#: Agent seeds a position is scored on. A position qualifies only if the frozen heuristic misses
#: the win on *every* one of these, so a lucky tie-break cannot create a fake target.
TRIAL_SEEDS = (1, 2, 3, 4)

#: The policy that answers everything the searched player does not decide, and that plays out the
#: rival's reply. The frozen shipping agent: a competent, non-adversarial defence.
POLICY_AGENT = "heuristic"
POLICY_SEED = 20260910


class NodeBudget(Exception):
    """Raised inside the solver when the node cap is reached."""


# ------------------------------------------------------------------ policies
def fixed_policy(agent: str = POLICY_AGENT, seed: int = POLICY_SEED):
    """A decision policy that is a **pure function of the position**.

    An agent object carries RNG state, so re-using one across a search tree would make each branch
    depend on how many decisions the branches before it happened to make, and a stored line would
    stop reproducing. Building the agent fresh for each decision costs a ``Pcg32`` and removes the
    problem entirely.
    """
    def pick(s: GameState, ch: Choice) -> int:
        ag = make_agent(agent, seed)
        ag.new_game(seed, ch.player)
        return ag.act(s, ch)
    return pick


def _materialise(s: GameState) -> Choice:
    legal_actions(s)
    return s.pending


# ------------------------------------------------------------- win confirmation
def could_win(s: GameState, me: int) -> bool:
    """A cheap precondition for :func:`confirmed_win`, and the definition of what counts.

    A turn can only produce a win here by ending with the winning Gig count on ``me``'s side (the
    check fires at the start of their next turn) or by ending the game outright. Everything else —
    most importantly the rival decking out on their own turn, which happens whatever ``me`` does —
    is not a consequence of the line being searched, and playing every leaf out to look for those
    would cost the solver a whole rival turn per leaf.
    """
    return bool(s.over) or len(s.gig[me]) >= s.cfg.gigs_to_win


def confirmed_win(s: GameState, me: int, *, policy=None, max_steps: int = MAX_FINISH) -> bool:
    """Did ``me`` actually win, once the searched turn is played out to its consequence?

    The Gig win is checked at the start of a turn, so this plays on — both seats on ``policy`` —
    until the game ends or ``me``'s next turn begins without it ending. Reaching seven Gigs and
    then having them stolen back is therefore not a win here, which is the point.
    """
    policy = policy or fixed_policy()
    if not could_win(s, me):
        return False
    c = s.clone()
    if c.over:
        return c.winner == me
    start = c.turn
    for _ in range(max_steps):
        if c.over or c.pending is None:
            break
        if c.active == me and c.turn > start:
            break                          # my next turn began and the win check did not fire
        ch = _materialise(c)
        apply(c, policy(c, ch))
    return bool(c.over) and c.winner == me


# ------------------------------------------------------------------ the solver
@dataclass
class Solution:
    """What the exhaustive turn search found."""

    won: bool
    line: list[int] = field(default_factory=list)
    nodes: int = 0
    #: True only when the whole turn tree was walked. False when a cap stopped it first — the node
    #: cap, or the depth cap on how many of the player's own decisions one turn may contain.
    exhausted: bool = True

    def to_json(self) -> dict:
        return {"won": self.won, "line": list(self.line), "nodes": self.nodes,
                "exhausted": self.exhausted}


def _own_options(s: GameState) -> list[int]:
    """Indices of the pending choice, one per equivalence class (``heuristic._equiv_key``)."""
    opts = legal_actions(s)
    seen = set()
    out = []
    for i, o in enumerate(opts):
        k = _equiv_key(s, o)
        if k in seen:
            continue
        seen.add(k)
        out.append(i)
    return out


def turn_search(s: GameState, me: int, *, max_nodes: int = MAX_NODES, max_depth: int = MAX_DEPTH,
                policy=None) -> Solution:
    """Exhaustively search ``me``'s own decisions for this turn for a line that wins the game.

    Stops at the first win. ``Solution.exhausted`` is True only when the whole tree was walked
    inside both ``max_nodes`` and ``max_depth``; a search that ran out of budget has ruled nothing
    out, and says so rather than reporting "no win here".
    """
    policy = policy or fixed_policy()
    state = {"nodes": 0, "truncated": False}
    start_turn = s.turn

    def over(c: GameState) -> bool:
        """The searched turn is finished: the game ended, or the turn counter moved on."""
        return bool(c.over) or c.turn != start_turn or c.pending is None

    def step_out(c: GameState) -> None:
        """Answer everything that is not ``me``'s decision, until the turn passes or ends."""
        guard = 0
        while not over(c) and c.pending.player != me and guard < 64:
            guard += 1
            ch = _materialise(c)
            apply(c, policy(c, ch))

    def dfs(node: GameState, line: list[int], depth: int) -> list[int] | None:
        if depth >= max_depth:
            state["truncated"] = True          # a turn longer than the depth cap: not exhaustive
            return None
        for i in _own_options(node):
            if state["nodes"] >= max_nodes:
                raise NodeBudget
            c = node.clone()
            state["nodes"] += 1
            apply(c, i)
            step_out(c)
            here = line + [i]
            # A leaf is the end of the turn — or, if step_out somehow ran out of its guard, a
            # decision that is not mine to make, which is played out rather than searched into.
            if over(c) or c.pending.player != me:
                if confirmed_win(c, me, policy=policy):
                    return here
                continue
            found = dfs(c, here, depth + 1)
            if found is not None:
                return found
        return None

    try:
        line = dfs(s, [], 0)
    except NodeBudget:
        return Solution(False, [], state["nodes"], exhausted=False)
    return Solution(line is not None, line or [], state["nodes"],
                    exhausted=not state["truncated"])


def replay_line(s: GameState, me: int, line, *, policy=None) -> bool:
    """Play a stored line back from ``s`` and report whether it really wins."""
    policy = policy or fixed_policy()
    c = s.clone()
    start_turn = c.turn
    it = iter(line)
    guard = 0
    while not c.over and c.pending is not None and c.turn == start_turn and guard < 400:
        guard += 1
        ch = _materialise(c)
        if ch.player == me:
            nxt = next(it, None)
            if nxt is None:
                break
            apply(c, nxt)
        else:
            apply(c, policy(c, ch))
    return confirmed_win(c, me, policy=policy)


def play_turn(s: GameState, me: int, agent_name: str, *, seed: int = 1, policy=None) -> tuple[bool, list[int]]:
    """Let ``agent_name`` play ``me``'s turn from ``s``; return (did it win, the line it chose)."""
    policy = policy or fixed_policy()
    c = s.clone()
    ag = make_agent(agent_name, seed)
    ag.new_game(seed, me)
    start_turn = c.turn
    line: list[int] = []
    guard = 0
    while not c.over and c.pending is not None and c.turn == start_turn and guard < 400:
        guard += 1
        ch = _materialise(c)
        if ch.player == me:
            i = ag.act(c, ch)
            line.append(i)
        else:
            i = policy(c, ch)
        apply(c, i)
    return confirmed_win(c, me, policy=policy), line


# ------------------------------------------------------------- building positions
def _eddie_card(reg: Registry):
    """The filler card the Eddies area is built from, matching ``tests/conftest.board``."""
    return reg.get("T-P1") if "T-P1" in reg.by_id else reg.get("floor-it")


def _place(s: GameState, reg: Registry, p: int, spec, zone: Zone) -> int:
    cid, opts = (spec[0], spec[1]) if isinstance(spec, (list, tuple)) else (spec, {})
    inst = s.new_instance(reg.get(cid).idx, p, zone)
    s.i_spent[inst] = 1 if opts.get("spent") else 0
    s.i_lag[inst] = 1 if opts.get("lag") else 0
    s.i_faceup[inst] = 1 if opts.get("faceup") else 0
    s.i_flags[inst] = opts.get("flags", 0)
    for gid in opts.get("gear", ()):
        g = s.new_instance(reg.get(gid).idx, p, zone)
        s.i_host[g] = inst
    return inst


def build_position(reg: Registry, spec: dict, cfg: RulesConfig = DEFAULT_CONFIG) -> GameState:
    """A hand-built mid-game state at the start of ``active``'s main phase.

    The same construction as ``tests/conftest.board``, driven by JSON instead of Python so that a
    suite position is data. ``tests/learn/test_delayed_reward.py`` pins the two together.
    """
    s = GameState(cfg, reg, spec.get("seed", 1))
    s.turn = spec.get("turn", 3)
    s.active = spec.get("active", 0)
    s.first_player = spec.get("first_player", 0)
    tt = spec.get("turns_taken")
    s.turns_taken = list(tt) if tt else [s.turn // 2, s.turn // 2]
    s.overtime = bool(spec.get("overtime", False))
    for p, side in enumerate(spec["sides"]):
        for key, zone in (("deck", Zone.DECK), ("hand", Zone.HAND), ("field", Zone.FIELD),
                          ("legends", Zone.LEGENDS), ("trash", Zone.TRASH)):
            for item in side.get(key, ()):
                _place(s, reg, p, item, zone)
        eddie = _eddie_card(reg)
        spent = side.get("spent_eddies", 0)
        for k in range(side.get("eddies", 0)):
            e = s.new_instance(eddie.idx, p, Zone.EDDIES)
            s.i_spent[e] = 1 if k < spent else 0
        s.gig[p] = [tuple(g) for g in side.get("gig", ())]
        s.fixer[p] = list(side["fixer"]) if "fixer" in side else list(DICE)
    s.invalidate()
    s.stack.append(EndTurnStep())
    s.pending = Choice(ChoiceKind.MAIN, s.active, tuple(main_menu(s)))
    return s


def build_from_replay(reg: Registry, entry: dict, cfg: RulesConfig = DEFAULT_CONFIG) -> GameState:
    """Rebuild a mined position by replaying its game up to the decision it was found at."""
    decks = (Decklist.from_counts(entry["decks"][0]["name"], entry["decks"][0]["legends"],
                                  entry["decks"][0]["main"]),
             Decklist.from_counts(entry["decks"][1]["name"], entry["decks"][1]["legends"],
                                  entry["decks"][1]["main"]))
    s = new_game(reg, decks, entry["seed"], cfg, record=True)
    for idx in entry["prefix"]:
        legal_actions(s)
        apply(s, idx)
    legal_actions(s)
    return s


def build_entry(reg: Registry, entry: dict, cfg: RulesConfig = DEFAULT_CONFIG) -> GameState:
    """A suite entry, whichever way it was made, as a live state at its decision."""
    if entry["kind"] == "board":
        return build_position(reg, entry["spec"], cfg)
    if entry["kind"] == "replay":
        return build_from_replay(reg, entry, cfg)
    raise ValueError(f"unknown position kind {entry['kind']!r}")


# ------------------------------------------------------------------ qualification
def qualify(reg: Registry, entry: dict, *, max_nodes: int = MAX_NODES,
            trial_seeds=TRIAL_SEEDS, cfg: RulesConfig = DEFAULT_CONFIG) -> dict:
    """Decide whether a candidate position belongs in the suite, and record the evidence.

    Returns the ``verified`` block: the winning line the solver found, what it cost, and the frozen
    heuristic's failure to find it on every trial seed. ``ok`` is the conjunction of both halves.
    """
    s = build_entry(reg, entry, cfg)
    me = entry.get("player", s.pending.player)
    gigs_before = len(s.gig[me])
    t0 = time.perf_counter()
    sol = turn_search(s, me, max_nodes=max_nodes)
    misses = []
    for seed in trial_seeds:
        won, line = play_turn(s, me, POLICY_AGENT, seed=seed)
        misses.append({"seed": seed, "won": won, "line": line})
    heuristic_wins = sum(1 for m in misses if m["won"])
    return {"ok": bool(sol.won) and heuristic_wins == 0,
            "player": me, "gigs_before": gigs_before,
            "line": sol.line, "nodes": sol.nodes, "exhausted": sol.exhausted,
            "solver_found_win": sol.won,
            "heuristic_seeds": list(trial_seeds), "heuristic_wins": heuristic_wins,
            "heuristic_lines": misses,
            "policy": f"{POLICY_AGENT}(seed {POLICY_SEED}) for the rival and the reply",
            "rules": cfg.digest(), "seconds": round(time.perf_counter() - t0, 2),
            "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}


# ------------------------------------------------------------------ the miner
def _at_a_main_decision(s: GameState) -> bool:
    ch = s.pending
    return ch is not None and ch.kind is ChoiceKind.MAIN and ch.player == s.active


def mine(reg: Registry, *, games: int = 40, seed: int = 0, agent: str = POLICY_AGENT,
         max_nodes: int = 4_000, min_gigs: int | None = None, limit: int | None = None,
         cfg: RulesConfig = DEFAULT_CONFIG, progress=None) -> list[dict]:
    """Scan self-play games for turns where a win exists that the frozen heuristic does not take.

    Only the **first** main-phase decision of a turn is examined — that is where a whole turn is
    still ahead, which is what "plan the turn" means — and only when the acting player is within
    reach of the win, because a solver that cannot possibly find a win is only burning nodes.

    Positions are stored as a replay prefix, so re-deriving one is exact and costs no board spec.
    """
    if min_gigs is None:
        min_gigs = cfg.gigs_to_win - 2
    rng = Pcg32(seed, seq=404)
    found: list[dict] = []
    scanned = examined = 0
    for g in range(games):
        decks = sample_pair(reg, rng)
        gseed = seed * 7919 + g
        s = new_game(reg, decks, gseed, cfg, record=True)
        agents = [make_agent(agent, gseed * 2 + i) for i in range(2)]
        for p, ag in enumerate(agents):
            ag.new_game(gseed, p)
        seen_turn = -1
        guard = 0
        while not s.over and guard < 20_000:
            guard += 1
            legal_actions(s)
            ch = s.pending
            if (_at_a_main_decision(s) and s.turn != seen_turn
                    and len(s.gig[s.active]) >= min_gigs):
                seen_turn = s.turn
                scanned += 1
                me = s.active
                sol = turn_search(s.clone(), me, max_nodes=max_nodes)
                if sol.won:
                    examined += 1
                    entry = {"id": f"mined-{gseed}-{len(s.actions)}", "kind": "replay",
                             "player": me, "source": f"mined from {agent} self-play",
                             "why": ("a win was available this turn and the frozen heuristic did "
                                     "not take it"),
                             "seed": gseed, "prefix": list(s.actions),
                             "decks": [_deck_json(decks[0]), _deck_json(decks[1])]}
                    v = qualify(reg, entry, max_nodes=max_nodes, cfg=cfg)
                    if v["ok"]:
                        entry["verified"] = v
                        found.append(entry)
                        if progress:
                            progress(entry, v)
                        if limit and len(found) >= limit:
                            return found
            apply(s, agents[ch.player].act(s, ch))
        if progress:
            progress(None, {"games": g + 1, "scanned": scanned, "wins_found": examined,
                            "qualified": len(found)})
    return found


def _deck_json(d: Decklist) -> dict:
    return {"name": d.name, "legends": list(d.legends), "main": d.counts()}


# ------------------------------------------------------------------ the suite
def load_suite(path: str | Path = SUITE_PATH,
               *, rules: str | None = DEFAULT_CONFIG.digest()) -> dict:
    """Read the suite, refusing one verified under a different ruleset.

    A changed ruling makes a stored line a line in a different game, so scoring an agent against a
    stale suite would produce a number that means nothing. ``rules=None`` reads anything, which is
    what re-verification and mining need in order to repair the file.
    """
    suite = json.loads(Path(path).read_text(encoding="utf-8"))
    if rules is not None and suite.get("rules") != rules:
        raise ValueError(
            f"{path}: the suite was verified under ruleset {suite.get('rules')}, this build is "
            f"{rules}. Re-verify it (`arena delayed --verify`) and update 'rules' before scoring "
            f"anything against it.")
    return suite


def save_suite(suite: dict, path: str | Path = SUITE_PATH) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(suite, indent=1) + "\n", encoding="utf-8")
    return p


def requalify_suite(reg: Registry, suite: dict, *, max_nodes: int = MAX_NODES,
                    cfg: RulesConfig = DEFAULT_CONFIG, progress=None) -> tuple[dict, list[str]]:
    """Re-derive every stored ``verified`` block with the current code, and return the failures.

    The file's numbers must be the ones this build produces, not the ones some earlier build did,
    so the suite can always be regenerated by the shipped tool rather than by whatever script
    happened to make it.
    """
    dropped = []
    for e in suite["positions"]:
        v = qualify(reg, e, max_nodes=max_nodes, cfg=cfg)
        e["verified"] = v
        if not v["ok"]:
            dropped.append(e["id"])
        if progress:
            progress(e, v)
    suite["rules"] = cfg.digest()
    return suite, dropped


def verify_suite(reg: Registry, suite: dict, *, max_nodes: int = MAX_NODES,
                 cfg: RulesConfig = DEFAULT_CONFIG) -> list[dict]:
    """Re-derive every stored claim: the line still wins, and the heuristic still misses it."""
    out = []
    for e in suite["positions"]:
        s = build_entry(reg, e, cfg)
        me = e.get("player", s.pending.player)
        stored = e.get("verified", {})
        line_ok = bool(stored.get("line")) and replay_line(s, me, stored["line"])
        wins = [play_turn(s, me, POLICY_AGENT, seed=sd)[0]
                for sd in stored.get("heuristic_seeds", TRIAL_SEEDS)]
        out.append({"id": e["id"], "stored_line_wins": line_ok,
                    "heuristic_wins": sum(wins),
                    "ok": line_ok and not any(wins)})
    return out


def score_agent(reg: Registry, suite: dict, agent: str, *, trial_seeds=TRIAL_SEEDS,
                cfg: RulesConfig = DEFAULT_CONFIG, progress=None) -> dict:
    """"Solved N of M": how many suite positions ``agent`` actually wins.

    A position counts as solved only when the agent wins it on **every** trial seed, so a lucky
    tie-break is not a solve. The per-seed detail is kept, because a position solved on two seeds
    of four is a real signal that something is being learned.
    """
    rows = []
    for e in suite["positions"]:
        s = build_entry(reg, e, cfg)
        me = e.get("player", s.pending.player)
        trials = []
        for sd in trial_seeds:
            won, line = play_turn(s, me, agent, seed=sd)
            trials.append({"seed": sd, "won": won, "line": line})
        wins = sum(1 for t in trials if t["won"])
        rows.append({"id": e["id"], "source": e.get("source", ""), "why": e.get("why", ""),
                     "wins": wins, "trials": len(trials), "solved": wins == len(trials),
                     "detail": trials})
        if progress:
            progress(rows[-1])
    solved = sum(1 for r in rows if r["solved"])
    partial = sum(r["wins"] for r in rows)
    return {"agent": agent, "solved": solved, "positions": len(rows),
            "trial_wins": partial, "trials": len(rows) * len(trial_seeds),
            "rules": cfg.digest(), "suite_version": suite.get("version"),
            "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "rows": rows}


def render_score(out: dict) -> str:
    lines = [f"### Delayed-reward suite: {out['agent']} — {out['when']}", "",
             f"**Solved {out['solved']} of {out['positions']}** "
             f"({out['trial_wins']} of {out['trials']} trials won). Every position has a verified "
             f"winning line that the frozen heuristic does not find; a position counts as solved "
             f"only when the agent wins it on every trial seed.", "",
             "| position | source | trials won | solved |", "|---|---|---:|---|"]
    for r in out["rows"]:
        lines.append(f"| `{r['id']}` | {r['source']} | {r['wins']}/{r['trials']} | "
                     f"{'yes' if r['solved'] else 'no'} |")
    lines += ["", "The win is confirmed by playing the turn out and the rival's whole reply with "
                  "the frozen heuristic in both seats, so a line that reaches seven Gigs and has "
                  "them stolen back does not count. That reply is one competent defence and one "
                  "sample of the rival's Gig die, not a proof against every defence."]
    return "\n".join(lines) + "\n"
