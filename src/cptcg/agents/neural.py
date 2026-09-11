"""The same one-ply agent as ``heuristic``, scored by a fitted value head instead of a weight dict.

This file exists to make one comparison clean. ``agents/heuristic.py`` is two things welded
together: a *search* (preview every legal option on a clone, resolve the rival's reactions by a
default policy, stop the moment the turn passes) and an *evaluation* (seventeen hand-written
constants). Only the second one is what Stage 2 is trying to replace, so this agent **inherits**
the first — ``act``, ``_keep``, ``_resolve`` and the ``_equiv_key`` dedup come straight from the
frozen module, unmodified — and overrides nothing but the line that turns a previewed position
into a number.

So a win here is a win for the learned value, and a loss here is a loss for the learned value.
Neither can be a difference in mulligan policy, in preview depth, or in how a rival's reaction was
assumed to go.

Three deliberate differences from ``evaluate()``. Two are forced by what a probability is; the
third is a hang this agent found and the heuristic only avoids by luck.

**It ranks on the logit, not the probability.** ``ValueModel.raw`` is the unbounded pre-logistic
score. The logistic is monotone, so the ordering is identical, but in a position the model thinks
is 99.4% won, two options can differ by 1e-5 in probability and by 0.2 in log-odds. Squashing
first would throw that away into float noise.

**The tie-break noise is in logit units and it is small.** The heuristic adds up to 0.0999 to a
score whose useful range is tens of points — about a part in a thousand. :data:`NeuralAgent.noise`
is set from the measured spread of ``raw`` across the options of real decisions (see
``tools/fit_eval.py diagnose``), for the same ratio. Copying the heuristic's constant would make
this agent play at random; dropping the noise entirely would make it prefer whichever option the
engine happens to list first, every time, which is a real bias in a menu that is ordered by zone.

**A preview it cannot tell apart from the position it is in is scored as a loss.** The rules offer
a free no-op — activate a Legend, decline the pick, get the identical menu back — and a greedy
agent on a static evaluation that prefers it will take it for ever. See ``_value``.

Configuration rides on class attributes because ``make_agent(name, seed)`` has no config channel:
subclass and set ``weights_path``, ``noise``, ``depth`` or ``go_first`` to get a variant, and
register it under its own name.

The weights load lazily and are cached per path (``learn.model.load_weights``), so importing this
module never touches the disk and a build with no ``weights.json`` still starts — it fails when
someone actually asks for this agent, with the path in the message.
"""

from __future__ import annotations

from cptcg.agents.base import register
from cptcg.agents.heuristic import HeuristicAgent, _equiv_key
from cptcg.core.actions import Choice
from cptcg.core.engine import apply
from cptcg.core.rng import Pcg32
from cptcg.core.state import GameState
from cptcg.learn.features import features
from cptcg.learn.model import WEIGHTS_PATH, ValueModel, load_weights

#: A decided preview is worth more than any opinion about an undecided one. In log-odds, and far
#: enough out that no accumulation of hidden units can reach it.
WIN = 1e6


class _Position:
    """The position a ``_greedy`` call is choosing *from*, for the no-op guard below.

    Built once per call and read at most a few times: the feature vector is extracted lazily,
    because the only previews that can possibly be no-ops are the ones that came back to a menu
    with exactly the same options, which is rare.
    """

    __slots__ = ("state", "me", "options", "_x")

    def __init__(self, state: GameState, me: int, options) -> None:
        self.state = state
        self.me = me
        self.options = options
        self._x = None

    @property
    def x(self):
        if self._x is None:
            self._x = features(self.state, self.me)
        return self._x


@register
class NeuralAgent(HeuristicAgent):
    """Greedy one-ply on ``ValueModel.raw``. Everything but the scorer is the frozen heuristic."""

    name = "neural"

    #: Where the fitted weights live. A subclass pointing elsewhere is how a frozen generation
    #: would be shipped beside the current one.
    weights_path = WEIGHTS_PATH

    #: Tie-break, in log-odds, times 0..999 — so up to 8e-3 of log-odds.
    #:
    #: **Measured, not chosen.** ``tools/fit_eval.py diagnose`` scores the options of 3,200 real
    #: multi-option decisions with both scorers. The median spread of ``evaluate()`` across one
    #: decision's options is 7.40 points, and the heuristic's noise reaches 0.0999 — 1.35% of it.
    #: The median spread of the learned logit across the *same* decisions is 0.596, so the same
    #: 1.35% is 8.05e-6 per unit. Copying the heuristic's 1e-4 would be a noise of 1.7x the whole
    #: spread, and this agent would play at random.
    noise = 8e-6

    def __init__(self, seed: int = 0) -> None:
        super().__init__(seed)
        self._model: ValueModel | None = None

    @property
    def model(self) -> ValueModel:
        m = self._model
        if m is None:
            m = self._model = load_weights(self.weights_path)
        return m

    # ------------------------------------------------------------------ scoring
    def _value(self, c: GameState, model: ValueModel, here: "_Position | None" = None) -> float:
        """Log-odds that ``self.me`` wins from this previewed position.

        The terminal short-circuit is not an optimisation: a finished game has no features worth
        reading, and a model that has never been asked to be certain should not be asked to
        express certainty. ``evaluate()`` does exactly the same thing with ``w["win"]``.

        The second guard has no counterpart in ``evaluate()`` and is not a taste. **A greedy agent
        on a static evaluation hangs whenever the rules offer a free no-op.** This pool has one:
        activating Panam Palmer and then declining the pick costs nothing and gives back the
        identical main menu. The frozen heuristic escapes it by accident — it happens to rate
        taking the pick above declining — but nothing in its design prevents it, and the fitted
        value rates declining higher, so `neural` re-activated the same Legend 750 times and a
        game hit ``runner.play_game``'s 50,000-action ceiling.

        The rule is stated in terms of what this agent can *perceive*: if a previewed position is
        indistinguishable from the one being chosen from — the same menu, and a bit-identical
        feature vector — then taking that option returns me here and I will choose it again, for
        ever. An option that provably cannot advance the game is scored as a loss. If every option
        is one, the first is still taken and the engine's own Overtime and turn limits end the
        game, exactly as before.
        """
        if c.over:
            return WIN if c.winner == self.me else -WIN
        x = features(c, self.me)
        if (here is not None and c.pending is not None and c.pending.player == self.me
                and c.pending.options == here.options and x == here.x):
            return -WIN
        return model.raw(x)

    # ------------------------------------------------------------------ search
    def _greedy(self, s: GameState, choice: Choice, depth: int) -> int:
        """``HeuristicAgent._greedy`` with the scoring line swapped, and nothing else.

        Kept as a copy rather than factored into the frozen file: ``heuristic.py`` is frozen, and a
        refactor there — however harmless it looked — would be a change to the thing this agent is
        being measured against. ``tests/unit/test_neural_agent.py`` compares the two bodies line by
        line so the copy cannot drift.

        The one added line builds the no-op guard's view of the position being chosen from; see
        ``_value``.
        """
        best_i, best_v = 0, -1e18
        seen = set()
        rng = self.rng; options = choice.options                      # noqa: E702
        model = self.model; noise = self.noise                        # noqa: E702
        here = _Position(s, self.me, options)
        for i in range(len(options)):
            key = _equiv_key(s, options[i])
            if key in seen:
                continue                                     # identical to an option already tried
            seen.add(key)
            c = s.clone()
            c.rng = Pcg32(rng.next_u32(), seq=3)             # never preview the true future
            apply(c, i)
            self._resolve(c, depth)
            v = self._value(c, model, here) + rng.next_u32() % 1000 * noise
            if v > best_v:
                best_i, best_v = i, v
        return best_i
