"""Effect context: the API card scripts use to change the game.

Card scripts only touch state through these atoms. Atoms either mutate immediately or queue a
choice — they never wait for input inside a Python call. Continuations receive a fresh
EffectCtx for the same card, so they work identically on cloned states.
"""

from __future__ import annotations

from itertools import combinations
from typing import Callable, Iterable

from cptcg.core import ops
from cptcg.core.actions import Choice, ChoiceKind, Pick, call_site
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
        """Legends in the Legends **area** (the slots). For "friendly Legends" as printed card
        text means it, which includes a Legend standing on the field, see ``all_legends`` and
        ``faceup_legends``."""
        out = self.s.legends(self.player if player is None else player)
        if faceup is None:
            return out
        return [i for i in out if bool(self.s.i_faceup[i]) == faceup]

    def field_legends(self, player: int | None = None) -> list[int]:
        """Legends standing on the field as Units (GO SOLO or the plain play, ruling 047)."""
        p = self.player if player is None else player
        defs = self.s.reg.defs
        return [i for i in self.s.units(p) if defs[self.s.i_card[i]].type is CardType.LEGEND]

    def all_legends(self, player: int | None = None) -> list[int]:
        """Every friendly Legend a card's text can mean: the Legends area plus the field.

        Ruling 044 (a solo'd Legend is still a Legend) and the owner's ruling on Goro Takemura
        *Losing His Way* (2026-09-21): a Legend standing on the field counts as a face-up Legend,
        and once every Legend has gone solo and been removed there are none left to count.
        Synapse Burnout's FAQ says the same in its own words -- "Does this effect count friendly
        face-up Legends in the field area? **Yes**", and it counts itself.
        """
        return self.legends(player) + self.field_legends(player)

    def faceup_legends(self, player: int | None = None) -> list[int]:
        """Face-up friendly Legends wherever they stand: the area's face-up slots plus the field
        (a Legend on the field is always face-up)."""
        return self.legends(player, faceup=True) + self.field_legends(player)

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

    def is_unit(self, inst: int) -> bool:
        """Is this instance a Unit **right now**? Ruling 044, settled by the FAQ.

        By zone, never by ``CardDef.type``. A Legend played to the field with GO SOLO *is* a Unit
        — the FAQ says so four separate times, and says it is still a Legend too, so the two
        answers are not exclusive — and reading the printed type gets that wrong. Six scripts used
        to ask the printed type while forty-eight asked the zone, and the seven audit findings that
        turn on the word were all on the six.

        ``s.units`` is the same list every zone-based site reads, so this cannot drift from them:
        it already excludes equipped Gear, which shares the field zone with its host.

        This needs the card to still BE somewhere, so it is no use to a DEFEATED listener: `defeat`
        moves the card out of play, and `move` clears the flag that recorded it had been on the
        field, before the event is dispatched. That case is answered by `defeat` itself and carried
        as the fifth element of the ``("defeated", ...)`` event.
        """
        return inst in self.s.units(self.s.i_owner[inst])

    def cred(self, player: int | None = None) -> int:
        return self.s.street_cred(self.player if player is None else player)

    def cred_even(self, player: int | None = None) -> bool:
        """CR 11.2.3: with no Gigs Street Cred is Null — neither even nor odd."""
        p = self.player if player is None else player
        if self.s.cfg.null_cred and not self.s.gig[p]:
            return False
        return self.cred(p) % 2 == 0

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
        """True the first time this card uses ``key`` this turn. This is a per-**instance** budget
        ("once per turn, this card"); printed "the first time X happens each turn" is not that,
        see ``first_this_turn``."""
        return self.s.use_once((self.inst, key))

    def first_this_turn(self, pred: Callable[[tuple], bool], ev: tuple | None = None) -> bool:
        """Is the event ``ev`` (the one being handled) the first this turn that satisfies ``pred``?

        "The first time an ARASAKA Unit is defeated each turn" counts *events*, not this card's
        sightings of them. Three FAQ answers say so: a Yorinobu Arasaka played after an ARASAKA
        Unit died this turn does not draw for the next death; a Yorinobu *Embracing Destruction*
        flipped after an ARASAKA attack does not draw for the next attack; a Jackie Welles *Pour
        One Out For Me* flipped after a Blue card does not trigger on the next one. A card that
        arrives mid-turn therefore has to see the turn's history, which ``s.turn_events`` keeps
        (every dispatched event, cleared with the turn). Earlier events are those before ``ev``
        itself in that list, compared by identity; with ``ev=None`` the whole log is checked, which
        is what a hook that runs *after* its event (an on_defeated step) wants when it passes the
        event it found.
        """
        for x in self.s.turn_events:
            if ev is not None and x is ev:
                return True
            if pred(x):
                return False
        return True

    # -------------------------------------------------------------- choices
    def ask(self, choice: Choice) -> None:
        ops.ask(self.s, choice)

    def choose(self, values: Iterable, cont: Callable[["EffectCtx", object], None], *,
               prompt: str = "", player: int | None = None, optional: bool = False,
               otherwise: Callable[["EffectCtx"], None] | None = None,
               tag: str = "", revealed: Iterable[int] = ()) -> None:
        """Pick one of ``values``; ``cont(ctx, value)`` runs with the pick. With ``optional``,
        a decline option is added and ``otherwise(ctx)`` runs on decline (if given).
        If there is nothing to choose, ``otherwise`` runs immediately.

        ``revealed`` names the instances this question has *shown* to the chooser — the top cards
        a peek looked at. Declare it whenever the effect read a card the chooser could not
        otherwise see; ``core.view`` pins exactly what is declared here (see ``view._pinned``).
        ``tag`` overrides the call site used to identify the question."""
        vals = list(values)
        if not vals:
            self._peek_only(revealed, player)
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
                        prompt=prompt or self.card.name, tag=f"{inst}@{tag or call_site(cont)}",
                        revealed=tuple(revealed)))

    def _peek_only(self, revealed, player=None) -> None:
        """Record a look that asked no question.

        A search whose filter matches nothing still *happened*: the cards were seen and then put
        back. Both choose() and choose_many() resolve that case without asking — correctly, there is
        no decision — and the consequence at the table is that the card appears to do nothing at
        all. Viktor Vektor *Sit Down and Relax* reveals the top 5 and, with no Gear among them,
        showed the player nothing whatsoever.

        This is narration, not a decision: emit() writes to s.log and nothing else, and is a no-op
        in rollouts where s.log is None. No action is added, so stored action streams are unchanged
        and the search costs the search nothing.
        """
        rev = tuple(revealed)
        if rev:
            self.s.emit("peek", self.player if player is None else player, rev)

    def choose_many(self, values: Iterable, lo: int, hi: int,
                    cont: Callable[["EffectCtx", list], None], *, prompt: str = "",
                    player: int | None = None, tag: str = "", revealed: Iterable[int] = ()) -> None:
        """Pick between ``lo`` and ``hi`` of ``values`` (clamped to what's available).
        ``revealed`` and ``tag`` are as in ``choose``."""
        vals = list(values)
        hi = min(hi, len(vals))
        lo = min(lo, hi)
        if hi == 0:
            self._peek_only(revealed, player)
            cont(self, [])
            return
        opts = tuple(Pick(c) for n in range(lo, hi + 1) for c in combinations(range(len(vals)), n))
        inst = self.inst

        def _cont(st: GameState, act: Pick) -> None:
            cont(EffectCtx(st, inst), [vals[i] for i in act.picks])

        self.ask(Choice(ChoiceKind.PICK, self.player if player is None else player, opts, _cont,
                        prompt=prompt or self.card.name, tag=f"{inst}@{tag or call_site(cont)}",
                        revealed=tuple(revealed)))

    def choose_one(self, effects: list[tuple[str, Callable[["EffectCtx"], None]]], *, both: bool = False,
                   player: int | None = None) -> None:
        """'Choose one effect' modal. ``both=True`` resolves every option in order instead."""
        if both:
            for _label, fn in reversed(effects):
                self.later(fn)
            return
        self.choose(effects, lambda c, e: e[1](c), prompt="Choose one effect", player=player,
                    tag=call_site(effects[0][1]) if effects else "")

    def maybe(self, cont: Callable[["EffectCtx"], None], *, prompt: str = "",
              player: int | None = None, revealed: Iterable[int] = (),
              after: Callable[["EffectCtx"], None] | None = None) -> None:
        """'You may ...' — a yes/no decision. ``revealed`` is as in ``choose``: name the card a
        peek showed the chooser, so the mask knows they have seen it.

        ``after(ctx)`` runs either way, and is how a printed sentence that follows a "may" is
        sequenced without being made conditional on it — the same distinction ``adjust_up_to`` and
        ``spend_one`` draw. Code written *after* the ``maybe`` call instead would run before the
        answer arrives, because asking a question returns rather than blocking.
        """
        def _resolve(c: "EffectCtx") -> None:
            cont(c)
            if after is not None:
                after(c)
        self.choose([True], lambda c, _v: _resolve(c),
                    prompt=prompt or f"{self.card.name}: use effect?",
                    player=player, optional=True, otherwise=after, tag=call_site(cont),
                    revealed=revealed)

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

        self.choose_many(hand, min(n, len(hand)), min(n, len(hand)), _done, prompt="Discard",
                         player=p, tag=call_site(cont))

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

        # The peek is real: the searcher has seen all ``n``, not just the ones they may take.
        self.choose_many(cands, lo, hi, _done, prompt="Search", tag=call_site(cont),
                         revealed=tuple(cards))

    def sell(self, inst: int, *, facedown: bool = False) -> None:
        """Sell a card for an Eddie. ``facedown``: sold without being looked at (Bootleg), so its
        identity stays hidden from both seats -- see ``F_FACEDOWN``."""
        ops.move(self.s, inst, Zone.EDDIES)
        if facedown:
            from cptcg.core.enums import F_FACEDOWN
            self.s.i_flags[inst] |= F_FACEDOWN
        if self.s.cfg.effect_sell_uses_action:           # CR 11.9.2.2
            from cptcg.core.state import ONCE_SOLD
            self.s.once[self.player] |= ONCE_SOLD

    def play_free(self, inst: int, *, then: Callable | None = None) -> None:
        """Play a card for free from hand or trash. Gear asks for a host."""
        from cptcg.core.engine import play_card
        from cptcg.core.legal import gear_hosts
        d = self.s.card(inst)
        if d.type is CardType.GEAR:
            def _host(c: "EffectCtx", h: int) -> None:
                if then is not None:
                    c.later(lambda c2: then(c2, inst))       # after the Gear's own PLAY trigger
                play_card(c.s, c.player, inst, host=h, cost=0)
            self.choose(gear_hosts(self.s, self.player), _host, prompt="Equip to", tag="equip")
            return
        if then is not None:
            self.later(lambda c2: then(c2, inst))
        play_card(self.s, self.player, inst, cost=0)

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
        """Register a temporary effect. For ``kind="listener"`` pass the listening card's instance
        as ``subject`` and the ``fn(s, ev)`` as ``value``, with ``fn.kinds`` naming the event kinds
        it acts on -- see ``ops._listeners``."""
        turns = (1 if self.s.active == self.player else 0) if until_my_next_turn else 0
        self.s.add_mod(kind, subject, value, turns=turns)

    def cant_ready(self, inst: int) -> None:
        from cptcg.core.enums import F_CANT_READY
        self.s.i_flags[inst] |= F_CANT_READY

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
                   optional: bool = False, player: int | None = None,
                   after: Callable[["EffectCtx"], None] | None = None,
                   otherwise: Callable[["EffectCtx"], None] | None = None) -> None:
        """Pick a Gig; ``cont(ctx, owner, index)`` runs with the pick.

        ``after(ctx)`` runs **whatever happens**: after the pick, after a decline, and when there
        was no legal Gig to offer in the first place. See :meth:`adjust_up_to` for why that hook
        exists and what goes wrong without it — and for the one thing it cannot do.

        ``otherwise(ctx)`` runs only on the paths where ``cont`` did not: a decline, or no legal
        Gig at all. That is the hook to use when ``cont`` itself opens another question, because
        ``after`` would then fire before the answer to it arrived.
        """
        cands = [(o, i, k, v) for o in owners for i, (k, v) in enumerate(self.gigs(o))
                 if pred is None or pred(k, v)]

        def _do(c: "EffectCtx", t: tuple) -> None:
            o, i, k, v = t
            gigs = c.gigs(o)
            if i < len(gigs) and gigs[i] == (k, v):
                cont(c, o, i)
            if after is not None:
                after(c)

        def _else(c: "EffectCtx") -> None:
            if after is not None:
                after(c)
            if otherwise is not None:
                otherwise(c)
        self.choose(cands, _do, prompt=prompt, optional=optional, player=player,
                    otherwise=_else, tag=call_site(cont))

    def adjust_up_to(self, owners: Iterable[int], lo: int, hi: int, *, cont: Callable | None = None,
                     after: Callable[["EffectCtx"], None] | None = None, optional: bool = True,
                     prompt: str = "Adjust a Gig") -> None:
        """'Increase/decrease/adjust a Gig by up to N' as ONE decision over (owner, index, amount)
        triples, plus a decline option. Fewer, richer decisions keep search trees small.

        Two hooks, and the difference between them is a class of bug rather than a convenience.
        ``cont(ctx, owner, index)`` runs only when a die actually moved, and is right for a clause
        that talks about *that* Gig ("If **it** becomes a min Gig, draw 1"). ``after(ctx)`` runs
        whatever happens — after the adjustment, after a decline, and when no legal adjustment
        existed to offer — and is right for a separate printed sentence with its own board
        condition ("Then, **if you control** a min Gig, draw 1").

        Getting that backwards is invisible and common: "up to N" includes zero and the engine
        offers the decline explicitly, a Gig already at its face cannot move at all (ruling 037),
        and in both cases a second sentence hung off ``cont`` silently never runs. Six cards in
        this set were written that way.

        **What ``after`` cannot do.** It runs the moment ``cont`` *returns*, and a continuation
        returns as soon as it asks a further question -- asking pushes a step and comes straight
        back. So ``after`` is for a ``cont`` that finishes synchronously. Where ``cont`` opens
        another prompt, the tail belongs on *that* prompt instead, or it is evaluated against the
        board as it was before the answer. Peace Offering is the worked example: its set is two
        nested questions, and hanging "then, if you control a value-pair" off the outer one drew
        before the die had moved.

        ``optional`` is the "up to" itself. Fourteen cards in this set adjust a Gig and thirteen of
        them print "up to N", so the decline is the default -- but Muamar Reyes *El Capitán* prints
        "⊡: Adjust a Gig by 1", with no "up to" and no "may", and there the do-nothing answer is one
        the card does not offer. Pass ``optional=False`` for a fixed amount.
        """
        cands = []
        for o in owners:
            for i, (k, v) in enumerate(self.gigs(o)):
                for a in range(lo, hi + 1):
                    if a != 0 and 1 <= v + a <= k:
                        cands.append((o, i, a, k, v))

        def _do(c: "EffectCtx", t: tuple) -> None:
            o, i, a, k, v = t
            gigs = c.gigs(o)
            if i < len(gigs) and gigs[i] == (k, v):      # else that die moved before the answer
                c.adjust_gig(o, i, a)
                if cont is not None:
                    cont(c, o, i)
            if after is not None:
                after(c)

        self.choose(cands, _do, prompt=prompt, optional=optional, otherwise=after,
                    tag=call_site(cont) or "adjust_gig")

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
        # Blind by design (ruling: you Call without peeking), so nothing is revealed here.
        self.choose([i for i in self.legends(faceup=False)], lambda c, i: c.call_free(i),
                    prompt=prompt, optional=True, tag="call_free")


ops._EffectCtx = EffectCtx   # see ops._ctx: bind once instead of importing on every cache miss
