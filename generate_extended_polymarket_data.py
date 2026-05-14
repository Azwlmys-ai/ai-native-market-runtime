#!/usr/bin/env python3
"""
生成更多 Polymarket 市场数据用于回测
包含体育、政治、经济、加密货币等多个类别
"""

import json
import random
from datetime import datetime, timedelta

# 生成时间序列（2026年3-4月，每小时一个数据点）
start_date = datetime(2026, 3, 1)
hours = 1440  # 60天 * 24小时

# 定义更多 Polymarket 市场
markets = [
    # 加密货币价格预测（已有）
    {
        'id': 'btc_100k_april',
        'question': 'Will Bitcoin hit $100k by April 30, 2026?',
        'category': 'crypto',
        'initial_price': 0.35,
        'volatility': 0.15,
        'trend': 0.0005,  # 上涨趋势
        'anchor': 'BTC',
        'anchor_threshold': 100000,
        'direction': 'above'
    },
    {
        'id': 'btc_50k_march',
        'question': 'Will Bitcoin drop below $50k in March 2026?',
        'category': 'crypto',
        'initial_price': 0.15,
        'volatility': 0.12,
        'trend': -0.0003,  # 下跌趋势
        'anchor': 'BTC',
        'anchor_threshold': 50000,
        'direction': 'below'
    },
    {
        'id': 'eth_5k_april',
        'question': 'Will Ethereum hit $5k by April 30, 2026?',
        'category': 'crypto',
        'initial_price': 0.42,
        'volatility': 0.18,
        'trend': 0.0004,
        'anchor': 'ETH',
        'anchor_threshold': 5000,
        'direction': 'above'
    },
    {
        'id': 'sol_200_april',
        'question': 'Will Solana hit $200 by April 30, 2026?',
        'category': 'crypto',
        'initial_price': 0.38,
        'volatility': 0.20,
        'trend': 0.0003,
        'anchor': 'SOL',
        'anchor_threshold': 200,
        'direction': 'above'
    },
    
    # 美股相关
    {
        'id': 'coin_300_april',
        'question': 'Will Coinbase stock hit $300 by April 30, 2026?',
        'category': 'stocks',
        'initial_price': 0.25,
        'volatility': 0.16,
        'trend': 0.0004,
        'anchor': 'COIN',
        'anchor_threshold': 300,
        'direction': 'above'
    },
    {
        'id': 'msft_500_april',
        'question': 'Will Microsoft hit $500 by April 30, 2026?',
        'category': 'stocks',
        'initial_price': 0.55,
        'volatility': 0.10,
        'trend': 0.0002,
        'anchor': 'MSFT',
        'anchor_threshold': 500,
        'direction': 'above'
    },
    
    # 体育赛事（固定概率，不受价格影响）
    {
        'id': 'nba_lakers_champion',
        'question': 'Will Lakers win NBA Championship 2026?',
        'category': 'sports',
        'initial_price': 0.18,
        'volatility': 0.08,
        'trend': 0.0001,
        'anchor': None,
        'anchor_threshold': None,
        'direction': None
    },
    {
        'id': 'nhl_bruins_playoffs',
        'question': 'Will Bruins make NHL Playoffs 2026?',
        'category': 'sports',
        'initial_price': 0.72,
        'volatility': 0.06,
        'trend': -0.0001,
        'anchor': None,
        'anchor_threshold': None,
        'direction': None
    },
    
    # 政治事件（固定概率）
    {
        'id': 'us_gdp_growth_q1',
        'question': 'Will US GDP grow >3% in Q1 2026?',
        'category': 'economy',
        'initial_price': 0.48,
        'volatility': 0.12,
        'trend': 0.0002,
        'anchor': None,
        'anchor_threshold': None,
        'direction': None
    },
    {
        'id': 'fed_rate_cut_april',
        'question': 'Will Fed cut rates in April 2026?',
        'category': 'economy',
        'initial_price': 0.35,
        'volatility': 0.15,
        'trend': 0.0003,
        'anchor': None,
        'anchor_threshold': None,
        'direction': None
    },
    
    # 科技事件
    {
        'id': 'gta_vi_release_2026',
        'question': 'Will GTA VI release in 2026?',
        'category': 'tech',
        'initial_price': 0.62,
        'volatility': 0.10,
        'trend': -0.0002,
        'anchor': None,
        'anchor_threshold': None,
        'direction': None
    },
    {
        'id': 'apple_vision_pro_sales',
        'question': 'Will Apple Vision Pro sell >5M units in 2026?',
        'category': 'tech',
        'initial_price': 0.28,
        'volatility': 0.14,
        'trend': 0.0001,
        'anchor': None,
        'anchor_threshold': None,
        'direction': None
    },
]

print(f"生成 {len(markets)} 个 Polymarket 市场数据...")

# 加载加密货币和股票数据（用于锚定）
with open('/opt/data/polymarket_arbitrage/data/historical/okx_BTC_USDT_klines_march_2026.json', 'r') as f:
    btc_march = json.load(f)
with open('/opt/data/polymarket_arbitrage/data/historical/okx_BTC_USDT_klines_april_2026.json', 'r') as f:
    btc_april = json.load(f)
btc_data = btc_march + btc_april

with open('/opt/data/polymarket_arbitrage/data/historical/okx_ETH_USDT_klines_march_2026.json', 'r') as f:
    eth_march = json.load(f)
with open('/opt/data/polymarket_arbitrage/data/historical/okx_ETH_USDT_klines_april_2026.json', 'r') as f:
    eth_april = json.load(f)
eth_data = eth_march + eth_april

with open('/opt/data/polymarket_arbitrage/data/historical/okx_SOL_USDT_klines_march_2026.json', 'r') as f:
    sol_march = json.load(f)
with open('/opt/data/polymarket_arbitrage/data/historical/okx_SOL_USDT_klines_april_2026.json', 'r') as f:
    sol_april = json.load(f)
sol_data = sol_march + sol_april

with open('/opt/data/polymarket_arbitrage/data/historical/us_stocks_march_2026.json', 'r') as f:
    us_stocks_data = json.load(f)
coin_data = us_stocks_data.get('COIN', [])
msft_data = us_stocks_data.get('MSFT', [])

anchor_data = {
    'BTC': btc_data,
    'ETH': eth_data,
    'SOL': sol_data,
    'COIN': coin_data,
    'MSFT': msft_data
}

# 生成每个市场的价格历史
for market in markets:
    print(f"  生成 {market['id']}...")
    
    price_history = []
    current_price = market['initial_price']
    
    for i in range(hours):
        timestamp = (start_date + timedelta(hours=i)).isoformat()
        
        # 如果有锚定资产，根据资产价格调整概率
        if market['anchor'] and market['anchor'] in anchor_data:
            anchor_list = anchor_data[market['anchor']]
            
            # 检查索引是否超出范围
            if i >= len(anchor_list):
                # 使用最后一个价格
                anchor_price = anchor_list[-1]['close']
            else:
                anchor_price = anchor_list[i]['close']
            
            threshold = market['anchor_threshold']
            
            if market['direction'] == 'above':
                # 价格越接近阈值，概率越高
                distance = (threshold - anchor_price) / anchor_price
                implied_prob = max(0.05, min(0.95, 1 - distance / 0.5))
            else:  # below
                # 价格越远离阈值，概率越低
                distance = (anchor_price - threshold) / anchor_price
                implied_prob = max(0.05, min(0.95, 1 - distance / 0.3))
            
            # 市场价格围绕隐含概率波动，但有偏差
            target_price = implied_prob + random.uniform(-0.15, 0.15)
        else:
            # 无锚定资产，随机游走
            target_price = current_price + market['trend'] + random.gauss(0, market['volatility'])
        
        # 限制价格范围 [0.01, 0.99]
        current_price = max(0.01, min(0.99, target_price))
        
        price_history.append({
            'timestamp': timestamp,
            'price': round(current_price, 4)
        })
    
    market['price_history'] = price_history

# 保存数据
output_file = '/opt/data/polymarket_arbitrage/data/historical/polymarket_markets_extended_march_april_2026.json'
with open(output_file, 'w') as f:
    json.dump(markets, f, indent=2)

print(f"\n✅ 已生成 {len(markets)} 个市场，每个市场 {hours} 小时数据")
print(f"保存至: {output_file}")

# 统计
print(f"\n市场分类:")
categories = {}
for m in markets:
    cat = m['category']
    categories[cat] = categories.get(cat, 0) + 1

for cat, count in sorted(categories.items()):
    print(f"  {cat}: {count} 个市场")
