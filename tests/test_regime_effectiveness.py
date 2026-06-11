"""Phase 3g-loop — regime_effectiveness regime 有效性聚合单测（确定性，numpy-free，不触网络）。

验证：postmortems × regime 标签 join、按 regime 分桶、复用 model_effectiveness 指标、
有效性裁定、无 regime_states 时降级 unknown、compute 落盘。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import regime_effectiveness as re_mod


def _pm(uid, mid, outcome, pnl, regime_hint=None, **extra):
    rec = {
        "postmortem_uid": uid, "canonical_market_id": str(mid),
        "market_name": f"market {mid}", "direction": "YES",
        "outcome": outcome, "realized_pnl": pnl,
        "entry_price": 0.5, "exit_price": 0.6 if outcome == "win" else 0.4,
        "expected_edge": 0.1, "confidence": 70.0,
        "liquidity_issue": 0, "timing_issue": 0, "model_issue": 0,
        "hypothesis_verdict": "confirmed" if outcome == "win" else "refuted",
        "closed_at": f"2026-06-0{uid[-1]}T00:00:00",
    }
    rec.update(extra)
    return rec


def _write_inputs(tmp_path, postmortems, regimes):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    with open(data / "postmortems.jsonl", "w", encoding="utf-8") as f:
        for r in postmortems:
            f.write(json.dumps(r) + "\n")
    if regimes is not None:
        rep = {"schema_version": "x", "model": "hmm", "regimes": regimes}
        (data / "regime_states.json").write_text(json.dumps(rep), encoding="utf-8")
    return data


def test_join_buckets_by_regime(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    pms = [
        _pm("p1", 100, "win", 1.0), _pm("p2", 100, "win", 1.0), _pm("p3", 100, "win", 1.0),
        _pm("p4", 200, "loss", -1.0), _pm("p5", 200, "loss", -1.0), _pm("p6", 200, "loss", -1.0),
    ]
    regimes = [
        {"series_id": "100", "current_regime": "calm"},
        {"series_id": "200", "current_regime": "turbulent"},
    ]
    _write_inputs(tmp_path, pms, regimes)

    rep = re_mod.compute(base_dir=tmp_path)
    assert rep["enforced"] is False
    assert rep["n_postmortems"] == 6
    assert rep["n_regime_matched"] == 6
    by = {e["key"]: e for e in rep["by_regime"]}
    assert set(by.keys()) == {"calm", "turbulent"}
    assert by["calm"]["n_win"] == 3 and by["calm"]["win_rate"] == 1.0
    assert by["calm"]["effectiveness"] == "effective"
    assert by["turbulent"]["n_loss"] == 3
    assert by["turbulent"]["effectiveness"] == "ineffective"


def test_unmatched_market_falls_back_unknown(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    pms = [_pm("p1", 999, "win", 1.0)]
    regimes = [{"series_id": "100", "current_regime": "calm"}]   # 999 无映射
    _write_inputs(tmp_path, pms, regimes)
    rep = re_mod.compute(base_dir=tmp_path)
    assert rep["n_regime_matched"] == 0
    assert rep["by_regime"][0]["key"] == "unknown"


def test_missing_regime_states_all_unknown(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    pms = [_pm("p1", 100, "win", 1.0), _pm("p2", 200, "loss", -1.0)]
    _write_inputs(tmp_path, pms, regimes=None)   # 无 regime_states.json（如主机无 numpy）
    rep = re_mod.compute(base_dir=tmp_path)
    assert rep["n_regimes_seen"] == 0
    assert all(e["key"] == "unknown" for e in rep["by_regime"])


def test_compute_writes_artifact(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    _write_inputs(tmp_path, [_pm("p1", 100, "win", 1.0)],
                  [{"series_id": "100", "current_regime": "calm"}])
    rep = re_mod.compute(base_dir=tmp_path)
    saved = json.loads((tmp_path / "data" / "regime_effectiveness.json").read_text(encoding="utf-8"))
    assert saved["schema_version"] == re_mod.SCHEMA_VERSION
    assert saved["attribution_source"] == "current_regime_proxy"
