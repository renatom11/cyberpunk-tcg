"""Browser pool check: run a tournament in the static site's Pyodide engine pool under headless
Chromium and compare every cell with the same tournament played by the CPython CLI.

    python tools/pw_pool_check.py --site /path/to/built/site [--cores 4 --cores 2] [--games 40]

Build the site first (a local Pyodide runtime is needed when the CDN is unreachable):
    python tools/build_site.py --out site --pyodide-dir /path/to/node_modules/pyodide

For each --cores value the page is told navigator.hardwareConcurrency is that number, so the pool
size follows the formula in boot.js; the reports must be identical for every pool size (games are
seeded, so worker count and chunk assignment cannot change a result) and the run time shows how
the pool scales. The error path (an unknown agent name) must fail the job and leave the pool usable.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
DECKS = ["data/decks/sample_fixers.json", "data/decks/sample_corpos.json", "data/decks/sample_gangers.json"]


class CoiHandler(http.server.SimpleHTTPRequestHandler):
    """Static files with the two headers that make the page cross-origin isolated on first load."""

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


def serve(site: Path, port: int) -> http.server.ThreadingHTTPServer:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(CoiHandler, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def cli_cells(games: int, seed: int) -> list:
    from cptcg.deck.decklist import Decklist
    from cptcg.sim.tournament import run_tournament
    decks = [Decklist.load(ROOT / d) for d in DECKS]
    t = run_tournament(decks, "heuristic", games, seed=seed, workers=1, sprt=None)
    return sorted((c.i, c.j, c.wins_i, c.n) for c in t.cells.values())


def browser_run(pg, body: dict, timeout: float) -> tuple[dict, float]:
    job = pg.evaluate("(b) => CPTCG_BRIDGE.api('/api/jobs', b)", body)
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(0.5)
        j = pg.evaluate("(id) => CPTCG_BRIDGE.api('/api/jobs/' + id)", job["id"])
        if j["status"] != "running":
            return j, time.time() - t0
    raise TimeoutError("job did not finish")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", required=True)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--cores", type=int, action="append", help="hardwareConcurrency values to test (default: the real one)")
    ap.add_argument("--timeout", type=float, default=1200)
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    srv = serve(Path(a.site), a.port)
    ref = cli_cells(a.games, a.seed)
    print(f"CLI reference: {ref}")
    ok = True
    errors: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking"])
        for cores in (a.cores or [None]):
            ctx = b.new_context()
            if cores:
                ctx.add_init_script(f"Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {cores}}})")
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append("PAGE " + str(e)))
            pg.on("console", lambda m: errors.append("CONSOLE " + m.text) if m.type == "error" else None)
            pg.goto(f"http://127.0.0.1:{a.port}/")
            pg.wait_for_function("window.CPTCG_BRIDGE && window.crossOriginIsolated", timeout=60000)
            pg.evaluate("CPTCG_BRIDGE.ready")
            hc, dm, pool = pg.evaluate("[navigator.hardwareConcurrency, navigator.deviceMemory || null, CPTCG_BRIDGE.pool]")
            print(f"\ncores={hc} deviceMemory={dm} pool={pool}")
            body = {"kind": "tourney", "name": "pw", "decks": DECKS, "games": a.games, "agent": "heuristic", "seed": a.seed, "no_sprt": True}
            j, secs = browser_run(pg, body, a.timeout)
            if j["status"] != "done" or not j.get("reports"):
                print(f"  FAIL: job status {j['status']}: {j.get('error')}")
                ok = False
            else:
                rep = pg.evaluate("(f) => CPTCG_BRIDGE.api('/api/report?file=' + encodeURIComponent(f))", j["reports"][0])
                cells = sorted((c["i"], c["j"], c["wins_i"], c["n"]) for c in rep["cells"])
                same = cells == ref
                ok &= same
                print(f"  {j['games']} games in {secs:.1f}s = {j['games'] / secs:.2f} games/s  cells {'IDENTICAL' if same else 'DIFFERENT: ' + str(cells)}")
            # error path: every chunk fails inside the pool; the job must fail and the pool must still work
            j, _ = browser_run(pg, {**body, "agent": "nope", "games": 8}, 120)
            print(f"  bad agent -> status {j['status']}: {str(j.get('error'))[:80]}")
            ok &= j["status"] == "failed"
            j, secs = browser_run(pg, {**body, "games": 8}, 300)
            print(f"  pool after the failure -> status {j['status']} ({j.get('games')} games in {secs:.1f}s)")
            ok &= j["status"] == "done"
            ctx.close()
        b.close()
    srv.shutdown()
    if errors:
        print("browser errors:", errors[:5])
    print("\nOK" if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
