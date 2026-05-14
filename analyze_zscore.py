#!/usr/bin/env python3
"""
分析配对价差 Z-Score 分布
找出为什么信号触发这么少
"""

import json
import numpy as np
from pathlib import Path
from collections import defaultdict

def analyze_zscore_distribution():
    data_dir = Path("/opt/data/polymarket_arbitrage/data/historical")
    
    # 加载数据
    with open(data_dir / "okx_klines_march_april_2026.json", 'r') as f:
        crypto = json.load(f)
    
    with open(data_dir / "commodities_march_april_2026.json", 'r') as f:
        commodities = json.load(f)
    
    # 配对列表
    pairs = [
        ('BTC-USDT', 'ETH-USDT', 'crypto'),
        ('ETH-USDT', 'SOL-USDT', 'crypto'),
        ('BTC-USDT', 'SOL-USDT', 'crypto'),
        ('gold', 'silver', 'commodity'),
        ('oil_wti', 'oil_brent', 'commodity'),
    ]
    
    print("=" * 80)
    print("配对价差 Z-Score 分析")
    print("=" * 80)
    
    for asset1, asset2, market_type in pairs:
        print(f"\n【{asset1} / {asset2}】")
        
        # 提取价格序列
        prices1 = []
        prices2 = []
        
        if market_type == 'crypto':
            data_source = crypto
            for d in data_source[asset1]['data']:
                ts = d['timestamp']
                price1 = float(d['close'])
                
                # 找到对应时间戳的 asset2 价格
                for d2 in data_source[asset2]['data']:
                    if d2['timestamp'] == ts:
                        price2 = float(d2['close'])
                        prices1.append(price1)
                        prices2.append(price2)
                        break
        else:
            data_source = commodities
            for d in data_source[asset1]['data']:
                if not d['close']:
                    continue
                ts = d['timestamp']
                price1 = float(d['close'])
                
                for d2 in data_source[asset2]['data']:
                    if d2['timestamp'] == ts and d2['close']:
                        price2 = float(d2['close'])
                        prices1.append(price1)
                        prices2.append(price2)
                        break
        
        if len(prices1) < 100:
            print(f"  数据点不足: {len(prices1)}")
            continue
        
        # 计算价差（比率）
        spreads = [p1 / p2 for p1, p2 in zip(prices1, prices2)]
        
        # 计算 Z-Score
        zscores = []
        for i in range(100, len(spreads)):
            window = spreads[i-100:i]
            mean = np.mean(window)
            std = np.std(window)
            if std > 0:
                zscore = (spreads[i] - mean) / std
                zscores.append(zscore)
        
        if not zscores:
            print(f"  无法计算 Z-Score")
            continue
        
        # 统计
        zscores = np.array(zscores)
        print(f"  数据点: {len(zscores)}")
        print(f"  Z-Score 范围: [{zscores.min():.2f}, {zscores.max():.2f}]")
        print(f"  Z-Score 均值: {zscores.mean():.2f}")
        print(f"  Z-Score 标准差: {zscores.std():.2f}")
        
        # 触发统计
        trigger_15 = np.sum(np.abs(zscores) > 1.5)
        trigger_20 = np.sum(np.abs(zscores) > 2.0)
        trigger_10 = np.sum(np.abs(zscores) > 1.0)
        
        print(f"  触发次数 (|Z| > 1.0): {trigger_10} ({trigger_10/len(zscores)*100:.1f}%)")
        print(f"  触发次数 (|Z| > 1.5): {trigger_15} ({trigger_15/len(zscores)*100:.1f}%)")
        print(f"  触发次数 (|Z| > 2.0): {trigger_20} ({trigger_20/len(zscores)*100:.1f}%)")

if __name__ == "__main__":
    analyze_zscore_distribution()
