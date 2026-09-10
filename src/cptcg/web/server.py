"""Local web server: a thin HTTP layer over ``cptcg.web.backend.dispatch``."""

from __future__ import annotations

import json
import mimetypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cptcg.web import backend
from cptcg.web.backend import *  # noqa: F401,F403  (tests and tools reach ROOT, DECK_DIRS, Game... through here)


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

    def _handle(self, method: str, body: dict) -> None:
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            status, obj = backend.dispatch(method, u.path, q, body)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500 if method == "GET" else 400)
        if status == 204:
            self.send_response(204)
            self.end_headers()
            return
        if isinstance(obj, dict) and "__file__" in obj:
            return self._file(Path(obj["__file__"]))
        if status == 404 and obj == {"error": "not found"}:
            return self.send_error(404)
        self._json(obj, status)

    def do_GET(self) -> None:
        self._handle("GET", {})

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        self._handle("POST", body)


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    backend.reg()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"cptcg web client: http://{host}:{port}/   (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
