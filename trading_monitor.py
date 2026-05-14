#!/usr/bin/env python3
"""
实时监控和交易分析系统
- 实时监控 8 个数据源
- 分析交易机会
- 确保每天至少 10 笔交易
- 每笔交易后复盘
- 胜率目标 >= 80%
"""

import json
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

class TradingMonitor:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        
        # 交易目标
        self.daily_trade_target = 10  # 每天至少 10 笔
        self.win_rate_target = 0.80   # 胜率目标 80%
        
        # 监控状态
        self.last_check = None
        self.trades_today = 0
        self.wins_today = 0
        
    def log(self, message, level="INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [{level}] [Monitor] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"trading_monitor_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def check_data_sources(self):
        """检查所有数据源状态"""
        self.log("=" * 60)
        self.log("检查数据源状态")
        
        latest_data_file = self.data_dir / "latest_data.json"
        if not latest_data_file.exists():
            self.log("❌ latest_data.json 不存在", "ERROR")
            return False
        
        with open(latest_data_file, 'r') as f:
            data = json.load(f)
        
        # 检查数据源
        sources = {
            "polymarket_markets": "Polymarket 市场",
            "google_news": "Google News",
            "fed_rate": "FRED 利率",
            "btc_funding_rate": "BTC 资金费率",
            "okx": "OKX 加密货币",
            "us_stocks": "美股数据"
        }
        
        all_ok = True
        for key, name in sources.items():
            if key in data:
                if key == "okx":
                    count = len(data[key].get("data", []))
                    if count > 0:
                        self.log(f"✅ {name}: {count} 个币种")
                    else:
                        self.log(f"❌ {name}: 数据为空", "WARNING")
                        all_ok = False
                elif key == "us_stocks":
                    count = data[key].get("total_symbols", 0)
                    if count > 0:
                        self.log(f"✅ {name}: {count} 个股票")
                    else:
                        self.log(f"❌ {name}: 数据为空", "WARNING")
                        all_ok = False
                elif key == "polymarket_markets":
                    count = len(data[key])
                    if count > 0:
                        self.log(f"✅ {name}: {count} 个市场")
                    else:
                        self.log(f"❌ {name}: 数据为空", "WARNING")
                        all_ok = False
                else:
                    self.log(f"✅ {name}: 正常")
            else:
                self.log(f"❌ {name}: 缺失", "ERROR")
                all_ok = False
        
        # 检查数据时效性
        timestamp = data.get("timestamp")
        if timestamp:
            data_time = datetime.fromisoformat(timestamp)
            age = datetime.now() - data_time
            if age.total_seconds() < 300:  # 5 分钟内
                self.log(f"✅ 数据时效性: {int(age.total_seconds())} 秒前")
            else:
                self.log(f"⚠️  数据时效性: {age} 前（可能过期）", "WARNING")
                all_ok = False
        
        return all_ok
    
    def analyze_trading_opportunities(self):
        """分析交易机会"""
        self.log("=" * 60)
        self.log("分析交易机会")
        
        # 读取信号文件
        signals_file = self.data_dir / "signals.json"
        if not signals_file.exists():
            self.log("⚠️  signals.json 不存在，等待 Agent 生成信号", "WARNING")
            return []
        
        with open(signals_file, 'r') as f:
            signals = json.load(f)
        
        if not signals:
            self.log("⚠️  当前无交易信号", "WARNING")
            return []
        
        self.log(f"📊 发现 {len(signals)} 个交易信号")
        
        # 分析信号质量
        high_quality = []
        for signal in signals:
            confidence = signal.get("confidence", 0)
            ev = signal.get("expected_value", 0)
            
            # 高质量信号标准
            if confidence >= 80 and ev >= 8:
                high_quality.append(signal)
                self.log(f"✅ 高质量信号: {signal.get('market_name', 'Unknown')}")
                self.log(f"   置信度: {confidence}%, EV: {ev}%")
        
        if high_quality:
            self.log(f"🎯 高质量信号: {len(high_quality)}/{len(signals)}")
        else:
            self.log("⚠️  无高质量信号（置信度 >= 80%, EV >= 8%）", "WARNING")
        
        return high_quality
    
    def check_daily_progress(self):
        """检查每日交易进度"""
        self.log("=" * 60)
        self.log("检查每日交易进度")
        
        # 读取交易日志
        trade_log_file = self.data_dir / "trade_log.json"
        if not trade_log_file.exists():
            self.log("⚠️  trade_log.json 不存在", "WARNING")
            return
        
        with open(trade_log_file, 'r') as f:
            trade_log = json.load(f)
        
        # 统计今日交易
        today = datetime.now().strftime("%Y-%m-%d")
        today_trades = [t for t in trade_log if t.get("timestamp", "").startswith(today)]
        
        self.trades_today = len(today_trades)
        self.wins_today = len([t for t in today_trades if t.get("status") == "win"])
        
        # 计算胜率
        win_rate = (self.wins_today / self.trades_today * 100) if self.trades_today > 0 else 0
        
        self.log(f"📊 今日交易统计:")
        self.log(f"   交易笔数: {self.trades_today}/{self.daily_trade_target}")
        self.log(f"   胜利笔数: {self.wins_today}")
        self.log(f"   胜率: {win_rate:.1f}% (目标: {self.win_rate_target*100}%)")
        
        # 检查是否达标
        if self.trades_today < self.daily_trade_target:
            remaining = self.daily_trade_target - self.trades_today
            self.log(f"⚠️  今日交易不足，还需 {remaining} 笔", "WARNING")
        else:
            self.log(f"✅ 今日交易已达标")
        
        if win_rate < self.win_rate_target * 100:
            self.log(f"⚠️  胜率低于目标 ({win_rate:.1f}% < {self.win_rate_target*100}%)", "WARNING")
        else:
            self.log(f"✅ 胜率达标")
    
    def check_recent_trades(self):
        """检查最近的交易和复盘"""
        self.log("=" * 60)
        self.log("检查最近交易和复盘")
        
        # 读取学习报告
        learning_report_file = self.data_dir / "learning_report.json"
        if not learning_report_file.exists():
            self.log("⚠️  learning_report.json 不存在", "WARNING")
            return
        
        with open(learning_report_file, 'r') as f:
            learning_report = json.load(f)
        
        # 显示最近的复盘
        recent_trades = learning_report.get("recent_trades", [])
        if recent_trades:
            self.log(f"📊 最近 {len(recent_trades)} 笔交易复盘:")
            for i, trade in enumerate(recent_trades[-5:], 1):  # 显示最近 5 笔
                status = trade.get("status", "unknown")
                market = trade.get("market_name", "Unknown")
                profit = trade.get("profit_pct", 0)
                
                status_icon = "✅" if status == "win" else "❌"
                self.log(f"   {i}. {status_icon} {market}: {profit:+.2f}%")
        else:
            self.log("⚠️  无最近交易记录", "WARNING")
        
        # 显示学习建议
        recommendations = learning_report.get("recommendations", [])
        if recommendations:
            self.log(f"💡 系统建议:")
            for rec in recommendations[:3]:  # 显示前 3 条
                self.log(f"   - {rec}")
    
    def generate_trading_suggestions(self):
        """生成交易建议"""
        self.log("=" * 60)
        self.log("生成交易建议")
        
        # 如果今日交易不足，提供建议
        if self.trades_today < self.daily_trade_target:
            remaining = self.daily_trade_target - self.trades_today
            self.log(f"🎯 建议: 今日还需完成 {remaining} 笔交易")
            self.log(f"   策略建议:")
            self.log(f"   1. 降低置信度阈值（从 80% 降至 70%）")
            self.log(f"   2. 增加扫描频率（从 30 秒降至 15 秒）")
            self.log(f"   3. 启用更多交易策略（NHL、娱乐市场）")
        
        # 如果胜率不足，提供建议
        win_rate = (self.wins_today / self.trades_today * 100) if self.trades_today > 0 else 0
        if win_rate < self.win_rate_target * 100:
            self.log(f"🎯 建议: 胜率需要提升")
            self.log(f"   策略建议:")
            self.log(f"   1. 提高置信度阈值（从 80% 升至 85%）")
            self.log(f"   2. 增加 EV 阈值（从 8% 升至 10%）")
            self.log(f"   3. 加强 Agent M 风险审查")
    
    def run_once(self):
        """执行一次完整的监控"""
        self.log("🔍 开始实时监控")
        
        # 1. 检查数据源
        data_ok = self.check_data_sources()
        
        # 2. 分析交易机会
        opportunities = self.analyze_trading_opportunities()
        
        # 3. 检查每日进度
        self.check_daily_progress()
        
        # 4. 检查最近交易
        self.check_recent_trades()
        
        # 5. 生成建议
        self.generate_trading_suggestions()
        
        self.log("✅ 监控完成")
        self.log("=" * 60)
        
        return data_ok, opportunities
    
    async def run_continuous(self, interval=60):
        """持续监控"""
        self.log("🚀 启动持续监控模式")
        self.log(f"   监控间隔: {interval} 秒")
        self.log(f"   每日交易目标: {self.daily_trade_target} 笔")
        self.log(f"   胜率目标: {self.win_rate_target*100}%")
        
        while True:
            try:
                self.run_once()
                await asyncio.sleep(interval)
            except KeyboardInterrupt:
                self.log("⚠️  收到中断信号，停止监控", "WARNING")
                break
            except Exception as e:
                self.log(f"❌ 监控异常: {e}", "ERROR")
                await asyncio.sleep(interval)

def main():
    monitor = TradingMonitor()
    
    # 执行一次监控
    monitor.run_once()

if __name__ == "__main__":
    main()
