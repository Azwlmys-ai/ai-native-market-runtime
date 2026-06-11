"""
enforcement — 学习产物 → paper 信号 position_size 强制层（Phase 5：纸面强制层）
============================================================================
定位（对齐 PRD §13「learning agent：淘汰失效模型」+ §11 优先级 4/5「Kelly/Markowitz sizing」
       + Phase 5「动态模型权重 / 自动淘汰失效模型」）
----------------------------------------------------------------------------
前面 Phase 3 把所有 learning 产物都留在 `enforced=False` 的**建议层**：
  * `data/rule_effectiveness.json`（rule_weights）—— 每规则/规则族一个 weight 乘子 + 处置标签；
  * `data/sizing_suggestions.json`（position_sizing）—— 每候选一个 Kelly×regime `sized_fraction`。
本模块把这两个建议**接进 paper 信号链路**：在 orchestrator 汇总 `signals.json` 时、写盘之前，
按学习结论调整每条信号的 `position_size`，让 PRD §5/§6 的「发现→交易→复盘→学习」闭环
真正把学习结果反馈回交易行为（动态权重 + sizing）。

⚠ 安全纪律（与项目 dry-run 纪律一致，不可破坏）
----------------------------------------------------------------------------
  * **默认全关**：两个 env 门控都不设 → 本层是恒等变换，信号一字不改（当前行为零回归）。
  * 只改 `position_size` 一个字段；**不绕过 Agent M 审查、不绕过 executor dry-run**；
    `success` 计数仍由 `EXECUTOR_DRY_RUN` 决定（real 下单与本层无关）。
  * **只降险**（默认）：最终仓位 ≤ 原始仓位，且 ≤ 绝对硬上限 `MAX_SIZE`。
    `PA_ENFORCE_ALLOW_SCALE_UP=1` 才允许 sizing 把仓位放大到原始之上（仍 ≤ MAX_SIZE）。
  * **绝不归零探针**：正仓位的信号至少保留 `SIZING_FLOOR`（PRD：继续低风险试错拿数据，
    不因学习结论把一条信号彻底踢出试错池）。
  * 每条被改信号写入可解释 `enforcement` 证据；整轮写 `data/enforcement_audit.json` + 影子表。

env 门控
----------------------------------------------------------------------------
  PA_ENFORCE_SIZING=1     用 Kelly×regime `sized_fraction` 作为仓位基准（按 signal_uid/market_id join）
  PA_ENFORCE_WEIGHTS=1    用学习 rule weight 乘子缩放仓位（按 learned_rule_match→rule/family join）
  PA_ENFORCE_LEARNING=1   便捷开关：等价同时开上面两个
  PA_SIZING_FLOOR         探针仓位地板（默认 0.005）
  PA_ENFORCE_MAX_SIZE     最终仓位绝对硬上限（默认 0.10）
  PA_ENFORCE_ALLOW_SCALE_UP=1   允许放大到原始仓位之上（默认只降险）

纯确定性、stdlib-only、沙箱可单测；加法产物，门控关时不改任何交易行为。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from runtime import datastore as _ds
from runtime.model_effectiveness import _rule_family  # 复用同一套规则族派生，保证 join 一致

SCHEMA_VERSION = "0.3.12-phase5-enforce"

DEFAULT_SIZING_FLOOR = 0.005
DEFAULT_MAX_SIZE = 0.10


# ---------------------------------------------------------------------------
# env 门控解析
# ---------------------------------------------------------------------------

def _truthy(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def gates() -> dict:
    """读 env → 当前强制配置（纯函数：可被单测显式构造，也被 compute 用）。"""
    combo = _truthy("PA_ENFORCE_LEARNING")
    return {
        "enforce_sizing": combo or _truthy("PA_ENFORCE_SIZING"),
        "enforce_weights": combo or _truthy("PA_ENFORCE_WEIGHTS"),
        "sizing_floor": _env_float("PA_SIZING_FLOOR", DEFAULT_SIZING_FLOOR),
        "max_size": _env_float("PA_ENFORCE_MAX_SIZE", DEFAULT_MAX_SIZE),
        "allow_scale_up": _truthy("PA_ENFORCE_ALLOW_SCALE_UP"),
    }


def any_enabled(cfg: Optional[dict] = None) -> bool:
    cfg = cfg or gates()
    return bool(cfg["enforce_sizing"] or cfg["enforce_weights"])


# ---------------------------------------------------------------------------
# 装载学习产物（事实源 JSON；本模块只读，不碰 DB）
# ---------------------------------------------------------------------------

def _load_json(base_dir: Optional[Path], name: str) -> dict:
    base = Path(base_dir) if base_dir else _ds.get_base_dir()
    p = base / "data" / name
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _weight_index(rule_report: dict) -> dict:
    """{scope: {key: entry}}，scope ∈ rule/family。供按 rule→family 回退查找。"""
    idx = {"rule": {}, "family": {}}
    for scope, items in (("rule", rule_report.get("by_rule")),
                         ("family", rule_report.get("by_family"))):
        for e in items or []:
            k = e.get("key")
            if k is not None:
                idx[scope][str(k)] = e
    return idx


def _sizing_index(sizing_report: dict) -> tuple:
    """({signal_uid: sug}, {market_id: sug})，双键索引供 join。"""
    by_uid, by_mkt = {}, {}
    for s in sizing_report.get("suggestions", []) or []:
        uid = s.get("signal_uid")
        mid = s.get("market_id")
        if uid is not None:
            by_uid[str(uid)] = s
        if mid is not None and str(mid) not in by_mkt:
            by_mkt[str(mid)] = s
    return by_uid, by_mkt


# ---------------------------------------------------------------------------
# 单条信号 join
# ---------------------------------------------------------------------------

def _signal_rule(sig: dict) -> Optional[str]:
    """信号的规则名（与 model_effectiveness 的标签口径一致）。"""
    v = sig.get("learned_rule_match")
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _lookup_weight(sig: dict, widx: dict) -> Optional[dict]:
    """按 rule 精确命中，回退 family。无 learned_rule_match → None（默认 weight=1.0）。"""
    rule = _signal_rule(sig)
    if not rule:
        return None
    hit = widx["rule"].get(rule)
    if hit:
        return {**hit, "matched_scope": "rule"}
    fam = _rule_family(rule)
    hit = widx["family"].get(fam)
    if hit:
        return {**hit, "matched_scope": "family"}
    return None


def _lookup_sizing(sig: dict, by_uid: dict, by_mkt: dict) -> Optional[dict]:
    """优先 pair_id/signal_uid 命中（协整候选），回退 market_id。"""
    for key in (sig.get("pair_id"), sig.get("signal_uid")):
        if key is not None and str(key) in by_uid:
            return {**by_uid[str(key)], "matched_by": "signal_uid"}
    mid = sig.get("market_id")
    if mid is not None and str(mid) in by_mkt:
        return {**by_mkt[str(mid)], "matched_by": "market_id"}
    return None


# ---------------------------------------------------------------------------
# 核心：对一批信号施加强制（纯函数，可单测）
# ---------------------------------------------------------------------------

def apply(signals: list, rule_report: dict, sizing_report: dict, cfg: dict) -> tuple:
    """返回 (new_signals, audit_entries)。门控关 → 原样返回、空 audit。

    顺序：sizing 设模型基准 → weight 乘子缩放 → clamp[floor, max] → 降险上限（默认）。
    只改 position_size；其余字段不动。每条改动写入信号内 `enforcement` 证据。
    """
    if not any_enabled(cfg) or not signals:
        return signals, []

    widx = _weight_index(rule_report) if cfg["enforce_weights"] else {"rule": {}, "family": {}}
    by_uid, by_mkt = _sizing_index(sizing_report) if cfg["enforce_sizing"] else ({}, {})
    floor = float(cfg["sizing_floor"])
    cap = float(cfg["max_size"])

    out, audit = [], []
    for sig in signals:
        if not isinstance(sig, dict):
            out.append(sig)
            continue
        try:
            orig = float(sig.get("position_size", 0.0) or 0.0)
        except (TypeError, ValueError):
            orig = 0.0
        base = orig
        applied = []
        ev = {
            "schema_version": SCHEMA_VERSION,
            "original_position_size": round(orig, 6),
            "applied": applied,
        }

        # 1) sizing：用 Kelly×regime sized_fraction 作为基准（join 命中才改）
        if cfg["enforce_sizing"]:
            sug = _lookup_sizing(sig, by_uid, by_mkt)
            if sug is not None:
                sf = sug.get("sized_fraction")
                if sf is not None:
                    base = float(sf)
                    applied.append("sizing")
                    ev["sizing"] = {
                        "matched_by": sug.get("matched_by"),
                        "sized_fraction": round(float(sf), 6),
                        "kelly_fraction": sug.get("kelly_fraction"),
                        "regime": sug.get("regime"),
                        "regime_scaler": sug.get("regime_scaler"),
                        "variance_source": sug.get("variance_source"),
                    }

        # 2) weight：学习 rule 权重乘子缩放
        weighted = base
        if cfg["enforce_weights"]:
            whit = _lookup_weight(sig, widx)
            if whit is not None:
                try:
                    w = float(whit.get("weight", 1.0))
                except (TypeError, ValueError):
                    w = 1.0
                weighted = base * w
                applied.append("weight")
                ev["weight"] = {
                    "matched_scope": whit.get("matched_scope"),
                    "key": whit.get("key"),
                    "weight": round(w, 6),
                    "recommendation": whit.get("recommendation"),
                    "effectiveness": whit.get("effectiveness"),
                }

        if not applied:
            out.append(sig)
            continue

        # 3) clamp：地板（不归零探针）→ 绝对硬上限
        final = weighted
        if orig > 0:
            final = max(final, floor)
        final = min(final, cap)
        # 4) 降险上限（默认）：最终不超过原始仓位，除非显式允许放大
        if not cfg["allow_scale_up"] and orig > 0:
            final = min(final, orig)
        final = round(max(0.0, final), 6)

        ev["final_position_size"] = final
        new_sig = {**sig, "position_size": final, "enforcement": ev}
        out.append(new_sig)
        audit.append({
            "market_id": sig.get("market_id"),
            "market_name": sig.get("market_name") or sig.get("market"),
            "signal_uid": sig.get("signal_uid"),
            "pair_id": sig.get("pair_id"),
            "source": sig.get("source"),
            "models_used": sig.get("models_used"),
            "learned_rule_match": sig.get("learned_rule_match"),
            "applied": list(applied),
            "original_position_size": round(orig, 6),
            "final_position_size": final,
            "weight": ev.get("weight"),
            "sizing": ev.get("sizing"),
        })
    return out, audit


# ---------------------------------------------------------------------------
# 顶层入口：被 orchestrator 在汇总信号、写盘前调用
# ---------------------------------------------------------------------------

def enforce_signals(signals: list, base_dir=None) -> tuple:
    """读学习产物 → 施加强制 → 落审计产物。返回 (new_signals, report)。

    门控关时：原样返回、不落盘（零副作用 / 零回归）。best-effort：异常由调用方吞掉。
    """
    cfg = gates()
    if not any_enabled(cfg):
        return signals, {"enforced": False, "applied_count": 0, "gates": cfg}

    rule_report = _load_json(base_dir, "rule_effectiveness.json") if cfg["enforce_weights"] else {}
    sizing_report = _load_json(base_dir, "sizing_suggestions.json") if cfg["enforce_sizing"] else {}
    new_signals, audit = apply(signals, rule_report, sizing_report, cfg)

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enforced": True,
        "gates": {
            "enforce_sizing": cfg["enforce_sizing"],
            "enforce_weights": cfg["enforce_weights"],
            "sizing_floor": cfg["sizing_floor"],
            "max_size": cfg["max_size"],
            "allow_scale_up": cfg["allow_scale_up"],
        },
        "n_signals": len(signals),
        "applied_count": len(audit),
        "n_sizing_applied": sum(1 for a in audit if "sizing" in a["applied"]),
        "n_weight_applied": sum(1 for a in audit if "weight" in a["applied"]),
        "source_rule_weights_generated_at": rule_report.get("generated_at"),
        "source_sizing_generated_at": sizing_report.get("generated_at"),
        "adjustments": audit,
    }
    _ds.write_enforcement_audit(report, base_dir=base_dir)
    return new_signals, report


def main():
    # CLI：对当前 signals.json 做一次只读演练（不回写 signals.json），打印审计摘要。
    base = _ds.get_base_dir()
    p = base / "data" / "signals.json"
    signals = []
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            signals = d if isinstance(d, list) else d.get("signals", [])
        except Exception:
            signals = []
    _, report = enforce_signals(signals, base_dir=base)
    print(json.dumps({
        "enforced": report.get("enforced"),
        "gates": report.get("gates"),
        "applied_count": report.get("applied_count"),
        "n_sizing_applied": report.get("n_sizing_applied"),
        "n_weight_applied": report.get("n_weight_applied"),
        "top": [(a["market_id"], a["original_position_size"], a["final_position_size"], a["applied"])
                for a in report.get("adjustments", [])[:8]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
