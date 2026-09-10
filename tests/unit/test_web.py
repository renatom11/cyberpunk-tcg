"""In-process tests of the web API: play a game via HTTP, undo, replay, reports."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from cptcg.web import server as web


@pytest.fixture(scope="module")
def base():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return json.load(r)


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def test_static_and_lists(base):
    with urllib.request.urlopen(base + "/") as r:
        assert b"CYBERPUNK TCG" in r.read()
    decks = get(base, "/api/decks")
    assert any(d["name"] == "Sample Arasaka" for d in decks)
    assert len(get(base, "/api/cards")) == 151


def test_play_undo_and_hidden_information(base):
    decks = [d for d in get(base, "/api/decks") if d["ok"]]
    r = post(base, "/api/games", {"deck_me": decks[0]["path"], "deck_ai": decks[1]["path"], "agent": "random", "seat": 1, "seed": 3})
    gid, v = r["id"], r["view"]
    assert v["human"] == 1 and v["players"][0]["hand"] is None and v["players"][1]["hand"] is not None
    turns = 0
    while not v["over"] and turns < 40:
        opts = v["pending"]["options"]
        assert v["pending"]["player"] == 1
        choice = next((o for o in opts if o["kind"] not in ("Pass",)), opts[0])
        v = post(base, f"/api/games/{gid}/act", {"index": choice["index"], "since": v["log_total"]})
        turns += 1
    assert turns > 5
    before = v["turn"]
    v = post(base, f"/api/games/{gid}/undo", {"since": 0})
    assert v["turn"] <= before and v["pending"]["player"] == 1
    rep = get(base, f"/api/games/{gid}/replay")
    assert rep["actions"] and rep["seed"] == 3
    with pytest.raises(urllib.error.HTTPError):
        post(base, f"/api/games/{gid}/act", {"index": 999})
