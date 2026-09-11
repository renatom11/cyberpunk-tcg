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
def base(tmp_path_factory):
    """The server, with the archetype, knowledge and hall-of-fame stores pointed at a temporary
    directory so no test writes into the user's real out/ stores."""
    from cptcg.deck import archetypes, hall_of_fame, knowledge
    from cptcg.web import backend
    stores = tmp_path_factory.mktemp("stores")
    saved = (archetypes.DEFAULT_PATH, knowledge.DEFAULT_PATH, hall_of_fame.DEFAULT_PATH)
    archetypes.DEFAULT_PATH = stores / "archetypes.json"
    knowledge.DEFAULT_PATH = stores / "knowledge.json"
    hall_of_fame.DEFAULT_PATH = stores / "hall_of_fame.json"
    assert backend.archetype_store().path == stores / "archetypes.json"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    archetypes.DEFAULT_PATH, knowledge.DEFAULT_PATH, hall_of_fame.DEFAULT_PATH = saved


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return json.load(r)


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def test_static_and_lists(base):
    with urllib.request.urlopen(base + "/") as r:
        html = r.read().decode()
    assert "CYBERPUNK TCG" in html
    # the report renderer is a separate script that app.js relies on, so it loads first
    assert html.index('src="static/report.js"') < html.index('src="static/app.js"')
    with urllib.request.urlopen(base + "/static/report.js") as r:
        assert b"Report.render" in r.read()
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
    arche = get(base, "/api/archetypes")
    ids = [b["id"] for b in arche["builders"]]
    assert ids[0] == "explorer" and {"legacy", "random"} <= set(ids) and arche["needed"] == 8
    assert isinstance(arche["archetypes"], list) and arche["decks"] >= len(arche["archetypes"])
    for a in arche["archetypes"]:
        assert {"id", "name", "description", "win_rate", "games", "decks", "members"} <= set(a) and a["id"] in ids
    explorer = post(base, "/api/build", {"mode": "explorer", "legends": sample["legends"], "seed": 5})
    assert explorer["ok"] and explorer["legends"] == sample["legends"]
    if arche["archetypes"]:
        learned = post(base, "/api/build", {"mode": arche["archetypes"][0]["id"], "seed": 6})
        assert learned["ok"] and len(learned["legends"]) == 3

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
    again = get(base, f"/api/deck?path={saved['path']}")
    assert again["main"] == built["main"]
    # The builder's label survives the build → save → load round trip.
    assert built["meta"]["generated"] and again["meta"] == built["meta"] == saved["meta"]
    if built["meta"].get("archetype_id"):
        assert again["meta"]["archetype"] == built["meta"]["archetype"]
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
    assert rep["version"] == 2 and rep["summary"] and rep["info"]["games_per_pair"] == 4
    assert rep["decks"][0]["path"] == decks[0] and rep["decks"][0]["profile"]["cards"] >= 40
    assert any(x["id"] == job["id"] for x in get(base, "/api/jobs"))
    # A finished job carries structural progress: a phase sentence, every matchup counted, nothing left.
    p = j["progress"]
    assert p["phase"] and p["step"] == p["steps"] == 1 and p["unit"] == "matchups"
    assert p["remaining_min"] == p["remaining_max"] == 0 and p["done"] == 4 == j["games"]
    # A tournament of hand-built decks teaches the (temporary) archetype store and, once it has
    # clusters, labels each deck with its nearest archetype; the response always carries the key.
    assert all("nearest" in d for d in rep["decks"]) and rep["how_played"].startswith("Every matchup")
    assert "expected" in rep and len(rep["expected"]) == 2
    # An archetype id the store does not know is refused before a job card exists.
    with pytest.raises(urllib.error.HTTPError) as ex:
        post(base, "/api/jobs", {"kind": "league", "archetypes": ["no-such-archetype"], "builders": 2, "generations": 1})
    assert ex.value.code == 400 and "unknown archetype" in ex.value.read().decode()
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


def test_estimate_is_a_range_from_the_job_body(base):
    """POST /api/estimate takes the same body a job does and answers with the games it plays if
    every comparison settles at its first batch (min) and if none does (max)."""
    decks = [d["path"] for d in get(base, "/api/decks") if d["ok"]][:4]
    t = post(base, "/api/estimate", {"kind": "tourney", "decks": decks, "games": 200})
    assert t["games_min"] == 6 * 40 and t["games_max"] == 6 * 200 and t["steps"] == 6 and t["unit"] == "matchups"
    assert post(base, "/api/estimate", {"kind": "tourney", "decks": decks, "games": 200, "no_sprt": True})["games_min"] == 6 * 200
    lg = post(base, "/api/estimate", {"kind": "league", "builders": 4, "generations": 2, "steps": 3, "games": 60, "hof": False})
    assert 0 < lg["games_min"] <= lg["games_max"] and lg["steps"] == 2 * (4 * 3 + 6) and lg["unit"] == "steps"
    assert post(base, "/api/estimate", {"kind": "league", "builders": 4, "generations": 2, "steps": 3, "games": 60})["games_max"] >= lg["games_max"]
    g = post(base, "/api/estimate", {"kind": "generate", "count": 5, "screen": 3, "hof_panel": False})
    assert g["games_min"] == g["games_max"] == 5 * 3 * 4 and g["steps"] == 10 and g["unit"] == "decks"
    assert post(base, "/api/estimate", {"kind": "generate", "count": 5, "screen": 0})["games_max"] == 0
    with pytest.raises(urllib.error.HTTPError):
        post(base, "/api/estimate", {"kind": "nope"})


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


def test_site_build_stamps_every_script(tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("build_site", Path(__file__).resolve().parents[2] / "tools/build_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = mod.build(tmp_path / "site")
    html = (tmp_path / "site/index.html").read_text(encoding="utf-8")
    v = m["build"]
    assert f'src="static/report.js?v={v}"' in html and f'src="static/app.js?v={v}"' in html and f'href="static/style.css?v={v}"' in html
    assert (tmp_path / "site/static/report.js").is_file()
    # The browser build copies the stores every job teaches back into the page's engine and its
    # local storage, so archetypes, card values and champions survive a reload.
    boot = (tmp_path / "site/static/boot.js").read_text(encoding="utf-8")
    assert all(f'"out/{name}.json"' in boot for name in ("archetypes", "knowledge", "hall_of_fame"))


def test_a_go_solo_legend_is_lagged_but_the_board_does_not_call_it_stuck(reg):
    """CR 4.5.2 lags a Legend that goes solo, and its keyword lets it attack regardless.

    The rules state and the player's options come apart here, so the board sends both. The LAG
    badge reads `lag_blocks`; if it read `lag` it would tell the player a card that can attack
    right now is stuck, which is the one thing the badge exists to say.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from conftest import Side, board, do, find

    from cptcg.core.actions import Attack, GoSolo
    from cptcg.core.enums import Zone
    from cptcg.web.view import view_state

    s = board(reg, Side(eddies=5, legends=[("T-L1", {"faceup": True}), "T-L5", "T-L6"]),
              Side(gig=[(6, 3)]))
    leg = find(s, "T-L1")
    do(s, GoSolo(leg))
    assert s.i_zone[leg] == Zone.FIELD and s.i_lag[leg] == 1        # the rule still applies
    assert Attack(leg) in s.pending.options                         # and it can still attack

    card = next(c for c in view_state(s, 0, ("me", "you"), [])["players"][0]["field"]
                if c["inst"] == leg)
    assert card["lag"] is True and card["lag_blocks"] is False


def test_an_ordinary_unit_played_this_turn_is_shown_as_stuck(reg):
    """The other half: without a keyword waiving it, Lag does stop the attack, and the badge says so."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from conftest import Side, board, find

    from cptcg.web.view import view_state

    s = board(reg, Side(field=[("T-U3", {"lag": True})]), Side(gig=[(6, 3)]))
    u = find(s, "T-U3")
    card = next(c for c in view_state(s, 0, ("me", "you"), [])["players"][0]["field"]
                if c["inst"] == u)
    assert card["lag"] is True and card["lag_blocks"] is True
