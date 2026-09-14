<!-- Working record for AUD-bonnie-and-clyde-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Bonnie and Clyde  (`bonnie-and-clyde`)

- type: PROGRAM, colour: RED, cost: 3, power: None, RAM: 3
- keywords: none
- tags: ['BRAINDANCE']

## Printed text (byte-exact from data/cards/wnc.json)

```
Defeat a rival Unit with power 4 or less. You may defeat 2 instead if a Rival controls at least 2 Gigs more than you.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 22-30

@script("bonnie-and-clyde")
def _():
    def play(c):
        n = 2 if len(c.gigs(c.rival)) >= len(c.gigs()) + 2 else 1
        c.choose_many(c.rival_units(power_le(c, 4)), 0, n,
                      lambda c2, us: [c2.defeat(u) for u in us], prompt="Defeat up to %d" % n)
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-bonnie-and-clyde-1

card: `bonnie-and-clyde`

claim: choose_many(lo=0) lets you defeat nothing; the printed 'may' covers only the second Unit

failing test: `tests/cards/audit/test_a01.py::test_bonnie_and_clyde_defeat_is_not_optional`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Bonnie and Clyde (`bonnie-and-clyde`)

Printed text (byte-exact):

```
Defeat a rival Unit with power 4 or less. You may defeat 2 instead if a Rival controls at least 2 Gigs more than you.
```

Implementation (src/cptcg/cards/sets/wnc.py:22-30):

```python
@script("bonnie-and-clyde")
def _():
    def play(c):
        n = 2 if len(c.gigs(c.rival)) >= len(c.gigs()) + 2 else 1
        c.choose_many(c.rival_units(power_le(c, 4)), 0, n,
                      lambda c2, us: [c2.defeat(u) for u in us], prompt="Defeat up to %d" % n)
    return CardScript(on_play=play)
```

The card is a PROGRAM with no timing keyword, so the whole text is its on-play effect; `CardScript(on_play=play)` is the right hook.

## 1. "Defeat a rival Unit with power 4 or less."

**Requires.** On resolution, exactly one Unit controlled by the Rival whose current power is 4 or
less is defeated. The count is "a" — one, not all. The side is rival only. The effect is
**mandatory**: there is no "may" on this sentence, so with at least one legal target the
controller must defeat one. Only when no rival Unit has power ≤ 4 does nothing happen.

**Implements.** `c.rival_units(power_le(c, 4))` builds the candidate set;
`c.choose_many(cands, 0, n, ...)` asks the question; the continuation runs `c2.defeat(u)` per pick.

**Check — side/filter/effect: match.** `EffectCtx.rival_units` (effects.py) is
`self.units(self.rival, pred)`, i.e. Units in the rival's FIELD only — correct side, and it does
not sweep in friendly Units or Legends. `power_le(c, 4)` (cards/dsl.py) is `c.power(u) <= 4`,
which routes to `ops.power` — printed power plus Gear, temp mods and static auras, floored at 0
(ruling 029). "4 or less" is `<= 4`, inclusive; correct. `c.defeat` → `ops.defeat`, the normal
defeat path (replacements, DEFEATED triggers, GO SOLO removal) — correct.

**Check — mandatory vs optional: MISMATCH.** The lower bound passed to `choose_many` is `0`.
In `EffectCtx.choose_many` the option set is
`tuple(Pick(c) for n in range(lo, hi + 1) for c in combinations(range(len(vals)), n))`,
so `lo = 0` puts the empty pick `Pick(())` on the menu. With at least one legal target the
controller is therefore allowed to resolve Bonnie and Clyde and defeat **nothing**. The printed
sentence is an unconditional "Defeat a rival Unit ...", with no "may" and no "up to".

The set's own convention confirms the reading of `lo`:

* `royce-dont-call-me-simon` — printed "Defeat a rival Unit with power 2 or less. If you have
  more ★ ..., defeat a rival Unit with power 3 or less instead." — is written as
  `defeat_one(c, c.rival_units(power_le(c, 3 if c.more_cred() else 2)))`, and `defeat_one`
  (dsl.py) defaults to `optional=False`, i.e. no decline option. Same sentence shape as clause 1
  here, implemented as mandatory.
* `we-gotta-live-together` — printed "Play **up to** 2 Units ... from your trash for free." — is
  the one written as `choose_many(..., 0, 2, ...)`. So `lo = 0` is the house spelling of
  "up to N", i.e. of text that explicitly permits zero. Bonnie and Clyde's text never says
  "up to"; the script's own prompt string ("Defeat up to %d") is text the card does not have.

Nothing in docs/rules.md or docs/rulings.md makes targeted defeats optional; `choose` /
`choose_many` already handle "no legal target" by resolving with nothing (see clause 4), so
`lo = 0` is not needed to cover the empty-board case.

Correct spelling would be `choose_many(cands, 1, n, ...)` (`choose_many` itself clamps
`lo = min(lo, hi)`, so an empty or single-target board still behaves).

**Verdict: mismatch — the script grants a decline ("defeat 0") option the printed text does not.**

## 2. "You may defeat 2 instead ..."

**Requires.** When the condition in clause 3 holds, the controller *may* defeat two rival Units
with power 4 or less instead of one. "May ... instead" makes the upgrade optional: with the
condition met the controller chooses between the printed one and the upgraded two. It does not
make the base effect optional — the choice is 1 or 2, not 0, 1 or 2. "2" is a maximum bounded by
the legal targets available: with only one legal target, one is defeated.

**Implements.** `n = 2 if <cond> else 1`, then `choose_many(cands, 0, n, ...)`.

**Check.** The upper bound is right: with the condition met the menu contains every 2-subset, so
"defeat 2" is reachable, and every 1-subset, so the "may" (decline the upgrade, still defeat one)
is reachable. `choose_many` clamps `hi = min(hi, len(vals))`, so with a single legal target the
effect degrades to defeating that one — correct for a maximum. Both picks are defeated in one
continuation (`[c2.defeat(u) for u in us]`) on the ctx it is handed (`c2`), which follows the
authoring rule in docs/effects-authoring.md.

The *lower* bound is again wrong, but that is the same defect already recorded in clause 1
(zero is selectable in both the `n = 1` and `n = 2` branches) rather than a separate one.

**Verdict: the optional upgrade itself matches; the shared `lo = 0` defect is clause 1's.**

## 3. "... if a Rival controls at least 2 Gigs more than you."

**Requires.** The condition counts **Gigs** — dice in a Gig area — not Street Cred (the sum of
faces, docs/rules.md "Gig area"; ruling 038 treats Cred separately). It compares the Rival's
count to the controller's: rival_count − my_count ≥ 2. Checked on resolution.

**Implements.** `len(c.gigs(c.rival)) >= len(c.gigs()) + 2`.

**Check: match.** `EffectCtx.gigs(player)` returns `s.gig[player]`, the list of `(sides, value)`
dice in that player's Gig area, so `len` is a count of dice, not a Cred total — right quantity.
`c.gigs()` with no argument defaults to `self.player`, the card's controller, and `c.rival` is
`1 - self.player` — right direction (rival ahead of you, not you ahead of the rival). "At least 2
more" is `rival >= mine + 2`, inclusive at exactly 2 — correct, and it is byte-for-byte the same
expression `we-gotta-live-together` uses for the same printed wording ("If a Rival controls at
least 2 more Gigs than you"). The condition is evaluated inside `play`, i.e. when the Program
resolves, which is the right timing; it is not re-read after the choice, which matters not at all
since nothing between the question and the defeats can change a Gig count.

**Verdict: match.**

## 4. Continuation / no-legal-target behaviour

**Requires.** With no rival Unit at power ≤ 4, the card simply does nothing; there is no later
sentence conditional on the defeat having happened, so nothing else is owed.

**Implements.** `choose_many` with an empty `vals` computes `hi = min(n, 0) = 0` and calls
`cont(self, [])` immediately — the list comprehension defeats nothing and returns. No stray
follow-up effect.

**Verdict: match.**

## 5. Everything the card does *not* say

No friendly-side effect, no "all", no draw, no Gig manipulation, no cost modifier, no lingering
mod. The script adds none of those (`CardScript(on_play=play)` only). The `self_cost` hook that
the neighbouring `we-gotta-live-together` and `carnage-at-the-colosseum` carry is correctly absent
here — Bonnie and Clyde's Gig-count condition modifies the *effect*, not the cost.

**Verdict: match.**

## Conclusion

One discrepancy, in clause 1: `c.choose_many(..., 0, n, ...)` makes a printed-mandatory defeat
optional. The text reads "Defeat a rival Unit with power 4 or less" (with an optional upgrade to
2), but the script offers the controller a legal "defeat none" pick whenever at least one rival
Unit with power ≤ 4 is on the board. The fix is `lo = 1`.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-bonnie-and-clyde-1 — kill attempt: FAILED. The finding survives.

Verdict: **survives**, class **B4** (scope of the printed "may": a decline option exists where the
text allows none). I tried all five kill routes and none of them lands.

## The claim under test

Printed text (`data/cards/wnc.json`, id `bonnie-and-clyde`, byte-exact):

> Defeat a rival Unit with power 4 or less. You may defeat 2 instead if a Rival controls at least
> 2 Gigs more than you.

Script, `src/cptcg/cards/sets/wnc.py:24-27`:

```python
n = 2 if len(c.gigs(c.rival)) >= len(c.gigs()) + 2 else 1
c.choose_many(c.rival_units(power_le(c, 4)), 0, n, ..., prompt="Defeat up to %d" % n)
```

`lo=0`, so per `src/cptcg/core/effects.py:188` the option set is
`Pick(c) for n in range(lo, hi+1) for c in combinations(...)` — the size-0 combination is always
included. That is a decline.

## Route 1 — a ruling deliberately covers it. NO.

I read all 41 rows of `docs/rulings.md`. None addresses mandatory-vs-optional effect resolution,
target counts, or declining a target. The six presumed-deliberate rows are all off-topic here:
012 (BLOCKER redirect scope), 015 (GO SOLO slot vacation), 019 (once-per-turn scope), 025 (payment
order), 026 (field limit), 030 (⊡ on Gear). The nearest miss is **037**, whose tail reads "'Up to N'
effects let you pick a legal amount" — but 037 is about setting a Gig to a value not on its face,
and its sentence is conditioned on the card printing *"up to N"*, which this card does not. It is
not a licence to insert "up to" into a card that prints a bare imperative.

`docs/rules.md` grants optionality only where a card or keyword prints "you may" (lines 91-92, 118,
132, 189). There is no printed "may" on the first sentence.

## Route 2 — the engine handles it elsewhere. NO.

I checked the whole path. `EffectCtx.choose_many` (`core/effects.py:177-196`) builds the options and
hands them straight to `ask(Choice(...))`; nothing downstream filters them. `core/legal.py` has no
`Pick` handling at all (its only option builders are `gig_die_options` and `ability_options`,
lines 12 and 74) — it never prunes a pending `Choice`'s `options`. `core/steps.py`/`core/ops.py`
apply whichever `Pick` arrives. So the empty pick reaches the player as a real, selectable action,
and an agent that takes it defeats nothing. Nothing anywhere forces a non-empty pick.

## Route 3 — the test board is unreachable. NO.

`Side(hand=["bonnie-and-clyde"], eddies=E)` vs `Side(field=["corpo-security"])`. Corpo Security is a
cost-2 Green Unit with power 2 (`data/cards/wnc.json` #76), so it is a legal `power_le(c, 4)` target;
Bonnie and Clyde costs 3 and `E` covers it. Both Gig areas are empty, so `0 >= 0 + 2` is false and
`n = 1` — the ordinary, un-upgraded mode of the card. This is a turn-3 board, not a contrivance.

## Route 4 — the test asserts a script internal. NO.

The assertion is `s.i_zone[find(s, "corpo-security")] == Zone.TRASH` — a printed-text outcome
(the rival Unit is defeated), in exactly the form `docs/effects-authoring.md` prescribes for card
scenarios. It names no prompt string, no `lo`/`hi`, no option count. (Contrast the *existing* test
`tests/cards/test_programs.py:27`, which does assert `max(len(o.picks) ...) == 2` — that one is
internal-ish, but it is not the test under review.)

## Route 5 — the finding misreads a word. NO.

The card is two sentences. The first, "Defeat a rival Unit with power 4 or less.", is a bare
imperative with no modal. The second, "You may defeat 2 **instead**", attaches its "may" to the
substitution: "instead" presupposes the thing being substituted for, so declining the may leaves
the first sentence standing, not cancelled. There is no reading on which the whole effect is
optional. With `n = 1` there is nothing for a "may" to govern at all, yet the script still offers
a decline.

## What actually killed my kill: the set's own templating

This set marks optionality explicitly, and the engine's own convention matches it one-for-one.
Sixteen WNC cards print "up to N" (6th-street-recruits, we-gotta-live-together, saul-bright-
stormrider, pepe-najarro-working-doubles, trust-no-one, ...). Every other `choose_many(..., 0, ...)`
in `src/cptcg/cards/sets/wnc.py` is one of them:

- line 235 `we-gotta-live-together` — "Play **up to 2** Units with cost 3 or less" → `0, 2`
- line 653 `pepe-najarro-working-doubles` — "ready **up to 2** MERC Legends" → `0, 2`
- line 843 `saul-bright-stormrider` — "ready **up to 3** friendly Units" → `0, 3`

and the one card with a mandatory count uses a non-zero `lo`:

- line 583 — `choose_many(c.rival_units(), min(n, ...), min(n, ...), ...)`, `lo == hi`.

So `lo=0` in this codebase means the card printed "up to". Bonnie and Clyde is the sole `lo=0` site
whose card does not. The script's own prompt, `"Defeat up to %d"`, quotes wording that is not on the
card — the tell the filer identified. That is a slip, not a convention, and not a ruling.

## Scope of the surviving finding

Only `lo` is wrong. Clause 2 (`power_le(c, 4)`), clause 3 (`hi = n`, so 1-or-2 is genuinely offered
when the condition holds — the real "may"), and clause 4 (the Gig comparison) are all correct.
Correct bounds are `lo = min(1, len(cands))`, `hi = n`; with no legal target `choose_many` already
clamps `hi` to 0 and calls the continuation with `[]` (`core/effects.py:183-187`), so the fix cannot
break the empty-board case.
