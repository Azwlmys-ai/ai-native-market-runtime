#!/usr/bin/env python3
"""
A股历史数据采集（新浪财经 API）
使用新浪财经 API 采集 5 月数据（60分钟 K线）
"""

import json
import requests
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from _paths import get_base_dir

def collect_cn_stocks():
    """采集 A股 5 月数据（新浪财经）"""
    print("📈 采集 A股数据（新浪财经 API）...")
    
    symbols = [
        ('sh600519', '贵州茅台'),
        ('sz000858', '五粮液'),
        ('sh601318', '中国平安'),
        ('sh600036', '招商银行'),
        ('sz000001', '平安银行')
    ]
    
    all_data = {}
    
    for code, name in symbols:
        try:
            print(f"  采集 {code} ({name})...", end=' ')
            
            url = 'https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData'
            params = {
                'symbol': code,
                'scale': 60,  # 60分钟
                'datalen': 200  # 足够覆盖 5 月
            }
            
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            
            # 解析 JSONP
            text = resp.text
            start = text.find('[')
            end = text.rfind(']') + 1
            
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                
                # 过滤 5 月数据
                may_data = []
                for item in data:
                    timestamp = item['day']
                    if '2026-05' in timestamp:
                        may_data.append({
                            'timestamp': timestamp,
                            'open': float(item['open']),
                            'high': float(item['high']),
                            'low': float(item['low']),
                            'close': float(item['close']),
                            'volume': float(item['volume'])
                        })
                
                if may_data:
                    all_data[code] = may_data
                    print(f"✅ {len(may_data)} 条数据")
                else:
                    print(f"⚠️ 无 5 月数据")
            else:
                print(f"⚠️ 解析失败")
        
        except Exception as e:
            print(f"❌ {type(e).__name__}: {str(e)[:50]}")
    
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
