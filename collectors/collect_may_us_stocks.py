#!/usr/bin/env python3
"""
采集 5 月份美股历史数据（Finnhub API）
"""

import json
import requests
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "historical"
CONFIG_PATH = BASE_DIR / "config" / "broker_config.json"

# 加载配置
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

# 时间范围：5月1日 - 5月6日
START_DATE = "2026-05-01"
END_DATE = "2026-05-06"

US_STOCKS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "COIN", "TTWO", "MSTR"]

def collect_us_stocks():
    """采集美股 5 月数据"""
    print("\n📈 采集美股数据...")
    
    api_key = config['brokers']['finnhub']['api_key']
    
    start_ts = int(datetime.strptime(START_DATE, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(END_DATE, "%Y-%m-%d").timestamp())
    
    stocks_data = {}
    
    for symbol in US_STOCKS:
        url = f"https://finnhub.io/api/v1/stock/candle"
        params = {
            "symbol": symbol,
            "resolution": "60",  # 1小时 K 线
            "from": start_ts,
            "to": end_ts,
            "token": api_key
        }
        
        try:
            print(f"  采集 {symbol}...", end=" ")
            resp = requests.get(url, params=params, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                
                if data.get('s') == 'ok':
                    # 转换为标准格式
                    candles = []
                    for i in range(len(data['t'])):
                        candles.append({
                            'timestamp': datetime.fromtimestamp(data['t'][i]).isoformat(),
                            'open': data['o'][i],
                            'high': data['h'][i],
                            'low': data['l'][i],
                            'close': data['c'][i],
                            'volume': data['v'][i]
                        })
                    
                    stocks_data[symbol] = candles
                    print(f"✅ {len(candles)} 条数据")
                else:
                    print(f"⚠️ 无数据")
            else:
                print(f"❌ HTTP {resp.status_code}")
        
        except Exception as e:
            print(f"❌ {e}")
    
    # 保存
    output_file = DATA_DIR / "us_stocks_may_2026.json"
    with open(output_file, 'w') as f:
        json.dump(stocks_data, f, indent=2)
    
    print(f"\n✅ 美股数据已保存: {output_file}")
    print(f"   总计: {len(stocks_data)} 个股票")
    
    return stocks_data

if __name__ == "__main__":
    print("=" * 80)
    print("采集 5 月份美股历史数据")
    print(f"时间范围: {START_DATE} → {END_DATE}")
    print("=" * 80)
    
    collect_us_stocks()
    
    print("\n" + "=" * 80)
    print("✅ 采集完成")
    print("=" * 80)
