"""Card scripts for Welcome to Night City and the starter sets.

One ``@script`` per card id, grouped by mechanic. Vanilla cards (no rules text) need no entry.
"""

from __future__ import annotations

from cptcg.cards.dsl import *  # noqa: F401,F403
from cptcg.cards.registry import script
from cptcg.core.enums import Zone


# =============================================================================
# Programs: removal, card flow, tempo
# =============================================================================
@script("wild-in-the-streets")
def _():
    return CardScript(on_play=lambda c: defeat_one(
        c, [u for p in (0, 1) for u in c.units(p) if c.s.i_spent[u]]))


@script("bonnie-and-clyde")
def _():
    def play(c):
        n = 2 if len(c.gigs(c.rival)) >= len(c.gigs()) + 2 else 1
        c.choose_many(c.rival_units(power_le(c, 4)), 0, n,
                      lambda c2, us: [c2.defeat(u) for u in us], prompt="Defeat up to %d" % n)
    return CardScript(on_play=play)


@script("carnage-at-the-colosseum")
def _():
    def play(c):
        best = max((c.power(u) for u in c.units()), default=0)
        defeat_one(c, c.rival_units(lambda u: c.power(u) < best))
    return CardScript(on_play=play,
                      self_cost=lambda c, p, base: max(1, base - gigs_8plus(c)))


@script("over-the-edge")
def _():
    def play(c):
        d20 = [v for k, v in c.gigs() if k == 20]
        if not d20:
            return
        lim = max(d20)
        defeat_one(c, [u for p in (0, 1) for u in c.units(p) if c.power(u) <= lim])
    return CardScript(on_play=play)


@script("dont-fear-the-reaper")
def _():
    def play(c):
        for u in c.rival_units():
            c.spend(u)
        defeat_one(c, [u for p in (0, 1) for u in c.units(p) if c.s.i_spent[u]])
    return CardScript(on_play=play)


@script("live-with-the-aftermath")
def _():
    def play(c):
        # Each player defeats one of their own Units; the rival chooses theirs.
        c.choose(c.rival_units(), lambda c2, u: c2.defeat(u), prompt="Defeat one of your Units",
                 player=c.rival)
        c.choose(c.units(), lambda c2, u: c2.defeat(u), prompt="Defeat one of your Units")
    return CardScript(on_play=play)


@script("les-elemens")
def _():
    def play(c):
        us = c.rival_units()
        if not us:
            return
        lo = min(c.power(u) for u in us)
        bottom_deck_one(c, [u for u in us if c.power(u) == lo])
    return CardScript(on_play=play)


@script("unlikely-bond")
def _():
    def play(c):
        def after(c2, _u):
            bottom_deck_one(c2, [u for u in c2.rival_units() if c2.s.i_spent[u]])
        bottom_deck_one(c, [u for u in c.units() if not c.s.i_spent[u]], optional=True, then=after)
    return CardScript(on_play=play)


@script("corporate-surveillance")
def _():
    return CardScript(on_play=lambda c: spend_one(c, c.rival_units(cost_le(c, 4))))


@script("memory-relapse")
def _():
    def play(c):
        def after(c2, u):
            c2.cant_ready(u)
            if c2.cred() % 2 == 0:
                c2.draw(1)
        spend_one(c, c.rival_units(), then=after)
    return CardScript(on_play=play)


@script("chrome-reverie")
def _():
    def play(c):
        c.choose(c.rival_units(), lambda c2, u: c2.mod("cant_attack", u, until_my_next_turn=True),
                 prompt="Can't attack until your next turn")
        if c.min_gigs():
            c.offer_call_free()
    return CardScript(on_play=play)


@script("all-is-lost")
def _():
    def play(c):
        ts = c.trash_top(3)
        c.choose([i for i in ts if c.is_type(i, UNIT)], lambda c2, i: c2.add_to_hand(i),
                 prompt="Add a Unit to hand")
    return CardScript(on_play=play)


@script("the-heist")
def _():
    def play(c):
        ts = c.trash_top(4)
        vals = set(c.gig_values())

        def got(c2, g):
            c2.add_to_hand(g)
            if (c2.d(g).cost or 0) in vals:
                c2.maybe(lambda c3: c3.play_free(g), prompt="Play it for free?")
        c.choose([i for i in ts if c.is_type(i, GEAR)], got, prompt="Add a Gear to hand")
    return CardScript(on_play=play)


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


@script("three-mouths-one-desire")
def _():
    return CardScript(on_play=lambda c: c.search_top(3, None, 1, 1 + len(c.min_gigs()), None))


@script("towerfall")
def _():
    def play(c):
        c.choose_one([
            ("All rival Units -5 power", lambda c2: [c2.temp_power(u, -5) for u in c2.rival_units()]),
            ("Bottom-deck rival 0-power Units",
             lambda c2: [c2.bottom_deck(u) for u in c2.rival_units() if c2.power(u) == 0]),
        ], both=c.less_cred())
    return CardScript(on_play=play)


@script("pyramid-song")
def _():
    def play(c):
        both = any(k == 4 and v == 1 for k, v in c.gigs())
        c.choose_one([
            ("Rival Unit -4 power", lambda c2: temp_power_one(c2, c2.rival_units(), -4)),
            ("Bottom-deck a 0-power rival Unit",
             lambda c2: bottom_deck_one(c2, c2.rival_units(lambda u: c2.power(u) == 0))),
        ], both=both)
    return CardScript(on_play=play)


@script("gunpoint-diplomacy")
def _():
    def play(c):
        def give(c2, u):
            opts = [("May attack ready Units", lambda c3: c3.mod("attack_ready_units", u)),
                    ("+3 power", lambda c3: c3.temp_power(u, 3))]
            if c2.less_cred():
                c2.choose_one(opts, player=c2.rival)
            else:
                c2.choose_one(opts, both=True)
        c.choose(c.units(), give, prompt="Give a friendly Unit")
    return CardScript(on_play=play)


@script("nocturne-op55n1")
def _():
    def play(c):
        c.choose_one([
            ("Draw 2", lambda c2: c2.draw(2)),
            ("A Unit can't attack until your next turn",
             lambda c2: c2.choose([u for p in (0, 1) for u in c2.units(p)],
                                  lambda c3, u: c3.mod("cant_attack", u, until_my_next_turn=True))),
            ("GO SOLO costs -2 this turn", lambda c2: c2.mod("cost_go_solo", c2.player, -2)),
        ])
    return CardScript(on_play=play, self_cost=lambda c, p, base: 1 if c.fixer_empty() else base)


@script("we-gotta-live-together")
def _():
    def play(c):
        c.choose_many([i for i in c.trash() if c.is_type(i, UNIT) and (c.d(i).cost or 0) <= 3], 0, 2,
                      lambda c2, us: [c2.play_free(u) for u in us], prompt="Play from trash")
    return CardScript(on_play=play,
                      self_cost=lambda c, p, base: 3 if len(c.gigs(c.rival)) >= len(c.gigs()) + 2 else base)


@script("appetite-for-destruction")
def _():
    def play(c):
        from cptcg.core.steps import stealable, push_steals
        me = c.player

        def listen(s, ev):
            if ev[0] == "fight_won" and s.i_owner[ev[1]] == me and ev[3] >= 3 and s.i_zone[ev[1]] is Zone.FIELD:
                s.mods = [m for m in s.mods if not (m[0] == "listener" and m[2] is listen)]
                cands = stealable(s, ev[1], 1 - me)
                if cands:
                    from cptcg.core.actions import Choice, ChoiceKind, Pick
                    from cptcg.core.ops import ask
                    unit = ev[1]
                    ask(s, Choice(ChoiceKind.PICK, me, tuple(Pick((i,)) for i in cands),
                                  lambda st, a: push_steals(st, unit, a.picks), prompt="Also steal a Gig"))
        c.mod("listener", me, listen)
    return CardScript(on_play=play)


@script("bootleg-black-sapphire-show")
def _():
    def play(c):
        top = c.top(1)
        if top:
            c.sell(top[0])
        vs = set(c.gig_values())
        if any(v % 2 == 0 for v in vs) and any(v % 2 == 1 for v in vs):
            c.draw(2)
    return CardScript(on_play=play)


# ---- Quickhacks / QUICK programs ---------------------------------------------
@script("floor-it")
def _():
    def play(c):
        temp_power_one(c, c.rival_units(), -1)
        c.draw(1)
    return CardScript(on_play=play)


@script("detonate")
def _():
    return CardScript(on_play=lambda c: defeat_one(
        c, [g for g in c.all_gear(c.rival) if (c.d(g).power or 0) <= 2]))


@script("synapse-burnout")
def _():
    def play(c):
        n = len(c.legends(faceup=True))
        temp_power_one(c, c.units(), n, FIGHTING | VS_UNIT)
    return CardScript(on_play=play)


@script("take-control")
def _():
    def play(c):
        def after(c2, u):
            c2.mod("steal_fewer", u, 1)
            if c2.d(u).tags & {"AI", "DRONE", "VEHICLE"}:
                c2.draw(1)
        c.choose(c.rival_units(), after, prompt="A rival Unit steals 1 fewer")
    return CardScript(on_play=play)


@script("reboot-optics")
def _():
    return CardScript(on_play=lambda c: c.mod("next_fight_no_defeat", c.player))


@script("safety-override")
def _():
    return CardScript(on_play=lambda c: c.mod("next_loss_defeats_winner", c.player))


@script("cyberpsychosis")
def _():
    def play(c):
        def give(c2, u):
            c2.temp_power(u, 3 * len(c2.gear(u)))

            def listen(s, ev):
                # "If that Unit steals or fights, defeat it at the end of this turn."
                if ev[0] in ("steal", "fight_won", "fight_lost") and ev[1] == u \
                        and not s.has_mod("defeat_at_end", u):
                    s.add_mod("defeat_at_end", u)
            c2.mod("listener", c2.player, listen)
        c.choose([u for p in (0, 1) for u in c.units(p) if c.equipped(u)], give, prompt="Equipped Unit")
    return CardScript(on_play=play)
