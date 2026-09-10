# cptcg — Cyberpunk TCG simulator

A rules engine, AI agents and a mass-simulation harness for the **Official Cyberpunk Trading Card
Game** (WeirdCo × CD PROJEKT RED). The point is to answer *"which decks are actually the best, and
why"* by having AI agents play thousands of games against each other — and, later, to let you play
against those agents yourself.

## Status

Early. See [`docs/rules.md`](docs/rules.md) for the transcribed official rules, which are the
authoritative reference for the engine, and [`docs/rulings.md`](docs/rulings.md) for the situations
the rules leave open and what this engine does about them.

## Layout

| Path | What |
|---|---|
| `src/cptcg/core/` | The rules engine: state, step machine, combat, legal moves |
| `src/cptcg/cards/` | Card definitions — static data in JSON, behaviour scripted by card ID |
| `src/cptcg/agents/` | Random, heuristic and (later) search-based players |
| `src/cptcg/sim/` | Match running, tournaments, statistics, replays |
| `src/cptcg/learn/` | The training loop: state features, deck sampling, experience capture |
| `data/` | Card data, card images, decklists |
| `docs/` | Rules transcription, rulings, authoring guide, [the training loop](docs/learning.md) |

## Design notes

- The core engine is **stdlib-only**, so it runs unmodified under PyPy and stays portable.
- Effects **never block**: an effect pushes `Step` objects and returns, so the engine can be cloned
  at any decision point. That is what makes a search-based AI possible later without a rewrite.
- Games are fully deterministic given `(ruleset hash, decklists, seed, action indices)`, so any
  result is exactly reproducible and any replay is a few hundred bytes.

## Play it now

**https://renatom11.github.io/cyberpunk-tcg/** — the web client with the rules engine running in
the browser (Pyodide). Play against the AI with the real cards, watch replays, build decks and run
small tournaments, on desktop or phone, nothing to install. Built from this repo by
`tools/build_site.py` and deployed by `.github/workflows/pages.yml` on every push.

## Usage

```bash
pip install -e '.[dev]'
pytest                                   # ~330 tests: rules, properties, one scenario per card

# play 1000 mirrored games between two decks and report win rates with 95% intervals
python -m cptcg sim --deck-a data/decks/the_heist.json \
                    --deck-b data/decks/embracing_power.json -n 1000 --seed 42 -j 4

python -m cptcg sim ... --replays out/replays    # one ~1 KB replay per game
python -m cptcg replay out/replays/g000042_0.json --step   # watch a game back
python -m cptcg validate data/decks/*.json       # deck legality + RAM
python -m cptcg cards --unimplemented            # cards still needing a script

# the lab: round robin with Bradley-Terry ratings, Nash support, FDR-corrected matrix, card IWD
python -m cptcg tourney data/decks/sample_*.json -n 300 -j 4 --out out/league1
python -m cptcg report out/league1/tournament.json     # re-render the plain-English Markdown report of any saved run

# AI deck-building: a builder constructs a RAM-legal deck toward a target shape, then improves it by measured play.
# Archetypes are learned from play (out/archetypes.json): clusters of decks that have played, named from
# the features that set them apart; until 8 decks have played every builder explores.
python -m cptcg archetypes                                      # what has been learned so far, with win rates
python -m cptcg build --archetype explorer --steps 30 --out out/built.json      # invent a shape, random Legends
python -m cptcg build --legends v-streetkid,dexter-deshawn-off-the-grid,rogue-amendiares-preem-solo --steps 30
python -m cptcg build --archetype low-curve-swarm --knowledge out/knowledge.json   # build toward a learned archetype

# Build a ton of different decks at once: builders pick their Legends with a novelty penalty,
# near-duplicates are rejected, then (optionally) every deck is screened against a panel and only
# the best are kept. 26 usable Legends with the unique-name rule give 2,528 legal triples.
python -m cptcg generate --count 100 --seed 1 --out data/decks/generated/batch1
python -m cptcg generate --count 200 --screen 10 --keep 20 --knowledge out/knowledge.json -j 4
python -m cptcg generate --count 12 --archetypes explorer --legends v-streetkid,jackie-welles-mamas-favorite,padre-man-of-the-cross

# AI builders evolving against each other, with a tournament report every generation.
# Builders explore or target learned archetypes; every generation feeds the archetype store, the
# knowledge store (per-card values learned from play) and the hall of fame (past champions join the
# field). See docs/deckbuilding.md.
python -m cptcg league --builders 6 --generations 3 --steps 5 --out out/league \
    --knowledge out/knowledge.json --hof out/hall_of_fame.json

# the web client: play against the AI, watch any replay back, browse lab reports, build decks
python -m cptcg serve            # then open http://127.0.0.1:8000/
```

The client has a GUIDE tab and an explainer at the top of every tab that says what the tab is for,
how to use it and what each control does. The board follows the layout of the popular online sim: hand, fixer dice tray and
Gig area on the left; Legends and field in the centre; log and a prompt panel with one button per
legal action on the right. Click a glowing card to act on it. UNDO and EXPORT (a replay file) are
free because games are deterministic. It holds no game logic — it renders the engine's view and
posts back an option index — so anything the engine can do, it can show. The BUILD page is a
deck builder in the same style: a filterable library, Legend slots with the RAM budget they unlock,
a cost curve, live legality, text export, save to `data/decks/`, and one-click AI builds — an
Explorer that invents a deck shape, or a build toward any archetype learned from play (using
learned card values when `out/knowledge.json` exists).

Agents: `random`, `heuristic` (greedy one-ply lookahead). The heuristic beats random ~95% of
the time. Speed is roughly 4 ms/game for random bots and ~175 ms/game (5–6 games/s) for
heuristic-vs-heuristic on one core; `-j` spreads games across cores and results are identical
regardless of `-j`. `python tools/bench.py check` replays 224 golden games and must print
IDENTICAL after any engine change; `bench.py time` measures speed and `bench.py fuzz` prints a
digest over random decks from the whole card pool for cross-checking two branches.

The card pool is in `data/cards/wnc.json` (see `data/COVERAGE.md` for what is verified and
scripted). `data/decks/the_heist.json` and `data/decks/embracing_power.json` are the two retail
starter decks exactly as WeirdCo published them; the `sample_*` decks are generated, RAM-legal
lists for variety.

Card faces live in `data/images/<id>.jpg` (plus `_back.jpg`) and were cut from screenshots of
the official card database with `tools/crop_cards.py`, which OCRs each page's captions, crops the
face above every caption and matches it to a card id by name and subtitle:

```
pip install pillow rapidocr-onnxruntime
python tools/crop_cards.py shots/*.png --back back.png --out data/images
```

Three faces the desktop grid never showed whole — 6th Street Recruits, Adam Smasher (Metal Over
Meat) and Adrenaline Converter — were cut by hand from phone captures of the same database, to
the same 423x590 geometry.

The art is © CD PROJEKT S.A. / WeirdCo and is included for personal use of this tool only.
