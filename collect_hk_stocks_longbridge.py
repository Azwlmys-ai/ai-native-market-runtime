#!/usr/bin/env python3
"""
使用长桥 API 采集港股历史数据
港股选择：腾讯控股、阿里巴巴、小米集团、美团、比亚迪股份
"""

import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
import time

# 读取配置
CONFIG_PATH = Path('/opt/data/polymarket_arbitrage/config/broker_config.json')

def load_longbridge_config():
    """加载长桥配置"""
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    
    lb_config = config['brokers']['longbridge']
    return lb_config['app_key'], lb_config['app_secret'], lb_config['http_url']

def get_longbridge_token(app_key, app_secret):
    """获取长桥 Access Token"""
    url = "https://openapi.longportapp.com/v1/token"
    
    data = {
        'app_key': app_key,
        'app_secret': app_secret,
        'grant_type': 'client_credentials'
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result.get('code') == 0:
            return result['data']['token']
        else:
            print(f"❌ 获取 Token 失败: {result.get('message')}")
            return None
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return None

def collect_longbridge_history(symbol, token, start_date, end_date):
    """采集长桥历史数据"""
    print(f"\n📊 采集 {symbol} 数据...")
    
    url = "https://openapi.longportapp.com/v1/quote/candlesticks"
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    params = {
        'symbol': symbol,
        'period': '60',  # 60分钟
        'count': 1500,   # 最多1500条
        'adjust_type': '1'  # 前复权
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if result.get('code') != 0:
            print(f"  ❌ API 错误: {result.get('message')}")
            return []
        
        candlesticks = result.get('data', {}).get('candlesticks', [])
        
        formatted_data = []
        for item in candlesticks:
            formatted_data.append({
                'timestamp': datetime.fromtimestamp(int(item['timestamp'])).isoformat(),
                'open': float(item['open']),
                'high': float(item['high']),
                'low': float(item['low']),
                'close': float(item['close']),
                'volume': int(item['volume'])
            })
        
        print(f"  ✅ 已采集 {len(formatted_data)} 条")
        return formatted_data
        
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return []

def main():
    print("="*80)
    print("采集港股真实历史数据（长桥 API）")
    print("="*80)
    
    # 加载配置
    app_key, app_secret, http_url = load_longbridge_config()
    print(f"\n✅ App Key: {app_key[:10]}...")
    
    # 获取 Token
    print("\n🔑 获取 Access Token...")
    token = get_longbridge_token(app_key, app_secret)
    
    if not token:
        print("❌ 无法获取 Token，退出")
        return
    
    print(f"✅ Token: {token[:20]}...")
    
    data_dir = Path('/opt/data/polymarket_arbitrage/data/historical')
    data_dir.mkdir(parents=True, exist_ok=True)
    
    start_date = "2026-03-01"
    end_date = "2026-04-30"
    
    # 港股列表（长桥格式）
    hk_stocks = {
        '腾讯控股': '00700.HK',
        '阿里巴巴': '09988.HK',
        '小米集团': '01810.HK',
        '美团': '03690.HK',
        '比亚迪股份': '01211.HK'
    }
    
    hk_data = {}
    
    for name, symbol in hk_stocks.items():
        data = collect_longbridge_history(symbol, token, start_date, end_date)
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
