#!/usr/bin/env python3
"""
A股历史数据采集（禁用代理）
使用 akshare 采集 5 月数据
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from _paths import get_base_dir

# 禁用代理（akshare 访问东方财富 API 不需要代理）
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)

import akshare as ak

def collect_cn_stocks():
    """采集 A股 5 月数据"""
    print("📈 采集 A股数据（akshare，禁用代理）...")
    
    symbols = [
        ('000001', '平安银行'),
        ('600519', '贵州茅台'),
        ('000858', '五粮液'),
        ('601318', '中国平安'),
        ('600036', '招商银行')
    ]
    
    all_data = {}
    
    for code, name in symbols:
        try:
            print(f"  采集 {code} ({name})...", end=' ')
            
            df = ak.stock_zh_a_hist(
                symbol=code,
                period='daily',
                start_date='20260501',
                end_date='20260506',
                adjust='qfq'  # 前复权
            )
            
            if not df.empty:
                data = []
                for index, row in df.iterrows():
                    data.append({
                        'date': str(row['日期']),
                        'open': float(row['开盘']),
                        'high': float(row['最高']),
                        'low': float(row['最低']),
                        'close': float(row['收盘']),
                        'volume': int(row['成交量']),
                        'amount': float(row['成交额'])
                    })
                
                all_data[code] = data
                print(f"✅ {len(data)} 条数据")
            else:
                print(f"⚠️ 无数据")
        
        except Exception as e:
            print(f"❌ {str(e)[:50]}")
    
    # 保存数据
    output_path = get_base_dir() / "data" / "historical" / "cn_stocks_may_2026.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ A股数据已保存: {output_path}")
    print(f"   总计: {len(all_data)} 个股票")
    
    return all_data

if __name__ == '__main__':
    print("=" * 80)
    print("开始采集 A股 5 月份历史数据")
    print("时间范围: 2026-05-01 → 2026-05-06")
    print("=" * 80)
    print()
    
    result = collect_cn_stocks()
    
    print()
    print("=" * 80)
    print("✅ A股数据采集完成")
    print("=" * 80)
