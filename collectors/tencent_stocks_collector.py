#!/usr/bin/env python3
"""
腾讯财经 A 股数据采集器
提供基本面数据：市盈率、市净率、ROE、负债率等
"""

import json
import requests
from datetime import datetime
from pathlib import Path

class TencentStocksCollector:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 代理配置
        self.proxies = {
            'http': 'http://host.docker.internal:17891',
            'https': 'http://host.docker.internal:17891'
        }
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Tencent Stocks] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"tencent_stocks_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def fetch_stock_fundamentals(self, stock_code):
        """
        获取单只股票的基本面数据
        腾讯财经 API
        """
        try:
            # 转换股票代码格式（sh600519 -> sh600519）
            if stock_code.startswith('sh') or stock_code.startswith('sz'):
                code = stock_code
            else:
                # 默认上海
                code = f"sh{stock_code}"
            
            # 腾讯财经 API
            url = f"http://qt.gtimg.cn/q={code}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'http://gu.qq.com/'
            }
            
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code != 200:
                return None
            
            # 解析响应
            # 格式: v_sh600519="1~贵州茅台~600519~1373.46~..."
            text = response.text.strip()
            
            if '="' not in text:
                return None
            
            data_str = text.split('="')[1].rstrip('";\n')
            parts = data_str.split('~')
            
            if len(parts) < 50:
                return None
            
            stock = {
                'code': code,
                'name': parts[1],
                'price': float(parts[3]) if parts[3] else 0,
                'close_prev': float(parts[4]) if parts[4] else 0,
                'open': float(parts[5]) if parts[5] else 0,
                'volume': int(parts[6]) if parts[6] else 0,
                'turnover': float(parts[37]) if len(parts) > 37 and parts[37] else 0,
                'high': float(parts[33]) if len(parts) > 33 and parts[33] else 0,
                'low': float(parts[34]) if len(parts) > 34 and parts[34] else 0,
                'pe_ratio': float(parts[39]) if len(parts) > 39 and parts[39] else 0,  # 市盈率
                'pb_ratio': float(parts[46]) if len(parts) > 46 and parts[46] else 0,  # 市净率
                'market_cap': float(parts[45]) if len(parts) > 45 and parts[45] else 0,  # 总市值（亿）
                'circulation_market_cap': float(parts[44]) if len(parts) > 44 and parts[44] else 0,  # 流通市值（亿）
                'timestamp': datetime.now().isoformat()
            }
            
            # 计算涨跌幅
            if stock['close_prev'] > 0:
                stock['change_pct'] = ((stock['price'] - stock['close_prev']) / stock['close_prev']) * 100
                stock['change_amount'] = stock['price'] - stock['close_prev']
            else:
                stock['change_pct'] = 0
                stock['change_amount'] = 0
            
            return stock
        
        except Exception as e:
            return None
    
    def run(self):
        """主流程"""
        self.log("=" * 60)
        self.log("开始采集腾讯财经基本面数据")
        
        # 读取现有数据
        data_file = self.data_dir / "latest_data.json"
        
        if not data_file.exists():
            self.log("❌ latest_data.json 不存在")
            return
        
        with open(data_file, 'r') as f:
            data = json.load(f)
        
        cn_stocks = data.get('cn_stocks', {}).get('data', [])
        
        if not cn_stocks:
            self.log("❌ 无 A 股数据")
            return
        
        self.log(f"📊 发现 {len(cn_stocks)} 只股票，开始补充基本面数据...")
        
        # 补充基本面数据
        enriched_count = 0
        
        for stock in cn_stocks:
            code = stock.get('code')
            
            # 如果已有市盈率数据，跳过
            if stock.get('pe_ratio'):
                continue
            
            # 获取基本面数据
            fundamentals = self.fetch_stock_fundamentals(code)
            
            if fundamentals:
                # 补充数据
                stock['pe_ratio'] = fundamentals.get('pe_ratio', 0)
                stock['pb_ratio'] = fundamentals.get('pb_ratio', 0)
                
                # 如果没有市值数据，也补充
                if not stock.get('market_cap'):
                    stock['market_cap'] = fundamentals.get('market_cap', 0)
                    stock['circulation_market_cap'] = fundamentals.get('circulation_market_cap', 0)
                
                enriched_count += 1
        
        # 保存更新后的数据
        with open(data_file, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 补充 {enriched_count} 只股票的基本面数据")
        self.log("=" * 60)

def main():
    collector = TencentStocksCollector()
    collector.run()

if __name__ == "__main__":
    main()
