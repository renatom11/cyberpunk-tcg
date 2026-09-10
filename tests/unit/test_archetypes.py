"""Archetypes learned from play: fingerprints, clustering, naming, and the two builders."""
import json

import pytest

from cptcg.cards.registry import load_default
from cptcg.core.rng import Pcg32
from cptcg.deck.archetypes import (FEATURES, FILL_FEATURES, MIN_DECKS, MIN_MEMBERS, ArchetypeStore, describe_fingerprint,
                                   fingerprint, name_from_z, name_still_fits, pool_ranges)
from cptcg.deck.builder import random_legends
from cptcg.deck.decklist import Decklist
from cptcg.deck.strategies import Explorer, Learned, builders_for, deck_profile, features, get_builder, rules_text
from cptcg.deck.validate import validate


@pytest.fixture(scope="module")
def reg():
    return load_default()


@pytest.fixture(scope="module")
def explorers(reg):
    """Sixteen Explorer decks on their own Legends, the raw material of a store."""
    rng = Pcg32(11)
    return [Explorer().build(reg, None, rng, name=f"x{i}") for i in range(16)]


@pytest.fixture(scope="module")
def store(reg, explorers):
    st = ArchetypeStore(reg=reg)
    for i, d in enumerate(explorers):
        st.add(d, None, games=40, wins=10 + i, bt=0.8 + 0.03 * i, source="fixture")
    assert st.refit()
    return st


def test_features_read_the_card_text(reg):
    assert features(reg.get("wild-in-the-streets")).removal >= 1          # "Defeat a spent Unit."
    assert features(reg.get("dexter-deshawn-one-last-chance")).gig_move >= 1   # "Adjust a Gig by up to 1."
    assert features(reg.get("peace-offering")).gig_payoff >= 1            # "value-pair"
    assert features(reg.get("delamain-cab")).eddies == 1                  # "ready 1 Eddie"
    assert features(reg.get("saburo-arasaka-stubborn-patriarch")).tag_refs == {"ARASAKA"}
    assert features(reg.get("corpo-security")).cant_attack
    assert "(" not in rules_text(reg.get("secondhand-bombus"))


def test_fingerprint_ranges_and_profile_agree(reg):
    for path in ("data/decks/sample_corpos.json", "data/decks/the_heist.json"):
        d = Decklist.load(path)
        fp = fingerprint(reg, d)
        assert set(fp) == set(FEATURES)
        n = len(d.main)
        for k in ("sell_share", "unit_share", "program_share", "gear_share", "cheap_share", "top_share"):
            assert 0.0 <= fp[k] <= 1.0
        assert fp["unit_share"] + fp["program_share"] + fp["gear_share"] == pytest.approx(1.0)
        assert 0.0 < fp["mean_cost"] <= 8.0 and 0.0 <= fp["mean_unit_power"] <= 20.0
        for k in ("blockers", "quick", "removal", "gig_cards", "haste", "economy", "steal", "draw"):
            assert 0 <= fp[k] <= 3 * n and fp[k] == int(fp[k])
        colours = [fp[k] for k in fp if k.startswith("colour_")]
        assert len(colours) == 4 and set(colours) <= {0.0, 1.0} and sum(colours) >= 1
        # deck_profile() is the same arithmetic on a subset of the features
        prof = deck_profile(d, reg)
        for k, v in prof.items():
            assert fp[k] == pytest.approx(v), k
        words = describe_fingerprint(fp)
        assert "average cost" in words and "% Units" in words and "% Programs" in words and "sellable" not in words
    with pytest.raises(KeyError):
        fingerprint(reg, Decklist("x", d.legends, ("no-such-card",)))
    assert describe_fingerprint(None) == ""


def _planted(seed: int, per: int = 10, spread: float = 0.15):
    """Three well-separated centres in fingerprint space, ``per`` noisy points each."""
    rng = Pcg32(seed, seq=3)
    centres = [
        {"mean_cost": 2.2, "unit_share": 0.7, "sell_share": 0.3, "removal": 2, "gig_cards": 5, "economy": 4, "blockers": 1},
        {"mean_cost": 4.0, "unit_share": 0.4, "sell_share": 0.6, "removal": 14, "gig_cards": 8, "economy": 6, "blockers": 8},
        {"mean_cost": 3.3, "unit_share": 0.5, "sell_share": 0.5, "removal": 4, "gig_cards": 24, "economy": 16, "blockers": 3},
    ]
    pts = []
    for c, centre in enumerate(centres):
        for j in range(per):
            fp = {k: 0.0 for k in FEATURES}
            fp.update({"program_share": 0.3, "gear_share": 0.2, "cheap_share": 0.3, "top_share": 0.2,
                       "mean_unit_power": 4.0, "quick": 2, "haste": 2, "steal": 1, "draw": 3, "tag_overlap": 0.5,
                       "colour_red": 1.0, "colour_green": 1.0})
            for k, v in centre.items():
                noise = (rng.below(1000) / 1000 - 0.5) * 2 * spread
                fp[k] = v * (1 + noise) if k != "unit_share" else v + noise * 0.3
            pts.append((c, j, fp))
    return pts


def _fake_deck(c: int, j: int) -> Decklist:
    """A stand-in deck whose last sorted Legend, ``P<c>``, names its planted group."""
    return Decklist.from_counts(f"c{c}-{j}", ["La", "Lb", f"P{c}"], {f"card{c}{j}": 3, "filler": 37})


def test_kmeans_recovers_three_planted_clusters_and_names_are_stable(tmp_path):
    st = ArchetypeStore(path=tmp_path / "a.json")
    for c, j, fp in _planted(1):
        st.add(_fake_deck(c, j), fp, games=20, wins=8 + 4 * c, bt=0.7 + 0.3 * c)
    assert st.refit() and len(st.archetypes) == 3
    groups = {}
    for a in st.archetypes:
        planted = {sig.split("::")[0].split("|")[-1] for sig in a.members}   # the P<c> Legend names the planted group
        assert len(planted) == 1, (a.name, planted)
        groups[planted.pop()] = a.name
    assert len(set(groups.values())) == 3
    names = sorted(a.name for a in st.archetypes)
    ids = {a.id for a in st.archetypes}
    assert all(n[0].isupper() and " " in n and n == n.strip() for n in names)   # "Adjective noun", like a player would say
    # Same data again (and in another order): same clusters, same names.
    st.decks.reverse()
    st.refit()
    assert sorted(a.name for a in st.archetypes) == names and {a.id for a in st.archetypes} == ids
    # A few more decks near the planted centres keep every name.
    for c, j, fp in _planted(2, per=2):
        st.add(_fake_deck(c, 20 + j), fp, games=20, wins=10, bt=1.0)
    st.refit()
    assert sorted(a.name for a in st.archetypes) == names
    # A group that keeps most of its members keeps its name even when a feature ranking shifts:
    # a fresh store fit on the same decks may name it differently, the continuing store does not.
    fresh = ArchetypeStore()
    for d in st.decks:
        fresh.add(Decklist.from_counts(d.name, d.legends, d.main), d.fingerprint, d.games, d.wins, d.bt)
    fresh.refit()
    assert {a.id for a in fresh.archetypes} == {a.id for a in st.archetypes}
    # Assignment is by nearest centre; the win rate of a group pools its members' games.
    best = st.ranked()[0]
    assert best.win_rate == max(a.win_rate for a in st.archetypes)
    c, j, fp = _planted(3, per=1)[2]
    assert st.get(st.assign(fp)).name == groups["P2"]
    assert "won" in best.description and "% of" in best.description
    # Round trip through the file.
    st.save()
    back = ArchetypeStore.load(tmp_path / "a.json")
    assert json.dumps(back.to_json(), sort_keys=True) == json.dumps(st.to_json(), sort_keys=True)
    assert back.get(best.name).id == best.id and back.get(best.id) is not None and back.get("nope") is None


def test_store_needs_eight_decks_before_it_clusters(reg, explorers):
    st = ArchetypeStore(reg=reg)
    for d in explorers[: MIN_DECKS - 1]:
        st.add(d, None, games=10, wins=5)
    assert not st.refit() and st.archetypes == [] and st.assign(fingerprint(reg, explorers[0])) is None
    assert "no archetypes yet" in st.summary()
    st.add(explorers[MIN_DECKS - 1], None, games=10, wins=5)
    assert st.refit() and st.archetypes and st.assign(fingerprint(reg, explorers[0])) in {a.id for a in st.archetypes}
    # a deck seen twice pools its record instead of appearing twice
    n = len(st.decks)
    rec = st.add(explorers[0], None, games=10, wins=9)
    assert len(st.decks) == n and rec.games == 20 and rec.wins == 14


def test_names_come_from_the_two_most_distinctive_features():
    z = {k: 0.0 for k in FILL_FEATURES}
    z.update(removal=2.5, blockers=1.8)
    assert name_from_z(z) == "Removal wall"
    z = {k: 0.0 for k in FILL_FEATURES}
    z.update(cheap_share=2.0, unit_share=1.5, removal=-1.0)
    assert name_from_z(z) == "Low-curve swarm"
    assert name_from_z(z, {"Low-curve swarm"}) == "Low-curve tempo"         # the next noun when the name is taken
    assert name_from_z({k: 0.0 for k in FILL_FEATURES}) == "Balanced midrange"
    # A noun never repeats a word of the adjective ("Low-curve curve", "Gig-value value").
    z = {k: 0.0 for k in FILL_FEATURES}
    z.update(cheap_share=2.0, mean_cost=-1.9)
    assert name_from_z(z) == "Low-curve decks"
    z = {k: 0.0 for k in FILL_FEATURES}
    z.update(gig_cards=2.0, draw=1.9, haste=1.0)
    assert name_from_z(z) == "Gig-value rush"
    # When the top two are nearly tied, the feature the group is high on gives the adjective.
    z = {k: 0.0 for k in FILL_FEATURES}
    z.update(economy=-1.05, blockers=1.0)
    assert name_from_z(z) == "Blocker beatdown"
    # A kept name must still describe the group.
    z = {k: 0.0 for k in FILL_FEATURES}
    z.update(removal=2.5, blockers=1.8, economy=0.2)
    assert name_still_fits("Removal wall", z) and name_still_fits("Blocker control", z)
    assert not name_still_fits("Eddies wall", z) and not name_still_fits("Removal engine", z)   # economy is not distinctive
    assert name_still_fits("Balanced midrange", {k: 0.0 for k in FILL_FEATURES}) and not name_still_fits("Balanced midrange", z)


def test_explorer_decks_are_legal_and_spread_over_the_fingerprint_space(reg):
    rng = Pcg32(5)
    legs = random_legends(reg, rng)
    decks = [Explorer().build(reg, legs, rng, name=f"e{i}") for i in range(12)]
    for d in decks:
        assert validate(d, reg).ok and d.legends == tuple(legs)
        assert d.meta["archetype"] == "exploring" and d.meta["generated"] == "explorer" and "context" in d.meta
    fps = [fingerprint(reg, d) for d in decks]
    pool = Explorer().make_ctx(reg, legs).pool
    lo, hi = pool_ranges(pool, frozenset().union(*(reg.get(l).tags for l in legs)))
    wide = 0
    for k in ("mean_cost", "unit_share", "program_share", "sell_share", "blockers", "removal", "gig_cards", "economy", "draw"):
        span = max(f[k] for f in fps) - min(f[k] for f in fps)
        assert span >= 0
        if span >= 0.2 * (hi[k] - lo[k]):
            wide += 1
    assert wide >= 6, wide          # the batch spreads along most of the features the pool allows
    assert len({tuple(sorted(d.counts().items())) for d in decks}) == 12


def test_learned_decks_land_nearer_their_centroid_than_explorer_decks(reg, store):
    rng = Pcg32(21)
    for arch in store.ranked()[:2]:
        learned = [Learned(arch, store).build(reg, None, rng, name=f"l{i}") for i in range(4)]
        explorers = [Explorer().build(reg, None, rng, name=f"e{i}") for i in range(4)]
        for d in learned:
            assert validate(d, reg).ok
            assert d.meta["archetype"] == arch.name and d.meta["archetype_id"] == arch.id and d.meta["generated"] == "learned"
        dl = [store.distance(fingerprint(reg, d), arch) for d in learned]
        de = [store.distance(fingerprint(reg, d), arch) for d in explorers]
        assert max(dl) < min(de), (arch.name, dl, de)
        # Learned builders draw their Legends from the archetype's own decks (sometimes with one swapped).
        member_legends = {l for m in store.members(arch) for l in m.legends}
        assert all(len(set(d.legends) & member_legends) >= 2 for d in learned)
    assert get_builder("explorer").name == "explorer" and isinstance(get_builder(store.ranked()[0].name, store), Learned)
    with pytest.raises(KeyError):
        get_builder("nope", store)
    line = builders_for(store, 8)
    assert [b.name == "explorer" for b in line] == [False, False, False, True, False, False, False, True]
    assert all(b.name == "explorer" for b in builders_for(ArchetypeStore(reg=reg), 5))


def test_an_outlier_never_becomes_its_own_archetype(tmp_path):
    st = ArchetypeStore(path=tmp_path / "a.json")
    for c, j, fp in _planted(4):
        st.add(_fake_deck(c, j), fp, games=20, wins=10, bt=1.0)
    far = {k: 0.0 for k in FEATURES}
    far.update(mean_cost=7.5, unit_share=0.05, program_share=0.9, removal=60, gig_cards=0, economy=45, draw=30, blockers=0)
    st.add(Decklist.from_counts("odd", ["Lx", "Ly", "Lz"], {"weird": 3, "filler": 37}), far, games=8, wins=4, bt=0.9)
    assert st.refit() and len(st.archetypes) == 3
    assert all(len(a.members) >= MIN_MEMBERS for a in st.archetypes)
    assert all(a.separation > 0 and a.separation_word() and a.lineages == len(a.members) for a in st.archetypes)
    assert 0 < st.separation <= 1 and st.to_json()["separation"] == round(st.separation, 3)


def test_one_lineage_counts_as_one_deck(reg, explorers):
    st = ArchetypeStore(reg=reg)
    for d in explorers[:6]:
        st.add(d, None, games=10, wins=5)
    base = explorers[6]
    pool = [c for c in reg.defs if c.id not in base.main and c.type.name != "LEGEND"][:5]
    variants = [base]
    for k, card in enumerate(pool):                           # one-card variants of the same list
        main = list(base.main)
        main[k] = card.id
        variants.append(Decklist(f"v{k}", base.legends, tuple(main), dict(base.meta)))
    for d in variants:
        st.add(d, None, games=10, wins=5)
    assert len(st.decks) == 12 and st.lineage_count() == 7
    assert not st.refit() and "7 distinct" in st.summary() and "1 more distinct deck" in st.summary()
    st.add(explorers[7], None, games=10, wins=5)
    assert st.lineage_count() == 8 and st.refit()


def test_no_structure_means_one_group():
    """Decks that do not split into kinds get one archetype, 'Balanced midrange', not two invented ones."""
    rng = Pcg32(9, seq=4)
    st = ArchetypeStore()
    for j in range(12):
        fp = {k: 0.0 for k in FEATURES}
        for k in FILL_FEATURES:
            fp[k] = 1.0 + rng.below(1000) / 1000                # isotropic noise around one centre
        fp["colour_red"] = 1.0
        st.add(Decklist.from_counts(f"n{j}", ["La", "Lb", f"L{j}"], {f"card{j}": 3, "filler": 37}), fp, games=10, wins=5)
    assert st.refit() and len(st.archetypes) == 1
    a = st.archetypes[0]
    assert a.name == "Balanced midrange" and st.separation == 0.0 and "only group so far" in a.description
    assert st.assign(st.decks[0].fingerprint) == a.id and "one group so far" in st.summary()


def test_ranking_smooths_tiny_records_and_old_ids_resolve(tmp_path, monkeypatch):
    from cptcg.deck import archetypes as mod
    st = ArchetypeStore(path=tmp_path / "a.json")
    for c, j, fp in _planted(5):
        st.add(_fake_deck(c, j), fp, games=20, wins=10 + 2 * c, bt=1.0)
    assert st.refit()
    small, big = st.archetypes[0], st.archetypes[1]
    small.games, small.wins, big.games, big.wins = 8, 5, 900, 500      # 62% of 8 must not outrank 56% of 900
    assert st.ranked()[0] is big and small.smoothed_rate < big.smoothed_rate < big.win_rate
    # A continuing group whose words no longer fit is renamed; the old name and id still find it.
    old = {a.id: a.name for a in st.archetypes}
    monkeypatch.setattr(mod, "name_still_fits", lambda name, z: False)
    st.refit()
    st.save()
    back = ArchetypeStore.load(tmp_path / "a.json")
    for old_id, old_name in old.items():
        a = back.get(old_id)
        assert a is not None and a.id != old_id and old_name in a.aliases and old_id in a.previous_ids
        assert back.get(old_name) is a and "formerly " + old_name in a.description
    assert back.renamed and all(back.get(k) is not None for k in back.renamed)


def test_small_leagues_keep_one_explorer(store):
    from cptcg.deck.strategies import explorer_quota
    assert explorer_quota(2) == explorer_quota(3) == explorer_quota(7) == 1 and explorer_quota(8) == 2
    for n in (2, 3, 5):
        line = builders_for(store, n)
        assert sum(b.name == "explorer" for b in line) == 1 and line[-1].name == "explorer"
    line = builders_for(store, 8)
    assert [b.name == "explorer" for b in line] == [False, False, False, True, False, False, False, True]
