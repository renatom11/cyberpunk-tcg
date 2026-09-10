"""In-process tests of the web API: play a game via HTTP, undo, replay, reports."""
import json
import shutil
import threading
import time
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
    assert any(d["name"] == "Sample Corpos" for d in decks)
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


def test_lab_jobs(base):
    # A tiny tournament between two sample decks with random bots finishes in seconds.
    decks = [d["path"] for d in get(base, "/api/decks") if d["name"].startswith("Sample")][:2]
    job = post(base, "/api/jobs", {"kind": "tourney", "name": "Smoke", "decks": decks, "games": 4, "agent": "random", "seed": 1, "jobs": 1})
    assert job["status"] == "running" and job["kind"] == "tourney"
    for _ in range(600):
        j = get(base, f"/api/jobs/{job['id']}")
        if j["status"] != "running":
            break
        time.sleep(0.1)
    assert j["status"] == "done", j
    assert len(j["reports"]) == 1 and j["reports"][0].startswith("out/lab/smoke-")
    rep = get(base, f"/api/report?file={j['reports'][0]}")
    assert len(rep["decks"]) == 2 and rep["markdown"].startswith("#")
    assert any(x["id"] == job["id"] for x in get(base, "/api/jobs"))
    # Bad input fails the job rather than the server.
    bad = post(base, "/api/jobs", {"kind": "tourney", "decks": decks[:1]})
    for _ in range(50):
        j = get(base, f"/api/jobs/{bad['id']}")
        if j["status"] != "running":
            break
        time.sleep(0.1)
    assert j["status"] == "failed" and "two" in j["error"]
    shutil.rmtree((web.ROOT / rep["file"]).parent, ignore_errors=True)  # the job's directory under out/lab
    shutil.rmtree(web.ROOT / "out" / "lab" / bad_dir(bad["id"]), ignore_errors=True)


def bad_dir(job_id: str) -> str:
    return f"tourney-{job_id}"


def test_job_cancel(base):
    """A running job stops at its next progress line once cancel is requested."""
    decks = [d["path"] for d in get(base, "/api/decks") if d["name"].startswith("Sample")][:3]
    job = post(base, "/api/jobs", {"kind": "tourney", "name": "Cancel me", "decks": decks, "games": 400, "agent": "random", "seed": 2, "jobs": 1})
    time.sleep(0.3)
    post(base, f"/api/jobs/{job['id']}/cancel", {})
    for _ in range(300):
        j = get(base, f"/api/jobs/{job['id']}")
        if j["status"] != "running":
            break
        time.sleep(0.1)
    assert j["status"] == "cancelled", j["status"]
    shutil.rmtree(web.ROOT / "out" / "lab" / f"cancel-me-{job['id']}", ignore_errors=True)
