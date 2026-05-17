"""Smoke tests for the repaired execution path.

These tests never place orders. They use explicit temporary base dirs and
mock subprocess calls so the executor cannot reach the real pm-trader binary.
"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


SAMPLE_SIGNAL = {
    "market_id": "test-market",
    "market_name": "Test Market",
    "direction": "NO",
    "position_size": 0.01,
    "price": 0.5,
}


def test_load_config():
    from llm_helper import get_fallback_map, load_llm_config

    cfg = load_llm_config()
    assert "agent_models" in cfg
    assert cfg["agent_models"]["agent_codex"] == "deepseek-v4-flash"
    fallback = get_fallback_map(cfg)
    assert fallback["grok-4.3"] == "claude-opus-4-7"
    assert "[REDACTED]" not in fallback


def test_fallback_map_uses_valid_config_values():
    from llm_helper import get_fallback_map

    cfg = {
        "fallback_map": {
            "grok-4.3": "gpt-5.4",
            "[REDACTED]": "deepseek-r1",
            "deepseek-r1": "",
            "TODO_MODEL": "gpt-5.4",
        }
    }
    fallback = get_fallback_map(cfg)
    assert fallback["grok-4.3"] == "gpt-5.4"
    assert fallback["deepseek-r1"] == "claude-opus-4-7"
    assert "[REDACTED]" not in fallback
    assert "TODO_MODEL" not in fallback


def test_pm_trader_env_adds_hermes_paths_when_available(tmp_path, monkeypatch):
    from _paths import get_pm_trader_env

    fake_home = tmp_path / "home"
    site_packages = fake_home / ".hermes/home/.local/lib/python3.13/site-packages"
    data_dir = fake_home / ".hermes/home/.pm-trader"
    site_packages.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("PM_TRADER_DATA_DIR", raising=False)
    monkeypatch.delenv("PYTHONPATH", raising=False)

    env = get_pm_trader_env()

    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(site_packages)
    assert env["PM_TRADER_DATA_DIR"] == str(data_dir)


def test_agent_p_uses_pm_trader_env(tmp_path):
    from agents.agent_p import AgentP

    agent = AgentP(base_dir=str(tmp_path))
    fake_positions = [{"market_slug": "test-market", "outcome": "no", "shares": 1}]
    fake = MagicMock(returncode=0, stdout=json.dumps({"ok": True, "data": fake_positions}), stderr="")

    with patch("agents.agent_p.get_pm_trader_env", return_value={"PYTHONPATH": "x"}) as mock_env:
        with patch("subprocess.run", return_value=fake) as mock_run:
            positions = agent.get_portfolio()

    assert positions == fake_positions
    assert json.loads((tmp_path / "data" / "positions.json").read_text()) == fake_positions
    mock_env.assert_called_once()
    assert mock_run.call_args.kwargs["env"] == {"PYTHONPATH": "x"}


def test_agent_g_uses_pm_trader_env(tmp_path):
    from agents.agent_g import AgentG

    agent = AgentG(base_dir=str(tmp_path))
    fake = MagicMock(returncode=0, stdout=json.dumps({"ok": True, "data": []}), stderr="")

    with patch("agents.agent_g.get_pm_trader_env", return_value={"PYTHONPATH": "x"}) as mock_env:
        with patch("subprocess.run", return_value=fake) as mock_run:
            trades = agent.load_trade_history()

    assert trades == []
    mock_env.assert_called_once()
    assert mock_run.call_args.kwargs["env"] == {"PYTHONPATH": "x"}


def test_agent_b_log_writes_file(tmp_path, monkeypatch):
    import agents.agent_b as agent_b

    monkeypatch.setattr(agent_b, "LOGS_DIR", tmp_path / "logs")

    agent_b.log("hello")

    today = datetime.now().strftime("%Y%m%d")
    log_file = tmp_path / "logs" / f"agent_b_{today}.log"
    assert log_file.exists()
    assert "hello" in log_file.read_text()


def test_load_approved_signals():
    p = PROJECT_ROOT / "data" / "approved_signals.json"
    assert p.exists(), f"approved_signals.json missing at {p}"
    sigs = json.loads(p.read_text())
    assert isinstance(sigs, list)
    if sigs:
        assert "market_id" in sigs[0], "schema changed; smoke test needs update"


@pytest.fixture
def flat_executor(tmp_path):
    from executors.signal_executor import SignalExecutor

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    return SignalExecutor(base_dir=str(tmp_path))


@pytest.fixture
def root_executor(tmp_path):
    from signal_executor import SignalExecutor

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "system_config.json").write_text(
        json.dumps({"pm_trader": {"path": "/tmp/mock_pm_trader.sh"}})
    )
    return SignalExecutor(base_dir=str(tmp_path))


def test_flat_executor_with_mock_success(flat_executor):
    fake = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch("subprocess.run", return_value=fake):
        r = flat_executor.execute_trade(SAMPLE_SIGNAL)
    assert r["status"] == "success"


def test_flat_executor_with_mock_timeout(flat_executor):
    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired("pm-trader", 30),
    ):
        r = flat_executor.execute_trade(SAMPLE_SIGNAL)
    assert r["status"] == "timeout"
    assert r["signal"] == SAMPLE_SIGNAL


def test_flat_executor_with_mock_exception(flat_executor):
    with patch("subprocess.run", side_effect=RuntimeError("boom")):
        r = flat_executor.execute_trade(SAMPLE_SIGNAL)
    assert r["status"] == "error"
    assert r["signal"] == SAMPLE_SIGNAL


def test_flat_executor_dry_run_env(flat_executor, monkeypatch):
    monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")
    with patch("subprocess.run") as mock_run:
        r = flat_executor.execute_trade(SAMPLE_SIGNAL)
    assert r["status"] == "dry_run"
    mock_run.assert_not_called()


def test_flat_executor_empty_signals_overwrites_execution_results(flat_executor):
    """No approved signals must write a fresh zero-result file, not leave stale dry-run data."""
    approved_file = flat_executor.data_dir / "approved_signals.json"
    approved_file.write_text("[]")
    stale_file = flat_executor.data_dir / "execution_results.json"
    stale_file.write_text(json.dumps({
        "timestamp": "stale",
        "total": 2,
        "success": 0,
        "dry_run": 2,
        "simulated": 0,
        "failed": 0,
        "results": [{"status": "dry_run"}, {"status": "dry_run"}],
    }))

    flat_executor.run()

    output = json.loads(stale_file.read_text())
    assert output["timestamp"] != "stale"
    assert output["total"] == 0
    assert output["success"] == 0
    assert output["dry_run"] == 0
    assert output["simulated"] == 0
    assert output["failed"] == 0
    assert output["results"] == []


def test_root_executor_with_mock_timeout(root_executor):
    nested_signal = {"signal": SAMPLE_SIGNAL}
    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired("pm-trader", 60),
    ):
        r = root_executor.execute_signal(nested_signal)
    assert r["status"] == "timeout"
    assert r["signal"] == SAMPLE_SIGNAL


def test_root_executor_with_mock_exception(root_executor):
    nested_signal = {"signal": SAMPLE_SIGNAL}
    with patch("subprocess.run", side_effect=RuntimeError("boom")):
        r = root_executor.execute_signal(nested_signal)
    assert r["status"] == "error"
    assert r["signal"] == SAMPLE_SIGNAL


def test_root_executor_dry_run_env(root_executor, monkeypatch):
    monkeypatch.setenv("EXECUTOR_DRY_RUN", "true")
    with patch("subprocess.run") as mock_run:
        r = root_executor.execute_signal({"signal": SAMPLE_SIGNAL})
    assert r["status"] == "dry_run"
    mock_run.assert_not_called()


def test_root_wrappers_reexport_canonical_classes():
    from signal_executor import SignalExecutor as RootSignalExecutor
    from sell_executor import SellExecutor as RootSellExecutor
    from executors.signal_executor import SignalExecutor as CanonicalSignalExecutor
    from executors.sell_executor import SellExecutor as CanonicalSellExecutor

    assert RootSignalExecutor is CanonicalSignalExecutor
    assert RootSellExecutor is CanonicalSellExecutor


def test_runtime_agents_respect_pa_base_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))

    from agents.regime_detector import RegimeDetector
    from agents.agent_a import AgentA
    from agents.strategy_manager import StrategyManager
    from agents.capital_adapter import CapitalAdapter
    from agents.agent_d import AgentD
    from agents.agent_e import AgentE
    from agents.agent_f import AgentF
    from agents.agent_h import AgentH
    from agents.agent_j import AgentJ
    from agents.agent_i import AgentI
    from agents.agent_k_v2 import AgentKv2
    from agents.agent_okx_funding import AgentOKXFunding

    classes = [
        AgentA,
        RegimeDetector,
        StrategyManager,
        CapitalAdapter,
        AgentD,
        AgentE,
        AgentF,
        AgentH,
        AgentJ,
        AgentI,
        AgentKv2,
        AgentOKXFunding,
    ]

    for cls in classes:
        instance = cls()
        assert instance.base_dir == tmp_path
        assert instance.data_dir == tmp_path / "data"
        assert instance.logs_dir == tmp_path / "logs"


def test_orchestrator_bootstraps_positions_file(tmp_path):
    from orchestrator import Orchestrator

    orchestrator = Orchestrator(base_dir=str(tmp_path))

    positions_file = orchestrator.data_dir / "positions.json"
    assert positions_file.exists()
    assert json.loads(positions_file.read_text()) == []


def test_orchestrator_rejects_stale_signals_and_writes_fresh_skip_outputs(tmp_path, monkeypatch):
    from orchestrator import Orchestrator

    monkeypatch.setenv("SIGNAL_MAX_AGE_SECONDS", "7200")
    orchestrator = Orchestrator(base_dir=str(tmp_path))
    signals_file = orchestrator.data_dir / "signals.json"
    stale_signal = dict(SAMPLE_SIGNAL)
    stale_signal["generated_at"] = datetime.fromtimestamp(
        time.time() - 3 * 60 * 60
    ).isoformat()
    signals_file.write_text(json.dumps([stale_signal]))
    stale_time = time.time() - 3 * 60 * 60
    os.utime(signals_file, (stale_time, stale_time))

    ready, reason = orchestrator._signals_ready_for_review()
    assert ready is False
    assert "signals stale" in reason

    orchestrator._write_skipped_review(reason)
    orchestrator._write_skipped_execution_results(reason)

    review = json.loads((orchestrator.data_dir / "review_results.json").read_text())
    approved = json.loads((orchestrator.data_dir / "approved_signals.json").read_text())
    execution = json.loads((orchestrator.data_dir / "execution_results.json").read_text())

    assert review["status"] == "skipped"
    assert review["approved_signals"] == []
    assert approved == []
    assert execution["status"] == "skipped"
    assert execution["total"] == 0
    assert execution["success"] == 0
    assert execution["dry_run"] == 0
    assert execution["results"] == []


def test_orchestrator_rejects_legacy_signals_without_generated_at(tmp_path):
    from orchestrator import Orchestrator

    orchestrator = Orchestrator(base_dir=str(tmp_path))
    signals_file = orchestrator.data_dir / "signals.json"
    signals_file.write_text(json.dumps([SAMPLE_SIGNAL]))

    ready, reason = orchestrator._signals_ready_for_review()

    assert ready is False
    assert "signals missing generated_at" in reason


def test_orchestrator_accepts_fresh_generated_at_signal(tmp_path):
    from orchestrator import Orchestrator

    orchestrator = Orchestrator(base_dir=str(tmp_path))
    signals_file = orchestrator.data_dir / "signals.json"
    signal = dict(SAMPLE_SIGNAL)
    signal["generated_at"] = datetime.now().isoformat()
    signals_file.write_text(json.dumps([signal]))

    ready, reason = orchestrator._signals_ready_for_review()
    assert ready is True
    assert reason == "signals fresh"


def test_ensure_signal_timestamps_adds_generated_at():
    from utils.signals import ensure_signal_timestamps

    original = dict(SAMPLE_SIGNAL)
    stamped = ensure_signal_timestamps([original], generated_at="2026-05-11T17:10:00")

    assert stamped[0]["generated_at"] == "2026-05-11T17:10:00"
    assert stamped[0]["timestamp"] == "2026-05-11T17:10:00"
    assert "generated_at" not in original


def test_agent_i_checks_agent_k_v2_log_name(tmp_path):
    from agents.agent_i import AgentI

    agent = AgentI(base_dir=str(tmp_path))
    today = datetime.now().strftime("%Y%m%d")
    log_file = agent.logs_dir / f"agent_k_v2_{today}.log"
    log_file.write_text(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [Agent K v2] ok\n")

    health = agent.check_agent_health()

    assert "k_v2" in health
    assert "k" not in health
    assert health["k_v2"]["status"] == "healthy"


def test_sell_executor_supports_legacy_signal(tmp_path):
    from executors.sell_executor import SellExecutor

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "system_config.json").write_text(
        json.dumps({"pm_trader": {"path": "/tmp/mock_pm_trader.sh"}})
    )
    executor = SellExecutor(base_dir=str(tmp_path))
    fake = MagicMock(returncode=0, stdout="ok", stderr="")

    with patch("subprocess.run", return_value=fake):
        r = executor.execute_sell(
            {"market": "test-market", "outcome": "NO", "shares": 3.5, "reason": "test"}
        )

    assert r["status"] == "success"


def test_sell_executor_dry_run_env(tmp_path, monkeypatch):
    from executors.sell_executor import SellExecutor

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "config").mkdir()
    executor = SellExecutor(base_dir=str(tmp_path))
    monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")

    with patch("subprocess.run") as mock_run:
        r = executor.execute_sell(
            {"market_id": "test-market", "token_id": "YES", "amount": 2.0}
        )

    assert r["status"] == "dry_run"
    mock_run.assert_not_called()


def test_sell_executor_writes_zero_results_when_no_signals(tmp_path):
    from executors.sell_executor import SellExecutor

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "sell_signals.json").write_text("[]")
    executor = SellExecutor(base_dir=str(tmp_path))

    executor.run()

    output = json.loads((tmp_path / "data" / "sell_execution_results.json").read_text())
    assert output["total"] == 0
    assert output["success"] == 0
    assert output["dry_run"] == 0
    assert output["failed"] == 0
    assert output["results"] == []


def test_sell_executor_run_writes_dry_run_results(tmp_path, monkeypatch):
    from executors.sell_executor import SellExecutor

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "sell_signals.json").write_text(json.dumps([
        {"market": "test-market", "outcome": "NO", "shares": 3.5, "reason": "test"}
    ]))
    executor = SellExecutor(base_dir=str(tmp_path))
    monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")

    executor.run()

    output = json.loads((tmp_path / "data" / "sell_execution_results.json").read_text())
    assert output["total"] == 1
    assert output["success"] == 0
    assert output["dry_run"] == 1
    assert output["failed"] == 0
    assert output["results"][0]["status"] == "dry_run"
    assert len(json.loads((tmp_path / "data" / "sell_signals.json").read_text())) == 1


def test_dump_pm_history_rejects_non_json():
    from scripts.dump_pm_history import fetch_history

    fake = MagicMock(returncode=0, stdout="Usage: pm-trader history [OPTIONS]", stderr="")
    with patch("subprocess.run", return_value=fake):
        with pytest.raises(ValueError):
            fetch_history("/tmp/mock_pm_trader.sh", 100)


def test_agent_codex_writes_gate_and_hermes_message(tmp_path):
    from agents.agent_codex import AgentCodex

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    (shared / "messages.json").write_text(json.dumps({"messages": []}))
    sample_file = tmp_path / "agent_sample.py"
    sample_file.write_text("print('ok')\n")
    request_file = tmp_path / "data" / "codex_review_request.json"
    request_file.write_text(
        json.dumps(
            {
                "requirements": "必须只是打印 ok",
                "summary": "新增 sample 文件",
                "files": ["agent_sample.py"],
                "notify_to": "hermes",
            }
        )
    )
    response = json.dumps(
        {
            "decision": "APPROVE",
            "summary": "可以发布",
            "findings": [],
            "required_tests": ["python3 -m py_compile agent_sample.py"],
            "deployment_notes": ["无"],
            "message_to_hermes": "Agent Codex 审核通过，可以进入发布前人工确认。",
        },
        ensure_ascii=False,
    )

    with patch("agents.agent_codex.call_llm_sync", return_value=response):
        payload = AgentCodex(base_dir=str(tmp_path), request_file=str(request_file)).run()

    assert payload["decision"] == "APPROVE"
    gate = json.loads((tmp_path / "data" / "deployment_gate.json").read_text())
    assert gate["status"] == "open"
    messages = json.loads((shared / "messages.json").read_text())["messages"]
    assert messages[-1]["from"] == "agent_codex"
    assert messages[-1]["to"] == "hermes"
    assert messages[-1]["type"] == "code_review"
    assert messages[-1]["metadata"]["tests_declared"] == []


def test_agent_codex_fail_closed_on_llm_error(tmp_path):
    from agents.agent_codex import AgentCodex

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    (shared / "messages.json").write_text(json.dumps({"messages": []}))
    sample_file = tmp_path / "agent_sample.py"
    sample_file.write_text("print('ok')\n")
    request_file = tmp_path / "data" / "codex_review_request.json"
    request_file.write_text(
        json.dumps(
            {
                "requirements": "必须只是打印 ok",
                "summary": "新增 sample 文件",
                "files": ["agent_sample.py"],
                "tests": ["python3 -m py_compile agent_sample.py"],
            }
        )
    )

    with patch("agents.agent_codex.call_llm_sync", side_effect=RuntimeError("model down")):
        payload = AgentCodex(base_dir=str(tmp_path), request_file=str(request_file)).run()

    assert payload["decision"] == "BLOCKED"
    gate = json.loads((tmp_path / "data" / "deployment_gate.json").read_text())
    assert gate["status"] == "blocked"
    assert gate["decision"] == "BLOCKED"
    messages = json.loads((shared / "messages.json").read_text())["messages"]
    assert messages[-1]["priority"] == "urgent"
    assert "审核失败" in messages[-1]["content"]


def test_agent_codex_includes_declared_tests_in_prompt_and_payload(tmp_path):
    from agents.agent_codex import AgentCodex

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    (shared / "messages.json").write_text(json.dumps({"messages": []}))
    sample_file = tmp_path / "agent_sample.py"
    sample_file.write_text("print('ok')\n")
    request_file = tmp_path / "data" / "codex_review_request.json"
    declared_tests = ["python3 -m py_compile agent_sample.py"]
    request_file.write_text(
        json.dumps(
            {
                "requirements": "必须只是打印 ok",
                "summary": "新增 sample 文件",
                "files": ["agent_sample.py"],
                "tests": declared_tests,
            }
        )
    )
    response = json.dumps(
        {
            "decision": "APPROVE",
            "summary": "可以发布",
            "findings": [],
            "required_tests": declared_tests,
            "deployment_notes": [],
            "message_to_hermes": "Agent Codex 审核通过。",
        },
        ensure_ascii=False,
    )

    captured = {}

    def fake_llm(agent_id, prompt, timeout=60, temperature=None):
        captured["agent_id"] = agent_id
        captured["prompt"] = prompt
        return response

    with patch("agents.agent_codex.call_llm_sync", side_effect=fake_llm):
        payload = AgentCodex(base_dir=str(tmp_path), request_file=str(request_file)).run()

    assert captured["agent_id"] == "agent_codex"
    assert "开发者声明的测试要求" in captured["prompt"]
    assert declared_tests[0] in captured["prompt"]
    assert payload["tests_declared"] == declared_tests
    gate = json.loads((tmp_path / "data" / "deployment_gate.json").read_text())
    assert gate["tests_declared"] == declared_tests
    assert gate["required_tests"] == declared_tests
    # message metadata must also carry tests_declared / required_tests so
    # Hermes UI can display them without re-reading the gate file.
    messages = json.loads((shared / "messages.json").read_text())["messages"]
    assert messages[-1]["metadata"]["tests_declared"] == declared_tests
    assert messages[-1]["metadata"]["required_tests"] == declared_tests


def test_agent_codex_blocks_empty_request_without_llm(tmp_path):
    from agents.agent_codex import AgentCodex

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    (shared / "messages.json").write_text(json.dumps({"messages": []}))
    request_file = tmp_path / "data" / "codex_review_request.json"
    request_file.write_text(json.dumps({"requirements": "审核本次改动", "files": []}))

    with patch("agents.agent_codex.call_llm_sync") as mock_llm:
        payload = AgentCodex(base_dir=str(tmp_path), request_file=str(request_file)).run()

    assert payload["decision"] == "BLOCKED"
    mock_llm.assert_not_called()
    gate = json.loads((tmp_path / "data" / "deployment_gate.json").read_text())
    assert gate["status"] == "blocked"
    assert gate["summary"] == "空审核请求"


def test_agent_codex_blocks_when_git_diff_unavailable_and_no_files(tmp_path):
    """files=[] + git subprocess 异常 → BLOCKED 且不调 LLM.

    Closes a fail-closed contract gap that the gate self-review caught:
    collect_git_diff used to return "[git diff unavailable: ...]" as a
    non-empty string, which let the empty-request guard fall through and
    actually call the LLM with no real review material.
    """
    from agents.agent_codex import AgentCodex

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    (shared / "messages.json").write_text(json.dumps({"messages": []}))
    request_file = tmp_path / "data" / "codex_review_request.json"
    request_file.write_text(json.dumps({"requirements": "审核", "files": []}))

    agent = AgentCodex(base_dir=str(tmp_path), request_file=str(request_file))

    with patch.object(
        agent, "collect_git_diff",
        return_value=("unavailable", "[git diff unavailable: boom]"),
    ):
        with patch("agents.agent_codex.call_llm_sync") as mock_llm:
            payload = agent.run()

    mock_llm.assert_not_called()
    assert payload["decision"] == "BLOCKED"
    gate = json.loads((tmp_path / "data" / "deployment_gate.json").read_text())
    assert gate["status"] == "blocked"
    assert gate["summary"] == "空审核请求"


def test_agent_codex_blocks_when_git_diff_failed_and_no_files(tmp_path):
    """files=[] + git returncode!=0 → BLOCKED 且不调 LLM."""
    from agents.agent_codex import AgentCodex

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    (shared / "messages.json").write_text(json.dumps({"messages": []}))
    request_file = tmp_path / "data" / "codex_review_request.json"
    request_file.write_text(json.dumps({"requirements": "审核", "files": []}))

    agent = AgentCodex(base_dir=str(tmp_path), request_file=str(request_file))

    with patch.object(
        agent, "collect_git_diff",
        return_value=("failed", "[git diff failed: bad rev]"),
    ):
        with patch("agents.agent_codex.call_llm_sync") as mock_llm:
            payload = agent.run()

    mock_llm.assert_not_called()
    assert payload["decision"] == "BLOCKED"
    gate = json.loads((tmp_path / "data" / "deployment_gate.json").read_text())
    assert gate["status"] == "blocked"
    assert gate["summary"] == "空审核请求"


def test_agent_codex_file_context_has_line_numbers_and_truncation_marker(tmp_path):
    from agents.agent_codex import AgentCodex, MAX_FILE_CHARS

    sample_file = tmp_path / "agent_sample.py"
    sample_file.write_text("alpha\nbeta\n")
    big_file = tmp_path / "big.py"
    big_file.write_text("x" * (MAX_FILE_CHARS + 100))
    agent = AgentCodex(base_dir=str(tmp_path))

    context = agent.collect_file_context(["agent_sample.py", "big.py"])

    # line numbers
    assert "    1 | alpha" in context
    assert "    2 | beta" in context
    # truncation marker is emitted when a file exceeds MAX_FILE_CHARS so the
    # prompt can fail-closed (the prompt rule forbids APPROVE on [truncated]).
    assert "[truncated]" in context


def test_agent_codex_rejects_invalid_request_schema(tmp_path):
    from agents.agent_codex import AgentCodex

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    (shared / "messages.json").write_text(json.dumps({"messages": []}))
    request_file = tmp_path / "data" / "codex_review_request.json"
    request_file.write_text(json.dumps({"requirements": "审核", "files": "agent_sample.py"}))

    payload = AgentCodex(base_dir=str(tmp_path), request_file=str(request_file)).run()

    assert payload["decision"] == "BLOCKED"
    gate = json.loads((tmp_path / "data" / "deployment_gate.json").read_text())
    assert gate["status"] == "blocked"
    assert "审核失败" in gate["summary"]


def test_agent_codex_notify_hermes_concurrent_writes(tmp_path):
    from agents.agent_codex import AgentCodex

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    (shared / "messages.json").write_text(json.dumps({"messages": []}))
    agent = AgentCodex(base_dir=str(tmp_path))
    request = {
        "requirements": "",
        "summary": "",
        "files": [],
        "tests": [],
        "release_target": "hermes",
        "notify_to": "hermes",
    }
    payload = {
        "review": {
            "decision": "APPROVE",
            "message_to_hermes": "ok",
            "required_tests": [],
        }
    }

    threads = [
        threading.Thread(target=agent.notify_hermes, args=(request, payload))
        for _ in range(12)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    messages = json.loads((shared / "messages.json").read_text())["messages"]
    assert len(messages) == 12


def test_agent_codex_parse_review_blocks_non_json_output(tmp_path):
    from agents.agent_codex import AgentCodex

    agent = AgentCodex(base_dir=str(tmp_path))
    review = agent.parse_review("This is not JSON at all.")

    assert review["decision"] == "BLOCKED"
    assert review["findings"]
    assert review["findings"][0]["title"] == "非 JSON 审核输出"


def test_agent_codex_parse_review_blocks_invalid_decision(tmp_path):
    from agents.agent_codex import AgentCodex

    agent = AgentCodex(base_dir=str(tmp_path))
    response = json.dumps({"decision": "MAYBE", "summary": "uncertain"})

    review = agent.parse_review(response)

    # Non-standard decision must fail-closed to BLOCKED, not silently
    # downgrade to CHANGES_REQUESTED — otherwise a malformed model response
    # could become a polite "please fix" instead of a deployment block.
    assert review["decision"] == "BLOCKED"


def test_agent_codex_notify_failure_keeps_gate_blocked_and_raises(tmp_path):
    from agents.agent_codex import AgentCodex

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    # Corrupt messages.json so notify_hermes raises JSONDecodeError after
    # save_result has already written gate=open.
    (shared / "messages.json").write_text("not json")
    sample_file = tmp_path / "agent_sample.py"
    sample_file.write_text("print('ok')\n")
    request_file = tmp_path / "data" / "codex_review_request.json"
    request_file.write_text(
        json.dumps(
            {
                "requirements": "必须只是打印 ok",
                "summary": "新增 sample 文件",
                "files": ["agent_sample.py"],
            }
        )
    )
    response = json.dumps(
        {
            "decision": "APPROVE",
            "summary": "可以发布",
            "findings": [],
            "required_tests": [],
            "deployment_notes": [],
            "message_to_hermes": "ok",
        },
        ensure_ascii=False,
    )

    with patch("agents.agent_codex.call_llm_sync", return_value=response):
        with pytest.raises(json.JSONDecodeError):
            AgentCodex(base_dir=str(tmp_path), request_file=str(request_file)).run()

    # Even though the LLM returned APPROVE, notify failure must force the
    # deployment gate back to BLOCKED so deployment is fail-closed.
    gate = json.loads((tmp_path / "data" / "deployment_gate.json").read_text())
    assert gate["status"] == "blocked"
    assert gate["decision"] == "BLOCKED"
    assert "Hermes 通知失败" in gate["summary"] or "通知" in gate["summary"]


def test_agent_codex_main_exits_nonzero_on_blocked(tmp_path, monkeypatch):
    """Non-APPROVE result must surface as a non-zero process exit so launchd /
    CI / wrapper scripts don't have to parse JSON to decide whether to deploy.
    """
    from agents import agent_codex as agent_codex_module

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    (shared / "messages.json").write_text(json.dumps({"messages": []}))
    request_file = tmp_path / "data" / "codex_review_request.json"
    # empty files + no .git → BLOCKED without even calling LLM
    request_file.write_text(json.dumps({"requirements": "审核", "files": []}))

    monkeypatch.setattr(
        sys,
        "argv",
        ["agent_codex.py", "--request", str(request_file)],
    )

    # AgentCodex inside main() uses default base_dir (project root); override
    # it via PA_BASE_DIR so the gate / results land in tmp_path.
    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exc_info:
        agent_codex_module.main()
    assert exc_info.value.code == 1


def test_agent_codex_does_not_overwrite_corrupt_messages(tmp_path):
    from agents.agent_codex import AgentCodex

    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    shared = tmp_path.parent / "shared"
    shared.mkdir(exist_ok=True)
    messages_file = shared / "messages.json"
    messages_file.write_text("not json")
    agent = AgentCodex(base_dir=str(tmp_path))
    request = {
        "requirements": "",
        "summary": "",
        "files": [],
        "tests": [],
        "release_target": "hermes",
        "notify_to": "hermes",
    }
    payload = {
        "review": {
            "decision": "BLOCKED",
            "message_to_hermes": "blocked",
            "required_tests": [],
        }
    }

    with pytest.raises(json.JSONDecodeError):
        agent.notify_hermes(request, payload)

    assert messages_file.read_text() == "not json"


# ---------------------------------------------------------------------------
# P2 #8: us_stocks_updater timeout guard and degraded-mode fallback
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine synchronously (no pytest-asyncio dependency)."""
    import asyncio
    return asyncio.run(coro)


_FINNHUB_OK = {
    "status": "success",
    "stocks": {"AAPL": 150.0},
    "total_symbols": 1,
    "timestamp": "2026-05-09T00:00:00",
}
_POLYGON_OK = {
    "status": "success",
    "stocks": {"MSFT": 300.0},
    "total_symbols": 1,
    "timestamp": "2026-05-09T00:00:00",
}


def test_us_stocks_partial_success_writes_data(tmp_path, monkeypatch):
    """One source succeeds, other raises TimeoutError: write successful data,
    no degraded marker."""
    import asyncio
    from collectors import us_stocks_updater

    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    async def mock_finnhub():
        return dict(_FINNHUB_OK)

    async def mock_polygon():
        raise asyncio.TimeoutError("polygon stalled")

    with patch("collectors.us_stocks_updater.collect_finnhub_data", new=mock_finnhub), \
         patch("collectors.us_stocks_updater.collect_polygon_data", new=mock_polygon):
        _run(us_stocks_updater.update_latest_data())

    data = json.loads((tmp_path / "data" / "latest_data.json").read_text())
    us = data["us_stocks"]
    assert us["source"] == "finnhub"
    assert us["stocks"] == {"AAPL": 150.0}
    assert "degraded" not in us
    assert "polygon_backup" not in us


def test_us_stocks_all_fail_preserves_existing(tmp_path, monkeypatch):
    """All sources fail with existing latest_data.json: preserve existing
    us_stocks fields and mark degraded/stale; exit normally."""
    from collectors import us_stocks_updater

    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    existing = {
        "us_stocks": {
            "source": "finnhub",
            "stocks": {"AAPL": 145.0},
            "total_symbols": 1,
            "timestamp": "2026-05-08T00:00:00",
        }
    }
    (tmp_path / "data" / "latest_data.json").write_text(
        json.dumps(existing), encoding="utf-8"
    )

    async def mock_fail():
        raise RuntimeError("network error")

    with patch("collectors.us_stocks_updater.collect_finnhub_data", new=mock_fail), \
         patch("collectors.us_stocks_updater.collect_polygon_data", new=mock_fail):
        _run(us_stocks_updater.update_latest_data())  # must not raise

    data = json.loads((tmp_path / "data" / "latest_data.json").read_text())
    us = data["us_stocks"]
    # Existing stocks preserved
    assert us["stocks"] == {"AAPL": 145.0}
    assert us["source"] == "finnhub"
    # Degraded markers added
    assert us["degraded"] is True
    assert us["status"] == "stale"
    assert "last_error" in us
    assert "last_attempt_timestamp" in us


def test_us_stocks_all_fail_no_existing_file(tmp_path, monkeypatch):
    """All sources fail with no existing file: exit without exception;
    create a degraded marker file (no crash, no hang)."""
    from collectors import us_stocks_updater

    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    async def mock_fail():
        raise RuntimeError("no network")

    with patch("collectors.us_stocks_updater.collect_finnhub_data", new=mock_fail), \
         patch("collectors.us_stocks_updater.collect_polygon_data", new=mock_fail):
        _run(us_stocks_updater.update_latest_data())  # must not raise

    # File should exist with degraded marker (empty base + degraded fields)
    out_path = tmp_path / "data" / "latest_data.json"
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    us = data["us_stocks"]
    assert us["degraded"] is True
    assert us["status"] == "stale"


# ---------------------------------------------------------------------------
# P2 #8 follow-up: Agent A preserves us_stocks when rewriting latest_data.json
# ---------------------------------------------------------------------------

def test_agent_a_preserves_us_stocks(tmp_path, monkeypatch):
    """Agent A must not drop us_stocks written by us_stocks_updater (step 0).

    Seeds latest_data.json with a us_stocks field, mocks all of Agent A's
    network/data-fetch methods, runs AgentA.run(), then confirms:
    1. us_stocks is preserved unchanged.
    2. Agent A's own normal fields are present.
    """
    import asyncio
    from agents.agent_a import AgentA

    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    seed_us_stocks = {
        "source": "finnhub",
        "stocks": {"AAPL": 150.0},
        "total_symbols": 1,
        "timestamp": "2026-05-09T09:31:00",
    }
    (tmp_path / "data" / "latest_data.json").write_text(
        json.dumps({"us_stocks": seed_us_stocks}), encoding="utf-8"
    )

    agent = AgentA()

    # Stub all async fetch methods to avoid real network calls.
    async def _empty_list(): return []
    async def _empty_str(): return ""
    async def _none(): return None

    with patch.object(agent, "fetch_polymarket_markets", side_effect=_empty_list), \
         patch.object(agent, "fetch_google_news", side_effect=_empty_str), \
         patch.object(agent, "fetch_fred_rates", side_effect=_empty_list), \
         patch.object(agent, "fetch_okx_funding", side_effect=_none), \
         patch.object(agent, "fetch_okx_data", side_effect=_none):
        asyncio.run(agent.run())

    result = json.loads((tmp_path / "data" / "latest_data.json").read_text())

    # us_stocks must be preserved intact
    assert result["us_stocks"] == seed_us_stocks

    # Agent A's own fields must still be written
    assert "timestamp" in result
    assert "polymarket_markets" in result
    assert "google_news" in result


def test_agent_a_handles_missing_existing_file(tmp_path, monkeypatch):
    """Agent A must work normally when latest_data.json does not yet exist."""
    import asyncio
    from agents.agent_a import AgentA

    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    agent = AgentA()

    async def _empty_list(): return []
    async def _empty_str(): return ""
    async def _none(): return None

    with patch.object(agent, "fetch_polymarket_markets", side_effect=_empty_list), \
         patch.object(agent, "fetch_google_news", side_effect=_empty_str), \
         patch.object(agent, "fetch_fred_rates", side_effect=_empty_list), \
         patch.object(agent, "fetch_okx_funding", side_effect=_none), \
         patch.object(agent, "fetch_okx_data", side_effect=_none):
        asyncio.run(agent.run())  # must not raise

    result = json.loads((tmp_path / "data" / "latest_data.json").read_text())
    assert "timestamp" in result


def test_agent_a_handles_corrupt_existing_file(tmp_path, monkeypatch):
    """Agent A must not crash when existing latest_data.json is corrupt JSON."""
    import asyncio
    from agents.agent_a import AgentA

    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "latest_data.json").write_text("not json", encoding="utf-8")

    agent = AgentA()

    async def _empty_list(): return []
    async def _empty_str(): return ""
    async def _none(): return None

    with patch.object(agent, "fetch_polymarket_markets", side_effect=_empty_list), \
         patch.object(agent, "fetch_google_news", side_effect=_empty_str), \
         patch.object(agent, "fetch_fred_rates", side_effect=_empty_list), \
         patch.object(agent, "fetch_okx_funding", side_effect=_none), \
         patch.object(agent, "fetch_okx_data", side_effect=_none):
        asyncio.run(agent.run())  # must not raise even with corrupt existing file

    result = json.loads((tmp_path / "data" / "latest_data.json").read_text())
    assert "timestamp" in result


def test_agent_a_preserves_polymarket_markets_on_fetch_failure(tmp_path, monkeypatch):
    """A transient Polymarket fetch failure must not overwrite prior markets with []."""
    import asyncio
    from agents.agent_a import AgentA

    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    seed_markets = [{"id": "m1", "question": "Will test pass?"}]
    (tmp_path / "data" / "latest_data.json").write_text(
        json.dumps({"polymarket_markets": seed_markets}), encoding="utf-8"
    )

    agent = AgentA()

    async def _failed_polymarket(): return None
    async def _empty_list(): return []
    async def _empty_str(): return ""
    async def _none(): return None

    with patch.object(agent, "fetch_polymarket_markets", side_effect=_failed_polymarket), \
         patch.object(agent, "fetch_google_news", side_effect=_empty_str), \
         patch.object(agent, "fetch_fred_rates", side_effect=_empty_list), \
         patch.object(agent, "fetch_okx_funding", side_effect=_none), \
         patch.object(agent, "fetch_okx_data", side_effect=_none):
        asyncio.run(agent.run())

    result = json.loads((tmp_path / "data" / "latest_data.json").read_text())
    assert result["polymarket_markets"] == seed_markets
    assert result["polymarket_status"] == "stale"


def test_agent_a_writes_empty_polymarket_when_fetch_succeeds_empty(tmp_path, monkeypatch):
    """A successful-but-empty Polymarket response remains distinguishable from failure."""
    import asyncio
    from agents.agent_a import AgentA

    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "latest_data.json").write_text(
        json.dumps({"polymarket_markets": [{"id": "old"}]}), encoding="utf-8"
    )

    agent = AgentA()

    async def _empty_list(): return []
    async def _empty_str(): return ""
    async def _none(): return None

    with patch.object(agent, "fetch_polymarket_markets", side_effect=_empty_list), \
         patch.object(agent, "fetch_google_news", side_effect=_empty_str), \
         patch.object(agent, "fetch_fred_rates", side_effect=_empty_list), \
         patch.object(agent, "fetch_okx_funding", side_effect=_none), \
         patch.object(agent, "fetch_okx_data", side_effect=_none):
        asyncio.run(agent.run())

    result = json.loads((tmp_path / "data" / "latest_data.json").read_text())
    assert result["polymarket_markets"] == []
    assert result["polymarket_status"] == "ok"


def test_runtime_agents_read_current_polymarket_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    latest = {
        "polymarket_markets": [
            {
                "id": "m1",
                "slug": "will-bitcoin-hit-100k",
                "question": "Will Bitcoin hit $100k?",
                "outcomes": ["YES", "NO"],
                "outcome_prices": [0.42, 0.58],
                "volume": 10000,
            }
        ],
        "btc_funding_rate": 0.0001,
        "okx": {
            "data": [
                {
                    "symbol": "BTC",
                    "spot_price": 81185.7,
                    "swap_price": 81153.8,
                    "funding_rate": 0.000036,
                }
            ]
        },
    }
    (tmp_path / "data" / "latest_data.json").write_text(json.dumps(latest), encoding="utf-8")

    from agents.agent_d import AgentD
    from agents.agent_e import AgentE
    from agents.agent_f import AgentF

    d_markets = AgentD().load_market_data()
    e_markets = AgentE().load_market_data()
    f_data = AgentF().load_market_data()

    assert len(d_markets) == 1
    assert d_markets[0]["yes_price"] == 0.42
    assert d_markets[0]["no_price"] == 0.58
    assert len(e_markets) == 1
    assert f_data["polymarket_markets"][0]["slug"] == "will-bitcoin-hit-100k"


def test_write_paper_signal_requires_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    monkeypatch.delenv("EXECUTOR_DRY_RUN", raising=False)
    from scripts import write_paper_signal

    with pytest.raises(SystemExit):
        write_paper_signal.main()


def test_write_paper_signal_creates_timestamped_signal(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")
    from scripts import write_paper_signal

    write_paper_signal.main()

    signals = json.loads((tmp_path / "data" / "signals.json").read_text())
    assert len(signals) == 1
    assert signals[0]["source"] == "paper_smoke"
    assert signals[0]["paper"] is True
    assert signals[0]["generated_at"]
    assert signals[0]["timestamp"]


# ---------------------------------------------------------------------------
# P2 #10: agent_cn_stocks path migration to _paths.get_base_dir()
# ---------------------------------------------------------------------------

def test_agent_cn_stocks_respects_pa_base_dir(tmp_path, monkeypatch):
    """AgentCNStocks() with PA_BASE_DIR set must use tmp_path as base."""
    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    from agents.agent_cn_stocks import AgentCNStocks

    agent = AgentCNStocks()
    assert agent.base_dir == tmp_path
    assert agent.data_dir == tmp_path / "data"
    assert agent.logs_dir == tmp_path / "logs"


def test_agent_cn_stocks_explicit_base_dir(tmp_path):
    """Explicit base_dir= argument must still be respected."""
    from agents.agent_cn_stocks import AgentCNStocks

    explicit = tmp_path / "custom"
    agent = AgentCNStocks(base_dir=str(explicit))
    assert agent.base_dir == explicit
    assert agent.data_dir == explicit / "data"


def test_agent_cn_stocks_load_data_reads_from_pa_base_dir(tmp_path, monkeypatch):
    """load_data() must read latest_data.json from PA_BASE_DIR/data, not /opt/data."""
    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    from agents.agent_cn_stocks import AgentCNStocks

    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    fixture = {
        "polymarket_markets": [
            {"id": "m1", "question": "Will Huawei ...", "outcome_prices": [0.6, 0.4]}
        ],
        "cn_stocks": {
            "data": [{"code": "002502", "name": "鼎龙股份", "price": 10.0}],
            "count": 1,
            "timestamp": "2026-05-09T00:00:00",
        },
    }
    (tmp_path / "data" / "latest_data.json").write_text(
        json.dumps(fixture), encoding="utf-8"
    )

    agent = AgentCNStocks()
    markets, cn_stocks = agent.load_data()

    assert len(markets) == 1
    assert "002502" in cn_stocks


# ---------------------------------------------------------------------------
# P2 #10 follow-up: analyze_arbitrage() handles string/non-numeric prices
# ---------------------------------------------------------------------------

def _cn_stocks_fixture(outcome_prices, change_pct=-3.0):
    """Return (market, cn_stocks) with the given outcome_prices list and change_pct."""
    market = {
        "id": "m1",
        "slug": "will-huawei-x",
        "question": "Will Huawei launch X?",
        "outcomes": ["YES", "NO"],
        "outcome_prices": outcome_prices,
    }
    cn_stocks = {
        "002502": {
            "code": "002502",
            "name": "鼎龙股份",
            "price": 10.0,
            "change_pct": change_pct,
        }
    }
    return market, cn_stocks


def test_agent_cn_stocks_string_prices_produce_signal(tmp_path, monkeypatch):
    """String outcome_prices like '0.61'/'0.39' must be coerced and produce a signal."""
    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    from agents.agent_cn_stocks import AgentCNStocks

    agent = AgentCNStocks()
    # Use change_pct=-4.0 to cross the strict < -3 threshold and guarantee a signal.
    market, cn_stocks = _cn_stocks_fixture(["0.61", "0.39"], change_pct=-4.0)

    result = agent.analyze_arbitrage(market, cn_stocks)

    # String prices must be coerced and produce exactly one signal.
    assert isinstance(result, list), "analyze_arbitrage must return a list"
    assert len(result) == 1, f"Expected 1 signal, got {len(result)}"
    signal = result[0]
    assert signal["polymarket_price"] == 0.61, (
        f"Expected polymarket_price=0.61, got {signal['polymarket_price']}"
    )
    assert signal["polymarket_action"] == "SELL", (
        f"Expected polymarket_action='SELL', got {signal['polymarket_action']}"
    )


def test_agent_cn_stocks_nonnumeric_prices_do_not_raise(tmp_path, monkeypatch):
    """Non-numeric outcome_prices like 'N/A' must be skipped without exception."""
    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))
    from agents.agent_cn_stocks import AgentCNStocks

    agent = AgentCNStocks()
    market, cn_stocks = _cn_stocks_fixture(["N/A", "N/A"])

    result = agent.analyze_arbitrage(market, cn_stocks)

    # Must not raise; no signal produced since all prices skipped
    assert result is None or result == []


# ---------------------------------------------------------------------------
# P3 #12: rotate_logs.py smoke tests
# ---------------------------------------------------------------------------

import importlib.util as _ilu
import os as _os
import time as _time


def _load_rotate_logs():
    """Import scripts/rotate_logs.py without requiring it on sys.path."""
    spec = _ilu.spec_from_file_location(
        "rotate_logs",
        str(PROJECT_ROOT / "scripts" / "rotate_logs.py"),
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_old_log(path, days_old=35):
    """Write a dummy .log file and backdate its mtime."""
    path.write_text("old log line\n")
    old_mtime = _time.time() - days_old * 86400
    _os.utime(path, (old_mtime, old_mtime))


def _make_recent_log(path):
    """Write a dummy .log file with current mtime."""
    path.write_text("recent log line\n")


def test_rotate_logs_dryrun_does_not_move_files(tmp_path):
    """Dry-run must not move or compress any files."""
    rl = _load_rotate_logs()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    archive_dir = tmp_path / "archive"

    old_log = logs_dir / "old_20260101.log"
    _make_old_log(old_log)

    summary = rl.rotate_logs(
        logs_dir=logs_dir,
        retention_days=30,
        archive_dir=archive_dir,
        apply=False,
    )

    assert len(summary["archived"]) == 1
    assert old_log.exists(), "dry-run must not remove the source log"
    assert not archive_dir.exists(), "dry-run must not create archive dir"


def test_rotate_logs_apply_archives_old_and_keeps_recent(tmp_path):
    """--apply must gzip old logs and leave recent logs untouched."""
    rl = _load_rotate_logs()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    archive_dir = tmp_path / "archive"

    old_log = logs_dir / "old_20260101.log"
    recent_log = logs_dir / "recent_20260509.log"
    _make_old_log(old_log)
    _make_recent_log(recent_log)

    summary = rl.rotate_logs(
        logs_dir=logs_dir,
        retention_days=30,
        archive_dir=archive_dir,
        apply=True,
    )

    assert len(summary["archived"]) == 1
    assert len(summary["skipped"]) == 1
    assert not old_log.exists(), "old log must be removed after archiving"
    assert recent_log.exists(), "recent log must remain"
    archived_gz = archive_dir / "old_20260101.log.gz"
    assert archived_gz.exists(), "gzip archive must exist"


def test_rotate_logs_ignores_non_log_files(tmp_path):
    """Non-.log files in logs-dir must be ignored (not archived, not deleted)."""
    rl = _load_rotate_logs()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    archive_dir = tmp_path / "archive"

    non_log = logs_dir / "notes.txt"
    _make_old_log(non_log)  # old mtime, but wrong extension

    summary = rl.rotate_logs(
        logs_dir=logs_dir,
        retention_days=30,
        archive_dir=archive_dir,
        apply=True,
    )

    assert len(summary["ignored"]) == 1
    assert len(summary["archived"]) == 0
    assert non_log.exists(), "non-.log file must not be touched"


def test_rotate_logs_collision_safe(tmp_path):
    """Archiving a second log with the same name must not overwrite an existing .gz."""
    rl = _load_rotate_logs()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    # Pre-plant a collision archive
    existing_gz = archive_dir / "app.log.gz"
    existing_gz.write_bytes(b"existing")

    old_log = logs_dir / "app.log"
    _make_old_log(old_log)

    summary = rl.rotate_logs(
        logs_dir=logs_dir,
        retention_days=30,
        archive_dir=archive_dir,
        apply=True,
    )

    assert len(summary["archived"]) == 1
    assert existing_gz.read_bytes() == b"existing", "pre-existing archive must not be overwritten"
    fallback_gz = archive_dir / "app.log.1.gz"
    assert fallback_gz.exists(), "collision-safe fallback archive must be created"


# ===========================================================================
# Agent M — FIX_PLAN #9: classify_signal, _preprocess_signal, backtest script
# ===========================================================================

def _load_agent_m_class():
    """
    Load AgentM without triggering openai / llm_helper imports.
    Stubs out call_llm_sync and ReviewCache so the class body compiles.
    """
    import importlib.util
    import types

    src_path = PROJECT_ROOT / "agents" / "agent_m.py"
    source = src_path.read_text(encoding="utf-8")

    stub_source = "\n".join(
        f"# STUBBED: {line}"
        if line.startswith(("from llm_helper", "from review_cache", "import llm_helper"))
        else line
        for line in source.splitlines()
    )

    header = (
        "call_llm_sync = None\n"
        "class ReviewCache:\n"
        "    def __init__(self, *a, **kw): pass\n"
        "    def get(self, *a): return None\n"
        "    def set(self, *a): pass\n"
    )
    stub_source = header + stub_source

    mod = types.ModuleType("agent_m_stub_smoke")
    mod.__dict__["__file__"] = str(src_path)
    mod.__dict__["__name__"] = "agent_m_stub_smoke"
    exec(compile(stub_source, str(src_path), "exec"), mod.__dict__)  # noqa: S102
    return mod.AgentM


def test_agent_m_classify_signal_whitelist_extreme():
    """classify_signal correctly identifies NHL/NBA whitelist + extreme-price signals."""
    AgentM = _load_agent_m_class()

    # NHL NO >= 0.85 → whitelist_extreme
    nhl_sig = {"market_name": "Will the Vegas Golden Knights win the 2026 NHL Stanley Cup?",
                "direction": "NO", "price": 0.87}
    cls = AgentM.classify_signal(nhl_sig)
    assert cls["is_whitelist"] is True
    assert cls["is_extreme_price"] is True
    assert cls["is_whitelist_extreme"] is True
    assert cls["is_arbitrage"] is False

    # NBA YES <= 0.15 → whitelist_extreme
    nba_sig = {"market_name": "Will the Los Angeles Lakers win the 2026 NBA Finals?",
               "direction": "YES", "price": 0.0145}
    cls2 = AgentM.classify_signal(nba_sig)
    assert cls2["is_whitelist_extreme"] is True

    # Politics signal → NOT whitelist_extreme
    pol_sig = {"market_name": "Will Gina Raimondo win the 2028 Democratic presidential nomination?",
               "direction": "YES", "price": 0.0065}
    cls3 = AgentM.classify_signal(pol_sig)
    assert cls3["is_whitelist"] is False
    assert cls3["is_whitelist_extreme"] is False

    # ARBITRAGE → is_arbitrage, not whitelist_extreme
    arb_sig = {"market_name": "BTC Polymarket vs OKX arb", "direction": "ARBITRAGE", "price": 0.4}
    cls4 = AgentM.classify_signal(arb_sig)
    assert cls4["is_arbitrage"] is True
    assert cls4["is_whitelist_extreme"] is False


def test_agent_m_preprocess_caps_position_for_whitelist(tmp_path):
    """
    FIX_PLAN #9: whitelist_extreme signal with position_size >= 0.20
    must be capped to 0.19 before reaching the LLM.
    Original position preserved in _original_position_size.
    Normal signals must NOT be modified.
    """
    AgentM = _load_agent_m_class()
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    agent = AgentM(base_dir=str(tmp_path))

    # Vegas: NHL whitelist_extreme, position=0.285 → must cap to 0.19
    vegas_sig = {
        "market_name": "Will the Vegas Golden Knights win the 2026 NHL Stanley Cup?",
        "direction": "NO",
        "price": 0.87,
        "position_size": 0.285,
    }
    cls = AgentM.classify_signal(vegas_sig)
    processed = agent._preprocess_signal(vegas_sig, cls)
    assert processed["position_size"] == 0.19, "position_size must be capped to 0.19"
    assert processed["_original_position_size"] == pytest.approx(0.285), \
        "_original_position_size must record the original value"
    # Original dict must NOT be mutated
    assert vegas_sig["position_size"] == pytest.approx(0.285), "original signal must be unchanged"

    # NBA whitelist_extreme exactly at 0.20 → must also cap
    nba_sig = {
        "market_name": "Will the Philadelphia 76ers win the 2026 NBA Finals?",
        "direction": "YES",
        "price": 0.0085,
        "position_size": 0.20,
    }
    cls2 = AgentM.classify_signal(nba_sig)
    processed2 = agent._preprocess_signal(nba_sig, cls2)
    assert processed2["position_size"] == 0.19

    # Politics signal (non-whitelist): position_size MUST NOT be modified
    pol_sig = {
        "market_name": "Will Gina Raimondo win the 2028 Democratic presidential nomination?",
        "direction": "YES",
        "price": 0.0065,
        "position_size": 0.22,
    }
    cls3 = AgentM.classify_signal(pol_sig)
    processed3 = agent._preprocess_signal(pol_sig, cls3)
    assert processed3 is pol_sig, "non-whitelist signals must be returned unchanged"
    assert processed3["position_size"] == pytest.approx(0.22)


def test_agent_m_rejects_whitelist_extreme_without_audit_fields(tmp_path):
    """
    High-price sports whitelist signals must fail closed when Agent B does not
    provide auditable data_sources and logic_chain.
    """
    AgentM = _load_agent_m_class()
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    agent = AgentM(base_dir=str(tmp_path))

    signal = {
        "market_id": "montreal-cup",
        "market_name": "Will the Montreal Canadiens win the 2026 NHL Stanley Cup?",
        "direction": "NO",
        "price": 0.9075,
        "position_size": 0.1,
        "expected_value": 9.2,
    }

    result = agent.review_signal(signal)

    assert result["decision"] == "REJECT"
    assert result["market_id"] == "montreal-cup"
    assert "data_sources" in result["reason"]
    assert "logic_chain" in result["reason"]
    assert result["review"]["failure_probability"] == 100
    assert agent.cache_misses == 0, "hard rejection must happen before cache/LLM review"


def test_agent_m_rejects_signal_for_violated_theme_exposure(tmp_path):
    AgentM = _load_agent_m_class()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (tmp_path / "logs").mkdir()
    (data_dir / "risk_snapshot.json").write_text(json.dumps({
        "exposure": {
            "violations": [{
                "type": "single_theme_exposure",
                "theme": "2028_democratic_presidential_nomination",
                "value": 4513.39,
                "limit": 0.3,
            }]
        }
    }))
    agent = AgentM(base_dir=str(tmp_path))

    signal = {
        "market_id": "raimondo-2028",
        "market_name": "Will Gina Raimondo win the 2028 Democratic presidential nomination?",
        "direction": "YES",
        "price": 0.11,
        "position_size": 0.1,
        "data_sources": ["Polymarket"],
        "logic_chain": ["test"],
    }

    result = agent.review_signal(signal)

    assert result["decision"] == "REJECT"
    assert "2028_democratic_presidential_nomination" in result["reason"]
    assert "拒绝继续加仓" in result["reason"]
    assert agent.cache_misses == 0, "risk hard rejection must happen before cache/LLM review"


def test_risk_engine_uses_pm_trader_position_values_for_theme_exposure(tmp_path):
    from risk.risk_engine import RiskEngine

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    positions = [
        {
            "market_slug": "will-gina-raimondo-win-the-2028-democratic-presidential-nomination",
            "market_question": "Will Gina Raimondo win the 2028 Democratic presidential nomination?",
            "current_value": 1714.29,
            "total_cost": 1600,
        },
        {
            "market_slug": "will-zohran-mamdani-win-the-2028-democratic-presidential-nomination",
            "market_question": "Will Zohran Mamdani win the 2028 Democratic presidential nomination?",
            "current_value": 1406.25,
            "total_cost": 1500,
        },
        {
            "market_slug": "will-tim-walz-win-the-2028-democratic-presidential-nomination",
            "market_question": "Will Tim Walz win the 2028 Democratic presidential nomination?",
            "current_value": 1392.86,
            "total_cost": 1500,
        },
    ]
    (data_dir / "positions.json").write_text(json.dumps(positions))

    exposure = RiskEngine(tmp_path).check_exposure()

    assert exposure["total_exposure"] == pytest.approx(4513.4)
    assert exposure["by_theme"]["2028_democratic_presidential_nomination"] == pytest.approx(4513.4)
    assert any(
        v["type"] == "single_theme_exposure"
        and v["theme"] == "2028_democratic_presidential_nomination"
        for v in exposure["violations"]
    )


def test_agent_m_backtest_script_runs_clean():
    """
    backtest_agent_m.py must exit 0 and produce coherent output
    against the real data directory (no LLM calls).
    """
    import subprocess as sp

    result = sp.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "backtest_agent_m.py")],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"backtest script failed:\n{result.stderr}"
    assert "离线回测评估器" in result.stdout
    assert "review_results" in result.stdout
    assert "评估完成" in result.stdout


def test_review_cache_key_includes_market_and_position(tmp_path):
    """
    Agent M pre-processing changes position_size before review. The review cache
    key must include market identity and position_size, otherwise an old cached
    rejection can mask the capped 19% signal.
    """
    from review_cache import ReviewCache

    cache = ReviewCache(str(tmp_path))
    base_signal = {
        "market_id": "vegas-cup",
        "market_name": "Will the Vegas Golden Knights win the 2026 NHL Stanley Cup?",
        "direction": "NO",
        "price": 0.87,
        "position_size": 0.285,
        "reason": "NHL high NO",
    }
    capped_signal = dict(base_signal, position_size=0.19, _original_position_size=0.285)
    other_market = dict(
        capped_signal,
        market_id="sabres-cup",
        market_name="Will the Buffalo Sabres win the 2026 NHL Stanley Cup?",
    )

    assert cache.calculate_signal_hash(base_signal) != cache.calculate_signal_hash(capped_signal)
    assert cache.calculate_signal_hash(capped_signal) != cache.calculate_signal_hash(other_market)


# ---------------------------------------------------------------------------
# P1-2: agent_m review_result exposes market_id / market_name at top level
# ---------------------------------------------------------------------------

def _load_agent_m_module():
    """
    Load agent_m.py as a module with call_llm_sync injectable.
    Returns (module, AgentM_class).
    """
    import types

    src_path = PROJECT_ROOT / "agents" / "agent_m.py"
    source = src_path.read_text(encoding="utf-8")
    stub_source = "\n".join(
        f"# STUBBED: {line}"
        if line.startswith(("from llm_helper", "from review_cache", "import llm_helper"))
        else line
        for line in source.splitlines()
    )
    header = (
        "call_llm_sync = None\n"
        "class ReviewCache:\n"
        "    def __init__(self, *a, **kw): pass\n"
        "    def get(self, *a): return None\n"
        "    def set(self, *a): pass\n"
    )
    stub_source = header + stub_source
    mod = types.ModuleType("agent_m_stub_smoke2")
    mod.__dict__["__file__"] = str(src_path)
    exec(compile(stub_source, str(src_path), "exec"), mod.__dict__)  # noqa: S102
    return mod, mod.AgentM


def test_agent_m_review_result_exposes_market_id_at_top_level(tmp_path):
    """review_result dicts must have market_id and market_name at top level (both normal and exception paths)."""
    from unittest.mock import MagicMock

    mod, AgentM = _load_agent_m_module()

    signal = {
        "market_id": "will-the-vegas-golden-knights-win",
        "market_name": "Will the Vegas Golden Knights win?",
        "market_type": "NHL",
        "direction": "NO",
        "price": 0.87,
        "position_size": 0.19,
    }

    # --- Normal path: LLM returns a parseable APPROVE decision ---
    fake_llm_response = '{"decision": "APPROVE", "explanation": "ok", "risk_points": [], "failure_probability": 18}'
    mod.call_llm_sync = MagicMock(return_value=fake_llm_response)

    agent = AgentM(base_dir=str(tmp_path))
    result = agent.review_signal(signal)

    assert result.get("market_id") == "will-the-vegas-golden-knights-win", (
        f"market_id missing at top level in normal path; keys={list(result.keys())}"
    )
    assert result.get("market_name") == "Will the Vegas Golden Knights win?"
    assert result["decision"] == "APPROVE"

    # --- Exception path: LLM raises, exception handler fires ---
    mod.call_llm_sync = MagicMock(side_effect=RuntimeError("network error"))
    agent2 = AgentM(base_dir=str(tmp_path))
    result2 = agent2.review_signal(signal)

    assert result2.get("market_id") == "will-the-vegas-golden-knights-win", (
        f"market_id missing at top level in exception path; keys={list(result2.keys())}"
    )
    assert result2.get("market_name") == "Will the Vegas Golden Knights win?"
    assert result2["decision"] == "REJECT"


# ---------------------------------------------------------------------------
# P1-3: agent_b skips LLM call when polymarket_markets is empty
# ---------------------------------------------------------------------------

def _load_agent_b_module():
    """Load agent_b.py with call_llm_sync stubbed out (no openai needed)."""
    import types

    src_path = PROJECT_ROOT / "agents" / "agent_b.py"
    source = src_path.read_text(encoding="utf-8")
    stub_source = "\n".join(
        f"# STUBBED: {line}"
        if line.startswith("from llm_helper")
        else line
        for line in source.splitlines()
    )
    header = "call_llm_sync = None\n"
    stub_source = header + stub_source

    mod = types.ModuleType("agent_b_stub_smoke")
    mod.__dict__["__file__"] = str(src_path)
    exec(compile(stub_source, str(src_path), "exec"), mod.__dict__)  # noqa: S102
    return mod


def test_agent_b_skips_when_no_polymarket_markets(tmp_path, monkeypatch, capsys):
    """agent_b main() must exit early without calling LLM when polymarket_markets is []."""
    import json as _json
    from unittest.mock import MagicMock

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "latest_data.json").write_text(
        _json.dumps({"polymarket_markets": [], "us_stocks": {}})
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PA_BASE_DIR", str(tmp_path))

    mod = _load_agent_b_module()
    sentinel = MagicMock(side_effect=AssertionError("LLM must not be called"))
    mod.call_llm_sync = sentinel

    mod.main()

    sentinel.assert_not_called()
    captured = capsys.readouterr()
    assert "无 Polymarket 市场数据" in captured.out, (
        "Expected early-exit log message, got: " + captured.out
    )
