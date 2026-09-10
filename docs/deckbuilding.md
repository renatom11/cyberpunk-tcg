# AI deck-building: personalities that learn

`python -m cptcg build` and `league` used to construct decks from one hand-weighted score plus
blind card-swap search. The builder now has **personalities** — named theses about how the game
is won — and a **knowledge store** that feeds what measured play has shown back into the next
build. This page explains what each personality believes, how the learning loop works, and how
to read a league report to see which philosophy is actually winning.

Code: `src/cptcg/deck/strategies.py`, `knowledge.py`, `hall_of_fame.py`; the league wiring is in
`builder.league(...)`.

## The shared machinery

Every personality builds through the same greedy filler (`builder.heuristic_deck`): rank the
RAM-legal pool by a score, fill type quotas along a cost curve, then top up sell-tag density.
The decks differ because the *score* differs, not the algorithm — so a difference in results is
a difference in thesis, not in construction luck.

Rather than hand-listing cards, each card's rules text is reduced once to a small `Features`
vector by regular expressions on the text with reminder parentheticals stripped: does it remove a
rival Unit (`defeat / bottom-deck / spend … rival`), debuff one, protect Gigs, **move a Gig**
(`adjust / increase / decrease / swap / set … Gig`), **pay off a Gig configuration** (`value-pair`,
`min Gig`, `8+ value`, `even/odd value`, "cost equal to a friendly Gig"), steal extra Gigs, draw,
**ready Eddies**, call a Legend for free, play at a discount, attack the turn it lands, pump, or
ready Units. A personality is then a dozen weights over those features plus the shape targets
(`BuildPrefs`: unit/program/gear shares, curve, sell floor). A new card set gets a first-cut
evaluation for free.

## The personalities

| Name | Thesis | What it stacks | Legends it wants |
|---|---|---|---|
| **aggro** | Race. A Unit steals two Gigs at power 10 and ready Units can't be attacked, so cheap power that swings early and often wins before the defender sets up. | Power-per-Eddie with a penalty per Eddie above 3; ADRENALINE and "can attack the turn it's played" (Valentino Street Racer, Nadia, Modded Kusanagi); Units that ready again (Saul Bright, Johnny); unblockable attackers (Valentino Guerrera). 65% Units, curve peaking at 2–3. | GO SOLO Legends costing ≤ 6 (V: Streetkid, Goro: Hands Unclean, Royce), pump texts (Saburo). |
| **control** | Deny. Only BLOCKER and QUICK interrupt a steal, so keep the Gigs, remove what attacks, and win the Overtime majority — or with one late finisher. | BLOCKERs (Meredith Stout, Rita Wheeler, Augmented Negotiators, Corpo Security), removal Programs and PLAY-removal Units (Sandayu Oda, Minotaur, Royce: Don't Call Me Simon, Wild in the Streets, Don't Fear the Reaper), QUICK reactions (Take Control, Safety Override), steal prevention (Chrome Fang, Alt: Mother of Daemons). 45% Units, heavier curve, sell floor 50%. | QUICK/BLOCKER Legends (Dum Dum, Goro: Vengeful Bodyguard) and removal CALLs (Padre spends a Unit, Wakako gives −2). |
| **economy** | Eddies win. Selling one card a turn is the only income and only *one* Unit in the pool is sellable, so the deck is mostly Programs and Gear, the Units are bombs the extra money pays for, and anything that readies an Eddie or plays for free is a second income. | Sell tags (60% floor), Eddie readying (Dying Night, Delamain Cab, Rogue: Queen of the Afterlife), free Legend calls (Arasaka Emergency Radioport, Tygers Whisper, Chrome Reverie), discounts (Zetatech Berserk, Maxtac Heavy, Octant, We Gotta Live Together), draw. Bimodal curve: cheap sellables and 6–8 cost bombs. | Legends with a cheap useful CALL (Dexter, Muamar, Padre, Wakako, Dum Dum, Viktor), Evelyn Parker (readies an Eddie on steals), Alt (Program discount). |
| **gig** | The dice are the game. Street Cred, value-pairs, min/max Gigs and 8+ faces are all things you can *set*, and several cards steal an extra Gig or draw when the faces line up. | Movers (Industrial Assembly, Peace Offering, Trust No One, Afterparty at Lizzie's, Zetatech Faceplate, Dexter: One Last Chance, Maxtac AV) and payoffs (V: Roamer of the Badlands — mover, payoff and extra steal in one card; Jackie: Ride or Die; Gorilla Arms; Kerry: Last Rockerboy; Bootleg Black Sapphire Show), Street Cred conditions. | Hanako (swap Gigs, draw per value-pair), Dexter/Muamar/Wakako/Padre (adjust, set), Kerry (reroll), Jackie: Pour One Out. |
| **synergy** | Tribes. Cards and Legends name tags — ARASAKA Units hit harder under Saburo, BRAINDANCE Programs pump under Judy, CYBERWARE Gear is cheap under Viktor — so maximise tag overlap with the Legends and between cards. | Cards carrying the Legends' tags, and cards whose text *names* a theme tag (payoffs); theme weight discounted when the legal pool is too shallow to build around. | Triples that share tags or colours, and Legends whose text names another Legend's tag (Yorinobu + Saburo + Goro). |
| **balanced** | The original heuristic: a bit of everything, no thesis. | Power-per-cost, blockers, sell tags, Legend tag overlap. | Anything. |

Measured over 20 random Legend triples (`tests/unit/test_strategies.py`), the decks differ the
way the theses say: Aggro's mean cost is ~3.3 vs Control's ~3.9; Economy has the highest sell
share (~0.67 vs 0.37–0.55); Gig decks carry ~27 cards whose text touches Gigs vs 10–15 for the
others; Control holds ~9 BLOCKERs and ~14 removal effects; Synergy has the highest tag overlap.

Use them directly:

```python
from cptcg.deck.strategies import get_strategy, all_strategies, deck_profile
s = get_strategy("gig")
legends = s.choose_legends(reg, rng)            # samples triples, keeps the best legend_fit + pool
deck = s.build(reg, legends, rng)               # deck.meta["strategy"] == "gig"
deck_profile(deck, reg)                         # mean cost, sell share, gig cards, blockers, ...
```

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

Each personality's score becomes `belief + knowledge_w · value(card, context) + noise`
(`knowledge_w = 6`, since shrunk IWD is ±0.1–0.3 and beliefs are ~0–5). The thesis still decides
the deck's shape; the evidence decides which cards fill it. Because the store persists
(`out/knowledge.json` by default), every league run makes the next generation's builders smarter.

IWD is correlational — draw order confounds it, and a card in a winning deck looks good — which
is why it enters as a shrunk prior rather than a verdict. The causal check remains the hill-climb's
paired card-swap SPRT.

## The hall of fame

A league only measures its decks against each other, so a population can drift into a local
fashion. `HallOfFame` (`deck/hall_of_fame.py`) keeps the best decks found so far — by
Bradley–Terry strength, with field win rate alongside — together with the personality that built
them. Future leagues add the top champions to the field the builders climb against, so a new
thesis has to beat what has actually won before, not only this generation's neighbours. Duplicate
decks (same Legends, same counts) keep their best record.

## Running a learning league

```python
from cptcg.deck.builder import league
for gen, t, decks in league(reg, n_builders=6, generations=4, steps=8,
                            strategies=None,                    # cycle every personality
                            knowledge_path="out/knowledge.json",
                            hall_of_fame_path="out/hall_of_fame.json",
                            out_dir="out/league"):
    ...
```

`strategies` accepts a list of names (`["aggro", "control"]`) or `BuilderStrategy` objects,
cycled across builders; `"legacy"` restores the original unopinionated builder. The CLI flags for
these arguments are the main tree's job; the API is the contract.

## Reading a league report

Each generation writes `report.md`. When decks carry `meta["strategy"]`:

- **Standings** gain a *Strategy* column, so the BT strength, field win rate and Nash weight of
  each deck are labelled with the thesis that built it.
- **Philosophies** groups decks by strategy: mean BT, pooled field win rate, and the best deck.
  This is the table to watch across generations. A thesis that keeps a mean BT above 1 while its
  decks are replaced and re-improved is winning *as a philosophy*; one that produced a single
  lucky deck shows a high "Best deck" but a mean near or below 1.
- **Nash support** says what a rational field would bring. If one philosophy's decks carry all
  the Nash weight, the others are strictly dominated in this pool; if support is split, the
  personalities form a rock-paper-scissors triangle worth reading off the head-to-head matrix
  (Aggro beating Economy, Control beating Aggro, is the classic shape).
- **Cards that move the needle** is per-deck IWD — the same numbers the knowledge store
  accumulates, before shrinkage. `Knowledge.top(n, context)` gives the shrunk, cross-league view.

The hall of fame entries record the strategy too (`HallOfFame.by_strategy()`), so the long-run
question — which philosophy keeps producing champions? — has a one-line answer.
