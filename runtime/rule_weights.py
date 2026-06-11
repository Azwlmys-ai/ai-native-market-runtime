"""
rule_weights — 规则权重建议（Phase 3e-2：Learning Runtime「淘汰失效模型」雏形）
============================================================================
定位
----
把 Phase 3e 的 `model_effectiveness.json`（有效性快照）转成**可执行的处置建议**：
对每条规则/规则族给出一个 weight 乘子 + 处置标签 + 可解释理由。
这是 PRD 第十三节「learning agent：哪些 edge 已失效」与 Phase 5「自动淘汰失效模型」
的**确定性雏形**——本模块只产出**建议产物**，**默认不接入 live 交易链路**。

为何只建议、不强制（对齐当前 PRD 方向）
----------------------------------------
当前阶段目标是「大量低风险试错获取反馈」，不是过早收紧。所以策略刻意保守：
  * 样本不足(insufficient) → weight=1.0 且标 `explore`：继续试错拿数据，绝不因小样本淘汰。
  * 失效(ineffective)     → weight=0.5 降权，但不归零。
  * 已衰减(decayed)       → weight=0.25 + 标 `retire_candidate`：提示人/Phase5 复核，仍不自动归零。
真正的 enforcement（按 weight 压仓 / 跳过）留给后续 env 门控的独立步骤，
**本轮不改 agent_b 的信号生成/过滤行为**。

确定性策略（硬规则，可解释）
----------------------------
  effectiveness      weight   recommendation
  ----------------   ------   --------------
  effective          1.10     keep         （略加权，鼓励复用有效规则）
  marginal           1.00     keep
  inconclusive       1.00     keep         （全 flat，无信息）
  insufficient       1.00     explore      （样本 < 阈值，需继续试错）
  ineffective        0.50     down_weight
  decayed            0.25     retire_candidate

写出：data/rule_effectiveness.json（建议产物）+ 影子 rule_weights 表（PA_SHADOW_DB 时）。
输入：data/model_effectiveness.json（JSON 事实源；本模块只读它，不直接碰 DB）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from runtime import datastore as _ds

SCHEMA_VERSION = "0.3.5-phase3e-weights"

# effectiveness → (weight, recommendation)
_POLICY = {
    "effective":    (1.10, "keep"),
    "marginal":     (1.00, "keep"),
    "inconclusive": (1.00, "keep"),
    "insufficient": (1.00, "explore"),
    "ineffective":  (0.50, "down_weight"),
    "decayed":      (0.25, "retire_candidate"),
}
_DEFAULT = (1.00, "keep")


def _rationale(entry: dict, recommendation: str) -> str:
    """逐条可解释理由（确定性，给人/agent 看）。"""
    eff = entry.get("effectiveness")
    n = entry.get("n_trades")
    wr = entry.get("win_rate")
    pnl = entry.get("total_realized_pnl")
    decayed = (entry.get("decay") or {}).get("edge_decayed")
    bits = [f"有效性={eff}", f"样本={n}"]
    if wr is not None:
        bits.append(f"胜率={wr}")
    if pnl is not None:
        bits.append(f"总盈亏={pnl}")
    head = "，".join(bits)
    tail = {
        "keep": "维持权重",
        "explore": "样本不足，继续试错收集反馈，不淘汰",
        "down_weight": "失效，降权但保留探索",
        "retire_candidate": "边已衰减，建议人工/后续复核淘汰（仍未自动归零）",
    }.get(recommendation, "")
    return f"{head}；处置={recommendation}（{tail}）" if decayed or recommendation != "keep" else head


def _weigh(entry: dict) -> dict:
    eff = entry.get("effectiveness")
    weight, rec = _POLICY.get(eff, _DEFAULT)
    return {
        "key": entry.get("key"),
        "effectiveness": eff,
        "n_trades": entry.get("n_trades"),
        "win_rate": entry.get("win_rate"),
        "total_realized_pnl": entry.get("total_realized_pnl"),
        "edge_decayed": bool((entry.get("decay") or {}).get("edge_decayed")),
        "weight": weight,
        "recommendation": rec,
        "rationale": _rationale(entry, rec),
    }


def _load_effectiveness(base_dir: Optional[Path]) -> dict:
    base = Path(base_dir) if base_dir else _ds.get_base_dir()
    p = base / "data" / "model_effectiveness.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute(base_dir=None) -> dict:
    """读 model_effectiveness.json → 产出规则权重建议，落盘建议产物 + 影子表。

    返回建议报告 dict。best-effort：建议产物，失败不应中断主流程。
    """
    eff = _load_effectiveness(base_dir)
    by_rule = [_weigh(e) for e in eff.get("by_rule", [])]
    by_family = [_weigh(e) for e in eff.get("by_family", [])]

    retire_candidates = sorted(
        {e["key"] for e in by_rule + by_family if e["recommendation"] == "retire_candidate"})
    down_weighted = sorted(
        {e["key"] for e in by_rule + by_family if e["recommendation"] == "down_weight"})

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enforced": False,  # 显式声明：本产物仅建议，未接入 live 交易链路
        "source_effectiveness_generated_at": eff.get("generated_at"),
        "by_rule": by_rule,
        "by_family": by_family,
        "summary": {
            "n_rules": len(by_rule),
            "retire_candidates": retire_candidates,
            "down_weighted": down_weighted,
        },
    }
    _ds.write_rule_weights(report, base_dir=base_dir)
    return report


def main():
    rep = compute()
    print(json.dumps({
        "enforced": rep["enforced"],
        "summary": rep["summary"],
        "rules": [(e["key"], e["recommendation"], e["weight"]) for e in rep["by_rule"]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
