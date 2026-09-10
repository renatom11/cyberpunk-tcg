"""Transcription of Welcome to Night City (MS01-WNC) + starter-set cards, from screenshots of
the official card database. Emits data/cards/wnc.json.

Kept as Python because it is far more compact and diffable than hand-written JSON. The JSON
file is what the engine loads; this script is how it was produced and how corrections are made.

Field notes:
  power  — printed power; a trailing "+" means "N+" (variable, board-dependent).
  sell   — whether the card shows the sell tag (€$).
  number — collector number as read from the card edge; small and rotated, so treat as
           approximate. Ids are name slugs for that reason.
  verified — every rules-relevant field was read from the full card face.
"""
import json
import re
import unicodedata
from pathlib import Path

CARDS = []
WNC, HEI, EBP = "MS01-WNC", "S001-HEI", "S002-EBP"


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"['\u2019\"]", "", s)          # rockn-rockerboy, not rockn-rockerboy-... / dont-fear
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def C(name, sub, type_, color, ram, cost, power, sell, tags, kws, text, number,
      set_=WNC, verified=True, flavor=None, notes=None):
    cid = slug(name) + (("-" + slug(sub)) if sub else "")
    assert cid not in {c["id"] for c in CARDS}, cid
    d = dict(id=cid, name=name, subtitle=sub, type=type_, color=color, ram=ram, cost=cost,
             power=power, sell_tag=sell, tags=list(tags), keywords=list(kws), text=text,
             set=set_, number=number, verified=verified)
    if flavor:
        d["flavor"] = flavor
    if notes:
        d["notes"] = notes
    CARDS.append(d)


L, U, P, G = "Legend", "Unit", "Program", "Gear"
R, GR, B, Y = "Red", "Green", "Blue", "Yellow"

# ----------------------------------------------------------------------------- A
C("6th Street Recruits", None, U, R, 1, 4, 6, False, ["6TH STREET", "GANGER"], [],
  "When a friendly Unit steals a d6, increase a Gig by up to 6.", 6, verified=False,
  notes="Stats and tags read from a gameplay screenshot; the rules text was tiny and is a best guess. Needs a card-face screenshot.")
C("Adam Smasher", "Ender of Legends", L, R, 2, 9, 9, True, ["ARASAKA", "MERC"], ["GO SOLO"],
  "GO SOLO\nPLAY: Defeat a rival Unit.", 1)
C("Adam Smasher", "Metal Over Meat", U, Y, 6, 9, 15, False, [], [], "", 41, verified=False,
  notes="Summary row only: cost 9, power 15, RAM 6. Text unread.")
C("Adrenaline Converter", None, G, Y, 4, 2, 3, True, ["CYBERWARE"], [], "", 60, verified=False,
  notes="Name partially visible ('Adrenaline Con...'); summary row: Gear, cost 2, power +3, RAM 4. Text unread.")
C("Afterparty at Lizzie's", None, P, Y, 1, 1, None, True, ["BRAINDANCE", "MOX"], [],
  "Adjust a Gig by up to 1. If you control 2 or more Gigs with different values, draw 1.", 65)
C("All is Lost", None, P, R, 2, 1, None, True, ["ZETATECH"], [],
  "Trash 3. Add a Unit from among them to your hand.", 27)
C("Alt Cunningham", "Mother of Daemons", U, Y, 3, 7, 8, False, ["MERC", "NETRUNNER"], [],
  "When a friendly equipped Unit or Legend is spent, draw 1.\n"
  "When a rival Unit would steal a Gig, you may discard 1 with cost equal to that Gig's value. "
  "If you do, the Gig isn't stolen.", 42)
C("Alt Cunningham", "Soulkiller Architect", L, B, 2, None, 0, True, ["MERC", "NETRUNNER"], [],
  "⊡: Your next Program this turn plays for -1 €$ for each friendly min Gig, to a minimum of 1 €$.\n"
  "1 €$, ⊡: Play a Program from your trash. Bottom-deck it after you play it. (You still pay its cost.)", 106)
C("Animals Wrecker", None, U, R, 3, 6, 10, False, ["ANIMAL", "GANGER"], [], "", 7,
  flavor="Takes a lot of juice to break bones like they do.")
C("Appetite for Destruction", None, P, R, 4, 3, None, True, ["GANGER"], [],
  "The next time a friendly Unit wins a fight by 3+ power this turn, it also steals a Gig.", 28)
C("Arasaka Emergency Radioport", None, G, R, 2, 2, 2, True, ["ARASAKA", "CYBERWARE"], [],
  "When this Unit or Legend is spent, you may look at a friendly face-down Legend. If that Legend "
  "is ARASAKA or has GO SOLO, you may Call it for free. (You may only Call a Legend once per turn.)", 23)
C("Augmented Negotiators", None, U, Y, 1, 3, 2, False, ["ARASAKA", "CORPO"], ["BLOCKER"],
  "BLOCKER.\nWhen this Unit uses BLOCKER, a Rival discards 1.", 43)
# ----------------------------------------------------------------------------- B
C("Bonnie and Clyde", None, P, R, 3, 3, None, True, ["BRAINDANCE"], [],
  "Defeat a rival Unit with power 4 or less. You may defeat 2 instead if a Rival controls at "
  "least 2 Gigs more than you.", 29)
C("Bootleg Black Sapphire Show", None, P, Y, 4, 5, None, True, ["BRAINDANCE"], [],
  "Sell the top card of your deck.\nIf you control a Gig with an even value and a Gig with an "
  "odd value, draw 2.", 66)
# ----------------------------------------------------------------------------- C
C("Caliber", "Totentanz's Top Dog", U, Y, 2, 5, 5, False, ["GANGER", "MAELSTROM"], [],
  "PLAY: Defeat a rival Unit with cost 2 or less.\nDEFEATED: A Rival discards 1. If the card's "
  "cost equals the value of a friendly Gig, that Rival discards 1 more.", 44)
C("Carnage at the Colosseum", None, P, R, 3, 6, None, True, ["BRAINDANCE", "EXTREME"], [],
  "Play this Program for -1 €$ for each friendly Gig with 8+ value, to a minimum of 1 €$.\n"
  "Defeat a rival Unit with less power than a friendly Unit.", 30)
C("Chrome Fang", None, U, R, 1, 5, 6, False, ["GANGER", "NETRUNNER", "TYGER CLAWS"], [],
  "PLAY: Until your next turn, rival Units can't steal friendly Gigs with value higher than "
  "their power.", 8)
C("Chrome Reverie", None, P, B, 1, 3, None, True, ["BRAINDANCE"], [],
  "A rival Unit can't attack until your next turn. If you control a min Gig, you may Call a "
  "Legend for free. (You can only Call a Legend once per turn.)", 131)
C("Corporate Surveillance", None, P, GR, 1, 2, None, True, ["CORPO"], [],
  "Spend a rival Unit with cost 4 or less.", 97)
C("Corpo Security", None, U, GR, 1, 2, 2, False, ["CORPO"], ["BLOCKER"],
  "This Unit can't attack.\nBLOCKER", 76)
C("Cyberpsychosis", None, P, Y, 2, 3, None, True, ["QUICKHACK"], ["QUICK"],
  "QUICK: Give an equipped Unit +3 power this turn for each of its equipped Gears. If that Unit "
  "steals or fights, defeat it at the end of this turn.", 67)
# ----------------------------------------------------------------------------- D
C("Deadman Transmitter", None, G, R, 3, 3, 1, True, ["CYBERWARE", "TRAUMA TEAM"], [],
  "If this Unit would be defeated, defeat its \"DEADMAN TRANSMITTER\" instead.", 24)
C("Delamain Cab", None, U, B, 2, 4, 4, False, ["VEHICLE"], [],
  "At the end of your turn, if this Unit stole a Gig this turn, ready 1 Eddie.", 112)
C("Delamain", "Rideshare AI", U, B, 3, 3, 0, False, ["AI"], [],
  "PLAY: Draw 2. (Units with power 0 don't steal Gigs.)", 111)
C("Detonate", None, P, R, 2, 1, None, True, ["QUICKHACK"], ["QUICK"],
  "QUICK: Defeat a rival Gear with power 2 or less.", 31)
C("Dexter DeShawn", "Off the Grid", L, R, 2, None, 0, True, ["FIXER"], [],
  "CALL: Choose one effect.\n- Give a friendly Unit +2 power this turn.\n- Draw 1.\n"
  "⊡: Increase a Gig by up to 2.", 2)
C("Dexter DeShawn", "One Last Chance", U, Y, 2, 3, 4, False, ["FIXER"], [],
  "PLAY / ATTACK: Adjust a Gig by up to 1.\nDEFEATED: If your ★ (Street Cred) differs from a "
  "Rival's by 10+, draw 2.", 9, set_=HEI)
C("(Don't Fear) The Reaper", None, P, GR, 3, 7, None, True, ["SAMURAI"], [],
  "Spend all rival Units. Then, defeat a spent Unit.", 98)
C("Dum Dum", "Maelstrom Triggerman", L, Y, 2, None, 0, True, ["GANGER", "MAELSTROM"], ["QUICK"],
  "CALL: You may defeat a friendly Gear. If you do, draw 2. Otherwise, draw 1.\n"
  "QUICK 1 €$, ⊡: Give a friendly Unit +1 power this turn for each of its equipped Gear.", 36)
C("Dying Night", "V's Pistol", G, B, 2, 2, 2, True, ["MERC", "WEAPON"], [],
  "ATTACK: Decrease a Gig by up to 2. At the end of your turn, if this Unit is named \"V\", "
  "ready 2 Eddies.", 128)
# ----------------------------------------------------------------------------- E
C("El Sombrerón", "La Venganza Lenta", U, R, 4, 5, "4+", False, ["GANGER", "VALENTINO"], [],
  "ATTACK: You may pay 2 €$. If you do, this Unit gains power equal to a friendly max Gig this turn.", 9)
C("Emergency Atlus", None, U, GR, 1, 3, 4, False, ["TRAUMA TEAM", "VEHICLE", "ZETATECH"], [], "", 77,
  flavor="Grab the policyholder, leave the rest for the city meatwagon.")
C("Evelyn Parker", "Beautiful Enigma", L, B, 2, None, 0, True, ["DOLL"], [],
  "When a friendly CORPO or GANGER Unit steals 1 or more Gigs, ready 1 Eddie.\n"
  "1 €$, ⊡: A rival Unit must attack next turn if it can.", 107)
C("Evelyn Parker", "Scheming Siren", U, B, 3, 2, 0, False, ["DOLL"], [],
  "ATTACK: Draw 1. Then, if you have more ★ (Street Cred) than a Rival, discard 1. "
  "(Units with power 0 don't steal Gigs.)", 113)
# ----------------------------------------------------------------------------- F
C("Field Operator", None, U, GR, 2, 3, 2, False, ["ARASAKA", "CORPO", "TECHIE"], [],
  "PLAY: If your ★ (Street Cred) is an even number, draw 1.", 78)
C("Floor It", None, P, B, 1, 1, None, True, ["MERC", "QUICKHACK"], ["QUICK"],
  "QUICK: Give a rival Unit -1 power this turn. Draw 1.", 132)
C("Fool on the Hill", None, P, GR, 3, 2, None, True, ["MERC"], [],
  "Reveal the top 2 cards of your deck. A Rival chooses whether you add them to your hand or "
  "trash them. If you trash them, draw 2.", 99)
# ----------------------------------------------------------------------------- G
C("Gilded Matón", None, U, Y, 2, 4, 3, False, ["GANGER", "VALENTINO"], [],
  "PLAY: You may defeat a friendly Gear. If you do, defeat a rival Unit with cost 3 or less.", 45)
C("Gorilla Arms", None, G, Y, 3, 4, 3, True, ["CYBERWARE"], [],
  "The first time this Unit steals 1 or more Gigs each turn, steal a rival Gig with a value not "
  "shared by a friendly Gig.", 60)
C("Goro Takemura", "Hands Unclean", L, GR, 2, 5, 7, True, ["ARASAKA", "CORPO"], ["GO SOLO", "BLOCKER"],
  "GO SOLO\nBLOCKER", 12, set_=EBP)
C("Goro Takemura", "Losing His Way", U, GR, 3, 4, "4+", False, ["ARASAKA", "CORPO"], [],
  "ATTACK: If all friendly Legends are face-up, this Unit has +5 power this turn.", 17, set_=EBP)
C("Goro Takemura", "Vengeful Bodyguard", L, GR, 2, None, 0, True, ["ARASAKA", "CORPO"], ["QUICK"],
  "QUICK 1 €$, ⊡: Give a friendly Unit with cost 4 or less BLOCKER this turn. If you control a "
  "value-pair of Gigs, also give it +1 power this turn.\n"
  "When a friendly Unit uses BLOCKER, you may discard 1. If you do, draw 1.", 71)
C("Gunpoint Diplomacy", None, P, R, 3, 4, None, True, ["GANGER", "PLAN"], [],
  "Give a friendly Unit these effects. If you have less ★ (Street Cred) than a Rival, they "
  "instead choose one effect for you.\n- The next time this Unit attacks this turn, it may attack "
  "ready Units.\n- Give this Unit +3 power this turn.", 32)
# ----------------------------------------------------------------------------- H
C("Hacked Corpo", None, U, B, 1, 4, 3, False, ["AI", "CORPO"], [],
  "PLAY: Trash 3. Add a Program from among them to your hand.", 114)
C("Hanako Arasaka", "Daughter of the Emperor", L, GR, 2, None, 0, True, ["ARASAKA", "CORPO", "NETRUNNER"], [],
  "⊡: Swap a friendly Gig with a rival Gig.\nAt the start of your turn, draw 1 for each friendly "
  "value-pair of Gigs.", 72)
C("Hanako Arasaka", "In a Gilded Cage", U, Y, 2, 4, 1, False, ["ARASAKA", "CORPO", "NETRUNNER"], [],
  "PLAY: Search the top 4 cards of your deck. Reveal any number of cards with cost equal to any "
  "friendly Gig values and add them to your hand. Bottom-deck the rest.", 46)
C("Heywood Ripperdoc", None, U, Y, 1, 6, 8, False, ["RIPPERDOC"], [],
  "PLAY: You may defeat a Gear. If its cost equals the value of a friendly Gig, draw 1.", 47)
# ----------------------------------------------------------------------------- I
C("Industrial Assembly", None, P, R, 1, 1, None, True, ["ARASAKA", "BRAINDANCE"], [],
  "Increase a Gig by up to 4. If you control a Gig with 8+ value, draw 1.", 33)
# ----------------------------------------------------------------------------- J
C("Jacked-In Voodoo Boy", None, U, B, 2, 2, 2, False, ["NETRUNNER", "VOODOO BOYS"], [],
  "This Unit can't attack unless you played a Program this turn.", 115)
C("Jackie Welles", "Mama's Favorite", L, GR, 2, 6, 8, True, ["MERC"], ["GO SOLO"],
  "GO SOLO\nIf a friendly Unit would be defeated, you may pay 1 €$ to defeat this Legend instead. "
  "(Remove it from the game.)", 73)
C("Jackie Welles", "Pour One Out For Me", L, B, 2, None, 0, True, ["MERC"], [],
  "The first time you play a Blue Unit or Blue Gear each turn, you may decrease a friendly Gig by "
  "up to 2. If it becomes a min Gig, draw 1.", 11, set_=HEI)
C("Jackie Welles", "Ride or Die Choom", U, Y, 2, 6, "8+", False, ["MERC", "VALENTINO"], [],
  "ATTACK: Give this Unit +2 power this turn for each friendly Gig with an even value.\n"
  "DEFEATED: Draw 1 for each friendly Gig with an odd value.", 48)
C("Japantown Jonin", None, U, R, 2, 2, 0, False, ["TYGER CLAWS"], [],
  "PLAY: Give a friendly Unit +2 power this turn. (Units with power 0 don't steal Gigs.)", 10)
C("Johnny Silverhand", "Never Stop Fighting", U, R, 2, 6, 8, False, ["MERC", "ROCKER", "SAMURAI"], [],
  "The first time this Unit wins a fight each turn, ready it.\nThis Unit wins all fights against "
  "CORPO Units.", 11)
C("Johnny Silverhand", "Rocking Renegade", L, R, 2, None, 0, True, ["MERC", "ROCKER", "SAMURAI"], [],
  "2 €$, ⊡: A friendly Unit can attack spent rival Units the turn it's played. If it's a ROCKER "
  "Unit, also give it +2 power this turn. This effect costs -1 €$ for each friendly Gig with 8+ value.", 3)
C("Judy Álvarez", "Braindance Maestro", L, B, 2, None, 0, True, ["GANGER", "MOX", "TECHIE"], [],
  "When you play a BRAINDANCE Program, give a friendly Unit +1 power this turn.\n"
  "⊡: Trash the top card of your deck. If it's a Program, you may add it to your hand.", 108)
C("Judy Álvarez", "Nothing to Doubt", U, B, 5, 6, 6, False, ["GANGER", "MOX", "TECHIE"], [],
  "1 €$, ⊡: Reveal the top card of your deck. You may play it for free. Otherwise, add it to your hand.", 116)
# ----------------------------------------------------------------------------- K
C("Kerry Eurodyne", "Axe, Attitude, Audience", L, Y, 2, None, 0, True, ["ROCKER", "SAMURAI"], [],
  "When you roll in a Gig from your fixer area, you may ignore the result and reroll it once.\n"
  "When you roll a min or max value on a Gig, draw 1. If it's a d20, draw 3 instead.", 37)
C("Kerry Eurodyne", "The Last Rockerboy", U, R, 1, 4, 5, False, ["ROCKER", "SAMURAI"], [],
  "⊡: If you control a Gig with 8+ value, draw 2.", 12)
C("Kiroshi Optics", None, G, Y, 1, 1, 1, True, ["CYBERWARE"], [],
  "(Equip to a Unit or friendly face-up Legend.)\nATTACK: Look at a friendly face-down Legend. "
  "(Don't reveal it.)", 61)
# ----------------------------------------------------------------------------- L
C("La Llorona", "Ghost of the Past", U, R, 1, 3, 3, False, ["GANGER", "VALENTINO"], ["BLOCKER"],
  "BLOCKER\nWhen this Unit uses BLOCKER, increase a Gig by up to 3.", 13)
C("Les Élémens", None, P, B, 4, 5, None, True, ["CORPO"], [],
  "Bottom-deck a Rival's lowest-power Unit. (If there are multiple, choose 1.)", 133)
C("Live with the Aftermath", None, P, Y, 3, 3, None, True, ["PLAN"], [],
  "Each player defeats one of their Units.", 68)
C("Lizzy Wizzy", "Delicate Weapon", U, B, 2, 5, 2, False, ["ROCKER"], ["BLOCKER"],
  "PLAY: You may play a Program with cost 3 or less from your hand or trash for free. Bottom-deck "
  "it after you play it.\nBLOCKER", 117)
# ----------------------------------------------------------------------------- M
C("Maelstrom Goons", None, U, Y, 2, 3, 3, False, ["GANGER", "MAELSTROM"], [],
  "When this Unit steals a Gig, if it's equipped, a Rival discards 1.", 49)
C("Maelstrom Zealots", None, U, GR, 1, 4, 0, False, ["GANGER", "MAELSTROM"], [],
  "When this Unit loses a fight, defeat the opposing rival Unit. (Units with power 0 don't steal Gigs.)", 79)
C("Maman Brigitte", "Spirit of Death", U, B, 4, 5, 3, False, ["MYSTIC", "NETRUNNER", "VOODOO BOYS"], [],
  "PLAY: You may discard 2 Programs. If you do, bottom-deck a rival unequipped Unit.", 118)
C("Mandibular Upgrade", None, G, Y, 2, 1, 0, True, ["CYBERWARE"], ["BLOCKER"],
  "(Equip to a friendly Unit or face-up Legend.)\nBLOCKER", 62)
C("Mantis Blades", None, G, R, 1, 1, 2, True, ["CYBERWARE"], [], "", 25, flavor="One cut, one kill.")
C("MaxTac AV", None, U, GR, 2, 5, 8, False, ["NCPD", "VEHICLE"], [],
  "PLAY: You may swap a friendly Gig with a rival Gig.", 80)
C("MaxTac Heavy", None, U, GR, 3, 7, 8, False, ["NCPD"], [],
  "Play this Unit for -1 €$ for each of a Rival's Units, to a minimum of 1 €$.", 81)
C("MaxTac Squadron", None, U, GR, 3, 3, 4, False, ["NCPD"], [],
  "At the end of your turn, if this Unit is spent, ready a friendly face-up Legend.", 82)
C("MaxTac Suppression Team", None, U, Y, 1, 5, 7, False, ["NCPD"], [],
  "Rival Units can't attack the turn they're played.", 50)
C("Memory Relapse", None, P, GR, 2, 4, None, True, ["BRAINDANCE"], [],
  "Spend a rival Unit. It can't ready until your next turn. If your ★ (Street Cred) is an even "
  "number, draw 1.", 100)
C("Meredith Stout", "Stone Cold Corpo", U, R, 1, 4, "5+", False, ["CORPO", "MILITECH"], ["BLOCKER"],
  "BLOCKER\nThis Unit has +2 power while fighting a Legend.\nWhen a Rival adjusts or swaps 1 or "
  "more friendly Gigs, you may add a card from your trash to your hand.", 14)
C("Minotaur", None, U, R, 2, 7, 9, False, ["ARASAKA", "DRONE", "MILITECH"], [],
  "PLAY: If you have more ★ (Street Cred) than a Rival, defeat a rival Unit with power 5 or less.", 3, set_=EBP)
C("Misty Olszewski", "Mender of Broken Spirits", U, B, 2, 3, 0, False, ["MYSTIC"], [],
  "This Unit can't attack.\nAt the end of your turn, choose a card type. Then, reveal the top card "
  "of your deck. If it's the chosen type, add it to your hand and ready 1 Eddie. Otherwise, trash "
  "it. (Unit, Gear, and Program are card types.)", 119)
C("Modded Kusanagi", None, U, B, 2, 6, 8, False, ["TYGER CLAWS", "VEHICLE"], ["ADRENALINE"],
  "ADRENALINE\nAt the end of your turn, return this Unit to its owner's hand.", 120)
C("Modded Muramasa", None, U, B, 2, 5, 4, False, ["VEHICLE"], [],
  "At the end of your turn, if you have less ★ (Street Cred) than a Rival, ready this Unit.", 121)
C("Mox Inciters", None, U, B, 2, 3, 2, False, ["GANGER", "MOX"], ["BLOCKER"],
  "PLAY: A rival Unit must attack next turn if it can.\nBLOCKER", 122)
C("MTOD12 Flathead", None, U, B, 3, 5, 7, True, ["DRONE", "MILITECH"], [],
  "If you have less ★ (Street Cred) than a Rival, this Unit can't be blocked.", 15, set_=HEI)
C("Muamar Reyes", "El Capitán", L, Y, 2, None, 0, True, ["FIXER"], [],
  "CALL: Choose one effect.\n- A friendly Unit can't be defeated in a fight this turn.\n- Draw 1.\n"
  "⊡: Adjust a Gig by 1.", 38)
# ----------------------------------------------------------------------------- N
C("Nadia", "Fighting Through Grief", U, GR, 2, 6, 8, False, ["MEDTECH", "TRAUMA TEAM"], [],
  "If a Rival controls more Gigs than you, this Unit can attack their Gig area the turn it's played.", 83)
C("NetWatch Netdriver", None, G, B, 2, 3, 2, True, ["CYBERWARE", "NETRUNNER", "NETWATCH"], [],
  "When this Unit or Legend is spent, draw 1.", 129)
C("Nocturne OP55N1", None, P, B, 2, 3, None, True, ["ARASAKA", "PLAN"], [],
  "If your fixer area is empty, play this Program for 1 €$.\nChoose one effect.\n- Draw 2.\n"
  "- A Unit can't attack until your next turn.\n- A friendly Legend may use GO SOLO for -2 €$ "
  "this turn, to a minimum of 1 €$.", 134)
# ----------------------------------------------------------------------------- O
C("Octant", None, U, R, 4, 7, 8, False, ["DRONE", "MILITECH", "ZETATECH"], [],
  "Play this Unit for -1 €$ for each friendly Gig with 8+ value, to a minimum of 1 €$.", 15)
C("Offduty Malfini", None, U, Y, 2, 4, 5, False, ["GANGER", "VOODOO BOYS"], [],
  "PLAY: Spend this Unit and a rival Unit.", 51)
C("Over the Edge", None, P, R, 2, 3, None, True, ["MERC"], [],
  "Defeat a Unit with power equal to or less than the value of a friendly d20.", 34)
C("Overwatch", "Panam's Gift", G, GR, 4, 4, 4, True, ["WEAPON"], ["QUICK"],
  "(Equip to a friendly Unit or face-up Legend.)\nQUICK 1 €$, ⊡: Discard 1. Defeat a spent rival "
  "Unit with cost equal to or less than the discarded card's cost.", 93)
# ----------------------------------------------------------------------------- P
C("Pacifica Netrunner", None, U, GR, 2, 4, 1, False, ["NETRUNNER"], [],
  "PLAY: If your ★ (Street Cred) is an even number, a rival Unit can't ready until your next turn.", 84)
C("Padre", "Man of the Cross", L, GR, 2, None, 0, True, ["FIXER", "GANGER", "VALENTINO"], [],
  "CALL: Choose one effect.\n- Spend a rival Unit.\n- Draw 1.\n"
  "⊡: Set a player's Gig to the same value as another player's Gig.", 74)
C("Panam Palmer", "Nomad Cavalry", L, GR, 2, None, 0, True, ["ALDECALDO", "MERC", "NOMAD"], [],
  "2 €$, ⊡: Move a Gear from this Legend to an unequipped friendly Unit. If you do, ready that Unit.\n"
  "At the end of your turn, if 5 or more friendly Units and/or Legends are equipped, ready them.", 75)
C("Panam Palmer", "Strength Through Family", U, GR, 4, 6, 6, False, ["ALDECALDO", "MERC", "NOMAD"], [],
  "During your turn, you may Call a Legend for free.\nATTACK: Discard 1. If you do, draw 1 for "
  "each friendly face-up Legend.", 85)
C("Peace Offering", None, P, GR, 1, 1, None, True, ["BRAINDANCE"], [],
  "You may set a Gig's value to the value of another Gig. Then, if you control a value-pair, draw 1.", 101)
C("Pepe Najarro", "Working Doubles", U, GR, 2, 4, 6, False, ["VALENTINO"], [],
  "ATTACK: If you control a value-pair of Gigs, ready up to 2 MERC Legends in your Legends area.", 86)
C("Placide", "Voodoo Sentinel", U, B, 2, 8, 10, False, ["GANGER", "NETRUNNER", "VOODOO BOYS"], [],
  "PLAY / ATTACK: You may discard 1 Program. If you do, bottom-deck a rival Unit.", 127)
C("Psycho Squad", None, U, B, 1, 4, 6, False, ["NCPD"], [], "", 124,
  flavor='Their protocol stops at "shoot first."')
C("Pyramid Song", None, P, B, 3, 3, None, True, ["BRAINDANCE"], [],
  "Choose one effect. If a friendly d4 is a min Gig, choose both instead.\n- Give a rival Unit -4 "
  "power this turn.\n- Bottom-deck a rival Unit with power 0.", 135)
# ----------------------------------------------------------------------------- R
C("Rebecca", "Having a Moment", L, R, 2, None, 0, True, [], [], "", 5, set_="PR001", verified=False,
  notes="Promo-style full-art card; no stats or text were visible in the screenshot. Everything here is a placeholder.")
C("Reboot Optics", None, P, B, 2, 2, None, True, ["QUICKHACK"], ["QUICK"],
  "QUICK: The next time a rival Unit fights this turn, it doesn't defeat the opposing friendly Unit.", 136)
C("Riding Nomad", None, U, GR, 4, 5, 4, False, ["NOMAD"], ["ADRENALINE"],
  "ADRENALINE (This Unit can attack the turn it's played.)", 87)
C("Riot Shield", None, G, GR, 2, 2, 1, True, ["WEAPON"], ["BLOCKER"],
  "(Equip to a friendly Unit or face-up Legend.)\nBLOCKER\nRivals must pay +2 €$ to use GO SOLO.", 94)
C("Rita Wheeler", "No Stupid Questions", U, B, 2, 4, 4, False, ["GANGER", "MOX"], ["BLOCKER"],
  "BLOCKER\nThe first time this Unit is spent each turn, draw 1, then discard 1.", 125)
C("River Ward", "Detective on the Hunt", L, Y, 2, None, 0, True, ["NCPD"], ["QUICK"],
  "QUICK ⊡: Play a Gear with cost 2 or less from your hand for free.\nWhen a friendly equipped "
  "Unit is defeated, search the top 2 cards of your deck and trash 1.", 39)
C("Rockn' Rockerboy", None, U, Y, 1, 5, 8, False, ["ROCKER"], [], "", 59,
  flavor="Scream your throat raw for something. Anything.")
C("Rogue Amendiares", "Preem Solo", L, Y, 2, 7, 7, True, ["MERC"], ["GO SOLO"],
  "GO SOLO\nWhen a friendly Legend steals a Gig, if its value is even, draw 1. If its value is "
  "odd, a Rival discards 1.", 40)
C("Rogue Amendiares", "Queen of the Afterlife", U, B, 2, 5, 4, False, ["FIXER", "MERC"], ["QUICK"],
  "The first time another friendly Unit steals a Gig with value less than its power each turn, "
  "ready 2 Eddies.\nQUICK 2 €$, ⊡: A rival Unit loses power equal to this Unit's power this turn.", 126)
C("Royce", "Don't Call Me Simon", U, R, 2, 5, 4, False, ["GANGER", "MAELSTROM"], [],
  "PLAY: Defeat a rival Unit with power 2 or less. If you have more ★ (Street Cred) than a Rival, "
  "defeat a rival Unit with power 3 or less instead.", 16)
C("Royce", "Psycho on the Edge", L, R, 2, 6, "6+", True, ["GANGER", "MAELSTROM"], ["GO SOLO"],
  "GO SOLO\nDuring your turn, this Legend has +2 power for each of its equipped Gear.", 4)
C("Ruthless Lowlife", None, U, R, 1, 2, 4, False, ["GANGER", "MAELSTROM"], [],
  "This Unit can only attack rival Units. (It can't attack Gig areas.)", 17)
# ----------------------------------------------------------------------------- S
C("Saburo Arasaka", "Stubborn Patriarch", L, GR, 2, None, 0, True, ["ARASAKA", "CORPO"], [],
  "Friendly ARASAKA Units have +1 power while attacking. (Units steal an extra Gig for every 10 power.)", 13, set_=EBP)
C("Safety Override", None, P, Y, 3, 2, None, True, ["QUICKHACK"], ["QUICK"],
  "QUICK: The next time a friendly Unit loses a fight this turn, defeat the opposing rival Unit.", 69)
C("Sandayu Oda", "Hanako's Guardian", U, GR, 2, 7, 8, False, ["ARASAKA", "CORPO"], [],
  "PLAY: Spend a rival Unit for each friendly value-pair of Gigs.\nThis Unit can attack rival "
  "Units the turn it's played.", 80, notes="Collector number uncertain.")
C("Sandevistan", None, G, GR, 3, 3, 2, True, ["CYBERWARE"], [],
  "(Equip to a friendly Unit or face-up Legend.)\nAt the end of your turn, ready this Unit or Legend.", 95)
C("Sasha Yakovleva", "Won't Let You Down", L, B, 2, 5, "0+", True, ["MAINE'S CREW", "MERC", "NETRUNNER"], ["GO SOLO"],
  "GO SOLO\nATTACK: Reveal the top card of your deck and add it to your hand. This Unit gains "
  "power equal to that card's cost this turn.\nDEFEATED: A Rival discards 1.", 109)
C("Satori", "Sword of Saburo", G, R, 1, 2, 2, True, ["ARASAKA", "WEAPON"], [],
  "(Equip to a friendly Unit or face-up Legend.)\nWhen this Unit wins a fight against a rival Unit, draw 1.", 26)
C("Saul Bright", "Stormrider", U, GR, 2, 8, 14, False, ["ALDECALDO", "NOMAD"], [],
  "Other friendly Units have +2 power while attacking.\nAt the end of your turn, ready up to 3 "
  "friendly Units.", 89)
C("Screw", "Lovelorn Fool", U, R, 2, 5, 7, False, ["GANGER", "MAELSTROM"], [],
  "DEFEATED: Add another Unit from your trash to your hand.", 18)
C("Secondhand Bombus", None, U, Y, 2, 2, 0, False, ["DRONE", "ZETATECH"], ["BLOCKER"],
  "BLOCKER (You may spend this Unit to redirect a rival Unit's attack to it instead.)\n"
  "(Units with power 0 don't steal Gigs.)", 53)
C("Shattered Memories", None, P, R, 2, 4, None, True, ["BRAINDANCE"], [],
  "Each player discards their hand and may draw 5.\nIf the total number of discarded cards equals "
  "the value of a friendly Gig, draw 2.", 35)
C("Sketchy Ripper", None, U, Y, 2, 2, 0, False, ["GANGER", "RIPPERDOC", "SCAVENGER"], [],
  "ATTACK: Search the top 3 cards of your deck. Reveal a Gear and add it to your hand. Bottom-deck "
  "the rest. (Units with power 0 don't steal Gigs.)", 54)
C("Swordwise Huscle", None, U, R, 2, 3, 3, False, ["MERC"], [],
  "ATTACK: If this Unit has power 5+, draw 1.", 19)
C("Synapse Burnout", None, P, GR, 1, 1, None, True, ["QUICKHACK"], ["QUICK"],
  "QUICK: A friendly Unit has +1 power for each friendly face-up Legend while fighting rival "
  "Units this turn.", 102)
# ----------------------------------------------------------------------------- T
C("Take Control", None, P, GR, 2, 2, None, True, ["QUICKHACK"], ["QUICK"],
  "QUICK: A rival Unit steals 1 fewer Gig this turn. If that Unit is an AI, DRONE, or VEHICLE, draw 1.", 103)
C("T-Bug", "Amateur Philosopher", U, Y, 2, 4, 4, False, ["MERC", "NETRUNNER"], [],
  "DEFEATED: Look at all friendly face-down Legends. Then, you may Call a Legend for free. "
  "(You can only Call a Legend once per turn.)", 55)
C("Tetratronic Rippler", None, G, B, 2, 1, 1, True, ["CYBERWARE"], [],
  "(Equip to a friendly Unit or face-up Legend.)\nWhen this Unit or Legend is spent, search the "
  "top card of your deck. You may trash it. (Otherwise, keep it on the top of your deck.)", 130)
C("The Heist", None, P, Y, 2, 2, None, True, ["MERC"], [],
  "Trash 4. Add a Gear from among them to your hand. If that Gear's cost equals the value of a "
  "friendly Gig, you may play it for free instead.", 70)
C("The Relic", "Experimental Biochip", G, Y, 4, 5, 3, True, ["ARASAKA", "CYBERWARE"], [],
  "(Equip to a friendly Unit or face-up Legend.)\nDEFEATED: Play another Unit with cost 9 or less "
  "from your trash for free. Then, bottom-deck this Unit.", 63)
C("Three Mouths, One Desire", None, P, B, 3, 2, None, True, ["BRAINDANCE", "DOLL"], [],
  "Search the top 3 cards of your deck. Add 1 to your hand. You may add 1 more for each friendly "
  "min Gig. Bottom-deck the rest.", 137)
C("Towerfall", None, P, B, 4, 6, None, True, ["BRAINDANCE"], [],
  "Choose one effect. If you have less ★ (Street Cred) than a Rival, choose both instead.\n"
  "- Give all rival Units -5 power this turn.\n- Bottom-deck all rival Units with power 0.", 138)
C("Trauma Team Operatives", None, U, Y, 2, 6, 7, False, ["MEDTECH", "TRAUMA TEAM"], [],
  "Play this Unit for -1 €$ for each Unit in your trash, to a minimum of 1 €$.", 56)
C("Trust No One", None, P, B, 1, 1, None, True, ["BRAINDANCE"], [],
  "Decrease a Gig by up to 3. Then, if you control a min Gig, draw 1.", 139)
C("Tyger's Whisper", None, U, GR, 1, 2, 0, False, ["FIXER", "TYGER CLAWS"], [],
  "PLAY: You may Call a Legend for free. (You can only Call a Legend once per turn.)\n"
  "(Units with power 0 don't steal Gigs.)", 88)
# ----------------------------------------------------------------------------- U
C("Unlikely Bond", None, P, B, 2, 4, None, True, ["MAELSTROM", "MOX"], [],
  "Bottom-deck a ready friendly Unit. If you do, bottom-deck a spent rival Unit.", 140)
# ----------------------------------------------------------------------------- V
C("V", "Corporate Exile", L, B, 2, 5, 8, True, ["CORPO", "MERC"], ["GO SOLO"],
  "GO SOLO (Pay this Legend's cost to play it as a ready Unit. It can attack this turn. When it "
  "leaves the field, remove it from the game.)", 12, set_=HEI)
C("V", "Roamer of the Badlands", U, R, 2, 5, 6, False, ["MERC", "NOMAD"], [],
  "When this Unit steals a Gig, increase it by up to 5.\nAt the end of your turn, if you control "
  "2 or more Gigs with 8+ value, draw 1.", 20)
C("V", "Streetkid", L, R, 2, 5, 6, True, ["MERC"], ["GO SOLO"],
  "CALL: Trash 3. Then, add 1 BRAINDANCE Program from your trash to your hand.\nGO SOLO", 5)
C("Valentino Guerrera", None, U, R, 2, 3, 4, False, ["GANGER", "VALENTINO"], [],
  "If you have more ★ (Street Cred) than a Rival, this Unit can attack ready Units with BLOCKER.", 21)
C("Valentino Street Racer", None, U, GR, 2, 3, 3, False, ["VALENTINO", "VEHICLE"], [],
  "PLAY: Give another friendly Unit with cost 5 or less ADRENALINE this turn. (A Unit with "
  "Adrenaline can attack the turn it's played.)", 91)
C("Viktor Vektor", "Drop Your Illusions", U, Y, 2, 5, 5, False, ["RIPPERDOC"], [],
  "Play your first CYBERWARE Gear each turn for -3 €$, to a minimum of 1 €$.", 57)
C("Viktor Vektor", "Sit Down and Relax", L, Y, 2, None, 0, True, ["RIPPERDOC"], [],
  "CALL: Search the top 5 cards of your deck. Reveal up to 2 Gears with cost 2 or less and add "
  "them to your hand. Bottom-deck the rest in a random order.", 1, set_=HEI,
  notes="Set/number uncertain.")
C("Viktor Vektor", "You Might Feel a Little Pinch", U, Y, 2, 3, 3, False, ["RIPPERDOC"], [],
  "PLAY: Play a CYBERWARE Gear with cost 2 or less from your trash for free. Equip it only to "
  "another friendly Unit.", 58)
# ----------------------------------------------------------------------------- W
C("Wakako Okada", "Peace and Harmony", L, B, 2, None, 0, True, ["FIXER", "TYGER CLAWS"], [],
  "CALL: Choose one effect.\n- Give a rival Unit -2 power this turn.\n- Draw 1.\n"
  "⊡: Decrease a Gig by up to 2.", 110)
C("We Gotta Live Together", None, P, GR, 2, 5, None, True, ["ALDECALDO", "NOMAD"], [],
  "If a Rival controls at least 2 more Gigs than you, play this Program for 3 €$.\n"
  "Play up to 2 Units with cost 3 or less from your trash for free.", 104)
C("Westbrook Netrunner", None, U, B, 2, 4, 5, False, ["NETRUNNER"], [],
  "PLAY: Until your next turn, rival Legends can't steal friendly Gigs with value less than their power.", 123)
C("Wild in the Streets", None, P, GR, 4, 5, None, True, ["GANGER"], [],
  "Defeat a spent Unit.", 105)
C("Wraith Marauders", None, U, GR, 2, 5, 4, False, ["GANGER", "NOMAD", "RAFFEN SHIV"], [],
  "When this Unit steals a Gig, ready another friendly Unit with power equal to the Gig's value.", 92)
# ----------------------------------------------------------------------------- Y
C("Yorinobu Arasaka", "Embracing Destruction", L, R, 2, None, 0, True, ["ARASAKA", "CORPO"], [],
  "The first time a friendly ARASAKA Unit attacks each turn, draw 1. Then, if you have less than "
  "20 ★ (Street Cred), discard 1.", 1, set_=EBP)
C("Yorinobu Arasaka", "Steel Dragon", U, R, 3, 7, 9, False, ["ARASAKA", "CORPO"], [],
  "PLAY: You may play a Unit with cost 4 or less from your hand or trash for free. It can attack "
  "rival Units this turn.\nThe first time an ARASAKA Unit is defeated each turn, draw 1.", 22)
# ----------------------------------------------------------------------------- Z
C("Zetatech Berserk", None, G, GR, 2, 6, 3, True, ["CYBERWARE", "ZETATECH"], [],
  "Play this Gear for -1 €$ for each friendly face-up Legend, to a minimum of 1 €$.", 96)
C("Zetatech Faceplate", None, G, Y, 2, 2, 2, True, ["CYBERWARE", "ZETATECH"], [],
  "(Equip to a friendly Unit or face-up Legend.)\nWhen this Unit or Legend is spent, adjust a Gig "
  "by up to 1. Then, if you control 3 or more Gigs with different values, draw 1.", 64)

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "data" / "cards" / "wnc.json"
    out.write_text(json.dumps({"set": "Welcome to Night City (+ starter sets)", "cards": CARDS},
                              indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    n_ok = sum(c["verified"] for c in CARDS)
    print(f"{len(CARDS)} cards written to {out.relative_to(out.parents[2])}; {n_ok} verified, "
          f"{len(CARDS) - n_ok} placeholders")
