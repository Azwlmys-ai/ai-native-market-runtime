#!/usr/bin/env python3
"""
优化后的跨市场回测系统 v11.0
基于市场关联分析结果，新增配对交易和跨市场套利策略
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

class OptimizedBacktestSystem:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data" / "historical"
        
        # 初始资金
        self.initial_capital = 30000
        self.capital = self.initial_capital
        
        # 资金分配（基于关联分析建议）
        self.allocations = {
            'polymarket': 0.50,      # 50% - 跨市场套利机会充足
            'pairs_trading': 0.30,   # 30% - 新增配对交易策略
            'crypto': 0.10,          # 10% - 降低单边加密货币
            'stocks': 0.10,          # 10% - 股票市场
        }
        
        # 持仓
        self.positions = []
        self.trade_log = []
        
        # 风控参数
        self.max_positions = {
            'polymarket': 8,
            'pairs_trading': 10,  # 提高到 10
            'crypto': 2,
            'stocks': 3
        }
        
        # 止盈止损
        self.take_profit = {
            'polymarket': 0.50,
            'pairs_trading': 0.15,  # 配对交易目标较小
            'crypto': 0.15,
            'stocks': 0.10
        }
        
        self.stop_loss = {
            'polymarket': -0.15,
            'pairs_trading': -0.05,  # 配对交易止损严格
            'crypto': -0.03,
            'stocks': -0.05
        }
        
        # 统计
        self.stats = {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'total_profit': 0,
            'max_drawdown': 0,
            'consecutive_losses': 0,
            'max_consecutive_losses': 0
        }
        
        # 配对交易参数
        self.pairs = [
            # 加密货币配对
            ('BTC-USDT', 'ETH-USDT', 0.912),
            ('ETH-USDT', 'SOL-USDT', 0.882),
            ('BTC-USDT', 'SOL-USDT', 0.867),
            ('BTC-USDT', 'BNB-USDT', 0.867),
            ('ETH-USDT', 'BNB-USDT', 0.857),
            ('SOL-USDT', 'BNB-USDT', 0.839),
            # 大宗商品配对
            ('gold', 'silver', 0.843),
            ('oil_wti', 'oil_brent', 0.859),
        ]
        
        self.pair_spreads = {}  # 存储历史价差
        
        # 配对交易触发阈值（进一步放宽）
        self.pairs_entry_zscore = 1.0  # 从 1.5 降到 1.0
        self.pairs_exit_zscore = 0.3   # 从 0.5 降到 0.3（更快平仓）
        
    def load_market_data(self):
        """加载所有市场数据"""
        print("加载市场数据...")
        
        data = {}
        
        # 加密货币
        crypto_file = self.data_dir / "okx_klines_march_april_2026.json"
        if crypto_file.exists():
            with open(crypto_file, 'r') as f:
                data['crypto'] = json.load(f)
                print(f"  ✓ 加密货币: {len(data['crypto'])} 个币种")
        
        # Polymarket
        pm_file = self.data_dir / "polymarket_extended_march_april_2026.json"
        if pm_file.exists():
            with open(pm_file, 'r') as f:
                data['polymarket'] = json.load(f)
                print(f"  ✓ Polymarket: {len(data['polymarket'])} 个市场")
        
        # 大宗商品
        commodity_file = self.data_dir / "commodities_march_april_2026.json"
        if commodity_file.exists():
            with open(commodity_file, 'r') as f:
                data['commodities'] = json.load(f)
                print(f"  ✓ 大宗商品: {len(data['commodities'])} 个品种")
        
        return data
    
    def calculate_spread_zscore(self, price1, price2, pair_key):
        """计算配对价差的 Z-Score"""
        # 价差 = price1 / price2（比率）
        spread = price1 / price2 if price2 > 0 else 0
        
        if pair_key not in self.pair_spreads:
            self.pair_spreads[pair_key] = []
        
        self.pair_spreads[pair_key].append(spread)
        
        # 需要至少 100 个数据点才能计算 Z-Score
        if len(self.pair_spreads[pair_key]) < 100:
            return 0
        
        # 计算最近 100 个数据点的均值和标准差
        recent_spreads = self.pair_spreads[pair_key][-100:]
        mean_spread = np.mean(recent_spreads)
        std_spread = np.std(recent_spreads)
        
        if std_spread == 0:
            return 0
        
        zscore = (spread - mean_spread) / std_spread
        return zscore
    
    def check_pairs_trading_signal(self, data, timestamp):
        """检查配对交易信号"""
        signals = []
        
        for asset1, asset2, correlation in self.pairs:
            # 判断是加密货币还是大宗商品
            is_crypto = 'USDT' in asset1
            
            if is_crypto:
                if 'crypto' not in data:
                    continue
                
                # 获取加密货币价格
                price1 = None
                price2 = None
                
                for symbol, info in data['crypto'].items():
                    if symbol == asset1:
                        for kline in info['data']:
                            if kline['timestamp'] == timestamp:
                                price1 = float(kline['close'])
                                break
                    elif symbol == asset2:
                        for kline in info['data']:
                            if kline['timestamp'] == timestamp:
                                price2 = float(kline['close'])
                                break
            else:
                if 'commodities' not in data:
                    continue
                
                # 获取大宗商品价格
                price1 = None
                price2 = None
                
                for name, info in data['commodities'].items():
                    if name == asset1:
                        for point in info['data']:
                            if point['timestamp'] == timestamp:
                                price1 = float(point['close']) if point['close'] else None
                                break
                    elif name == asset2:
                        for point in info['data']:
                            if point['timestamp'] == timestamp:
                                price2 = float(point['close']) if point['close'] else None
                                break
            
            if not price1 or not price2:
                continue
            
            # 计算价差 Z-Score
            pair_key = f"{asset1}_{asset2}"
            zscore = self.calculate_spread_zscore(price1, price2, pair_key)
            
            # 信号触发条件：Z-Score 超过 ±1.5（放宽）
            if zscore > self.pairs_entry_zscore:
                # 价差过大，做空 asset1，做多 asset2
                signals.append({
                    'type': 'pairs_trading',
                    'pair': (asset1, asset2),
                    'action': 'short_long',
                    'price1': price1,
                    'price2': price2,
                    'zscore': zscore,
                    'timestamp': timestamp,
                    'is_crypto': is_crypto
                })
            elif zscore < -self.pairs_entry_zscore:
                # 价差过小，做多 asset1，做空 asset2
                signals.append({
                    'type': 'pairs_trading',
                    'pair': (asset1, asset2),
                    'action': 'long_short',
                    'price1': price1,
                    'price2': price2,
                    'zscore': zscore,
                    'timestamp': timestamp,
                    'is_crypto': is_crypto
                })
        
        return signals
    
    def check_cross_market_signal(self, data, timestamp):
        """检查跨市场套利信号（Polymarket + 加密货币）"""
        signals = []
        
        if 'polymarket' not in data or 'crypto' not in data:
            return signals
        
        # 遍历 Polymarket 市场
        for pm_market in data['polymarket']:
            market_name = pm_market.get('market', pm_market.get('question', ''))
            
            # BTC 相关市场
            if 'btc' in market_name.lower() or 'bitcoin' in market_name.lower():
                # 获取 BTC 当前价格
                btc_price = None
                for symbol, info in data['crypto'].items():
                    if symbol == 'BTC-USDT':
                        for kline in info['data']:
                            if kline['timestamp'] == timestamp:
                                btc_price = float(kline['close'])
                                break
                
                if not btc_price:
                    continue
                
                # 获取 Polymarket 隐含概率
                for price_point in pm_market.get('data', []):
                    if price_point['timestamp'] == timestamp:
                        yes_price = float(price_point['yes_price'])
                        
                        # 判断市场类型
                        if '$100k' in market_name or '100k' in market_name:
                            # BTC 达到 $100k 的概率
                            implied_prob = yes_price
                            # 放宽条件：BTC > $90k 且概率 < 0.4
                            if btc_price > 90000 and implied_prob < 0.4:
                                signals.append({
                                    'type': 'cross_market',
                                    'market': market_name,
                                    'asset': 'BTC-USDT',
                                    'action': 'buy_yes',
                                    'price': yes_price,
                                    'btc_price': btc_price,
                                    'timestamp': timestamp
                                })
                            # 新增：BTC < $70k 且概率 > 0.6，做空 YES
                            elif btc_price < 70000 and implied_prob > 0.6:
                                signals.append({
                                    'type': 'cross_market',
                                    'market': market_name,
                                    'asset': 'BTC-USDT',
                                    'action': 'sell_yes',
                                    'price': yes_price,
                                    'btc_price': btc_price,
                                    'timestamp': timestamp
                                })
                        elif '$50k' in market_name or '50k' in market_name:
                            # BTC 跌破 $50k 的概率
                            implied_prob = yes_price
                            # 放宽条件：BTC > $70k 且概率 > 0.6
                            if btc_price > 70000 and implied_prob > 0.6:
                                signals.append({
                                    'type': 'cross_market',
                                    'market': market_name,
                                    'asset': 'BTC-USDT',
                                    'action': 'sell_yes',
                                    'price': yes_price,
                                    'btc_price': btc_price,
                                    'timestamp': timestamp
                                })
                            # 新增：BTC < $60k 且概率 < 0.4，做多 YES
                            elif btc_price < 60000 and implied_prob < 0.4:
                                signals.append({
                                    'type': 'cross_market',
                                    'market': market_name,
                                    'asset': 'BTC-USDT',
                                    'action': 'buy_yes',
                                    'price': yes_price,
                                    'btc_price': btc_price,
                                    'timestamp': timestamp
                                })
        
        return signals
    
    def execute_pairs_trade(self, signal):
        """执行配对交易"""
        # 检查持仓限制
        pairs_positions = [p for p in self.positions if p['strategy'] == 'pairs_trading']
        if len(pairs_positions) >= self.max_positions['pairs_trading']:
            return False
        
        # 计算仓位大小（配对交易资金的 30%，提高资金利用率）
        position_size = self.capital * self.allocations['pairs_trading'] * 0.3
        
        # 创建配对持仓
        position = {
            'strategy': 'pairs_trading',
            'pair': signal['pair'],
            'action': signal['action'],
            'entry_price1': signal['price1'],
            'entry_price2': signal['price2'],
            'entry_zscore': signal['zscore'],
            'entry_time': signal['timestamp'],
            'position_size': position_size,
            'status': 'open',
            'is_crypto': signal['is_crypto']
        }
        
        self.positions.append(position)
        self.capital -= position_size
        
        return True
    
    def execute_cross_market_trade(self, signal):
        """执行跨市场套利交易"""
        # 检查持仓限制
        pm_positions = [p for p in self.positions if p['strategy'] == 'polymarket']
        if len(pm_positions) >= self.max_positions['polymarket']:
            return False
        
        # 计算仓位大小
        position_size = self.capital * self.allocations['polymarket'] * 0.125
        
        # 创建持仓
        position = {
            'strategy': 'polymarket',
            'market': signal['market'],
            'asset': signal['asset'],
            'action': signal['action'],
            'entry_price': signal['price'],
            'btc_price': signal['btc_price'],
            'entry_time': signal['timestamp'],
            'position_size': position_size,
            'status': 'open'
        }
        
        self.positions.append(position)
        self.capital -= position_size
        
        return True
    
    def check_exit_signals(self, data, timestamp):
        """检查平仓信号"""
        for position in self.positions:
            if position['status'] != 'open':
                continue
            
            if position['strategy'] == 'pairs_trading':
                # 配对交易平仓逻辑
                asset1, asset2 = position['pair']
                is_crypto = position.get('is_crypto', 'USDT' in asset1)
                
                # 获取当前价格
                price1 = None
                price2 = None
                
                if is_crypto:
                    if 'crypto' not in data:
                        continue
                    
                    for symbol, info in data['crypto'].items():
                        if symbol == asset1:
                            for kline in info['data']:
                                if kline['timestamp'] == timestamp:
                                    price1 = float(kline['close'])
                                    break
                        elif symbol == asset2:
                            for kline in info['data']:
                                if kline['timestamp'] == timestamp:
                                    price2 = float(kline['close'])
                                    break
                else:
                    if 'commodities' not in data:
                        continue
                    
                    for name, info in data['commodities'].items():
                        if name == asset1:
                            for point in info['data']:
                                if point['timestamp'] == timestamp:
                                    price1 = float(point['close']) if point['close'] else None
                                    break
                        elif name == asset2:
                            for point in info['data']:
                                if point['timestamp'] == timestamp:
                                    price2 = float(point['close']) if point['close'] else None
                                    break
                
                if not price1 or not price2:
                    continue
                
                # 计算当前 Z-Score
                pair_key = f"{asset1}_{asset2}"
                zscore = self.calculate_spread_zscore(price1, price2, pair_key)
                
                # 平仓条件：Z-Score 回归到 ±0.5 以内
                if abs(zscore) < self.pairs_exit_zscore:
                    self.close_pairs_position(position, price1, price2, timestamp)
    
    def close_pairs_position(self, position, exit_price1, exit_price2, timestamp):
        """平仓配对交易"""
        # 计算收益
        if position['action'] == 'short_long':
            # 做空 asset1，做多 asset2
            pnl1 = (position['entry_price1'] - exit_price1) / position['entry_price1']
            pnl2 = (exit_price2 - position['entry_price2']) / position['entry_price2']
        else:
            # 做多 asset1，做空 asset2
            pnl1 = (exit_price1 - position['entry_price1']) / position['entry_price1']
            pnl2 = (position['entry_price2'] - exit_price2) / position['entry_price2']
        
        # 平均收益
        avg_pnl = (pnl1 + pnl2) / 2
        profit = position['position_size'] * avg_pnl
        
        # 更新资金
        self.capital += position['position_size'] + profit
        
        # 记录交易
        trade = {
            'strategy': 'pairs_trading',
            'pair': position['pair'],
            'entry_time': position['entry_time'],
            'exit_time': timestamp,
            'entry_price1': position['entry_price1'],
            'entry_price2': position['entry_price2'],
            'exit_price1': exit_price1,
            'exit_price2': exit_price2,
            'pnl': avg_pnl,
            'profit': profit,
            'position_size': position['position_size']
        }
        
        self.trade_log.append(trade)
        position['status'] = 'closed'
        
        # 更新统计
        self.stats['total_trades'] += 1
        if profit > 0:
            self.stats['wins'] += 1
            self.stats['consecutive_losses'] = 0
        else:
            self.stats['losses'] += 1
            self.stats['consecutive_losses'] += 1
            self.stats['max_consecutive_losses'] = max(
                self.stats['max_consecutive_losses'],
                self.stats['consecutive_losses']
            )
        
        self.stats['total_profit'] += profit
    
    def run_backtest(self):
        """运行回测"""
        print("\n" + "=" * 80)
        print("开始回测（优化版 v11.0）")
        print("=" * 80)
        
        # 加载数据
        data = self.load_market_data()
        
        if not data:
            print("✗ 无可用数据")
            return
        
        # 获取时间范围（使用加密货币数据作为基准）
        if 'crypto' not in data:
            print("✗ 缺少加密货币数据")
            return
        
        # 获取所有时间戳
        timestamps = []
        for symbol, info in data['crypto'].items():
            for kline in info['data']:
                timestamps.append(kline['timestamp'])
        
        timestamps = sorted(set(timestamps))
        print(f"\n回测时间范围: {len(timestamps)} 个时间点")
        
        # 逐时间点回测
        for i, timestamp in enumerate(timestamps):
            # 检查配对交易信号
            pairs_signals = self.check_pairs_trading_signal(data, timestamp)
            for signal in pairs_signals:
                self.execute_pairs_trade(signal)
            
            # 检查跨市场套利信号
            cross_signals = self.check_cross_market_signal(data, timestamp)
            for signal in cross_signals:
                self.execute_cross_market_trade(signal)
            
            # 检查平仓信号
            self.check_exit_signals(data, timestamp)
            
            # 每 100 个时间点打印进度
            if (i + 1) % 100 == 0:
                print(f"  进度: {i+1}/{len(timestamps)} ({(i+1)/len(timestamps)*100:.1f}%)")
        
        # 输出结果
        self.print_results()
    
    def print_results(self):
        """输出回测结果"""
        print("\n" + "=" * 80)
        print("回测结果")
        print("=" * 80)
        
        total_return = (self.capital - self.initial_capital) / self.initial_capital
        win_rate = self.stats['wins'] / self.stats['total_trades'] if self.stats['total_trades'] > 0 else 0
        
        print(f"\n初始资金: ${self.initial_capital:,.2f}")
        print(f"最终资金: ${self.capital:,.2f}")
        print(f"总收益: {total_return:+.2%} (${self.capital - self.initial_capital:+,.2f})")
        print(f"\n总交易: {self.stats['total_trades']} 笔")
        print(f"胜率: {win_rate:.1%} ({self.stats['wins']} 胜 {self.stats['losses']} 负)")
        
        # 按策略统计
        strategy_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'profit': 0})
        for trade in self.trade_log:
            strategy = trade['strategy']
            strategy_stats[strategy]['trades'] += 1
            if trade['profit'] > 0:
                strategy_stats[strategy]['wins'] += 1
            strategy_stats[strategy]['profit'] += trade['profit']
        
        print("\n按策略统计:")
        print("-" * 80)
        for strategy, stats in strategy_stats.items():
            win_rate = stats['wins'] / stats['trades'] if stats['trades'] > 0 else 0
            print(f"{strategy:20s}: {stats['trades']:3d} 笔, 胜率 {win_rate:.1%}, 收益 ${stats['profit']:+,.2f}")

if __name__ == "__main__":
    system = OptimizedBacktestSystem()
    system.run_backtest()
