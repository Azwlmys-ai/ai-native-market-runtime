#!/usr/bin/env python3
"""
采集美股真实历史数据
使用 Polygon.io 和 Finnhub API
"""

import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

# 读取配置
CONFIG_PATH = Path('/opt/data/polymarket_arbitrage/config/broker_config.json')

def load_api_keys():
    """加载 API Keys"""
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    
    polygon_key = config['brokers']['polygon']['api_key']
    finnhub_key = config['brokers']['finnhub']['api_key']
    
    return polygon_key, finnhub_key

def collect_polygon_historical(symbol, start_date, end_date, api_key):
    """采集 Polygon 历史数据（聚合K线）"""
    print(f"\n📊 采集 Polygon {symbol} 历史数据...")
    
    # Polygon API: 聚合K线
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/hour/{start_date}/{end_date}"
    
    params = {
        'adjusted': 'true',
        'sort': 'asc',
        'limit': 50000,
        'apiKey': api_key
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if result.get('status') != 'OK':
            print(f"  ❌ API 错误: {result.get('error', 'Unknown error')}")
            return []
        
        results = result.get('results', [])
        
        formatted_data = []
        for item in results:
            formatted_data.append({
                'timestamp': datetime.fromtimestamp(item['t'] / 1000).isoformat(),
                'open': item['o'],
                'high': item['h'],
                'low': item['l'],
                'close': item['c'],
                'volume': item['v']
            })
        
        print(f"  ✅ 已采集 {len(formatted_data)} 条")
        return formatted_data
        
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return []

def collect_finnhub_candles(symbol, start_date, end_date, api_key):
    """采集 Finnhub 历史K线数据"""
    print(f"\n📊 采集 Finnhub {symbol} 历史数据...")
    
    # Finnhub API: 股票K线
    url = "https://finnhub.io/api/v1/stock/candle"
    
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
    
    params = {
        'symbol': symbol,
        'resolution': '60',  # 60分钟
        'from': start_ts,
        'to': end_ts,
        'token': api_key
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if result.get('s') != 'ok':
            print(f"  ❌ API 错误: {result.get('s', 'Unknown error')}")
            return []
        
        timestamps = result.get('t', [])
        opens = result.get('o', [])
        highs = result.get('h', [])
        lows = result.get('l', [])
        closes = result.get('c', [])
        volumes = result.get('v', [])
        
        formatted_data = []
        for i in range(len(timestamps)):
            formatted_data.append({
                'timestamp': datetime.fromtimestamp(timestamps[i]).isoformat(),
                'open': opens[i],
                'high': highs[i],
                'low': lows[i],
                'close': closes[i],
                'volume': volumes[i]
            })
        
        print(f"  ✅ 已采集 {len(formatted_data)} 条")
        return formatted_data
        
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return []

def main():
    print("="*80)
    print("采集美股真实历史数据")
    print("="*80)
    
    # 加载 API Keys
    polygon_key, finnhub_key = load_api_keys()
    print(f"\n✅ Polygon API Key: {polygon_key[:10]}...")
    print(f"✅ Finnhub API Key: {finnhub_key[:10]}...")
    
    data_dir = Path('/opt/data/polymarket_arbitrage/data/historical')
    data_dir.mkdir(parents=True, exist_ok=True)
    
    start_date = "2026-03-01"
    end_date = "2026-04-30"
    
    # 美股列表
    us_stocks = {
        'ARKK': 'ARKK',
        'CRSP': 'CRSP',
        'TSLA': 'TSLA'
    }
    
    us_data = {}
    
    # 优先使用 Polygon（更稳定）
    print("\n" + "="*80)
    print("使用 Polygon API 采集数据")
    print("="*80)
    
    for name, ticker in us_stocks.items():
        data = collect_polygon_historical(ticker, start_date, end_date, polygon_key)
        
        if data:
            us_data[name] = data
        else:
            print(f"  ⚠️ Polygon 失败，尝试 Finnhub...")
            time.sleep(2)
            
            # Fallback 到 Finnhub
            data = collect_finnhub_candles(ticker, start_date, end_date, finnhub_key)
            if data:
                us_data[name] = data
        
        time.sleep(12)  # Polygon 免费版限制: 5 次/分钟
    
    # 保存数据
    if us_data:
        filename = data_dir / 'us_stocks_march_2026.json'
        with open(filename, 'w') as f:
            json.dump(us_data, f, indent=2)
        
        print("\n" + "="*80)
        print(f"✅ 已保存美股数据: {filename}")
        print("="*80)
        
        for name, data in us_data.items():
            if data:
                prices = [d['close'] for d in data]
                print(f"  {name}: {len(data)} 条, ${min(prices):.2f} - ${max(prices):.2f}")
    else:
        print("\n❌ 未采集到任何数据")

if __name__ == '__main__':
    main()
