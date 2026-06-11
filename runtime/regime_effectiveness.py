"""
regime_effectiveness — regime 有效性学习聚合器（Phase 3g-loop：regime 学习闭环）
============================================================================
定位（对齐 PRD §13「learning agent 学习：哪个 regime 有效」）
----------------------------------------------------------------------------
继 HMM 市场状态识别（Phase 3g）产出 regime 标签之后，本模块把【已平仓复盘
postmortems】按交易所在市场的 **regime 标签**分组，算出每个 regime 下的胜率 /
盈亏 / edge 兑现 / 问题归因 / 失效信号——回答 PRD 的「哪个 regime 有效」。

与 model_effectiveness（Phase 3e）同骨架，复用其全部指标计算（DRY）；唯一差别是
**分组标签来源 = regime 而非规则/模型**。

regime 标签从哪来（当前真实可用归因 + 诚实代理）
----------------------------------------------
postmortem 经 `canonical_market_id` 关联到该市场**当前** regime（`data/regime_states.json`，
HMM 周期末快照）。注意：这是「当前 regime」作为「开仓时 regime」的**代理**——
当前价格历史短、交易少，尚不持久化逐周期 regime 时间序列。

> 未来升级（teed up，不改本骨架）：持久化逐周期 regime 历史，按 postmortem 的 opened_at
> join 开仓时刻的 regime（regime-at-open），标签来源一换即可，聚合骨架不变。

设计纪律（与 model_effectiveness 一致）
--------------------------------------
* 纯确定性、numpy-free、沙箱可复现（只读 postmortems + regime_states.json）。
* 加法产物：不改审批/执行/学习的任何行为。
* JSON 事实源 data/regime_effectiveness.json + 影子表 regime_effectiveness（PA_SHADOW_DB 时）。
* 只读 postmortems（真实已平仓复盘），天然不碰 dry_run 执行结果。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from runtime import datastore as _ds
from runtime import model_effectiveness as _me   # 复用指标计算（_blank_acc/_accumulate/_finalize）

SCHEMA_VERSION = "0.3.9-phase3g-loop-regime-eff"


# ---------------------------------------------------------------------------
# 装载：postmortems + regime 标签映射
# ---------------------------------------------------------------------------

def _load_postmortems(base_dir: Optional[Path]) -> list:
    """读 postmortems：优先影子表（PA_SHADOW_DB），否则 data/postmortems.jsonl。"""
    if os.environ.get("PA_SHADOW_DB", "").lower() in ("1", "true", "yes"):
        try:
            from runtime import _shadow
            return _shadow._rows("SELECT * FROM postmortems")  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            print(f"[regime_effectiveness] 影子库读取失败，回退 jsonl: {exc}", flush=True)
    base = Path(base_dir) if base_dir else _ds.get_base_dir()
    p = base / "data" / "postmortems.jsonl"
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _load_regime_map(base_dir: Optional[Path]) -> dict:
    """读 data/regime_states.json → {series_id: current_regime}。
    缺文件（如主机无 numpy 未产出）时返回空映射 → 全部归 unknown，诚实降级。"""
    base = Path(base_dir) if base_dir else _ds.get_base_dir()
    p = base / "data" / "regime_states.json"
    if not p.exists():
        return {}
    try:
        rep = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for r in rep.get("regimes", []) or []:
        sid = str(r.get("series_id") or "")
        if sid:
            out[sid] = r.get("current_regime") or "unknown"
    return out


def _regime_for(rec: dict, regime_map: dict) -> str:
    """解析一条 postmortem 的市场 regime 标签。无映射 → unknown。"""
    for key in ("canonical_market_id", "market_id"):
        mid = rec.get(key)
        if mid is not None and str(mid) in regime_map:
            return regime_map[str(mid)]
    return "unknown"


# ---------------------------------------------------------------------------
# 聚合（复用 model_effectiveness 的指标计算）
# ---------------------------------------------------------------------------

def _aggregate_by_regime(records: list, regime_map: dict) -> list:
    buckets: dict = {}
    for rec in records:
        regime = _regime_for(rec, regime_map)
        buckets.setdefault(regime, _me._blank_acc())  # noqa: SLF001
        _me._accumulate(buckets[regime], rec)          # noqa: SLF001
    out = [_me._finalize(k, acc) for k, acc in buckets.items()]  # noqa: SLF001
    out.sort(key=lambda e: (e["n_trades"], e["total_realized_pnl"] or 0), reverse=True)
    return out


# ---------------------------------------------------------------------------
# 顶层入口
# ---------------------------------------------------------------------------

def compute(base_dir=None) -> dict:
    """聚合 postmortems × regime → regime 有效性报告并落盘（JSON 事实源 + 影子表）。"""
    records = _load_postmortems(base_dir)
    regime_map = _load_regime_map(base_dir)
    by_regime = _aggregate_by_regime(records, regime_map)

    n_matched = sum(1 for r in records if _regime_for(r, regime_map) != "unknown")
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution_source": "current_regime_proxy",   # 当前 regime 代理开仓 regime（见模块 docstring）
        "enforced": False,                                # 学习产物，不接入交易链路
        "n_postmortems": len(records),
        "n_regime_matched": n_matched,
        "n_regimes_seen": len(regime_map),
        "by_regime": by_regime,
    }
    _ds.write_regime_effectiveness(report, base_dir=base_dir)
    return report


def main():
    rep = compute()
    print(json.dumps({
        "n_postmortems": rep["n_postmortems"],
        "n_regime_matched": rep["n_regime_matched"],
        "by_regime": [(e["key"], e["n_trades"], e["win_rate"], e["effectiveness"])
                      for e in rep["by_regime"]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
