import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import fit_policy  # noqa: E402
import harvest  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.learn.experience import GameRecord  # noqa: E402
from cptcg.learn.policy import NAFEAT  # noqa: E402


def test_corpus_rows_pair_stored_visits_with_their_options():
    out = harvest.play_chunk((0, 1, 5, "ismcts:4", "heuristic", None))
    rec = GameRecord.from_json(out["records"][0])
    reg = load_default()
    rows = list(fit_policy.corpus_rows(reg, rec, 1.0))
    searched = [v for v in rec.visits if v and len(v) > 1 and sum(v) > 0]
    assert rows and len(rows) == len(searched)
    for (feats, dist), v in zip(rows, searched):
        assert len(feats) == len(dist) == len(v)
        assert all(len(f) == NAFEAT for f in feats)
        assert abs(sum(dist) - 1.0) < 1e-9
        assert dist == [x / sum(v) for x in v]
    assert list(fit_policy.corpus_rows(reg, rec, 0.0)) == []
