"""Token view of a position for the card-aware model (unified design, layer A).

Every card instance the observer may identify is a token; hidden instances are not (they enter
through the belief counts below and the 114 aggregates). Each die in either Gig area and each
fixer die is a token. The choice being made and the attack in flight are a small context vector.
Belief inputs are computed from public evidence only (``learn.opponent``): per card, how many
copies the rival could still be holding in hand or deck, and which face-down Legends are
possible.

Everything here is plain ints and floats in tuples, pure stdlib, so it runs inside harvest
workers and inside the package; ``tools/`` turns it into arrays and feeds torch or numpy.

Token layouts (indices are documented once, here, and the digest pins them):

  card token   (card_idx, zone, owner_rel, spent, lag, faceup, go_solo, gear_power, n_gear,
                known_to_rival, host_is_legend, in_hand_playable)
  die token    (owner_rel, sides, face, is_min, is_max, is_even, is_8plus, in_pair, in_fixer)
  context      (choice_kind, tag_class, attack_live, attacker_card_idx, target_kind, redirects,
                gig_steal_allowed, unblockable, mover_is_active, turn, overtime)
  option token (card_idx, kind_idx, submode_idx, pick_class_idx) + the 52 action features
"""

from __future__ import annotations

import hashlib

from cptcg.core.actions import Choice
from cptcg.core.enums import F_GO_SOLO, NO_INST, NZONE, CardType, Zone
from cptcg.core.legal import play_cost
from cptcg.core.ops import available
from cptcg.core.state import GameState
from cptcg.core.view import knows_identity
from cptcg.learn.coverage import _pick_vals, option_key
from cptcg.learn.opponent import colour_bounds, possible_pool
from cptcg.learn.policy import action_features

CARD_TOKEN = ("card_idx", "zone", "owner_rel", "spent", "lag", "faceup", "go_solo", "gear_power",
              "n_gear", "known_to_rival", "host_is_legend", "in_hand_playable")
DIE_TOKEN = ("owner_rel", "sides", "face", "is_min", "is_max", "is_even", "is_8plus", "in_pair", "in_fixer")
CONTEXT = ("choice_kind", "tag_class", "attack_live", "attacker_card_idx", "target_kind", "redirects",
           "gig_steal_allowed", "unblockable", "mover_is_active", "turn", "overtime")
OPTION_TOKEN = ("card_idx", "kind_idx", "submode_idx", "pick_class_idx")

#: Action kinds and sub-modes are small vocabularies; unknown strings map to 0.
KIND_VOCAB = ("", "EndTurn", "Pass", "Sell", "Play", "GoSolo", "CallLegend", "Activate", "Attack",
              "Target", "Block", "GigDie", "Mulligan", "Order", "Pick")
SUBMODE_VOCAB = ("", "gear:unit", "gear:legend", "quick", "keyword", "plain", "reaction", "main",
                 "ab0", "ab1", "ab0:quick", "ab1:quick", "gig", "unit", "d4", "d6", "d8", "d10", "d12",
                 "d20", "keep", "mulligan", "first", "second")
PICK_VOCAB = ("", "decline", "die", "trigger", "index", "yes", "card", "amount", "adjust:up",
              "adjust:down", "tuple", "type")
TAG_CLASSES = ("", "steal", "order", "adjust_gig", "equip", "call_free", "effect")


def tokens_digest() -> str:
    text = "\n".join(("|".join(CARD_TOKEN), "|".join(DIE_TOKEN), "|".join(CONTEXT), "|".join(OPTION_TOKEN),
                      "|".join(KIND_VOCAB), "|".join(SUBMODE_VOCAB), "|".join(PICK_VOCAB), "|".join(TAG_CLASSES)))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def card_tokens(s: GameState, me: int) -> list[tuple]:
    """One token per instance ``me`` may identify, in instance order."""
    out = []
    defs = s.reg.defs
    i_card, i_zone, i_owner = s.i_card, s.i_zone, s.i_owner
    avail = available(s, me)
    gear_of: dict[int, list[int]] = {}
    for inst in range(len(i_card)):
        h = s.i_host[inst]
        if h != NO_INST:
            gear_of.setdefault(h, []).append(inst)
    rival = 1 - me
    from cptcg.core.enums import F_FACEDOWN
    for inst in range(len(i_card)):
        zone = i_zone[inst]
        if i_owner[inst] == me and (zone == Zone.DECK or (zone == Zone.EDDIES and s.i_flags[inst] & F_FACEDOWN)):
            # My own undrawn cards: the multiset is mine to know even though the order is not, and
            # a set of tokens carries no order. A card I sold unseen (F_FACEDOWN) belongs to that
            # same multiset and is tokenised as undrawn, so a determinization that swaps it with a
            # deck card leaves the token set unchanged.
            zone = Zone.DECK
        elif not knows_identity(s, me, inst):
            continue
        d = defs[i_card[inst]]
        gp = 0
        gs = gear_of.get(inst, ())
        for g in gs:
            gp += defs[i_card[g]].power or 0
        h = s.i_host[inst]
        host_is_legend = 1 if (h != NO_INST and defs[i_card[h]].type is CardType.LEGEND) else 0
        playable = 0
        if zone == Zone.HAND and i_owner[inst] == me and d.type is not CardType.LEGEND:
            playable = 1 if play_cost(s, me, inst) <= avail else 0
        out.append((d.idx, int(zone), 0 if i_owner[inst] == me else 1, int(s.i_spent[inst]),
                    int(s.i_lag[inst]), int(s.i_faceup[inst]), 1 if s.i_flags[inst] & F_GO_SOLO else 0,
                    gp, len(gs), 1 if knows_identity(s, rival, inst) else 0, host_is_legend, playable))
    return out


def die_tokens(s: GameState, me: int) -> list[tuple]:
    out = []
    for p in (me, 1 - me):
        rel = 0 if p == me else 1
        vals = [v for _k, v in s.gig[p]]
        for sides, v in s.gig[p]:
            out.append((rel, sides, v, 1 if v == 1 else 0, 1 if v == sides else 0, 1 if v % 2 == 0 else 0,
                        1 if v >= 8 else 0, 1 if vals.count(v) > 1 else 0, 0))
        for sides in s.fixer[p]:
            out.append((rel, sides, 0, 0, 0, 0, 0, 0, 1))
    return out


def _tag_class(tag: str) -> int:
    if not tag:
        return 0
    if tag.endswith("@steal"):
        return 1
    if tag.endswith("@order"):
        return 2
    if "adjust_gig" in tag:
        return 3
    if tag.endswith("@equip"):
        return 4
    if tag.endswith("@call_free"):
        return 5
    return 6


def context(s: GameState, me: int, ch: Choice) -> tuple:
    atk = s.atk
    live = 1 if atk is not None and not atk.fizzled else 0
    return (int(ch.kind), _tag_class(ch.tag or ""), live,
            s.reg.defs[s.i_card[atk.attacker]].idx if live else -1,
            atk.target_kind if live else -1, atk.redirects if live else 0,
            1 if (live and atk.gig_steal_allowed) else 0, 1 if (live and atk.unblockable) else 0,
            1 if s.active == me else 0, s.turn, 1 if s.overtime else 0)


def belief(s: GameState, me: int) -> tuple[list[int], list[int]]:
    """Public-evidence beliefs about the rival (no sampler, no population prior):

    ``deck``: per non-Legend card of the pool (in registry order), the number of copies the rival
    could still hold in hand or deck — 3 minus the copies already seen, and 0 outside their
    possible pool (``opponent.possible_pool`` from the colour bounds). ``legends``: per Legend,
    1 if it could be one of their face-down slots (colour possible, not already face-up or seen).
    """
    reg = s.reg
    rival = 1 - me
    bounds = colour_bounds(s, me)
    pool = possible_pool(reg, bounds)
    seen: dict[int, int] = {}
    for inst in range(len(s.i_card)):
        if s.i_owner[inst] == rival and knows_identity(s, me, inst):
            seen[s.i_card[inst]] = seen.get(s.i_card[inst], 0) + 1
    deck, legends = [], []
    from cptcg.learn.opponent import max_ram
    caps = max_ram(bounds)
    for d in reg.defs:
        if d.type is CardType.LEGEND:
            possible = caps[d.color] >= d.ram and seen.get(d.idx, 0) == 0
            legends.append(1 if possible else 0)
        else:
            n = 3 - seen.get(d.idx, 0) if d.id in pool else 0
            deck.append(max(0, n))
    return deck, legends


def option_tokens(s: GameState, me: int, ch: Choice) -> list[tuple]:
    """Per legal option: ``(card_idx, kind_idx, submode_idx, pick_class_idx)`` plus the 52 action
    features, with the option's card identity read only if ``me`` may (the 'unknown card' flag of
    the action features covers the rest)."""
    vals = _pick_vals(ch) if ch.kind.name == "PICK" else None
    out = []
    for a in ch.options:
        cid, kind, sub = option_key(s, ch, a, vals)
        card_idx = -1
        inst = getattr(a, "inst", None)
        if cid is not None:
            d = s.reg.get(cid)
            if inst is None or inst < 0 or knows_identity(s, me, inst):
                card_idx = d.idx
        pick_class = 0
        if kind == "Pick":
            pick_class = PICK_VOCAB.index(sub) if sub in PICK_VOCAB else 0
            sub = ""
        head = (card_idx, KIND_VOCAB.index(kind) if kind in KIND_VOCAB else 0,
                SUBMODE_VOCAB.index(sub) if sub in SUBMODE_VOCAB else 0, pick_class)
        out.append(head + tuple(action_features(s, me, a)))
    return out


def decision_tokens(s: GameState, me: int, ch: Choice) -> dict:
    """Everything the card-aware model reads for one decision, as plain tuples."""
    from cptcg.learn.features import features
    deck, legs = belief(s, me)
    return {"cards": card_tokens(s, me), "dice": die_tokens(s, me), "context": context(s, me, ch),
            "aggregates": tuple(features(s, me)), "belief_deck": deck, "belief_legends": legs,
            "options": option_tokens(s, me, ch)}
