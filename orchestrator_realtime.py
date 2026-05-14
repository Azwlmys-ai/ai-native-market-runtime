#!/usr/bin/env python3
"""
实时交易 Orchestrator
- 每天至少 10 笔交易
- 胜率 >= 80%
- 每笔交易后复盘
"""

import json
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from _paths import get_base_dir, get_pm_trader, get_pm_trader_env

class RealtimeOrchestrator:
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
        log_msg = f"[{timestamp}] [{level}] [Orchestrator] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"orchestrator_{datetime.now().strftime('%Y%m%d')}.log"
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
    
    def step_0_us_stocks(self):
        """步骤 0: 美股数据采集"""
        self.log("步骤 0: 美股数据采集")
        script = self.collectors_dir / "us_stocks_updater.py"
        if script.exists():
            success, output = self.run_script(script, timeout=90)  # 增加到 90 秒
            if success:
                self.log("✅ 美股数据采集完成")
            else:
                self.log("⚠️ 美股数据采集失败", "WARNING")
        else:
            self.log("⚠️ us_stocks_updater.py 不存在", "WARNING")
    
    def step_0_1_cn_stocks(self):
        """步骤 0.1: A 股数据采集"""
        self.log("步骤 0.1: A 股数据采集")
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
            success, output = self.run_script(script, timeout=60)
            if success:
                self.log("✅ 数据采集完成")
            else:
                self.log("⚠️ 数据采集失败", "WARNING")
        else:
            self.log("❌ agent_a.py 不存在", "ERROR")
    
    def step_2_intelligence(self):
        """步骤 2: 情报分析 (Agent B Enhanced v2)"""
        self.log("步骤 2: 情报分析 (Agent B Enhanced v2)")
        script = self.agents_dir / "agent_b_enhanced_v2.py"
        if script.exists():
            success, output = self.run_script(script, timeout=120)
            if success:
                self.log("✅ 情报分析完成")
            else:
                self.log("⚠️ 情报分析失败", "WARNING")
        else:
            self.log("❌ agent_b_enhanced_v2.py 不存在", "ERROR")
    
    def step_3_cross_market_arbitrage(self):
        """步骤 3: 跨市场套利 (Agent K)"""
        self.log("步骤 3: 跨市场套利 (Agent K)")
        script = self.agents_dir / "agent_k_v2.py"
        if script.exists():
            success, output = self.run_script(script, timeout=120)
            if success:
                self.log("✅ 跨市场套利分析完成")
            else:
                self.log("⚠️ 跨市场套利分析失败", "WARNING")
        else:
            self.log("⚠️ agent_k_v2.py 不存在", "WARNING")
    
    def step_4_okx_funding(self):
        """步骤 4: OKX 资金费率套利"""
        self.log("步骤 4: OKX 资金费率套利")
        script = self.agents_dir / "agent_okx_funding.py"
        if script.exists():
            success, output = self.run_script(script, timeout=60)
            if success:
                self.log("✅ OKX 资金费率分析完成")
            else:
                self.log("⚠️ OKX 资金费率分析失败", "WARNING")
        else:
            self.log("⚠️ agent_okx_funding.py 不存在", "WARNING")
    
    def step_4_1_cn_stocks_arbitrage(self):
        """步骤 4.1: A 股套利分析"""
        self.log("步骤 4.1: A 股套利分析")
        script = self.agents_dir / "agent_cn_stocks.py"
        if script.exists():
            success, output = self.run_script(script, timeout=60)
            if success:
                self.log("✅ A 股套利分析完成")
            else:
                self.log("⚠️ A 股套利分析失败", "WARNING")
        else:
            self.log("⚠️ agent_cn_stocks.py 不存在", "WARNING")
    
    def step_4_2_stock_trader(self):
        """步骤 4.2: 美股/港股套利分析"""
        self.log("步骤 4.2: 美股/港股套利分析")
        script = self.agents_dir / "agent_stock_trader.py"
        if script.exists():
            success, output = self.run_script(script, timeout=60)
            if success:
                self.log("✅ 美股/港股套利分析完成")
            else:
                self.log("⚠️ 美股/港股套利分析失败", "WARNING")
        else:
            self.log("⚠️ agent_stock_trader.py 不存在", "WARNING")
    
    def step_5_signal_review(self):
        """步骤 5: 信号审查 (Agent M)"""
        self.log("步骤 5: 信号审查 (Agent M)")
        script = self.agents_dir / "agent_m.py"
        if script.exists():
            success, output = self.run_script(script, timeout=120)
            if success:
                self.log("✅ 信号审查完成")
                return True
            else:
                self.log("⚠️ 信号审查失败", "WARNING")
                return False
        else:
            self.log("❌ agent_m.py 不存在", "ERROR")
            return False
    
    def step_6_execute_signals(self):
        """步骤 6: 执行交易信号（Polymarket + OKX + 股票）"""
        self.log("步骤 6: 执行交易信号")
        
        # 6.1: 执行 Polymarket 交易
        self.log("步骤 6.1: 执行 Polymarket 交易")
        polymarket_count = 0
        
        approved_signals_file = self.data_dir / "approved_signals.json"
        if approved_signals_file.exists():
            with open(approved_signals_file, 'r') as f:
                approved_signals = json.load(f)
            
            if approved_signals:
                self.log(f"📊 发现 {len(approved_signals)} 个 Polymarket 信号")
                
                script = self.executors_dir / "signal_executor.py"
                if script.exists():
                    success, output = self.run_script(script, timeout=180)
                    if success:
                        self.log("✅ Polymarket 交易执行完成")
                        polymarket_count = len(approved_signals)
                    else:
                        self.log("⚠️ Polymarket 交易执行失败", "WARNING")
        
        # 6.2: 执行 OKX 模拟交易
        self.log("步骤 6.2: 执行 OKX 模拟交易")
        okx_count = 0
        
        okx_signals_file = self.data_dir / "okx_arbitrage_signals.json"
        if okx_signals_file.exists():
            with open(okx_signals_file, 'r') as f:
                okx_signals = json.load(f)
            
            if okx_signals:
                self.log(f"📊 发现 {len(okx_signals)} 个 OKX 信号")
                
                script = self.executors_dir / "okx_paper_trader.py"
                if script.exists():
                    success, output = self.run_script(script, timeout=60)
                    if success:
                        self.log("✅ OKX 模拟交易完成")
                        okx_count = len(okx_signals)
                    else:
                        self.log("⚠️ OKX 模拟交易失败", "WARNING")
        
        # 6.3: 执行股票模拟交易
        self.log("步骤 6.3: 执行美股模拟交易")
        stock_count = 0
        
        stock_signals_file = self.data_dir / "stock_arbitrage_signals.json"
        if stock_signals_file.exists():
            with open(stock_signals_file, 'r') as f:
                stock_signals = json.load(f)
            
            if stock_signals:
                self.log(f"📊 发现 {len(stock_signals)} 个美股信号")
                
                script = self.executors_dir / "stock_paper_trader.py"
                if script.exists():
                    success, output = self.run_script(script, timeout=60)
                    if success:
                        self.log("✅ 美股模拟交易完成")
                        stock_count = len(stock_signals)
                    else:
                        self.log("⚠️ 美股模拟交易失败", "WARNING")
        
        # 6.4: 执行 A 股模拟交易
        self.log("步骤 6.4: 执行 A 股模拟交易")
        cn_stock_count = 0
        
        cn_stock_signals_file = self.data_dir / "cn_stocks_arbitrage_signals.json"
        if cn_stock_signals_file.exists():
            with open(cn_stock_signals_file, 'r') as f:
                cn_stock_signals = json.load(f)
            
            if cn_stock_signals:
                self.log(f"📊 发现 {len(cn_stock_signals)} 个 A 股信号")
                
                script = self.executors_dir / "cn_stocks_paper_trader.py"
                if script.exists():
                    success, output = self.run_script(script, timeout=60)
                    if success:
                        self.log("✅ A 股模拟交易完成")
                        cn_stock_count = len(cn_stock_signals)
                    else:
                        self.log("⚠️ A 股模拟交易失败", "WARNING")
        
        total_count = polymarket_count + okx_count + stock_count + cn_stock_count
        self.log(f"✅ 总计执行 {total_count} 笔交易 (Polymarket: {polymarket_count}, OKX: {okx_count}, 美股: {stock_count}, A股: {cn_stock_count})")
        
        return total_count
    
    def step_7_position_management(self):
        """步骤 7: 持仓管理 (Agent P + 止损检查)"""
        self.log("步骤 7: 持仓管理 (Agent P)")
        
        # 先运行止损检查
        stop_loss_script = self.agents_dir / "agent_p_stop_loss.py"
        if stop_loss_script.exists():
            success, output = self.run_script(stop_loss_script, timeout=60)
            if success:
                self.log("✅ 止损检查完成")
            else:
                self.log("⚠️ 止损检查失败", "WARNING")
        
        # 再运行常规持仓管理
        script = self.agents_dir / "agent_p.py"
        if script.exists():
            success, output = self.run_script(script, timeout=120)
            if success:
                self.log("✅ 持仓管理完成")
            else:
                self.log("⚠️ 持仓管理失败", "WARNING")
        else:
            self.log("⚠️ agent_p.py 不存在", "WARNING")
    
    def step_8_execute_sells(self):
        """步骤 8: 执行卖出信号"""
        self.log("步骤 8: 执行卖出信号")
        
        # 读取卖出信号
        sell_signals_file = self.data_dir / "sell_signals.json"
        if not sell_signals_file.exists():
            self.log("⚠️ 无卖出信号", "WARNING")
            return 0
        
        with open(sell_signals_file, 'r') as f:
            sell_signals = json.load(f)
        
        if not sell_signals:
            self.log("⚠️ 卖出信号为空", "WARNING")
            return 0
        
        self.log(f"📊 发现 {len(sell_signals)} 个卖出信号")
        
        # 执行卖出
        script = self.executors_dir / "sell_executor.py"
        if script.exists():
            success, output = self.run_script(script, timeout=180)
            if success:
                self.log("✅ 卖出执行完成")
                return len(sell_signals)
            else:
                self.log("⚠️ 卖出执行失败", "WARNING")
                return 0
        else:
            self.log("❌ sell_executor.py 不存在", "ERROR")
            return 0
    
    def step_9_learning(self):
        """步骤 9: 交易复盘 (Agent G)"""
        self.log("步骤 9: 交易复盘 (Agent G)")
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
        """检查每日交易进度（买入 + 卖出），计算真实胜率"""
        try:
            # 调用 pm-trader history 获取交易记录
            result = subprocess.run(
                [get_pm_trader(), "history", "--limit", "100"],
                capture_output=True,
                text=True,
                timeout=10,
                env=get_pm_trader_env()
            )
            
            if result.returncode != 0:
                self.log("⚠️ 无法读取交易历史", "WARNING")
                return 0, 0, 0, 0.0
            
            data = json.loads(result.stdout)
            trades = data.get('data', [])
            
            # 统计今日交易
            today = datetime.now().strftime("%Y-%m-%d")
            today_trades = [t for t in trades if t.get("created_at", "").startswith(today)]
            
            # 区分买入和卖出（注意：pm-trader 使用小写 "buy"/"sell"）
            buys = [t for t in today_trades if t.get("side", "").lower() == "buy"]
            sells = [t for t in today_trades if t.get("side", "").lower() == "sell"]
            
            # 构建买入成本字典（使用全部历史，不限今日）
            buy_costs = {}
            all_buys = [t for t in trades if t.get("side", "").lower() == "buy"]
            for buy in all_buys:
                key = (buy.get("market_condition_id"), buy.get("outcome"))
                if key not in buy_costs:
                    buy_costs[key] = []
                buy_costs[key].append({
                    "avg_price": buy.get("avg_price", 0),
                    "amount_usd": buy.get("amount_usd", 0),
                    "shares": buy.get("shares", 0),
                    "fee": buy.get("fee", 0),
                    "created_at": buy.get("created_at", "")
                })
            
            # 统计获利卖出（真实盈亏计算）
            profitable_sells = 0
            for sell in sells:
                key = (sell.get("market_condition_id"), sell.get("outcome"))
                sell_time = sell.get("created_at", "")
                
                # 查找对应的买入记录（在卖出之前）
                if key in buy_costs:
                    matching_buys = [b for b in buy_costs[key] if b["created_at"] < sell_time]
                    
                    if matching_buys:
                        # 使用最近一次买入的平均价格
                        latest_buy = matching_buys[-1]
                        buy_avg_price = latest_buy["avg_price"]
                        sell_avg_price = sell.get("avg_price", 0)
                        
                        # 判断获利：卖出价格 > 买入价格
                        if sell_avg_price > buy_avg_price:
                            profitable_sells += 1
                else:
                    # 没有匹配的买入记录，使用旧逻辑（卖出价格 > 0.5）
                    if sell.get("avg_price", 0) > 0.5:
                        profitable_sells += 1
            
            total_trades = len(buys) + len(sells)
            win_rate = profitable_sells / len(sells) if sells else 0.0
            
            return total_trades, len(buys), profitable_sells, win_rate
        
        except Exception as e:
            self.log(f"⚠️ 读取交易进度失败: {e}", "WARNING")
            return 0, 0, 0, 0.0
    
    def run_cycle(self):
        """执行一次完整的交易周期"""
        self.log("=" * 60)
        self.log("🚀 开始新的交易周期")
        
        # 步骤 0: 美股数据采集
        self.step_0_us_stocks()
        
        # 步骤 0.1: A 股数据采集
        self.step_0_1_cn_stocks()
        
        # 步骤 1: 数据采集
        self.step_1_data_collection()
        
        # 步骤 2: 情报分析
        self.step_2_intelligence()
        
        # 步骤 3: 跨市场套利
        self.step_3_cross_market_arbitrage()
        
        # 步骤 4: OKX 资金费率套利
        self.step_4_okx_funding()
        
        # 步骤 4.1: A 股套利分析
        self.step_4_1_cn_stocks_arbitrage()
        
        # 步骤 4.2: 美股/港股套利分析
        self.step_4_2_stock_trader()
        
        # 步骤 5: 信号审查
        review_success = self.step_5_signal_review()
        
        if review_success:
            # 步骤 6: 执行交易
            executed_count = self.step_6_execute_signals()
            
            # 步骤 7: 持仓管理
            self.step_7_position_management()
            
            # 步骤 8: 执行卖出
            sold_count = self.step_8_execute_sells()
            
            # 步骤 9: 交易复盘
            if executed_count > 0 or sold_count > 0:
                self.step_9_learning()
        
        # 检查每日进度
        total_trades, buys_count, profitable_sells, win_rate = self.check_daily_progress()
        
        self.log("=" * 60)
        self.log(f"📊 今日交易统计:")
        self.log(f"   总交易笔数: {total_trades}/{self.daily_trade_target} (买入: {buys_count}, 卖出: {total_trades - buys_count})")
        self.log(f"   获利卖出: {profitable_sells}/{self.daily_profit_target}")
        self.log(f"   胜率: {win_rate:.1%} (目标: {self.win_rate_target:.0%})")
        
        if total_trades < self.daily_trade_target:
            remaining = self.daily_trade_target - total_trades
            self.log(f"⚠️ 今日交易不足，还需至少 {remaining} 笔", "WARNING")
        else:
            self.log(f"✅ 今日交易已达标 ({total_trades} 笔)")
        
        if profitable_sells < self.daily_profit_target:
            remaining_profit = self.daily_profit_target - profitable_sells
            self.log(f"⚠️ 获利卖出不足，还需至少 {remaining_profit} 笔", "WARNING")
        else:
            self.log(f"✅ 获利卖出已达标 ({profitable_sells} 笔)")
        
        if win_rate < self.win_rate_target and total_trades > 0:
            self.log(f"⚠️ 胜率低于目标", "WARNING")
        elif total_trades > 0:
            self.log(f"✅ 胜率达标")
        
        self.log("✅ 交易周期完成")
        self.log("=" * 60)
    
    def run_continuous(self):
        """持续运行"""
        self.log("🚀 启动实时交易系统")
        self.log(f"   扫描间隔: {self.scan_interval} 秒")
        self.log(f"   每日交易目标: 不小于 {self.daily_trade_target} 笔 (买入 + 卖出)")
        self.log(f"   每日获利目标: 不小于 {self.daily_profit_target} 笔")
        self.log(f"   胜率目标: {self.win_rate_target:.0%}")
        
        cycle_count = 0
        
        while True:
            try:
                cycle_count += 1
                self.log(f"📍 第 {cycle_count} 个周期")
                
                self.run_cycle()
                
                self.log(f"⏳ 等待 {self.scan_interval} 秒后开始下一个周期")
                time.sleep(self.scan_interval)
                
            except KeyboardInterrupt:
                self.log("⚠️ 收到中断信号，停止系统", "WARNING")
                break
            except Exception as e:
                self.log(f"❌ 系统异常: {e}", "ERROR")
                self.log(f"⏳ 等待 {self.scan_interval} 秒后重试")
                time.sleep(self.scan_interval)

def main():
    orchestrator = RealtimeOrchestrator()
    orchestrator.run_continuous()

if __name__ == "__main__":
    main()
