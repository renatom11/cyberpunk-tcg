# Regenerations of `games.json`

`tests/golden/games.json` pins 224 games as exact action-index streams. A real card fix will
legitimately change some of them, and the danger has never been the change — it is regenerating on a
diff nobody localised, which turns "the fix worked" into "the fix, plus whatever else was on the
tree". This file is the ledger, so `git log -- tests/golden/games.json` stays a readable history of
deliberate decisions rather than a list of times the file moved.

Every entry records the five pieces of evidence from `docs/verification.md`. A regeneration without
all five is not one.


## 2026-09-21 — Stage 0 E10: the reaction window always opens (G2, engine-wide)

**The change.** `steps.ReactionWindowStep` no longer returns silently when the defender's only
option is Pass. That skip was a tell no table has: the window's absence proved the defender held
no affordable QUICK, no ready BLOCKER and no Call, and its presence proved they did (the design's
leak 1.3b-11, removed per the owner's decision 2d) — and inside a search it made the attacker's
tree branch by what each sampled world had dealt the defender. A Pass-only window is now a
decision with one answer, recorded in the stream like any other. `tests/conftest.do` answers
such a window for the scenario tests, whose question is what the attack does. Reproduced red
first (`test_the_reaction_window_opens_even_when_the_defender_can_only_pass`).

**One window is left as it was, and it is written down as a residual.** The window that
*re-opens* after a Block (a redirect, ruling 012) still closes silently when the defender has
nothing further. The first version of this change opened it too, and the delayed suite lost
`defensive-setup-shield-the-wrecker` to it: the frozen heuristic's preview of a Block runs to the
next pending decision and stops (`HeuristicAgent._resolve` returns as soon as the turn is not its
own), so a Pass-only re-window left every Block looking like a spent Unit and an unresolved
fight (preview −17.75 against Pass's −10.80 on that board; −10.75 with the fight resolved), and
the heuristic stopped blocking. The heuristic is frozen and is the yardstick, so the engine keeps
that one window closed. What it still reveals is whether a defender who has already blocked
could have reacted again — after a Block only, and only to that attack's owner. Recorded in
`docs/stage0.md` under the tells not removed.

**1. Prediction.** Every key. Observed: all 8.

**2. Localisation.** All eight first divergences are the new decision itself — a `REACTION` with
the single option `Pass` (e.g. `the_heist~embracing_power~heuristic` game 0 at decision 23,
`sample_corpos~sample_nomads~random` game 1 at 23). 224 games hold 1,845 more decisions than
before (24,944 → 26,789), about eight Pass-only windows a game; the ordering-prompt count is
unchanged at 455.

**3. Revert confirmation.** `steps.py` stashed against the NEW golden: DIFFERENT on all 8 keys.

**4. Aggregate.**

| key | games | winner flips | end-reason | mean turn delta |
|---|---|---|---|---|
| sample_arasaka~sample_fixers~heuristic | 16/16 | 0 | 0 | +0.00 |
| sample_arasaka~sample_fixers~random | 40/40 | 0 | 0 | +0.00 |
| sample_corpos~sample_nomads~heuristic | 11/16 | 0 | 0 | +0.00 |
| sample_corpos~sample_nomads~random | 39/40 | 0 | 0 | +0.00 |
| sample_gangers~sample_netrunners~heuristic | 16/16 | 0 | 0 | +0.00 |
| sample_gangers~sample_netrunners~random | 40/40 | 0 | 0 | +0.00 |
| the_heist~embracing_power~heuristic | 16/16 | 0 | 0 | +0.00 |
| the_heist~embracing_power~random | 40/40 | 0 | 0 | +0.00 |

Every stream moves (a Pass inserted at every attack) and **nothing else does**: no winner, no
end reason, no turn count. That is the signature of a decision with one answer.

**5. Two-sided reachability.** Both digests moved, upward by the inserted Passes: `fuzz -n 300
--seed 1` (heuristic) `e8d0c4e2881afafea7962ebe` → `014fdb7214d1b2cd95fb49bc`, 43,390 → 48,449
actions; `fuzz -n 400 --seed 1 --agent random` `cefbabf3d4080dc639aad834` →
`b45f5d44a3ee37f69f860373`, 32,342 → 34,539. The delayed suite was re-derived and **all 72 positions still qualify** (the defensive position that the first version lost is back). The bootstrap sample was re-recorded.

---

## 2026-09-21 — Stage 0 E8 + E9: trigger ordering over every queue, and costs resolve after what they paid for (G2, engine-wide)

**The change.** Ruling 046's ordering now covers every queue its row said it must: the printed
ATTACK triggers of a Unit and its Gear together with the "attacks" hooks and spend triggers of the
same act (`steps.attack_triggers`); the printed DEFEATED triggers of a host and its Gear with the
"defeated" hooks and the dead card's own listener (`ops.defeat`); a card's PLAY or CALL trigger with
the "played"/"called" hooks **and the spend triggers of whatever paid for it** (`ops.settle_entry`);
and temporary listeners, which now carry the instance that registered them and the event kinds
they act on. `OrderTriggersStep` takes any `(inst, fn)` entries. Dispatch gains a ``deferring``
mode that collects a block's events instead of running them, which is also what E9 needed: an
activated ⊡ effect resolves before the spend triggers its cost raised, and a card is played (or a
Legend Called) before the spend triggers of what paid for it — *"After. Resolve the activated ⊡:
effect first"*, *"After. Play the card first then adjust the Gig"*. Reproduced red first (four
S0-E8 and two S0-E9 markers).

**What the measurement changed.** Building the groups exposed that 046's implementation counted a
hook as a pending trigger whenever it matched an event's *kind*: a Gear's "when its host is spent"
hook heard every spend, V Roamer's "when this Unit steals" hook heard every steal, and each such
no-op was offered for ordering against a real trigger. Groups of 5–14 entries appeared, and the
046 entry's own figure of **10.2 prompts per game (7.2% of decisions)** was mostly that. Every
`on_event` script now declares `wants(ctx, ev)` (`CardScript.wants`, read by `ops._matched`), so
only a trigger that would act is pending. On the new golden: **455 ordering prompts in 224 games,
2.03 per game, 1.82% of decisions** (attack 178, play 273, call 1, end-turn 2, spent 1), 406 of
them binary, the widest 5. The steal/spent/end-turn groups of the old golden (98/138/156) were
almost entirely inactive hooks.

**1. Prediction.** Every key. Observed: all 8.

**2. Localisation.** Two kinds of divergence, both expected. New prompts:
`the_heist~embracing_power~heuristic` game 0 diverges at decision 81 and the `random` key at 60 on
an `attack@order` (a spend-trigger Gear on an attacker with an ATTACK trigger). Removed prompts:
`sample_gangers~sample_netrunners~heuristic` game 0 at decision 39 and `random` at 88 are MAIN
menus where the old stream held a spurious 046 prompt; `sample_arasaka~sample_fixers~heuristic` at
55 a TARGET; `sample_corpos~sample_nomads~heuristic` game 3 at 93 a MAIN. The remaining two are
effect picks reached after an earlier shift. The board that raised 046 (two Gear on one attacker)
still asks: `test_046_the_controller_orders_their_own_simultaneous_triggers`.

**3. Revert confirmation.** `state.py`, `ops.py`, `steps.py`, `engine.py`, `effects.py`,
`registry.py` and `wnc.py` stashed against the NEW golden: DIFFERENT on all 8 keys.

**4. Aggregate.**

| key | games | winner flips | end-reason | mean turn delta |
|---|---|---|---|---|
| sample_arasaka~sample_fixers~heuristic | 13/16 | 0 | 1 | −0.15 |
| sample_arasaka~sample_fixers~random | 22/40 | 1 | 3 | +0.09 |
| sample_corpos~sample_nomads~heuristic | 5/16 | 0 | 0 | +0.00 |
| sample_corpos~sample_nomads~random | 24/40 | 3 | 3 | +0.00 |
| sample_gangers~sample_netrunners~heuristic | 16/16 | 3 | 2 | +0.00 |
| sample_gangers~sample_netrunners~random | 40/40 | 6 | 5 | +0.10 |
| the_heist~embracing_power~heuristic | 14/16 | 0 | 1 | −0.21 |
| the_heist~embracing_power~random | 35/40 | 13 | 6 | −0.14 |

Twenty-six winner flips in 224 games; the streams move in almost every game because inactive
prompts vanished and real ones appeared, but the outcomes barely do.

**5. Two-sided reachability.** Both digests moved, and *downward* in actions — the inverse of the
046 entry's signature, for the same reason: `fuzz -n 300 --seed 1` (heuristic)
`5c2396bc999e8eb6aa87cde5` → `e8d0c4e2881afafea7962ebe`, 45,456 → **43,390**; `fuzz -n 400
--seed 1 --agent random` `fa05c56621a1bd4484e71fef` → `cefbabf3d4080dc639aad834`, 33,886 →
**32,342**. Fewer decisions per game, each of them a real one.

**The delayed suite: 73 → 72.** Re-derived, **one position no longer qualifies**: `mined-23773-81`
(mined from heuristic self-play, horizon 1). Its exhaustive turn search hit the node cap without
finding the win — at the default 30,000 nodes and again at 300,000 (8 minutes) — so the result is
"unproven", not "lost": the turn's tree grew under the new ordering (a play paid with Legends can
now ask which trigger resolves first, and every such prompt is a branch). A position the solver
cannot re-prove has no verified line to score against, so it is removed rather than kept on an
old claim; the other 72 requalify. The committed bootstrap sample was re-recorded (its streams
moved with every key).

---

## 2026-09-21 — Stage 0 E7: Bootleg's sold card is nobody's to see (G0, no golden movement)

**The change.** A card sold from the deck without being looked at (Bootleg Black Sapphire Show;
FAQ: *"Do I reveal or get to look at the card I am selling? **No**"*) carries `F_FACEDOWN` in the
Eddies area. `view.knows_identity` answers No for both seats; `_hidden_groups` permutes it with the
owner's deck (owner's mask) and with the rival's hand+deck pool (rival's mask); `info_key` counts it
in the Eddies multiset without naming it and in the pool it belongs to; `learn.features` counts it
among the undrawn so every feature stays a function of the information set; the web view sends it
without a name. Reproduced red first (`test_bootleg_sells_the_top_card_unseen`).

**1. Prediction.** G0 — Bootleg is in no golden deck. **Observed: IDENTICAL**, as required.

**2–4.** Not applicable.

**5. Two-sided reachability.** Neither fuzz digest moved (`5c2396bc999e8eb6aa87cde5` /
`fa05c56621a1bd4484e71fef`, unchanged action counts) — and cannot: the fuzz hashes actions and
outcomes of perfect-information heuristic play, and no card and no agent reads the identity of a
card in an Eddies area (ruling 025's note). The change is to *information* — who may name the
card — and is reached by the scenario test and the determinization property tests
(`tests/props/test_determinization.py`, which pin `info_key` stable across sampled worlds), not by
outcomes. Stated here rather than pretending a digest moved.

**Also in this regeneration:** `data/experience/bootstrap-sample.jsonl.gz` re-recorded (same
command as its sidecar: 100 heuristic games, seed 1, then `compact`). Its stored action streams
stopped replaying after E5/E6 moved the golden — `test_the_committed_sample_still_replays` caught
it after E6 — and should have been re-recorded with those entries; it is re-recorded here, once,
and the delayed suite was re-derived (**all 73 positions still qualify**).

---

## 2026-09-21 — Stage 0 E6: "the first time … each turn" counts events, not a card's memory (G2)

**The change.** `GameState.turn_events` logs every dispatched event of the turn (cleared with the
turn, in `info_key`), and `EffectCtx.first_this_turn(pred, ev)` answers "is this the first event
this turn that satisfies pred" from it. The eight scripts that print the phrase use it instead of
a per-instance `once` key: Yorinobu Arasaka *Steel Dragon* and *Embracing Destruction*, Jackie
Welles *Pour One Out For Me* (the three the FAQ answers by name: a card that arrives mid-turn does
not get a fresh count), Johnny Silverhand, Rita Wheeler, Gorilla Arms, Rogue Amendiares and Viktor
Vektor *Drop Your Illusions* (the audit's open finding AUD-viktor-…-1, now green). `ops.defeat`
also hands the "defeated" event to the dead card's own listener, which is how Yorinobu counts
itself (FAQ). Reproduced red first (three S0-E6 markers, plus a new self-count test).

**1. Prediction.** By deck membership six keys (the three pairings holding Yorinobu ED, Jackie
POOFM, Rita or Rogue). **Observed: three** — `the_heist~embracing_power~heuristic`,
`sample_gangers~sample_netrunners~heuristic`, `sample_arasaka~sample_fixers~random`.

**2. Localisation.** Each window is the FAQ's own case. `sample_arasaka~sample_fixers~random`
game 17, decision 69: Goro (ARASAKA) attacks, *then* Yorinobu *Embracing Destruction* is Called,
then Goro *Hands Unclean* attacks — the old engine drew for the second ARASAKA attack, the new one
does not. `sample_gangers~sample_netrunners~heuristic` game 6, decision 61: Westbrook Netrunner
(Blue) is played, *then* Jackie *Pour One Out For Me* is Called, then Tetratronic Rippler (Blue
Gear) — the old engine offered Jackie's adjust, the new one does not. `the_heist~embracing_power~heuristic`
game 1, decision 47: V *Corporate Exile* goes solo (a Blue Unit played) with Jackie in the deck.

**3. Revert confirmation.** `state.py`, `steps.py`, `ops.py`, `view.py`, `effects.py` and `wnc.py`
stashed against the NEW golden: DIFFERENT on exactly the same three keys, at actions 47, 61, 69.

**4. Aggregate.**

| key | games | winner flips | end-reason | mean turn delta |
|---|---|---|---|---|
| sample_arasaka~sample_fixers~random | 1/40 | 0 | 0 | +0.00 |
| sample_gangers~sample_netrunners~heuristic | 1/16 | 0 | 0 | +0.00 |
| the_heist~embracing_power~heuristic | 2/16 | 0 | 0 | +0.00 |

Four games in 224, no winner or end-reason moved: the phrase only differs when a card arrives
between two matching events of one turn.

**5. Two-sided reachability.** Both digests moved: `fuzz -n 300 --seed 1` (heuristic)
`66bf558a9a8f2cf16af3427b` → `5c2396bc999e8eb6aa87cde5`, 45,451 → 45,456 actions; `fuzz -n 400
--seed 1 --agent random` `efecec525b2d5cf1e7e78897` → `fa05c56621a1bd4484e71fef`, 33,890 → 33,886.
The delayed suite was re-derived and **all 73 positions still qualify**.

---

## 2026-09-21 — Stage 0 E5: "friendly Legends" includes a Legend standing on the field (G1)

**The change.** `EffectCtx.all_legends` / `faceup_legends` read the Legends area **and** the field
(a solo'd or plainly-played Legend is a face-up Legend), and the six scripts that count or pick
friendly Legends use them: Synapse Burnout (FAQ: counts field Legends and counts itself), Zetatech
Berserk's discount, Panam Palmer *Strength Through Family*'s draw, MaxTac Squadron's ready, Pepe
Najarro's ready, and Goro Takemura *Losing His Way* — whose empty-area case the owner settled the
same day (ruling 042: a field Legend counts, and with none left there is nothing to be face-up, so
no bonus). Reproduced red first (four S0-E5 markers), and AUD-goro-takemura-losing-his-way-1's
vacuous reading is retired in favour of the settled one.

**1. Prediction.** By deck membership six keys may change (`sample_arasaka~sample_fixers` and
`the_heist~embracing_power` via Goro; `sample_corpos~sample_nomads` via Panam, Pepe and Synapse).
**Observed: the two `sample_corpos~sample_nomads` keys.** Goro's keys did not move: his condition
only differs when a Legend stands on the field, and in those decks' golden games he never attacks
with one there.

**2. Localisation.** `sample_corpos~sample_nomads~heuristic` game 1 diverges at decision 168 on
*"sample_nomads attacks with Panam Palmer — Strength Through Family"* (the draw now counts a
field Legend); the `random` key at decision 84 on *"attacks with Pepe Najarro — Working Doubles"*
immediately after *"Jackie Welles — Mama's Favorite is played to the field for its cost"* — a
spent field Legend Pepe may now ready.

**3. Revert confirmation.** `effects.py` and `wnc.py` stashed against the NEW golden: DIFFERENT on
exactly the same two keys, at actions 168 and 84.

**4. Aggregate.**

| key | games | winner flips | end-reason | mean turn delta |
|---|---|---|---|---|
| sample_corpos~sample_nomads~heuristic | 5/16 | 1 | 0 | +0.00 |
| sample_corpos~sample_nomads~random | 2/40 | 1 | 0 | +0.00 |

**5. Two-sided reachability.** Both digests moved: `fuzz -n 300 --seed 1` (heuristic)
`c9e5062374f3027ce660cbfb` → `66bf558a9a8f2cf16af3427b`, 45,441 → 45,451 actions; `fuzz -n 400
--seed 1 --agent random` `2e54e2c3c5448a6898b8cc0f` → `efecec525b2d5cf1e7e78897`, 33,880 → 33,890.
The delayed suite was re-derived and **all 73 positions still qualify**.

---

## 2026-09-21 — Stage 0 E4: Dying Night pays out after V died (G1, no golden movement)

**The change.** The ATTACK trigger of Dying Night on a host named "V" books the end-of-turn
"ready 2 Eddies" on the player through a listener that outlives the Gear, so the FAQ's case —
*"the Unit attacks but is defeated before the end of the turn, can I still ready 2 Eddies?
**Yes**"* — pays; a host that survives is paid once (a mark in `s.used` tells the end-of-turn hook
the listener owns it). Reproduced red first (`test_dying_night_readies_eddies_even_if_v_died`).

**1. Prediction.** Dying Night sits in `sample_corpos~sample_nomads` and `the_heist~embracing_power`
(four keys). **Observed: none.** The golden never has a V wearing Dying Night attack and die in the
same turn, and where V survives the listener pays exactly what the hook used to pay, at the same
point of the end-of-turn dispatch (listeners run after hooks, and no other end-of-turn hook of those
decks asks a question between them).

**2–4.** Not applicable: `bench.py check` IDENTICAL.

**5. Two-sided reachability.** Neither fuzz digest moved (`c9e5062374f3027ce660cbfb` /
`2e54e2c3c5448a6898b8cc0f`, unchanged action counts). Reached by its scenario test alone. The
delayed suite was re-derived and **all 73 positions still qualify**.

---

## 2026-09-21 — Stage 0 E3: "can't be blocked" fixed at declaration (G2, no golden movement)

**The change.** `AttackContext.unblockable` is set once in `engine._attack` and read by
`legal.reaction_menu`, instead of the menu re-evaluating the attacker's `unblockable(ctx)` each time
it is built. MTOD12 Flathead is the only card with the hook and its condition is Street Cred, so
the FAQ's case — *"triggered effects or reactions make my Rival's Street Cred lower than mine, can
my Rival then block? **No**"* — is exactly a Flathead whose ATTACK trigger (Dying Night, here)
moved a Gig. The field is in `view._atk_key`. Reproduced red first
(`test_flathead_stays_unblockable_when_cred_flips_after_declaration`).

**1. Prediction.** `core/**`, so every key in principle; by deck membership Flathead is only in
`the_heist~embracing_power`. **Observed: none** — the golden never has a Flathead's cred flip inside
its own attack.

**2–4.** Not applicable: `bench.py check` IDENTICAL.

**5. Two-sided reachability.** Neither fuzz digest moved (`c9e5062374f3027ce660cbfb` /
`2e54e2c3c5448a6898b8cc0f`, unchanged action counts), re-run on the clean E3 tree after a
sequencing slip (see `docs/stage0_decisions.md`). Reached by its scenario test alone. The delayed
suite was re-derived and **all 73 positions still qualify**.

---

## 2026-09-21 — Stage 0 E2: Take Control reaches effect steals (G1, no golden movement)

**The change.** `ops.steal_reduction` — the sum of "steals 1 fewer" modifiers on a Unit — is now
read by Appetite for Destruction's and Gorilla Arms's bonus steals as well as by the attack path,
per the FAQ (*"Does this apply to Units stealing Gigs through effects outside of attacking?
**Yes**"*). Reproduced red first (`test_take_control_applies_to_an_effect_steal`).

**1. Prediction.** Appetite for Destruction sits in `sample_gangers~sample_netrunners`; Take Control
and Gorilla Arms are in no golden deck. Two keys may change. **Observed: none.** For a key to move,
Take Control and an effect steal by the same Unit have to land in one game, and the golden decks
never hold both.

**2–4.** Not applicable: `bench.py check` IDENTICAL, so there is no divergence to localise, no
revert to confirm and no aggregate.

**5. Two-sided reachability.** Neither fuzz digest moved (`c9e5062374f3027ce660cbfb` /
`2e54e2c3c5448a6898b8cc0f`, unchanged action counts): 700 random-deck games did not produce a
Take-Controlled Unit making an effect steal either. The change is reached by its scenario test
alone, which is stated here rather than hidden. The delayed suite was re-derived on the E2 tree and
**all 73 positions still qualify**.

---

## 2026-09-21 — Stage 0 E1: three FAQ answers on Sketchy Ripper, Misty and El Sombrerón (G1)

**The change.** Three scripts brought to the published FAQ, each answered there by name.
Sketchy Ripper's search takes zero or one Gear (`lo=0`): *"can I choose not to reveal any cards
and bottom-deck them all even if there's a Gear among them? **Yes**"* — reversing
AUD-sketchy-ripper-1, which had read the clause as mandatory before the FAQ existed. Misty
Olszewski offers **Legend** as a fourth card type (*"Can I choose 'Legends' for this effect?
**Yes**"*): it always misses, since Legends never sit in a deck, but it is the player's to choose.
El Sombrerón offers the 2 €$ whether or not a max Gig exists (*"Yes, but El Sombrerón won't gain
any power from it"*) and, with several max Gigs, asks which one (*"can I choose which one El
Sombrerón's effect uses? **Yes**"*) instead of taking the largest. Reproduced red first in
`tests/rules/test_stage0_engine.py` (four S0-E1 markers, now removed).

**1. Prediction.** `golden_impact.py predict` from deck membership: Sketchy Ripper sits in
`sample_arasaka~sample_fixers`, El Sombrerón in `sample_gangers~sample_netrunners`, Misty in no
golden deck. Four keys may change. Observed: exactly those four.

**2. Localisation.** Every window has the named card at the divergence itself:
`sample_arasaka~sample_fixers~heuristic` game 2 diverges at decision 120 on *"attacks with Sketchy
Ripper → targeting the Gig area"* (the new decline option), the `random` key at decision 61 on the
same line; `sample_gangers~sample_netrunners~heuristic` game 4 at decision 195 on *"attacks with
El Sombrerón ... declines"* (the pay is now offered without a max Gig), the `random` key at
decision 114 on an El Sombrerón attack into Westbrook Netrunner.

**3. Revert confirmation.** `wnc.py` stashed against the NEW golden: DIFFERENT on exactly the same
four keys, at actions 195, 114, 120 and 61.

**4. Aggregate.**

| key | games | winner flips | end-reason | mean turn delta |
|---|---|---|---|---|
| sample_arasaka~sample_fixers~heuristic | 5/16 | 0 | 0 | +0.00 |
| sample_arasaka~sample_fixers~random | 12/40 | 2 | 3 | −0.17 |
| sample_gangers~sample_netrunners~heuristic | 5/16 | 0 | 0 | +0.00 |
| sample_gangers~sample_netrunners~random | 1/40 | 0 | 0 | +0.00 |

Small and one-sided, as a new decline option should be: the heuristic games differ in action
indices only (the menu grew), with no winner or end-reason moving.

**5. Two-sided reachability.** `fuzz -n 300 --seed 1` (heuristic)
`590b01a340045483d5445fa9` → `c9e5062374f3027ce660cbfb`, 45,488 → 45,441 actions. `fuzz -n 400
--seed 1 --agent random` did **not** move (`2e54e2c3c5448a6898b8cc0f`, 33,880 actions, measured
twice before the change and once after): 400 random games over the whole pool did not reach a
Sketchy Ripper search with a Gear in the top three, a Misty end of turn, or an El Sombrerón attack
with 2 €$ up. Misty is in no golden deck; her change is reached by the heuristic fuzz and by
`test_misty_may_name_legend`. Note the random baseline recorded here differs from the one the 046
entry wrote (`a70eb43f…`, 33,954): the measurement was re-taken on the committed `750c723` tree
and is stable across runs, so that entry's figure came from a working tree that was not the commit.

The delayed suite was re-derived and **all 73 positions still qualify** (2m25s).

---

## 2026-09-20 — ruling 046, the controller orders their own triggers (G2, a new decision point)

**The change.** Two of a player's cards triggering on one event now resolve in the order that
player chooses. `steps.OrderTriggersStep` asks, resolves exactly one, and re-pushes with the
remainder — the shape `ReactionWindowStep` uses — on the existing `Pick` action, so
`action_feature_digest()` is unmoved and fitted policy heads still load. `ops.dispatch` keeps
calling hooks inline where there is no choice to make, which is most events and is what keeps
dispatch cheap.

**The restriction is the part worth reading, and it is measured rather than argued.** Over 287,247
dispatched events across 240 golden-deck games, 4.8% matched two or more of one player's hooks —
but a third of those were two or three copies of the *same card*: Rita Wheeler beside Rita Wheeler,
Meredith Stout beside Meredith Stout. Ordering two identical effects is a choice whose branches
cannot be told apart. Asking would have put a meaningless prompt in front of the player thousands
of times and handed the search a branching factor it pays for and learns nothing from. Requiring
two **distinct** cards takes it to 3.2%, and every one of those is a real decision. In play:
**10.2 prompts per game, 7.2% of decisions**, 607 of 815 of them binary, the widest five options.

The FAQ is also explicit about what this does *not* cover, and the step does not overreach: a
trigger meeting an **activated** ⊡ effect is ordered ("After. Resolve the activated effect first"),
as is one meeting a cost being paid ("After. Play the card first"). Only triggers that land
together are a choice. Across players there is none either — the turn player's resolve first, which
is the order `act[6][s.active]` already has.

**The one behaviour change beyond the ordering**, stated plainly: a group that moves to the step
runs as a step rather than inside the caller's remaining code. It is confined to the 3.2%, and it
is arguably the more correct sequencing — the rules put a trigger in a pending queue that resolves
after the current effect finishes.

**1. Prediction.** Every key. Observed: all 8.

**2. Localisation.** `steal` and `spent` were the two commonest ordering sites in the measurement
(5,058 and 3,879), and the windows match: `sample_arasaka~sample_fixers~heuristic` diverges at
decision 55 three lines after a Gig-area attack and a steal; the `random` key at 81, likewise on a
steal. The board that raised the ruling in the first place — two Gear on one Unit, both triggering
when the host is spent — is pinned as a test rather than left to the golden:
`test_046_the_controller_orders_their_own_simultaneous_triggers`.

**3. Revert confirmation.** `ops.py` and `steps.py` restored against the NEW golden: DIFFERENT on
all 8 keys, at actions 39, 55, 66, 81, 82, 86, 88 and 93.

**4. Aggregate.**

| key | games | winner flips | end-reason | mean turn delta |
|---|---|---|---|---|
| sample_arasaka~sample_fixers~heuristic | 7/16 | 0 | 1 | +0.29 |
| sample_arasaka~sample_fixers~random | 10/40 | 0 | 1 | +0.20 |
| sample_corpos~sample_nomads~heuristic | 5/16 | 0 | 0 | +0.00 |
| sample_corpos~sample_nomads~random | 17/40 | 1 | 1 | +0.24 |
| sample_gangers~sample_netrunners~heuristic | 16/16 | 0 | 3 | +0.06 |
| sample_gangers~sample_netrunners~random | 40/40 | 9 | 6 | −0.07 |
| the_heist~embracing_power~heuristic | 5/16 | 0 | 0 | +0.00 |
| the_heist~embracing_power~random | 16/40 | 3 | 4 | −0.75 |

Smaller than 027 or 047 and for a clear reason: this adds a decision only where two distinct
triggers actually land together, so a key moves in proportion to how often its decks do that.
`sample_gangers~sample_netrunners` moves in every game — it is the pairing holding Evelyn Parker
beside Rogue Amendiares, the commonest pair in the measurement at 3,322 occurrences — and
`sample_corpos~sample_nomads~heuristic` in five of sixteen. Thirteen winner flips over 224 games.

**5. Two-sided reachability.** Both instruments move, and upward, which is the signature of a new
decision rather than a changed outcome. `fuzz -n 300 --seed 1` (heuristic)
`c5be361c42116422b76a6cce` → `590b01a340045483d5445fa9`, 43,176 → **45,488** actions; `fuzz -n 400
--seed 1 --agent random` `907adf81e67f6ff1b096e61d` → `a70eb43fb4524c97167d14b8`, 32,179 →
**33,954**. Those +2,312 and +1,775 actions are the ordering prompts themselves.

The delayed suite was re-derived and **all 73 positions still qualify**.

---

## 2026-09-20 — ruling 047, a second way onto the field (G2, engine-wide)

**The change.** A face-up Legend with a numeric cost can be played to the field **without** using
GO SOLO. The FAQ: *"Can I play a Legend to the field from the Legends area without using GO SOLO?
**Yes**, as long as the Legend has a numeric cost value… It enters the field **with lag**, and **in
the same orientation** it was in the Legends area."* All 8 costed Legends in the set carry GO SOLO,
so this is a second choice on eight cards, not a new card becoming playable.

**Not a new Action class.** `learn.policy.KINDS` is a tuple of Action *classes* that `_SPEC`
one-hots over, so `PlayLegend` would move `action_feature_digest()` and every fitted policy head
would be refused on load — the same hazard ruling 046 flagged. `GoSolo` gains a
`keyword: bool = True` field instead. Measured before and after the edit: `2ea962c9a03712d4` both
times.

The keyword's permission to attack through Lag needed its own flag, and that is the part worth
recording. `attack_permission` granted it on `has_keyword(GO_SOLO)`, and the card still *prints*
GO SOLO whichever way it was played — so the keyword alone cannot tell the two plays apart, and the
plain play would have silently kept the benefit the FAQ withholds from it. `F_NO_SOLO_KEYWORD` is
set only by the keyword-less play. `F_GO_SOLO` stays on both, because it means "a Legend standing
on the field" and is what sends it out of the game when it leaves (CR 4.4.1).

**1. Prediction.** Every key. A second option on every costed face-up Legend, on every turn one is
face-up, renumbers every action index after it in any game where that happens — and a Legend is
Called in most games. Observed: all 8.

**2. Localisation.** The narration names the new play in as many words: *"… played to the field for
its cost, lagged"*. It is reached: over 160 random games across the eight golden matchups, the new
action was taken **32 times** — a play that could not be made at all on the previous build.
Divergences land at decisions 29 to 55, which is the first turn a Legend is face-up in each key.

**3. Revert confirmation.** `actions.py`, `legal.py` and `engine.py` restored against the NEW
golden: DIFFERENT on all 8 keys, at actions 29, 29, 31, 31, 40, 41, 45 and 55.

**4. Aggregate.**

| key | games | winner flips | end-reason | mean turn delta |
|---|---|---|---|---|
| sample_arasaka~sample_fixers~heuristic | 12/16 | 0 | 0 | +0.00 |
| sample_arasaka~sample_fixers~random | 31/40 | 5 | 2 | +0.00 |
| sample_corpos~sample_nomads~heuristic | 16/16 | 0 | 0 | +0.00 |
| sample_corpos~sample_nomads~random | 39/40 | 8 | 6 | +0.18 |
| sample_gangers~sample_netrunners~heuristic | 15/16 | 0 | 0 | +0.00 |
| sample_gangers~sample_netrunners~random | 24/40 | 6 | 6 | +0.04 |
| the_heist~embracing_power~heuristic | 15/16 | 0 | 0 | +0.00 |
| the_heist~embracing_power~random | 40/40 | 17 | 13 | +0.30 |

The shape is the telling part and it is not the same as 027's. **Zero winner flips in all four
heuristic keys**, 36 in the random ones. The frozen heuristic scores a ply deep and the new play is
strictly worse than GO SOLO on the turn you make it — lagged, cannot attack, same cost — so the
greedy agent sees the extra option, never takes it, and its games diverge only by renumbering.
Random takes it about one time in five that it is offered, and that is where the flips are. An
option a one-ply agent correctly refuses is exactly what the delayed-reward suite exists to
measure, and a reminder that these numbers are conditional on that opponent.

**5. Two-sided reachability.** Both instruments move. `fuzz -n 300 --seed 1` (heuristic)
`9ee8e3cc046f0c1af07847fd` → `c5be361c42116422b76a6cce`, 43,182 → 43,176 actions; `fuzz -n 400
--seed 1 --agent random` `d711b635731a993f789bc554` → `907adf81e67f6ff1b096e61d`, 32,517 → 32,179.
The random drop of 338 actions is the new play being taken: it ends a Legend's turn sooner than GO
SOLO does, since the arrival cannot attack.

The delayed suite was re-derived and **all 73 positions still qualify**.

---

## 2026-09-20 — ruling 044, a solo'd Legend is a Unit (six scripts, seven findings)

**The fix.** Six card scripts decided Unit-hood by ``CardDef.type``, which excludes a Legend
standing on the field through GO SOLO; forty-eight asked by zone, which includes it. The FAQ
settles it and settles it *inclusively* — *"When a Legend uses GO SOLO is it still a Legend?
**Yes**"*, and Synapse Burnout's answer calls the same card "now also a Unit" — so zone is the
right side and the six were the defect. `EffectCtx.is_unit` is now the one way to ask.

Seven strict-xfail findings go green with it, and their deleted markers are the record:
`AUD-saburo-arasaka-stubborn-patriarch-1`, `AUD-6th-street-recruits-1`,
`AUD-satori-sword-of-saburo-1`, `AUD-river-ward-detective-on-the-hunt-1`,
`AUD-jackie-welles-mamas-favorite-1` and `-2`, `AUD-jackie-welles-pour-one-out-for-me-1`.

**One of the six could not be fixed the same way, and that is the interesting part.** River Ward
*Detective on the Hunt* listens for `("defeated", ...)`, and by the time that fires `ops.defeat`
has already moved the card out of the field **and** `move` has cleared `F_GO_SOLO`, the flag that
recorded it was standing there. So there is neither a zone nor a flag left to read: a zone test
would answer No for every card including an ordinary Unit, and the printed-type test it replaced
answered No for exactly the case the FAQ says is Yes. `defeat` now answers the question itself,
before the move, and carries it as the event's fifth element. The field is appended, so every
existing listener indexes as it did.

A second thing the fix exposed: `tests/conftest.board` and `learn.delayed.build_position` were
placing a Legend in the FIELD area without `F_GO_SOLO`, which is a board no game can reach — it is
the flag that sends such a Legend out of the game rather than to the trash. Both set it now, and
River Ward's test passes for the right reason rather than by accident.

**1. Prediction.** Tier G1 by cards, all 8 keys: `sample_arasaka` holds Saburo and Satori,
`sample_corpos` holds Jackie *Mama's Favorite*, `sample_gangers` and `the_heist` hold Jackie *Pour
One Out For Me*. (The change also touches `core/**` — `ops.defeat`'s event field and the new
`EffectCtx.is_unit` — but both are additive and neither alters a game on its own, which step 3
below is the evidence for.) Observed: 5, all predicted, nothing outside.

**2. Localisation.** `sample_arasaka~sample_fixers~random` game 2 diverges at decision 89, and the
window says it outright: *"Goro Takemura — Hands Unclean GOES SOLO onto the field … attacks with
Goro Takemura … steals a d4 showing 4 … steals a d8 showing 3"* — a solo'd ARASAKA Legend
attacking, which is precisely the card Saburo's aura now reaches, and two stolen dice is what the
+1 power buys at the `steal_count` boundary. `sample_corpos~sample_nomads~heuristic` game 1 shows
*"attacks with Jackie Welles — Mama's Favorite"* from the field. The other three keys diverge at
decisions 66, 73 and 87, with a named card first a legal option 62 to 93 decisions earlier.

**3. Revert confirmation.** The six script hunks reverted against the new golden, leaving the two
`core/**` edits in place: DIFFERENT on exactly those 5 keys, at exactly actions 66, 73, 87, 89 and
101. That is also the evidence that the engine edits move nothing on their own.

**4. Aggregate.**

| key | games | winner flips | end-reason | mean turn delta |
|---|---|---|---|---|
| sample_arasaka~sample_fixers~heuristic | 7/16 | 0 | 2 | +0.00 |
| sample_arasaka~sample_fixers~random | 2/40 | 0 | 1 | −1.00 |
| sample_corpos~sample_nomads~heuristic | 9/16 | 1 | 0 | +0.00 |
| the_heist~embracing_power~heuristic | 14/16 | 0 | 0 | +0.00 |
| the_heist~embracing_power~random | 21/40 | 4 | 6 | −0.05 |

Five winner flips over 224 games and turn deltas at or near zero: these are the same games, played
slightly differently in the ones where a Legend stood on the field. Three keys did not move at all,
which at G1 is ordinary — the cards are in those decks and never mattered. The contrast with the
027 entry above (223 of 224 games, 55 flips) is the difference between a rule that adds an option
to every menu and a rule that changes what six cards do when a particular board arises.

**5. Two-sided reachability.** Both instruments move. `fuzz -n 300 --seed 1` (heuristic)
`0c0b5c1f7e32e9b8d652742c` → `9ee8e3cc046f0c1af07847fd`, 43,261 → 43,182 actions; `fuzz -n 400
--seed 1 --agent random` `9fabde15ecca34ffd589536d` → `d711b635731a993f789bc554`, 32,549 → 32,517.
Crash-free, 150 of 151 cards reached.

The delayed suite was re-derived and **all 73 positions still qualify** — unlike ruling 027, which
dissolved six. The committed experience sample and the demo replay were re-recorded again: their
action streams are indices, and six cards asking a different question changes what those indices
mean.

---

## 2026-09-20 — ruling 027, a Legend may spend itself toward its own cost (G2, engine-wide)

**The change.** `exclude=` dropped from the three *playing* `pay()` sites (CallLegend in the main
menu and in a reaction, and `go_solo`) and from the two menu subtractions that mirrored it in
`legal.py`; and a solo'd Legend now arrives ready. `engine.activate` keeps its exclusion, which is
a different rule. Settled by the FAQ, not by argument: *"Can I spend a Legend for an Eddie when
playing it with it's own GO SOLO? **Yes**"*.

The first G2 entry in this ledger where the change is not attributable to any card — the closest
precedent is Mox Inciters, recorded as "G2 by file and unlocalisable by construction: a card script
cannot remove an option from a menu the engine builds". That entry had no instrument. This one does:
`golden_impact.py --engine`, added with the fix.

**1. Prediction, written before the change.** Every key. Deck membership predicts nothing here,
because the change is not about a card: every golden deck brings three Legends, and `main_menu` now
compares each one's cost against a total it is no longer subtracted from, on every turn of every
game. So the hard stop inverts — a key that did **not** move would be the thing needing an
explanation. Observed: all 8, and every game inside them bar one.

**2. Localisation.** The window for `sample_arasaka~sample_fixers~heuristic` (diverges at decision
6) shows the change outright, three lines in: *"sample_fixers (seat 1) Calls a Legend by spending 1
Legend"* — turn one, no Eddies on the table, a face-down Legend paying for its own Call. That line
could not occur on the previous build at all. The other seven keys diverge at decisions 4 to 16,
which is the first turn in each: a Legend is on the table from the start, so the menu differs from
the first main phase, and an added option renumbers every index after it.

**3. Revert confirmation.** `engine.py` and `legal.py` restored to their pre-027 state against the
NEW golden: DIFFERENT on all 8 keys, at actions 4, 4, 4, 4, 5, 6, 4, 16. The regeneration was taken
on a tree carrying only the intended change.

**4. Aggregate.**

| key | games | winner flips | end-reason | mean turn delta |
|---|---|---|---|---|
| sample_arasaka~sample_fixers~heuristic | 16/16 | 4 | 5 | +0.00 |
| sample_arasaka~sample_fixers~random | 40/40 | 11 | 11 | −0.53 |
| sample_corpos~sample_nomads~heuristic | 16/16 | 3 | 5 | +0.12 |
| sample_corpos~sample_nomads~random | 40/40 | 12 | 4 | +0.10 |
| sample_gangers~sample_netrunners~heuristic | 16/16 | 0 | 4 | +0.31 |
| sample_gangers~sample_netrunners~random | 39/40 | 8 | 12 | −0.18 |
| the_heist~embracing_power~heuristic | 16/16 | 8 | 4 | −0.50 |
| the_heist~embracing_power~random | 40/40 | 17 | 13 | −0.10 |

Much the largest regeneration in this ledger, past even Mox Inciters, and the size is the point.
This is not a card behaving differently in the games that play it; it is one more legal move
available to both seats on most turns of every game. 223 of 224 games moving is the expected shape,
and the turn deltas — all inside half a turn — say the games are otherwise the same games. The one
unmoved game is worth naming rather than rounding away: `sample_gangers~sample_netrunners~random`
has a single game in which neither seat ever reached a position where the extra €$ was the
difference.

**5. Two-sided reachability.** Both instruments move. `fuzz -n 300 --seed 1` (heuristic)
`2d3fa49cdabadbdb3b6fa1cd` → `0c0b5c1f7e32e9b8d652742c`, 42,668 → 43,261 actions; `fuzz -n 400
--seed 1 --agent random` `e5b6084fdeaa99c52fe15ff6` → `9fabde15ecca34ffd589536d`, 32,596 → 32,549.
Both crash-free, 150 of 151 cards reached.

**What it cost outside the golden**, recorded here because the golden is not the only frozen thing a
rules change invalidates: six of the 79 delayed-reward positions stopped qualifying (two are now
solved outright by the frozen heuristic — `sell-to-afford-go-solo` is "sell a card to afford the GO
SOLO", and the Legend now affords itself — three push random play over the 25% floor, and one lost
its winning line because the *rival* gained the same option), the committed experience sample and
the demo replay were re-recorded, and two tests were repaired. The commit before this one has the
detail. The ruleset digest did **not** move, deliberately: see `docs/rulings.md` row 027.

---

## 2026-09-14 — `unlikely-bond` (AUD-unlikely-bond-1)

**The fix.** "Bottom-deck a ready friendly Unit. If you do, bottom-deck a spent rival Unit." The
friendly bottom-deck was scripted `optional=True`, manufacturing a decline the card never grants.
Verified first: the blind reader landed on the same clause in the same direction, and the kill
attempt failed on all five routes.

**1. Prediction, written before the change.** `golden_impact.py predict unlikely-bond` → tier G1,
two keys, `sample_gangers~sample_netrunners~{heuristic,random}`. Only `sample_gangers` runs the card
and it runs three copies. Observed: exactly those two keys. Nothing outside the prediction moved.

**2. Localisation.** In the heuristic key the game diverges at decision 138; the card first became a
legal option at decision 130. In the random key, decision 29 against 28 — and there the card is
visibly played in the narration one line before.

This is the entry that corrected the protocol. The rule used to be "the fixed card must appear in
the replay window", and in the heuristic game it never appears: Unlikely Bond was drawn, sat in
hand, and was never cast. The frozen heuristic scores candidate actions by resolving them a ply
deep, so a card that is merely *playable* changes what the agent thinks the board is worth. The rule
is now "a named card must have been an option before the divergence", which is the claim the
evidence can actually support.

It also corrected the instrument. `golden_impact.py` narrated the window by replaying the golden
action indices on the fixed engine, which is unsound: an action index names a position in an option
list, not a move, so removing an option — or removing a whole decision, as dropping `optional=True`
does when `AskStep` then resolves a one-option choice inline — makes every later index mean
something else. The replay kept succeeding and narrated a game that never happened. It now narrates
the game the current engine actually plays.

**3. Revert confirmation.** Script hunk reverted, new golden kept: `check` went DIFFERENT on exactly
those two keys and no others, at exactly actions 138 and 29. The regeneration was taken on a tree
carrying only the intended change.

**4. Aggregate.** heuristic 10/16 games changed, 3 winner flips, 2 end-reason changes, mean turn
delta +0.10. random 1/40 changed, 1 winner flip, mean turn delta −3.00. A three-of Program in one of
the two decks, played by an agent that previews it: a third of the heuristic games touched and
almost none of the random ones is the expected shape, since random rarely assembles the board the
card wants.

**5. Two-sided reachability.** Not applicable at G1 — the golden sees this card directly. (The fuzz
check exists for the 54 cards no golden deck contains.)

---

## 2026-09-14 — `shattered-memories` (AUD-shattered-memories-1)

**The fix.** "Each player discards their hand and **may** draw 5." The script drew for both players
unconditionally, with a comment reading `# "may draw 5": always beneficial, auto`. It is not always
beneficial: `ops.draw` ends the game on an empty deck, so the Program could deck a player out
against their will — and the Rival's "may" is the Rival's to spend, not the controller's to assume.
Both players are now asked. `EffectCtx.maybe` gains the same `after=` hook `adjust_up_to`,
`choose_gig` and `spend_one` have, so the third sentence ("If the total number of discarded cards
equals the value of a friendly Gig, draw 2") is sequenced after both answers without being made
conditional on either.

**1. Prediction.** Tier G1, two keys, `the_heist~embracing_power~{heuristic,random}`. Observed:
exactly those two.

**2. Localisation.** heuristic diverges at decision 17, card first a legal option at 15. random
diverges at 26, first an option at 11.

**3. Revert confirmation.** Script hunk reverted, new golden kept: DIFFERENT on exactly those two
keys, at exactly actions 17 and 26.

**4. Aggregate.** heuristic 9/16 games, 1 winner flip, 1 end-reason change, mean turn delta −0.22.
random 8/40, 2 flips, 2 end-reason changes, −0.62. Turning one unconditional draw into two
questions changes the decision count in every game that plays the card, so a majority of the
heuristic games moving is expected; the small turn deltas say the games are otherwise the same
games.

**5. Two-sided reachability.** Not applicable at G1.

`EffectCtx.maybe` also changed, which is a `core/**` edit and so G2 by the letter of the tier table.
It is additive — no existing caller passes `after` — and the revert in step 3 reverted only the card
hunk, leaving the engine change in place; `check` went DIFFERENT on the two card keys and nothing
else, which is the evidence that the engine change on its own moves nothing.

---

## 2026-09-14 — `peace-offering` (AUD-peace-offering-1)

**The fix.** "You may set a Gig's value to the value of another Gig. **Then, if you control a
value-pair, draw 1.**" The draw was nested inside the set's continuation, so declining the "may" —
or having no second Gig to copy from — skipped a sentence that is about the board rather than about
the set.

**The interesting part is what the first attempt got wrong.** Hanging the tail off the outer
prompt's `after=` hook looked right and produced a passing decline test and a *failing* take test:
with the set taken, no draw happened. `after` runs the moment `cont` returns, and a continuation
returns as soon as it asks a further question — asking pushes a step and comes straight back. Peace
Offering's set is two nested questions, so `after` fired before the die had moved and found no pair.

`after` is therefore for a continuation that finishes synchronously; where `cont` opens another
prompt, the tail belongs on *that* prompt. `choose_gig` gains `otherwise=` for exactly this — the
paths where `cont` did not run — and the limitation is now written into `adjust_up_to`'s docstring,
with this card named as the worked example. The three earlier `after=` uses were re-checked and are
all synchronous continuations.

**1. Prediction.** Tier G1, two keys. Observed: one of them, `sample_corpos~sample_nomads~random`.
**2. Localisation.** Diverges at decision 37; card first a legal option at 34. The narration shows
it directly: "plays Peace Offering ... declines ... draws a card".
**3. Revert confirmation.** DIFFERENT on exactly that one key at exactly action 37.
**4. Aggregate.** 1 of 40 games, 1 winner flip, 1 end-reason change, mean turn delta −1.00. The
heuristic key did not move at all, which fits: this changes the game only when the set is declined
or impossible, and the heuristic takes it whenever it is offered.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `trust-no-one` (AUD-trust-no-one-1)

**The fix.** "Decrease a Gig by up to 3. **Then, if you control a min Gig, draw 1.**" The draw hung
off `cont`, so a declined "up to 3" — or a Gig already on its minimum face, which cannot be
decreased at all under ruling 037 — skipped it. Moved to `after=`, which is safe here because this
continuation finishes synchronously.

**1. Prediction.** Tier G1, four keys. Observed: two of them, both `random`.
**2. Localisation.** decisions 29 and 12, with the card first a legal option at 4 and earlier.
**3. Revert confirmation.** DIFFERENT on exactly those two keys, at exactly actions 29 and 12.
**4. Aggregate.** 1 of 40 and 3 of 40 games, two winner flips, two end-reason changes. Both
heuristic keys unmoved: the heuristic takes a decrease whenever one is legal, so the changed path —
declined or impossible — is one only random play reaches.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `industrial-assembly` (AUD-industrial-assembly-1)

**The fix.** "Increase a Gig by up to 4. **If you control a Gig with 8+ value, draw 1.**" Same shape
as Trust No One and sharper in one respect: a d10 already showing 10 cannot be raised at all
(ruling 037), so the engine asks nothing and the continuation is never scheduled — and that d10 is
exactly the 8+ Gig the second sentence is asking about.

**1. Prediction.** Tier G1, four keys. Observed: two, both `random`.
**2. Localisation.** decisions 16 and 27, card first a legal option at 4 and earlier.
**3. Revert confirmation.** DIFFERENT on exactly those two keys at exactly those actions.
**4. Aggregate.** 3 of 40 and 1 of 40, no winner flips, one end-reason change. Both heuristic keys
unmoved, same reason as Trust No One: the heuristic takes an increase whenever one is legal.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `afterparty-at-lizzies` (AUD-afterparty-at-lizzies-1)

**The fix.** "Adjust a Gig by up to 1. **If you control 2 or more Gigs with different values, draw
1.**" Two Gigs showing 3 and 4 are two Gigs with different values whether or not a die moved, and
"up to 1" includes zero — the engine offers the decline explicitly. Moved to `after=`.

**1. Prediction.** Four keys. Observed: two, both `random`.
**2. Localisation.** decisions 47 and 25, card first a legal option at 4 and earlier.
**3. Revert confirmation.** DIFFERENT on exactly those two keys at exactly those actions.
**4. Aggregate.** 4 of 40 and 1 of 40, one winner flip, no end-reason changes, turn deltas +0.25 and
0.00. Both heuristic keys unmoved.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `el-sombreron-la-venganza-lenta` (AUD-el-sombreron-la-venganza-lenta-1)

**The fix.** "ATTACK: You may pay 2 €$. If you do, this Unit gains power equal to a friendly **max
Gig** this turn." A max Gig is a die showing its maximum face — the mirror of "min Gig", which six
cards in this set use and which `EffectCtx.min_gigs` implements exactly that way. The script used
`max(gig_values())`, the largest *value* in the area, so a d12 on 9 beside a d4 on 4 gave +9 where
the card gives +4. `EffectCtx.max_gigs` already existed and was unused.

A pre-existing green test encoded the bug — a d12 on 9 expecting +9 — which is why no one noticed.
It now uses a real max Gig, and a control beside it shows the card does not even ask when there is
none.

**1. Prediction.** Two keys. Observed: both.
**2. Localisation.** decisions 146 and 62; the card first a legal option at 80 and earlier, and the
narration shows it attacking one line before.
**3. Revert confirmation.** DIFFERENT on exactly those two keys at exactly those actions.
**4. Aggregate.** 3 of 16 and 1 of 40 games, no winner flips, no end-reason changes, turn deltas
0.00. A pure power-number change on one Unit in one deck: the games stay the same games.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `sketchy-ripper` (AUD-sketchy-ripper-1)

**The fix.** "ATTACK: Search the top 3 cards of your deck. **Reveal a Gear and add it to your
hand.** Bottom-deck the rest." No "may", and Sasha Yakovleva's identical verb phrase is already
scripted as mandatory. The search ran with a lower bound of zero, so the engine offered a decline.
`lo=1` is safe with no Gear in the top three: `choose_many` clamps hi to the candidates available
and then lo to hi, so the search resolves with an empty pick and still bottom-decks all three — a
control test pins that.

A pre-existing green test answered the Pick that only existed because of the bug. It now asserts
that nothing is asked, which is the printed behaviour.

**1. Prediction.** Two keys. Observed: both.
**2. Localisation.** decisions 114 and 82; card first a legal option at 41 and earlier.
**3. Revert confirmation.** DIFFERENT on exactly those two keys at exactly those actions.
**4. Aggregate.** 4 of 16 and 13 of 40 games, two winner flips, three end-reason changes, turn
deltas 0.00 and +0.54. A third of the random games is a large share and an expected one: removing a
decision from an ATTACK trigger shifts every index after it in any game where the Unit attacks, and
random attacks with it often.
**5. Two-sided reachability.** Not applicable at G1.

---

## 2026-09-14 — `zetatech-faceplate` (AUD-zetatech-faceplate-1) — the last of the six

**The fix.** "When this Unit or Legend is spent, adjust a Gig by up to 1. **Then, if you control 3
or more Gigs with different values, draw 1.**" The sixth and last card written with its tail clause
inside the first clause's continuation. `tests/cards/test_script_lints.py::test_a_state_based_tail_clause_is_not_trapped_in_a_continuation`
goes green with this one, which is what the whole detector was for.

**The lint needed teaching first.** It flagged Peace Offering after that card was fixed, because
Peace Offering's tail *has* to live inside a continuation — its set is two nested questions, so the
tail belongs on the inner one. The lint now distinguishes the slot a continuation is passed into:
`cont=`/`then=` run only if the prompt was answered, `after=`/`otherwise=` run whatever happens. A
clause in the second kind is sequenced, not trapped.

**The test needed strengthening too**, and this is the sharper lesson. Its first assertion said the
Gig area was unchanged — but the attack that spends the host also *steals*, so the test had been
failing on the steal rather than on the missing draw. A strict xfail proves a test fails; it does
not prove it fails for the reason in its reason string. The board now attacks a spent rival Unit
instead, and the test fails, and now passes, for the clause it names.

**1. Prediction.** Two keys. Observed: one.
**2. Localisation.** decision 89; the Gear first a legal option at 32.
**3. Revert confirmation.** DIFFERENT on exactly that key.
**4. Aggregate.** 3 of 40 games, no winner flips, no end-reason changes, turn delta 0.00.
**5. Two-sided reachability.** Not applicable at G1.

## 2026-09-14 — `dying-night-vs-pistol` (AUD-dying-night-vs-pistol-1)

**The fix.** "At the end of your turn, if this Unit is named "V", ready 2 Eddies." The clause tested
the host's *name* and nothing else, so the Gear paid out while sitting on a face-up V in the Legends
area — which is not a Unit. The gate is now the host's zone, so a V that has GONE SOLO onto the
field keeps paying (ruling 015) and a Called one does not.

**1. Prediction.** Four keys may change: `the_heist` and `sample_corpos` are the two golden decks
holding the card, in one matchup each, heuristic and random. Observed: two, both of them random.
Observed ⊂ predicted.

**2. Localisation.** `sample_corpos~sample_nomads~random` game 3 diverges at decision 23, and the
narration of the game the *current* engine plays shows the cause outright: eight decisions earlier,
sample_corpos "plays Dying Night — V's Pistol (Gear) on V — Corporate Exile" — a Legend in the
Legends area, the exact board the fix changes. `the_heist~embracing_power~random` game 13 diverges
at 26 with the card first a legal option at 10.

**3. Revert confirmation.** Old script against the new golden: DIFFERENT on exactly those two keys,
same games, same action numbers.

**4. Aggregate.** 2 of 40 and 1 of 40 games, no winner flips, one end-reason change, mean turn delta
+0.50 and +0.00. An Eddie source removed from a board where a Legend hosted the Gear shifts a turn
and rarely more; nothing here is unexplainable.

**5. Two-sided reachability.** Not required at G1, but recorded: `fuzz --agent random -n 400
--seed 1` moves c0f43d0ac9ccbc54221d480d → 3b4932720efc3f3b2354f268 and the default heuristic fuzz
digest is 8a1e68700fe9fd617d05d0df.

## 2026-09-14 — `reboot-optics` (AUD-reboot-optics-1)

**The fix.** "The next time a rival Unit fights this turn, it doesn't defeat the opposing friendly
Unit." The shield was consumed only by a fight it actually saved a Unit from, so a rival Unit that
fought and lost — or tied, or was already barred from defeating anything by CR 9.19.2 — left it
standing for every later fight that turn. The fight is the trigger; the shield is spent by it either
way. The edit is in `steps.fight`, but `next_fight_no_defeat` is written by this card alone and read
only there, so the deck-membership prediction still applies.

**1. Prediction.** Four keys: `sample_arasaka` and `the_heist` hold the card. Observed: one.

**2. Localisation.** `sample_arasaka~sample_fixers~random` game 20 at decision 114; the Program was
first a legal option at 95. The window shows a fight resolving at Sketchy Ripper 0 against Ruthless
Lowlife 6 — a 0-power attacker that cannot defeat anything under CR 9.19.2, which is precisely the
fight that used to leave the shield unspent.

**3. Revert confirmation.** Old `steps.py` against the new golden: DIFFERENT on that one key, same
game, same action.

**4. Aggregate.** 1 of 40 games, no winner flips, no end-reason change, mean turn delta −1.00: one
game ended a turn earlier, which is what a Unit dying when it should have is worth.

**5. Two-sided reachability.** Not required at G1 reach. The card-level test is the evidence, and it
now pins both halves — the first fight spends the shield even though it protected nobody, and the
second fight kills the Unit that used to be saved.

## 2026-09-14 — `mox-inciters` / `evelyn-parker-beautiful-enigma` (AUD-mox-inciters-1)

**The fix.** "A rival Unit must attack next turn if it can." Two cards wrote the `must_attack` mod
and nothing in `src/` read it, so the obligation was bookkeeping. `legal.main_menu` now drops
EndTurn while an obligated Unit can attack. G2 by file and unlocalisable by construction: a card
script cannot remove an option from a menu the engine builds.

**1. Prediction.** Four keys — `sample_gangers` holds Mox Inciters, `sample_fixers` holds Evelyn
Parker. Observed: all four, and nothing else.

**2. Localisation.** `sample_arasaka~sample_fixers~heuristic` game 4 diverges at decision 157, and
the line immediately before it is `sample_fixers activates Evelyn Parker — Beautiful Enigma: A rival
Unit must attack`. The rival's next turn then opens with an attack. The other three keys diverge in
the forties, where Mox Inciters lands early.

**3. Revert confirmation.** Old `legal.py` against the new golden: DIFFERENT on exactly those four
keys.

**4. Aggregate.** 22/40 and 24/40 random games, 2/16 and 12/16 heuristic games, ten winner flips,
turn deltas +0.00 to +0.32. Much the largest regeneration in this ledger, and the size is the point:
an obligation that was inert on two cards across two golden decks changes every game in which either
card is played, and removing an option renumbers every index after it. An unchanged golden here
would have meant the fix did nothing.

**5. Two-sided reachability.** `fuzz --agent random -n 400 --seed 1` moves
3b4932720efc3f3b2354f268 → 739dfb303644a4bcbad64a06 (32335 → 32481 actions) and the default
heuristic fuzz moves 8a1e68700fe9fd617d05d0df → 399958ef4d06ba064c0411b6 (8601 → 8634). Both
instruments see it, which no other fix in this ledger has managed.

## 2026-09-14 — `alt-cunningham-soulkiller-architect` (AUD-alt-cunningham-soulkiller-architect-1)

**The fix.** "⊡: Your next Program this turn plays for -1 €$ for each friendly min Gig, to a minimum
of 1 €$." A `legal=` guard the card does not print made the ability unavailable with no min Gig, so
the Legend could not be spent at all. Deleting the guard restores an activation whose discount is
zero — and whose ⊡ is worth paying when something watches for the spend.

**1. Prediction.** Two keys: `sample_gangers` is the only golden deck holding the card. Observed:
both.

**2. Localisation.** `sample_gangers~sample_netrunners~heuristic` game 1 at decision 76, with the
card a legal option from decision 9; the random key diverges at 20. The narration around the
heuristic divergence shows sample_gangers activating a *different* Legend's ability in the same
window — the frozen agent's arithmetic over an enlarged menu, which is what adding a legal action to
every turn does.

**3. Revert confirmation.** The guard restored against the new golden: DIFFERENT on exactly those
two keys, same games, same actions.

**4. Aggregate.** 13 of 16 heuristic games and 28 of 40 random ones, 10 winner flips in the random
key, turn deltas −0.38 and +0.18. Large for one card, and the mechanism is the one the ledger has
seen before with Unlikely Bond: a new option in the main menu renumbers every action index after it,
so a key diverges as soon as the card is *on the board*, not when it is used.

**5. Two-sided reachability.** Not required at G1; recorded anyway — `fuzz --agent random -n 400
--seed 1` moves 5e97831a765d264cbf2bd32c → 57d2e94a287e533545144a7f, 32,561 → 32,633 actions, which
is this fix alone (Kerry's had already been taken).

## 2026-09-14 — `muamar-reyes-el-capitan` (AUD-muamar-reyes-el-capitan-1)

**The fix.** "⊡: Adjust a Gig by 1." The shared `adjust_up_to` helper hard-coded `optional=True`, so
the menu carried a decline on the one card of fourteen that does not print "up to". The helper gains
`optional=`, defaulting to the decline because thirteen cards do print it; Muamar's call site passes
`optional=False`.

**1. Prediction.** Two keys: `sample_arasaka` is the only golden deck holding him. Observed: both,
and nothing else — which also cleared the other card fix on the tree that night (Royce), whose own
two predicted keys did not move at all.

**2. Localisation.** `sample_arasaka~sample_fixers~heuristic` game 0 at decision 16, the ability
first a legal option at 4.

**3. Revert confirmation.** `optional=False` removed against the new golden: DIFFERENT on exactly
those two keys, at exactly actions 16 and 36.

**4. Aggregate.** 16 of 16 heuristic games and 31 of 40 random ones; no winner flips in the
heuristic key, two in the random one; turn deltas +0.00 and +0.19. Every heuristic game moving is
the expected shape for removing an option from a menu the agent reaches every turn — it renumbers
every action index after it, so the key diverges the first time the ability is available rather than
the first time the decline would have been taken. The zero turn delta says the games are otherwise
the same games.

**5. Two-sided reachability.** Not required at G1.

## 2026-09-14 — `kerry-eurodyne-axe-attitude-audience` (AUD-kerry-eurodyne-axe-attitude-audience-1)

**The fix.** The min/max draw was queued with `later`, which pushes a step on top of the stack, so it
resolved before the player was asked whether to reroll — and its guard read a mod nothing writes. A
roll of 1 on a d6 drew a card and the reroll to 6 drew another. The draw now hangs off the reroll
question's `after=`, once, on the value the die ends on.

**1. Prediction.** Two keys; `sample_fixers` is the only golden deck holding him. Observed: both.
**2. Localisation.** `sample_arasaka~sample_fixers~heuristic` game 0 at decision 39, the card first a
legal option at 14.
**3. Revert confirmation.** DIFFERENT on exactly those two keys against the new golden.
**4. Aggregate.** 8 of 16 and 15 of 40 games, one winner flip each, turn deltas +0.00 and −0.53. A
Legend whose trigger fires on the Gig roll every single turn, so half the games touching it is the
expected shape.
**5. Two-sided reachability.** Not required at G1.

**A second file had to move first.** The five mined suite positions are stored as action-index
replays of real games, and this fix stopped them rebuilding. They were frozen into board specs
against the previous build (`delayed.freeze_replays`) before the fix was restored — the same lesson
as this ledger's, one instrument over: an index is not a move.
