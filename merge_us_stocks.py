#!/usr/bin/env python3
"""
合并美股历史数据（3月 + 4月）
"""

import json
from pathlib import Path

def merge_us_stocks():
    data_dir = Path("/opt/data/polymarket_arbitrage/data/historical")
    
    # 检查是否有4月数据
    march_file = data_dir / "us_stocks_march_2026.json"
    april_file = data_dir / "us_stocks_april_2026.json"
    
    if not march_file.exists():
        print("✗ 3月数据不存在")
        return
    
    with open(march_file, 'r') as f:
        march_data = json.load(f)
    
    print(f"3月数据: {len(march_data)} 只股票")
    for symbol, info in march_data.items():
        if isinstance(info, list):
            print(f"  {symbol}: {len(info)} 条")
        else:
            print(f"  {symbol}: {len(info['data'])} 条")
    
    if april_file.exists():
        with open(april_file, 'r') as f:
            april_data = json.load(f)
        
        print(f"\n4月数据: {len(april_data)} 只股票")
        
        # 合并数据
        merged_data = {}
        for symbol in march_data.keys():
            if symbol in april_data:
                # 处理列表格式
                march_list = march_data[symbol] if isinstance(march_data[symbol], list) else march_data[symbol]['data']
                april_list = april_data[symbol] if isinstance(april_data[symbol], list) else april_data[symbol]['data']
                
                merged_data[symbol] = march_list + april_list
                print(f"  {symbol}: {len(merged_data[symbol])} 条")
            else:
                merged_data[symbol] = march_data[symbol]
        
        # 保存
        output_file = data_dir / "us_stocks_march_april_2026.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(merged_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 合并完成: {output_file}")
    else:
        print("\n⚠ 只有3月数据，无需合并")
        # 直接复制为统一文件名
        output_file = data_dir / "us_stocks_march_april_2026.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(march_data, f, indent=2, ensure_ascii=False)
        print(f"✓ 已复制为: {output_file}")

if __name__ == "__main__":
    merge_us_stocks()
