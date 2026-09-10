"""In-process tests of the web API: play a game via HTTP, undo, replay, reports."""
import json
import threading
import urllib.error
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


def test_deck_builder_endpoints(base, tmp_path):
    sample = get(base, "/api/deck?path=data/decks/sample_corpos.json")
    assert sample["ok"] and sample["size"] == 40 and len(sample["legends"]) == 3
    assert sum(sample["ram"].values()) > 0

    # Validation reports RAM limits and errors without touching disk.
    v = post(base, "/api/validate", {"name": "x", "legends": sample["legends"][:2], "main": sample["main"]})
    assert not v["ok"] and any("3 Legends" in e for e in v["errors"])

    # AI builds are legal decks; keeping the Legends keeps them.
    built = post(base, "/api/build", {"mode": "heuristic", "legends": sample["legends"], "seed": 3})
    assert built["ok"] and built["legends"] == sample["legends"] and 40 <= built["size"] <= 50
    rnd = post(base, "/api/build", {"mode": "random", "seed": 4})
    assert rnd["ok"] and len(rnd["legends"]) == 3
    names = [s["name"] for s in get(base, "/api/strategies")]
    assert {"aggro", "control", "economy", "gig", "synergy", "balanced", "legacy", "random"} <= set(names)
    aggro = post(base, "/api/build", {"mode": "aggro", "legends": sample["legends"], "seed": 5})
    assert aggro["ok"] and aggro["legends"] == sample["legends"]

    # Saving writes a loadable file; a second save without overwrite is refused.
    orig = web.DECK_DIRS[0]
    web.DECK_DIRS[0] = tmp_path
    try:
        _check_save(base, tmp_path, built)
    finally:
        web.DECK_DIRS[0] = orig


def _check_save(base, tmp_path, built):
    saved = post(base, "/api/decks", dict(built, name="My Build!"))
    assert saved["path"].endswith("my-build.json") and (tmp_path / "my-build.json").exists()
    assert get(base, f"/api/deck?path={saved['path']}")["main"] == built["main"]
    req = urllib.request.Request(base + "/api/decks", data=json.dumps(dict(built, name="My Build!")).encode(),
                                 headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as ex:
        urllib.request.urlopen(req)
    assert ex.value.code == 409
    illegal = urllib.request.Request(base + "/api/decks", data=json.dumps({"name": "bad", "legends": [], "main": {}}).encode(),
                                     headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as ex:
        urllib.request.urlopen(illegal)
    assert ex.value.code == 400
