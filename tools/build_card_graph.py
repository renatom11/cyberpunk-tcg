"""The card interaction graph: what each card creates, what each card is paid for, and the links.

Three kinds of link, kept separate because they mean different things to a deckbuilder:

  direct    A creates exactly the thing B is paid for.               Trust No One -> Three Mouths
  indirect  A creates something that LEADS to what B wants, one      Viktor Vektor -> Royce
            implication step away (a Gear tutor finds Gear; you
            still have to equip it).
  co-need   A and B are paid for the SAME board state that no card   Field Operator & Memory Relapse
            directly produces (Street Cred parity, which dice you
            rolled, how far behind you are). They are not a combo —
            they are two cards that want the same game.

Tribal links are computed from the printed text naming a tag, not hand-authored, so an anthem can
never silently drift out of sync with the Units it pumps.
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from card_map import C, TOKENS

#: One step of "this leads to that". Deliberately shallow: a tutor finds Gear, an increase pushes a
#: Gig up. Chaining these transitively would connect most of the pool to most of the pool and stop
#: meaning anything.
IMPLIES = {
    "gear.tutor":    ["gear.equip"],
    "gear.equip":    ["gear.equipped", "gear.stack"],
    "gig.increase":  ["gig.high8", "gig.max"],
    "gig.decrease":  ["gig.min"],
    "gig.swap":      ["gig.pair", "gig.distinct"],
    "trash.self":    ["program.trash"],
    "program.play":  ["program.trash"],
    "legend.call_free": ["legend.faceup"],
    "legend.go_solo":   ["legend.faceup"],
    "unit.ready":    ["spend.trigger"],
    "power.pump":    ["power.threshold"],
}

cards = {c["id"]: c for c in json.load(open("data/cards/wnc.json"))["cards"]}
ALL_TAGS = sorted({t for c in cards.values() for t in c["tags"]})

def buffs(c):
    txt = (c.get("text") or "").upper()
    return [t for t in ALL_TAGS if t in txt]

produced = {t for v in C.values() for t in v["p"]} | {x for v in IMPLIES.values() for x in v}
edges, seen = [], set()
for a, va in C.items():
    direct = set(va["p"])
    indirect = {x for t in va["p"] for x in IMPLIES.get(t, ())} - direct
    for b, vb in C.items():
        if a == b:
            continue
        want = set(vb["r"])
        for tok in sorted(direct & want):
            edges.append({"from": a, "to": b, "token": tok, "kind": "direct"})
        for tok in sorted(indirect & want):
            edges.append({"from": a, "to": b, "token": tok, "kind": "indirect"})

# co-need: same rewarded token that nothing produces
states = {t for v in C.values() for t in v["r"]} - produced
co = []
for tok in sorted(states):
    members = sorted(cid for cid, v in C.items() if tok in v["r"])
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            co.append({"a": a, "b": b, "token": tok, "kind": "co-need"})

tribal = [{"from": a, "to": b, "token": "tribe." + tag, "kind": "tribal"}
          for a, ca in cards.items() for tag in buffs(ca)
          for b, cb in cards.items() if a != b and tag in cb["tags"]]

arch = {}
for cid, v in C.items():
    for a in v["arch"]:
        arch.setdefault(a, []).append(cid)

out = {"version": 1, "tokens": TOKENS, "implies": IMPLIES,
       "state_tokens": sorted(states),
       "cards": {cid: {"produces": v["p"], "rewards": v["r"], "archetypes": v["arch"],
                       "buffs_tags": buffs(cards[cid]), "tags": cards[cid]["tags"]}
                 for cid, v in C.items()},
       "edges": edges, "co_need": co, "tribal_edges": tribal,
       "archetypes": {k: sorted(v) for k, v in sorted(arch.items())}}
json.dump(out, open("data/strategy/graph.json", "w"), indent=1)

d = sum(1 for e in edges if e["kind"] == "direct")
print("cards %d | tokens %d | direct %d | indirect %d | co-need %d | tribal %d | archetypes %d"
      % (len(C), len(TOKENS), d, len(edges) - d, len(co), len(tribal), len(arch)))
deg = {}
for e in edges:
    deg[e["from"]] = deg.get(e["from"], 0) + 1
    deg[e["to"]] = deg.get(e["to"], 0) + 1
for e in co:
    deg[e["a"]] = deg.get(e["a"], 0) + 1
    deg[e["b"]] = deg.get(e["b"], 0) + 1
iso = [cid for cid in C if deg.get(cid, 0) == 0]
print("isolated after all three link types (%d): %s"
      % (len(iso), ", ".join(cards[c]["name"] for c in iso)))
print("\nVIKTOR -> ROYCE now:", [e for e in edges
      if e["from"] == "viktor-vektor-sit-down-and-relax" and e["to"] == "royce-psycho-on-the-edge"])
