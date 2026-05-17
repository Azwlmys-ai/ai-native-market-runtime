"""
tests/test_account_watchdog.py
账户级 Watchdog 单元测试
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.account_watchdog import (
    check_risk,
    gather_account_state,
    run_test_telegram,
    run_watchdog,
    send_telegram,
    write_emergency_state,
    STOP_TRADING_FILE,
    EMERGENCY_STATE_FILE,
    DATA_DIR,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_stop_files(tmp_path):
    """每个测试前后确保 STOP_TRADING / emergency_state 不存在（不污染真实 data/）。"""
    for f in (STOP_TRADING_FILE, EMERGENCY_STATE_FILE):
        if f.exists():
            f.unlink()
    yield
    for f in (STOP_TRADING_FILE, EMERGENCY_STATE_FILE):
        if f.exists():
            f.unlink()


def _healthy_state():
    return {
        "timestamp": "2026-05-16T10:00:00+00:00",
        "source": "mock",
        "total_value": 9800.0,
        "cash": 2000.0,
        "positions_value": 7800.0,
        "starting_balance": 10000.0,
        "pnl": -200.0,
        "drawdown_pct": -2.0,
        "open_positions": 10,
        "total_exposure": 7000.0,
        "last_execution_ts": "2026-05-16T09:00:00",
        "stale_seconds": 3600,
    }


def _critical_state():
    return {
        **_healthy_state(),
        "pnl": -2100.0,
        "drawdown_pct": -21.0,
        "open_positions": 15,
        "stale_seconds": 90000,
    }


# ─── 测试 1：正常状态不触发 ──────────────────────────────────────────────────

def test_no_trigger_on_healthy_state():
    """正常账户状态不应触发 watchdog。"""
    triggered, violations, warnings = check_risk(_healthy_state())
    assert not triggered
    assert len(violations) == 0


# ─── 测试 2：drawdown 超阈值触发 ─────────────────────────────────────────────

def test_trigger_on_drawdown(monkeypatch):
    """drawdown 超过 halt 阈值时，应触发告警。"""
    monkeypatch.setenv("WATCHDOG_MAX_DRAWDOWN_PCT", "20")
    state = {**_healthy_state(), "drawdown_pct": -21.0}
    triggered, violations, warnings = check_risk(state)
    assert triggered
    assert any("drawdown" in v.lower() for v in violations)


def test_warning_on_drawdown_below_halt(monkeypatch):
    """drawdown 超过 warning 但未到 halt 时，只警告不触发。"""
    monkeypatch.setenv("WATCHDOG_MAX_DRAWDOWN_PCT", "20")
    monkeypatch.setenv("WATCHDOG_WARN_DRAWDOWN_PCT", "10")
    state = {**_healthy_state(), "drawdown_pct": -15.0}
    triggered, violations, warnings = check_risk(state)
    assert not triggered
    assert len(warnings) > 0


# ─── 测试 3：触发时写入 emergency_state.json ─────────────────────────────────

def test_emergency_state_written_on_trigger():
    """触发 watchdog 时（非 dry-run）应写入 emergency_state.json。"""
    state = _critical_state()
    violations = ["CRITICAL drawdown -21.0% ≤ -20% halt threshold"]

    write_emergency_state(state, violations, dry_run=False, no_write_stop=True)

    assert EMERGENCY_STATE_FILE.exists()
    data = json.loads(EMERGENCY_STATE_FILE.read_text())
    assert data["triggered"] is True
    assert len(data["violations"]) > 0
    assert data["account_snapshot"]["drawdown_pct"] == -21.0


def test_emergency_state_not_written_in_dry_run():
    """dry-run 模式不应写入 emergency_state.json。"""
    state = _critical_state()
    violations = ["CRITICAL drawdown -21.0% ≤ -20% halt threshold"]

    write_emergency_state(state, violations, dry_run=True)

    assert not EMERGENCY_STATE_FILE.exists()


# ─── 测试 4：STOP_TRADING 文件写入 ───────────────────────────────────────────

def test_stop_trading_file_written_on_trigger():
    """触发 watchdog 时应写入 STOP_TRADING 文件。"""
    state = _critical_state()
    violations = ["CRITICAL drawdown -21.0% ≤ -20% halt threshold"]

    write_emergency_state(state, violations, dry_run=False, no_write_stop=False)

    assert STOP_TRADING_FILE.exists()
    content = STOP_TRADING_FILE.read_text()
    assert "STOP_TRADING active" in content


def test_stop_trading_not_written_with_no_write_stop():
    """--no-write-stop 时不写 STOP_TRADING，但写 emergency_state。"""
    state = _critical_state()
    violations = ["CRITICAL drawdown -21.0% ≤ -20% halt threshold"]

    write_emergency_state(state, violations, dry_run=False, no_write_stop=True)

    assert not STOP_TRADING_FILE.exists()
    assert EMERGENCY_STATE_FILE.exists()


def test_stop_trading_not_written_in_dry_run():
    """dry-run 时不写 STOP_TRADING。"""
    state = _critical_state()
    write_emergency_state(state, ["CRITICAL drawdown"], dry_run=True)
    assert not STOP_TRADING_FILE.exists()


# ─── 测试 5：Telegram 未配置不崩溃 ──────────────────────────────────────────

def test_telegram_skipped_when_no_token(monkeypatch):
    """TELEGRAM_BOT_TOKEN 未配置时，send_telegram 安全跳过，不崩溃。"""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    # 同时 mock channel_directory.json 读取失败
    with patch("builtins.open", side_effect=FileNotFoundError):
        result = send_telegram("test message")

    assert result is False  # 返回 False 而非抛异常


def test_telegram_skipped_when_no_chat_id(monkeypatch):
    """token 存在但无 chat_id 时，安全跳过。"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with patch("pathlib.Path.read_text", side_effect=FileNotFoundError):
        result = send_telegram("test message")
    assert result is False


def test_telegram_request_failure_not_crash(monkeypatch):
    """Telegram 请求失败（网络错误）不崩溃。"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")

    with patch("urllib.request.urlopen", side_effect=Exception("network error")):
        result = send_telegram("test message")

    assert result is False


# ─── 测试 6：--test-telegram 不写 STOP_TRADING ───────────────────────────────

def test_test_telegram_does_not_write_stop_trading(monkeypatch):
    """--test-telegram 模式绝对不写 STOP_TRADING。"""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with patch("scripts.account_watchdog.gather_account_state", return_value=_healthy_state()):
        run_test_telegram(dry_run=True)

    assert not STOP_TRADING_FILE.exists()
    assert not EMERGENCY_STATE_FILE.exists()


def test_test_telegram_sends_with_test_prefix(monkeypatch):
    """--test-telegram 发送时消息包含 [TEST] 前缀。"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")

    sent_messages = []

    def mock_urlopen(req, timeout=None):
        sent_messages.append(json.loads(req.data.decode()))
        resp = MagicMock()
        resp.read.return_value = json.dumps({"ok": True}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch("urllib.request.urlopen", mock_urlopen), \
         patch("scripts.account_watchdog.gather_account_state", return_value=_healthy_state()):
        run_test_telegram(dry_run=True)

    assert len(sent_messages) == 1
    assert sent_messages[0]["text"].startswith("[TEST]")
    assert not STOP_TRADING_FILE.exists()


# ─── 测试 7：run_watchdog dry-run 模式全流程 ─────────────────────────────────

def test_run_watchdog_dry_run_no_files(monkeypatch):
    """run_watchdog --dry-run 触发时不应写入任何文件。"""
    monkeypatch.setenv("WATCHDOG_MAX_DRAWDOWN_PCT", "1")  # 极低阈值，强制触发
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with patch("scripts.account_watchdog.gather_account_state", return_value=_critical_state()):
        triggered, state, violations, warnings = run_watchdog(dry_run=True)

    assert triggered
    assert not STOP_TRADING_FILE.exists()
    assert not EMERGENCY_STATE_FILE.exists()


def test_run_watchdog_healthy_no_files(monkeypatch):
    """run_watchdog 正常状态不触发，不写文件。"""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with patch("scripts.account_watchdog.gather_account_state", return_value=_healthy_state()):
        triggered, state, violations, warnings = run_watchdog(dry_run=True)

    assert not triggered
    assert not STOP_TRADING_FILE.exists()


# ─── 测试 8：orchestrator STOP_TRADING 集成 ──────────────────────────────────

def test_orchestrator_respects_stop_trading(monkeypatch, tmp_path):
    """orchestrator._execute_signals 在 STOP_TRADING 存在且非 dry-run 时跳过。"""
    sys.path.insert(0, str(PROJECT_ROOT))
    from orchestrator import Orchestrator

    # 创建最小目录结构
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "data" / "STOP_TRADING").write_text("STOP_TRADING active\n")

    orc = Orchestrator(base_dir=str(tmp_path))

    monkeypatch.delenv("EXECUTOR_DRY_RUN", raising=False)

    logged = []
    orc.log = lambda msg: logged.append(msg)

    # _write_skipped_execution_results 需要 data dir
    def noop_skip(reason):
        logged.append(f"skipped: {reason}")
    orc._write_skipped_execution_results = noop_skip

    orc._execute_signals()

    assert any("STOP_TRADING" in m for m in logged)
    assert not any("执行成功" in m for m in logged)


def test_orchestrator_dry_run_continues_with_stop_trading(monkeypatch, tmp_path):
    """dry-run 模式下即使 STOP_TRADING 存在，也应继续（打印警告）。"""
    from orchestrator import Orchestrator

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "data" / "STOP_TRADING").write_text("STOP_TRADING active\n")

    # 创建一个假 signal_executor.py
    fake_exec = tmp_path / "signal_executor.py"
    fake_exec.write_text(
        "import json; print(json.dumps({'status':'dry_run'}))"
    )

    orc = Orchestrator(base_dir=str(tmp_path))
    monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")

    logged = []
    orc.log = lambda msg: logged.append(msg)

    orc._execute_signals()

    # dry-run 时应有警告但仍继续
    assert any("DRY_RUN" in m or "dry" in m.lower() for m in logged)


# ─── 测试 9：时区修复（stale_seconds 不再为负）────────────────────────────────

def test_stale_seconds_uses_local_time_not_utc(tmp_path, monkeypatch):
    """
    execution_results.json 里的 timestamp 是本地时间（无 tzinfo）。
    修复前 gather_account_state 把它当 UTC，导致 UTC+8 地区 stale_seconds ≈ -28800s。
    修复后应用 .astimezone(utc) 正确转换，stale_seconds 应 ≥ 0。
    """
    import json
    from datetime import datetime, timezone, timedelta
    from pathlib import Path
    from scripts.account_watchdog import gather_account_state, DATA_DIR

    # 写一个"刚刚"完成的 execution_results，使用本地时间格式
    local_now = datetime.now()  # naive, local
    er = {
        "timestamp": local_now.isoformat(),
        "total": 1, "success": 0, "dry_run": 1, "failed": 0, "results": [],
    }
    # 指向真实 DATA_DIR（只写临时覆盖）
    er_path = DATA_DIR / "execution_results.json"
    original = None
    if er_path.exists():
        original = er_path.read_text()
    er_path.write_text(json.dumps(er))

    try:
        state = gather_account_state()
        stale = state.get("stale_seconds")
        # 应为非负值，且很小（刚写入）
        assert stale is not None, "stale_seconds 不应为 None"
        assert stale >= -60, f"stale_seconds={stale} 为负，时区处理仍有问题"
        assert stale < 3600, f"stale_seconds={stale} 过大，可能读错时间"
    finally:
        # 恢复原始文件
        if original is not None:
            er_path.write_text(original)
