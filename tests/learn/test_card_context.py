import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import card_context  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402

SAMPLE = ROOT / "data" / "experience" / "bootstrap-sample.jsonl.gz"


def _t(offered, played, field="0", cred="level", stage="t1-3"):
    return {"seat": 0, "turn": 1, "offered": set(offered), "played": set(played),
            "ctx": {"rival_field": field, "cred": cred, "stage": stage}}


def test_rates_are_per_seat_turn_and_split_by_context():
    turns = [_t("ab", "a", field="0")] * 3 + [_t("ab", "b", field="2+")] * 3
    r = card_context.summarise(turns, [("a", "b", "tok")], min_n=3)
    a = r["cards"]["a"]
    assert (a["offered"], a["played"], a["rate"]) == (6, 3, 0.5)
    assert a["by_context"]["rival_field=0"]["rate"] == 1.0
    assert a["by_context"]["rival_field=2+"]["rate"] == 0.0
    assert a["spread"]["rival_field"] == 1.0 and a["spread"]["cred"] is None


def test_lift_compares_joint_play_with_independence():
    # a and b always played together on half the turns: joint 0.5 against 0.5 * 0.5 expected
    turns = [_t("ab", "ab")] * 4 + [_t("ab", "")] * 4
    r = card_context.summarise(turns, [("a", "b", "tok")], min_n=4)
    (p,) = r["pairs"]
    assert (p["both"], p["expected"], p["lift"]) == (0.5, 0.25, 2.0)
    assert r["pooled_lift"] == 2.0


def test_replayed_turns_belong_to_the_mover_and_played_is_offered():
    reg = load_default()
    rec = next(iter(read_games(str(SAMPLE))))
    turns = card_context.seat_turns(reg, rec)
    assert turns and any(t["played"] for t in turns)
    for t in turns:
        assert t["played"] <= t["offered"]
    keys = [(t["seat"], t["turn"]) for t in turns]
    assert len(keys) == len(set(keys))
