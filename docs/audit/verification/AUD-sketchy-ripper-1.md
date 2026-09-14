<!-- Working record for AUD-sketchy-ripper-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Sketchy Ripper  (`sketchy-ripper`)

- type: UNIT, colour: YELLOW, cost: 2, power: 0, RAM: 2
- keywords: none
- tags: ['GANGER', 'RIPPERDOC', 'SCAVENGER']

## Printed text (byte-exact from data/cards/wnc.json)

```
ATTACK: Search the top 3 cards of your deck. Reveal a Gear and add it to your hand. Bottom-deck the rest. (Units with power 0 don't steal Gigs.)
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 625-629

@script("sketchy-ripper")
def _():
    return CardScript(on_attack=lambda c: c.search_top(3, lambda i: c.is_type(i, GEAR), 0, 1))
```

---

# The finding, and the test that failed

# AUD-sketchy-ripper-1

card: `sketchy-ripper`

claim: 'Reveal a Gear and add it to your hand' is mandatory, but the script offers a decline (search_top lo=0)

failing test: `tests/cards/audit/test_a07.py::test_sketchy_ripper_must_take_the_gear_it_finds`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Sketchy Ripper (`sketchy-ripper`)

Printed text (byte-exact):

```
ATTACK: Search the top 3 cards of your deck. Reveal a Gear and add it to your hand. Bottom-deck the rest. (Units with power 0 don't steal Gigs.)
```

Implementation (`/home/user/cyberpunk-tcg/src/cptcg/cards/sets/wnc.py` lines 625-627):

```python
@script("sketchy-ripper")
def _():
    return CardScript(on_attack=lambda c: c.search_top(3, lambda i: c.is_type(i, GEAR), 0, 1))
```

Helper under audit: `EffectCtx.search_top` (`/home/user/cyberpunk-tcg/src/cptcg/core/effects.py` lines 256-277),
which calls `EffectCtx.choose_many` (lines 178-196), `ops.top_cards` (ops.py 255-257) and
`ops.bottom_deck` (ops.py 260-261).

## 1. "ATTACK:" — timing/trigger

Requires: the effect fires when this Unit attacks (ruling 023: after the target is declared, when
the attacker is spent).

Implemented by: `CardScript(on_attack=...)`, the engine's printed ATTACK hook per
`docs/effects-authoring.md`. No condition attached, so it fires on every attack the Unit makes.

Match: yes.

## 2. "Search the top 3 cards of your deck."

Requires: look at (only) the top 3 cards of the controller's own deck; the peek is private to the
controller.

Implemented by: `search_top(3, ...)` → `cards = self.top(3)` → `ops.top_cards(s, self.player, 3)`,
where `EffectCtx.player = s.i_owner[inst]`, i.e. this card's controller — "your deck", not the
rival's. `top_cards` returns the top-most `n` (fewer if the deck is short — a deck with 0-2 cards
degrades gracefully rather than erroring). The peek is declared to the view layer with
`revealed=tuple(cards)` on the choice, so the searcher (and only the searcher) knows all 3, which
is what `core/view.py` lines 75-80 and 154-161 require.

Match: yes.

## 3. "Reveal a Gear and add it to your hand."

Requires, clause by clause:

a. The card taken must be a Gear — a type restriction, not a tag or cost restriction.
b. Exactly one card ("a Gear", singular, no "up to", no "any number").
c. **Mandatory** when the top 3 contain at least one Gear. The sentence carries no "may", no
   "up to", no "any number" — the three optionality spellings this set actually uses elsewhere:
   - `viktor-vektor-sit-down-and-relax`: "Reveal **up to 2** Gears with cost 2 or less and add them
     to your hand" → scripted `lo=0, hi=2` (wnc.py 1186-1188).
   - `hanako-arasaka-in-a-gilded-cage`: "Reveal **any number** of cards ..." → scripted `lo=0, hi=4`
     (wnc.py 446-448).
   - `three-mouths-one-desire`: "Add 1 to your hand. **You may** add 1 more for each friendly min
     Gig" → scripted `lo=1, hi=1+len(min_gigs)` (wnc.py 179) — the mandatory part is `lo=1`.
   So within this set's own drafting conventions, plain "Reveal a Gear and add it to your hand" is
   the mandatory case and should be `lo=1, hi=1`.
d. It should be revealed (shown), not taken secretly.

Implemented by:
- (a) the predicate `lambda i: c.is_type(i, GEAR)` with `GEAR = CardType.GEAR`
  (`src/cptcg/cards/dsl.py` line 17) → `cands` in `search_top` line 260. Correct.
- (b) `hi=1` → at most one card added. Correct.
- (c) **`lo=0`** → `choose_many(cands, 0, 1, ...)` builds options for both the empty combination
  and each single Gear (effects.py line 184), so the controller may decline to take a Gear even
  when one is sitting in the top 3, and all 3 cards get bottom-decked instead. The printed text
  gives no such permission. **Mismatch.**
  Note that `lo=1` would be safe for the no-Gear case: `choose_many` clamps `hi = min(hi, len(vals))`
  then `lo = min(lo, hi)` (effects.py 182-183), and with `hi == 0` it runs the continuation with an
  empty pick list immediately — so "no Gear in the top 3" would still resolve to "bottom-deck all 3"
  with no illegal forced pick and no stuck choice.
  Strategic consequence is real, not cosmetic: this Unit has power 0 and attacks purely to trigger
  the search, and its controller may sometimes prefer to keep the Gear on top of the deck (it is
  bottom-decked either way here) or, more importantly, to avoid revealing a Gear / to keep hand
  size or a known deck top. Whether or not the decline is ever strong, offering it changes both the
  legal action set and the information the search agent explores.
- (d) "Reveal": handled the same way as every other search card in this engine — the top cards are
  marked `revealed` to the *chooser* only (effects.py 276-277); nothing broadcasts the added card
  to the rival. This is a systemic engine convention (Viktor and Hanako read identically and also
  say "Reveal"), not a card-specific deviation, so I do not treat it as this card's error.

## 4. "Bottom-deck the rest."

Requires: every one of the looked-at cards that was not added to hand goes to the bottom of the
deck (rules.md line 191: "put cards on the bottom of your deck in any order"). Not random order —
contrast Viktor, whose text says "in a random order".

Implemented by `search_top` lines 263-270: `rest = [i for i in cards if i not in picks]`, and since
`bottom_random` is left at its default `False`, each is bottom-decked with `ops.bottom_deck` in the
order seen. `rest` is computed from `cards` (all 3 looked at), not from `cands`, so non-Gear cards
are included. The engine fixes the bottom order instead of asking; that is the same approximation
every search card makes and the order of unknown deck cards is not a strategic decision here.

Match: yes.

## 5. "(Units with power 0 don't steal Gigs.)"

Requires: nothing card-specific — parenthetical reminder text of a general rule.

Implemented by the engine: `ops.steal_count` (`src/cptcg/core/ops.py` lines 427-428) — "Gigs stolen
by a Gig-area attack: 0 at power 0, one more per 10 power above that." The card's printed power is
0 in `data/cards/wnc.json`, so the rule applies without any script line.

Match: yes (correctly not scripted).

## Conclusion

One discrepancy: clause 3, the mandatory add. The printed text says "Reveal a Gear and add it to
your hand" with no optionality wording, but the script passes `lo=0`, making the add optional when
a Gear is present. The fix is `c.search_top(3, lambda i: c.is_type(i, GEAR), 1, 1)`.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-sketchy-ripper-1 — kill attempt: FAILED (finding survives)

Card: `sketchy-ripper` — "ATTACK: Search the top 3 cards of your deck. **Reveal a Gear and add it
to your hand.** Bottom-deck the rest. (Units with power 0 don't steal Gigs.)"

Script: `src/cptcg/cards/sets/wnc.py:681-683`
```python
return CardScript(on_attack=lambda c: c.search_top(3, lambda i: c.is_type(i, GEAR), 0, 1))
```
(the brief's "lines 625-629" is stale; the script is at 681-683 in the current tree.)

Test result: `XFAIL` (strict) — the engine fails as the filer claims.

I tried all five kill routes and none of them lands.

## 1. Is a ruling deliberately covering it? No.

I read all 41 rows of `docs/rulings.md`. None concerns search optionality, reveal, or the
minimum count of a "search N / add to hand" effect. The usual suspects are all about other
subjects: 012 BLOCKER redirect scope, 015 GO SOLO slot vacation, 019 once-per-turn scope,
025 payment order, 026 field limit, 030 the ⊡ symbol on Gear. 022 (deck order / "bottom-deck
puts cards on the bottom in any order") touches this card's third sentence only, and the script
gets that part right. There is no `RulesConfig` field for this and no recorded default, so there
is nothing here presumed deliberate.

## 2. Does the engine already handle it elsewhere? No — I ran the board and looked.

`EffectCtx.search_top` (`src/cptcg/core/effects.py:269-290`) passes `lo` straight through to
`choose_many`, which builds
`opts = tuple(Pick(c) for n in range(lo, hi + 1) for c in combinations(...))`
(`effects.py:188`). With `lo=0, hi=1` that is literally `(Pick(()), Pick((0,)))`. Probing the
audit test's own board confirms it:

```
PENDING prompt: Search   OPTIONS: (Pick(picks=()), Pick(picks=(0,)))   revealed: (2, 1, 0)
```

`Pick(())` — decline — is a legal action the engine hands to the player. Nothing in
`core/legal.py`, `core/ops.py` or `core/steps.py` prunes it; `legal_actions` just serves
`s.pending.options`. So the decline is real, not a display artefact.

The one defensible reason to write `lo=0` would be "the top 3 might contain no Gear, and `lo=1`
would then be unsatisfiable". That reason does not exist here: `choose_many` clamps first —
`hi = min(hi, len(vals)); lo = min(lo, hi)`, and `if hi == 0: cont(self, [])`
(`effects.py:183-187`). With zero Gears among the top 3, `lo=1` degrades to an automatic empty
resolution and the three cards bottom-deck normally. `lo=1` is safe.

## 3. Is the board unreachable? No.

`Side(field=["sketchy-ripper"], deck=["floor-it", "mantis-blades", "floor-it"])` vs
`Side(gig=[(4, 1)])`: a Unit that has been in play since a previous turn, a three-card deck late
in a game, and a Rival with one die in the Gig area. The attack is legal — ruling 009 only bars
attacking a Gig area holding **0** dice, and the card's own reminder text ("Units with power 0
don't steal Gigs") presumes a 0-power Sketchy Ripper attacking a Gig area. Ruling 010 confirms
0-power Units fight. The exact same board already ships in the non-audit suite at
`tests/cards/test_units.py:259-264`.

## 4. Does it assert a script internal? No.

The assertion is `s.i_zone[find(s, "mantis-blades")] == Zone.HAND` — a zone, which is exactly
what the printed sentence "add it to your hand" promises. No ctx, no lo/hi, no tag. And the test
correctly needs no follow-up `Pick`: with `lo=hi=1` and one candidate `choose_many` emits a
single option, and `docs/effects-authoring.md` ("A choice with a single option resolves
automatically") says that auto-resolves.

## 5. Does the finding misread the text? No — and the set's own vocabulary proves it.

"Reveal a Gear and add it to your hand" is a bare imperative with a singular article. The set
hedges explicitly whenever a search is optional or open-ended, and `wnc.py` tracks that hedge
exactly:

| card | printed hedge | script |
|---|---|---|
| Viktor Vektor | "Reveal **up to 2** Gears" | `search_top(5, ..., 0, 2)` — wnc.py:1237-1239 |
| Hanako Arasaka | "Reveal **any number** of cards" | `search_top(4, ..., 0, 4)` — wnc.py:498-500 |
| Three Mouths, One Desire | "**Add 1** to your hand." (then "You **may** add 1 more…") | `search_top(3, None, 1, 1 + len(c.min_gigs()))` — wnc.py:219 |
| Sketchy Ripper | *(no hedge)* | `search_top(3, ..., **0**, 1)` — wnc.py:683 |

Sketchy Ripper is the only unhedged one written with `lo=0`. And the identical construction on
another card is already scripted as mandatory: Sasha Yakovleva, "ATTACK: Reveal the top card of
your deck and add it to your hand", is `c.add_to_hand(top[0])` with no question at all
(wnc.py:1472-1479). The same verb phrase cannot be mandatory on Sasha and optional on Sketchy
Ripper.

Nor is the decline strategically empty, which would at least make it harmless: choosing between
a Gear in hand and a Gear on the bottom of the deck is a real decision (hand size is unlimited —
ruling 020 — but deck order and future draws are not), so offering the choice hands the player a
line the printed text does not grant.

## Verdict

Survives. `lo` should be `1`, not `0`, at `src/cptcg/cards/sets/wnc.py:683`. The existing
`tests/cards/test_units.py::test_sketchy_ripper_finds_gear` will need its now-superfluous
`do(s, Pick((0,)))` removed when the fix lands.
