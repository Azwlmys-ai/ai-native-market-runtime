#!/usr/bin/env python3
"""
polymarket_arbitrage 本地控制网关
供 Hermes Gateway / Telegram Bot 通过 terminal toolset 调用

用法:
  python3 scripts/local_gateway_control.py status [--telegram]
  python3 scripts/local_gateway_control.py health [--telegram]
  python3 scripts/local_gateway_control.py metrics [--telegram]
  python3 scripts/local_gateway_control.py agents [--telegram]
  python3 scripts/local_gateway_control.py run-once --dry-run [--telegram]

--telegram 模式:
  启用 Telegram 安全输出，总长度严格控制在 3000 字符以内。
  建议 Gateway 始终传入此参数以防止消息截断。

安全护栏:
  - run-once 必须带 --dry-run，否则拒绝执行
  - 不修改任何 Agent 核心逻辑、风控阈值或交易策略
"""

import sys
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None

ROOT = Path(__file__).resolve().parent.parent
RUN_STATE_FILE = ROOT / "data" / "gateway_run_once_state.json"

# Telegram 单条消息安全上限（留余量给 Markdown 格式开销）
TELEGRAM_MAX_CHARS = 3000


# ─── 工具函数 ────────────────────────────────────────────────────────────────

def _read_json(path):
    p = ROOT / path
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _log_tail(log_path, n=3):
    p = ROOT / log_path
    if not p.exists():
        return []
    lines = p.read_text(errors="replace").splitlines()
    return lines[-n:] if len(lines) >= n else lines


def _ensure_mock_pm_trader():
    mock = "/tmp/mock_pm_trader.sh"
    with open(mock, "w") as f:
        f.write(
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  balance)\n"
            '    printf \'{"ok":true,"data":{"total_value":0,"cash":0,"pnl":0}}\\n\'\n'
            "    ;;\n"
            "  portfolio)\n"
            '    printf \'{"ok":true,"data":[]}\\n\'\n'
            "    ;;\n"
            "  *)\n"
            '    printf \'{"ok":true,"dry_run":true}\\n\'\n'
            "    ;;\n"
            "esac\n"
        )
    os.chmod(mock, 0o755)
    return mock


def _cap(text, max_len=TELEGRAM_MAX_CHARS):
    """把输出裁剪到安全长度，超出时附加说明。"""
    if len(text) <= max_len:
        return text
    suffix = f"\n\n…（内容已裁剪，共 {len(text)} 字符，超出 Telegram 限制）"
    return text[: max_len - len(suffix)] + suffix


def _fmt_ts(ts):
    """把 ISO 时间戳压缩为 MM-DD HH:MM 格式。"""
    if not ts:
        return "N/A"
    try:
        return ts[5:16].replace("T", " ")  # MM-DD HH:MM
    except Exception:
        return str(ts)[:16]


def _now_label():
    local_tz = ZoneInfo("Asia/Shanghai") if ZoneInfo else timezone(timedelta(hours=8))
    local_now = datetime.now(local_tz)
    utc_now = datetime.now(timezone.utc)
    return (
        f"本地 {local_now.strftime('%m-%d %H:%M')} Asia/Shanghai / "
        f"UTC {utc_now.strftime('%m-%d %H:%M')}"
    )


def _sell_signal_summary():
    signals = _read_json("data/sell_signals.json")
    if not isinstance(signals, list) or not signals:
        return None

    urgent = [s for s in signals if s.get("priority") == "urgent"]
    high = [s for s in signals if s.get("priority") == "high"]
    top = urgent or high or signals
    names = []
    for signal in top[:2]:
        market = str(signal.get("market", "?"))
        short = market.replace("will-the-", "").replace("-win-the-2026-nhl-stanley-cup", "")
        names.append(f"{short}:{signal.get('reason', '')[:24]}")
    return {
        "total": len(signals),
        "urgent": len(urgent),
        "high": len(high),
        "examples": names,
    }


def _position_index():
    positions = _read_json("data/positions.json")
    if not isinstance(positions, list):
        return {}

    index = {}
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        slug = pos.get("market_slug") or pos.get("market") or pos.get("market_id")
        outcome = pos.get("outcome")
        if slug:
            index[str(slug)] = pos
            if outcome:
                index[f"{slug}:{outcome}"] = pos
    return index


def _find_position_for_signal(signal, positions):
    market = signal.get("market") or signal.get("market_id")
    outcome = signal.get("outcome") or signal.get("token_id")
    if not market:
        return None
    return positions.get(f"{market}:{outcome}") or positions.get(str(market))


def _trading_mode_summary():
    launchd_plist = Path.home() / "Library" / "LaunchAgents" / "com.libo.polymarket-orchestrator-dryrun.plist"
    scheduler_script = ROOT / "scripts" / "scheduled_orchestrator_dryrun.sh"
    legacy_script = Path.home() / ".hermes" / "home" / "scripts" / "polymarket_arbitrage_script.sh"
    stop_file = ROOT / "data" / "STOP_TRADING"

    mode = "UNKNOWN"
    reasons = []
    for path in (scheduler_script, legacy_script):
        try:
            text = path.read_text()
        except Exception:
            continue
        if "EXECUTOR_DRY_RUN=1" in text or "export EXECUTOR_DRY_RUN=1" in text:
            mode = "DRY_RUN"
            reasons.append(path.name)

    schedule = []
    if launchd_plist.exists():
        schedule.append("launchd 900s dry-run")
    if legacy_script.exists():
        schedule.append("legacy dry-run script")

    return {
        "mode": mode,
        "reasons": reasons,
        "schedule": schedule,
        "stop_trading": stop_file.exists(),
    }


def _pid_running(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _read_run_state():
    try:
        if RUN_STATE_FILE.exists():
            return json.loads(RUN_STATE_FILE.read_text())
    except Exception:
        pass
    return None


def _write_run_state(state):
    RUN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUN_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _infer_run_status(state):
    if not state:
        return "none", []

    pid = state.get("pid")
    running = _pid_running(pid) if pid else False
    log_rel = state.get("log")
    full_tail = _log_tail(log_rel, 200) if log_rel else []
    tail = full_tail[-8:]

    if running:
        return "running", tail
    if any("run_once 退出码: 0" in line for line in full_tail):
        return "completed", tail
    if any("run_once 退出码:" in line for line in full_tail):
        return "failed", tail
    if any("扫描周期完成" in line for line in full_tail):
        return "completed", tail
    return "exited_unknown", tail


# ─── 命令实现 ────────────────────────────────────────────────────────────────

def cmd_status(telegram=False):
    lines = [f"📊 系统状态 [{_now_label()}]"]

    # 健康（最重要，放最前）
    hr = _read_json("data/health_report.json")
    if hr:
        icon = "⚠️" if hr.get("alert_required") else "✅"
        lines.append(f"{icon} {hr.get('overall_status','unknown')}  检查:{_fmt_ts(hr.get('timestamp'))}")
        issues = hr.get("issues", [])
        if issues:
            for iss in issues[:3]:
                lines.append(f"  • {str(iss)[:60]}")
    else:
        lines.append("⚠️ health_report.json 不存在")

    mode = _trading_mode_summary()
    if mode["mode"] == "DRY_RUN":
        lines.append("🛡 交易模式: DRY_RUN 强制，真实买卖禁用")
    else:
        lines.append(f"🛡 交易模式: {mode['mode']}")
    if mode["schedule"]:
        lines.append(f"⏱ 调度: {', '.join(mode['schedule'])}")
    if mode["stop_trading"]:
        lines.append("🛑 STOP_TRADING 文件存在")

    lines.append("")

    # 执行结果
    er = _read_json("data/execution_results.json")
    if er:
        suc = er.get("success", 0)
        dry = er.get("dry_run", 0)
        tot = er.get("total", 0)
        ts = _fmt_ts(er.get("timestamp"))
        lines.append(f"📋 买入执行 [{ts}]  total:{tot} dry:{dry} ✅成功:{suc}")
    else:
        lines.append("📋 execution_results.json 不存在")

    ser = _read_json("data/sell_execution_results.json")
    if ser:
        lines.append(
            f"📋 卖出执行 [{_fmt_ts(ser.get('timestamp'))}]  "
            f"total:{ser.get('total',0)} dry:{ser.get('dry_run',0)} "
            f"✅成功:{ser.get('success',0)} failed:{ser.get('failed',0)}"
        )
    sell_pending = _sell_signal_summary()
    if sell_pending:
        lines.append(
            f"📤 待卖出信号: {sell_pending['total']} 条 "
            f"(urgent:{sell_pending['urgent']} high:{sell_pending['high']})"
        )
        for item in sell_pending["examples"]:
            lines.append(f"  • {item}")

    # 信号
    sigs = _read_json("data/signals.json")
    rr = _read_json("data/review_results.json")
    ap = _read_json("data/approved_signals.json")
    sig_cnt = len(sigs) if sigs is not None else "?"
    ap_cnt = len(ap) if isinstance(ap, list) else "?"
    if rr:
        approved = rr.get("approved", 0)
        rejected = rr.get("rejected", 0)
        lines.append(f"📡 信号: {sig_cnt} 条  审查通过:{approved} 拒绝:{rejected}  待执行:{ap_cnt}")
        if approved == 0 and er and er.get("total", 0) == 0:
            lines.append("  • 执行 total=0 是因为无审查通过信号，不是去重/持仓限制")
    else:
        lines.append(f"📡 信号: {sig_cnt} 条  待执行:{ap_cnt}")

    # 日志尾部（Telegram 模式只取 2 行，非 Telegram 取 5 行）
    today = datetime.now().strftime("%Y%m%d")
    n_tail = 2 if telegram else 5
    tail = _log_tail(f"logs/orchestrator_{today}.log", n_tail)
    if tail:
        lines.append("")
        lines.append("📝 最新日志:")
        for l in tail:
            # 截断过长的日志行
            lines.append(f"  {l[:90]}")
    else:
        lines.append("📝 今日无 orchestrator 日志")

    orch = _read_json("data/orchestrator_status.json")
    if orch:
        lines.append("")
        lines.append(
            f"🧭 Orchestrator: {orch.get('state','?')}  更新:{_fmt_ts(orch.get('updated_at'))}"
        )
        if orch.get("current_step"):
            lines.append(f"  step: {str(orch.get('current_step'))[:80]}")
        lines.append(f"  last: {str(orch.get('last_log') or '-')[:80]}")

    result = "\n".join(lines)
    return _cap(result) if telegram else result


def cmd_health(telegram=False):
    hr = _read_json("data/health_report.json")
    if hr is None:
        return "❌ health_report.json 不存在"

    icon = "⚠️" if hr.get("alert_required") else "✅"
    lines = [
        f"🏥 健康检查 [{_fmt_ts(hr.get('timestamp'))}]",
        f"{icon} {hr.get('overall_status','unknown')}",
    ]

    issues = hr.get("issues", [])
    max_issues = 5 if telegram else 8
    if issues:
        lines.append(f"问题 ({len(issues)}):")
        for iss in issues[:max_issues]:
            lines.append(f"  • {str(iss)[:80]}")
        if len(issues) > max_issues:
            lines.append(f"  …（另 {len(issues)-max_issues} 条省略）")
    else:
        lines.append("无问题 ✅")

    recs = hr.get("recommendations", [])
    max_recs = 2 if telegram else 4
    if recs:
        lines.append(f"建议 ({len(recs)}):")
        for r in recs[:max_recs]:
            lines.append(f"  → {str(r)[:80]}")

    result = "\n".join(lines)
    return _cap(result) if telegram else result


def cmd_metrics(telegram=False):
    lines = [f"📈 执行指标 [{_now_label()}]"]

    er = _read_json("data/execution_results.json")
    if er:
        lines.append(f"上次: {_fmt_ts(er.get('timestamp'))}")
        lines.append(f"买入 total:{er.get('total',0)}  dry:{er.get('dry_run',0)}  ✅成功:{er.get('success',0)}  failed:{er.get('failed',0)}")
        results = er.get("results", [])
        max_detail = 3 if telegram else 5
        if results:
            lines.append(f"明细 (最多 {max_detail}):")
            for r in results[:max_detail]:
                mid = r.get("market_id", "?")[:35]
                lines.append(f"  {mid}  {r.get('status','?')}")
    else:
        lines.append("execution_results.json 不存在")

    ser = _read_json("data/sell_execution_results.json")
    if ser:
        lines.append(
            f"卖出 total:{ser.get('total',0)}  dry:{ser.get('dry_run',0)}  "
            f"✅成功:{ser.get('success',0)}  failed:{ser.get('failed',0)}"
        )
    sell_pending = _sell_signal_summary()
    if sell_pending:
        lines.append(
            f"待卖出:{sell_pending['total']}  urgent:{sell_pending['urgent']}  high:{sell_pending['high']}"
        )

    sigs = _read_json("data/signals.json")
    rr = _read_json("data/review_results.json")
    ap = _read_json("data/approved_signals.json")
    if rr:
        lines.append(
            f"信号:{len(sigs) if sigs is not None else '?'}  "
            f"审查通过:{rr.get('approved', 0)}  拒绝:{rr.get('rejected', 0)}  "
            f"待执行:{len(ap) if isinstance(ap,list) else '?'}"
        )
    else:
        lines.append(f"信号:{len(sigs) if sigs is not None else '?'}  待执行:{len(ap) if isinstance(ap,list) else '?'}")

    result = "\n".join(lines)
    return _cap(result) if telegram else result


def cmd_live_readiness(telegram=False):
    mode = _trading_mode_summary()
    rr = _read_json("data/review_results.json") or {}
    er = _read_json("data/execution_results.json") or {}
    ser = _read_json("data/sell_execution_results.json") or {}
    risk = _read_json("data/risk_snapshot.json") or {}
    exposure = risk.get("exposure", {})
    violations = exposure.get("violations", [])
    pending_sell = _sell_signal_summary()

    blockers = []
    warnings = []

    if mode["mode"] == "DRY_RUN":
        blockers.append("调度脚本强制 EXECUTOR_DRY_RUN=1，真实交易关闭")
    if mode["stop_trading"]:
        blockers.append("STOP_TRADING 文件存在")
    if rr.get("approved", 0) == 0:
        warnings.append("Agent M 当前审查通过=0，买入侧即使 live 也无单可下")
    if pending_sell:
        warnings.append(
            f"存在待卖出信号 {pending_sell['total']} 条，其中 urgent={pending_sell['urgent']}"
        )
    if ser and ser.get("dry_run", 0):
        warnings.append(f"上次卖出执行为 dry_run={ser.get('dry_run', 0)}，未真实调用 pm-trader sell")
    if violations:
        for v in violations[:3]:
            if v.get("type") == "single_theme_exposure":
                warnings.append(f"主题暴露超限: {v.get('theme')} ${v.get('value')}")
            else:
                warnings.append(f"风险违规: {v.get('type')} ${v.get('value')}")

    lines = ["🧪 Live readiness（只读）"]
    lines.append(f"模式: {mode['mode']}")
    if mode["schedule"]:
        lines.append(f"调度: {', '.join(mode['schedule'])}")
    lines.append(f"买入: total={er.get('total', 0)} success={er.get('success', 0)} dry={er.get('dry_run', 0)}")
    lines.append(f"卖出: total={ser.get('total', 0)} success={ser.get('success', 0)} dry={ser.get('dry_run', 0)} failed={ser.get('failed', 0)}")
    lines.append(f"审查: approved={rr.get('approved', 0)} rejected={rr.get('rejected', 0)}")

    if blockers:
        lines.append("阻断:")
        for item in blockers:
            lines.append(f"  - {item}")
    else:
        lines.append("阻断: 无硬阻断（仍需人工确认才能 live）")

    if warnings:
        lines.append("风险/注意:")
        for item in warnings[:6]:
            lines.append(f"  - {item}")

    result = "\n".join(lines)
    return _cap(result) if telegram else result


def cmd_sell_plan(telegram=False):
    signals = _read_json("data/sell_signals.json")
    if not isinstance(signals, list) or not signals:
        return "📤 卖出计划（只读）\n无待卖出信号"

    positions = _position_index()
    ser = _read_json("data/sell_execution_results.json") or {}
    mode = _trading_mode_summary()

    lines = ["📤 卖出计划（只读，不下单）"]
    lines.append(
        f"模式:{mode['mode']}  上次卖出 total:{ser.get('total',0)} "
        f"dry:{ser.get('dry_run',0)} success:{ser.get('success',0)} failed:{ser.get('failed',0)}"
    )

    actionable = 0
    for signal in signals[:6]:
        market = str(signal.get("market") or signal.get("market_id") or "?")
        short = market.replace("will-the-", "").replace("-win-the-2026-nhl-stanley-cup", "")
        outcome = signal.get("outcome") or signal.get("token_id") or "?"
        shares = float(signal.get("shares") or signal.get("amount") or 0)
        priority = signal.get("priority", "medium")
        pos = _find_position_for_signal(signal, positions) or {}
        value = float(pos.get("current_value") or 0)
        live_price = float(pos.get("live_price") or 0)

        flags = []
        if priority != "urgent":
            flags.append("非 urgent")
        if shares <= 0:
            flags.append("无 shares")
        if live_price <= 0:
            flags.append("价格=0/疑似无买盘")
        if 0 < value < 1:
            flags.append("市值<$1")
        if not pos:
            flags.append("未匹配持仓")

        if not flags:
            actionable += 1
            verdict = "可进入人工确认"
        else:
            verdict = "不建议自动实盘: " + "、".join(flags)

        lines.append(
            f"• {short} {outcome} sh:{shares:.4g} price:{live_price:.4g} "
            f"value:${value:.2f} [{priority}]"
        )
        lines.append(f"  → {verdict}")

    if len(signals) > 6:
        lines.append(f"…另 {len(signals)-6} 条省略")

    lines.append("")
    if actionable:
        lines.append(f"结论: {actionable} 条可做人工 live 确认；当前脚本仍不会真实下单。")
    else:
        lines.append("结论: 当前没有适合自动实盘卖出的信号；保持 dry-run 更稳。")

    result = "\n".join(lines)
    return _cap(result) if telegram else result


def cmd_agents(telegram=False):
    today = datetime.now().strftime("%Y%m%d")
    log_dir = ROOT / "logs"
    lines = [f"🤖 Agent [{today}]"]

    agent_logs = sorted(log_dir.glob(f"*_{today}.log"),
                        key=lambda p: p.stat().st_size, reverse=True)
    if not agent_logs:
        lines.append("今日无 Agent 日志")
        return "\n".join(lines)

    # Telegram 模式只显示前 10 个（按大小排序），非 Telegram 全部
    max_agents = 10 if telegram else len(agent_logs)
    for log_path in agent_logs[:max_agents]:
        name = log_path.stem.replace(f"_{today}", "")[:25]
        size = log_path.stat().st_size
        tail = _log_tail(f"logs/{log_path.name}", 1)
        # 截断日志行到 70 chars
        last = (tail[0][:70] if tail else "(空)") if not telegram else (tail[0][:50] if tail else "(空)")
        lines.append(f"  {name:<25}  {size:5d}B  {last}")

    if len(agent_logs) > max_agents:
        lines.append(f"  …（另 {len(agent_logs)-max_agents} 个省略）")

    result = "\n".join(lines)
    return _cap(result) if telegram else result


def cmd_run_once(dry_run: bool, telegram: bool = False):
    if not dry_run:
        return (
            "❌ 安全护栏：run-once 只允许带 --dry-run 参数\n"
            "正确用法: python3 scripts/local_gateway_control.py run-once --dry-run"
        )

    existing = _read_run_state()
    existing_status, _ = _infer_run_status(existing)
    if existing_status == "running":
        return cmd_run_status(telegram=telegram)

    mock_path = _ensure_mock_pm_trader()
    env = {
        **os.environ,
        "EXECUTOR_DRY_RUN": "1",
        "PM_TRADER_PATH": mock_path,
        "PYTHONPATH": str(ROOT),
        "PYTHONUNBUFFERED": "1",
    }

    ts = datetime.now()
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"gateway_run_once_{ts.strftime('%Y%m%d_%H%M%S')}.log"
    log_rel = str(log_file.relative_to(ROOT))
    try:
        log_handle = open(log_file, "a")
        proc = subprocess.Popen(
            ["bash", str(ROOT / "scripts" / "run_local_dryrun.sh")],
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
            start_new_session=True,
        )
        log_handle.close()
        state = {
            "pid": proc.pid,
            "started_at": ts.isoformat(),
            "log": log_rel,
            "dry_run": True,
        }
        _write_run_state(state)
        lines = [
            f"🚀 dry-run 已后台启动 [{ts.strftime('%m-%d %H:%M:%S')}]",
            f"pid:{proc.pid}",
            f"log:{log_rel}",
            "用 run-status --telegram 查看进度",
        ]
    except Exception as e:
        lines = [f"❌ 启动异常: {e}"]

    result = "\n".join(lines)
    return _cap(result) if telegram else result


def cmd_run_status(telegram=False):
    state = _read_run_state()
    if not state:
        return "ℹ️ 无 gateway dry-run 记录"

    status, tail = _infer_run_status(state)
    lines = [
        f"🧪 dry-run 状态: {status}",
        f"pid:{state.get('pid', '?')}  started:{_fmt_ts(state.get('started_at'))}",
        f"log:{state.get('log', '?')}",
    ]

    orch = _read_json("data/orchestrator_status.json")
    if orch:
        lines.append(
            f"orchestrator:{orch.get('state','?')}  step:{str(orch.get('current_step') or '-')[:70]}"
        )
        lines.append(f"last:{str(orch.get('last_log') or '-')[:90]}")

    if tail:
        n_tail = 5 if telegram else 8
        lines.append(f"tail:")
        for line in tail[-n_tail:]:
            lines.append(f"  {line[:100]}")

    result = "\n".join(lines)
    return _cap(result) if telegram else result


# ─── 主入口 ──────────────────────────────────────────────────────────────────

COMMANDS = {
    "status": cmd_status,
    "health": cmd_health,
    "metrics": cmd_metrics,
    "agents": cmd_agents,
    "live-readiness": cmd_live_readiness,
    "sell-plan": cmd_sell_plan,
    "run-status": cmd_run_status,
}

HELP = """polymarket_arbitrage 本地控制网关

用法:
  python3 scripts/local_gateway_control.py <command> [--telegram] [--dry-run]

命令:
  status              系统状态快照
  health              健康报告
  metrics             执行指标
  agents              Agent 日志概览
  live-readiness      只读检查 live 交易阻断项和风险
  sell-plan           只读检查待卖出信号是否适合人工 live 确认
  run-once --dry-run  后台触发单次 dry-run 扫描（禁止真实交易）
  run-status          查看后台 dry-run 进度

选项:
  --telegram   启用 Telegram 安全模式（输出 ≤ 3000 字符）
  --dry-run    run-once 时必须提供，否则被拒绝
"""

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(HELP)
        sys.exit(0)

    command = sys.argv[1]
    dry_run_flag = "--dry-run" in sys.argv
    telegram_flag = "--telegram" in sys.argv

    if command == "run-once":
        print(cmd_run_once(dry_run=dry_run_flag, telegram=telegram_flag))
    elif command in COMMANDS:
        print(COMMANDS[command](telegram=telegram_flag))
    else:
        print(f"❌ 未知命令: {command}\n")
        print(HELP)
        sys.exit(1)
