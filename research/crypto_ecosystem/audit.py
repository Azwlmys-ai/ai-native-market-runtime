"""Crypto Ecosystem data availability audit — read-only."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from .config import AUDIT_SYMBOLS
from .data_utils import (
    bars_to_daily,
    daily_returns,
    detect_gaps,
    detect_split_anomalies,
    fetch_yahoo_daily,
    load_local_daily,
    load_okx_hourly,
)
from .lead_lag_offline import run_lead_lag
from .longbridge_probe import (
    fetch_history,
    probe_cp00048_constituents,
    probe_history_window,
    probe_quote,
    probe_static,
)
from .paths import (
    AUDIT_JSON,
    LEAD_LAG_JSON,
    MIN_DAILY_SAMPLES,
    REPORTS_DIR,
    RESEARCH_ROOT,
)


def _research_value(sym: dict[str, Any]) -> str:
    daily_n = sym.get("daily", {}).get("count", 0)
    if daily_n < MIN_DAILY_SAMPLES:
        return "LOW"
    gaps = sym.get("gaps", {}).get("has_material_gaps", False)
    splits = sym.get("splits", {}).get("likely_split_issues", False)
    h1 = sym.get("hourly", {}).get("available", False)
    m5 = sym.get("five_min", {}).get("available", False)
    if gaps or splits:
        return "MEDIUM"
    if daily_n >= 500 and h1 and m5:
        return "HIGH"
    if daily_n >= 500:
        return "MEDIUM-HIGH"
    return "MEDIUM"


def audit_symbol(sym) -> dict[str, Any]:
    row: dict[str, Any] = {
        "ticker": sym.ticker,
        "layer": sym.layer,
        "longbridge_symbol": sym.longbridge_symbol,
    }

    # LongBridge quote
    if sym.longbridge_symbol:
        q = probe_quote(sym.longbridge_symbol)
        row["quote"] = q
        row["collectible_lb"] = q.get("ok", False)
        static = probe_static(sym.longbridge_symbol)
        row["static"] = static
    else:
        row["collectible_lb"] = False

    # Daily series — Yahoo/local first (faster); LongBridge only for CP00048 / LB-only symbols
    daily_bars: list[dict] = []
    daily_source = "none"
    lb_daily_note: str | None = None
    if sym.local_json:
        daily_bars = load_local_daily(sym.ticker, sym.local_json)
        if daily_bars:
            daily_source = "local_shared_intelligence"
    if not daily_bars and sym.yahoo_ticker:
        daily_bars = fetch_yahoo_daily(sym.yahoo_ticker)
        if daily_bars:
            daily_source = "yahoo"
    if not daily_bars and sym.longbridge_symbol:
        hist = probe_history_window(sym.longbridge_symbol, "1d", date(2020, 1, 1), date.today())
        if hist.get("ok") and hist.get("bars"):
            daily_bars = bars_to_daily(hist["bars"])
            daily_source = "longbridge"
            if hist.get("count", 0) >= 1000:
                lb_daily_note = "longbridge_daily_capped_1000"
        else:
            lb_daily_note = hist.get("error")

    row["daily"] = {
        "source": daily_source,
        "count": len(daily_bars),
        "earliest": daily_bars[0]["date"] if daily_bars else None,
        "latest": daily_bars[-1]["date"] if daily_bars else None,
        "note": lb_daily_note,
    }
    row["gaps"] = detect_gaps(daily_bars)
    row["splits"] = detect_split_anomalies(daily_bars)

    # Hourly / 5m — probe recent window only (audit availability, not full backfill)
    h1_bars: list[dict] = []
    m5_bars: list[dict] = []
    if sym.longbridge_symbol and sym.ticker not in ("BTC", "ETH", "SOL"):
        h1 = probe_history_window(sym.longbridge_symbol, "60m", date(2025, 11, 1), date.today())
        m5 = probe_history_window(sym.longbridge_symbol, "5m", date(2026, 5, 20), date.today())
        h1_bars = h1.get("bars", []) if h1.get("ok") else []
        m5_bars = m5.get("bars", []) if m5.get("ok") else []

    h1_source = "longbridge" if h1_bars else "none"
    # Crypto hourly fallback from OKX local (LongBridge has no crypto history)
    if sym.ticker in ("BTC", "ETH", "SOL") and not h1_bars:
        okx = load_okx_hourly(sym.ticker)
        if okx:
            h1_bars = [{"ts": r.get("timestamp", ""), "close": float(r.get("close", 0))} for r in okx]
            h1_source = "okx_local"

    row["hourly"] = {
        "available": len(h1_bars) > 0,
        "source": h1_source,
        "count": len(h1_bars),
        "earliest": (h1_bars[0].get("ts", "")[:10] if h1_bars else None),
        "latest": (h1_bars[-1].get("ts", "")[:10] if h1_bars else None),
    }
    row["five_min"] = {
        "available": len(m5_bars) > 0,
        "source": "longbridge" if m5_bars else "none",
        "count": len(m5_bars),
        "earliest": (m5_bars[0].get("ts", "")[:10] if m5_bars else None),
        "latest": (m5_bars[-1].get("ts", "")[:10] if m5_bars else None),
    }

    row["returns_daily"] = daily_returns(daily_bars)
    row["research_value"] = _research_value(row)
    return row


def run_full_audit() -> dict[str, Any]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    symbols = [audit_symbol(s) for s in AUDIT_SYMBOLS]
    cp00048_special = probe_cp00048_constituents()

    # attach CP00048 static from audit
    for s in symbols:
        if s["ticker"] == "CP00048":
            cp00048_special["daily_audit"] = s.get("daily")
            cp00048_special["hourly_audit"] = s.get("hourly")
            cp00048_special["five_min_audit"] = s.get("five_min")

    series = {s["ticker"]: s.get("returns_daily", {}) for s in symbols}
    sufficient = all(
        s.get("daily", {}).get("count", 0) >= MIN_DAILY_SAMPLES
        for s in symbols
        if s["ticker"] in {"BTC", "CP00048", "MSTR", "COIN", "BLOK", "WGMI"}
    )
    lead_lag = run_lead_lag(series) if sufficient else {
        "status": "SKIPPED",
        "reason": "core symbols lack >=200 daily samples",
        "results": [],
    }

    report = {
        "audit_date": str(date.today()),
        "phase": "data_availability_audit",
        "symbols": symbols,
        "cp00048_special": cp00048_special,
        "lead_lag": lead_lag,
        "recommendation": _build_recommendation(symbols, lead_lag),
    }

    AUDIT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if isinstance(lead_lag, list):
        LEAD_LAG_JSON.write_text(json.dumps(lead_lag, indent=2), encoding="utf-8")

    md_main = format_main_report(report)
    md_cp = format_cp00048_report(report)
    md_ll = format_lead_lag_report(lead_lag if isinstance(lead_lag, list) else [])

    (REPORTS_DIR / "data_availability_audit.md").write_text(md_main, encoding="utf-8")
    (REPORTS_DIR / "cp00048_special.md").write_text(md_cp, encoding="utf-8")
    (REPORTS_DIR / "lead_lag_offline.md").write_text(md_ll, encoding="utf-8")
    (REPORTS_DIR / "FILE_MANIFEST.md").write_text(format_manifest(), encoding="utf-8")

    return report


def _build_recommendation(symbols: list[dict], lead_lag: Any) -> dict[str, Any]:
    issues: list[str] = []
    btc = next((s for s in symbols if s["ticker"] == "BTC"), {})
    cp = next((s for s in symbols if s["ticker"] == "CP00048"), {})
    ibit = next((s for s in symbols if s["ticker"] == "IBIT"), {})
    crcl = next((s for s in symbols if s["ticker"] == "CRCL"), {})

    if btc.get("daily", {}).get("source") != "longbridge":
        issues.append("BTC/ETH/SOL 无 LongBridge 历史K线，需 Yahoo/OKX 异构源")
    if cp.get("hourly", {}).get("count", 0) < 500:
        issues.append("CP00048 小时K仅约3个月，不足以做小时级 Lead-Lag")
    if ibit.get("daily", {}).get("count", 0) < 400:
        issues.append("IBIT/FBTC 上市不足2年，现货ETF层历史偏短")
    if crcl.get("daily", {}).get("count", 0) < MIN_DAILY_SAMPLES:
        issues.append("CRCL 日K不足200样本（2025 IPO）")

    core_ok = (
        btc.get("daily", {}).get("count", 0) >= MIN_DAILY_SAMPLES
        and cp.get("daily", {}).get("count", 0) >= MIN_DAILY_SAMPLES
    )

    if core_ok and len(issues) <= 2:
        verdict = "A"
        label = "建议启动（日频 V0，小时频待补数）"
    else:
        verdict = "B"
        label = "暂不建议启动完整 V0"

    return {"verdict": verdict, "label": label, "issues": issues, "core_daily_ok": core_ok}


def format_main_report(report: dict[str, Any]) -> str:
    lines = [
        "# Crypto Ecosystem Lead-Lag Research V0 — 数据可得性审计",
        "",
        f"**审计日期:** {report['audit_date']}",
        f"**阶段:** 只读审计（未启动研究流水线）",
        "",
        "## 汇总表",
        "",
        "| 标的 | 可采集 | 日K | 1h | 5m | 最早日期 | 样本数 | 研究价值 |",
        "|------|--------|-----|----|----|----------|--------|----------|",
    ]
    for s in report["symbols"]:
        coll = "✓" if s.get("quote", {}).get("ok") or s.get("daily", {}).get("count", 0) > 0 else "✗"
        d_ok = "✓" if s.get("daily", {}).get("count", 0) > 0 else "✗"
        h_ok = "✓" if s.get("hourly", {}).get("available") else "✗"
        m_ok = "✓" if s.get("five_min", {}).get("available") else "✗"
        lines.append(
            f"| {s['ticker']} | {coll} | {d_ok} | {h_ok} | {m_ok} | "
            f"{s.get('daily', {}).get('earliest') or 'N/A'} | "
            f"{s.get('daily', {}).get('count', 0)} | {s.get('research_value', 'N/A')} |"
        )

    lines.extend(["", "## 分项检查", ""])
    for s in report["symbols"]:
        lines.append(f"### {s['ticker']} ({s['layer']})")
        lines.append(f"- **LongBridge 报价:** {'可用' if s.get('quote', {}).get('ok') else '不可用'}")
        lines.append(f"- **日K 来源:** {s.get('daily', {}).get('source')}，{s.get('daily', {}).get('count', 0)} 条")
        lines.append(f"- **1h:** {s.get('hourly', {}).get('source')}，{s.get('hourly', {}).get('count', 0)} 条")
        lines.append(f"- **5m:** {s.get('five_min', {}).get('source')}，{s.get('five_min', {}).get('count', 0)} 条")
        gaps = s.get("gaps", {})
        splits = s.get("splits", {})
        lines.append(f"- **缺口:** {gaps.get('gap_count', 0)} 处，最大连续缺口 {gaps.get('max_gap_days', 0)} 天")
        lines.append(f"- **拆股/复权:** {'疑似问题' if splits.get('likely_split_issues') else '未见异常'}")
        lines.append("")

    rec = report.get("recommendation", {})
    lines.extend([
        "## 最终建议",
        "",
        f"**{rec.get('verdict', '?')}. {rec.get('label', '')}**",
        "",
        "### 阻塞/风险项",
    ])
    for issue in rec.get("issues", []):
        lines.append(f"- {issue}")
    lines.extend([
        "",
        "### 成功标准回答",
        "",
        "> 当前数据质量是否足以支撑 Crypto Ecosystem Lead-Lag Research V0？",
        "",
        _verdict_text(rec),
    ])
    return "\n".join(lines)


def _verdict_text(rec: dict) -> str:
    if rec.get("verdict") == "A":
        return (
            "**部分足够。** 日频层面 BTC↔区块链指数↔核心股/ETF 具备 ~3-4 年重叠样本，"
            "可启动 **日频 Lead-Lag V0**；小时/5分钟级需补数且 CP00048 小时历史过短，"
            "暂不适合作为小时级核心驱动。"
        )
    return (
        "**尚不足够。** 关键标的存在异构数据源、小时K缺口或上市时间过短，"
        "建议先完成数据补齐与 CP00048 成分透明度确认后再启动。"
    )


def format_cp00048_report(report: dict[str, Any]) -> str:
    cp = report.get("cp00048_special", {})
    sym = next((s for s in report["symbols"] if s["ticker"] == "CP00048"), {})
    lines = [
        "# CP00048 区块链指数 — 专项审计",
        "",
        "## 1. 指数类型",
        "",
        f"- **LongBridge 符号:** CP00048.US",
        f"- **名称:** {cp.get('static', {}).get('name_en', 'Blockchain')} / {cp.get('static', {}).get('name_cn', '区块链')}",
        f"- **板块:** {cp.get('static', {}).get('board', 'USSector')}",
        "- **结论:** 是 LongBridge 自定义 US Sector / 主题指数（非交易所标准指数）",
        "",
        "## 2. 历史 K 线",
        "",
        f"- **日K:** {sym.get('daily', {}).get('count', 0)} 条，{sym.get('daily', {}).get('earliest')} → {sym.get('daily', {}).get('latest')}",
        f"- **1h:** {sym.get('hourly', {}).get('count', 0)} 条，{sym.get('hourly', {}).get('earliest')} → {sym.get('hourly', {}).get('latest')}",
        f"- **5m:** {sym.get('five_min', {}).get('count', 0)} 条，{sym.get('five_min', {}).get('earliest')} → {sym.get('five_min', {}).get('latest')}",
        "",
        "## 3. 成分股获取能力",
        "",
        f"- **OpenAPI 专用成分接口:** {'有' if cp.get('constituent_api_available') else '无'}",
    ]
    for note in cp.get("notes", []):
        lines.append(f"- {note}")
    lines.extend([
        "",
        "## 4. 指数计算方式",
        "",
        "- **公开文档:** LongBridge OpenAPI 未披露 CP00048 加权/再平衡规则",
        "- **calc_indexes:** 仅返回 LastDone 等行情字段，无成分权重",
        "- **研究影响:** 指数编制不透明，Lead-Lag 结论需标注「指数方法论未知」",
        "",
        "## 5. 研究适用性",
        "",
        "- **日频:** 可用（与 BTC 重叠约 3+ 年）",
        "- **小时频:** 不足（1h 历史约 3 个月）",
        "- **成分验证:** 无法通过 API 交叉验证指数构成",
    ])
    return "\n".join(lines)


def format_lead_lag_report(results: list[dict]) -> str:
    lines = [
        "# 离线 Lead-Lag 初测（审计附验）",
        "",
        "仅当日频核心标的样本 ≥ 200 时执行。滞后：0/1/2/3/5。",
        "",
        "| Driver | Target | Lag | 样本数 | 命中率 | 相关系数 | 状态 |",
        "|--------|--------|-----|--------|--------|----------|------|",
    ]
    for r in results:
        if r.get("status") == "INSUFFICIENT DATA" and "lag" not in r:
            lines.append(f"| {r.get('driver')} | {r.get('target')} | — | — | — | — | INSUFFICIENT DATA |")
            continue
        lines.append(
            f"| {r.get('driver')} | {r.get('target')} | {r.get('lag')} | "
            f"{r.get('sample_count', '—')} | {r.get('hit_rate', '—')} | "
            f"{r.get('correlation', '—')} | {r.get('status', '')} |"
        )
    lines.extend([
        "",
        "**说明:** 此为审计阶段初测，不构成策略结论；样本不足对已标记 INSUFFICIENT DATA。",
    ])
    return "\n".join(lines)


def format_manifest() -> str:
    return """# Crypto Ecosystem Audit — 新增文件清单

## 审计脚本（research/crypto_ecosystem/）

| 文件 | 用途 |
|------|------|
| `__init__.py` | 包初始化 |
| `paths.py` | 路径与阈值常量 |
| `config.py` | 审计标的与 Lead-Lag 配对 |
| `longbridge_probe.py` | LongBridge 只读探测 |
| `data_utils.py` | 缺口/拆股/收益率工具 |
| `lead_lag_offline.py` | 离线 Lead-Lag 初测 |
| `audit.py` | 主审计与报告生成 |
| `run_audit.py` | CLI 入口 |

## 输出报告（shared_intelligence/research/crypto_ecosystem_v0/）

| 文件 | 用途 |
|------|------|
| `audit_results.json` | 完整审计 JSON |
| `lead_lag_offline.json` | Lead-Lag 初测 JSON |
| `reports/data_availability_audit.md` | 数据可得性审计报告 |
| `reports/cp00048_special.md` | CP00048 专项报告 |
| `reports/lead_lag_offline.md` | 离线 Lead-Lag 初测 |
| `reports/FILE_MANIFEST.md` | 本清单 |

**约束遵守:** 未修改交易系统 / Paper Loop / Cross Market / Scheduler / 风控；未新增 Cron 或长期任务。
"""
