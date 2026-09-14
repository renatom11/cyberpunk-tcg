"""Batch A03 — Programs: removal, card flow, tempo (part 3/3).

Audit of src/cptcg/cards/sets/wnc.py lines 232-318 against the printed ``text`` in
data/cards/wnc.json. Every test here is a finding: it asserts what the card *says*, so it fails
against the script as written. See out/audit/a03/findings.md for the clause maps.
"""
import pytest
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, EndTurn, Play, Target
from cptcg.core.enums import TARGET_UNIT, Zone

E = 9  # plenty of eddies


def play(s, cid):
    do(s, Play(find(s, cid, Zone.HAND)))
    return s


# --------------------------------------------------------------------------- AUD-reboot-optics-1
def test_reboot_optics_shield_covers_only_the_next_fight(pool):
    """"QUICK: The next time a rival Unit fights this turn, it doesn't defeat the opposing
    friendly Unit."

    Maxtac (7) kills the spent Corpo Security (2): a rival Unit has fought, so the shield is spent
    — it protected nobody, but the card names the *fight* as the trigger, not the defeat. The
    second fight, Psycho Squad (6) into the spent Animals Wrecker (10), is therefore unshielded
    and Psycho Squad must be defeated. (Under the narrower reading of "a rival Unit fights" —
    only a rival Unit that attacks — the shield never applies on our own turn at all, and Psycho
    Squad dies for that reason instead. Both readings kill it; the script saved it.)

    Fixed: AUD-reboot-optics-1.
    """
    s = board(pool, Side(hand=["reboot-optics"], eddies=E,
                         field=["maxtac-suppression-team", "psycho-squad"]),
              Side(field=[("corpo-security", {"spent": True}),
                          ("animals-wrecker", {"spent": True})]))
    corpo, wrecker = find(s, "corpo-security"), find(s, "animals-wrecker")
    mine = find(s, "psycho-squad")
    play(s, "reboot-optics")
    do(s, Attack(find(s, "maxtac-suppression-team")))
    do(s, Target(TARGET_UNIT, corpo))
    assert s.i_zone[corpo] == Zone.TRASH                 # fight 1 happened: a rival Unit fought
    do(s, Attack(mine))
    do(s, Target(TARGET_UNIT, wrecker))
    assert s.i_zone[wrecker] == Zone.FIELD               # fight 2 happened and 10 beat 6
    assert s.i_zone[mine] == Zone.TRASH


# --------------------------------------------------------------------------- AUD-cyberpsychosis-1
def test_cyberpsychosis_defeats_a_unit_that_fought_to_a_tie(pool):
    """"QUICK: Give an equipped Unit +3 power this turn for each of its equipped Gears. If that
    Unit steals or fights, defeat it at the end of this turn."

    Psycho Squad (6) + Deadman Transmitter (1) + 3 = 10 ties the spent Animals Wrecker (10).
    Ruling 010 / CR 9.17.3: on a tie both are defeated — the Gear takes our Unit's defeat instead
    (Deadman Transmitter), so the Unit survives the fight it fought. It fought, so it must be
    defeated at the end of the turn.

    Fixed: AUD-cyberpsychosis-1.
    """
    s = board(pool, Side(hand=["cyberpsychosis"], eddies=E,
                         field=[("psycho-squad", {"gear": ["deadman-transmitter"]})],
                         deck=["floor-it"] * 3),
              Side(field=[("animals-wrecker", {"spent": True})], deck=["floor-it"] * 3))
    u, wrecker = find(s, "psycho-squad"), find(s, "animals-wrecker")
    gear = find(s, "deadman-transmitter")
    play(s, "cyberpsychosis")
    do(s, Attack(u))
    do(s, Target(TARGET_UNIT, wrecker))
    assert s.i_zone[wrecker] == Zone.TRASH    # the tie was resolved: 10 vs 10
    assert s.i_zone[gear] == Zone.TRASH       # the Gear took our Unit's defeat instead
    assert s.i_zone[u] == Zone.FIELD          # ... so the Unit that fought is still on the field
    do(s, EndTurn())
    assert s.i_zone[u] == Zone.TRASH
