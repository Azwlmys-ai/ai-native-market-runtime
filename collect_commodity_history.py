#!/usr/bin/env python3
"""
采集大宗商品历史数据（2026年3-4月）
使用 Yahoo Finance API
"""

import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
import time

class CommodityHistoryCollector:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data" / "historical"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def collect_commodity_history(self, symbol, name, start_date, end_date):
        """
        采集单个商品的历史数据
        symbol: Yahoo Finance 代码（如 GC=F）
        name: 商品名称（如 gold）
        """
        print(f"正在采集 {name} ({symbol})...")
        
        try:
            # 转换日期为时间戳
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
            
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                'period1': start_ts,
                'period2': end_ts,
                'interval': '1h',  # 1小时K线
                'includePrePost': 'false'
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
                    result = data['chart']['result'][0]
                    timestamps = result.get('timestamp', [])
                    quotes = result.get('indicators', {}).get('quote', [{}])[0]
                    
                    opens = quotes.get('open', [])
                    highs = quotes.get('high', [])
                    lows = quotes.get('low', [])
                    closes = quotes.get('close', [])
                    volumes = quotes.get('volume', [])
                    
                    history = []
                    for i in range(len(timestamps)):
                        # 跳过空数据
                        if closes[i] is None:
                            continue
                            
                        history.append({
                            'timestamp': timestamps[i],
                            'date': datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d %H:%M:%S'),
                            'open': round(opens[i], 2) if opens[i] else None,
                            'high': round(highs[i], 2) if highs[i] else None,
                            'low': round(lows[i], 2) if lows[i] else None,
                            'close': round(closes[i], 2) if closes[i] else None,
                            'volume': int(volumes[i]) if volumes[i] else 0
                        })
                    
                    print(f"  ✓ {name}: {len(history)} 条数据")
                    return history
                else:
                    print(f"  ✗ {name}: 数据格式错误")
                    return None
            else:
                print(f"  ✗ {name}: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            return None
    
    def collect_all(self):
        """采集所有大宗商品历史数据"""
        print("=" * 80)
        print("采集大宗商品历史数据（2026年3-4月）")
        print("=" * 80)
        
        # 商品列表
        commodities = {
            'gold': 'GC=F',        # 黄金期货
            'silver': 'SI=F',      # 白银期货
            'oil_wti': 'CL=F',     # WTI 原油期货
            'oil_brent': 'BZ=F',   # 布伦特原油期货
            'natural_gas': 'NG=F', # 天然气期货
            'copper': 'HG=F',      # 铜期货
        }
        
        start_date = "2026-03-01"
        end_date = "2026-04-30"
        
        all_data = {}
        
        for name, symbol in commodities.items():
            history = self.collect_commodity_history(symbol, name, start_date, end_date)
            if history:
                all_data[name] = {
                    'symbol': symbol,
                    'data': history
                }
            time.sleep(2)  # 避免请求过快
        
        # 保存数据
        if all_data:
            output_file = self.data_dir / "commodities_march_april_2026.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, indent=2, ensure_ascii=False)
            
            print("\n" + "=" * 80)
            print(f"✓ 采集完成，共 {len(all_data)} 个商品")
            for name, info in all_data.items():
                print(f"  - {name}: {len(info['data'])} 条数据")
            print(f"✓ 数据已保存到: {output_file}")
            print("=" * 80)
        else:
            print("\n✗ 采集失败，无有效数据")

if __name__ == "__main__":
    collector = CommodityHistoryCollector()
    collector.collect_all()
