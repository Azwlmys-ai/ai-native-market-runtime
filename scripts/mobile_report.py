#!/usr/bin/env python3
"""
mobile_report — 生成自包含离线 HTML 快照（手机浏览器查看）
============================================================================
主机无固定 IP、跑不了在线 dashboard → 把当前研究闭环数据渲染成一个**单文件、
零依赖、内联样式**的 HTML，写到 data/reports/，由 Telegram bot 作为文档发到手机。

只读事实源：review_results.json（三级）/ hypotheses.jsonl / postmortems.jsonl /
            paper_portfolio.json / execution_results.json / orchestrator_status.json
只写 data/reports/research_<ts>.html。纯 stdlib。
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = DATA / "reports"


def _json(name, default):
    p = DATA / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _jsonl(name, limit=2000):
    p = DATA / name
    rows = []
    if not p.exists():
        return rows
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        return []
    return rows[-limit:]


def _as_list(v):
    if not v:
        return []
    if isinstance(v, list):
        return v
    try:
        d = json.loads(v)
        return d if isinstance(d, list) else [v]
    except Exception:
        return [v]


def _dedup_postmortems(rows):
    """按 postmortem_uid 去重（latest wins）。postmortems.jsonl 逐周期累积同一笔多版本，
    去重还原 canonical 笔数，避免计数膨胀。输入按文件顺序，后出现者更新。返回去重后列表。"""
    by_uid = {}
    order = []
    for p in rows:
        uid = p.get("postmortem_uid")
        key = uid if uid is not None else id(p)
        if key not in by_uid:
            order.append(key)
        by_uid[key] = p          # latest wins（文件后出现的覆盖前者）
    return [by_uid[k] for k in order]


def _clean_name(p):
    """展示用市场名：优先 market_name，退回 canonical id 并剥 slug:/q: 临时键前缀。"""
    name = str(p.get("market_name") or "").strip()
    if not name:
        cid = str(p.get("canonical_market_id") or "?")
        if cid.startswith("slug:"):
            cid = cid[5:]
        elif cid.startswith("q:"):
            cid = "(未命名市场)"
        name = cid
    return name


def _canonical_positions():
    """优先读 runtime.db 的 canonical paper_positions（按 canonical_market_id 去重）；
    缺库/读失败回退裸 paper_portfolio.json（best-effort）。
    返回 (open_list, closed_list, realized_pnl, source)。"""
    db = DATA / "runtime.db"
    if db.exists():
        try:
            import sqlite3
            c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            c.row_factory = sqlite3.Row
            rows = [dict(r) for r in c.execute(
                "SELECT market_name, canonical_market_id, direction, status, "
                "entry_price, notional_usd, realized_pnl "
                "FROM paper_positions ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END")]
            c.close()
            open_l = [r for r in rows if r.get("status") == "open"]
            closed_l = [r for r in rows if r.get("status") == "closed"]
            realized = sum(r.get("realized_pnl") or 0 for r in closed_l
                           if isinstance(r.get("realized_pnl"), (int, float)))
            return open_l, closed_l, realized, "canonical"
        except Exception:
            pass
    portfolio = _json("paper_portfolio.json", []) or []
    open_l = [p for p in portfolio if isinstance(p, dict) and not p.get("closed_at")]
    closed_l = [p for p in portfolio if isinstance(p, dict) and p.get("closed_at")]
    realized = sum((p.get("realized_pnl") or 0) for p in closed_l
                   if isinstance(p.get("realized_pnl"), (int, float)))
    return open_l, closed_l, realized, "raw"


# 3c-2 失败条件对照 verdict → 短标签（no_prediction 不展示）
_VERDICT_LABEL = {
    "confirmed": "假设成立",
    "refuted": "假设证伪",
    "loss_unexplained": "亏损·预测外",
    "inconclusive": "无定论",
}


def _e(v):
    return html.escape(str(v)) if v is not None else ""


def _grade_chip(g):
    g = (g or "").lower()
    cls = {"approve": "g-ap", "paper_probe": "g-pp", "reject": "g-rj"}.get(g, "g-x")
    label = {"approve": "通过", "paper_probe": "试错", "reject": "拒绝"}.get(g, g)
    return f'<span class="chip {cls}">{label}</span>'


def build_html() -> str:
    rr = _json("review_results.json", {}) or {}
    er = _json("execution_results.json", {}) or {}
    orch = _json("orchestrator_status.json", {}) or {}
    hyps = list(reversed(_jsonl("hypotheses.jsonl")))[:20]
    pms_all = _dedup_postmortems(_jsonl("postmortems.jsonl"))
    pms = list(reversed(pms_all))[:25]
    # 持仓汇总：canonical（runtime.db 去重）优先，缺库回退裸 portfolio
    open_pos, closed_pos, realized, pos_src = _canonical_positions()

    win = sum(1 for p in pms_all if p.get("outcome") == "win")
    loss = sum(1 for p in pms_all if p.get("outcome") == "loss")
    flat = sum(1 for p in pms_all if p.get("outcome") == "flat")

    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

    # ── KPI 卡 ──
    kpis = [
        ("信号", rr.get("total", "—")),
        ("通过", rr.get("approved", 0)),
        ("试错", rr.get("paper_probe", 0)),
        ("拒绝", rr.get("rejected", 0)),
        ("模拟买入", er.get("dry_run", 0)),
        ("成交成功", er.get("success", 0)),
        ("持仓中", len(open_pos)),
        ("已实现盈亏", f"{realized:+.1f}"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="kl">{_e(k)}</div><div class="kv">{_e(v)}</div></div>'
        for k, v in kpis
    )

    # ── 三级评级明细 ──
    def grade_rows(items, grade):
        out = ""
        for it in _as_list(items):
            sig = it.get("signal") or {}
            rv = it.get("review") or {}
            name = it.get("market_name") or sig.get("market_name") or sig.get("market") or "?"
            fp = rv.get("failure_probability")
            ps = sig.get("position_size")
            out += (
                f'<tr><td>{_e(name)}</td><td>{_e(sig.get("direction",""))}</td>'
                f"<td>{_grade_chip(grade)}</td>"
                f'<td>{_e(str(fp)+"%") if fp is not None else "—"}</td>'
                f'<td>{_e(f"{ps*100:.1f}%") if isinstance(ps,(int,float)) else "—"}</td></tr>'
            )
        return out

    grading_rows = (
        grade_rows(rr.get("approved_signals"), "approve")
        + grade_rows(rr.get("probe_signals"), "paper_probe")
        + grade_rows(rr.get("rejected_signals"), "reject")
    ) or '<tr><td colspan="5" class="empty">暂无评级</td></tr>'

    # ── 持仓表（canonical，open 优先）──
    def _num(v):
        return v if isinstance(v, (int, float)) else None

    pos_rows = ""
    for p in open_pos[:30]:
        ep = _num(p.get("entry_price"))
        no = _num(p.get("notional_usd"))
        pos_rows += (
            f'<tr><td>{_e(_clean_name(p))}</td><td>{_e(p.get("direction") or "—")}</td>'
            f'<td>{_e(f"{ep:.4f}") if ep is not None else "—"}</td>'
            f'<td>{_e(f"${no:,.0f}") if no is not None else "—"}</td></tr>'
        )
    pos_rows = pos_rows or '<tr><td colspan="4" class="empty">暂无持有中持仓</td></tr>'
    pos_note = "" if pos_src == "canonical" else '<span class="src src-d">裸 JSON 回退</span>'
    realized_cls = "win" if realized > 0 else ("loss" if realized < 0 else "flat")

    # ── 假设卡 ──
    hyp_html = ""
    for h in hyps:
        src = h.get("source", "derived")
        src_label = "原生" if src == "agent_b" else "派生"
        fc = _as_list(h.get("failure_conditions"))
        fc_html = "".join(f"<li>{_e(c)}</li>" for c in fc[:3])
        hyp_html += (
            f'<div class="card"><div class="ch"><b>{_e(h.get("market_name") or "?")}</b>'
            f'<span class="src {"src-b" if src=="agent_b" else "src-d"}">{src_label}</span></div>'
            f'<div class="meta">方向 {_e(h.get("direction"))} · 置信 {_e(h.get("confidence"))} · '
            f'边 {_e(h.get("expected_edge"))} · 持仓 {_e(h.get("holding_horizon_days"))}天</div>'
            + (f'<div class="lbl">失败条件</div><ul>{fc_html}</ul>' if fc_html else "")
            + "</div>"
        )
    hyp_html = hyp_html or '<div class="empty">暂无假设</div>'

    # ── 复盘卡 ──
    pm_html = ""
    for p in pms:
        oc = p.get("outcome", "?")
        oc_cls = {"win": "win", "loss": "loss"}.get(oc, "flat")
        oc_label = {"win": "盈", "loss": "亏", "flat": "平"}.get(oc, _e(oc))
        pnl = p.get("realized_pnl")
        pnl_s = f" {pnl:+.1f}" if isinstance(pnl, (int, float)) else ""
        vlabel = _VERDICT_LABEL.get(p.get("hypothesis_verdict"))
        flags = (
            (f'<span class="flag vd">{vlabel}</span>' if vlabel else "")
            + "".join(
                f'<span class="flag">{lbl}</span>'
                for lbl, on in [("流动性", p.get("liquidity_issue")), ("时机", p.get("timing_issue")), ("模型", p.get("model_issue"))]
                if on
            )
        )
        pm_html += (
            f'<div class="card"><div class="ch"><b>{_e(_clean_name(p))}</b>'
            f'<span class="oc {oc_cls}">{oc_label}{_e(pnl_s)}</span></div>'
            + (f'<div class="fr">{_e(p.get("failure_reason"))}</div>' if p.get("failure_reason") else "")
            + (f'<div class="flags">{flags}</div>' if flags else "")
            + "</div>"
        )
    pm_html = pm_html or '<div class="empty">暂无复盘</div>'

    orch_state = orch.get("state", "unknown")

    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>研究闭环快照 · {ts}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#0b1020;color:#e2e8f0;font:14px/1.5 -apple-system,system-ui,"PingFang SC",sans-serif;padding:14px 12px 40px}}
h1{{font-size:17px;margin:0 0 2px}}.sub{{color:#94a3b8;font-size:12px;margin-bottom:14px}}
h2{{font-size:14px;color:#cbd5e1;margin:20px 0 8px;border-left:3px solid #3b82f6;padding-left:8px}}
.kgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}
.kpi{{background:#141b2e;border:1px solid #1e293b;border-radius:10px;padding:8px}}
.kl{{font-size:10px;color:#94a3b8;text-transform:uppercase}}.kv{{font-size:18px;font-weight:600;margin-top:2px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{text-align:left;color:#94a3b8;font-weight:500;padding:6px 6px;background:#141b2e}}
td{{padding:6px 6px;border-top:1px solid #1e293b;vertical-align:top}}
.chip{{font-size:10px;padding:1px 6px;border-radius:5px;border:1px solid}}
.g-ap{{color:#6ee7b7;border-color:#065f46;background:#064e3b55}}.g-pp{{color:#fcd34d;border-color:#92400e;background:#78350f55}}.g-rj{{color:#fca5a5;border-color:#991b1b;background:#7f1d1d55}}
.card{{background:#141b2e;border:1px solid #1e293b;border-radius:10px;padding:10px;margin-bottom:8px}}
.ch{{display:flex;justify-content:space-between;gap:8px;align-items:center}}.ch b{{font-size:13px}}
.src{{font-size:10px;padding:1px 6px;border-radius:5px}}.src-b{{color:#7dd3fc;background:#0c4a6e55}}.src-d{{color:#94a3b8;background:#33415555}}
.meta{{color:#94a3b8;font-size:11px;margin-top:4px}}.lbl{{font-size:10px;color:#64748b;margin-top:6px;text-transform:uppercase}}
ul{{margin:2px 0 0;padding-left:18px}}li{{font-size:12px;color:#cbd5e1}}
.oc{{font-size:12px;font-weight:600}}.win{{color:#6ee7b7}}.loss{{color:#fca5a5}}.flat{{color:#94a3b8}}
.fr{{font-size:12px;color:#cbd5e1;margin-top:4px}}.flags{{margin-top:6px}}.flag{{font-size:10px;background:#33415588;color:#cbd5e1;padding:1px 6px;border-radius:5px;margin-right:4px}}.flag.vd{{background:#7f1d1d88;color:#fca5a5}}
.empty{{color:#64748b;text-align:center;padding:16px}}.col2{{}}
@media(min-width:560px){{.col2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}}}
.foot{{margin-top:24px;color:#475569;font-size:11px;text-align:center}}
</style></head><body>
<h1>🔬 研究闭环快照</h1>
<div class="sub">{ts} · 调度: {_e(orch_state)} · 只读 · 模拟盘</div>

<div class="kgrid">{kpi_html}</div>

<h2>💼 Paper 持仓 · canonical {pos_note}</h2>
<div class="sub">持有中 {len(open_pos)} · 已平仓 {len(closed_pos)} · 已实现盈亏 <span class="oc {realized_cls}">{realized:+.1f}</span></div>
<table><thead><tr><th>市场</th><th>方向</th><th>入场</th><th>名义</th></tr></thead>
<tbody>{pos_rows}</tbody></table>

<h2>Agent M · 三级风险评级</h2>
<table><thead><tr><th>市场</th><th>方向</th><th>评级</th><th>失败概率</th><th>仓位</th></tr></thead>
<tbody>{grading_rows}</tbody></table>

<div class="col2">
<div><h2>Agent B · 研究假设</h2>{hyp_html}</div>
<div><h2>Agent G · 复盘 (盈 {win}/亏 {loss}/平 {flat})</h2>{pm_html}</div>
</div>

<div class="foot">polymarket_arbitrage · 自包含离线快照 · 无需服务器</div>
</body></html>"""


def write_report() -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = REPORTS / f"research_{ts}.html"
    out.write_text(build_html(), encoding="utf-8")
    return out


def main():
    p = write_report()
    print(str(p))


if __name__ == "__main__":
    main()
