#!/usr/bin/env python3
"""
账户级亏损 Watchdog
独立于 orchestrator 和 Agent I 运行。

功能：
  - 读取账户、持仓、执行状态
  - 检查 drawdown / 持仓数 / 暴露风险 / 数据陈旧度
  - 触发阈值时写入 emergency_state.json 和 STOP_TRADING 文件
  - 尝试 Telegram 推送（未配置时安全降级）

用法：
  python3 scripts/account_watchdog.py --once --dry-run
  python3 scripts/account_watchdog.py --test-telegram --dry-run
  python3 scripts/account_watchdog.py --once

环境变量阈值（可覆盖）：
  WATCHDOG_MAX_DAILY_LOSS_PCT    默认 -10.0（%）
  WATCHDOG_MAX_DRAWDOWN_PCT      默认 -20.0（%，读 system_config.drawdown_halt）
  WATCHDOG_MAX_OPEN_POSITIONS    默认 50
  WATCHDOG_MAX_STALE_SECONDS     默认 86400（24h）
  WATCHDOG_MAX_TOTAL_EXPOSURE    默认 9000（USD）

Telegram（可选）：
  TELEGRAM_BOT_TOKEN             Bot Token
  TELEGRAM_CHAT_ID               Chat ID（默认从 ~/.hermes/channel_directory.json 读）
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

STOP_TRADING_FILE = DATA_DIR / "STOP_TRADING"
EMERGENCY_STATE_FILE = DATA_DIR / "emergency_state.json"

# ─── 默认阈值 ───────────────────────────────────────────────────────────────

def _load_system_config_thresholds():
    cfg_path = ROOT / "config" / "system_config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
        risk = cfg.get("risk_management", {})
        acct = cfg.get("account", {})
        return {
            "starting_balance": acct.get("starting_balance", 10000.0),
            "drawdown_halt": risk.get("drawdown_halt", 20),
            "drawdown_warning": risk.get("drawdown_warning", 10),
        }
    except Exception:
        return {"starting_balance": 10000.0, "drawdown_halt": 20, "drawdown_warning": 10}


def _env_float(name, default):
    val = os.environ.get(name)
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return default


def _env_int(name, default):
    val = os.environ.get(name)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return default


# ─── 数据读取 ────────────────────────────────────────────────────────────────

def _read_json(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _get_pm_trader_balance():
    """通过 pm-trader balance 获取账户余额（可能失败）。"""
    try:
        from _paths import get_pm_trader, get_pm_trader_env
        trader = get_pm_trader()
        env = get_pm_trader_env()
        result = subprocess.run(
            [trader, "balance"],
            capture_output=True, text=True, timeout=10, env=env
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if data.get("ok"):
                return data.get("data", {})
    except Exception:
        pass
    return None


def gather_account_state():
    """
    收集账户状态。优先级：pm-trader balance > positions.json 推导。
    返回 dict 包含 total_value, pnl, drawdown_pct, cash, positions_value,
    open_positions, total_exposure, last_exec_ts, stale_seconds.
    """
    cfg = _load_system_config_thresholds()
    starting = cfg["starting_balance"]
    now_ts = datetime.now(timezone.utc).timestamp()

    # 1. 持仓数据（positions.json — 始终可读）
    positions = _read_json(DATA_DIR / "positions.json") or []
    if not isinstance(positions, list):
        positions = []

    open_positions = len(positions)
    total_exposure = sum(p.get("total_cost", 0) for p in positions)
    positions_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
    positions_value = sum(p.get("current_value", 0) for p in positions)

    # 2. 尝试 pm-trader balance（容器内才有效）
    balance = _get_pm_trader_balance()
    if balance:
        total_value = balance.get("total_value", positions_value)
        cash = balance.get("cash", 0)
        pnl = balance.get("pnl", positions_pnl)
        source = "pm-trader"
    else:
        # 回退：用持仓数据估算（无法得知现金，用 starting - exposure 估算）
        estimated_cash = max(0, starting - total_exposure)
        total_value = positions_value + estimated_cash
        cash = estimated_cash
        pnl = total_value - starting
        source = "positions.json (estimated)"

    drawdown_pct = (pnl / starting * 100) if starting > 0 else 0

    # 3. 执行结果陈旧度
    er = _read_json(DATA_DIR / "execution_results.json") or {}
    last_exec_ts_str = er.get("timestamp", "")
    stale_seconds = None
    if last_exec_ts_str:
        try:
            last_dt = datetime.fromisoformat(last_exec_ts_str.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                # Project timestamps are written with datetime.now().isoformat() — local time.
                # .astimezone() on a naive datetime uses the OS local timezone (Python ≥ 3.6).
                last_dt = last_dt.astimezone(timezone.utc)
            stale_seconds = now_ts - last_dt.timestamp()
        except Exception:
            pass

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "total_value": round(total_value, 2),
        "cash": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "starting_balance": starting,
        "pnl": round(pnl, 2),
        "drawdown_pct": round(drawdown_pct, 2),
        "open_positions": open_positions,
        "total_exposure": round(total_exposure, 2),
        "last_execution_ts": last_exec_ts_str,
        "stale_seconds": round(stale_seconds, 0) if stale_seconds is not None else None,
    }


# ─── 风险检查 ────────────────────────────────────────────────────────────────

def check_risk(state):
    """
    返回 (triggered: bool, violations: list[str], warnings: list[str])
    """
    cfg = _load_system_config_thresholds()

    max_drawdown = _env_float("WATCHDOG_MAX_DRAWDOWN_PCT", cfg["drawdown_halt"])
    warn_drawdown = _env_float("WATCHDOG_WARN_DRAWDOWN_PCT", cfg["drawdown_warning"])
    max_daily_loss = _env_float("WATCHDOG_MAX_DAILY_LOSS_PCT", -10.0)
    max_positions = _env_int("WATCHDOG_MAX_OPEN_POSITIONS", 50)
    max_stale = _env_int("WATCHDOG_MAX_STALE_SECONDS", 86400)
    max_exposure = _env_float("WATCHDOG_MAX_TOTAL_EXPOSURE", 9000.0)

    violations = []
    warnings = []
    triggered = False

    dpct = state.get("drawdown_pct", 0)
    if dpct <= -max_drawdown:
        violations.append(
            f"CRITICAL drawdown {dpct:.1f}% ≤ -{max_drawdown}% halt threshold"
        )
        triggered = True
    elif dpct <= -warn_drawdown:
        warnings.append(f"WARNING drawdown {dpct:.1f}% ≤ -{warn_drawdown}% warning threshold")

    if state.get("open_positions", 0) > max_positions:
        violations.append(
            f"CRITICAL open_positions {state['open_positions']} > {max_positions}"
        )
        triggered = True

    stale = state.get("stale_seconds")
    if stale is not None and stale > max_stale:
        h = int(stale / 3600)
        violations.append(
            f"CRITICAL data stale {h}h > {max_stale//3600}h threshold"
        )
        triggered = True

    exp = state.get("total_exposure", 0)
    if exp > max_exposure:
        violations.append(
            f"CRITICAL total_exposure ${exp:.0f} > ${max_exposure:.0f}"
        )
        triggered = True

    return triggered, violations, warnings


# ─── Telegram 推送 ───────────────────────────────────────────────────────────

def _get_telegram_config():
    """读取 Telegram token 和 chat_id（不抛出异常）。"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not chat_id:
        # 从 hermes channel_directory 读取第一个 Telegram chat
        try:
            cd_path = Path.home() / ".hermes" / "channel_directory.json"
            cd = json.loads(cd_path.read_text())
            tg_channels = cd.get("platforms", {}).get("telegram", [])
            if tg_channels:
                chat_id = str(tg_channels[0].get("id", ""))
        except Exception:
            pass

    return token, chat_id


def send_telegram(message, test_mode=False):
    """
    发送 Telegram 消息。
    - token/chat_id 未配置：打印 skipped，不崩溃
    - 请求失败：打印错误，不崩溃
    返回 True=成功, False=跳过/失败
    """
    token, chat_id = _get_telegram_config()

    if not token:
        print("[Telegram] skipped — TELEGRAM_BOT_TOKEN not set")
        return False
    if not chat_id:
        print("[Telegram] skipped — TELEGRAM_CHAT_ID not found")
        return False

    prefix = "[TEST] " if test_mode else ""
    full_msg = prefix + message

    try:
        import urllib.request
        import urllib.parse
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": full_msg, "parse_mode": "Markdown"})
        req = urllib.request.Request(
            url,
            data=payload.encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print(f"[Telegram] ✅ 消息已发送 (chat_id={chat_id})")
                return True
            else:
                print(f"[Telegram] ❌ 发送失败: {result}")
                return False
    except Exception as e:
        print(f"[Telegram] ❌ 请求异常: {e}")
        return False


# ─── 写入告警状态 ─────────────────────────────────────────────────────────────

def write_emergency_state(state, violations, dry_run=False, no_write_stop=False):
    """写入 emergency_state.json 和 STOP_TRADING 文件。"""
    emergency = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "triggered": True,
        "violations": violations,
        "account_snapshot": {
            "total_value": state.get("total_value"),
            "pnl": state.get("pnl"),
            "drawdown_pct": state.get("drawdown_pct"),
            "open_positions": state.get("open_positions"),
            "total_exposure": state.get("total_exposure"),
        },
        "dry_run": dry_run,
        "stop_trading_written": False,
    }

    DATA_DIR.mkdir(exist_ok=True)

    if not dry_run:
        EMERGENCY_STATE_FILE.write_text(json.dumps(emergency, indent=2, ensure_ascii=False))
        print(f"📄 emergency_state.json 已写入: {EMERGENCY_STATE_FILE}")

        if not no_write_stop:
            STOP_TRADING_FILE.write_text(
                f"STOP_TRADING active\n"
                f"Written: {emergency['timestamp']}\n"
                f"Violations: {'; '.join(violations)}\n"
                f"Account: drawdown={state.get('drawdown_pct'):.1f}%  "
                f"positions={state.get('open_positions')}\n"
            )
            emergency["stop_trading_written"] = True
            print(f"🛑 STOP_TRADING 文件已写入: {STOP_TRADING_FILE}")
    else:
        print(f"[DRY-RUN] 将写入 emergency_state.json")
        if not no_write_stop:
            print(f"[DRY-RUN] 将写入 STOP_TRADING 文件")

    return emergency


# ─── 主逻辑 ──────────────────────────────────────────────────────────────────

def run_watchdog(dry_run=False, no_write_stop=False, verbose=False):
    """执行一次 watchdog 检查。返回 (triggered, state, violations, warnings)。"""
    print(f"[Watchdog] 开始账户检查 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")

    state = gather_account_state()
    print(f"  数据来源: {state['source']}")
    print(f"  总资产:   ${state['total_value']:.2f}")
    print(f"  盈亏:     ${state['pnl']:.2f}  ({state['drawdown_pct']:.1f}%)")
    print(f"  持仓数:   {state['open_positions']}")
    print(f"  总敞口:   ${state['total_exposure']:.2f}")
    if state["stale_seconds"] is not None:
        h = int(state["stale_seconds"] / 3600)
        m = int((state["stale_seconds"] % 3600) / 60)
        print(f"  数据陈旧: {h}h {m}m")
    else:
        print(f"  数据陈旧: 未知（无执行记录）")

    triggered, violations, warnings = check_risk(state)

    if warnings:
        for w in warnings:
            print(f"  ⚠️  {w}")

    if triggered:
        print()
        print("  🚨 风险阈值触发！")
        for v in violations:
            print(f"     {v}")
        write_emergency_state(state, violations, dry_run=dry_run, no_write_stop=no_write_stop)

        msg = (
            f"🚨 *Polymarket Watchdog 告警*\n"
            f"时间: `{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}`\n"
            f"总资产: `${state['total_value']:.2f}`\n"
            f"盈亏: `${state['pnl']:.2f}` (`{state['drawdown_pct']:.1f}%`)\n"
            f"持仓: `{state['open_positions']}` 个\n"
            f"\n风险:\n" +
            "\n".join(f"• {v}" for v in violations) +
            ("\n\n⛔ STOP\\_TRADING 已激活" if not no_write_stop and not dry_run else "")
        )
        send_telegram(msg)
    else:
        print(f"  ✅ 无风险触发（{len(warnings)} 个警告）")

    return triggered, state, violations, warnings


def run_test_telegram(dry_run=False):
    """仅发送测试消息，不改变交易状态，不写 STOP_TRADING。"""
    print("[Watchdog] test-telegram 模式 — 仅发送测试消息，不写入任何文件")

    state = gather_account_state()
    msg = (
        f"✅ *Polymarket Watchdog 测试消息*\n"
        f"时间: `{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}`\n"
        f"总资产: `${state['total_value']:.2f}`\n"
        f"盈亏: `${state['pnl']:.2f}` (`{state['drawdown_pct']:.1f}%`)\n"
        f"持仓: `{state['open_positions']}` 个\n"
        f"Watchdog 运行正常，Telegram 推送链路已验证。"
    )
    ok = send_telegram(msg, test_mode=True)
    print(f"[Watchdog] test-telegram {'成功' if ok else '失败（见上方信息）'}")
    return ok


# ─── CLI 入口 ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Polymarket 账户级亏损 Watchdog")
    parser.add_argument("--once", action="store_true", help="运行一次检查")
    parser.add_argument("--test-telegram", action="store_true",
                        help="仅发送测试 Telegram 消息，不改变交易状态")
    parser.add_argument("--dry-run", action="store_true",
                        help="不写入任何文件（STOP_TRADING/emergency_state）")
    parser.add_argument("--no-write-stop", action="store_true",
                        help="风险触发时不写 STOP_TRADING（仅写 emergency_state）")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()

    if args.test_telegram:
        # test-telegram 强制 dry-run，不写 STOP_TRADING
        run_test_telegram(dry_run=True)
        return

    if args.once or True:  # 默认执行一次
        triggered, state, violations, warnings = run_watchdog(
            dry_run=args.dry_run,
            no_write_stop=args.no_write_stop,
            verbose=args.verbose,
        )
        if triggered and not args.dry_run:
            sys.exit(2)  # 非零退出码供外部 cron 检测


if __name__ == "__main__":
    main()
