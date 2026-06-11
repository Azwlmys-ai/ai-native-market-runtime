"""Phase 3e-2 — rule_weights 权重建议单测（确定性，不触 DB/网络）。

验证策略映射、保守探索语义（insufficient 不淘汰）、summary 汇总、
以及 compute() 读 model_effectiveness.json → 落盘 rule_effectiveness.json。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import rule_weights as rw


def _eff_entry(key, effectiveness, n=5, win_rate=0.5, pnl=0.0, decayed=False):
    return {
        "key": key, "effectiveness": effectiveness, "n_trades": n,
        "win_rate": win_rate, "total_realized_pnl": pnl,
        "decay": {"edge_decayed": decayed},
    }


def test_policy_maps_each_grade():
    cases = {
        "effective": (1.10, "keep"),
        "marginal": (1.00, "keep"),
        "inconclusive": (1.00, "keep"),
        "insufficient": (1.00, "explore"),
        "ineffective": (0.50, "down_weight"),
        "decayed": (0.25, "retire_candidate"),
    }
    for eff, (weight, rec) in cases.items():
        out = rw._weigh(_eff_entry("r", eff))
        assert out["weight"] == weight, eff
        assert out["recommendation"] == rec, eff


def test_insufficient_is_not_retired():
    # 保守探索：样本不足绝不淘汰，权重保持 1.0
    out = rw._weigh(_eff_entry("rare", "insufficient", n=1))
    assert out["weight"] == 1.00
    assert out["recommendation"] == "explore"


def test_compute_summary_lists_candidates(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    eff = {
        "generated_at": "2026-06-05T00:00:00Z",
        "by_rule": [
            _eff_entry("mid_range_GTA_VI", "ineffective", n=8, win_rate=0.1, pnl=-200.0),
            _eff_entry("mid_range_NHL", "decayed", n=6, win_rate=0.3, pnl=-10.0, decayed=True),
            _eff_entry("highprob_NBA", "effective", n=5, win_rate=0.8, pnl=300.0),
            _eff_entry("rare_rule", "insufficient", n=1),
        ],
        "by_family": [],
        "by_agent": [],
    }
    (data / "model_effectiveness.json").write_text(json.dumps(eff), encoding="utf-8")

    rep = rw.compute(base_dir=tmp_path)
    assert rep["enforced"] is False
    assert rep["schema_version"] == rw.SCHEMA_VERSION
    assert rep["summary"]["retire_candidates"] == ["mid_range_NHL"]
    assert rep["summary"]["down_weighted"] == ["mid_range_GTA_VI"]
    # 落盘建议产物
    saved = json.loads((data / "rule_effectiveness.json").read_text(encoding="utf-8"))
    assert saved["enforced"] is False
    assert len(saved["by_rule"]) == 4


def test_compute_empty_when_no_effectiveness_file(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    (tmp_path / "data").mkdir()
    rep = rw.compute(base_dir=tmp_path)
    assert rep["by_rule"] == []
    assert rep["summary"]["retire_candidates"] == []
