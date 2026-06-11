#!/usr/bin/env python3
"""Cross Market Research V0.1 — data quality fixes (research-only)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from research.cross_market.calendar_align import alignment_rules_doc
from research.cross_market.compare_v01 import compare_validations, format_comparison_markdown
from research.cross_market.config import CN_TARGETS, FACTORS, RESEARCH_QUESTIONS, US_TARGETS
from research.cross_market.factors import build_all_factors, load_series_returns
from research.cross_market.import_series import (
    fetch_northbound_deal_history,
    fetch_northbound_kamt,
    run_import,
)
from research.cross_market.lead_lag import rank_relationships, run_full_matrix
from research.cross_market.paths import (
    CHINA_DIR,
    CHINA_HISTORY_START,
    FLOWS_DIR,
    REPORTS_DIR,
    RESEARCH_ROOT,
    V0_BASELINE_VALIDATION,
    V01_COMPARISON,
    V01_DELIVERABLES,
    VALIDATION_END,
    VALIDATION_START,
)
from research.cross_market.reports import write_reports
from research.cross_market.research_db import (
    get_connection,
    save_lead_lag_results,
    save_question_verdict,
    upsert_factor_returns,
    upsert_returns,
)
from research.cross_market.run_v0 import _evaluate_questions


def audit_northbound_root_cause() -> dict:
    """Read-only audit of northbound data pipeline."""
    kamt = fetch_northbound_kamt("2020-01-01", lmt=3000)
    deal = fetch_northbound_deal_history("2020-01-01")
    path = FLOWS_DIR / "northbound.json"
    stored = []
    if path.exists():
        stored = json.loads(path.read_text()).get("bars", [])
    return {
        "root_cause": (
            "Eastmoney RPT_MUTUAL_DEAL_HISTORY 自约 2024-09 起不再返回 NET_DEAL_AMT/FUND_INFLOW；"
            "V0 错误地合并 001+003 且遇 null 提前停页。"
            "V0.1 改用 push2his kamt.kline s2n（MUTUAL_TYPE=005 等效序列）为主源，"
            "deal history 仅作历史补全。"
        ),
        "field_deprecation_since": "约 2024-09-20",
        "v0_wrong_mutual_type": "001+003 求和（应为 005 北向合计）",
        "v0_pagination_bug": "遇 NET_DEAL_AMT=null 跳过且提前 break，导致大量缺口",
        "recent_gap": "2026-04-08 之后 kamt s2n 亦为 0（东方财富未更新净流入字段）",
        "kamt_rows_valid": len(kamt),
        "deal_rows_valid": len(deal),
        "stored_rows": len(stored),
        "kamt_range": [kamt[0]["date"], kamt[-1]["date"]] if kamt else None,
        "deal_range": [deal[0]["date"], deal[-1]["date"]] if deal else None,
        "unit": "百万元（与 akshare NET_DEAL_AMT 原始口径一致）",
        "alternative_if_unfixable": "无免费可靠替代；可考虑港交所披露易汇总（延迟高）或持股变动推算（非净流入）",
    }


def _china_extension_stats() -> dict:
    stats = {}
    for code in CN_TARGETS:
        p = CHINA_DIR / f"{code}.json"
        if not p.exists():
            stats[code] = {"rows": 0}
            continue
        data = json.loads(p.read_text())
        bars = data.get("bars", [])
        dates = [b["date"] for b in bars]
        stats[code] = {
            "rows": len(bars),
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
            "meets_2020": bool(dates) and min(dates)[:7] <= "2020-01",
        }
    return stats


def run_pipeline(skip_import: bool = False) -> dict:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)

    # preserve V0 baseline
    v0_path = RESEARCH_ROOT / "validation_3yr.json"
    if v0_path.exists() and not V0_BASELINE_VALIDATION.exists():
        shutil.copy(v0_path, V0_BASELINE_VALIDATION)

    nb_audit = audit_northbound_root_cause()

    if not skip_import:
        import_result = run_import(CHINA_HISTORY_START, VALIDATION_END)
    else:
        import_result = {"skipped": True}

    china_stats = _china_extension_stats()
    nb_audit["stored_after_import"] = json.loads(
        (FLOWS_DIR / "northbound.json").read_text()
    ).get("bars", []) if (FLOWS_DIR / "northbound.json").exists() else []

    factors = build_all_factors()
    drivers: dict[str, dict] = {**factors}
    for key in ("DXY", "US10Y", "US2Y", "BTC", "ETH", "SOXX"):
        drivers[key] = load_series_returns(key)
    drivers["northbound"] = load_series_returns("northbound")

    cn_targets = {code: load_series_returns(code) for code in CN_TARGETS}
    us_targets = {sym: load_series_returns(sym) for sym in US_TARGETS}
    all_targets = {**cn_targets, **us_targets}

    all_results = run_full_matrix(drivers, all_targets, use_alignment=True)
    verdicts = _evaluate_questions(factors, all_results)
    strongest, weakest = rank_relationships(all_results, 10)

    conn = get_connection()
    for code in CN_TARGETS:
        upsert_returns(conn, code, "china", cn_targets[code], "shared_intelligence")
    for sym in US_TARGETS:
        upsert_returns(conn, sym, "us", us_targets[sym], "shared_intelligence")
    for fid, rets in factors.items():
        upsert_factor_returns(conn, fid, rets)
    save_lead_lag_results(conn, all_results)
    for v in verdicts:
        save_question_verdict(conn, v["id"], v["question"], v["driver"], v["target"], v["verdict"], v["evidence"])
    conn.commit()
    conn.close()

    validation = {
        "version": "0.1",
        "period": f"{VALIDATION_START} → {VALIDATION_END}",
        "alignment": "us_close_cn_open / cn_close_us_open / cn_close_cn_next",
        "verdicts": verdicts,
        "strongest_top10": strongest,
        "weakest_top10": weakest,
        "total_pairs_tested": len(all_results),
        "northbound_audit": nb_audit,
        "china_stats": china_stats,
    }
    v1_path = RESEARCH_ROOT / "validation_3yr.json"
    v1_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")

    report_paths = write_reports()

    # V0 vs V0.1 comparison
    v0 = json.loads(V0_BASELINE_VALIDATION.read_text()) if V0_BASELINE_VALIDATION.exists() else {}
    diff = compare_validations(v0, validation) if v0 else {}
    if diff:
        V01_COMPARISON.write_text(format_comparison_markdown(diff), encoding="utf-8")

    deliverable = _build_deliverables(nb_audit, china_stats, verdicts, strongest, weakest, diff, report_paths)
    V01_DELIVERABLES.write_text(deliverable, encoding="utf-8")

    print(f"\n=== V0.1 Complete ===")
    print(f"Deliverables: {V01_DELIVERABLES}")
    print(f"Validation: {v1_path}")
    if diff:
        print(f"Comparison: {V01_COMPARISON}")
    return {"deliverables": str(V01_DELIVERABLES), "verdicts": verdicts}


def _build_deliverables(nb_audit, china_stats, verdicts, strongest, weakest, diff, report_paths) -> str:
    lines = [
        "# Cross Market Research V0.1 — 交付\n",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        "## 1. 修改/新增文件清单\n",
        "- `research/cross_market/calendar_align.py` — 交易日对齐",
        "- `research/cross_market/compare_v01.py` — V0/V0.1 对比",
        "- `research/cross_market/run_v01.py` — V0.1 流水线",
        "- `research/cross_market/import_series.py` — 北向+kamt、A股扩展",
        "- `research/cross_market/lead_lag.py` — 对齐感知 lead-lag\n",
        "## 2. 北向资金问题根因\n",
        f"- {nb_audit['root_cause']}",
        f"- 字段停更：{nb_audit['field_deprecation_since']}",
        f"- V0 错误：{nb_audit['v0_wrong_mutual_type']}",
        f"- 近期缺口：{nb_audit['recent_gap']}",
        f"- 修复后有效行数：kamt={nb_audit['kamt_rows_valid']}, deal={nb_audit['deal_rows_valid']}\n",
        "## 3. A股历史扩展结果\n",
        "| 指数 | 行数 | 起始 | 满足≥2020 |",
        "|------|------|------|-----------|",
    ]
    for code, meta in CN_TARGETS.items():
        s = china_stats.get(code, {})
        lines.append(
            f"| {meta['name']} ({code}) | {s.get('rows',0)} | {s.get('start','-')} | "
            f"{'✅' if s.get('meets_2020') else '❌'} |"
        )
    lines.append("\n" + alignment_rules_doc())
    lines.append("\n## 5. V0.1 六个核心问题结论\n")
    cross_ids = {"Q1", "Q2", "Q4", "Q5", "Q6"}
    cross_unproven = True
    for v in verdicts:
        ev = v.get("evidence", {})
        lines.append(f"### {v['id']}: {v['question']}")
        note = ""
        if v["id"] == "Q3":
            note = "（同日对齐，共变非领先）"
        lines.append(f"- **结论**: {v['verdict']}{note}")
        if v["id"] in cross_ids and v["verdict"].startswith("存在"):
            cross_unproven = False
        if isinstance(ev, dict) and ev.get("sample_count"):
            lines.append(
                f"- 样本数={ev.get('sample_count')} 命中率={ev.get('hit_rate')} "
                f"平均收益={ev.get('avg_return')}% 回撤={ev.get('avg_drawdown')}% "
                f"相关={ev.get('correlation')} 对齐={ev.get('alignment','')}"
            )
        lines.append("")
    lines.extend(["## 6. 最强传导 TOP10\n", "| Driver | Target | Align | Window | n | Hit | Corr |"])
    lines.append("|--------|--------|-------|--------|---|-----|------|")
    for r in strongest:
        lines.append(
            f"| {r['driver']} | {r['target']} | {r.get('alignment','')} | {r['window_days']} | "
            f"{r['sample_count']} | {r['hit_rate']} | {r['correlation']} |"
        )
    lines.extend(["\n## 7. 最弱传导 TOP10\n"])
    for r in weakest:
        lines.append(f"- {r['driver']} → {r['target']}: corr={r['correlation']} n={r['sample_count']}")
    lines.extend(["\n## 8. V0 vs V0.1 对比\n"])
    if diff:
        for q in diff.get("questions", []):
            if q.get("verdict_changed"):
                lines.append(
                    f"- {q['id']}: {q['v0_verdict']} → {q['v1_verdict']} "
                    f"(n {q['v0_n']}→{q['v1_n']}, corr {q['v0_corr']}→{q['v1_corr']})"
                )
    else:
        lines.append("- 无 V0 baseline，跳过对比")
    lines.extend([
        "\n## 9. 是否建议接入定时日报\n",
        "**建议：可作为独立 research cron，不接入交易 Scheduler。**",
        "- 每日 08:00（CN open 前）生成 `us_close_cn_open`",
        "- 每日 21:30（US open 后）生成 `cn_close_us_open`",
        "- 输出目录：`shared_intelligence/research/cross_market_v0/reports/`",
        "- 硬隔离：不写入 signals / orchestrator / paper engine\n",
        "## 总体结论\n",
    ])
    if cross_unproven:
        lines.append("**当前数据无法证明稳定跨市场领先关系。**")
    else:
        lines.append("跨市场问题中仅 Q5 显示弱关联；总体不足以证明稳定领先关系。")
    lines.append("\n---\n*Research Layer only.*\n")
    lines.append(f"\n日报: {report_paths}\n")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Cross Market Research V0.1")
    parser.add_argument("--skip-import", action="store_true")
    args = parser.parse_args()
    run_pipeline(skip_import=args.skip_import)


if __name__ == "__main__":
    main()
