"""Cross Market Research Brief — US Close→CN Open and CN Close→US Open."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .brief_format import BRIEF_FOOTER, BRIEF_TITLE, enrich_evidence, format_evidence_block
from .config import CN_TARGETS, FACTORS, RESEARCH_QUESTIONS, US_TARGETS
from .factors import build_all_factors, factor_summary, load_flow_levels, load_series_returns
from .calendar_align import build_pairs, infer_alignment, trading_days_from_returns
from .lead_lag import analyze_lead_lag
from .paths import BRIEF_INDEX_FILE, REPORTS_ARCHIVE_DIR, REPORTS_DIR


def _latest_return(rets: dict[str, float], n: int = 1) -> dict[str, Any]:
    if not rets:
        return {"date": None, "return_pct": None}
    dates = sorted(rets.keys())
    d = dates[-1]
    if n == 1:
        return {"date": d, "return_pct": round(rets[d] * 100, 4)}
    chunk = dates[-n:]
    cum = sum(rets[x] for x in chunk) * 100
    return {"date": d, "return_pct": round(cum, 4), "window_days": n}


def _best_evidence(driver: str, target: str, driver_rets: dict, target_rets: dict) -> dict:
    align = infer_alignment(driver, target)
    pairs = build_pairs(
        trading_days_from_returns(driver_rets),
        trading_days_from_returns(target_rets),
        align,
    )
    results = analyze_lead_lag(
        driver, target, driver_rets, target_rets,
        windows=(1, 3, 5), lags=(1,), pairs=pairs, alignment=align,
    )
    valid = [r for r in results if r.sample_count >= 30 and r.direction == "driver_leads"]
    if not valid:
        valid = [r for r in results if r.sample_count >= 10]
    if not valid:
        return enrich_evidence({"verdict": "无法证明", "reason": "样本不足"}, align)
    best = max(valid, key=lambda r: abs(r.correlation) if r.correlation == r.correlation else 0)
    ev = {
        "verdict": "存在统计关联" if best.direction == "driver_leads" else "无法证明",
        "sample_count": best.sample_count,
        "hit_rate": best.hit_rate,
        "avg_return_pct": best.avg_return,
        "avg_drawdown_pct": best.avg_drawdown,
        "correlation": best.correlation,
        "lag_days": best.lag_days,
        "window_days": best.window_days,
        "direction": best.direction,
    }
    return enrich_evidence(ev, align)


def _brief_header(subtitle: str, as_of: str | None = None) -> list[str]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return [
        f"# {BRIEF_TITLE}",
        f"\n**{subtitle}**\n",
        f"生成时间：{now}",
        f"参考交易日：{as_of or 'latest'}",
        f"报告类型：Research Brief（研究归因，非交易建议）\n",
    ]


def _brief_footer() -> list[str]:
    return [
        "\n---\n",
        f"**{BRIEF_FOOTER}**",
    ]


def report_us_close_cn_open(as_of: str | None = None) -> str:
    """US Close → CN Open Research Brief."""
    factors = build_all_factors()
    factor_state = factor_summary(factors)
    dxy = load_series_returns("DXY")
    us10y = load_series_returns("US10Y")
    cn_targets = {code: load_series_returns(code) for code in CN_TARGETS}

    lines = _brief_header("US Close → CN Open", as_of)
    lines.extend([
        "## 1. 全球市场摘要\n",
        f"- QQQ 1日: {_latest_return(load_series_returns('QQQ'))}",
        f"- SPY 1日: {_latest_return(load_series_returns('SPY'))}",
        f"- SOXX 1日: {_latest_return(load_series_returns('SOXX'))}\n",
        "## 2. Global Factors 状态\n",
    ])
    for fs in factor_state:
        lines.append(f"- **{fs['name']}** ({fs['factor']}): {fs.get('last_return', 'N/A')}% @ {fs.get('last_date', 'N/A')}")
    lines.extend([
        "\n## 3. DXY 状态\n",
        f"- 1日: {_latest_return(dxy)}",
        f"- 5日: {_latest_return(dxy, 5)}\n",
        "## 4. US10Y 状态\n",
        f"- 1日: {_latest_return(us10y)}",
        f"- 5日: {_latest_return(us10y, 5)}\n",
        "## 5. AI Composite\n",
        f"- {_latest_return(factors.get('Factor_A', {}))}\n",
        "## 6. Semiconductor Composite\n",
        f"- {_latest_return(factors.get('Factor_B', {}))}\n",
        "## 7. Crypto Composite\n",
        f"- {_latest_return(factors.get('Factor_C', {}))}\n",
        "## 8. Commodity Composite\n",
        f"- {_latest_return(factors.get('Factor_D', {}))}\n",
        "## 9. A股传导研究（DXY）\n",
    ])
    for code, meta in CN_TARGETS.items():
        ev = _best_evidence("DXY", code, dxy, cn_targets[code])
        lines.append(format_evidence_block(ev, meta["name"]))
    lines.extend(["\n## 10. 历史样本验证\n"])
    for q in RESEARCH_QUESTIONS[:4]:
        dr = load_series_returns(q["driver"]) if not q["driver"].startswith("Factor") else factors.get(q["driver"], {})
        tr = load_series_returns(q["target"])
        ev = _best_evidence(q["driver"], q["target"], dr, tr)
        lines.append(format_evidence_block(ev, q["question"]))
    lines.extend([
        "\n## 11. 研究说明\n",
        "- 统计关联不等于因果；样本外可能失效。",
        "- 结论强度基于历史样本，不代表未来可复制。",
    ])
    lines.extend(_brief_footer())
    return "\n".join(lines) + "\n"


def report_cn_close_us_open(as_of: str | None = None) -> str:
    """CN Close → US Open Research Brief."""
    factors = build_all_factors()
    factor_state = factor_summary(factors)
    flows = load_flow_levels("northbound")
    cn_targets = {code: load_series_returns(code) for code in CN_TARGETS}
    us_targets = {sym: load_series_returns(sym) for sym in US_TARGETS}

    latest_flow_date = max(flows.keys()) if flows else None
    latest_flow = flows.get(latest_flow_date) if latest_flow_date else None

    lines = _brief_header("CN Close → US Open", as_of)
    lines.extend(["## 1. A股市场摘要\n"])
    for code, meta in CN_TARGETS.items():
        lines.append(f"- {meta['name']}: {_latest_return(cn_targets[code])}")
    lines.extend(["\n## 2. 指数表现\n"])
    for code, meta in CN_TARGETS.items():
        lines.append(f"- {meta['name']} 5日: {_latest_return(cn_targets[code], 5)}")
    lines.extend([
        "\n## 3. 北向资金\n",
        f"- 最新日期: {latest_flow_date}",
        f"- 净流入(百万元): {latest_flow}\n",
        "## 4. 中国市场风险偏好\n",
        f"- 创业板 vs 上证 1日: "
        f"{_latest_return(cn_targets.get('399006', {})).get('return_pct', 'N/A')} vs "
        f"{_latest_return(cn_targets.get('000001', {})).get('return_pct', 'N/A')}\n",
        "## 5. Global Factors 状态\n",
    ])
    for fs in factor_state:
        lines.append(f"- {fs['name']}: {fs.get('last_return', 'N/A')}%")
    lines.extend(["\n## 6. 跨市场传导研究\n"])
    nb_rets = load_series_returns("northbound") if flows else {}
    for sym in US_TARGETS:
        ev = _best_evidence("000001", sym, cn_targets.get("000001", {}), us_targets[sym])
        lines.append(format_evidence_block(ev, f"上证 → {sym}"))
    if nb_rets:
        ev_nb = _best_evidence("northbound", "QQQ", nb_rets, us_targets["QQQ"])
        lines.append(format_evidence_block(ev_nb, "北向 → QQQ"))
    lines.extend(["\n## 7. 历史样本验证\n"])
    for q in RESEARCH_QUESTIONS:
        dr_key = q["driver"]
        if dr_key == "northbound":
            dr = nb_rets
        elif dr_key.startswith("Factor"):
            dr = factors.get(dr_key, {})
        else:
            dr = load_series_returns(dr_key)
        tr = load_series_returns(q["target"]) if q["target"] in CN_TARGETS else us_targets.get(q["target"], {})
        ev = _best_evidence(dr_key, q["target"], dr, tr)
        lines.append(format_evidence_block(ev, q["question"]))
    lines.extend(_brief_footer())
    return "\n".join(lines) + "\n"


def _update_index(brief_key: str, archive_path: str, latest_path: str) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    index: dict = {"briefs": [], "updated_at": datetime.now().isoformat()}
    if BRIEF_INDEX_FILE.exists():
        try:
            index = json.loads(BRIEF_INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    entries = [e for e in index.get("briefs", []) if e.get("brief_key") != brief_key]
    entries.insert(0, {
        "brief_key": brief_key,
        "archive_path": archive_path,
        "latest_path": latest_path,
        "generated_at": datetime.now().isoformat(),
    })
    index["briefs"] = entries[:50]
    index["updated_at"] = datetime.now().isoformat()
    BRIEF_INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def write_brief(brief_type: str) -> dict[str, str]:
    """Write one brief to archive + latest. brief_type: us-cn | cn-us."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if brief_type == "us-cn":
        content = report_us_close_cn_open()
        stem = "us_close_cn_open"
    elif brief_type == "cn-us":
        content = report_cn_close_us_open()
        stem = "cn_close_us_open"
    else:
        raise ValueError(f"unknown brief_type: {brief_type}")

    archive_path = REPORTS_ARCHIVE_DIR / f"{stem}_{ts}.md"
    latest_path = REPORTS_DIR / f"{stem}_latest.md"
    archive_path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")
    _update_index(brief_type, str(archive_path), str(latest_path))
    return {"brief_type": brief_type, "archive": str(archive_path), "latest": str(latest_path)}


def write_reports() -> dict[str, str]:
    """Write both briefs (compat with run_v0/v01)."""
    r1 = write_brief("us-cn")
    r2 = write_brief("cn-us")
    return {"us_close_cn_open": r1["archive"], "cn_close_us_open": r2["archive"]}
