<!-- Working record for AUD-kiroshi-optics-1. Agent-written; the repository's tests are the settled part, not this file. -->

# The card, as the blind reader saw it

# Kiroshi Optics  (`kiroshi-optics`)

- type: GEAR, colour: YELLOW, cost: 1, power: 1, RAM: 1
- keywords: none
- tags: ['CYBERWARE']

## Printed text (byte-exact from data/cards/wnc.json)

```
(Equip to a Unit or friendly face-up Legend.)
ATTACK: Look at a friendly face-down Legend. (Don't reveal it.)
```

## Implementation

```python
src/cptcg/cards/sets/wnc.py lines 715-720

@script("kiroshi-optics")
def _():
    return CardScript(on_attack=lambda c: c.choose(c.legends(faceup=False), lambda c2, l: c2.look_at(l),
                                                   prompt="Look at a face-down Legend"))
```

---

# The finding, and the test that failed

# AUD-kiroshi-optics-1

card: `kiroshi-optics`

claim: text allows equipping to any Unit (incl. rival); legal.gear_hosts offers friendly Units only

failing test: `tests/cards/audit/test_a08.py::test_kiroshi_optics_may_equip_to_any_unit`

---

# Skeptic 1 — blind re-derivation (never shown the finding)

# Blind audit — Kiroshi Optics (`kiroshi-optics`)

Printed text (byte-exact):

```
(Equip to a Unit or friendly face-up Legend.)
ATTACK: Look at a friendly face-down Legend. (Don't reveal it.)
```

Implementation (`src/cptcg/cards/sets/wnc.py:715-720`):

```python
@script("kiroshi-optics")
def _():
    return CardScript(on_attack=lambda c: c.choose(c.legends(faceup=False), lambda c2, l: c2.look_at(l),
                                                   prompt="Look at a face-down Legend"))
```

---

## 1. "(Equip to a Unit or friendly face-up Legend.)"

**Requires:** a host restriction at play time. Read literally, "friendly" modifies only the Legend
half, so the Unit half is unqualified — any Unit, rival Units included; Legends must be friendly and
face-up.

**Implements:** nothing card-specific. Hosts come from the engine's general rule,
`src/cptcg/core/legal.py:18-20` `gear_hosts()` = friendly Units on the field + friendly face-up
Legends (used by `legal.py:142` for the Play action and by `effects.py:288-295` `play_free`). There
is no per-card host hook anywhere in the engine (`CardScript.extra` has no equip key; nothing else
calls `gear_hosts`).

**Match:** matches for the Legend half exactly. The Unit half is narrower than a literal reading of
this line: the engine will not offer a rival Unit as a host.

I do **not** count this as the card's implementation error, for reasons that are all about the line
itself rather than about the engine being convenient:

- Every other parenthetical of this kind in the set reads "(Equip to a friendly Unit or face-up
  Legend.)" — adrenaline-converter, mandibular-upgrade, overwatch-panams-gift, riot-shield,
  sandevistan, satori-sword-of-saburo, tetratronic-rippler, the-relic-experimental-biochip,
  zetatech-faceplate. Kiroshi's line is the same words with "friendly" one noun to the right, i.e.
  a transcription scramble of the standard reminder, not a bespoke clause.
- It is reminder text: it restates the general Gear rule in rules.md ("Gear — pay its cost and equip
  it to a friendly Unit or Legend"), and reminder text restating a rule does not usually grant a new
  permission.
- The literal reading has no game meaning: the card is a +1 power body with an ATTACK trigger that
  looks at *your* face-down Legend. Equipping it to a rival's Unit would hand the rival power and
  make the look fire on the rival's attack. Nothing in the set does anything like this, and the
  engine has no notion of rival-hosted Gear at all (`view.py:56` and ruling 016 both assume a Gear's
  host is friendly).

Recorded as a data-text oddity worth a transcription re-check of card #61, not as a script defect.

## 2. "ATTACK:" — timing and who fires it

**Requires:** the effect fires when the equipped Unit attacks (Gear ATTACK triggers fire for the
host, per `docs/effects-authoring.md`), after the target is declared (ruling 023).

**Implements:** `on_attack=` on the CardScript. `steps.py:220-226` `attack_triggers()` pushes
`Trigger.ATTACK` for every Gear on the attacker and then for the attacker itself, and that runs from
`AttackDeclaredStep` (`steps.py:228-235`), i.e. after `DeclareTargetStep`. `ops.push_trigger`
(`ops.py:531-540`) dispatches index 2 of the hook tuple to `on_attack`.

**Match:** yes. Correct hook, correct ordering under ruling 023, fires for the host's attack.

## 3. "Look at a friendly face-down Legend."

Three things to check: *friendly*, *face-down*, *a* (exactly one), and mandatory-vs-may.

**Requires:** the Gear's controller looks at exactly one of their own face-down Legends; it is
mandatory when one exists (no "you may"); nothing happens when there are none.

**Implements:** `c.legends(faceup=False)`.
`EffectCtx.legends` (`effects.py:55-60`) defaults `player` to `self.player`, and `self.player` is
`s.i_owner[inst]` of the Gear instance (`effects.py:20-23`) — so the candidate list is the *gear
owner's* Legends, i.e. friendly. `s.legends()` (`state.py:214-216`) returns Legend-area cards
excluding Gear sharing the zone. The `faceup=False` filter keeps only slots with `i_faceup` false.

`c.choose(...)` with no `optional=` (`effects.py:143-176`): options are one Pick per candidate, no
decline option is appended, and the asking player defaults to `self.player` (the gear owner). So it
is a mandatory choice of exactly one, asked of the right seat. With an empty candidate list `choose`
returns immediately and, with no `otherwise`, does nothing — correct for "there is no friendly
face-down Legend".

Contrast with the two sibling cards, which read differently and are scripted differently:
`t-bug-amateur-philosopher` ("Look at **all** friendly face-down Legends") loops `for l in
c.legends(faceup=False)` (wnc.py:694-698); `arasaka-emergency-radioport` ("you **may** look at a
friendly face-down Legend") passes `optional=True` (wnc.py:1084). Kiroshi is neither "all" nor
"may", and is the plain single mandatory `choose`.

**Match:** yes on all four points — friendly side, face-down filter, exactly one, mandatory.

## 4. "(Don't reveal it.)"

**Requires:** the look is private — the chooser learns the identity, the rival does not.

**Implements:** `c2.look_at(l)` → `effects.py:407-409`: `s.i_known[inst] |= 1 << self.player` plus an
emit. Only the looker's bit is set (contrast `ops.call_legend`, `ops.py:547`, which sets `0b11` when
a Legend is actually flipped face-up). `view.legend_identity_known` (`view.py:120-126`) reads exactly
that bit, so the rival's view of the slot is unchanged and the slot stays face-down for the engine.

The continuation correctly uses the ctx it was handed (`c2`, not the enclosing `c`), as required by
`docs/effects-authoring.md`.

No `revealed=` is passed to `choose`, and that is right here: `revealed` pins what the *question*
showed the chooser before they answered (view.py:73-82 spells this out and names this exact case —
"Look at a face-down Legend ... is blind by design, and `effects.look_at` writes `i_known` once the
slot is actually seen"). The pick here is blind; the peek happens in the continuation.

**Match:** yes.

## 5. No continuation / no second sentence

There is no "then" clause on this card, so the cont-vs-after hazard documented on
`adjust_up_to` does not apply. Nothing is hung off the pick that should run when the pick is
impossible.

---

## Verdict

The ATTACK ability — side, count, face-down filter, mandatory-ness, privacy of the look, and trigger
timing — is implemented faithfully. The only thing I would flag is the printed equip parenthetical
(section 1), whose word order differs from every other Gear in the set; I read that as a
transcription slip in `data/cards/wnc.json` rather than a mis-implemented ability, and I am not
reporting it as the card's error.

---

# Skeptic 2 — told the finding is presumed wrong

# AUD-kiroshi-optics-1 — attempt to kill

**Verdict: KILLED** (route 5 — the finding misreads the word *friendly*; F, false positive).
No code should change: `legal.gear_hosts` (`src/cptcg/core/legal.py:18-20`) is already right for
Kiroshi Optics, as it is for the other sixteen Gear in MS01-WNC.

Test run: `XFAIL` (strict), failing exactly where the filer says — `Play(inst=0, host=11)` is not in
`main_menu`. So the engine does behave as reported. That proves what the engine does, not what the
card should do.

Printed text (`data/cards/wnc.json`, `"verified": true`):

```
(Equip to a Unit or friendly face-up Legend.)
ATTACK: Look at a friendly face-down Legend. (Don't reveal it.)
```

## The kill: the filer's own parse, applied consistently, contradicts the filer

The whole finding rests on one grammatical claim: in `(Equip to a Unit or friendly face-up
Legend.)` the single adjective *friendly* attaches to its own conjunct only, so the other conjunct
("a Unit") is unrestricted.

Apply that same rule to the nine Gear the filer counts as the template
(`adrenaline-converter`, `mandibular-upgrade`, `overwatch-panams-gift`, `riot-shield`,
`sandevistan`, `satori-sword-of-saburo`, `tetratronic-rippler`, `the-relic-experimental-biochip`,
`zetatech-faceplate`):

```
(Equip to a friendly Unit or face-up Legend.)
```

Conjunct-local *friendly* makes those read "a **friendly** Unit, or **any** face-up Legend" — i.e.
all nine may be bolted onto a **rival's face-up Legend**. `gear_hosts` forbids that too
(`[i for i in s.legends(player) if s.i_faceup[i]]`, own Legends only), and neither the a08 batch nor
any other audit batch has filed it: `grep -rn "rival face-up Legend" out/audit tests/cards/audit`
returns nothing of the kind, and batch a10 cites the same rule approvingly as settled law
(`tests/cards/audit/test_a10.py:62-64`: "Gear legally equips to a face-up Legend in the Legends
area (docs/rules.md, 'Gear — pay its cost and equip it to a friendly Unit or Legend';
core.legal.gear_hosts)").

So the finding reads the one *friendly* as **distributing** across the coordination on nine cards
and as **conjunct-local** on the tenth, choosing whichever parse makes that particular line differ
from the engine. That is not a scope difference in the text; it is an inconsistent parse.

The distributive reading is the one the corpus fixes, not a charitable guess:

* `docs/rules.md:73` states the general rule in the *same* one-*friendly*-over-a-coordination
  template: "**Gear** — pay its cost and equip it to a friendly Unit or Legend." Nobody, the filer
  included, reads that as "…or any Legend, including the Rival's". The template's semantics are
  therefore settled by the rulebook sentence the card lines paraphrase.
* The set writes modifiers this way elsewhere and means them to distribute:
  `panam-palmer-nomad-cavalry` — "if 5 or more **friendly** Units and/or Legends are equipped";
  `alt-cunningham-mother-of-daemons` — "When a **friendly** equipped Unit or Legend is spent".

## Why the line cannot grant an exception even on its own terms

Host legality is a **general rule**, not a Kiroshi ability. **7 of the 17 Gear in the set print no
equip line at all** (`mantis-blades` has empty text; `deadman-transmitter`, `dying-night-vs-pistol`,
`gorilla-arms`, `netwatch-netdriver`, `arasaka-emergency-radioport`, `zetatech-berserk` print
none) and they host exactly like the ten that do. The parenthetical is reminder text for
`rules.md:73` plus the face-up qualifier that view.py records as a general property of face-down
Legends ("it is never a legal Gear host (`legal.gear_hosts`)", `src/cptcg/core/view.py:56`).

Every parenthetical in MS01-WNC is of that kind — restating a rule ("(You may only Call a Legend
once per turn.)", ruling 041), a keyword ("(A Unit with Adrenaline can attack the turn it's
played.)"), or a default ("(Don't reveal it.)", "(Otherwise, keep it on the top of your deck.)").
Not one grants a capability the rules deny. When this set *does* legislate about equipping, it does
so in rules text, outside parentheses, and spells the restriction out:
`viktor-vektor-you-might-feel-a-little-pinch` — "Equip it only to another **friendly** Unit";
`panam-palmer-nomad-cavalry` — "Move a Gear from this Legend to an unequipped **friendly** Unit".
A set-unique licence to equip the Rival's board, expressed only by moving one word inside the
reminder line, is not how this set prints exceptions (cf. `yorinobu-arasaka-steel-dragon`, "It can
attack rival Units this turn"; `riot-shield`, "Rivals must pay +2 €$ to use GO SOLO").

## The wide reading also leaves the card's own second line undefined

Gear text is written from the host controller's seat — `sandevistan` "At the end of **your** turn,
ready this Unit or Legend", `dying-night-vs-pistol` "At the end of **your** turn … ready 2 Eddies",
`tetratronic-rippler` "search the top card of **your** deck", `arasaka-emergency-radioport` "**you**
may look at a friendly face-down Legend". On a rival host, *whose* turn, *whose* deck and *whose*
"friendly face-down Legend"? Nothing in `docs/rules.md` or the 41 rows of `docs/rulings.md` answers
it; `detonate` ("Defeat a **rival** Gear") and `river-ward` / `alt-cunningham` ("a **friendly**
equipped Unit") become undecidable as well. The finding resolves this only by pointing at
`c.player` in `effects.py` — a script internal, not printed text — and the engine's own
representation assumes it never happens (`ops._active`, `src/cptcg/core/ops.py:43`: "an instance
only ever sits in its owner's zones").

And the "coherent design" the finding asserts does not survive contact with `ops.power`
(`src/cptcg/core/ops.py:396-406`): equipped Gear power is added to the **host**, so the unique
option the wide reading creates is "pay 1 €$ to give a rival Unit +1 power, and get a look at one of
your own face-down Legends whenever *they* attack" — strictly dominated by equipping the same Gear
to your own Unit, which gets the identical trigger plus the power.

## The other four routes, for the record

1. **A ruling covers it.** No. 016 (no re-equipping), 017 (Gear can't be attacked), 031 (face-down
   Legends inert), 034 (Legend leaves play) all touch Gear but none settles *who may host*, and
   `RulesConfig` has only `gear_reequip` (`src/cptcg/core/config.py:52`). The kill does not need
   one.
2. **Engine handles it elsewhere.** No. `gear_hosts` is the single source, called from
   `legal.py:142` and `effects.EffectCtx.play_free` (`effects.py:301-308`); nothing else offers a
   host. The engine is consistent — and, per the parse above, correct.
3. **Unreachable board.** No. `Side(hand=["kiroshi-optics"], field=["psycho-squad"], eddies=9)` vs
   `Side(field=["corpo-security"])` is an ordinary main phase, and the deck is colour-legal
   (Blue + Yellow, RAM 1 each).
4. **Asserts an internal.** No. `Play(k, theirs) in options(s)` is a legal-move outcome, the right
   thing to assert for an equip-restriction clause. The test is sound; its premise is not.

## Disposition

`tests/cards/audit/test_a08.py::test_kiroshi_optics_may_equip_to_any_unit` should be deleted (not
un-xfailed), and the one-word transposition in the reminder line recorded as a transcription
variant of `(Equip to a friendly Unit or face-up Legend.)`. If anyone still wants it settled by
fiat rather than by parse, the place is a new row in `docs/rulings.md` ("one *friendly* in an equip
line governs both the Unit and the Legend"), not a change to `legal.gear_hosts`.
