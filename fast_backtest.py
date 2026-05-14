#!/usr/bin/env python3
"""
快速回测系统 - 基于规则的策略
- 使用学习知识库的策略规则
- 不依赖 LLM 实时分析
- 快速执行 100 笔交易
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import random

class FastBacktest:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.historical_dir = self.data_dir / "historical"
        self.logs_dir = self.base_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # 回测参数
        self.initial_capital = 10000
        self.current_capital = self.initial_capital
        self.positions = []
        self.trades = []
        self.target_trades = 100
        
        # 策略参数（优化版 - 提高胜率）
        self.take_profit = 0.04  # 4% 止盈（快速获利）
        self.stop_loss = -0.02   # -2% 止损（严格止损）
        self.position_size = 100  # 每笔 $100
        self.max_positions = 10  # 最多 10 个持仓
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Fast Backtest] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"fast_backtest_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_historical_data(self):
        """加载历史数据"""
        self.log("加载历史数据...")
        
        data = {}
        
        # 加载 OKX K 线数据
        for symbol in ['BTC', 'ETH', 'BNB', 'SOL']:
            file_path = self.historical_dir / f"okx_{symbol}_USDT_klines_march_2026.json"
            if file_path.exists():
                with open(file_path, 'r') as f:
                    klines = json.load(f)
                    klines.sort(key=lambda x: x['timestamp'])
                    data[symbol] = klines
                    self.log(f"✅ {symbol}: {len(klines)} 条")
        
        return data
    
    def calculate_indicators(self, klines, index):
        """计算技术指标"""
        if index < 20:
            return None
        
        # 计算 20 周期移动平均
        prices = [klines[i]['close'] for i in range(index - 19, index + 1)]
        ma20 = sum(prices) / 20
        
        # 计算波动率
        returns = [(prices[i] / prices[i-1] - 1) for i in range(1, len(prices))]
        volatility = (sum(r**2 for r in returns) / len(returns)) ** 0.5
        
        # 当前价格
        current_price = klines[index]['close']
        
        # 价格相对 MA20 的位置
        price_vs_ma = (current_price / ma20 - 1)
        
        return {
            'ma20': ma20,
            'volatility': volatility,
            'price_vs_ma': price_vs_ma,
            'current_price': current_price
        }
    
    def generate_signal(self, asset, indicators, prev_indicators):
        """生成交易信号（优化版 - 提高胜率）"""
        if not indicators or not prev_indicators:
            return None
        
        # 策略 1: 强势突破（高胜率）
        # 价格从下方突破 MA20，且波动率适中
        if (prev_indicators['price_vs_ma'] < -0.015 and 
            indicators['price_vs_ma'] > -0.005 and 
            indicators['volatility'] < 0.04):
            return {
                'action': 'buy',
                'asset': asset,
                'reason': '强势突破',
                'confidence': 85
            }
        
        # 策略 2: 深度超跌反弹（高胜率）
        # 价格跌破 MA20 超过 4%，波动率低，可能反弹
        if (indicators['price_vs_ma'] < -0.04 and 
            indicators['volatility'] < 0.03 and
            prev_indicators['price_vs_ma'] < indicators['price_vs_ma']):  # 开始反弹
            return {
                'action': 'buy',
                'asset': asset,
                'reason': '深度超跌',
                'confidence': 80
            }
        
        # 策略 3: 稳定趋势（高胜率）
        # 价格在 MA20 上方 2-4%，波动率极低
        if (0.02 < indicators['price_vs_ma'] < 0.04 and 
            indicators['volatility'] < 0.02):
            return {
                'action': 'buy',
                'asset': asset,
                'reason': '稳定趋势',
                'confidence': 75
            }
        
        # 策略 4: 回调买入（中等胜率）
        # 价格在 MA20 上方，但开始回调
        if (0.01 < indicators['price_vs_ma'] < 0.025 and 
            prev_indicators['price_vs_ma'] > indicators['price_vs_ma'] and
            indicators['volatility'] < 0.025):
            return {
                'action': 'buy',
                'asset': asset,
                'reason': '回调买入',
                'confidence': 70
            }
        
        return None
    
    def execute_trade(self, signal, price, timestamp):
        """执行买入"""
        amount = min(self.position_size, self.current_capital * 0.2)  # 最多 20% 仓位
        
        if amount < 50:  # 最小交易金额
            return False
        
        if amount > self.current_capital:
            return False
        
        shares = amount / price
        self.current_capital -= amount
        
        position = {
            'asset': signal['asset'],
            'entry_price': price,
            'shares': shares,
            'amount': amount,
            'entry_time': timestamp,
            'reason': signal['reason'],
            'confidence': signal['confidence']
        }
        
        self.positions.append(position)
        self.log(f"✅ 买入 {signal['asset']}: ${amount:.2f} @ ${price:.2f} ({signal['reason']})")
        
        return True
    
    def check_exit(self, data, index):
        """检查持仓是否需要平仓"""
        exits = []
        
        for i, pos in enumerate(self.positions):
            asset = pos['asset']
            
            if asset not in data or index >= len(data[asset]):
                continue
            
            current_price = data[asset][index]['close']
            pnl_percent = (current_price / pos['entry_price'] - 1)
            
            # 止盈
            if pnl_percent >= self.take_profit:
                exits.append((i, pos, current_price, pnl_percent, '止盈'))
            
            # 止损
            elif pnl_percent <= self.stop_loss:
                exits.append((i, pos, current_price, pnl_percent, '止损'))
        
        # 执行平仓
        for i, pos, exit_price, pnl_percent, reason in reversed(exits):
            exit_amount = pos['shares'] * exit_price
            profit = exit_amount - pos['amount']
            
            self.current_capital += exit_amount
            
            trade = {
                'asset': pos['asset'],
                'entry_price': pos['entry_price'],
                'exit_price': exit_price,
                'entry_time': pos['entry_time'],
                'exit_time': data[pos['asset']][index]['timestamp'],
                'amount': pos['amount'],
                'profit': profit,
                'pnl_percent': pnl_percent,
                'reason': reason,
                'confidence': pos['confidence']
            }
            
            self.trades.append(trade)
            self.log(f"✅ 卖出 {pos['asset']}: ${exit_amount:.2f} @ ${exit_price:.2f} ({reason}, {pnl_percent:.2%})")
            
            self.positions.pop(i)
    
    def run_backtest(self):
        """运行回测"""
        self.log("=" * 80)
        self.log("开始快速回测（2026 年 3 月）")
        self.log("=" * 80)
        
        # 加载数据
        data = self.load_historical_data()
        
        if not data:
            self.log("❌ 无历史数据")
            return
        
        # 获取最长序列
        max_length = max(len(klines) for klines in data.values())
        
        self.log(f"\n初始资金: ${self.initial_capital:,.2f}")
        self.log(f"目标交易: {self.target_trades} 笔")
        self.log(f"数据长度: {max_length} 个时间点")
        self.log(f"策略: 均线突破 + 超跌反弹 + 趋势跟随")
        self.log(f"止盈: {self.take_profit:.0%}, 止损: {self.stop_loss:.0%}\n")
        
        # 存储上一个指标
        prev_indicators = {}
        
        # 遍历时间序列
        for i in range(max_length):
            # 检查是否达到目标
            if len(self.trades) >= self.target_trades:
                self.log(f"\n✅ 达到目标交易数 {self.target_trades} 笔")
                break
            
            # 检查持仓平仓条件
            self.check_exit(data, i)
            
            # 分析每个资产
            for asset in ['BTC', 'ETH', 'BNB', 'SOL']:
                if asset not in data or i >= len(data[asset]):
                    continue
                
                # 计算指标
                indicators = self.calculate_indicators(data[asset], i)
                
                if not indicators:
                    continue
                
                # 生成信号
                if asset in prev_indicators:
                    signal = self.generate_signal(asset, indicators, prev_indicators[asset])
                    
                    if signal and signal['action'] == 'buy':
                        # 限制持仓数量
                        if len(self.positions) < self.max_positions:
                            price = data[asset][i]['close']
                            timestamp = data[asset][i]['timestamp']
                            self.execute_trade(signal, price, timestamp)
                
                # 更新指标
                prev_indicators[asset] = indicators
            
            # 每 100 个时间点输出进度
            if i % 100 == 0:
                self.log(f"进度: {i}/{max_length} ({i/max_length*100:.1f}%), 交易: {len(self.trades)}/{self.target_trades}, 资金: ${self.current_capital:,.2f}, 持仓: {len(self.positions)}")
        
        # 强制平仓
        self.log("\n强制平仓所有持仓...")
        final_index = max_length - 1
        
        for pos in self.positions:
            asset = pos['asset']
            
            if asset not in data or final_index >= len(data[asset]):
                continue
            
            exit_price = data[asset][final_index]['close']
            exit_amount = pos['shares'] * exit_price
            profit = exit_amount - pos['amount']
            pnl_percent = profit / pos['amount']
            
            self.current_capital += exit_amount
            
            trade = {
                'asset': pos['asset'],
                'entry_price': pos['entry_price'],
                'exit_price': exit_price,
                'entry_time': pos['entry_time'],
                'exit_time': data[asset][final_index]['timestamp'],
                'amount': pos['amount'],
                'profit': profit,
                'pnl_percent': pnl_percent,
                'reason': '强制平仓',
                'confidence': pos['confidence']
            }
            
            self.trades.append(trade)
        
        self.positions = []
        
        # 生成报告
        self.generate_report()
    
    def generate_report(self):
        """生成回测报告"""
        self.log("\n" + "=" * 80)
        self.log("回测报告")
        self.log("=" * 80)
        
        total_trades = len(self.trades)
        profitable_trades = len([t for t in self.trades if t['profit'] > 0])
        losing_trades = len([t for t in self.trades if t['profit'] < 0])
        win_rate = profitable_trades / total_trades if total_trades > 0 else 0
        
        total_profit = sum(t['profit'] for t in self.trades)
        total_return = (self.current_capital / self.initial_capital - 1) * 100
        
        avg_profit = sum(t['profit'] for t in self.trades if t['profit'] > 0) / profitable_trades if profitable_trades > 0 else 0
        avg_loss = sum(t['profit'] for t in self.trades if t['profit'] < 0) / losing_trades if losing_trades > 0 else 0
        
        max_profit = max((t['profit'] for t in self.trades), default=0)
        max_loss = min((t['profit'] for t in self.trades), default=0)
        
        self.log(f"\n📊 交易统计")
        self.log(f"总交易数: {total_trades}")
        self.log(f"盈利交易: {profitable_trades} ({profitable_trades/total_trades*100:.1f}%)")
        self.log(f"亏损交易: {losing_trades} ({losing_trades/total_trades*100:.1f}%)")
        self.log(f"胜率: {win_rate:.2%}")
        
        self.log(f"\n💰 收益统计")
        self.log(f"初始资金: ${self.initial_capital:,.2f}")
        self.log(f"最终资金: ${self.current_capital:,.2f}")
        self.log(f"总收益: ${total_profit:,.2f}")
        self.log(f"总回报率: {total_return:.2f}%")
        
        self.log(f"\n📈 盈亏分析")
        self.log(f"平均盈利: ${avg_profit:.2f}")
        self.log(f"平均亏损: ${avg_loss:.2f}")
        self.log(f"盈亏比: {abs(avg_profit/avg_loss):.2f}" if avg_loss != 0 else "盈亏比: N/A")
        self.log(f"最大单笔盈利: ${max_profit:.2f}")
        self.log(f"最大单笔亏损: ${max_loss:.2f}")
        
        # 按资产统计
        self.log("\n🎯 按资产统计")
        asset_stats = defaultdict(lambda: {'trades': 0, 'profit': 0, 'wins': 0})
        for trade in self.trades:
            asset = trade['asset']
            asset_stats[asset]['trades'] += 1
            asset_stats[asset]['profit'] += trade['profit']
            if trade['profit'] > 0:
                asset_stats[asset]['wins'] += 1
        
        for asset, stats in sorted(asset_stats.items()):
            win_rate = stats['wins'] / stats['trades'] if stats['trades'] > 0 else 0
            self.log(f"  {asset}: {stats['trades']} 笔, 胜率 {win_rate:.1%}, 收益 ${stats['profit']:.2f}")
        
        # 按策略统计
        self.log("\n📋 按策略统计")
        strategy_stats = defaultdict(lambda: {'trades': 0, 'profit': 0, 'wins': 0})
        for trade in self.trades:
            reason = trade.get('reason', 'Unknown')
            strategy_stats[reason]['trades'] += 1
            strategy_stats[reason]['profit'] += trade['profit']
            if trade['profit'] > 0:
                strategy_stats[reason]['wins'] += 1
        
        for strategy, stats in sorted(strategy_stats.items(), key=lambda x: x[1]['profit'], reverse=True):
            win_rate = stats['wins'] / stats['trades'] if stats['trades'] > 0 else 0
            self.log(f"  {strategy}: {stats['trades']} 笔, 胜率 {win_rate:.1%}, 收益 ${stats['profit']:.2f}")
        
        # 保存详细记录
        output_file = self.data_dir / "fast_backtest_trades.json"
        with open(output_file, 'w') as f:
            json.dump({
                'summary': {
                    'total_trades': total_trades,
                    'profitable_trades': profitable_trades,
                    'losing_trades': losing_trades,
                    'win_rate': win_rate,
                    'initial_capital': self.initial_capital,
                    'final_capital': self.current_capital,
                    'total_profit': total_profit,
                    'total_return': total_return,
                    'avg_profit': avg_profit,
                    'avg_loss': avg_loss,
                    'max_profit': max_profit,
                    'max_loss': max_loss
                },
                'trades': self.trades
            }, f, indent=2, ensure_ascii=False)
        
        self.log(f"\n✅ 详细交易记录已保存: {output_file}")
        self.log("=" * 80)

def main():
    backtest = FastBacktest()
    backtest.run_backtest()

if __name__ == "__main__":
    main()
