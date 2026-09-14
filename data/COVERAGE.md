# Card data coverage

Pool: **151 cards** (Welcome to Night City + starter sets).

| | Count |
|---|---|
| Transcribed and verified against the card face | 150 |
| Needing a card-face screenshot | 1 |
| Vanilla (no rules text — need no script) | 10 |
| Scripted | 140 |
| Rules text not yet scripted | 0 |

## Needs a card-face screenshot

These have placeholder or partial data. Decks containing them are refused unless `--allow-unverified` is passed.

- **Rebecca** — Having a Moment (`rebecca-having-a-moment`): Promo-style full-art card; no stats or text were visible in the screenshot. Everything here is a placeholder.

## Rules text not yet scripted

Transcribed, but the effect is not implemented. Decks containing them are refused unless `--allow-unscripted` is passed (the card would play as vanilla).




## What is *checked*

The table above counts what exists. This one counts what has been verified, which is a different question and the one that decides whether a simulation result means anything. `needs_script` reads 0 for every card in the pool and is blind to a script that is wrong rather than missing.

| | Count |
|---|---|
| Scripted cards | 140 |
| ... named by at least one test | 140 |
| ... named by no test at all | 0 |
| Open audit findings (failing tests, awaiting a fix) | 32 |

Open findings — each is a `xfail(strict=True)` test under `tests/cards/audit/`, so the suite stays green until a fix makes one pass and pytest reports XPASS:

- `AUD-6th-street-recruits-1`
- `AUD-afterparty-at-lizzies-1`
- `AUD-bonnie-and-clyde-1`
- `AUD-chrome-fang-1`
- `AUD-cyberpsychosis-1`
- `AUD-dying-night-vs-pistol-1`
- `AUD-el-sombreron-la-venganza-lenta-1`
- `AUD-fool-on-the-hill-1`
- `AUD-gorilla-arms-1`
- `AUD-goro-takemura-losing-his-way-1`
- `AUD-gunpoint-diplomacy-1`
- `AUD-industrial-assembly-1`
- `AUD-kiroshi-optics-1`
- `AUD-maelstrom-zealots-1`
- `AUD-memory-relapse-1`
- `AUD-misty-olszewski-mender-of-broken-spirits-1`
- `AUD-mox-inciters-1`
- `AUD-peace-offering-1`
- `AUD-placide-voodoo-sentinel-1`
- `AUD-reboot-optics-1`
- `AUD-royce-psycho-on-the-edge-1`
- `AUD-saburo-arasaka-stubborn-patriarch-1`
- `AUD-satori-sword-of-saburo-1`
- `AUD-shattered-memories-1`
- `AUD-sketchy-ripper-1`
- `AUD-the-relic-experimental-biochip-1`
- `AUD-trust-no-one-1`
- `AUD-unlikely-bond-1`
- `AUD-viktor-vektor-drop-your-illusions-1`
- `AUD-westbrook-netrunner-1`
- `AUD-yorinobu-arasaka-steel-dragon-1`
- `AUD-zetatech-faceplate-1`

See [docs/verification.md](../docs/verification.md) for what each kind of check can and cannot prove.

