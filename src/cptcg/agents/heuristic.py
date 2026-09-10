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
from cptcg.core.enums import NO_INST, NZONE, CardType, Keyword, Zone
from cptcg.core.ops import ATTACKING, _active, _ctx
from cptcg.core.rng import Pcg32
from cptcg.core.state import GameState

W = dict(
    win=10_000.0, gig=12.0, gig_sq=1.5, rival_six=-40.0, my_six=25.0, cred=0.15,
    unit_ready=1.0, unit_spent=0.55, unit_count=1.5, blocker=2.0, threat=-3.0,
    hand=1.2, eddies=1.4, faceup=2.0, removed=-3.0, deck=0.05, gear=0.8,
)
_FIELD, _LEGENDS, _EDDIES, _REMOVED, _DECK, _HAND = Zone.FIELD, Zone.LEGENDS, Zone.EDDIES, Zone.REMOVED, Zone.DECK, Zone.HAND
_GEAR = CardType.GEAR
_BLOCKER = Keyword.BLOCKER


def evaluate(s: GameState, me: int, w: dict = W) -> float:
    """Board score from ``me``'s perspective. Reads only public zones and my own hand.
    power()/has_keyword()/units()/legends()/street_cred()/steal_count() are inlined for speed;
    tests/unit/test_heuristic_eval.py checks this against the reference implementation.
    Keep the floating-point statements in exactly this order and shape."""
    if s.over:
        return w["win"] if s.winner == me else -w["win"]
    r = 1 - me
    v = 0.0
    gig = s.gig
    g_me, g_r = len(gig[me]), len(gig[r])
    v += w["gig"] * (g_me - g_r) + w["gig_sq"] * (g_me * g_me - g_r * g_r)
    if g_r >= 6:
        v += w["rival_six"]
    if g_me >= 6:
        v += w["my_six"]
    c_me = 0
    for _sides, val in gig[me]:          # == s.street_cred(me): exact int sum
        c_me += val
    c_r = 0
    for _sides, val in gig[r]:
        c_r += val
    v += w["cred"] * (c_me - c_r)
    act = _active(s)                     # same call site as the original gear_of = _active(s)[5]
    gear_of = act[5]
    pm = act[2]
    kwm = act[11]                        # conditional keyword grants; empty for most pools
    hooks = None                         # [(hook, ctx)], resolved once on the first unit
    kw_hooks = None                      # [(hook, ctx)] for kwm, resolved on the first miss
    z = s.z; i_host = s.i_host; i_card = s.i_card; i_spent = s.i_spent; i_faceup = s.i_faceup
    defs = s.reg.defs; temp_power = s.temp_power; mods = s.mods
    w_spent = w["unit_spent"]; w_ready = w["unit_ready"]; w_count = w["unit_count"]
    w_blocker = w["blocker"]; w_gear = w["gear"]; w_eddies = w["eddies"]; w_faceup = w["faceup"]
    w_removed = w["removed"]; w_deck = w["deck"]
    threat = 0            # Gigs the rival's ready Units could steal next turn ...
    blockers = 0          # ... less what my ready Blockers can absorb
    for p, sign in ((me, 1.0), (r, -1.0)):
        base = p * NZONE
        s_spent = sign * w_spent; s_ready = sign * w_ready; s_count = sign * w_count
        s_blocker = sign * w_blocker; s_gear = sign * w_gear
        # Iterating the live FIELD list (not the units() snapshot) is safe: nothing here mutates
        # the state, and the power_mod hooks in the pool are pure reads.
        for u in z[base + _FIELD]:                   # == s.units(p): same list, order and filter
            if i_host[u] != NO_INST:
                continue
            d = defs[i_card[u]]
            if d.type is _GEAR:
                continue
            # ---- power(s, u, ATTACKING) for a FIELD card: printed + Gear (act[5]) + temp + auras, clamp 0
            pw = d.power or 0
            gear = gear_of.get(u, ())
            for g in gear:
                pw += defs[i_card[g]].power or 0
            if temp_power:
                for target, delta, cond in temp_power:
                    if target == u and (cond == 0 or ATTACKING & cond == cond):
                        pw += delta
            if pm:
                if hooks is None:
                    hooks = [(hook, _ctx(s, i)) for i, hook in pm]
                for hook, c in hooks:
                    pw += hook(c, u, ATTACKING)
            if pw < 0:
                pw = 0
            spent = i_spent[u]
            v += (s_spent if spent else s_ready) * pw
            v += s_count
            # ---- (not spent) and has_keyword(s, u, BLOCKER): printed, then equipped Gear, then granted
            if spent:
                ready_blocker = False
            elif _BLOCKER in d.keywords:
                ready_blocker = True
            else:
                ready_blocker = False
                for g in gear:
                    if _BLOCKER in defs[i_card[g]].keywords:
                        ready_blocker = True
                        break
                else:
                    if mods and s.has_mod("kw", u) and _BLOCKER in s.mod_values("kw", u):
                        ready_blocker = True
                if not ready_blocker and kwm:
                    if kw_hooks is None:
                        kw_hooks = [(hook, _ctx(s, i)) for i, hook in kwm]
                    for hook, c in kw_hooks:
                        if hook(c, u, _BLOCKER):
                            ready_blocker = True
                            break
            if ready_blocker:
                v += s_blocker
            v += s_gear * len(gear)
            if p == r:
                if not spent:
                    threat += 0 if pw <= 0 else 1 + pw // 10   # steal_count(pw)
            elif ready_blocker:
                blockers += 1
        n_leg = 0
        fu = 0
        for i in z[base + _LEGENDS]:                 # == len(s.legends(p)) and its face-up sum
            if i_host[i] == NO_INST:
                n_leg += 1
                fu += i_faceup[i]
        v += sign * w_eddies * (len(z[base + _EDDIES]) + n_leg)
        v += sign * w_faceup * fu
        v += sign * w_removed * len(z[base + _REMOVED])
        v += sign * w_deck * len(z[base + _DECK])
    v += w["hand"] * len(z[me * NZONE + _HAND])
    # Counted whoever's turn it is, so ending the turn isn't "safe".
    v += w["threat"] * max(0, min(threat, g_me) - blockers)
    return v


def _equiv_key(s: GameState, a) -> tuple:
    """Options that differ only in *which copy* of a card they name are interchangeable."""
    inst = getattr(a, "inst", None)
    if inst is None or inst < 0:            # Pick has no inst attribute, so no name test is needed
        return (a,)
    host = getattr(a, "host", -1)
    return (type(a), s.i_card[inst], s.i_zone[inst], s.i_card[host] if host >= 0 else -1,
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
        rng = self.rng; me = self.me; options = choice.options
        for i in range(len(options)):
            key = _equiv_key(s, options[i])
            if key in seen:
                continue                                     # identical to an option already tried
            seen.add(key)
            c = s.clone()
            c.rng = Pcg32(rng.next_u32(), seq=3)             # never preview the true future
            apply(c, i)
            self._resolve(c, depth)
            # evaluate() runs before the draw (left operand first), so the per-option RNG order is
            # unchanged; next_u32() % 1000 == below(1000): its rejection threshold is 0.
            v = evaluate(c, me) + rng.next_u32() % 1000 * 1e-4
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
