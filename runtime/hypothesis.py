"""
hypothesis — Agent B 研究假设提取（Phase 3c）
============================================================================
把每个 Agent B 信号转成结构化研究假设（hypothesis）：
  方向 / 置信 / 预期边 / 持仓时长 / 核心论点 / 风险 / 失败条件。

形成闭环：hypotheses(signal_uid) → signals → paper_positions → postmortems(signal_uid)。
即「当初的假设」可与「实际结果/复盘」对照。

两档来源：
  * 3c-1 derived（本模块默认）：从现有信号字段确定性派生。方向/置信/预期边/风险是真的；
    持仓时长从 risk_notes 的 end_date 派生；失败条件从 risk_notes 的非流动性风险项派生（偏样板）。
  * 3c-2 agent_b（后续）：agent_b prompt 原生输出 holding_horizon_days / failure_conditions，
    本模块优先采用之（见 build_hypothesis 的 native 优先逻辑）。

写出：data/hypotheses.jsonl（事实源）+ 影子 hypotheses 表。加法、零 live 风险。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from _paths import get_base_dir
from runtime import datastore as _ds

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            d = json.loads(v)
            return d if isinstance(d, list) else [v]
        except Exception:
            return [v]
    return [v]


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    m = _DATE_RE.search(str(s))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d")
    except ValueError:
        return None


def _holding_horizon_days(signal: dict) -> Optional[float]:
    # 3c-2 原生字段优先
    native = _f(signal.get("holding_horizon_days"))
    if native is not None:
        return native
    # 派生：从 risk_notes 的 time_risk(end_date) 到 generated_at 的天数
    end_dt = None
    for note in _as_list(signal.get("risk_notes")):
        if isinstance(note, str) and "end_date" in note:
            end_dt = _parse_date(note)
            if end_dt:
                break
    if end_dt is None:
        ev = signal.get("market_evidence") or {}
        end_dt = _parse_date(ev.get("end_date", "")) if isinstance(ev, dict) else None
    start_dt = _parse_date(signal.get("generated_at") or signal.get("timestamp") or "")
    if end_dt and start_dt:
        days = (end_dt - start_dt).days
        return float(days) if days >= 0 else None
    return None


def _failure_conditions(signal: dict) -> Optional[str]:
    # 3c-2 原生字段优先
    native = signal.get("failure_conditions")
    if native:
        return native if isinstance(native, str) else json.dumps(native, ensure_ascii=False)
    # 派生：取 risk_notes 中描述失败模式的项（strategy/correlation/can fail），排除纯流动性/时间
    fails = []
    for note in _as_list(signal.get("risk_notes")):
        s = str(note)
        low = s.lower()
        if any(k in low for k in ("strategy_risk", "correlation_risk", "can fail", "过拟合", "失效")):
            fails.append(s)
    return "；".join(fails) if fails else None


def build_hypothesis(signal: dict, cycle_id: str = "") -> dict:
    mid = str(signal.get("market_id") or "")
    direction = signal.get("direction")
    signal_uid = _ds.uid(mid, direction,
                         signal.get("generated_at") or signal.get("timestamp"), signal.get("source"))
    chain = _as_list(signal.get("logic_chain"))
    thesis = signal.get("reason") or ("；".join(str(x) for x in chain[:2]) if chain else "")
    native_fail = bool(signal.get("failure_conditions") or signal.get("holding_horizon_days"))
    return {
        "hypothesis_uid": _ds.uid(signal_uid),
        "signal_uid": signal_uid,
        "canonical_market_id": mid,
        "market_name": signal.get("market_name") or (signal.get("market_evidence") or {}).get("market_name"),
        "direction": direction,
        "confidence": _f(signal.get("confidence")),
        "expected_edge": _f(signal.get("expected_value") or signal.get("ev")),
        "holding_horizon_days": _holding_horizon_days(signal),
        "thesis": thesis,
        "risk_summary": "；".join(str(x) for x in _as_list(signal.get("risk_notes"))) or None,
        "failure_conditions": _failure_conditions(signal),
        "source": "agent_b" if native_fail else "derived",
        "cycle_id": cycle_id,
    }


def _seen_uids(hist_path: Path) -> set:
    """从已有 hypotheses.jsonl 收集 hypothesis_uid，用于幂等去重（不依赖 DB）。"""
    seen = set()
    if not hist_path.exists():
        return seen
    try:
        with open(hist_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    seen.add(json.loads(line).get("hypothesis_uid"))
                except Exception:
                    continue
    except Exception:
        pass
    return seen


def generate(base_dir=None, cycle_id: str = "") -> dict:
    """从 data/signals.json（事实源）逐信号生成研究假设。幂等：已生成的 uid 跳过。

    best-effort —— 假设是加法产物，失败不影响主流程。
    """
    base = Path(base_dir) if base_dir else get_base_dir()
    sig_path = base / "data" / "signals.json"
    if not sig_path.exists():
        return {"generated": 0}
    try:
        signals = json.loads(sig_path.read_text(encoding="utf-8"))
    except Exception:
        return {"generated": 0}
    if not isinstance(signals, list):
        return {"generated": 0}

    seen = _seen_uids(base / "data" / "hypotheses.jsonl")
    generated = 0
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        try:
            rec = build_hypothesis(sig, cycle_id=cycle_id)
            if rec["hypothesis_uid"] in seen:
                continue
            _ds.append_hypothesis(rec, base_dir=base_dir)
            seen.add(rec["hypothesis_uid"])
            generated += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[hypothesis] 单条生成失败（跳过）: {exc}", flush=True)
    return {"generated": generated}


def main():
    print(generate())


if __name__ == "__main__":
    main()
