"""
postmortem — Agent G 复盘引擎（Phase 3a）
============================================================================
逐笔已平仓持仓 → 结构化复盘。利用 2a 的 canonical 身份把【已平仓持仓】
join 回【原始信号】，从而拿到 hypothesis / expected_edge，与实际结果对照。

PRD 复盘字段：hypothesis / expected_edge / actual_result / failure_reason /
             liquidity_issue / timing_issue / model_issue。

两条路径：
  * **确定性 fallback**（默认，沙箱可验）：纯规则从数据算出全部字段，不依赖 LLM。
  * **LLM 增强**（use_llm=True，主机）：仅对 failure_reason 叙述增强，其余字段不变。

写出：data/postmortems.jsonl（事实源）+ 影子 postmortems 表（经 datastore 门面）。
设计为加法：不改审批/执行/学习行为；只新增复盘产物。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from runtime import _shadow
from runtime import datastore as _ds


def _f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _outcome(pnl: Optional[float]) -> str:
    if pnl is None:
        return "flat"
    if pnl > 0:
        return "win"
    if pnl < 0:
        return "loss"
    return "flat"


def _hypothesis_from_signal(signal: Optional[dict], position: dict) -> str:
    if signal:
        reason = signal.get("reason")
        chain = signal.get("logic_chain")
        if isinstance(chain, str):
            try:
                chain = json.loads(chain)
            except Exception:
                chain = [chain]
        parts = []
        if signal.get("direction"):
            parts.append(f"方向={signal.get('direction')}")
        if signal.get("confidence") is not None:
            parts.append(f"置信={signal.get('confidence')}")
        head = "，".join(parts)
        body = reason or (("；".join(chain[:2])) if isinstance(chain, list) and chain else "")
        return (head + "：" + body) if body else (head or "（无 reason）")
    return f"未关联到原始信号（{position.get('market_name') or position.get('canonical_market_id')}）"


def _failure_reason_deterministic(outcome: str, close_reason: str) -> str:
    cr = close_reason or "(无)"
    if outcome == "loss":
        return f"亏损了结：{cr}"
    if outcome == "win":
        return f"盈利了结：{cr}"
    return f"无明显盈亏：{cr}"


# ---------------------------------------------------------------------------
# Phase 3c-2：失败条件对照（「当初说的失败条件是否真发生」）
# ---------------------------------------------------------------------------

def _parse_conditions(failure_conditions) -> list:
    """把 hypothesis.failure_conditions 解析成逐条列表。
    可能是 JSON 数组字符串、'；' 拼接串、原生 list 或 None。"""
    if not failure_conditions:
        return []
    if isinstance(failure_conditions, list):
        items = failure_conditions
    elif isinstance(failure_conditions, str):
        s = failure_conditions.strip()
        items = None
        if s.startswith("["):
            try:
                d = json.loads(s)
                items = d if isinstance(d, list) else None
            except Exception:
                items = None
        if items is None:
            # 退回按中文/英文分号切分
            items = [p for p in re.split(r"[；;]\s*", s) if p.strip()]
    else:
        items = [failure_conditions]
    return [str(x).strip() for x in items if str(x).strip()]


def _classify_condition(cond: str) -> str:
    """把单条失败条件归类，用于与复盘的问题标志（流动性/时机/模型）对照。
    返回 liquidity / timing / model / event 之一（event=方向性/事件性，落在亏损即视为兑现）。"""
    low = cond.lower()
    if any(k in low for k in ("流动性", "liquidity", "滑点", "slippage", "深度", "depth", "成交量")):
        return "liquidity"
    if any(k in low for k in ("时间", "超时", "到期", "结算", "时间窗口", "timeout", "expire",
                              "end_date", "deadline", "跳票", "延期", "推迟")):
        return "timing"
    if any(k in low for k in ("过拟合", "失效", "strategy_risk", "correlation", "相关", "模型",
                              "overfit", "high-price", "learned", "规则")):
        return "model"
    # 其余（事件触发/方向性，如「若 X 队夺冠」「若价格突破」）归为 event
    return "event"


def _review_failure_conditions(conditions: list, outcome: str,
                               liquidity_issue: bool, timing_issue: bool,
                               model_issue: bool) -> dict:
    """对照：当初预测的每条失败条件，结合实际结果判定是否「发生」。

    判定（确定性）：
      * win  → 假设成立，预测的失败条件均未发生（occurred=False）。
      * loss → 至少一条失败兑现；逐条按类别与复盘问题标志对照：
               类别命中对应问题标志 → occurred=True；event 类（方向性/事件）→ 亏损即视为兑现；
               其余无法对应 → occurred=None（未能从复盘信号判定）。
      * flat → 无明显盈亏，occurred=None。
    verdict：no_prediction / confirmed / refuted / loss_unexplained / inconclusive。
    """
    had = len(conditions) > 0
    items = []
    flag = {"liquidity": liquidity_issue, "timing": timing_issue, "model": model_issue}
    for cond in conditions:
        cat = _classify_condition(cond)
        if outcome == "win":
            occurred, basis = False, "盈利了结，假设成立"
        elif outcome == "loss":
            if cat in ("liquidity", "timing", "model") and flag.get(cat):
                occurred, basis = True, f"{cat}_issue"
            elif cat == "event":
                occurred, basis = True, "亏损了结，方向性/事件失败兑现"
            else:
                occurred, basis = None, "无法从复盘信号判定"
        else:  # flat
            occurred, basis = None, "无明显盈亏"
        items.append({"condition": cond, "category": cat,
                      "occurred": occurred, "basis": basis})

    materialized = sum(1 for it in items if it["occurred"] is True)
    if not had:
        verdict = "no_prediction"
    elif outcome == "win":
        verdict = "confirmed"
    elif outcome == "flat":
        verdict = "inconclusive"
    elif materialized > 0:
        verdict = "refuted"
    else:
        verdict = "loss_unexplained"

    return {
        "predicted": conditions,
        "had_predicted_conditions": had,
        "items": items,
        "materialized_count": materialized,
        "verdict": verdict,
    }


def build_postmortem(position: dict, signal: Optional[dict], use_llm: bool = False,
                     hypothesis: Optional[dict] = None) -> dict:
    """从一条已平仓持仓 + 可选原始信号 + 可选研究假设，构建结构化复盘记录（确定性）。

    Phase 3c-2：若传入 hypothesis，则把其 failure_conditions 与实际结果对照，
    产出 failure_conditions_review + hypothesis_verdict（「当初说的失败条件是否真发生」）。
    """
    pnl = _f(position.get("realized_pnl"))
    outcome = _outcome(pnl)
    confidence = _f(signal.get("confidence")) if signal else None
    expected_edge = _f(signal.get("expected_value")) if signal else None
    close_reason = position.get("close_reason") or ""

    # 问题归因（确定性规则）
    risk_notes = signal.get("risk_notes") if signal else None
    if isinstance(risk_notes, str):
        rn_text = risk_notes
    else:
        rn_text = json.dumps(risk_notes, ensure_ascii=False) if risk_notes else ""
    liquidity_issue = ("liquidity" in rn_text.lower()) or \
                      (position.get("price_source") in ("missing", "entry_price_fallback"))
    timing_issue = any(k in close_reason for k in ("时间", "超时", "time", "timeout", "expire"))
    # 模型问题：高置信却亏损 → 模型高估
    model_issue = bool(confidence is not None and confidence >= 70 and outcome == "loss")

    failure_reason = _failure_reason_deterministic(outcome, close_reason)
    source = "deterministic"

    if use_llm:
        enriched = _llm_failure_reason(position, signal, outcome, close_reason)
        if enriched:
            failure_reason = enriched
            source = "llm"

    # Phase 3c-2：失败条件对照。优先用 hypothesis.failure_conditions，
    # 退回信号原生 failure_conditions（B prompt 原生字段）。
    fc_raw = (hypothesis or {}).get("failure_conditions")
    if not fc_raw and signal:
        fc_raw = signal.get("failure_conditions")
    conditions = _parse_conditions(fc_raw)
    fc_review = _review_failure_conditions(
        conditions, outcome, bool(liquidity_issue), bool(timing_issue), model_issue)

    rec = {
        "postmortem_uid": _ds.uid(position.get("position_uid")),
        "position_uid": position.get("position_uid"),
        "canonical_market_id": position.get("canonical_market_id"),
        "market_name": position.get("market_name"),
        "direction": position.get("direction"),
        "signal_uid": (signal or {}).get("signal_uid"),
        "hypothesis": _hypothesis_from_signal(signal, position),
        "expected_edge": expected_edge,
        "confidence": confidence,
        "entry_price": _f(position.get("entry_price")),
        "exit_price": _f(position.get("exit_price")),
        "realized_pnl": pnl,
        "outcome": outcome,
        "failure_reason": failure_reason,
        "liquidity_issue": bool(liquidity_issue),
        "timing_issue": bool(timing_issue),
        "model_issue": model_issue,
        # Phase 3c-2：失败条件对照
        "hypothesis_uid": (hypothesis or {}).get("hypothesis_uid"),
        "hypothesis_source": (hypothesis or {}).get("source"),
        "failure_conditions_review": fc_review,
        "hypothesis_verdict": fc_review["verdict"],
        "source": source,
        "closed_at": position.get("closed_at"),
    }
    return rec


def _llm_failure_reason(position: dict, signal: Optional[dict], outcome: str,
                        close_reason: str) -> Optional[str]:
    """主机路径：用 LLM 对 failure_reason 做叙述增强。沙箱/无 LLM 时返回 None。"""
    try:
        from llm_helper import call_llm_sync
    except Exception:
        return None
    try:
        prompt = (
            "你是交易复盘分析师。基于以下一笔已平仓交易，用一句话给出失败/成功的核心原因，"
            "聚焦流动性/时机/模型三类问题中最相关的一个，简体中文：\n"
            f"市场：{position.get('market_name')}\n方向：{position.get('direction')}\n"
            f"结果：{outcome}，realized_pnl={position.get('realized_pnl')}\n"
            f"平仓原因：{close_reason}\n原始假设：{_hypothesis_from_signal(signal, position)}\n"
        )
        out = call_llm_sync("agent_g", prompt)
        return out.strip()[:500] if out else None
    except Exception:
        return None


def generate(base_dir=None, use_llm: bool = False, limit: int = 500) -> dict:
    """对所有【已平仓但未复盘】的持仓逐笔生成复盘。幂等：已复盘的不重做。

    返回 {"generated": n}。best-effort —— 复盘是加法产物，失败不应影响主流程。
    """
    generated = 0
    try:
        rows = _shadow.closed_positions_without_postmortem()
    except Exception as exc:  # noqa: BLE001
        print(f"[postmortem] 读已平仓持仓失败（非致命）: {exc}", flush=True)
        return {"generated": 0}

    for pos in rows[:limit]:
        try:
            signal = _shadow.latest_signal_for(pos.get("canonical_market_id"), pos.get("direction"))
            # Phase 3c-2：按 signal_uid 取研究假设，供失败条件对照
            hypothesis = None
            try:
                hypothesis = _shadow.hypothesis_for_signal((signal or {}).get("signal_uid"))
            except Exception:
                hypothesis = None
            rec = build_postmortem(pos, signal, use_llm=use_llm, hypothesis=hypothesis)
            _ds.append_postmortem(rec, base_dir=base_dir)
            generated += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[postmortem] 单笔复盘失败（跳过）: {exc}", flush=True)
    return {"generated": generated}


def main():
    import os
    use_llm = os.environ.get("PA_POSTMORTEM_LLM", "").lower() in ("1", "true", "yes")
    print(generate(use_llm=use_llm))


if __name__ == "__main__":
    main()
