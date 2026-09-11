"""The handle. One command, a budget, and a chain of generations that each passed or failed.

    python tools/learn.py run --hours 12                # turn the handle until the budget is out
    python tools/learn.py run --generations 3           # or a fixed number of them
    python tools/learn.py status                        # what happened, and what is the incumbent
    python tools/learn.py drift                         # is the ladder a straight line?
    python tools/learn.py promote N                     # ship generation N's weights into the package

One generation is four steps, and every one of them is a subprocess of a tool that already exists
and is already tested:

1. **generate** — ``harvest.py play`` with ``ismcts-explore``, which is the search with root
   Dirichlet noise and visit-proportional move sampling on. Split across opponents by
   ``learn.loop.opponent_schedule``: mostly the current best against itself, a quarter against a
   uniformly sampled earlier generation, and a tenth against the frozen heuristic and random play.
2. **examples** — ``harvest.py examples``, the same sampling the bootstrap used.
3. **fit** — ``fit_eval.py fit`` over a *window* of recent generations, not just this one.
4. **gate** — three arena runs against the incumbent, and ``learn.loop.decide`` turns them into a
   promotion or a rejection with a reason.

Why a subprocess and not an import
----------------------------------
The fit reads a multi-gigabyte float32 matrix through numpy and the generation holds none of it.
Keeping them in separate processes means the loop's resident memory is the size of a ledger, and a
fit that dies on memory kills a generation rather than the run. It also means every step is a
command a human can re-run by hand from the log, which is the property that makes a failed
generation debuggable at all.

What this does not do
---------------------
It does not touch ``src/cptcg/agents/weights.json``. A promoted generation is promoted *in the
ledger*; shipping it into the package is a separate, deliberate command, because that file is what
the website and every test run against and it should move when a human says so.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.learn.loop import (  # noqa: E402
    ANCHOR, FLOOR, REPLAY_WINDOW, GateResult, GenerationRecord, Ledger, decide, drift_report,
    opponent_schedule, pick_past,
)
from cptcg.learn.model import WEIGHTS_PATH  # noqa: E402

DEFAULT_DIR = ROOT / "out" / "learn"
GENERATOR = "ismcts-explore"       # noisy: makes data
PLAYER = "ismcts"                  # quiet: gets measured


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run(cmd: list[str], *, log: Path, dry: bool = False) -> int:
    """Run one step, tee-ing to a per-step log so a failure is readable afterwards."""
    line = " ".join(cmd)
    print(f"  $ {line}", flush=True)
    if dry:
        return 0
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n$ {line}\n")
        fh.flush()
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        return subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env, cwd=str(ROOT))


def agent_with(name: str, weights: str | Path | None) -> str:
    """``ismcts@path`` — which weights an agent plays with, carried inside its name so that the
    arena's worker processes can build it too."""
    return f"{name}@{weights}" if weights else name


# ------------------------------------------------------------------ the steps
def step_generate(led: Ledger, g: GenerationRecord, gdir: Path, *, games: int, workers: int,
                  dry: bool) -> bool:
    """Self-play into a resumable experience file, split across the opponent pool."""
    best = led.best()
    incumbent = best.weights if best else str(WEIGHTS_PATH)
    past = [x for x in led.promoted if x.n != g.n]
    plan = opponent_schedule(games, len(past))
    g.notes.append("opponents: " + ", ".join(f"{k} {v}" for k, v in plan.items()))
    led.save()
    ok = True
    for k, (role, n) in enumerate(plan.items()):
        if role == "self":
            opp = agent_with(GENERATOR, incumbent)
        elif role == "past":
            pastgen = pick_past(past, g.seed, k)
            opp = agent_with(GENERATOR, pastgen.weights if pastgen else incumbent)
        else:
            opp = role                        # heuristic and random carry no weights
        out = gdir / f"games-{role}.jsonl.gz"
        rc = _run([sys.executable, str(ROOT / "tools" / "harvest.py"), "play",
                   "--games", str(n), "--agent", agent_with(GENERATOR, incumbent),
                   "--agent-b", opp, "--seed", str(g.seed + k), "--workers", str(workers),
                   "--out", str(out), "--resume"],
                  log=gdir / "generate.log", dry=dry)
        ok = ok and rc == 0
    g.games = games
    return ok


def step_examples(g: GenerationRecord, gdir: Path, *, workers: int, dry: bool) -> bool:
    ok = True
    for src in sorted(gdir.glob("games-*.jsonl.gz")) or ([Path("dry")] if dry else []):
        rc = _run([sys.executable, str(ROOT / "tools" / "harvest.py"), "examples",
                   "--in", str(src), "--out", str(gdir / f"ex-{src.stem.split('-')[-1]}"),
                   "--rate", "0.125", "--perspectives", "both", "--workers", str(workers)],
                  log=gdir / "examples.log", dry=dry)
        ok = ok and rc == 0
    return ok


def step_fit(led: Ledger, g: GenerationRecord, gdir: Path, *, hidden: int, dry: bool) -> bool:
    """Fit over a window of generations, not just the newest one.

    Fitting only the newest is how a network forgets: each generation is a narrow sample of one
    player's habits, and a net refitted on it alone chases the last few thousand games. The window
    is the replay buffer every project that has run this loop ended up with.
    """
    window = [x for x in led.gens if x.n > g.n - REPLAY_WINDOW]
    ex: list[str] = []
    for x in window:
        ex += [str(p) for p in sorted((gdir.parent / f"gen-{x.n:03d}").glob("ex-*.f32"))]
    if not ex and not dry:
        g.notes.append("no example files to fit — generation produced nothing")
        return False
    g.notes.append(f"fit window: generations {[x.n for x in window]}, {len(ex)} example files")
    out = gdir / "weights.json"
    rc = _run([sys.executable, str(ROOT / "tools" / "fit_eval.py"), "fit", *ex,
               "--hidden", str(hidden), "--epochs", "400", "--patience", "25",
               "--out", str(out), "--name", f"gen-{g.n}"],
              log=gdir / "fit.log", dry=dry)
    g.weights = str(out)
    return rc == 0


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def step_gate(led: Ledger, g: GenerationRecord, gdir: Path, *, games: int, workers: int,
              dry: bool) -> GateResult | None:
    """Three measurements: the candidate against the incumbent, and both against what cannot move.

    The head-to-head is the claim. The frozen panel and the delayed-reward suite are the checks
    that the claim was not bought by the pair of them drifting together — see ``learn.loop`` for
    why that is the failure this loop is shaped around.
    """
    best = led.best()
    incumbent = agent_with(PLAYER, best.weights if best else WEIGHTS_PATH)
    cand = agent_with(PLAYER, g.weights)
    # One directory per step, so reading a result back is a glob with exactly one answer rather
    # than a guess at how the arena spelled two agent names into a file name.
    steps = [(["a-vs-b", cand, incumbent, "-n", str(games), "-j", str(workers)], "avb"),
             (["panel", cand, "-j", str(workers)], "panel"),
             (["delayed", cand], "delayed")]
    got = {}
    for args, tag in steps:
        d = gdir / "gate" / tag
        _run([sys.executable, str(ROOT / "tools" / "arena.py"), *args,
              "--out", str(d), "--no-docs"], log=gdir / "gate.log", dry=dry)
        got[tag] = {} if dry else _read_json(next(iter(sorted(d.glob("*.json"))), Path("x")))
    if dry:
        return None
    avb, panel, delayed = got["avb"], got["panel"], got["delayed"]
    g.gate = {"a_vs_b": avb, "panel": panel, "delayed": delayed,
              "panel_anchor": panel_anchor(panel)}
    base_panel = (best.gate.get("panel_anchor") if best else None)
    base_delayed = (best.gate.get("delayed", {}) if best else {}).get("solved")
    here = panel_anchor(panel)
    return GateResult(
        sprt=avb.get("verdict", "continue"),
        win_rate=100.0 * avb.get("rate", 0.0),
        pairing_lo=100.0 * float(avb.get("cluster_low") or 0.0),
        panel=here,
        panel_incumbent=float(base_panel if base_panel is not None else here),
        delayed=int(delayed.get("solved", 0)),
        delayed_incumbent=int(base_delayed if base_delayed is not None else 0),
    )


def panel_anchor(panel: dict) -> float:
    """The one number from the frozen panel that a generation is held to, as a percentage.

    The panel plays several members; the one that matters for drift is the **frozen heuristic**,
    because it is the member that provably cannot move. Random play is a floor rather than a
    yardstick — every fitted agent beats it above 90% and the number stops discriminating — and
    the ``gen0`` slot is a future generation, so it says nothing about whether this one regressed.
    """
    for m in panel.get("members", ()):
        if m.get("id") == "heuristic" and m.get("available") and m.get("result"):
            return 100.0 * float(m["result"].get("rate", 0.0))
    return 0.0


# ------------------------------------------------------------------ commands
def cmd_run(a) -> int:
    led = Ledger(a.dir)
    led.header.setdefault("started", _now())
    led.header["generator"] = GENERATOR
    led.header["player"] = PLAYER
    deadline = time.time() + a.hours * 3600 if a.hours else None
    made = 0
    while True:
        if a.generations and made >= a.generations:
            print(f"done: {made} generation(s)")
            break
        if deadline and time.time() >= deadline:
            print("done: out of budget")
            break
        g = led.unfinished()
        if g is None:
            n = led.next_n()
            g = led.add(GenerationRecord(n=n, seed=a.seed + n * 7919, started=_now(),
                                         parent=(led.best().weights if led.best() else str(WEIGHTS_PATH))))
        gdir = Path(a.dir) / f"gen-{g.n:03d}"
        gdir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== generation {g.n}  ({g.status})  {_now()}")

        if g.status == "generating":
            if not step_generate(led, g, gdir, games=a.games, workers=a.workers, dry=a.dry_run):
                g.status, g.reason = "failed", "generation step failed; see generate.log"
                led.save(); return 1
            g.status = "fitting"; led.save()
        if g.status == "fitting":
            if not step_examples(g, gdir, workers=a.workers, dry=a.dry_run):
                g.status, g.reason = "failed", "examples step failed; see examples.log"
                led.save(); return 1
            if not step_fit(led, g, gdir, hidden=a.hidden, dry=a.dry_run):
                g.status, g.reason = "failed", "fit step failed; see fit.log"
                led.save(); return 1
            g.status = "gating"; led.save()
        if g.status == "gating":
            res = step_gate(led, g, gdir, games=a.gate_games, workers=a.workers, dry=a.dry_run)
            if a.dry_run:
                print("  (dry run: no gate verdict)")
                return 0
            ok, why = decide(res)
            g.status = "promoted" if ok else "rejected"
            g.reason = why
            g.finished = _now()
            led.save()
            print(f"  {g.status.upper()}: {why}")
        made += 1
    return 0


def cmd_status(a) -> int:
    led = Ledger(a.dir)
    if not led.gens:
        print(f"no generations yet under {a.dir}")
        return 0
    best = led.best()
    print(f"{len(led.gens)} generation(s); incumbent: "
          f"{'gen ' + str(best.n) if best else 'the shipped weights (none promoted yet)'}")
    print(f"{'gen':>4} {'status':<10} {'games':>7}  reason")
    for g in led.gens:
        print(f"{g.n:>4} {g.status:<10} {g.games:>7}  {g.reason}")
    return 0


def cmd_drift(a) -> int:
    """Play the incumbent against every earlier generation and look for a circle."""
    led = Ledger(a.dir)
    best = led.best()
    past = [g for g in led.promoted if g.n != (best.n if best else -1)]
    if best is None or not past:
        print("not enough promoted generations to check for drift yet")
        return 0
    out = Path(a.dir) / "drift"
    rates: dict[int, float] = {}
    for g in past:
        rc = _run([sys.executable, str(ROOT / "tools" / "arena.py"), "a-vs-b",
                   agent_with(PLAYER, best.weights), agent_with(PLAYER, g.weights),
                   "-n", str(a.games), "-j", str(a.workers), "--no-sprt",
                   "--out", str(out), "--no-docs"], log=out / "drift.log", dry=a.dry_run)
        if rc or a.dry_run:
            continue
        d = _read_json(sorted(out.glob("a-vs-b_*.json"))[-1])
        rates[g.n] = 100.0 * d.get("a_wins", 0) / max(1, d.get("games", 0))
    ok, bad = drift_report(rates)
    print(f"generation {best.n} against its ancestors: "
          + ", ".join(f"gen {n} {r:.1f}%" for n, r in sorted(rates.items())))
    if ok:
        print("the ladder is a straight line as far as this can see")
    else:
        print("DRIFT:")
        for line in bad:
            print("  - " + line)
    return 0


def cmd_promote(a) -> int:
    led = Ledger(a.dir)
    g = next((x for x in led.gens if x.n == a.n), None)
    if g is None or not g.weights:
        print(f"generation {a.n} has no fitted weights")
        return 1
    if g.status != "promoted" and not a.force:
        print(f"generation {a.n} is {g.status!r}, not 'promoted'. Pass --force to ship it anyway.")
        return 1
    src, dst = Path(g.weights), Path(a.into)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"shipped generation {a.n} into {dst}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/learn.py", description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n".join(__doc__.splitlines()[2:8]))
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--dir", default=str(DEFAULT_DIR), help="where the ledger and generations live")
        p.add_argument("-j", "--workers", type=int, default=os.cpu_count() or 1)
        p.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")

    p = sub.add_parser("run", help="turn the handle")
    common(p)
    p.add_argument("--hours", type=float, default=0.0, help="stop starting generations after this long")
    p.add_argument("--generations", type=int, default=0, help="or stop after this many")
    p.add_argument("--games", type=int, default=20000, help="self-play games per generation")
    p.add_argument("--gate-games", type=int, default=360, help="games in the head-to-head gate")
    p.add_argument("--hidden", type=int, default=16)
    p.add_argument("--seed", type=int, default=20260911)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("status", help="what happened so far")
    common(p)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("drift", help="the incumbent against every ancestor")
    common(p)
    p.add_argument("--games", type=int, default=120)
    p.set_defaults(fn=cmd_drift)

    p = sub.add_parser("promote", help="ship a generation's weights into the package")
    common(p)
    p.add_argument("n", type=int)
    p.add_argument("--into", default=str(WEIGHTS_PATH))
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_promote)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
