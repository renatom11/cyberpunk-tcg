"""A small stdlib HTTP server: play vs AI, watch replays, browse decks and lab reports.

No framework on purpose — `python -m cptcg serve` works anywhere the engine runs. The UI holds no
game logic: it renders the view JSON and posts back an option index.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from cptcg.agents.base import make_agent
from cptcg.cards.registry import load_default
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import Pcg32
from cptcg.deck.builder import heuristic_deck, random_deck
from cptcg.deck.decklist import Decklist
from cptcg.deck.validate import validate
from cptcg.sim.budget import Tracker
from cptcg.sim.narrate import narrate
from cptcg.sim.record import Replay
from cptcg.web.view import card_json, view_state

ROOT = Path(__file__).resolve().parents[3]
STATIC = Path(__file__).resolve().parent / "static"
IMAGES = ROOT / "data" / "images"
DECK_DIRS = [ROOT / "data" / "decks", ROOT / "out"]
REG = None
LOCK = threading.Lock()
GAMES: dict[str, "Game"] = {}


def reg():
    global REG
    if REG is None:
        REG = load_default()
    return REG


class Game:
    def __init__(self, decks, agent_name: str, human_seat: int, seed: int) -> None:
        self.decks = decks
        self.agent_name = agent_name
        self.human = human_seat
        self.seed = seed
        self.names = ("You" if human_seat == 0 else f"AI ({decks[0].name})",
                      "You" if human_seat == 1 else f"AI ({decks[1].name})")
        self.reset()

    def reset(self, actions: list[int] | None = None) -> None:
        self.s = new_game(reg(), self.decks, self.seed, record=True)
        self.agent = make_agent(self.agent_name, self.seed)
        self.agent.new_game(self.seed, 1 - self.human)
        self.lines: list[str] = []
        self.cursor = 0
        self.human_marks: list[int] = []            # action counts at each human decision
        for idx in actions or []:
            self._note_human()
            apply(self.s, idx)
        self._narrate()
        self.run_ai()

    def _note_human(self) -> None:
        if self.s.pending is not None and self.s.pending.player == self.human:
            self.human_marks.append(len(self.s.actions))

    def _narrate(self) -> None:
        new = self.s.log[self.cursor:]
        self.cursor = len(self.s.log)
        self.lines += narrate(self.s, new, self.names)

    def run_ai(self) -> None:
        """Let the AI act until it's the human's decision or the game is over."""
        guard = 0
        while not self.s.over and self.s.pending is not None and self.s.pending.player != self.human and guard < 500:
            legal_actions(self.s)
            apply(self.s, self.agent.act(self.s, self.s.pending))
            guard += 1
        self._narrate()

    def act(self, index: int) -> None:
        legal_actions(self.s)
        if self.s.pending is None or self.s.pending.player != self.human:
            raise ValueError("not your decision")
        if not 0 <= index < len(self.s.pending.options):
            raise ValueError("bad option")
        self.human_marks.append(len(self.s.actions))
        apply(self.s, index)
        self._narrate()
        self.run_ai()

    def undo(self) -> None:
        if len(self.human_marks) < 1:
            return
        # go back to the state before the human's last decision
        target = self.human_marks[-1]
        actions = list(self.s.actions[:target])
        self.human_marks = []
        self.reset(actions)
        self.human_marks = self.human_marks[:-1] if self.human_marks else []

    def view(self, since: int = 0) -> dict:
        v = view_state(self.s, self.human, self.names, self.lines[since:])
        v["log_total"] = len(self.lines)
        v["human"] = self.human
        return v


def rel(path: Path) -> str:
    """Path as the client sees it: relative to the repo when inside it, absolute otherwise."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def abs_deck_path(rel_or_abs: str) -> Path | None:
    path = Path(rel_or_abs)
    path = (path if path.is_absolute() else ROOT / path).resolve()
    if not any(path.is_relative_to(d.resolve()) for d in DECK_DIRS) or not path.is_file():
        return None
    return path


def list_decks() -> list[dict]:
    out = []
    for d in DECK_DIRS:
        for p in sorted(d.rglob("*.json")) if d.exists() else []:
            try:
                raw = json.loads(p.read_text())
                if not (isinstance(raw, dict) and "legends" in raw and "main" in raw):
                    continue
                deck = Decklist.load(p)
                v = validate(deck, reg())
                out.append({"path": rel(p), "name": deck.name, "legends": list(deck.legends),
                            "size": len(deck.main), "ok": v.ok, "errors": v.errors[:3]})
            except Exception:  # noqa: BLE001
                continue
    return out


# Deck meta the BUILD page carries through a load → edit → save round trip, so a deck built
# toward an archetype (or opened from a league report) keeps its label when saved again.
META_KEYS = ("generated", "archetype", "archetype_id", "context", "steps", "seed", "batch_index")


def deck_json(deck: Decklist) -> dict:
    """A decklist plus its validation, the shape the deck-builder page edits."""
    v = validate(deck, reg())
    return {"name": deck.name, "legends": list(deck.legends), "main": deck.counts(),
            "note": deck.meta.get("note", ""), "meta": {k: deck.meta[k] for k in META_KEYS if k in deck.meta},
            "ok": v.ok, "errors": v.errors, "warnings": v.warnings,
            "ram": {c.name.title(): n for c, n in v.ram_limits.items()}, "size": len(deck.main)}


def deck_from_body(body: dict) -> Decklist:
    counts = {str(k): int(n) for k, n in (body.get("main") or {}).items() if int(n) > 0}
    raw = body.get("meta") or {}
    meta = {k: raw[k] for k in META_KEYS if isinstance(raw, dict) and raw.get(k) is not None}
    if body.get("note"):
        meta["note"] = body["note"]
    return Decklist.from_counts(str(body.get("name") or "untitled"), [str(x) for x in body.get("legends") or []],
                                counts, **meta)


def deck_slug(name: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in name.strip().lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "untitled"


def build_deck(body: dict) -> Decklist:
    """The BUILD page's AI build. ``mode``: ``explorer`` (invent a shape), an archetype id or
    name from the store (build toward it), ``heuristic``/``legacy`` or ``random``."""
    legends = [str(x) for x in body.get("legends") or []] or None
    seed = int(body.get("seed", int(time.time()) % 1_000_000))
    rng = Pcg32(seed, seq=9)
    mode = body.get("mode") or "explorer"
    name = body.get("name") or f"{mode} {seed}"
    if mode == "random":
        return random_deck(reg(), rng, legends, name=name)
    if mode in ("heuristic", "legacy"):
        return heuristic_deck(reg(), legends, rng, name=name)
    from cptcg.deck.strategies import get_builder
    return get_builder(mode, archetype_store()).build(reg(), legends, rng, knowledge=knowledge(), name=name)


def knowledge():
    """Learned card values from past leagues, if a store exists; builders add them to their opinions."""
    from cptcg.deck.knowledge import DEFAULT_PATH, Knowledge
    path = ROOT / DEFAULT_PATH
    return Knowledge.load(path, reg()) if path.exists() else None


def archetype_store():
    """The archetypes learned from every tournament and league run here (``out/archetypes.json``;
    an empty store before the first one)."""
    from cptcg.deck.archetypes import DEFAULT_PATH, ArchetypeStore
    return ArchetypeStore.load(ROOT / DEFAULT_PATH, reg())


def learn_archetypes(t, source: str = "", generation: int = 0):
    """Record a finished tournament's decks in the archetype store, re-cluster, save; returns
    the store so the report can label each deck with its nearest archetype."""
    store = archetype_store()
    store.update_from_tournament(t, source=source, generation=generation)
    store.refit()
    store.save()
    return store


def check_archetypes(specs) -> None:
    """Raise ValueError (a 400 for the client) when a league or generate body names an
    archetype the store does not know — before a job card is created for it."""
    if not specs or specs == "legacy" or specs == ["legacy"]:
        return
    from cptcg.deck.strategies import get_builder
    store = archetype_store()
    for spec in specs:
        try:
            get_builder(spec, store)
        except KeyError as e:
            raise ValueError(str(e).strip('"')) from None


EXPLORER_DESCRIPTION = ("Invents a deck shape at random (within what the Legends allow) and builds toward it. "
                        "This is how new archetypes get found; every builder explores until enough decks have played.")


def list_archetypes() -> dict:
    """GET /api/archetypes: the learned archetypes (by win rate) with their record and member
    decks, how many decks the store holds, and the builder options the BUILD page offers."""
    from cptcg.deck.archetypes import MIN_DECKS
    store = archetype_store()
    archetypes = []
    for a in store.ranked():
        row = a.to_json()
        row["members"] = [d.name for d in store.members(a)]
        archetypes.append(row)
    builders = [{"id": "explorer", "name": "Explorer", "description": EXPLORER_DESCRIPTION}]
    builders += [{"id": a["id"], "name": a["name"], "description": a["description"]} for a in archetypes]
    builders.append({"id": "legacy", "name": "legacy", "description": "The original unopinionated builder: curve, type mix and sell-tag floor only."})
    builders.append({"id": "random", "name": "random", "description": "A uniformly random legal deck: the control group."})
    return {"decks": len(store.decks), "distinct": store.lineage_count(), "needed": MIN_DECKS,
            "tournaments": store.tournaments, "separation": round(store.separation, 3),
            "noise_reference": round(store.noise_reference, 3), "archetypes": archetypes, "builders": builders}


def list_replays() -> list[str]:
    """Replay files: demo replays shipped in data/replays plus anything under out/**/replays."""
    out = []
    for base in (ROOT / "data" / "replays", ROOT / "out"):
        if base.exists():
            out += [str(p.relative_to(ROOT)) for p in base.rglob("*.json") if "replays" in p.parts]
    return sorted(out)


def list_reports() -> list[str]:
    out_dir = ROOT / "out"
    return sorted(str(p.relative_to(ROOT)) for p in out_dir.rglob("tournament.json")) if out_dir.exists() else []


def report_json(path_: Path) -> dict:
    """A saved tournament with everything the web report needs. Files written before version 2
    are upgraded on read: the summary sentences, deck profiles and ratings are recomputed from
    the loaded tournament, and each deck's meta (archetype, generation, ...) comes from the
    sibling ``<name>.json`` a league writes next to it. The league series (``league.json`` in
    the run's directory) is attached as ``league_series`` when there is one."""
    from cptcg.sim.report import (disclosure, glossary_json, how_played, label_nearest, profile_sentence,
                                  render_report)
    from cptcg.sim.tournament import Tournament
    data = json.loads(path_.read_text(encoding="utf-8"))
    old = int(data.get("version", 1)) < Tournament.JSON_VERSION or "summary" not in data
    if old or "expected" not in data or "nearest" not in (data.get("decks") or [{}])[0]:
        # Old files (version 1, or version 2 saved before the field-expected win rates and the
        # nearest-archetype labels existed) are rebuilt from the loaded run: Tournament.load
        # merges the sibling <name>.json deck files the same way the CLI does.
        t = Tournament.load(path_, rel_to=ROOT)
        if "nearest" not in t.info:
            try:
                label_nearest(t, archetype_store())
            except (OSError, ValueError, KeyError):
                pass
        data = t.to_json(reg())
        md = path_.with_name("report.md")
        data["markdown"] = render_report(t, reg=reg()) if old or not md.exists() else md.read_text(encoding="utf-8")
    else:
        md = path_.with_name("report.md")
        data["markdown"] = md.read_text(encoding="utf-8") if md.exists() else ""
    data["file"] = rel(path_)
    for d in data.get("decks", []):          # files saved before the shape sentence was stored
        d.setdefault("shape", profile_sentence(d["profile"]) if d.get("profile") else None)
        d.setdefault("nearest", None)
    data.setdefault("how_played", "")
    # The disclosure and the glossary are the report's words, not the run's data: they are taken
    # fresh from Python on every read so a saved file never carries stale wording.
    data["disclosure"] = disclosure(data.get("agent") or "heuristic")
    data["glossary"] = glossary_json()
    for parent in (path_.parent, path_.parent.parent):
        series = parent / "league.json"
        if series.is_file():
            try:
                data["league_series"] = json.loads(series.read_text(encoding="utf-8"))
            except ValueError:
                pass
            break
    return data


# ---------------------------------------------------------------- lab jobs
# A tournament or league runs in a thread of the server process; the games themselves fan out
# over the runner's process pool exactly as the CLI does. The client polls for progress lines.
class JobCancelled(Exception):
    """Raised from Job.log once a cancel was requested; jobs log often enough to stop promptly."""


class Job:
    def __init__(self, kind: str, params: dict) -> None:
        self.id = str(params.get("job_id") or uuid.uuid4().hex[:8])
        self.kind = kind
        self.params = params
        self.status = "running"
        self.lines: list[str] = []
        self.reports: list[str] = []
        self.decks: list[str] = []
        self.error: str | None = None
        self.started = time.time()
        self.finished: float | None = None
        self.cancel_requested = False
        self.progress: dict | None = None          # budget.Tracker.to_json(): phase, step/steps, remaining range
        from cptcg.sim import runner
        self._games0 = runner.GAMES_PLAYED

    @property
    def games(self) -> int:
        """Games played so far by this job (the runner counts every finished game)."""
        from cptcg.sim import runner
        return runner.GAMES_PLAYED - self._games0

    def _emit(self) -> None:
        if PROGRESS_HOOK is not None:
            PROGRESS_HOOK(self.to_json())
        if self.cancel_requested:
            raise JobCancelled()

    def log(self, msg: str) -> None:
        self.lines.append(msg)
        self._emit()

    def set_progress(self, line: str | None = None, **fields) -> None:
        """Replace the job's progress object (``phase``, ``step``, ``steps``, ``unit``, ``done``,
        ``remaining_min``, ``remaining_max`` — a Tracker's ``to_json()``), optionally logging a
        line with it. Like ``log`` it is a cancel point."""
        if line is not None:
            self.lines.append(line)
        self.progress = dict(fields)
        self._emit()

    def to_json(self) -> dict:
        return {"id": self.id, "kind": self.kind, "params": self.params, "status": self.status,
                "lines": self.lines[-60:], "n_lines": len(self.lines), "reports": self.reports, "decks": self.decks,
                "error": self.error, "games": self.games, "progress": self.progress,
                "elapsed": round((self.finished or time.time()) - self.started, 1)}


JOBS: dict[str, Job] = {}


def _job_dir(job: Job) -> Path:
    out = ROOT / "out" / "lab" / f"{deck_slug(job.params.get('name') or job.kind)}-{job.id}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _run_tourney(job: Job) -> None:
    from cptcg.sim.report import render_report
    from cptcg.sim.stats import SPRT
    from cptcg.sim.tournament import run_tournament
    body = job.params
    paths = [abs_deck_path(x) for x in body.get("decks") or []]
    if any(x is None for x in paths) or len(paths) < 2:
        raise ValueError("pick at least two existing decks")
    decks = [Decklist.load(x) for x in paths]
    for d in decks:
        v = validate(d, reg())
        if not v.ok:
            raise ValueError(f"{d.name}: {v.errors[0]}")
    games = int(body.get("games", 200))
    seed = int(body.get("seed", 0))
    agent = body.get("agent") or "heuristic"
    out = _job_dir(job)
    tracker = Tracker.for_tourney(len(decks), games, sprt=not body.get("no_sprt"))
    tracker.phase = f"starting: {len(decks)} decks, {tracker.steps} matchups"
    job.set_progress(f"{len(decks)} decks, up to {games} games per pair, {agent} agents, seed {seed}", **tracker.to_json())

    def progress(a, b, k, n, verdict):
        settled = tracker.cell(a, b, n, verdict)
        tracker.phase = f"{a} vs {b} ({n} of {games} games{cell_note(settled, n, games)})"
        job.set_progress(f"{a} vs {b}: {k}/{n}" + ("" if verdict == "continue" else f" [{verdict}]"), **tracker.to_json())

    t = run_tournament(decks, agent, games, seed=seed, workers=body.get("jobs") or DEFAULT_WORKERS,
                       sprt=None if body.get("no_sprt") else SPRT(float(body.get("delta", 0.05))), progress=progress)
    title = body.get("name") or f"Tournament: {len(decks)} decks"
    t.info["title"] = title
    t.paths = [rel(x) for x in paths]
    from cptcg.sim.report import label_nearest
    label_nearest(t, learn_archetypes(t, source=title))     # decks not built toward an archetype get their nearest one
    t.save(out / "tournament.json", reg())
    (out / "report.md").write_text(render_report(t, title, reg()), encoding="utf-8")
    job.reports.append(rel(out / "tournament.json"))
    order = t.standings()
    tracker.finish(f"finished: {t.info['total_games']} games")
    job.set_progress("standings: " + ", ".join(decks[i].name for i in order), **tracker.to_json())


def hof_extra(body: dict, n: int = 2) -> int:
    """How many hall-of-fame champions a league with these settings would add to every
    builder's climb field (0 without the option or without a store)."""
    if not body.get("hof", True):
        return 0
    from cptcg.deck.hall_of_fame import DEFAULT_PATH as HOF_PATH, HallOfFame
    path = ROOT / HOF_PATH
    if not path.exists():
        return 0
    try:
        return len(HallOfFame.load(path).opponents(n))
    except (OSError, ValueError, KeyError):
        return 0


def screen_panel(body: dict) -> list[Decklist]:
    """The decks a generate job screens against: the strongest hall-of-fame champions (when
    the option is on and a store exists) plus the first sample decks."""
    from cptcg.deck.hall_of_fame import DEFAULT_PATH as HOF_PATH, HallOfFame
    panel = [Decklist.load(p) for p in sorted(DECK_DIRS[0].glob("sample_*.json"))[:4]]
    hof_path = ROOT / HOF_PATH
    if body.get("hof_panel", True) and hof_path.exists():
        panel = (HallOfFame.load(hof_path).opponents(4) or []) + panel[:2]
    return panel


def estimate(body: dict) -> dict:
    """The game budget of a job described like a POST /api/jobs body, before it runs:
    ``games_min`` if every comparison settles at its first batch, ``games_max`` if none does,
    plus ``steps`` (the structural units the job card counts) and their ``unit`` name. The same
    formulas feed the job's own progress, so the form and the job card agree."""
    from cptcg.sim import budget
    kind = body.get("kind")
    if kind == "tourney":
        n = len(body.get("decks") or [])
        cap = int(body.get("games", 200))
        lo, hi = budget.tourney_budget(n, cap, sprt=not body.get("no_sprt"))
        return {"games_min": lo, "games_max": hi, "steps": budget.pairs(n), "unit": "matchups"}
    if kind == "league":
        b, gens, steps = int(body.get("builders", 6)), int(body.get("generations", 3)), int(body.get("steps", 5))
        cap = int(body.get("games", 60))
        field = max(0, b - 1) + hof_extra(body)
        lo, hi = budget.league_budget(b, gens, steps, cap, field)
        return {"games_min": lo, "games_max": hi, "steps": gens * (b * steps + budget.pairs(b)), "unit": "steps"}
    if kind == "generate":
        count = max(1, min(500, int(body.get("count", 20))))
        screen = int(body.get("screen", 0))
        panel = len(screen_panel(body)) if screen else 0
        lo, hi = budget.generate_budget(count, screen, panel)
        return {"games_min": lo, "games_max": hi, "steps": count + (count if screen and panel else 0), "unit": "decks"}
    raise ValueError("kind must be tourney, league or generate")


def cell_note(settled: bool, n: int, cap: int) -> str:
    """What the job card says about a matchup: a cell that played every game it was allowed
    reached the cap — it never had the chance to stop early, so calling it "settled" would
    claim the early-stop test decided something."""
    if not settled:
        return ""
    return ", reached the cap" if n >= cap else ", settled early"


def _run_league(job: Job) -> None:
    from cptcg.deck.archetypes import DEFAULT_PATH as ARCHETYPES_PATH
    from cptcg.deck.builder import league
    from cptcg.deck.knowledge import DEFAULT_PATH as KNOWLEDGE_PATH
    from cptcg.deck.hall_of_fame import DEFAULT_PATH as HOF_PATH
    body = job.params
    out = _job_dir(job)
    archetypes = body.get("archetypes") or None
    if archetypes == ["legacy"]:
        archetypes = "legacy"
    seed = int(body.get("seed", 0))
    n_builders, gens = int(body.get("builders", 6)), int(body.get("generations", 3))
    steps, cap = int(body.get("steps", 5)), int(body.get("games", 60))
    tracker = Tracker.for_league(n_builders, gens, steps, cap, field=max(0, n_builders - 1) + hof_extra(body))
    tracker.phase = f"starting: {n_builders} builders, {gens} generations"
    job.set_progress(**tracker.to_json())

    def on_event(kind, **e):
        gen = e.get("gen", 0)
        head = f"gen {gen} of {gens}"
        line = None
        if kind == "climb_start":
            tracker.climb_start(e["builder"], e["field"], e["steps"], gen=gen)
            tracker.phase = f"{head} · improving {e['builder']} against {e['field']} decks"
        elif kind == "climb_step":
            tracker.climb_step(e["builder"], e["step"], e["games"], gen=gen)
            tracker.phase = f"{head} · improving {e['builder']} (swap {e['step']} of {e['steps']})"
            line = climb_line(e)
        elif kind == "climb_done":
            tracker.climb_done(e["builder"], gen=gen)
        elif kind == "tourney_cell":
            settled = tracker.cell(e["a"], e["b"], e["n"], e["verdict"], e["cap"], gen=gen)
            tracker.phase = (f"{head} · round robin · {e['a']} vs {e['b']} "
                             f"({e['n']} of {e['cap']} games{cell_note(settled, e['n'], e['cap'])})")
        elif kind == "gen_done":
            tracker.gen_done(gen)
            tracker.phase = f"{head} · done" + (f" · {e['replaced']} is replaced" if e.get("replaced") else "")
        job.set_progress(line, **tracker.to_json())

    for gen, t, decks in league(reg(), n_builders, gens, steps, seed=seed, agent=body.get("agent") or "heuristic",
                                workers=body.get("jobs") or DEFAULT_WORKERS, games_per_pair=cap, out_dir=out,
                                progress=job.log, archetypes=archetypes, on_event=on_event,
                                knowledge_path=ROOT / KNOWLEDGE_PATH if body.get("knowledge", True) else None,
                                hall_of_fame_path=ROOT / HOF_PATH if body.get("hof", True) else None,
                                archetypes_path=ROOT / ARCHETYPES_PATH):
        job.reports.append(rel(out / f"gen{gen}" / "tournament.json"))
        order = t.standings()
        expected = t.expected_rates()
        job.log(f"generation {gen}: " + ", ".join(f"{decks[i].name} {100 * expected[i]:.0f}%" for i in order)
                + " expected win rate vs this field")
    tracker.finish(f"finished: {gens} generations")
    job.set_progress(**tracker.to_json())


def climb_line(e: dict) -> str:
    """A hill-climb step as one log line, card names instead of ids."""
    from cptcg.sim.report import card_name
    p = e.get("proposal") or {}
    swap = f"{card_name(reg(), p.get('out', '?'))} → {card_name(reg(), p.get('in', '?'))}"
    if p.get("kind") == "legend":
        swap = "Legend " + swap
    what = "accepted" if e.get("accepted") else "rejected"
    disc, played = e.get("discordant", 0), e.get("games", 0)
    detail = (f"challenger won {e.get('challenger_wins', 0)} of {disc} games that came out differently, {played} played"
              if disc else f"no game came out differently in {played} played")
    return f"  {e['builder']} swap {e['step']}: {swap} — {what} ({detail})"


def _run_generate(job: Job) -> None:
    from cptcg.deck.generate import generate_decks, save_batch, screen_decks
    body = job.params
    count = max(1, min(500, int(body.get("count", 20))))
    archetypes = body.get("archetypes") or None
    legends = body.get("legends") or None
    seed = int(body.get("seed", 0))
    screen = int(body.get("screen", 0))
    panel = screen_panel(body) if screen else []
    tracker = Tracker.for_generate(count, screen, len(panel))
    tracker.phase = f"building deck 1 of {count}"
    job.set_progress(**tracker.to_json())
    built = 0

    def on_built(msg):
        nonlocal built
        built += 1
        tracker.built(built)
        tracker.phase = f"building deck {min(count, built + 1)} of {count}" if built < count else f"built {count} decks"
        job.set_progress(msg, **tracker.to_json())

    batch = generate_decks(reg(), count, archetypes, seed=seed, knowledge=knowledge(), legends=legends,
                           max_similarity=float(body.get("max_similarity", 0.7)),
                           prefix=deck_slug(body.get("name") or "gen") + "-", progress=on_built,
                           store=archetype_store())
    decks = batch.decks
    job.log(f"{len(decks)} decks on {len(batch.triples)} Legend triples; {batch.rejected_similar} near-duplicates rejected")
    out = DECK_DIRS[0] / "generated" / f"{deck_slug(body.get('name') or 'batch')}-{job.id}"
    if screen and panel:
        screened = 0

        def on_screened(msg):
            nonlocal screened
            screened += 1
            tracker.screened(screened)
            tracker.phase = (f"screening deck {screened + 1} of {len(decks)} against {len(panel)} panel decks"
                             if screened < len(decks) else f"screened {len(decks)} decks against {len(panel)} panel decks")
            job.set_progress(msg, **tracker.to_json())

        ranked = screen_decks(reg(), decks, panel, screen, agent=body.get("agent") or "heuristic", seed=seed,
                              workers=body.get("jobs") or DEFAULT_WORKERS, progress=on_screened)
        keep = int(body.get("keep", 0))
        decks = [r.deck for r in (ranked[:keep] if keep else ranked)]
        job.log("ranking: " + ", ".join(f"{r.deck.name} {100 * r.rate:.0f}%" for r in ranked[:10]))
        out.mkdir(parents=True, exist_ok=True)
        (out / "screen.json").write_text(json.dumps([{"name": r.deck.name, "wins": r.wins, "games": r.games}
                                                     for r in ranked], indent=1), encoding="utf-8")
    paths = save_batch(decks, out)
    job.decks = [rel(p) for p in paths]
    tracker.finish(f"finished: {len(paths)} decks saved")
    job.set_progress(f"saved {len(paths)} decks to {rel(out)}/", **tracker.to_json())


def start_job(body: dict) -> Job:
    kind = body.get("kind")
    if kind not in ("tourney", "league", "generate"):
        raise ValueError("kind must be tourney, league or generate")
    if kind in ("league", "generate"):
        check_archetypes(body.get("archetypes"))
    job = Job(kind, body)

    def run():
        try:
            {"tourney": _run_tourney, "league": _run_league, "generate": _run_generate}[kind](job)
            job.status = "done"
        except JobCancelled:
            job.status = "cancelled"
            job.lines.append("cancelled")
        except Exception as e:  # noqa: BLE001
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"
            job.lines.append("failed: " + job.error)
        if job.progress is not None:               # nothing remains once a job has stopped, however it stopped
            job.progress.update(remaining_min=0, remaining_max=0)
            if job.status != "done":
                job.progress["phase"] = job.status
        job.finished = time.time()

    with LOCK:
        JOBS[job.id] = job
    if INLINE_JOBS:
        run()
    else:
        threading.Thread(target=run, daemon=True, name=f"job-{job.id}").start()
    return job


REPLAY_CACHE: dict[str, list[dict]] = {}


def replay_views(rel: str) -> list[dict]:
    if rel in REPLAY_CACHE:
        return REPLAY_CACHE[rel]
    rep = Replay.load(ROOT / rel)
    names = (rep.decks[0]["name"], rep.decks[1]["name"])
    views = []
    lines: list[str] = []
    cursor = 0
    for s, idx in rep.steps(reg()):
        new = s.log[cursor:]
        cursor = len(s.log)
        lines = lines + narrate(s, new, names)
        v = view_state(s, None, names, lines)
        if idx is not None and s.pending is not None:
            v["next_action"] = v["pending"]["options"][idx]["label"] if v["pending"] else None
        views.append(v)
    REPLAY_CACHE[rel] = views
    return views


def card_json_static(d) -> dict:
    return {"id": d.id, "name": d.name, "subtitle": d.subtitle, "type": d.type.name.title(), "color": d.color.name.title(),
            "cost": d.cost, "power": (f"{d.power}+" if d.power_variable else d.power), "ram": d.ram,
            "sell_tag": d.sell_tag, "tags": sorted(d.tags), "keywords": [k.name.replace("_", " ") for k in d.keywords],
            "text": d.text, "verified": d.verified, "set": d.set_code, "number": d.number}


# ---------------------------------------------------------------- environment knobs
# The same backend serves the local HTTP server and the in-browser build (Pyodide). The browser
# has one thread and no processes: jobs run inline and games are single-worker.
INLINE_JOBS = False          # run a job to completion inside start_job() instead of a thread
DEFAULT_WORKERS = None       # process count for simulations (None = all cores; 1 in the browser)
IMAGE_IDS: set | None = None # card ids with art, when the images are not on the local filesystem
PROGRESS_HOOK = None         # callable(job_json) invoked on every job log line or progress update (browser: postMessage)


def _has_image(cid: str) -> bool:
    return (cid in IMAGE_IDS) if IMAGE_IDS is not None else (IMAGES / f"{cid}.jpg").exists()


def dispatch(method: str, path: str, query: dict, body: dict) -> tuple[int, object]:
    """Route one request. Returns (status, json-able object); a static file is
    ``{"__file__": "<absolute path>"}``."""
    p = path
    q = query or {}
    body = body or {}
    if method == "GET":
        if p == "/" or p == "/index.html":
            return 200, {"__file__": str(STATIC / "index.html")}
        if p == "/favicon.ico":
            return 204, None
        if p.startswith("/static/"):
            return 200, {"__file__": str(STATIC / p[len("/static/"):])}
        if p.startswith("/images/"):
            return 200, {"__file__": str(IMAGES / p[len("/images/"):])}
        if p == "/api/decks":
            return 200, list_decks()
        if p == "/api/archetypes":
            return 200, list_archetypes()
        if p == "/api/deck":
            path_ = abs_deck_path(q.get("path", ""))
            if path_ is None:
                return 404, {"error": "no such deck"}
            return 200, dict(deck_json(Decklist.load(path_)), path=rel(path_))
        if p == "/api/cards":
            return 200, [dict(card_json_static(d), image=_has_image(d.id)) for d in reg().defs]
        if p.startswith("/api/games/"):
            gid = p.split("/")[3]
            with LOCK:
                g = GAMES.get(gid)
                if g is None:
                    return 404, {"error": "no such game"}
                if p.endswith("/replay"):
                    return 200, Replay.from_game(g.s, g.decks, ("human", g.agent_name)).__dict__ | {"decks": list(Replay.from_game(g.s, g.decks).decks)}
                return 200, g.view(int(q.get("since", 0)))
        if p == "/api/replays":
            return 200, list_replays()
        if p == "/api/replay":
            views = replay_views(q["file"])
            step = max(0, min(len(views) - 1, int(q.get("step", 0))))
            return 200, {"step": step, "steps": len(views), "view": views[step]}
        if p == "/api/reports":
            return 200, list_reports()
        if p == "/api/report":
            path_ = (ROOT / q["file"]).resolve()
            if not path_.is_relative_to((ROOT / "out").resolve()) or path_.name != "tournament.json":
                return 404, {"error": "no such report"}
            return 200, report_json(path_)
        if p == "/api/jobs":
            with LOCK:
                return 200, [j.to_json() for j in sorted(JOBS.values(), key=lambda j: j.started, reverse=True)]
        if p.startswith("/api/jobs/"):
            with LOCK:
                j = JOBS.get(p.split("/")[3])
            return (200, j.to_json()) if j else (404, {"error": "no such job"})
        return 404, {"error": "not found"}

    if method == "POST":
        if p == "/api/games":
            a = Decklist.load(abs_deck_path(body["deck_me"]) or (ROOT / body["deck_me"]))
            b = Decklist.load(abs_deck_path(body["deck_ai"]) or (ROOT / body["deck_ai"]))
            seat = int(body.get("seat", 0))
            decks = (a, b) if seat == 0 else (b, a)
            seed = int(body.get("seed", int(time.time()) % 1_000_000))
            g = Game(decks, body.get("agent", "heuristic"), seat, seed)
            gid = uuid.uuid4().hex[:8]
            with LOCK:
                GAMES[gid] = g
            return 200, {"id": gid, "view": g.view()}
        if p == "/api/jobs":
            return 200, start_job(body).to_json()
        if p == "/api/estimate":
            return 200, estimate(body)
        if p.startswith("/api/jobs/") and p.endswith("/cancel"):
            with LOCK:
                j = JOBS.get(p.split("/")[3])
            if j is None:
                return 404, {"error": "no such job"}
            j.cancel_requested = True
            return 200, j.to_json()
        if p == "/api/validate":
            return 200, deck_json(deck_from_body(body))
        if p == "/api/build":
            return 200, deck_json(build_deck(body))
        if p == "/api/decks":
            deck = deck_from_body(body)
            v = validate(deck, reg())
            if not v.ok:
                return 400, {"error": "deck is not legal: " + "; ".join(v.errors[:3])}
            path_ = DECK_DIRS[0] / f"{deck_slug(deck.name)}.json"
            if path_.exists() and not body.get("overwrite"):
                return 409, {"error": "exists", "path": rel(path_)}
            DECK_DIRS[0].mkdir(parents=True, exist_ok=True)
            deck.save(path_)
            return 200, dict(deck_json(deck), path=rel(path_))
        if p.startswith("/api/games/"):
            parts = p.split("/")
            gid, verb = parts[3], parts[4] if len(parts) > 4 else ""
            with LOCK:
                g = GAMES.get(gid)
                if g is None:
                    return 404, {"error": "no such game"}
                if verb == "act":
                    g.act(int(body["index"]))
                elif verb == "undo":
                    g.undo()
                elif verb == "concede":
                    from cptcg.core.enums import EndReason
                    from cptcg.core.ops import end_game
                    end_game(g.s, 1 - g.human, EndReason.CONCEDE)
                    g._narrate()
                else:
                    return 404, {"error": "unknown verb"}
                return 200, g.view(int(body.get("since", 0)))
        return 404, {"error": "not found"}
    return 405, {"error": "method not allowed"}
