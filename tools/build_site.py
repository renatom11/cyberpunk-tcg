"""Build the static site: the web client with the rules engine running in the browser.

    python tools/build_site.py --out site [--pyodide-url URL]

The result is plain files (HTML, JS, the ``cptcg`` package zipped, card data, decks, art) that
any static host serves — GitHub Pages deploys it from .github/workflows/pages.yml. In the
browser, static/boot.js loads Pyodide and runs cptcg.web.backend in a Web Worker.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"


def build_id() -> str:
    """Short git SHA (falls back to a timestamp): stamped into every asset URL so a new deploy is
    never served from a browser's or GitHub Pages' cache of the previous one."""
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return time.strftime("%Y%m%d%H%M%S", time.gmtime())


def build(out: Path, pyodide_url: str = PYODIDE) -> dict:
    static = ROOT / "src/cptcg/web/static"
    v = build_id()
    if out.exists():
        shutil.rmtree(out)
    (out / "static").mkdir(parents=True)
    for f in static.iterdir():
        if f.suffix in (".js", ".css"):
            shutil.copy(f, out / "static" / f.name)
    html = (static / "index.html").read_text(encoding="utf-8")
    boot = (f'<script>window.CPTCG_STATIC = {json.dumps({"pyodide": pyodide_url, "v": v})};</script>\n'
            f'<script src="static/boot.js?v={v}"></script>')
    html = html.replace("<!-- STATIC_BOOT -->", boot)
    html = html.replace('href="static/style.css"', f'href="static/style.css?v={v}"')
    html = html.replace('src="static/report.js"', f'src="static/report.js?v={v}"')
    html = html.replace('src="static/app.js"', f'src="static/app.js?v={v}"')
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("")
    shutil.copy(static / "coi.js", out / "coi.js")          # service worker must sit at the site root to scope it

    # the engine
    with zipfile.ZipFile(out / "cptcg.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted((ROOT / "src/cptcg").rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                z.write(p, p.relative_to(ROOT / "src"))

    # data: cards, decks, replays, art
    manifest = {"decks": [], "images": [], "replays": []}
    (out / "data/cards").mkdir(parents=True)
    shutil.copy(ROOT / "data/cards/wnc.json", out / "data/cards/wnc.json")
    for p in sorted((ROOT / "data/decks").rglob("*.json")):
        rel = p.relative_to(ROOT)
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, out / rel)
        manifest["decks"].append(str(rel))
    demo = ROOT / "data/replays"
    if demo.exists():
        for p in sorted(demo.glob("*.json")):
            rel = p.relative_to(ROOT)
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(p, out / rel)
            manifest["replays"].append(str(rel))
    imgs = ROOT / "data/images"
    if imgs.exists():
        (out / "images").mkdir()
        for p in sorted(imgs.glob("*.jpg")):
            shutil.copy(p, out / "images" / p.name)
            if not p.stem.startswith("_"):
                manifest["images"].append(p.stem)
    manifest["build"] = v
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="site")
    ap.add_argument("--pyodide-url", default=PYODIDE, help="where the Pyodide runtime is served from")
    ap.add_argument("--pyodide-dir", help="copy a local Pyodide runtime (the npm package dir) into site/pyo and use it")
    a = ap.parse_args()
    m = build(Path(a.out), "pyo/" if a.pyodide_dir else a.pyodide_url)
    if a.pyodide_dir:
        src = Path(a.pyodide_dir)
        dst = Path(a.out) / "pyo"
        dst.mkdir()
        for name in ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"):
            shutil.copy(src / name, dst / name)
    print(f"site written to {a.out}/ (build {m['build']}): {len(m['decks'])} decks, {len(m['images'])} card images, {len(m['replays'])} replays")


if __name__ == "__main__":
    main()
