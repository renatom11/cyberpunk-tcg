"""The cheap bootstrap: heuristic and random self-play turned into labelled positions, at scale.

    python tools/harvest.py play  --games N [--agent heuristic] [--agent-b NAME] [--out PATH]
                                  [--seed S] [--workers W] [--mix random=.3,heuristic=.35,...]
                                  [--resume | --fresh] [--minutes M]
    python tools/harvest.py examples --in PATH [PATH ...] --out PREFIX [--rate 0.125] [--seed S]
                                  [--workers W] [--max-games N] [--perspectives move|both]
    python tools/harvest.py compact PATH [PATH ...]
    python tools/harvest.py stats PATH [PATH ...]

Three properties are the whole point of this file.

**A fresh deck pair per game.** Every game draws its own pair from ``learn.decks.sample_pair``, so
what is learned is how to play *a* deck rather than how to play one matchup, and the two retail
starters — which ``sample_pair`` refuses to return — stay out of training entirely. The pair is a
pure function of the game index rather than of a sequential stream:

    pair_rng(seed, i)  = Pcg32((seed ^ (i * 0x9E3779B1)) & MASK64, seq=909)
    game_seed(seed, i) = (seed * 1000003 + i) & 0x7FFFFFFF

``arena.sampled_pairings`` advances one generator across games, which is right for a gate but wrong
here: it makes game *i* reachable only by drawing the *i-1* pairs before it, and that breaks both
sharding and resume. Indexing instead means a worker handed games 5000-5099 draws exactly the decks
and seeds those games would have had in any other run with the same ``--seed``. Whole-run
reproducibility, arbitrary sharding and exact resume all fall out of the one property. Each record
carries ``meta={"i": i}``.

**Replays, never features.** ``learn.experience`` stores a game as its action indices, and
``Replay.steps`` recomputes every state exactly, so ``features()`` is recomputable for free and
storing it would be a second copy that can drift from the engine that made it — and that changes
shape every time ``learn/features.py`` does. 12.6 bytes per decision raw, 1.8 gzipped.

**Resumability.** Sessions get wiped mid-run and an interrupt can tear the last line (or the last
gzip member). The data file is the bulk; the truth about how far it got is the sidecar
``<out>.harvest.json``, rewritten atomically after every chunk. ``--resume`` refuses if the seed,
the agents, the mix or the ruleset digest differ — a resume that silently mixed two distributions
would be invisible in a loss curve — then truncates the data file back to the recorded byte count,
which discards a torn tail and nothing else, and continues from the recorded game index.

Nothing under ``src/cptcg`` is touched: everything here is already importable, so the stdlib-only
rule for the browser build is satisfied by construction and ``tools/bench.py check`` cannot move.
No numpy either — harvesting is engine-bound, and the numpy half of the training split lives in the
trainer. The ``.f32`` example file is written with ``array('f').tofile`` and read with one
``numpy.fromfile``.

**What the labels are worth.** A value fitted to these games predicts the outcome *under heuristic
play*. That is a real bias, not ground truth, and it is written down beside the numbers in
``docs/learning.md`` rather than left implied.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from array import array
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.deck.decklist import Decklist  # noqa: E402
from cptcg.learn import decks as D  # noqa: E402
from cptcg.learn.experience import (GameRecord, format_size_stats, outcome, read_games,  # noqa: E402
                                    replay_features, size_stats, write_games)
from cptcg.learn.features import FEATURE_NAMES, NFEAT, features  # noqa: E402
from cptcg.sim import runner  # noqa: E402
from cptcg.sim.record import Replay  # noqa: E402

MASK64 = 0xFFFFFFFFFFFFFFFF

#: Bumped when the manifest shape changes incompatibly.
MANIFEST_FORMAT = 1

#: The extra columns after the ``NFEAT`` features, in order. ``game`` is the harvest's game index
#: and exists so a trainer can split train/val **by game, never by position**; ``ply`` is the
#: decision index within the game, for calibration by game phase.
EXTRA_COLUMNS = ("label", "game", "ply")

COLUMNS = tuple(FEATURE_NAMES) + EXTRA_COLUMNS

#: Decision gaps the decorrelation measurement reports. The default ``--rate`` is defended by this
#: table, not by assertion: see ``docs/learning.md``.
GAPS = (1, 2, 4, 8, 16)

#: Bernoulli keep-rate per decision. **Measured, not guessed.** Consecutive decisions inside one
#: turn share almost the whole feature vector and share the label exactly, so they add loss weight
#: without adding information. Over 554,479 heuristic decisions the mean L2 distance between
#: feature vectors *k* decisions apart runs 1.098 (k=1), 1.517, 1.928, 2.501, 2.699 (k=16) against
#: 3.397 for two positions from **different** games: one decision apart is 32% of the way to an
#: independent pair, and the curve is still climbing at k=4 but flat by k=16. Halving the rate from
#: 1-in-4 to 1-in-8 buys +0.573; halving again buys only +0.198. 1-in-8 is the knee, and games are
#: the cheap resource (34 games/s), so that is the default. ``--rate 1.0`` keeps everything.
DEFAULT_RATE = 0.125

#: What ``--perspectives`` may be, and why ``both`` exists.
#:
#: ``move`` writes the obvious row: the features of the player to move, labelled with whether that
#: player went on to win. It has one flaw, and it is not visible in any loss curve. ``to_move_me``
#: (feature 3, "1 if the pending choice is mine") is then **1.0 in every single row** — a constant
#: column. The agent, though, scores *previewed* positions, and its most common preview by far is
#: the one where its turn has just ended: there ``pending.player`` is the rival and the agent feeds
#: ``to_move_me = 0.0``, a value the network has never seen. Whatever weight training happened to
#: leave on that input then applies, unlearned and unmeasured, to exactly the comparison that
#: decides whether to end the turn.
#:
#: ``both`` writes that row **and** the same position seen from the other seat, with that seat's
#: own label. ``features(s, me)`` and ``outcome(record, me)`` are both already defined for either
#: player, so this costs one extra feature extraction per kept decision and nothing else. The
#: column stops being constant, the model learns the position from both sides, and
#: ``p(s, 0) + p(s, 1) ~ 1`` becomes a free calibration check. Both rows carry the same ``game``,
#: so the by-game split keeps them on the same side and the label still cannot leak.
PERSPECTIVES = ("move", "both")


# ------------------------------------------------------------------ the index -> game mapping
def pair_rng(seed: int, i: int) -> Pcg32:
    """The generator that draws game ``i``'s deck pair. Independent of every other game."""
    return Pcg32((seed ^ ((i * 0x9E3779B1) & MASK64)) & MASK64, seq=909)


def game_seed(seed: int, i: int) -> int:
    """The engine seed for game ``i``: shuffles, dice and the agents' own randomness."""
    return (seed * 1000003 + i) & 0x7FFFFFFF


def default_out(agent_a: str, agent_b: str, seed: int) -> Path:
    """Where a harvest lands when ``--out`` is not given: **never** inside the repository.

    ``CPTCG_HARVEST_DIR`` names the directory when set (point it at the session scratchpad);
    otherwise the system temporary directory, which is wiped rather than committed.
    """
    base = os.environ.get("CPTCG_HARVEST_DIR") or str(Path(tempfile.gettempdir()) / "cptcg-harvest")
    return Path(base) / f"{agent_a}-vs-{agent_b}-s{seed}.jsonl.gz"


def parse_mix(text: str | None) -> dict[str, float] | None:
    """``"random=.3,heuristic=.35"`` to a source mix, validated against the sampler's names."""
    if not text:
        return None
    mix: dict[str, float] = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"--mix wants name=weight pairs, got {part!r}")
        k, v = part.split("=", 1)
        mix[k.strip()] = float(v)
    D.normalised_mix(mix)                      # raises on an unknown source or an all-zero mix
    return mix


# ------------------------------------------------------------------ deck source bookkeeping
def deck_source(name: str) -> str:
    """Which ``learn.decks`` source produced a decklist with this name.

    The sampler names what it builds (``random``, ``built``, ``explorer``) and leaves the fixed
    lists their own names, so the realised mix can be tallied from the records without storing it.
    ``sample_pair`` may append ``-b`` to make a pair's two names distinct.
    """
    n = name[:-2] if name.endswith("-b") else name
    if n == "random":
        return "random"
    if n == "built":
        return "heuristic"
    if n == "explorer":
        return "explorer"
    try:
        if any(d.name == n for d in D.training_decks()):
            return "sample"
    except Exception:                          # no data directory: the sampler falls back too
        pass
    return "other"


def _tally(counter: dict, key, n: int = 1) -> None:
    counter[str(key)] = counter.get(str(key), 0) + n


# ------------------------------------------------------------------ workers
def play_chunk(job: tuple) -> list[dict]:
    """Play games ``lo..hi`` and return their records as JSON. Runs in a worker process."""
    lo, hi, seed, agent_a, agent_b, mix = job
    reg = runner._REG or load_default()
    names = (agent_a, agent_b)
    out = []
    for i in range(lo, hi):
        a, b = D.sample_pair(reg, pair_rng(seed, i), mix=mix)
        gs = game_seed(seed, i)
        s = runner.play_game(reg, (a, b), names, gs, DEFAULT_CONFIG, record=True)
        rec = GameRecord.from_replay(Replay.from_game(s, (a, b), names), meta={"i": i})
        out.append(rec.to_json())
    return out


def _keep_rng(harvest_seed: int, record_seed: int) -> Pcg32:
    """The Bernoulli draw for one game's decisions: seeded from the record's own seed, so the
    same replays give the same rows every time, whatever order or worker count reads them."""
    return Pcg32((((record_seed * 2654435761) & MASK64) ^ harvest_seed) & MASK64, seq=311)


def examples_chunk(job: tuple) -> tuple:
    """Turn a batch of records into float32 rows. Runs in a worker process.

    Returns ``(row_bytes, n_rows, n_decisions, gap_sums, gap_counts, label_sum)``. The gap sums are
    the decorrelation measurement: mean L2 distance between feature vectors *k* decisions apart,
    over every decision, sampled or not.
    """
    batch, rate, seed, both = job
    reg = runner._REG or load_default()
    rows = array("f")
    n_rows = n_dec = 0
    label_sum = 0.0
    gap_sums = {k: 0.0 for k in GAPS}
    gap_counts = {k: 0 for k in GAPS}
    keep_all = rate >= 1.0
    cut = int(round(max(0.0, rate) * 10_000))
    for gi, raw in batch:
        rec = GameRecord.from_json(raw, rules=None)
        rng = _keep_rng(seed, rec.seed)
        ring: deque = deque(maxlen=max(GAPS) + 1)
        for ply, (s, _chosen, _v, _val) in enumerate(replay_features(rec, reg)):
            me = s.pending.player
            f = features(s, me)
            n_dec += 1
            ring.appendleft(f)
            for k in GAPS:
                if len(ring) > k:
                    old = ring[k]
                    gap_sums[k] += sum((x - y) * (x - y) for x, y in zip(f, old)) ** 0.5
                    gap_counts[k] += 1
            if keep_all or rng.below(10_000) < cut:
                seats = (me, 1 - me) if both else (me,)
                for seat in seats:
                    fv = f if seat == me else features(s, seat)
                    label = outcome(rec, seat)
                    rows.extend(fv)
                    rows.append(label)
                    rows.append(float(gi))
                    rows.append(float(ply))
                    label_sum += label
                    n_rows += 1
    if sys.byteorder != "little":
        rows.byteswap()
    return rows.tobytes(), n_rows, n_dec, gap_sums, gap_counts, label_sum


def ordered_map(fn, jobs, workers: int):
    """``fn`` over ``jobs`` in parallel, results yielded **in job order**, look-ahead bounded.

    One level below ``runner.run_match``, which is built around one deck pair per call and would
    therefore want one process pool per game here. The pieces it uses are the same:
    ``runner.load_registry`` warms each worker's card registry once, and ``runner.EXECUTOR`` (the
    browser build's process-free executor) forces the in-process path, as it does there.
    """
    if workers <= 1 or runner.EXECUTOR is not None:
        runner.load_registry()
        for j in jobs:
            yield fn(j)
        return
    from concurrent.futures import ProcessPoolExecutor    # lazily: the browser build has none
    ahead = max(2, workers * 2)
    with ProcessPoolExecutor(max_workers=workers, initializer=runner.load_registry) as ex:
        pending: deque = deque()
        try:
            for j in jobs:
                pending.append(ex.submit(fn, j))
                while len(pending) >= ahead:
                    yield pending.popleft().result()
            while pending:
                yield pending.popleft().result()
        finally:
            for f in pending:
                f.cancel()


# ------------------------------------------------------------------ the manifest
def manifest_path(out: str | Path) -> Path:
    return Path(str(out) + ".harvest.json")


def write_manifest(out: str | Path, man: dict) -> None:
    """Rewrite the manifest atomically: a torn manifest would be worse than a torn data file."""
    p = manifest_path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(man, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def read_manifest(out: str | Path) -> dict | None:
    p = manifest_path(out)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def check_resumable(man: dict, *, seed: int, agents: tuple[str, str], mix, rules: str) -> None:
    """Refuse a resume that would mix two distributions into one file."""
    want = {"seed": seed, "agents": list(agents), "mix": mix, "rules": rules}
    have = {k: man.get(k) for k in want}
    diff = [k for k in want if have[k] != want[k]]
    if man.get("format") != MANIFEST_FORMAT:
        diff.append("format")
    if diff:
        raise ValueError(
            f"refusing to resume {man.get('out')}: "
            + "; ".join(f"{k} was {have.get(k)!r}, now {want.get(k)!r}" for k in diff)
            + ". Two distributions in one file are invisible in a loss curve. "
              "Use --fresh, or a different --out.")


# ------------------------------------------------------------------ play
def cmd_play(a) -> int:
    agent_b = a.agent_b or a.agent
    agents = (a.agent, agent_b)
    mix = parse_mix(a.mix)
    rules = DEFAULT_CONFIG.digest()
    out = Path(a.out) if a.out else default_out(a.agent, agent_b, a.seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    workers = a.workers or max(1, os.cpu_count() or 1)

    man = read_manifest(out)
    if a.fresh or man is None:
        if man is not None or out.exists():
            if not a.fresh:
                raise SystemExit(
                    f"{out} already exists but has no usable manifest; pass --fresh to overwrite.")
            out.unlink(missing_ok=True)
            manifest_path(out).unlink(missing_ok=True)
        man = {"format": MANIFEST_FORMAT, "out": str(out), "seed": a.seed, "agents": list(agents),
               "mix": mix, "rules": rules, "games_target": a.games, "games_done": 0, "bytes": 0,
               "decisions": 0, "elapsed_s": 0.0, "sources": {}, "end_reasons": {}, "winners": {},
               "started": _now(), "updated": _now()}
        write_manifest(out, man)
    else:
        if not a.resume:
            raise SystemExit(
                f"{out} is a harvest already {man['games_done']} games in. "
                f"Pass --resume to continue it, or --fresh to start over.")
        check_resumable(man, seed=a.seed, agents=agents, mix=mix, rules=rules)
        # Truncate back to the last committed byte: this discards a torn tail and nothing else.
        if out.exists() and out.stat().st_size != man["bytes"]:
            print(f"resume: truncating {out.stat().st_size - man['bytes']} torn byte(s)",
                  file=sys.stderr)
            os.truncate(out, man["bytes"])
        elif not out.exists() and man["bytes"]:
            raise SystemExit(f"manifest says {man['bytes']} bytes but {out} is gone")
        man["games_target"] = max(man["games_target"], a.games)

    target = man["games_target"]
    done = man["games_done"]
    if done >= target:
        print(f"already complete: {done}/{target} games", file=sys.stderr)
        return _report(out, man, workers, 0, man["elapsed_s"])

    todo = target - done
    chunk = min(250, max(1, todo // max(1, workers * 8)))
    jobs = [(lo, min(lo + chunk, target), a.seed, agents[0], agents[1], mix)
            for lo in range(done, target, chunk)]
    deadline = time.time() + a.minutes * 60 if a.minutes else None

    t0 = time.time()
    games_here = decisions_here = 0
    print(f"harvesting {todo} games -> {out} ({agents[0]} vs {agents[1]}, {workers} worker(s), "
          f"chunk {chunk})", file=sys.stderr)
    for raws in ordered_map(play_chunk, jobs, workers):
        records = [GameRecord.from_json(r, rules=rules) for r in raws]
        write_games(out, records, append=True)
        for r in records:
            decisions_here += r.n_decisions
            _tally(man["end_reasons"], r.end_reason)
            _tally(man["winners"], "draw" if r.winner is None else f"seat{r.winner}")
            for d in r.decks:
                _tally(man["sources"], deck_source(d["name"]))
        games_here += len(records)
        man["games_done"] = done + games_here
        man["bytes"] = out.stat().st_size
        man["decisions"] = man.get("decisions", 0) + decisions_here
        decisions_here = 0
        man["elapsed_s"] = round(man.get("elapsed_s", 0.0) + (time.time() - t0), 3)
        t0 = time.time()
        man["updated"] = _now()
        write_manifest(out, man)
        print(f"  {man['games_done']}/{target} games, {man['bytes'] / 1024:.0f} KB, "
              f"{man['games_done'] / max(1e-9, man['elapsed_s']):.1f} games/s", file=sys.stderr)
        if deadline and time.time() >= deadline:
            print(f"--minutes {a.minutes} reached; stopped cleanly at a chunk boundary "
                  f"({man['games_done']}/{target}). Re-run with --resume.", file=sys.stderr)
            break
    return _report(out, man, workers, games_here, man["elapsed_s"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _report(out: Path, man: dict, workers: int, games_here: int, elapsed: float) -> int:
    """What it actually cost. Measurements only — never an estimate where a number was measured."""
    games = man["games_done"]
    decisions = man["decisions"]
    el = max(1e-9, elapsed)
    gps = games / el
    pph = decisions / el * 3600.0
    print(f"\n{out}")
    print(f"  {games} games, {decisions} decisions, {el:.1f}s wall "
          f"({workers} worker(s), {os.cpu_count()} cores)")
    print(f"  measured throughput: {gps:.1f} games/s, {pph / 1e6:.2f}M positions/hour")
    print("  " + format_size_stats(size_stats(out)).replace("\n", "\n  "))
    tot = max(1, sum(man["sources"].values()))
    print("  realised deck mix: "
          + ", ".join(f"{k} {v * 100 / tot:.1f}%" for k, v in sorted(man["sources"].items())))
    print("  end reasons: " + ", ".join(f"{k} {v}" for k, v in sorted(man["end_reasons"].items())))
    print("  winners: " + ", ".join(f"{k} {v}" for k, v in sorted(man["winners"].items())))
    print(f"  manifest: {manifest_path(out)}")
    if games < man["games_target"]:
        print(f"  incomplete: {games}/{man['games_target']} — re-run with --resume")
    return 0


# ------------------------------------------------------------------ examples
def _batches(paths, rules, batch: int, max_games: int | None):
    """Stream ``(game_index, record_json)`` batches out of the harvest files, in file order."""
    cur: list = []
    n = 0
    for p in paths:
        for rec in read_games(p, rules=rules):
            gi = int(rec.meta.get("i", n))
            cur.append((gi, rec.to_json()))
            n += 1
            if len(cur) >= batch:
                yield cur
                cur = []
            if max_games and n >= max_games:
                break
        if max_games and n >= max_games:
            break
    if cur:
        yield cur


def cmd_examples(a) -> int:
    paths = [Path(p) for p in getattr(a, "in")]
    prefix = Path(a.out)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    f32 = Path(str(prefix) + ".f32")
    header = Path(str(prefix) + ".json")
    header.unlink(missing_ok=True)             # the header is written LAST, see below
    rules = DEFAULT_CONFIG.digest()
    workers = a.workers or max(1, os.cpu_count() or 1)
    both = a.perspectives == "both"

    total_games = 0
    for p in paths:
        total_games += sum(1 for _ in read_games(p, rules=rules))
    if a.max_games:
        total_games = min(total_games, a.max_games)
    batch = min(250, max(1, total_games // max(1, workers * 8)))

    n_rows = n_dec = 0
    label_sum = 0.0
    gap_sums = {k: 0.0 for k in GAPS}
    gap_counts = {k: 0 for k in GAPS}
    t0 = time.time()
    with open(f32, "wb") as fh:
        for blob, nr, nd, gs, gc, ls in ordered_map(
                examples_chunk,
                ((b, a.rate, a.seed, both) for b in _batches(paths, rules, batch, a.max_games)),
                workers):
            fh.write(blob)
            n_rows += nr
            n_dec += nd
            label_sum += ls
            for k in GAPS:
                gap_sums[k] += gs[k]
                gap_counts[k] += gc[k]
    el = time.time() - t0

    decorr = {str(k): (gap_sums[k] / gap_counts[k]) if gap_counts[k] else None for k in GAPS}
    head = {"format": MANIFEST_FORMAT, "rows": n_rows, "cols": len(COLUMNS),
            "columns": list(COLUMNS), "nfeat": NFEAT, "dtype": "float32", "byte_order": "little",
            "order": "C", "data": f32.name, "bytes": f32.stat().st_size,
            "rules": rules, "rate": a.rate, "seed": a.seed, "games": total_games,
            "decisions": n_dec, "perspectives": a.perspectives,
            "mean_label": (label_sum / n_rows) if n_rows else None,
            "sources": [str(p) for p in paths],
            "source_manifests": [read_manifest(p) for p in paths],
            "decorrelation_l2": decorr, "created": _now()}
    if head["bytes"] != n_rows * len(COLUMNS) * 4:
        raise SystemExit(f"{f32} is {head['bytes']} bytes, expected "
                         f"{n_rows * len(COLUMNS) * 4} for {n_rows} rows — refusing to claim it")
    header.write_text(json.dumps(head, indent=1) + "\n", encoding="utf-8")

    print(f"{f32}")
    print(f"  {n_rows} rows x {len(COLUMNS)} float32 ({head['bytes'] / 1e6:.1f} MB) from "
          f"{total_games} games / {n_dec} decisions at --rate {a.rate}")
    print(f"  {el:.1f}s wall, {total_games / max(1e-9, el):.0f} games/s "
          f"({workers} worker(s), {os.cpu_count()} cores)")
    print(f"  mean label {head['mean_label']}")
    print("  decorrelation, mean L2 between feature vectors k decisions apart:")
    for k in GAPS:
        v = decorr[str(k)]
        print(f"    k={k:<3} {v:.4f}" if v is not None else f"    k={k:<3} n/a")
    print(f"  header: {header}  (written last, so a killed run leaves an obviously incomplete pair)")
    print("  read it with: numpy.fromfile(path, dtype='<f4').reshape(rows, cols)")
    print("  split train/val on the 'game' column, never on rows: positions inside one game share "
          "a label.")
    return 0


# ------------------------------------------------------------------ compact
def cmd_compact(a) -> int:
    """Rewrite finished harvests as a single gzip member.

    Appending is what makes a harvest resumable, and every append writes a **discrete** gzip
    member. That is the whole trick behind the byte-offset resume — truncating to a recorded
    member boundary yields exactly the committed records — but it costs real space: each member
    restarts the compressor with an empty window, so a 100-game harvest written in 34 chunks is
    666 gzipped bytes per game where the same records in one member are 245. Compaction is
    therefore a separate, explicit step for a harvest that is **done**: it refuses a file whose
    manifest disagrees with its size (resume that first), and it updates the recorded byte count so
    a later ``--resume`` still lines up.
    """
    for raw in a.paths:
        p = Path(raw)
        man = read_manifest(p)
        before = p.stat().st_size
        if man and man["bytes"] != before:
            raise SystemExit(f"{p} has an uncommitted tail ({before} bytes, manifest says "
                             f"{man['bytes']}). Run play --resume first.")
        if man and man["games_done"] < man["games_target"]:
            raise SystemExit(f"{p} is only {man['games_done']}/{man['games_target']} games in; "
                             f"finish it before compacting.")
        # The temp file must keep the ``.gz`` suffix: that is what tells write_games to compress.
        gz = ".gz" if p.name.endswith(".gz") else ""
        tmp = p.parent / (p.name + ".compacting" + gz)
        tmp.unlink(missing_ok=True)
        n = write_games(tmp, read_games(p, rules=None), append=False)
        back = sum(1 for _ in read_games(tmp, rules=None))
        if back != n or (gz and tmp.stat().st_size >= before):
            tmp.unlink(missing_ok=True)
            raise SystemExit(f"refusing to compact {p}: {n} games in, {back} back, "
                             f"{before} -> {tmp.stat().st_size if tmp.exists() else 0} bytes")
        os.replace(tmp, p)
        after = p.stat().st_size
        if sum(1 for _ in read_games(p, rules=None)) != n:      # the file we actually kept
            raise SystemExit(f"{p} does not read back after compaction")
        if man:
            man["bytes"] = after
            man["compacted"] = _now()
            write_manifest(p, man)
        print(f"{p}: {n} games, {before} -> {after} bytes ({100 * after / max(1, before):.0f}%)")
    return 0


# ------------------------------------------------------------------ stats
def cmd_stats(a) -> int:
    for p in a.paths:
        print(format_size_stats(size_stats(p)))
        sources: dict = {}
        reasons: dict = {}
        winners: dict = {}
        holdouts = 0
        for r in read_games(p, rules=None):
            _tally(reasons, r.end_reason)
            _tally(winners, "draw" if r.winner is None else f"seat{r.winner}")
            for d in r.decks:
                _tally(sources, deck_source(d["name"]))
                if D.is_holdout(Decklist.from_counts(d["name"], d["legends"], d["main"])):
                    holdouts += 1
        tot = max(1, sum(sources.values()))
        print("  deck mix: "
              + ", ".join(f"{k} {v * 100 / tot:.1f}%" for k, v in sorted(sources.items())))
        print("  end reasons: " + ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())))
        print("  winners: " + ", ".join(f"{k} {v}" for k, v in sorted(winners.items())))
        print(f"  held-out starters present: {holdouts}"
              + ("  <-- THIS HARVEST IS POISONED" if holdouts else " (as it must be)"))
        man = read_manifest(p)
        if man:
            print(f"  manifest: seed {man['seed']}, agents {man['agents']}, mix {man['mix']}, "
                  f"{man['games_done']}/{man['games_target']} games, {man['elapsed_s']:.1f}s")
    return 0


# ------------------------------------------------------------------ CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("play", help="self-play into a resumable experience file")
    p.add_argument("--games", type=int, required=True)
    p.add_argument("--agent", default="heuristic", help="seat 0 agent (default heuristic)")
    p.add_argument("--agent-b", default=None, help="seat 1 agent (defaults to --agent)")
    p.add_argument("--out", default=None)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--mix", default=None, help="random=.3,heuristic=.35,explorer=.2,sample=.15")
    p.add_argument("--resume", action="store_true", help="continue an interrupted harvest")
    p.add_argument("--fresh", action="store_true", help="overwrite any existing harvest")
    p.add_argument("--minutes", type=float, default=None,
                   help="stop cleanly at the next chunk boundary after this many minutes")
    p.set_defaults(fn=cmd_play)

    e = sub.add_parser("examples", help="replays -> (features, label) rows for the trainer")
    e.add_argument("--in", nargs="+", required=True, dest="in")
    e.add_argument("--out", required=True, help="prefix: writes PREFIX.f32 and PREFIX.json")
    e.add_argument("--rate", type=float, default=DEFAULT_RATE,
                   help=f"Bernoulli keep-rate per decision (default {DEFAULT_RATE}; see the "
                        f"decorrelation table this prints, and docs/learning.md)")
    e.add_argument("--seed", type=int, default=7)
    e.add_argument("--workers", type=int, default=None)
    e.add_argument("--max-games", type=int, default=None)
    e.add_argument("--perspectives", choices=PERSPECTIVES, default="move",
                   help="'move': one row per decision, for the player to move. 'both': that row "
                        "and the rival's, each with its own label. See the note by PERSPECTIVES.")
    e.set_defaults(fn=cmd_examples)

    c = sub.add_parser("compact", help="rewrite a finished harvest as one gzip member")
    c.add_argument("paths", nargs="+")
    c.set_defaults(fn=cmd_compact)

    s = sub.add_parser("stats", help="size and composition of an existing harvest")
    s.add_argument("paths", nargs="+")
    s.set_defaults(fn=cmd_stats)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
