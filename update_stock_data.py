#!/usr/bin/env python3
"""
更新股票数据 - 替换为新的选股
美股：ARKK（ARK 创新 ETF）、CRSP（Crispr）、TSLA（特斯拉）
A股：中科曙光(603019)、新讯达(300252)、绿盟科技(300369)、九安医疗(002432)
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

def generate_stock_data(symbol, base_price, volatility, num_hours=1440):
    """生成股票历史数据"""
    data = []
    current_price = base_price
    start_time = datetime(2026, 3, 1, 0, 0, 0)
    
    for i in range(num_hours):
        timestamp = start_time + timedelta(hours=i)
        
        # 随机波动
        change = random.uniform(-volatility, volatility)
        current_price = current_price * (1 + change)
        
        # 偶尔制造极端行情（暴跌/暴涨）
        if random.random() < 0.02:  # 2% 概率
            extreme_change = random.uniform(-0.15, 0.15)  # ±15%
            current_price = current_price * (1 + extreme_change)
        
        high = current_price * (1 + random.uniform(0, 0.01))
        low = current_price * (1 - random.uniform(0, 0.01))
        open_price = data[-1]['close'] if data else current_price
        
        data.append({
            'timestamp': timestamp.isoformat(),
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(current_price, 2),
            'volume': random.randint(1000000, 10000000)
        })
    
    return data

def main():
    print("🔄 更新股票数据...")
    
    # 美股配置
    us_stocks = {
        'ARKK': {'base_price': 45.0, 'volatility': 0.03},   # ARK 创新 ETF
        'CRSP': {'base_price': 65.0, 'volatility': 0.04},   # Crispr（生物科技）
        'TSLA': {'base_price': 180.0, 'volatility': 0.035}, # 特斯拉
    }
    
    # A股配置（人民币价格，需要转换为美元）
    cn_stocks = {
        '中科曙光': {'base_price': 35.0, 'volatility': 0.04},   # 603019
        '新讯达': {'base_price': 18.0, 'volatility': 0.045},    # 300252
        '绿盟科技': {'base_price': 12.0, 'volatility': 0.04},   # 300369
        '九安医疗': {'base_price': 8.5, 'volatility': 0.05},    # 002432
    }
    
    # 生成美股数据
    print("\n📊 生成美股数据...")
    us_data = {}
    for symbol, config in us_stocks.items():
        print(f"  - {symbol}: 基准价 ${config['base_price']}, 波动率 {config['volatility']*100:.1f}%")
        us_data[symbol] = generate_stock_data(
            symbol, 
            config['base_price'], 
            config['volatility']
        )
    
    # 生成 A股数据
    print("\n📊 生成 A股数据...")
    cn_data = {}
    for symbol, config in cn_stocks.items():
        print(f"  - {symbol}: 基准价 ¥{config['base_price']}, 波动率 {config['volatility']*100:.1f}%")
        cn_data[symbol] = generate_stock_data(
            symbol, 
            config['base_price'], 
            config['volatility']
        )
    
    # 保存数据
    data_dir = Path('/opt/data/polymarket_arbitrage/data/historical')
    
    us_file = data_dir / 'us_stocks_march_2026.json'
    with open(us_file, 'w') as f:
        json.dump(us_data, f, indent=2)
    print(f"\n✅ 美股数据已保存: {us_file}")
    print(f"   股票数量: {len(us_data)}")
    print(f"   数据点数: {len(us_data['ARKK'])} 小时")
    
    cn_file = data_dir / 'cn_stocks_march_2026.json'
    with open(cn_file, 'w') as f:
        json.dump(cn_data, f, indent=2)
    print(f"\n✅ A股数据已保存: {cn_file}")
    print(f"   股票数量: {len(cn_data)}")
    print(f"   数据点数: {len(cn_data['中科曙光'])} 小时")
    
    # 统计信息
    print("\n" + "="*80)
    print("数据统计")
    print("="*80)
    
    print("\n美股:")
    for symbol in us_data.keys():
        prices = [d['close'] for d in us_data[symbol]]
        print(f"  {symbol}: ${min(prices):.2f} - ${max(prices):.2f}")
    
    print("\nA股:")
    for symbol in cn_data.keys():
        prices = [d['close'] for d in cn_data[symbol]]
        print(f"  {symbol}: ¥{min(prices):.2f} - ¥{max(prices):.2f}")

if __name__ == '__main__':
    main()
