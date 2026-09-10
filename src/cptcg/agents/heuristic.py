"""Greedy one-ply heuristic agent.

For each legal option it previews the result on a clone — with the clone's RNG reseeded so the
preview can't peek at the real future draws or rolls — resolves the rival's pending reactions
with a default policy (they pass), scores the board, and takes the best. Cheap enough for mass
simulation; the search agent later reuses the same evaluator for rollouts.
"""

from __future__ import annotations

from cptcg.agents.base import Agent, register
from cptcg.core.actions import Choice, ChoiceKind, ChooseOrder, Mulligan, Pass, TakeGigDie
from cptcg.core.engine import apply
from cptcg.core.enums import NZONE, CardType, Keyword, Zone
from cptcg.core.ops import ATTACKING, available, has_keyword, power, steal_count
from cptcg.core.rng import Pcg32
from cptcg.core.state import GameState

W = dict(
    win=10_000.0, gig=12.0, gig_sq=1.5, rival_six=-40.0, my_six=25.0, cred=0.15,
    unit_ready=1.0, unit_spent=0.55, unit_count=1.5, blocker=2.0, threat=-3.0,
    hand=1.2, eddies=1.4, faceup=2.0, removed=-3.0, deck=0.05, gear=0.8,
)


def evaluate(s: GameState, me: int, w: dict = W) -> float:
    """Board score from ``me``'s perspective. Reads only public zones and my own hand."""
    if s.over:
        return w["win"] if s.winner == me else -w["win"]
    r = 1 - me
    v = 0.0
    g_me, g_r = len(s.gig[me]), len(s.gig[r])
    v += w["gig"] * (g_me - g_r) + w["gig_sq"] * (g_me * g_me - g_r * g_r)
    if g_r >= 6:
        v += w["rival_six"]
    if g_me >= 6:
        v += w["my_six"]
    v += w["cred"] * (s.street_cred(me) - s.street_cred(r))
    for p, sign in ((me, 1.0), (r, -1.0)):
        base = p * NZONE
        units = s.units(p)
        for u in units:
            pw = power(s, u, ATTACKING)
            v += sign * (w["unit_spent"] if s.i_spent[u] else w["unit_ready"]) * pw
            v += sign * w["unit_count"]
            if has_keyword(s, u, Keyword.BLOCKER) and not s.i_spent[u]:
                v += sign * w["blocker"]
            v += sign * w["gear"] * len(s.gear_on(u))
        v += sign * w["eddies"] * (len(s.z[base + Zone.EDDIES]) + sum(
            1 for i in s.legends(p) if s.i_zone[i] is Zone.LEGENDS))
        v += sign * w["faceup"] * sum(s.i_faceup[i] for i in s.legends(p))
        v += sign * w["removed"] * len(s.z[base + Zone.REMOVED])
        v += sign * w["deck"] * len(s.z[base + Zone.DECK])
    v += w["hand"] * len(s.z[me * NZONE + Zone.HAND])
    # Threat: how many Gigs the rival's ready Units could steal on their turn, less what my
    # ready Blockers can absorb. Counted whoever's turn it is, so ending the turn isn't "safe".
    threat = sum(steal_count(power(s, u, ATTACKING)) for u in s.units(r) if not s.i_spent[u])
    blockers = sum(1 for u in s.units(me) if not s.i_spent[u] and has_keyword(s, u, Keyword.BLOCKER))
    v += w["threat"] * max(0, min(threat, g_me) - blockers)
    return v


def _equiv_key(s: GameState, a) -> tuple:
    """Options that differ only in *which copy* of a card they name are interchangeable."""
    inst = getattr(a, "inst", None)
    if inst is None or inst < 0 or a.__class__.__name__ == "Pick":
        return (a,)
    cid = s.i_card[inst]
    host = getattr(a, "host", -1)
    return (a.__class__.__name__, cid, s.i_zone[inst], s.i_card[host] if host >= 0 else -1,
            getattr(a, "ability", -1))


def _default_index(choice: Choice) -> int:
    """How the preview assumes the rival answers: pass / keep / first option."""
    for i, o in enumerate(choice.options):
        if isinstance(o, Pass) or (isinstance(o, Mulligan) and o.keep):
            return i
    return 0


@register
class HeuristicAgent(Agent):
    name = "heuristic"
    go_first = False
    depth = 1            # how many of my own follow-up choices to resolve greedily in a preview

    def act(self, s: GameState, choice: Choice) -> int:
        kind = choice.kind
        if kind is ChoiceKind.ORDER:
            return choice.index_of(ChooseOrder(self.go_first))
        if kind is ChoiceKind.MULLIGAN:
            return 0 if self._keep(s) else 1
        if kind is ChoiceKind.GIG_DIE:
            best = max(o.sides for o in choice.options)
            return choice.index_of(TakeGigDie(best))
        if len(choice.options) == 1:
            return 0
        return self._greedy(s, choice, self.depth)

    def _keep(self, s: GameState) -> bool:
        hand = s.z[self.me * NZONE + Zone.HAND]
        cheap_units = sum(1 for i in hand if s.card(i).type is CardType.UNIT and (s.card(i).cost or 9) <= 4)
        sellable = sum(1 for i in hand if s.card(i).sell_tag)
        return cheap_units >= 2 and sellable >= 1

    def _greedy(self, s: GameState, choice: Choice, depth: int) -> int:
        best_i, best_v = 0, -1e18
        seen = set()
        for i in range(len(choice.options)):
            key = _equiv_key(s, choice.options[i])
            if key in seen:
                continue                                     # identical to an option already tried
            seen.add(key)
            c = s.clone()
            c.rng = Pcg32(self.rng.next_u32(), seq=3)        # never preview the true future
            apply(c, i)
            self._resolve(c, depth)
            v = evaluate(c, self.me) + self.rng.below(1000) * 1e-4
            if v > best_v:
                best_i, best_v = i, v
        return best_i

    def _resolve(self, c: GameState, depth: int) -> None:
        """Play out pending decisions in a preview: the rival's reactions by default policy, my
        follow-up choices greedily. Stops at my main menu or as soon as the turn passes — a
        preview must never run into the next turn, or ending the turn gets credit for next
        turn's free Gig and draw."""
        guard = 0
        while not c.over and c.pending is not None and guard < 12:
            guard += 1
            if c.active != self.me:
                return
            ch = c.pending
            if ch.player != self.me:
                apply(c, _default_index(ch))
            elif ch.kind is ChoiceKind.MAIN:
                return
            elif depth > 0 and len(ch.options) > 1:
                apply(c, self._greedy(c, ch, depth - 1))
            else:
                apply(c, 0)
