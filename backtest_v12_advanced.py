#!/usr/bin/env python3
"""
优化后的跨市场回测系统 v12.0
新增：趋势跟踪策略、动态止盈、更多配对、优化跨市场套利
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

class AdvancedBacktestSystem:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data" / "historical"
        
        # 初始资金
        self.initial_capital = 30000
        self.capital = self.initial_capital
        
        # 资金分配（优化）
        self.allocations = {
            'polymarket': 0.30,      # 30% - 跨市场套利
            'pairs_trading': 0.70,   # 70% - 配对交易（主力）
            'trend_following': 0.00, # 0% - 禁用趋势跟踪（亏损严重）
            'crypto': 0.00,          # 0% - 禁用单边加密货币
        }
        
        # 持仓
        self.positions = []
        self.trade_log = []
        
        # 风控参数
        self.max_positions = {
            'polymarket': 5,
            'pairs_trading': 6,
            'trend_following': 2,
            'crypto': 2
        }
        
        # 止盈止损
        self.take_profit = {
            'polymarket': 0.50,
            'pairs_trading': 0.15,
            'trend_following': 0.25,
            'crypto': 0.15
        }
        
        self.stop_loss = {
            'polymarket': -0.15,
            'pairs_trading': -0.03,
            'trend_following': -0.03,
            'crypto': -0.03
        }
        
        # 统计
        self.stats = {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'total_profit': 0,
            'max_drawdown': 0,
            'consecutive_losses': 0,
            'max_consecutive_losses': 0,
            'peak_capital': self.initial_capital
        }
        
        # 配对交易参数（扩展）
        self.pairs = [
            # 加密货币配对（6个）
            ('BTC-USDT', 'ETH-USDT', 0.912),
            ('ETH-USDT', 'SOL-USDT', 0.882),
            ('BTC-USDT', 'SOL-USDT', 0.867),
            ('BTC-USDT', 'BNB-USDT', 0.867),
            ('ETH-USDT', 'BNB-USDT', 0.857),
            ('SOL-USDT', 'BNB-USDT', 0.839),
            # 大宗商品配对（2个）
            ('gold', 'silver', 0.843),
            ('oil_wti', 'oil_brent', 0.859),
        ]
        
        self.pair_spreads = {}
        self.pairs_entry_zscore = 1.2
        self.pairs_exit_zscore = 0.5  # 放宽平仓条件
        
        # 趋势跟踪参数
        self.trend_lookback = 50  # 50 小时均线
        self.trend_threshold = 0.02  # 2% 突破
        
        # 动态止盈参数
        self.trailing_stop_pct = 0.3  # 回撤 30% 时止盈（更激进）
        
        # 时间止损
        self.max_holding_hours = 48  # 最长持仓 48 小时
        
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
        spread = price1 / price2 if price2 > 0 else 0
        
        if pair_key not in self.pair_spreads:
            self.pair_spreads[pair_key] = []
        
        self.pair_spreads[pair_key].append(spread)
        
        if len(self.pair_spreads[pair_key]) < 100:
            return 0
        
        recent_spreads = self.pair_spreads[pair_key][-100:]
        mean_spread = np.mean(recent_spreads)
        std_spread = np.std(recent_spreads)
        
        if std_spread == 0:
            return 0
        
        zscore = (spread - mean_spread) / std_spread
        return zscore
    
    def calculate_moving_average(self, prices, period):
        """计算移动平均"""
        if len(prices) < period:
            return None
        return np.mean(prices[-period:])
    
    def check_pairs_trading_signal(self, data, timestamp):
        """检查配对交易信号"""
        signals = []
        
        for asset1, asset2, correlation in self.pairs:
            is_crypto = 'USDT' in asset1
            
            if is_crypto:
                if 'crypto' not in data:
                    continue
                
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
            
            pair_key = f"{asset1}_{asset2}"
            zscore = self.calculate_spread_zscore(price1, price2, pair_key)
            
            if zscore > self.pairs_entry_zscore:
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
    
    def check_trend_following_signal(self, data, timestamp, price_history):
        """检查趋势跟踪信号"""
        signals = []
        
        if 'crypto' not in data:
            return signals
        
        for symbol, info in data['crypto'].items():
            # 获取当前价格
            current_price = None
            for kline in info['data']:
                if kline['timestamp'] == timestamp:
                    current_price = float(kline['close'])
                    break
            
            if not current_price:
                continue
            
            # 更新价格历史
            if symbol not in price_history:
                price_history[symbol] = []
            price_history[symbol].append(current_price)
            
            # 计算移动平均
            ma = self.calculate_moving_average(price_history[symbol], self.trend_lookback)
            
            if ma is None:
                continue
            
            # 趋势信号：价格突破均线 2%
            breakout = (current_price - ma) / ma
            
            if breakout > self.trend_threshold:
                # 上涨趋势
                signals.append({
                    'type': 'trend_following',
                    'asset': symbol,
                    'action': 'buy',
                    'price': current_price,
                    'ma': ma,
                    'breakout': breakout,
                    'timestamp': timestamp
                })
            elif breakout < -self.trend_threshold:
                # 下跌趋势（做空）
                signals.append({
                    'type': 'trend_following',
                    'asset': symbol,
                    'action': 'sell',
                    'price': current_price,
                    'ma': ma,
                    'breakout': breakout,
                    'timestamp': timestamp
                })
        
        return signals
    
    def check_cross_market_signal(self, data, timestamp):
        """检查跨市场套利信号（优化）"""
        signals = []
        
        if 'polymarket' not in data or 'crypto' not in data:
            return signals
        
        for pm_market in data['polymarket']:
            market_name = pm_market.get('market', pm_market.get('question', ''))
            
            if 'btc' in market_name.lower() or 'bitcoin' in market_name.lower():
                btc_price = None
                for symbol, info in data['crypto'].items():
                    if symbol == 'BTC-USDT':
                        for kline in info['data']:
                            if kline['timestamp'] == timestamp:
                                btc_price = float(kline['close'])
                                break
                
                if not btc_price:
                    continue
                
                for price_point in pm_market.get('data', []):
                    if price_point['timestamp'] == timestamp:
                        yes_price = float(price_point['yes_price'])
                        
                        if '$100k' in market_name or '100k' in market_name:
                            # 放宽条件
                            if btc_price > 85000 and yes_price < 0.5:
                                signals.append({
                                    'type': 'cross_market',
                                    'market': market_name,
                                    'asset': 'BTC-USDT',
                                    'action': 'buy_yes',
                                    'price': yes_price,
                                    'btc_price': btc_price,
                                    'timestamp': timestamp
                                })
                            elif btc_price < 75000 and yes_price > 0.5:
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
                            if btc_price > 65000 and yes_price > 0.5:
                                signals.append({
                                    'type': 'cross_market',
                                    'market': market_name,
                                    'asset': 'BTC-USDT',
                                    'action': 'sell_yes',
                                    'price': yes_price,
                                    'btc_price': btc_price,
                                    'timestamp': timestamp
                                })
                            elif btc_price < 55000 and yes_price < 0.5:
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
        pairs_positions = [p for p in self.positions if p['strategy'] == 'pairs_trading' and p['status'] == 'open']
        if len(pairs_positions) >= self.max_positions['pairs_trading']:
            return False
        
        # 使用当前资金计算仓位，但设置最小值保护
        base_position = self.capital * self.allocations['pairs_trading'] * 0.15
        min_position = 500  # 最小仓位 $500
        position_size = max(base_position, min_position)
        
        # 检查可用资金
        if self.capital < position_size:
            return False
        
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
            'is_crypto': signal['is_crypto'],
            'peak_profit': 0  # 动态止盈
        }
        
        self.positions.append(position)
        self.capital -= position_size
        
        return True
    
    def execute_trend_trade(self, signal):
        """执行趋势跟踪交易"""
        trend_positions = [p for p in self.positions if p['strategy'] == 'trend_following' and p['status'] == 'open']
        if len(trend_positions) >= self.max_positions['trend_following']:
            return False
        
        position_size = self.initial_capital * self.allocations['trend_following'] * 0.2
        
        if self.capital < position_size:
            return False
        
        position = {
            'strategy': 'trend_following',
            'asset': signal['asset'],
            'action': signal['action'],
            'entry_price': signal['price'],
            'entry_ma': signal['ma'],
            'entry_time': signal['timestamp'],
            'position_size': position_size,
            'status': 'open',
            'peak_profit': 0
        }
        
        self.positions.append(position)
        self.capital -= position_size
        
        return True
    
    def execute_cross_market_trade(self, signal):
        """执行跨市场套利交易"""
        pm_positions = [p for p in self.positions if p['strategy'] == 'polymarket' and p['status'] == 'open']
        if len(pm_positions) >= self.max_positions['polymarket']:
            return False
        
        position_size = self.initial_capital * self.allocations['polymarket'] * 0.1
        
        if self.capital < position_size:
            return False
        
        position = {
            'strategy': 'polymarket',
            'market': signal['market'],
            'asset': signal['asset'],
            'action': signal['action'],
            'entry_price': signal['price'],
            'btc_price': signal['btc_price'],
            'entry_time': signal['timestamp'],
            'position_size': position_size,
            'status': 'open',
            'peak_profit': 0
        }
        
        self.positions.append(position)
        self.capital -= position_size
        
        return True
    
    def check_exit_signals(self, data, timestamp):
        """检查平仓信号（动态止盈）"""
        for position in self.positions:
            if position['status'] != 'open':
                continue
            
            if position['strategy'] == 'pairs_trading':
                self.check_pairs_exit(position, data, timestamp)
            elif position['strategy'] == 'trend_following':
                self.check_trend_exit(position, data, timestamp)
    
    def check_pairs_exit(self, position, data, timestamp):
        """配对交易平仓逻辑"""
        asset1, asset2 = position['pair']
        is_crypto = position.get('is_crypto', 'USDT' in asset1)
        
        price1 = None
        price2 = None
        
        if is_crypto:
            if 'crypto' not in data:
                return
            
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
                return
            
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
            return
        
        # 计算持仓时间
        from datetime import datetime
        entry_time = datetime.fromisoformat(position['entry_time'].replace('Z', '+00:00'))
        current_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        holding_hours = (current_time - entry_time).total_seconds() / 3600
        
        # 计算当前收益
        if position['action'] == 'short_long':
            pnl1 = (position['entry_price1'] - price1) / position['entry_price1']
            pnl2 = (price2 - position['entry_price2']) / position['entry_price2']
        else:
            pnl1 = (price1 - position['entry_price1']) / position['entry_price1']
            pnl2 = (position['entry_price2'] - price2) / position['entry_price2']
        
        avg_pnl = (pnl1 + pnl2) / 2
        
        # 更新峰值收益
        if avg_pnl > position['peak_profit']:
            position['peak_profit'] = avg_pnl
        
        # 动态止盈：回撤 30%
        trailing_stop = position['peak_profit'] * (1 - self.trailing_stop_pct)
        
        # 计算 Z-Score
        pair_key = f"{asset1}_{asset2}"
        zscore = self.calculate_spread_zscore(price1, price2, pair_key)
        
        # 平仓条件：Z-Score 回归 OR 动态止盈触发 OR 止损 OR 时间止损
        if abs(zscore) < self.pairs_exit_zscore or \
           (position['peak_profit'] > 0.03 and avg_pnl < trailing_stop) or \
           avg_pnl < self.stop_loss['pairs_trading'] or \
           holding_hours > self.max_holding_hours:
            self.close_pairs_position(position, price1, price2, timestamp)
    
    def check_trend_exit(self, position, data, timestamp):
        """趋势跟踪平仓逻辑"""
        if 'crypto' not in data:
            return
        
        current_price = None
        for symbol, info in data['crypto'].items():
            if symbol == position['asset']:
                for kline in info['data']:
                    if kline['timestamp'] == timestamp:
                        current_price = float(kline['close'])
                        break
        
        if not current_price:
            return
        
        # 计算收益
        if position['action'] == 'buy':
            pnl = (current_price - position['entry_price']) / position['entry_price']
        else:
            pnl = (position['entry_price'] - current_price) / position['entry_price']
        
        # 更新峰值收益
        if pnl > position['peak_profit']:
            position['peak_profit'] = pnl
        
        # 动态止盈
        trailing_stop = position['peak_profit'] * (1 - self.trailing_stop_pct)
        
        # 平仓条件
        if pnl > self.take_profit['trend_following'] or \
           (position['peak_profit'] > 0.1 and pnl < trailing_stop) or \
           pnl < self.stop_loss['trend_following']:
            self.close_trend_position(position, current_price, timestamp)
    
    def close_pairs_position(self, position, exit_price1, exit_price2, timestamp):
        """平仓配对交易"""
        if position['action'] == 'short_long':
            pnl1 = (position['entry_price1'] - exit_price1) / position['entry_price1']
            pnl2 = (exit_price2 - position['entry_price2']) / position['entry_price2']
        else:
            pnl1 = (exit_price1 - position['entry_price1']) / position['entry_price1']
            pnl2 = (position['entry_price2'] - exit_price2) / position['entry_price2']
        
        avg_pnl = (pnl1 + pnl2) / 2
        profit = position['position_size'] * avg_pnl
        
        self.capital += position['position_size'] + profit
        
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
        
        self.update_stats(profit)
    
    def close_trend_position(self, position, exit_price, timestamp):
        """平仓趋势跟踪交易"""
        if position['action'] == 'buy':
            pnl = (exit_price - position['entry_price']) / position['entry_price']
        else:
            pnl = (position['entry_price'] - exit_price) / position['entry_price']
        
        profit = position['position_size'] * pnl
        
        self.capital += position['position_size'] + profit
        
        trade = {
            'strategy': 'trend_following',
            'asset': position['asset'],
            'action': position['action'],
            'entry_time': position['entry_time'],
            'exit_time': timestamp,
            'entry_price': position['entry_price'],
            'exit_price': exit_price,
            'pnl': pnl,
            'profit': profit,
            'position_size': position['position_size']
        }
        
        self.trade_log.append(trade)
        position['status'] = 'closed'
        
        self.update_stats(profit)
    
    def update_stats(self, profit):
        """更新统计"""
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
        
        # 更新最大回撤
        if self.capital > self.stats['peak_capital']:
            self.stats['peak_capital'] = self.capital
        
        drawdown = (self.stats['peak_capital'] - self.capital) / self.stats['peak_capital']
        self.stats['max_drawdown'] = max(self.stats['max_drawdown'], drawdown)
    
    def run_backtest(self):
        """运行回测"""
        print("\n" + "=" * 80)
        print("开始回测（高级版 v12.0）")
        print("=" * 80)
        
        data = self.load_market_data()
        
        if not data:
            print("✗ 无可用数据")
            return
        
        if 'crypto' not in data:
            print("✗ 缺少加密货币数据")
            return
        
        # 获取时间戳
        timestamps = []
        for symbol, info in data['crypto'].items():
            for kline in info['data']:
                timestamps.append(kline['timestamp'])
        
        timestamps = sorted(set(timestamps))
        print(f"\n回测时间范围: {len(timestamps)} 个时间点")
        
        # 价格历史（用于趋势跟踪）
        price_history = {}
        
        # 逐时间点回测
        for i, timestamp in enumerate(timestamps):
            # 配对交易信号
            pairs_signals = self.check_pairs_trading_signal(data, timestamp)
            for signal in pairs_signals:
                self.execute_pairs_trade(signal)
            
            # 趋势跟踪信号
            trend_signals = self.check_trend_following_signal(data, timestamp, price_history)
            for signal in trend_signals:
                self.execute_trend_trade(signal)
            
            # 跨市场套利信号
            cross_signals = self.check_cross_market_signal(data, timestamp)
            for signal in cross_signals:
                self.execute_cross_market_trade(signal)
            
            # 检查平仓
            self.check_exit_signals(data, timestamp)
            
            if (i + 1) % 100 == 0:
                print(f"  进度: {i+1}/{len(timestamps)} ({(i+1)/len(timestamps)*100:.1f}%)")
        
        # 强制平仓所有未平仓持仓
        print("\n强制平仓所有未平仓持仓...")
        self.force_close_all_positions(data, timestamps[-1])
        
        # 输出结果
        self.print_results()
        
        # 保存交易记录
        self.save_trades()
    
    def force_close_all_positions(self, data, timestamp):
        """强制平仓所有未平仓持仓"""
        for position in self.positions:
            if position['status'] != 'open':
                continue
            
            if position['strategy'] == 'pairs_trading':
                asset1, asset2 = position['pair']
                is_crypto = position.get('is_crypto', 'USDT' in asset1)
                
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
                
                if price1 and price2:
                    self.close_pairs_position(position, price1, price2, timestamp)
            
            elif position['strategy'] == 'trend_following':
                if 'crypto' not in data:
                    continue
                
                current_price = None
                for symbol, info in data['crypto'].items():
                    if symbol == position['asset']:
                        for kline in info['data']:
                            if kline['timestamp'] == timestamp:
                                current_price = float(kline['close'])
                                break
                
                if current_price:
                    self.close_trend_position(position, current_price, timestamp)
    
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
        print(f"最大回撤: {self.stats['max_drawdown']:.2%}")
        print(f"\n总交易: {self.stats['total_trades']} 笔")
        print(f"胜率: {win_rate:.1%} ({self.stats['wins']} 胜 {self.stats['losses']} 负)")
        print(f"最大连续亏损: {self.stats['max_consecutive_losses']} 笔")
        
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
            avg_profit = stats['profit'] / stats['trades'] if stats['trades'] > 0 else 0
            print(f"{strategy:20s}: {stats['trades']:3d} 笔, 胜率 {win_rate:.1%}, 收益 ${stats['profit']:+,.2f}, 平均 ${avg_profit:+.2f}")
    
    def save_trades(self):
        """保存交易记录"""
        output_file = self.base_dir / "data" / "backtest_v12_trades.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.trade_log, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 交易记录已保存到: {output_file}")

if __name__ == "__main__":
    system = AdvancedBacktestSystem()
    system.run_backtest()
