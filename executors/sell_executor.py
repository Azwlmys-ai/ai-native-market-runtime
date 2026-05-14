#!/usr/bin/env python3
"""
Sell signal executor.

Canonical implementation used by root sell_executor.py and orchestrator variants.
Supports both legacy Agent P signals (market/outcome/shares) and newer flat
signals (market_id/token_id/amount).
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir, get_pm_trader, get_pm_trader_env


class SellExecutor:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.config_dir = self.base_dir / "config"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [SellExecutor] {message}", flush=True)

    def load_config(self):
        config_file = self.config_dir / "system_config.json"
        try:
            with open(config_file, "r") as f:
                return json.load(f)
        except Exception as exc:
            self.log(f"⚠️ 加载配置失败: {exc}")
            return {}

    def get_pm_trader(self):
        return get_pm_trader()

    def load_sell_signals(self):
        sell_signals_file = self.data_dir / "sell_signals.json"
        if not sell_signals_file.exists():
            self.log("⚠️ sell_signals.json 不存在")
            return []

        try:
            with open(sell_signals_file, "r") as f:
                signals = json.load(f)
        except Exception as exc:
            self.log(f"❌ 加载卖出信号失败: {exc}")
            return []

        if not isinstance(signals, list):
            self.log(f"⚠️ 信号格式错误: {type(signals)}")
            return []

        priority_order = {"urgent": 0, "high": 1, "medium": 2}
        signals.sort(key=lambda x: priority_order.get(x.get("priority", "medium"), 2))
        self.log(f"📊 发现 {len(signals)} 个卖出信号")
        return signals

    def normalize_signal(self, signal):
        market = signal.get("market_id") or signal.get("market")
        outcome = signal.get("token_id") or signal.get("outcome")
        amount = signal.get("amount")
        if amount is None:
            amount = signal.get("shares", 0)

        return {
            "market": market,
            "outcome": outcome,
            "amount": amount or 0,
            "reason": signal.get("reason", "Unknown"),
            "priority": signal.get("priority", "medium"),
        }

    def execute_sell(self, signal):
        normalized = self.normalize_signal(signal)
        market = normalized["market"]
        outcome = normalized["outcome"]
        amount = normalized["amount"]

        if not market or not outcome or amount <= 0:
            self.log(f"⚠️ 信号数据不完整: {signal}")
            return {
                "status": "failed",
                "signal": signal,
                "error": "incomplete signal",
                "timestamp": datetime.now().isoformat(),
            }

        self.log(f"[{normalized['priority'].upper()}] 卖出: {market} {outcome} {amount} - {normalized['reason']}")

        if os.environ.get("EXECUTOR_DRY_RUN", "").lower() in ("1", "true", "yes"):
            self.log(f"[DRY_RUN] would sell: {market} {outcome} amount={amount}")
            return {
                "status": "dry_run",
                "signal": signal,
                "timestamp": datetime.now().isoformat(),
            }

        try:
            result = subprocess.run(
                [self.get_pm_trader(), "sell", market, outcome, str(amount)],
                capture_output=True,
                text=True,
                timeout=60,
                env=get_pm_trader_env(),
            )

            if result.returncode == 0:
                self.log("✅ 卖出成功")
                record = self._build_trade_record(signal, normalized, result.stdout, "success")
                self._append_json_log(self.data_dir / "trade_log.json", record)
                self._append_json_log(self.data_dir / "sell_log.json", record)
                return {
                    "status": "success",
                    "signal": signal,
                    "output": result.stdout,
                    "timestamp": datetime.now().isoformat(),
                }

            self.log(f"❌ 卖出失败: {result.stderr}")
            return {
                "status": "failed",
                "signal": signal,
                "error": result.stderr,
                "timestamp": datetime.now().isoformat(),
            }
        except subprocess.TimeoutExpired:
            self.log("❌ 卖出超时")
            return {
                "status": "timeout",
                "signal": signal,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as exc:
            self.log(f"❌ 卖出异常: {exc}")
            return {
                "status": "error",
                "signal": signal,
                "error": str(exc),
                "timestamp": datetime.now().isoformat(),
            }

    def _build_trade_record(self, signal, normalized, output, status):
        return {
            "timestamp": datetime.now().isoformat(),
            "action": "sell",
            "market_id": signal.get("market_id") or signal.get("market"),
            "market_name": signal.get("market_name") or signal.get("market"),
            "token_id": signal.get("token_id") or signal.get("outcome"),
            "amount": normalized["amount"],
            "reason": normalized["reason"],
            "status": status,
            "output": output,
        }

    def _append_json_log(self, path, record):
        records = []
        if path.exists():
            try:
                with open(path, "r") as f:
                    records = json.load(f)
                if not isinstance(records, list):
                    records = []
            except Exception:
                records = []

        records.append(record)
        with open(path, "w") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

    def run(self):
        signals = self.load_sell_signals()
        if not signals:
            self.log("⚠️ 无卖出信号")
            return

        results = [self.execute_sell(signal) for signal in signals]
        success_count = sum(1 for result in results if result["status"] == "success")
        dry_run_count = sum(1 for result in results if result["status"] == "dry_run")
        failed_count = len(results) - success_count - dry_run_count

        self.log(f"✅ 卖出完成: {success_count} success, {dry_run_count} dry-run, {failed_count} failed")

        sell_signals_file = self.data_dir / "sell_signals.json"
        with open(sell_signals_file, "w") as f:
            json.dump([], f)

        self.log("✅ 卖出信号已清空")


def main():
    SellExecutor().run()


if __name__ == "__main__":
    main()
