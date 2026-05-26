"""
tests/test_agent_p_stop_loss.py

测试 normalize_stop_loss() 对各种输入类型的处理。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.agent_p import normalize_stop_loss, _DEFAULT_STOP_LOSS


def test_float_direct():
    """float 直接返回"""
    assert normalize_stop_loss(0.12) == 0.12
    assert normalize_stop_loss(-0.10) == -0.10


def test_int_coerced_to_float():
    """int 转为 float"""
    result = normalize_stop_loss(0)
    assert isinstance(result, float)
    assert result == 0.0


def test_dict_value_key():
    """dict 含 'value' 字段"""
    assert normalize_stop_loss({"value": 0.12}) == 0.12


def test_dict_pct_key():
    """dict 含 'pct' 字段"""
    assert normalize_stop_loss({"pct": 0.12}) == 0.12


def test_dict_stop_loss_pct_key():
    """dict 含 'stop_loss_pct' 字段"""
    assert normalize_stop_loss({"stop_loss_pct": 0.12}) == 0.12


def test_dict_range_format_uses_max():
    """strategy_config 真实格式 {"min": -0.12, "max": -0.08}，应取 max"""
    result = normalize_stop_loss({"min": -0.12, "max": -0.08})
    assert result == -0.08


def test_dict_priority_value_over_max():
    """'value' 优先级高于 'max'"""
    result = normalize_stop_loss({"value": -0.05, "max": -0.08})
    assert result == -0.05


def test_none_returns_default(capsys):
    """None → 默认值，并打印 WARNING"""
    result = normalize_stop_loss(None)
    assert result == _DEFAULT_STOP_LOSS
    captured = capsys.readouterr()
    assert "WARNING" in captured.out


def test_dict_bad_fields_returns_default(capsys):
    """dict 无任何可用数值字段 → 默认值，并打印 WARNING"""
    result = normalize_stop_loss({"bad": "x"})
    assert result == _DEFAULT_STOP_LOSS
    captured = capsys.readouterr()
    assert "WARNING" in captured.out


def test_string_returns_default(capsys):
    """非法类型（str）→ 默认值，并打印 WARNING"""
    result = normalize_stop_loss("wrong")
    assert result == _DEFAULT_STOP_LOSS
    captured = capsys.readouterr()
    assert "WARNING" in captured.out


def test_custom_default():
    """自定义 default 在非法输入时生效"""
    result = normalize_stop_loss(None, default=-0.20)
    assert result == -0.20


# ---------------------------------------------------------------------------
# 集成级：用真实 strategy_config 格式验证 analyze_positions 不再崩溃
# ---------------------------------------------------------------------------
import json
import types


def _make_agent_p(tmp_path):
    from agents.agent_p import AgentP
    agent = AgentP(base_dir=str(tmp_path))
    # 写入与生产相同结构的 strategy_config.json
    strategy_config = {
        "take_profit": {
            "default": {"min": 0.10, "max": 0.15}
        },
        "stop_loss": {
            "medium_confidence": {"min": -0.12, "max": -0.08}
        },
        "trailing_stop": {
            "trigger_profit": 0.20,
            "trailing_percent": 0.05
        }
    }
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "strategy_config.json").write_text(
        json.dumps(strategy_config)
    )
    return agent


def test_analyze_positions_with_dict_stop_loss_no_crash(tmp_path):
    """analyze_positions 使用 dict stop_loss 的 strategy_config 时不崩溃"""
    agent = _make_agent_p(tmp_path)
    positions = [
        {
            "market_slug": "btc-price-above-100k",
            "percent_pnl": -15.0,   # 超止损，应生成信号
            "outcome": "Yes",
            "shares": 10,
        },
        {
            "market_slug": "eth-price-above-5k",
            "percent_pnl": 20.0,    # 超止盈，应生成信号
            "outcome": "No",
            "shares": 5,
        },
        {
            "market_slug": "trump-wins-2028",
            "percent_pnl": 3.0,     # 小盈利，无信号（live_price 未设置）
            "outcome": "Yes",
            "shares": 3,
        },
    ]
    # 不应抛出 TypeError
    signals = agent.analyze_positions(positions)
    assert isinstance(signals, list)
    reasons = [s["reason"] for s in signals]
    # 止损信号应存在（-15% < -8%）
    assert any("止损" in r for r in reasons)
    # 止盈信号应存在（20% >= 15%）
    assert any("止盈" in r or "获利回撤" in r for r in reasons)


def test_analyze_positions_no_positions_returns_empty(tmp_path):
    """空持仓时返回空列表，不崩溃"""
    agent = _make_agent_p(tmp_path)
    signals = agent.analyze_positions([])
    assert signals == []
