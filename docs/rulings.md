# Rulings

The official guide leaves some situations unsettled; the Comprehensive Rules (last updated Sep 1, 2026) settled most of them and are cited below as "CR x.y". Rather than guess silently in code, each is
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
| 006 | How is Overtime won? | **7 or more Gigs in your Gig area at any point** — checked continuously. The gameplay guide's "majority" wording was superseded by Comprehensive Rules 1.11. | `overtime_win` = "seven_gigs" | Settled (CR 1.11) |
| 007 | When exactly does Overtime begin? | **At the end of a turn, once both players have begun a turn with an empty fixer area** (CR 1.11.1, 8.17) — normally after 7 turns each. | `overtime_start` = "empty_fixers" | Settled (CR 1.11.1) |
| 008 | 7-Gig win vs. deckout on the same turn. | **The win check is Start Phase step 0, before the draw** — you win. | `win_check_before_draw` = true | Settled |
| 009 | May you attack a Gig area holding 0 dice? | **No** — an empty Gig area is not a valid attack target (CR 9.3.2.2). If it empties after the declaration the attack proceeds and steals nothing (CR 5.12.4.1, 9.22). | `allow_empty_gig_attack` = false | Settled (CR 9.3.2.2) |
| 010 | Do 0-power Units fight? | **Yes**, and they lose every fight they don't tie — but **a 0-power Unit cannot defeat a Unit** as the result of a fight (CR 9.19.2). Ties: both lose and both are defeated (CR 9.17.3). | `zero_power_fights` = true, `zero_power_cannot_defeat` = true | Settled (CR 9.17-9.19) |
| 011 | How many reactions per attack? | **As many as the defender wants**, in any order (CR 9.7); each BLOCKER fully replaces the current target (CR 9.9.1). | `max_redirects_per_attack` = 99 | Settled (CR 9.7) |
| 012 | Can a Blocker redirect an attack aimed at a spent Unit, or only at a Gig area? | **Both** — the keyword text is unqualified. | `blocker_redirects_unit_attacks` = true | Uncertain |
| 013 | Must a Blocker be ready to redirect? | **Yes** — "spend this Unit" requires a ready card. | *(implied by spend)* | Settled |
| 014 | Can a lagged Unit use BLOCKER? | **Yes.** Lag only forbids attacking and activating ⊡ effects (CR 11.3.1); BLOCKER is a reaction on a ready Unit (CR 9.9). | `lagged_units_can_block` = true | Settled (CR 11.3.1) |
| 015 | A `GO SOLO` Legend on the field — still spendable as an Eddie? Does it hold its Legend slot? | **Not spendable** (it is a Unit now); its slot sits empty, and when it leaves the field it is removed from the game — a permanent loss of that Eddie source. | `go_solo_vacates_slot` = true | Uncertain |
| 016 | Can Gear be moved after it is played? | **No**, unless a card says so. Gear on a Legend that Go Solos moves with it. | `gear_reequip` = false | Settled |
| 017 | Can Gear be attacked? | **No** — only Units are legal attack targets. | — | Settled |
| 018 | Mulligan ordering and information. | **Simultaneous and hidden** — implemented sequentially, but neither player's view reveals the other's choice. | `hidden_mulligan` = true | Settled |
| 019 | "Once per turn" — does Calling a Legend on the Rival's turn consume your own turn's Call? | **No.** Both players' once-per-turn counters reset at the start of every turn, so a player may Call on their own turn and again on the Rival's. | `once_per_turn_scope` = "turn" | Uncertain |
| 020 | Hand size limit. | **None** — the guide states none. | `hand_limit` = null | Settled |
| 021 | May you Sell for Eddie during a reaction window? | **No** — main phase, your own turn only. | `sell_in_reactions` = false | Settled |
| 022 | Deck order semantics. | Index 0 is the **bottom**, index −1 the **top**. "Trash N" takes from the top and preserves order into the trash. Bottom-deck puts cards on the bottom in any order. | — | Settled |
| 023 | Do `ATTACK` triggers resolve before the target is declared? | **No** — the target is chosen as part of declaring the attack, then the attacker is spent and `ATTACK` / 'when spent' effects become pending together (CR 9.3-9.5, 11.21.2). The earlier reading of the gameplay guide was wrong. | `attack_triggers_before_target` = false | Settled (CR 9.3) |
| 024 | An attacker is spent after attacking — can the Rival attack it later? | **Yes.** Attacking carries a real cost. | — | Settled |
| 025 | Cost payment order when Eddies and Legends are both available. | Auto-paid: ready Eddies → face-down Legends → face-up Legends (face-up last, since they may host Gear or have abilities). Exposing payment as a player decision multiplies the search branching factor for almost no strategic content. | `explicit_payment` = false | Approximation |
| 026 | Is the field size-limited? | **No limit.** The online sim draws a fixed row of field slots, but the guide states no cap. | `field_limit` = null | Uncertain |
| 027 | Can a spent Legend use GO SOLO? | **Yes.** It enters the field in the same orientation it had in the Legends area, so a spent Legend arrives spent (CR 4.5.1), and with Lag (CR 4.5.2); the keyword still lets it attack that turn, but Lag stops its ⊡ effects. It may not spend itself toward its own cost. | `go_solo_requires_ready` = false, `go_solo_enters_lagged` = true | Settled (CR 4.5) |
| 028 | Does the d20 winner choose, or simply go first? | **They choose** (the online sim offers "Go first / Go second"). | `first_player_choice` = true | Settled |
| 029 | Can power go below 0? | **No** — effective power floors at 0. Cards like Towerfall ("-5 power, then bottom-deck rival Units with power 0") only make sense this way. | — | Settled |
| 030 | What does ⊡ spend on a Gear ability? | **The Gear itself** — the glossary says the symbol means "spend this card". The host keeps its own ready state. | — | Uncertain |
| 031 | Are face-down Legends' texts active? | **No** — only face-up Legends contribute static effects, event triggers and abilities. Their identity is unknown, so their text can't apply. | — | Settled |
| 032 | Does a Legend's `PLAY` trigger when it GOES SOLO? | **Yes** — GO SOLO reads "pay this Legend's cost to **play it** as a ready Unit", and Adam Smasher *Ender of Legends* (GO SOLO + "PLAY: Defeat a rival Unit") only makes sense this way. Calling a Legend is not playing it. | — | Settled |
| 033 | Which Legends can be played to the field? | Any Legend with a cost (CR 4.5); in this set every costed Legend carries GO SOLO. Null-cost Legends never can (CR 4.5.3). | — | Settled (CR 4.5) |
| 034 | What happens to a Legend that leaves the field or Legends area? | **Removed from the game**, whatever sent it there — trash, hand or deck are invalid areas for a Legend (CR 4.4.1). Its Gear goes where it was sent and stays there (CR 4.12.2). DEFEATED triggers still resolve, after the removal (CR 4.4.2). | `legends_removed_when_leaving` = true | Settled (CR 4.4) |
| 035 | Where is a Program while it resolves? | **Outside every area** — not in your trash yet (CR 4.14.2). So "add a Program from your trash" can't pick the Program being played. | `programs_resolve_outside_areas` = true | Settled (CR 4.14.2) |
| 036 | Does a Sell caused by an effect use up the once-per-turn Sell action? | **Yes** (CR 11.9.2.2). Effects may still Sell any number of cards (CR 5.8.4). | `effect_sell_uses_action` = true | Settled (CR 11.9.2.2) |
| 037 | Adjusting a Gig to a value not on its face, or to the value it already has. | **The effect fails** — no change (CR 6.4.4, 6.4.5). "Up to N" effects let you pick a legal amount. | `set_gig_off_face_fails` = true | Settled (CR 6.4) |
| 038 | Street Cred with no Gigs. | **Null** — not 0: neither even nor odd, and smaller than 0 when compared (CR 5.11.4, 11.2.3). | `null_cred` = true | Settled (CR 11.2.3) |
| 039 | Start Phase order. | Win check, then start-of-turn effects (removing "until your next turn" effects first), then Ready, Draw, roll in a Gig (CR 8.6). Lag is removed from **all** Units at the end of each turn (CR 11.3.2). | — | Settled (CR 8.6) |
| 040 | May a face-up Legend without a Sell Tag be spent for 1 €$? | **No** (CR 5.7.2.2); face-down Legends always may. Every Legend in this set has a Sell Tag. | — | Settled (CR 5.7.2.2) |
| 041 | Calling a Legend through an effect. | Still limited to once per turn: "Call a Legend may be used only once per turn even if a game action tells you to" (CR 5.7.3). | — | Settled (CR 5.7.3) |
