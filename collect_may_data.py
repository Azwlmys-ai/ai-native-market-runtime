#!/usr/bin/env python3
"""
采集 5 月份的市场数据用于回测
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import time

def collect_okx_may_data():
    """采集 OKX 5 月份数据"""
    print("采集 OKX 加密货币数据（5月）...")
    
    import ccxt
    
    exchange = ccxt.okx({
        'enableRateLimit': True,
    })
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']
    
    # 5 月 1 日 - 5 月 6 日
    start_date = datetime(2026, 5, 1, 0, 0, 0)
    end_date = datetime(2026, 5, 6, 23, 59, 59)
    
    all_data = {}
    
    for symbol in symbols:
        print(f"  采集 {symbol}...")
        
        try:
            since = int(start_date.timestamp() * 1000)
            end_ts = int(end_date.timestamp() * 1000)
            
            all_klines = []
            
            while since < end_ts:
                klines = exchange.fetch_ohlcv(symbol, '1h', since=since, limit=100)
                
                if not klines:
                    break
                
                all_klines.extend(klines)
                since = klines[-1][0] + 3600000
                
                time.sleep(0.5)
            
            # 转换格式
            formatted_data = []
            for k in all_klines:
                if k[0] >= int(start_date.timestamp() * 1000) and k[0] <= int(end_date.timestamp() * 1000):
                    formatted_data.append({
                        'timestamp': datetime.fromtimestamp(k[0] / 1000).isoformat() + 'Z',
                        'open': str(k[1]),
                        'high': str(k[2]),
                        'low': str(k[3]),
                        'close': str(k[4]),
                        'volume': str(k[5])
                    })
            
            symbol_key = symbol.replace('/', '-')
            all_data[symbol_key] = {
                'symbol': symbol_key,
                'data': formatted_data
            }
            
            print(f"    ✓ {len(formatted_data)} 条数据")
            
        except Exception as e:
            print(f"    ✗ 失败: {e}")
    
    # 保存
    output_file = Path("/opt/data/polymarket_arbitrage/data/historical/okx_klines_may_2026.json")
    with open(output_file, 'w') as f:
        json.dump(all_data, f, indent=2)
    
    print(f"\n✓ 已保存到: {output_file}")
    return len(all_data)

def collect_commodities_may_data():
    """采集大宗商品 5 月份数据"""
    print("\n采集大宗商品数据（5月）...")
    
    import yfinance as yf
    
    commodities = {
        'gold': 'GC=F',
        'silver': 'SI=F',
        'oil_wti': 'CL=F',
        'oil_brent': 'BZ=F',
        'natural_gas': 'NG=F',
        'copper': 'HG=F'
    }
    
    start_date = "2026-05-01"
    end_date = "2026-05-07"
    
    all_data = {}
    
    for name, ticker in commodities.items():
        print(f"  采集 {name} ({ticker})...")
        
        try:
            df = yf.download(ticker, start=start_date, end=end_date, interval='1h', progress=False)
            
            if df.empty:
                print(f"    ✗ 无数据")
                continue
            
            data_points = []
            for index, row in df.iterrows():
                data_points.append({
                    'timestamp': index.isoformat() + 'Z',
                    'open': float(row['Open']) if pd.notna(row['Open']) else None,
                    'high': float(row['High']) if pd.notna(row['High']) else None,
                    'low': float(row['Low']) if pd.notna(row['Low']) else None,
                    'close': float(row['Close']) if pd.notna(row['Close']) else None,
                    'volume': float(row['Volume']) if pd.notna(row['Volume']) else None
                })
            
            all_data[name] = {
                'name': name,
                'ticker': ticker,
                'data': data_points
            }
            
            print(f"    ✓ {len(data_points)} 条数据")
            
        except Exception as e:
            print(f"    ✗ 失败: {e}")
    
    # 保存
    output_file = Path("/opt/data/polymarket_arbitrage/data/historical/commodities_may_2026.json")
    with open(output_file, 'w') as f:
        json.dump(all_data, f, indent=2)
    
    print(f"\n✓ 已保存到: {output_file}")
    return len(all_data)

def merge_march_april_may_data():
    """合并 3-4-5 月数据"""
    print("\n合并 3-4-5 月数据...")
    
    base_dir = Path("/opt/data/polymarket_arbitrage/data/historical")
    
    # 合并加密货币数据
    print("  合并加密货币数据...")
    march_april_file = base_dir / "okx_klines_march_april_2026.json"
    may_file = base_dir / "okx_klines_may_2026.json"
    
    if march_april_file.exists() and may_file.exists():
        with open(march_april_file, 'r') as f:
            march_april_data = json.load(f)
        
        with open(may_file, 'r') as f:
            may_data = json.load(f)
        
        merged_crypto = {}
        for symbol in march_april_data.keys():
            if symbol in may_data:
                merged_crypto[symbol] = {
                    'symbol': symbol,
                    'data': march_april_data[symbol]['data'] + may_data[symbol]['data']
                }
                print(f"    {symbol}: {len(merged_crypto[symbol]['data'])} 条")
        
        output_file = base_dir / "okx_klines_march_april_may_2026.json"
        with open(output_file, 'w') as f:
            json.dump(merged_crypto, f, indent=2)
        
        print(f"  ✓ 加密货币数据已保存")
    
    # 合并大宗商品数据
    print("  合并大宗商品数据...")
    march_april_file = base_dir / "commodities_march_april_2026.json"
    may_file = base_dir / "commodities_may_2026.json"
    
    if march_april_file.exists() and may_file.exists():
        with open(march_april_file, 'r') as f:
            march_april_data = json.load(f)
        
        with open(may_file, 'r') as f:
            may_data = json.load(f)
        
        merged_commodities = {}
        for name in march_april_data.keys():
            if name in may_data:
                merged_commodities[name] = {
                    'name': name,
                    'ticker': march_april_data[name].get('ticker', ''),
                    'data': march_april_data[name]['data'] + may_data[name]['data']
                }
                print(f"    {name}: {len(merged_commodities[name]['data'])} 条")
        
        output_file = base_dir / "commodities_march_april_may_2026.json"
        with open(output_file, 'w') as f:
            json.dump(merged_commodities, f, indent=2)
        
        print(f"  ✓ 大宗商品数据已保存")

if __name__ == "__main__":
    print("=" * 80)
    print("采集 5 月份市场数据")
    print("=" * 80)
    
    # 检查依赖
    try:
        import ccxt
        import yfinance as yf
        import pandas as pd
    except ImportError as e:
        print(f"✗ 缺少依赖: {e}")
        print("请安装: pip install ccxt yfinance pandas")
        sys.exit(1)
    
    # 采集数据
    crypto_count = collect_okx_may_data()
    commodity_count = collect_commodities_may_data()
    
    # 合并数据
    merge_march_april_may_data()
    
    print("\n" + "=" * 80)
    print("采集完成")
    print("=" * 80)
    print(f"  加密货币: {crypto_count} 个币种")
    print(f"  大宗商品: {commodity_count} 个品种")
