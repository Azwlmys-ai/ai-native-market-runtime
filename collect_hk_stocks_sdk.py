#!/usr/bin/env python3
"""
使用长桥 Python SDK 采集港股历史数据
"""

import json
from datetime import datetime, date
from pathlib import Path
from longbridge.openapi import Config as LBConfig, QuoteContext, Period, AdjustType
import time

# 读取配置
CONFIG_PATH = Path('/opt/data/polymarket_arbitrage/config/broker_config.json')

def load_longbridge_config():
    """加载长桥配置"""
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    
    lb_config = config['brokers']['longbridge']
    return lb_config['app_key'], lb_config['app_secret'], lb_config['access_token']

def collect_hk_stock_history(symbol, quote_ctx):
    """采集港股历史K线数据"""
    print(f"\n📊 采集 {symbol} 数据...")
    
    try:
        # 获取历史K线（60分钟）
        resp = quote_ctx.history_candlesticks_by_offset(
            symbol=symbol,
            period=Period.Min_60,
            adjust_type=AdjustType.ForwardAdjust,
            forward=False,
            count=1500  # 最多1500条
        )
        
        if not resp:
            print(f"  ❌ 未获取到数据")
            return []
        
        formatted_data = []
        for candle in resp:
            formatted_data.append({
                'timestamp': candle.timestamp.isoformat(),
                'open': float(candle.open),
                'high': float(candle.high),
                'low': float(candle.low),
                'close': float(candle.close),
                'volume': int(candle.volume)
            })
        
        print(f"  ✅ 已采集 {len(formatted_data)} 条")
        return formatted_data
        
    except Exception as e:
        print(f"  ❌ 采集失败: {e}")
        return []

def main():
    print("="*80)
    print("采集港股真实历史数据（长桥 Python SDK）")
    print("="*80)
    
    # 加载配置
    app_key, app_secret, access_token = load_longbridge_config()
    print(f"\n✅ App Key: {app_key[:10]}...")
    
    # 创建配置
    config = LBConfig.from_env()
    
    # 手动设置
    config.app_key = app_key
    config.app_secret = app_secret
    config.access_token = access_token
    
    # 创建行情上下文
    print("\n🔌 连接长桥 API...")
    try:
        quote_ctx = QuoteContext(config)
        print("✅ 连接成功")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return
    
    data_dir = Path('/opt/data/polymarket_arbitrage/data/historical')
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # 港股列表
    hk_stocks = {
        '腾讯控股': '700.HK',
        '阿里巴巴': '9988.HK',
        '小米集团': '1810.HK',
        '美团': '3690.HK',
        '比亚迪股份': '1211.HK'
    }
    
    hk_data = {}
    
    for name, symbol in hk_stocks.items():
        data = collect_hk_stock_history(symbol, quote_ctx)
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
