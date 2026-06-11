"""Cross Market Research Brief — formatting helpers (no trade language)."""

from __future__ import annotations

from typing import Any

from .calendar_align import AlignmentMode

BRIEF_FOOTER = (
    "本报告仅用于研究归因，不构成交易信号，不接入任何交易决策。"
)

BRIEF_TITLE = "Cross Market Research Brief"


def evidence_strength(ev: dict[str, Any]) -> str:
    if ev.get("verdict") == "无法证明" or ev.get("reason"):
        return "无"
    if ev.get("is_same_day_comovement"):
        return "共变（非领先）"
    hit = ev.get("hit_rate") or 0
    corr = abs(ev.get("correlation") or 0)
    if hit > 0.55 and corr > 0.15:
        return "弱至中等"
    if hit > 0.52 and corr > 0.05:
        return "弱"
    return "无"


def enrich_evidence(ev: dict[str, Any], alignment: AlignmentMode) -> dict[str, Any]:
    ev = dict(ev)
    ev["alignment"] = alignment
    ev["is_same_day_comovement"] = alignment == "same_calendar"
    ev["has_lead_lag"] = (
        ev.get("verdict") != "无法证明"
        and not ev.get("reason")
        and alignment != "same_calendar"
        and ev.get("direction") == "driver_leads"
    )
    ev["conclusion_strength"] = evidence_strength(ev)
    return ev


def format_evidence_block(ev: dict[str, Any], label: str = "") -> str:
    prefix = f"**{label}** " if label else ""
    if ev.get("reason"):
        return f"- {prefix}结论强度=无 | 样本不足"
    comove = "是" if ev.get("is_same_day_comovement") else "否"
    lead = "是" if ev.get("has_lead_lag") else "否"
    return (
        f"- {prefix}结论强度={ev.get('conclusion_strength', '无')} | "
        f"样本数={ev.get('sample_count')} | 命中率={ev.get('hit_rate')} | "
        f"相关系数={ev.get('correlation')} | 同日共变={comove} | 具备领先性={lead} | "
        f"对齐={ev.get('alignment', '')}"
    )
