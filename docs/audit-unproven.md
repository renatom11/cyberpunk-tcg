# Suspected, unproven

The card audit filed 43 findings, and every one of them came with a test that was seen to fail. This
file is the other output: **45 bucketed items an auditor noticed and could not prove** — 13
S-SUSPICION, 12 U-UNREACHABLE, 20 N-NOTE — plus the four cross-cutting batches' "examined and not
filed" sections, which say why a whole shape of suspicion was dropped. Kept because the alternative
is losing them. They were written into `out/audit/<batch>/findings.md`, and `out/` is
gitignored and lives in an ephemeral container — so without this file they existed until the machine
was reclaimed and no longer.

**This is not a to-do list of bugs.** Read the bucket on each item before reading the item:

| bucket | what it means | what to do with it |
|---|---|---|
| **S-SUSPICION** | the auditor believed the script was wrong, wrote the scenario, and the test **passed** | the most dangerous class in the whole audit. A passing test is evidence the engine is right *on that board*; it is not evidence the suspicion was baseless. Never fix one of these directly — find the board that fails first, or leave it alone |
| **U-UNREACHABLE** | the branch is wrong but no card in MS01-WNC can reach it | a latent fragility, and a note for whoever adds the set that makes it reachable |
| **U-FIXTURE** | needs a test helper the audit was not allowed to add (auditors could not touch `tests/conftest.py`) | writable now, by someone who may edit the fixture — none were filed this pass |
| **N-NOTE** | style, naming, a comment that is now wrong, an idiom worth changing | ordinary cleanup, no correctness claim |

The rule that produced these buckets is the rule the audit was run under: a finding has two legs —
an observed failing test *and* a clause-by-clause expectation derived from the printed text — and
anything with only one leg goes here instead of into a fix. The `xfail(strict=True)` tests under
`tests/cards/audit/` are the other side of that contract; these are the observations that never
earned one.

Verbatim from the batch reports, grouped by the section of `src/cptcg/cards/sets/wnc.py` each batch
read. Line numbers are as of the audit and may have drifted.


## A01 — Programs: removal and flow (1/3)

- **S-SUSPICION — Memory Relapse / Corporate Surveillance target an already-spent rival Unit.**
  Both scripts pass the whole `c.rival_units()` (filtered only by cost, for Corporate
  Surveillance) to `spend_one`, so an already-spent Unit is a legal pick; `ops.spend` returns
  immediately for a spent card (`src/cptcg/core/ops.py:320-325`). For Corporate Surveillance the
  outcome is unobservable (probe: only spent cheap Unit on the board ⇒ no state change either
  way), so no test can distinguish it. For Memory Relapse it *is* observable — the script still
  applies "can't ready until your next turn" to a Unit it did not actually spend. I did not file
  this as a finding because both readings are defensible: ruling **013** ("'spend this Unit'
  requires a ready card") points at "no legal target", while the mainstream TCG convention is that
  a spend/tap effect may target an already-spent permanent and the rider still applies. Card text
  is silent. Flagging for a rules decision rather than freezing a guess into an xfail.
  **Answered:** this became [`rulings.md`](rulings.md) row 043, left Uncertain with the engine's
  behaviour standing — exactly what "flag it for a decision" was asking for.
- **U-UNREACHABLE — Live with the Aftermath's candidate lists are snapshots.** Both `c.rival_units()`
  and `c.units()` are materialised when the Program resolves, and the two picks are then queued.
  If resolving the first defeat removed a Unit from the other player's list (a DEFEATED trigger
  that kills across the board), the second chooser could "defeat" an instance that is already in
  the trash — `ops.defeat` returns `False` for a card outside FIELD/LEGENDS — and end up defeating
  nothing while still controlling a Unit. I could not build a legal board that does this with the
  cards in this set (no printed DEFEATED trigger defeats a Unit on the other side), so there is no
  failing test and no finding.
- **N-NOTE — Over the Edge silently uses the best friendly d20.** `lim = max(d20)` rather than
  asking which d20 to use. The candidate set for any smaller d20 is a subset of the candidate set
  for the largest, so no reachable outcome differs; it is a search-space simplification in the
  same spirit as ruling 025, not a text deviation. Probe with `gig=[(20, 3), (20, 8)]` and rival
  Units of power 6 and 8: both are offered, which is what "a friendly d20" permits.

## A02 — Programs: removal, card flow, tempo (2/3)

### U-UNREACHABLE — Chrome Reverie resolves its two clauses in reverse printed order

`chrome-reverie` (wnc.py:108-112) queues the "a rival Unit can't attack" question first (109) and
the "you may Call a Legend for free" question second (112). Both go through `ops.ask`, which does
`s.stack.append(AskStep(choice))` (ops.py:167-169) — a LIFO stack — so the *Call* question is asked
**before** the can't-attack question. The existing `test_chrome_reverie_locks_attacker_and_may_call`
answers the Call first, which confirms the order.

I could not build a state where the order is observable in printed-text terms. The only way the
Call could change the can't-attack decision is a `CALL` trigger that removes a rival Unit from the
field, and there is none: the seven `on_call` hooks in wnc.py are v-streetkid (trash 3 / add a
BRAINDANCE Program), wakako-okada (rival Unit −2 power / draw 1), dexter-deshawn-off-the-grid
(friendly Unit +2 / draw 1), padre (**spend** a rival Unit / draw 1 — spending does not remove it),
muamar-reyes (no-defeat-in-fight / draw 1), viktor-vektor (search top 5), dum-dum (defeat a
*friendly* Gear / draw). Calling also cannot add a rival Unit. The candidate list on line 109 is
snapshotted at script time either way, so no reordering of the two answers changes any zone, power,
Gig or keyword. Recorded rather than dropped because a future `CALL` Legend that bounces or defeats
a rival Unit would make it live.

### N-NOTE — `offer_call_free` lets the controller pick *which* face-down Legend flips

`chrome-reverie` line 112 calls `effects.offer_call_free` (effects.py:386-391), which presents each
face-down Legend as its own option. `docs/rules.md` says *"flip one face-up at random"* / *"without
looking first"*, and ruling 041 only constrains the once-per-turn limit. With all slots unknown the
options are interchangeable, so this is normally a no-op; it stops being one once a slot's identity
is known to the controller (`ops.call_legend` and `effects.look_at` both set `i_known`). This is
engine-level behaviour shared by every card that Calls, not something `chrome-reverie` does, so it
is out of this batch's scope — recorded only so the next audit of `offer_call_free` has the pointer.
Style/scope note only; no test written.

## A03 — Programs: Quickhacks (3/3)

**N-NOTE 1 — Synapse Burnout counts face-up Legends once, at resolution** (wnc.py:292-293).
"A friendly Unit has +1 power for each friendly face-up Legend while fighting rival Units this
turn": `n` is frozen when the Program resolves, so Calling a Legend afterwards does not raise the
bonus. Both readings are defensible — a resolution-time pump vs. a continuous "has +1 for each"
characteristic — and the engine offers a Program no continuous mechanism at all (`power_mod`
hooks only run for cards *in play*; a Program is outside every area while it resolves and in the
trash after, ruling 035). I did **not** write a test: freezing either reading as a strict xfail
would be a coin flip. Flagged for a card-text ruling, not as a defect.

**N-NOTE 2 — Take Control's "steals 1 fewer Gig" only reaches attack-steals** (wnc.py:301).
`steal_fewer` is read in exactly one place, `ResolveAttackStep` (steps.py:334), so a steal that an
*effect* hands the same Unit is not reduced. Verified against Appetite for Destruction from this
very batch: Animals Wrecker under Take Control still stole the die its 8-margin fight win granted
(`s.gig[0] == [(6, 3)]`, `s.gig[1] == []`). Whether "steals 1 fewer Gig this turn" is a blanket
rider on that Unit or only shrinks an attack's steal count is genuinely open, so no test was
written and no expectation frozen.

**N-NOTE 3 — Safety Override shares the tied-fight blind spot, harmlessly** (wnc.py:315,
steps.py:390-394). Under ruling 010 a tie is a loss for the friendly Unit, so "the next time a
friendly Unit loses a fight this turn, defeat the opposing rival Unit" should fire; it does not.
I could not build an observable failure: on a tie the engine already sets `defeat_t` *and*
`defeat_a`, so the effect's defeat coincides with the fight's, and any replacement that saves the
opposing Unit from one would equally save it from the other. U-UNREACHABLE; recorded as a code
fact with no expectation attached.

**N-NOTE 4 — ordering in Floor It; printed-vs-current power in Detonate.**
(a) Floor It (wnc.py:277-279) queues the -1 power choice and *then* draws, so the draw resolves
before the debuff is applied; the printed order is the reverse. I looked for a printed-text
outcome that differs and found none (an empty rival field still draws; a deckout ends the game
either way), so this is style only. (b) Detonate (wnc.py:286) filters on `c.d(g).power` (printed)
rather than `c.power(g)` (current). No card in `data/cards/wnc.json` modifies a Gear's power and
every Gear has a printed power (lowest: Mandibular Upgrade 0, correctly eligible), so the two
agree today — U-UNREACHABLE for a failing test, worth knowing if a power-pumping Gear ever ships.

## A04 — Gig manipulation

* **N-NOTE — peace-offering offers sources that cannot legally be copied.** `wnc.py:370` builds
  `others` from every other Gig with no filter, so the menu includes sources whose value is off the
  target die's face (copying a d10's 9 onto a d6) or equal to the target's current value. Ruling 037
  is explicit that such an effect **fails — no change** (and `ops.set_gig:502-506` implements that),
  so choosing one is legal-but-inert rather than wrong. This is a search-branching / UI nicety, not
  a text discrepancy: the printed text does not restrict which other Gig you may name. Recorded as
  a note only — no test, and it should **not** be "fixed" by narrowing the choice without a ruling.
* **S-SUSPICION — "a Gig" reaching the rival's Gig area.** All three adjust cards pass
  `[c.player, c.rival]` as the owners while their payoff clause is friendly-only, which looked like
  a friendly/rival scope error. I wrote the scenario for `trust-no-one` (rival holds the only Gig, a
  d6 at 4; the player decreases it by 1 and draws nothing because *they* control no min Gig) and ran
  it in the scratchpad: it **passed** — `s.gig[1] == [(6, 3)]`, hand empty. The printed text says "a
  Gig" unqualified, `docs/rules.md` gives no default owner, and the set's own convention is to write
  "friendly" when it means friendly (`wnc.py:1370` "Decrease a friendly Gig"). The scripts are
  right, so the test was discarded rather than frozen into `tests/cards/audit/test_a04.py`.

## A05 — Units: PLAY triggers (1/2)

**S-SUSPICION — Gilded Matón / Heywood Ripperdoc: a replaced Gear defeat still pays out.**
Both scripts call `c.defeat(g)` and ignore its return value (`ops.defeat` returns `False` when a
replacement effect takes over, `ops.py` `defeat`). Gilded Matón's text conditions the rival-Unit
defeat on "**If you do**", so a Gear whose defeat is replaced should not pay out. I wrote the
scenario and could not make it fail: the only two `would_defeat` replacements in the pool are
`deadman-transmitter` (`wnc.py:1106-1111`, fires only when the *host* is defeated, never the Gear
itself) and `jackie-welles-mamas-favorite` (`wnc.py:1339-1359`, returns `False` unless
`c.d(inst).type is UNIT`). No card in MS01-WNC can replace the defeat of a Gear, so the branch is
unreachable today. Recording it as a latent fragility, not a finding.

## A06 — Units: PLAY triggers (2/2)

**U-1 — S-SUSPICION — Yorinobu Arasaka *Steel Dragon* does not draw for its own defeat.**
Yorinobu is itself an ARASAKA Unit, so "The first time an ARASAKA Unit is defeated each turn, draw 1"
arguably covers its own death. `ops.defeat` (ops.py:456-461) calls `move(...)` *before*
`dispatch(("defeated", ...))`, so by dispatch time Yorinobu is in the trash, out of
`_rebuild_active`'s per-player lists, and its `on_event` hook is not called. I wrote the scenario
and it behaved as the engine describes; I did **not** file it, because this is a whole-engine
convention (a continuous "when X happens" ability on a card that has just left play stops applying),
not something this card's script chose, and changing it would touch every `on_event` card in the
pool. The printed text does not distinguish. Flag for a rules-level decision, not a card fix. Once
AUD-yorinobu-arasaka-steel-dragon-1 is fixed, this becomes the only remaining gap in clause 7.

**U-2 — S-SUSPICION — Off-Duty Malfini can "spend" an already-spent rival Unit.**
`spend_one(c, c.rival_units())` (wnc.py:522-524) offers every rival Unit, spent ones included, and
`ops.spend` (ops.py:320-322) returns immediately if `i_spent` is set — so a player can throw the
clause away. I wrote the board (one ready + one spent rival Unit) and the engine did offer both
picks. It is not a finding: "Spend this Unit and a rival Unit" places no readiness condition on the
target, and choosing a redundant target is the player's prerogative in every comparable card. The
mandatory half — Malfini spends itself even when the rival's field is empty — behaves correctly.

## A07 — Units: ATTACK and DEFEATED

### U-1 · `swordwise-huscle` · "If this Unit has power 5+" is measured with `sit=ATTACKING` only — **S-SUSPICION**

wnc.py:632 evaluates `c.power(sit=ATTACKING)`, so a power bonus that is conditional on `FIGHTING`
or `VS_UNIT` (e.g. Synapse Burnout, wnc.py:293, `temp_power_one(..., FIGHTING | VS_UNIT)`) does not
count toward the 5 even when the declared target is a rival Unit and the fight is one step away.
I wrote the straightforward probes and they **passed**: at printed 3 + Mantis Blades 2 the unit is
power 5 in every situation and draws (`power(s, u) == power(s, u, ATTACKING) == 5`). The only board
that separates the readings needs a `FIGHTING`-conditional buff, and on that board the plain reading
of "has power 5+" at trigger time (ruling 023: the trigger resolves after the target is declared but
before the fight) is that a fight-only bonus is *not* yet part of the Unit's power — which is what
the script does. Recorded as suspicion only; no finding.

### U-2 · `pepe-najarro-working-doubles` · MERC tags are read off face-down Legends — **S-SUSPICION**

wnc.py:653 filters `c.legends()` by `"MERC" in c.d(l).tags` without regard to `i_faceup`, so a
face-down spent MERC Legend is a legal pick. I wrote the probe and it **passed** under the reading I
believe correct: the text says "MERC Legends **in your Legends area**", with no face-up requirement,
and **ruling 031** withholds only a face-down Legend's *text* ("only face-up Legends contribute
static effects, event triggers and abilities"), not its identity or tags — which its controller
knows anyway. Contrast Panam and Synapse Burnout, which say "face-up" when they mean it. No finding.

## A08 — Gear with ATTACK / DEFEATED triggers

- **N-NOTE — `gear_hosts` excludes face-down Legends, engine-wide.** `docs/rules.md` says
  "Gear — pay its cost and equip it to a friendly Unit **or Legend**" with no face-up requirement,
  and `dying-night-vs-pistol` (like 6 other Gear) prints **no** equip parenthetical at all, so its
  hosts come straight from that sentence. `legal.gear_hosts` nonetheless requires
  `s.i_faceup[i]`. This is a coherent engine-wide policy (ruling 031: a face-down Legend's text is
  inactive, and its identity is hidden, so hosting one leaks nothing but is odd), it is shared by
  every Gear in the game, and 9 of 17 Gear print "face-up Legend" explicitly — so it is a
  cross-cutting rules-doc/engine question, not a defect in the three scripts in this range.
  Recorded as style/scope note only; no test written.
- **S-SUSPICION — The Relic on a face-up Legend host.** I reasoned through (but did not need a
  failing test for) the case where the host is a face-up Legend: ruling 034 removes the Legend from
  the game and the Gear follows, so `i_zone[host] is Zone.TRASH` is false and nothing is
  bottom-decked. That is the ruling's own default, and "this Unit" does not name a Legend. Correct
  as scripted — **D** by ruling 034, no finding.

## A09 — Statics and cost modifiers

**U-1 · N-NOTE — "reveal" is a pool-wide engine gap, not eight card bugs.**
`i_known` is only ever written by `ops.call_legend` (ops.py:547) and `effects.look_at`
(effects.py:383), and `view.knows_identity` reads it only for the LEGENDS zone; `Choice.revealed`
pins instances for the *chooser* and only while the Choice is pending. So there is no mechanism a
card script could call to reveal a non-Legend card to the opponent durably. The eight cards that
print "reveal" are `fool-on-the-hill`, `hanako-arasaka-in-a-gilded-cage`,
`judy-alvarez-nothing-to-doubt`, `misty-olszewski-mender-of-broken-spirits`,
`sasha-yakovleva-wont-let-you-down`, `sketchy-ripper`, `viktor-vektor-sit-down-and-relax`, and
(negatively) `kiroshi-optics`. AUD-misty-…-1 above is filed as Misty's instance; the fix is one
engine affordance, not eight scripts.

**U-2 · N-NOTE — MaxTac Suppression Team vs. a printed "can attack the turn it's played".**
`legal.attack_permission` (legal.py:33-40) returns `(False, False)` for any lagged Unit whose Rival
controls a suppressor **before** the Unit's own `attack_perm` hook runs (legal.py:44-47). So MaxTac
Suppression Team beats Nadia's "this Unit can attack their Gig area the turn it's played", beats
ADRENALINE and beats GO SOLO. `docs/rules.md` states no "can't beats can" precedence rule and no
ruling covers it, so both readings are arguable — but this is a *settled repo decision*, not an
accident: the code comment says "full stop", and `tests/cards/test_statics.py::
test_maxtac_suppression_stops_adrenaline` pins the ADRENALINE case. I confirmed Nadia
(`attacks == set()`) and a GO SOLO `v-corporate-exile` (`attack_permission == (False, False)`) both
follow the same rule, i.e. the engine is self-consistent. No test filed: writing one would freeze
whichever reading I picked, and I have no authority to pick.

**U-3 · S-SUSPICION — cost-reduction floor vs. a cost *increase*.**
All three reducers floor inside `self_cost` (`max(1, base - n)`) and `ops.play_cost` floors again at
ops.py:358-359 only when the *net* delta is negative. With enough reducers plus an increaser the two
orders could differ (e.g. base 7, −8 from Octant, +2 → engine 3; "floor last" → 1). I wrote the
probe and it cannot be reached: the only two `cost_mod` hooks in the pool are
`viktor-vektor-drop-your-illusions` (wnc.py:817-821, CYBERWARE Gear only, negative) and `riot-shield`
(wnc.py:831, `+2` and only when `go_solo` is true, while `self_cost` is skipped for GO SOLO at
ops.py:348). Nothing can raise the cost of a Unit played from hand, so no legal game distinguishes
the two orders. Filed as a note, not a finding.

## A10 — Power auras

- **U-UNREACHABLE — `meredith-stout-stone-cold-corpo`, "adjusts or swaps **1 or more** friendly
  Gigs".** The script triggers on `gig_changed` (wnc.py 855-858), and `ops.adjust_gig` / `set_gig`
  dispatch that event once **per die**, so an effect moving two friendly Gigs would offer Meredith's
  trash-return twice, where "1 or more" reads like one trigger for the whole effect. I grepped every
  card text in `data/cards/wnc.json` for adjust/increase/decrease/swap: all sixteen are "a Gig" or
  "a friendly Gig with a rival Gig" — single-die effects (`afterparty-at-lizzies`,
  `industrial-assembly`, `trust-no-one`, `la-llorona-ghost-of-the-past`,
  `hanako-arasaka-daughter-of-the-emperor`, `maxtac-av`, `6th-street-recruits`, ...), and
  `swap_gigs` likewise dispatches exactly one event. No legal game reaches a two-Gig rival adjust,
  so the difference cannot be shown and is not a finding.
- **S-SUSPICION — `zetatech-berserk`, "for each friendly face-up Legend".** A friendly Legend that
  has gone solo is face-up but on the field, and `c.legends(p, faceup=True)` reads only the Legends
  area, so it is not counted. I judge the script right — ruling 015's default is that a gone-solo
  Legend vacates its Legend slot and "is a Unit now", exactly the trap list's presumed-D case — and
  every discount probe I wrote PASSED: 3 friendly face-up Legends -> 6-3 = 3 €$; 0 friendly face-up
  with 3 **rival** face-up -> 6 €$; the "minimum of 1" clamp is unreachable, since a player has only
  3 Legends against a printed cost of 6.

## A11 — Turn hooks

- **S-SUSPICION — `maxtac-squadron`: "ready a friendly face-up Legend" and a GO SOLO Legend on the
  field.** Symmetric to AUD-6th-street-recruits-1: `c.legends(faceup=True)` reads only the Legends
  *area* (`state.legends`, `core/state.py:214`), so a face-up Legend that GO SOLO'd onto the field
  and is sitting spent cannot be readied. I built and ran that board (MaxTac spent, Goro Takemura
  solo'd and spent by attacking, end of turn): Goro stays spent. **I am not filing it.** "Face-up"
  is a Legends-area orientation — a solo'd Legend is on the field as a Unit, and ruling 015's
  default reading of it ("it is a Unit now") cuts *against* calling it a "face-up Legend" there.
  Both halves of the batch's GO SOLO question cannot be answered the same way from the same
  evidence, and here the evidence points at the script being right. Recorded so the next auditor
  does not re-derive it.
- **N-NOTE — `6th-street-recruits` / `la-llorona-ghost-of-the-past`: "increase a Gig" is offered
  over *both* players' Gig areas** (`c.adjust_up_to([c.player, c.rival], …)`). The in-file comment
  at `wnc.py:941-944` defends this, and the card data corroborates it rather than contradicting it:
  `jackie-welles-pour-one-out-for-me` is the only card in the set that narrows the scope
  ("decrease a **friendly** Gig"), and `meredith-stout-stone-cold-corpo` reads "When a **Rival**
  adjusts or swaps 1 or more friendly Gigs, …", which only makes sense if an unscoped "a Gig" can
  reach across the table. The offer is also always optional, so no forced self-harm. Style note
  only; no finding.

## A12 — Gear: host-spent triggers

**S-SUSPICION — overwatch-panams-gift and the GO SOLO Legend on the field.**
I suspected Overwatch of the same scope error as Satori and wrote the test: it **passed**. A Legend
played to the field with GO SOLO is in `c.rival_units()` and is defeated by "Defeat a spent rival
Unit" exactly as the printed text says. Recorded because it is the evidence that the two cards read
the same two words differently, and because `tests/cards/test_audit_shape.py` keeps passing
scenarios out of the audit directory — the code and its result are under AUD-satori-sword-of-saburo-1
above.

**U-UNREACHABLE — sandevistan on the Rival's end of turn.**
"At the end of **your** turn" is scripted as `e[1] == c.player`, so I tried to catch it readying the
host at the end of the Rival's turn. No board distinguishes the two readings: with `active=1`,
`do(s, EndTurn())` runs straight on into the controller's own Start Phase, which readies every spent
card anyway (ruling 001) — my probe saw the host ready, from the Start Phase and not from the Gear.
The scope test in the script is right by reading; there is nothing to assert either way.

**U-UNREACHABLE — deadman-transmitter replaces the defeat of a Legends-area host.**
`would_defeat` (L1104-1110) fires for whatever `c.host()` is, but the printed text says "If **this
Unit** would be defeated". A face-up Legend in the Legends area is a legal Gear host and is not a
Unit, so the replacement should arguably not apply to it. I could not build a legal game that
defeats a Legend while it sits in the Legends area: `ops.defeat` returns False immediately for any
card outside FIELD/LEGENDS, and no card in the set targets a Legends-area Legend with a defeat
(the ones that defeat Legends — jackie-welles-mamas-favorite — do it to a Legend on the field,
where it *is* a Unit and the replacement is correct). No failing test, so no finding.

**N-NOTE — adrenaline-converter grants ADRENALINE to a Legends-area host.**
`kw_mod` (L1038-1041) returns True for `inst == c.host()` whatever the host is, and I confirmed by
probe that `has_keyword(s, <face-up Legend in the Legends area>, ADRENALINE)` is True. The text says
"this Unit has ADRENALINE" (contrast zetatech-faceplate's "this Unit **or** Legend"), so under the
reading used by `test_a08.py::test_dying_night_ready_2_only_when_the_host_is_a_unit` this is a
scope error. It has no reachable consequence: ADRENALINE only lets a card attack the turn it is
played (`rules.md` Keywords; `legal.py` L41), a Legend in the Legends area cannot attack, and once it
GOES SOLO it is on the field carrying GO SOLO, which already clears the same Lag check. Style only.

**N-NOTE — arasaka-emergency-radioport offers a Call that cannot happen.**
L1077-1078 asks "Call <name> for free?" before checking `ops.can_call_free`; `c.call_free` then
does nothing if the once-per-turn Call is spent (ruling 041, and `offer_call_free` in
`effects.py` L386-391 shows the guarded pattern). The outcome matches the printed reminder text
"(You may only Call a Legend once per turn.)" either way — only a dead prompt is added.

**N-NOTE — overwatch-panams-gift is illegal to activate with an empty hand.**
`legal=lambda c: bool(c.hand())` (L1121) is a condition the printed cost line does not state. It can
only ever save the controller from paying 1 €$ and spending the Gear for nothing (with no cards to
discard, `picks` is empty and the `if picks:` guard at L1116 skips the defeat), so I could not
construct a board where the added restriction costs anyone anything.

## A13 — Legends (1/2)

### U-UNREACHABLE — Kerry's reroll is offered once per **turn**, not once per roll-in

wnc.py 1235-1238 guards the offer with `(c.inst, "reroll_offer") in c.s.used`, and `s.used` is
cleared by `EndTurnCleanupStep` (`core/steps.py:181`) — so the guard is per turn. The printed
"reroll it once" attaches to the *roll* ("you may ignore the result and reroll it **once**"), so a
second roll-in in the same turn should get its own offer. No legal game reaches a second roll-in:
`gain_gig` is called from exactly two places (`core/steps.py:135` in `GainGigStep`, and
`core/engine.py:138` resolving the `GIG_DIE` menu that same step opened), both once per start
phase, and no card in `data/cards/*.json` rolls in an extra Gig. I could only provoke it by calling
`ops.gain_gig` twice by hand, which no rules sequence does. Recorded, not claimed.

### N-NOTE — two abilities in this batch have no `legal=` predicate, so they can be paid for nothing

`river-ward-detective-on-the-hunt`'s Gear ability (wnc.py 1214) and `padre-man-of-the-cross`'s
set-Gig ability (wnc.py 1171) are offered on the main menu whatever the board looks like. Activating
River Ward with no cost-2-or-less Gear in hand, or Padre when one side has no Gigs, spends the
Legend and resolves to nothing (`c.choose` with an empty candidate list and no `otherwise` returns
silently). Two other Legends a few lines away do guard themselves — Hanako
(`legal=lambda c: bool(c.gigs()) and bool(c.gigs(c.rival))`, wnc.py 1267) and Panam
(`legal=…`, wnc.py 1286). This is a playability/menu-hygiene difference, not a printed-text
discrepancy — neither card's text promises the ability is unavailable — so it is a note, not a
finding.

### N-NOTE — "Reveal up to 2 Gears" (Viktor) is modelled as a private search

`EffectCtx.search_top` declares `revealed=tuple(cards)` (effects.py:276-277), which marks the five
cards as seen **by the searcher**, per that parameter's documented meaning ("the instances this
question has *shown* to the chooser"). Viktor's text says "**Reveal** up to 2 Gears … and add them
to your hand", which in TCG usage means shown to the opponent. There is no `revealed_to_opponent`
channel in `core/view` to express that, so I cannot write a test that distinguishes the two, and the
distinction has no mechanical consequence in this engine (nothing reads the rival's knowledge of a
specific card). Style/information-model note only.

## A14 — Legends (2/2)

**S-SUSPICION — `alt-cunningham-soulkiller-architect`, when the min-Gig count is read.**
"Your next Program this turn plays for -1 €$ for each friendly min Gig, to a minimum of 1 €$."
The script snapshots the count at activation: `c.mod("cost_next_program", c.player, -len(c.min_gigs()))`
(wnc.py:1332) stores a fixed number, and `ops.play_cost` later just adds it. I wrote the probe
(activate Alt with one min Gig, then use Hanako Arasaka's ⊡ to swap a rival 1 onto my side, making
two min Gigs, then read the cost of a 3-cost Program): the cost stays 2, i.e. the second min Gig is
ignored. **The probe passes under the snapshot reading, so I am filing no test.** Both readings are
defensible — "plays for -1 €$ for each friendly min Gig" can be read as a price fixed when the
effect resolves, or as a modifier evaluated when the Program is actually played — and a strict-xfail
for the second reading would freeze a coin-flip into the repo. Worth a human decision; if the
"evaluate on play" reading is chosen, the fix is a callable/`cost_mod` hook rather than a stored
integer. (The `to a minimum of 1 €$` half is right: `ops.play_cost` floors any reduction at 1 when
the base cost is ≥ 1 — verified at 1, 2 and 3 min Gigs.)

**N-NOTE — "Reveal" is not modelled as information for `sasha-yakovleva-wont-let-you-down`.**
"ATTACK: **Reveal** the top card of your deck and add it to your hand." The script (wnc.py:1427-1429)
moves the card to hand without marking it known to the Rival (`c.look_at` / `revealed=` exist for
exactly that). It is a set-wide convention rather than a defect of this card —
`judy-alvarez-nothing-to-doubt` reveals the same way, with a comment saying so — so fixing it is a
pool-wide decision and there is no zone/power/hand-size outcome to assert.

**N-NOTE — `johnny-silverhand-rocking-renegade` has no `legal` guard.**
The ability (wnc.py:1310) can be activated with no friendly Units on the field: you pay, Johnny is
spent, and `c.choose([])` does nothing. Legal by the printed text (the cost is paid to activate),
but sibling cards in the batch guard the same shape — Panam's ability carries
`legal=lambda c: bool(c.gear()) and any(...)` (wnc.py:1298). Style only, no rules consequence.

## A15 — Legend abilities

**U-UNREACHABLE-1 — Judy's `type is not LEGEND` guard (wnc.py 1454).** A Legend on top of the deck
would be denied the free play, which ruling 033 otherwise permits for any costed Legend ("Any Legend
with a cost (CR 4.5); in this set every costed Legend carries GO SOLO"). But no legal game puts a
Legend in a deck: Legends start in the Legends area, and ruling 034 removes one from the game the
moment it leaves the field or the Legends area ("trash, hand or deck are invalid areas for a Legend
(CR 4.4.1)"). `board()` can plant one there by hand, but the resulting position is not reachable, so
the guard is unfalsifiable and is in fact defensive. The companion guard `c.d(i).cost is not None`
(same line) is dead for the same reason — a scan of `data/cards/wnc.json` finds **zero** non-Legend
cards with a null cost. Bucket: **U-UNREACHABLE**.

**U-UNREACHABLE-2 — Rogue's drain measures her power before the target question is answered.**
`drain` computes `p = c.power()` (wnc.py 1475) and closes over the integer, then `temp_power_one`
queues the "which rival Unit" question. If anything could change Rogue's power between the question
and the answer, the delta would be stale. Nothing can: the choice is the next step on the stack, and
`engine.activate` (engine.py 221-229) pushes the effect's `HookStep` *before* paying and
self-spending, so even the ⊡ cost cannot land in that window — and spending does not change power
anyway. There is no legal game state inside the gap. Bucket: **U-UNREACHABLE**. (Measuring at the
start of the effect's own resolution is also the ordinary reading of "equal to this Unit's power";
`test_rogue_drain_counts_her_own_temporary_power` pins that it *does* include buffs standing at that
moment.)

**N-NOTE-1 — "Reveal" is not modelled as a reveal to the Rival (engine-wide, not a card defect).**
Judy *Nothing to Doubt* prints "**Reveal** the top card of your deck"; the script moves it straight
to hand (wnc.py 1453, with a comment saying so). `core.view.knows_identity` treats `Zone.HAND` as
readable only by its owner, and `s.i_known` is consulted **only** for the `LEGENDS` zone
(view.py 121-137) — `ops.call_legend` (ops.py 547) is its single writer of `0b11`. So no engine
mechanism exists for making a hand card public to the other seat, and every "reveal …, add it to
your hand" card in the set has the same gap (`viktor-vektor-sit-down-and-relax` via `search_top`,
`sketchy-ripper`). Batch A14 records the same observation from the other side. Filing it against Judy
would be filing an engine limitation as a card bug, and it is in any case not expressible in the
assertion vocabulary this batch is allowed to use (zones, hand size, `power()`, `has_keyword`).
Bucket: **N-NOTE**.

## B01 — Cross-cutting: on_event trigger words vs event kinds

* **Once-per-turn guards.** Every "the first time … each turn" hook in the batch has a `c.once(...)`
  and every one places it last in the condition, so it is consumed only by a qualifying event:
  gorilla-arms `once("steal")`, jackie `once("blue")`, rogue `once("ready_eddies")`. The set-wide
  sweep found no missing guard; the one genuine per-event/per-action mismatch,
  `evelyn-parker-beautiful-enigma` readying an Eddie per die instead of per steal of "1 or more
  Gigs", is already AUD-evelyn-parker-beautiful-enigma-1 (batch a13) and is not my card.
* **`s.used` clearing at every turn boundary** (so `once()` is per game-turn, not per player-turn)
  is ruling 019, settled on purpose.
* **`goro-takemura-vengeful-bodyguard`'s BLOCKER redirect scope** is ruling 012.
* **Off-batch observation, not filed because the card is not mine:**
  `yorinobu-arasaka-steel-dragon`'s `defeated` hook is the only hook in the set whose printed noun
  carries no side ("an ARASAKA Unit is defeated") while the code restricts it to `e[2] == c.player`.
  That is already AUD-yorinobu-arasaka-steel-dragon-1 (batch a06); recording it here only because
  the cross-cutting read confirms it is the single side-scoping outlier among all 39 hooks — every
  other hook whose text says "friendly" checks owner, and no other hook adds an owner check the
  text did not ask for.

## B02 — Cross-cutting: the modifier family

**4.1 Read sites that are narrower than the action they gate.** `steal_fewer` (take-control,
"A rival Unit steals **1 fewer Gig** this turn") is read only in `ResolveAttackStep`, so an
effect-driven steal — Gorilla Arms, Appetite for Destruction — takes its full count. That is
exactly `AUD-chrome-fang-1` / `AUD-westbrook-netrunner-1` (a05) one mod over, and the fix is the
same fix: route effect steals through the shared path. Recorded here rather than filed a third
time. Likewise Evelyn Parker's `⊡: A rival Unit must attack next turn if it can` is dead for the
same reason `AUD-mox-inciters-1` is dead, and will come back to life with the same fix.

**4.2 Prevention vs. instruction ordering in `steps.fight`.** The three "no defeat" mods
(`no_defeat_in_fight`, the 0-power rule, `next_fight_no_defeat`) are applied first, and
`next_loss_defeats_winner` then sets `defeat_a` / `defeat_t` back to `True` unconditionally — so
Safety Override defeats a winner that Muamar Reyes protected with *"A friendly Unit can't be
defeated in a fight this turn."* The engine's own precedent elsewhere is that a printed "can't"
beats a printed "can" (MaxTac Suppression Team overrides ADRENALINE — confirmation 2 below), which
argues the prohibition should win. Against that, Safety Override's defeat is arguably an *effect*
defeating the Unit rather than the fight defeating it, and Muamar's clause says "in a fight". The
card text does not settle it, so it is recorded, not filed.

**4.3 `cost_go_solo` is consumed after one GO SOLO.** `ops.consume_cost_mods` clears the mod on the
first GO SOLO, and nothing limits GO SOLO to once per turn, so a second Legend that turn pays full
price. Nocturne prints "**A friendly Legend** may use GO SOLO for -2 €$ this turn" — the singular
subject makes one-Legend consumption a defensible reading, so this is not a finding. (Contrast
Alt Cunningham's "your **next** Program this turn", where consumption is certainly right.)

## B03 — Cross-cutting: optionality, sides, counts

**5.1 `floor-it` — "Give a rival Unit -1 power this turn. Draw 1."** `temp_power_one` pushes the
prompt and `c.draw(1)` then runs immediately, so the card draws before the player says which rival
Unit loses the power. That is out of printed order, and I could construct no printed-text outcome
that differs: the draw is unconditional, nothing in the pool triggers on a draw, the pending prompt
is still answered before the fight it was played into resolves, and on an empty deck both orders end
the game the same way. The only difference is that the chooser sees one more card before deciding —
real, but not a board state I can assert against the card. Recorded rather than filed. *(The
absence of a continuation is also what makes `floor-it` **right** about the other half of the same
question: with no rival Unit on the board the prompt is skipped and the printed "Draw 1" still
happens. That is a confirmation, and it is in `test_confirmed_b03.py`.)*

**5.2 `take-control` versus `gorilla-arms`.** "A rival Unit steals 1 fewer Gig this turn" is a claim
about every path on which that Unit steals, and `steal_fewer` is read at exactly one site
(`steps.ResolveAttackStep`, the attack-steal count). `gorilla-arms` pushes an extra steal outside
that site. It works out: Gorilla Arms adds a fixed 1 and Take Control subtracts a fixed 1, so the
total is still one fewer than it would have been. No finding. (The *protection* half of the same
question — Gorilla Arms not consulting `stealable` — was filed separately as `AUD-gorilla-arms-1`.)

**5.3 `overwatch-panams-gift`'s `legal=lambda c: bool(c.hand())`.** The ability is not offered with
an empty hand, which narrows the legal action set beyond anything printed. It is unreachable as a
difference: with an empty hand the effect provably does nothing (`discard(1)` over an empty hand
resolves to `[]`, the defeat clause is guarded by `if picks`), and no card in the set reads whether
a *Gear* is spent, so there is no reason to pay 1 €$ for it. Recorded, not filed.

## B05 — Cross-cutting: replacement and permission effects

**6.1 Safety Override is applied after every prohibition in `steps.fight`.** `next_loss_defeats_winner`
sets `defeat_a` / `defeat_t` back to `True` after `no_defeat_in_fight`, the 0-power rule and
`next_fight_no_defeat` have cleared them — so Safety Override kills through Muamar Reyes's
"can't be defeated in a fight" and, in the `t_wins` case, through my own Reboot Optics (whose
`if defeat_t and …` guard never even runs, so the shield is not consumed either). It is the one
place in the engine where a permission is resolved after a prohibition. B02 §4.2 examined this and
declined to file on the grounds that "defeat the opposing rival Unit" reads as an *effect*
defeating the Unit rather than the fight doing it, and Reboot Optics' wording ("**it** doesn't
defeat the opposing friendly Unit") is, if anything, a weaker claim still. Recorded, not filed —
and named here so the third agent to find it does not file it either.

**6.2 Adrenaline Converter grants ADRENALINE to a face-up Legend host.** `kw_mod` returns true for
`inst == c.host()` with no test that the host is a Unit, and the card prints "this **Unit** has
ADRENALINE" over "(Equip to a friendly Unit **or face-up Legend**.)". I could not construct a board
where it is observable: `has_keyword(…, ADRENALINE)` is read in exactly one place,
`legal.attack_permission`, which is only ever called for a card on the field, and a Legend that
reaches the field did so via GO SOLO, which already carries its own attack permission. An
unobservable difference is not a printed-text finding.

**6.3 `play_cost` floors the sum of the deltas, not each one in turn.** Riot Shield's "+2 €$ to use
GO SOLO" and Nocturne's "-2 €$ … to a minimum of 1 €$" are added together before the floor is
applied, so a base cost of 2 would come out 2 where clause-at-a-time gives 3. The cheapest GO SOLO Legend in
the set costs 5, so `base - 2 >= 1` always and the floor never binds; and ordering questions like
this are settled deliberately by ruling 025. Not a finding.
