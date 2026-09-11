"""Information Set Monte Carlo Tree Search over the fitted value head.

This is the "teacher" the training plan has been pointing at since Stage 0, and it exists to fix
one specific, structural failure rather than to be generically stronger.

**What it fixes.** ``agents/neural.py`` is greedy *per decision*: it previews each single option and
scores the board that comes back. ``heuristic._resolve``, which it inherits unchanged, returns the
instant ``c.active != self.me`` — a preview is forbidden from running past the end of the turn, by
design, or ending the turn would get credit for next turn's free Gig and draw. So a line whose value
only appears once several of its moves are on the board is invisible to it at *any* strength of
evaluation. ``two-pieces-of-gear`` in ``data/arena/delayed.json`` is the clean case: 7+2 and 7+1
each still steal one Gig and only 7+2+1 crosses the threshold, so each equip alone scores as a
rounding error and the pair is unreachable by construction. Searching the *sequence* is the fix.

**Why sampling and not exhaustive search.** ``docs/learning.md`` measured a two-turn exhaustive tree
at roughly 3.6e8 clones — about five hours for one position at the ~20,000 clones a second this
engine manages. There is no version of enumerating that horizon, so the tree is sampled.

**Single-observer ISMCTS.** One tree, owned by ``self.me``. Each iteration samples a world with
``core.view.determinize`` — permuting only the identities this seat may not know, which is a
*complete* determinization of every future draw because ``ops.draw`` consumes no randomness — then
descends by PUCT, expands one node, evaluates a leaf and backs the value up. Actions that were legal
in a sampled world get an availability count, which is what lets one tree average over worlds whose
legal sets differ.

Three measurements shaped the implementation, and two of them contradict the plan it was built from:

*Nodes are keyed by position in the tree, not by* ``info_key``. ``info_key`` costs 38.7 us, and a
30-ply descent over 200 iterations would call it 6,000 times — 232 ms a decision, more than the
whole search budget. Tree position is the standard SO-ISMCTS identity and it is free. ``info_key``
is still the right thing for a transposition table and is used in the tests.

*Rollouts lose to the value head by a factor of seven, per ply.* A full rollout from a mid-game
position costs 25.8 ms over ~40 decisions — 0.65 ms for a single ply of frozen-heuristic play,
against 89 us for a value-head leaf (49 us of ``features`` plus 40 us of ``ValueModel.raw``). At 200
iterations a rollout policy would cost 5.2 s a decision, or thirteen minutes a game. The plan said
to roll out to the end in early generations so that delayed payoffs entered the target at all; at
this budget that is simply not affordable, and the calibrated value head (holdout Brier 0.139, ECE
0.022) is what makes skipping it defensible. ``rollout_depth`` keeps the claim testable rather than
assumed — see the class attribute.

*The prior is the value head, because there is no policy head until Stage 4.* Each child is previewed
once and scored, and the scores are softmaxed. That is ~107 us per child, so it is computed lazily —
only when a node is visited a second time and a choice among its children actually has to be made.
Most nodes in a 200-iteration tree are visited once and never pay it.

Pure stdlib, like everything under ``src/cptcg``: this package is shipped into the browser.
"""

from __future__ import annotations

import math

from cptcg.agents.base import register
from cptcg.agents.heuristic import _default_index, _equiv_key
from cptcg.agents.neural import NeuralAgent, _same_position
from cptcg.core.actions import Choice, ChoiceKind
from cptcg.core.engine import apply, legal_actions
from cptcg.core.rng import Pcg32
from cptcg.core.state import GameState
from cptcg.core.view import determinize
from cptcg.learn.features import features


class _Node:
    """One decision in the tree. Values are stored from the *searching seat's* perspective
    throughout; ``_select`` flips them for a node where the rival chooses, which is correct because
    the game is zero-sum."""

    __slots__ = ("visits", "value", "children", "avail", "prior", "actor", "expanded", "allowed")

    def __init__(self) -> None:
        self.visits = 0
        self.value = 0.0
        self.children: dict = {}
        self.avail: dict = {}
        self.prior: dict | None = None
        self.actor = -1
        self.expanded = False
        #: Root only: the subset of actions worth searching, after collapsing options that differ
        #: only in which copy of a card they name.
        self.allowed = None

    def q(self, default: float) -> float:
        return self.value / self.visits if self.visits else default


@register
class IsmctsAgent(NeuralAgent):
    """ISMCTS over ``ValueModel``. Everything it evaluates with is Stage 2; what is new is that it
    searches a sequence of decisions instead of scoring one."""

    name = "ismcts"

    #: This agent samples the hidden information rather than reading it, so ``cheat:ismcts`` is
    #: meaningful and ``tools/arena.py exploit`` can price the hidden information for free.
    uses_determinization = True

    #: Iterations per decision. 200 is ~0.7 ms each here, so ~140 ms a decision and ~20 s a game.
    iterations = 200

    #: Wall-clock ceiling per decision, seconds. 0 disables it. The browser build sets this, because
    #: a phone under Pyodide cannot be budgeted in iterations.
    max_seconds = 0.0

    #: Decisions deep the tree may go. A player-turn is ~10 decisions (median; max 27), so 36 spans
    #: my turn, the rival's answer and my next turn — the horizon the delayed-reward suite asks for.
    max_depth = 36

    #: PUCT exploration. Higher trusts the prior less.
    c_puct = 1.4

    #: Softmax temperature for the value-head prior. The learned logit's median spread across one
    #: decision's options is 0.596 (measured in ``fit_eval diagnose``, quoted in ``NeuralAgent``),
    #: so a temperature of 1.0 would make every prior nearly uniform and the prior pointless.
    prior_temp = 0.3

    #: Whether the prior previews an option all the way to a settled position, as the greedy agent
    #: does, or scores it where it lands. Scoring where it lands can be *mid-action*: "Attack" is
    #: then measured at the target menu, with the attacker already spent and nothing stolen yet, so
    #: attacking reads as a pure loss and takes the lowest prior on the board. Settling fixes that
    #: and costs the prior its independence from the greedy policy. Chosen by measurement — the
    #: table is in docs/learning.md.
    prior_settle = True

    #: Plies of frozen-heuristic play before falling back to the value head at a leaf. 0 means the
    #: value head alone. Each ply costs ~0.65 ms against the leaf's 89 us, so this is expensive by
    #: construction; it exists so "would playing further help?" stays a measurement.
    rollout_depth = 0

    #: Dirichlet concentration for root exploration noise, and the weight it is mixed in at. Both
    #: off by default: they are for generating varied training data in Stage 4, and a gate has to
    #: measure the agent playing to win.
    root_noise_alpha = 0.0
    root_noise_weight = 0.25

    #: Visit-count temperature for the final choice. 0 is argmax, which is what a gate measures.
    temperature = 0.0

    # ------------------------------------------------------------------ entry point
    def act(self, s: GameState, choice: Choice) -> int:
        kind = choice.kind
        # Turn order and the mulligan are one-off, pre-board decisions with no sequence to search,
        # and the frozen policies for them are inherited deliberately.
        if kind is ChoiceKind.ORDER or kind is ChoiceKind.MULLIGAN or len(choice.options) == 1:
            return super().act(s, choice)
        return self._search(s, choice)

    # ------------------------------------------------------------------ the search
    def _search(self, s: GameState, choice: Choice) -> int:
        root = _Node()
        root.actor = choice.player
        root.expanded = True
        root.allowed = self._root_actions(s, choice)

        deadline = None
        if self.max_seconds > 0.0:
            import time
            deadline = time.perf_counter() + self.max_seconds

        rng = self.rng
        for n in range(self.iterations):
            if deadline is not None and (n & 7) == 0:
                import time
                if time.perf_counter() >= deadline:
                    break
            # The true state when cheating, a sampled world otherwise. determinize already returns
            # a clone; the cheating branch has to make one so the live game is never touched.
            if self.cheating:
                w = s.clone()
            else:
                w = determinize(s, self.me, rng)
            # Never replay the true future: the Gig die is the one chance node left in the game and
            # it is rolled inside apply(), so each iteration has to roll its own.
            w.rng = Pcg32(rng.next_u32(), seq=3)
            self._iterate(root, w)

        return self._choose(s, choice, root)

    def _root_actions(self, s: GameState, choice: Choice):
        """Collapse options that differ only in which copy of a card they name.

        ``_equiv_key`` reads ``s.i_card``, so it means something different in every sampled world
        and must not be used inside the tree. At the root there is exactly one world — the real one
        — so it is both safe and worth it: three identical face-down Legends are one choice.
        """
        seen, keep = set(), []
        for a in choice.options:
            key = _equiv_key(s, a)
            if key in seen:
                continue
            seen.add(key)
            keep.append(a)
        return frozenset(keep) if len(keep) < len(choice.options) else None

    def _iterate(self, root: _Node, w: GameState) -> None:
        node = root
        visited = [root]
        depth = 0
        value = 0.5
        while True:
            if w.over:
                value = self._terminal(w)
                break
            if depth >= self.max_depth:
                value = self._leaf(w)
                break
            legal_actions(w)
            ch = w.pending
            if ch is None:
                value = self._leaf(w)
                break
            opts = ch.options
            if len(opts) == 1:
                apply(w, 0)                 # forced: not a decision, so it grows no tree
                continue
            if ch.player != self.me and ch.kind is ChoiceKind.PICK:
                # determinize re-derives a rival MAIN, REACTION or TARGET menu from the sampled
                # world, but a PICK's options come from a card script that cannot be re-run from
                # there. Answering it by the frozen default is honest; branching on it would be
                # branching on a menu this world did not actually produce.
                apply(w, _default_index(ch))
                continue

            if not node.expanded:
                node.actor = ch.player
                node.expanded = True
                value = self._leaf(w)
                break

            node.actor = ch.player
            idx = self._select(node, w, ch)
            a = opts[idx]
            child = node.children.get(a)
            if child is None:
                child = node.children[a] = _Node()
            apply(w, idx)
            node = child
            visited.append(node)
            depth += 1

        for n in visited:
            n.visits += 1
            n.value += value

    def _select(self, node: _Node, w: GameState, ch: Choice) -> int:
        opts = ch.options
        allowed = node.allowed
        avail = node.avail
        children = node.children
        idxs = [i for i in range(len(opts)) if allowed is None or opts[i] in allowed]
        if not idxs:                                  # pragma: no cover - allowed is root-only
            idxs = list(range(len(opts)))

        prior = node.prior
        if prior is None:
            prior = node.prior = self._priors(w, ch, idxs)

        # Availability, not visits: this is the whole difference between ISMCTS and MCTS. An action
        # legal in few sampled worlds must not be punished for the visits it never had the chance
        # to collect.
        for i in idxs:
            a = opts[i]
            avail[a] = avail.get(a, 0) + 1

        mine = ch.player == self.me
        parent_q = node.q(0.5)
        fpu = parent_q if mine else 1.0 - parent_q     # unvisited children inherit the parent
        c_puct = self.c_puct
        best_i, best_score = idxs[0], -1e18
        for i in idxs:
            a = opts[i]
            kid = children.get(a)
            if kid is not None and kid.visits:
                q = kid.value / kid.visits
                q = q if mine else 1.0 - q
                n = kid.visits
            else:
                q, n = fpu, 0
            score = q + c_puct * prior.get(a, 1.0 / len(idxs)) * math.sqrt(avail[a]) / (1 + n)
            if score > best_score:
                best_i, best_score = i, score
        return best_i

    def _priors(self, w: GameState, ch: Choice, idxs: list[int]) -> dict:
        """One-ply previews, softmaxed, from the perspective of whoever is choosing.

        There is no policy head until Stage 4, so this is what a prior can be made of. It costs
        about 107 us per option, which is why it is computed here — on a node's second visit, when
        a choice among children actually has to be made — and not at expansion.
        """
        opts = ch.options
        actor = ch.player
        model = self.model
        raw = []
        for i in idxs:
            c = w.clone()
            c.rng = Pcg32(self.rng.next_u32(), seq=3)
            apply(c, i)
            # Settle the compound part of the action before scoring it, exactly as the greedy agent's
            # preview does. Without this the prior is measured *mid-action*: "Attack" is scored at the
            # target menu, where the attacker is already spent and nothing has been stolen yet, so
            # attacking looks like a pure loss and gets the lowest prior on the board. That is what
            # made the search equip the Gear correctly and then end the turn instead of swinging.
            if self.prior_settle:
                self._resolve(c, 1)
            if c.over:
                won = c.winner == actor
                raw.append(12.0 if won else -12.0)
            else:
                raw.append(model.raw(features(c, actor)))
        hi = max(raw)
        t = self.prior_temp
        exps = [math.exp((v - hi) / t) for v in raw]
        total = sum(exps) or 1.0
        return {opts[i]: e / total for i, e in zip(idxs, exps)}

    def _terminal(self, w: GameState) -> float:
        winner = w.winner
        if winner is None or winner < 0:
            return 0.5
        return 1.0 if winner == self.me else 0.0

    def _leaf(self, w: GameState) -> float:
        """Win probability for the searching seat. ``rollout_depth`` plies of frozen-heuristic play
        first, if it is set — see the module docstring for what that costs."""
        if self.rollout_depth > 0:
            w = self._rollout(w)
            if w.over:
                return self._terminal(w)
        return self.model.value(w, self.me)

    def _rollout(self, w: GameState) -> GameState:
        for _ in range(self.rollout_depth):
            if w.over:
                break
            legal_actions(w)
            ch = w.pending
            if ch is None:
                break
            apply(w, 0 if len(ch.options) == 1 else HeuristicPolicy.act(self, w, ch))
        return w

    # ------------------------------------------------------------------ the answer
    def _choose(self, s: GameState, choice: Choice, root: _Node) -> int:
        if not root.children:
            # Nothing was ever expanded — iterations=0, or every path was forced. The greedy
            # Stage 2 answer is the honest fallback, not an arbitrary index.
            return super().act(s, choice)
        opts = choice.options
        counts = [(i, root.children[opts[i]].visits) for i in range(len(opts))
                  if opts[i] in root.children]
        if self.temperature > 0.0:
            return self._sample(counts)
        best_i, best_n, best_q = counts[0][0], -1, -1e18
        for i, n in counts:
            kid = root.children[opts[i]]
            q = kid.q(-1e18)
            if n > best_n or (n == best_n and q > best_q):
                best_i, best_n, best_q = i, n, q
        return best_i

    def _sample(self, counts: list) -> int:
        t = 1.0 / self.temperature
        weights = [(i, n ** t) for i, n in counts if n > 0]
        if not weights:
            return counts[0][0]
        total = sum(w for _, w in weights)
        pick = (self.rng.next_u32() / 4294967296.0) * total
        upto = 0.0
        for i, w in weights:
            upto += w
            if pick < upto:
                return i
        return weights[-1][0]                          # pragma: no cover - float tail


class HeuristicPolicy:
    """The frozen greedy policy, reached without giving ``IsmctsAgent`` a second inheritance path.

    ``_rollout`` wants the heuristic's answer, and ``IsmctsAgent`` already *is* a ``NeuralAgent``
    whose ``_greedy`` is the neural one. This hands the rollout the grandparent's implementation
    explicitly, so which policy a rollout uses is stated rather than implied by the MRO.
    """

    @staticmethod
    def act(agent: IsmctsAgent, w: GameState, ch: Choice) -> int:
        from cptcg.agents.heuristic import HeuristicAgent
        return HeuristicAgent._greedy(agent, w, ch, 0)
