"""Search over whole-turn *plans* instead of one decision at a time.

**The failure this exists to fix, stated as a measurement.** ``ismcts`` builds a fresh tree on every
decision and throws it away (``ismcts._search``). A player-turn is about five of my own
multi-option decisions (median; p90 nine), so a turn costs five or nine separate searches and
**never once evaluates a complete turn**. Every leaf the value head is shown is mid-turn — after a
Gig has been banked, before a setup move has paid for itself. ``two-pieces-of-gear`` in
``data/arena/delayed.json`` is the clean case: it is a **horizon-1** position, winnable entirely
inside one turn by ``equip, equip, call, attack``, and ISMCTS at 200 iterations solves it **0 times
in 16**. The diagnostic in ``docs/learning.md`` walked that line and found the value head ranking
the winning move *last of four*, preferring ``Attack`` (+3.9026) to ``CallLegend`` (+3.0422) by 0.86
logits. It is not blind. It is being asked the wrong question, at the wrong moment.

So this agent asks a different question: not *which move is best here* but *which complete turn is
best*, with every candidate scored **at the turn boundary** — where the setup has already been paid
for and the value head is measuring a board it was calibrated on.

**Why this is affordable, and it is the arithmetic that makes the idea work at all.** A bare
``GameState.clone()`` is 4.6 us and clone+apply 8.6 us, about 117,000 a second. (The "~20,000 clones
a second" in ``docs/learning.md`` is a *search node* including the frozen-heuristic rival response,
not a state copy.) A median turn is five own decisions at about six options, so walking a whole turn
exhaustively is thousands of nodes, not millions — the verified turn trees stored in
``data/arena/delayed.json`` run 14, 31, 84, 238, 389, 574, 1405 and 6389 nodes. This is the same
order of engine work a turn already costs under ISMCTS; it is simply spent on complete turns.

**And on fourteen of fifteen sampled mid-game turns, it is not.** Those overflowed 30,000 clones
without exhausting, at roughly 12,000 leaves (``docs/learning.md``). So the budget is spent in two
phases and the fallback is stated rather than implied:

1. an exhaustive walk of my own decisions to the end of the turn, scoring every leaf, under a node
   cap and a wall-clock deadline;
2. if either cap is hit, **complete plans sampled at random** until the budget runs out, keeping the
   best line found across both phases.

The fallback deliberately samples whole plans rather than beaming over partial ones, because ranking
partial plans by the value head would reintroduce the exact mid-turn evaluation this agent exists to
avoid. Sampling uniformly is the honest placeholder: the right generator is a trained policy head,
which is what ``learn/policy.py`` is for and what it has never been fitted with.

**What is borrowed and what is not.** ``learn.delayed`` already walks a turn — ``turn_search`` asks
"does a winning line exist" for puzzle verification. The helpers are shared here (``_own_options``
for copy-dedup, ``fixed_policy`` for the rival, ``_materialise``, ``NodeBudget``) but the walk is
written out rather than parameterised, because ``turn_search``'s behaviour is what
``data/arena/delayed.json``'s stored verifications mean and it must not move underneath them.

**Hidden information, and the mistake worth writing down.** One ``determinize`` per plan search, not
per node: permuting identities is a *complete* determinization of every future draw, because
``ops.draw`` consumes no randomness. Inside my own turn there is then essentially no chance left —
the Gig die is rolled at the front of the turn, before the main phase — which is why a turn plan is
worth computing as a unit at all.

The first version stopped there, and it cost four points. ISMCTS samples a world **per iteration**,
two hundred of them per decision, and averages; this agent was picking the plan that scored best in
*one* sampled world and playing it. On the delayed suite that is invisible, because those positions
are solved or not by whether the line exists at all. In general play it is a variance disaster: the
plan chosen is the one that got the friendliest guess about the rival's hand. Measured, at matched
budget 32 — **delayed 64/128 → 110/128, panel 87.2% → 83.3%**. Better at the thing it was built for
and worse at playing.

So proposing and scoring are separated. Candidate plans are *proposed* in one world, where the walk
can be exhaustive and cheap, then **re-scored across ``worlds`` fresh determinizations** and chosen
on the mean. Re-scoring is only a replay of the plan's own actions — a handful of ``apply`` calls
each — so the second phase costs a few percent of the first, and a plan that only works when the
rival's hand is guessed kindly now loses to one that works generally. A plan whose actions stop
being legal in another world is scored *where it breaks*, because fragility is a real cost of a plan
rather than an excuse to skip the sample.

Pure stdlib, like everything under ``src/cptcg``: this package is shipped into the browser.
"""

from __future__ import annotations

import os

from cptcg.agents.base import register
from cptcg.agents.neural import NeuralAgent, position_key
from cptcg.core.actions import Choice, ChoiceKind
from cptcg.core.engine import apply, legal_actions
from cptcg.core.rng import Pcg32
from cptcg.core.state import GameState
from cptcg.core.view import determinize
from cptcg.learn.opponent import RivalPrior
from cptcg.learn.delayed import NodeBudget, _materialise, _own_options, fixed_policy
from cptcg.learn.features import features

#: Score of a finished game, from the searching seat. Large enough to dominate any logit the value
#: head produces (its observed range is single digits), small enough to stay far from inf.
WIN = 1e6

#: Nodes the exhaustive phase may expand per unit of ``iterations``. One dial controls cost, so
#: ``plan:32`` is a budget in the same sense ``ismcts:32`` is, and ``tests/props`` can make every
#: registered agent shallow by setting ``iterations`` alone.
NODES_PER_ITERATION = 64


class _Budget:
    """Nodes and wall-clock in one place, so the two phases cannot disagree about what is left."""

    __slots__ = ("nodes", "cap", "deadline")

    def __init__(self, cap: int, seconds: float) -> None:
        self.nodes = 0
        self.cap = cap
        self.deadline = None
        if seconds > 0.0:
            import time
            self.deadline = time.perf_counter() + seconds

    def spend(self) -> None:
        self.nodes += 1
        if self.nodes >= self.cap:
            raise NodeBudget
        if self.deadline is not None and (self.nodes & 63) == 0:
            import time
            if time.perf_counter() >= self.deadline:
                raise NodeBudget

    def spent_out(self) -> bool:
        if self.nodes >= self.cap:
            return True
        if self.deadline is not None:
            import time
            return time.perf_counter() >= self.deadline
        return False


@register
class PlanAgent(NeuralAgent):
    """Choose a whole turn at once, scored where the turn ends."""

    name = "plan"

    #: Samples hidden information rather than reading it, so ``cheat:plan`` is meaningful and
    #: ``tools/arena.py exploit`` can price hidden information for this agent too.
    uses_determinization = True

    #: Known or inferred rival list (Stage 0, decision 3); same switch as ``IsmctsAgent``.
    known_opponent_deck = os.environ.get("CPTCG_KNOWN_LIST", "0") == "1"

    #: The single budget dial, so ``plan:32`` means what ``ismcts:32`` means. It scales the
    #: exhaustive node cap (via ``NODES_PER_ITERATION``) and *is* the number of sampled plans the
    #: fallback may try.
    iterations = 200

    #: Wall-clock ceiling per *plan*, seconds. 0 disables it. A turn plan is computed once and then
    #: played out, so this is a per-turn budget, not a per-decision one — which is what makes the
    #: same agent usable as a ten-second oracle here and a one-second opponent in a browser.
    max_seconds = 0.0

    #: My own decisions deep one turn may go. ``learn.delayed`` uses 14 for the same walk; a turn
    #: that runs longer is truncated rather than searched, and the cycle guard below is what keeps
    #: that from being the common case.
    max_depth = 14

    #: Fresh determinizations each surviving candidate plan is re-scored in. 1 reproduces the
    #: single-world agent that scored 83.3% on the panel against gen-1's 87.2%; the cost is a replay
    #: of the plan's own actions, so this is cheap in a way the proposal phase is not.
    worlds = 8

    #: Candidate plans carried from the proposal phase into the scoring phase. Small on purpose: the
    #: proposal phase's ranking is one noisy world's opinion, so this is a shortlist to re-examine
    #: rather than a result to trust.
    candidates = 8

    #: Of my own turns played out by the frozen policy past the end of the planned turn, before a
    #: candidate is scored. 0 scores at the turn boundary, which is where the first version stopped
    #: and where it lost four panel points to ``ismcts``: a per-decision search with ``max_depth``
    #: 36 sees my turn, the rival's answer *and* my next turn, so stopping at my own boundary
    #: traded cross-turn depth for within-turn coherence and paid for it. Affordable only because
    #: it runs on the shortlist: a played-out rival turn costs milliseconds, against ~90 us for a
    #: value-head leaf, so this would be ruinous inside the proposal walk and is nothing here.
    lookahead = 1

    def __init__(self, seed: int = 0) -> None:
        super().__init__(seed)
        self._reset_plan()

    def new_game(self, seed: int, me: int) -> None:
        super().new_game(seed, me)
        self._reset_plan()

    def _reset_plan(self) -> None:
        #: Remaining steps of the current turn's plan, as ``(ChoiceKind, Action)``. Actions rather
        #: than indices because a plan is computed in a *sampled* world and played in the real one:
        #: an index would silently mean a different move if the menu came back in another shape.
        self._plan: list = []
        self._plan_turn = -1

    # ------------------------------------------------------------------ entry point
    def act(self, s: GameState, choice: Choice) -> int:
        kind = choice.kind
        # Turn order and the mulligan are one-off, pre-board decisions with no turn to plan, and
        # the frozen policies for them are inherited deliberately — same rule as ``ismcts``.
        if kind is ChoiceKind.ORDER or kind is ChoiceKind.MULLIGAN or len(choice.options) == 1:
            return super().act(s, choice)

        step = self._next_step(s, choice)
        if step is not None:
            return step

        self._plan = self._plan_turn_from(s, choice)
        self._plan_turn = s.turn
        step = self._next_step(s, choice)
        if step is not None:
            return step
        # The plan came back empty or unusable — an exhausted budget before a single leaf, or a
        # menu the sampled world could not reproduce. The greedy Stage 2 answer is the honest
        # fallback, exactly as ``ismcts._choose`` treats an unexpanded root.
        return super().act(s, choice)

    def _next_step(self, s: GameState, choice: Choice) -> int | None:
        """The plan's next move, if it is still the move this decision is asking for.

        A plan is computed against a sampled world and a *fixed* rival policy. The real rival may
        answer differently and a card may resolve differently, so the plan can stop applying
        mid-turn. Rather than trusting it, every step is re-checked against the live menu: the
        decision has to be mine, of the kind the plan expected, and the action has to still be on
        the menu. Anything else drops the plan and re-plans from here, which is cheap and is the
        only thing that keeps a stale plan from playing a move that means something else now.
        """
        if not self._plan or s.turn != self._plan_turn or choice.player != self.me:
            return None
        kind, action = self._plan[0]
        if kind is not choice.kind:
            return None
        try:
            i = choice.options.index(action)
        except ValueError:
            return None
        self._plan.pop(0)
        return i

    # ------------------------------------------------------------------ the search
    def _world(self, s: GameState):
        """One sampled world, with its own Gig die. The true state only when cheating."""
        if self.cheating:
            w = s.clone()
        elif self.known_opponent_deck:
            w = determinize(s, self.me, self.rng)
        else:
            # The inferred list (Stage 0, decision 3): identities drawn from public evidence.
            prior = RivalPrior(s, self.me)
            w = determinize(s, self.me, self.rng, known_opponent_deck=False, identities=prior.sample(self.rng))
        # Never replay the true future: the Gig die is the one chance node left and it is rolled
        # inside apply(), so each world rolls its own.
        w.rng = Pcg32(self.rng.next_u32(), seq=3)
        return w

    def _plan_turn_from(self, s: GameState, choice: Choice) -> list:
        """The best complete turn from here, as ``(ChoiceKind, Action)`` steps.

        Two phases: propose candidate plans in one world, then score the shortlist across several.
        """
        candidates = self._propose(s)
        if not candidates:
            return []
        if self.worlds <= 1 or len(candidates) == 1:
            return candidates[0][1]
        return self._best_across_worlds(s, [line for _, line in candidates])

    # ------------------------------------------------------------------ phase 1: propose
    def _propose(self, s: GameState) -> list:
        """A shortlist of complete turns, best-first, from a single sampled world."""
        rng = self.rng
        w = self._world(s)

        model = self.model
        policy = fixed_policy()
        budget = _Budget(max(1, NODES_PER_ITERATION * self.iterations), self.max_seconds)
        start_turn = w.turn
        #: key -> (score, line). Keyed by the actions themselves so the same turn found twice, by
        #: the walk and by a sample, is one candidate rather than two shortlist slots.
        found: dict = {}

        def over(c: GameState) -> bool:
            """The planned turn is finished: the game ended, or the turn counter moved on."""
            return bool(c.over) or c.turn != start_turn or c.pending is None

        def step_out(c: GameState) -> None:
            """Answer everything that is not mine to decide, until the turn passes or ends."""
            guard = 0
            while not over(c) and c.pending.player != self.me and guard < 64:
                guard += 1
                apply(c, policy(c, _materialise(c)))

        def leaf(c: GameState) -> float:
            if c.over:
                return 0.0 if c.winner is None else (WIN if c.winner == self.me else -WIN)
            return model.raw(features(c, self.me))

        def offer(score: float, line: list) -> None:
            key = tuple(a for _, a in line)
            if key not in found or score > found[key][0]:
                found[key] = (score, list(line))

        def walk(node: GameState, line: list, seen: frozenset, depth: int) -> None:
            """Exhaustive, depth-first, scoring only where the turn ends."""
            if depth >= self.max_depth:
                offer(leaf(node), line)         # judged where it stands rather than dropped
                return
            ch = _materialise(node)
            opts = ch.options
            for i in _own_options(node):
                budget.spend()
                c = node.clone()
                apply(c, i)
                step_out(c)
                key = position_key(c)
                # The pool's free no-op returns a byte-identical position; without this the walk
                # would spend its whole budget declining the same optional pick. See
                # ``tests/props/test_no_agent_cycles.py`` for the seed that found it.
                if key in seen:
                    continue
                here = line + [(ch.kind, opts[i])]
                if over(c) or c.pending.player != self.me:
                    offer(leaf(c), here)
                else:
                    walk(c, here, seen | {key}, depth + 1)

        def sample(node: GameState) -> None:
            """One complete turn, choosing uniformly among my own options at every step.

            Uniform because the alternative — ranking partial plans by the value head — is the
            mid-turn evaluation this agent exists to avoid. A trained policy head is the right
            generator here and does not exist yet; ``learn/policy.py`` is where it will go.
            """
            c, line, seen, depth = node.clone(), [], set(), 0
            while depth < self.max_depth:
                if over(c) or c.pending.player != self.me:
                    break
                ch = _materialise(c)
                choices = _own_options(c)
                if not choices:
                    break
                i = choices[rng.below(len(choices))]
                budget.spend()
                line.append((ch.kind, ch.options[i]))
                apply(c, i)
                step_out(c)
                key = position_key(c)
                if key in seen:
                    break
                seen.add(key)
                depth += 1
            offer(leaf(c), line)

        try:
            walk(w, [], frozenset(), 0)
        except NodeBudget:
            # The turn did not fit. Everything the walk did see still counts — ``found`` is only
            # ever written from a real leaf — and the rest of the budget goes to whole plans.
            budget.cap = int(budget.cap * 1.5) + self.iterations
            try:
                for _ in range(self.iterations):
                    if budget.spent_out():
                        break
                    sample(w)
            except NodeBudget:
                pass
        ranked = sorted(found.values(), key=lambda sl: -sl[0])
        return ranked[:max(1, self.candidates)]

    # ------------------------------------------------------------------ phase 2: score
    def _best_across_worlds(self, s: GameState, lines: list) -> list:
        """Re-score each candidate in fresh worlds and return the one with the best mean.

        This is where the single-world agent lost its four panel points. A plan is replayed rather
        than re-searched, so a world costs a handful of ``apply`` calls per candidate — and the same
        worlds are used for every candidate, which is common random numbers: the comparison between
        two plans is paired, so a world that is harsh for one is harsh for both and the difference
        is measured with far less noise than the individual scores carry.
        """
        model = self.model
        policy = fixed_policy()
        totals = [0.0] * len(lines)
        for _ in range(self.worlds):
            w = self._world(s)
            for k, line in enumerate(lines):
                totals[k] += self._replay_score(w, line, model, policy)
        best = max(range(len(lines)), key=lambda k: totals[k])
        return lines[best]

    def _replay_score(self, w: GameState, line: list, model, policy) -> float:
        """Play ``line`` out in ``w`` and score where it lands.

        A plan proposed in one world can stop being legal in another — a rival reaction it did not
        expect, a card that resolved differently. It is scored **where it breaks** rather than
        skipped: a plan that only survives one guess about the rival's hand is genuinely worse than
        one that survives several, and pretending otherwise is how the single-world version chose
        the plans it did.
        """
        start_turn = w.turn
        c = w.clone()

        def over() -> bool:
            return bool(c.over) or c.turn != start_turn or c.pending is None

        def step_out() -> None:
            guard = 0
            while not over() and c.pending.player != self.me and guard < 64:
                guard += 1
                apply(c, policy(c, _materialise(c)))

        step_out()
        for kind, action in line:
            if over() or c.pending.player != self.me or c.pending.kind is not kind:
                break
            ch = _materialise(c)
            try:
                i = ch.options.index(action)
            except ValueError:
                break
            apply(c, i)
            step_out()
        if not c.over and self.lookahead > 0:
            self._play_on(c, policy, start_turn)
        if c.over:
            return 0.0 if c.winner is None else (WIN if c.winner == self.me else -WIN)
        return model.raw(features(c, self.me))

    def _play_on(self, c: GameState, policy, start_turn: int) -> None:
        """Play past the end of the planned turn, both seats under the frozen policy.

        The same convention ``learn.delayed.confirmed_win`` uses to judge a suite line: a turn that
        banks seven Gigs and has them stolen back did not win, and a board that looks strong at my
        own boundary is not strong if the rival's reply dismantles it. The frozen policy is one
        competent defence rather than a proof against every defence, and this is where the plan is
        scored rather than where it is chosen, so a wrong guess costs a ranking and not a move.
        """
        want = start_turn + self.lookahead * 2       # my turn again, `lookahead` of mine later
        guard = 0
        while not c.over and c.pending is not None and c.turn < want and guard < 400:
            guard += 1
            apply(c, policy(c, _materialise(c)))

    # ------------------------------------------------------------------ introspection
    def plan_for(self, s: GameState) -> list:
        """The plan this agent would play from ``s``, without playing it. For tests and tools."""
        legal_actions(s)
        return self._plan_turn_from(s, s.pending)

    def best_line_score(self, s: GameState) -> tuple[float | None, list]:
        """``(score, line)`` of the plan this agent would play: the line's mean replay score
        across the agent's worlds (the value head's raw output where the turn lands, ``WIN`` for
        a won game), which is what the Stage 0 oracle labels a position with. ``None`` when no
        plan could be proposed."""
        legal_actions(s)
        candidates = self._propose(s)
        if not candidates:
            return None, []
        lines = [line for _, line in candidates]
        if self.worlds <= 1 or len(lines) == 1:
            return float(candidates[0][0]), lines[0]
        model = self.model
        policy = fixed_policy()
        totals = [0.0] * len(lines)
        for _ in range(self.worlds):
            w = self._world(s)
            for k, line in enumerate(lines):
                totals[k] += self._replay_score(w, line, model, policy)
        best = max(range(len(lines)), key=lambda k: totals[k])
        return totals[best] / self.worlds, lines[best]


@register
class PlanDeep(PlanAgent):
    """The same plan search, scored two of my own turns out instead of one.

    A separate registered agent rather than a flag, because it is a different point on the
    cost curve and an arena row needs a name. The curve is the finding: at matched budget 32 on the
    frozen panel, scoring at my own turn boundary gives **83.1%**, playing the rival's reply out
    gives **85.0%**, and this row says whether the trend continues or flattens. ``ismcts`` at the
    same budget scores 87.2% with a ``max_depth`` of 36 — about my turn, the rival's answer and my
    next turn — so the question this answers is whether the plan agent's deficit was ever about
    turn-level coherence at all, or simply about seeing less of the game.
    """

    name = "plan-deep"
    lookahead = 2
