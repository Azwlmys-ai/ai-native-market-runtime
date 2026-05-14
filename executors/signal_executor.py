"""
Signal Executor - 执行层买入
职责：执行通过审查的交易信号
"""

import json
import os
import subprocess
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir, get_pm_trader, get_pm_trader_env

class SignalExecutor:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        self.trader_path = get_pm_trader()
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [Signal Executor] {message}")
    
    def load_approved_signals(self):
        """加载通过审查的信号"""
        approved_file = self.data_dir / "approved_signals.json"
        
        if not approved_file.exists():
            self.log("❌ approved_signals.json 不存在")
            return []
        
        try:
            with open(approved_file, 'r') as f:
                signals = json.load(f)
            
            return signals
        
        except Exception as e:
            self.log(f"❌ 加载审查通过的信号失败: {e}")
            return []
    
    def execute_trade(self, signal):
        """执行单个交易"""
        market_id = signal.get("market_id")
        market_name = signal.get("market_name", "Unknown")
        direction = signal.get("direction")
        price = signal.get("price")
        position_size = signal.get("position_size", 0.10)
        
        # 计算交易金额（基于 $10,000 账户）
        account_balance = 10000
        amount = int(account_balance * position_size)
        
        self.log(f"执行交易: {market_name[:60]}")
        self.log(f"  Market ID: {market_id}")
        self.log(f"  方向: {direction}, 金额: ${amount}, 价格: {price}")

        if os.environ.get("EXECUTOR_DRY_RUN", "").lower() in ("1", "true", "yes"):
            self.log(f"[DRY_RUN] would execute: {market_id} {direction} size={position_size}")
            return {
                "status": "dry_run",
                "signal": signal,
                "timestamp": datetime.now().isoformat()
            }
        
        try:
            # 使用 pm-trader 执行交易
            cmd = [
                self.trader_path,
                "buy",
                market_id,
                direction,
                str(amount)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=get_pm_trader_env()
            )
            
            if result.returncode == 0:
                self.log(f"✅ 交易成功")
                return {
                    "status": "success",
                    "signal": signal,
                    "output": result.stdout,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                self.log(f"❌ 交易失败: {result.stderr}")
                return {
                    "status": "failed",
                    "signal": signal,
                    "error": result.stderr,
                    "timestamp": datetime.now().isoformat()
                }
        
        except subprocess.TimeoutExpired:
            self.log(f"❌ 交易超时")
            return {
                "status": "timeout",
                "signal": signal,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            self.log(f"❌ 交易异常: {e}")
            return {
                "status": "error",
                "signal": signal,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def execute_signal(self, signal_data):
        """兼容旧根目录执行器的嵌套 review_results.json schema"""
        return self.execute_trade(signal_data.get("signal", signal_data))

    def _write_execution_results(
        self,
        total,
        success_count,
        dry_run_count,
        simulated_count,
        failed_count,
        results,
    ):
        output = {
            "timestamp": datetime.now().isoformat(),
            "total": total,
            "success": success_count,
            "dry_run": dry_run_count,
            "simulated": simulated_count,
            "failed": failed_count,
            "results": results
        }

        output_file = self.data_dir / "execution_results.json"
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        return output_file
    
    def run(self):
        """执行所有通过审查的信号"""
        self.log("=" * 60)
        self.log("开始执行交易信号...")
        
        signals = self.load_approved_signals()
        
        if not signals:
            self.log("ℹ️  无待执行信号")
            output_file = self._write_execution_results(
                total=0,
                success_count=0,
                dry_run_count=0,
                simulated_count=0,
                failed_count=0,
                results=[],
            )
            self.log(f"结果已保存到 {output_file}")
            self.log("=" * 60)
            return
        
        self.log(f"📊 发现 {len(signals)} 个待执行信号")
        
        results = []
        success_count = 0
        dry_run_count = 0
        simulated_count = 0
        failed_count = 0
        
        for i, signal in enumerate(signals, 1):
            self.log(f"\n[{i}/{len(signals)}]")
            result = self.execute_trade(signal)
            results.append(result)
            
            if result["status"] == "success":
                success_count += 1
            elif result["status"] == "dry_run":
                dry_run_count += 1
            elif result["status"] == "simulated":
                simulated_count += 1
            else:
                failed_count += 1
        
        output_file = self._write_execution_results(
            total=len(signals),
            success_count=success_count,
            dry_run_count=dry_run_count,
            simulated_count=simulated_count,
            failed_count=failed_count,
            results=results,
        )
        
        self.log(
            f"\n✅ 执行完成: {success_count} 成功, {dry_run_count} dry-run, "
            f"{simulated_count} simulated, {failed_count} 失败"
        )
        self.log(f"结果已保存到 {output_file}")
        self.log("=" * 60)

def main():
    executor = SignalExecutor()
    executor.run()

if __name__ == "__main__":
    main()
