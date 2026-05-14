#!/usr/bin/env python3
import json
from pathlib import Path

# 加载数据
with open('data/historical/polymarket_markets_march_april_2026.json', 'r') as f:
    pm_data = json.load(f)

with open('data/historical/okx_BTC_USDT_klines_march_2026.json', 'r') as f:
    btc_data = json.load(f)

# 检查 BTC 价格范围
btc_prices = [k['close'] for k in btc_data]
print(f'BTC 价格范围: ${min(btc_prices):.0f} - ${max(btc_prices):.0f}')

# 检查 Polymarket BTC 市场
for market in pm_data:
    if 'bitcoin' in market['question'].lower() or 'btc' in market['question'].lower():
        print(f"\n市场: {market['question']}")
        print(f"  初始价格: {market['initial_price']:.2f}")
        print(f"  当前价格: {market['current_price']:.2f}")
        
        # 检查是否有 100k 目标
        if '100k' in market['question'] or '$100k' in market['question']:
            print(f"  目标: $100k")
            print(f"  BTC 最高价: ${max(btc_prices):.0f}")
            print(f"  距离目标: {(100000 - max(btc_prices)) / max(btc_prices) * 100:.1f}%")
            print(f"  PM 价格: {market['current_price']:.2f}")
            
            # 检查是否满足触发条件
            if (100000 - max(btc_prices)) / max(btc_prices) < 0.10:
                print(f"  ✅ 距离 < 10%，应该触发")
            else:
                print(f"  ❌ 距离 > 10%，不触发")
