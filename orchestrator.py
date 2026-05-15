"""
Orchestrator - Multi-Agent 系统调度器
职责：协调所有 Agent 的执行顺序和数据流
"""

import json
import os
import time
import asyncio
from pathlib import Path
from datetime import datetime
from _paths import get_base_dir, get_pm_trader, get_pm_trader_env

SIGNAL_MAX_AGE_SECONDS = 2 * 60 * 60


class Orchestrator:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self._bootstrap_runtime_files()
    
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Orchestrator] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"orchestrator_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def run_once(self):
        """执行一次完整的扫描周期"""
        self.log("=" * 60)
        self.log("开始新的扫描周期")
        
        try:
            # 第 0 步：美股数据采集（US Stocks Updater）
            self.log("步骤 0/17: 美股数据采集 (US Stocks)")
            self._run_collector("us_stocks_updater")
            
            # 第 1 步：数据采集（Agent A）
            self.log("步骤 1/17: 数据采集 (Agent A)")
            self._run_agent("agent_a")
            
            # 第 2 步：市场状态识别（Regime Detector）
            self.log("步骤 2/16: 市场状态识别 (Regime Detector)")
            self._run_agent("regime_detector")
            
            # 第 3 步：策略管理（Strategy Manager）
            self.log("步骤 3/16: 策略管理 (Strategy Manager)")
            self._run_agent("strategy_manager")
            
            # 第 4 步：资金分配（Capital Adapter）
            self.log("步骤 4/16: 资金分配 (Capital Adapter)")
            self._run_agent("capital_adapter")
            
            # 第 5 步：情报研究（Agent B）
            self.log("步骤 5/16: 情报研究 (Agent B)")
            self._run_agent("agent_b")
            
            # 第 6 步：价值投资（Agent K v2）
            self.log("步骤 6/16: 价值投资 (Agent K v2)")
            self._run_agent("agent_k_v2")
            
            # 第 7 步：无风险套利（Agent D）
            self.log("步骤 7/16: 无风险套利 (Agent D)")
            self._run_agent("agent_d")
            
            # 第 8 步：BTC 套利（Agent E）
            self.log("步骤 8/16: BTC 套利 (Agent E)")
            self._run_agent("agent_e")
            
            # 第 9 步：跨平台套利（Agent F）
            self.log("步骤 9/16: 跨平台套利 (Agent F)")
            self._run_agent("agent_f")
            
            # 第 10 步：钱包跟单（Agent H）
            self.log("步骤 10/16: 钱包跟单 (Agent H)")
            self._run_agent("agent_h")
            
            # 第 11 步：资金费率套利（Agent OKX Funding）
            self.log("步骤 11/16: 资金费率套利 (Agent OKX Funding)")
            self._run_agent("agent_okx_funding")
            
            # 第 12 步：交叉验证（Agent J）
            self.log("步骤 12/16: 交叉验证 (Agent J)")
            self._run_agent("agent_j")
            
            # 步骤 12.5：汇总各 agent 信号到 signals.json
            self._consolidate_signals_for_review()

            # 步骤 12.6：定量风险引擎（P0 Risk Engine）
            self.log("步骤 12.6/17: 定量风险引擎 (RiskEngine)")
            self._run_risk_engine()

            # 第 13 步：风险审查（Agent M）
            self.log("步骤 13/17: 风险审查 (Agent M)")
            signals_ready, skip_reason = self._signals_ready_for_review()
            if signals_ready:
                self._run_agent("agent_m")
            else:
                self.log(f"⏭️  跳过 Agent M: {skip_reason}")
                self._write_skipped_review(skip_reason)
            
            # 第 14 步：信号执行（买入）
            self.log("步骤 14/16: 信号执行（买入）")
            if signals_ready:
                self._execute_signals()
            else:
                self.log(f"⏭️  跳过买入执行: {skip_reason}")
                self._write_skipped_execution_results(skip_reason)
            
            # 第 15 步：持仓管理（Agent P）
            self.log("步骤 15/16: 持仓管理 (Agent P)")
            self._run_agent("agent_p")
            
            # 第 16 步：卖出执行
            self.log("步骤 16/16: 卖出执行")
            self._execute_sell_signals()
            
            # 第 17 步：交易复盘（Agent G）
            self.log("步骤 17/18: 交易复盘 (Agent G)")
            self._run_agent("agent_g")
            
            # 第 18 步：系统监控（Agent I）
            self.log("步骤 18/18: 系统监控 (Agent I)")
            self._run_agent("agent_i")
            
            self.log("✅ 扫描周期完成")
        
        except Exception as e:
            self.log(f"❌ 扫描周期失败: {e}")

    def _bootstrap_runtime_files(self):
        """Create minimal runtime files that downstream agents expect."""
        positions_file = self.data_dir / "positions.json"
        if not positions_file.exists():
            with open(positions_file, "w") as f:
                json.dump([], f, indent=2, ensure_ascii=False)

    def _run_risk_engine(self):
        """P0: 运行定量风险引擎，生成 data/risk_snapshot.json"""
        try:
            from risk.risk_engine import RiskEngine
            engine = RiskEngine(self.base_dir)
            output = engine.run()
            self.log(f"✅ RiskEngine 快照已生成: {output}")
        except Exception as e:
            self.log(f"⚠️  RiskEngine 执行失败（不中断流水线）: {e}")

    def _signal_max_age_seconds(self):
        raw_value = os.environ.get("SIGNAL_MAX_AGE_SECONDS", str(SIGNAL_MAX_AGE_SECONDS))
        try:
            return max(0, int(raw_value))
        except ValueError:
            return SIGNAL_MAX_AGE_SECONDS

    def _parse_signal_time(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None

    def _signals_ready_for_review(self):
        """Fail closed when the signal batch is empty, invalid, or stale."""
        signals_file = self.data_dir / "signals.json"
        if not signals_file.exists():
            return False, "signals.json missing"

        try:
            with open(signals_file, "r") as f:
                signals = json.load(f)
        except Exception as exc:
            return False, f"signals.json unreadable: {exc}"

        if not isinstance(signals, list):
            return False, f"signals.json schema is {type(signals).__name__}, expected list"
        if not signals:
            return False, "signals.json has no signals"

        missing_time_count = 0
        signal_times = []
        for signal in signals:
            if not isinstance(signal, dict):
                return False, "signals.json contains non-object signal"
            parsed = self._parse_signal_time(signal.get("generated_at") or signal.get("timestamp"))
            if parsed is None:
                missing_time_count += 1
            else:
                signal_times.append(parsed)

        if missing_time_count:
            return False, f"signals missing generated_at: count={missing_time_count}"

        newest_signal_ts = max(signal_times)
        age_seconds = datetime.now().timestamp() - newest_signal_ts
        max_age = self._signal_max_age_seconds()

        if age_seconds > max_age:
            return (
                False,
                f"signals stale: age={int(age_seconds)}s exceeds max_age={max_age}s",
            )

        return True, "signals fresh"

    def _consolidate_signals_for_review(self):
        """把各 agent 本轮产出的信号汇总到 signals.json，供 Agent M 审查。
        各 agent 输出格式不统一，这里做 schema 归一化。
        """
        now = datetime.now().isoformat()
        fresh_signals = []

        # --- Agent B: intelligence_report.json ---
        intel_file = self.data_dir / "intelligence_report.json"
        if intel_file.exists():
            try:
                intel = json.loads(intel_file.read_text())
                # intel 可能是 {"signals": [...]} 或直接 [...]
                raw_list = intel.get("signals", []) if isinstance(intel, dict) else intel
                # 尝试找市场名称映射（用 latest_data.json）
                market_name_map = {}
                latest = self.data_dir / "latest_data.json"
                if latest.exists():
                    ld = json.loads(latest.read_text())
                    for m in ld.get("polymarket_markets", ld.get("markets", [])):
                        slug = m.get("slug", "")
                        qid = m.get("id", "")
                        name = m.get("question", "")
                        if slug:
                            market_name_map[slug] = (qid or slug, name)

                for sig in raw_list:
                    if not isinstance(sig, dict):
                        continue
                    slug = sig.get("market_slug", "")
                    mid, mname = market_name_map.get(slug, (slug, slug))
                    side = sig.get("side", "")
                    direction = "NO" if "no" in side.lower() else "YES"
                    fresh_signals.append({
                        "market_id": mid,
                        "market_name": mname,
                        "market": mname,
                        "direction": direction,
                        "price": sig.get("price", 0.5),
                        "position_size": sig.get("position_size", 0.1),
                        "expected_value": sig.get("ev", sig.get("expected_value", 0)),
                        "confidence": sig.get("confidence", 70),
                        "source": "agent_b",
                        "generated_at": now,
                        "timestamp": now,
                    })
            except Exception as e:
                self.log(f"⚠️  读取 intelligence_report.json 失败: {e}")

        if not fresh_signals:
            self.log("⚠️  本轮无新信号，signals.json 不更新")
            return

        # 写入 signals.json（完整替换，不追加旧信号）
        signals_file = self.data_dir / "signals.json"
        with open(signals_file, "w") as f:
            json.dump(fresh_signals, f, indent=2, ensure_ascii=False)
        self.log(f"✅ 汇总 {len(fresh_signals)} 个新信号到 signals.json")

    def _write_skipped_review(self, reason):
        timestamp = datetime.now().isoformat()
        review_file = self.data_dir / "review_results.json"
        approved_file = self.data_dir / "approved_signals.json"
        review = {
            "timestamp": timestamp,
            "status": "skipped",
            "reason": reason,
            "total": 0,
            "approved": 0,
            "rejected": 0,
            "approved_signals": [],
            "rejected_signals": [],
            "cache_stats": {"hits": 0, "misses": 0, "hit_rate": "0%"},
        }
        with open(review_file, "w") as f:
            json.dump(review, f, indent=2, ensure_ascii=False)
        with open(approved_file, "w") as f:
            json.dump([], f, indent=2, ensure_ascii=False)

    def _write_skipped_execution_results(self, reason):
        output = {
            "timestamp": datetime.now().isoformat(),
            "status": "skipped",
            "reason": reason,
            "total": 0,
            "success": 0,
            "dry_run": 0,
            "simulated": 0,
            "failed": 0,
            "results": [],
        }
        output_file = self.data_dir / "execution_results.json"
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
    
    def _run_agent(self, agent_name):
        """运行单个 Agent"""
        agent_file = self.base_dir / "agents" / f"{agent_name}.py"
        
        if not agent_file.exists():
            self.log(f"⚠️  Agent 文件不存在: {agent_file}")
            return
        
        # agent_m 双模型验证；regime_detector/capital_adapter LLM 调用慢，给足时间
        if agent_name == "agent_m":
            timeout = 240
        elif agent_name in ("regime_detector", "capital_adapter"):
            timeout = 150
        else:
            timeout = 120
        
        try:
            import subprocess
            result = subprocess.run(
                ["python3", str(agent_file)],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                self.log(f"✅ {agent_name} 执行成功")
            else:
                self.log(f"❌ {agent_name} 执行失败: {result.stderr}")
        
        except subprocess.TimeoutExpired:
            self.log(f"⏱️  {agent_name} 执行超时")
        except Exception as e:
            self.log(f"❌ {agent_name} 执行异常: {e}")
    
    def _run_collector(self, collector_name):
        """运行数据采集器"""
        try:
            import subprocess
            
            collector_file = self.base_dir / "collectors" / f"{collector_name}.py"
            if collector_file.exists():
                result = subprocess.run(
                    ["python3", str(collector_file)],
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    self.log(f"✅ {collector_name} 执行成功")
                else:
                    self.log(f"❌ {collector_name} 执行失败: {result.stderr}")
            else:
                self.log(f"⚠️  {collector_name} 不存在")
        
        except subprocess.TimeoutExpired:
            self.log(f"⏱️  {collector_name} 执行超时")
        except Exception as e:
            self.log(f"❌ {collector_name} 执行异常: {e}")
    
    def _execute_signals(self):
        """执行买入信号"""
        try:
            import subprocess
            
            executor_file = self.base_dir / "signal_executor.py"
            if executor_file.exists():
                result = subprocess.run(
                    ["python3", str(executor_file)],
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    self.log("✅ 买入信号执行完成")
                else:
                    self.log(f"⚠️  买入信号执行失败: {result.stderr}")
            else:
                self.log("⚠️  买入执行器不存在")
            
        except Exception as e:
            self.log(f"❌ 买入信号执行异常: {e}")
    
    def _execute_sell_signals(self):
        """执行卖出信号"""
        try:
            import subprocess
            
            sell_executor_file = self.base_dir / "sell_executor.py"
            if sell_executor_file.exists():
                result = subprocess.run(
                    ["python3", str(sell_executor_file)],
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    self.log("✅ 卖出执行完成")
                else:
                    self.log(f"⚠️  卖出执行失败: {result.stderr}")
            else:
                self.log("⚠️  卖出执行器不存在")
        
        except Exception as e:
            self.log(f"❌ 卖出执行异常: {e}")
    
    def _generate_report(self):
        """生成周期报告"""
        try:
            import subprocess
            
            # 获取账户余额
            config_file = self.base_dir / "config" / "system_config.json"
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            result = subprocess.run(
                [get_pm_trader(), "balance"],
                capture_output=True,
                text=True,
                timeout=30,
                env=get_pm_trader_env()
            )
            
            if result.returncode == 0:
                balance_data = json.loads(result.stdout)
                if balance_data.get("ok"):
                    data = balance_data.get("data", {})
                    self.log(f"💰 账户余额: ${data.get('total_value', 0):.2f}")
                    self.log(f"📊 盈亏: ${data.get('pnl', 0):.2f}")
        
        except Exception as e:
            self.log(f"⚠️  生成报告失败: {e}")

def main():
    orchestrator = Orchestrator()
    orchestrator.run_once()

if __name__ == "__main__":
    main()
