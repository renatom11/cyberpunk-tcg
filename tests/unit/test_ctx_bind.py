"""ops._ctx binds EffectCtx once through a module global instead of importing on every miss."""

import subprocess
import sys
from pathlib import Path

from cptcg.core import effects as fx
from cptcg.core import ops
from cptcg.core.config import DEFAULT_CONFIG
from cptcg.core.enums import Zone
from cptcg.core.state import GameState

ROOT = Path(__file__).resolve().parents[2]


def test_effects_binds_ops_global():
    assert ops._EffectCtx is fx.EffectCtx


def test_ctx_falls_back_to_import_when_effects_not_loaded():
    # A fresh interpreter that imports only ops + registry (never effects): the first _ctx call
    # must still build an EffectCtx via the local import, which in turn binds ops._EffectCtx.
    code = """
import sys
from pathlib import Path
from cptcg.core import ops
from cptcg.cards.registry import Registry
from cptcg.core.config import DEFAULT_CONFIG
from cptcg.core.enums import Zone
from cptcg.core.state import GameState
assert 'cptcg.core.effects' not in sys.modules, 'effects imported too early'
assert ops._EffectCtx is None
reg = Registry.from_files(Path(sys.argv[1]))
s = GameState(DEFAULT_CONFIG, reg, 1)
s.new_instance(0, 0, Zone.DECK)
c = ops._ctx(s, 0)
assert type(c).__name__ == 'EffectCtx', type(c)
assert ops._EffectCtx is not None and type(c) is ops._EffectCtx
assert ops._ctx(s, 0) is c
print('OK')
"""
    r = subprocess.run([sys.executable, "-c", code, str(ROOT / "tests/fixtures/cards_test.json")],
                       cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src")},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "OK"


def test_ctx_cached_per_state_and_fresh_after_clone(reg):
    s = GameState(DEFAULT_CONFIG, reg, 7)
    a = s.new_instance(0, 0, Zone.DECK)
    b = s.new_instance(1, 1, Zone.DECK)
    ca, cb = ops._ctx(s, a), ops._ctx(s, b)
    assert isinstance(ca, fx.EffectCtx) and ca.s is s and ca.inst == a and ca.player == 0
    assert ops._ctx(s, a) is ca and ops._ctx(s, b) is cb and ca is not cb
    t = s.clone()
    ta = ops._ctx(t, a)
    assert ta is not ca and ta.s is t and ta.inst == a
    assert ops._ctx(s, a) is ca                     # the original's cache is untouched
