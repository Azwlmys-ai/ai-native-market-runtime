"""V0 vs V0.1 comparison — research-only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _verdict_map(validation: dict) -> dict[str, dict]:
    out = {}
    for v in validation.get("verdicts", []):
        out[v["id"]] = v
    return out


def _top_key(row: dict) -> str:
    return f"{row.get('driver')}→{row.get('target')}|w{row.get('window_days')}|l{row.get('lag_days')}"


def compare_validations(v0: dict, v1: dict) -> dict[str, Any]:
    v0m = _verdict_map(v0)
    v1m = _verdict_map(v1)
    question_diffs = []
    for qid in sorted(set(v0m) | set(v1m)):
        a, b = v0m.get(qid, {}), v1m.get(qid, {})
        ea, eb = a.get("evidence", {}), b.get("evidence", {})
        question_diffs.append({
            "id": qid,
            "question": b.get("question") or a.get("question"),
            "v0_verdict": a.get("verdict"),
            "v1_verdict": b.get("verdict"),
            "v0_n": ea.get("sample_count"),
            "v1_n": eb.get("sample_count"),
            "v0_hit": ea.get("hit_rate"),
            "v1_hit": eb.get("hit_rate"),
            "v0_corr": ea.get("correlation"),
            "v1_corr": eb.get("correlation"),
            "verdict_changed": a.get("verdict") != b.get("verdict"),
            "strengthened": (
                b.get("verdict", "").startswith("存在") and not a.get("verdict", "").startswith("存在")
            ),
            "weakened": (
                a.get("verdict", "").startswith("存在") and not b.get("verdict", "").startswith("存在")
            ),
        })

    s0 = {_top_key(r): r for r in v0.get("strongest_top10", [])}
    s1 = {_top_key(r): r for r in v1.get("strongest_top10", [])}
    disappeared = [k for k in s0 if k not in s1]
    emerged = [k for k in s1 if k not in s0]

    return {
        "questions": question_diffs,
        "disappeared_strong": disappeared,
        "emerged_strong": emerged,
        "v0_pairs_tested": v0.get("total_pairs_tested"),
        "v1_pairs_tested": v1.get("total_pairs_tested"),
    }


def format_comparison_markdown(diff: dict[str, Any]) -> str:
    lines = ["# Cross Market V0 vs V0.1 对比\n"]
    lines.append("## 六个核心问题\n")
    lines.append("| ID | 问题 | V0结论 | V0.1结论 | n变化 | hit变化 | corr变化 |")
    lines.append("|----|------|--------|----------|-------|---------|----------|")
    for q in diff["questions"]:
        n_chg = f"{q.get('v0_n')}→{q.get('v1_n')}"
        hit_chg = f"{q.get('v0_hit')}→{q.get('v1_hit')}"
        corr_chg = f"{q.get('v0_corr')}→{q.get('v1_corr')}"
        lines.append(
            f"| {q['id']} | {q.get('question','')[:20]} | {q.get('v0_verdict')} | "
            f"{q.get('v1_verdict')} | {n_chg} | {hit_chg} | {corr_chg} |"
        )

    strengthened = [q for q in diff["questions"] if q.get("strengthened")]
    weakened = [q for q in diff["questions"] if q.get("weakened")]
    unchanged_weak = [q for q in diff["questions"] if not q.get("verdict_changed")]

    lines.append("\n## 结论变化\n")
    lines.append(f"- **增强**: {len(strengthened)} 条")
    for q in strengthened:
        lines.append(f"  - {q['id']}: {q['v0_verdict']} → {q['v1_verdict']}")
    lines.append(f"- **消失/减弱**: {len(weakened)} 条")
    for q in weakened:
        lines.append(f"  - {q['id']}: {q['v0_verdict']} → {q['v1_verdict']}")
    lines.append(f"- **未变**: {len(unchanged_weak)} 条")

    lines.append("\n## TOP10 传导关系\n")
    lines.append(f"- V0 有、V0.1 消失: {len(diff.get('disappeared_strong', []))}")
    for k in diff.get("disappeared_strong", [])[:5]:
        lines.append(f"  - {k}")
    lines.append(f"- V0.1 新增: {len(diff.get('emerged_strong', []))}")
    for k in diff.get("emerged_strong", [])[:5]:
        lines.append(f"  - {k}")

    cross_market = [q for q in diff["questions"] if q["id"] in ("Q1", "Q2", "Q4", "Q5", "Q6")]
    cross_unproven = all(not str(q.get("v1_verdict", "")).startswith("存在") for q in cross_market)
    lines.append("\n## 总体判断\n")
    lines.append(
        "- Q3 (BTC→QQQ) 为同日对齐，反映共变而非跨日领先，不计入跨市场领先结论。"
    )
    if cross_unproven:
        lines.append(
            "**当前数据无法证明稳定跨市场领先关系。** "
            "V0.1 数据修复后，跨市场问题 Q1/Q2/Q4/Q5/Q6 均无法证明或仅极弱关联。"
        )
    else:
        lines.append("部分跨市场关系显示弱统计关联，但不足以证明稳定领先。")
    return "\n".join(lines) + "\n"
