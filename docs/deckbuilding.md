# AI deck-building: archetypes learned from play

`python -m cptcg build` and `league` used to construct decks from one hand-weighted score plus
blind card-swap search, and for a while from six hand-written "personalities" (aggro, control,
economy, …) whose weights I designed from the rulebook. Those are gone: the user does not want
invented archetypes. **An archetype is now a cluster of decks that have actually played**, and
the builders build toward what the data found rather than toward a thesis somebody wrote down.
A **knowledge store** still feeds what measured play has shown about each card back into the
next build. This page explains the fingerprint an archetype is made of, how the clusters and
their names are produced, how the two builders use them, and how to read a league report to see
which archetype is actually winning.

Code: `src/cptcg/deck/archetypes.py` (fingerprint, store, clustering, naming),
`strategies.py` (the builders), `knowledge.py`, `hall_of_fame.py`; the league wiring is in
`builder.league(...)`.

## The fingerprint

Every deck is reduced to the same numbers (`archetypes.fingerprint(reg, deck)`):

| Feature | What it is |
|---|---|
| `mean_cost`, `cheap_share`, `top_share` | average cost; share of cards costing 2 or less; share costing 5 or more |
| `unit_share`, `program_share`, `gear_share` | the type mix (they sum to 1) |
| `sell_share` | share of cards with a sell tag — selling is the only income |
| `mean_unit_power` | average power of the Units |
| `blockers`, `quick` | cards with BLOCKER / QUICK |
| `removal`, `gig_cards`, `haste`, `economy`, `steal`, `draw` | counts of effects read off the rules text (see below) |
| `tag_overlap` | average number of a card's tags shared with its Legends |
| `colour_red` … `colour_yellow` | 0/1: which colours the Legends bring (weighted half when clustering) |

Rather than hand-listing cards, each card's rules text is reduced once to a small `Features`
vector by regular expressions on the text with reminder parentheticals stripped: does it remove a
rival Unit (`defeat / bottom-deck / spend … rival`), **move a Gig** (`adjust / increase / decrease
/ swap / set … Gig`), **pay off a Gig configuration** (`value-pair`, `min Gig`, `8+ value`,
`even/odd value`), steal extra Gigs, draw, **ready Eddies**, call a Legend for free, play at a
discount, attack the turn it lands. A new card set gets a fingerprint for free.
`describe_fingerprint(fp)` turns the numbers into the sentence the reports print ("cheap curve
(average cost 2.4), 65% Units, 42% sellable, 9 removal effects, 6 Gig-manipulation cards").
`strategies.deck_profile(deck, reg)` is the older subset of the same numbers, kept for tests.

## The archetype store

`ArchetypeStore` (`out/archetypes.json`) records every deck that finishes a tournament or a
league generation — its Legends, card counts, fingerprint, games, wins and Bradley–Terry
strength (a deck seen again pools its record). After every update it **refits**:

1. Fingerprints are standardised (mean 0, one standard deviation = 1 per feature; colours × 0.5).
2. k-means (seeded k-means++ start, at most 50 iterations) is run for k = 2 … 6 and the k with
   the best simplified-silhouette score is kept — the clustering that separates the groups most
   cleanly. Decks are sorted by signature first, so insertion order never changes the result.
3. Each cluster becomes an archetype with a centre (in the fingerprint's own units, so it reads
   like a deck), its members, their pooled win rate and mean strength, a description, and a
   **name generated from the two features whose standardised centre is furthest from the
   overall mean**: the first gives an adjective, the second a noun, from a fixed table
   (`removal` high → "Removal", `blockers` high → "wall": *Removal wall*; `cheap_share` high +
   `unit_share` high → *Low-curve swarm*; `economy` high → "Eddies", `draw` high → "value"). Ties
   break in feature order; a clash takes the next noun. Names are therefore stable as long as a
   cluster keeps the features that set it apart.

The store needs **8 distinct decks** before it clusters. Below that it has no archetypes,
`assign(fp)` returns `None`, and every builder explores (reports label such decks *exploring*).

```python
from cptcg.deck.archetypes import ArchetypeStore, fingerprint, describe_fingerprint
store = ArchetypeStore.load("out/archetypes.json", reg)
store.update_from_tournament(t, source="my run"); store.refit(); store.save()
for a in store.ranked():                       # by pooled win rate
    print(a.name, a.id, a.win_rate, a.games, a.description)
store.assign(fingerprint(reg, deck))           # nearest archetype id for any deck, or None
```

## The builders

Both builders (`strategies.py`) share one greedy fill: pick, forty times, the card (three
copies at most) that leaves the deck's projected fingerprint closest to a **target** — squared
distance, each feature in its own scale, scaled by the number of cards placed so far so the
closeness term stays the same size from the first pick to the last — plus the card's learned
value from the knowledge store, a small tag-theme term, and noise so two builds differ.

- **Explorer** draws its target at random inside the range the legal pool allows
  (`pool_ranges`: the lowest and highest each feature can reach with 40 cards from that pool).
  Features that cannot disagree are drawn together — one cost tilt sets average cost and the
  cheap and expensive shares, and the type shares are one random composition — and each build
  pushes hard on five randomly chosen features while holding the rest loosely, because seventeen
  independent targets contradict each other and a least-squares fill would settle in the middle
  of everything. Its Legends are a random triple with a deep pool. Decks carry
  `meta["archetype"] == "exploring"`.
- **Learned(archetype, store)** targets the archetype's centre in the store's standardised
  scale, and draws its Legends from the archetype's member decks with probability proportional to
  their smoothed win rate, divided by how often a batch already used them; one time in five a
  Legend is swapped for a fresh one so nearby triples get tried. Decks carry
  `meta["archetype"]` (the name) and `meta["archetype_id"]`.

Measured in `tests/unit/test_archetypes.py`: twelve Explorer decks on one Legend triple spread
over most features of the pool's range; Learned decks land about one standard deviation from
their centre where Explorer decks land five or more.

## How learning feeds in

Every game reports which cards each deck drew and who won. `Knowledge` (`deck/knowledge.py`)
keeps, per card, the four counts behind IWD — games/wins when drawn, games/wins when not — both
globally and per **context**, the deck's Legend colour set (`"GREEN|RED"`). Colour is the right
bucket: it fixes which cards are even legal together, and there are few enough combinations that
each fills quickly.

The value a builder reads is IWD shrunk by evidence:

    global:   value = iwd · n / (n + k)                         (toward 0)
    context:  value = (iwd_ctx · n_ctx + global · k) / (n_ctx + k)   (toward the global estimate)

with `n = drawn·undrawn / (drawn + undrawn)`, the effective sample of a difference of two
proportions, and `k = 30`. A card seen in 10 games says almost nothing; after a few hundred it
speaks with most of its voice. `synergy(a, b)` is the same idea on co-draws: how much better games
go when both cards were drawn than their individual records predict.

Each builder's card score becomes `closeness + knowledge_w · value(card, context) + theme + noise`
(`knowledge_w = 6`, since shrunk IWD is ±0.1–0.3 and the closeness term is ~0–2). The target
decides the deck's shape; the evidence decides which cards fill it. Because the store persists
(`out/knowledge.json` by default), every league run makes the next generation's builders smarter.

IWD is correlational — draw order confounds it, and a card in a winning deck looks good — which
is why it enters as a shrunk prior rather than a verdict. The causal check remains the hill-climb's
paired card-swap SPRT.

## The hall of fame

A league only measures its decks against each other, so a population can drift into a local
fashion. `HallOfFame` (`deck/hall_of_fame.py`) keeps the best decks found so far — by
Bradley–Terry strength, with field win rate alongside — together with the archetype that built
them (`HallOfFame.by_archetype()` counts champions per archetype). Future leagues add the top
champions to the field the builders climb against, so a new build has to beat what has actually
won before, not only this generation's neighbours. Duplicate decks (same Legends, same counts)
keep their best record.

## Generating a population

`cptcg generate` (and the LAB page's *Generate decks* form) builds many different decks in one
go, each one on purpose:

1. The builders take turns: every archetype in the store (by win rate) and one Explorer, or the
   builders named with `--archetypes`. Each picks its Legend triple as described above, with a
   **novelty penalty** for triples and individual Legends the batch has already used, so deck 80
   explores a corner of the Legend space that deck 3 did not.
2. The deck is filled toward that builder's target plus the learned values in the knowledge
   store, with the usual build noise.
3. A candidate whose main deck is more than 70% similar (Jaccard over card copies) to an accepted
   deck is thrown away and rebuilt, up to six times; only if the pool under those Legends is too
   narrow to differ is a near-copy accepted.
4. Optionally every deck is **screened**: mirrored games against a small panel (the sample decks,
   or the hall of fame when one exists), ranked by pooled win rate, and `--keep N` saves only the
   best. A screen is deliberately cheap (10 games per opponent is enough to discard the bottom
   half); rank the survivors properly with `cptcg tourney`.

The Legend space itself: 27 Legends are printed, 26 are usable today (Rebecca's ability is not
revealed yet, so the builders never pick her). Three of the names appear twice (V, Goro Takemura,
Jackie Welles) and a deck may not repeat a name, which cuts the 2,600 triples of usable Legends to
**2,528 legal triples** (297 of them with Adam Smasher), every one with at least 29 legal
main-deck cards. Most mix two colours, about a third use three, and a few are mono-colour — the
only way to reach RAM 5–6 cards.

## Running a learning league

```python
from cptcg.deck.builder import league
for gen, t, decks in league(reg, n_builders=6, generations=4, steps=8,
                            archetypes=None,                    # automatic (see below)
                            archetypes_path="out/archetypes.json",
                            knowledge_path="out/knowledge.json",
                            hall_of_fame_path="out/hall_of_fame.json",
                            out_dir="out/league"):
    ...
```

`archetypes=None` is automatic: the store's archetypes by win rate, cycled, with one builder in
four an Explorer — and every builder an Explorer while the store has no clusters (a **cold
start** works: the first league explores, the store refits after each generation, and as soon as
eight distinct decks have played the next replacement builds toward a learned archetype). A list
of archetype ids or names (`"explorer"` allowed) is cycled instead; `"legacy"` restores the
original unopinionated builder. Each generation the replaced builder is rebuilt toward the
surviving archetype that wins least often (or as an Explorer when fewer than a quarter of the
survivors explore), so the league keeps re-testing ideas instead of converging on the current
winner. The CLI: `cptcg league --archetypes a,b --archetype-store out/archetypes.json`;
`cptcg archetypes` lists what has been learned.

## Reading a league report

Each generation writes `tournament.json` (everything the report needs: the run's settings, every
deck's list, meta and shape numbers, each builder's hill-climb history, the summary sentences) and
`report.md`, the plain-English Markdown rendered from it; `python -m cptcg report <file>` renders
it again, and a cumulative `league.json` holds the standings of every generation. Decks carry
their kind in `meta["archetype"]` — the learned archetype's name, or *exploring*:

- **Standings** gain an *Archetype* column, so the strength, win rate and "bring it?" share of
  each deck are labelled with the group it was built toward.
- **Archetypes in this run** groups decks by kind: mean strength, pooled win rate, and the best
  deck. This is the table to watch across generations. An archetype that keeps a mean strength
  above 1 while its decks are replaced and re-improved is winning *as a kind of deck*; one that
  produced a single lucky deck shows a high "Best deck" but a mean near or below 1. The store's
  own pooled win rate (`cptcg archetypes`, or the LAB league form) is the cross-run view.
- **Nash support** says what a rational field would bring. If one archetype's decks carry all
  the Nash weight, the others are strictly dominated in this pool; if support is split, the
  archetypes counter each other — read the triangle off the head-to-head matrix.
- **Cards that helped and hurt** is per-deck IWD (win rate when drawn minus when not drawn) —
  the same numbers the knowledge store accumulates, before shrinkage. `Knowledge.top(n, context)`
  gives the shrunk, cross-league view.

The hall of fame entries record the archetype too (`HallOfFame.by_archetype()`), so the
long-run question — which kind of deck keeps producing champions? — has a one-line answer.

### What to expect from a cold start

The first league on a fresh checkout has no archetypes: every builder explores, and the reports
label every deck *exploring*. Once eight distinct decks have played, the store clusters them and
names the groups; from then on new builders target the groups and the names accumulate a record.
Early names are provisional — two clusters of four decks each say little — and the description
next to each name (how many decks, how many games, the pooled win rate) is there so nobody
mistakes a young group for an established one. No archetype is claimed to be good until its
own games say so.
