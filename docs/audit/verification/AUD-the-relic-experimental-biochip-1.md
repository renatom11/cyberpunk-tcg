<!-- Working record for AUD-the-relic-experimental-biochip-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# The Relic — Experimental Biochip  (`the-relic-experimental-biochip`)

- type: GEAR, colour: YELLOW, cost: 5, power: 3, RAM: 4
- keywords: none
- tags: ['ARASAKA', 'CYBERWARE']

## Printed text (byte-exact from data/cards/wnc.json)

```
(Equip to a friendly Unit or face-up Legend.)
DEFEATED: Play another Unit with cost 9 or less from your trash for free. Then, bottom-deck this Unit.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 721-735

@script("the-relic-experimental-biochip")
def _():
    def defeated(c):
        hosts = c.s.mod_values("was_host", c.inst)
        host = hosts[-1] if hosts else None
        cands = [i for i in c.trash() if c.is_type(i, UNIT) and (c.d(i).cost or 0) <= 9 and i != host]

        def after(c2, i):
            c2.play_free(i)
            if host is not None and c2.s.i_zone[host] is Zone.TRASH:
                c2.bottom_deck(host)
        c.choose(cands, after, prompt="Play a Unit from trash")
    return CardScript(on_defeated=defeated)
```

---

# The finding, and the test that failed

# AUD-the-relic-experimental-biochip-1

card: `the-relic-experimental-biochip`

claim: 'Then, bottom-deck this Unit' is skipped when the trash holds no eligible Unit

failing test: `tests/cards/audit/test_a08.py::test_the_relic_bottom_decks_the_host_with_no_unit_to_recur`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — The Relic, Experimental Biochip (`the-relic-experimental-biochip`)

Printed text (byte-exact):

```
(Equip to a friendly Unit or face-up Legend.)
DEFEATED: Play another Unit with cost 9 or less from your trash for free. Then, bottom-deck this Unit.
```

Script under audit: `src/cptcg/cards/sets/wnc.py:721-731`.

```python
def defeated(c):
    hosts = c.s.mod_values("was_host", c.inst)          # L724
    host = hosts[-1] if hosts else None                  # L725
    cands = [i for i in c.trash() if c.is_type(i, UNIT) and (c.d(i).cost or 0) <= 9 and i != host]   # L726

    def after(c2, i):
        c2.play_free(i)                                  # L729
        if host is not None and c2.s.i_zone[host] is Zone.TRASH:   # L730
            c2.bottom_deck(host)                         # L731
    c.choose(cands, after, prompt="Play a Unit from trash")        # L732
```

## 1. "(Equip to a friendly Unit or face-up Legend.)"

Reminder text for the Gear type; `docs/rules.md` ("Gear — pay its cost and equip it to a friendly
Unit or Legend") and `legal.gear_hosts` handle equipping generically. No script line is needed and
none is present. **Match.**

## 2. "DEFEATED:" — the trigger, and what "this Unit" denotes

`docs/effects-authoring.md`: "Gear's `on_attack` / `on_defeated` fire when its *host* attacks / is
defeated." `ops.defeat` (ops.py:452-458) records `add_mod("was_host", gear, host)` for each attached
Gear and then pushes `Trigger.DEFEATED` for the Gear and for the host. The script registers
`on_defeated=defeated` and recovers the host from that mod (L724-725), taking the most recent entry.

Elsewhere in this set Gear text uses "this Unit" for the **host** (`adrenaline-converter`: "this
Unit has ADRENALINE"; `sandevistan`: "ready this Unit or Legend"; `dying-night-vs-pistol`: "if this
Unit is named V"). So on this card "this Unit" = the defeated host, and "**another** Unit" means a
Unit other than that host. The script's reading is consistent with that. **Match.**

Edge cases in the host lookup are handled sanely: a Legend host is removed from the game rather than
trashed (ruling 034, `ops.move` L188-190), so the `Zone.TRASH` guard at L730 correctly skips the
bottom-deck; `Zone` is an `IntEnum`, so the `is` comparison is valid and matches the idiom used
throughout `core/`.

## 3. "Play another Unit with cost 9 or less from your trash for free."

Requirements:
- **a** Unit — exactly one, not all. `c.choose(cands, ...)` picks one. Match.
- **another** — not the host. `i != host` in L726. Match.
- **Unit** — `c.is_type(i, UNIT)`. Match.
- **cost 9 or less** — `(c.d(i).cost or 0) <= 9`, inclusive, null cost treated as 0. Match.
- **from your trash** — `c.trash()` defaults to `self.player`, and `EffectCtx.player` is the owner of
  the Gear instance, i.e. the Relic's controller. Match.
- **for free** — `play_free` → `play_card(..., cost=0)` (effects.py:285-299). Match.
- **mandatory, not "may"** — `c.choose(...)` is called without `optional=True`, so no decline option
  is offered; with a single candidate the engine auto-resolves. Match.

## 4. "Then, bottom-deck this Unit."

Requirement: after the play, put the defeated host (this Unit) on the bottom of the owner's deck.
The clause carries **no condition of its own** — unlike "Then, *if you control a min Gig*, draw 1"
(Trust No One) or "Then, *if you control 3 or more Gigs with different values*, draw 1" (Zetatech
Faceplate). Nothing in the printed text makes it depend on the first sentence succeeding; "Then" is
sequencing, not "if you do".

Implementation: the bottom-deck lives **inside `after`**, the continuation of `c.choose` (L729-731).
`EffectCtx.choose` (effects.py:144-160) runs `otherwise` — here `None` — and returns immediately when
`vals` is empty:

```python
vals = list(values)
if not vals:
    if otherwise is not None:
        otherwise(self)
    return
```

So when the trash holds **no other Unit with cost 9 or less** (a common state: the host has only just
arrived in the trash, and it is excluded by "another"), the whole effect is a no-op and the host is
**never bottom-decked**, even though the printed "Then" clause is unconditional.

This is precisely the failure mode the engine's own docs call out as a bug class, in
`EffectCtx.adjust_up_to` (effects.py:370-380): "`after(ctx)` runs whatever happens — after the
adjustment, after a decline, and when no legal adjustment existed to offer — and is right for a
separate printed sentence with its own board condition… a second sentence hung off `cont` silently
never runs." The correct shape here is `c.choose(cands, after, otherwise=<bottom-deck the host>)`, or
hoisting the bottom-deck out of the continuation entirely.

**Mismatch** — direction: the script makes an unconditional clause conditional on the first sentence
having a legal target.

## 5. Ordering / secondary observations (not reported as the finding)

- L729-731 bottom-decks the host immediately after `play_free`, while the played Unit's own `PLAY`
  trigger is only queued as a stack step (`push_trigger` → `HookStep`). So the bottom-deck resolves
  before the revived Unit's PLAY effect. The printed order ("Play … Then, bottom-deck") is satisfied
  in the sense that the play happened first; this is a trigger-ordering nuance, not a clause error.
- The `Zone.TRASH` guard at L730 means a host pulled out of the trash by the revived Unit's effect is
  not bottom-decked, which is correct ("this Unit" must still be there to move).

## Verdict

One discrepancy: clause 4, "Then, bottom-deck this Unit", does not resolve when the first sentence
has no legal target.

---

# Skeptic 2 — told the finding is presumed wrong

# Attempt to kill AUD-the-relic-experimental-biochip-1 — FAILED (finding survives)

Card: `the-relic-experimental-biochip`
Printed text (byte-exact, data/cards/wnc.json):
`DEFEATED: Play another Unit with cost 9 or less from your trash for free. Then, bottom-deck this Unit.`

Observed: `tests/cards/audit/test_a08.py::test_the_relic_bottom_decks_the_host_with_no_unit_to_recur`
reports **XFAIL** (strict). Direct probe of the same board: after the host is defeated with an
empty trash, `s.i_zone[host] == 4` (`Zone.TRASH`), not `Zone.DECK` (`Zone.DECK == 0`). The host is
never bottom-decked. `s.mod_values("was_host", gear) == [2]`, so the host *is* identified — the
skip is not a misidentified host, it is the second sentence not running.

Cause, `src/cptcg/cards/sets/wnc.py:794-806`: `bottom_deck(host)` lives inside `after`, the
continuation of `c.choose(cands, after, ...)`. With `cands == []`, `EffectCtx.choose`
(`src/cptcg/core/effects.py:156-160`) returns immediately and only runs `otherwise` — which this
script does not pass. So the whole second printed sentence is unreachable whenever the trash holds
no *other* Unit with cost 9 or less.

## The five kills, tried and failed

1. **A ruling covers it.** It does not. `docs/rulings.md` has 41 rows; none touches Gear DEFEATED
   sequencing, "Then" clauses, or recursion. The usual suspects are all off-topic here: 012
   (BLOCKER redirect), 015 (GO SOLO slot), 019 (once-per-turn scope), 025 (payment order), 026
   (field limit), 030 (⊡ on Gear). Ruling 022 is the only one in the neighbourhood and it *defines*
   bottom-deck; it does not gate it. `RulesConfig` has no flag for this.

2. **The engine already handles it.** It does not, and worse: the engine already ships the exact
   mechanism the script declines to use. `choose(..., otherwise=...)` is documented as "If there is
   nothing to choose, `otherwise` runs immediately" (`core/effects.py:148-160`); `maybe(..., after=)`
   exists for the same reason ("how a printed sentence that follows a 'may' is sequenced without
   being made conditional on it", `core/effects.py:208-218`). Five scripts in `wnc.py` already pass
   `otherwise=`. Nothing in `core/ops.py`, `core/steps.py` or `core/legal.py` bottom-decks a
   defeated Gear host on its own — verified by probe above.

3. **Unreachable board.** The board is ordinary: a spent rival Unit wearing a Gear, an empty trash,
   attacked and defeated. Playing the Relic from hand puts nothing in the trash, so an empty (or
   Unit-free) rival trash on an early turn is routine. It is the *same* board as the passing
   `tests/cards/audit/test_confirmed_a08.py::test_the_relic_cannot_recur_its_own_host` and
   `tests/cards/test_units.py::test_the_relic_recurs_a_unit_and_bottom_decks_host`, minus the one
   card in the trash. Note the trash is not even empty at resolution time — it holds the host and
   the Gear; the host is excluded by "another", which is itself a confirmed, deliberate reading.

4. **Asserts an internal.** It asserts `s.i_zone[host] == Zone.DECK` — the printed outcome of
   "bottom-deck this Unit", using the same idiom as the two already-green Relic tests. Reviewable.

5. **Misreads a word.** Two words were candidates and both check out.
   - *"this Unit"* = the host. Gear in this set says "this Unit" for its host (`dying-night-vs-pistol`:
     "if this Unit is named 'V'"; `zetatech-faceplate`: "When this Unit or Legend is spent"). The
     reading is already pinned green by `test_the_relic_recurs_a_unit_and_bottom_decks_host`.
     Reading it as the recurred Unit would make the card "play a Unit for free, then bury it",
     which no test or script in the repo supports.
   - *"Then,"* = sequencing, not a condition. This set spells conditionality out as **"If you do"** —
     four printed cards do exactly that (e.g. "You may defeat a friendly Gear. **If you do**, draw 2.";
     "ATTACK: You may pay 2 €$. **If you do**, ..."). The Relic prints no "If you do" and no "if"
     at all, so the bottom-deck is unconditional. `docs/verification.md:32-40` states the project's
     own doctrine for this shape verbatim: "a card prints two sentences ... and the script
     implements it inside the *continuation* of the first — so declining the first sentence, **or
     having no legal way to perform it**, skips the second entirely", and the lint's docstring
     (`tests/cards/test_script_lints.py:306-319`) adds "'Then' sequences them rather than making
     the draw conditional". Six cards are already logged as open findings of this class in
     `TRAPPED_TAIL_CLAUSES_OPEN` — including the other Gear, `zetatech-faceplate`.

The Relic escapes the lint only because `TAIL_EFFECT` covers three phrasings (draw / discard / Call
a Legend for free) and `_COND` requires the tail sentence to start with "if" — the Relic's tail is
*unconditional*, which makes it a stronger instance of the same bug, not an excluded one.

## Verdict

Survives. Classification **B4-scope-or-condition**: `bottom_deck(host)` is implemented but gated on
an unprinted condition (that a Unit was actually recurred). The printed sentence carries no
condition, and the set's own "If you do" convention shows what a conditional tail looks like. The
one-line shape of a fix is to hang the bottom-deck off the sequence rather than the pick
(`otherwise=`/`after=`), the same remedy the six logged tail-clause findings need.
