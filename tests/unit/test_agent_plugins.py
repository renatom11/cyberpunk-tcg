"""``CPTCG_AGENT_PLUGINS``: modules under ``tools/`` register agents into every process that
resolves an agent name, so numpy agents work in harvest and arena workers."""

import sys
from pathlib import Path

from cptcg.agents import base as B


def test_a_plugin_module_is_imported_and_its_agent_resolves(monkeypatch, tmp_path):
    (tmp_path / "s0_dummy_plugin.py").write_text(
        "from cptcg.agents.base import register\n"
        "from cptcg.agents.random_agent import RandomAgent\n"
        "@register\nclass Dummy(RandomAgent):\n    name = 's0-dummy'\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv(B.PLUGINS_ENV, "s0_dummy_plugin")
    B._plugins_loaded.discard("s0_dummy_plugin")
    ag = B.make_agent("s0-dummy", 1)
    assert type(ag).name == "s0-dummy"
    sys.modules.pop("s0_dummy_plugin", None)
    B._plugins_loaded.discard("s0_dummy_plugin")
    B.AGENTS.pop("s0-dummy", None)


def test_tools_is_on_the_path_when_a_plugin_is_named(monkeypatch):
    monkeypatch.setenv(B.PLUGINS_ENV, "")
    B.load_plugins()               # nothing named: nothing imported, no path change
    tools = str(Path(B.__file__).resolve().parents[3] / "tools")
    monkeypatch.setenv(B.PLUGINS_ENV, "cards_model")
    try:
        __import__("numpy")
    except ImportError:
        return
    B.load_plugins()
    assert tools in sys.path
