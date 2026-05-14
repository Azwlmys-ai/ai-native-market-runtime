#!/usr/bin/env python3
"""
使用 yfinance 采集港股历史数据
港股选择：腾讯控股、阿里巴巴、小米集团、美团、比亚迪股份
"""

import json
import yfinance as yf
from datetime import datetime
from pathlib import Path
import time

def collect_hk_stock_yfinance(symbol, ticker):
    """采集港股历史数据"""
    print(f"\n📊 采集 {symbol}({ticker}) 数据...")
    
    try:
        # 下载历史数据（1小时间隔）
        stock = yf.Ticker(ticker)
        df = stock.history(
            start="2026-03-01",
            end="2026-05-01",
            interval="1h"
        )
        
        if df.empty:
            print(f"  ❌ 未获取到数据")
            return []
        
        formatted_data = []
        for index, row in df.iterrows():
            formatted_data.append({
                'timestamp': index.isoformat(),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume'])
            })
        
        print(f"  ✅ 已采集 {len(formatted_data)} 条")
        return formatted_data
        
    except Exception as e:
        print(f"  ❌ 采集失败: {e}")
        return []

def main():
    print("="*80)
    print("采集港股真实历史数据（yfinance）")
    print("="*80)
    
    data_dir = Path('/opt/data/polymarket_arbitrage/data/historical')
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # 港股列表（Yahoo Finance 格式）
    hk_stocks = {
        '腾讯控股': '0700.HK',
        '阿里巴巴': '9988.HK',
        '小米集团': '1810.HK',
        '美团': '3690.HK',
        '比亚迪股份': '1211.HK'
    }
    
    hk_data = {}
    
    for name, ticker in hk_stocks.items():
        data = collect_hk_stock_yfinance(name, ticker)
        if data:
            hk_data[name] = data
        time.sleep(1)
    
    # 保存数据
    if hk_data:
        filename = data_dir / 'hk_stocks_march_2026.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(hk_data, f, indent=2, ensure_ascii=False)
        
        print("\n" + "="*80)
        print(f"✅ 已保存港股数据: {filename}")
        print("="*80)
        
        for name, data in hk_data.items():
            if data:
                prices = [d['close'] for d in data]
                print(f"  {name}: {len(data)} 条, HK${min(prices):.2f} - HK${max(prices):.2f}")
    else:
        print("\n❌ 未采集到任何数据")

if __name__ == '__main__':
    main()
