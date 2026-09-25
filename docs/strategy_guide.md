# The Cyberpunk TCG: a strategy guide

*For a player who knows the rules and has played a few games. Written from every card in the set,
the comprehensive rules and FAQ as our engine implements them, 132 solved positions, and about
forty thousand recorded games between machine players of varying strength. The machine appears only
as evidence. Where a claim rests on the rules it says so; where it rests on our games it says "in
our games"; where it is a belief it says "we suspect".*

*Last updated: 2026-09-21 (Stage 0 measurements; KT1 rerun pending). Changelog at the end.*

---

## How to read this book

Every chapter gives a principle, says why it follows from the rules, works a concrete example with
named cards, names the mistake a new player makes, and, where we have one, gives the number from
our games. Chapters 1 to 9 each end with a short paragraph on what the principle means for the deck
you build, because in this game play and construction are one problem: the three Legends you pick
decide which cards you are allowed to run, and the cards you run decide which plays exist.

Card text is quoted from the cards themselves. Where the text is abbreviated in prose, the card's
full wording is what counts, and the guide never states an effect from memory.

---

## 1. The clock and the race

**The principle.** There are two clocks, and the one that matters changes at the Overtime boundary.
Before it, seven Gigs must survive a whole rival turn to count. After it, seven Gigs win the moment
they exist.

**Why, from the rules.** The win condition is *seven Gig dice in your Gig area at the start of your
turn*, checked before you take a die from the fixer. Each player owns six dice, so the seventh has
to be stolen. Overtime "begins at the end of a turn once both players have begun a turn with an
empty fixer area", which under normal alternation is after each player has taken seven turns, and
"during Overtime a player with 7 or more Gig dice in their Gig area wins immediately, at any
point". So before Overtime, if you steal to seven on your turn, the rival gets a full turn to steal
one back before your check; if they do, you are at six and nothing happened. In Overtime the same
steal ends the game on the spot, on either player's turn, in the middle of an effect.

The second clock is the deck: "if you are required to draw a card but have no cards left in your
deck, your Rival immediately wins." A 40-card deck loses six to the opening hand and one a turn, so
by the Overtime boundary you have drawn about thirteen. That leaves plenty, unless your deck trashes
itself: All is Lost ("Trash 3"), The Heist ("Trash 4"), Hacked Corpo ("Trash 3"), V — Streetkid's
CALL ("Trash 3"), Judy Álvarez — Braindance Maestro's spend ("Trash the top card"), Fool on the
Hill, Shattered Memories ("Each player discards their hand and may draw 5") and Rita Wheeler's
draw-then-discard all shorten it. In our games deck-out is rare (6 of 20,000 simple-player games)
but that is because our machines do not build the decks that court it; a deck with nine trash
effects and Shattered Memories can lose to its own engine.

**The example.** You are on six Gigs with a ready 8-power Unit and the rival's Gig area in front of
you. The obvious move steals the seventh. But the rival's Rockn' Rockerboy is lying spent in their
field; it readies at the start of their turn and takes one back, and your check finds six. One of
our solved positions (`gig-shaping-odd-cred-lets-the-guard-wake`) has exactly this board. The
winning line is to make the seventh Gig *survive*: Pacifica Netrunner reads "PLAY: If your ★
(Street Cred) is an even number, a rival Unit can't ready until your next turn", your Street Cred is
21, and every rival die shows an even face, so stealing any of them leaves you odd. So the line
first spends an Eddie and a card on Trust No One aimed at *your own* d6, 3 down to 2 ("Decrease a
Gig by up to 3"), which flips your parity, then plays Pacifica naming the Rockerboy, then steals.
The Rockerboy never wakes and seven is still seven when your turn begins. Every move before the
last one lowers your Street Cred, costs a card, or costs an Eddie; none of it shows on the board.

**The mistake.** Taking the seventh Gig because it is there. Before Overtime the question at six is
never "can I steal one" but "can I make it survive their turn". The tools are the ones that stop
their attackers from readying or attacking: Pacifica Netrunner and Memory Relapse ("can't ready
until your next turn"), Chrome Reverie and Nocturne OP55N1 ("can't attack until your next turn"),
MaxTac Suppression Team ("Rival Units can't attack the turn they're played"), a ready Blocker held
back (chapter 5), Westbrook Netrunner and Chrome Fang, which make your dice unstealable by value
(chapter 7), and simply killing or spending the attacker. The other half of the mistake is the
mirror: at Overtime, being at six with the rival at six is a coin flip decided by whoever steals
first, on either turn, so a Unit that can attack on your turn and a QUICK that can steal on theirs
are both worth a game.

**The numbers.** In our search-agent self-play, 71% of games ended by a seven-Gig check at the start
of a turn and 29% in Overtime; under the simpler player it was 52% and 48%, which says the weaker
player lets the race drag to the boundary far more often. The average game ran 13 to 14 turns
under both, which is to say the typical game ends *at* the Overtime boundary, and the continuous
check is live for most of the endgame you will actually play.

**What this means for your deck.** Count the cards that make a seventh Gig survive, not only the
cards that take it. A deck with no "can't attack" or "can't ready" effect, no Blocker and no
anti-steal text is a deck that has to win in Overtime, and that is a plan, but it should be a plan
you chose. Count your self-trashing too: every "Trash N" is a turn off the second clock.

---

## 2. Economy

**The principle.** Your three Legends are your economy from turn one, every Eddie you spend on your
turn is gone for their turn, and the once-a-turn Sell is the only engine that makes new Eddies.

**Why, from the rules.** The Eddies area starts empty and you create Eddies only by selling a
sell-tagged card from hand, once per turn, for exactly 1 €$ "however much it cost in hand". Every
Legend can be spent to pay 1 €$ "whether face-up or face-down" (all 27 carry a Sell Tag), so a fresh
deck has three Eddies of buying power before it has sold anything. Spent cards ready in *your* Start
Phase, which means what you spend on your turn stays spent through the rival's turn, and what they
can see standing ready at the end of your turn is exactly what you can react with.

The first player pays for the roll: "the player going first spends their 2 leftmost Legends and
doesn't ready them on their first turn", so turn one is one Legend and a Sell for the first player
against three Legends and a Sell for the second. In our simple-player round robin the first player
won 38.5% of 7,600 games; under the search player it was 53.3% of 3,800. We cannot yet tell you
which is closer to the truth for strong humans, and both of our players are hard-wired to go second
when they win the roll, so we have never measured a *chosen* first turn at all. The rules-guaranteed
part is the cost: two Eddies of tempo on the first turn.

Only Programs, Gear and one Unit (MTOD12 Flathead) carry Sell Tags. Seventy-two of seventy-three
Units cannot be sold. A hand of Units generates nothing; it can only spend the Legends.

**The example: what a spent Legend really costs.** A face-up Legend spent for 1 €$ is a card that
cannot use its spend-icon ability this turn (Hanako Arasaka — Daughter of the Emperor's "⊡: Swap a
friendly Gig with a rival Gig", Dexter DeShawn — Off the Grid's "⊡: Increase a Gig by up to 2",
Padre's "⊡: Set a player's Gig to the same value as another player's Gig", and the rest), and a
face-down Legend spent is a Call that arrives already sideways if you flip it later. The reaction
Call on their turn needs 1 €$ too. So the real price of playing a 3-cost Unit with one Eddie and two
Legends is: that Unit, minus one ability, minus one reaction Call, minus one QUICK you could have
paid for on their turn.

Some cards turn that around. NetWatch Netdriver reads "When this Unit or Legend is spent, draw 1";
on a face-up Legend it fires every time the Legend pays, so the Legend is an Eddie *and* a draw.
Zetatech Faceplate ("When this Unit or Legend is spent, adjust a Gig by up to 1. Then, if you
control 3 or more Gigs with different values, draw 1"), Tetratronic Rippler ("search the top card
of your deck. You may trash it") and Arasaka Emergency Radioport ("look at a friendly face-down
Legend. If that Legend is ARASAKA or has GO SOLO, you may Call it for free") do the same on the
spend. Sandevistan on a Legend readies it at the end of your turn, so it pays twice. That is the
Gear-on-Legend engine of chapter 9, and it is why the rules let you equip Gear to a face-up Legend
in the first place.

**The other engines.** Evelyn Parker — Beautiful Enigma readies an Eddie "When a friendly CORPO or
GANGER Unit steals 1 or more Gigs". Delamain Cab readies one at end of turn "if this Unit stole a
Gig this turn". Dying Night readies two "if this Unit is named 'V'" at the end of your turn (and
the FAQ, as our engine has it, readies them even if V died attacking). Rogue Amendiares — Queen of
the Afterlife readies two "the first time another friendly Unit steals a Gig with value less than
its power each turn". Misty Olszewski readies one on a correct type call. Then the discounts, which
are Eddies you never had to make: Zetatech Berserk (−1 per friendly face-up Legend), Alt
Cunningham — Soulkiller Architect (a Program for −1 per friendly min Gig), Johnny Silverhand —
Rocking Renegade (−1 per friendly Gig with 8+), Octant and Carnage at the Colosseum (the same),
MaxTac Heavy (−1 per rival Unit), Trauma Team Operatives (−1 per Unit in your trash), We Gotta Live
Together (5 becomes 3 while two Gigs behind), Nocturne (3 becomes 1 with an empty fixer), Viktor
Vektor — Drop Your Illusions (−3 on your first CYBERWARE Gear each turn), and the free Calls:
Tyger's Whisper, Panam Palmer — Strength Through Family, Chrome Reverie with a min Gig, T-Bug on
death, Radioport on a spend.

**The mistake.** Spending down to zero on your own turn with no reason. Everything you leave ready
is your reaction budget (chapter 5), and the rival can count it. The second mistake is selling the
card that wins: in our solved positions the simple player sells the Gear it needed *after*
attacking, one move too late, in five separate positions (`sell-to-afford-overwatch`,
`sell-to-afford-satori`, `sell-to-afford-the-blank-body`, `sell-to-afford-the-right-blade`,
`sell-to-afford-cyberpsychosis`). The rule is: sell first, and sell the card whose printed cost you
will never reach this turn, never the card that makes the attack.

**The numbers.** Payment has real content more often than the rules' "spend any number of Legends"
suggests: in 5,000 of our games, 14.2% of all payments spent a Legend that had something to lose
(a usable ability, the last face-down slot a reaction Call could still use, or a spend-trigger
Gear) while another source stood ready. Our engine now asks which Legends pay; a table does too.

**What this means for your deck.** Count your Sell Tags: that number is your economy, and a deck
with twenty-eight Units has twelve chances to ever make an Eddie. Count the cards that turn a
Legend's spend into something (Netdriver, Faceplate, Rippler, Radioport, Sandevistan, Alt
Cunningham — Mother of Daemons' draw on an equipped spend) and put them on the Legend you intend
to spend, not the one you intend to activate.

---

## 3. The Legends area

**The principle.** A Legend is four things in one slot: an Eddie, a blind Call, a reaction, and, for
eight of them, a body. Every use spends one of the others, and the order in which you cash them is
most of what separates a good turn from a bad one.

**Why, from the rules.** Legends "start face-down in a random order"; once per turn you may Call one
"without looking first", in your main phase or "as a reaction when a rival Unit attacks". Face-down
text is inert (as our rulings read the rules), so a Call is the only way to switch a Legend on, and
its CALL trigger fires when it flips. A Legend can be spent for 1 €$ face-up or face-down. The eight
Legends with a printed cost all carry GO SOLO: "Pay this Legend's cost to play it as a ready Unit.
It can attack this turn. If it leaves the field, remove it from the game."

**Calling blind is not always blind.** With two Legends already face-up, the third Call is a
certainty, and several of our solved positions turn on that: `steal-threshold-dexter-call-second-
seat` Calls the last face-down Legend knowing it is Dexter DeShawn — Off the Grid, takes his CALL
"+2 power to a friendly Unit" *before* the attack rather than "Draw 1" after it, and turns an
8-power attack into a 10-power one for two Gigs. With one face-up and two down, a Call is a coin
flip between two known cards, and you should know which two. With none face-up you know the
multiset and nothing else. The peeking cards (Kiroshi Optics' ATTACK, T-Bug's DEFEATED, Radioport's
spend) turn a lottery into a choice, and the fact that you looked is public even if what you saw
is not.

**Main phase or reaction?** The seven Legends with a CALL trigger are the reason to hold the Call:
Wakako Okada ("Give a rival Unit -2 power this turn" or "Draw 1", plus "⊡: Decrease a Gig by up to
2"), Padre ("Spend a rival Unit" or "Draw 1"), Dexter DeShawn — Off the Grid ("+2 power" or "Draw
1"), Muamar Reyes ("A friendly Unit can't be defeated in a fight this turn" or "Draw 1"), Dum Dum
("You may defeat a friendly Gear. If you do, draw 2. Otherwise, draw 1"), Viktor Vektor — Sit Down
and Relax (search five, take up to two cheap Gears), and V — Streetkid ("Trash 3. Then, add 1
BRAINDANCE Program from your trash to your hand"). Padre's spend and Wakako's −2 are *defensive*
CALLs: flipped during the rival's first attack, Padre turns their second attacker sideways so it
never attacks (`defend-padre-benches-the-second-raider`), and Wakako's −2 turns a 2-power raider
into a 0-power one that steals nothing (`defend-wakako-weakens-the-runt`). A Call spent in your
main phase for "Draw 1" is a Call you no longer have on their turn. The rule of thumb: Call in the
main phase when the flip changes *this* turn's attack (a Legend-counter, Saburo's aura, a +2 you
will use now); hold it when the flip is a lottery and the reaction might matter.

**What GO SOLO trades away.** A Legend that goes solo becomes a Unit that is *also still a Legend*
(the FAQ says so, and our engine counts it for Synapse Burnout, Zetatech Berserk and every other
"friendly face-up Legend" text). It arrives ready and can attack at once. In exchange the slot is
empty for the rest of the game, the Legend is no longer an Eddie, and when it leaves the field it
is removed from the game, so a fight it loses is a permanent loss of a third of your economy. The
FAQ adds two things a new player misses: a Legend may spend *itself* for 1 €$ toward its own GO
SOLO (`card-semantics-legend-pays-for-its-own-go-solo` wins on exactly that Eddie), and a costed
Legend may also be played to the field *without* the keyword, for its printed cost, arriving lagged
and in the same orientation it had. That second way exists for one reason: Riot Shield reads
"Rivals must pay +2 €$ to use GO SOLO", and the plain play is not GO SOLO (`card-semantics-legend-
plain-play-dodges-riot-shield`: Adam Smasher — Ender of Legends for nine, his PLAY "Defeat a rival
Unit" clears the blocker, the Wrecker takes both dice).

Gear equipped to a face-up Legend in the Legends area goes with it when it goes solo (the rules:
"When the host card moves to a different area, all equipped Gear goes with it"). Royce — Psycho on
the Edge reads "During your turn, this Legend has +2 power for each of its equipped Gear", and the
FAQ applies that in the area too, so two Tetratronic Ripplers on Royce *before* he goes solo make
him 6 + 1 + 1 + 2 + 2 = 12 on arrival (`card-semantics-royce-gear-in-the-legends-area`).

**Which Legend to spend when you have the choice.** Spend the face-down slot you do not intend to
Call: it reveals nothing about identity, and a spent face-down Legend can still be Called later
(it flips and stays spent). Spend the face-up Legend whose ability you have already used or cannot
use. Spend the Legend wearing the spend-trigger Gear, because that spend is a draw or an adjust.
Never spend the face-up Legend whose QUICK you will want on their turn (Goro Takemura — Vengeful
Bodyguard, Dum Dum, River Ward). In our games the choice was real in 14% of payments, and until
this month our engine made it for the player with a fixed order; a table never did.

**The mistake.** Calling at the first opportunity. Our simple player Calls a face-down Legend at
the first reaction window whenever it has an Eddie, because a face-up card looks like progress; it
is the single most common reason it loses the defensive positions in our suite (nine of thirteen
`defend-*` positions are built so that the early Call makes the real answer unaffordable). The
second mistake is the opposite one: sitting on a Legend-counter deck with three face-down Legends.
Zetatech Berserk costs 6 minus one per face-up Legend; Panam Palmer — Strength Through Family's
ATTACK draws one per face-up Legend; Goro Takemura — Losing His Way needs "all friendly Legends"
face-up for his +5. Those decks want the flips early and the Eddies late.

**The numbers.** Of 90,696 GO SOLO offers in 10,000 search-agent games, 5,793 were taken (6.4%).
The plain play was never taken for Rogue Amendiares — Preem Solo in 4,993 offers or for Adam
Smasher — Ender of Legends in 219, so we have no evidence about it beyond the rules; and the
search never once declined the discard on Panam Palmer — Strength Through Family's ATTACK in 385
offers, including turns where no Legend was face-up and the discard drew nothing. Read those as
holes in the machine's play, not as advice.

**What this means for your deck.** Pick at least one Legend whose CALL is a reaction (Padre,
Wakako, Muamar, Dexter) or whose text is a QUICK (Goro — Vengeful Bodyguard, Dum Dum, River Ward),
so that a held Call is a threat and not a coin. If you run a GO SOLO Legend, run the Gear that
rides with it and count the Eddie it can pay itself. If you run Legend-counters, do not run Adam
Smasher — Ender of Legends beside them: the solo'd Legend still counts, but a removed one does not.

---

## 4. Attacking

**The principle.** Only spent rival Units can be attacked, so a ready Unit is safe but protects
nothing; attacking is the act of spending your Unit into a rival turn where it can be fought; and
the steal count moves at 10 power, so the whole attacking game is the arithmetic of 9 versus 10.

**Why, from the rules.** "Ready Units can't be attacked." A Unit attacks by being spent, the target
is "a spent rival Unit (to start a fight), or the rival Gig area (to steal a Gig)", and "Units
steal an additional Gig at power 10, two more at power 20, and so on — and 0 Gigs at power 0". A
Unit that attacked on your turn is spent through the rival's whole turn: it can be attacked, and it
cannot use BLOCKER (which reads "spend this Unit"). So attacking exposes the attacker twice: as a
fight target and as a Blocker you no longer have. "A Unit doesn't have to attack. Ready Units can't
be attacked, but most Units — even ready ones — can't protect your Gigs; only Units with reaction
effects like QUICK or BLOCKER can interrupt attacks."

**The 10-power breakpoint.** A 9-power attacker and a 1-power attacker steal the same single Gig;
a 10-power attacker steals two. Nothing else in the game doubles a card's value for one point. The
cheapest points are: Japantown Jonin's PLAY ("Give a friendly Unit +2 power this turn") for two
Eddies on a 0-power body; Kiroshi Optics (+1 for one Eddie); Mantis Blades (+2 for one); Satori,
Dying Night, Zetatech Faceplate, Radioport, Netdriver and Sandevistan (+2 each); Saburo Arasaka's
aura ("Friendly ARASAKA Units have +1 power while attacking", which the FAQ applies in the steal
step, not only in fights); Dexter DeShawn — Off the Grid's CALL (+2); Johnny Silverhand — Rocking
Renegade's spend (+2 to a ROCKER); Dum Dum's QUICK (+1 per equipped Gear); Cyberpsychosis (+3 per
Gear, and the Unit dies at end of turn if it stole); Saul Bright ("Other friendly Units have +2
power while attacking"). Eleven of our solved positions are nothing but this arithmetic
(`steal-threshold-*`), and the machine's one-ply player fails every one of them because a +2 on a
Unit that has not attacked yet scores as a rounding error against the attack itself.

**Ordering the attacks.** Each attack resolves fully before the next, and the defender reacts to
each. Two consequences. First, a Blocker or a QUICK spent on your first attack is gone for your
second, so attack from least valuable to most valuable and let them spend their answers on the
swing that does not matter. Second, the defender knows what each attack threatens, so the swing
that takes their *last* die is the one that draws the reaction. The play-around family in our suite
is the catalogue: against a Green rival holding Take Control ("QUICK: A rival Unit steals 1 fewer
Gig this turn. If that Unit is an AI, DRONE, or VEHICLE, draw 1") with two Eddies up, the winning
line sends the one-Gig DRONE first, which draws no reaction because a die remains, and then the
two-Gig attacker for the last two, when the reaction is forced and still chases the DRONE for the
card (`play-around-take-control-bait-the-drone`, and the same shape with a VEHICLE, an AI and a
Minotaur). Against a spent solo'd Legend on their field and a 0-power Blocker in front of it, attack
the *Legend* first: a fight that defeats it removes it from the game, so the defender throws the
Blocker in front of that rather than let it happen, and your real attacker then walks into an
empty Gig area (`play-around-draw-the-bombus-block`). Against Overwatch on a face-up rival Legend
("QUICK 1 €$, ⊡: Discard 1. Defeat a spent rival Unit with cost equal to or less than the
discarded card's cost"), attack their spent Ruthless Lowlife with a cheap Unit first; the rival
spends Overwatch to save a Unit that cannot even attack Gig areas, and your 10-power Unit then
takes both dice (`play-around-overwatch-eats-the-fang`). None of these first attacks is worth
anything on the board, and that is the point.

**Blockers you can go through.** Valentino Guerrera: "If you have more ★ (Street Cred) than a
Rival, this Unit can attack ready Units with BLOCKER", and the FAQ says the attacked Unit cannot
block him with itself. MTOD12 Flathead: "If you have less ★ (Street Cred) than a Rival, this Unit
can't be blocked", fixed at the moment the attack is declared. Gunpoint Diplomacy gives a friendly
Unit "may attack ready Units" or +3 power, but if you have less Street Cred the rival chooses which.
Corporate Surveillance ("Spend a rival Unit with cost 4 or less"), Padre's CALL and Offduty
Malfini's PLAY ("Spend this Unit and a rival Unit") turn a Blocker sideways for the length of one
attack, and a spent Unit cannot block. Bonnie and Clyde, Caliber, Royce — Don't Call Me Simon and
Minotaur kill small ones outright.

**What to leave ready.** Every Unit that attacked is a fight target and a non-Blocker on their
turn. Every Eddie you spent is a reaction you cannot afford. The cards that ready things at the end
of your turn make attacking free: Saul Bright ("At the end of your turn, ready up to 3 friendly
Units"), Sandevistan's host, Modded Muramasa ("if you have less ★ than a Rival, ready this Unit"),
MaxTac Squadron ("if this Unit is spent, ready a friendly face-up Legend"), Panam Palmer — Nomad
Cavalry (readies everything at five equipped), Wraith Marauders (readies a Unit whose power equals
the stolen die), Johnny Silverhand — Never Stop Fighting ("The first time this Unit wins a fight
each turn, ready it"). A Unit that will be ready again when the turn ends should always attack.

**The mistake.** Leading with the biggest attack. It is the swing the defender is waiting for, and
the one their single QUICK or Blocker is saved for. Our simple player leads with its best attack in
every one of the twelve play-around positions and loses them all; the search player solves one.

**The numbers.** In 10,000 search-agent games, 348,002 attacks were offered and 147,932 taken
(42.5%); the defender had a Block available 30,916 times and used it 10,339 times (33%). The
search solves 4 of the 11 steal-threshold positions and 5 of the 13 race positions in our suite;
the simple player solves none.

**What this means for your deck.** Every attacker wants to be 10, not 8, and the cheapest route is
a Gear or a Jonin, not a bigger Unit. Count how many of your Units reach 10 with one card, and run
that card. Run something that goes through Blockers (Valentino, Flathead, Surveillance, Padre) or
something that kills them, because the decks you meet will run eleven Blockers between them.

---

## 5. Defending

**The principle.** The reaction window is a second game with its own budget: what you left ready
at the end of your turn, and nothing else. A rival who ended their turn with nothing ready cannot
react, and you can see that.

**Why, from the rules.** After the attacker is spent and its ATTACK effects resolve ("and before
your Rival reacts"), the defender "may take any number of these": Call a Legend (once per turn, 1
€$), QUICK effects and Programs, BLOCKER. A Block "redirects the attack to it instead", each Block
replaces the target, there is no limit on Blocks per attack (FAQ), and "even if you defeat it, you
don't steal any Gigs" — a blocked attack never steals. The attacker gets no reply window. Sell is
not allowed in a reaction (main phase only). Every QUICK Program costs at least 1 €$; the QUICK
abilities cost 1 or 2 except River Ward's, which is free, and Alt Cunningham — Mother of Daemons'
replacement ("When a rival Unit would steal a Gig, you may discard 1 with cost equal to that Gig's
value. If you do, the Gig isn't stolen"), which costs a card.

**What you can react with.** Eleven Blockers: eight Units (Corpo Security 2, Lizzy Wizzy 2, Mox
Inciters 2, Rita Wheeler 4, La Llorona 3, Meredith Stout 5, Augmented Negotiators 2, Secondhand
Bombus 0), two Gear (Riot Shield, Mandibular Upgrade — a 1-cost Gear that makes any host a
Blocker), and Goro Takemura — Hands Unclean once he is on the field. Goro Takemura — Vengeful
Bodyguard makes one: "QUICK 1 €$, ⊡: Give a friendly Unit with cost 4 or less BLOCKER this turn."
Seven QUICK Programs (chapter 6 has the table). Five QUICK abilities: Goro — Vengeful Bodyguard, Dum
Dum (+1 per equipped Gear), River Ward ("Play a Gear with cost 2 or less from your hand for free"),
Rogue Amendiares — Queen of the Afterlife ("2 €$, ⊡: A rival Unit loses power equal to this Unit's
power this turn"), and Overwatch on a Unit or face-up Legend. Overwatch deserves a sentence of its
own: the attacker is spent the moment it attacks, so "defeat a spent rival Unit with cost equal to
or less than the discarded card's cost" kills the attacker *in the window*, before it steals, if
you have a card expensive enough to discard (`defend-overwatch-discards-the-big-card`).

**The window as a game.** Sequence inside it: Call first (the flip may draw a QUICK or turn on a
QUICK Legend), then pumps, then decide on the Block knowing final powers. A Block is a fight your
Unit fights as if it had attacked, so it should be a fight you want: Animals Wrecker wearing Riot
Shield takes Johnny Silverhand — Never Stop Fighting's 8 with 11 and he stays down; Corpo Security
takes the 4-power Valentino and dies for the die (`defend-johnny-comes-back-block-with-the-
wrecker`). Block Johnny with the 2-power Unit instead and he wins, readies ("the first time this
Unit wins a fight each turn, ready it") and attacks again into a board with nothing left. Safety
Override ("The next time a friendly Unit loses a fight this turn, defeat the opposing rival Unit")
turns a losing Block into an execution (`defend-safety-override-kills-johnny`); Synapse Burnout
("+1 power for each friendly face-up Legend while fighting rival Units this turn") turns it into a
winning one when your Legends are face-up (`defend-synapse-outmuscles-johnny`). Rogue's 2 €$ makes
a 4-power attacker a 0-power one, and "0 Gigs at power 0" (`defend-rogue-drains-the-thief`). Floor
It's −1 does the same to a 1-power attacker and draws a card (`defend-floor-it-the-one-power-
thief`). Detonate ("Defeat a rival Gear with power 2 or less") takes Mantis Blades off a 10-power
attacker and makes it an 8 (`defend-detonate-the-blades`). Take Control makes a two-Gig steal a
one-Gig steal.

**How to tell they cannot react.** Count what is ready on their side at the end of their turn:
Eddies, Legends (each is an Eddie or a Call), Blockers on the field, Units with a QUICK ability and
the Eddies to pay it, Gear with QUICK. If the ready Eddies plus ready Legends are zero, there is no
Call, no QUICK Program, no paid ability; only Blockers, River Ward's free Gear, and Alt's discard
remain, and all three are on the table in front of you. That is a turn to attack with everything.
In our search-agent games the defender had *nothing but Pass* in 66% of reaction windows (104,848
of 158,496): tapped out is the normal state, and a player who leaves one Legend ready is already
unusual.

**The mistake.** Two of them, opposite. Blocking when the fight loses and the Blocker is worth more
than the die (a Blocker is also next turn's attacker), and *not* blocking when the die is the
seventh. Our simple player blocks only when the naive attack would take its last stealable die; a
human who learns that pattern in a rival can attack around it forever, and one who does the same
thing gets attacked around. The third mistake is the first-window Call: it spends the Eddie the
real answer needs (chapter 3).

**The numbers.** The search player holds 3 of the 13 defend positions in our suite; the simple
player holds none. Reaction-window entropy in the search corpus is 0.50 nats, the second-lowest
of any decision kind, which is to say the machine's defensive play is close to a fixed rule.

**What this means for your deck.** A deck with no Blocker, no QUICK and no reaction Call has no
defence at all, and a rival who counts will know it. Two cheap Blockers and one QUICK trick
(Safety Override in Yellow with two Yellow Legends, Synapse Burnout in Green, Reboot Optics or
Floor It in Blue, Detonate in Red) turn every one of the rival's attacks into a question. And the
budget is planned on your own turn: the Eddie you leave ready is the price of the question.

---

## 6. Reading the opponent

**The principle.** Deck-building rules are public, so every card the rival shows proves something
about their whole deck; and everything you show proves something about yours.

**Why, from the rules.** Every Legend has RAM 2 and "each Legend's RAM only counts toward its own
color", so a colour's cap is 0, 2, 4 or 6 depending on how many of the three Legends are that
colour. A card of colour X and RAM r is legal only if X's cap is at least r, so it proves at least
⌈r/2⌉ Legends of X. Three slots is all there are, so proofs compete: two Legends of X proven means
at most one slot for everything else, which caps every other colour at 2. The main deck is 40 to
50 cards with at most three copies of each, and cards must stay within the RAM limit.

**The table.** What the rival can still be holding, from what they have shown (computed over every
legal triple; "cards they can still hold" is the size of the pool their hidden cards must come
from):

| shown so far | Red cap | Green cap | Blue cap | Yellow cap | cards they can still hold |
|---|---:|---:|---:|---:|---:|
| nothing | 6 | 6 | 6 | 6 | 124 |
| one Blue card, RAM 1–2 | 4 | 4 | 6 | 4 | 122 |
| one Blue card, RAM 3–4 | 2 | 2 | 6 | 2 | 97 |
| one Blue card, RAM 5 | 0 | 0 | 6 | 0 | 31 |
| Blue RAM 3–4, then any Red card | 2 | 0 | 4 | 0 | 53 (triple fixed: Blue, Blue, Red) |
| Blue, Red, Yellow, each RAM ≤ 2 | 2 | 0 | 2 | 2 | 65 (triple fixed: Blue, Red, Yellow) |

Two colours each with a RAM 3+ card is impossible under a legal deck. A face-up Legend proves
itself, and the unique-name rule removes its namesake: a face-up Jackie Welles — Mama's Favorite
(Green) proves the Blue Jackie is absent (the clashes are V, Goro Takemura and Jackie Welles).
Once the triple is fixed, the rival's remaining deck is exactly their pool minus everything you
have seen, at most three copies each.

**What a Sell reveals.** The card, permanently: "reveal it to your opponent, then place it
face-down in the Eddies area", and its identity in the Eddies multiset is public for the rest of
the game. A Sell of a RAM-3 Program fixes two Legends of its colour on the spot. And only Programs,
Gear and Flathead can be sold, so the sold card was the sellable card they valued least: a Sell of
Take Control on turn two says they did not expect to need a QUICK.

**What a declined Block reveals.** A ready Blocker on the table and a Gig attack waved through means
one of three things: they value the Blocker's body over that die (it is not their last), they hold
a QUICK they preferred to keep, or they are our simple player. A declined Call with an Eddie up
means the face-down Legends are not worth a coin to them right now. Passing with two Eddies ready
and a Green cap of 2 or more says Take Control or Synapse Burnout may be coming on the next attack;
passing with none says nothing can.

**The seven QUICK Programs, and how to know which are live.**

| Program | colour | cost | RAM | needs | what it does |
|---|---|---:|---:|---|---|
| Floor It | Blue | 1 | 1 | one Blue Legend | rival Unit −1 power, draw 1 |
| Reboot Optics | Blue | 2 | 2 | one Blue Legend | next rival fight does not defeat your Unit |
| Synapse Burnout | Green | 1 | 1 | one Green Legend | +1 per friendly face-up Legend in fights |
| Take Control | Green | 2 | 2 | one Green Legend | rival Unit steals 1 fewer; draw vs AI/DRONE/VEHICLE |
| Detonate | Red | 1 | 2 | one Red Legend | defeat a rival Gear with power ≤ 2 |
| Safety Override | Yellow | 2 | 3 | **two** Yellow Legends | when your Unit loses a fight, defeat the winner |
| Cyberpsychosis | Yellow | 3 | 2 | one Yellow Legend | +3 per Gear on an equipped Unit; it dies at end of turn if it stole or fought |

A Program is live when its colour's cap is at least its RAM *and* they have the Eddies ready to
cast it. Safety Override needs two Yellow Legends, so a rival who has shown a Green RAM-4 card
(Overwatch, Wild in the Streets, Riding Nomad, Panam Palmer — Strength Through Family) cannot have it: two Green Legends cap Yellow at 2. The QUICK abilities join the list:
Goro — Vengeful Bodyguard and Dum Dum need 1 €$, Rogue Amendiares — Queen of the Afterlife needs 2,
Overwatch needs 1 and a card, River Ward needs a Gear in hand. And the replacement effects: Alt
Cunningham — Mother of Daemons needs a hand card whose cost equals the die you are stealing, so a
die showing 10 or more is unprotectable (no non-Legend costs more than 9); Jackie Welles — Mama's
Favorite needs 1 €$ and saves a Unit by removing herself from the game.

**The other side: what you give away, and how to give away less.** Every Sell shows a colour and a
RAM; sell what is already proven or duplicated, and keep unseen colours and RAM-3 cards in hand
until they are played for effect. A RAM-3 card played on turn one fixes two of your Legends and
tells the rival which of *your* QUICKs are impossible. Face-down Legends keep their colour, cap and
CALL hidden and still pay 1 €$; a Call as a reaction reveals at the moment it matters and not
before. Spending a Legend reveals which slot turned sideways and nothing about what it is, so spend
the slot you will not Call. There is no hand limit, and only counts leak from a hand. Attack before
developing, so they commit reactions before they see your board. Where a card lets you decline a
reveal, decline it: Sketchy Ripper and Viktor Vektor — Sit Down and Relax "may" reveal (FAQ), and
T-Bug never reveals what it looked at. Ending your turn with Eddies up is itself a message, true or
false: a held Eddie with nothing behind it is the only bluff this game has.

**The numbers.** Our belief model uses nothing but the colour and RAM bounds above and the cards it
has seen. On 200 held-out games it predicts the rival's next revealed card 0.53 nats a card better
than a uniform guess over the pool, which is to say its guess is about 1.7 times as likely to be
right, and it never once assigned zero probability to the truth. The list itself was worth less
than we expected to the search player: given the rival's exact decklist rather than the inferred
pool, its panel score moved 0.9 points, inside noise, and a version that could see the rival's
hand beat the honest version 44.6% of the time [39.0, 50.2] at the training search budget. We
suspect that says the machine does not yet know what to do with the information, not that the
information is worthless; a strong human would tell you otherwise, and chapter 12 says why.

**What this means for your deck.** Your first Sell and your first RAM-3 card are announcements;
choose which ones you are willing to make. Two-colour and three-colour decks are fixed as soon as
the second colour shows; a mono deck shows the least per card and the most at once (chapter 10c).
Run at least one QUICK your rival cannot rule out from your colours, because a possible QUICK is a
reaction you never have to cast.

---

## 7. Dice

**The principle.** The five dice you roll in are a five-turn plan, the die you steal is a choice
about conditions and not about count, and the biggest face is the right answer far less often than
it looks.

**Why, from the rules.** "At the start of your turn, after drawing, choose one die from this area,
roll it to set its value, then move it to your Gig area. You may choose any die except the d20,
which is always last." So the first five turns each ask which of d4, d6, d8, d10, d12 to roll, the
sixth is forced, and a stolen die keeps its face (as our rulings read the rules: the die moves, it
is not rerolled). Street Cred is the sum of the faces in your Gig area, and a steal moves cred by
twice the face between the two players. Adjusting a die to a value not on its face fails, and
adjusting by zero is not adjusting (FAQ).

**Which die to roll.** The means are 2.5, 3.5, 4.5, 5.5, 6.5 and 10.5. Small dice make min Gigs
and pairs and are cheap to lose; big dice make 8+ faces and Street Cred and are expensive to lose.
About forty cards key on individual faces, and they sort into packages:

* *Min Gig.* Alt Cunningham — Soulkiller Architect ("Your next Program this turn plays for -1 €$
  for each friendly min Gig"), Chrome Reverie ("If you control a min Gig, you may Call a Legend for
  free"), Jackie Welles — Pour One Out For Me ("If it becomes a min Gig, draw 1"), Three Mouths,
  One Desire ("You may add 1 more for each friendly min Gig"), Trust No One ("if you control a min
  Gig, draw 1"), Pyramid Song ("If a friendly d4 is a min Gig, choose both instead"), Kerry
  Eurodyne — Axe, Attitude, Audience ("When you roll a min or max value on a Gig, draw 1. If it's a
  d20, draw 3 instead"). A d4 showing 1 is a min Gig that feeds five of these at once and costs one
  point of cred if stolen.
* *8+.* Industrial Assembly ("Increase a Gig by up to 4. If you control a Gig with 8+ value, draw
  1"), Octant and Carnage at the Colosseum (−1 €$ per 8+ Gig), Johnny Silverhand — Rocking
  Renegade (his ability costs −1 per 8+ Gig), Kerry Eurodyne — The Last Rockerboy ("⊡: If you
  control a Gig with 8+ value, draw 2"), V — Roamer of the Badlands ("if you control 2 or more Gigs
  with 8+ value, draw 1"). Only the d8, d10, d12 and d20 can show 8+, and only the d20 can show it
  by default more often than not.
* *Value-pairs.* Hanako Arasaka — Daughter of the Emperor ("At the start of your turn, draw 1 for
  each friendly value-pair of Gigs"), Pepe Najarro ("If you control a value-pair of Gigs, ready up
  to 2 MERC Legends"), Sandayu Oda ("Spend a rival Unit for each friendly value-pair"), Goro
  Takemura — Vengeful Bodyguard (+1 with a pair), Peace Offering ("set a Gig's value to the value
  of another Gig. Then, if you control a value-pair, draw 1"). Small dice pair easily.
* *Parity.* Field Operator, Memory Relapse and Pacifica Netrunner want even cred; Jackie Welles —
  Ride or Die Choom counts even friendly Gigs on attack and odd ones on death; Rogue Amendiares —
  Preem Solo draws on an even stolen value and makes the rival discard on an odd one; Bootleg
  Black Sapphire Show draws two with one even and one odd Gig.
* *Distinct values and max.* Afterparty at Lizzie's (draw with two different values), Zetatech
  Faceplate (draw with three), Gorilla Arms (steal a value no friendly Gig shares), El Sombrerón
  ("gains power equal to a friendly max Gig" — a die on its top face).
* *Cost equals a Gig value.* Hanako Arasaka — In a Gilded Cage, The Heist, Heywood Ripperdoc,
  Caliber's DEFEATED, Alt Cunningham — Mother of Daemons, Shattered Memories. Small values here are
  worth more than big ones, because cards cost 1 to 9.
* *Specific dice.* 6th Street Recruits ("When a friendly Unit steals a d6, increase a Gig by up to
  6"), Over the Edge ("Defeat a Unit with power equal to or less than the value of a friendly
  d20"), Pyramid Song's d4, Kerry's d20.

So the answer to "which die first" is the hand: a hand of min-Gig cards rolls the d4 on turn one;
a hand with Octant rolls the d12; a Hanako deck rolls the two small dice early to pair them. The
default of rolling big first buys cred and a target.

**Which die to steal.** When your power fixes the count, the pick is entirely about conditions, and
our dice family is the catalogue. Steal the smallest die on the table when it is the only even one
and Jackie attacks next (`dice-even-die-for-jackie`: take the d6 showing 2 and she attacks at 10
for two). Steal the die that makes your cred even before Pacifica (`dice-steal-even-cred-for-
pacifica`: 21 plus 3 is 24; 21 plus 8 is 29). Steal the die whose value is less than your Unit's
power so Rogue readies two Eddies and V goes solo (`dice-rogue-readies-the-solo`: the 3, not the
11). Steal the die whose face equals a spent friendly Unit's power so Wraith Marauders ready it
(`dice-marauders-wake-the-netrunner`: the 1, to wake a 1-power Unit that then takes the seventh).
Steal the d6 so the Recruits push another die to its top face for El Sombrerón (`dice-recruits-
pump-for-sombreron`). Keep every friendly face below the solo'd rival Legend's power under
Westbrook Netrunner (`dice-westbrook-keeps-them-small`). Under Gorilla Arms, steal a *shared*
value first so the bonus steal still has an unshared one to take, and think a turn ahead about
which values your fixer can still produce (`dice-orphan-a-value-for-tomorrow`).

**The adjusters.** Seventeen cards move dice, and thirteen of them are unscoped — they can move
*either* player's dice: Industrial Assembly (+4), Trust No One (−3), Afterparty (±1), Peace
Offering (set to another Gig), Dying Night's ATTACK (−2), Zetatech Faceplate (±1 on a spend), Dexter
DeShawn — One Last Chance (±1 on play and attack), Dexter — Off the Grid's spend (+2), Muamar Reyes'
spend (±1), Wakako's spend (−2), Padre's spend (set to another), Hanako's spend (swap), MaxTac AV's
PLAY (swap), La Llorona (+3 when she blocks), 6th Street Recruits (+6 on a stolen d6), V — Roamer
(+5 on a steal), Kerry (reroll). Their uses, in rough order of how often a new player misses them:
flip your own parity; make or break a pair; push a die over 8 before a cost check; raise a die
above an attacker's power under Chrome Fang ("rival Units can't steal friendly Gigs with value
higher than their power"); lower your own cred to turn on Flathead, Towerfall ("If you have less ★
than a Rival, choose both") or Modded Muramasa; and, the one that feels wrong, *lower your own
die*. Meredith Stout punishes adjustments of her side's dice ("When a Rival adjusts or swaps 1 or
more friendly Gigs, you may add a card from your trash to your hand"), so against her, adjust your
own.

**The mistake.** Rolling and stealing for Street Cred. Cred wins nothing; it gates thirteen cards
and it makes your dice a target. The machine's one-ply player always takes the biggest die, and it
is what every dice position in our suite is built to punish.

**The numbers.** With our value head as the judge, at the start-of-turn die choice the chosen die
was the best option 55% of the time and the *biggest* die was best only 40.9% of the time (8,000
decisions); at steal picks the chosen die was best 79.5% (9,039 decisions). The judge is our own
evaluator, which is weak on dice, so read these as "the big die is not the default" rather than
as a ranking. The search player, which does search the roll, rolled the five dice in an order
close to random over 80,000 start-of-turn decisions (each of the five chosen between 14,600 and
16,700 times): it has no fixer plan at all. The dice family in our suite: the search solves 2 of
12, the simple player 0.

**What this means for your deck.** Decide what your dice are for before you pick cards: a min-Gig
deck, an 8+ deck, a pair deck and a parity deck want different rolls and different steals, and a
deck that runs two of these packages will find they fight each other. Run at least two adjusters
that reach your own dice; the ones that reach the rival's are a bonus. And know your face count:
d4 and d6 make even and odd equally, the d20 makes 8+ two times in three.

---

## 8. Turn sequencing

**The principle.** Almost every card in the game reads the board at one instant, and the main phase
lets you act "any number, any order". Close games are decided by which instant you choose.

**Why, from the rules.** The main phase actions are Sell (once), Play, Call (once), Attack, in any
order; costs are paid when the card is played; triggers read the board when they fire; "the first
time … each turn" counts events from the start of the turn, including ones before the card arrived
(the FAQ, as our engine has it); end-of-turn effects resolve while your attackers are still spent;
and costs resolve *after* the thing they paid for (FAQ: play the card first, then the spend
triggers), so a Legend wearing Netdriver draws after the Program it paid for has resolved, with the
new card in hand for the next play. When two of your own triggers fire at once, you order them
(FAQ, ruling 046 in our engine).

**The orderings that decide games.**

1. *Sell first.* The Eddie is spendable immediately and the Sell is once a turn; a Sell after the
   attack buys nothing this turn.
2. *Call before the Legend-counters.* Zetatech Berserk ("-1 €$ for each friendly face-up Legend"),
   Synapse Burnout, Panam Palmer — Strength Through Family's ATTACK ("draw 1 for each friendly
   face-up Legend"), Goro Takemura — Losing His Way ("If all friendly Legends are face-up"), and
   before the first ARASAKA attack if Yorinobu Arasaka — Embracing Destruction is the one still
   down ("The first time a friendly ARASAKA Unit attacks each turn, draw 1"). The FAQ fixes the
   moment: a Legend flipped after the attack is declared does not count.
3. *Dice before cost and condition checks.* Industrial Assembly's +4 before Octant, Carnage or
   Johnny — Rocking Renegade's discount; Peace Offering before Hanako's pair count or Sandayu
   Oda's PLAY ("Spend a rival Unit for each friendly value-pair"); Trust No One before Pacifica.
4. *Board-priced costs at the right moment.* MaxTac Heavy ("-1 €$ for each of a Rival's Units")
   before you remove their Units; Trauma Team Operatives ("-1 €$ for each Unit in your trash")
   after trades (`recursion-trade-corpse-pays-the-trauma-team` trades a Unit for the third corpse
   that makes it affordable); We Gotta Live Together, Nadia and Adrenaline Converter while you are
   still behind (`race-converter-needs-them-two-ahead`: play the Converter *before* the steal that
   closes the gap, or it never has ADRENALINE).
5. *First-time-each-turn triggers make the first instance the one that counts.* Viktor Vektor —
   Drop Your Illusions discounts your *first* CYBERWARE Gear by 3, so play the expensive one first;
   Jackie Welles — Pour One Out For Me acts on your first Blue Unit or Blue Gear; Rogue Amendiares —
   Queen of the Afterlife readies two Eddies on the first qualifying steal, so make that steal
   before the plays it funds; Gorilla Arms' bonus is on the first steal; Rita Wheeler draws and
   discards on the first spend. And the flip side: Yorinobu Arasaka — Steel Dragon draws on "the
   first time an ARASAKA Unit is defeated each turn", so if one already died this turn before he
   landed, he draws nothing.
6. *Attacks that ready or fund before the plays they pay for.* Johnny Silverhand — Never Stop
   Fighting readies on his first fight win, Wraith Marauders ready a Unit, Pepe Najarro readies
   MERC Legends, Evelyn — Beautiful Enigma readies an Eddie per CORPO or GANGER steal, Rogue readies
   two: all of these are Eddies and attackers for the rest of the same turn if the attack comes
   first.
7. *Haste grants before the attack, permissions before the play.* Valentino Street Racer's PLAY
   gives "another friendly Unit with cost 5 or less ADRENALINE this turn", so the Unit it targets
   must already be on the field (`race-pacifica-before-the-racer`: the 1-power Netrunner first, the
   Racer second, the Netrunner attacks); Johnny — Rocking Renegade's spend lets a Unit attack spent
   rival Units the turn it is played and works on a Unit played earlier (FAQ); Yorinobu — Steel
   Dragon's free play "can attack rival Units this turn".
8. *End-of-turn readies make attacks free.* Saul Bright readies up to three Units at end of turn,
   Sandevistan readies its host, Modded Muramasa readies itself when behind on cred, MaxTac
   Squadron readies a Legend, Panam — Nomad Cavalry readies everything at five equipped: a Unit that
   will stand up again should attack, and a Legend that will stand up again should pay.
9. *Setups before the swing that reads them.* The Jonin's +2, the Kiroshi's +1, Saburo's Call,
   Dexter's CALL, the Gear on the attacker: every one of them is worth nothing on a Unit that has
   already attacked. Our entire steal-threshold family is this rule.

**The example.** `race-dying-night-drops-my-cred`: six Gigs against one, the rival's last die is a
d12 showing 12 behind a ready Corpo Security with BLOCKER, your cred is 13 to their 12, and your
attackers are MTOD12 Flathead ("If you have less ★ than a Rival, this Unit can't be blocked") and a
Ruthless Lowlife ("can only attack rival Units") wearing Dying Night ("ATTACK: Decrease a Gig by up
to 2"). The order is: Lowlife attacks a spent 0-power Sketchy Ripper, a fight that wins nothing,
and its Gear's ATTACK lowers *your own* d20 from 4 to 2; now 11 is less than 12, Flathead cannot
be blocked, and it takes the d12 as the seventh. The same two attacks in the other order lose.

**The mistake.** Attacking first because the attack is the biggest thing on the board. Every setup
in this chapter is invisible on the board until the attack reads it, and a player who scores the
board after each move will make the attack first every time. Our simple player does, in all 132
positions.

**The numbers.** The suite's horizon-1 positions (the win is inside the searched turn) are solved
24 of 110 by the search and 0 by the simple player; horizon-2 positions (the setup pays off a turn
later) 7 of 22 and 0. Ordering inside a turn is something the machine can partly find by search;
ordering across two turns it mostly cannot.

**What this means for your deck.** A deck is a set of orderings. If your Legend-counter cards
want early Calls and your reaction Calls want held ones, the deck argues with itself; if your
cost-reducers want a full rival board and your removal wants an empty one, likewise. Read each card
for the instant it checks, and build so that your instants agree.

---

## 9. Card families and the counters to each

**The principle.** The set's 151 cards are a small number of engines and a small number of answers,
and every engine is priced by how many answers it has.

**Why, from the rules.** Tags are "a card's affiliations, referenced by effects"; only ten of the
thirty-nine printed tags are ever referenced by text (ARASAKA, CORPO, GANGER, ROCKER, BRAINDANCE,
MERC, AI, DRONE, VEHICLE, CYBERWARE). Everything else is a matter of what a card's text reads:
dice, Gear, the trash, face-up Legends.

**Tag engines.**

* *ARASAKA* (19 cards). Saburo Arasaka: "Friendly ARASAKA Units have +1 power while attacking",
  which turns the 9-power ARASAKA bodies (Minotaur, Yorinobu — Steel Dragon) into two-Gig stealers
  and puts Sandayu Oda (8) and Goro — Losing His Way (4 + 5) within a Gear of it. Yorinobu —
  Embracing Destruction draws on the first ARASAKA attack; Yorinobu — Steel Dragon draws on the
  first ARASAKA defeat, either side's; Arasaka Emergency Radioport looks at a face-down Legend on a
  spend and Calls it free if it is ARASAKA or has GO SOLO. In our Legend-swap test Saburo was the
  largest single-card effect we have ever measured: removing him from an ARASAKA list cost 18.5 to
  19.7 points against every legal replacement (p < 0.001 on all four), and 8.8 to 12.9 points in
  the Embracing Power starter. *Counters:* the aura is "while attacking" only, so fights on your
  turn ignore it; Take Control makes the two-Gig steal a one-Gig steal; Blockers turn it into a
  fight; and the bodies are big-Unit removal targets (Over the Edge with a high d20, Les Élémens
  bottom-decks the lowest-power one, Wild in the Streets and Don't Fear the Reaper hit spent ones).
  Saburo himself has no cost and never reaches the field, so he cannot be attacked.
* *CORPO and GANGER.* Evelyn Parker — Beautiful Enigma readies an Eddie when a friendly CORPO or
  GANGER Unit steals (nine CORPO Units, twenty GANGER Units); Johnny Silverhand — Never Stop
  Fighting "wins all fights against CORPO Units". *Counter:* against Johnny, do not fight with
  CORPO; block him with something else, or let him attack the Gig area and take the die back.
* *ROCKER.* Johnny — Rocking Renegade's spend gives a ROCKER +2 and same-turn attacks on rival
  Units; Rockn' Rockerboy is 8 power for 5 at RAM 1; Kerry — The Last Rockerboy draws two with an
  8+ Gig. *Counter:* the +2 is a spend of a Legend and 2 €$ minus discounts; a Blocker eats the
  10-power swing.
* *BRAINDANCE.* Thirteen Programs, none of them QUICK. Judy Álvarez — Braindance Maestro gives a
  friendly Unit +1 when you play one and digs for them with her spend; V — Streetkid's CALL fetches
  one from the trash; Alt Cunningham — Soulkiller Architect replays one from the trash and discounts
  the next by your min Gigs. *Counter:* bottom-deck the trash engine's fuel; Meredith Stout draws
  from the trash when her dice are adjusted, so the dice Programs feed her.
* *MERC.* Ten of the 27 Legends are MERC; Pepe Najarro readies up to two of them on a value-pair
  when he attacks, which is two Eddies or two abilities back. *Counter:* break the pair.
* *CYBERWARE.* Thirteen of the seventeen Gear. Viktor Vektor — Drop Your Illusions plays the first
  one each turn for −3; Viktor — You Might Feel a Little Pinch replays a cheap one from the trash on
  another Unit. *Counter:* Gear removal (below).
* *AI, DRONE, VEHICLE.* Twelve Units. Take Control draws a card when it hits one, and that is the
  bait our play-around positions are built on: the reaction chases the card.

**Dice engines.** Chapter 7. *Counters:* Meredith Stout against adjusters; Westbrook Netrunner
("rival Legends can't steal friendly Gigs with value less than their power") against solo'd
Legends; Chrome Fang ("rival Units can't steal friendly Gigs with value higher than their power")
against small attackers; steal their key die first.

**Gear engines.** Gear on a face-up Legend fires every time the Legend pays (Netdriver's draw,
Faceplate's adjust and draw, Rippler's peek, Radioport's look and free Call), and Sandevistan
readies it for a second payment. Royce — Psycho on the Edge is +2 per Gear during your turn; Dum
Dum's QUICK is +1 per Gear; Cyberpsychosis is +3 per Gear; Panam — Nomad Cavalry moves a Gear from
herself to a Unit and readies it, and readies everything at five equipped; Alt Cunningham — Mother
of Daemons draws when an equipped Unit or Legend is spent; River Ward plays a cheap Gear free in the
window and digs when an equipped Unit dies; Maelstrom Goons make the rival discard when equipped;
Gilded Matón and Dum Dum's CALL cash a Gear in. *Counters:* Detonate ("Defeat a rival Gear with
power 2 or less") kills twelve of the seventeen Gear and misses only Overwatch, Zetatech Berserk,
Adrenaline Converter, Gorilla Arms and The Relic; Heywood Ripperdoc's PLAY defeats any Gear;
Maman Brigitte bottom-decks only *unequipped* Units, so a single Gear is armour against her; and
because "when the host card moves to a different area, all equipped Gear goes with it", killing or
bottom-decking the host takes the Gear too.

**Trash engines.** Play from the trash: Yorinobu — Steel Dragon (a Unit cost ≤4 from hand or
trash), Lizzy Wizzy (a Program cost ≤3 from hand or trash), Alt — Soulkiller Architect (a Program),
We Gotta Live Together (two Units cost ≤3), Viktor — Little Pinch (a CYBERWARE Gear cost ≤2), The
Relic ("DEFEATED: Play another Unit with cost 9 or less from your trash for free"), Judy's spend.
Return to hand: Screw ("DEFEATED: Add another Unit from your trash to your hand"), Meredith Stout,
V — Streetkid, All is Lost, The Heist, Hacked Corpo. Trauma Team Operatives is priced by corpses.
Our recursion-trade positions are all one shape: trade a Unit evenly, or kill your own, to cash
the trigger (`recursion-trade-relic-into-kusanagi`: attack a spent 0-power Maelstrom Zealots so
both die, The Relic plays Modded Kusanagi free, ADRENALINE attacks at once). *Counters:*
bottom-decking instead of defeating. The rules trigger DEFEATED "when this Unit is defeated", and
a bottom-decked Unit is not defeated, so Les Élémens, Pyramid Song, Towerfall, Unlikely Bond,
Maman Brigitte and Placide all skip the DEFEATED text and put the card where no trash effect can
reach it. Six cards do that; count them in a deck that fears Screw and The Relic.

**Legend-count engines.** Zetatech Berserk, Synapse Burnout, Panam — Strength Through Family, Goro —
Losing His Way, MaxTac Squadron, Pepe, and the free Calls (Tyger's Whisper, Panam — Strength
Through Family, Chrome Reverie with a min Gig, T-Bug's DEFEATED, Radioport). A solo'd Legend still
counts as face-up (FAQ). *Counters:* a solo'd Legend removed from the game no longer counts, and
Adam Smasher — Ender of Legends' PLAY ("Defeat a rival Unit") reaches one on the field; so does any
fight it loses while spent.

**The counters, listed once.** Removal by power: Bonnie and Clyde (≤4, two if two Gigs behind),
Minotaur (≤5 with more cred), Over the Edge (≤ a friendly d20's face), Royce — Don't Call Me Simon
(≤2, ≤3 with more cred), Carnage at the Colosseum (less power than a friendly Unit), Adam Smasher —
Metal Over Meat ("Defeat all other Units"). Removal by cost: Caliber (≤2), Gilded Matón (≤3, for
a Gear), Corporate Surveillance (spend ≤4), Overwatch (≤ the discarded card's cost). Spent-gated:
Wild in the Streets, Unlikely Bond, Don't Fear the Reaper, Overwatch. Bottom-deck: the six above.
Replacement shields: Deadman Transmitter ("If this Unit would be defeated, defeat its DEADMAN
TRANSMITTER instead"), Jackie Welles — Mama's Favorite (pay 1 €$, remove her instead), Muamar
Reyes' CALL, Reboot Optics. Anti-steal: Chrome Fang, Westbrook Netrunner, Alt — Mother of Daemons,
Take Control. Anti-attack: Chrome Reverie, Nocturne, MaxTac Suppression Team, Memory Relapse,
Pacifica Netrunner, and the forced attacks of Mox Inciters and Evelyn — Beautiful Enigma's spend
("A rival Unit must attack next turn if it can"). Blockers and their bypasses: chapter 5. Fight
tricks: Floor It, Synapse Burnout, Safety Override, Reboot Optics, Cyberpsychosis, Dum Dum, Goro —
Vengeful Bodyguard, Rogue — Queen of the Afterlife, Muamar, Wakako, Dexter — Off the Grid, Japantown
Jonin, Gunpoint Diplomacy. Gear removal: Detonate, Heywood Ripperdoc.

**Context.** The same card is two cards: MaxTac Heavy is a 1-drop against a wide board and a
7-drop against one Unit; Detonate is dead against a deck with no Gear; Take Control cantrips only
against machines; Bonnie and Clyde, Nadia, Adrenaline Converter and We Gotta Live Together switch
off when you steal back; Towerfall sweeps when behind on cred and debuffs when ahead; Chrome
Reverie is a turn of tempo against one big attacker and nothing against three small ones; Johnny —
Never Stop Fighting is defined by the rival's CORPO count; El Sombrerón is 4 power without a max
Gig and 16 to 24 with a maxed d12 or d20.

**The mistake.** Building an engine with no answer in mind, and playing an answer with no engine
in front of it. Detonate in hand against a Gear-less deck is a Sell.

**The numbers.** The cards our simple player plays least often when it holds them, as a share of
the games it drew them: Chrome Reverie 3.6%, Appetite for Destruction 5.9%, Unlikely Bond 8.4%,
Cyberpsychosis 8.4%, Safety Override 10.2%, Reboot Optics 11.6%, Gunpoint Diplomacy 12.4%, We Gotta
Live Together 12.5%, Take Control 14.6%, Adam Smasher — Metal Over Meat 15.4%. Eight of the ten are
answers or setups whose value is off the board. The search player, on a probe of four of them, played
Adam Smasher — Metal Over Meat more (29% against 20%) and Bootleg Black Sapphire Show far less (2%
against 13%); the QUICKs it played about as rarely.

**What this means for your deck.** Name your engine, then count the six bottom-deckers, the two
Gear killers, the eleven Blockers, the seven QUICKs and the five anti-attack cards the rival could
be holding against it, and decide how many of them your colours let *them* run. Then name the
engines you expect to meet, and give yourself two answers to each — one on the board and one in
the window.

---

## 10. Deck building

### 10a. The Legend decision comes first, and it is a constraint, not a resource

Three Legends with unique names. Each brings 2 RAM of its own colour, and "each Legend's RAM only
counts toward its own color". RAM is never spent; it is a ceiling: a card is legal in your deck only
if its RAM is at or below your total in its colour. So your triple is not three cards; it is a
choice of which slice of the 124 main-deck cards you are allowed to see at all.

The arithmetic (computed over every card and every legal triple):

| colour class | Legends | caps | main-deck cards you may run | share of legal triples |
|---|---|---|---:|---:|
| mono | three of one colour | 6 in it, 0 elsewhere | **31** | 4% |
| two-plus-one | two of one, one of another | 4 and 2 | **51 to 54** | 54% |
| one-of-each | three colours | 2, 2 and 2 | **65 to 67** | 42% |

There are 31 main-deck cards in each colour. Exactly two cards need three Legends of one colour:
Judy Álvarez — Nothing to Doubt (Blue, RAM 5: "1 €$, ⊡: Reveal the top card of your deck. You may
play it for free. Otherwise, add it to your hand") and Adam Smasher — Metal Over Meat (Yellow, RAM
6: "PLAY: Defeat all other Units", 15 power for 9). Thirty-four cards need two Legends of their
colour (RAM 3 or 4), among them Overwatch, Safety Override, Sandevistan, Deadman Transmitter,
Gorilla Arms, The Relic, Adrenaline Converter, Panam Palmer — Strength Through Family, Riding
Nomad, Wild in the Streets, Les Élémens, Towerfall, Pyramid Song, Three Mouths, Maman Brigitte,
Delamain, MTOD12 Flathead, Octant, El Sombrerón, Animals Wrecker, Alt Cunningham — Mother of
Daemons, Carnage at the Colosseum, Appetite for Destruction, Bonnie and Clyde, Gunpoint Diplomacy,
Fool on the Hill, MaxTac Heavy, MaxTac Squadron, Goro — Losing His Way and Yorinobu — Steel Dragon
(Minotaur, by contrast, is RAM 2). The other ninety are RAM 1 or 2 and need one Legend of their
colour.

What each class trades. **Mono** sees the deepest cards (the two RAM-5/6 cards, every RAM-3/4 card
of its colour) and the smallest pool: thirty-one cards for forty slots means at least nine cards
are three-ofs and every card in the colour is in the deck whether it fits the plan or not. **Two-
plus-one** is the natural class: the whole of one colour plus the shallow half of another, fifty-odd
cards, room to leave the weak ones out. **One-of-each** is breadth with a cap of 2 everywhere: no
RAM-3/4 card at all, sixty-five choices for forty slots, three CALL or QUICK Legends from three
colours, and a reaction suite the rival can never fully rule out. There are 2,528 legal triples
over the 26 usable Legends (Rebecca — Having a Moment has no revealed text and is excluded from
everything we do). Our rated field so far is twenty decks: ten mono, ten two-plus-one, and **not
one one-of-each deck** — the class that holds 42% of all triples has never been rated by us. Almost
none of the Legend space has been explored, and the largest class of it not at all.

### 10b. Coherence versus variety

A 40-card list "does something" when most of its cards read the same instant of the same board.
The build-arounds are chapter 9's families: an ARASAKA list wants Saburo and the 9-power bodies and
Radioport; a Gear list wants Royce or Dum Dum or Cyberpsychosis and the two Viktors and a Legend to
hang Netdriver on; a dice list wants one package from chapter 7 and two adjusters that reach its
own dice; a trash list wants Screw, The Relic, Trauma Team and the six cards that fill the trash; a
Legend-count list wants the free Calls and Berserk and Panam — Strength Through Family.

Then the counts that every list needs whatever it does:

* **The curve.** The second player has four Eddies on turn one (three Legends and a Sell), the
  first player two. A deck whose cheapest cards cost 4 does nothing for two turns. Ten cards at
  cost 1 to 2 is not too many.
* **Sell Tags.** Every non-Unit card sells; one Unit does. A deck's sellable count is its economy
  and its reaction budget. Twelve to eighteen sellables is the range our better lists sit in
  (Embracing Power has 17 non-Units of 40; The Heist 17; the samples 12 to 18).
* **Blockers.** Eleven exist; a deck with none has no defence except QUICKs. Two to four.
* **Dead cards.** Count how many of your cards do nothing against a given opponent: Detonate
  against no Gear, Take Control's draw against no machines, Synapse Burnout with your Legends face-
  down, Bonnie and Clyde against a field of 6-power bodies, Johnny — Never Stop Fighting's second
  line against no CORPO. A card that is dead against a third of the field is a Sell a third of the
  time, and that may be fine, but you should know it.
* **The three name clashes.** V — Corporate Exile (Blue) and V — Streetkid (Red); Goro Takemura —
  Hands Unclean and Goro — Vengeful Bodyguard (both Green); Jackie Welles — Pour One Out For Me
  (Blue) and Jackie — Mama's Favorite (Green). A deck may not repeat a name, so each pair is an
  either/or, and the two Goros are the only pair in one colour: a mono-Green deck cannot run both.

Why forty cards. The minimum is 40 and the maximum 50, and every card above forty dilutes the
three-ofs you built the deck around. Deck-out is not a reason to go bigger: at thirteen cards drawn
by the Overtime boundary, a forty-card deck without self-trashing has twenty-seven left. Go to
fifty only when the deck's plan is to trash itself for value and needs the fuel.

In our own play-tested lists the cards that most raised the win rate of the decks they were drawn
in (chapter 10e explains the measure and its limits) are unglamorous bodies with an angle:
Swordwise Huscle (+12.8 points), Maman Brigitte (+12.2), Valentino Guerrera (+10.9), Animals
Wrecker (+10.6), Mox Inciters (+11.3), Kerry Eurodyne — The Last Rockerboy (+10.2). The cards that
most lowered it are the ones whose value is off the board and that our simple player plays badly:
Modded Kusanagi (−10.0), Misty Olszewski (−7.9), Alt Cunningham — Mother of Daemons (−7.2), Heywood
Ripperdoc (−6.9), Sandevistan (−6.7), Panam — Strength Through Family (−6.6), Appetite for
Destruction (−6.5). Read the second list as "hard to play", not "bad".

### 10c. Your deck is also information

Chapter 6 from the other chair. A card you play is a proof about your Legends, and the proof is
worth more to the rival than the card sometimes is to you.

* A **mono** deck shows the *least* per card early and the *most* at once: every card you play
  proves one Legend of that colour and nothing else, until a RAM-3/4 card proves two and a RAM-5/6
  card proves all three. Judy — Nothing to Doubt or Adam Smasher — Metal Over Meat on the table is
  the whole decklist's colour class announced. Until then the rival cannot rule out a second
  colour and must respect QUICKs you cannot have.
* A **two-plus-one** deck is fixed the moment a RAM-3/4 card of the major colour and any card of
  the minor colour have both been seen: from then on the rival knows the pool exactly, fifty-odd
  cards minus what they have seen.
* A **one-of-each** deck is fixed after one card of each colour, and that usually happens by turn
  three. But what it fixes is a cap of 2 everywhere, and the cap-2 pool contains six of the seven
  QUICK Programs (all but Safety Override), so the rival learns your colours and still cannot rule
  out much.

Which Legends to keep face-down: the one whose colour you have not yet shown, because a Call
reveals a colour as surely as a card does, and the one whose CALL you want in the reaction window.
Which RAM to show first: a RAM-3/4 card on turn one tells the rival which two of your Legends share
a colour and therefore which QUICKs you cannot hold on their turn; a RAM-1 card of the same colour
tells them almost nothing. If the RAM-3 card is not the play that wins the turn, play the RAM-1
one. And the Sell: sell the card whose colour is already proven.

### 10d. What the games say

We rated twenty decks (twelve frozen benchmark lists, the six sample lists, the two retail starters)
in two full round robins, 190 pairs, under two different players: the simple one-ply player, 40
games a pair, and the search player at budget 32, 20 games a pair. Two facts came back, and they
disagree with each other.

**Under the simple player the format looked like rock-paper-scissors.** The residual after fitting
a straight ranking (Bradley–Terry) was larger than a transitive field would produce (RMS 0.089
against a permutation null of 0.069, p < 0.001), and the equilibrium mixture put weight on three
decks: a Red mono list (panel-3-b, 54%), a Yellow mono list (panel-5-b, 38%) and another Red mono
list (panel-0-b, 8%). Three decks that each beat one of the others.

**Under the search player one deck dominated.** The residual was still above the null (0.109
against 0.095, p < 0.001), but the equilibrium put 99.9% of its weight on panel-5-b, the Yellow
mono list; the field is a hierarchy with cycles in the middle that do not reach the top.

**And the two players disagreed about the ranking:** Spearman 0.59 between the two ratings, with
a bootstrap interval of [0.17, 0.85] over the twenty decks. The top five under the simple player
were Sample Gangers, panel-5-b, panel-0-b, panel-5-a and panel-2-a; under the search player
panel-0-b, panel-5-b, Embracing Power, panel-5-a and The Heist.

Two readings, and we cannot yet tell you which is true. The first: the game *is* rock-paper-
scissors and the search player is simply not strong enough to play the counter-decks well, so the
cycles collapse into whatever the search is good at. The second: the game *is* a hierarchy and the
simple player's fixed habits (always the biggest die, never a block until the last die, always
Call first) are what created the cycles, which a real player erases. A third round robin under a
stronger player will separate them, and until then we report both.

**"This deck wins" versus "this player played it well."** They are hard to separate because every
game is a deck *and* a player, and a rating is a rating under a player. We separate them three
ways. The same deck under two different players: a deck strong under both is strong; a deck strong
under one only is **player-dependent**, and we say so rather than "good". Mirrored matches with
the decks swapped: when two players are compared, every seed is played from both seats and with
the deck assignments exchanged, so the deck term cancels. And the paired Legend-swap test (10e),
which changes one card and replays the same seeds against the same field, so only that card moves.

Player-dependent, by our two round robins: **Sample Gangers** (first under the simple player at
0.69 of games won; fifteenth under the search at 0.38), **panel-2-a** (fifth, then thirteenth),
**Sample Corpos** the other way (fourteenth at 0.37, then sixth at 0.62), **Sample Nomads**
(0.37, then 0.51). Strong under both: **panel-5-b** (second and second), **panel-0-b** (third and
first), **panel-5-a** (fourth and fourth), **Embracing Power** (sixth and third). Weak under both:
Sample Fixers, Sample Netrunners, panel-4-a, panel-4-b, panel-0-a.

### 10e. Per-card evidence

**In-deck win-rate difference (IWD).** For a card, over every game in which it was in a list: the
share of games won when it was drawn, minus the share won when it was in the deck but never drawn.
In plain terms, "does having this card in hand make you win more, across every context it
appeared in?" It is shrunk toward zero by evidence (a card seen ten times says almost nothing), and
it has two limits that matter: a card in a bad deck looks bad whatever it does, and draw order is
confounded with game length (a card drawn late was drawn in a long game). It is a prior, not a
verdict. Our store holds 28,400 play-test games and every one of the 150 usable cards; the top and
bottom of it are in 10b. All of it is under the simple player.

**Legends have no IWD at all**, by construction: a Legend is never "drawn", so there is no
not-drawn arm to difference against. What a Legend has is a win rate when played, which is a fact
about the decks it was in (the six Yellow Legends came back at 56 to 62% and the six Blue ones at
28 to 32%, in blocks, because each block is the same few decks). The instrument that works is the
**paired Legend swap**: play a deck against a fixed field on fixed seeds, replace exactly one
Legend with one that keeps the deck legal, replay the same seeds against the same field, and count
only the games exactly one version won. The median swap is discordant in 11.8% of its games; the
pairing removes the rest.

What we measured (eight decks, 24 slots, 131 legal swaps, 100 seeds × 3 opponents × 2 seats, the
simple player; 52 swaps significant at p < 0.05; the median swap costs 1.3 points, which is what
deliberately built decks should show):

* **Saburo Arasaka — Stubborn Patriarch** out of an ARASAKA sample list: −18.5 to −19.7 points
  against each of the four legal replacements (Hanako — Daughter of the Emperor, Padre, Panam —
  Nomad Cavalry, Jackie — Mama's Favorite), p < 0.001 on all four. Out of the Embracing Power
  starter: −8.8 to −12.9. The largest single-card effect we have measured. (Measured before our
  engine's fix that made his aura reach a Legend played with GO SOLO, so it will be re-run.)
* **Goro Takemura — Hands Unclean is an upgrade three decks are not taking**: +6.7 into Sample
  Fixers over Kerry Eurodyne — Axe, Attitude, Audience, +5.0 into the same deck over Muamar Reyes,
  +4.1 into Sample Corpos over Hanako, +5.8 into the ARASAKA list over Padre. A 5-cost 7-power
  BLOCKER with GO SOLO is worth more than a modal CALL to a one-ply player, at least.
* **Evelyn Parker — Beautiful Enigma** out of Sample Fixers for V — Corporate Exile: +7.2; for Judy
  — Braindance Maestro: +4.2; for Jackie — Pour One Out For Me: +3.8. Evelyn's economy needs CORPO
  or GANGER stealers and the Fixers list has three.
* **V — Corporate Exile** out of The Heist: −7.0 (Wakako), −5.6 (Evelyn), −5.2 (Alt), −4.8 (Judy),
  −3.9 (Sasha). The naive win-rate-when-played had implied thirty points; the gap between six and
  thirty is the confound, measured.
* **Jackie Welles — Mama's Favorite** out of Sample Nomads for Dexter — Off the Grid: −9.6; Panam —
  Nomad Cavalry for Dexter: −7.8; Padre for Dexter: −5.5. Dexter's +2 does not fit a deck built to
  ready its own Units.
* **Yorinobu — Embracing Destruction** out of Embracing Power: −4.1 to −6.4 against every
  replacement; **Goro — Hands Unclean** for his namesake Vengeful Bodyguard in the same deck: −6.9.

**Cards no agent has meaningfully played.** In 10,000 search-agent games every one of the 150 usable
cards was played at least 27 times, so nothing is at zero; but the least-played are the ones whose
value the machine cannot see: Appetite for Destruction (27 plays), Gunpoint Diplomacy (30), Bootleg
Black Sapphire Show (43), Chrome Reverie (52), Shattered Memories (56), The Relic (64), Deadman
Transmitter (66), Maelstrom Zealots and Memory Relapse (76), Unlikely Bond (83). Three of those ten
(Chrome Reverie, Appetite, Shattered Memories) are load-bearing in solved positions of our suite.
For these cards the per-card evidence is thin and biased toward the machine's blind spots, and the
IWD numbers in 10b should be read with that in mind. The plain (non-GO SOLO) play of a costed
Legend, and the declines on Panam — Strength Through Family and Shattered Memories, have never been
taken by any of our agents at all.

### 10f. How our system builds decks, and what it will produce

The deck lab keeps a **population of decks with names** that persists across training: it starts
from the twenty rated lists, and every generation of the learning loop re-rates it under the new
player, proposes one single-card improvement per deck by a paired swap test against a uniform
field, admits a candidate only when it beats that field by a margin, and retires the weakest member
under *both* players rather than the weakest under one. A **bandit over Legend triples** proposes
new triples by colour class, so the one-of-each class that has never been rated gets its trial. An
**exposure floor** builds lists around the cards with the fewest games each generation, so nothing
is written off before a competent player has tried it. An **archive** keeps every deck that ever
existed with its record; nothing is forgotten.

The rating is **plain Bradley–Terry with a bootstrap interval**, under each player, because a
ranking is defined whether or not the field cycles. The Nash mixture is computed and reported as a
diagnostic of cycling, and it becomes a weight only if cycling is confirmed under the strong player
for two generations running. What a reader will eventually be able to look up: a ranked list of
decks with intervals under each player; the full matchup table with its cycles marked; per-card
evidence (IWD in context, and the paired swap results) and per-Legend evidence (the swap table);
and a list of Legend triples ranked by how well their best deck did, with the untried ones marked
untried.

The honest caveat: a deck rated by our machine is rated by our machine's play, and chapter 12 lists
the things it does not yet do that a good human does. A deck whose plan needs a held Call, a bluffed
Eddie or a two-turn setup will be under-rated until the player learns those; the "player-dependent"
list is where that shows up first.

### 10g. Starting points

The two retail starters are held out of all our training (the deck sampler refuses to generate
them), so their ratings are clean; the six sample lists are the hand-built decks people actually
see. Each with what it is built to do and what beat it, from the matchup tables (win rates over 40
games a pair under the simple player, 20 under the search).

**Embracing Power** (starter; Goro Takemura — Hands Unclean, Yorinobu Arasaka — Embracing
Destruction, Saburo Arasaka — Stubborn Patriarch; Green 4, Red 2). The ARASAKA deck: Saburo's +1
while attacking, Yorinobu's draw on the first ARASAKA attack, Minotaur and MaxTac AV as the big
bodies, three Satori for draws on won fights, three Sandevistan, three Corpo Security to hold the
dice, Corporate Surveillance to turn Blockers sideways, Radioport to Call for free. Sixth under the
simple player (won 65% of its games) and third under the search (73%); a deck strong under both.
It lost to the Yellow mono list panel-5-b and the Red mono list panel-5-a (22% and 28% under the
simple player) and to the Red mono list panel-0-b (35% under the search), which are the decks with
the biggest removal and the fastest steals. Nothing in it stops a 10-power attacker except a Block.

**The Heist** (starter; V — Corporate Exile, Viktor Vektor — Sit Down and Relax, Jackie Welles —
Pour One Out For Me; Blue 4, Yellow 2). The Gear deck: three each of Kiroshi Optics, Mandibular
Upgrade and Zetatech Faceplate, Viktor's CALL to find two of them, Dying Night for V, Delamain Cab
and Evelyn Parker — Scheming Siren as cheap stealers, Floor It and Reboot Optics as the QUICKs,
Flathead as the unblockable finisher. Ninth under the simple player (54%), fifth under the search
(62%). Sample Gangers beat it 78% of the time under the simple player (Detonate and Heywood are not
in Gangers, but Chrome Fang and eleven-power bodies are); the three mono lists at the top of the
table beat it under the search. Its Gear are all power 2 or less, so Detonate is its nightmare.

**Sample Corpos** (Hanako — Daughter of the Emperor, Sasha Yakovleva, V — Corporate Exile; Blue 4,
Green 2). Cheap CORPO bodies, three Les Élémens to bottom-deck the rival's weakest, three MaxTac AV
to swap dice, three Dying Night for V, Peace Offering for Hanako's pairs. Fourteenth under the
simple player (37%), sixth under the search (62%): player-dependent, upward. Sample Gangers and
panel-2-a took 93% of games from it under the simple player; the search found what the swaps and
bottom-decks are for.

**Sample Fixers** (Muamar Reyes, Kerry — Axe, Attitude, Audience, Evelyn — Beautiful Enigma; Yellow
4, Blue 2). Three Rockn' Rockerboy and three Rogue Amendiares — Queen of the Afterlife as the
engine, Dexter — One Last Chance and Afterparty to shape dice for Kerry's draws, Augmented
Negotiators and Mandibular Upgrade and Secondhand Bombus and Lizzy Wizzy as a wall of Blockers.
Weak under both players (36%, 31%); the swap test says it would rather have Goro — Hands Unclean
or V — Corporate Exile than two of its Legends. Sample Gangers beat it 95 games in 100.

**Sample Gangers** (Royce — Psycho on the Edge, Johnny Silverhand — Rocking Renegade, Wakako Okada;
Red 4, Blue 2). El Sombrerón and Valentino Guerrera and Chrome Fang, three Gunpoint Diplomacy and
three Appetite for Destruction, Mox Inciters and Rita Wheeler and La Llorona as Blockers, Mantis
Blades for Royce. First under the simple player (69%), fifteenth under the search (38%): the most
player-dependent deck we have. Under the search it lost every game to panel-5-a and 95 in 100 to
Embracing Power. The simple player's fixed habits are what Gangers punishes; a player who blocks
and orders attacks takes that away.

**Sample Netrunners** (Alt — Soulkiller Architect, Judy — Braindance Maestro, Jackie — Pour One Out
For Me; mono Blue). The BRAINDANCE deck: Chrome Reverie, Three Mouths, Trust No One, Pyramid Song,
Judy — Nothing to Doubt (the RAM-5 card only a mono deck can run), Placide and Maman Brigitte as
Program-fed removal, Westbrook Netrunner and Netdriver. Weak under both (41%, 24%), and last under
the search. Its plan is the one our machines play worst (chapter 12): Chrome Reverie is the card the
simple player plays least of any in the set.

**Sample Nomads** (Panam — Nomad Cavalry, Padre, Jackie — Mama's Favorite; mono Green). Saul Bright
and Riding Nomad and Wraith Marauders, Sandevistan and Riot Shield for Panam's five-equipped ready,
Synapse Burnout as the QUICK, We Gotta Live Together to rebuild, Tyger's Whisper to Call free.
Fourteenth under the simple player (37%), tenth under the search (51%): player-dependent, upward.

**Sample Ripperdocs** (Viktor — Sit Down and Relax, Dum Dum, River Ward; mono Yellow). Both Viktors,
Heywood Ripperdoc, three Safety Override (the QUICK only a two-Yellow deck can run), The Heist to
dig for Gear, MaxTac Suppression Team, Kiroshi and Mandibular for River Ward to play free in the
window. Middle under both (52%, 48%). Embracing Power beat it 95 in 100 under the search.

What the eight have in common: not one is one-of-each, and only two of the eight (Fixers, Corpos)
run more than one QUICK. The decks that beat them under the search are the two Red mono lists and
the Yellow mono list, which are the decks with the deepest removal. That is a fact about the search
player as much as about the decks, and 10d says how we will find out which.

---

## 11. Worked positions

Eight puzzles from the suite and two deck-building questions. Every board here is a verified
position: an exhaustive search proved the line wins, the simple player fails it on every seed, and
random play wins it at most a quarter of the time. Dice are written as *die: face*. In each, decide
what you would do before reading the answer. You are player one unless the puzzle says otherwise.

### Puzzle 1 — the blank body (steal-threshold-jonin-pump)

Turn 9, your main phase. Your Gig area: d4: 1, d6: 4, d8: 7, d10: 2, d12: 9 (five Gigs; only the
d20 left in your fixer). Two Eddies ready. On your field: Heywood Ripperdoc, ready, 8 power. In
hand: Japantown Jonin (cost 2, 0 power, "PLAY: Give a friendly Unit +2 power this turn"). Your
three Legends are face-down. The rival has three Gigs (d4: 6, d6: 1, d8: 8), one Eddie, no Units.

*What do you do?*

The attack steals one Gig at 8 power: six, and the rival's turn to answer. The line is to play the
Jonin **first**, a 0-power Unit that enters with Lag and could never steal anything, and put its +2
on the Ripperdoc: 8 becomes 10, and 10 steals two. Five plus two is seven, and the win check fires
at the start of your next turn. The whole position is the difference between 9 and 10, supplied by
a card worth nothing on the board until the attack reads it. The simple player attacks first and
plays the Jonin afterwards, where the +2 lands on a spent Unit and is gone.

### Puzzle 2 — the smaller die (dice-even-die-for-jackie)

Turn 9. Your Gigs: d4: 3, d6: 5, d8: 7, d10: 9, all odd. One Eddie; every Legend spent. On the
field, both ready: Jackie Welles — Ride or Die Choom (8 power; "ATTACK: Give this Unit +2 power
this turn for each friendly Gig with an even value") and Rockn' Rockerboy (8). The rival's Gigs:
d12: 11, d10: 9, d8: 7, d6: 2. No rival Units.

*Which Unit attacks first, and which die does it take?*

Either Unit steals one at 8; the natural pick is the 11 for the Street Cred. The line is: Rockerboy
first, and it steals the **d6 showing 2**, the smallest die on the table. Now one friendly Gig is
even, Jackie attacks at 10 and steals two. Four plus one plus two is seven. Jackie first steals
nothing extra whichever die she takes, because her trigger reads the Gig area when she attacks,
before her own steal lands.

### Puzzle 3 — lower your own die (race-dying-night-drops-my-cred)

Turn 13, your fixer is empty. Your Gigs: d4: 1, d6: 1, d8: 2, d10: 2, d12: 3, d20: 4 (six; Street
Cred 13). Two Eddies; Legends all face-up and spent. Field, both ready: MTOD12 Flathead (7 power,
"If you have less ★ than a Rival, this Unit can't be blocked") and Ruthless Lowlife (4 power, "can
only attack rival Units") wearing Dying Night ("ATTACK: Decrease a Gig by up to 2"). The rival:
one Gig, a d12 showing 12 (Street Cred 12), a ready Corpo Security (2 power, BLOCKER, "can't
attack") and a spent Sketchy Ripper (0 power).

*How do you take the seventh Gig?*

Flathead into the Gig area is blocked: 13 is not less than 12, Corpo Security redirects, the guard
dies and the die stays. The line: the Lowlife attacks the spent Sketchy Ripper (a fight that wins
nothing), and Dying Night's ATTACK lowers **your own d20 from 4 to 2**. Street Cred 11 is less than
12; Flathead cannot be blocked; it takes the d12 as the seventh. Two Street Cred thrown away and a
fight against a 0-power Unit, and the position hinges on both.

### Puzzle 4 — bait the reaction (play-around-take-control-bait-the-drone)

Turn 11. Your Gigs: d4: 3, d6: 4, d8: 6, d10: 7 (four). Two Eddies. Field, both ready: Animals
Wrecker (10 power) and Octant (8 power, DRONE). The rival: three Gigs (d4: 2, d6: 5, d8: 3), two
Eddies ready, all three Legends face-up (a Green deck), a spent Tyger's Whisper, and two cards in
hand — you should assume one is Take Control ("QUICK: A rival Unit steals 1 fewer Gig this turn. If
that Unit is an AI, DRONE, or VEHICLE, draw 1"), which their colours allow.

*In what order do you attack?*

Wrecker first takes two of three; the rival, still holding a die, lets it through. Octant then comes
for the last one, that is an emergency, and Take Control lands on the DRONE for the card: Octant
steals nothing, six. The line sends **Octant first**: one Gig, the smaller swing, no reaction. Then
the Wrecker comes for the last two, the rival must react now, and its Take Control still chases the
DRONE for the card — a DRONE that has already attacked. The Wrecker takes both. Seven.

### Puzzle 5 — the block that kills (defend-safety-override-kills-johnny)

Turn 10, the rival's turn; you are defending. Your Gigs: d4: 1, d6: 6, d10: 4, d12: 8. Two Eddies
ready; all three Legends spent face-down. Your field: Augmented Negotiators (2 power, BLOCKER). In
hand: Safety Override ("QUICK: The next time a friendly Unit loses a fight this turn, defeat the
opposing rival Unit"), The Heist, Gilded Matón. The rival has six Gigs and attacks your Gig area
with Johnny Silverhand — Never Stop Fighting (8 power; "The first time this Unit wins a fight each
turn, ready it"); a Swordwise Huscle beside him is lagged.

*The reaction window is open. What do you do?*

A plain Block loses: the Negotiators die, Johnny wins his first fight, readies, and attacks again
into an empty board for the seventh. Passing hands him the seventh now. The line: play Safety
Override, then Block. The Negotiators lose the fight, Johnny readies — and is defeated in the same
fight by the Override. The Gig stays, the attacker is gone. Two Eddies, exactly what you had. The
simple player spends one of them Calling a face-down Legend at the first window and can then afford
nothing.

### Puzzle 6 — a family the machine cannot solve (gig-shaping-odd-cred-lets-the-guard-wake)

Turn 15 (Overtime is close but not here). Your Gigs: d4: 1, d6: 3, d8: 5, d10: 3, d12: 6, and a
stolen d6: 3 — six Gigs, Street Cred 21. Five Eddies; Legends spent. Field: Emergency Atlus,
ready, 4 power. In hand: Pacifica Netrunner (cost 4, 1 power; "PLAY: If your ★ is an even number, a
rival Unit can't ready until your next turn") and Trust No One (cost 1; "Decrease a Gig by up to 3.
Then, if you control a min Gig, draw 1"). The rival: three Gigs (d8: 4, d10: 6, d12: 8), a spent
Rockn' Rockerboy (8 power), two Eddies.

*The seventh Gig is one attack away. What do you do?*

Attack and you are on seven; the Rockerboy readies at the start of their turn, takes one back, and
your check finds six. Pacifica would stop him, but 21 is odd, and every rival die is even, so any
steal leaves you odd. The line: Trust No One on **your own d6, 3 down to 2** (one Street Cred and a
card, for nothing visible); Street Cred 20 is even; play Pacifica naming the Rockerboy; then attack
for the seventh. He never wakes. No machine player we have solves any of the nine gig-shaping
positions: the value of a pip on your own die is invisible to a board score, and the search's one-
ply proposals never suggest it.

### Puzzle 7 — the worst-looking play on the menu (removal-first-bonnie-clears-corpo-security)

Turn 9. Your Gigs: d4: 3, d6: 5, d8: 2, d10: 9, and two stolen dice, d4: 1 and d6: 6 (six). Four
Eddies. Field: Animals Wrecker, ready, 10 power. Hand: Bonnie and Clyde (cost 3; "Defeat a rival
Unit with power 4 or less"), Ruthless Lowlife, Swordwise Huscle. The rival: two Gigs (d8: 4, d10:
6), one Eddie, a ready Corpo Security (2 power, BLOCKER, cannot attack).

*What do you do?*

The Wrecker steals two, which is everything the rival has — if it reaches the Gig area. Corpo
Security redirects, the Wrecker kills a 2-power Unit that could never have attacked, and the turn
is over on six. The line: Bonnie and Clyde on Corpo Security **first**, three Eddies and a card to
remove a threat that does not exist, and then the Wrecker walks into an empty field for both dice.
Eight. The simple player's preview answers every reaction with a pass, so it never sees the block
coming; a human who leads with the swing is making the same assumption.

### Puzzle 8 — trade your own Unit (recursion-trade-relic-into-kusanagi)

Turn 17; your fixer is empty but the rival's is not, so Overtime has not begun. Your Gigs: d4: 3, d6: 5, d8: 2, d10: 7, d12: 9 (five). Two
Eddies; Legends face-up and spent. Field: Maelstrom Goons (3 power) wearing The Relic (+3; "DEFEATED:
Play another Unit with cost 9 or less from your trash for free. Then, bottom-deck this Unit"), so 6
power. Hand: Zetatech Faceplate (cost 2, +2), Hanako Arasaka — In a Gilded Cage, Bootleg Black
Sapphire Show. Trash: Modded Kusanagi (cost 6, 8 power, ADRENALINE, returns to hand at end of turn),
Psycho Squad, Misty, Kiroshi Optics. The rival: four Gigs (d4: 2, d6: 4, d8: 6, d20: 11), one Eddie,
a spent Maelstrom Zealots (0 power; "When this Unit loses a fight, defeat the opposing rival Unit")
and a spent Corpo Security.

*What do you do?*

Six power steals one: six Gigs, no die left to make seven. The line: attack the **spent Zealots**.
Your Goons win a fight against 0 power, Zealots' text defeats the Goons anyway, both hit the trash,
and you have stolen nothing. Then The Relic's DEFEATED plays Modded Kusanagi from your trash for
free; ADRENALINE lets it attack the turn it lands; Zetatech Faceplate for two Eddies makes it 10;
and 10 steals two: seven, on a board the rival cannot take one back from before your check. Every
move before the last is worse
on the board than the greedy steal, and the simple player takes the single Gig on all twenty seeds.

### Puzzle 9 — build the forty (two-plus-one)

The triple: Saburo Arasaka — Stubborn Patriarch (Green), Goro Takemura — Hands Unclean (Green),
Yorinobu Arasaka — Embracing Destruction (Red). Green cap 4, Red cap 2. The pool is all thirty-one
Green cards and the twenty-two Red cards of RAM 1 or 2: fifty-three choices for forty slots.

*Build the deck, and say why.*

The engine is ARASAKA: Saburo's "+1 power while attacking", Yorinobu's "The first time a friendly
ARASAKA Unit attacks each turn, draw 1. Then, if you have less than 20 ★, discard 1". So the
attackers are ARASAKA and want to sit on 9: Minotaur (7 for 9, "PLAY: If you have more ★ than a
Rival, defeat a rival Unit with power 5 or less" — Red, RAM 2, legal), Sandayu Oda (8, spends a
rival Unit per value-pair), Goro — Losing His Way (4, +5 with all Legends face-up; Green RAM 3,
legal), Field Operator as the cheap body. Satori ("When this Unit wins a fight against a rival
Unit, draw 1"; ARASAKA, Red RAM 1) and Radioport ("look at a friendly face-down Legend. If that
Legend is ARASAKA or has GO SOLO, you may Call it for free"; Red RAM 2) are the Gear: every Legend
in the triple is ARASAKA or has GO SOLO, so Radioport's free Call always fires. Corporate
Surveillance turns Blockers sideways for the 10-power swings. Corpo Security holds your dice. Over
the Edge (Red RAM 2) is the answer to a big body once the d20 is in. Industrial Assembly (Red RAM 1)
pushes a die toward Yorinobu's 20-cred clause; Octant, which would want the same 8+ faces, is Red
RAM 4 and illegal under this triple, which is the kind of thing the pool decides for you. What the
class has done: this is the Embracing Power starter, sixth and third in our two round robins, and
its Saburo is the single most valuable Legend we have measured (10e). What beats it: the mono lists
with the deepest removal, because it runs no QUICK at all and no anti-attack card; add Synapse
Burnout (Green RAM 1), Take Control (Green RAM 2) or Detonate (Red RAM 2), all of which the pool
allows and the starter does not run.

### Puzzle 10 — build the forty (one-of-each)

The triple: Dexter DeShawn — Off the Grid (Red), Muamar Reyes — El Capitán (Yellow), Wakako Okada —
Peace and Harmony (Blue). Caps 2, 2 and 2; sixty-seven cards, no RAM-3 or RAM-4 card at all. Three
fixers, three modal CALLs ("+2 power / Draw 1", "can't be defeated in a fight / Draw 1", "-2 power
to a rival Unit / Draw 1"), and three spend-icons that move dice (+2, ±1, −2).

*Build the deck, and say why.*

The Legends are a dice deck's toolkit and a defender's: every one of the three Calls is worth
holding for the reaction window (chapter 3), and between them they can push, pull and set almost
any face. The payoffs the pool allows: Jackie Welles — Ride or Die Choom (Yellow RAM 2; +2 per even
friendly Gig on attack), Rockn' Rockerboy (8 for 5), Kerry Eurodyne — The Last Rockerboy (Red RAM 1;
"⊡: If you control a Gig with 8+ value, draw 2"), 6th Street Recruits (Red RAM 1; +6 on a stolen
d6), Valentino Guerrera and Chrome Fang for the Street Cred games, Afterparty at Lizzie's and
Industrial Assembly and Trust No One as the cheap adjusters. The reactions the pool allows: Floor
It and Reboot Optics (Blue), Detonate (Red), Cyberpsychosis (Yellow); Safety Override is RAM 3 and
out. Blockers: La Llorona (Red RAM 1; "+3 to a Gig when it blocks"), Meredith Stout (Red RAM 1;
punishes their adjusts), Mox Inciters and Rita Wheeler (Blue), Augmented Negotiators and Secondhand
Bombus (Yellow), Mandibular Upgrade. Cheap Gear for the 10-power line: Mantis Blades, Kiroshi Optics,
Zetatech Faceplate. What this class has done in our games: **nothing — we have never rated a
one-of-each deck**, and this is the honest answer to the question. Its information profile (10c)
is the best in the game: the rival learns your three colours by turn three and still cannot rule
out four QUICKs. Its weakness is structural: no card above RAM 2, so no Overwatch, no Relic, no
Gorilla Arms, no Animals Wrecker, no MaxTac Heavy, and the biggest body it can run is Minotaur,
Johnny — Never Stop Fighting or Modded Kusanagi at 8 to 9. It is the deck our exposure floor and
Legend bandit will try first, because it is the class with no evidence.

---

## 12. What the bot taught us

Short, and only the things we learned by watching a machine play badly.

1. **The board lies about setups.** A one-ply player that scores the board after every move attacks
   first in all 132 of our solved positions and wins none of them. Every winning line has at least
   one move — a Jonin, a Call, a pip on your own die, a Gear on the attacker — that is worth
   nothing until the attack reads it. If your instinct is to attack first, that is the instinct of
   a machine we know loses.
2. **The Gear that wins gets sold.** The simple player sells the card that would have made the
   attack, one move after attacking, in five separate positions. Sell first, and sell the card whose
   cost you will never reach.
3. **Blocking only for the last die is a tell you can be attacked around forever.** Our simple
   player does exactly that, and every play-around position exploits it. A defender's habits are
   information.
4. **Calling at the first window costs the Eddie the real answer needed.** Nine of thirteen defend
   positions are lost on that one habit.
5. **The biggest die is not the default.** With our evaluator as judge, the biggest die was the
   best roll only 41% of the time; the search player, which does search the roll, has no fixer plan
   at all (the five dice come out in near-random order over 80,000 decisions).
6. **The machine has never gone first, never played a Legend without GO SOLO, and never declined
   Panam's discard or Shattered Memories' draw.** Those are holes in our evidence, not advice; a
   strong player should treat each as unexplored.
7. **Payment is a decision.** Fourteen percent of payments spent a Legend with something to lose
   while another source stood ready. The rules always gave the choice; the machine only just got it.
8. **A Legend's win rate is a fact about its deck.** The paired swap test found Saburo worth
   nineteen points in the right list and the raw win-rate-when-played had hidden it in a block of
   identical numbers; V — Corporate Exile's raw thirty points were six once paired.
9. **Two players disagree about which decks are good** (rank correlation 0.59), and the
   disagreement is largest for the decks whose plan needs a habit the weak player lacks. A deck
   rating is a rating under a player.
10. **Knowing the rival's list was worth nothing to our search** (0.9 points, inside noise), and
    knowing their hand beat the honest version 44.6% of the time. We suspect that is because the
    machine cannot yet *act* on what it knows: it does not hold Eddies to bluff, does not order
    attacks to draw out a QUICK it has inferred, and does not sell to hide a colour. Chapter 6 is
    the part of this book a strong human is furthest ahead of the machine on.

---

## Maintenance

*Last updated: 2026-09-21.* Sections 7, 10d, 10e, 10f, 10g, 11 and 12 are refreshed at every
milestone as measurements land; the rest changes only when the rules do. Sources for the numbers:
`docs/stage0.md` (kill tests and baselines), `out/s0/kt2/*/tournament.json` (round robins),
`out/legend_swap.json` (Legend swaps), `data/strategy/knowledge.json` and `measured.json` (IWD and
play rates), `out/s1/baselines/coverage_s10k.md` (what the search agent did in 10,000 games),
`data/arena/delayed.json` (the solved positions).

### Changelog

* 2026-09-21 — first edition. Rules and engine as of the four owner rulings of 21 September (E1–E12
  and rulings 048–057 landed; no rule changes pending). Measurements: Stage 0 day-0 baselines, the
  two kill-test-2 round robins, the 10,000-game search corpus, the 28,400-game play-test store, the
  131-swap Legend test. Open: the KT1 rerun (card identity in the value head) had not reported when
  this edition was written; nothing in the guide depends on its verdict.
