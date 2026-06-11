"""Phase 5 — enforcement 纸面强制层单测（确定性，numpy-free，不触网络）。

验证：门控关=恒等（零回归）、sizing 替换（signal_uid/market_id join）、weight 压仓、
floor 不归零探针、max 硬上限、默认只降险 / 允许放大、无命中不改、冷启动、
gates env 解析、enforce_signals 落审计产物。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import enforcement as enf


# ---------------------------------------------------------------------------
# 测试用 cfg / 输入构造
# ---------------------------------------------------------------------------

def _cfg(sizing=False, weights=False, floor=0.005, max_size=0.10, scale_up=False):
    return {"enforce_sizing": sizing, "enforce_weights": weights,
            "sizing_floor": floor, "max_size": max_size, "allow_scale_up": scale_up}


def _sig(market_id="m1", position_size=0.05, **extra):
    s = {"market_id": market_id, "market_name": f"mkt {market_id}",
         "direction": "YES", "price": 0.5, "position_size": position_size}
    s.update(extra)
    return s


def _rule_report(by_rule=None, by_family=None):
    return {"by_rule": by_rule or [], "by_family": by_family or []}


def _sizing_report(suggestions):
    return {"suggestions": suggestions}


# ---------------------------------------------------------------------------
# 门控关 = 恒等（零回归）
# ---------------------------------------------------------------------------

def test_gates_off_is_identity():
    sigs = [_sig(position_size=0.05)]
    out, audit = enf.apply(sigs, _rule_report(), _sizing_report([]), _cfg())
    assert out is sigs              # 原对象原样返回
    assert audit == []
    assert "enforcement" not in out[0]


def test_any_enabled():
    assert enf.any_enabled(_cfg(sizing=True)) is True
    assert enf.any_enabled(_cfg(weights=True)) is True
    assert enf.any_enabled(_cfg()) is False


# ---------------------------------------------------------------------------
# sizing 强制
# ---------------------------------------------------------------------------

def test_sizing_join_by_signal_uid_and_derisk_cap():
    # sized_fraction=0.2 但默认只降险 → 不超过原始 0.05
    sig = _sig(market_id="m1", position_size=0.05, signal_uid="u1")
    rep = _sizing_report([{"signal_uid": "u1", "market_id": "m1",
                           "sized_fraction": 0.2, "regime": "calm"}])
    out, audit = enf.apply([sig], _rule_report(), rep, _cfg(sizing=True))
    assert out[0]["position_size"] == 0.05            # 降险封顶到原始
    assert audit[0]["applied"] == ["sizing"]
    assert out[0]["enforcement"]["sizing"]["matched_by"] == "signal_uid"


def test_sizing_join_by_pair_id():
    sig = _sig(market_id="legA", position_size=0.05, pair_id="pair1")
    rep = _sizing_report([{"signal_uid": "pair1", "market_id": "legX",
                           "sized_fraction": 0.02, "regime": "turbulent"}])
    out, _ = enf.apply([sig], _rule_report(), rep, _cfg(sizing=True))
    assert out[0]["position_size"] == 0.02
    assert out[0]["enforcement"]["sizing"]["matched_by"] == "signal_uid"


def test_sizing_join_by_market_id_fallback():
    sig = _sig(market_id="m9", position_size=0.05)
    rep = _sizing_report([{"signal_uid": "u9", "market_id": "m9", "sized_fraction": 0.03}])
    out, _ = enf.apply([sig], _rule_report(), rep, _cfg(sizing=True))
    assert out[0]["position_size"] == 0.03
    assert out[0]["enforcement"]["sizing"]["matched_by"] == "market_id"


def test_sizing_floor_never_zeros_probe():
    # 负边 → sized_fraction=0，但正仓位探针至少保留 floor
    sig = _sig(market_id="m1", position_size=0.05, signal_uid="u1")
    rep = _sizing_report([{"signal_uid": "u1", "market_id": "m1", "sized_fraction": 0.0}])
    out, _ = enf.apply([sig], _rule_report(), rep, _cfg(sizing=True, floor=0.005))
    assert out[0]["position_size"] == 0.005


def test_sizing_scale_up_allowed_respects_max():
    sig = _sig(market_id="m1", position_size=0.05, signal_uid="u1")
    rep = _sizing_report([{"signal_uid": "u1", "market_id": "m1", "sized_fraction": 0.2}])
    out, _ = enf.apply([sig], _rule_report(), rep,
                       _cfg(sizing=True, scale_up=True, max_size=0.10))
    assert out[0]["position_size"] == 0.10            # 放大但被绝对硬上限截断


def test_sizing_no_match_untouched():
    sig = _sig(market_id="zzz", position_size=0.05, signal_uid="nope")
    rep = _sizing_report([{"signal_uid": "u1", "market_id": "m1", "sized_fraction": 0.02}])
    out, audit = enf.apply([sig], _rule_report(), rep, _cfg(sizing=True))
    assert out[0]["position_size"] == 0.05
    assert "enforcement" not in out[0]
    assert audit == []


# ---------------------------------------------------------------------------
# weight 强制
# ---------------------------------------------------------------------------

def test_weight_down_weight_scales_position():
    sig = _sig(position_size=0.08, learned_rule_match="mid_range_GTA_VI")
    rep = _rule_report(by_rule=[{"key": "mid_range_GTA_VI", "weight": 0.5,
                                 "recommendation": "down_weight", "effectiveness": "ineffective"}])
    out, audit = enf.apply([sig], rep, _sizing_report([]), _cfg(weights=True))
    assert out[0]["position_size"] == 0.04            # 0.08 × 0.5
    assert audit[0]["applied"] == ["weight"]
    assert out[0]["enforcement"]["weight"]["matched_scope"] == "rule"
    assert out[0]["enforcement"]["weight"]["recommendation"] == "down_weight"


def test_weight_family_fallback():
    sig = _sig(position_size=0.08, learned_rule_match="mid_range_NHL")
    # 无精确 rule，命中 family=mid_range
    rep = _rule_report(by_family=[{"key": "mid_range", "weight": 0.25,
                                   "recommendation": "retire_candidate"}])
    out, _ = enf.apply([sig], rep, _sizing_report([]), _cfg(weights=True))
    assert out[0]["position_size"] == 0.02            # 0.08 × 0.25
    assert out[0]["enforcement"]["weight"]["matched_scope"] == "family"


def test_weight_keep_derisk_no_increase():
    # effective → weight 1.10，但默认只降险 → 不放大
    sig = _sig(position_size=0.05, learned_rule_match="r1")
    rep = _rule_report(by_rule=[{"key": "r1", "weight": 1.10, "recommendation": "keep"}])
    out, _ = enf.apply([sig], rep, _sizing_report([]), _cfg(weights=True))
    assert out[0]["position_size"] == 0.05            # 不超过原始


def test_weight_no_rule_match_untouched():
    sig = _sig(position_size=0.05)                    # 无 learned_rule_match
    rep = _rule_report(by_rule=[{"key": "r1", "weight": 0.5}])
    out, audit = enf.apply([sig], rep, _sizing_report([]), _cfg(weights=True))
    assert out[0]["position_size"] == 0.05
    assert "enforcement" not in out[0]
    assert audit == []


# ---------------------------------------------------------------------------
# sizing + weight 组合：sizing 设基准，再被 weight 缩放
# ---------------------------------------------------------------------------

def test_sizing_then_weight_compose():
    sig = _sig(market_id="m1", position_size=0.10, signal_uid="u1",
               learned_rule_match="r1")
    srep = _sizing_report([{"signal_uid": "u1", "market_id": "m1", "sized_fraction": 0.08}])
    wrep = _rule_report(by_rule=[{"key": "r1", "weight": 0.5, "recommendation": "down_weight"}])
    out, audit = enf.apply([sig], wrep, srep, _cfg(sizing=True, weights=True))
    # base=0.08 (sizing) → ×0.5 (weight) = 0.04 ≤ floor/max/原始 → 0.04
    assert out[0]["position_size"] == 0.04
    assert set(audit[0]["applied"]) == {"sizing", "weight"}


# ---------------------------------------------------------------------------
# gates env 解析 + 顶层 enforce_signals 落盘
# ---------------------------------------------------------------------------

def test_gates_env_parsing(monkeypatch):
    monkeypatch.delenv("PA_ENFORCE_LEARNING", raising=False)
    monkeypatch.setenv("PA_ENFORCE_SIZING", "1")
    monkeypatch.delenv("PA_ENFORCE_WEIGHTS", raising=False)
    g = enf.gates()
    assert g["enforce_sizing"] is True and g["enforce_weights"] is False
    monkeypatch.setenv("PA_ENFORCE_LEARNING", "true")
    g = enf.gates()
    assert g["enforce_sizing"] is True and g["enforce_weights"] is True


def test_enforce_signals_off_no_side_effects(tmp_path, monkeypatch):
    for k in ("PA_ENFORCE_LEARNING", "PA_ENFORCE_SIZING", "PA_ENFORCE_WEIGHTS"):
        monkeypatch.delenv(k, raising=False)
    sigs = [_sig(position_size=0.05)]
    out, rep = enf.enforce_signals(sigs, base_dir=tmp_path)
    assert out is sigs
    assert rep["enforced"] is False
    assert not (tmp_path / "data" / "enforcement_audit.json").exists()


def test_enforce_signals_writes_audit(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_ENFORCE_LEARNING", raising=False)
    monkeypatch.delenv("PA_ENFORCE_WEIGHTS", raising=False)
    monkeypatch.setenv("PA_ENFORCE_SIZING", "1")
    monkeypatch.setenv("PA_SHADOW_DB", "")            # 不写影子库，仅 JSON
    data = tmp_path / "data"
    data.mkdir()
    (data / "sizing_suggestions.json").write_text(json.dumps(
        {"suggestions": [{"signal_uid": "u1", "market_id": "m1",
                          "sized_fraction": 0.02, "regime": "calm"}]}), encoding="utf-8")
    sigs = [_sig(market_id="m1", position_size=0.05, signal_uid="u1")]
    out, rep = enf.enforce_signals(sigs, base_dir=tmp_path)
    assert out[0]["position_size"] == 0.02
    assert rep["enforced"] is True and rep["applied_count"] == 1
    audit_file = data / "enforcement_audit.json"
    assert audit_file.exists()
    saved = json.loads(audit_file.read_text())
    assert saved["n_sizing_applied"] == 1


def test_cold_start_empty_products(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_ENFORCE_LEARNING", raising=False)
    monkeypatch.setenv("PA_ENFORCE_SIZING", "1")
    monkeypatch.setenv("PA_ENFORCE_WEIGHTS", "1")
    sigs = [_sig(market_id="m1", position_size=0.05, signal_uid="u1",
                 learned_rule_match="r1")]
    out, rep = enf.enforce_signals(sigs, base_dir=tmp_path)   # 无任何产物文件
    assert out[0]["position_size"] == 0.05            # 冷启动：无命中，不改
    assert rep["applied_count"] == 0
