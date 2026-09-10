import pytest

from cptcg.cards.registry import load_default
from cptcg.core.enums import Keyword
from cptcg.core.rng import Pcg32
from cptcg.deck.builder import random_legends
from cptcg.deck.strategies import (PERSONALITIES, Aggro, Control, Economy, GigManipulation, Synergy,
                                   all_strategies, deck_profile, features, get_strategy, legend_fit,
                                   rules_text)
from cptcg.deck.validate import validate


@pytest.fixture(scope="module")
def reg():
    return load_default()


@pytest.fixture(scope="module")
def triples(reg):
    rng = Pcg32(7)
    return [random_legends(reg, rng) for _ in range(20)]


@pytest.fixture(scope="module")
def profiles(reg, triples):
    """Mean deck profile per personality over the same 20 Legend triples."""
    rng = Pcg32(11)
    out = {}
    for s in all_strategies():
        rows = []
        for legs in triples:
            d = s.build(reg, legs, rng)
            v = validate(d, reg)
            assert v.ok, (s.name, str(v))
            assert d.meta["strategy"] == s.name and "context" in d.meta
            rows.append(deck_profile(d, reg))
        out[s.name] = {k: sum(r[k] for r in rows) / len(rows) for k in rows[0]}
    return out


def test_five_named_personalities_with_descriptions():
    assert {"aggro", "control", "economy", "gig", "synergy"} <= set(PERSONALITIES)
    for s in all_strategies():
        assert s.name and len(s.describe()) > 40
    assert isinstance(get_strategy("Aggro"), Aggro)
    with pytest.raises(KeyError):
        get_strategy("yolo")


def test_features_read_the_card_text(reg):
    assert features(reg.get("wild-in-the-streets")).removal >= 1          # "Defeat a spent Unit."
    assert features(reg.get("dexter-deshawn-one-last-chance")).gig_move >= 1   # "Adjust a Gig by up to 1."
    assert features(reg.get("peace-offering")).gig_payoff >= 1            # "value-pair"
    assert features(reg.get("delamain-cab")).eddies == 1                  # "ready 1 Eddie"
    assert features(reg.get("rogue-amendiares-queen-of-the-afterlife")).eddies == 2
    assert features(reg.get("saburo-arasaka-stubborn-patriarch")).tag_refs == {"ARASAKA"}
    assert features(reg.get("corpo-security")).cant_attack
    assert features(reg.get("psycho-squad")) == features(reg.get("psycho-squad"))     # vanilla, cached
    assert not any((features(reg.get("psycho-squad")).removal, features(reg.get("psycho-squad")).gig))
    assert "(" not in rules_text(reg.get("secondhand-bombus"))


def test_personalities_build_measurably_different_decks(profiles):
    p = profiles
    assert p["aggro"]["mean_cost"] < p["control"]["mean_cost"] - 0.3
    assert p["economy"]["sell_share"] == max(v["sell_share"] for v in p.values())
    assert p["gig"]["gig_cards"] == max(v["gig_cards"] for v in p.values())
    assert p["gig"]["gig_cards"] > 1.4 * p["aggro"]["gig_cards"]
    assert p["control"]["blockers"] == max(v["blockers"] for v in p.values())
    assert p["control"]["removal"] == max(v["removal"] for v in p.values())
    assert p["synergy"]["tag_overlap"] == max(v["tag_overlap"] for v in p.values())
    assert p["aggro"]["unit_share"] > p["economy"]["unit_share"]


def test_same_legends_different_lists(reg, triples):
    rng = Pcg32(3)
    lists = {s.name: set(s.build(reg, triples[0], rng).main) for s in all_strategies()}
    names = list(lists)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            jaccard = len(lists[a] & lists[b]) / len(lists[a] | lists[b])
            assert jaccard < 0.8, (a, b, jaccard)


def test_legend_fit_prefers_what_each_personality_wants(reg):
    go_solo = [reg.get(i) for i in ("v-streetkid", "goro-takemura-hands-unclean", "royce-psycho-on-the-edge")]
    no_solo = [reg.get(i) for i in ("padre-man-of-the-cross", "wakako-okada-peace-and-harmony", "muamar-reyes-el-capitan")]
    assert legend_fit(Aggro(), go_solo, reg) > legend_fit(Aggro(), no_solo, reg)
    assert legend_fit(Control(), no_solo, reg) > legend_fit(Control(), go_solo, reg)   # removal CALLs
    arasaka = [reg.get(i) for i in ("saburo-arasaka-stubborn-patriarch", "goro-takemura-hands-unclean",
                                    "yorinobu-arasaka-embracing-destruction")]
    assert legend_fit(Synergy(), arasaka, reg) > legend_fit(Synergy(), no_solo, reg)
    gig = [reg.get(i) for i in ("hanako-arasaka-daughter-of-the-emperor", "dexter-deshawn-off-the-grid",
                                "kerry-eurodyne-axe-attitude-audience")]
    assert legend_fit(GigManipulation(), gig, reg) > legend_fit(GigManipulation(), go_solo, reg)
    calls = [reg.get(i) for i in ("dexter-deshawn-off-the-grid", "evelyn-parker-beautiful-enigma",
                                  "viktor-vektor-sit-down-and-relax")]
    assert legend_fit(Economy(), calls, reg) > legend_fit(Economy(), go_solo, reg)


def test_choose_legends_is_legal_and_suits_the_strategy(reg):
    for s in all_strategies():
        rng = Pcg32(5)
        ids = s.choose_legends(reg, rng, samples=15)
        d = s.build(reg, ids, rng)
        assert validate(d, reg).ok and d.legends == tuple(ids)
    rng = Pcg32(9)
    aggro = [reg.get(i) for i in Aggro().choose_legends(reg, rng, samples=25)]
    assert any(Keyword.GO_SOLO in l.keywords for l in aggro)
    syn = [reg.get(i) for i in Synergy().choose_legends(reg, rng, samples=25)]
    assert sum(len(syn[i].tags & syn[j].tags) for i in range(3) for j in range(i + 1, 3)) >= 1
