"""Phase 3f 加固单测：跨周期冷却、降级腿跳过、TOP_K env 覆盖。

均针对 env 门控的协整→信号桥（默认关），加固 enforcement 上线前的边界。
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import cointegration as ci


def _pair_report():
    rng = np.random.default_rng(7)
    b = 0.5 + 0.06 * np.sin(np.linspace(0, 6, 24)) + rng.normal(0, 1e-3, 24)
    a = 1.0 * b + rng.normal(0, 2e-3, 24)
    a[-1] += 0.06
    st = ci.analyze_pair("111", list(a), "222", list(b))
    return {"candidates": [ci._build_signal(st)]}


_META = {"111": {"name": "A", "slug": "a", "yes_price": 0.55, "no_price": 0.45},
         "222": {"name": "B", "slug": "b", "yes_price": 0.50, "no_price": 0.50}}


def test_cooldown_skips_recent_pair_direction():
    rep = _pair_report()
    base = ci.to_pipeline_signals(rep, _META)
    assert len(base) == 2
    # 把其中一腿标记为「近周期已发」→ 该腿被冷却跳过
    leg0 = base[0]
    recent = {(leg0["market_id"], leg0["direction"])}
    out = ci.to_pipeline_signals(rep, _META, recent_keys=recent)
    keys = {(s["market_id"], s["direction"]) for s in out}
    assert (leg0["market_id"], leg0["direction"]) not in keys
    assert len(out) == 1


def test_skip_degraded_drops_priceless_leg():
    rep = _pair_report()
    # 不给 meta → 两腿都无价
    emitted_05 = ci.to_pipeline_signals(rep, market_meta={})       # 旧行为：伪造 0.5
    assert len(emitted_05) == 2 and all(s["price"] == 0.5 for s in emitted_05)
    skipped = ci.to_pipeline_signals(rep, market_meta={}, skip_degraded=True)
    assert skipped == []                                           # 加固：无价腿全跳过


def test_skip_degraded_keeps_priced_leg_only():
    rep = _pair_report()
    one = {"111": _META["111"]}                                    # 只给 111 价
    out = ci.to_pipeline_signals(rep, market_meta=one, skip_degraded=True)
    assert len(out) == 1 and out[0]["market_id"] == "111"


def test_top_k_env_override(monkeypatch):
    assert ci._top_k() == ci.TOP_K
    monkeypatch.setenv("PA_COINT_TOP_K", "3")
    assert ci._top_k() == 3
    monkeypatch.setenv("PA_COINT_TOP_K", "garbage")
    assert ci._top_k() == ci.TOP_K                                 # 非法回退默认


def test_recent_keys_empty_when_shadow_off(monkeypatch, tmp_path):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    assert ci.recent_cointegration_keys(tmp_path, hours=12) == set()
    assert ci.recent_cointegration_keys(tmp_path, hours=0) == set()
