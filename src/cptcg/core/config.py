"""Rules configuration.

Every open question in docs/rulings.md is a field here, so a ruling is (a) testable, (b) hashed
into every simulation result and replay, and (c) flippable in one place when official
clarification arrives. Simulation results carry ``RulesConfig.digest()`` so that changing a ruling
visibly invalidates comparisons with older runs instead of quietly shifting them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class RulesConfig:
    # --- game constants (from the guide) ---
    gigs_to_win: int = 7
    opening_hand: int = 6
    deck_min: int = 40
    deck_max: int = 50
    max_copies: int = 3
    max_turns: int = 80                    # hard safety cap; hitting it is a bug, not a draw

    # --- rulings (numbers refer to docs/rulings.md) ---
    eddies_ready: bool = True              # 001
    perfect_eddie_memory: bool = True      # 002
    spent_legend_callable: bool = True     # 003
    empty_fixer_skips: bool = True         # 004
    reroll_stolen_dice: bool = False       # 005
    overtime_win: str = "seven_gigs"       # 006: CR 1.11 — 7+ Gigs at any point during Overtime
    overtime_start: str = "empty_fixers"   # 007: CR 1.11.1 — after both players began a turn with an empty fixer
    win_check_before_draw: bool = True     # 008
    allow_empty_gig_attack: bool = False   # 009: CR 9.3.2.2 — an empty Gig area is not a valid target
    zero_power_fights: bool = True         # 010
    zero_power_cannot_defeat: bool = True  # 010: CR 9.19.2
    max_redirects_per_attack: int = 99     # 011: CR 9.7 — as many reactions as the defender wants
    blocker_redirects_unit_attacks: bool = True  # 012
    lagged_units_can_block: bool = True    # 014: CR 11.3.1 — Lag only forbids attacking and ⊡ effects
    go_solo_vacates_slot: bool = True      # 015
    gear_reequip: bool = False             # 016
    hidden_mulligan: bool = True           # 018
    once_per_turn_scope: str = "turn"      # 019
    hand_limit: int | None = None          # 020
    sell_in_reactions: bool = False        # 021
    attack_triggers_before_target: bool = False  # 023: CR 9.3 — the target is part of the declaration
    explicit_payment: bool = False         # 025
    field_limit: int | None = None         # 026
    go_solo_requires_ready: bool = False   # 027: CR 4.5.1 — it enters in the same orientation
    go_solo_enters_lagged: bool = True     # 033: CR 4.5.2 — with Lag; the keyword still lets it attack
    legends_removed_when_leaving: bool = True   # 034: CR 4.4.1 — any Legend in an invalid area is removed
    programs_resolve_outside_areas: bool = True # 035: CR 4.14.2 — not in the trash while resolving
    effect_sell_uses_action: bool = True   # 036: CR 11.9.2.2
    set_gig_off_face_fails: bool = True    # 037: CR 6.4.4 — adjusting to a value not on the die fails
    null_cred: bool = True                 # 038: CR 11.2.3 — no Gigs = Null Street Cred (not even, not odd)
    first_player_choice: bool = True       # 028: d20 winner chooses order (else: winner goes first)

    def digest(self) -> str:
        parts = [f"{f.name}={getattr(self, f.name)!r}" for f in fields(self)]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


DEFAULT_CONFIG = RulesConfig()
