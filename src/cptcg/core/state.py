"""Game state.

Structure-of-arrays: every card instance gets an integer id at setup and keeps it for the whole
game; all mutable per-instance data lives in parallel lists indexed by that id. ``clone()`` is
therefore a fixed handful of ``list.copy()`` calls no matter how tangled the board gets — that is
the number a search agent's whole budget hangs on.

Static per-instance data (``i_card``, ``i_owner``) never changes after setup and is *shared*
between clones, not copied.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cptcg.core.config import RulesConfig
from cptcg.core.enums import NO_INST, NZONE, CardType, Zone
from cptcg.core.rng import Pcg32

if TYPE_CHECKING:
    from cptcg.cards.registry import Registry
    from cptcg.core.actions import Choice

ONCE_SOLD = 1
ONCE_CALLED = 2


class AttackContext:
    __slots__ = ("attacker", "attacker_ctrl", "target_kind", "target",
                 "gig_steal_allowed", "redirects", "fizzled")

    def __init__(self, attacker: int, ctrl: int) -> None:
        self.attacker = attacker
        self.attacker_ctrl = ctrl
        self.target_kind = -1
        self.target = NO_INST
        self.gig_steal_allowed = True
        self.redirects = 0
        self.fizzled = False

    def copy(self) -> "AttackContext":
        a = AttackContext.__new__(AttackContext)
        a.attacker = self.attacker
        a.attacker_ctrl = self.attacker_ctrl
        a.target_kind = self.target_kind
        a.target = self.target
        a.gig_steal_allowed = self.gig_steal_allowed
        a.redirects = self.redirects
        a.fizzled = self.fizzled
        return a


class GameState:
    __slots__ = (
        # shared, immutable
        "cfg", "reg",
        # scalars
        "rng", "seed", "turn", "active", "first_player", "turns_taken", "overtime",
        "over", "winner", "end_reason", "pending", "stack", "atk", "once",
        # instance arrays (SoA)
        "i_card", "i_owner",                       # static after setup: shared by clones
        "i_zone", "i_spent", "i_lag", "i_faceup", "i_host", "i_flags", "i_known",
        # zones: index = player * NZONE + zone
        "z",
        # dice
        "fixer", "gig",
        # temporary power mods: (inst, delta, cond) — cleared at end of turn
        "temp_power",
        # temporary effects with expiry: (kind, subject, value, expires_turn)
        "mods",
        # per-turn bookkeeping: keys used for "the first time ... each turn"; cards played this turn
        "used", "played",
        # recording (None in rollouts)
        "log", "actions",
    )

    def __init__(self, cfg: RulesConfig, reg: "Registry", seed: int) -> None:
        self.cfg = cfg
        self.reg = reg
        self.rng = Pcg32(seed)
        self.seed = seed
        self.turn = 0
        self.active = 0
        self.first_player = 0
        self.turns_taken = [0, 0]
        self.overtime = False
        self.over = False
        self.winner = -1
        self.end_reason = -1
        self.pending: Choice | None = None
        self.stack: list = []
        self.atk: AttackContext | None = None
        self.once = [0, 0]
        self.i_card: list[int] = []
        self.i_owner: list[int] = []
        self.i_zone: list[int] = []
        self.i_spent = bytearray()
        self.i_lag = bytearray()
        self.i_faceup = bytearray()
        self.i_host: list[int] = []
        self.i_flags: list[int] = []
        self.i_known: list[int] = []
        self.z: list[list[int]] = [[] for _ in range(2 * NZONE)]
        self.fixer: list[list[int]] = [[], []]
        self.gig: list[list[tuple[int, int]]] = [[], []]
        self.temp_power: list[tuple[int, int, int]] = []
        self.mods: list[tuple] = []
        self.used: set = set()
        self.played: list[int] = []
        self.log: list | None = None
        self.actions: list[int] | None = None

    # ------------------------------------------------------------------ clone
    def clone(self) -> "GameState":
        s = GameState.__new__(GameState)
        s.cfg = self.cfg
        s.reg = self.reg
        s.rng = self.rng.copy()
        s.seed = self.seed
        s.turn = self.turn
        s.active = self.active
        s.first_player = self.first_player
        s.turns_taken = self.turns_taken[:]
        s.overtime = self.overtime
        s.over = self.over
        s.winner = self.winner
        s.end_reason = self.end_reason
        s.pending = self.pending                       # frozen
        s.stack = self.stack[:]                        # steps are immutable
        s.atk = self.atk.copy() if self.atk is not None else None
        s.once = self.once[:]
        s.i_card = self.i_card                         # shared: never mutated after setup
        s.i_owner = self.i_owner                       # shared
        s.i_zone = self.i_zone[:]
        s.i_spent = bytearray(self.i_spent)
        s.i_lag = bytearray(self.i_lag)
        s.i_faceup = bytearray(self.i_faceup)
        s.i_host = self.i_host[:]
        s.i_flags = self.i_flags[:]
        s.i_known = self.i_known[:]
        s.z = [lst[:] for lst in self.z]
        s.fixer = [self.fixer[0][:], self.fixer[1][:]]
        s.gig = [self.gig[0][:], self.gig[1][:]]
        s.temp_power = self.temp_power[:]
        s.mods = self.mods[:]
        s.used = set(self.used)
        s.played = self.played[:]
        s.log = None
        s.actions = None
        return s

    # -------------------------------------------------------------- instances
    def new_instance(self, card_idx: int, owner: int, zone: Zone) -> int:
        inst = len(self.i_card)
        self.i_card.append(card_idx)
        self.i_owner.append(owner)
        self.i_zone.append(zone)
        self.i_spent.append(0)
        self.i_lag.append(0)
        self.i_faceup.append(0)
        self.i_host.append(NO_INST)
        self.i_flags.append(0)
        self.i_known.append(0)
        self.z[owner * NZONE + zone].append(inst)
        return inst

    def card(self, inst: int):
        return self.reg.defs[self.i_card[inst]]

    def zone(self, player: int, zone: Zone) -> list[int]:
        return self.z[player * NZONE + zone]

    def units(self, player: int) -> list[int]:
        """Units on the field (excludes attached Gear, which shares the zone)."""
        defs = self.reg.defs
        return [i for i in self.z[player * NZONE + Zone.FIELD]
                if self.i_host[i] == NO_INST and defs[self.i_card[i]].type is not CardType.GEAR]

    def gear_on(self, host: int) -> list[int]:
        owner = self.i_owner[host]
        return [i for i in self.z[owner * NZONE + self.i_zone[host]] if self.i_host[i] == host]

    def legends(self, player: int) -> list[int]:
        """Legend cards in the Legends area (excludes Gear equipped to them, which shares the zone)."""
        return [i for i in self.z[player * NZONE + Zone.LEGENDS] if self.i_host[i] == NO_INST]

    # ------------------------------------------------------------------- dice
    def street_cred(self, player: int) -> int:
        return sum(v for _, v in self.gig[player])

    # ------------------------------------------------------------------- mods
    def add_mod(self, kind: str, subject: int, value=None, *, turns: int = 0) -> None:
        """Add a temporary effect. turns=0: this turn; 1: until the end of next turn (i.e.
        'until your next turn' when added on your own turn)."""
        self.mods.append((kind, subject, value, self.turn + turns))

    def has_mod(self, kind: str, subject: int) -> bool:
        for k, sub, _v, _e in self.mods:
            if k == kind and sub == subject:
                return True
        return False

    def mod_values(self, kind: str, subject: int) -> list:
        return [v for k, sub, v, _e in self.mods if k == kind and sub == subject]

    def use_once(self, key: tuple) -> bool:
        """True the first time ``key`` is used this turn, False afterwards."""
        if key in self.used:
            return False
        self.used.add(key)
        return True

    # -------------------------------------------------------------- recording
    def emit(self, *event) -> None:
        if self.log is not None:
            self.log.append(event)

    def rival(self, player: int) -> int:
        return 1 - player
