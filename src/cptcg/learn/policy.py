"""What a *move* looks like: the policy head's input, and the head itself.

``action_features(s, me, action)`` describes one legal move in one position, and ``PolicyModel``
turns that into a logit. A softmax over the legal moves is a prior — an opinion about which move
to look at first, before any of them have been tried.

Why a policy head at all, when there is already a value head
-----------------------------------------------------------
Because they buy different things, and the search only has one of them today.

``IsmctsAgent._priors`` builds its prior by *playing each move and scoring the result*: clone,
apply, settle, extract 114 features, run the network. Measured on this container that is about
107 us per option, and a node with six children pays 640 us before it can choose between them.
It is a good prior — it is the value head, which is calibrated — and it is the single most
expensive thing the search does.

A policy head does not play the move. It reads the move: what kind it is, what it costs against
what is available, what type of card it names, how big that card is, whether the board is in a
state where that kind of move tends to matter. That is a *worse* opinion per move and a much
cheaper one, and the trade is the point. A search is a budget of nodes, and the way to get more of
them is to stop paying a clone for every child before you have any reason to look at it. The value
head then decides what the leaf is actually worth, which is what it is good at.

Measured here, median over 300 calls on a real 13-option main menu (the value-head prior on the
same node costs 82.4 us per move: clone, apply, 114 features, network)::

    width    params   us/move   vs the value prior   a 13-child node
    linear       53       8.4         9.8x                110 us
    2           109      10.0         8.3x                130 us
    4           217      12.6         6.6x                163 us
    8           433      17.6         4.7x                228 us
    16          865      27.7         3.0x                361 us
    32        1,729      48.1         1.7x                625 us

Extracting the 52 move features is 7.2 us of that and is the floor: a linear head is almost all
floor, so there is no point going below width 2. The *accuracy* half of this trade is not measured
yet — nothing has been fitted — so the shipped width is a placeholder and the sweep that picks it
is the next measurement, not a decision already taken. What the table does settle is that the
expensive end is pointless: at width 32 the head costs more than half the prior it replaces and
the whole argument for having one has gone.

This is the division of labour every engine that has run this loop converged on: a cheap policy
orders the moves, an expensive value judges the positions, and the search spends its budget where
the policy says to look. It is also the piece that attacks the failure Stage 3 could not fix.
``two-pieces-of-gear`` needs both Gear equipped *before* an attack, and no amount of better
evaluation finds it, because the first equip scores as a rounding error however well you score it.
What finds it is depth, and depth is bought by not wasting nodes.

What it may read
----------------
The same mask ``features.py`` obeys, for the same reason. A face-down Legend's identity is not
readable, so ``CallLegend`` on one is described by the *slot* — is it ready, is it the last one —
and every card-identity feature is left at zero with ``act_unknown_card`` raised. Inside the
search this is being called on a determinized world where the sampled identity is the world's
truth, which is exactly what determinization is for; the mask still holds at the root and anywhere
else it is called on a real state. ``tests/learn/test_policy.py`` checks it against a permuted
state, the same way the value features are checked.

Everything lands in [0, 1] or, where a difference is signed, [-1, 1], and everything is clipped.
"""

from __future__ import annotations

import json
import math
from operator import mul
from pathlib import Path

from cptcg.core.actions import (Action, Activate, Attack, Block, CallLegend, ChooseOrder, EndTurn,
                                GoSolo, Mulligan, Pass, Pick, Play, Sell, TakeGigDie, Target)
from cptcg.core.enums import NO_INST, TARGET_GIG, CardType, Keyword, Zone
from cptcg.core.ops import available, play_cost, power
from cptcg.core.state import ONCE_SOLD, GameState
from cptcg.core.config import DEFAULT_CONFIG
from cptcg.core.view import knows_identity

#: Bumped with the value head's, because they are written by the same trainer and read by the same
#: agent; a reader that understands one understands the other.
FORMAT = 1
_RULES = DEFAULT_CONFIG.digest()
_SUMPROD = getattr(math, "sumprod", None) or (lambda a, b: sum(map(mul, a, b)))
_TANH = math.tanh
_EXP = math.exp

#: The kinds of move, in a fixed order. One-hot, because the kind is the single most informative
#: thing about a move and a network should not have to discover an ordering that does not exist.
KINDS: tuple[type, ...] = (EndTurn, Sell, Play, GoSolo, CallLegend, Activate, Attack, Target,
                           Block, Pass, Pick, Mulligan, ChooseOrder, TakeGigDie)

_SPEC: tuple[tuple[str, str], ...] = (
    # --- which kind of move it is --------------------------------------------------------------
    *((f"act_is_{k.__name__.lower()}", "one-hot over move kind") for k in KINDS),
    # --- what it costs, against what there is ---------------------------------------------------
    ("act_cost", "the move's cost in euro / 7"),
    ("act_cost_share", "the move's cost as a share of the euro available"),
    ("act_free", "1 if the move costs nothing"),
    ("act_spends_all", "1 if the move spends every euro available"),
    # --- the card it names ----------------------------------------------------------------------
    ("act_unknown_card", "1 if the move names a card this seat may not identify"),
    ("act_card_unit", "the named card is a Unit"),
    ("act_card_program", "the named card is a Program"),
    ("act_card_gear", "the named card is Gear"),
    ("act_card_legend", "the named card is a Legend"),
    ("act_card_power", "printed power of the named card / 15"),
    ("act_card_ram", "RAM of the named card / 5"),
    ("act_card_sellable", "the named card carries a sell tag"),
    ("act_card_blocker", "the named card has BLOCKER"),
    ("act_card_quick", "the named card has QUICK"),
    ("act_card_gosolo", "the named card has GO SOLO"),
    # --- where the card is, and what state it is in ---------------------------------------------
    ("act_from_hand", "the named card is in my hand"),
    ("act_from_field", "the named card is on the field"),
    ("act_from_legends", "the named card is a Legend slot"),
    ("act_card_spent", "the named card is spent"),
    ("act_card_lagged", "the named card has Lag"),
    ("act_has_host", "Gear: it is being equipped to something"),
    ("act_host_power", "Gear: current power of the host / 15"),
    # --- what the move does on the board --------------------------------------------------------
    ("act_live_power", "current power of the attacker or Unit named / 15"),
    ("act_power_vs_best_rival", "(named power - biggest rival power) / 15, signed"),
    ("act_target_gig", "Target: it is the rival's Gig area rather than a Unit"),
    ("act_steals", "Target on the Gig area: dice this would steal / 3"),
    ("act_die_sides", "TakeGigDie: sides / 20"),
    ("act_die_is_last", "TakeGigDie: it is the only die left in the fixer"),
    ("act_keep", "Mulligan/ChooseOrder: the 'keep' or 'go first' branch"),
    ("act_picks", "Pick: how many things it picks / 3"),
    # --- the position it is being made in, in the few terms a move ordering needs -----------------
    ("pos_my_gigs", "my Gigs / 7"),
    ("pos_gig_lead", "(my Gigs - rival Gigs) / 7, signed"),
    ("pos_my_units", "my Units / 4"),
    ("pos_rival_units", "rival Units / 4"),
    ("pos_avail", "euro available to me / 7"),
    ("pos_hand", "cards in my hand / 8"),
    ("pos_overtime", "1 in Overtime"),
    ("pos_sold_already", "1 if the once-per-turn sale is gone"),
)

ACTION_FEATURE_NAMES: tuple[str, ...] = tuple(n for n, _ in _SPEC)
ACTION_FEATURE_SCALING: dict[str, str] = dict(_SPEC)
NAFEAT = len(_SPEC)

_KIND_INDEX = {k: i for i, k in enumerate(KINDS)}


def _u(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _b(x: float) -> float:
    return -1.0 if x < -1.0 else (1.0 if x > 1.0 else x)


def _named(a: Action) -> int:
    """The instance a move is about, or ``NO_INST``. One place, so a new action kind is one edit."""
    return getattr(a, "inst", NO_INST)


def action_features(s: GameState, me: int, a: Action) -> tuple[float, ...]:
    """Describe one legal move. No clone, no apply, no value head — that is the whole point."""
    f = [0.0] * NAFEAT
    idx = _KIND_INDEX.get(type(a))
    if idx is not None:
        f[idx] = 1.0
    o = len(KINDS)

    avail = available(s, me)
    inst = _named(a)

    # ---- cost
    cost = 0
    if isinstance(a, Play):
        cost = play_cost(s, me, inst)
    elif isinstance(a, GoSolo):
        cost = play_cost(s, me, inst, go_solo=True)
    elif isinstance(a, CallLegend):
        cost = 1
    f[o + 0] = _u(cost / 7.0)
    f[o + 1] = _u(cost / avail) if avail else 0.0
    f[o + 2] = 1.0 if cost == 0 else 0.0
    f[o + 3] = 1.0 if (cost and cost == avail) else 0.0

    # ---- the card it names, if this seat may identify it
    o += 4
    if inst is not None and inst >= 0:
        if not knows_identity(s, me, inst):
            f[o + 0] = 1.0
        else:
            d = s.card(inst)
            t = d.type
            f[o + 1] = 1.0 if t is CardType.UNIT else 0.0
            f[o + 2] = 1.0 if t is CardType.PROGRAM else 0.0
            f[o + 3] = 1.0 if t is CardType.GEAR else 0.0
            f[o + 4] = 1.0 if t is CardType.LEGEND else 0.0
            pw = d.power
            f[o + 5] = _u((pw if isinstance(pw, int) else 0) / 15.0)
            f[o + 6] = _u((d.ram or 0) / 5.0)
            f[o + 7] = 1.0 if d.sell_tag else 0.0
            kw = d.keywords
            f[o + 8] = 1.0 if Keyword.BLOCKER in kw else 0.0
            f[o + 9] = 1.0 if Keyword.QUICK in kw else 0.0
            f[o + 10] = 1.0 if Keyword.GO_SOLO in kw else 0.0

    # ---- where it is and what state it is in (public for every instance)
    o += 11
    if inst is not None and inst >= 0:
        z = s.i_zone[inst] % 8
        f[o + 0] = 1.0 if z == Zone.HAND else 0.0
        f[o + 1] = 1.0 if z == Zone.FIELD else 0.0
        f[o + 2] = 1.0 if z == Zone.LEGENDS else 0.0
        f[o + 3] = 1.0 if s.i_spent[inst] else 0.0
        f[o + 4] = 1.0 if s.i_lag[inst] else 0.0
    host = getattr(a, "host", NO_INST)
    if host is not None and host >= 0:
        f[o + 5] = 1.0
        f[o + 6] = _u(power(s, host) / 15.0)

    # ---- what it does on the board
    o += 7
    live = None
    if isinstance(a, (Attack, Block)) or (inst is not None and inst >= 0
                                          and s.i_zone[inst] % 8 == Zone.FIELD):
        live = power(s, inst)
        f[o + 0] = _u(live / 15.0)
    rival_best = max((power(s, u) for u in s.units(1 - me)), default=0)
    if live is not None:
        f[o + 1] = _b((live - rival_best) / 15.0)
    if isinstance(a, Target):
        if a.kind == TARGET_GIG:
            f[o + 2] = 1.0
            atk = s.atk
            p = power(s, atk.attacker) if atk is not None else 0
            f[o + 3] = _u((1 + p // 10) / 3.0)      # one die, plus one more per 10 power
    if isinstance(a, TakeGigDie):
        f[o + 4] = _u(a.sides / 20.0)
        f[o + 5] = 1.0 if len(s.fixer[me]) <= 1 else 0.0
    if isinstance(a, Mulligan):
        f[o + 6] = 1.0 if a.keep else 0.0
    elif isinstance(a, ChooseOrder):
        f[o + 6] = 1.0 if a.go_first else 0.0
    if isinstance(a, Pick):
        f[o + 7] = _u(len(a.picks) / 3.0)

    # ---- the position, in the few terms a move ordering needs
    o += 8
    mine, theirs = len(s.gig[me]), len(s.gig[1 - me])
    f[o + 0] = _u(mine / 7.0)
    f[o + 1] = _b((mine - theirs) / 7.0)
    f[o + 2] = _u(len(s.units(me)) / 4.0)
    f[o + 3] = _u(len(s.units(1 - me)) / 4.0)
    f[o + 4] = _u(avail / 7.0)
    f[o + 5] = _u(len(s.zone(me, Zone.HAND)) / 8.0)
    f[o + 6] = 1.0 if s.overtime else 0.0
    f[o + 7] = 1.0 if (s.once[me] & ONCE_SOLD) else 0.0
    return tuple(f)


# ------------------------------------------------------------------- the head
class PolicyModel:
    """One hidden layer over ``action_features``, out to a single logit per move.

    The same arithmetic as ``ValueModel`` and deliberately so — one hand-written forward pass to
    keep working under Pyodide, one numpy trainer in ``tools/`` — but a different contract. A value
    is calibrated and read on its own; a policy logit is only ever compared with the logits of the
    *other moves in the same position*, so nothing here is squashed and no probability is claimed.
    ``prior`` does the softmax that turns a set of them into one.
    """

    __slots__ = ("hidden", "w1", "b1", "w2", "b2", "header", "_rows")

    def __init__(self, hidden, w1, b1, w2, b2, header=None):
        self.hidden = hidden
        self.w1, self.b1, self.w2, self.b2 = w1, b1, w2, b2
        self.header = header or {}
        self._rows = tuple(zip(w1, b1, w2))

    def logit(self, x) -> float:
        out = self.b2
        for w, b, v in self._rows:
            out += v * _TANH(_SUMPROD(w, x) + b)
        return out

    def prior(self, s: GameState, me: int, actions, temp: float = 1.0) -> dict:
        """Softmax over the moves, at a temperature. The prior a search should look at first.

        Shifted by the maximum before exponentiating, which is not a nicety: an untrained head
        returns zeros and a badly-scaled one returns hundreds, and ``exp`` raises on the second.
        """
        raw = [self.logit(action_features(s, me, a)) for a in actions]
        if not raw:
            return {}
        hi = max(raw)
        t = temp or 1.0
        exps = [_EXP((v - hi) / t) for v in raw]
        total = sum(exps) or 1.0
        return {a: e / total for a, e in zip(actions, exps)}

    # ------------------------------------------------------------------- disk
    def to_json(self) -> dict:
        d = dict(self.header)
        d.update(format=FORMAT, kind="policy", hidden=self.hidden, activation="tanh",
                 features=list(ACTION_FEATURE_NAMES), feature_digest=action_feature_digest(),
                 rules=DEFAULT_CONFIG.digest(),
                 w1=[list(r) for r in self.w1], b1=list(self.b1),
                 w2=list(self.w2), b2=self.b2)
        return d

    @classmethod
    def from_json(cls, d: dict, *, rules: str | None = _RULES, where: str = "policy") -> "PolicyModel":
        """Refuse anything that would silently order moves by the wrong opinion.

        Same checks as the value head and for the same reason: a stale feature list or a changed
        ruling makes a plausible number out of a model that is not the one that was measured. The
        ``kind`` check is the one that is new — a value head and a policy head have the same shape
        on disk and mean entirely different things.
        """
        def bad(msg):
            return ValueError(f"{where}: {msg}")

        if d.get("format") != FORMAT:
            raise bad(f"format {d.get('format')!r}, this build reads {FORMAT}")
        if d.get("kind") != "policy":
            raise bad(f"kind {d.get('kind')!r}: this is a {d.get('kind')} head, not a policy head")
        if d.get("activation") != "tanh":
            raise bad(f"activation {d.get('activation')!r}, this build implements 'tanh'")
        names = list(d.get("features") or ())
        if names != list(ACTION_FEATURE_NAMES):
            if len(names) != NAFEAT:
                raise bad(f"{len(names)} move features, this build extracts {NAFEAT}")
            i = next(i for i, (a, b) in enumerate(zip(names, ACTION_FEATURE_NAMES)) if a != b)
            raise bad(f"move feature {i} is {names[i]!r} in the weights but "
                      f"{ACTION_FEATURE_NAMES[i]!r} here")
        if rules is not None and d.get("rules") != rules:
            raise bad(f"fitted under ruleset {d.get('rules')}, this build is {rules}")
        hidden = int(d["hidden"])
        w1 = tuple(tuple(float(v) for v in row) for row in d["w1"])
        b1 = tuple(float(v) for v in d["b1"])
        w2 = tuple(float(v) for v in d["w2"])
        if len(w1) != hidden or len(b1) != hidden or len(w2) != hidden:
            raise bad(f"hidden={hidden} but shapes are w1={len(w1)} b1={len(b1)} w2={len(w2)}")
        for i, row in enumerate(w1):
            if len(row) != NAFEAT:
                raise bad(f"w1 row {i} has {len(row)} weights, expected {NAFEAT}")
        header = {k: v for k, v in d.items()
                  if k not in ("w1", "b1", "w2", "b2", "format", "kind", "hidden", "activation",
                               "features", "feature_digest", "rules")}
        header["rules"] = d.get("rules")
        return cls(hidden, w1, b1, w2, float(d["b2"]), header)

    @classmethod
    def load(cls, path, *, rules: str | None = _RULES) -> "PolicyModel":
        p = Path(path)
        return cls.from_json(json.loads(p.read_text(encoding="utf-8")), rules=rules, where=str(p))

    def save(self, path) -> "Path":
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_json()) + "\n", encoding="utf-8")
        return p


def action_feature_digest(names=ACTION_FEATURE_NAMES) -> str:
    import hashlib
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()[:16]


def zeros(hidden: int = 16) -> PolicyModel:
    """An untrained head: every move equally likely. The honest state before a fit, and what the
    search falls back to rather than pretending to have an opinion."""
    return PolicyModel(hidden,
                       tuple(tuple(0.0 for _ in range(NAFEAT)) for _ in range(hidden)),
                       tuple(0.0 for _ in range(hidden)),
                       tuple(0.0 for _ in range(hidden)), 0.0,
                       {"run": {"name": "zeros"}})


_CACHE: dict = {}


def load_policy(path, *, rules: str | None = _RULES) -> PolicyModel:
    """Load once per process, like the value head: agents are rebuilt per game."""
    key = str(path)
    m = _CACHE.get(key)
    if m is None:
        m = _CACHE[key] = PolicyModel.load(path, rules=rules)
    return m


_BESIDE: dict = {}


def policy_in(path, *, rules: str | None = _RULES):
    """The policy head living in the same file as a value head, or ``None`` if there is not one.

    One file per generation, two heads inside it. A generation is a *player*, and a player is both
    halves; shipping them as two files invites the pair to come apart, and an agent pointed at
    ``gen-007/weights.json`` should get gen 7's opinion about moves as well as its opinion about
    positions without being told twice.

    ``ValueModel.from_json`` keeps unknown top-level keys in its header, so a combined file is
    still a perfectly ordinary value head to every reader that predates this. Returning ``None``
    rather than an untrained head is deliberate: the search falls back to the prior it already has,
    which is a real opinion, instead of a uniform one dressed up as a model.
    """
    key = str(path)
    if key in _BESIDE:
        return _BESIDE[key]
    m = None
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        blob = d.get("policy")
        if blob:
            m = PolicyModel.from_json(blob, rules=rules, where=f"{path}:policy")
    except FileNotFoundError:
        m = None
    _BESIDE[key] = m
    return m


def write_beside(weights_path, policy: PolicyModel) -> "Path":
    """Put a fitted policy head into an existing value-head file, leaving the value half alone."""
    p = Path(weights_path)
    d = json.loads(p.read_text(encoding="utf-8"))
    d["policy"] = policy.to_json()
    p.write_text(json.dumps(d) + "\n", encoding="utf-8")
    _BESIDE.pop(str(p), None)
    return p
