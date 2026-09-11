"""Fit the policy head: make the training rows, fit them, and sweep the width.

    python tools/fit_policy.py make --games 400 --target value  --out out/pol/v
    python tools/fit_policy.py make --games 60  --target search --out out/pol/s
    python tools/fit_policy.py sweep out/pol/v --widths linear,2,4,8,16
    python tools/fit_policy.py fit  out/pol/v --hidden 8 --into src/cptcg/agents/weights.json

Two targets, and the difference between them is the whole question
------------------------------------------------------------------
``--target value`` distils the prior the search already uses: for each decision, softmax the
one-ply value-head previews and fit the policy to that. It is cheap — the rows come out of ordinary
greedy games — and what it buys is purely speed, the same ordering at a fraction of the cost.

``--target search`` fits the *visit distribution of a full ISMCTS search* instead. That is a
strictly better opinion, because it is what the whole search concluded rather than what one ply
guessed, and it is the target every project that has run this loop ended up using. It costs a real
search per row, so it is perhaps fifty times slower to collect.

Both are here because "is the expensive target worth it?" is a question with a number, and the
number is a held-out agreement rate between the fitted head and the target it was fitted to, plus
whatever the arena says afterwards. Publishing one without the other would be choosing by taste.

The rows
--------
Variable width: a decision with six legal moves is six rows sharing one group id, and the loss is a
cross-entropy *within a group*. The matrix is ``[group, target, ...NAFEAT features]`` as float32,
written with ``array('f').tofile`` exactly like the value trainer's, with a JSON header beside it.
Splitting is by **game**, never by row, for the same reason as the value head: the moves of one
decision share a normalisation and the decisions of one game share a player's habits.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from array import array
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.learn.decks import sample_pair  # noqa: E402
from cptcg.learn.features import features  # noqa: E402
from cptcg.learn.model import load_weights  # noqa: E402
from cptcg.learn.policy import (ACTION_FEATURE_NAMES, NAFEAT, PolicyModel,  # noqa: E402
                                action_feature_digest, action_features, write_beside)
from cptcg.sim.runner import new_game  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ------------------------------------------------------------------ making rows
class Recorder:
    """An agent wrapper that plays normally and writes down what it was asked and what it thought.

    It is a wrapper rather than a subclass so that the agent it records is *exactly* the registered
    one — the thing being distilled has to be the thing that plays, or the head is fitted to a
    player that does not exist.
    """

    def __init__(self, agent, target: str, model, prior_temp: float) -> None:
        self.agent, self.target, self.model, self.prior_temp = agent, target, model, prior_temp
        self.rows: list[tuple[int, float, tuple]] = []      # (group, target, features)
        self.group = 0
        self.decisions = 0
        self.name = getattr(agent, "name", "agent")
        self.uses_determinization = getattr(agent, "uses_determinization", False)
        self.cheating = getattr(agent, "cheating", False)

    def new_game(self, seed: int, me: int) -> None:
        self.agent.new_game(seed, me)

    def act(self, s, choice) -> int:
        i = self.agent.act(s, choice)
        opts = choice.options
        if len(opts) > 1:
            dist = self._target(s, choice)
            if dist is not None:
                self.group += 1
                me = choice.player
                for a, p in zip(opts, dist):
                    self.rows.append((self.group, p, action_features(s, me, a)))
                self.decisions += 1
        return i

    def _target(self, s, choice):
        opts = choice.options
        if self.target == "search":
            visits = getattr(self.agent, "last_visits", None)
            if not visits:
                return None
            total = sum(visits.values())
            if total <= 0:
                return None
            return [visits.get(a, 0) / total for a in opts]
        # value: softmax the one-ply previews, which is the prior the search builds today
        me = choice.player
        raw = []
        for k in range(len(opts)):
            c = s.clone()
            c.rng = Pcg32(12345 + k, seq=3)
            apply(c, k)
            raw.append(12.0 if (c.over and c.winner == me)
                       else -12.0 if c.over else self.model.raw(features(c, me)))
        hi = max(raw)
        t = self.prior_temp or 1.0
        import math
        exps = [math.exp((v - hi) / t) for v in raw]
        total = sum(exps) or 1.0
        return [e / total for e in exps]


def _play(reg, decks, agents, seed: int, max_actions: int = 50_000):
    """``runner.play_game``'s loop, with the agents passed in as objects.

    The runner builds its agents from names, which is right for it — a worker process gets a
    string — and wrong here, because the whole point is to hand it a wrapper that writes down what
    the real agent was asked and what it thought. Same loop, same order, same ceiling.
    """
    s = new_game(reg, decks, seed, DEFAULT_CONFIG, record=False)
    for p, ag in enumerate(agents):
        ag.new_game(seed, p)
    n = 0
    while not s.over:
        legal_actions(s)
        ch = s.pending
        apply(s, agents[ch.player].act(s, ch))
        n += 1
        if n > max_actions:
            raise RuntimeError(f"game {seed} exceeded {max_actions} actions")
    return s


def cmd_make(a) -> int:
    model = load_weights()
    rng = Pcg32(a.seed, seq=99)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = array("f")
    header = {"kind": "policy-rows", "target": a.target, "agent": a.agent, "games": a.games,
              "seed": a.seed, "rules": DEFAULT_CONFIG.digest(), "when": _now(),
              "features": list(ACTION_FEATURE_NAMES), "feature_digest": action_feature_digest(),
              "cols": ["group", "target"] + list(ACTION_FEATURE_NAMES)}
    reg = load_default()
    t0 = time.perf_counter()
    groups = 0
    game_col: list[int] = []
    for i in range(a.games):
        decks = sample_pair(reg, rng)
        rec = Recorder(make_agent(a.agent, a.seed + i), a.target, model, a.prior_temp)
        other = make_agent(a.agent, a.seed + 100000 + i)
        before = len(rec.rows)
        _play(reg, decks, (rec, other), a.seed * 1000003 + i)
        for g, p, f in rec.rows[before:]:
            buf.append(float(g + groups))
            buf.append(float(p))
            for v in f:
                buf.append(float(v))
            game_col.append(i)
        groups += rec.group
        if (i + 1) % max(1, a.games // 10) == 0:
            done = len(buf) // (NAFEAT + 2)
            print(f"  {i + 1}/{a.games} games, {groups} decisions, {done} rows, "
                  f"{time.perf_counter() - t0:.0f}s", flush=True)
    rows = len(buf) // (NAFEAT + 2)
    with open(f"{out}.f32", "wb") as fh:
        buf.tofile(fh)
    header.update(rows=rows, groups=groups, cols_n=NAFEAT + 2, game=game_col,
                  seconds=round(time.perf_counter() - t0, 1))
    Path(f"{out}.json").write_text(json.dumps(header) + "\n", encoding="utf-8")
    print(f"\n{rows} rows over {groups} decisions from {a.games} games "
          f"({rows / max(1, groups):.1f} moves per decision), "
          f"{time.perf_counter() - t0:.0f}s")
    print(f"  {out}.f32 + {out}.json")
    return 0


# ------------------------------------------------------------------ the fit
def _load(prefix: str):
    import numpy as np
    head = json.loads(Path(f"{prefix}.json").read_text(encoding="utf-8"))
    if head.get("feature_digest") != action_feature_digest():
        raise SystemExit(f"{prefix}: fitted for a different move-feature list "
                         f"({head.get('feature_digest')} against {action_feature_digest()})")
    n = head["cols_n"]
    m = np.fromfile(f"{prefix}.f32", dtype="<f4").reshape(-1, n)
    return head, m[:, 0].astype(np.int64), m[:, 1].astype(np.float64), m[:, 2:].astype(np.float64)


def _split(head, group, holdout: float):
    """By game, never by row: the moves of one decision share a normalisation."""
    import numpy as np
    games = np.asarray(head["game"], dtype=np.int64)
    uniq = np.unique(games)
    cut = int(len(uniq) * (1.0 - holdout))
    train_games = set(uniq[:cut].tolist())
    is_train = np.array([g in train_games for g in games])
    return is_train


def _forward(W1, b1, w2, b2, X):
    import numpy as np
    return np.tanh(X @ W1.T + b1) @ w2 + b2


def _group_softmax(logits, group):
    """Softmax inside each decision. Shifted by the group max, so a big logit cannot overflow."""
    import numpy as np
    order = np.argsort(group, kind="stable")
    g = group[order]
    z = logits[order]
    starts = np.searchsorted(g, np.unique(g))
    ends = np.append(starts[1:], len(g))
    out = np.empty_like(z)
    for s_, e_ in zip(starts, ends):
        seg = z[s_:e_]
        seg = np.exp(seg - seg.max())
        out[s_:e_] = seg / seg.sum()
    back = np.empty_like(out)
    back[order] = out
    return back


def _agree(p, target, group):
    """Share of decisions where the head's best move is the target's best move."""
    import numpy as np
    order = np.argsort(group, kind="stable")
    g, a, b = group[order], p[order], target[order]
    starts = np.searchsorted(g, np.unique(g))
    ends = np.append(starts[1:], len(g))
    hit = 0
    for s_, e_ in zip(starts, ends):
        hit += int(np.argmax(a[s_:e_]) == np.argmax(b[s_:e_]))
    return hit / max(1, len(starts))


def train(X, y, group, is_train, *, hidden, l2, epochs, patience, seed, log=print):
    """Adam on the within-decision cross-entropy. ``hidden=0`` fits a linear head."""
    import numpy as np
    rs = np.random.RandomState(seed)
    d = X.shape[1]
    h = max(1, hidden) if hidden else 1
    lin = hidden == 0
    W1 = (rs.randn(h, d) * (1.0 / np.sqrt(d))) if not lin else np.zeros((1, d))
    b1 = np.zeros(h)
    w2 = rs.randn(h) * 0.1
    b2 = 0.0
    if lin:                                   # a linear head is one row of weights straight out
        W1 = rs.randn(1, d) * (1.0 / np.sqrt(d))
        w2 = np.array([1.0])
    tr, ho = is_train, ~is_train
    ps = [W1, b1, w2]
    ms = [np.zeros_like(p) for p in ps]
    vs = [np.zeros_like(p) for p in ps]
    best, best_w, bad, t = 1e18, None, 0, 0
    for ep in range(epochs):
        # full-batch: the matrices here are small (52 columns) and the loss is per decision, so
        # batching by decision would complicate the grouping for no measured gain
        Z = X[tr] @ W1.T + b1
        H = Z if lin else np.tanh(Z)
        logits = H @ w2 + b2
        p = _group_softmax(logits, group[tr])
        gl = (p - y[tr])                      # d(cross-entropy)/d(logit) inside a softmax group
        gw2 = H.T @ gl + l2 * w2
        gb2 = gl.sum()
        dH = np.outer(gl, w2)
        dZ = dH if lin else dH * (1 - H * H)
        gW1 = dZ.T @ X[tr] + l2 * W1
        gb1 = dZ.sum(axis=0)
        t += 1
        for k, (par, grad) in enumerate(zip(ps, [gW1, gb1, gw2])):
            ms[k] = 0.9 * ms[k] + 0.1 * grad
            vs[k] = 0.999 * vs[k] + 0.001 * grad * grad
            mhat = ms[k] / (1 - 0.9 ** t)
            vhat = vs[k] / (1 - 0.999 ** t)
            par -= 0.02 * mhat / (np.sqrt(vhat) + 1e-8)
        b2 -= 0.02 * gb2 / max(1.0, abs(gb2))
        ph = _group_softmax(_forward(W1, b1, w2, b2, X[ho]), group[ho])
        loss = float(-(y[ho] * np.log(np.clip(ph, 1e-12, 1))).sum() / max(1, len(np.unique(group[ho]))))
        if loss < best - 1e-6:
            best, best_w, bad = loss, (W1.copy(), b1.copy(), w2.copy(), b2), 0
        else:
            bad += 1
            if bad >= patience:
                log(f"    stopped at epoch {ep} (best {best:.4f})")
                break
    W1, b1, w2, b2 = best_w
    ph = _group_softmax(_forward(W1, b1, w2, b2, X[ho]), group[ho])
    return (W1, b1, w2, b2), best, _agree(ph, y[ho], group[ho])


def _model(parts, hidden) -> PolicyModel:
    W1, b1, w2, b2 = parts
    h = W1.shape[0]
    return PolicyModel(h, tuple(tuple(float(v) for v in row) for row in W1),
                       tuple(float(v) for v in b1), tuple(float(v) for v in w2), float(b2),
                       {"run": {"name": f"policy-h{hidden}", "when": _now()}})


def cmd_fit(a) -> int:
    head, group, y, X = _load(a.rows)
    is_train = _split(head, group, a.holdout)
    print(f"{len(y)} rows over {len(set(group.tolist()))} decisions, "
          f"{is_train.sum()} training rows; target {head['target']!r}")
    parts, loss, agree = train(X, y, group, is_train, hidden=a.hidden, l2=a.l2,
                               epochs=a.epochs, patience=a.patience, seed=a.seed)
    m = _model(parts, a.hidden)
    m.header["run"].update(rows=int(len(y)), target=head["target"], holdout_loss=loss,
                           holdout_agreement=agree, source=a.rows)
    print(f"held-out cross-entropy {loss:.4f}, top-move agreement {agree * 100:.1f}%")
    if a.into:
        write_beside(a.into, m)
        print(f"written into {a.into} beside the value head")
    else:
        p = m.save(a.out or f"{a.rows}-policy.json")
        print(f"written to {p}")
    return 0


def cmd_sweep(a) -> int:
    head, group, y, X = _load(a.rows)
    is_train = _split(head, group, a.holdout)
    widths = [0 if w.strip() == "linear" else int(w) for w in a.widths.split(",")]
    print(f"target {head['target']!r}, {len(y)} rows over "
          f"{len(set(group.tolist()))} decisions\n")
    print(f"| width | params | held-out cross-entropy | top-move agreement |")
    print(f"|---|---:|---:|---:|")
    for w in widths:
        parts, loss, agree = train(X, y, group, is_train, hidden=w, l2=a.l2, epochs=a.epochs,
                                   patience=a.patience, seed=a.seed, log=lambda *_: None)
        params = (max(1, w) * NAFEAT + 2 * max(1, w) + 1) if w else NAFEAT + 1
        print(f"| {'linear' if w == 0 else w} | {params} | {loss:.4f} | {agree * 100:.1f}% |")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/fit_policy.py", description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n".join(__doc__.splitlines()[2:8]))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("make", help="play games and write the training rows")
    p.add_argument("--games", type=int, default=200)
    p.add_argument("--agent", default="neural", help="the player being distilled")
    p.add_argument("--target", choices=("value", "search"), default="value")
    p.add_argument("--prior-temp", type=float, default=0.3, help="softmax temperature for --target value")
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_make)

    for name in ("fit", "sweep"):
        p = sub.add_parser(name, help="fit the head" if name == "fit" else "cross-entropy by width")
        p.add_argument("rows")
        p.add_argument("--holdout", type=float, default=0.2)
        p.add_argument("--l2", type=float, default=1e-4)
        p.add_argument("--epochs", type=int, default=400)
        p.add_argument("--patience", type=int, default=30)
        p.add_argument("--seed", type=int, default=0)
        if name == "fit":
            p.add_argument("--hidden", type=int, default=8, help="0 for a linear head")
            p.add_argument("--into", default=None, help="a weights.json to write the policy into")
            p.add_argument("--out", default=None)
            p.set_defaults(fn=cmd_fit)
        else:
            p.add_argument("--widths", default="linear,2,4,8,16")
            p.set_defaults(fn=cmd_sweep)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
