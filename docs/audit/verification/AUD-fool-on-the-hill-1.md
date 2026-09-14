<!-- Working record for AUD-fool-on-the-hill-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Fool on the Hill  (`fool-on-the-hill`)

- type: PROGRAM, colour: GREEN, cost: 2, power: None, RAM: 3
- keywords: none
- tags: ['MERC']

## Printed text (byte-exact from data/cards/wnc.json)

```
Reveal the top 2 cards of your deck. A Rival chooses whether you add them to your hand or trash them. If you trash them, draw 2.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 139-158

@script("fool-on-the-hill")
def _():
    def play(c):
        from cptcg.core.ops import move
        top = c.top(2)
        if not top:
            return

        def decide(c2, keep):
            if keep:
                for i in top:
                    c2.add_to_hand(i)
            else:
                for i in top:
                    move(c2.s, i, Zone.TRASH)
                c2.draw(2)
        c.choose([True, False], decide, prompt="Rival: add to hand (yes) or trash (no)?", player=c.rival)
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-fool-on-the-hill-1

card: `fool-on-the-hill`

claim: 'Reveal the top 2 cards of your deck' is never implemented — the Rival makes the choice without being shown the cards

failing test: `tests/cards/audit/test_a02.py::test_fool_on_the_hill_reveals_the_top_two_to_the_chooser`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Fool on the Hill (`fool-on-the-hill`)

Printed text (byte-exact):

> Reveal the top 2 cards of your deck. A Rival chooses whether you add them to your hand or trash them. If you trash them, draw 2.

Implementation: `src/cptcg/cards/sets/wnc.py` lines 139-158 (`@script("fool-on-the-hill")`).

```python
def play(c):
    from cptcg.core.ops import move
    top = c.top(2)                                            # L1
    if not top:                                               # L2
        return                                                # L3

    def decide(c2, keep):                                     # L4
        if keep:                                              # L5
            for i in top:                                     # L6
                c2.add_to_hand(i)                             # L7
        else:                                                 # L8
            for i in top:                                     # L9
                move(c2.s, i, Zone.TRASH)                     # L10
            c2.draw(2)                                        # L11
    c.choose([True, False], decide, prompt="Rival: add to hand (yes) or trash (no)?",
             player=c.rival)                                  # L12
```

---

## 1. "Reveal the top 2 cards of your deck."

**Requires.** The top 2 cards of the *controller's* deck become visible information to both
players — in particular to the Rival, who is about to make a decision about them. The cards do
not change zone: they are shown, then either added to hand or trashed by the next sentence. If
the deck holds fewer than 2, only what is there is revealed.

**Implemented by.** L1 `top = c.top(2)` → `ops.top_cards` (`src/cptcg/core/ops.py:255`), which is
a pure read: `deck[-n:][::-1]`, top-first, no move, no bookkeeping. Nothing else in the script
touches visibility. The subsequent `c.choose(...)` at L12 is called **without** `revealed=`.

**Match: NO.** Selecting the cards is not revealing them. In this engine the only mechanism that
makes a hidden card visible to the player who is being asked a question is `Choice.revealed`:

- `EffectCtx.choose(..., revealed=...)` (`src/cptcg/core/effects.py:147-175`) — *"``revealed``
  names the instances this question has shown to the chooser — the top cards a peek looked at.
  Declare it whenever the effect read a card the chooser could not otherwise see."*
- `core/view.py:_pinned` (lines 150-161) returns `ch.revealed` only when `ch.player == me`, and
  `visible()` (line 141-142) treats a `Zone.DECK` instance as visible to `me` only if it is in
  `_pinned(s, me)`. `view.py:75-81` is explicit: *"A choice that declares nothing reveals
  nothing."* Anything not pinned is permuted by `determinize`, i.e. the chooser is not merely
  un-informed, the search agent actively resamples those two instances.

Empirically (scratch script, default pool, Fool on the Hill played by seat 0 over a known deck):

```
pending: PICK  player: 1  opts: (Pick((0,)), Pick((1,)))  revealed: ()
top insts: [6, 7]
pinned for 1: ()   knows_identity(1, i): [False, False]
worlds seen by rival across 25 determinizations: 4 distinct
```

So the Rival answers "add to hand or trash?" without having seen either card, and a search agent
sitting in that seat samples them freshly every rollout. The whole strategic content of the card —
the Rival must make an informed, usually painful, choice — is gone; the decision degrades to a
blind guess based only on the fact that two unknown cards are involved.

This is the house convention, not an invented requirement. The two other WNC cards that peek at
the top of the deck and then ask a question about what they saw both declare it:

- `tetratronic-rippler` (`wnc.py:1060-1063`): `top = c.top(1)` … `c.maybe(..., revealed=top, ...)`
- `river-ward-detective-on-the-hunt` (`wnc.py:1211-1212`): `top = c.top(2)` …
  `c.choose(top, ..., revealed=top, ...)`

and `EffectCtx.search_top` (`effects.py:277`) passes `revealed=tuple(cards)` with the comment
*"The peek is real"*. `tests/props/test_determinization.py:562` asserts exactly this property for
another card (*"the choice does not declare what it showed"*). Fool on the Hill is the one card
whose printed text contains the literal word **Reveal** and whose chooser is the *opponent* — the
one case where the declaration matters most — and it is the one that omits it.

Note the two cards where a missing `revealed` is *correct* and deliberate, for contrast:
`judy-alvarez-nothing-to-doubt` (`wnc.py:1428-1437`) adds the card to hand first, so it is
visible by zone ("reveal: it goes to hand either way"), and
`bootleg-black-sapphire-show` (`wnc.py:265`) sells the top card into the public Eddies area
(ruling 002). Neither applies here: with `keep=False` the cards are never in a zone the Rival can
see until *after* the decision, and even with `keep=True` they only become public after the
answer.

**Direction: missing.**

## 2. "A Rival chooses whether you add them to your hand or trash them."

**Requires.** (a) The *Rival*, not the controller, makes the decision. (b) It is a forced choice
between exactly two options — not a "may", and no third "do nothing" branch. (c) The choice is
all-or-nothing over both revealed cards ("them"), not card-by-card. (d) On "hand", the cards go to
the **controller's** hand ("*you* add them"), not the Rival's.

**Implemented by.** L12 `c.choose([True, False], decide, player=c.rival)`.

- (a) `player=c.rival`; `EffectCtx.rival` is `1 - self.player` and `self.player` is
  `s.i_owner[inst]`, the Program's controller, so the question is posed to the opponent. The live
  run confirms `pending.player == 1` when seat 0 plays the card. Match.
- (b) `optional` is not passed (defaults `False`), so no decline `Pick(())` option is appended
  (`effects.py:163-165`) and both options are always present. Match.
- (c) `decide` loops over all of `top` in one branch or the other. Match.
- (d) L7 `c2.add_to_hand(i)` → `ops.move(s, inst, Zone.HAND)`, and `move` (`ops.py:184`) resolves
  the destination as `owner = s.i_owner[inst]` — the cards are the controller's own deck cards, so
  they land in the controller's hand regardless of who answered. Confirmed by the run: after
  picking "yes", the two cards appear in p0's hand and p1's hand is empty. Match.
- Continuation hygiene: `decide` uses the `c2` it is handed for every mutation (per
  `docs/effects-authoring.md`, "The one rule"), closing over only the `top` instance ids, which are
  stable across clones. Match.

**Match: yes.**

## 3. "If you trash them, draw 2."

**Requires.** The draw is conditional on the trash branch actually being taken, it is 2 cards, and
it is the controller who draws. Ordering: the trash happens first, so the 2 drawn cards are the
*next* two, not the ones just trashed.

**Implemented by.** L8-L11. `c2.draw(2)` sits inside the `else` (trash) branch only — nothing
draws in the keep branch. `EffectCtx.draw` defaults `player` to `self.player`, and `c2` is a fresh
`EffectCtx` for the same inst, so `c2.player` is still the controller (not the Rival who answered
the question). L9-L10 trash before L11 draws.

Live run, deck bottom→top `[6th-street-recruits, chrome-fang, adrenaline-converter, psycho-squad,
animals-wrecker, chrome-reverie]`:

- pick "yes": p0 hand `[chrome-reverie, animals-wrecker]`, deck down to 4, trash holds only the
  Program itself. No draw. Correct.
- pick "no": p0 trash `[chrome-reverie, animals-wrecker, fool-on-the-hill]`, p0 hand
  `[psycho-squad, adrenaline-converter]` — the next two, not the trashed two — deck down to 2.
  Correct.

`move(c2.s, i, Zone.TRASH)` rather than `ops.discard` is right: `ops.discard` (`ops.py:264-266`)
emits a `"discard"` event, which is a hand event; `ops.trash_top` uses a bare `move` for exactly
this, and both peer cards above trash deck cards with `move`. Trash order is preserved top-first,
per ruling 022.

Deckout: if the trash empties the deck, `ops.draw` (`ops.py:223-236`) ends the game with the Rival
as winner. That is the correct reading of an unconditional "draw 2" and not a discrepancy.

**Match: yes.**

## 4. Unwritten clause: fewer than 2 cards in the deck / empty deck (L2-L3)

**Requires.** Nothing printed. With an empty deck there is nothing to reveal and nothing for the
Rival to choose between.

**Implemented by.** L2-L3 return early only when `top` is completely empty; with exactly 1 card
the Rival is still asked and the single card is added or trashed (then `draw(2)` decks you out).
Both readings are defensible and the early return is the safer one — asking a question with no
subject, then drawing 2 off an empty deck to lose the game, would be a worse reading of "if you
trash them". Not a discrepancy.

**Match: acceptable.**

---

## Verdict

Clauses 2, 3 and the empty-deck guard are faithful; I checked both branches on a live board and
the zone movement, the sidedness and the conditionality are all exactly what the text says.

The single discrepancy is clause 1: **"Reveal the top 2 cards of your deck." is not implemented.**
The script reads the two instances but never declares them on the `Choice`, so under
`core/view.py` the Rival — the player the card makes decide — is never shown them and a search
agent in that seat resamples their identities. The one-token fix is
`c.choose([True, False], decide, prompt=..., player=c.rival, revealed=top)`, matching
`tetratronic-rippler` and `river-ward-detective-on-the-hunt`.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-fool-on-the-hill-1 — attempted kill: FAILED (finding survives)

Card text (byte-exact, `data/cards/wnc.json`):
> Reveal the top 2 cards of your deck. A Rival chooses whether you add them to your hand or trash them. If you trash them, draw 2.

Test result: `XFAIL` (strict). `--runxfail` shows it dies on the last assertion,
`tests/cards/audit/test_a02.py:53` — "the Rival was not shown the top 2" — not on a crash and not
on the `s.pending.player == 1` line, so the sentence under test really is the reveal clause.

## Route 1 — a ruling deliberately covers it

No. None of docs/rulings.md 001-041 concerns revealing to a chooser; the six usual suspects
(012 BLOCKER redirect scope, 015 GO SOLO slot, 019 once-per-turn scope, 025 payment order,
026 field limit, 030 ⊡ on Gear) are untouched by this card. The only ruling that mentions
revealing is **002**, and it runs *against* the defence: "Selling requires revealing the card;
**both players saw it**." docs/rules.md line 181 defines the verb the same way — "sell a
sell-tagged card from hand: **reveal it to your opponent**". In this game's vocabulary a printed
"Reveal" is public, so the Rival being asked to decide is entitled to see the two cards.

## Route 2 — the engine already handles it

No. I checked every place it could live:

- `src/cptcg/core/effects.py:147-176` — `choose(..., revealed=)` is the declared mechanism, and
  its docstring is explicit: "Declare it whenever the effect read a card the chooser could not
  otherwise see; `core.view` pins exactly what is declared here."
- `src/cptcg/core/view.py:155-161` (`_pinned`) — "Nothing here guesses: a choice that declares
  nothing pins nothing." `knows_identity` for `Zone.DECK` is *only* `inst in _pinned(...)`.
- `src/cptcg/core/ops.py:255` `top_cards` is a pure slice of `s.z[...]`; it sets no flag. The only
  `i_known` write in ops.py is line 547 (`call_legend`).
- `src/cptcg/core/engine.py:78` merely copies `ch.revealed` through when a lazy menu is rebuilt.
- `core/steps.py`, `core/legal.py` contain no reveal handling at all.

The script at `src/cptcg/cards/sets/wnc.py:139-158` passes no `revealed=`, and its prompt
("Rival: add to hand (yes) or trash (no)?") names neither card. Sibling cards in the same file do
it correctly — `tetratronic-rippler` (line 1075) uses `c.maybe(..., revealed=top, prompt=f"Trash
{c.d(top[0]).name}?")`, the line-1224 script uses `c.choose(top, ..., revealed=top)`, and
`effects.search_top` (line 275-277) passes `revealed=tuple(cards)` with the comment "The peek is
real". So the capability exists and this card alone skips it.

Nor is this the over-hiding the module says it tolerates. `core/view.py` lists exactly two accepted
omissions (a card bottom-decked from a public zone; a peek with no choice left open) and then says:
"**The one case that *is* modelled is the peek that is still open**." That is precisely this case —
the choice is pending when the information is needed. The consequence is not confined to the AI
mask: `src/cptcg/web/view.py:94` sets a card's `"name"` to `None` unless `knows_identity` allows it,
so a human Rival in the browser is asked this question with two blank cards.

## Route 3 — unreachable board

No. `Side(hand=["fool-on-the-hill"], eddies=9, deck=["floor-it", "psycho-squad"])` vs `Side()` is a
late-game position: a 2-card deck and an empty rival deck are ordinary, nothing is over the field
limit, no keyword is abused, and the assertion is read before any draw could deck anyone out.

## Route 4 — asserts a script internal

No — the opposite. `view.knows_identity` is the repo's own designated reviewable predicate for this
question. `tests/cards/audit/test_confirmed_a08.py:30-33` says so in as many words: asserted
"through `view.knows_identity`, which is the same question the redaction layer asks ... rather than
through the `i_known` bitmask, which is an engine internal and would make this test unreviewable."
The test never inspects `Choice.revealed` or the closure; it asks what seat 1 may legitimately see.

## Route 5 — misreads a word

No. "Reveal" is public by rules.md line 181 and ruling 002; "A Rival chooses" correctly makes seat 1
the chooser (the script gets that part right, `player=c.rival`); "the top 2 cards of your deck"
matches `c.top(2)` and ruling 022's deck orientation. Every word lines up; only the first verb has
no implementation.

## Verdict

Survives. Classification **B2-missing-clause**: the printed sentence "Reveal the top 2 cards of your
deck" has no counterpart in the script. The minimal fix is the one the engine already expects —
`c.choose([True, False], decide, ..., player=c.rival, revealed=top)`, ideally with the two card
names in the prompt, matching `tetratronic-rippler`.
