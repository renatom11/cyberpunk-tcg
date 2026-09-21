"""Monotonicity (Stage 0 instrument): does a value head move the right way for a one-step
change it should never get wrong?

    python tools/monotonicity.py GAMES [--positions 500] [--seed 5] [--weights W.json | --cards W.npz [--ablate]] [--out J]

Positions are sampled uniformly over MAIN decisions of the corpus. Every perturbation is a
**rules-legal** state: the dice of the game are conserved (each player brought one of each size;
a stolen die sits in the thief's Gig area), because the first version of this tool added a die
to the Gig area while the same die stayed in the fixer — a state no game reaches — and the
card-aware model, which reads the dice as tokens, answered that impossible state with a 22%
violation rate that the legal version does not show. ``test_perturbations_conserve_the_dice``
pins it.

Counted in the overall rate (unambiguous under the rules):

* ``+gig``: the rival's last Gig die is stolen into the mover's area (value must not fall)
* ``-gig``: the mover's last Gig die is taken by the rival (must not rise)
* ``+ready``: a spent friendly Unit readied (must not fall)
* ``-unit``: a friendly Unit removed to the trash (must not rise)

Reported beside them but not counted (ambiguous, and every head is sensitive to it):

* ``+die`` / ``-die``: a die moves from the mover's fixer to their Gig area, or back. Taking a
  die advances the mover's own clock toward Overtime and, in the corpora, the fixer count is also
  a turn-parity signal (the player to move has taken this turn's die); the 114 heads and the
  card-aware head all lower their value for ``+die`` in a third to two thirds of positions.

The violation rate per perturbation is the share of positions where the head moves the wrong
way by more than ``--tol`` (0.005 win-probability points). A head that is exactly flat passes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.actions import ChoiceKind  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.enums import NO_INST, Zone  # noqa: E402
from cptcg.core.ops import move  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402


def _valuer(a):
    if a.cards:
        os.environ.setdefault("CPTCG_AGENT_PLUGINS", "cards_agents")
        import cards_agents as CA
        m = CA.load_cards_model(a.cards, a.ablate)
        return lambda s, me: 1.0 / (1.0 + math.exp(-float(CA._value_batch(m, [s], me)[0])))
    ag = make_agent("neural" + (f"@{a.weights}" if a.weights else ""), 1)
    return lambda s, me: float(ag.model.value(s, me))


def sample_positions(reg, path, n, seed):
    rng = Pcg32(seed, seq=23)
    games = list(read_games(path))
    out = []
    tries = 0
    while len(out) < n and tries < n * 20:
        tries += 1
        rec = games[rng.below(len(games))]
        ply = rng.below(max(1, len(rec.actions)))
        s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
        for k, idx in enumerate(rec.actions):
            legal_actions(s)
            if k == ply:
                break
            apply(s, idx)
        legal_actions(s)
        ch = s.pending
        if ch is not None and ch.kind is ChoiceKind.MAIN and not s.over:
            out.append(s)
    return out


def perturb(s, me, kind):
    """A rules-legal one-step change from the mover's seat, or None when it does not apply."""
    c = s.clone()
    c.pending = None
    r = 1 - me
    if kind == "+gig":
        if not c.gig[r]:
            return None
        die = c.gig[r][-1]
        c.gig[r] = c.gig[r][:-1]
        c.gig[me] = c.gig[me] + [die]
    elif kind == "-gig":
        if not c.gig[me]:
            return None
        die = c.gig[me][-1]
        c.gig[me] = c.gig[me][:-1]
        c.gig[r] = c.gig[r] + [die]
    elif kind == "+die":
        if not c.fixer[me]:
            return None
        sides = c.fixer[me][0]
        c.fixer[me] = c.fixer[me][1:]
        c.gig[me] = c.gig[me] + [(sides, max(1, sides // 2))]
    elif kind == "-die":
        if not c.gig[me]:
            return None
        sides, _v = c.gig[me][-1]
        c.gig[me] = c.gig[me][:-1]
        c.fixer[me] = c.fixer[me] + [sides]
    elif kind == "+ready":
        spent = [u for u in c.units(me) if c.i_spent[u]]
        if not spent:
            return None
        c.i_spent[spent[0]] = 0
    elif kind == "-unit":
        units = list(c.units(me))
        if not units:
            return None
        u = units[0]
        for g in [i for i in range(len(c.i_card)) if c.i_host[i] == u]:
            move(c, g, Zone.TRASH)
        move(c, u, Zone.TRASH)
    c.invalidate()
    return c


COUNTED = (("+gig", +1), ("-gig", -1), ("+ready", +1), ("-unit", -1))
REPORTED = (("+die", +1), ("-die", -1))


def dice_multiset(s) -> dict:
    """Die sizes over both players' Gig and fixer areas: what a legal perturbation conserves."""
    out: dict = {}
    for p in (0, 1):
        for sides, _v in s.gig[p]:
            out[sides] = out.get(sides, 0) + 1
        for sides in s.fixer[p]:
            out[sides] = out.get(sides, 0) + 1
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("games")
    ap.add_argument("--positions", type=int, default=500)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--tol", type=float, default=0.005)
    ap.add_argument("--weights", default=None)
    ap.add_argument("--cards", default=None)
    ap.add_argument("--ablate", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    reg = load_default()
    val = _valuer(a)
    positions = sample_positions(reg, a.games, a.positions, a.seed)
    stats = {}
    for kind, sign in COUNTED + REPORTED:
        n = viol = 0
        deltas = []
        for s in positions:
            me = s.pending.player
            base = s.clone()
            base.pending = None
            v0 = val(base, me)
            c = perturb(s, me, kind)
            if c is None:
                continue
            v1 = val(c, me)
            d = (v1 - v0) * sign
            deltas.append(d)
            n += 1
            if d < -a.tol:
                viol += 1
        deltas.sort()
        stats[kind] = {"n": n, "violations": viol, "violation_rate": viol / n if n else None,
                       "median_delta_signed": deltas[len(deltas) // 2] if deltas else None}
    counted = [k for k, _ in COUNTED]
    out = {"games": a.games, "positions": len(positions), "head": a.cards or a.weights or "shipped",
           "ablate": bool(a.ablate), "tol": a.tol, "perturbations": stats, "counted": counted,
           "reported_only": [k for k, _ in REPORTED],
           "overall_violation_rate": (sum(stats[k]["violations"] for k in counted)
                                      / max(1, sum(stats[k]["n"] for k in counted)))}
    print(json.dumps(out, indent=1))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
