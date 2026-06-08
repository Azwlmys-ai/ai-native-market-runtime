"""Merge multi-agent signals for Agent M review (minimal consolidation layer).

Agent B signals come from intelligence_report.json; D/E/F/H/J/K append to
signals.json before orchestrator consolidate runs. This module merges them
without letting non-B agents override B on duplicate keys.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

# Agents that append to signals.json before consolidate (non-B producers).
NON_B_AGENT_SOURCES = frozenset({
    "agent_d",
    "agent_e",
    "agent_f",
    "agent_h",
    "agent_j",
    "agent_k",
    "agent_k_v2",
})

AGENT_B_SOURCE = "agent_b"

DEFAULT_MAX_TOTAL_SIGNALS = 20
DEFAULT_MAX_PER_NON_B_AGENT = 3
DEFAULT_COINT_SIGNAL_CAP = 8
COINTEGRATION_SOURCE = "cointegration"


def parse_signal_time(value) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def is_signal_fresh(signal: dict, max_age_seconds: int, now_ts: Optional[float] = None) -> bool:
    if max_age_seconds < 0:
        return True
    ts = parse_signal_time(signal.get("generated_at") or signal.get("timestamp"))
    if ts is None:
        return False
    now = now_ts if now_ts is not None else datetime.now().timestamp()
    return (now - ts) <= max_age_seconds


def source_agent_id(signal: dict) -> str:
    raw = signal.get("source_agent") or signal.get("source") or "unknown"
    return str(raw).lower()


def is_agent_b_signal(signal: dict) -> bool:
    return source_agent_id(signal) == AGENT_B_SOURCE


def dedup_key(signal: dict) -> tuple:
    market_id = str(
        signal.get("market_id")
        or signal.get("market_slug")
        or signal.get("market")
        or signal.get("market_name")
        or ""
    ).strip().lower()
    outcome = str(signal.get("direction") or signal.get("side") or "").strip().upper()
    if not outcome and signal.get("strategy") == "risk_free_arbitrage":
        outcome = "ARB"
    if signal.get("strategy") == "risk_free_arbitrage":
        action = "arb"
    else:
        action = str(signal.get("action") or "open").strip().lower()
    return (market_id, outcome, action)


def confidence_score(signal: dict) -> float:
    try:
        return float(signal.get("confidence", 0))
    except (TypeError, ValueError):
        return 0.0


def tag_signal(
    signal: dict,
    *,
    source_agent: str,
    signal_origin: str,
    generated_cycle_id: str,
    signal_merge_reason: str,
) -> dict:
    out = dict(signal)
    out["source_agent"] = source_agent
    out["signal_origin"] = signal_origin
    out["generated_cycle_id"] = generated_cycle_id
    out["signal_merge_reason"] = signal_merge_reason
    if not out.get("source"):
        out["source"] = source_agent
    return out


def filter_fresh_non_b_from_file(
    signals: list,
    max_age_seconds: int,
    now_ts: Optional[float] = None,
    cycle_id: str = "",
) -> list:
    """Return fresh, non-B signals appended by D/E/F/H/J/K for the current cycle."""
    out = []
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        src = source_agent_id(sig)
        if src not in NON_B_AGENT_SOURCES:
            continue
        sig_cycle = str(sig.get("generated_cycle_id") or "")
        if cycle_id and sig_cycle and sig_cycle != cycle_id:
            continue
        if not is_signal_fresh(sig, max_age_seconds, now_ts=now_ts):
            continue
        out.append(sig)
    return out


def is_cointegration_signal(signal: dict) -> bool:
    return source_agent_id(signal) == COINTEGRATION_SOURCE


def _cointegration_rank_key(signal: dict) -> tuple:
    """Lower tuple = higher priority for cointegration probe selection."""
    research = signal.get("research_candidate")
    if research is None:
        research = signal.get("tier") == "research"
    ev = signal.get("evidence") or {}
    try:
        zscore = abs(float(ev.get("zscore") or 0))
    except (TypeError, ValueError):
        zscore = 0.0
    return (
        -int(bool(research)),
        -confidence_score(signal),
        -zscore,
    )


def cap_cointegration_probe_signals(
    signals: list,
    cap: int = DEFAULT_COINT_SIGNAL_CAP,
) -> tuple[list, dict]:
    """Cap cointegration probe signals with priority sort + dedup."""
    candidate_total = len(signals)
    if cap <= 0:
        stats = {
            "candidate_total": candidate_total,
            "selected": 0,
            "dropped": candidate_total,
            "cap": cap,
        }
        return [], stats

    best_by_key: dict[tuple, dict] = {}
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        key = dedup_key(sig)
        existing = best_by_key.get(key)
        if existing is None or _cointegration_rank_key(sig) < _cointegration_rank_key(existing):
            best_by_key[key] = sig

    ranked = sorted(best_by_key.values(), key=_cointegration_rank_key)
    selected = ranked[:cap]
    stats = {
        "candidate_total": candidate_total,
        "selected": len(selected),
        "dropped": candidate_total - len(selected),
        "cap": cap,
    }
    return selected, stats


def _signal_priority_rank(signal: dict) -> tuple:
    """Lower = keep first when applying max_total cap."""
    src = source_agent_id(signal)
    if src == AGENT_B_SOURCE:
        tier = 0
    elif src == COINTEGRATION_SOURCE:
        tier = 2
    else:
        tier = 1
    return (tier, -confidence_score(signal))


def apply_max_total_cap(signals: list, max_total: int) -> list:
    """Trim merged signals to max_total while preserving source priority."""
    if max_total <= 0 or len(signals) <= max_total:
        return list(signals)
    ranked = sorted(signals, key=_signal_priority_rank)
    return ranked[:max_total]


def cap_per_non_b_agent(signals: list, max_per_agent: int = DEFAULT_MAX_PER_NON_B_AGENT) -> list:
    """Keep at most max_per_agent signals per non-B source (highest confidence first)."""
    if max_per_agent <= 0:
        return []
    buckets: dict[str, list] = {}
    for sig in signals:
        buckets.setdefault(source_agent_id(sig), []).append(sig)
    capped = []
    for _src, group in buckets.items():
        group.sort(key=confidence_score, reverse=True)
        capped.extend(group[:max_per_agent])
    return capped


def merge_signals(
    b_signals: list,
    non_b_signals: list,
    *,
    max_total: int = DEFAULT_MAX_TOTAL_SIGNALS,
    cycle_id: str = "",
) -> list:
    """Merge B + non-B with dedup. B wins on key collision; else higher confidence."""
    merged: dict[tuple, dict] = {}

    for sig in b_signals:
        if not isinstance(sig, dict):
            continue
        tagged = tag_signal(
            sig,
            source_agent=AGENT_B_SOURCE,
            signal_origin=sig.get("signal_origin") or "intelligence_report",
            generated_cycle_id=cycle_id or sig.get("generated_cycle_id") or "",
            signal_merge_reason=sig.get("signal_merge_reason") or "agent_b_primary",
        )
        merged[dedup_key(tagged)] = tagged

    non_b_sorted = sorted(non_b_signals, key=confidence_score, reverse=True)
    for sig in non_b_sorted:
        if not isinstance(sig, dict):
            continue
        src = source_agent_id(sig)
        tagged = tag_signal(
            sig,
            source_agent=src,
            signal_origin="signals_json_append",
            generated_cycle_id=cycle_id or sig.get("generated_cycle_id") or "",
            signal_merge_reason="merged_non_b_agent",
        )
        key = dedup_key(tagged)
        existing = merged.get(key)
        if existing is not None:
            if is_agent_b_signal(existing):
                continue
            if confidence_score(tagged) <= confidence_score(existing):
                continue
        merged[key] = tagged

    result = list(merged.values())
    # B-first ordering: all B signals, then non-B by confidence.
    result.sort(
        key=lambda s: (
            0 if is_agent_b_signal(s) else 1,
            -confidence_score(s),
        ),
    )
    if max_total > 0 and len(result) > max_total:
        # Always keep all B signals if possible; trim non-B tail.
        b_only = [s for s in result if is_agent_b_signal(s)]
        non_b_only = [s for s in result if not is_agent_b_signal(s)]
        if len(b_only) >= max_total:
            result = b_only[:max_total]
        else:
            room = max_total - len(b_only)
            result = b_only + non_b_only[:room]
    return result


def consolidate_merge(
    b_signals: list,
    signals_file_content: list,
    *,
    max_age_seconds: int,
    max_total: int = DEFAULT_MAX_TOTAL_SIGNALS,
    max_per_non_b_agent: int = DEFAULT_MAX_PER_NON_B_AGENT,
    cycle_id: str = "",
    now_ts: Optional[float] = None,
) -> list:
    """Full pipeline: fresh non-B from file → per-agent cap → merge with B."""
    fresh_non_b = filter_fresh_non_b_from_file(
        signals_file_content,
        max_age_seconds,
        now_ts=now_ts,
        cycle_id=cycle_id,
    )
    capped_non_b = cap_per_non_b_agent(fresh_non_b, max_per_agent=max_per_non_b_agent)
    return merge_signals(
        b_signals,
        capped_non_b,
        max_total=max_total,
        cycle_id=cycle_id,
    )
