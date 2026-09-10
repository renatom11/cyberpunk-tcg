"""The delayed-reward suite: positions where the greedy move is not the winning move.

This is the falsifiability instrument for the whole training loop. The claim the loop makes is
that a value function trained on outcomes learns to play a sequence whose *early* moves look
worthless — the plan's "A then B then C, low, low, high" against "X then Y then Z, medium, medium,
low". A one-ply agent compares A against X on immediate impact and takes X. If a generation cannot
raise its score here, the loop is not doing what the plan claims, and that has to be visible.

What a position is
------------------

A position qualifies only when **all three** hold:

1. a winning line exists — an exhaustive search over the acting player's own decisions for this
   turn finds a sequence after which the game is won inside the position's **horizon**
   (``max_turns``, below) and, past a horizon of one, a sequence that leaves the winning Gig count
   still *off* the board when the turn ends: the reward has to be genuinely invisible to an agent
   scoring the board one ply later, and
2. the frozen heuristic does **not** find it, on any of the seeds the suite scores agents on, and
3. **random play does not stumble into it often**: uniform random play over the same turn wins at
   most :data:`MAX_FLOOR` of the scoring seeds. A position many lines win is not a planning test,
   it is a coin toss, and the suite says so with a number rather than hoping.

The first is what makes a position a *delayed* reward rather than a puzzle; the second is what
makes the suite discriminating rather than merely hard; the third is what makes "solved N of M"
readable, because without it the floor is not zero and nobody says so.

The horizon: what "wins" means, precisely
-----------------------------------------

Reaching seven Gigs does not end the game where it happens: ``steps.WinCheckStep`` runs at the
*start* of a turn (CR 8.6), so a turn that gets to seven wins at the start of the player's next
turn — unless the rival takes the Gigs back or wins first in between. So the goal predicate is not
"seven Gigs on the board" but the real thing: after the searched turn ends, the game is played on
with the **frozen heuristic in both seats**, and the line counts as a win only if the game then
actually ends with the searched player as the winner (:func:`confirmed_win`).

``max_turns`` says how far that play-on may run, counted in the searched player's own turns:

* ``max_turns=1`` — the win must be there at the start of their very next turn. Everything the
  line is worth is banked inside the searched turn: **within-turn sequencing**.
* ``max_turns=2`` — the play-on continues through the rival's answer, the searched player's *next*
  turn (played greedily, by the frozen heuristic) and the rival's answer to that. The searched turn
  cannot win by itself, and qualification insists on it: the winning Gig count must still be off
  the board when that turn ends, so there is nothing there for a one-ply agent to score. What the
  line leaves behind is a board a *greedy* continuation converts a turn later. That is a reward
  arriving **after the move that earned it**, which is the thing the plan says a one-ply agent
  cannot see, and the thing the first version of this suite could not hold.

Both live in the same suite, each position carrying its own ``max_turns``, and
:func:`render_score` prints the horizon per position so a reader always knows which claim a row is
evidence for.

What the suite does **not** measure: it is not a search over multi-turn *plans*. Only the searched
turn's own decisions are chosen by the solver or by the scored agent; every later turn, on both
sides, is played by the frozen policy. A horizon-2 position therefore asks "is there a move here
whose payoff lands next turn, and do you make it", not "can you plan two turns of your own". The
full two-turn tree is not tractable, and not by a little: on fourteen of fifteen sampled mid-game
turns one turn's own tree passed 30,000 clones without exhausting, at about 12,000 leaves, so
crossing it with a second turn's tree is on the order of 3.6e8 clones — some five hours per
position at the ~20,000 clones a second this engine manages, against the ~6 s scoring an agent on
the whole suite costs today. Widening the *goal* was affordable; widening the *search* was not.

The floor
---------

Every position stores what **uniform random play** scores on it, measured on exactly the seeds
agents are scored on, and :func:`render_score` prints it as a column beside the agent's own. That
is the floor a result has to be read against. The frozen heuristic's zero is *not* the floor: it is
a selection criterion — a position is only in the suite because the heuristic missed it on those
very seeds — so its zero is true by construction, and the number that is actually measured is the
random column.

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
count, the heuristic's failure and the random floor. :func:`verify_suite` re-derives all of it from
scratch, so a stored claim that stops being true is a test failure and not a silent lie.
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

#: Steps the win confirmation may play out per turn of horizon after the searched turn ends.
MAX_FINISH = 400

#: The seeds every agent is scored on, and the seeds the floor is measured on. Sixteen, so that a
#: position random play wins a quarter of the time cannot be passed by luck: 0.25**16 is 1 in 4
#: billion, and even one random wins six times in ten would need 0.6**16, about 3 in 10,000.
SCORE_SEEDS = tuple(range(101, 117))

#: The extra seeds used only to select positions. A position is *chosen* partly because the frozen
#: heuristic missed it, so its miss is checked on the scoring seeds as well: the heuristic's zero is
#: then true by construction on exactly the seeds it is reported on, which is what the docs say.
TRIAL_SEEDS = (1, 2, 3, 4)

#: Every seed the frozen heuristic has to miss for a position to qualify.
QUALIFY_SEEDS = TRIAL_SEEDS + SCORE_SEEDS

#: The floor agent: uniform random play over the same turn. Not an opponent — a control.
FLOOR_AGENT = "random"

#: The most of :data:`SCORE_SEEDS` random play may win and the position still qualify. A position
#: random wins more often than this is not a planning test; the suite refuses it rather than
#: reporting a solve that a coin could have produced.
MAX_FLOOR = 0.25

#: How far past the searched turn a win may land, counted in the searched player's own turns.
#: 1 is within-turn sequencing; 2 is a payoff that arrives the turn after the move that earned it.
DEFAULT_MAX_TURNS = 1

#: Node caps the miner searches a candidate under, by horizon. At a horizon of one most leaves are
#: rejected by :func:`could_win` without playing anything out, so a wide search is cheap; at two
#: every leaf costs a rival turn and one of ``me``'s, so a candidate with no win in it costs about
#: a minute at 4,000 nodes and thirteen seconds at 600. Wins, when they exist, are found in the
#: first few dozen nodes — every horizon-2 position in the stored suite was found inside 90 — so
#: the smaller budget costs very little and makes mining practical. A candidate that hits the cap
#: is reported ``exhausted=False`` and proves nothing either way.
MINE_NODES = {1: 4_000, 2: 600}

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
    """The cheap precondition for a **horizon-1** win, and the definition of what counts there.

    Inside one turn a win can only come from ending with the winning Gig count on ``me``'s side
    (the check fires at the start of their next turn) or from ending the game outright. Everything
    else — most importantly the rival decking out on their own turn, which happens whatever ``me``
    does — is not a consequence of the line being searched, and playing every leaf out to look for
    those would cost the solver a whole rival turn per leaf.

    At a horizon of two or more this is no longer a precondition and is not used: the whole point
    of the wider goal is that the board at the end of the searched turn does *not* yet show the
    win, so :func:`confirmed_win` plays it out instead.
    """
    return bool(s.over) or len(s.gig[me]) >= s.cfg.gigs_to_win


def confirmed_win(s: GameState, me: int, *, policy=None, max_steps: int | None = None,
                  max_turns: int = DEFAULT_MAX_TURNS) -> bool:
    """Did ``me`` actually win, once the searched turn is played out to its consequence?

    The Gig win is checked at the start of a turn, so this plays on — both seats on ``policy`` —
    until the game ends or ``me`` has begun ``max_turns`` further turns without it ending.
    Reaching seven Gigs and then having them stolen back is therefore not a win here, which is the
    point.

    ``max_turns=1`` stops the moment ``me``'s next turn begins: everything the searched turn was
    worth had to be banked inside it. ``max_turns=2`` lets that next turn be played out, greedily,
    by ``policy``, and stops at the start of the one after: the searched turn then wins by leaving
    a board a greedy continuation converts, which is a reward one turn later than the move.
    """
    policy = policy or fixed_policy()
    if max_turns <= 1 and not could_win(s, me):
        return False
    if max_steps is None:
        max_steps = MAX_FINISH * max_turns
    c = s.clone()
    if c.over:
        return c.winner == me
    start = c.turn
    my_turns = 0
    for _ in range(max_steps):
        if c.over or c.pending is None:
            break
        if c.active == me and c.turn > start:
            my_turns += 1                  # one of my turns began and the win check did not fire
            start = c.turn
            if my_turns >= max_turns:
                break
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
                max_turns: int = DEFAULT_MAX_TURNS, policy=None) -> Solution:
    """Exhaustively search ``me``'s own decisions for this turn for a line that wins the game.

    Stops at the first win. ``Solution.exhausted`` is True only when the whole tree was walked
    inside both ``max_nodes`` and ``max_depth``; a search that ran out of budget has ruled nothing
    out, and says so rather than reporting "no win here".

    ``max_turns`` is the horizon the leaves are judged against (:func:`confirmed_win`), **not** a
    number of turns to search: the decisions searched are always this turn's, and later turns are
    played by ``policy`` on both sides. Widening it makes every leaf expensive, because
    :func:`could_win` can no longer reject one without playing it out — at a horizon of two a leaf
    costs a rival turn plus one of ``me``'s, so a position whose turn tree has a couple of thousand
    leaves takes about a minute instead of a second.
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
                if confirmed_win(c, me, policy=policy, max_turns=max_turns):
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


def replay_to_end_of_turn(s: GameState, me: int, line, *, policy=None) -> GameState:
    """Play a stored line back from ``s`` and return the state the searched turn ended in.

    Separate from :func:`replay_line` so the board a line *leaves* can be looked at on its own —
    which is the whole content of a delayed position, where that board does not yet show the win.
    """
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
    return c


def replay_line(s: GameState, me: int, line, *, policy=None,
                max_turns: int = DEFAULT_MAX_TURNS) -> bool:
    """Play a stored line back from ``s`` and report whether it really wins inside the horizon."""
    policy = policy or fixed_policy()
    end = replay_to_end_of_turn(s, me, line, policy=policy)
    return confirmed_win(end, me, policy=policy, max_turns=max_turns)


def play_turn(s: GameState, me: int, agent_name: str, *, seed: int = 1, policy=None,
              max_turns: int = DEFAULT_MAX_TURNS) -> tuple[bool, list[int]]:
    """Let ``agent_name`` play ``me``'s turn from ``s``; return (did it win, the line it chose).

    The agent chooses this turn and nothing else: past the end of it both seats are the frozen
    policy, for as many of ``me``'s turns as the position's horizon allows. Solver and agent are
    therefore compared on exactly the same decisions.
    """
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
    return confirmed_win(c, me, policy=policy, max_turns=max_turns), line


def floor_rate(s: GameState, me: int, *, seeds=SCORE_SEEDS, agent: str = FLOOR_AGENT,
               max_turns: int = DEFAULT_MAX_TURNS, policy=None) -> tuple[int, int]:
    """How often ``agent`` — uniform random by default — wins the position by itself.

    Returned as (wins, trials) so the caller can print the fraction rather than a rounded rate.
    This is the floor "solved N of M" has to be read against: several positions are winnable by
    many lines rather than by one, and a suite that does not say so is not readable as progress.
    """
    wins = 0
    for sd in seeds:
        if play_turn(s, me, agent, seed=sd, policy=policy, max_turns=max_turns)[0]:
            wins += 1
    return wins, len(tuple(seeds))


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
def entry_horizon(entry: dict) -> int:
    """The horizon a position was qualified at, in the searched player's own turns.

    Stored per position, because scoring an agent at a different horizon than the one the position
    was selected under would compare two different claims. Absent means 1: the shape every position
    in the first version of the suite had.
    """
    return int(entry.get("max_turns", DEFAULT_MAX_TURNS))


def qualify(reg: Registry, entry: dict, *, max_nodes: int = MAX_NODES,
            trial_seeds=QUALIFY_SEEDS, score_seeds=SCORE_SEEDS,
            cfg: RulesConfig = DEFAULT_CONFIG) -> dict:
    """Decide whether a candidate position belongs in the suite, and record the evidence.

    Returns the ``verified`` block: the winning line the solver found, what it cost, the frozen
    heuristic's failure to find it on every seed the suite ever reports, and the random floor.
    ``ok`` is the conjunction of the whole definition — a win exists inside the horizon and, past a
    horizon of one, is still off the board when the turn ends; the heuristic misses it; and random
    play does not stumble into it more than :data:`MAX_FLOOR` of the time.
    """
    s = build_entry(reg, entry, cfg)
    me = entry.get("player", s.pending.player)
    horizon = entry_horizon(entry)
    gigs_before = len(s.gig[me])
    t0 = time.perf_counter()
    sol = turn_search(s, me, max_nodes=max_nodes, max_turns=horizon)
    misses = []
    heuristic_wins = 0
    for seed in trial_seeds:
        won, line = play_turn(s, me, POLICY_AGENT, seed=seed, max_turns=horizon)
        heuristic_wins += int(won)
        if seed in TRIAL_SEEDS or won:
            misses.append({"seed": seed, "won": won, "line": line})
    floor_wins, floor_trials = floor_rate(s, me, seeds=score_seeds, max_turns=horizon)
    floor = floor_wins / floor_trials if floor_trials else 0.0
    # A horizon-2 position whose line leaves the winning Gig count sitting on the board is a
    # within-turn puzzle wearing a "delayed" label: a one-ply agent scoring the board at the end of
    # its turn would see that payoff perfectly well. The reward has to still be invisible when the
    # turn ends, which is exactly ``not could_win`` there — and that in turn makes a horizon-1 win
    # impossible, so it is the stronger of the two tests and the only one worth running.
    really_late = horizon <= 1 or (
        bool(sol.won) and not could_win(replay_to_end_of_turn(s, me, sol.line), me))
    return {"ok": bool(sol.won) and heuristic_wins == 0 and floor <= MAX_FLOOR and really_late,
            "player": me, "max_turns": horizon, "reward_is_late": really_late,
            "gigs_before": gigs_before,
            "line": sol.line, "nodes": sol.nodes, "exhausted": sol.exhausted,
            "solver_found_win": sol.won,
            "heuristic_seeds": list(trial_seeds), "heuristic_wins": heuristic_wins,
            "heuristic_lines": misses,
            "floor_agent": FLOOR_AGENT, "floor_seeds": list(score_seeds),
            "floor_wins": floor_wins, "floor_trials": floor_trials,
            "floor_rate": round(floor, 3), "max_floor": MAX_FLOOR,
            "policy": f"{POLICY_AGENT}(seed {POLICY_SEED}) for the rival and the reply",
            "rules": cfg.digest(), "seconds": round(time.perf_counter() - t0, 2),
            "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}


# ------------------------------------------------------------------ the miner
def _at_a_main_decision(s: GameState) -> bool:
    ch = s.pending
    return ch is not None and ch.kind is ChoiceKind.MAIN and ch.player == s.active


def mine(reg: Registry, *, games: int = 40, seed: int = 0, agent: str = POLICY_AGENT,
         max_nodes: int | None = None, min_gigs: int | None = None, limit: int | None = None,
         max_turns: int = DEFAULT_MAX_TURNS, cfg: RulesConfig = DEFAULT_CONFIG,
         progress=None) -> list[dict]:
    """Scan self-play games for turns where a win exists that the frozen heuristic does not take.

    Only the **first** main-phase decision of a turn is examined — that is where a whole turn is
    still ahead, which is what "plan the turn" means — and only when the acting player is within
    reach of the win, because a solver that cannot possibly find a win is only burning nodes. One
    Gig of reach is allowed per turn of horizon: at ``max_turns=1`` that is ``gigs_to_win - 2``
    (steal two and the check fires next turn), at 2 one lower.

    The three tests run cheapest-first, which matters at a horizon of two where the solver costs a
    minute and the other two cost a second: the heuristic must miss the turn, random must not win
    it more than :data:`MAX_FLOOR` of the time, and only then is the tree searched.

    Positions are stored as a replay prefix, so re-deriving one is exact and costs no board spec.
    """
    if min_gigs is None:
        min_gigs = cfg.gigs_to_win - 1 - max_turns
    if max_nodes is None:
        max_nodes = MINE_NODES.get(max_turns, min(MINE_NODES.values()))
    rng = Pcg32(seed, seq=404)
    found: list[dict] = []
    scanned = skipped_heuristic = skipped_floor = examined = 0
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
                here = s.clone()
                # Cheapest first: a turn the frozen agent already wins is not a target at all.
                if any(play_turn(here, me, POLICY_AGENT, seed=sd, max_turns=max_turns)[0]
                       for sd in QUALIFY_SEEDS):
                    skipped_heuristic += 1
                elif floor_rate(here, me, max_turns=max_turns)[0] > MAX_FLOOR * len(SCORE_SEEDS):
                    skipped_floor += 1                      # random wins it: a coin toss, not a plan
                else:
                    entry = {"id": f"mined-{gseed}-{len(s.actions)}", "kind": "replay",
                             "player": me, "max_turns": max_turns,
                             "source": f"mined from {agent} self-play",
                             "why": _mined_why(max_turns),
                             "seed": gseed, "prefix": list(s.actions),
                             "decks": [_deck_json(decks[0]), _deck_json(decks[1])]}
                    v = qualify(reg, entry, max_nodes=max_nodes, cfg=cfg)
                    examined += int(v["solver_found_win"])
                    if v["ok"]:
                        entry["verified"] = v
                        found.append(entry)
                        if progress:
                            progress(entry, v)
                        if limit and len(found) >= limit:
                            return found
            apply(s, agents[ch.player].act(s, ch))
        if progress:
            progress(None, {"games": g + 1, "scanned": scanned,
                            "skipped_heuristic_wins_it": skipped_heuristic,
                            "skipped_random_wins_it": skipped_floor,
                            "wins_found": examined, "qualified": len(found)})
    return found


def _mined_why(max_turns: int) -> str:
    if max_turns <= 1:
        return "a win was available inside this turn and the frozen heuristic did not take it"
    return (f"a line here wins within {max_turns} of my turns and the frozen heuristic does not "
            f"play it. The turn it ends still has the winning Gig count off the board, so nothing "
            f"an agent scoring one ply later can see is what makes it right; the rival answers, "
            f"and the payoff arrives on the following turn under greedy play")


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
    """Re-derive every stored claim: the line still wins inside the position's horizon and, past a
    horizon of one, still does *not* win inside the turn; the heuristic still misses it; and the
    floor is still the number the file says it is."""
    out = []
    for e in suite["positions"]:
        s = build_entry(reg, e, cfg)
        me = e.get("player", s.pending.player)
        horizon = entry_horizon(e)
        stored = e.get("verified", {})
        line_ok = bool(stored.get("line")) and replay_line(s, me, stored["line"],
                                                           max_turns=horizon)
        # For a horizon of two or more: the turn must end with the win still off the board.
        late_ok = horizon <= 1 or not could_win(
            replay_to_end_of_turn(s, me, stored["line"]), me)
        wins = [play_turn(s, me, POLICY_AGENT, seed=sd, max_turns=horizon)[0]
                for sd in stored.get("heuristic_seeds", QUALIFY_SEEDS)]
        floor_wins, floor_trials = floor_rate(
            s, me, seeds=stored.get("floor_seeds", SCORE_SEEDS),
            agent=stored.get("floor_agent", FLOOR_AGENT), max_turns=horizon)
        floor_ok = (floor_wins == stored.get("floor_wins", floor_wins)
                    and floor_wins <= MAX_FLOOR * floor_trials)
        out.append({"id": e["id"], "max_turns": horizon, "stored_line_wins": line_ok,
                    "reward_is_late": late_ok, "heuristic_wins": sum(wins),
                    "floor_wins": floor_wins, "floor_trials": floor_trials,
                    "floor_matches_stored": floor_ok,
                    "ok": line_ok and late_ok and not any(wins) and floor_ok})
    return out


def score_agent(reg: Registry, suite: dict, agent: str, *, trial_seeds=SCORE_SEEDS,
                cfg: RulesConfig = DEFAULT_CONFIG, progress=None) -> dict:
    """"Solved N of M": how many suite positions ``agent`` actually wins, against the floor.

    A position counts as solved only when the agent wins it on **every** scoring seed. With sixteen
    seeds and a floor capped at a quarter, that is a solve no floor-level agent reaches by luck
    (0.25**16). The per-seed detail is kept, because a position won on six seeds of sixteen is a
    real signal even though it is not a solve, and each row carries the floor beside it so the
    number is readable without going back to the data file.
    """
    rows = []
    for e in suite["positions"]:
        s = build_entry(reg, e, cfg)
        me = e.get("player", s.pending.player)
        horizon = entry_horizon(e)
        stored = e.get("verified", {})
        trials = []
        for sd in trial_seeds:
            won, line = play_turn(s, me, agent, seed=sd, max_turns=horizon)
            trials.append({"seed": sd, "won": won, "line": line})
        wins = sum(1 for t in trials if t["won"])
        rows.append({"id": e["id"], "source": e.get("source", ""), "why": e.get("why", ""),
                     "max_turns": horizon,
                     "wins": wins, "trials": len(trials), "solved": wins == len(trials),
                     "floor_agent": stored.get("floor_agent", FLOOR_AGENT),
                     "floor_wins": stored.get("floor_wins"),
                     "floor_trials": stored.get("floor_trials"),
                     "detail": trials})
        if progress:
            progress(rows[-1])
    solved = sum(1 for r in rows if r["solved"])
    partial = sum(r["wins"] for r in rows)
    floor_wins = sum(r["floor_wins"] or 0 for r in rows)
    floor_trials = sum(r["floor_trials"] or 0 for r in rows)
    return {"agent": agent, "solved": solved, "positions": len(rows),
            "trial_wins": partial, "trials": len(rows) * len(trial_seeds),
            "floor_agent": FLOOR_AGENT, "floor_trial_wins": floor_wins,
            "floor_trials": floor_trials,
            "horizons": sorted({r["max_turns"] for r in rows}),
            "rules": cfg.digest(), "suite_version": suite.get("version"),
            "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "rows": rows}


def render_score(out: dict) -> str:
    by_h = {}
    for r in out["rows"]:
        by_h.setdefault(r["max_turns"], []).append(r)
    names = {1: "one turn (won inside the searched turn)",
             2: "two turns (the payoff lands after the rival's answer)"}
    horizons = ", ".join(f"{len(v)} at a horizon of {names.get(k, str(k) + ' turns')}"
                         for k, v in sorted(by_h.items()))
    lines = [f"### Delayed-reward suite: {out['agent']} — {out['when']}", "",
             f"**Solved {out['solved']} of {out['positions']}** "
             f"({out['trial_wins']} of {out['trials']} trials won), against a floor of "
             f"{out['floor_trial_wins']} of {out['floor_trials']} trials for uniform "
             f"{out['floor_agent']} play. Every position has a verified winning line that the "
             f"frozen heuristic does not find on any of these seeds; a position counts as solved "
             f"only when the agent wins it on every one of them. The suite holds {horizons}.", "",
             "| position | source | horizon | trials won | floor | solved |",
             "|---|---|---:|---:|---:|---|"]
    for r in out["rows"]:
        floor = ("—" if r["floor_wins"] is None
                 else f"{r['floor_wins']}/{r['floor_trials']}")
        lines.append(f"| `{r['id']}` | {r['source']} | {r['max_turns']} | "
                     f"{r['wins']}/{r['trials']} | {floor} | "
                     f"{'yes' if r['solved'] else 'no'} |")
    lines += ["",
              "**Horizon** is how far past the searched turn the win may land, counted in the "
              "searched player's own turns. At 1 the line wins inside the turn; at 2 the searched "
              "turn cannot win by itself and has to leave a board the frozen policy converts on "
              "the following turn — a reward that arrives after the move that earned it. Only the "
              "searched turn is chosen by the agent either way: the suite measures which line you "
              "take *this* turn, not whether you can plan two of them.",
              "",
              "**Floor** is uniform random play over the same turn, on the same seeds, stored "
              "when the position was qualified. Read the agent's column against it, not against "
              "the frozen heuristic's zero: the heuristic scores zero here by construction, "
              "because missing these positions on these seeds is how they were selected.",
              "",
              "The win is confirmed by playing the turn out and the rival's whole reply with the "
              "frozen heuristic in both seats, so a line that reaches seven Gigs and has them "
              "stolen back does not count. That reply is one competent defence and one sample of "
              "the rival's Gig die, not a proof against every defence."]
    return "\n".join(lines) + "\n"
