# Rulings

The official guide leaves some situations unsettled. Rather than guess silently in code, each is
recorded here with a **default** and a corresponding field in `RulesConfig`. The active config is
hashed into every simulation result and replay, so changing a ruling visibly invalidates
comparisons with older runs instead of quietly shifting them.

Status legend — **Settled**: the guide implies it strongly enough that the alternative breaks the
game. **Uncertain**: a real coin-flip; revisit when official clarification lands.

| # | Question | Default | `RulesConfig` | Status |
|---|---|---|---|---|
| 001 | Do Eddies ready during Start Phase step 1? | **Yes.** Step 1 says "return all your spent cards to ready", and Eddies are cards that spend to pay costs. Without this the economy has no engine — you could never spend the same Eddie twice. | `eddies_ready` = true | Settled |
| 002 | Are the identities of cards in an Eddies area public? | **Yes, as an unordered multiset.** Selling requires revealing the card; both players saw it. Order is lost because they sit face-down. | `perfect_eddie_memory` = true | Settled |
| 003 | Can a Legend spent as an Eddie still be Called? | **Yes.** Spent/ready and face-down/face-up are orthogonal states. | `spent_legend_callable` = true | Settled |
| 004 | Start Phase step 3 with an empty fixer area (turn 7+). | **Skip the step.** You may not take dice from your own Gig area, and stolen dice never enter a fixer area. | `empty_fixer_skips` = true | Settled |
| 005 | Are stolen dice rerolled? | **No** — the die keeps its face value, so stealing transfers Street Cred as well as a Gig. | `reroll_stolen_dice` = false | Settled |
| 006 | Overtime "majority" — of what denominator? | **Majority of the dice currently in both Gig areas** (`2 × mine > total`), checked continuously as a state-based action. Dice still in a fixer area don't count. | `overtime_majority` = "gig_areas" | Uncertain |
| 007 | When exactly does Overtime begin? | **Once both players have completed 7 turns** — live from the start of turn 15. | `overtime_after_turn` = 7 | Uncertain |
| 008 | 7-Gig win vs. deckout on the same turn. | **The win check is Start Phase step 0, before the draw** — you win. | `win_check_before_draw` = true | Settled |
| 009 | May you attack a Gig area holding 0 dice? | **Yes** — `ATTACK` triggers still matter — and it steals nothing. | `allow_empty_gig_attack` = true | Uncertain |
| 010 | Do 0-power or negative-power Units still fight? | **Yes.** Only the *steal count* is floored at 0. A 0-power Unit loses every fight it doesn't tie. | `zero_power_fights` = true | Settled |
| 011 | Can several Blockers redirect one attack? Does a redirect close the reaction window? | **One redirect per attack**; the window stays open for other reactions. | `max_redirects_per_attack` = 1 | Uncertain |
| 012 | Can a Blocker redirect an attack aimed at a spent Unit, or only at a Gig area? | **Both** — the keyword text is unqualified. | `blocker_redirects_unit_attacks` = true | Uncertain |
| 013 | Must a Blocker be ready to redirect? | **Yes** — "spend this Unit" requires a ready card. | *(implied by spend)* | Settled |
| 014 | Can a Unit with `LAG` block? | **No.** Lag forbids self-spend effects, and Blocker is a self-spend. | `lagged_units_can_block` = false | Uncertain |
| 015 | A `GO SOLO` Legend on the field — still spendable as an Eddie? Does it hold its Legend slot? | **Not spendable** (it is a Unit now); its slot sits empty, and when it leaves the field it is removed from the game — a permanent loss of that Eddie source. | `go_solo_vacates_slot` = true | Uncertain |
| 016 | Can Gear be moved after it is played? | **No**, unless a card says so. Gear on a Legend that Go Solos moves with it. | `gear_reequip` = false | Settled |
| 017 | Can Gear be attacked? | **No** — only Units are legal attack targets. | — | Settled |
| 018 | Mulligan ordering and information. | **Simultaneous and hidden** — implemented sequentially, but neither player's view reveals the other's choice. | `hidden_mulligan` = true | Settled |
| 019 | "Once per turn" — does Calling a Legend on the Rival's turn consume your own turn's Call? | **No.** Both players' once-per-turn counters reset at the start of every turn, so a player may Call on their own turn and again on the Rival's. | `once_per_turn_scope` = "turn" | Uncertain |
| 020 | Hand size limit. | **None** — the guide states none. | `hand_limit` = null | Settled |
| 021 | May you Sell for Eddie during a reaction window? | **No** — main phase, your own turn only. | `sell_in_reactions` = false | Settled |
| 022 | Deck order semantics. | Index 0 is the **bottom**, index −1 the **top**. "Trash N" takes from the top and preserves order into the trash. Bottom-deck puts cards on the bottom in any order. | — | Settled |
| 023 | Do `ATTACK` triggers resolve before the target is declared? | **Yes** — the guide orders them step 1 then step 2. This is the most surprising ordering in the engine and it is implemented faithfully: an `ATTACK` trigger can change which targets are legal. | `attack_triggers_before_target` = true | Settled |
| 024 | An attacker is spent after attacking — can the Rival attack it later? | **Yes.** Attacking carries a real cost. | — | Settled |
| 025 | Cost payment order when Eddies and Legends are both available. | Auto-paid: ready Eddies → face-down Legends → face-up Legends (face-up last, since they may host Gear or have abilities). Exposing payment as a player decision multiplies the search branching factor for almost no strategic content. | `explicit_payment` = false | Approximation |
| 026 | Is the field size-limited? | **No limit.** The online sim draws a fixed row of field slots, but the guide states no cap. | `field_limit` = null | Uncertain |
| 027 | Can a spent Legend use GO SOLO? | **No** — it must be ready. Otherwise spend it for 1 €$, then GO SOLO it and it arrives ready: a free Eddie every turn. | `go_solo_requires_ready` = true | Uncertain |
| 028 | Does the d20 winner choose, or simply go first? | **They choose** (the online sim offers "Go first / Go second"). | `first_player_choice` = true | Settled |
| 029 | Can power go below 0? | **No** — effective power floors at 0. Cards like Towerfall ("-5 power, then bottom-deck rival Units with power 0") only make sense this way. | — | Settled |
| 030 | What does ⊡ spend on a Gear ability? | **The Gear itself** — the glossary says the symbol means "spend this card". The host keeps its own ready state. | — | Uncertain |
| 031 | Are face-down Legends' texts active? | **No** — only face-up Legends contribute static effects, event triggers and abilities. Their identity is unknown, so their text can't apply. | — | Settled |
| 032 | Does a Legend's `PLAY` trigger when it GOES SOLO? | **Yes** — GO SOLO reads "pay this Legend's cost to **play it** as a ready Unit", and Adam Smasher *Ender of Legends* (GO SOLO + "PLAY: Defeat a rival Unit") only makes sense this way. Calling a Legend is not playing it. | — | Settled |
