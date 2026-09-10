"""What a position looks like to the player to move: the value model's input.

``features(s, me)`` turns a live ``GameState`` into a fixed-length tuple of floats. It is a
*description*, not a score — no weights, no opinion about which way is good. ``FEATURE_NAMES``
names the entries in order and ``FEATURE_SCALING`` records what each one was divided by, so a
reader never has to reverse-engineer a magic constant. Every entry lands in [0, 1], except the
handful of signed differences which land in [-1, 1]; both are clipped, so a feature can never
run away and a small network trains without per-feature normalisation.

Why the deck is in here
-----------------------
The board alone cannot say whether a plan is reachable. A hand of two expensive Units is a
disaster from a cheap deck and a normal draw from a top-heavy one, and "hold this Gig for one
more turn" only makes sense if the outs are still in the deck. So a third of the vector describes
**the list you were handed**: its curve, type mix and sell-tag density, what of it is still
undrawn, the RAM your Legends unlock, and your hand measured against that list rather than
against nothing.

What it reads, and nothing else
-------------------------------
Only what ``me`` may legitimately see at the table. Card *identities* (``i_card``) are read for:

* every instance ``me`` owns — your own list is yours to know. The identities of your own DECK
  are read as an **unordered multiset** only (bucket counts): the deck's *order* is never
  touched, which is what makes future draws unknown.
* the rival's FIELD, EDDIES (public as a multiset once sold, ruling 002), TRASH and REMOVED, and
  any face-up Legend.

Never read: the rival's HAND or DECK contents, the identity behind a face-down Legend slot on
either side, and the order of any DECK. Permuting those disturbs no feature, which
``tests/learn/test_features.py`` checks directly against a permuted state.

Other per-instance fields read (all public): ``i_owner``, ``i_zone``, ``i_spent``, ``i_faceup``,
``i_host``, ``i_lag``. Scalars read: ``turn``, ``turns_taken``, ``active``, ``first_player``,
``overtime``, ``empty_starts``, ``pending.player``, ``gig``, ``fixer``, and zone lengths.
``i_known`` is deliberately *not* read: a Legend identity learned by looking is real knowledge,
but it lands in the same bucket sums as the rest of your triple, so the vector cannot leak it.

``core/view.py`` is the authoritative mask, and this module agrees with it by construction rather
than by import — it stays a tight loop over arrays with no per-call set building. The precise
relation is that every feature here is a function of ``view.info_key(s, me)``: your own deck
enters that key as ``my_pool``, a *sorted multiset* of card indices, which is exactly what the
bucket counts below summarise. That is why ``view.determinize`` — which resamples every identity
you may not see — cannot move a single entry, and why ``view.redact`` (which blanks your deck's
identities along with everyone else's) is deliberately *not* the right instrument for this vector.

Cost
----
One pass over your own instances (about 45), one over each public zone, and one ``power()`` and
``has_keyword()`` per Unit in play. No intermediate lists are built per call. This is called
millions of times in self-play, so keep it that way.
"""

from __future__ import annotations

from cptcg.core.enums import NO_INST, NZONE, CardType, Color, Keyword, Zone
from cptcg.core.ops import ATTACKING, _active, has_keyword, play_cost, power, steal_count
from cptcg.core.state import GameState

_DECK, _HAND, _FIELD, _EDDIES, _TRASH, _LEGENDS, _REMOVED = (
    Zone.DECK, Zone.HAND, Zone.FIELD, Zone.EDDIES, Zone.TRASH, Zone.LEGENDS, Zone.REMOVED)
_UNIT, _PROGRAM, _GEAR, _LEGEND = CardType.UNIT, CardType.PROGRAM, CardType.GEAR, CardType.LEGEND
_BLOCKER = Keyword.BLOCKER
_NCOLOR = len(Color)

# Scale denominators. Each is a "generous typical maximum", not a hard bound: the clip below
# turns the rare over-run into a saturated 1.0 rather than an outlier that skews training.
S_TURN = 30.0          # games end around turn 20; 30 leaves headroom for Overtime
S_GIGS = 7.0           # cfg.gigs_to_win
S_CRED = 70.0          # 7 Gigs averaging 10 pips
S_DIE = 20.0           # the biggest die
S_FIXER = 6.0          # len(DICE)
S_EDDIES = 12.0
S_POWER = 60.0         # total Unit power on one side
S_UNIT_POWER = 15.0    # the biggest printed power in the pool
S_UNITS = 8.0
S_BLOCKERS = 4.0
S_GEAR = 6.0
S_DECK = 50.0          # cfg.deck_max
S_HAND = 10.0
S_TRASH = 30.0
S_REMOVED = 8.0
S_RAM = 6.0            # three Legends of one colour, 2 RAM each
S_COST = 7.0           # cost buckets run 1..7+
NCOST = 7

# (name, what it is divided by / how it is scaled). The order here *is* the vector order.
_SPEC = (
    # --- clock and phase ------------------------------------------------------------------
    ("turn", "turn number / 30"),
    ("turns_taken_me", "my completed turns / 15"),
    ("my_turn", "1 if it is my turn"),
    ("to_move_me", "1 if the pending choice is mine"),
    ("first_player_me", "1 if I went first"),
    ("overtime", "1 in Overtime"),
    ("empty_fixer_me", "1 once I have begun a turn with an empty fixer area"),
    ("empty_fixer_rival", "1 once the rival has"),
    # --- the win condition ----------------------------------------------------------------
    ("gigs_me", "my Gigs / 7"),
    ("gigs_rival", "rival Gigs / 7"),
    ("gigs_diff", "(mine - theirs) / 7, signed"),
    ("to_seven_me", "(7 - mine) / 7"),
    ("to_seven_rival", "(7 - theirs) / 7"),
    ("at_six_me", "1 if I am one Gig from the win"),
    ("at_six_rival", "1 if the rival is"),
    ("cred_me", "my Street Cred / 70"),
    ("cred_rival", "rival Street Cred / 70"),
    ("cred_diff", "(mine - theirs) / 70, signed"),
    ("gig_mean_me", "my mean Gig value / 20"),
    ("gig_mean_rival", "rival mean Gig value / 20"),
    ("gig_max_me", "my biggest Gig value / 20"),
    ("gig_min_me", "my smallest Gig value / 20"),
    ("gig_even_me", "share of my Gigs with an even value"),
    ("gig_even_rival", "share of rival Gigs with an even value"),
    # --- the fixer area -------------------------------------------------------------------
    ("fixer_left_me", "my unrolled dice / 6"),
    ("fixer_left_rival", "rival unrolled dice / 6"),
    ("fixer_best_me", "sides of my biggest unrolled die / 20"),
    ("fixer_best_rival", "sides of the rival's biggest / 20"),
    # --- economy --------------------------------------------------------------------------
    ("eddies_me", "cards in my Eddies area / 12"),
    ("eddies_rival", "cards in the rival's Eddies area / 12"),
    ("ready_eddies_me", "€$ I can pay right now / 12"),
    ("ready_eddies_rival", "€$ the rival can pay right now / 12"),
    ("eddies_diff", "(mine - theirs) / 12, signed"),
    # --- the board ------------------------------------------------------------------------
    ("units_me", "my Units in play / 8"),
    ("units_rival", "rival Units in play / 8"),
    ("power_ready_me", "power of my ready Units / 60"),
    ("power_ready_rival", "power of the rival's ready Units / 60"),
    ("power_spent_me", "power of my spent Units / 60"),
    ("power_spent_rival", "power of the rival's spent Units / 60"),
    ("power_ready_diff", "(mine - theirs) ready power / 60, signed"),
    ("power_best_me", "my biggest ready Unit / 15"),
    ("power_best_rival", "the rival's biggest ready Unit / 15"),
    ("blockers_me", "my ready BLOCKERs / 4"),
    ("blockers_rival", "rival ready BLOCKERs / 4"),
    ("gear_me", "Gear attached to my Units / 6"),
    ("gear_rival", "Gear attached to rival Units / 6"),
    ("lagged_me", "my lagged Units / 4"),
    ("lagged_rival", "rival lagged Units / 4"),
    ("threat", "Gigs the rival's ready Units could steal / 7"),
    ("threat_net", "that, capped by my Gigs, less my ready BLOCKERs / 7"),
    ("steal_me", "Gigs my ready Units could steal / 7"),
    # --- zone sizes -----------------------------------------------------------------------
    ("deck_me", "my remaining deck / 50"),
    ("deck_rival", "rival remaining deck / 50"),
    ("deck_low_me", "1 if my deck is down to 5 cards or fewer"),
    ("deck_low_rival", "1 if the rival's is"),
    ("hand_me", "cards in my hand / 10"),
    ("hand_rival", "cards in the rival's hand / 10"),
    ("trash_me", "my trash / 30"),
    ("trash_rival", "rival trash / 30"),
    ("removed_me", "my removed-from-game pile / 8"),
    ("removed_rival", "rival removed-from-game pile / 8"),
    # --- Legends --------------------------------------------------------------------------
    ("legends_me", "Legends still in my Legends area / 3"),
    ("legends_rival", "Legends still in the rival's / 3"),
    ("faceup_me", "my face-up Legends / 3"),
    ("faceup_rival", "rival face-up Legends / 3"),
    ("ram_red", "Red RAM my Legends unlock / 6"),
    ("ram_green", "Green RAM my Legends unlock / 6"),
    ("ram_blue", "Blue RAM my Legends unlock / 6"),
    ("ram_yellow", "Yellow RAM my Legends unlock / 6"),
    ("legend_red", "1 if one of my Legends is Red"),
    ("legend_green", "1 if one of my Legends is Green"),
    ("legend_blue", "1 if one of my Legends is Blue"),
    ("legend_yellow", "1 if one of my Legends is Yellow"),
    # --- the list I was handed (all 40-50 main-deck cards, wherever they are now) -----------
    ("list_size", "(main-deck size - 40) / 10"),
    ("list_cost1", "share of my list costing 1 or less"),
    ("list_cost2", "share costing 2"),
    ("list_cost3", "share costing 3"),
    ("list_cost4", "share costing 4"),
    ("list_cost5", "share costing 5"),
    ("list_cost6", "share costing 6"),
    ("list_cost7", "share costing 7 or more"),
    ("list_mean_cost", "mean cost of my list / 7"),
    ("list_unit_share", "share of my list that is Units"),
    ("list_program_share", "share that is Programs"),
    ("list_gear_share", "share that is Gear"),
    ("list_sell_share", "share carrying a sell tag"),
    ("list_blocker_share", "share printed with BLOCKER"),
    ("list_unit_power", "mean printed power of the Units in my list / 15"),
    # --- what of it is still undrawn (my DECK zone, as a multiset) -------------------------
    ("undrawn_frac", "cards left in my deck / my list size"),
    ("undrawn_cost1", "share of what is left costing 1 or less"),
    ("undrawn_cost2", "share costing 2"),
    ("undrawn_cost3", "share costing 3"),
    ("undrawn_cost4", "share costing 4"),
    ("undrawn_cost5", "share costing 5"),
    ("undrawn_cost6", "share costing 6"),
    ("undrawn_cost7", "share costing 7 or more"),
    ("undrawn_mean_cost", "mean cost of what is left / 7"),
    ("undrawn_unit_share", "share of what is left that is Units"),
    ("undrawn_program_share", "share that is Programs"),
    ("undrawn_gear_share", "share that is Gear"),
    ("undrawn_sell_share", "share carrying a sell tag"),
    ("undrawn_blocker_share", "share printed with BLOCKER"),
    # --- my hand, measured against that list ------------------------------------------------
    ("hand_mean_cost", "mean cost in hand / 7"),
    ("hand_min_cost", "cheapest card in hand / 7"),
    ("hand_cheap", "cards in hand costing 2 or less / 6"),
    ("hand_sellable", "cards in hand with a sell tag / 6"),
    ("hand_playable", "cards in hand I could pay for right now / 6"),
    ("hand_playable_share", "share of my hand I could pay for right now"),
    ("hand_units", "Units in hand / 6"),
    ("hand_programs", "Programs in hand / 6"),
    ("hand_gear", "Gear in hand / 6"),
    ("hand_unit_power", "biggest printed Unit power in hand / 15"),
    ("hand_cost_vs_deck", "(mean hand cost - mean undrawn cost) / 7, signed"),
    ("hand_sell_vs_list", "hand sell-tag share - list sell-tag share, signed"),
)

FEATURE_NAMES: tuple[str, ...] = tuple(n for n, _ in _SPEC)
FEATURE_SCALING: dict[str, str] = dict(_SPEC)
NFEAT = len(_SPEC)


def _u(x: float) -> float:
    """Clip to [0, 1]."""
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _b(x: float) -> float:
    """Clip to [-1, 1]."""
    return -1.0 if x < -1.0 else (1.0 if x > 1.0 else x)


def _side(s: GameState, p: int, gear_of: dict) -> tuple:
    """Public board numbers for player ``p`` — everything here is visible to both players.

    Returns (units, ready power, spent power, best ready power, ready BLOCKERs, attached Gear,
    lagged Units, stealable Gigs, Legends in area, face-up Legends, Eddies cards, ready €$).
    The ready-€$ count mirrors ``ops.payable_sources``: ready Eddies, ready face-down Legends,
    and ready face-up Legends that carry a sell tag (CR 5.7.2.2).
    """
    base = p * NZONE
    z = s.z
    defs = s.reg.defs
    i_card = s.i_card
    i_host = s.i_host
    i_spent = s.i_spent
    i_faceup = s.i_faceup
    i_lag = s.i_lag
    units = pw_ready = pw_spent = best = 0
    blockers = gear_n = lagged = steal = 0
    for u in z[base + _FIELD]:
        if i_host[u] != NO_INST:
            continue
        d = defs[i_card[u]]
        if d.type is _GEAR:
            continue
        units += 1
        pw = power(s, u, ATTACKING)
        gear_n += len(gear_of.get(u, ()))
        if i_lag[u]:
            lagged += 1
        if i_spent[u]:
            pw_spent += pw
            continue
        pw_ready += pw
        if pw > best:
            best = pw
        steal += steal_count(pw)
        if has_keyword(s, u, _BLOCKER):
            blockers += 1
    n_leg = faceup = ready_src = 0
    for i in z[base + _LEGENDS]:
        if i_host[i] != NO_INST:
            continue
        n_leg += 1
        if i_faceup[i]:
            faceup += 1
            if not i_spent[i] and defs[i_card[i]].sell_tag:
                ready_src += 1
        elif not i_spent[i]:
            ready_src += 1
    n_edd = 0
    for i in z[base + _EDDIES]:
        n_edd += 1
        if not i_spent[i]:
            ready_src += 1
    return (units, pw_ready, pw_spent, best, blockers, gear_n, lagged, steal,
            n_leg, faceup, n_edd, ready_src)


def features(s: GameState, me: int) -> tuple[float, ...]:
    """Describe ``s`` from ``me``'s seat. See the module docstring for what is read."""
    r = 1 - me
    defs = s.reg.defs
    i_card = s.i_card
    i_owner = s.i_owner
    i_zone = s.i_zone
    z = s.z
    gear_of = _active(s)[5]

    mine = _side(s, me, gear_of)
    theirs = _side(s, r, gear_of)
    avail = mine[11]

    # ---------------------------------------------------------------- my own cards, one pass
    # "list" = the 40-50 main-deck cards I was handed, wherever they sit now; "und" = the part
    # still in my deck, as an unordered multiset; "hand" = what I am holding.
    list_n = list_cost_sum = list_sell = list_blocker = list_unit_n = list_unit_pw = 0
    und_n = und_cost_sum = und_sell = und_blocker = 0
    hand_n = hand_cost_sum = hand_sell = hand_cheap = hand_playable = hand_unit_pw = 0
    hand_min = 99
    list_cost = [0] * NCOST
    und_cost = [0] * NCOST
    list_type = [0, 0, 0]
    und_type = [0, 0, 0]
    hand_type = [0, 0, 0]
    ram = [0] * _NCOLOR
    for inst in range(len(i_card)):
        if i_owner[inst] != me:
            continue
        d = defs[i_card[inst]]
        t = d.type
        if t is _LEGEND:
            ram[d.color] += d.ram
            continue
        cost = d.cost or 0
        bucket = 0 if cost <= 1 else (NCOST - 1 if cost >= NCOST else cost - 1)
        ti = t - 1                                  # UNIT/PROGRAM/GEAR -> 0/1/2
        sell = 1 if d.sell_tag else 0
        blocker = 1 if _BLOCKER in d.keywords else 0
        list_n += 1
        list_cost[bucket] += 1
        list_cost_sum += cost
        list_type[ti] += 1
        list_sell += sell
        list_blocker += blocker
        if t is _UNIT:
            list_unit_n += 1
            list_unit_pw += d.power or 0
        zone = i_zone[inst]
        if zone == _DECK:
            und_n += 1
            und_cost[bucket] += 1
            und_cost_sum += cost
            und_type[ti] += 1
            und_sell += sell
            und_blocker += blocker
        elif zone == _HAND:
            hand_n += 1
            hand_cost_sum += cost
            hand_type[ti] += 1
            hand_sell += sell
            if cost <= 2:
                hand_cheap += 1
            if cost < hand_min:
                hand_min = cost
            if t is _UNIT and (d.power or 0) > hand_unit_pw:
                hand_unit_pw = d.power or 0
            if play_cost(s, me, inst) <= avail:
                hand_playable += 1
    if hand_min > 90:
        hand_min = 0

    # ---------------------------------------------------------------- Gigs and fixer dice
    g_me = s.gig[me]
    g_r = s.gig[r]
    n_me = len(g_me)
    n_r = len(g_r)
    cred_me = even_me = 0
    gmax = 0
    gmin = 0
    if n_me:
        gmin = 21
        for _sides, v in g_me:
            cred_me += v
            if not v & 1:
                even_me += 1
            if v > gmax:
                gmax = v
            if v < gmin:
                gmin = v
    cred_r = even_r = 0
    for _sides, v in g_r:
        cred_r += v
        if not v & 1:
            even_r += 1
    fx_me = s.fixer[me]
    fx_r = s.fixer[r]

    # ---------------------------------------------------------------- zone sizes
    b_me = me * NZONE
    b_r = r * NZONE
    deck_me = len(z[b_me + _DECK])
    deck_r = len(z[b_r + _DECK])
    hand_r = len(z[b_r + _HAND])

    # ---------------------------------------------------------------- derived denominators
    inv_list = 1.0 / list_n if list_n else 0.0
    inv_und = 1.0 / und_n if und_n else 0.0
    inv_hand = 1.0 / hand_n if hand_n else 0.0
    und_mean = und_cost_sum * inv_und
    hand_mean = hand_cost_sum * inv_hand
    list_sell_share = list_sell * inv_list
    threat = theirs[7]
    threat_net = threat if threat < n_me else n_me
    threat_net -= mine[4]

    out: list[float] = []
    add = out.append
    ext = out.extend
    # --- clock and phase
    ext((
        _u(s.turn / S_TURN),
        _u(s.turns_taken[me] / 15.0),
        1.0 if s.active == me else 0.0,
        1.0 if (s.pending is not None and s.pending.player == me) else 0.0,
        1.0 if s.first_player == me else 0.0,
        1.0 if s.overtime else 0.0,
        1.0 if (s.empty_starts >> me) & 1 else 0.0,
        1.0 if (s.empty_starts >> r) & 1 else 0.0,
    ))
    # --- the win condition
    ext((
        _u(n_me / S_GIGS),
        _u(n_r / S_GIGS),
        _b((n_me - n_r) / S_GIGS),
        _u((S_GIGS - n_me) / S_GIGS),
        _u((S_GIGS - n_r) / S_GIGS),
        1.0 if n_me >= 6 else 0.0,
        1.0 if n_r >= 6 else 0.0,
        _u(cred_me / S_CRED),
        _u(cred_r / S_CRED),
        _b((cred_me - cred_r) / S_CRED),
        _u(cred_me / (n_me * S_DIE)) if n_me else 0.0,
        _u(cred_r / (n_r * S_DIE)) if n_r else 0.0,
        _u(gmax / S_DIE),
        _u(gmin / S_DIE),
        (even_me / n_me) if n_me else 0.0,
        (even_r / n_r) if n_r else 0.0,
    ))
    # --- the fixer area
    ext((
        _u(len(fx_me) / S_FIXER),
        _u(len(fx_r) / S_FIXER),
        _u(max(fx_me) / S_DIE) if fx_me else 0.0,
        _u(max(fx_r) / S_DIE) if fx_r else 0.0,
    ))
    # --- economy
    ext((
        _u(mine[10] / S_EDDIES),
        _u(theirs[10] / S_EDDIES),
        _u(mine[11] / S_EDDIES),
        _u(theirs[11] / S_EDDIES),
        _b((mine[10] - theirs[10]) / S_EDDIES),
    ))
    # --- the board
    ext((
        _u(mine[0] / S_UNITS),
        _u(theirs[0] / S_UNITS),
        _u(mine[1] / S_POWER),
        _u(theirs[1] / S_POWER),
        _u(mine[2] / S_POWER),
        _u(theirs[2] / S_POWER),
        _b((mine[1] - theirs[1]) / S_POWER),
        _u(mine[3] / S_UNIT_POWER),
        _u(theirs[3] / S_UNIT_POWER),
        _u(mine[4] / S_BLOCKERS),
        _u(theirs[4] / S_BLOCKERS),
        _u(mine[5] / S_GEAR),
        _u(theirs[5] / S_GEAR),
        _u(mine[6] / S_BLOCKERS),
        _u(theirs[6] / S_BLOCKERS),
        _u(threat / S_GIGS),
        _u(threat_net / S_GIGS),
        _u(mine[7] / S_GIGS),
    ))
    # --- zone sizes
    ext((
        _u(deck_me / S_DECK),
        _u(deck_r / S_DECK),
        1.0 if deck_me <= 5 else 0.0,
        1.0 if deck_r <= 5 else 0.0,
        _u(hand_n / S_HAND),
        _u(hand_r / S_HAND),
        _u(len(z[b_me + _TRASH]) / S_TRASH),
        _u(len(z[b_r + _TRASH]) / S_TRASH),
        _u(len(z[b_me + _REMOVED]) / S_REMOVED),
        _u(len(z[b_r + _REMOVED]) / S_REMOVED),
    ))
    # --- Legends
    ext((
        _u(mine[8] / 3.0),
        _u(theirs[8] / 3.0),
        _u(mine[9] / 3.0),
        _u(theirs[9] / 3.0),
    ))
    for c in range(_NCOLOR):
        add(_u(ram[c] / S_RAM))
    for c in range(_NCOLOR):
        add(1.0 if ram[c] else 0.0)
    # --- the list I was handed
    add(_u((list_n - 40) / 10.0))
    for b in range(NCOST):
        add(list_cost[b] * inv_list)
    ext((
        _u(list_cost_sum * inv_list / S_COST),
        list_type[0] * inv_list,
        list_type[1] * inv_list,
        list_type[2] * inv_list,
        list_sell_share,
        list_blocker * inv_list,
        _u(list_unit_pw / (list_unit_n * S_UNIT_POWER)) if list_unit_n else 0.0,
    ))
    # --- what of it is still undrawn
    add(_u(und_n * inv_list))
    for b in range(NCOST):
        add(und_cost[b] * inv_und)
    ext((
        _u(und_mean / S_COST),
        und_type[0] * inv_und,
        und_type[1] * inv_und,
        und_type[2] * inv_und,
        und_sell * inv_und,
        und_blocker * inv_und,
    ))
    # --- my hand, measured against that list
    ext((
        _u(hand_mean / S_COST),
        _u(hand_min / S_COST),
        _u(hand_cheap / 6.0),
        _u(hand_sell / 6.0),
        _u(hand_playable / 6.0),
        hand_playable * inv_hand,
        _u(hand_type[0] / 6.0),
        _u(hand_type[1] / 6.0),
        _u(hand_type[2] / 6.0),
        _u(hand_unit_pw / S_UNIT_POWER),
        _b((hand_mean - und_mean) / S_COST) if (hand_n and und_n) else 0.0,
        _b(hand_sell * inv_hand - list_sell_share) if hand_n else 0.0,
    ))
    return tuple(out)
