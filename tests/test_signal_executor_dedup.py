"""
tests/test_signal_executor_dedup.py

验证 signal_executor 开仓去重使用 get_open_positions，异常不静默放行。
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from executors.signal_executor import SignalExecutor
from paper_pnl import PaperPortfolio, get_paper_portfolio


@pytest.fixture(autouse=True)
def _reset_global_portfolio():
    import paper_pnl as pp_mod
    pp_mod._GLOBAL_PORTFOLIO = None
    yield
    pp_mod._GLOBAL_PORTFOLIO = None


def _executor(tmp_path):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    return SignalExecutor(base_dir=str(tmp_path))


def test_has_open_position_blocks_duplicate_by_market_id(tmp_path):
    ex = _executor(tmp_path)
    pp = PaperPortfolio(base_dir=tmp_path)
    pp.open_position({
        "market_id": "540819",
        "market_slug": "dup-market",
        "direction": "NO",
        "price": 0.50,
    })
    with patch("executors.signal_executor.get_paper_portfolio", return_value=pp):
        assert ex._has_open_position({
            "market_id": "540819",
            "direction": "NO",
        }) is True


def test_has_open_position_blocks_duplicate_by_slug(tmp_path):
    ex = _executor(tmp_path)
    pp = PaperPortfolio(base_dir=tmp_path)
    pp.open_position({
        "market_id": "540844",
        "market_slug": "slug-dup-market",
        "direction": "NO",
        "price": 0.50,
    })
    with patch("executors.signal_executor.get_paper_portfolio", return_value=pp):
        assert ex._has_open_position({
            "market_slug": "slug-dup-market",
            "direction": "NO",
        }) is True


def test_has_open_position_uses_get_open_positions_not_legacy_method(tmp_path):
    ex = _executor(tmp_path)
    pp = MagicMock()
    pp.get_open_positions.return_value = []
    pp.open_positions = MagicMock(side_effect=AttributeError("no open_positions"))
    with patch("executors.signal_executor.get_paper_portfolio", return_value=pp):
        assert ex._has_open_position({
            "market_id": "1",
            "direction": "YES",
        }) is False
    pp.get_open_positions.assert_called_once()
    pp.open_positions.assert_not_called()


def test_has_open_position_raises_on_portfolio_error(tmp_path):
    ex = _executor(tmp_path)
    broken = MagicMock()
    broken.get_open_positions.side_effect = RuntimeError("portfolio broken")
    with patch("executors.signal_executor.get_paper_portfolio", return_value=broken):
        with pytest.raises(RuntimeError, match="portfolio broken"):
            ex._has_open_position({
                "market_id": "1",
                "direction": "YES",
            })


def test_execute_skips_duplicate_without_live_success(tmp_path, monkeypatch):
    ex = _executor(tmp_path)
    monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")
    pp = PaperPortfolio(base_dir=tmp_path)
    pp.open_position({
        "market_id": "999",
        "market_slug": "already-open",
        "direction": "NO",
        "price": 0.50,
    })
    signals = [{
        "market_id": "999",
        "market_slug": "already-open",
        "direction": "NO",
        "price": 0.51,
        "source": "agent_b",
        "grade": "paper_probe",
    }]
    with patch.object(ex, "load_approved_signals", return_value=signals):
        with patch("executors.signal_executor.get_paper_portfolio", return_value=pp):
            with patch.object(ex, "execute_trade") as mock_exec:
                ex.run()
                mock_exec.assert_not_called()
    results = json.loads((tmp_path / "data" / "execution_results.json").read_text())
    assert results["success"] == 0
    assert results["dry_run"] == 0
    assert any(r.get("status") == "skipped_duplicate" for r in results["results"])
