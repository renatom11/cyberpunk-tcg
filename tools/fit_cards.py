"""Card-aware value and policy heads: token rows from a corpus, a torch fit, an evaluation.

    python tools/fit_cards.py rows --in out/s0/h20k.jsonl.gz out/s0/r8k.jsonl.gz --out out/s0/excards \\
        [--rate 0.125] [--perspectives both] [--workers 4] [--max-games N]
    python tools/fit_cards.py fit out/s0/excards.npz [more.npz] --out out/s0/wcards.npz \\
        [--epochs 30] [--batch 256] [--lr 1e-3] [--holdout 0.2] [--policy-weight 0.5] [--patience 5]
    python tools/fit_cards.py eval out/s0/excards.npz --weights out/s0/wcards.npz [--ablate]

``rows`` replays every game of the corpus under the current engine (a corpus that no longer
replays is refused, exactly as ``tools/harvest.py examples`` refuses it) and keeps each decision
with probability ``--rate`` using the same per-game Bernoulli stream ``harvest examples`` uses, so
the two row sets are drawn from the same decisions. Every kept decision yields the mover's row
(tokens, context, aggregates, beliefs, the legal options, the chosen index, the search's visits
where the record has them) and, with ``--perspectives both``, the other seat's value-only row.
Labels are the game outcome for the row's seat (1 / 0 / 0.5), as ``learn.experience.outcome``.

``fit`` trains ``tools/cards_model.TorchCardsModel`` on CPU: Brier loss on the value head (the
same criterion ``tools/fit_eval.py`` uses for the 114-feature head, so the two are comparable),
cross-entropy on the policy head over the mover's legal options (target: the visit distribution
where present, else the chosen option), Adam, held-out games, early stopping on held-out value
Brier. The exported ``.npz`` carries the digests (rules, cards, features, tokens) and the fit's
numbers. ``eval`` scores a weights file on rows, with ``--ablate`` permuting the identity
embedding — the design's kill-test-1 ablation, on the held-out rows rather than on the panel.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import cards_model as CM  # noqa: E402
from cptcg.cards.registry import cards_digest, load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.learn import tokens as T  # noqa: E402
from cptcg.learn.policy import NAFEAT  # noqa: E402
from cptcg.learn.experience import outcome, read_games  # noqa: E402
from cptcg.learn.model import feature_digest  # noqa: E402

MASK64 = (1 << 64) - 1
ROWS_FORMAT = 1


def _keep_rng(harvest_seed: int, record_seed: int) -> Pcg32:
    return Pcg32((((record_seed * 2654435761) & MASK64) ^ harvest_seed) & MASK64, seq=311)


# ----------------------------------------------------------------------------- rows
class _Acc:
    """Flat, offset-indexed accumulation of ragged rows."""

    def __init__(self) -> None:
        self.cards, self.card_off = [], [0]
        self.dice, self.die_off = [], [0]
        self.opts, self.opt_off = [], [0]
        self.visits = []
        self.ctx, self.agg, self.bel_deck, self.bel_leg = [], [], [], []
        self.label, self.game, self.ply, self.mover, self.chosen = [], [], [], [], []

    def add(self, d: dict, label: float, game: int, ply: int, mover: int, chosen: int, visits) -> None:
        self.cards.extend(d["cards"]); self.card_off.append(len(self.cards))
        self.dice.extend(d["dice"]); self.die_off.append(len(self.dice))
        opts = d.get("options", ()) if mover else ()
        self.opts.extend(opts); self.opt_off.append(len(self.opts))
        if mover and visits and len(visits) == len(opts):
            self.visits.extend(int(v) for v in visits)
        else:
            self.visits.extend([-1] * len(opts))
        self.ctx.append(d["context"]); self.agg.append(d["aggregates"])
        self.bel_deck.append(d["belief_deck"]); self.bel_leg.append(d["belief_legends"])
        self.label.append(label); self.game.append(game); self.ply.append(ply)
        self.mover.append(mover); self.chosen.append(chosen if mover else -1)

    def arrays(self) -> dict:
        return {"cards": np.array(self.cards, dtype=np.int16).reshape(-1, len(T.CARD_TOKEN)),
                "card_off": np.array(self.card_off, dtype=np.int64),
                "dice": np.array(self.dice, dtype=np.int16).reshape(-1, len(T.DIE_TOKEN)),
                "die_off": np.array(self.die_off, dtype=np.int64),
                "opts": np.array(self.opts, dtype=np.float32).reshape(-1, 4 + NAFEAT),
                "opt_off": np.array(self.opt_off, dtype=np.int64),
                "visits": np.array(self.visits, dtype=np.int32),
                "ctx": np.array(self.ctx, dtype=np.int32).reshape(-1, len(T.CONTEXT)),
                "agg": np.array(self.agg, dtype=np.float32).reshape(-1, 114),
                "bel_deck": np.array(self.bel_deck, dtype=np.int8).reshape(-1, 124),
                "bel_leg": np.array(self.bel_leg, dtype=np.int8).reshape(-1, 27),
                "label": np.array(self.label, dtype=np.float32),
                "game": np.array(self.game, dtype=np.int32), "ply": np.array(self.ply, dtype=np.int16),
                "mover": np.array(self.mover, dtype=np.int8), "chosen": np.array(self.chosen, dtype=np.int16)}


def rows_chunk(job: tuple) -> dict:
    """Rows for one batch of records. Runs in a worker."""
    batch, rate, seed, both = job
    reg = load_default()
    acc = _Acc()
    cut = int(round(max(0.0, rate) * 10_000))
    n_dec = 0
    for gi, rec in batch:
        rng = _keep_rng(seed, rec.seed)
        s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
        for ply, idx in enumerate(rec.actions):
            legal_actions(s)
            ch = s.pending
            n_dec += 1
            keep = rate >= 1.0 or rng.below(10_000) < cut
            if keep and len(ch.options) > 1:
                me = ch.player
                d = T.decision_tokens(s, me, ch)
                v = rec.visits[ply] if (rec.visits and ply < len(rec.visits) and rec.visits[ply]) else None
                acc.add(d, outcome(rec, me), gi, ply, 1, idx, v)
                if both:
                    d2 = T.decision_tokens(s, 1 - me, ch)
                    d2["options"] = ()
                    acc.add(d2, outcome(rec, 1 - me), gi, ply, 0, -1, None)
            apply(s, idx)
    out = acc.arrays()
    out["n_decisions"] = n_dec
    return out


def cmd_rows(a) -> None:
    t0 = time.time()
    records = []
    gi = 0
    for src in a.inputs:
        for rec in read_games(src):
            records.append((gi, rec))
            gi += 1
            if a.max_games and gi >= a.max_games:
                break
        if a.max_games and gi >= a.max_games:
            break
    both = a.perspectives == "both"
    chunk = max(1, len(records) // max(1, (a.workers or 1) * 8))
    jobs = [(records[i:i + chunk], a.rate, a.seed, both) for i in range(0, len(records), chunk)]
    parts = []
    if (a.workers or 1) > 1:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for p in ex.map(rows_chunk, jobs):
                parts.append(p)
                print(f"  {len(parts)}/{len(jobs)} chunks", file=sys.stderr)
    else:
        for j in jobs:
            parts.append(rows_chunk(j))
    merged: dict = {}
    n_dec = sum(p.pop("n_decisions") for p in parts)
    for key in parts[0]:
        if key.endswith("_off"):
            offs = [parts[0][key]]
            base = int(parts[0][key][-1])
            for p in parts[1:]:
                offs.append(p[key][1:] + base)
                base += int(p[key][-1])
            merged[key] = np.concatenate(offs)
        else:
            merged[key] = np.concatenate([p[key] for p in parts])
    meta = {"format": ROWS_FORMAT, "rows": int(len(merged["label"])), "decisions": n_dec,
            "games": len(records), "rate": a.rate, "seed": a.seed, "perspectives": a.perspectives,
            "sources": [str(x) for x in a.inputs], "rules": DEFAULT_CONFIG.digest(), "cards": cards_digest(),
            "feature_digest": feature_digest(), "tokens_digest": T.tokens_digest(),
            "mean_label": float(merged["label"].mean()) if len(merged["label"]) else None,
            "seconds": round(time.time() - t0, 1)}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(out) + ".npz", meta=json.dumps(meta), **merged)
    print(f"{meta['rows']} rows from {meta['decisions']} decisions in {meta['games']} games "
          f"({meta['seconds']}s) -> {out}.npz")


# ----------------------------------------------------------------------------- loading rows
def load_rows(paths: list[str]) -> tuple[dict, list[dict]]:
    """Concatenate row files; game ids are renumbered across files."""
    merged: dict = {}
    metas = []
    game_base = 0
    for p in paths:
        z = np.load(p, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        if meta["rules"] != DEFAULT_CONFIG.digest():
            raise SystemExit(f"{p}: rows are for ruleset {meta['rules']}, this build is {DEFAULT_CONFIG.digest()}")
        if meta["tokens_digest"] != T.tokens_digest():
            raise SystemExit(f"{p}: token layout {meta['tokens_digest']} != {T.tokens_digest()}")
        metas.append(meta)
        part = {k: z[k] for k in z.files if k != "meta"}
        part["game"] = part["game"] + game_base
        game_base = int(part["game"].max()) + 1 if len(part["game"]) else game_base
        if not merged:
            merged = part
            continue
        for key in part:
            if key.endswith("_off"):
                merged[key] = np.concatenate([merged[key], part[key][1:] + merged[key][-1]])
            else:
                merged[key] = np.concatenate([merged[key], part[key]])
    return merged, metas


def gather(rows: dict, idx: np.ndarray) -> dict:
    """Padded batch arrays for the row indices ``idx`` (a numpy re-implementation of
    ``cards_model.batch_tokens`` straight from the flat arrays)."""
    n = len(idx)
    co, do_, oo = rows["card_off"], rows["die_off"], rows["opt_off"]
    ncards = co[idx + 1] - co[idx]
    ndice = do_[idx + 1] - do_[idx]
    nopts = oo[idx + 1] - oo[idx]
    C, K, O = int(ncards.max()), int(max(1, ndice.max())), int(max(1, nopts.max()))
    card_id = np.full((n, C), -1, dtype=np.int32)
    card_st = np.zeros((n, C, CM.CARD_STATE), dtype=np.float32)
    die = np.zeros((n, K, CM.DIE_FEATS), dtype=np.float32)
    die_m = np.zeros((n, K), dtype=np.float32)
    opt_id = np.full((n, O), -1, dtype=np.int32)
    opt_f = np.zeros((n, O, 3 + NAFEAT), dtype=np.float32)
    opt_m = np.zeros((n, O), dtype=np.float32)
    visits = np.full((n, O), -1, dtype=np.int32)
    die_scale = np.array([1, 20, 20, 1, 1, 1, 1, 1, 1], dtype=np.float32)
    for i, r in enumerate(idx):
        c = rows["cards"][co[r]:co[r + 1]]
        m = len(c)
        if m:
            card_id[i, :m] = c[:, 0]
            zone = np.minimum(c[:, 1], 7)
            card_st[i, np.arange(m), zone] = 1.0
            card_st[i, :m, 8:] = np.stack([c[:, 2], c[:, 3], c[:, 4], c[:, 5], c[:, 6], np.minimum(c[:, 7], 10) / 10.0,
                                           np.minimum(c[:, 8], 3) / 3.0, c[:, 9], c[:, 10], c[:, 11]], axis=1)
        d = rows["dice"][do_[r]:do_[r + 1]]
        if len(d):
            die[i, :len(d)] = d.astype(np.float32) / die_scale
            die_m[i, :len(d)] = 1.0
        o = rows["opts"][oo[r]:oo[r + 1]]
        if len(o):
            opt_id[i, :len(o)] = o[:, 0].astype(np.int32)
            opt_f[i, :len(o), 0] = o[:, 1] / 14.0
            opt_f[i, :len(o), 1] = o[:, 2] / 23.0
            opt_f[i, :len(o), 2] = o[:, 3] / 11.0
            opt_f[i, :len(o), 3:] = o[:, 4:]
            opt_m[i, :len(o)] = 1.0
            visits[i, :len(o)] = rows["visits"][oo[r]:oo[r + 1]]
    ctx = np.stack([CM._ctx_vec(tuple(int(x) for x in rows["ctx"][r])) for r in idx])
    bel = np.concatenate([rows["bel_deck"][idx].astype(np.float32) / 3.0, rows["bel_leg"][idx].astype(np.float32)], axis=1)
    return {"card_id": card_id, "card_st": card_st, "die": die, "die_m": die_m, "ctx": ctx,
            "agg": rows["agg"][idx], "bel": bel, "atk_id": rows["ctx"][idx, 3].astype(np.int32),
            "opt_id": opt_id, "opt_f": opt_f, "opt_m": opt_m, "visits": visits,
            "label": rows["label"][idx], "mover": rows["mover"][idx], "chosen": rows["chosen"][idx]}


def split_by_game(game: np.ndarray, holdout: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    games = np.unique(game)
    rng.shuffle(games)
    n_hold = int(round(len(games) * holdout))
    hold = set(games[:n_hold].tolist())
    mask = np.array([g in hold for g in game])
    return np.nonzero(~mask)[0], np.nonzero(mask)[0]


# ----------------------------------------------------------------------------- fit
def _to_torch(b: dict, torch):
    return {k: torch.from_numpy(np.ascontiguousarray(v)) for k, v in b.items()}


def _eval_value(model, rows, idx, torch, batch=512, ablate_seed=None) -> dict:
    """Held-out Brier (value) and top-1 policy agreement on mover rows."""
    model.eval()
    emb_backup = None
    if ablate_seed is not None:
        emb_backup = model.p["emb"].data.clone()
        rng = np.random.default_rng(ablate_seed)
        perm = torch.from_numpy(rng.permutation(CM.NCARDS))
        model.p["emb"].data[:CM.NCARDS] = emb_backup[:CM.NCARDS][perm]
    se = 0.0
    n = 0
    agree = 0
    n_mover = 0
    with torch.no_grad():
        for i in range(0, len(idx), batch):
            b = gather(rows, idx[i:i + batch])
            tb = _to_torch(b, torch)
            p = torch.sigmoid(model.value_logit(tb))
            se += float(((p - tb["label"]) ** 2).sum())
            n += len(p)
            mv = b["mover"] > 0
            if mv.any():
                lg = model.policy_logits(tb)
                top = lg.argmax(-1).numpy()
                agree += int((top[mv] == b["chosen"][mv]).sum())
                n_mover += int(mv.sum())
    if emb_backup is not None:
        model.p["emb"].data.copy_(emb_backup)
    return {"brier": se / max(n, 1), "rows": n, "policy_top1": agree / max(n_mover, 1), "mover_rows": n_mover}


def cmd_fit(a) -> None:
    import torch
    torch.set_num_threads(a.threads)
    torch.manual_seed(a.seed)
    rows, metas = load_rows(a.rows)
    reg = load_default()
    static = CM.static_card_table(reg)
    model = CM.torch_model(static, emb=a.embed, dropout=a.dropout)
    train_idx, hold_idx = split_by_game(rows["game"], a.holdout, a.seed)
    print(f"rows {len(rows['label'])}: train {len(train_idx)} holdout {len(hold_idx)}; "
          f"params {sum(p.numel() for p in model.parameters())}")
    const = float(((rows["label"][hold_idx] - rows["label"][train_idx].mean()) ** 2).mean())
    opt = torch.optim.Adam(model.parameters(), lr=a.lr, weight_decay=a.l2)
    best = None
    best_state = None
    since = 0
    history = []
    rng = np.random.default_rng(a.seed)
    t0 = time.time()
    for epoch in range(a.epochs):
        model.train()
        order = train_idx.copy()
        rng.shuffle(order)
        tot_v = tot_p = 0.0
        nb = 0
        for i in range(0, len(order), a.batch):
            b = gather(rows, order[i:i + a.batch])
            tb = _to_torch(b, torch)
            p = torch.sigmoid(model.value_logit(tb))
            loss_v = ((p - tb["label"]) ** 2).mean()
            loss = loss_v
            mv = tb["mover"] > 0
            if a.policy_weight > 0 and bool(mv.any()):
                lg = model.policy_logits(tb)[mv]
                vis = tb["visits"][mv].float()
                has_vis = (vis.max(-1).values > 0)
                target = torch.zeros_like(lg)
                ch = tb["chosen"][mv].long()
                target[torch.arange(len(ch)), ch] = 1.0
                if bool(has_vis.any()):
                    vv = vis.clamp(min=0)
                    vv = vv / vv.sum(-1, keepdim=True).clamp(min=1)
                    target[has_vis] = vv[has_vis]
                logp = torch.log_softmax(lg, -1)
                loss_p = -(target * logp).sum(-1).mean()
                loss = loss + a.policy_weight * loss_p
                tot_p += loss_p.item()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            tot_v += loss_v.item()
            nb += 1
        ev = _eval_value(model, rows, hold_idx, torch)
        history.append({"epoch": epoch + 1, "train_brier": tot_v / max(nb, 1), "train_policy_ce": tot_p / max(nb, 1),
                        "holdout_brier": ev["brier"], "holdout_policy_top1": ev["policy_top1"],
                        "seconds": round(time.time() - t0, 1)})
        h = history[-1]
        print(f"epoch {h['epoch']:3d}  train brier {h['train_brier']:.5f}  ce {h['train_policy_ce']:.4f}  "
              f"holdout brier {h['holdout_brier']:.5f}  top1 {h['holdout_policy_top1']:.3f}  {h['seconds']}s")
        if best is None or ev["brier"] < best - 1e-6:
            best = ev["brier"]
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            since = 0
        else:
            since += 1
            if since >= a.patience:
                print(f"early stop: no held-out improvement for {a.patience} epochs")
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    ev = _eval_value(model, rows, hold_idx, torch)
    abl = _eval_value(model, rows, hold_idx, torch, ablate_seed=20260921)
    meta = {"name": a.name, "rows": int(len(rows["label"])), "train_rows": int(len(train_idx)),
            "holdout_rows": int(len(hold_idx)), "sources": [m["sources"] for m in metas],
            "rules": DEFAULT_CONFIG.digest(), "cards": cards_digest(), "feature_digest": feature_digest(),
            "tokens_digest": T.tokens_digest(), "static_cols": int(static.shape[1]),
            "holdout": {"const": const, "network": ev["brier"], "policy_top1": ev["policy_top1"],
                        "ablated_network": abl["brier"], "ablated_policy_top1": abl["policy_top1"]},
            "history": history, "epochs": len(history), "lr": a.lr, "batch": a.batch, "l2": a.l2,
            "policy_weight": a.policy_weight, "embed": a.embed, "dropout": a.dropout, "seed": a.seed,
            "seconds": round(time.time() - t0, 1)}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    model.export_npz(str(out), meta)
    print(json.dumps(meta["holdout"], indent=1))
    print(f"wrote {out}")


def cmd_fit114(a) -> None:
    """Fit the 114-feature head (``learn.model.ValueModel``: tanh hidden layer, Brier loss) on the
    SAME rows and the SAME by-game split as ``fit`` uses for the card-aware model, so the two
    heads in kill test 1 differ only in what they read. Exported in ``weights.json`` format."""
    import torch
    from cptcg.learn.features import FEATURE_NAMES
    from cptcg.learn.model import feature_digest, FORMAT as VFORMAT
    torch.manual_seed(a.seed)
    torch.set_num_threads(a.threads)
    rows, metas = load_rows(a.rows)
    train_idx, hold_idx = split_by_game(rows["game"], a.holdout, a.seed)
    X = torch.from_numpy(rows["agg"].astype(np.float32))
    y = torch.from_numpy(rows["label"].astype(np.float32))
    n_in = X.shape[1]
    w1 = torch.nn.Parameter(torch.randn(a.hidden, n_in) * (1.0 / n_in) ** 0.5)
    b1 = torch.nn.Parameter(torch.zeros(a.hidden))
    w2 = torch.nn.Parameter(torch.randn(a.hidden) * (1.0 / a.hidden) ** 0.5)
    b2 = torch.nn.Parameter(torch.zeros(1))
    params = [w1, b1, w2, b2]
    opt = torch.optim.Adam(params, lr=a.lr, weight_decay=a.l2)

    def fwd(xb):
        return torch.sigmoid(torch.tanh(xb @ w1.T + b1) @ w2 + b2)

    def brier(idx):
        with torch.no_grad():
            tot = 0.0
            for k in range(0, len(idx), 8192):
                sl = idx[k:k + 8192]
                tot += float(((fwd(X[sl]) - y[sl]) ** 2).sum())
            return tot / max(1, len(idx))
    best, best_state, since = 1e9, None, 0
    rng = np.random.default_rng(a.seed)
    t0 = time.time()
    ep = 0
    for ep in range(1, a.epochs + 1):
        order = train_idx.copy()
        rng.shuffle(order)
        for k in range(0, len(order), a.batch):
            sl = order[k:k + a.batch]
            opt.zero_grad()
            loss = ((fwd(X[sl]) - y[sl]) ** 2).mean()
            loss.backward()
            opt.step()
        hb = brier(hold_idx)
        print(f"epoch {ep:3d}  train brier {brier(train_idx):.5f}  holdout brier {hb:.5f}  {time.time() - t0:.0f}s", flush=True)
        if hb < best - 1e-5:
            best, since = hb, 0
            best_state = [p.detach().clone() for p in params]
        else:
            since += 1
            if since >= a.patience:
                print(f"early stop: no held-out improvement for {a.patience} epochs")
                break
    w1v, b1v, w2v, b2v = [p.numpy() for p in best_state]
    out = {"run": {"tool": "fit_cards.py fit114", "rows": [str(r) for r in a.rows], "seed": a.seed,
                   "holdout": a.holdout, "train_rows": int(len(train_idx)), "holdout_rows": int(len(hold_idx)),
                   "holdout_brier": best},
           "train": {"lr": a.lr, "l2": a.l2, "batch": a.batch, "epochs": ep, "patience": a.patience},
           "format": VFORMAT, "kind": "value", "hidden": a.hidden, "activation": "tanh",
           "features": list(FEATURE_NAMES), "feature_digest": feature_digest(),
           "rules": DEFAULT_CONFIG.digest(), "cards": cards_digest(),
           "w1": [[float(v) for v in row] for row in w1v], "b1": [float(v) for v in b1v],
           "w2": [float(v) for v in w2v], "b2": float(b2v[0])}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out), encoding="utf-8")
    print(f"wrote {a.out}: hidden {a.hidden}, holdout Brier {best:.5f}")


def cmd_eval(a) -> None:
    import torch
    rows, _ = load_rows(a.rows)
    reg = load_default()
    static = CM.static_card_table(reg)
    z = np.load(a.weights, allow_pickle=False)
    model = CM.torch_model(static, emb=int(json.loads(str(z["meta"])).get("EMB", CM.EMB)))
    with torch.no_grad():
        for k in z.files:
            if k != "meta":
                model.p[k].data.copy_(torch.from_numpy(z[k]))
    idx = np.arange(len(rows["label"]))
    ev = _eval_value(model, rows, idx, torch, ablate_seed=20260921 if a.ablate else None)
    print(json.dumps(ev, indent=1))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rows")
    r.add_argument("--in", nargs="+", required=True, dest="inputs")
    r.add_argument("--out", required=True, help="prefix; writes PREFIX.npz")
    r.add_argument("--rate", type=float, default=0.125)
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--perspectives", choices=("move", "both"), default="both")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--max-games", type=int, default=0)
    r.set_defaults(fn=cmd_rows)
    f = sub.add_parser("fit")
    f.add_argument("rows", nargs="+")
    f.add_argument("--out", required=True)
    f.add_argument("--name", default="cards-s0")
    f.add_argument("--epochs", type=int, default=30)
    f.add_argument("--batch", type=int, default=256)
    f.add_argument("--lr", type=float, default=1e-3)
    f.add_argument("--l2", type=float, default=1e-5)
    f.add_argument("--holdout", type=float, default=0.2)
    f.add_argument("--policy-weight", type=float, default=0.5)
    f.add_argument("--patience", type=int, default=5)
    f.add_argument("--embed", type=int, default=CM.EMB, help="identity embedding width")
    f.add_argument("--dropout", type=float, default=0.0,
                   help="training-time dropout on the token MLP outputs and the pooled vector")
    f.add_argument("--seed", type=int, default=0)
    f.add_argument("--threads", type=int, default=4)
    f.set_defaults(fn=cmd_fit)
    h = sub.add_parser("fit114", help="the 114-feature head on the same rows and split")
    h.add_argument("rows", nargs="+")
    h.add_argument("--out", required=True)
    h.add_argument("--hidden", type=int, default=16)
    h.add_argument("--epochs", type=int, default=200)
    h.add_argument("--batch", type=int, default=256)
    h.add_argument("--lr", type=float, default=1e-3)
    h.add_argument("--l2", type=float, default=1e-5)
    h.add_argument("--holdout", type=float, default=0.2)
    h.add_argument("--patience", type=int, default=10)
    h.add_argument("--seed", type=int, default=1)
    h.add_argument("--threads", type=int, default=4)
    h.set_defaults(fn=cmd_fit114)
    e = sub.add_parser("eval")
    e.add_argument("rows", nargs="+")
    e.add_argument("--weights", required=True)
    e.add_argument("--ablate", action="store_true")
    e.set_defaults(fn=cmd_eval)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
