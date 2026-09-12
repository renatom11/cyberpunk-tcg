"""The card interaction graph stays in step with the card pool.

The graph is hand-authored per card — what each one creates and what it is paid for — so the thing
that rots is the join: a card added to the pool with no entry, an entry naming a card that was
renamed, a token invented in one place and never defined. None of that is visible by reading the
file, and all of it is trivially checkable.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "data" / "strategy" / "graph.json"
POOL = ROOT / "data" / "cards" / "wnc.json"


@pytest.fixture(scope="module")
def g():
    return json.loads(GRAPH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pool():
    return {c["id"]: c for c in json.loads(POOL.read_text(encoding="utf-8"))["cards"]}


def test_every_card_in_the_pool_has_an_entry(g, pool):
    missing = sorted(set(pool) - set(g["cards"]))
    assert not missing, f"cards with no interaction entry: {missing}"


def test_the_graph_names_no_card_that_does_not_exist(g, pool):
    unknown = sorted(set(g["cards"]) - set(pool))
    assert not unknown, f"entries for cards not in the pool: {unknown}"


def test_every_token_used_is_defined(g):
    used = set()
    for v in g["cards"].values():
        used |= set(v["produces"]) | set(v["rewards"])
    for t, xs in g["implies"].items():
        used.add(t)
        used |= set(xs)
    undefined = sorted(used - set(g["tokens"]))
    assert not undefined, f"tokens used but never defined: {undefined}"


def test_every_defined_token_is_actually_used(g):
    """A token nobody produces AND nobody rewards is vocabulary that describes nothing."""
    used = set()
    for v in g["cards"].values():
        used |= set(v["produces"]) | set(v["rewards"])
    assert not sorted(set(g["tokens"]) - used), "defined tokens that no card uses"


@pytest.mark.parametrize("key, a, b", [("edges", "from", "to")])
def test_edges_point_at_real_cards_and_never_at_themselves(g, pool, key, a, b):
    for e in g[key]:
        assert e[a] in pool and e[b] in pool, e
        assert e[a] != e[b], f"self-edge: {e}"
        assert e["token"] in g["tokens"], e


def test_a_direct_edge_really_is_produces_meeting_rewards(g):
    """The edge list is generated, so this checks the generator rather than trusting it."""
    for e in g["edges"]:
        if e["kind"] != "direct":
            continue
        assert e["token"] in g["cards"][e["from"]]["produces"], e
        assert e["token"] in g["cards"][e["to"]]["rewards"], e


def test_state_tokens_are_exactly_those_no_card_produces(g):
    produced = {t for v in g["cards"].values() for t in v["produces"]}
    produced |= {x for xs in g["implies"].values() for x in xs}
    rewarded = {t for v in g["cards"].values() for t in v["rewards"]}
    assert sorted(g["state_tokens"]) == sorted(rewarded - produced)


def test_the_worked_example_survives(g):
    """The combo this map was asked for: something pushes a Gig down, something else is paid for a
    min Gig. If this edge ever disappears the vocabulary has drifted."""
    got = [e for e in g["edges"]
           if e["from"] == "trust-no-one" and e["to"] == "three-mouths-one-desire"]
    assert any(e["token"] == "gig.min" for e in got), got


def test_tribal_edges_only_join_a_buffer_to_a_member(g, pool):
    for e in g["tribal_edges"]:
        tag = e["token"].split(".", 1)[1]
        assert tag in pool[e["to"]]["tags"], e
        assert tag in g["cards"][e["from"]]["buffs_tags"], e


def test_derived_data_never_lands_in_the_card_pool_directory():
    """``registry.load_default`` globs every ``*.json`` in ``data/cards``, so a commentary file
    dropped there is parsed as a card set and takes the whole pool down. That is exactly what
    happened when this graph was first written to ``data/cards/graph.json``: every card test in the
    suite errored at fixture setup. Derived files live in ``data/strategy``."""
    from cptcg.cards.registry import DATA_DIR
    stray = sorted(p.name for p in DATA_DIR.glob("*.json") if p.name != "wnc.json")
    assert not stray, (f"non-card JSON in the card pool directory: {stray}. "
                       f"registry.load_default() will try to parse these as card sets.")


def test_the_web_backend_serves_the_map_and_the_notes():
    """The CARDS page is the only consumer; if the join breaks there the page silently loses its
    panel rather than erroring, so it is worth asserting here."""
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from cptcg.web import backend as B

    links = B.card_links()
    pool = {c["id"] for c in json.loads(POOL.read_text(encoding="utf-8"))["cards"]}
    assert set(links) == pool
    # every link points at a real card, both directions agree
    for cid, v in links.items():
        for key in ("enables", "enabled_by", "tribal", "co_need"):
            for l in v[key]:
                assert l["id"] in pool, (cid, key, l)
    # the worked example, through the backend rather than the file
    mins = [l["id"] for l in links["trust-no-one"]["enables"] if l["token"] == "gig.min"]
    assert "three-mouths-one-desire" in mins

    # hand-written notes attach to the card JSON
    guided = [B.card_json_static(d) for d in B.reg().defs]
    assert any("guide" in c for c in guided), "no card carries hand-written guide text"
    for c in guided:
        if "guide" in c:
            assert c["guide"].get("guide"), c["id"]
