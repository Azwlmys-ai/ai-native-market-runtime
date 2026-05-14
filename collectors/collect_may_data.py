#!/usr/bin/env python3
"""
采集 5 月份多市场历史数据
- 美股（Finnhub API）
- A股（东方财富 API）
- 港股（yfinance）
- 大宗商品（Alpha Vantage）
- 汇率（exchangerate-api.com）
"""

import json
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta
import time

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "historical"
CONFIG_PATH = BASE_DIR / "config" / "broker_config.json"

# 加载配置
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

# 时间范围：5月1日 - 5月6日
START_DATE = "2026-05-01"
END_DATE = "2026-05-06"

# ============================================================================
# 1. 美股数据采集（Finnhub）
# ============================================================================

US_STOCKS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "COIN", "TTWO", "MSTR"]

async def collect_us_stocks():
    """采集美股 5 月数据"""
    print("\n📈 采集美股数据...")
    
    api_key = config['brokers']['finnhub']['api_key']
    
    # Finnhub 历史数据 API
    # https://finnhub.io/docs/api/stock-candles
    
    start_ts = int(datetime.strptime(START_DATE, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(END_DATE, "%Y-%m-%d").timestamp())
    
    stocks_data = {}
    
    async with aiohttp.ClientSession() as session:
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
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
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
                            print(f"  ✅ {symbol}: {len(candles)} 条数据")
                        else:
                            print(f"  ⚠️ {symbol}: 无数据")
                    else:
                        print(f"  ❌ {symbol}: HTTP {resp.status}")
                
                await asyncio.sleep(0.1)  # 避免限流
                
            except Exception as e:
                print(f"  ❌ {symbol}: {e}")
    
    # 保存
    output_file = DATA_DIR / "us_stocks_may_2026.json"
    with open(output_file, 'w') as f:
        json.dump(stocks_data, f, indent=2)
    
    print(f"✅ 美股数据已保存: {output_file}")
    return stocks_data

# ============================================================================
# 2. A股数据采集（东方财富）
# ============================================================================

CN_STOCKS = ["000001", "600519", "000858", "601318"]  # 平安银行、茅台、五粮液、中国平安

async def collect_cn_stocks():
    """采集 A 股 5 月数据"""
    print("\n📈 采集 A 股数据...")
    
    # 东方财富历史数据 API
    # http://push2his.eastmoney.com/api/qt/stock/kline/get
    
    stocks_data = {}
    
    async with aiohttp.ClientSession() as session:
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
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
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
                            print(f"  ✅ {code}: {len(candles)} 条数据")
                        else:
                            print(f"  ⚠️ {code}: 无数据（可能是假期）")
                    else:
                        print(f"  ❌ {code}: HTTP {resp.status}")
                
                await asyncio.sleep(0.2)
                
            except Exception as e:
                print(f"  ❌ {code}: {e}")
    
    # 保存
    output_file = DATA_DIR / "cn_stocks_may_2026.json"
    with open(output_file, 'w') as f:
        json.dump(stocks_data, f, indent=2)
    
    print(f"✅ A 股数据已保存: {output_file}")
    return stocks_data

# ============================================================================
# 3. 港股数据采集（yfinance）
# ============================================================================

HK_STOCKS = ["0700.HK", "9988.HK", "0941.HK"]  # 腾讯、阿里、中国移动

async def collect_hk_stocks():
    """采集港股 5 月数据"""
    print("\n📈 采集港股数据...")
    
    try:
        import yfinance as yf
    except ImportError:
        print("  ⚠️ yfinance 未安装，跳过港股采集")
        return {}
    
    stocks_data = {}
    
    for symbol in HK_STOCKS:
        try:
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
                print(f"  ✅ {symbol}: {len(candles)} 条数据")
            else:
                print(f"  ⚠️ {symbol}: 无数据")
        
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
        
        time.sleep(0.2)
    
    # 保存
    output_file = DATA_DIR / "hk_stocks_may_2026.json"
    with open(output_file, 'w') as f:
        json.dump(stocks_data, f, indent=2)
    
    print(f"✅ 港股数据已保存: {output_file}")
    return stocks_data

# ============================================================================
# 4. 大宗商品数据采集（Alpha Vantage）
# ============================================================================

COMMODITIES = {
    "WTI": "WTI",      # 原油
    "BRENT": "BRENT",  # 布伦特原油
    "NATURAL_GAS": "NATURAL_GAS",
    "COPPER": "COPPER",
    "ALUMINUM": "ALUMINUM"
}

async def collect_commodities():
    """采集大宗商品 5 月数据"""
    print("\n📦 采集大宗商品数据...")
    
    # Alpha Vantage 免费额度：25次/天
    api_key = "demo"  # 需要注册获取真实 API Key
    
    commodities_data = {}
    
    async with aiohttp.ClientSession() as session:
        for name, symbol in COMMODITIES.items():
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "TIME_SERIES_INTRADAY",
                "symbol": symbol,
                "interval": "60min",
                "apikey": api_key
            }
            
            try:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if "Time Series (60min)" in data:
                            time_series = data["Time Series (60min)"]
                            
                            candles = []
                            for ts, values in time_series.items():
                                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                                if START_DATE <= dt.strftime("%Y-%m-%d") <= END_DATE:
                                    candles.append({
                                        'timestamp': ts,
                                        'open': float(values['1. open']),
                                        'high': float(values['2. high']),
                                        'low': float(values['3. low']),
                                        'close': float(values['4. close']),
                                        'volume': float(values['5. volume'])
                                    })
                            
                            commodities_data[name] = candles
                            print(f"  ✅ {name}: {len(candles)} 条数据")
                        else:
                            print(f"  ⚠️ {name}: API 限制或无数据")
                    else:
                        print(f"  ❌ {name}: HTTP {resp.status}")
                
                await asyncio.sleep(12)  # 免费版限制：5次/分钟
                
            except Exception as e:
                print(f"  ❌ {name}: {e}")
    
    # 保存
    output_file = DATA_DIR / "commodities_may_2026.json"
    with open(output_file, 'w') as f:
        json.dump(commodities_data, f, indent=2)
    
    print(f"✅ 大宗商品数据已保存: {output_file}")
    return commodities_data

# ============================================================================
# 5. 汇率数据采集（exchangerate-api.com）
# ============================================================================

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CNY"]

async def collect_forex():
    """采集汇率 5 月数据"""
    print("\n💱 采集汇率数据...")
    
    # exchangerate-api.com 免费版
    # https://www.exchangerate-api.com/docs/free
    
    forex_data = {}
    
    async with aiohttp.ClientSession() as session:
        # 获取每日汇率
        current_date = datetime.strptime(START_DATE, "%Y-%m-%d")
        end_date = datetime.strptime(END_DATE, "%Y-%m-%d")
        
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            
            url = f"https://api.exchangerate-api.com/v4/latest/USD"
            
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        rates = {}
                        for currency in CURRENCIES:
                            if currency in data['rates']:
                                rates[currency] = data['rates'][currency]
                        
                        forex_data[date_str] = {
                            'base': 'USD',
                            'rates': rates,
                            'timestamp': date_str
                        }
                        
                        print(f"  ✅ {date_str}: {len(rates)} 个汇率")
                    else:
                        print(f"  ❌ {date_str}: HTTP {resp.status}")
                
            except Exception as e:
                print(f"  ❌ {date_str}: {e}")
            
            current_date += timedelta(days=1)
            await asyncio.sleep(1)
    
    # 保存
    output_file = DATA_DIR / "forex_may_2026.json"
    with open(output_file, 'w') as f:
        json.dump(forex_data, f, indent=2)
    
    print(f"✅ 汇率数据已保存: {output_file}")
    return forex_data

# ============================================================================
# 主函数
# ============================================================================

async def main():
    print("=" * 80)
    print("开始采集 5 月份多市场历史数据")
    print(f"时间范围: {START_DATE} → {END_DATE}")
    print("=" * 80)
    
    # 并发采集
    results = await asyncio.gather(
        collect_us_stocks(),
        collect_cn_stocks(),
        collect_hk_stocks(),
        collect_commodities(),
        collect_forex(),
        return_exceptions=True
    )
    
    print("\n" + "=" * 80)
    print("✅ 5 月数据采集完成")
    print("=" * 80)
    
    # 统计
    for i, name in enumerate(["美股", "A股", "港股", "大宗商品", "汇率"]):
        if isinstance(results[i], dict):
            print(f"  {name}: {len(results[i])} 个标的")
        else:
            print(f"  {name}: 采集失败 - {results[i]}")

if __name__ == "__main__":
    asyncio.run(main())
