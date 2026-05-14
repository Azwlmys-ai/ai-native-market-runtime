#!/usr/bin/env python3
"""
采集 5 月份所有市场历史数据
- 美股（yfinance）
- A股（东方财富 API）
- 港股（yfinance）
- 汇率（exchangerate-api.com）
"""

import json
import requests
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta
import time

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "historical"

# 时间范围：5月1日 - 5月6日
START_DATE = "2026-05-01"
END_DATE = "2026-05-06"

# ============================================================================
# 1. 美股数据采集（yfinance）
# ============================================================================

US_STOCKS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "COIN", "TTWO", "MSTR"]

def collect_us_stocks():
    """采集美股 5 月数据"""
    print("\n📈 采集美股数据...")
    
    stocks_data = {}
    
    for symbol in US_STOCKS:
        try:
            print(f"  采集 {symbol}...", end=" ")
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=START_DATE, end=END_DATE, interval="1h")
            
            if not hist.empty:
                candles = []
                for idx, row in hist.iterrows():
                    candles.append({
                        'timestamp': idx.isoformat(),
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'close': float(row['Close']),
                        'volume': float(row['Volume'])
                    })
                
                stocks_data[symbol] = candles
                print(f"✅ {len(candles)} 条数据")
            else:
                print(f"⚠️ 无数据")
        
        except Exception as e:
            print(f"❌ {e}")
        
        time.sleep(0.5)
    
    # 保存
    output_file = DATA_DIR / "us_stocks_may_2026.json"
    with open(output_file, 'w') as f:
        json.dump(stocks_data, f, indent=2)
    
    print(f"✅ 美股数据已保存: {output_file}")
    print(f"   总计: {len(stocks_data)} 个股票")
    
    return stocks_data

# ============================================================================
# 2. A股数据采集（东方财富）
# ============================================================================

CN_STOCKS = ["000001", "600519", "000858", "601318"]  # 平安银行、茅台、五粮液、中国平安

def collect_cn_stocks():
    """采集 A 股 5 月数据"""
    print("\n📈 采集 A 股数据...")
    
    stocks_data = {}
    
    for code in CN_STOCKS:
        # 判断市场代码
        market = "1" if code.startswith("6") else "0"
        secid = f"{market}.{code}"
        
        url = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "klt": "60",  # 60分钟
            "fqt": "1",
            "beg": START_DATE.replace("-", ""),
            "end": END_DATE.replace("-", ""),
        }
        
        try:
            print(f"  采集 {code}...", end=" ")
            resp = requests.get(url, params=params, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                
                if data.get('data') and data['data'].get('klines'):
                    klines = data['data']['klines']
                    
                    candles = []
                    for k in klines:
                        parts = k.split(',')
                        candles.append({
                            'timestamp': parts[0],
                            'open': float(parts[1]),
                            'close': float(parts[2]),
                            'high': float(parts[3]),
                            'low': float(parts[4]),
                            'volume': float(parts[5])
                        })
                    
                    stocks_data[code] = candles
                    print(f"✅ {len(candles)} 条数据")
                else:
                    print(f"⚠️ 无数据（可能是假期）")
            else:
                print(f"❌ HTTP {resp.status_code}")
        
        except Exception as e:
            print(f"❌ {e}")
        
        time.sleep(0.5)
    
    # 保存
    output_file = DATA_DIR / "cn_stocks_may_2026.json"
    with open(output_file, 'w') as f:
        json.dump(stocks_data, f, indent=2)
    
    print(f"✅ A 股数据已保存: {output_file}")
    print(f"   总计: {len(stocks_data)} 个股票")
    
    return stocks_data

# ============================================================================
# 3. 港股数据采集（yfinance）
# ============================================================================

HK_STOCKS = ["0700.HK", "9988.HK", "0941.HK"]  # 腾讯、阿里、中国移动

def collect_hk_stocks():
    """采集港股 5 月数据"""
    print("\n📈 采集港股数据...")
    
    stocks_data = {}
    
    for symbol in HK_STOCKS:
        try:
            print(f"  采集 {symbol}...", end=" ")
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=START_DATE, end=END_DATE, interval="1h")
            
            if not hist.empty:
                candles = []
                for idx, row in hist.iterrows():
                    candles.append({
                        'timestamp': idx.isoformat(),
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'close': float(row['Close']),
                        'volume': float(row['Volume'])
                    })
                
                stocks_data[symbol] = candles
                print(f"✅ {len(candles)} 条数据")
            else:
                print(f"⚠️ 无数据")
        
        except Exception as e:
            print(f"❌ {e}")
        
        time.sleep(0.5)
    
    # 保存
    output_file = DATA_DIR / "hk_stocks_may_2026.json"
    with open(output_file, 'w') as f:
        json.dump(stocks_data, f, indent=2)
    
    print(f"✅ 港股数据已保存: {output_file}")
    print(f"   总计: {len(stocks_data)} 个股票")
    
    return stocks_data

# ============================================================================
# 4. 汇率数据采集（exchangerate-api.com）
# ============================================================================

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CNY"]

def collect_forex():
    """采集汇率 5 月数据"""
    print("\n💱 采集汇率数据...")
    
    forex_data = {}
    
    # 获取每日汇率
    current_date = datetime.strptime(START_DATE, "%Y-%m-%d")
    end_date = datetime.strptime(END_DATE, "%Y-%m-%d")
    
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        
        url = f"https://api.exchangerate-api.com/v4/latest/USD"
        
        try:
            print(f"  采集 {date_str}...", end=" ")
            resp = requests.get(url, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                
                rates = {}
                for currency in CURRENCIES:
                    if currency in data['rates']:
                        rates[currency] = data['rates'][currency]
                
                forex_data[date_str] = {
                    'base': 'USD',
                    'rates': rates,
                    'timestamp': date_str
                }
                
                print(f"✅ {len(rates)} 个汇率")
            else:
                print(f"❌ HTTP {resp.status_code}")
        
        except Exception as e:
            print(f"❌ {e}")
        
        current_date += timedelta(days=1)
        time.sleep(1)
    
    # 保存
    output_file = DATA_DIR / "forex_may_2026.json"
    with open(output_file, 'w') as f:
        json.dump(forex_data, f, indent=2)
    
    print(f"✅ 汇率数据已保存: {output_file}")
    print(f"   总计: {len(forex_data)} 天")
    
    return forex_data

# ============================================================================
# 主函数
# ============================================================================

def main():
    print("=" * 80)
    print("开始采集 5 月份多市场历史数据")
    print(f"时间范围: {START_DATE} → {END_DATE}")
    print("=" * 80)
    
    # 顺序采集
    us_data = collect_us_stocks()
    cn_data = collect_cn_stocks()
    hk_data = collect_hk_stocks()
    forex_data = collect_forex()
    
    print("\n" + "=" * 80)
    print("✅ 5 月数据采集完成")
    print("=" * 80)
    print(f"  美股: {len(us_data)} 个标的")
    print(f"  A股: {len(cn_data)} 个标的")
    print(f"  港股: {len(hk_data)} 个标的")
    print(f"  汇率: {len(forex_data)} 天")

if __name__ == "__main__":
    main()
