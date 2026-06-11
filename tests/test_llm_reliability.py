"""LLM 调用可靠性：fallback、sentinel 过滤、model_error 与 risk_reject 区分。"""

import json
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_fallback_sentinel_filtered_from_map():
    from llm_helper import get_fallback_map

    cfg = {
        "fallback_map": {
            "deepseek-v4-pro": "__SINGLE_PROVIDER_NO_FALLBACK__",
            "grok-4.3": "claude-opus-4-7",
        }
    }
    fb = get_fallback_map(cfg)
    assert "__SINGLE_PROVIDER_NO_FALLBACK__" not in fb.values()
    assert fb["deepseek-v4-pro"] == "grok-4-1-fast-reasoning"


def test_agent_m_e_f_route_via_agent_b():
    from llm_helper import routing_agent_id

    assert routing_agent_id("agent_m_primary") == "agent_b"
    assert routing_agent_id("agent_e") == "agent_b"
    assert routing_agent_id("agent_f") == "agent_b"
    assert routing_agent_id("agent_b") == "agent_b"
    assert routing_agent_id("agent_g") == "agent_g"


def test_build_model_chain_excludes_sentinel():
    from llm_helper import _build_model_chain

    cfg = {
        "fallback_map": {"deepseek-v4-pro": "__SINGLE_PROVIDER_NO_FALLBACK__"},
        "agent_providers": {},
    }
    chain = _build_model_chain(cfg, "deepseek-v4-pro")
    assert chain == ["deepseek-v4-pro", "grok-4-1-fast-reasoning"]


@patch("llm_helper._call_single_model")
def test_primary_connection_error_uses_fallback(mock_call):
    from llm_helper import LLMModelError, call_llm_sync

    mock_call.side_effect = [
        LLMModelError("conn", error_type="connection_error", models_tried=["deepseek-v4-pro"]),
        "ok from fallback",
    ]

    with patch("llm_helper.load_llm_config") as mock_cfg:
        mock_cfg.return_value = {
            "agent_models": {"agent_b": "deepseek-v4-pro", "agent_e": "deepseek-v4-pro"},
            "agent_providers": {
                "agent_b": {
                    "model": "deepseek-v4-pro",
                    "api_base": "https://api.deepseek.com",
                    "api_key": "k",
                    "proxy": "http://127.0.0.1:17891",
                },
                "agent_g": {
                    "model": "grok-4-1-fast-reasoning",
                    "api_base": "https://api.example/v1",
                    "api_key": "k",
                }
            },
            "proxy_api_key": "k",
            "proxy_api_base": "https://api.deepseek.com",
        }
        out = call_llm_sync("agent_e", "ping", timeout=60)

    assert out == "ok from fallback"
    assert mock_call.call_count == 2


@patch("llm_helper._call_single_model")
def test_all_providers_fail_raises_model_error(mock_call):
    from llm_helper import LLMModelError, call_llm_sync

    mock_call.side_effect = LLMModelError(
        "API 错误: Connection error.",
        error_type="connection_error",
        models_tried=["deepseek-v4-pro"],
    )

    with patch("llm_helper.load_llm_config") as mock_cfg:
        mock_cfg.return_value = {
            "agent_models": {"agent_m_primary": "deepseek-v4-pro"},
            "agent_providers": {},
            "proxy_api_key": "k",
            "proxy_api_base": "https://api.deepseek.com",
        }
        with pytest.raises(LLMModelError) as exc:
            call_llm_sync("agent_m_primary", "ping", timeout=30)

    assert exc.value.error_type == "connection_error"


def _load_agent_m_module():
    src_path = PROJECT_ROOT / "agents" / "agent_m.py"
    source = src_path.read_text(encoding="utf-8")
    stub_source = "\n".join(
        f"# STUBBED: {line}"
        if line.startswith(("from llm_helper", "from review_cache", "import llm_helper"))
        else line
        for line in source.splitlines()
    )
    header = (
        "from llm_helper import LLMModelError\n"
        "call_llm_sync = None\n"
        "class ReviewCache:\n"
        "    def __init__(self, *a, **kw): pass\n"
        "    def get(self, *a): return None\n"
        "    def set(self, *a): pass\n"
    )
    mod = types.ModuleType("agent_m_reliability")
    mod.__dict__["__file__"] = str(src_path)
    exec(compile(header + stub_source, str(src_path), "exec"), mod.__dict__)  # noqa: S102
    return mod


def test_agent_m_model_error_not_counted_as_risk_reject(tmp_path):
    from llm_helper import LLMModelError

    mod = _load_agent_m_module()
    signal = {
        "market_id": "m1",
        "market_name": "Test market",
        "direction": "YES",
        "position_size": 0.1,
        "data_sources": ["x"],
        "logic_chain": ["a", "b"],
    }

    err = LLMModelError(
        "API 错误: Connection error.",
        error_type="connection_error",
        agent_id="agent_m_primary",
        models_tried=["deepseek-v4-pro", "grok-4-1-fast-reasoning"],
        fallback_used=True,
    )
    mod.call_llm_sync = MagicMock(side_effect=err)

    agent = mod.AgentM(base_dir=str(tmp_path))
    result = agent.review_signal(signal)

    assert result["review_status"] == "model_error"
    assert result["decision"] == "DEFER"
    assert result["review"]["error_type"] == "connection_error"
    assert agent._grade(result) == "DEFER"


@patch("llm_helper._call_single_model")
def test_hedged_race_grok_fast_path_no_hedge(mock_call):
    from llm_helper import call_llm_hedged_race

    mock_call.return_value = "grok ok"
    with patch("llm_helper.load_llm_config") as mock_cfg:
        mock_cfg.return_value = {
            "agent_models": {"agent_b": "grok-4-1-fast-reasoning"},
            "agent_providers": {
                "agent_b": {
                    "model": "grok-4-1-fast-reasoning",
                    "api_base": "https://api.example/v1",
                    "api_key": "k",
                },
                "deepseek_v4_flash": {
                    "model": "deepseek-v4-flash",
                    "api_base": "https://api.deepseek.com",
                    "api_key": "k",
                },
            },
            "fallback_map": {"grok-4-1-fast-reasoning": "deepseek-v4-flash"},
            "proxy_api_key": "k",
            "proxy_api_base": "https://api.deepseek.com",
        }
        content, stats = call_llm_hedged_race("agent_b", "ping", hedge_delay_sec=0.01, deadline_sec=5)

    assert content == "grok ok"
    assert stats["winner"] == "grok"
    assert stats["hedge_triggered"] is False
    assert stats["deepseek_started"] is False
    assert mock_call.call_count == 1


@patch("llm_helper._call_single_model")
def test_hedged_race_triggers_flash_on_grok_hang(mock_call):
    import time
    from llm_helper import call_llm_hedged_race

    def _side_effect(**kwargs):
        if kwargs["current_model"] == "grok-4-1-fast-reasoning":
            time.sleep(0.05)
            raise Exception("hang")
        return "flash ok"

    mock_call.side_effect = lambda **kw: _side_effect(**kw)

    with patch("llm_helper.load_llm_config") as mock_cfg:
        mock_cfg.return_value = {
            "agent_models": {"agent_b": "grok-4-1-fast-reasoning"},
            "agent_providers": {
                "agent_b": {
                    "model": "grok-4-1-fast-reasoning",
                    "api_base": "https://api.example/v1",
                    "api_key": "k",
                },
                "deepseek_v4_flash": {
                    "model": "deepseek-v4-flash",
                    "api_base": "https://api.deepseek.com",
                    "api_key": "k",
                },
            },
            "fallback_map": {"grok-4-1-fast-reasoning": "deepseek-v4-flash"},
            "proxy_api_key": "k",
            "proxy_api_base": "https://api.deepseek.com",
        }
        content, stats = call_llm_hedged_race("agent_b", "ping", hedge_delay_sec=0.01, deadline_sec=5)

    assert content == "flash ok"
    assert stats["hedge_triggered"] is True
    assert stats["deepseek_started"] is True
    assert stats["winner"] == "deepseek"
    assert mock_call.call_count == 2


def test_agent_m_risk_reject_still_reject(tmp_path):
    mod = _load_agent_m_module()
    agent = mod.AgentM(base_dir=str(tmp_path))

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "risk_snapshot.json").write_text(
        json.dumps(
            {
                "exposure": {
                    "violations": [
                        {
                            "type": "single_theme_exposure",
                            "theme": "2028_democratic_presidential_nomination",
                            "value": 4600,
                            "limit": 0.3,
                        }
                    ]
                }
            }
        )
    )

    signal = {
        "market_id": "hunter",
        "market_name": "Will Hunter Biden win the 2028 Democratic presidential nomination?",
        "theme": "2028_democratic_presidential_nomination",
        "direction": "YES",
        "position_size": 0.1,
    }
    result = agent.review_signal(signal)
    assert result["review_status"] == "risk_reject"
    assert result["decision"] == "REJECT"
    assert agent._grade(result) == "REJECT"
