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
    overtime_majority: str = "gig_areas"   # 006
    overtime_after_turn: int = 7           # 007
    win_check_before_draw: bool = True     # 008
    allow_empty_gig_attack: bool = True    # 009
    zero_power_fights: bool = True         # 010
    max_redirects_per_attack: int = 1      # 011
    blocker_redirects_unit_attacks: bool = True  # 012
    lagged_units_can_block: bool = False   # 014
    go_solo_vacates_slot: bool = True      # 015
    gear_reequip: bool = False             # 016
    hidden_mulligan: bool = True           # 018
    once_per_turn_scope: str = "turn"      # 019
    hand_limit: int | None = None          # 020
    sell_in_reactions: bool = False        # 021
    attack_triggers_before_target: bool = True  # 023
    explicit_payment: bool = False         # 025
    field_limit: int | None = None         # 026
    go_solo_requires_ready: bool = True    # 027
    first_player_choice: bool = True       # 028: d20 winner chooses order (else: winner goes first)

    def digest(self) -> str:
        parts = [f"{f.name}={getattr(self, f.name)!r}" for f in fields(self)]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


DEFAULT_CONFIG = RulesConfig()
