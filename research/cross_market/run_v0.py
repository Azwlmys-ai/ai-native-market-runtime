#!/usr/bin/env python3
"""Cross Market Research V0 — main pipeline (research-only)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# allow running as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from research.cross_market.audit import format_audit_markdown, run_audit
from research.cross_market.config import CN_TARGETS, FACTORS, RESEARCH_QUESTIONS, US_TARGETS
from research.cross_market.factors import build_all_factors, load_series_returns
from research.cross_market.import_series import run_import
from research.cross_market.lead_lag import analyze_lead_lag, rank_relationships, run_full_matrix
from research.cross_market.paths import REPORTS_DIR, RESEARCH_ROOT, VALIDATION_END, VALIDATION_START
from research.cross_market.reports import write_reports
from research.cross_market.research_db import (
    get_connection,
    save_lead_lag_results,
    save_question_verdict,
    upsert_factor_returns,
    upsert_returns,
)


def _evaluate_questions(factors: dict, all_results: list) -> list[dict]:
    verdicts = []
    for q in RESEARCH_QUESTIONS:
        driver = q["driver"]
        target = q["target"]
        matching = [
            r for r in all_results
            if r.driver == driver and r.target == target and r.sample_count >= 30
        ]
        if not matching:
            verdict = "无法证明"
            evidence = {"reason": "样本不足或无匹配结果"}
        else:
            best = max(matching, key=lambda r: abs(r.correlation) if r.correlation == r.correlation else 0)
            if best.direction == "driver_leads" and best.hit_rate > 0.52:
                verdict = "存在统计领先关系（弱至中等）"
            else:
                verdict = "无法证明"
            evidence = best.to_dict()
        verdicts.append({**q, "verdict": verdict, "evidence": evidence})
    return verdicts


def _deliverables_manifest() -> str:
    files = sorted(Path(__file__).parent.rglob("*"))
    code_files = [str(f.relative_to(Path(__file__).parent.parent.parent)) for f in files if f.is_file()]
    return json.dumps({"module_files": code_files}, indent=2, ensure_ascii=False)


def run_pipeline(skip_import: bool = False) -> dict:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)

    # 1. Audit
    audit = run_audit()
    audit_path = RESEARCH_ROOT / "audit_data_inventory.md"
    audit_path.write_text(format_audit_markdown(audit), encoding="utf-8")

    # 2. Import
    if not skip_import:
        import_result = run_import(VALIDATION_START, VALIDATION_END)
    else:
        import_result = {"skipped": True}

    # 3. Build factors & load targets
    factors = build_all_factors()
    drivers: dict[str, dict] = {**factors}
    for key in ("DXY", "US10Y", "US2Y", "BTC", "ETH", "SOXX"):
        drivers[key] = load_series_returns(key)
    drivers["northbound"] = load_series_returns("northbound")

    cn_targets = {code: load_series_returns(code) for code in CN_TARGETS}
    us_targets = {sym: load_series_returns(sym) for sym in US_TARGETS}
    all_targets = {**cn_targets, **us_targets}

    # 4. Lead-lag matrix
    all_results = run_full_matrix(drivers, all_targets)

    # 5. Research DB
    conn = get_connection()
    for code in CN_TARGETS:
        upsert_returns(conn, code, "china", cn_targets[code], "shared_intelligence")
    for sym in US_TARGETS:
        upsert_returns(conn, sym, "us", us_targets[sym], "shared_intelligence")
    for fid, rets in factors.items():
        upsert_factor_returns(conn, fid, rets)
    save_lead_lag_results(conn, all_results)

    verdicts = _evaluate_questions(factors, all_results)
    for v in verdicts:
        save_question_verdict(conn, v["id"], v["question"], v["driver"], v["target"], v["verdict"], v["evidence"])
    conn.commit()
    conn.close()

    strongest, weakest = rank_relationships(all_results, 10)

    # 6. Reports
    report_paths = write_reports()

    # 7. Final deliverables doc
    deliverable = _build_deliverables(audit, import_result, verdicts, strongest, weakest, report_paths)
    out_path = RESEARCH_ROOT / "V0_DELIVERABLES.md"
    out_path.write_text(deliverable, encoding="utf-8")

    validation_path = RESEARCH_ROOT / "validation_3yr.json"
    validation_path.write_text(json.dumps({
        "period": f"{VALIDATION_START} → {VALIDATION_END}",
        "verdicts": verdicts,
        "strongest_top10": strongest,
        "weakest_top10": weakest,
        "total_pairs_tested": len(all_results),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== V0 Complete ===")
    print(f"Deliverables: {out_path}")
    print(f"Validation: {validation_path}")
    for k, v in report_paths.items():
        print(f"Report {k}: {v}")
    return {"deliverables": str(out_path), "verdicts": verdicts}


def _build_deliverables(audit, import_result, verdicts, strongest, weakest, report_paths) -> str:
    lines = [
        "# Cross Market Research V0 — 第一阶段交付\n",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        "## 1. 新增文件清单\n",
        "- `research/cross_market/` — 完整研究模块",
        "- `shared_intelligence/history/china/` — A股指数",
        "- `shared_intelligence/history/flows/` — 北向资金",
        "- `shared_intelligence/history/macro/` — DXY, US10Y, US2Y",
        "- `shared_intelligence/research/cross_market_v0/` — 研究DB + 报告\n",
        "## 2. 新增数据源清单\n",
        "| 序列 | 来源 | 路径 |",
        "|------|------|------|",
        "| 上证/创业板 | a_share_research_db + Sina 补全 | history/china/ |",
        "| 深成指/沪深300 | Sina Finance | history/china/ |",
        "| 北向资金 | Eastmoney RPT_MUTUAL_DEAL_HISTORY | history/flows/ |",
        "| DXY/US10Y/US2Y | Yahoo Finance | history/macro/ |",
        "| 美股/因子成分 | Yahoo Finance | history/markets/ |\n",
        "## 3. 数据存储结构\n",
        "```",
        "shared_intelligence/",
        "  history/macro/   DXY.json US10Y.json US2Y.json",
        "  history/china/   000001.json 399001.json 399006.json 000300.json",
        "  history/flows/   northbound.json",
        "  history/markets/ QQQ SPY SOXX + factor components",
        "  research/cross_market_v0/",
        "    cross_market_v0.db",
        "    reports/",
        "    validation_3yr.json",
        "```\n",
        "## 4. 日报样例\n",
        f"- {report_paths.get('us_close_cn_open', 'N/A')}",
        f"- {report_paths.get('cn_close_us_open', 'N/A')}\n",
        "## 5. 过去3年历史验证结果\n",
        f"验证区间：{VALIDATION_START} → {VALIDATION_END}\n",
    ]
    for v in verdicts:
        ev = v.get("evidence", {})
        lines.append(f"### {v['id']}: {v['question']}")
        lines.append(f"- **结论**: {v['verdict']}")
        if isinstance(ev, dict) and ev.get("sample_count"):
            lines.append(
                f"- 样本数={ev.get('sample_count')} 命中率={ev.get('hit_rate')} "
                f"平均收益={ev.get('avg_return')}% 回撤={ev.get('avg_drawdown')}% 相关={ev.get('correlation')}"
            )
        lines.append("")
    lines.extend(["## 6. 最强传导关系 TOP10\n", "| Driver | Target | Lag | Window | n | Hit | AvgRet% | Corr |"])
    lines.append("|--------|--------|-----|--------|---|-----|---------|------|")
    for r in strongest:
        lines.append(
            f"| {r['driver']} | {r['target']} | {r['lag_days']} | {r['window_days']} | "
            f"{r['sample_count']} | {r['hit_rate']} | {r['avg_return']} | {r['correlation']} |"
        )
    lines.extend(["\n## 7. 最弱传导关系 TOP10\n"])
    for r in weakest:
        lines.append(f"- {r['driver']} → {r['target']}: corr={r['correlation']} hit={r['hit_rate']} n={r['sample_count']}")
    lines.extend([
        "\n## 8. 下一阶段建议\n",
        "- 扩展 A股历史至 2020+（当前 a_share DB 仅 2024 起）",
        "- 加入港股/汇率（CNH）作为传导中介变量",
        "- 分 regime（高/低波动）做条件 lead-lag",
        "- 日内 US close → CN next open 精确对齐（时区校正）",
        "- 仍保持研究层隔离，不接入交易\n",
        "---\n*Research Layer only. 未修改任何交易逻辑。*\n",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Cross Market Research V0")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--skip-import", action="store_true")
    parser.add_argument("--reports-only", action="store_true")
    args = parser.parse_args()

    if args.audit_only:
        audit = run_audit()
        print(format_audit_markdown(audit))
        return
    if args.reports_only:
        write_reports()
        return
    run_pipeline(skip_import=args.skip_import)


if __name__ == "__main__":
    main()
