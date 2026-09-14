# League generation 2

4 decks, agent `heuristic`, seed 2002. Every pair played as mirrored seed pairs; cells stopped early when an SPRT settled them, so sample sizes differ by cell.

## Standings (Bradley–Terry)

| # | Deck | BT strength | vs field | 95% interval | Nash weight |
|---|---|---|---|---|---|
| 1 | builder1 | 1.57 | 69% (120) | 60–77% | 0% |
| 2 | builder4 | 1.48 | 68% (120) | 59–75% | 100% |
| 3 | builder2 | 0.66 | 43% (120) | 35–52% | 0% |
| 4 | builder3 | 0.29 | 20% (120) | 14–28% | 0% |

Intransitivity (largest |observed − BT-predicted|): **14 points** — a rock-paper-scissors relationship is present.

Nash support (what a rational field brings): builder4 100%

## Head-to-head (row beats column)

| | builder1 | builder4 | builder2 | builder3 |
|---|---|---|---|---|
| builder1 | · | 45% (40) | **80%** (40) | **82%** (40) |
| builder4 | 55% (40) | · | 55% (40) | **92%** (40) |
| builder2 | **20%** (40) | 45% (40) | · | 65% (40) |
| builder3 | **18%** (40) | **8%** (40) | 35% (40) | · |

Bold = significant after Benjamini–Hochberg FDR at q < 0.05. (n) = games in the cell.

## Cards that move the needle (per deck)

IWD = win rate in games where the card was drawn minus games where it wasn't. Correlational — draw order confounds it; the causal check is a card-swap A/B.

**builder1**

| Card | GIH WR | GND WR | IWD | drawn |
|---|---|---|---|---|
| chrome-fang | 78% | 64% | +14 | 45 |
| kiroshi-optics | 72% | 59% | +13 | 93 |
| the-heist | 71% | 63% | +8 | 93 |
| shattered-memories | 71% | 64% | +6 | 92 |
| valentino-guerrera | 70% | 67% | +3 | 96 |
| … | | | | |
| maelstrom-goons | 65% | 81% | -16 | 88 |
| mantis-blades | 64% | 84% | -20 | 89 |
| screw-lovelorn-fool | 66% | 88% | -21 | 104 |

**builder4**

| Card | GIH WR | GND WR | IWD | drawn |
|---|---|---|---|---|
| la-llorona-ghost-of-the-past | 71% | 52% | +18 | 99 |
| valentino-guerrera | 79% | 63% | +17 | 34 |
| arasaka-emergency-radioport | 74% | 60% | +14 | 68 |
| meredith-stout-stone-cold-corpo | 70% | 61% | +10 | 87 |
| ruthless-lowlife | 69% | 62% | +8 | 94 |
| … | | | | |
| chrome-fang | 64% | 73% | -8 | 76 |
| over-the-edge | 65% | 76% | -11 | 91 |
| satori-sword-of-saburo | 65% | 78% | -13 | 93 |

**builder2**

| Card | GIH WR | GND WR | IWD | drawn |
|---|---|---|---|---|
| augmented-negotiators | 46% | 17% | +30 | 108 |
| dexter-deshawn-one-last-chance | 50% | 38% | +12 | 56 |
| maxtac-suppression-team | 44% | 36% | +9 | 106 |
| cyberpsychosis | 45% | 38% | +6 | 94 |
| alt-cunningham-mother-of-daemons | 44% | 40% | +4 | 100 |
| … | | | | |
| gorilla-arms | 41% | 59% | -18 | 103 |
| heywood-ripperdoc | 37% | 58% | -21 | 84 |
| jackie-welles-ride-or-die-choom | 39% | 61% | -22 | 97 |

**builder3**

| Card | GIH WR | GND WR | IWD | drawn |
|---|---|---|---|---|
| mox-inciters | 22% | 0% | +22 | 111 |
| rita-wheeler-no-stupid-questions | 23% | 5% | +18 | 101 |
| mtod12-flathead | 22% | 7% | +15 | 106 |
| placide-voodoo-sentinel | 21% | 12% | +9 | 104 |
| netwatch-netdriver | 22% | 14% | +8 | 91 |
| … | | | | |
| unlikely-bond | 19% | 28% | -9 | 102 |
| dying-night-vs-pistol | 19% | 33% | -15 | 108 |
| three-mouths-one-desire | 16% | 50% | -34 | 106 |

