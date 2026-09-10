"""A small stdlib HTTP server: play vs AI, watch replays, browse decks and lab reports.

No framework on purpose — `python -m cptcg serve` works anywhere the engine runs. The UI holds no
game logic: it renders the view JSON and posts back an option index.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cptcg.agents.base import make_agent
from cptcg.cards.registry import load_default
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import Pcg32
from cptcg.deck.builder import heuristic_deck, random_deck
from cptcg.deck.decklist import Decklist
from cptcg.deck.validate import validate
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


def deck_json(deck: Decklist) -> dict:
    """A decklist plus its validation, the shape the deck-builder page edits."""
    v = validate(deck, reg())
    return {"name": deck.name, "legends": list(deck.legends), "main": deck.counts(),
            "note": deck.meta.get("note", ""), "ok": v.ok, "errors": v.errors, "warnings": v.warnings,
            "ram": {c.name.title(): n for c, n in v.ram_limits.items()}, "size": len(deck.main)}


def deck_from_body(body: dict) -> Decklist:
    counts = {str(k): int(n) for k, n in (body.get("main") or {}).items() if int(n) > 0}
    meta = {"note": body["note"]} if body.get("note") else {}
    return Decklist.from_counts(str(body.get("name") or "untitled"), [str(x) for x in body.get("legends") or []],
                                counts, **meta)


def deck_slug(name: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in name.strip().lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "untitled"


def build_deck(body: dict) -> Decklist:
    legends = [str(x) for x in body.get("legends") or []] or None
    seed = int(body.get("seed", int(time.time()) % 1_000_000))
    rng = Pcg32(seed, seq=9)
    mode = body.get("mode") or "balanced"
    name = body.get("name") or f"{mode} {seed}"
    if mode == "random":
        return random_deck(reg(), rng, legends, name=name)
    if mode in ("heuristic", "legacy"):
        return heuristic_deck(reg(), legends, rng, name=name)
    from cptcg.deck.strategies import get_strategy
    return get_strategy(mode).build(reg(), legends, rng, knowledge=knowledge(), name=name)


def knowledge():
    """Learned card values from past leagues, if a store exists; builders add them to their opinions."""
    from cptcg.deck.knowledge import DEFAULT_PATH, Knowledge
    path = ROOT / DEFAULT_PATH
    return Knowledge.load(path, reg()) if path.exists() else None


def list_strategies() -> list[dict]:
    from cptcg.deck.strategies import all_strategies, blurb
    out = [{"name": st.name, "description": blurb(st.describe())} for st in all_strategies()]
    out.append({"name": "legacy", "description": "The original unopinionated builder: curve, type mix and sell-tag floor only."})
    out.append({"name": "random", "description": "A uniformly random legal deck: the control group."})
    return out


def list_replays() -> list[str]:
    out_dir = ROOT / "out"
    return sorted(str(p.relative_to(ROOT)) for p in out_dir.rglob("*.json") if "replays" in p.parts) if out_dir.exists() else []


def list_reports() -> list[str]:
    out_dir = ROOT / "out"
    return sorted(str(p.relative_to(ROOT)) for p in out_dir.rglob("tournament.json")) if out_dir.exists() else []


# ---------------------------------------------------------------- lab jobs
# A tournament or league runs in a thread of the server process; the games themselves fan out
# over the runner's process pool exactly as the CLI does. The client polls for progress lines.
class Job:
    def __init__(self, kind: str, params: dict) -> None:
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind
        self.params = params
        self.status = "running"
        self.lines: list[str] = []
        self.reports: list[str] = []
        self.decks: list[str] = []
        self.error: str | None = None
        self.started = time.time()
        self.finished: float | None = None

    def log(self, msg: str) -> None:
        self.lines.append(msg)

    def to_json(self) -> dict:
        return {"id": self.id, "kind": self.kind, "params": self.params, "status": self.status,
                "lines": self.lines[-60:], "n_lines": len(self.lines), "reports": self.reports, "decks": self.decks,
                "error": self.error,
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
    job.log(f"{len(decks)} decks, up to {games} games per pair, {agent} agents, seed {seed}")

    def progress(a, b, k, n, verdict):
        job.log(f"{a} vs {b}: {k}/{n}" + ("" if verdict == "continue" else f" [{verdict}]"))

    t = run_tournament(decks, agent, games, seed=seed, workers=body.get("jobs"),
                       sprt=None if body.get("no_sprt") else SPRT(float(body.get("delta", 0.05))), progress=progress)
    t.save(out / "tournament.json")
    (out / "report.md").write_text(render_report(t, body.get("name") or f"Tournament: {len(decks)} decks"), encoding="utf-8")
    job.reports.append(rel(out / "tournament.json"))
    order = t.standings()
    job.log("standings: " + ", ".join(decks[i].name for i in order))


def _run_league(job: Job) -> None:
    from cptcg.deck.builder import league
    from cptcg.deck.knowledge import DEFAULT_PATH as KNOWLEDGE_PATH
    from cptcg.deck.hall_of_fame import DEFAULT_PATH as HOF_PATH
    body = job.params
    out = _job_dir(job)
    strategies = body.get("strategies") or None
    if strategies == ["legacy"]:
        strategies = "legacy"
    seed = int(body.get("seed", 0))
    for gen, t, decks in league(reg(), int(body.get("builders", 6)), int(body.get("generations", 3)),
                                int(body.get("steps", 5)), seed=seed, agent=body.get("agent") or "heuristic",
                                workers=body.get("jobs"), games_per_pair=int(body.get("games", 60)), out_dir=out,
                                progress=job.log, strategies=strategies,
                                knowledge_path=ROOT / KNOWLEDGE_PATH if body.get("knowledge", True) else None,
                                hall_of_fame_path=ROOT / HOF_PATH if body.get("hof", True) else None):
        job.reports.append(rel(out / f"gen{gen}" / "tournament.json"))
        order = t.standings()
        bt = t.bt()
        job.log(f"generation {gen}: " + ", ".join(f"{decks[i].name} {bt[i]:.2f}" for i in order))


def _run_generate(job: Job) -> None:
    from cptcg.deck.generate import generate_decks, save_batch, screen_decks
    from cptcg.deck.hall_of_fame import DEFAULT_PATH as HOF_PATH, HallOfFame
    body = job.params
    count = max(1, min(500, int(body.get("count", 20))))
    strategies = body.get("strategies") or None
    legends = body.get("legends") or None
    seed = int(body.get("seed", 0))
    batch = generate_decks(reg(), count, strategies, seed=seed, knowledge=knowledge(), legends=legends,
                           max_similarity=float(body.get("max_similarity", 0.7)),
                           prefix=deck_slug(body.get("name") or "gen") + "-", progress=job.log)
    decks = batch.decks
    job.log(f"{len(decks)} decks on {len(batch.triples)} Legend triples; {batch.rejected_similar} near-duplicates rejected")
    out = DECK_DIRS[0] / "generated" / f"{deck_slug(body.get('name') or 'batch')}-{job.id}"
    screen = int(body.get("screen", 0))
    if screen:
        panel = [Decklist.load(p) for p in sorted(DECK_DIRS[0].glob("sample_*.json"))[:4]]
        hof_path = ROOT / HOF_PATH
        if body.get("hof_panel", True) and hof_path.exists():
            panel = (HallOfFame.load(hof_path).opponents(4) or []) + panel[:2]
        ranked = screen_decks(reg(), decks, panel, screen, agent=body.get("agent") or "heuristic", seed=seed,
                              workers=body.get("jobs"), progress=job.log)
        keep = int(body.get("keep", 0))
        decks = [r.deck for r in (ranked[:keep] if keep else ranked)]
        job.log("ranking: " + ", ".join(f"{r.deck.name} {100 * r.rate:.0f}%" for r in ranked[:10]))
        out.mkdir(parents=True, exist_ok=True)
        (out / "screen.json").write_text(json.dumps([{"name": r.deck.name, "wins": r.wins, "games": r.games}
                                                     for r in ranked], indent=1), encoding="utf-8")
    paths = save_batch(decks, out)
    job.decks = [rel(p) for p in paths]
    job.log(f"saved {len(paths)} decks to {rel(out)}/")


def start_job(body: dict) -> Job:
    kind = body.get("kind")
    if kind not in ("tourney", "league", "generate"):
        raise ValueError("kind must be tourney, league or generate")
    job = Job(kind, body)

    def run():
        try:
            {"tourney": _run_tourney, "league": _run_league, "generate": _run_generate}[kind](job)
            job.status = "done"
        except Exception as e:  # noqa: BLE001
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"
            job.log("failed: " + job.error)
        job.finished = time.time()

    with LOCK:
        JOBS[job.id] = job
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


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet
        pass

    def _json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path
        try:
            if p == "/" or p == "/index.html":
                return self._file(STATIC / "index.html")
            if p == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if p.startswith("/static/"):
                return self._file(STATIC / p[len("/static/"):])
            if p.startswith("/images/"):
                return self._file(IMAGES / p[len("/images/"):])
            if p == "/api/decks":
                return self._json(list_decks())
            if p == "/api/strategies":
                return self._json(list_strategies())
            if p == "/api/deck":
                path = abs_deck_path(q.get("path", ""))
                if path is None:
                    return self._json({"error": "no such deck"}, 404)
                return self._json(dict(deck_json(Decklist.load(path)), path=rel(path)))
            if p == "/api/cards":
                r = reg()
                return self._json([dict(card_json_static(d), image=(IMAGES / f"{d.id}.jpg").exists()) for d in r.defs])
            if p.startswith("/api/games/"):
                gid = p.split("/")[3]
                with LOCK:
                    g = GAMES.get(gid)
                    if g is None:
                        return self._json({"error": "no such game"}, 404)
                    if p.endswith("/replay"):
                        return self._json(Replay.from_game(g.s, g.decks, ("human", g.agent_name)).__dict__ | {"decks": list(Replay.from_game(g.s, g.decks).decks)})
                    return self._json(g.view(int(q.get("since", 0))))
            if p == "/api/replays":
                return self._json(list_replays())
            if p == "/api/replay":
                views = replay_views(q["file"])
                step = max(0, min(len(views) - 1, int(q.get("step", 0))))
                return self._json({"step": step, "steps": len(views), "view": views[step]})
            if p == "/api/reports":
                return self._json(list_reports())
            if p == "/api/report":
                path = (ROOT / q["file"]).resolve()
                if not path.is_relative_to(ROOT / "out") or path.name != "tournament.json":
                    return self._json({"error": "no such report"}, 404)
                data = json.loads(path.read_text())
                md = path.with_name("report.md")
                data["markdown"] = md.read_text(encoding="utf-8") if md.exists() else ""
                data["file"] = rel(path)
                return self._json(data)
            if p == "/api/jobs":
                with LOCK:
                    return self._json([j.to_json() for j in sorted(JOBS.values(), key=lambda j: j.started, reverse=True)])
            if p.startswith("/api/jobs/"):
                with LOCK:
                    j = JOBS.get(p.split("/")[3])
                return self._json(j.to_json()) if j else self._json({"error": "no such job"}, 404)
            self.send_error(404)
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self) -> None:
        u = urlparse(self.path)
        p = u.path
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        try:
            if p == "/api/games":
                a = Decklist.load(ROOT / body["deck_me"])
                b = Decklist.load(ROOT / body["deck_ai"])
                seat = int(body.get("seat", 0))
                decks = (a, b) if seat == 0 else (b, a)
                seed = int(body.get("seed", int(time.time()) % 1_000_000))
                g = Game(decks, body.get("agent", "heuristic"), seat, seed)
                gid = uuid.uuid4().hex[:8]
                with LOCK:
                    GAMES[gid] = g
                return self._json({"id": gid, "view": g.view()})
            if p == "/api/jobs":
                return self._json(start_job(body).to_json())
            if p == "/api/validate":
                return self._json(deck_json(deck_from_body(body)))
            if p == "/api/build":
                return self._json(deck_json(build_deck(body)))
            if p == "/api/decks":
                deck = deck_from_body(body)
                v = validate(deck, reg())
                if not v.ok:
                    return self._json({"error": "deck is not legal: " + "; ".join(v.errors[:3])}, 400)
                path = DECK_DIRS[0] / f"{deck_slug(deck.name)}.json"
                if path.exists() and not body.get("overwrite"):
                    return self._json({"error": "exists", "path": rel(path)}, 409)
                DECK_DIRS[0].mkdir(parents=True, exist_ok=True)
                deck.save(path)
                return self._json(dict(deck_json(deck), path=rel(path)))
            if p.startswith("/api/games/"):
                parts = p.split("/")
                gid, verb = parts[3], parts[4] if len(parts) > 4 else ""
                with LOCK:
                    g = GAMES.get(gid)
                    if g is None:
                        return self._json({"error": "no such game"}, 404)
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
                        return self._json({"error": "unknown verb"}, 404)
                    return self._json(g.view(int(body.get("since", 0))))
            self.send_error(404)
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"{type(e).__name__}: {e}"}, 400)


def card_json_static(d) -> dict:
    return {"id": d.id, "name": d.name, "subtitle": d.subtitle, "type": d.type.name.title(), "color": d.color.name.title(),
            "cost": d.cost, "power": (f"{d.power}+" if d.power_variable else d.power), "ram": d.ram,
            "sell_tag": d.sell_tag, "tags": sorted(d.tags), "keywords": [k.name.replace("_", " ") for k in d.keywords],
            "text": d.text, "verified": d.verified}


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    reg()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"cptcg web client: http://{host}:{port}/   (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
