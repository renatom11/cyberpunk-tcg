"""Batch b03 — confirmations: ``on_play`` sides, counts, optionality and ordering, and the engine
was right.

Nine scenarios the b03 cross-cutting pass suspected, drove through the engine, and found correct.
They are kept because a negative result is only worth its check: the census in
out/audit/b03/findings.md says the whole ``on_play`` column agrees with the printed text, and these
are the boards behind the rows most likely to be mis-read by the next person — the three unqualified
nouns that mean *both* players', the one-shot trigger, the "for each" count, and the separate
printed sentence that must still run when the prompt before it has nothing to offer.

Every assertion is a printed-text outcome: zones, Gig faces, hand size, keywords.
"""
from conftest import Side, board, do, find, options

from cptcg.core import ops
from cptcg.core.actions import Attack, ChoiceKind, Pass, Pick, Play
from cptcg.core.enums import Keyword, Zone

E = 9  # plenty of eddies


def play(s, cid):
    do(s, Play(find(s, cid, Zone.HAND)))
    return s


def ids(s, p, zone=Zone.FIELD):
    return sorted(s.card(i).id for i in s.zone(p, zone))


# --------------------------------------------------------------- unqualified nouns mean both sides
def test_adam_smasher_defeats_every_other_unit_on_both_sides_but_not_a_legend_in_its_area(pool):
    """'PLAY: Defeat all other Units.' — 'all other' is unqualified, so it is both players'.

    The two halves a reader can get wrong in opposite directions: a Legend sitting face-up in the
    *Legends area* is not a Unit and survives, while Adam Smasher himself is excluded by the printed
    word 'other'. Every Unit on either field goes.
    """
    s = board(pool, Side(hand=["adam-smasher-metal-over-meat"], eddies=E,
                         field=["emergency-atlus", "hacked-corpo"],
                         legends=[("adam-smasher-ender-of-legends", {"faceup": True})]),
              Side(field=["maxtac-av", "sketchy-ripper"]))
    play(s, "adam-smasher-metal-over-meat")
    assert ids(s, 0) == ["adam-smasher-metal-over-meat"]      # his own field cleared but himself
    assert ids(s, 1) == []                                    # ... and the Rival's too
    assert ids(s, 0, Zone.LEGENDS) == ["adam-smasher-ender-of-legends"]   # a Legend is not a Unit


def test_heywood_ripperdoc_may_defeat_a_rival_gear_and_draws_on_a_cost_match(pool):
    """'PLAY: You may defeat a Gear. If its cost equals the value of a friendly Gig, draw 1.'

    'a Gear' is unqualified, so a *rival's* Gear is a legal target — Gilded Maton prints 'a
    **friendly** Gear' and Detonate 'a **rival** Gear' when they mean to narrow it. Overwatch costs
    4 and the only friendly Gig shows 4, so the second sentence fires; 'its' refers back to the Gear
    that was defeated, so nesting that clause is correct.
    """
    s = board(pool, Side(hand=["heywood-ripperdoc"], eddies=E, gig=[(4, 4)], deck=["floor-it"]),
              Side(field=[("sketchy-ripper", {"gear": ["overwatch-panams-gift"]})]))
    play(s, "heywood-ripperdoc")
    do(s, Pick((0,)))                                         # the Rival's Gear is on the menu
    assert ids(s, 1) == ["sketchy-ripper"]                    # the Gear is gone, its host is not
    assert ids(s, 1, Zone.TRASH) == ["overwatch-panams-gift"]
    assert len(s.zone(0, Zone.HAND)) == 1                     # cost 4 == the friendly Gig's value


def test_dont_fear_the_reaper_can_be_forced_onto_your_own_spent_unit(pool):
    """'Spend all rival Units. Then, defeat a spent Unit.'

    'a spent Unit' is unqualified and the clause prints no 'may', so with the Rival's board empty
    the only spent Unit in play is the controller's own and it must be defeated. Wild in the
    Streets prints the identical unqualified clause and builds the identical both-sides list.
    """
    s = board(pool, Side(hand=["dont-fear-the-reaper"], eddies=E,
                         field=[("emergency-atlus", {"spent": True}), "hacked-corpo"]),
              Side())
    play(s, "dont-fear-the-reaper")
    assert ids(s, 0) == ["hacked-corpo"]                      # the ready Unit was never a candidate
    assert ids(s, 0, Zone.TRASH) == ["dont-fear-the-reaper", "emergency-atlus"]


def test_dont_fear_the_reaper_counts_the_units_it_just_spent(pool):
    """'Spend all rival Units. **Then**, defeat a spent Unit.'

    'Then' sequences the two, so the candidate list is built *after* the mass spend — a rival Unit
    that was ready a moment ago is a legal target for the defeat.
    """
    s = board(pool, Side(hand=["dont-fear-the-reaper"], eddies=E), Side(field=["sketchy-ripper"]))
    play(s, "dont-fear-the-reaper")
    assert ids(s, 1) == []                                    # spent by sentence one, then defeated
    assert ids(s, 1, Zone.TRASH) == ["sketchy-ripper"]


# ------------------------------------------------------------------------------ counts and bounds
def test_sandayu_oda_spends_one_rival_unit_per_friendly_value_pair(pool):
    """'PLAY: Spend a rival Unit for each friendly value-pair of Gigs.'

    Two friendly value-pairs (3,3 and 5,5), three rival Units: the prompt is exactly two, not
    'up to two' and not all three. The card prints no 'may', so declining is not on the menu.
    """
    s = board(pool, Side(hand=["sandayu-oda-hanakos-guardian"], eddies=E,
                         gig=[(6, 3), (8, 3), (10, 5), (12, 5)]),
              Side(field=["sketchy-ripper", "emergency-atlus", "maxtac-av"]))
    play(s, "sandayu-oda-hanakos-guardian")
    assert all(len(o.picks) == 2 for o in s.pending.options), "exactly two, no more and no fewer"
    do(s, Pick((0, 2)))
    spent = sorted(s.card(u).id for u in s.zone(1, Zone.FIELD) if s.i_spent[u])
    assert spent == ["maxtac-av", "sketchy-ripper"]
    assert not any(s.i_spent[u] for u in s.zone(1, Zone.FIELD)
                   if s.card(u).id == "emergency-atlus")


def test_valentino_street_racer_cannot_give_adrenaline_to_itself(pool):
    """'PLAY: Give **another friendly** Unit with cost 5 or less ADRENALINE this turn.'

    Three words of scope in one clause and all three bind here: 'another' excludes the Racer,
    'friendly' excludes the Rival's Unit, and 'cost 5 or less' excludes Adam Smasher at 9 — leaving
    exactly one legal target, which the mandatory prompt takes without asking.
    """
    s = board(pool, Side(hand=["valentino-street-racer"], eddies=E,
                         field=[("emergency-atlus", {"lag": True}),
                                ("adam-smasher-metal-over-meat", {"lag": True})]),
              Side(field=["sketchy-ripper"]))
    play(s, "valentino-street-racer")
    got = {s.card(u).id: ops.has_keyword(s, u, Keyword.ADRENALINE) for u in s.zone(0, Zone.FIELD)}
    assert got == {"emergency-atlus": True, "adam-smasher-metal-over-meat": False,
                   "valentino-street-racer": False}
    assert not ops.has_keyword(s, find(s, "sketchy-ripper", player=1), Keyword.ADRENALINE)


def test_take_control_really_makes_a_rival_unit_steal_one_fewer_gig(pool):
    """'QUICK: A rival Unit steals 1 fewer Gig this turn.'

    A printed reduction is only real if the site that counts the steal reads it. Adam Smasher at
    power 15 takes two Gigs off an unattended Gig area; played as a reaction, Take Control leaves
    him one.
    """
    def run(use_it):
        s = board(pool, Side(hand=["take-control"], eddies=E, gig=[(6, 3), (8, 5), (10, 7)],
                             deck=["floor-it"]),
                  Side(field=["adam-smasher-metal-over-meat"], eddies=E), active=1)
        do(s, Attack(find(s, "adam-smasher-metal-over-meat", player=1)))
        for _ in range(4):
            if s.pending is None or s.pending.kind is not ChoiceKind.REACTION:
                break
            plays = [o for o in options(s) if isinstance(o, Play)]
            do(s, plays[0] if (use_it and plays) else Pass())
            use_it = False
        for _ in range(6):
            if s.pending is None or s.pending.kind is ChoiceKind.MAIN:
                break
            do(s, s.pending.options[0])
        return len(s.gig[0])

    assert run(False) == 1, "power 15 steals two of the three Gigs"
    assert run(True) == 2, "with Take Control it steals one"


def test_appetite_for_destruction_fires_once_even_across_two_qualifying_wins(pool):
    """'**The next time** a friendly Unit wins a fight by 3+ power this turn, it also steals a Gig.'

    A one-shot, not an until-end-of-turn modifier. Two friendly attackers (power 8) each win a
    fight by 4 against a spent 4-power defender in the same turn; exactly one extra Gig changes
    hands, and the same board without the Program moves none at all — a fight steals nothing by
    itself, so the one Gig is the trigger and the second win did not fire it again.
    """
    def run(with_program):
        s = board(pool, Side(hand=["appetite-for-destruction"], eddies=E,
                             field=["maxtac-av", "sandayu-oda-hanakos-guardian"], gig=[(4, 1)]),
                  Side(field=[("emergency-atlus", {"spent": True}),
                              ("emergency-atlus", {"spent": True})],
                       gig=[(6, 3), (8, 5), (10, 7)]))
        if with_program:
            play(s, "appetite-for-destruction")
        for atk in ("maxtac-av", "sandayu-oda-hanakos-guardian"):
            do(s, Attack(find(s, atk, Zone.FIELD, 0)))
            for _ in range(8):
                if s.pending is None or s.pending.kind is ChoiceKind.MAIN:
                    break
                do(s, s.pending.options[0])
        assert ids(s, 1) == [], "both defenders lost their fights"
        return len(s.gig[0]), len(s.gig[1])

    assert run(False) == (1, 3), "a won fight steals nothing on its own"
    assert run(True) == (2, 2), "one extra Gig for the first 3+ win, and only the first"


# ------------------------------------------------------- a separate sentence runs with no prompt
def test_floor_it_still_draws_when_there_is_no_rival_unit_to_weaken(pool):
    """'QUICK: Give a rival Unit -1 power this turn. Draw 1.'

    Two printed sentences and the second is not conditional on the first. With the Rival's field
    empty the prompt has no candidate and is skipped entirely — the shape that swallows the second
    sentence on six other cards in this set — and 'Draw 1' still happens, because it is written
    outside the continuation rather than inside it.
    """
    s = board(pool, Side(hand=["floor-it"], eddies=E, deck=["all-is-lost"]), Side())
    play(s, "floor-it")
    assert ids(s, 0, Zone.HAND) == ["all-is-lost"]


def test_carnage_at_the_colosseum_has_no_target_without_a_friendly_unit(pool):
    """'Defeat a rival Unit with less power than a friendly Unit.'

    The threshold is a board fact, not a printed number: with no friendly Unit in play there is
    nothing for a rival Unit to have less power than, so the mandatory prompt has no candidate and
    every rival Unit survives.
    """
    s = board(pool, Side(hand=["carnage-at-the-colosseum"], eddies=E), Side(field=["sketchy-ripper"]))
    play(s, "carnage-at-the-colosseum")
    assert ids(s, 1) == ["sketchy-ripper"]
    assert ids(s, 0, Zone.TRASH) == ["carnage-at-the-colosseum"]
