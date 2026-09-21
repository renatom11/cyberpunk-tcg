"""Agents that play with the card-aware model through its numpy twin (Stage 0, layer B).

Registered names (loaded into a process by ``CPTCG_AGENT_PLUGINS=cards_agents``, which
``cptcg.agents.base.make_agent`` imports on an unknown name, in every harvest and arena worker):

* ``neural-cards@W.npz``          greedy one-ply on the card-aware value head, options batched
* ``neural-cards-ablated@W.npz``  the same with the identity embedding permuted (kill test 1)
* ``ismcts-cards:N@W.npz``        ``IsmctsAgent`` with the value head at the leaves and the policy
                                   head as the PUCT prior, both from the numpy model; the leaf
                                   and the prior are batched across a node's children at expansion

The greedy agent keeps ``NeuralAgent``'s loop (the no-op guard, the seat key, the settle) and
swaps only what it scores with: every option is previewed by clone+apply+settle exactly as the
114-feature agent does, and the previews are evaluated in one batched forward. The search agent
overrides ``_leaf`` and ``_priors``; ``_priors`` already has the state clones of every child in
hand, so the batch is free.

numpy lives here, never under ``src/cptcg``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cards_model as CM  # noqa: E402
from cptcg.agents.base import register  # noqa: E402
from cptcg.agents.neural import WIN, NeuralAgent, _same_position, seat_key  # noqa: E402
from cptcg.agents.search.ismcts import IsmctsAgent  # noqa: E402
from cptcg.core.actions import Choice, ChoiceKind  # noqa: E402
from cptcg.core.engine import apply, legal_actions  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.core.state import GameState  # noqa: E402
from cptcg.learn import tokens as T  # noqa: E402

_CACHE: dict = {}


def load_cards_model(path: str, ablate: bool) -> CM.NumpyCardsModel:
    key = (str(path), ablate)
    m = _CACHE.get(key)
    if m is None:
        m = CM.NumpyCardsModel.load(path)
        if ablate:
            m = m.ablate_identity()
        _CACHE[key] = m
    return m


def _value_batch(model: CM.NumpyCardsModel, states: list, me: int) -> np.ndarray:
    """Value for ``me`` in each state, one forward. States with no pending choice are given a
    neutral MAIN context (the value head is a position evaluator)."""
    decs = []
    for c in states:
        ch = c.pending
        if ch is None:
            ch = Choice(ChoiceKind.MAIN, c.active, (), lazy=True)
        d = {"cards": T.card_tokens(c, me), "dice": T.die_tokens(c, me), "context": T.context(c, me, ch),
             "aggregates": tuple(_features(c, me)), "options": ()}
        deck, legs = T.belief(c, me)
        d["belief_deck"], d["belief_legends"] = deck, legs
        decs.append(d)
    return model.raw(CM.batch_tokens(decs))


def _features(s, me):
    from cptcg.learn.features import features
    return features(s, me)


@register
class NeuralCardsAgent(NeuralAgent):
    """Greedy on the card-aware value head; previews batched."""
    name = "neural-cards"
    weights_path = str(ROOT / "out" / "s0" / "wcards.npz")
    ablate = False

    @property
    def cards_model(self) -> CM.NumpyCardsModel:
        m = getattr(self, "_cards_model", None)
        if m is None or getattr(self, "_cards_path", None) != self.weights_path:
            m = load_cards_model(self.weights_path, self.ablate)
            self._cards_model, self._cards_path = m, self.weights_path
        return m

    def _greedy(self, s: GameState, choice: Choice, depth: int) -> int:
        options = choice.options
        seen = set()
        rng = self.rng
        here = s
        previews, idxs = [], []
        for i in range(len(options)):
            key = seat_key(s, self.me, options[i])
            if key in seen:
                continue
            seen.add(key)
            c = s.clone()
            c.rng = Pcg32(rng.next_u32(), seq=3)
            apply(c, i)
            self._resolve(c, depth)
            previews.append(c)
            idxs.append(i)
        scores = np.zeros(len(previews), dtype=np.float64)
        need = []
        for k, c in enumerate(previews):
            if c.over:
                scores[k] = WIN if c.winner == self.me else -WIN
            elif _same_position(c, here):
                scores[k] = -WIN
            else:
                need.append(k)
        if need:
            vals = _value_batch(self.cards_model, [previews[k] for k in need], self.me)
            for k, v in zip(need, vals):
                scores[k] = float(v)
        best_i, best_v = 0, -1e18
        for k, i in enumerate(idxs):
            v = scores[k] + rng.next_u32() % 1000 * self.noise
            if v > best_v:
                best_i, best_v = i, v
        return best_i


@register
class NeuralCardsAblated(NeuralCardsAgent):
    name = "neural-cards-ablated"
    ablate = True


@register
class IsmctsCardsAgent(IsmctsAgent):
    """The search with the card-aware heads: numpy value at the leaves, numpy policy as prior."""
    name = "ismcts-cards"
    weights_path = str(ROOT / "out" / "s0" / "wcards.npz")
    ablate = False
    policy_temp = 1.0

    @property
    def cards_model(self) -> CM.NumpyCardsModel:
        m = getattr(self, "_cards_model", None)
        if m is None or getattr(self, "_cards_path", None) != self.weights_path:
            m = load_cards_model(self.weights_path, self.ablate)
            self._cards_model, self._cards_path = m, self.weights_path
        return m

    @property
    def policy(self):
        return None                      # the 114-feature policy file is never consulted

    def _leaf(self, w: GameState) -> float:
        if w.over:
            return 1.0 if w.winner == self.me else 0.0
        v = _value_batch(self.cards_model, [w], self.me)[0]
        return float(1.0 / (1.0 + np.exp(-v)))

    def _priors(self, w: GameState, ch: Choice, idxs) -> dict:
        actor = ch.player
        opts = ch.options
        d = T.decision_tokens(w, actor, ch)
        d["options"] = [d["options"][i] for i in idxs]
        pol = self.cards_model.policy(CM.batch_tokens([d]))[0]
        pol = pol[:len(idxs)]
        if self.policy_temp != 1.0:
            pol = np.power(np.maximum(pol, 1e-9), 1.0 / self.policy_temp)
        tot = float(pol.sum())
        if tot <= 0:
            return {opts[i]: 1.0 / len(idxs) for i in idxs}
        return {opts[i]: float(p) / tot for i, p in zip(idxs, pol)}   # keyed by option, as the base class


@register
class IsmctsCardsAblated(IsmctsCardsAgent):
    name = "ismcts-cards-ablated"
    ablate = True
