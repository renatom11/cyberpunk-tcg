"""In-browser bridge: the same backend, driven from JavaScript through Pyodide.

The static site (see tools/build_site.py) loads Pyodide in a Web Worker, unpacks the ``cptcg``
package into the virtual filesystem, writes the card data and deck files under ``/cptcg`` and
calls ``handle`` for every request the client would otherwise send over HTTP.
"""

from __future__ import annotations

import json
from pathlib import Path

from cptcg.web import backend


def setup(root: str, image_ids: list[str] | None = None, progress=None) -> None:
    r = Path(root)
    backend.ROOT = r
    backend.DECK_DIRS = [r / "data" / "decks", r / "out"]
    backend.IMAGES = r / "data" / "images"
    backend.INLINE_JOBS = True
    backend.DEFAULT_WORKERS = 1
    backend.IMAGE_IDS = set(image_ids) if image_ids is not None else None
    backend.PROGRESS_HOOK = (lambda j: progress(json.dumps(j))) if progress is not None else None
    for d in (r / "data" / "decks", r / "out" / "replays", r / "out" / "lab"):
        d.mkdir(parents=True, exist_ok=True)
    backend.reg()


def handle(method: str, path: str, query_json: str, body_json: str) -> str:
    try:
        status, obj = backend.dispatch(method, path, json.loads(query_json or "{}"), json.loads(body_json or "{}"))
    except Exception as e:  # noqa: BLE001
        status, obj = 400, {"error": f"{type(e).__name__}: {e}"}
    return json.dumps({"status": status, "body": obj})


def write_file(rel: str, content: str) -> None:
    p = backend.ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def read_file(rel: str) -> str:
    return (backend.ROOT / rel).read_text(encoding="utf-8")


def list_files(prefix: str) -> str:
    base = backend.ROOT / prefix
    if not base.exists():
        return "[]"
    return json.dumps(sorted(str(p.relative_to(backend.ROOT)) for p in base.rglob("*") if p.is_file()))
