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
            if c2.cred_even():
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


# =============================================================================
# Programs: Gig manipulation
# =============================================================================
@script("afterparty-at-lizzies")
def _():
    def play(c):
        def after(c2, _o, _i):
            if len(set(c2.gig_values())) >= 2:
                c2.draw(1)
        c.adjust_up_to([c.player, c.rival], -1, 1, cont=after)
    return CardScript(on_play=play)


@script("industrial-assembly")
def _():
    def play(c):
        def after(c2, _o, _i):
            if gigs_8plus(c2):
                c2.draw(1)
        c.adjust_up_to([c.player, c.rival], 1, 4, cont=after, prompt="Increase a Gig")
    return CardScript(on_play=play)


@script("trust-no-one")
def _():
    def play(c):
        def after(c2, _o, _i):
            if c2.min_gigs():
                c2.draw(1)
        c.adjust_up_to([c.player, c.rival], -3, -1, cont=after, prompt="Decrease a Gig")
    return CardScript(on_play=play)


@script("peace-offering")
def _():
    def play(c):
        def pick_target(c2, o, i):
            others = [(o2, j) for o2 in (0, 1) for j in range(len(c2.gigs(o2))) if (o2, j) != (o, i)]

            def pick_source(c3, src):
                c3.set_gig(o, i, c3.gigs(src[0])[src[1]][1])
                if c3.has_value_pair():
                    c3.draw(1)
            c2.choose(others, pick_source, prompt="Copy the value of")
        c.choose_gig([0, 1], pick_target, prompt="Set which Gig?", optional=True)
    return CardScript(on_play=play)


# =============================================================================
# Units: PLAY triggers
# =============================================================================
@script("adam-smasher-metal-over-meat")
def _():
    def play(c):
        # Every Unit on both sides but himself. Legends are not Units, so a face-up Legend
        # stays; each Unit's Gear follows its host through the normal defeat path, which also
        # gives replacement effects ("if this Unit would be defeated ...") their chance.
        for u in [u for p in (0, 1) for u in c.units(p) if u != c.inst]:
            c.defeat(u)
    return CardScript(on_play=play)


@script("caliber-totentanzs-top-dog")
def _():
    def defeated(c):
        def after(c2, picks):
            if picks and (c2.d(picks[0]).cost or 0) in set(c2.gig_values()):
                c2.discard(1, player=c2.rival)
        discard_rival(c, 1, cont=after)
    return CardScript(on_play=lambda c: defeat_one(c, c.rival_units(cost_le(c, 2))), on_defeated=defeated)


@script("chrome-fang")
def _():
    return CardScript(on_play=lambda c: c.mod("protect_gt_power", c.player, until_my_next_turn=True))


@script("westbrook-netrunner")
def _():
    return CardScript(on_play=lambda c: c.mod("protect_legends_lt_power", c.player, until_my_next_turn=True))


@script("delamain-rideshare-ai")
def _():
    return CardScript(on_play=lambda c: c.draw(2))


@script("field-operator")
def _():
    return CardScript(on_play=lambda c: c.draw(1) if c.cred_even() else None)


@script("gilded-maton")
def _():
    def play(c):
        def after(c2, _g):
            defeat_one(c2, c2.rival_units(cost_le(c2, 3)))
        c.choose(c.all_gear(), lambda c2, g: (c2.defeat(g), after(c2, g)), prompt="Defeat a friendly Gear?",
                 optional=True)
    return CardScript(on_play=play)


@script("hacked-corpo")
def _():
    def play(c):
        ts = c.trash_top(3)
        c.choose([i for i in ts if c.is_type(i, PROGRAM)], lambda c2, i: c2.add_to_hand(i), prompt="Add a Program")
    return CardScript(on_play=play)


@script("hanako-arasaka-in-a-gilded-cage")
def _():
    def play(c):
        vals = set(c.gig_values())
        c.search_top(4, lambda i: (c.d(i).cost or 0) in vals, 0, 4)
    return CardScript(on_play=play)


@script("heywood-ripperdoc")
def _():
    def play(c):
        def after(c2, g):
            cost = c2.d(g).cost or 0
            c2.defeat(g)
            if cost in set(c2.gig_values()):
                c2.draw(1)
        c.choose(c.all_gear(0) + c.all_gear(1), after, prompt="Defeat a Gear?", optional=True)
    return CardScript(on_play=play)


@script("japantown-jonin")
def _():
    return CardScript(on_play=lambda c: temp_power_one(c, c.units(), 2))


@script("lizzy-wizzy-delicate-weapon")
def _():
    def play(c):
        cands = [i for i in c.hand() + c.trash() if c.is_type(i, PROGRAM) and (c.d(i).cost or 0) <= 3]

        def go(c2, i):
            c2.play_free(i, then=lambda c3, j: c3.bottom_deck(j))
        c.choose(cands, go, prompt="Play a Program for free?", optional=True)
    return CardScript(on_play=play)


@script("maman-brigitte-spirit-of-death")
def _():
    def play(c):
        progs = hand_of_type(c, PROGRAM)
        if len(progs) < 2:
            return

        def after(c2, picks):
            if len(picks) == 2:
                bottom_deck_one(c2, [u for u in c2.rival_units() if not c2.equipped(u)])

        def yes(c2):
            from cptcg.core.ops import discard
            c2.choose_many(hand_of_type(c2, PROGRAM), 2, 2,
                           lambda c3, ps: ([discard(c3.s, x) for x in ps], after(c3, ps)), prompt="Discard 2 Programs")
        c.maybe(yes, prompt="Discard 2 Programs?")
    return CardScript(on_play=play)


@script("maxtac-av")
def _():
    def play(c):
        def mine(c2, o, i):
            c2.choose_gig([c2.rival], lambda c3, _o2, j: c3.swap_gig(i, j), prompt="Swap with rival Gig")
        c.choose_gig([c.player], mine, prompt="Swap which friendly Gig?", optional=True)
    return CardScript(on_play=play)


@script("minotaur")
def _():
    return CardScript(on_play=lambda c: defeat_one(c, c.rival_units(power_le(c, 5))) if c.more_cred() else None)


@script("mox-inciters")
def _():
    return CardScript(on_play=lambda c: c.choose(
        c.rival_units(), lambda c2, u: c2.mod("must_attack", u, until_my_next_turn=True), prompt="Must attack"))


@script("offduty-malfini")
def _():
    def play(c):
        c.spend(c.inst)
        spend_one(c, c.rival_units())
    return CardScript(on_play=play)


@script("pacifica-netrunner")
def _():
    def play(c):
        if c.cred_even():
            c.choose(c.rival_units(), lambda c2, u: c2.cant_ready(u), prompt="Can't ready")
    return CardScript(on_play=play)


@script("royce-dont-call-me-simon")
def _():
    return CardScript(on_play=lambda c: defeat_one(c, c.rival_units(power_le(c, 3 if c.more_cred() else 2))))


@script("tygers-whisper")
def _():
    return CardScript(on_play=lambda c: c.offer_call_free())


@script("valentino-street-racer")
def _():
    return CardScript(on_play=lambda c: c.choose(
        [u for u in c.units() if u != c.inst and (c.d(u).cost or 0) <= 5],
        lambda c2, u: c2.grant(u, ADRENALINE), prompt="Give ADRENALINE"))


@script("viktor-vektor-you-might-feel-a-little-pinch")
def _():
    def play(c):
        from cptcg.core.engine import play_card
        cands = [i for i in c.trash() if c.is_type(i, GEAR) and "CYBERWARE" in c.d(i).tags
                 and (c.d(i).cost or 0) <= 2]

        def pick_gear(c2, g):
            c2.choose([u for u in c2.units() if u != c2.inst],
                      lambda c3, h: play_card(c3.s, c3.player, g, host=h, cost=0), prompt="Equip to")
        c.choose(cands, pick_gear, prompt="Play a CYBERWARE Gear from trash")
    return CardScript(on_play=play)


@script("yorinobu-arasaka-steel-dragon")
def _():
    def play(c):
        cands = [i for i in c.hand() + c.trash() if c.is_type(i, UNIT) and (c.d(i).cost or 0) <= 4]
        c.choose(cands, lambda c2, i: c2.play_free(i, then=lambda c3, u: c3.mod("attack_units_now", u)),
                 prompt="Play a Unit for free?", optional=True)

    def ev(c, e):
        if e[0] == "defeated" and e[2] == c.player and "ARASAKA" in c.d(e[1]).tags and c.once("arasaka_defeated"):
            c.draw(1)
    return CardScript(on_play=play, on_event=ev, events=frozenset({"defeated"}))


@script("sandayu-oda-hanakos-guardian")
def _():
    def play(c):
        n = c.value_pairs()
        c.choose_many(c.rival_units(), min(n, len(c.rival_units())), min(n, len(c.rival_units())),
                      lambda c2, us: [c2.spend(u) for u in us], prompt="Spend rival Units")
    return CardScript(on_play=play, attack_perm=lambda c, b: (True, b[1]) if c.s.i_lag[c.inst] else b)


@script("placide-voodoo-sentinel")
def _():
    def eff(c):
        progs = hand_of_type(c, PROGRAM)

        def yes(c2):
            from cptcg.core.ops import discard
            c2.choose(hand_of_type(c2, PROGRAM),
                      lambda c3, i: (discard(c3.s, i), bottom_deck_one(c3, c3.rival_units())), prompt="Discard")
        if progs and c.rival_units():
            c.maybe(yes, prompt="Discard a Program to bottom-deck a rival Unit?")
    return CardScript(on_play=eff, on_attack=eff)


@script("dexter-deshawn-one-last-chance")
def _():
    def adjust(c):
        c.adjust_up_to([c.player, c.rival], -1, 1)

    def defeated(c):
        if abs(c.cred() - c.cred(c.rival)) >= 10:
            c.draw(2)
    return CardScript(on_play=adjust, on_attack=adjust, on_defeated=defeated)


# =============================================================================
# Units: ATTACK / DEFEATED triggers
# =============================================================================
@script("evelyn-parker-scheming-siren")
def _():
    def attack(c):
        c.draw(1)
        if c.more_cred():
            c.discard(1)
    return CardScript(on_attack=attack)


@script("sketchy-ripper")
def _():
    return CardScript(on_attack=lambda c: c.search_top(3, lambda i: c.is_type(i, GEAR), 0, 1))


@script("swordwise-huscle")
def _():
    return CardScript(on_attack=lambda c: c.draw(1) if c.power(sit=ATTACKING) >= 5 else None)


@script("panam-palmer-strength-through-family")
def _():
    def attack(c):
        def after(c2, picks):
            if picks:
                c2.draw(len(c2.legends(faceup=True)))
        c.discard(1, cont=after)

    from cptcg.core.ops import can_call_free
    call = Ability(effect=lambda c: c.offer_call_free(), cost=0,
                   legal=lambda c: c.is_active_turn() and can_call_free(c.s, c.player), label="Call a Legend for free")
    return CardScript(on_attack=attack, abilities=(call,))


@script("pepe-najarro-working-doubles")
def _():
    def attack(c):
        if c.has_value_pair():
            c.choose_many([l for l in c.legends() if "MERC" in c.d(l).tags and c.s.i_spent[l]], 0, 2,
                          lambda c2, ls: [c2.ready(l) for l in ls], prompt="Ready MERC Legends")
    return CardScript(on_attack=attack)


@script("jackie-welles-ride-or-die-choom")
def _():
    return CardScript(
        on_attack=lambda c: c.temp_power(c.inst, 2 * sum(1 for v in c.gig_values() if v % 2 == 0)),
        on_defeated=lambda c: c.draw(sum(1 for v in c.gig_values() if v % 2 == 1)))


@script("el-sombreron-la-venganza-lenta")
def _():
    from cptcg.core.ops import available, pay

    def attack(c):
        if available(c.s, c.player) < 2 or not c.gigs():
            return

        def yes(c2):
            pay(c2.s, c2.player, 2)
            c2.temp_power(c2.inst, max(c2.gig_values()))
        c.maybe(yes, prompt="Pay 2 €$ for +power?")
    return CardScript(on_attack=attack)


@script("goro-takemura-losing-his-way")
def _():
    return CardScript(on_attack=lambda c: c.temp_power(c.inst, 5)
                      if c.legends() and all(c.s.i_faceup[l] for l in c.legends()) else None)


@script("screw-lovelorn-fool")
def _():
    return CardScript(on_defeated=lambda c: c.choose(
        [i for i in c.trash() if c.is_type(i, UNIT) and i != c.inst],
        lambda c2, i: c2.add_to_hand(i), prompt="Add a Unit from trash"))


@script("t-bug-amateur-philosopher")
def _():
    def defeated(c):
        for l in c.legends(faceup=False):
            c.look_at(l)
        c.offer_call_free()
    return CardScript(on_defeated=defeated)


# =============================================================================
# Gear with ATTACK / DEFEATED triggers (fire for the host)
# =============================================================================
@script("dying-night-vs-pistol")
def _():
    def ev(c, e):
        h = c.host()
        if e[0] == "end_turn" and e[1] == c.player and h >= 0 and c.d(h).name == "V":
            c.ready_eddies(2)
    return CardScript(on_attack=lambda c: c.adjust_up_to([c.player, c.rival], -2, -1, prompt="Decrease a Gig"),
                      on_event=ev, events=frozenset({"end_turn"}))


@script("kiroshi-optics")
def _():
    return CardScript(on_attack=lambda c: c.choose(c.legends(faceup=False), lambda c2, l: c2.look_at(l),
                                                   prompt="Look at a face-down Legend"))


@script("the-relic-experimental-biochip")
def _():
    def defeated(c):
        hosts = c.s.mod_values("was_host", c.inst)
        host = hosts[-1] if hosts else None
        cands = [i for i in c.trash() if c.is_type(i, UNIT) and (c.d(i).cost or 0) <= 9 and i != host]

        def after(c2, i):
            c2.play_free(i)
            if host is not None and c2.s.i_zone[host] is Zone.TRASH:
                c2.bottom_deck(host)
        c.choose(cands, after, prompt="Play a Unit from trash")
    return CardScript(on_defeated=defeated)


# =============================================================================
# Units: static effects, restrictions, cost modifiers
# =============================================================================
@script("corpo-security")
def _():
    return CardScript(extra={"cant_attack": True})


@script("misty-olszewski-mender-of-broken-spirits")
def _():
    def ev(c, e):
        if e[0] != "end_turn" or e[1] != c.player:
            return

        def chosen(c2, t):
            from cptcg.core.ops import move
            top = c2.top(1)
            if not top:
                return
            if c2.d(top[0]).type is t:
                c2.add_to_hand(top[0])
                c2.ready_eddies(1)
            else:
                move(c2.s, top[0], Zone.TRASH)
        c.choose([UNIT, GEAR, PROGRAM], chosen, prompt="Choose a card type")
    return CardScript(extra={"cant_attack": True}, on_event=ev, events=frozenset({"end_turn"}))


@script("ruthless-lowlife")
def _():
    return CardScript(attack_perm=lambda c, b: (b[0], False))


@script("valentino-guerrera")
def _():
    return CardScript(extra={"attack_ready_blockers_if_more_cred": True})


@script("mtod12-flathead")
def _():
    return CardScript(unblockable=lambda c: c.less_cred())


@script("maxtac-suppression-team")
def _():
    return CardScript(extra={"suppress_new_units": True})


@script("jacked-in-voodoo-boy")
def _():
    return CardScript(attack_perm=lambda c, b: b if c.played_this_turn(lambda i: c.is_type(i, PROGRAM)) else (False, False))


@script("nadia-fighting-through-grief")
def _():
    return CardScript(attack_perm=lambda c, b: (b[0], True)
                      if c.s.i_lag[c.inst] and len(c.gigs(c.rival)) > len(c.gigs()) else b)


@script("octant")
def _():
    return CardScript(self_cost=lambda c, p, base: max(1, base - gigs_8plus(c)))


@script("maxtac-heavy")
def _():
    return CardScript(self_cost=lambda c, p, base: max(1, base - len(c.units(1 - p))))


@script("trauma-team-operatives")
def _():
    return CardScript(self_cost=lambda c, p, base: max(1, base - sum(1 for i in c.trash(p) if c.is_type(i, UNIT))))


@script("zetatech-berserk")
def _():
    return CardScript(self_cost=lambda c, p, base: max(1, base - len(c.legends(p, faceup=True))))


@script("viktor-vektor-drop-your-illusions")
def _():
    def cost_mod(c, p, inst, go_solo):
        d = c.d(inst)
        if p == c.player and d.type is GEAR and "CYBERWARE" in d.tags and (c.inst, "cyberware") not in c.s.used:
            return -3
        return 0

    def ev(c, e):
        if e[0] == "played" and e[2] == c.player and c.d(e[1]).type is GEAR and "CYBERWARE" in c.d(e[1]).tags:
            c.s.used.add((c.inst, "cyberware"))
    return CardScript(cost_mod=cost_mod, on_event=ev, events=frozenset({"played"}))


@script("riot-shield")
def _():
    return CardScript(cost_mod=lambda c, p, inst, go_solo: 2 if go_solo and p != c.player else 0)


# ---- power auras ----------------------------------------------------------------
@script("saul-bright-stormrider")
def _():
    def pm(c, unit, sit):
        return 2 if sit & ATTACKING and unit != c.inst and c.s.i_owner[unit] == c.player \
            and c.s.i_zone[unit] is Zone.FIELD else 0

    def ev(c, e):
        if e[0] == "end_turn" and e[1] == c.player:
            c.choose_many([u for u in c.units() if c.s.i_spent[u]], 0, 3,
                          lambda c2, us: [c2.ready(u) for u in us], prompt="Ready up to 3 Units")
    return CardScript(power_mod=pm, on_event=ev, events=frozenset({"end_turn"}))


@script("saburo-arasaka-stubborn-patriarch")
def _():
    return CardScript(power_mod=lambda c, unit, sit: 1 if sit & ATTACKING and c.s.i_owner[unit] == c.player
                      and "ARASAKA" in c.d(unit).tags and c.d(unit).type is UNIT else 0)


@script("meredith-stout-stone-cold-corpo")
def _():
    def ev(c, e):
        if e[0] == "gig_changed" and e[1] == c.rival and e[2] == c.player:
            c.choose(list(c.trash()), lambda c2, i: c2.add_to_hand(i), prompt="Add a card from trash", optional=True)
    return CardScript(power_mod=lambda c, unit, sit: 2 if unit == c.inst and sit & FIGHTING and sit & VS_LEGEND else 0,
                      on_event=ev, events=frozenset({"gig_changed"}))


@script("adam-smasher-ender-of-legends")
def _():
    # PLAY on a Legend fires when it GOES SOLO onto the field.
    return CardScript(on_play=lambda c: defeat_one(c, c.rival_units()))


@script("royce-psycho-on-the-edge")
def _():
    return CardScript(power_mod=lambda c, unit, sit: 2 * len(c.gear()) if unit == c.inst and c.is_active_turn()
                      and c.s.i_zone[c.inst] is Zone.FIELD else 0)


@script("johnny-silverhand-never-stop-fighting")
def _():
    def ev(c, e):
        if e[0] == "fight_won" and e[1] == c.inst and c.once("won"):
            c.ready(c.inst)
    return CardScript(extra={"wins_vs_tag": "CORPO"}, on_event=ev, events=frozenset({"fight_won"}))


# ---- end-of-turn / start-of-turn ---------------------------------------------------
@script("modded-kusanagi")
def _():
    def ev(c, e):
        if e[0] == "end_turn" and e[1] == c.player and c.in_play():
            c.return_to_hand(c.inst)
    return CardScript(on_event=ev, events=frozenset({"end_turn"}))


@script("modded-muramasa")
def _():
    def ev(c, e):
        if e[0] == "end_turn" and e[1] == c.player and c.less_cred():
            c.ready(c.inst)
    return CardScript(on_event=ev, events=frozenset({"end_turn"}))


@script("maxtac-squadron")
def _():
    def ev(c, e):
        if e[0] == "end_turn" and e[1] == c.player and c.s.i_spent[c.inst]:
            c.choose([l for l in c.legends(faceup=True) if c.s.i_spent[l]], lambda c2, l: c2.ready(l),
                     prompt="Ready a face-up Legend")
    return CardScript(on_event=ev, events=frozenset({"end_turn"}))


@script("delamain-cab")
def _():
    def ev(c, e):
        if e[0] == "end_turn" and e[1] == c.player and ("stole", c.inst) in c.s.used:
            c.ready_eddies(1)
    return CardScript(on_event=ev, events=frozenset({"end_turn"}))


@script("v-roamer-of-the-badlands")
def _():
    def ev(c, e):
        if e[0] == "steal" and e[1] == c.inst:
            idx = len(c.gigs()) - 1
            c.choose([a for a in range(1, 6) if c.gigs()[idx][1] + a <= c.gigs()[idx][0]],
                     lambda c2, a: c2.adjust_gig(c2.player, idx, a), prompt="Increase the stolen Gig", optional=True)
        elif e[0] == "end_turn" and e[1] == c.player and gigs_8plus(c) >= 2:
            c.draw(1)
    return CardScript(on_event=ev, events=frozenset({"steal", "end_turn"}))


@script("wraith-marauders")
def _():
    def ev(c, e):
        if e[0] == "steal" and e[1] == c.inst:
            v = e[4]
            c.choose([u for u in c.units() if u != c.inst and c.s.i_spent[u] and c.power(u) == v],
                     lambda c2, u: c2.ready(u), prompt="Ready a Unit")
    return CardScript(on_event=ev, events=frozenset({"steal"}))


@script("6th-street-recruits")
def _():
    def ev(c, e):
        # "increase a Gig" is unscoped here, as it is on La Llorona and Dexter Deshawn in this
        # set, so either player's Gig may be increased; only text that says "a friendly Gig"
        # (Jackie Welles) narrows it. Increase only, hence 1..6.
        if e[0] == "steal" and e[3] == 6 and c.s.i_owner[e[1]] == c.player \
                and c.d(e[1]).type is UNIT:
            c.adjust_up_to([c.player, c.rival], 1, 6, prompt="Increase a Gig")
    return CardScript(on_event=ev, events=frozenset({"steal"}))


@script("maelstrom-goons")
def _():
    def ev(c, e):
        if e[0] == "steal" and e[1] == c.inst and c.equipped(c.inst):
            discard_rival(c, 1)
    return CardScript(on_event=ev, events=frozenset({"steal"}))


@script("maelstrom-zealots")
def _():
    def ev(c, e):
        if e[0] == "fight_lost" and e[1] == c.inst:
            c.defeat(e[2])
    return CardScript(on_event=ev, events=frozenset({"fight_lost"}))


@script("la-llorona-ghost-of-the-past")
def _():
    def ev(c, e):
        if e[0] == "blocked" and e[1] == c.inst:
            c.adjust_up_to([c.player, c.rival], 1, 3, prompt="Increase a Gig")
    return CardScript(on_event=ev, events=frozenset({"blocked"}))


@script("augmented-negotiators")
def _():
    def ev(c, e):
        if e[0] == "blocked" and e[1] == c.inst:
            discard_rival(c, 1)
    return CardScript(on_event=ev, events=frozenset({"blocked"}))


@script("rita-wheeler-no-stupid-questions")
def _():
    def ev(c, e):
        if e[0] == "spent" and e[1] == c.inst and c.once("spent"):
            c.draw(1)
            c.discard(1)
    return CardScript(on_event=ev, events=frozenset({"spent"}))


@script("alt-cunningham-mother-of-daemons")
def _():
    def ev(c, e):
        if e[0] == "spent" and c.s.i_owner[e[1]] == c.player and c.equipped(e[1]):
            c.draw(1)

    def would_steal(c, thief_unit, victim, index):
        if victim != c.player:
            return False
        from cptcg.core.steps import do_steal
        val = c.gigs()[index][1]
        cands = [i for i in c.hand() if (c.d(i).cost or 0) == val]
        if not cands:
            return False
        thief = c.s.i_owner[thief_unit]

        def decide(c2, i):
            from cptcg.core.ops import discard
            discard(c2.s, i)
        c.choose(cands, decide, prompt="Discard to prevent the steal?", optional=True,
                 otherwise=lambda c2: do_steal(c2.s, thief_unit, thief, index))
        return True
    return CardScript(on_event=ev, events=frozenset({"spent"}), would_steal=would_steal)


# =============================================================================
# Gear: host-spent triggers and statics
# =============================================================================
def _host_spent(c, e):
    return e[0] == "spent" and e[1] == c.host()


@script("gorilla-arms")
def _():
    def ev(c, e):
        if e[0] == "steal" and e[1] == c.host() and c.once("steal"):
            from cptcg.core.steps import push_steals
            mine = set(c.gig_values())
            cands = [i for i, (_k, v) in enumerate(c.gigs(c.rival)) if v not in mine]
            c.choose(cands, lambda c2, i: push_steals(c2.s, c2.host(), [i]), prompt="Steal a rival Gig")
    return CardScript(on_event=ev, events=frozenset({"steal"}))


@script("adrenaline-converter")
def _():
    def kw_mod(c, inst, kw):
        # "this Unit" is the host and nobody else. The Gig counts change mid-turn (a steal is
        # enough), so the condition is read on every has_keyword call instead of being granted.
        return (kw is ADRENALINE and inst == c.host()
                and len(c.gigs(c.rival)) >= len(c.gigs()) + 2)
    return CardScript(kw_mod=kw_mod)


@script("zetatech-faceplate")
def _():
    def ev(c, e):
        if _host_spent(c, e):
            def after(c2, _o, _i):
                if len(set(c2.gig_values())) >= 3:
                    c2.draw(1)
            c.adjust_up_to([c.player, c.rival], -1, 1, cont=after)
    return CardScript(on_event=ev, events=frozenset({"spent"}))


@script("tetratronic-rippler")
def _():
    def ev(c, e):
        if _host_spent(c, e):
            top = c.top(1)
            if top:
                from cptcg.core.ops import move
                c.maybe(lambda c2: move(c2.s, top[0], Zone.TRASH), prompt=f"Trash {c.d(top[0]).name}?")
    return CardScript(on_event=ev, events=frozenset({"spent"}))


@script("netwatch-netdriver")
def _():
    return CardScript(events=frozenset({"spent"}), on_event=lambda c, e: c.draw(1) if _host_spent(c, e) else None)


@script("arasaka-emergency-radioport")
def _():
    def ev(c, e):
        if not _host_spent(c, e):
            return

        def look(c2, l):
            c2.look_at(l)
            d = c2.d(l)
            if "ARASAKA" in d.tags or GO_SOLO in d.keywords:
                c2.maybe(lambda c3: c3.call_free(l), prompt=f"Call {d.name} for free?")
        c.choose(c.legends(faceup=False), look, prompt="Look at a face-down Legend", optional=True)
    return CardScript(on_event=ev, events=frozenset({"spent"}))


@script("sandevistan")
def _():
    def ev(c, e):
        if e[0] == "end_turn" and e[1] == c.player and c.host() >= 0:
            c.ready(c.host())
    return CardScript(on_event=ev, events=frozenset({"end_turn"}))


@script("satori-sword-of-saburo")
def _():
    def ev(c, e):
        if e[0] == "fight_won" and e[1] == c.host() and c.d(e[2]).type is UNIT:
            c.draw(1)
    return CardScript(on_event=ev, events=frozenset({"fight_won"}))


@script("deadman-transmitter")
def _():
    def would_defeat(c, inst):
        if inst == c.host():
            c.defeat(c.inst)
            return True
        return False
    return CardScript(would_defeat=would_defeat)


@script("overwatch-panams-gift")
def _():
    def eff(c):
        def after(c2, picks):
            if picks:
                lim = c2.d(picks[0]).cost or 0
                defeat_one(c2, [u for u in c2.rival_units() if c2.s.i_spent[u] and (c2.d(u).cost or 0) <= lim])
        c.discard(1, cont=after)
    return CardScript(abilities=(Ability(effect=eff, cost=1, self_spend=True, quick=True,
                                         legal=lambda c: bool(c.hand()), label="Discard: defeat"),))


# =============================================================================
# Legends
# =============================================================================
def _choose_one_call(options):
    return lambda c: c.choose_one(options)


@script("v-streetkid")
def _():
    def call(c):
        ts = c.trash_top(3)
        c.choose([i for i in c.trash() if c.is_type(i, PROGRAM) and "BRAINDANCE" in c.d(i).tags],
                 lambda c2, i: c2.add_to_hand(i), prompt="Add a BRAINDANCE Program")
    return CardScript(on_call=call)


@script("wakako-okada-peace-and-harmony")
def _():
    return CardScript(
        on_call=_choose_one_call([("Rival Unit -2 power", lambda c: temp_power_one(c, c.rival_units(), -2)),
                                  ("Draw 1", lambda c: c.draw(1))]),
        abilities=(Ability(effect=lambda c: c.adjust_up_to([c.player, c.rival], -2, -1, prompt="Decrease a Gig"),
                           self_spend=True, label="Decrease a Gig by up to 2"),))


@script("dexter-deshawn-off-the-grid")
def _():
    return CardScript(
        on_call=_choose_one_call([("Friendly Unit +2 power", lambda c: temp_power_one(c, c.units(), 2)),
                                  ("Draw 1", lambda c: c.draw(1))]),
        abilities=(Ability(effect=lambda c: c.adjust_up_to([c.player, c.rival], 1, 2, prompt="Increase a Gig"),
                           self_spend=True, label="Increase a Gig by up to 2"),))


@script("padre-man-of-the-cross")
def _():
    def set_gig(c):
        def target(c2, o, i):
            def source(c3, src):
                c3.set_gig(o, i, c3.gigs(src[0])[src[1]][1])
            c2.choose([(1 - o, j) for j in range(len(c2.gigs(1 - o)))], source, prompt="To the value of")
        c.choose_gig([0, 1], target, prompt="Set which Gig?")
    return CardScript(
        on_call=_choose_one_call([("Spend a rival Unit", lambda c: spend_one(c, c.rival_units())),
                                  ("Draw 1", lambda c: c.draw(1))]),
        abilities=(Ability(effect=set_gig, self_spend=True, label="Set a Gig to another player's Gig"),))


@script("muamar-reyes-el-capitan")
def _():
    return CardScript(
        on_call=_choose_one_call([("A friendly Unit can't be defeated in a fight this turn",
                                   lambda c: c.choose(c.units(), lambda c2, u: c2.mod("no_defeat_in_fight", u))),
                                  ("Draw 1", lambda c: c.draw(1))]),
        abilities=(Ability(effect=lambda c: c.adjust_up_to([c.player, c.rival], -1, 1, prompt="Adjust a Gig by 1"),
                           self_spend=True, label="Adjust a Gig by 1"),))


@script("viktor-vektor-sit-down-and-relax")
def _():
    return CardScript(on_call=lambda c: c.search_top(
        5, lambda i: c.is_type(i, GEAR) and (c.d(i).cost or 0) <= 2, 0, 2, bottom_random=True))


@script("dum-dum-maelstrom-triggerman")
def _():
    def call(c):
        c.choose(c.all_gear(), lambda c2, g: (c2.defeat(g), c2.draw(2)), prompt="Defeat a friendly Gear?",
                 optional=True, otherwise=lambda c2: c2.draw(1))

    def pump(c):
        c.choose(c.units(), lambda c2, u: c2.temp_power(u, len(c2.gear(u))), prompt="+1 power per Gear")
    return CardScript(on_call=call, abilities=(Ability(effect=pump, cost=1, self_spend=True, quick=True,
                                                       label="+1 power per equipped Gear"),))


@script("river-ward-detective-on-the-hunt")
def _():
    def free_gear(c):
        c.choose([i for i in c.hand() if c.is_type(i, GEAR) and (c.d(i).cost or 0) <= 2],
                 lambda c2, g: c2.play_free(g), prompt="Play a Gear for free")

    def ev(c, e):
        if e[0] == "defeated" and e[2] == c.player and e[3] and c.d(e[1]).type is UNIT:
            from cptcg.core.ops import move
            top = c.top(2)
            c.choose(top, lambda c2, i: move(c2.s, i, Zone.TRASH), prompt="Trash 1 of the top 2")
    return CardScript(abilities=(Ability(effect=free_gear, self_spend=True, quick=True, label="Play a cheap Gear"),),
                      on_event=ev, events=frozenset({"defeated"}))


@script("kerry-eurodyne-axe-attitude-audience")
def _():
    def ev(c, e):
        if e[0] != "gig_rolled" or e[1] != c.player:
            return
        sides, value = e[2], e[3]
        idx = len(c.gigs()) - 1

        def after(c2, sides=sides):
            v = c2.gigs()[idx][1]
            if v == 1 or v == sides:
                c2.draw(3 if sides == 20 else 1)

        def reroll(c2):
            from cptcg.core.ops import reroll_gig
            reroll_gig(c2.s, c2.player, idx)
            after(c2)
        if (c.inst, "reroll_offer") in c.s.used:
            after(c)
            return
        c.s.used.add((c.inst, "reroll_offer"))
        c.maybe(reroll, prompt=f"Reroll the d{sides} ({value})?", )
        # if declined, the original roll stands: check min/max on it
        c.later(lambda c2: after(c2) if not c2.s.has_mod("rerolled", c2.inst) else None)
    return CardScript(on_event=ev, events=frozenset({"gig_rolled"}))


@script("evelyn-parker-beautiful-enigma")
def _():
    def ev(c, e):
        if e[0] == "steal" and c.s.i_owner[e[1]] == c.player and c.d(e[1]).tags & {"CORPO", "GANGER"}:
            c.ready_eddies(1)
    return CardScript(on_event=ev, events=frozenset({"steal"}), abilities=(Ability(
        effect=lambda c: c.choose(c.rival_units(), lambda c2, u: c2.mod("must_attack", u, until_my_next_turn=True),
                                  prompt="Must attack next turn"),
        cost=1, self_spend=True, label="A rival Unit must attack"),))


@script("hanako-arasaka-daughter-of-the-emperor")
def _():
    def swap(c):
        def mine(c2, _o, i):
            c2.choose_gig([c2.rival], lambda c3, _o2, j: c3.swap_gig(i, j), prompt="Swap with")
        c.choose_gig([c.player], mine, prompt="Swap which friendly Gig?")

    def ev(c, e):
        if e[0] == "start_turn" and e[1] == c.player and c.value_pairs():
            c.draw(c.value_pairs())
    return CardScript(abilities=(Ability(effect=swap, self_spend=True, label="Swap Gigs",
                                         legal=lambda c: bool(c.gigs()) and bool(c.gigs(c.rival))),), on_event=ev, events=frozenset({"start_turn"}))


@script("panam-palmer-nomad-cavalry")
def _():
    def move_gear(c):
        from cptcg.core.ops import move
        def pick(c2, g):
            c2.choose([u for u in c2.units() if not c2.equipped(u)],
                      lambda c3, u: (move(c3.s, g, Zone.FIELD, host=u), c3.ready(u)), prompt="Move Gear to")
        c.choose(c.gear(), pick, prompt="Move which Gear?")

    def ev(c, e):
        if e[0] == "end_turn" and e[1] == c.player:
            eq = [u for u in c.units() + c.legends(faceup=True) if c.equipped(u)]
            if len(eq) >= 5:
                for u in eq:
                    c.ready(u)
    return CardScript(abilities=(Ability(effect=move_gear, cost=2, self_spend=True, label="Move a Gear",
                                         legal=lambda c: bool(c.gear()) and any(not c.equipped(u) for u in c.units())),),
                      on_event=ev, events=frozenset({"end_turn"}))


@script("johnny-silverhand-rocking-renegade")
def _():
    def eff(c):
        def give(c2, u):
            c2.mod("attack_units_now", u)
            if "ROCKER" in c2.d(u).tags:
                c2.temp_power(u, 2)
        c.choose(c.units(), give, prompt="A friendly Unit can attack spent rival Units now")
    return CardScript(abilities=(Ability(effect=eff, cost=lambda c: max(0, 2 - gigs_8plus(c)), self_spend=True,
                                         label="Unit may attack this turn"),))


@script("judy-alvarez-braindance-maestro")
def _():
    def ev(c, e):
        if e[0] == "played" and e[2] == c.player and c.d(e[1]).type is PROGRAM and "BRAINDANCE" in c.d(e[1]).tags:
            temp_power_one(c, c.units(), 1)

    def mill(c):
        ts = c.trash_top(1)
        if ts and c.is_type(ts[0], PROGRAM):
            c.maybe(lambda c2: c2.add_to_hand(ts[0]), prompt=f"Add {c.d(ts[0]).name} to hand?")
    return CardScript(on_event=ev, events=frozenset({"played"}), abilities=(Ability(effect=mill, self_spend=True, label="Trash top; take a Program"),))


@script("alt-cunningham-soulkiller-architect")
def _():
    from cptcg.core.ops import available, pay, play_cost

    def discount(c):
        c.mod("cost_next_program", c.player, -len(c.min_gigs()))

    def from_trash(c):
        cands = [i for i in c.trash() if c.is_type(i, PROGRAM) and play_cost(c.s, c.player, i) <= available(c.s, c.player)]

        def go(c2, i):
            from cptcg.core.engine import play_card
            c2.later(lambda c3: c3.bottom_deck(i))
            play_card(c2.s, c2.player, i, cost=play_cost(c2.s, c2.player, i))
        c.choose(cands, go, prompt="Play a Program from trash")
    return CardScript(abilities=(
        Ability(effect=discount, self_spend=True, label="Next Program costs less", legal=lambda c: bool(c.min_gigs())),
        Ability(effect=from_trash, cost=1, self_spend=True, label="Play a Program from trash")))


@script("jackie-welles-mamas-favorite")
def _():
    from cptcg.core.ops import available, pay

    def would_defeat(c, inst):
        if c.s.i_owner[inst] != c.player or c.d(inst).type is not UNIT or not c.in_play() \
                or c.s.i_zone[c.inst] is not Zone.LEGENDS or available(c.s, c.player, exclude=c.inst) < 1:
            return False
        from cptcg.core.ops import defeat, move
        me = c.inst

        def save(c2):
            # The option was offered when 1 €$ was available; by the time the pick is applied
            # (a search preview may run other choices first) the last Eddie can be spent, and
            # a replacement you cannot pay for does not happen: the Unit is defeated as normal.
            if available(c2.s, c2.player, exclude=me) < 1:
                defeat(c2.s, inst, allow_replace=False)
                return
            pay(c2.s, c2.player, 1, exclude=me)
            c2.s.i_flags[me] |= __import__("cptcg.core.enums", fromlist=["F_GO_SOLO"]).F_GO_SOLO
            defeat(c2.s, me, allow_replace=False)
        c.choose([True], lambda c2, _v: save(c2), prompt=f"Pay 1 €$: defeat Jackie instead of {c.d(inst).name}?",
                 optional=True, otherwise=lambda c2: defeat(c2.s, inst, allow_replace=False))
        return True
    return CardScript(would_defeat=would_defeat)


@script("jackie-welles-pour-one-out-for-me")
def _():
    def ev(c, e):
        if e[0] == "played" and e[2] == c.player and c.d(e[1]).color.name == "BLUE" \
                and c.d(e[1]).type in (UNIT, GEAR) and c.once("blue"):
            def after(c2, o, i):
                if c2.gigs(o)[i][1] == 1:
                    c2.draw(1)
            c.adjust_up_to([c.player], -2, -1, cont=after, prompt="Decrease a friendly Gig")
    return CardScript(on_event=ev, events=frozenset({"played"}))


@script("rogue-amendiares-preem-solo")
def _():
    def ev(c, e):
        if e[0] == "steal" and c.s.i_owner[e[1]] == c.player and c.d(e[1]).type is LEGEND:
            if e[4] % 2 == 0:
                c.draw(1)
            else:
                discard_rival(c, 1)
    return CardScript(on_event=ev, events=frozenset({"steal"}))


@script("goro-takemura-vengeful-bodyguard")
def _():
    def give(c):
        def to(c2, u):
            c2.grant(u, BLOCKER)
            if c2.has_value_pair():
                c2.temp_power(u, 1)
        c.choose([u for u in c.units() if (c.d(u).cost or 0) <= 4], to, prompt="Give BLOCKER")

    def ev(c, e):
        if e[0] == "blocked" and c.s.i_owner[e[1]] == c.player and c.hand():
            c.maybe(lambda c2: c2.discard(1, cont=lambda c3, ps: c3.draw(1) if ps else None),
                    prompt="Discard 1 to draw 1?")
    return CardScript(abilities=(Ability(effect=give, cost=1, self_spend=True, quick=True, label="Give BLOCKER"),),
                      on_event=ev, events=frozenset({"blocked"}))


@script("yorinobu-arasaka-embracing-destruction")
def _():
    def ev(c, e):
        if e[0] == "attack" and e[2] == c.player and "ARASAKA" in c.d(e[1]).tags and c.once("arasaka_attack"):
            c.draw(1)
            if c.cred() < 20:
                c.discard(1)
    return CardScript(on_event=ev, events=frozenset({"attack"}))


@script("sasha-yakovleva-wont-let-you-down")
def _():
    def attack(c):
        top = c.top(1)
        if top:
            c.add_to_hand(top[0])
            c.temp_power(c.inst, c.d(top[0]).cost or 0)
    return CardScript(on_attack=attack, on_defeated=lambda c: discard_rival(c, 1))


# =============================================================================
# Units with activated abilities
# =============================================================================
@script("judy-alvarez-nothing-to-doubt")
def _():
    def eff(c):
        top = c.top(1)
        if not top:
            return
        i = top[0]
        c.add_to_hand(i)                                   # reveal: it goes to hand either way...
        if c.d(i).type is not LEGEND and c.d(i).cost is not None:
            def free(c2):
                c2.play_free(i)
            c.maybe(free, prompt=f"Play {c.d(i).name} for free?")
    return CardScript(abilities=(Ability(effect=eff, cost=1, self_spend=True, label="Reveal top: play free or keep"),))


@script("kerry-eurodyne-the-last-rockerboy")
def _():
    return CardScript(abilities=(Ability(effect=lambda c: c.draw(2) if gigs_8plus(c) else None, self_spend=True,
                                         legal=lambda c: gigs_8plus(c) > 0, label="Draw 2"),))


@script("rogue-amendiares-queen-of-the-afterlife")
def _():
    def ev(c, e):
        if e[0] == "steal" and e[1] != c.inst and c.s.i_owner[e[1]] == c.player \
                and e[4] < c.power(e[1]) and c.once("ready_eddies"):
            c.ready_eddies(2)

    def drain(c):
        p = c.power()
        temp_power_one(c, c.rival_units(), -p)
    return CardScript(on_event=ev, events=frozenset({"steal"}), abilities=(Ability(effect=drain, cost=2, self_spend=True, quick=True,
                                                      label="Rival Unit loses power"),))
