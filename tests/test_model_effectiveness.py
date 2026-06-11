"""Phase 3e — model_effectiveness 聚合器单测（确定性，不触 DB/网络）。

只测纯聚合逻辑：标签派生、胜率/盈亏/edge兑现、有效性裁定、decay 检测、
以及 compute() 走 jsonl 降级路径 + 落盘 data/model_effectiveness.json。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import model_effectiveness as me


def _pm(rule, outcome, pnl, expected_edge=10.0, confidence=80.0,
        closed_at="2026-06-01T00:00:00Z", verdict="confirmed",
        liquidity=False, timing=False, model=False, source="agent_b"):
    return {
        "sig_rule": rule, "sig_source": source,
        "outcome": outcome, "realized_pnl": pnl,
        "expected_edge": expected_edge, "confidence": confidence,
        "closed_at": closed_at, "hypothesis_verdict": verdict,
        "liquidity_issue": liquidity, "timing_issue": timing, "model_issue": model,
        "market_name": "Will bitcoin hit $1m before GTA VI?",
    }


def test_rule_family_strips_market_suffix():
    assert me._rule_family("mid_range_GTA_VI") == "mid_range"
    assert me._rule_family("mid_range_NHL") == "mid_range"
    assert me._rule_family("highprob") == "highprob"


def test_effective_verdict_winning_rule():
    recs = [_pm("mid_range_NHL", "win", 100.0) for _ in range(4)]
    out = me._aggregate_scope(recs, "rule")
    e = next(x for x in out if x["key"] == "mid_range_NHL")
    assert e["n_trades"] == 4
    assert e["win_rate"] == 1.0
    assert e["total_realized_pnl"] == 400.0
    assert e["effectiveness"] == "effective"


def test_ineffective_verdict_losing_rule():
    recs = [_pm("mid_range_GTA_VI", "loss", -50.0) for _ in range(4)]
    out = me._aggregate_scope(recs, "rule")
    e = out[0]
    assert e["effectiveness"] == "ineffective"
    assert e["total_realized_pnl"] == -200.0


def test_insufficient_below_min_samples():
    recs = [_pm("rare_rule", "win", 100.0)]
    e = me._aggregate_scope(recs, "rule")[0]
    assert e["effectiveness"] == "insufficient"


def test_inconclusive_all_flat():
    recs = [_pm("flat_rule", "flat", 0.0) for _ in range(3)]
    e = me._aggregate_scope(recs, "rule")[0]
    assert e["effectiveness"] == "inconclusive"


def test_decay_detection_flags_recent_winrate_drop():
    # 早窗全胜、近窗全负 → 应判 decayed
    early = [_pm("decay_rule", "win", 10.0, closed_at=f"2026-05-0{i}T00:00:00Z") for i in range(1, 5)]
    recent = [_pm("decay_rule", "loss", -10.0, closed_at=f"2026-06-0{i}T00:00:00Z") for i in range(1, 5)]
    e = me._aggregate_scope(early + recent, "rule")[0]
    assert e["decay"]["edge_decayed"] is True
    assert e["effectiveness"] == "decayed"


def test_family_aggregates_across_market_types():
    recs = [_pm("mid_range_NHL", "win", 100.0), _pm("mid_range_GTA_VI", "win", 100.0),
            _pm("mid_range_NBA", "loss", -20.0)]
    fam = me._aggregate_scope(recs, "family")
    assert len(fam) == 1
    assert fam[0]["key"] == "mid_range"
    assert fam[0]["n_trades"] == 3


def test_compute_writes_json_via_jsonl_path(tmp_path, monkeypatch):
    # 确保走 jsonl 降级路径（PA_SHADOW_DB 关）
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    with open(data / "postmortems.jsonl", "w", encoding="utf-8") as f:
        for r in [_pm("mid_range_NHL", "win", 100.0) for _ in range(3)]:
            # jsonl 路径下无 sig_rule，归因降级会用 market_name 解析；这里直接给 hypothesis_source
            r.pop("sig_rule"); r.pop("sig_source")
            r["hypothesis_source"] = "agent_b"
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    rep = me.compute(base_dir=tmp_path)
    assert rep["attribution_source"] == "jsonl_degraded"
    assert rep["n_postmortems"] == 3
    assert (data / "model_effectiveness.json").exists()
    saved = json.loads((data / "model_effectiveness.json").read_text(encoding="utf-8"))
    assert saved["schema_version"] == me.SCHEMA_VERSION
