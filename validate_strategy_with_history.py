#!/usr/bin/env python3
"""
使用历史数据验证策略并生成新的交易信号
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

class StrategyValidator:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data" / "historical"
        
        # 配对交易参数（从回测中验证的最优参数）
        self.pairs = [
            ('BTC-USDT', 'ETH-USDT', 0.912),
            ('ETH-USDT', 'SOL-USDT', 0.882),
            ('BTC-USDT', 'SOL-USDT', 0.867),
            ('BTC-USDT', 'BNB-USDT', 0.867),
            ('ETH-USDT', 'BNB-USDT', 0.857),
            ('SOL-USDT', 'BNB-USDT', 0.839),
            ('gold', 'silver', 0.843),
            ('oil_wti', 'oil_brent', 0.859),
        ]
        
        self.pair_spreads = {}
        self.entry_zscore = 1.2
        self.exit_zscore = 0.5
        
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
    
    def scan_for_signals(self, data):
        """扫描历史数据，生成交易信号"""
        print("\n扫描交易信号...")
        
        # 获取时间戳
        timestamps = []
        for symbol, info in data['crypto'].items():
            for kline in info['data']:
                timestamps.append(kline['timestamp'])
        
        timestamps = sorted(set(timestamps))
        
        # 只分析最后 200 个时间点（最近的数据）
        recent_timestamps = timestamps[-200:]
        
        signals = []
        
        for timestamp in recent_timestamps:
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
                
                if zscore > self.entry_zscore:
                    signals.append({
                        'timestamp': timestamp,
                        'pair': (asset1, asset2),
                        'action': 'short_long',
                        'price1': price1,
                        'price2': price2,
                        'zscore': zscore,
                        'correlation': correlation,
                        'is_crypto': is_crypto
                    })
                elif zscore < -self.entry_zscore:
                    signals.append({
                        'timestamp': timestamp,
                        'pair': (asset1, asset2),
                        'action': 'long_short',
                        'price1': price1,
                        'price2': price2,
                        'zscore': zscore,
                        'correlation': correlation,
                        'is_crypto': is_crypto
                    })
        
        return signals
    
    def analyze_signals(self, signals):
        """分析信号质量"""
        print(f"\n发现 {len(signals)} 个交易信号")
        
        if not signals:
            print("  ✗ 没有发现交易信号")
            return
        
        # 按配对统计
        from collections import defaultdict
        pair_stats = defaultdict(lambda: {'count': 0, 'avg_zscore': []})
        
        for signal in signals:
            pair_key = f"{signal['pair'][0]} / {signal['pair'][1]}"
            pair_stats[pair_key]['count'] += 1
            pair_stats[pair_key]['avg_zscore'].append(abs(signal['zscore']))
        
        print("\n按配对统计:")
        for pair, stats in sorted(pair_stats.items(), key=lambda x: x[1]['count'], reverse=True):
            avg_z = np.mean(stats['avg_zscore'])
            print(f"  {pair:30s}: {stats['count']:3d} 个信号, 平均 Z-Score {avg_z:.2f}")
        
        # 最新信号
        latest_signals = sorted(signals, key=lambda x: x['timestamp'], reverse=True)[:10]
        
        print(f"\n最新 10 个信号:")
        for i, signal in enumerate(latest_signals, 1):
            action_str = "做空/做多" if signal['action'] == 'short_long' else "做多/做空"
            print(f"  {i}. {signal['timestamp']}")
            print(f"     配对: {signal['pair'][0]} / {signal['pair'][1]}")
            print(f"     操作: {action_str}")
            print(f"     价格: ${signal['price1']:.2f} / ${signal['price2']:.2f}")
            print(f"     Z-Score: {signal['zscore']:.2f}")
            print(f"     相关性: {signal['correlation']:.3f}")
            print()
    
    def save_signals(self, signals):
        """保存信号到文件"""
        output_file = self.base_dir / "data" / "validated_signals.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(signals, f, indent=2, ensure_ascii=False)
        
        print(f"✓ 信号已保存到: {output_file}")
    
    def run(self):
        """运行验证"""
        print("=" * 80)
        print("策略验证 - 使用历史数据生成新交易信号")
        print("=" * 80)
        
        data = self.load_market_data()
        
        if not data:
            print("✗ 无可用数据")
            return
        
        signals = self.scan_for_signals(data)
        self.analyze_signals(signals)
        
        if signals:
            self.save_signals(signals)

if __name__ == "__main__":
    validator = StrategyValidator()
    validator.run()
