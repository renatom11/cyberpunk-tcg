# Stage 0 — rules questions parked for the owner

Items skipped because answering them would guess at a rule or alter the game. Each says what is
blocked on it. (Answered 2026-09-21 in the session: Kiroshi Optics host scope; Goro *Losing His
Way* with an empty Legends area.)

- **Spend triggers raised by paying for a Call.** The FAQ settles the play ("After. Play the card
  first") and the activated effect ("After. Resolve the activated effect first") but says nothing
  about paying 1 €$ for a Call with a Legend that hosts a spend-trigger Gear. Implemented by
  analogy with the play (Call first, then the spend triggers, ordered with the CALL trigger when
  the controller has a choice). Nothing blocked; say if the analogy is wrong.
- **Two copies of one card in an ordering group.** Two Deadman Transmitters on one host (FAQ: "choose
  one of them") and, more generally, identical triggers of one card are collapsed to one choice, as
  ruling 046 already does. Nothing blocked.

**Q1 and Q2 above — SETTLED (owner rulings 054, 055).**

## Q3 — does a Gear's ⊡ ability spend the Gear or its host? — SETTLED (owner ruling 056)

Raised by the play-around proposals (Overwatch: Panam's Gift). The engine spends the **Gear instance** (`legal.ability_options` / `engine.activate` test and spend `inst`, the Gear), so a Gear's ⊡ can be used while its host is spent, and using it leaves the host ready to BLOCK afterwards. The glossary says any card can be spent, which makes this defensible, but the printed ⊡ on a Gear could also be read as spending the host it is attached to. Not changed (no rule changes after E12); one verified position (`play-around-overwatch-on-the-lowlife`) depends on the current reading and would need re-qualifying if the ruling went the other way.

## Q4 — may a spent face-down Legend be Called? — SETTLED (owner ruling 057)

Raised by the defend proposals. `legal.main_menu` / `reaction_menu` offer a Call for any face-down Legend when 1 €$ is available, without checking the target's orientation, so a spent face-down Legend can be Called (it flips face-up and stays spent, CR 11.11.1.3). The rules text does not forbid it and the FAQ does not address it. Several defend positions use spent face-down Legends as Eddie-eating decoys for the frozen heuristic; they hold either way. Not changed.

## Q3 addendum — every Gear with a spend-icon ability (for the owner's ruling)

Searched the registry: exactly **one** Gear carries a ⊡ ability.

- **Overwatch** (`overwatch-panams-gift`, cost 4): "(Equip to a friendly Unit or face-up Legend.)\nQUICK 1 €$, ⊡: Discard 1. Defeat a spent rival Unit with cost equal to or less than the discarded card's cost."

Its text does not say which card the ⊡ spends, so nothing contradicts the ruling that it spends the equipped Unit or Legend; the ruling is landed for it (Q3, Settled — owner ruling). No card is parked.

