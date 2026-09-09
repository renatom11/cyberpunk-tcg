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
| `data/` | Card data, card images, decklists |
| `docs/` | Rules transcription, rulings, authoring guide |

## Design notes

- The core engine is **stdlib-only**, so it runs unmodified under PyPy and stays portable.
- Effects **never block**: an effect pushes `Step` objects and returns, so the engine can be cloned
  at any decision point. That is what makes a search-based AI possible later without a rewrite.
- Games are fully deterministic given `(ruleset hash, decklists, seed, action indices)`, so any
  result is exactly reproducible and any replay is a few hundred bytes.

## Development

```bash
pip install -e '.[dev]'
pytest
```
