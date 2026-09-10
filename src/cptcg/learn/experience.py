"""What the AI did: the training data, and the archival record of the reasoning behind it.

**Replays plus search output, never features.** A game is fully determined by
``(ruleset digest, decklists, seed, action indices)``, so ``sim.record.Replay`` already stores a
whole game as an action list of a few bytes per decision, and ``Replay.steps(reg, cfg)`` re-yields
the exact ``(state, action index)`` pair for every decision it held. Anything computed *from* a
state — the feature vector, the legal move list, the labels — is recomputable offline for free,
and storing it would only be a second copy that can drift from the engine that made it. Features
also change shape whenever ``learn/features.py`` changes; a replay does not, so a replay written
today still trains a model designed next year.

What is **not** recomputable is what the search was thinking: which moves it spent its iterations
on, and what it thought the position was worth. That is the policy training target and the only
thing search produces that the engine cannot reproduce, so that is exactly what is written
alongside the replay:

* ``visits`` — per decision, one byte per legal option, the search's visit counts normalised so
  that the most-visited option is 255. See :func:`quantise_visits`.
* ``values`` — per decision, one byte, the search's win probability **for the player to move at
  that decision**, times 255.

Both are optional. A record with neither is a plain game log — which is what the cheap bootstrap
generation writes today, since no search agent exists yet — and it is still a full value-training
example, because the value label comes from who won (:func:`outcome`), not from the search.

Storage
-------
One JSON object per line (JSONL), gzip if the path ends in ``.gz``. Appendable, so a session can
add to a generation it did not start: ``write_games(path, more)`` opens in append mode, and
because gzip members concatenate, an appended ``.gz`` reads back as one continuous stream.

Every record carries ``rules``, the ``RulesConfig.digest()`` under which it was played.
:func:`read_games` refuses a record from a different ruleset rather than letting a changed ruling
silently poison a training set — the same protection ``Replay.steps`` applies at replay time.

The schema, field by field with units and quantisation, is in ``docs/learning.md``.

Size and retention
------------------
:func:`size_stats` measures a real file. Measured over 100 heuristic self-play games (136
decisions each, six legal options per decision): 12.6 bytes per decision without search output and
26.1 with it, which is 1.7 and 3.5 KB per game, falling to 1.8 and 8.0 bytes per decision gzipped.
Ten thousand searched games is therefore about 35 MB, 11 MB gzipped.

**Retention policy for this repository: keep the most recent generations, prune older ones.**
Experience is regenerable — the seed and the decklists reproduce it exactly — while trained
weights are not, so weights are kept forever and old experience is deleted once the generation
that learned from it has been gated.
"""

from __future__ import annotations

import base64
import gzip
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from cptcg.cards.registry import Registry
from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.core.state import GameState
from cptcg.sim.record import Replay

#: Bumped when the on-disk shape changes incompatibly. Reading refuses anything else.
FORMAT = 1

#: Everything quantised here is a byte: 0..255 inclusive.
QMAX = 255


# ------------------------------------------------------------------ quantisation
def quantise_visits(counts: Sequence[float]) -> list[int]:
    """Visit counts to one byte per option, normalised so the most-visited option is 255.

    Normalising by the **maximum** rather than by the sum keeps the search's choice exactly: the
    argmax is always the byte 255, whatever the iteration budget was, and a distribution is
    recovered with :func:`visit_policy`. The absolute number of iterations is lost, which is why
    ``GameRecord.sims`` records it once for the whole game.

    Rounding is half-up so that the byte is a plain nearest-value rounding rather than Python's
    round-half-to-even, which would make the table awkward to reproduce in another language.
    """
    m = max(counts) if counts else 0
    if m <= 0:
        return [0] * len(counts)
    return [int(c * QMAX / m + 0.5) for c in counts]


def visit_policy(visits: Sequence[int]) -> list[float]:
    """Quantised visit bytes back to a probability distribution over the legal options."""
    total = sum(visits)
    if total <= 0:
        n = len(visits)
        return [1.0 / n] * n if n else []
    return [v / total for v in visits]


def quantise_value(v: float) -> int:
    """A win probability in [0, 1] to one byte. Values outside the range are clipped."""
    return int(min(1.0, max(0.0, v)) * QMAX + 0.5)


def dequantise_value(b: int) -> float:
    """The inverse of :func:`quantise_value`, to within 1/510."""
    return b / QMAX


def _pack(xs: Sequence[int]) -> str:
    return base64.b64encode(bytes(xs)).decode("ascii")


def _unpack(s: str) -> list[int]:
    return list(base64.b64decode(s.encode("ascii")))


# ------------------------------------------------------------------ the record
@dataclass
class GameRecord:
    """One stored game: a replay, plus whatever the search reported while playing it.

    ``visits`` and ``values`` hold the **quantised bytes**, not the raw counts, so a record is the
    file's contents in memory and a round trip through JSON is exact. Use
    :meth:`GameRecord.from_replay` to build one from raw search output; it quantises for you.
    """

    seed: int
    decks: tuple[dict, dict]           # serialised Decklists, exactly as sim.record.Replay has them
    actions: list[int]                 # the chosen option index at each decision, in order
    rules: str = DEFAULT_CONFIG.digest()        # the ruleset this game was played under
    agents: tuple[str, str] = ("?", "?")
    winner: int | None = None
    end_reason: str | None = None
    turns: int | None = None
    #: Per decision, one byte per legal option (see :func:`quantise_visits`). An **empty list**
    #: means that decision was not searched. ``None`` means the whole game carries no search output.
    visits: list[list[int]] | None = None
    #: Per decision, one byte: the search's win probability for the player to move. All-or-nothing.
    values: list[int] | None = None
    #: Search iterations per decision, if the search ran a fixed budget. Documentation for the
    #: visit bytes, which are scale-free.
    sims: int | None = None
    format: int = FORMAT
    meta: dict = field(default_factory=dict)    # free-form: generation number, sampler mix, ...

    # --- construction -------------------------------------------------------
    @classmethod
    def from_replay(cls, rep: Replay, *, visits: Sequence[Sequence[float]] | None = None,
                    values: Sequence[float] | None = None, sims: int | None = None,
                    meta: dict | None = None) -> "GameRecord":
        """Wrap a finished :class:`~cptcg.sim.record.Replay`, quantising raw search output.

        ``visits`` takes **raw** counts, one list per decision, each as long as that decision's
        legal option list; an empty list marks a decision the search skipped. ``values`` takes raw
        win probabilities in [0, 1], one per decision, for the player to move there.
        """
        n = len(rep.actions)
        qv = None
        if visits is not None:
            if len(visits) != n:
                raise ValueError(f"visits has {len(visits)} entries, the game had {n} decisions")
            qv = [quantise_visits(v) for v in visits]
        qval = None
        if values is not None:
            if len(values) != n:
                raise ValueError(f"values has {len(values)} entries, the game had {n} decisions")
            qval = [quantise_value(v) for v in values]
        return cls(seed=rep.seed, decks=(dict(rep.decks[0]), dict(rep.decks[1])),
                   actions=list(rep.actions), rules=rep.rules, agents=tuple(rep.agents),
                   winner=rep.winner, end_reason=rep.end_reason, turns=rep.turns,
                   visits=qv, values=qval, sims=sims, meta=dict(meta or {}))

    def replay(self) -> Replay:
        """The replay this record wraps: the same game, without the search output."""
        return Replay(seed=self.seed, decks=(dict(self.decks[0]), dict(self.decks[1])),
                      actions=list(self.actions), rules=self.rules, agents=tuple(self.agents),
                      winner=self.winner, end_reason=self.end_reason, turns=self.turns)

    @property
    def n_decisions(self) -> int:
        return len(self.actions)

    # --- serialisation ------------------------------------------------------
    def to_json(self) -> dict:
        d: dict = {"format": self.format, "rules": self.rules, "seed": self.seed,
                   "decks": [dict(self.decks[0]), dict(self.decks[1])],
                   "agents": list(self.agents), "actions": list(self.actions),
                   "winner": self.winner, "end_reason": self.end_reason, "turns": self.turns,
                   "visits": None if self.visits is None else [_pack(v) for v in self.visits],
                   "values": None if self.values is None else _pack(self.values),
                   "sims": self.sims}
        if self.meta:
            d["meta"] = self.meta
        return d

    @classmethod
    def from_json(cls, d: dict, *, rules: str | None = None, where: str = "") -> "GameRecord":
        """Parse one record. ``rules``, when given, is the digest the caller demands.

        A record from another ruleset is a *different game*, and mixing one into a training set
        would be invisible in the loss curve, so this is an error rather than a warning.
        """
        fmt = d.get("format")
        if fmt != FORMAT:
            raise ValueError(f"{where}experience format {fmt!r}, this build reads {FORMAT}")
        got = d.get("rules")
        if rules is not None and got != rules:
            raise ValueError(
                f"{where}record was played under ruleset {got}, this build is {rules}. A ruling "
                f"changed, so the two are not the same game: regenerate the experience, or read it "
                f"with the matching RulesConfig.")
        visits = d.get("visits")
        values = d.get("values")
        return cls(seed=d["seed"], decks=(dict(d["decks"][0]), dict(d["decks"][1])),
                   actions=list(d["actions"]), rules=got, agents=tuple(d.get("agents", ("?", "?"))),
                   winner=d.get("winner"), end_reason=d.get("end_reason"), turns=d.get("turns"),
                   visits=None if visits is None else [_unpack(v) for v in visits],
                   values=None if values is None else _unpack(values),
                   sims=d.get("sims"), format=fmt, meta=dict(d.get("meta", {})))


# ------------------------------------------------------------------ files
def _open(path: str | Path, mode: str):
    p = str(path)
    if p.endswith(".gz"):
        return gzip.open(p, mode + "t", encoding="utf-8")
    return open(p, mode, encoding="utf-8")


def write_games(path: str | Path, records: Iterable[GameRecord], *, append: bool = True) -> int:
    """Write records as JSONL, gzipped when ``path`` ends in ``.gz``. Returns the count written.

    Appending is the default so that a chunked session adds to the generation it is filling. A
    gzip append writes a second member; ``read_games`` (and ``gzip`` generally) reads concatenated
    members as one stream, so the file stays valid.
    """
    n = 0
    with _open(path, "a" if append else "w") as f:
        for r in records:
            f.write(json.dumps(r.to_json(), separators=(",", ":")))
            f.write("\n")
            n += 1
    return n


def read_games(path: str | Path, *,
               rules: str | None = DEFAULT_CONFIG.digest()) -> Iterator[GameRecord]:
    """Yield records from a JSONL(.gz) file, refusing any played under another ruleset.

    ``rules`` is the digest to demand; pass ``None`` to read whatever is there (for a forensic
    look at an old file, never for training).
    """
    with _open(path, "r") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            yield GameRecord.from_json(json.loads(line), rules=rules,
                                       where=f"{path}:{lineno}: ")


# ------------------------------------------------------------------ back to examples
def replay_features(record: GameRecord, reg: Registry, cfg: RulesConfig = DEFAULT_CONFIG
                    ) -> Iterator[tuple[GameState, int, list[int] | None, float | None]]:
    """Turn a stored game back into training examples: the one obvious way.

    Yields ``(state, chosen, visits, value)`` once per decision, in order:

    * ``state`` — the live ``GameState`` at that decision, with ``state.pending`` holding the
      legal options. It is the *same object* every time, mutated forward by the engine, so read
      what you need (``features(state, state.pending.player)``, say) before asking for the next
      item; keep it only by cloning.
    * ``chosen`` — the option index the agent took, an index into ``state.pending.options``.
    * ``visits`` — the quantised visit bytes over those options, or ``None`` if this game (or this
      decision) carried no search output. :func:`visit_policy` makes it a distribution.
    * ``value`` — the search's win probability for ``state.pending.player``, or ``None``.

    The value *label* for training is not here: it is :func:`outcome`, which is who eventually won,
    because a value head must be fitted to the future rather than to the search's guess about it.

    Raises ``ValueError`` if the ruleset digest disagrees (from ``Replay.steps``) or if a stored
    visit row is not as wide as the legal option list it claims to describe — which would mean the
    file and the engine no longer agree about what was legal, and every example after it is
    misaligned.
    """
    rep = record.replay()
    for i, (s, idx) in enumerate(rep.steps(reg, cfg)):
        if idx is None:
            break
        v = None
        if record.visits is not None and record.visits[i]:
            v = record.visits[i]
            if len(v) != len(s.pending.options):
                raise ValueError(
                    f"decision {i}: {len(v)} stored visit counts but "
                    f"{len(s.pending.options)} legal "
                    f"options — the record and the engine disagree about this position")
        val = None if record.values is None else dequantise_value(record.values[i])
        yield s, idx, v, val


def outcome(record: GameRecord, player: int) -> float:
    """The value label: 1.0 if ``player`` won this game, 0.0 if they lost, 0.5 if nobody did."""
    if record.winner is None:
        return 0.5
    return 1.0 if record.winner == player else 0.0


# ------------------------------------------------------------------ the size budget
def size_stats(path: str | Path) -> dict:
    """Measure a real experience file against the storage budget.

    Returns games, decisions, bytes on disk, bytes gzipped (the file itself if it is already
    gzipped, otherwise what it would compress to), and both per decision and per game. This is the
    number to quote in ``docs/learning.md`` when the retention policy is reviewed.
    """
    raw = 0
    games = decisions = searched = 0
    for r in read_games(path, rules=None):
        games += 1
        decisions += r.n_decisions
        if r.visits is not None:
            searched += 1
    with _open(path, "r") as f:
        for line in f:
            raw += len(line.encode("utf-8"))
    disk = os.path.getsize(path)
    gz = disk if str(path).endswith(".gz") else len(gzip.compress(Path(path).read_bytes(), 6))
    d = max(1, decisions)
    g = max(1, games)
    return {"path": str(path), "games": games, "decisions": decisions, "with_search": searched,
            "bytes": raw, "disk_bytes": disk, "gz_bytes": gz,
            "bytes_per_decision": raw / d, "gz_bytes_per_decision": gz / d,
            "bytes_per_game": raw / g, "gz_bytes_per_game": gz / g,
            "decisions_per_game": decisions / g}


def format_size_stats(st: dict) -> str:
    """The one-paragraph human form of :func:`size_stats`."""
    return (f"{st['path']}: {st['games']} games, {st['decisions']} decisions "
            f"({st['decisions_per_game']:.1f} per game, "
            f"{st['with_search']} games with search output)\n"
            f"  {st['bytes_per_decision']:.1f} bytes/decision, "
            f"{st['bytes_per_game']:.0f} bytes/game uncompressed\n"
            f"  {st['gz_bytes_per_decision']:.1f} bytes/decision, "
            f"{st['gz_bytes_per_game']:.0f} bytes/game gzipped "
            f"({st['gz_bytes'] / 1024:.1f} KB total)")
