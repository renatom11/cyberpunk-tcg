# League generation 1

4 decks, agent `heuristic`, seed 2001. Every pair played as mirrored seed pairs; cells stopped early when an SPRT settled them, so sample sizes differ by cell.

## Standings (Bradley–Terry)

| # | Deck | BT strength | vs field | 95% interval | Nash weight |
|---|---|---|---|---|---|
| 1 | builder1 | 1.74 | 72% (120) | 64–80% | 100% |
| 2 | builder4 | 1.38 | 66% (120) | 57–74% | 0% |
| 3 | builder2 | 0.54 | 38% (120) | 29–46% | 0% |
| 4 | builder3 | 0.34 | 24% (120) | 17–33% | 0% |

Intransitivity (largest |observed − BT-predicted|): **9 points**.

Nash support (what a rational field brings): builder1 100%

## Head-to-head (row beats column)

| | builder1 | builder4 | builder2 | builder3 |
|---|---|---|---|---|
| builder1 | · | 50% (40) | **80%** (40) | **88%** (40) |
| builder4 | 50% (40) | · | 62% (40) | **85%** (40) |
| builder2 | **20%** (40) | 38% (40) | · | 55% (40) |
| builder3 | **12%** (40) | **15%** (40) | 45% (40) | · |

Bold = significant after Benjamini–Hochberg FDR at q < 0.05. (n) = games in the cell.

## Cards that move the needle (per deck)

IWD = win rate in games where the card was drawn minus games where it wasn't. Correlational — draw order confounds it; the causal check is a card-swap A/B.

**builder1**

| Card | GIH WR | GND WR | IWD | drawn |
|---|---|---|---|---|
| ruthless-lowlife | 75% | 66% | +9 | 91 |
| the-heist | 74% | 67% | +7 | 99 |
| kiroshi-optics | 73% | 70% | +3 | 93 |
| shattered-memories | 73% | 71% | +2 | 89 |
| carnage-at-the-colosseum | 73% | 72% | +1 | 41 |
| … | | | | |
| mantis-blades | 68% | 85% | -17 | 87 |
| screw-lovelorn-fool | 70% | 89% | -19 | 102 |
| valentino-guerrera | 68% | 88% | -20 | 94 |

**builder4**

| Card | GIH WR | GND WR | IWD | drawn |
|---|---|---|---|---|
| la-llorona-ghost-of-the-past | 70% | 48% | +22 | 99 |
| ruthless-lowlife | 70% | 52% | +19 | 91 |
| arasaka-emergency-radioport | 71% | 59% | +12 | 66 |
| valentino-guerrera | 73% | 63% | +10 | 37 |
| kerry-eurodyne-the-last-rockerboy | 67% | 61% | +6 | 89 |
| … | | | | |
| satori-sword-of-saburo | 63% | 74% | -11 | 89 |
| over-the-edge | 62% | 75% | -12 | 88 |
| johnny-silverhand-never-stop-fighting | 62% | 81% | -19 | 94 |

**builder2**

| Card | GIH WR | GND WR | IWD | drawn |
|---|---|---|---|---|
| augmented-negotiators | 42% | 7% | +34 | 106 |
| dexter-deshawn-one-last-chance | 45% | 31% | +13 | 56 |
| cyberpsychosis | 40% | 29% | +12 | 92 |
| t-bug-amateur-philosopher | 38% | 31% | +7 | 104 |
| maxtac-suppression-team | 38% | 33% | +5 | 102 |
| … | | | | |
| trauma-team-operatives | 31% | 42% | -11 | 54 |
| heywood-ripperdoc | 34% | 46% | -12 | 85 |
| jackie-welles-ride-or-die-choom | 35% | 50% | -15 | 98 |

**builder3**

| Card | GIH WR | GND WR | IWD | drawn |
|---|---|---|---|---|
| goro-takemura-losing-his-way | 29% | 0% | +29 | 101 |
| synapse-burnout | 27% | 14% | +14 | 91 |
| riot-shield | 28% | 15% | +13 | 86 |
| pepe-najarro-working-doubles | 27% | 14% | +13 | 98 |
| field-operator | 26% | 19% | +7 | 93 |
| … | | | | |
| fool-on-the-hill | 22% | 31% | -8 | 94 |
| panam-palmer-strength-through-family | 21% | 42% | -21 | 101 |
| corpo-security | 21% | 54% | -33 | 107 |

