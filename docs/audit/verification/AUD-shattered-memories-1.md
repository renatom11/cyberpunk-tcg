<!-- Working record for AUD-shattered-memories-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Shattered Memories  (`shattered-memories`)

- type: PROGRAM, colour: RED, cost: 4, power: None, RAM: 2
- keywords: none
- tags: ['BRAINDANCE']

## Printed text (byte-exact from data/cards/wnc.json)

```
Each player discards their hand and may draw 5.
If the total number of discarded cards equals the value of a friendly Gig, draw 2.
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 159-176

@script("shattered-memories")
def _():
    def play(c):
        from cptcg.core.ops import discard
        total = 0
        for p in (c.player, c.rival):
            hand = list(c.hand(p))
            total += len(hand)
            for i in hand:
                discard(c.s, i)
        vals = set(c.gig_values())
        for p in (c.player, c.rival):
            c.draw(5, player=p)                       # "may draw 5": always beneficial, auto
        if total in vals:
            c.draw(2)
    return CardScript(on_play=play)
```

---

# The finding, and the test that failed

# AUD-shattered-memories-1

card: `shattered-memories`

claim: 'may draw 5' is drawn unconditionally, so the Program can deck a player out against their will

failing test: `tests/cards/audit/test_a02.py::test_shattered_memories_draw_five_is_optional`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Shattered Memories (`shattered-memories`)

Printed text:

```
Each player discards their hand and may draw 5.
If the total number of discarded cards equals the value of a friendly Gig, draw 2.
```

Implementation: `src/cptcg/cards/sets/wnc.py` lines 159-176.

---

## 1. "Each player discards their hand"

**Requires:** both players (controller and rival) put their entire hand into the trash. Not optional
(no "may" attaches to the discard), not a chosen subset, not one side only. The Program itself is not
in hand while it resolves (ruling 035), so it is not among the discarded cards.

**Implements:** lines 163-168 —
```python
for p in (c.player, c.rival):
    hand = list(c.hand(p))
    total += len(hand)
    for i in hand:
        discard(c.s, i)
```
`c.hand(p)` is `s.zone(p, Zone.HAND)` and `ops.discard` is `move(..., Zone.TRASH)` + emit. Both sides,
whole hand, mandatory, snapshot taken with `list(...)` before mutating.

**Match:** yes. Controller-first ordering matches the active player resolving first; discarding the
controller's hand cannot change the rival's hand, so counting as it goes is safe.

## 2. "and may draw 5"

**Requires:** after discarding, **each player independently chooses** whether to draw 5. It is a "may",
and it is attached to "each player", so the rival makes their own decision about their own draw and the
controller makes theirs. Declining is a legal, and sometimes necessary, choice: `ops.draw`
(`src/cptcg/core/ops.py:223-236`) ends the game with `EndReason.DECKOUT` in favour of the opponent the
moment a draw is attempted from an empty deck, so a player holding fewer than 5 cards in deck loses
outright by drawing. The optionality is therefore load-bearing, not cosmetic — it is exactly the escape
hatch that stops a symmetrical wipe from being a one-sided kill.

**Implements:** lines 169-171 —
```python
for p in (c.player, c.rival):
    c.draw(5, player=p)                       # "may draw 5": always beneficial, auto
```
No `c.maybe(...)` / `c.choose(..., optional=True)` anywhere; `EffectCtx.draw` (effects.py:221) goes
straight to `ops.draw`. The inline justification ("always beneficial") is false given the deckout rule
above, and even where it is beneficial the decision belongs to each player, and in particular the
rival's decision belongs to the rival (a `maybe` here would need `player=p`).

**Match:** NO. The optional draw is implemented as a mandatory draw for both players. Concretely: rival
has 3 cards left in deck; controller plays Shattered Memories; both hands are trashed; the script forces
`draw(5)` on the rival, who mills out on the 4th card and loses the game immediately. Under the printed
text the rival simply declines and the game continues. The same forcing applies to the controller (a
controller with a thin deck cannot decline their own draw either), so the card can also kill its own
caster.

## 3. "If the total number of discarded cards ..."

**Requires:** the count is the number of cards discarded by sentence 1, summed over **both** players.

**Implements:** `total` accumulated at line 165 over both `p` in `(c.player, c.rival)`, before any draws.

**Match:** yes. Nothing between the discards and the test can change the count, and the draws happen
after the count is fixed.

## 4. "... equals the value of a friendly Gig"

**Requires:** true if *some* die in the **controller's own** Gig area shows a face value equal to the
total. Rival dice do not count.

**Implements:** line 169 `vals = set(c.gig_values())`, line 172 `if total in vals:`.
`EffectCtx.gig_values(player=None)` (effects.py:110) defaults to `self.player`, i.e. the controller, and
returns `[v for _, v in self.s.gig[p]]` — face values of friendly dice only. Existence test ("a Gig") is
the `in` on the set. Reading `vals` before the draws is harmless: drawing cards never changes dice.

**Match:** yes. Edge case worth noting and correctly handled: with no friendly Gigs the set is empty and
the condition is false, and a total of 0 (both hands empty) only pays off if a friendly die actually
shows 0, which no die can, so it correctly never triggers on an empty-hand total.

## 5. "draw 2"

**Requires:** the **controller** draws 2 — unconditionally once the sentence-3/4 condition holds. It is
not a "may", and it is not contingent on whether anyone took the optional draw in sentence 1; the
condition is about *discarded* cards only.

**Implements:** line 173 `c.draw(2)` — `player` omitted, so the controller. Inside `if total in vals:`
and nothing else.

**Match:** yes (subject to clause 2: because the draw-5 is forced, this line is reached in states the
printed card would not produce, but the line itself is faithful). One cosmetic note: if a deckout
`end_game` fired during the forced 5-draw the script still runs `c.draw(2)`; that only exists because of
the clause-2 defect and is not itself a separate reading of the text.

---

## Verdict

One discrepancy, in clause 2. The printed "may" — a per-player option on the draw 5 — is dropped and
both players are forced to draw. Because `ops.draw` loses the game on an empty deck, this is not a
cosmetic auto-resolution of a strictly-beneficial choice: it converts a symmetrical refill into a
potential forced loss for either player, and it takes the rival's decision away from the rival. The rest
of the card (mandatory two-sided hand discard, total across both hands, friendly-Gig value match,
controller draws 2) is implemented faithfully.

---

# Skeptic 2 — told the finding is presumed wrong

# Kill attempt — AUD-shattered-memories-1 — VERDICT: SURVIVES

Card: `shattered-memories`. Printed text (data/cards/wnc.json:2428):

> Each player discards their hand and may draw 5.
> If the total number of discarded cards equals the value of a friendly Gig, draw 2.

Test status: `XFAIL` (strict) — it fails exactly as the filer claims. I reproduced the outcome
directly: playing the Program with the Rival on a 2-card deck ends the game, `s.over = True`,
`winner = 0`, `reason = EndReason.DECKOUT (1)`.

I attempted all five kill routes and none of them lands.

## 1. A ruling deliberately covers it — NO

`docs/rulings.md` has 41 rows; none addresses optional ("may") effects, who owns a "may", or
auto-resolving a beneficial choice. `src/cptcg/core/config.py:27-67` (`RulesConfig`) has no flag for
it either, so there is nothing hashed into results that this behaviour could be an intentional
setting of.

The usual trap rulings do not reach it: 012 (BLOCKER redirect scope), 015 (GO SOLO slot), 019
(once-per-turn scope), 026 (field limit), 030 (⊡ on Gear) are all off-topic. The nearest miss is
**025** (payment order auto-resolved to cut branching), and it cuts against the kill twice over:
it is scoped in its own words to "Cost payment order when Eddies and Legends are both available",
and it is justified by "almost no strategic content ... no card ever reads the identity of a card
sitting in an Eddies area". Declining a draw that would otherwise lose you the game on the spot is
the maximum-strategic-content case, the opposite of 025's premise. Ruling 025 also records that the
web client *does* ask a human when there is more than one way to pay — i.e. the approximation is a
search-efficiency concession, not a statement that the choice does not exist.

Rulings that are on point support the filer: **020** (no hand size limit, so nothing forces a draw)
and `docs/rules.md` "Win conditions": *"**Deckout.** If you are required to draw a card but have no
cards left in your deck, your **Rival** immediately wins."*

## 2. The engine already handles it — NO

- `src/cptcg/core/ops.py:223-236` `draw()`: `if not deck: end_game(s, winner=1 - player,
  reason=EndReason.DECKOUT); return drawn`. No guard, no "draw as many as you can".
- `src/cptcg/core/effects.py:221-222` `EffectCtx.draw()` is a thin pass-through to `ops.draw`.
- Nothing in `core/steps.py` or `core/legal.py` intercepts a mid-resolution draw.
- The capability the script needs exists and is unused here: `effects.maybe`
  (src/cptcg/core/effects.py:208-214) takes `player=`, and `choose(..., player=c.rival)` is used
  ~20 lines above in the same file by `fool-on-the-hill` (src/cptcg/cards/sets/wnc.py:166). So the
  Rival *can* be asked; `shattered-memories` (wnc.py:183) simply calls `c.draw(5, player=p)` for
  both seats.

## 3. The board is unreachable — NO

`tests/conftest.py:75-102` `board()` builds a plain mid-game main phase. The only unusual element
is the Rival's 2-card deck, which is ordinary late-game state. I re-ran the same position with
`turn=15` as well as the test's default `turn=3`: identical result (`over=True`, winner 0,
DECKOUT), because nothing in the resolution path reads the turn counter. `eddies=9` is the suite-
wide `E = 9` convention and is only there to pay the cost 4. The phenomenon does not depend on any
artefact of the construction.

## 4. It asserts a script internal — NO

The assertion is `assert not s.over` — a game-outcome fact (did this card end the game?), the most
reviewable kind of printed-text assertion there is. It touches no continuation, tag, stack shape,
or private field.

## 5. It misreads the printed text — NO

"Each player discards their hand and may draw 5." — "Each player" is the subject of both coordinated
verbs ("discards ... and may draw"), so each player individually owns their own "may". The script's
own inline comment states the premise it relies on — `# "may draw 5": always beneficial, auto`
(wnc.py:183) — and that premise is false whenever a player has fewer than 5 cards left, by the
Deckout rule quoted above.

There is no alternative reading that rescues the code. If "may" were instead read as belonging only
to the controller, the script would be wrong in a *different* way (it draws 5 for the Rival with no
permission at all). Under either reading the implementation does not match the text.

Clause 1 ("discards their hand", incl. ruling 035 keeping the resolving Program out of the discard),
clause 3 (`total` across both hands vs `c.gig_values()` = friendly) and clause 4 (`c.draw(2)` for
the controller) are all correctly implemented; only the "may" is dropped.

## Conclusion

**Survives.** Classification **B4 (scope/condition — "may" implemented as "must")**. The fix is to
route each player's draw through `c.maybe(lambda c2: c2.draw(5, player=p), player=p, ...)` (or an
equivalent per-seat `choose(..., optional=True)`), keeping the existing discard, Gig-value check and
`draw(2)` untouched. Note the order dependency: the controller's own forced draw can also lose the
game on the spot, so both seats need the offer, and the "draw 2" rider must still key off `total`
computed before any draws.
