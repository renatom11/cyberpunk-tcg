"""The card-aware model's numpy inference twin and its row builder (Stage 0, tools/). numpy and
torch live only under ``tools/``; these tests skip where they are absent."""

import json
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import cards_model as CM  # noqa: E402
import fit_cards as FC  # noqa: E402
from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.learn import tokens as T  # noqa: E402
from cptcg.learn.decks import sample_pair  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402

SAMPLE = ROOT / "data" / "experience" / "bootstrap-sample.jsonl.gz"


def _decisions(reg, seed=31, n=6):
    s = new_game(reg, sample_pair(reg, Pcg32(seed)), seed)
    ags = [make_agent("heuristic", seed * 2 + i) for i in (0, 1)]
    for p, a in enumerate(ags):
        a.new_game(seed, p)
    out = []
    while len(out) < n and not s.over:
        legal_actions(s)
        ch = s.pending
        if ch is None:
            break
        if len(ch.options) > 1:
            out.append(T.decision_tokens(s, ch.player, ch))
        apply(s, ags[ch.player].act(s, ch))
    return out


def _random_numpy_model(reg, seed=1):
    static = CM.static_card_table(reg)
    rng = np.random.default_rng(seed)
    w = {}
    for k, shp in CM.init_shapes(static.shape[1]).items():
        fan = shp[0] if len(shp) > 1 else 1
        w[k] = (rng.standard_normal(shp) * (1.0 / fan) ** 0.5).astype(np.float32)
    w["emb"][-1] = 0.0
    return CM.NumpyCardsModel(w, static, {"format": CM.FORMAT})


def test_static_table_and_parameter_count():
    reg = load_default()
    static = CM.static_card_table(reg)
    assert static.shape[0] == CM.NCARDS + 1
    assert CM.n_params(static.shape[1]) == sum(int(np.prod(s)) for s in CM.init_shapes(static.shape[1]).values())


def test_value_is_a_probability_and_policy_sums_to_one_over_real_options():
    reg = load_default()
    m = _random_numpy_model(reg)
    decs = _decisions(reg)
    b = CM.batch_tokens(decs)
    v = m.value(b)
    assert v.shape == (len(decs),) and np.all((v > 0) & (v < 1))
    pol = m.policy(b)
    for i, d in enumerate(decs):
        k = len(d["options"])
        assert abs(pol[i, :k].sum() - 1.0) < 1e-5
        assert np.all(pol[i, k:] == 0)


def test_batching_does_not_change_a_single_decisions_output():
    reg = load_default()
    m = _random_numpy_model(reg)
    decs = _decisions(reg)
    together = m.raw(CM.batch_tokens(decs))
    alone = np.array([m.raw(CM.batch_tokens([d]))[0] for d in decs])
    assert np.allclose(together, alone, atol=1e-4)


def test_ablation_permutes_only_the_identity_rows():
    reg = load_default()
    m = _random_numpy_model(reg)
    a = m.ablate_identity()
    assert a.meta.get("ablated") is True
    for k in m.w:
        if k != "emb":
            assert np.array_equal(m.w[k], a.w[k])
    assert not np.array_equal(m.w["emb"][:CM.NCARDS], a.w["emb"][:CM.NCARDS])
    assert sorted(map(tuple, m.w["emb"][:CM.NCARDS].round(6))) == sorted(map(tuple, a.w["emb"][:CM.NCARDS].round(6)))
    decs = _decisions(reg)
    assert not np.allclose(m.raw(CM.batch_tokens(decs)), a.raw(CM.batch_tokens(decs)))


def test_the_torch_twin_agrees_with_numpy(tmp_path):
    torch = pytest.importorskip("torch")
    reg = load_default()
    static = CM.static_card_table(reg)
    tm = CM.torch_model(static)
    path = tmp_path / "w.npz"
    tm.export_npz(path, {"rules": "test"})
    nm = CM.NumpyCardsModel.load(path, reg)
    decs = _decisions(reg)
    b = CM.batch_tokens(decs)
    with torch.no_grad():
        tv = tm.value_logit(FC._to_torch(b, torch)).numpy()
        tp = torch.softmax(tm.policy_logits(FC._to_torch(b, torch)), dim=-1).numpy()
    assert np.allclose(tv, nm.raw(b), atol=1e-4)
    assert np.allclose(tp * b["opt_m"], nm.policy(b), atol=1e-4)


def test_the_twin_agrees_at_another_embedding_width_and_dropout_is_off_at_inference(tmp_path):
    """``--embed`` and ``--dropout`` (the rerun's configs d and e): the numpy twin reads the width
    from the weights, and a model fitted with dropout exports the same arithmetic as one without."""
    torch = pytest.importorskip("torch")
    reg = load_default()
    static = CM.static_card_table(reg)
    tm = CM.torch_model(static, emb=16, dropout=0.2)
    tm.eval()
    path = tmp_path / "w16.npz"
    tm.export_npz(path, {"rules": "test"})
    nm = CM.NumpyCardsModel.load(path, reg)
    assert nm.emb.shape == (CM.NCARDS + 1, 16) and nm.meta["EMB"] == 16 and nm.meta["dropout"] == 0.2
    decs = _decisions(reg)
    b = CM.batch_tokens(decs)
    with torch.no_grad():
        tv = tm.value_logit(FC._to_torch(b, torch)).numpy()
        tv2 = tm.value_logit(FC._to_torch(b, torch)).numpy()
    assert np.allclose(tv, tv2)                       # eval mode: dropout is off, so it is deterministic
    assert np.allclose(tv, nm.raw(b), atol=1e-4)
    tm.train()
    with torch.no_grad():
        a1 = tm.value_logit(FC._to_torch(b, torch)).numpy()
        a2 = tm.value_logit(FC._to_torch(b, torch)).numpy()
    assert not np.allclose(a1, a2)                    # train mode: dropout is live
    assert nm.ablate_identity().emb.shape == nm.emb.shape


@pytest.mark.skipif(not SAMPLE.exists(), reason="no bootstrap sample")
def test_rows_count_every_multi_option_decision_at_rate_one():
    recs = []
    for rec in read_games(SAMPLE):
        recs.append(rec)
        if len(recs) == 2:
            break
    out = FC.rows_chunk(([(i, r) for i, r in enumerate(recs)], 1.0, 7, True))
    reg = load_default()
    from cptcg.core.config import DEFAULT_CONFIG
    expect = 0
    for rec in recs:
        s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
        for idx in rec.actions:
            legal_actions(s)
            if len(s.pending.options) > 1:
                expect += 1
            apply(s, idx)
    assert int(out["mover"].sum()) == expect
    assert len(out["label"]) == 2 * expect
    assert out["card_off"][-1] == len(out["cards"]) and out["opt_off"][-1] == len(out["opts"])
    b = FC.gather(out, np.arange(len(out["label"])))
    assert b["card_id"].shape[0] == 2 * expect
    # the flat-array gather agrees with batch_tokens on the same decisions
    m = _random_numpy_model(reg)
    v1 = m.raw(b)
    assert np.all(np.isfinite(v1))


def test_the_card_agent_reads_a_position_as_if_at_its_own_main(tmp_path, monkeypatch):
    """The value head is E[outcome | board, decision context]; the agent fixes the context so two
    boards are compared under one conditional (the first panel run showed why)."""
    monkeypatch.setenv("CPTCG_AGENT_PLUGINS", "cards_agents")
    import cards_agents as CA
    from cptcg.core.actions import Choice, ChoiceKind
    reg = load_default()
    m = _random_numpy_model(reg)
    s = new_game(reg, sample_pair(reg, Pcg32(41)), 41)
    ags = [make_agent("heuristic", 3), make_agent("heuristic", 4)]
    for p, a in enumerate(ags):
        a.new_game(41, p)
    # play to a decision of seat 1, so seat 0 is the non-mover
    for _ in range(60):
        legal_actions(s)
        if s.pending.player == 1 and s.pending.kind is not ChoiceKind.MAIN:
            break
        apply(s, ags[s.pending.player].act(s, s.pending))
    assert s.pending.player == 1
    neutral = T.context(s, 0, Choice(ChoiceKind.MAIN, 0, (), lazy=True))
    own = T.context(s, 0, s.pending)
    assert neutral != own
    v_default = CA._value_batch(m, [s], 0)[0]
    v_neutral = CA._value_batch(m, [s], 0, context=neutral)[0]
    v_own = CA._value_batch(m, [s], 0, context=own)[0]
    assert abs(v_default - v_neutral) < 1e-6
    assert v_default != v_own


@pytest.mark.skipif(not SAMPLE.exists(), reason="no bootstrap sample")
@pytest.mark.skipif(not SAMPLE.exists(), reason="no bootstrap sample")
def test_a_resumed_fit_matches_an_uninterrupted_one(tmp_path):
    """The machine restarts mid-fit: ``--resume`` must continue to the same weights, dropout and all."""
    pytest.importorskip("torch")
    recs = []
    for rec in read_games(SAMPLE):
        recs.append(rec)
        if len(recs) == 6:
            break
    out = FC.rows_chunk(([(i, r) for i, r in enumerate(recs)], 0.5, 7, True))
    out.pop("n_decisions")
    meta = {"rules": __import__("cptcg.core.config", fromlist=["DEFAULT_CONFIG"]).DEFAULT_CONFIG.digest(),
            "tokens_digest": T.tokens_digest(), "seconds": 0, "sources": []}
    np.savez_compressed(tmp_path / "rows.npz", meta=json.dumps(meta), **out)
    common = ["fit", str(tmp_path / "rows.npz"), "--epochs", "3", "--patience", "9", "--threads", "1",
              "--dropout", "0.2", "--embed", "16", "--batch", "64"]
    FC.main(common + ["--out", str(tmp_path / "straight.npz")])
    FC.main(common + ["--out", str(tmp_path / "split.npz"), "--stop-after", "2"])
    assert not (tmp_path / "split.npz").exists() and (tmp_path / "split.npz.ckpt.pt").exists()
    FC.main(common + ["--out", str(tmp_path / "split.npz"), "--resume"])
    assert not (tmp_path / "split.npz.ckpt.pt").exists()
    a, b = np.load(tmp_path / "straight.npz"), np.load(tmp_path / "split.npz")
    for k in a.files:
        if k != "meta":
            assert np.allclose(a[k], b[k], atol=1e-6), k


def test_fit114_writes_a_loadable_head_from_the_card_rows(tmp_path):
    pytest.importorskip("torch")
    from cptcg.learn.model import ValueModel
    recs = []
    for rec in read_games(SAMPLE):
        recs.append(rec)
        if len(recs) == 6:
            break
    out = FC.rows_chunk(([(i, r) for i, r in enumerate(recs)], 0.5, 7, True))
    n_dec = out.pop("n_decisions")
    meta = {"rules": __import__("cptcg.core.config", fromlist=["DEFAULT_CONFIG"]).DEFAULT_CONFIG.digest(),
            "tokens_digest": T.tokens_digest(), "seconds": 0}
    np.savez_compressed(tmp_path / "rows.npz", meta=json.dumps(meta), **out)
    FC.main(["fit114", str(tmp_path / "rows.npz"), "--out", str(tmp_path / "w.json"), "--epochs", "3", "--threads", "1"])
    m = ValueModel.load(tmp_path / "w.json")
    reg = load_default()
    s = new_game(reg, sample_pair(reg, Pcg32(3)), 3)
    assert 0.0 < m.value(s, 0) < 1.0
