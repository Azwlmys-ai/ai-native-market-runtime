#!/usr/bin/env python3
"""Paper P&L Report Generator

从 data/paper_portfolio.json + data/paper_pnl_history.jsonl 生成
可读的盈亏报告。

输出：
  --text   终端 ASCII 表格（默认）
  --json   纯 JSON
  --md     保存到 reports/paper_pnl_YYYYMMDD.md

用法：
  EXECUTOR_DRY_RUN=1 python scripts/paper_pnl_report.py
  python scripts/paper_pnl_report.py --md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from paper_pnl import PaperPortfolio, DEFAULT_ACCOUNT_BALANCE


REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_history(history_file: Path) -> list[dict]:
    snapshots = []
    if history_file.exists():
        with open(history_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        snapshots.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return snapshots


def calc_metrics(snapshots: list[dict]) -> dict:
    """从历史快照计算衍生指标。

    返回值：equity_curve（累积资金曲线）, drawdown（最大回撤率）
    """
    if not snapshots:
        return {"equity_curve": [], "max_drawdown": 0.0, "total_cycles": 0}

    equity = [DEFAULT_ACCOUNT_BALANCE + s["total_pnl"] for s in snapshots]
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    return {
        "equity_curve": equity,
        "max_drawdown": round(max_dd, 4),
        "total_cycles": len(snapshots),
        "last_equity": equity[-1] if equity else DEFAULT_ACCOUNT_BALANCE,
        "peak_equity": peak,
    }


def build_text_report(pp: PaperPortfolio, snapshots: list[dict]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("  PAPER P&L 盈亏统计报告")
    lines.append(f"  生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)
    lines.append("")

    # ---- 当前持仓 ----
    lines.append("-" * 70)
    open_pos = pp.get_open_positions()
    lines.append(f"  当前开仓：{len(open_pos)} 笔")
    if open_pos:
        lines.append(f"  {'市场':<40} {'方向':>4} {'入场价':>8} {'大小':>6} {'名义':>10}")
        for p in open_pos:
            lines.append(
                f"  {p.market_name[:38]:<40} {p.direction:>4} "
                f"${p.entry_price:>7.3f} {p.position_size:>5.0%} "
                f"${p.notional_usd:>9.0f}"
            )
    lines.append("")

    # ---- 已平仓统计 ----
    lines.append("-" * 70)
    closed = [p for p in pp.positions if p.closed_at]
    winning = [p for p in closed if p.realized_pnl > 0]
    losing = [p for p in closed if p.realized_pnl < 0]
    flat = [p for p in closed if p.realized_pnl == 0]

    lines.append(f"  已平仓：{len(closed)} 笔")
    lines.append(f"    赢利：{len(winning)} 笔  亏损：{len(losing)} 笔  持平：{len(flat)} 笔")

    total_realized = pp.get_realized_pnl_total()
    total_unrealized = pp.get_unrealized_pnl_total()
    lines.append(f"  已实现盈亏：${total_realized:+.4f}")
    lines.append(f"  未实现盈亏：${total_unrealized:+.4f}")
    lines.append(f"  总 盈 亏  ：${(total_realized + total_unrealized):+.4f}")

    if closed:
        win_rate = len(winning) / len(closed) * 100
        lines.append(f"  胜率：{win_rate:.1f}%")
        avg_win = sum(p.realized_pnl for p in winning) / len(winning) if winning else 0
        avg_loss = sum(p.realized_pnl for p in losing) / len(losing) if losing else 0
        lines.append(f"  平均赢利：${avg_win:+.4f}")
        lines.append(f"  平均亏损：${avg_loss:+.4f}")
        if avg_loss != 0:
            lines.append(f"  盈亏比：{abs(avg_win / avg_loss):.2f}")

    # ---- 最近 10 笔平仓 ----
    lines.append("")
    lines.append("-" * 70)
    lines.append("  最近已平仓（最多10笔）：")
    recent = sorted(closed, key=lambda p: p.closed_at or "", reverse=True)[:10]
    for i, p in enumerate(recent):
        lines.append(
            f"    {i+1}. {p.market_name[:50]:<50} "
            f"{p.direction} ${p.realized_pnl:+.4f}  "
            f"({p.closed_at or ''})"
        )

    # ---- 历史曲线 ----
    metrics = calc_metrics(snapshots)
    lines.append("")
    lines.append("-" * 70)
    lines.append(f"  历史快照数：{metrics['total_cycles']}")
    lines.append(f"  起始权益：${DEFAULT_ACCOUNT_BALANCE:,.0f}")
    lines.append(f"  当前权益：${metrics['last_equity']:,.2f}")
    lines.append(f"  峰值权益：${metrics['peak_equity']:,.2f}")
    lines.append(f"  最大回撤：{metrics['max_drawdown']:.2%}")
    lines.append(f"  总回报率：{(metrics['last_equity'] - DEFAULT_ACCOUNT_BALANCE) / DEFAULT_ACCOUNT_BALANCE:.4%}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def build_json_report(pp: PaperPortfolio, snapshots: list[dict]) -> dict:
    summary = pp.get_summary()
    metrics = calc_metrics(snapshots)
    summary["metrics"] = metrics
    return summary


def build_md_report(pp: PaperPortfolio, snapshots: list[dict]) -> str:
    """生成 Markdown 格式报告并保存到文件。"""
    summary = pp.get_summary()
    metrics = calc_metrics(snapshots)
    today = datetime.now().strftime("%Y%m%d")

    lines = []
    lines.append(f"# Paper P&L Report — {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("## 账户概览")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 虚拟本金 | ${DEFAULT_ACCOUNT_BALANCE:,} |")
    lines.append(f"| 当前权益 | ${metrics['last_equity']:,.2f} |")
    lines.append(f"| 峰值权益 | ${metrics['peak_equity']:,.2f} |")
    lines.append(f"| 已实现盈亏 | ${summary['realized_pnl']:+,.4f} |")
    lines.append(f"| 未实现盈亏 | ${summary['unrealized_pnl']:+,.4f} |")
    lines.append(f"| 总盈亏 | ${summary['total_pnl']:+,.4f} |")
    lines.append(f"| 总回报率 | {(metrics['last_equity'] - DEFAULT_ACCOUNT_BALANCE) / DEFAULT_ACCOUNT_BALANCE:.4%} |")
    lines.append(f"| 最大回撤 | {metrics['max_drawdown']:.2%} |")
    lines.append("")

    lines.append("## 交易统计")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 总平仓数 | {summary['closed_positions']} |")
    lines.append(f"| 赢利 | {summary['winning_trades']} |")
    lines.append(f"| 亏损 | {summary['losing_trades']} |")
    lines.append(f"| 胜率 | {summary['win_rate']:.1%} |")
    lines.append(f"| 平均赢利 | ${summary['avg_win']:+,.4f} |")
    lines.append(f"| 平均亏损 | ${summary['avg_loss']:+,.4f} |")
    lines.append(f"| 盈亏比 | {summary['profit_factor']:.2f} |")
    lines.append(f"| 当前开仓 | {summary['open_positions']} |")
    lines.append(f"| 历史快照 | {metrics['total_cycles']} |")
    lines.append("")

    if summary["open_positions_detail"]:
        lines.append("## 当前持仓")
        lines.append("")
        lines.append("| 市场 | 方向 | 入场价 | 名义金额 |")
        lines.append("|------|------|--------|----------|")
        for p in summary["open_positions_detail"]:
            lines.append(
                f"| {p['market_name'][:60]} | {p['direction']} | "
                f"${p['entry_price']:.3f} | ${p['notional_usd']:.0f} |"
            )
        lines.append("")

    lines.append(f"*自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC*")
    content = "\n".join(lines)

    # 保存到文件
    output_path = REPORTS_DIR / f"paper_pnl_{today}.md"
    with open(output_path, "w") as f:
        f.write(content)
    print(f"✅ Markdown 报告已保存到 {output_path}")

    return content


def main():
    parser = argparse.ArgumentParser(description="Paper P&L Report Generator")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--md", action="store_true", help="生成 Markdown 报告文件")
    args = parser.parse_args()

    pp = PaperPortfolio()
    history_file = pp.history_file
    snapshots = load_history(history_file)

    if args.md:
        content = build_md_report(pp, snapshots)
        print(content)
    elif args.json:
        report = build_json_report(pp, snapshots)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        report = build_text_report(pp, snapshots)
        print(report)


if __name__ == "__main__":
    main()