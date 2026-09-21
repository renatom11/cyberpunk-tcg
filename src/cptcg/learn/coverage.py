"""Decision-space coverage: what every decision offered, what was chosen, materialised at harvest.

The unified design's Part 3 asks for accounting that is *independent of replay*: a stored action
index dies the day a card gains or loses a prompt, but "this card was offered a Play and it was
chosen" does not. So at harvest time every decision is reduced to a compact record --

    {"t": turn, "k": ChoiceKind value, "p": player, "off": [(card_id, kind, sub-mode), ...],
     "ch": chosen index, "v": root visit counts or None}

-- and the harvest sidecar carries the aggregate: offered and chosen counts per
``(card, kind, sub-mode)`` triple, per ChoiceKind, and per-kind entropy of the search's visit
distributions where a searching agent produced them. Sub-modes are the distinctions Part 3 names:
a Gear's host class, GO SOLO with or without the keyword, a Target's kind, a Pick's candidate
class (card, die, amount, mode, trigger, decline, yes).

Pure stdlib: this module runs in the harvest workers and can ship with the package.
"""

from __future__ import annotations

import math
from collections import Counter

from cptcg.core.actions import (Activate, Attack, Block, CallLegend, Choice, ChooseOrder, EndTurn,
                                GoSolo, Mulligan, Pass, Pick, Play, Sell, TakeGigDie, Target)
from cptcg.core.enums import NO_INST, TARGET_GIG, CardType, Zone
from cptcg.core.state import GameState

FORMAT = 1


def _pick_vals(ch: Choice):
    """The list a PICK's indices point into, read the way ``web.view._pick_env`` reads it."""
    try:
        cells = ch.cont.__closure__ or ()
        env = {nm: c.cell_contents for nm, c in zip(ch.cont.__code__.co_freevars, cells)}
    except Exception:  # noqa: BLE001
        return None
    return env.get("vals")


def _card_id(s: GameState, inst) -> str | None:
    if isinstance(inst, int) and 0 <= inst < len(s.i_card):
        return s.card(inst).id
    return None


def option_key(s: GameState, ch: Choice, a, vals=None) -> tuple:
    """``(card_id or None, kind, sub-mode)`` for one legal option, from the omniscient view.

    Coverage is about what the *card* was offered, so identities are read as they are, not as
    the seat knows them; this never feeds an agent.
    """
    if isinstance(a, EndTurn):
        return (None, "EndTurn", "")
    if isinstance(a, Pass):
        return (None, "Pass", "")
    if isinstance(a, Sell):
        return (_card_id(s, a.inst), "Sell", "")
    if isinstance(a, Play):
        sub = ""
        if a.host != NO_INST:
            sub = "gear:legend" if s.i_zone[a.host] == Zone.LEGENDS else "gear:unit"
        elif ch.kind.name == "REACTION":
            sub = "quick"
        return (_card_id(s, a.inst), "Play", sub)
    if isinstance(a, GoSolo):
        return (_card_id(s, a.inst), "GoSolo", "keyword" if a.keyword else "plain")
    if isinstance(a, CallLegend):
        return (_card_id(s, a.inst), "CallLegend", "reaction" if ch.kind.name == "REACTION" else "main")
    if isinstance(a, Activate):
        return (_card_id(s, a.inst), "Activate", f"ab{a.ability}" + (":quick" if ch.kind.name == "REACTION" else ""))
    if isinstance(a, Attack):
        return (_card_id(s, a.inst), "Attack", "")
    if isinstance(a, Target):
        if a.kind == TARGET_GIG:
            return (None, "Target", "gig")
        return (_card_id(s, a.inst), "Target", "unit")
    if isinstance(a, Block):
        return (_card_id(s, a.inst), "Block", "")
    if isinstance(a, TakeGigDie):
        return (None, "GigDie", f"d{a.sides}")
    if isinstance(a, Mulligan):
        return (None, "Mulligan", "keep" if a.keep else "mulligan")
    if isinstance(a, ChooseOrder):
        return (None, "Order", "first" if a.go_first else "second")
    if isinstance(a, Pick):
        return _pick_key(s, ch, a, vals)
    return (None, type(a).__name__, "")


def _pick_key(s: GameState, ch: Choice, a: Pick, vals) -> tuple:
    tag = ch.tag or ""
    owner_inst = None
    head = tag.split("@", 1)[0]
    if head.isdigit():
        owner_inst = int(head)
    effect = _card_id(s, owner_inst) if owner_inst is not None else None
    if not a.picks:
        return (effect, "Pick", "decline")
    if tag.endswith("@steal"):
        return (effect, "Pick", "die")
    if tag.endswith("@order"):
        v = vals[a.picks[0]] if vals is not None and a.picks[0] < len(vals) else None
        return (_card_id(s, v), "Pick", "trigger")
    if vals is None or a.picks[0] >= len(vals):
        return (effect, "Pick", "index")
    v = vals[a.picks[0]]
    if isinstance(v, bool):
        return (effect, "Pick", "yes")
    if isinstance(v, int):
        cid = _card_id(s, v)
        if cid is not None and len(a.picks) == 1 and "amount" not in tag:
            return (effect, "Pick", "card")
        return (effect, "Pick", "amount")
    if isinstance(v, tuple):
        if len(v) == 5:
            return (effect, "Pick", "adjust:" + ("up" if v[2] > 0 else "down"))
        if len(v) == 2 and isinstance(v[0], int):
            return (effect, "Pick", "die")
        return (effect, "Pick", "tuple")
    if isinstance(v, CardType):
        return (effect, "Pick", "type")
    return (effect, "Pick", type(v).__name__.lower())


def decision_record(s: GameState, ch: Choice, chosen: int, visits=None) -> dict:
    """One decision's coverage record. ``visits`` is the search's root visit list (per option)
    or None when the mover did not search."""
    vals = _pick_vals(ch) if ch.kind.name == "PICK" else None
    return {"t": s.turn, "k": int(ch.kind), "p": ch.player,
            "off": [option_key(s, ch, a, vals) for a in ch.options],
            "ch": chosen,
            "v": [int(x) for x in visits] if visits else None}


def _entropy(counts) -> float:
    tot = float(sum(counts))
    if tot <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / tot
            h -= p * math.log(p)
    return h


class Coverage:
    """Aggregate of decision records. ``to_json`` is what the harvest sidecar stores."""

    def __init__(self) -> None:
        self.offered: Counter = Counter()
        self.chosen: Counter = Counter()
        self.kind_decisions: Counter = Counter()
        self.kind_options: Counter = Counter()
        self.kind_entropy_sum: dict = {}
        self.kind_entropy_n: Counter = Counter()
        self.kind_searched: Counter = Counter()
        self.decisions = 0

    def add(self, rec: dict) -> None:
        self.decisions += 1
        k = rec["k"]
        self.kind_decisions[k] += 1
        self.kind_options[k] += len(rec["off"])
        for key in rec["off"]:
            self.offered[tuple(key)] += 1
        self.chosen[tuple(rec["off"][rec["ch"]])] += 1
        v = rec.get("v")
        if v:
            self.kind_searched[k] += 1
            self.kind_entropy_sum[k] = self.kind_entropy_sum.get(k, 0.0) + _entropy(v)
            self.kind_entropy_n[k] += 1

    def merge(self, other: "Coverage") -> None:
        self.offered.update(other.offered)
        self.chosen.update(other.chosen)
        self.kind_decisions.update(other.kind_decisions)
        self.kind_options.update(other.kind_options)
        for k, v in other.kind_entropy_sum.items():
            self.kind_entropy_sum[k] = self.kind_entropy_sum.get(k, 0.0) + v
        self.kind_entropy_n.update(other.kind_entropy_n)
        self.kind_searched.update(other.kind_searched)
        self.decisions += other.decisions

    @staticmethod
    def _k(key: tuple) -> str:
        return "|".join("" if x is None else str(x) for x in key)

    @staticmethod
    def _unk(sk: str) -> tuple:
        a, b, c = sk.split("|", 2)
        return (a or None, b, c)

    def to_json(self) -> dict:
        from cptcg.core.actions import ChoiceKind
        kinds = {}
        for k in sorted(self.kind_decisions):
            n = self.kind_decisions[k]
            kinds[ChoiceKind(k).name] = {
                "decisions": n, "mean_options": self.kind_options[k] / n,
                "searched": self.kind_searched[k],
                "mean_visit_entropy": (self.kind_entropy_sum.get(k, 0.0) / self.kind_entropy_n[k])
                if self.kind_entropy_n[k] else None}
        raw = {str(k): [self.kind_decisions[k], self.kind_options[k], self.kind_searched[k],
                        self.kind_entropy_sum.get(k, 0.0), self.kind_entropy_n[k]]
               for k in sorted(self.kind_decisions)}
        return {"format": FORMAT, "decisions": self.decisions, "kinds": kinds, "kinds_raw": raw,
                "offered": dict(sorted((self._k(k), v) for k, v in self.offered.items())),
                "chosen": dict(sorted((self._k(k), v) for k, v in self.chosen.items()))}

    @classmethod
    def from_json(cls, d: dict) -> "Coverage":
        """The inverse of ``to_json``, exact: a chunk's coverage merges into a run's."""
        c = cls()
        c.decisions = d.get("decisions", 0)
        c.offered = Counter({cls._unk(k): v for k, v in d.get("offered", {}).items()})
        c.chosen = Counter({cls._unk(k): v for k, v in d.get("chosen", {}).items()})
        for k, (nd, no, ns, es, en) in d.get("kinds_raw", {}).items():
            k = int(k)
            c.kind_decisions[k] = nd
            c.kind_options[k] = no
            c.kind_searched[k] = ns
            if en:
                c.kind_entropy_sum[k] = es
                c.kind_entropy_n[k] = en
        return c


def starvation(cov: Coverage, *, min_offered: int = 20, max_chosen: int = 0) -> list[tuple]:
    """Triples offered at least ``min_offered`` times and chosen at most ``max_chosen`` times.

    This is the *candidate* list; whether a starved mode is a training problem or rejected on
    the merits is decided by the value-head margin the report tool computes.
    """
    out = []
    for key, n in cov.offered.items():
        if n >= min_offered and cov.chosen.get(key, 0) <= max_chosen:
            out.append((key, n, cov.chosen.get(key, 0)))
    out.sort(key=lambda x: -x[1])
    return out
