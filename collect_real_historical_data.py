#!/usr/bin/env python3
"""
采集真实历史数据 - 所有市场
- 加密货币：OKX API（BTC、ETH、SOL、BNB）
- 美股：Yahoo Finance API（ARKK、CRSP、TSLA）
- A股：东方财富/新浪财经 API（中科曙光、新讯达、绿盟科技、九安医疗）
- Polymarket：Polymarket API
"""

import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

def collect_okx_klines(symbol, start_date, end_date):
    """采集 OKX K线数据（1小时）"""
    print(f"\n📊 采集 OKX {symbol} K线数据...")
    
    url = "https://www.okx.com/api/v5/market/history-candles"
    
    # 转换为时间戳（毫秒）
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
    
    all_data = []
    current_ts = end_ts
    max_requests = 15  # 限制请求次数（15次 × 100条 = 1500条，足够2个月）
    request_count = 0
    
    while current_ts > start_ts and request_count < max_requests:
        params = {
            'instId': f'{symbol}-USDT',
            'bar': '1H',
            'before': current_ts,
            'limit': 100
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result['code'] != '0':
                print(f"  ❌ API 错误: {result['msg']}")
                break
            
            data = result['data']
            if not data:
                break
            
            all_data.extend(data)
            current_ts = int(data[-1][0])
            request_count += 1
            
            if request_count % 5 == 0:
                print(f"  ✅ 已采集 {len(all_data)} 条")
            
            time.sleep(0.1)  # 减少延迟
            
        except Exception as e:
            print(f"  ❌ 请求失败: {e}")
            break
    
    print(f"  ✅ 完成采集 {len(all_data)} 条")
    
    # 转换格式
    formatted_data = []
    for item in reversed(all_data):
        formatted_data.append({
            'timestamp': datetime.fromtimestamp(int(item[0]) / 1000).isoformat(),
            'open': float(item[1]),
            'high': float(item[2]),
            'low': float(item[3]),
            'close': float(item[4]),
            'volume': float(item[5])
        })
    
    return formatted_data

def collect_yahoo_finance(symbol, start_date, end_date):
    """采集 Yahoo Finance 美股数据（1小时）"""
    print(f"\n📊 采集 Yahoo Finance {symbol} 数据...")
    
    # Yahoo Finance API v8
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol
    
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
    
    params = {
        'period1': start_ts,
        'period2': end_ts,
        'interval': '1h',
        'includePrePost': 'false'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        chart = result['chart']['result'][0]
        timestamps = chart['timestamp']
        quotes = chart['indicators']['quote'][0]
        
        formatted_data = []
        for i, ts in enumerate(timestamps):
            formatted_data.append({
                'timestamp': datetime.fromtimestamp(ts).isoformat(),
                'open': quotes['open'][i],
                'high': quotes['high'][i],
                'low': quotes['low'][i],
                'close': quotes['close'][i],
                'volume': quotes['volume'][i]
            })
        
        print(f"  ✅ 已采集 {len(formatted_data)} 条")
        return formatted_data
        
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return []

def collect_cn_stock_sina(symbol, code, start_date, end_date):
    """采集新浪财经 A股数据（日线，转换为小时线）"""
    print(f"\n📊 采集新浪财经 {symbol}({code}) 数据...")
    
    # 新浪财经 API
    url = f"https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData"
    
    params = {
        'symbol': code,
        'scale': 60,  # 60分钟
        'datalen': 1440  # 最多1440条
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # 解析 JSONP
        text = response.text
        start = text.find('[')
        end = text.rfind(']') + 1
        data = json.loads(text[start:end])
        
        formatted_data = []
        for item in data:
            formatted_data.append({
                'timestamp': item['day'],
                'open': float(item['open']),
                'high': float(item['high']),
                'low': float(item['low']),
                'close': float(item['close']),
                'volume': float(item['volume'])
            })
        
        print(f"  ✅ 已采集 {len(formatted_data)} 条")
        return formatted_data
        
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return []

def main():
    print("="*80)
    print("采集真实历史数据")
    print("="*80)
    
    data_dir = Path('/opt/data/polymarket_arbitrage/data/historical')
    data_dir.mkdir(parents=True, exist_ok=True)
    
    start_date = "2026-03-01"
    end_date = "2026-04-30"
    
    # 1. 采集加密货币数据（OKX）
    print("\n" + "="*80)
    print("1. 采集加密货币数据（OKX）")
    print("="*80)
    
    crypto_symbols = ['BTC', 'ETH', 'SOL', 'BNB']
    
    for symbol in crypto_symbols:
        data = collect_okx_klines(symbol, start_date, end_date)
        if data:
            # 保存 3月数据
            march_data = [d for d in data if d['timestamp'].startswith('2026-03')]
            if march_data:
                filename = data_dir / f'okx_{symbol}_USDT_klines_march_2026.json'
                with open(filename, 'w') as f:
                    json.dump(march_data, f, indent=2)
                print(f"  💾 已保存 3月数据: {filename} ({len(march_data)} 条)")
            
            # 保存 4月数据
            april_data = [d for d in data if d['timestamp'].startswith('2026-04')]
            if april_data:
                filename = data_dir / f'okx_{symbol}_USDT_klines_april_2026.json'
                with open(filename, 'w') as f:
                    json.dump(april_data, f, indent=2)
                print(f"  💾 已保存 4月数据: {filename} ({len(april_data)} 条)")
        
        time.sleep(1)
    
    # 2. 采集美股数据（Yahoo Finance）
    print("\n" + "="*80)
    print("2. 采集美股数据（Yahoo Finance）")
    print("="*80)
    
    us_stocks = {
        'ARKK': 'ARKK',
        'CRSP': 'CRSP',
        'TSLA': 'TSLA'
    }
    
    us_data = {}
    for name, ticker in us_stocks.items():
        data = collect_yahoo_finance(ticker, start_date, end_date)
        if data:
            us_data[name] = data
        time.sleep(1)
    
    if us_data:
        filename = data_dir / 'us_stocks_march_2026.json'
        with open(filename, 'w') as f:
            json.dump(us_data, f, indent=2)
        print(f"\n💾 已保存美股数据: {filename}")
        for name, data in us_data.items():
            print(f"  - {name}: {len(data)} 条")
    
    # 3. 采集 A股数据（新浪财经）
    print("\n" + "="*80)
    print("3. 采集 A股数据（新浪财经）")
    print("="*80)
    
    cn_stocks = {
        '中科曙光': 'sh603019',
        '新讯达': 'sz300252',
        '绿盟科技': 'sz300369',
        '九安医疗': 'sz002432'
    }
    
    cn_data = {}
    for name, code in cn_stocks.items():
        data = collect_cn_stock_sina(name, code, start_date, end_date)
        if data:
            cn_data[name] = data
        time.sleep(1)
    
    if cn_data:
        filename = data_dir / 'cn_stocks_march_2026.json'
        with open(filename, 'w') as f:
            json.dump(cn_data, f, indent=2)
        print(f"\n💾 已保存 A股数据: {filename}")
        for name, data in cn_data.items():
            print(f"  - {name}: {len(data)} 条")
    
    print("\n" + "="*80)
    print("✅ 数据采集完成")
    print("="*80)

if __name__ == '__main__':
    main()
