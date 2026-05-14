#!/usr/bin/env python3
"""
合并加密货币历史数据（3月 + 4月）
"""

import json
from pathlib import Path

def merge_crypto_data():
    data_dir = Path("/opt/data/polymarket_arbitrage/data/historical")
    
    # 需要合并的币种
    symbols = ['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT']
    
    merged_data = {}
    
    for symbol in symbols:
        print(f"合并 {symbol}...")
        
        # 读取3月和4月数据
        march_file = data_dir / f"okx_{symbol.replace('-', '_')}_klines_march_2026.json"
        april_file = data_dir / f"okx_{symbol.replace('-', '_')}_klines_april_2026.json"
        
        all_klines = []
        
        if march_file.exists():
            with open(march_file, 'r') as f:
                march_data = json.load(f)
                all_klines.extend(march_data)
                print(f"  3月: {len(march_data)} 条")
        
        if april_file.exists():
            with open(april_file, 'r') as f:
                april_data = json.load(f)
                all_klines.extend(april_data)
                print(f"  4月: {len(april_data)} 条")
        
        if all_klines:
            # 按时间戳排序去重
            all_klines.sort(key=lambda x: x['timestamp'])
            
            # 去重（相同时间戳只保留一条）
            seen = set()
            unique_klines = []
            for k in all_klines:
                ts = k['timestamp']
                if ts not in seen:
                    seen.add(ts)
                    unique_klines.append(k)
            
            merged_data[symbol] = {
                'symbol': symbol,
                'data': unique_klines
            }
            print(f"  合并后: {len(unique_klines)} 条")
    
    # 保存合并后的数据
    output_file = data_dir / "okx_klines_march_april_2026.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ 合并完成，保存到: {output_file}")
    print(f"✓ 共 {len(merged_data)} 个币种")

if __name__ == "__main__":
    merge_crypto_data()
