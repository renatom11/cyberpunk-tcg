<!-- Working record for AUD-industrial-assembly-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Industrial Assembly  (`industrial-assembly`)

- type: PROGRAM, colour: RED, cost: 1, power: None, RAM: 1
- keywords: none
- tags: ['ARASAKA', 'BRAINDANCE']

## Printed text (byte-exact from data/cards/wnc.json)

```
Increase a Gig by up to 4. If you control a Gig with 8+ value, draw 1.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 347-356

@script("industrial-assembly")
def _():
    def play(c):
        def after(c2, _o, _i):
            if gigs_8plus(c2):
                c2.draw(1)
        c.adjust_up_to([c.player, c.rival], 1, 4, cont=after, prompt="Increase a Gig")
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-industrial-assembly-1

card: `industrial-assembly`

claim: the draw is nested in the adjust continuation, so when no increase is legal the separate 8+-value draw clause never runs

failing test: `tests/cards/audit/test_a04.py::test_industrial_assembly_draws_when_no_gig_can_be_increased`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Industrial Assembly (`industrial-assembly`)

Printed text (byte-exact):

```
Increase a Gig by up to 4. If you control a Gig with 8+ value, draw 1.
```

Implementation (`src/cptcg/cards/sets/wnc.py:347-356`):

```python
@script("industrial-assembly")
def _():
    def play(c):
        def after(c2, _o, _i):
            if gigs_8plus(c2):
                c2.draw(1)
        c.adjust_up_to([c.player, c.rival], 1, 4, cont=after, prompt="Increase a Gig")
    return CardScript(on_play=play)
```

Helpers read: `EffectCtx.adjust_up_to` / `choose` / `draw` / `gigs` (`src/cptcg/core/effects.py:355-375`,
`144-175`, `106-110`, `221-222`), `gigs_8plus` (`src/cptcg/cards/dsl.py:44`),
`ops.adjust_gig` (`src/cptcg/core/ops.py:484-495`).

---

## 1. "Increase a Gig" — timing and who resolves it

**Requires.** A PROGRAM with no printed trigger word: its text resolves on play (rules.md,
"Program — instantaneous. Pay its cost, resolve the effect, move it to the trash"). The controller
of the card makes the choice.

**Implements.** `CardScript(on_play=play)`. `adjust_up_to` → `choose(..., player=None)`, which asks
`self.player` (`effects.py:172`), and `EffectCtx.player = s.i_owner[inst]` (`effects.py:25`), i.e.
the caster. **Match.**

## 2. "a Gig" — which Gigs are eligible

**Requires.** "a Gig", unqualified. The set qualifies the side when it means one: "decrease a
**friendly** Gig" (Jackie Welles), "each **friendly** Gig with 8+ value" (Carnage, Octant). Bare
"a Gig" therefore means any Gig, either Gig area.

**Implements.** `owners=[c.player, c.rival]`, and the candidate loop walks
`self.gigs(o)` for both. Same as every other bare-"a Gig" card in the set
(`wnc.py:343, 605, 711, 947, 971, 1052, 1147, 1156, 1180`), while the one "friendly Gig" card passes
`[c.player]` (`wnc.py:1370`). **Match.**

## 3. "a" (exactly one die), not "all"

**Requires.** One Gig die is increased, not several.

**Implements.** `choose` over `(owner, index, amount)` triples picks exactly one triple, and `_do`
calls `adjust_gig` once. **Match.**

## 4. "by up to 4" — the legal amounts

**Requires.** An increase of 1, 2, 3 or 4 — an increase, never a decrease — and "up to" also permits
0 (decline). Ruling 037 (CR 6.4.4/6.4.5): a result that is not a face of the die fails, and "'Up to
N' effects let you pick a legal amount", so amounts that would run past the die's top face simply
must not be offered.

**Implements.** `lo=1, hi=4` → `for a in range(1, 5)`; `a != 0 and 1 <= v + a <= k` filters out
off-face results; `optional=True` adds the decline `Pick(())`. Verified live: with mine
`[(12,7),(4,2)]` and rival `[(6,3)]` the engine offers 9 adjustments + decline; with every die at its
top face it offers nothing. Sign and magnitude match the sibling cards (`-3,-1` for "Decrease … up to
3", `-1,1` for "Adjust … up to 1"). **Match.**

## 5. "If you control a Gig with 8+ value" — the condition

**Requires.** A state check on **your own** Gig area at the time the card resolves: at least one die
you control showing 8 or more.

**Implements.** `gigs_8plus(c2)` = `sum(1 for v in c2.gig_values(None) if v >= 8)`, and
`gig_values(None)` defaults to `self.player` = the caster, so only friendly dice count; truthiness of
the count = "at least one". Side and threshold are right, and it is evaluated on the continuation's
own ctx `c2`, per docs/effects-authoring.md. **Match** as far as *what* is tested.

## 6. "draw 1" — the effect

**Requires.** You draw one card.

**Implements.** `c2.draw(1)` → `ops.draw(s, c2.player, 1)`, the caster. **Match.**

## 7. Sentence 2 is an independent sentence, not a rider on sentence 1  — **MISMATCH**

**Requires.** "Increase a Gig by up to 4. **If** you control a Gig with 8+ value, draw 1." The second
sentence states its own condition and is not linked to the first by "Then," or by "If you do";
compare Trust No One ("Decrease a Gig by up to 3. **Then,** if you control a min Gig, draw 1.") and
Zetatech Faceplate ("… **Then,** if …"), which do link them, and Jackie Welles ("If **it** becomes a
min Gig"), which refers back to the die that changed. Industrial Assembly's condition mentions
nothing about the increase. So the 8+ check must be made when the card resolves, whether or not any
increase was actually made — including the "up to 4" = 0 case and the case where no legal increase
exists at all. Ruling 023 is the precedent that the printed wording governs over the engine's earlier
habit.

**Implements.** `after` is passed only as `cont=` to `adjust_up_to`, and `adjust_up_to` calls
`cont(c, o, i)` only from inside `_do`, i.e. only after a candidate triple was picked and applied;
`choose(..., optional=True)` is given no `otherwise=`, so the decline branch runs nothing
(`effects.py:166-171`), and when the candidate list is empty `choose` returns immediately with no
`otherwise` either (`effects.py:157-160`).

**Observed** (engine probe, not a repo test):

- Mine `[(10,10),(6,3)]`, rival `[(6,3)]`, player declines the increase → **no draw**, although a
  10-value Gig is controlled. Text: draw 1.
- Mine `[(12,12),(4,4)]`, rival `[(6,6)]` (every die on its top face, no legal increase) → the engine
  asks nothing and **no draw**, although a 12-value Gig is controlled. Text: draw 1.
- Mine `[(12,7),(4,2)]`, increase the d12 to 8 → draws 1. Correct.

**Effect of the bug.** The draw is silently gated on a non-zero increase. It costs the caster the
card exactly when the board already satisfies the printed condition and the increase is undesirable
(e.g. the only legal increases would hand value to the Rival, or every die is capped), and it also
makes the player's decline choice carry a hidden cost the card never printed.

**Note on scope.** Afterparty at Lizzie's (`wnc.py:337-344`) has the same two-sentence shape and the
same nesting, so this may be a house idiom rather than a one-card slip; either way, for *this* card
the printed text does not condition the draw on the increase happening.

---

## Verdict

Clauses 1-6 are faithful. The single discrepancy is clause 7: the script makes
"If you control a Gig with 8+ value, draw 1" conditional on an increase actually being applied, a
condition the printed text does not state.

---

# Skeptic 2 — told the finding is presumed wrong

# Kill attempt — AUD-industrial-assembly-1 (`industrial-assembly`)

Verdict: **SURVIVES**. I tried all five kill routes and none of them lands.

Printed text, byte-exact from `data/cards/wnc.json`:

    Increase a Gig by up to 4. If you control a Gig with 8+ value, draw 1.

Implementation (`src/cptcg/cards/sets/wnc.py:347-356`): the draw is hung off `cont=after`, the
hook that `adjust_up_to` runs **only when a die actually moved**.

## Route 1 — a ruling covers it: NO

None of the presumed-deliberate rows (012, 015, 019, 025, 026, 030) touches Gig adjustment.
The only nearby row is **ruling 037** ("Adjusting a Gig to a value not on its face ... the effect
fails — no change (CR 6.4.4, 6.4.5). 'Up to N' effects let you pick a legal amount"). 037 makes the
*first* sentence do nothing; it says nothing about the second sentence, and it is not a ruling that
a later sentence is conditional on an earlier one resolving. `docs/rules.md` has no text making a
second printed sentence contingent on the first. There is no ruling to hide behind.

## Route 2 — the engine already handles it: NO

`src/cptcg/core/effects.py:364-400` (`adjust_up_to`) builds `cands` only from amounts `a != 0` with
`1 <= v + a <= k`, so a d10 showing 10 produces an empty candidate list. `choose`
(`effects.py:156-160`) then runs `otherwise` and returns; `adjust_up_to` passes `otherwise=after`,
and this script supplies no `after` — so nothing runs at all. `ops.adjust_gig`
(`src/cptcg/core/ops.py:484-495`) likewise returns early. `core/steps.py` and `core/legal.py`
contain no post-effect rescue path for an unresolved clause.

The opposite of a rescue: the engine's own API docstring names this exact bug.
`effects.py:371-380` says `cont` "runs only when a die actually moved, and is right for a clause
that talks about *that* Gig", while `after` "runs whatever happens ... and is right for a separate
printed sentence with its own board condition", and adds: "Getting that backwards is invisible and
common ... a second sentence hung off `cont` silently never runs. Six cards in this set were
written that way." Industrial Assembly's second sentence is *"If you control a Gig with 8+ value"* —
a board condition, not a statement about the adjusted die — so it is squarely the documented misuse.

## Route 3 — unreachable board: NO (though the filed test has a cosmetic defect)

The filed test leaves `fixer` at its default full `DICE = (4, 6, 8, 10, 12, 20)`
(`src/cptcg/core/enums.py:58`) while also putting a d10 in the Gig area, i.e. seven dice for a
player who owns six (`docs/rules.md:13`). That is a nit, not a kill: I reran the same scenario on a
strictly six-dice board (`gig=[(10, 10)]`, `fixer=[4, 6, 8, 12, 20]`) and it fails identically —
hand 0, expected 1.

The bug is also not confined to the "no legal increase" corner. On an unimpeachable board with two
Gigs — d10 at 10 and d4 at 2 — the adjust *is* offered, the player declines the "up to 4" (which
"up to" permits, and which the engine offers explicitly as `optional=True`,
`effects.py:397`), the player still controls a Gig with value 10, and the draw still does not
happen. So even removing the ruling-037 corner entirely, the clause is skipped.

## Route 4 — asserts an internal: NO

The test asserts `s.gig[0] == [(10, 10)]` and `len(s.zone(0, Zone.HAND)) == 1` — a printed Gig value
and a hand size. No script internals, no hook names, no engine state.

## Route 5 — misreads the text: NO

"Increase a Gig by up to 4." and "If you control a Gig with 8+ value, draw 1." are two sentences.
The second has no "If you do", no "it", no back-reference of any kind; its condition is a
controlled-board condition evaluated on its own. The d10 at 10 satisfies it
(`gigs_8plus`, `src/cptcg/cards/dsl.py:44`, counts own Gigs with value >= 8). Reading the draw as
gated on a die having moved adds a condition the card does not print.

## Observed

`tests/cards/audit/test_a04.py::test_industrial_assembly_draws_when_no_gig_can_be_increased`
XFAILs (strict), and with `--runxfail`: `assert 0 == 1` on hand size. The engine does what the filer
says, and nothing in the card text, `docs/rules.md`, or `docs/rulings.md` justifies it.

Correct fix shape: pass the draw as `after=` (which runs after an adjustment, after a decline, and
when nothing was offerable) rather than `cont=`.
