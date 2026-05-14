#!/usr/bin/env python3
"""
高级实时交易 Orchestrator v2.0
- 集成 Regime Detector（市场状态识别）
- 集成 Strategy Manager（动态策略调整）
- 集成 Agent D/E/F（多种套利策略）
- 集成学习知识库（learning_knowledge_base.json）
- 每天至少 10 笔交易，胜率 >= 80%
"""

import json
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from _paths import get_base_dir

class AdvancedOrchestrator:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.agents_dir = self.base_dir / "agents"
        self.collectors_dir = self.base_dir / "collectors"
        self.executors_dir = self.base_dir / "executors"
        
        # 确保目录存在
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 交易目标
        self.daily_trade_target = 10  # 每天不小于 10 笔交易（买入 + 卖出）
        self.daily_profit_target = 5  # 每天不小于 5 笔获利卖出
        self.win_rate_target = 0.80
        
        # 扫描间隔（秒）
        self.scan_interval = 30
        
    def log(self, message, level="INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [{level}] [Orchestrator Advanced] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"orchestrator_advanced_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def run_script(self, script_path, timeout=60):
        """运行 Python 脚本"""
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                self.log(f"脚本执行失败: {script_path}", "ERROR")
                self.log(f"错误: {result.stderr}", "ERROR")
                return False, result.stderr
        except subprocess.TimeoutExpired:
            self.log(f"脚本超时: {script_path}", "ERROR")
            return False, "Timeout"
        except Exception as e:
            self.log(f"脚本异常: {script_path} - {e}", "ERROR")
            return False, str(e)
    
    def step_0_market_regime(self):
        """步骤 0: 市场状态识别（Regime Detector）"""
        self.log("步骤 0: 市场状态识别")
        script = self.agents_dir / "regime_detector.py"
        if script.exists():
            success, output = self.run_script(script, timeout=60)
            if success:
                self.log("✅ 市场状态识别完成")
                # 读取市场状态
                regime_file = self.data_dir / "market_regime.json"
                if regime_file.exists():
                    with open(regime_file, 'r') as f:
                        regime = json.load(f)
                    self.log(f"📊 当前市场: {regime.get('regime')} (置信度 {regime.get('confidence')})")
            else:
                self.log("⚠️ 市场状态识别失败", "WARNING")
        else:
            self.log("⚠️ regime_detector.py 不存在", "WARNING")
    
    def step_0_1_strategy_manager(self):
        """步骤 0.1: 策略管理（Strategy Manager）"""
        self.log("步骤 0.1: 策略管理")
        script = self.agents_dir / "strategy_manager.py"
        if script.exists():
            success, output = self.run_script(script, timeout=60)
            if success:
                self.log("✅ 策略配置生成完成")
                # 读取策略配置
                config_file = self.data_dir / "strategy_config.json"
                if config_file.exists():
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                    self.log(f"📊 止盈范围: {config.get('take_profit', {})}")
                    self.log(f"📊 止损参数: {config.get('stop_loss', {})}")
            else:
                self.log("⚠️ 策略配置生成失败", "WARNING")
        else:
            self.log("⚠️ strategy_manager.py 不存在", "WARNING")
    
    def step_0_2_us_stocks(self):
        """步骤 0.2: 美股数据采集"""
        self.log("步骤 0.2: 美股数据采集")
        script = self.collectors_dir / "us_stocks_updater.py"
        if script.exists():
            success, output = self.run_script(script, timeout=90)
            if success:
                self.log("✅ 美股数据采集完成")
            else:
                self.log("⚠️ 美股数据采集失败", "WARNING")
        else:
            self.log("⚠️ us_stocks_updater.py 不存在", "WARNING")
    
    def step_0_3_cn_stocks(self):
        """步骤 0.3: A 股数据采集"""
        self.log("步骤 0.3: A 股数据采集")
        script = self.collectors_dir / "cn_stocks_collector.py"
        if script.exists():
            success, output = self.run_script(script, timeout=30)
            if success:
                self.log("✅ A 股数据采集完成")
            else:
                self.log("⚠️ A 股数据采集失败", "WARNING")
        else:
            self.log("⚠️ cn_stocks_collector.py 不存在", "WARNING")
    
    def step_1_data_collection(self):
        """步骤 1: 数据采集 (Agent A)"""
        self.log("步骤 1: 数据采集 (Agent A)")
        script = self.agents_dir / "agent_a.py"
        if script.exists():
            success, output = self.run_script(script, timeout=120)
            if success:
                self.log("✅ 数据采集完成")
            else:
                self.log("⚠️ 数据采集失败", "WARNING")
        else:
            self.log("⚠️ agent_a.py 不存在", "WARNING")
    
    def step_2_intelligence_analysis(self):
        """步骤 2: 情报分析 (Agent B)"""
        self.log("步骤 2: 情报分析 (Agent B)")
        script = self.agents_dir / "agent_b.py"
        if script.exists():
            success, output = self.run_script(script, timeout=120)
            if success:
                self.log("✅ 情报分析完成")
            else:
                self.log("⚠️ 情报分析失败", "WARNING")
        else:
            self.log("⚠️ agent_b.py 不存在", "WARNING")
    
    def step_3_arbitrage_strategies(self):
        """步骤 3: 多策略套利扫描"""
        self.log("步骤 3: 多策略套利扫描")
        
        # Agent K: 跨市场套利
        self.log("  → Agent K: 跨市场套利")
        script_k = self.agents_dir / "agent_k.py"
        if script_k.exists():
            success, output = self.run_script(script_k, timeout=120)
            if success:
                self.log("  ✅ Agent K 完成")
            else:
                self.log("  ⚠️ Agent K 失败", "WARNING")
        
        # Agent D: 无风险套利（YES + NO < $1.00）
        self.log("  → Agent D: 无风险套利")
        script_d = self.agents_dir / "agent_d.py"
        if script_d.exists():
            success, output = self.run_script(script_d, timeout=60)
            if success:
                self.log("  ✅ Agent D 完成")
            else:
                self.log("  ⚠️ Agent D 失败", "WARNING")
        
        # Agent E: BTC 短期套利
        self.log("  → Agent E: BTC 短期套利")
        script_e = self.agents_dir / "agent_e.py"
        if script_e.exists():
            success, output = self.run_script(script_e, timeout=60)
            if success:
                self.log("  ✅ Agent E 完成")
            else:
                self.log("  ⚠️ Agent E 失败", "WARNING")
        
        # Agent F: OKX 跨平台套利
        self.log("  → Agent F: OKX 跨平台套利")
        script_f = self.agents_dir / "agent_f.py"
        if script_f.exists():
            success, output = self.run_script(script_f, timeout=60)
            if success:
                self.log("  ✅ Agent F 完成")
            else:
                self.log("  ⚠️ Agent F 失败", "WARNING")
        
        # Agent OKX Funding: 资金费率套利
        self.log("  → Agent OKX Funding: 资金费率套利")
        script_okx = self.agents_dir / "agent_okx_funding.py"
        if script_okx.exists():
            success, output = self.run_script(script_okx, timeout=60)
            if success:
                self.log("  ✅ Agent OKX Funding 完成")
            else:
                self.log("  ⚠️ Agent OKX Funding 失败", "WARNING")
    
    def step_4_signal_review(self):
        """步骤 4: 信号审查 (Agent M)"""
        self.log("步骤 4: 信号审查 (Agent M)")
        script = self.agents_dir / "agent_m.py"
        if script.exists():
            success, output = self.run_script(script, timeout=120)
            if success:
                self.log("✅ 信号审查完成")
                
                # 读取审查结果
                signals_file = self.data_dir / "signals.json"
                if signals_file.exists():
                    with open(signals_file, 'r') as f:
                        signals = json.load(f)
                    
                    approved = [s for s in signals if s.get('approved')]
                    rejected = [s for s in signals if not s.get('approved')]
                    
                    self.log(f"📊 审查结果: {len(approved)} 通过, {len(rejected)} 拒绝")
            else:
                self.log("⚠️ 信号审查失败", "WARNING")
        else:
            self.log("⚠️ agent_m.py 不存在", "WARNING")
    
    def step_5_signal_execution(self):
        """步骤 5: 信号执行（买入）"""
        self.log("步骤 5: 信号执行（买入）")
        script = self.executors_dir / "signal_executor.py"
        if script.exists():
            success, output = self.run_script(script, timeout=180)
            if success:
                self.log("✅ 信号执行完成")
            else:
                self.log("⚠️ 信号执行失败", "WARNING")
        else:
            self.log("⚠️ signal_executor.py 不存在", "WARNING")
    
    def step_6_position_management(self):
        """步骤 6: 持仓管理 (Agent P)"""
        self.log("步骤 6: 持仓管理 (Agent P)")
        script = self.agents_dir / "agent_p.py"
        if script.exists():
            success, output = self.run_script(script, timeout=180)
            if success:
                self.log("✅ 持仓管理完成")
            else:
                self.log("⚠️ 持仓管理失败", "WARNING")
        else:
            self.log("⚠️ agent_p.py 不存在", "WARNING")
    
    def step_7_sell_execution(self):
        """步骤 7: 卖出执行"""
        self.log("步骤 7: 卖出执行")
        script = self.executors_dir / "sell_executor.py"
        if script.exists():
            success, output = self.run_script(script, timeout=180)
            if success:
                self.log("✅ 卖出执行完成")
            else:
                self.log("⚠️ 卖出执行失败", "WARNING")
        else:
            self.log("⚠️ sell_executor.py 不存在", "WARNING")
    
    def step_8_trade_review(self):
        """步骤 8: 交易复盘 (Agent G)"""
        self.log("步骤 8: 交易复盘 (Agent G)")
        script = self.agents_dir / "agent_g.py"
        if script.exists():
            success, output = self.run_script(script, timeout=120)
            if success:
                self.log("✅ 交易复盘完成")
            else:
                self.log("⚠️ 交易复盘失败", "WARNING")
        else:
            self.log("⚠️ agent_g.py 不存在", "WARNING")
    
    def check_daily_progress(self):
        """检查每日进度"""
        self.log("检查每日进度...")
        
        trade_file = self.data_dir / "trade_log.json"
        if not trade_file.exists():
            self.log("⚠️ 无交易记录")
            return
        
        try:
            with open(trade_file, 'r') as f:
                trades = json.load(f)
            
            # 筛选今日交易
            today = datetime.now().strftime("%Y-%m-%d")
            today_trades = [t for t in trades if t.get('timestamp', '').startswith(today)]
            
            # 统计买入和卖出
            buys = [t for t in today_trades if t.get('action') == 'buy']
            sells = [t for t in today_trades if t.get('action') == 'sell']
            
            # 计算真实胜率（匹配历史买入记录）
            profitable_sells = 0
            for sell in sells:
                market = sell.get('market')
                outcome = sell.get('outcome')
                sell_price = sell.get('price', 0)
                sell_time = sell.get('timestamp')
                
                # 查找对应的买入记录（同一市场 + 同一结果 + 时间在卖出之前）
                matching_buys = [
                    b for b in trades 
                    if b.get('action') == 'buy' 
                    and b.get('market') == market 
                    and b.get('outcome') == outcome
                    and b.get('timestamp', '') < sell_time
                ]
                
                if matching_buys:
                    # 使用最近的买入记录
                    buy = matching_buys[-1]
                    buy_price = buy.get('price', 0)
                    
                    # 真实盈亏 = 卖出价格 - 买入价格
                    profit = sell_price - buy_price
                    
                    if profit > 0:
                        profitable_sells += 1
            
            win_rate = profitable_sells / len(sells) if sells else 0
            
            total_trades = len(buys) + len(sells)
            
            self.log(f"📊 今日交易: {total_trades}/{self.daily_trade_target} 笔")
            self.log(f"📊 买入: {len(buys)} 笔")
            self.log(f"📊 卖出: {len(sells)} 笔")
            self.log(f"📊 获利卖出: {profitable_sells}/{self.daily_profit_target} 笔")
            self.log(f"📊 胜率: {win_rate:.1%} (目标 {self.win_rate_target:.0%})")
            
            # 检查是否达标
            if total_trades >= self.daily_trade_target:
                self.log("✅ 交易数量达标")
            else:
                self.log(f"⚠️ 交易数量不足，还需 {self.daily_trade_target - total_trades} 笔", "WARNING")
            
            if profitable_sells >= self.daily_profit_target:
                self.log("✅ 获利卖出达标")
            else:
                self.log(f"⚠️ 获利卖出不足，还需 {self.daily_profit_target - profitable_sells} 笔", "WARNING")
            
            if win_rate >= self.win_rate_target:
                self.log("✅ 胜率达标")
            else:
                self.log(f"⚠️ 胜率不达标，当前 {win_rate:.1%}，目标 {self.win_rate_target:.0%}", "WARNING")
        
        except Exception as e:
            self.log(f"❌ 检查进度失败: {e}", "ERROR")
    
    def run_cycle(self):
        """运行一个完整周期"""
        self.log("=" * 80)
        self.log("开始新的交易周期")
        self.log("=" * 80)
        
        try:
            # 步骤 0: 市场状态识别
            self.step_0_market_regime()
            
            # 步骤 0.1: 策略管理
            self.step_0_1_strategy_manager()
            
            # 步骤 0.2: 美股数据采集
            self.step_0_2_us_stocks()
            
            # 步骤 0.3: A 股数据采集
            self.step_0_3_cn_stocks()
            
            # 步骤 1: 数据采集
            self.step_1_data_collection()
            
            # 步骤 2: 情报分析
            self.step_2_intelligence_analysis()
            
            # 步骤 3: 多策略套利扫描
            self.step_3_arbitrage_strategies()
            
            # 步骤 4: 信号审查
            self.step_4_signal_review()
            
            # 步骤 5: 信号执行（买入）
            self.step_5_signal_execution()
            
            # 步骤 6: 持仓管理
            self.step_6_position_management()
            
            # 步骤 7: 卖出执行
            self.step_7_sell_execution()
            
            # 步骤 8: 交易复盘
            self.step_8_trade_review()
            
            # 检查每日进度
            self.check_daily_progress()
            
            self.log("✅ 交易周期完成")
        
        except Exception as e:
            self.log(f"❌ 交易周期异常: {e}", "ERROR")
        
        self.log("=" * 80)
    
    def run(self):
        """主循环"""
        self.log("🚀 高级 Orchestrator 启动")
        self.log(f"📊 交易目标: {self.daily_trade_target} 笔/天, 胜率 >= {self.win_rate_target:.0%}")
        self.log(f"⏱️  扫描间隔: {self.scan_interval} 秒")
        
        while True:
            try:
                self.run_cycle()
                
                self.log(f"⏸️  等待 {self.scan_interval} 秒...")
                time.sleep(self.scan_interval)
            
            except KeyboardInterrupt:
                self.log("⏹️  收到停止信号，退出...")
                break
            except Exception as e:
                self.log(f"❌ 主循环异常: {e}", "ERROR")
                self.log(f"⏸️  等待 {self.scan_interval} 秒后重试...")
                time.sleep(self.scan_interval)

def main():
    orchestrator = AdvancedOrchestrator()
    orchestrator.run()

if __name__ == "__main__":
    main()
