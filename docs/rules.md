# Cyberpunk TCG — Official Rules (transcription)

Transcribed from the official *Printable Gameplay Guide* (WeirdCo / CD PROJEKT RED, © 2026).
This file is the **authoritative reference** for the engine. Where the engine must decide something
this document does not settle, the decision is recorded in [`rulings.md`](rulings.md) with a
`RulesConfig` flag — never guessed silently in code.

> **Card text beats this document.** The guide states: *"If there's a conflict between a card's text
> and this guide, follow the text on the card."*

## Components

Each player needs six dice — **d4, d6, d8, d10, d12, d20** — and a deck of Cyberpunk TCG cards.

Playmat areas: **Fixer area**, **Gig area**, **Field**, **Eddies area**, **Legends area**,
**Deck**, **Trash**.

## Win conditions

- **7 Gigs.** If a player has at least **7 Gig dice** in their Gig area at the **start of their
  turn** — before taking one from the fixer area — they win.
- Each player owns only 6 dice, so reaching 7 **requires stealing at least one** from the Rival.
- **Deckout.** If you are required to draw a card but have no cards left in your deck, your **Rival**
  immediately wins.
- **Overtime.** Begins at the end of a turn once both players have begun a turn with an empty
  fixer area (normally after each has taken 7 turns). During Overtime a player with **7 or more**
  Gig dice in their Gig area wins immediately, at any point (Comprehensive Rules 1.11).

Each discrete die is a single Gig. Controlling two dice is always closer to winning than one.

## Playmat areas

**Fixer area.** All your Gig dice start here. At the start of your turn, after drawing, choose one
die from this area, roll it to set its value, then move it to your Gig area. You may choose any die
**except the d20, which is always last**.

**Gig area.** The Gigs you control, including any stolen from your Rival. **Street Cred** is the sum
of the top faces of all dice in this area.

**Field.** Where you play Units. Units here can attack one of your Rival's **spent** Units to start a
fight, or attack your Rival's Gig area to steal a Gig.

**Eddies area.** Eddies (€$) are the currency. To play a card you pay its cost — the number in the
top left corner — by **spending** (turning sideways) that many Eddies. The area starts empty; you
create Eddies by selling cards from your hand.

**Legends area.** Your 3 Legends — they start face-down in a random order. Once per turn you may
**Call a Legend** by spending 1 €$ to flip one face-up, **without looking first**. Whether face-up or
face-down, a Legend can also be spent to pay 1 €$.

**Deck.** Draw from the top. **Trash.** Discarded, defeated or trashed cards go here face-up.

## Reading your cards

| Field | Meaning |
|---|---|
| **Cost** | Top left. Spend that many Eddies to play it. |
| **Sell tag** | Cards with this symbol can be sold for Eddies. Legends with a sell tag can be spent to pay 1 €$. |
| **Type** | Top right: Legend, Unit, Program or Gear. |
| **RAM** | Legends' cumulative RAM amount and color determines which other cards may go in the deck. |
| **Tags** | A card's affiliations (MERC, ARASAKA, CYBERWARE…), referenced by effects. |
| **Power** | Bottom right. Used in fights; a Unit steals an extra Gig per 10 power. |
| Set code, card number, rarity, artist | Identification only. |

### Card types

- **Legend** — a deck's centerpiece characters. All 3 begin face-down in random order. Once per turn
  you may Call a Legend (spend 1 €$, flip one face-up at random). You may also spend any number of
  Legends as 1 €$ each, face-up or face-down.
- **Unit** — pay its cost and place it **ready** in the field. Units can't attack the turn they're
  played.
- **Program** — instantaneous. Pay its cost, resolve the effect, move it to the trash.
- **Gear** — pay its cost and equip it to a friendly Unit or Legend. When the host card moves to a
  different area, all equipped Gear goes with it.

### Timing triggers

| Trigger | When |
|---|---|
| `PLAY` | When you play this card. |
| `CALL` | When you flip this Legend face-up through Call a Legend. |
| `ATTACK` | When this Unit attacks — **and before your Rival reacts**. |
| `DEFEATED` | When this Unit is defeated. |

### Keywords

| Keyword | Effect |
|---|---|
| `ADRENALINE` | This Unit can attack the turn it's played. |
| `GO SOLO` | Pay this Legend's cost to play it as a ready Unit. It can attack this turn. If it leaves the field, remove it from the game. |
| `QUICK` | You may also activate this effect (or play this Program) as a reaction when a rival Unit attacks. |
| `BLOCKER` | When a rival Unit attacks, you may spend this Unit to redirect the attack to it instead. |

## Setup

1. **Shuffle** your deck and randomize your Legends face-down in the Legends area.
2. **Determine play order.** Both players roll a d20 (reroll on a tie). The higher roll decides who
   goes first. The player going first **spends their 2 leftmost Legends and doesn't ready them on
   their first turn**.
3. **Draw 6.** You may mulligan once: shuffle your hand back into your deck and draw 6 new cards.

## Turn order

Each turn has two phases: the **Start Phase** and the **Main Phase**.

### Start Phase (in order)

1. **Ready spent cards** — return all your spent (sideways) cards to ready (upright).
2. **Draw 1** — add the top card of your deck to your hand.
3. **Gain a Gig** — take a die from your fixer area, roll it, add it to your Gig area. Any die except
   the d20, which is always rolled last.

### Main Phase (any number, any order)

- **Sell for Eddie** *(once per turn)* — sell any card in hand with a sell tag. Reveal it to your
  opponent, then place it face-down in the Eddies area. However much it cost in hand, it is worth
  only **1 €$**.
- **Play** — spend Eddies equal to the card's cost. You may also spend any number of Legends as 1 €$
  each, face-up or face-down. **All Units enter the field with `LAG`**, which lasts until the end of
  the turn; Units with Lag can't attack or activate self-spend effects.
- **Call a Legend** *(once per turn)* — spend 1 €$ to flip a Legend face-up. No peeking beforehand.
- **Attack** — spend the attacking Unit.

## Attacking

Each Unit attacks individually and completes all steps before another Unit attacks.

1. **Spend the attacking Unit** (turn it sideways). Resolve any `ATTACK` effects on it. Units can't
   attack the turn they're played.
2. **Declare a target** — a **spent** rival Unit (to start a fight), or the rival Gig area (to steal
   a Gig). **Ready Units can't be attacked.**
3. **Rival reacts.** The attacked player may take any number of these:
   - **Call a Legend** (once per turn) — spend 1 €$ to flip a Legend face-up.
   - **`QUICK`** — activate card effects or play cards with the Quick keyword.
   - **`BLOCKER`** — spend a Unit with Blocker to redirect the attack to it instead.
4. **Resolve.**
   - *Attacked a spent Unit* → **Fight.** Compare both Units' power. The higher power Unit defeats
     the other; on a tie they defeat each other. Move defeated Units to the trash and resolve any
     `DEFEATED` effects.
   - *Attacked the Gig area* → **Steal.** Choose a rival Gig die and move it to your Gig area. Units
     steal an additional Gig at power 10, two more at power 20, and so on — and **0 Gigs at power 0**.

     | Power | Gigs stolen |
     |---|---|
     | 0 | 0 |
     | 1–9 | 1 |
     | 10–19 | 2 |
     | 20+ | 3, etc. |

A Unit doesn't have to attack. Ready Units can't be attacked, but most Units — even ready ones —
can't protect your Gigs; only Units with reaction effects like `QUICK` or `BLOCKER` can interrupt
attacks.

**When a Unit redirects an attack, a fight plays out as though your Unit attacked the blocking Unit
instead. Even if you defeat it, you don't steal any Gigs.** In general, if an effect redirects or
stops a direct attack on your Rival, you don't get to steal a Gig.

## Deck building & RAM

- Use exactly **3 Legend cards with unique names**.
- Include **no fewer than 40 and no more than 50** cards, not counting your Legends.
- Use **no more than 3 copies** of the same card.
- Cards must stay within the **RAM limit** set by your Legends.

Each Legend has a colored border and a RAM limit. **Each Legend's RAM only counts toward its own
color.** The cumulative RAM of your three Legends sets the maximum RAM value for cards of that color
in your deck.

> Example: Goro Takemura: Hands Unclean (2 Green RAM) + Saburo Arasaka: Stubborn Patriarch (2 Green
> RAM) + Yorinobu Arasaka: Embracing Destruction (2 Red RAM) allows Green cards up to **4 RAM** and
> Red cards up to **2 RAM**.

## Glossary

- **Spend / spent** — turn a card sideways. Spent cards can't be spent again until they ready.
  Eddies and Legends spend to pay costs; Units spend when they attack.
- **Ready** — upright. Only ready Units can attack, and ready Units can't be attacked.
- **Cost** — the number in the top left corner.
- **Eddies (€$)** — each face-down card in your Eddies area is 1 Eddie. Legends spent as €$ are not
  actually Eddies.
- **Sell** — once per turn, sell a sell-tagged card from hand: reveal it, place it face-down in the
  Eddies area. Worth 1 €$ regardless of its cost.
- **Gigs** — the dice. First player to start their turn with 7 or more wins.
- **Street Cred** — the sum of the top faces of the dice in your Gig area.
- **Fixer** — all dice start in the fixer area; one moves to the Gig area each turn.
- **Lag** — Units with Lag can't attack or activate self-spend effects. All Units enter with Lag,
  which lasts until end of turn.
- **Power** — bottom-right number, used while attacking.
- **Call a Legend** — once per turn, spend 1 €$ to flip a Legend face-up. May be done during your
  main phase **or as a reaction when a rival Unit attacks**.
- **Bottom-deck** — put cards on the bottom of your deck in any order.
- **Trash** (verb) — put the top card of your deck into your trash area; with a number, that many.

## Credits

Game design and rules: Richard Zapp, Chris Solis, David McDarby, Casey Campbell, Madeline Anthony.
Preliminary game development: Brieger Creative — John Brieger, Breeze Grigas, Bryan Lue.
