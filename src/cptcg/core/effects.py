"""Effect context: the API card scripts use to change the game.

Card scripts only touch state through these atoms. Atoms either mutate immediately or queue a
choice — they never wait for input inside a Python call. Continuations receive a fresh
EffectCtx for the same card, so they work identically on cloned states.
"""

from __future__ import annotations

from itertools import combinations
from typing import Callable, Iterable

from cptcg.core import ops
from cptcg.core.actions import Choice, ChoiceKind, Pick
from cptcg.core.enums import NO_INST, NZONE, CardType, Keyword, Zone
from cptcg.core.state import GameState


class EffectCtx:
    __slots__ = ("s", "inst", "player")

    def __init__(self, s: GameState, inst: int) -> None:
        self.s = s
        self.inst = inst
        self.player = s.i_owner[inst]

    # ------------------------------------------------------------ identity
    @property
    def rival(self) -> int:
        return 1 - self.player

    @property
    def card(self):
        return self.s.card(self.inst)

    def in_play(self, inst: int | None = None) -> bool:
        i = self.inst if inst is None else inst
        return self.s.i_zone[i] in (Zone.FIELD, Zone.LEGENDS)

    def host(self) -> int:
        """For Gear: the Unit or Legend it is equipped to."""
        return self.s.i_host[self.inst]

    def is_active_turn(self) -> bool:
        return self.s.active == self.player

    # ------------------------------------------------------------- queries
    def units(self, player: int | None = None, pred: Callable | None = None) -> list[int]:
        out = self.s.units(self.player if player is None else player)
        return [u for u in out if pred is None or pred(u)] if pred else out

    def rival_units(self, pred: Callable | None = None) -> list[int]:
        return self.units(self.rival, pred)

    def legends(self, player: int | None = None, faceup: bool | None = None) -> list[int]:
        out = self.s.legends(self.player if player is None else player)
        if faceup is None:
            return out
        return [i for i in out if bool(self.s.i_faceup[i]) == faceup]

    def hand(self, player: int | None = None) -> list[int]:
        return self.s.zone(self.player if player is None else player, Zone.HAND)

    def trash(self, player: int | None = None) -> list[int]:
        return self.s.zone(self.player if player is None else player, Zone.TRASH)

    def gear(self, inst: int | None = None) -> list[int]:
        return self.s.gear_on(self.inst if inst is None else inst)

    def equipped(self, inst: int) -> bool:
        return bool(self.s.gear_on(inst))

    def all_gear(self, player: int | None = None) -> list[int]:
        p = self.player if player is None else player
        return [i for z in (Zone.FIELD, Zone.LEGENDS) for i in self.s.z[p * NZONE + z]
                if self.s.i_host[i] != NO_INST]

    def power(self, inst: int | None = None, sit: int = 0) -> int:
        return ops.power(self.s, self.inst if inst is None else inst, sit)

    def d(self, inst: int):
        return self.s.card(inst)

    def has_tag(self, inst: int, tag: str) -> bool:
        return tag in self.s.card(inst).tags

    def is_type(self, inst: int, t: CardType) -> bool:
        return self.s.card(inst).type is t

    def cred(self, player: int | None = None) -> int:
        return self.s.street_cred(self.player if player is None else player)

    def more_cred(self) -> bool:
        return self.cred() > self.cred(self.rival)

    def less_cred(self) -> bool:
        return self.cred() < self.cred(self.rival)

    def gigs(self, player: int | None = None) -> list[tuple[int, int]]:
        return self.s.gig[self.player if player is None else player]

    def gig_values(self, player: int | None = None) -> list[int]:
        return [v for _, v in self.gigs(player)]

    def value_pairs(self, player: int | None = None) -> int:
        """Number of value-pairs: pairs of dice sharing a value (each die in at most one pair)."""
        from collections import Counter
        return sum(n // 2 for n in Counter(self.gig_values(player)).values())

    def has_value_pair(self, player: int | None = None) -> bool:
        return self.value_pairs(player) > 0

    def min_gigs(self, player: int | None = None) -> list[int]:
        """Indices of dice showing their minimum face (1)."""
        return [i for i, (_k, v) in enumerate(self.gigs(player)) if v == 1]

    def max_gigs(self, player: int | None = None) -> list[int]:
        return [i for i, (k, v) in enumerate(self.gigs(player)) if v == k]

    def gigs_with(self, pred: Callable[[int, int], bool], player: int | None = None) -> list[int]:
        return [i for i, (k, v) in enumerate(self.gigs(player)) if pred(k, v)]

    def fixer_empty(self) -> bool:
        return not self.s.fixer[self.player]

    def played_this_turn(self, pred: Callable | None = None) -> list[int]:
        return [i for i in self.s.played if self.s.i_owner[i] == self.player and (pred is None or pred(i))]

    def once(self, key: str) -> bool:
        """True the first time this card uses ``key`` this turn."""
        return self.s.use_once((self.inst, key))

    # -------------------------------------------------------------- choices
    def ask(self, choice: Choice) -> None:
        ops.ask(self.s, choice)

    def choose(self, values: Iterable, cont: Callable[["EffectCtx", object], None], *,
               prompt: str = "", player: int | None = None, optional: bool = False,
               otherwise: Callable[["EffectCtx"], None] | None = None) -> None:
        """Pick one of ``values``; ``cont(ctx, value)`` runs with the pick. With ``optional``,
        a decline option is added and ``otherwise(ctx)`` runs on decline (if given).
        If there is nothing to choose, ``otherwise`` runs immediately."""
        vals = list(values)
        if not vals:
            if otherwise is not None:
                otherwise(self)
            return
        opts = tuple(Pick((i,)) for i in range(len(vals)))
        if optional:
            opts = opts + (Pick(()),)
        inst = self.inst

        def _cont(st: GameState, act: Pick) -> None:
            c = EffectCtx(st, inst)
            if act.picks:
                cont(c, vals[act.picks[0]])
            elif otherwise is not None:
                otherwise(c)

        self.ask(Choice(ChoiceKind.PICK, self.player if player is None else player, opts, _cont,
                        prompt=prompt or self.card.name))

    def choose_many(self, values: Iterable, lo: int, hi: int,
                    cont: Callable[["EffectCtx", list], None], *, prompt: str = "",
                    player: int | None = None) -> None:
        """Pick between ``lo`` and ``hi`` of ``values`` (clamped to what's available)."""
        vals = list(values)
        hi = min(hi, len(vals))
        lo = min(lo, hi)
        if hi == 0:
            cont(self, [])
            return
        opts = tuple(Pick(c) for n in range(lo, hi + 1) for c in combinations(range(len(vals)), n))
        inst = self.inst

        def _cont(st: GameState, act: Pick) -> None:
            cont(EffectCtx(st, inst), [vals[i] for i in act.picks])

        self.ask(Choice(ChoiceKind.PICK, self.player if player is None else player, opts, _cont,
                        prompt=prompt or self.card.name))

    def choose_one(self, effects: list[tuple[str, Callable[["EffectCtx"], None]]], *, both: bool = False,
                   player: int | None = None) -> None:
        """'Choose one effect' modal. ``both=True`` resolves every option in order instead."""
        if both:
            for _label, fn in reversed(effects):
                self.later(fn)
            return
        self.choose(effects, lambda c, e: e[1](c), prompt="Choose one effect", player=player)

    def maybe(self, cont: Callable[["EffectCtx"], None], *, prompt: str = "", player: int | None = None) -> None:
        """'You may ...' — a yes/no decision."""
        self.choose([True], lambda c, _v: cont(c), prompt=prompt or f"{self.card.name}: use effect?",
                    player=player, optional=True)

    def later(self, fn: Callable[["EffectCtx"], None]) -> None:
        """Queue ``fn(ctx)`` to run after whatever is currently queued above it resolves."""
        from cptcg.core.steps import HookStep
        self.s.stack.append(HookStep(fn, self.inst))

    # ---------------------------------------------------------------- cards
    def draw(self, n: int = 1, player: int | None = None) -> int:
        return ops.draw(self.s, self.player if player is None else player, n)

    def discard(self, n: int, player: int | None = None, cont: Callable | None = None) -> None:
        """The player discards ``n`` cards of their choice. ``cont(ctx, [insts])`` runs after."""
        p = self.player if player is None else player
        hand = list(self.hand(p))

        def _done(c: "EffectCtx", picks: list) -> None:
            for i in picks:
                ops.discard(c.s, i)
            if cont is not None:
                cont(c, picks)

        self.choose_many(hand, min(n, len(hand)), min(n, len(hand)), _done, prompt="Discard", player=p)

    def trash_top(self, n: int, player: int | None = None) -> list[int]:
        return ops.trash_top(self.s, self.player if player is None else player, n)

    def top(self, n: int, player: int | None = None) -> list[int]:
        return ops.top_cards(self.s, self.player if player is None else player, n)

    def add_to_hand(self, inst: int) -> None:
        ops.move(self.s, inst, Zone.HAND)

    def bottom_deck(self, inst: int) -> None:
        ops.bottom_deck(self.s, inst)

    def bottom_deck_random(self, insts: list[int]) -> None:
        insts = list(insts)
        self.s.rng.shuffle(insts)
        for i in insts:
            ops.bottom_deck(self.s, i)

    def search_top(self, n: int, take: Callable[[int], bool] | None, lo: int, hi: int,
                   cont: Callable | None = None, *, bottom_random: bool = False) -> None:
        """Look at the top ``n``; add ``lo``..``hi`` of those matching ``take`` to hand;
        bottom-deck the rest (in chosen or random order)."""
        cards = self.top(n)
        cands = [c for c in cards if take is None or take(c)]

        def _done(c: "EffectCtx", picks: list) -> None:
            for i in picks:
                c.add_to_hand(i)
            rest = [i for i in cards if i not in picks]
            if bottom_random:
                c.bottom_deck_random(rest)
            else:
                for i in rest:
                    c.bottom_deck(i)
            if cont is not None:
                cont(c, picks)

        self.choose_many(cands, lo, hi, _done, prompt="Search")

    def sell(self, inst: int) -> None:
        ops.move(self.s, inst, Zone.EDDIES)

    def play_free(self, inst: int, *, then: Callable | None = None) -> None:
        """Play a card for free from hand or trash. Gear asks for a host."""
        from cptcg.core.engine import play_card
        from cptcg.core.legal import gear_hosts
        d = self.s.card(inst)
        if d.type is CardType.GEAR:
            def _host(c: "EffectCtx", h: int) -> None:
                play_card(c.s, c.player, inst, host=h, cost=0)
                if then is not None:
                    then(c, inst)
            self.choose(gear_hosts(self.s, self.player), _host, prompt="Equip to")
            return
        play_card(self.s, self.player, inst, cost=0)
        if then is not None:
            then(self, inst)

    # ------------------------------------------------------------- in play
    def defeat(self, inst: int) -> None:
        ops.defeat(self.s, inst)

    def spend(self, inst: int) -> None:
        ops.spend(self.s, inst)

    def ready(self, inst: int) -> None:
        ops.ready(self.s, inst)

    def ready_eddies(self, n: int) -> int:
        return ops.ready_eddies(self.s, self.player, n)

    def temp_power(self, inst: int, delta: int, cond: int = 0) -> None:
        ops.add_temp_power(self.s, inst, delta, cond)

    def grant(self, inst: int, kw: Keyword) -> None:
        self.s.add_mod("kw", inst, kw)

    def mod(self, kind: str, subject: int, value=None, *, until_my_next_turn: bool = False) -> None:
        turns = (1 if self.s.active == self.player else 0) if until_my_next_turn else 0
        self.s.add_mod(kind, subject, value, turns=turns)

    def cant_ready(self, inst: int) -> None:
        from cptcg.core.enums import F_NO_READY_NEXT
        self.s.i_flags[inst] |= F_NO_READY_NEXT

    def return_to_hand(self, inst: int) -> None:
        ops.move(self.s, inst, Zone.HAND)

    # ---------------------------------------------------------------- dice
    def adjust_gig(self, owner: int, index: int, delta: int) -> None:
        ops.adjust_gig(self.s, self.player, owner, index, delta)

    def set_gig(self, owner: int, index: int, value: int) -> None:
        ops.set_gig(self.s, self.player, owner, index, value)

    def swap_gig(self, mine: int, theirs: int) -> None:
        ops.swap_gigs(self.s, self.player, mine, theirs)

    def choose_gig(self, owners: Iterable[int], cont: Callable[["EffectCtx", int, int], None], *,
                   pred: Callable[[int, int], bool] | None = None, prompt: str = "Choose a Gig",
                   optional: bool = False, player: int | None = None) -> None:
        cands = [(o, i) for o in owners for i, (k, v) in enumerate(self.gigs(o))
                 if pred is None or pred(k, v)]
        self.choose(cands, lambda c, ov: cont(c, ov[0], ov[1]), prompt=prompt, optional=optional,
                    player=player)

    def adjust_up_to(self, owners: Iterable[int], lo: int, hi: int, *, cont: Callable | None = None,
                     prompt: str = "Adjust a Gig") -> None:
        """'Increase/decrease/adjust a Gig by up to N': pick a die, then an amount in lo..hi."""
        def _die(c: "EffectCtx", owner: int, index: int) -> None:
            k, v = c.gigs(owner)[index]
            amounts = [a for a in range(lo, hi + 1) if a != 0 and 1 <= v + a <= k]
            if not amounts:
                if cont is not None:
                    cont(c, owner, index)
                return

            def _amt(c2: "EffectCtx", a: int) -> None:
                c2.adjust_gig(owner, index, a)
                if cont is not None:
                    cont(c2, owner, index)

            c.choose(amounts, _amt, prompt=prompt, optional=True,
                     otherwise=(lambda c3: cont(c3, owner, index)) if cont is not None else None)

        self.choose_gig(owners, _die, prompt=prompt, optional=True)

    # ------------------------------------------------------------- legends
    def call_free(self, inst: int) -> None:
        if not self.s.i_faceup[inst] and ops.can_call_free(self.s, self.player):
            ops.call_legend(self.s, self.player, inst)

    def look_at(self, inst: int) -> None:
        self.s.i_known[inst] |= 1 << self.player
        self.s.emit("look", self.player, inst)

    def offer_call_free(self, prompt: str = "Call a Legend for free?") -> None:
        if not ops.can_call_free(self.s, self.player):
            return
        self.choose([i for i in self.legends(faceup=False)], lambda c, i: c.call_free(i),
                    prompt=prompt, optional=True)
