"""The card-aware model: token encoder, one attention layer, value and policy heads.

Two implementations of the same arithmetic, both here so they cannot drift apart:

* ``TorchCardsModel`` (torch, training only; ``tools/fit_cards.py``);
* ``NumpyCardsModel`` (numpy, inference inside the search and the greedy agent;
  ``tools/cards_agents.py``), loaded from the ``.npz`` that ``export_npz`` writes.

Inputs are the token view in ``cptcg.learn.tokens`` (pure stdlib), turned into padded arrays by
``batch_tokens`` below. Static per-card features come from the registry once
(``static_card_table``): type, colour, cost, power, RAM, Sell Tag, keywords, the 39 tags and the
regex text features ``deck.strategies.features`` computes, so a card the corpus never showed still
has a description, and the identity embedding (151 × EMB) is what the identity ablation shuffles.

Sizes are deliberately small (about 150k parameters at D=64): the design's per-leaf budget is a
few hundred microseconds in numpy, and ``tools/timing.py --micro`` is where that is checked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import Registry, load_default  # noqa: E402
from cptcg.core.enums import NZONE, CardType, Color, Keyword  # noqa: E402
from cptcg.deck.strategies import features as text_features  # noqa: E402
from cptcg.learn import tokens as T  # noqa: E402
from cptcg.learn.policy import NAFEAT  # noqa: E402

NCARDS = 151
EMB = 32
D = 64
HEADS = 2
FORMAT = 1

_KEYWORDS = (Keyword.GO_SOLO, Keyword.QUICK, Keyword.BLOCKER, Keyword.ADRENALINE)
_TEXT_FIELDS = ("removal", "debuff", "protect", "gig_move", "gig_payoff", "gig_steal", "cred", "draw",
                "eddies", "discount", "haste", "pump", "ready", "cant_attack", "unblockable")


def tag_vocab(reg: Registry) -> list[str]:
    return sorted({t for d in reg.defs for t in d.tags})


def static_card_table(reg: Registry) -> np.ndarray:
    """Per card (registry order): type 4 | colour 4 | cost/9 | power/15 | ram/6 | sell | 4 keywords |
    39 tags | 15 text features. Row 0.. NCARDS-1; an extra all-zero row for 'no card'."""
    tags = tag_vocab(reg)
    ncol = 4 + 4 + 3 + 1 + len(_KEYWORDS) + len(tags) + len(_TEXT_FIELDS)
    tab = np.zeros((len(reg.defs) + 1, ncol), dtype=np.float32)
    for d in reg.defs:
        row = tab[d.idx]
        row[int(d.type) - 1 if int(d.type) >= 1 else 0] = 1.0 if int(d.type) - 1 < 4 else 0.0
        row[4 + int(d.color)] = 1.0
        row[8] = (d.cost or 0) / 9.0
        row[9] = (d.power if isinstance(d.power, int) else 0) / 15.0
        row[10] = (d.ram or 0) / 6.0
        row[11] = 1.0 if d.sell_tag else 0.0
        for k, kw in enumerate(_KEYWORDS):
            if kw in d.keywords:
                row[12 + k] = 1.0
        o = 12 + len(_KEYWORDS)
        for t in d.tags:
            row[o + tags.index(t)] = 1.0
        o += len(tags)
        f = text_features(d)
        for k, name in enumerate(_TEXT_FIELDS):
            v = getattr(f, name, 0)
            row[o + k] = float(v) if not isinstance(v, bool) else (1.0 if v else 0.0)
    return tab


# ----------------------------------------------------------------------------- batching
CARD_STATE = 8 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1     # zone one-hot(8) + 10 scalars
DIE_FEATS = 9
CTX_FEATS = 7 + 7 + 2 + 3 + 4 + 2                            # kind(7) tag(7) live/mover(2) ints(3) target(4) turn/ot(2)
OPT_FEATS = 4 + 52                                           # kind/submode/pick one-hots handled inside


def _card_state(tok) -> np.ndarray:
    (_idx, zone, owner, spent, lag, faceup, solo, gp, ng, known, hostleg, playable) = tok
    v = np.zeros(CARD_STATE, dtype=np.float32)
    v[min(zone, 7)] = 1.0
    v[8:] = (owner, spent, lag, faceup, solo, min(gp, 10) / 10.0, min(ng, 3) / 3.0, known, hostleg, playable)
    return v


def _ctx_vec(ctx) -> np.ndarray:
    kind, tag, live, atk_idx, tkind, redirects, gsa, unb, mover, turn, ot = ctx
    v = np.zeros(CTX_FEATS, dtype=np.float32)
    v[min(kind, 6)] = 1.0
    v[7 + min(tag, 6)] = 1.0
    v[14] = live
    v[15] = mover
    v[16] = min(redirects, 3) / 3.0
    v[17] = gsa
    v[18] = unb
    v[19 + (tkind + 1 if tkind in (0, 1) else 0)] = 1.0     # none / unit / gig
    v[23] = min(turn, 40) / 40.0
    v[24] = ot
    return v


def batch_tokens(decisions: list[dict], max_cards: int = 0, max_dice: int = 0, max_opts: int = 0) -> dict:
    """Pad a list of ``tokens.decision_tokens`` dicts into arrays: card ids (int32, -1 = pad), card
    state, die features, masks, context, aggregates, beliefs, option card ids/features, masks.
    Pads to the batch's own widest decision unless a width is given (attention is quadratic in
    the token count, so padding to a fixed 96 cost the inference path a factor of several)."""
    n = len(decisions)
    max_cards = max_cards or max(1, max(len(d["cards"]) for d in decisions))
    max_dice = max_dice or max(1, max(len(d["dice"]) for d in decisions))
    max_opts = max_opts or max(1, max(len(d.get("options", ())) for d in decisions))
    card_id = np.full((n, max_cards), -1, dtype=np.int32)
    card_st = np.zeros((n, max_cards, CARD_STATE), dtype=np.float32)
    die = np.zeros((n, max_dice, DIE_FEATS), dtype=np.float32)
    die_m = np.zeros((n, max_dice), dtype=np.float32)
    ctx = np.zeros((n, CTX_FEATS), dtype=np.float32)
    agg = np.zeros((n, 114), dtype=np.float32)
    bel = np.zeros((n, 124 + 27), dtype=np.float32)
    atk_id = np.full((n,), -1, dtype=np.int32)
    opt_id = np.full((n, max_opts), -1, dtype=np.int32)
    opt_f = np.zeros((n, max_opts, 3 + NAFEAT), dtype=np.float32)
    opt_m = np.zeros((n, max_opts), dtype=np.float32)
    for i, d in enumerate(decisions):
        cards = d["cards"][:max_cards]
        for j, tok in enumerate(cards):
            card_id[i, j] = tok[0]
            card_st[i, j] = _card_state(tok)
        for j, tok in enumerate(d["dice"][:max_dice]):
            die[i, j] = np.array(tok, dtype=np.float32) / np.array([1, 20, 20, 1, 1, 1, 1, 1, 1], dtype=np.float32)
            die_m[i, j] = 1.0
        ctx[i] = _ctx_vec(d["context"])
        atk_id[i] = d["context"][3]
        agg[i] = np.array(d["aggregates"], dtype=np.float32)
        bel[i, :124] = np.array(d["belief_deck"], dtype=np.float32) / 3.0
        bel[i, 124:] = np.array(d["belief_legends"], dtype=np.float32)
        for j, o in enumerate(d.get("options", ())[:max_opts]):
            opt_id[i, j] = o[0]
            opt_f[i, j, 0] = o[1] / 14.0
            opt_f[i, j, 1] = o[2] / 23.0
            opt_f[i, j, 2] = o[3] / 11.0
            opt_f[i, j, 3:] = np.array(o[4:], dtype=np.float32)
            opt_m[i, j] = 1.0
    return {"card_id": card_id, "card_st": card_st, "die": die, "die_m": die_m, "ctx": ctx, "agg": agg,
            "bel": bel, "atk_id": atk_id, "opt_id": opt_id, "opt_f": opt_f, "opt_m": opt_m}


# ----------------------------------------------------------------------------- numpy model
def _relu(x):
    return np.maximum(x, 0.0)


def _softmax(x, axis=-1):
    x = x - x.max(axis=axis, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=axis, keepdims=True)


class NumpyCardsModel:
    """Inference twin of ``TorchCardsModel``; weights from ``export_npz``."""

    def __init__(self, w: dict, static: np.ndarray, meta: dict) -> None:
        self.w = {k: np.asarray(v, dtype=np.float32) for k, v in w.items()}
        self.static = static.astype(np.float32)
        self.meta = meta
        self.emb = self.w["emb"]                       # (NCARDS+1, EMB); last row = no card

    @classmethod
    def load(cls, path: str | Path, reg: Registry | None = None) -> "NumpyCardsModel":
        z = np.load(path, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        w = {k: z[k] for k in z.files if k != "meta"}
        reg = reg or load_default()
        return cls(w, static_card_table(reg), meta)

    def ablate_identity(self, seed: int = 20260921) -> "NumpyCardsModel":
        """The identity ablation: the embedding rows permuted, everything else intact."""
        rng = np.random.default_rng(seed)
        w = dict(self.w)
        emb = w["emb"].copy()
        perm = rng.permutation(NCARDS)
        emb[:NCARDS] = emb[:NCARDS][perm]
        w["emb"] = emb
        return NumpyCardsModel(w, self.static, dict(self.meta, ablated=True))

    def _card_vec(self, ids: np.ndarray) -> np.ndarray:
        safe = np.where(ids < 0, NCARDS, ids)
        return np.concatenate([self.emb[safe], self.static[safe]], axis=-1)

    def encode(self, b: dict) -> tuple[np.ndarray, np.ndarray]:
        """State summary (N, D) and per-decision token matrix for the policy (N, D)."""
        w = self.w
        ids = b["card_id"]
        cmask = (ids >= 0).astype(np.float32)
        cv = np.concatenate([self._card_vec(ids), b["card_st"]], axis=-1)        # (N, C, EMB+S+CS)
        ct = _relu(cv @ w["card_w1"] + w["card_b1"]) @ w["card_w2"] + w["card_b2"]  # (N, C, D)
        dt = _relu(b["die"] @ w["die_w1"] + w["die_b1"]) @ w["die_w2"] + w["die_b2"]  # (N, K, D)
        cls = np.broadcast_to(w["cls"], (ids.shape[0], 1, D))
        x = np.concatenate([cls, ct, dt], axis=1)                                   # (N, 1+C+K, D)
        m = np.concatenate([np.ones((ids.shape[0], 1), np.float32), cmask, b["die_m"]], axis=1)
        # one self-attention layer, HEADS heads, with residual and a feed-forward block
        q = x @ w["attn_q"]; k = x @ w["attn_k"]; v = x @ w["attn_v"]
        n, t, _ = x.shape
        hd = D // HEADS
        q = q.reshape(n, t, HEADS, hd).transpose(0, 2, 1, 3)
        k = k.reshape(n, t, HEADS, hd).transpose(0, 2, 1, 3)
        v = v.reshape(n, t, HEADS, hd).transpose(0, 2, 1, 3)
        att = (q @ k.transpose(0, 1, 3, 2)) * np.float32(1.0 / np.sqrt(hd))         # (N, H, T, T)
        att = att + (np.float32(1.0) - m)[:, None, None, :] * np.float32(-1e9)
        att = _softmax(att, axis=-1)
        o = (att @ v).transpose(0, 2, 1, 3).reshape(n, t, D) @ w["attn_o"]
        x = x + o
        x = x + (_relu(x @ w["ff_w1"] + w["ff_b1"]) @ w["ff_w2"] + w["ff_b2"])
        mm = m[:, :, None]
        pooled_mean = (x * mm).sum(1) / np.maximum(mm.sum(1), 1.0)
        pooled_max = np.where(mm > 0, x, np.float32(-1e9)).max(1)
        summary_in = np.concatenate([x[:, 0], pooled_mean, pooled_max, b["agg"], b["bel"], b["ctx"]], axis=-1)
        h = _relu(summary_in @ w["sum_w1"] + w["sum_b1"])
        summary = _relu(h @ w["sum_w2"] + w["sum_b2"])                               # (N, D)
        return summary, x

    def value(self, b: dict) -> np.ndarray:
        """Win probability for the mover, (N,)."""
        summary, _ = self.encode(b)
        logit = summary @ self.w["val_w"] + self.w["val_b"]
        return 1.0 / (1.0 + np.exp(-logit.reshape(-1)))

    def raw(self, b: dict) -> np.ndarray:
        summary, _ = self.encode(b)
        return (summary @ self.w["val_w"] + self.w["val_b"]).reshape(-1)

    def policy(self, b: dict) -> np.ndarray:
        """Per-decision softmax over the padded options, (N, max_opts); pads get 0."""
        summary, _ = self.encode(b)
        w = self.w
        ov = np.concatenate([self._card_vec(b["opt_id"]), b["opt_f"]], axis=-1)   # (N, O, ...)
        ot = _relu(ov @ w["opt_w1"] + w["opt_b1"]) @ w["opt_w2"] + w["opt_b2"]     # (N, O, D)
        logits = (ot * summary[:, None, :]).sum(-1) * np.float32(1.0 / np.sqrt(D)) + (ot @ w["opt_bias"]).reshape(ot.shape[0], -1)
        logits = np.where(b["opt_m"] > 0, logits, np.float32(-1e9))
        return _softmax(logits, axis=-1) * b["opt_m"]


def init_shapes(static_cols: int, emb: int = EMB) -> dict:
    """Parameter shapes shared by both implementations (``emb`` = identity embedding width)."""
    cin = emb + static_cols + CARD_STATE
    oin = emb + static_cols + 3 + NAFEAT
    sin = 3 * D + 114 + 151 + CTX_FEATS
    return {"emb": (NCARDS + 1, emb), "card_w1": (cin, D), "card_b1": (D,), "card_w2": (D, D), "card_b2": (D,),
            "die_w1": (DIE_FEATS, D), "die_b1": (D,), "die_w2": (D, D), "die_b2": (D,), "cls": (1, 1, D),
            "attn_q": (D, D), "attn_k": (D, D), "attn_v": (D, D), "attn_o": (D, D),
            "ff_w1": (D, 2 * D), "ff_b1": (2 * D,), "ff_w2": (2 * D, D), "ff_b2": (D,),
            "sum_w1": (sin, 2 * D), "sum_b1": (2 * D,), "sum_w2": (2 * D, D), "sum_b2": (D,),
            "val_w": (D, 1), "val_b": (1,),
            "opt_w1": (oin, D), "opt_b1": (D,), "opt_w2": (D, D), "opt_b2": (D,), "opt_bias": (D, 1)}


def n_params(static_cols: int, emb: int = EMB) -> int:
    return sum(int(np.prod(v)) for v in init_shapes(static_cols, emb).values())


# ----------------------------------------------------------------------------- torch model
def torch_model(static: np.ndarray, emb: int = EMB, dropout: float = 0.0):
    """Build the torch twin. Imported lazily so numpy-only users never need torch.

    ``emb`` is the identity embedding width (the numpy twin reads it from the weights);
    ``dropout`` (training mode only) is applied to the token MLP outputs and to the pooled
    vector, so an exported model is the same arithmetic as before with ``dropout=0``."""
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    shapes = init_shapes(static.shape[1], emb)

    class TorchCardsModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.p = nn.ParameterDict()
            g = torch.Generator().manual_seed(20260921)
            for k, shp in shapes.items():
                if k.endswith("_b1") or k.endswith("_b2") or k in ("val_b",):
                    t = torch.zeros(shp)
                elif k == "emb":
                    t = torch.randn(shp, generator=g) * 0.1
                    t[-1] = 0.0
                elif k == "cls":
                    t = torch.randn(shp, generator=g) * 0.1
                else:
                    fan_in = shp[0] if len(shp) > 1 else 1
                    t = torch.randn(shp, generator=g) * (1.0 / fan_in) ** 0.5
                self.p[k] = nn.Parameter(t)
            self.register_buffer("static", torch.tensor(static, dtype=torch.float32))

        def _card_vec(self, ids):
            safe = torch.where(ids < 0, torch.full_like(ids, NCARDS), ids).long()
            return torch.cat([self.p["emb"][safe], self.static[safe]], dim=-1)

        def encode(self, b):
            w = self.p
            ids = b["card_id"]
            cmask = (ids >= 0).float()
            cv = torch.cat([self._card_vec(ids), b["card_st"]], dim=-1)
            ct = torch.relu(cv @ w["card_w1"] + w["card_b1"]) @ w["card_w2"] + w["card_b2"]
            dt = torch.relu(b["die"] @ w["die_w1"] + w["die_b1"]) @ w["die_w2"] + w["die_b2"]
            if dropout > 0:
                ct = F.dropout(ct, dropout, self.training)
                dt = F.dropout(dt, dropout, self.training)
            n = ids.shape[0]
            x = torch.cat([w["cls"].expand(n, 1, D), ct, dt], dim=1)
            m = torch.cat([torch.ones(n, 1, device=ids.device), cmask, b["die_m"]], dim=1)
            q = x @ w["attn_q"]; k = x @ w["attn_k"]; v = x @ w["attn_v"]
            t = x.shape[1]
            hd = D // HEADS
            q = q.view(n, t, HEADS, hd).transpose(1, 2)
            k = k.view(n, t, HEADS, hd).transpose(1, 2)
            v = v.view(n, t, HEADS, hd).transpose(1, 2)
            att = (q @ k.transpose(-1, -2)) / (hd ** 0.5)
            att = att + (1.0 - m)[:, None, None, :] * -1e9
            att = torch.softmax(att, dim=-1)
            o = (att @ v).transpose(1, 2).reshape(n, t, D) @ w["attn_o"]
            x = x + o
            x = x + (torch.relu(x @ w["ff_w1"] + w["ff_b1"]) @ w["ff_w2"] + w["ff_b2"])
            mm = m[:, :, None]
            pooled_mean = (x * mm).sum(1) / mm.sum(1).clamp(min=1.0)
            pooled_max = torch.where(mm > 0, x, torch.full_like(x, -1e9)).max(1).values
            pooled = torch.cat([x[:, 0], pooled_mean, pooled_max], dim=-1)
            if dropout > 0:
                pooled = F.dropout(pooled, dropout, self.training)
            sin = torch.cat([pooled, b["agg"], b["bel"], b["ctx"]], dim=-1)
            h = torch.relu(sin @ w["sum_w1"] + w["sum_b1"])
            return torch.relu(h @ w["sum_w2"] + w["sum_b2"])

        def value_logit(self, b):
            return (self.encode(b) @ self.p["val_w"] + self.p["val_b"]).reshape(-1)

        def policy_logits(self, b):
            summary = self.encode(b)
            w = self.p
            ov = torch.cat([self._card_vec(b["opt_id"]), b["opt_f"]], dim=-1)
            ot = torch.relu(ov @ w["opt_w1"] + w["opt_b1"]) @ w["opt_w2"] + w["opt_b2"]
            logits = (ot * summary[:, None, :]).sum(-1) / (D ** 0.5) + (ot @ w["opt_bias"]).reshape(ot.shape[0], -1)
            return logits.masked_fill(b["opt_m"] <= 0, -1e9)

        def export_npz(self, path, meta: dict) -> None:
            arrays = {k: v.detach().cpu().numpy().astype(np.float32) for k, v in self.p.items()}
            np.savez_compressed(path, meta=json.dumps(dict(meta, format=FORMAT, D=D, EMB=emb, HEADS=HEADS,
                                                           dropout=dropout)), **arrays)

    return TorchCardsModel()
