#!/usr/bin/env python3
"""Generate event_memory_gap_analysis.md from live shared_intelligence state."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_SHARED = Path("/Users/libo/shared_intelligence")
_OUT = Path(__file__).resolve().parent / "event_memory_gap_analysis.md"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _count_events(events_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in events_dir.glob("*_calendar.json"):
        data = json.loads(p.read_text())
        counts[p.name] = len(data.get("events", []))
    return counts


def main() -> int:
    events_dir = _SHARED / "events"
    attributed = _load_jsonl(_SHARED / "trades" / "event_attributed_trades.jsonl")
    obs_count = len(list((_SHARED / "observations").glob("OBS_*.md")))
    hyp_count = len(list((_SHARED / "hypotheses").glob("HYP_*.md")))
    ins_count = len(list((_SHARED / "insights").glob("INS_*.json")))

    event_counts = Counter()
    theme_counts = Counter()
    source_event = Counter()
    for row in attributed:
        for e in row.get("events") or []:
            event_counts[e] += 1
            source_event[(row.get("source"), e)] += 1
        for t in row.get("themes") or []:
            theme_counts[t] += 1

    with_events = sum(1 for r in attributed if r.get("event_count", 0) > 0)
    multi = sum(1 for r in attributed if r.get("event_count", 0) >= 2)
    etf_hits = sum(1 for r in attributed if r.get("source") == "us_etf" and r.get("event_count", 0))
    okx_hits = sum(1 for r in attributed if r.get("source") == "okx" and r.get("event_count", 0))

    min_event = event_counts.most_common()[-1] if event_counts else ("none", 0)
    rarest = min(event_counts.items(), key=lambda x: x[1]) if event_counts else ("none", 0)

    can_hypothesis = multi >= 10 or with_events >= 10

    md = "\n".join([
        "# Event Memory Gap Analysis",
        "",
        f"> Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## 1. 当前事件库最大缺口",
        "",
        "- **CPI 日历**仍为 `proxy:bls_mid_month` 近似日，非 BLS 官方发布日。",
        "- **PPI / VIX / DXY / US10Y / BTC ETF Flows** 尚未入库（PRD Chapter 6 待建）。",
        "- **Fed Speakers** 无结构化日历。",
        f"- 事件文件计数: `{event_counts and dict(_count_events(events_dir))}`",
        "",
        "## 2. 哪类事件样本最少？",
        "",
        f"- 当前归因样本中最少事件类型: **{rarest[0]}** ({rarest[1]} trades)",
        f"- 主题覆盖: `{dict(theme_counts)}`",
        "- Earnings 实际日历已替换 proxy，但 OKX/BTC 与 AVGO 的直接重叠样本仍稀少。",
        "",
        "## 3. 哪类事件最可能对 ETF 有影响？",
        "",
        f"- ETF 命中事件窗口的交易: **{etf_hits}**",
        "- 预期高影响: **NFP / FOMC / CPI**（RATES/INFLATION）+ **AVGO/NVDA EARNINGS**（AI/SEMICONDUCTORS → SOXL/NVDL）",
        f"- 当前 ETF 主要命中: `{dict(Counter(e for (s,e) in source_event if s=='us_etf'))}`",
        "",
        "## 4. 哪类事件最可能对 OKX 有影响？",
        "",
        f"- OKX 命中事件窗口的交易: **{okx_hits}**",
        "- 预期高影响: **FOMC / CPI**（宏观波动）+ **NVDA EARNINGS**（BTC/ETH 联动）",
        f"- 当前 OKX 主要命中: `{dict(Counter(e for (s,e) in source_event if s=='okx'))}`",
        "",
        "## 5. Observation 是否足够升级为 Hypothesis？",
        "",
        f"- Observations on disk: **{obs_count}**",
        f"- Hypotheses: **{hyp_count}** | Insight candidates: **{ins_count}**",
        f"- Multi-event trades: **{multi}** | Event-attributed: **{with_events}**",
        f"- **结论:** {'可进入 Hypothesis 候选（≥10 单事件样本）' if can_hypothesis else '不足 — 需扩大交易样本或放宽周度导出窗口'}",
        "- 升级为 **Insight** 需 ≥30 样本 + 人工统计复核（见 observation_promotion_rules.md）。",
        "",
        "## Next Actions (non-trading)",
        "",
        "1. 用 BLS/FRED API 替换 CPI proxy 日期",
        "2. 入库 PPI + 市场宏观序列",
        "3. 扩展 trade export 历史窗口（不只当前 ISO week）",
        "4. 在 AVGO/NFP 同日窗口积累 ≥30 样本后复核 AI×RATES 交叉主题",
        "",
    ])

    _OUT.write_text(md, encoding="utf-8")
    print(f"Wrote {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
