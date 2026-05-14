#!/usr/bin/env python3
"""
统一所有市场数据的时间戳格式
转换为 ISO 8601 字符串格式
"""

import json
from pathlib import Path
from datetime import datetime

def convert_commodity_timestamps():
    """转换大宗商品时间戳"""
    data_dir = Path("/opt/data/polymarket_arbitrage/data/historical")
    commodity_file = data_dir / "commodities_march_april_2026.json"
    
    with open(commodity_file, 'r') as f:
        data = json.load(f)
    
    print("转换大宗商品时间戳...")
    
    for name, info in data.items():
        converted_count = 0
        for point in info['data']:
            if isinstance(point['timestamp'], int):
                # Unix 时间戳转 ISO 8601
                dt = datetime.fromtimestamp(point['timestamp'])
                point['timestamp'] = dt.strftime('%Y-%m-%dT%H:%M:%S')
                converted_count += 1
        
        print(f"  {name}: {converted_count} 条")
    
    # 保存
    with open(commodity_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ 转换完成: {commodity_file}")

if __name__ == "__main__":
    convert_commodity_timestamps()
