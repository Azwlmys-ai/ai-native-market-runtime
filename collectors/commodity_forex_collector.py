#!/usr/bin/env python3
"""
大宗商品和汇率数据采集器（免费版）

数据源：
1. 汇率：ExchangeRate API（免费 1500 次/月）
2. 大宗商品：使用 Yahoo Finance（免费无限制）
"""

import json
import csv
import io
import requests
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from _paths import get_base_dir

class CommodityForexCollector:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # ExchangeRate API（免费，无需 API Key）
        self.exchange_api_base = "https://api.exchangerate-api.com/v4/latest"
        
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [Commodity/Forex] {message}", flush=True)
    
    def fetch_commodities_yahoo(self):
        """从 Yahoo Finance 获取大宗商品数据"""
        commodities = {}
        
        # Yahoo Finance 商品代码
        yahoo_symbols = {
            'gold': 'GC=F',        # 黄金期货
            'silver': 'SI=F',      # 白银期货
            'oil_wti': 'CL=F',     # WTI 原油期货
            'oil_brent': 'BZ=F',   # 布伦特原油期货
            'natural_gas': 'NG=F', # 天然气期货
            'copper': 'HG=F',      # 铜期货
        }
        
        for name, symbol in yahoo_symbols.items():
            try:
                # 使用 Yahoo Finance 查询接口
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                params = {
                    'interval': '1d',
                    'range': '1d'
                }
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                response = requests.get(url, params=params, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'chart' in data and 'result' in data['chart']:
                        result = data['chart']['result'][0]
                        meta = result.get('meta', {})
                        
                        price = meta.get('regularMarketPrice')
                        currency = meta.get('currency', 'USD')
                        
                        if price:
                            commodities[name] = {
                                'price': round(price, 2),
                                'currency': currency,
                                'symbol': symbol,
                                'source': 'Yahoo Finance'
                            }
                            self.log(f"✅ {name}: ${price:.2f}")
                        else:
                            self.log(f"⚠️ {name}: 无价格数据")
                    else:
                        self.log(f"⚠️ {name}: 数据格式错误")
                else:
                    self.log(f"❌ {name}: HTTP {response.status_code}")
            
            except Exception as e:
                self.log(f"❌ {name}: {e}")
        
        return commodities

    def fetch_commodities_stooq(self):
        """从 Stooq 获取商品/金属报价，作为 Yahoo 403 时的轻量真实数据源。"""
        commodities = {}
        stooq_symbols = {
            'gold': 'xauusd',
            'silver': 'xagusd',
            'oil_wti': 'cl.f',
            'natural_gas': 'ng.f',
            'copper': 'hg.f',
        }

        for name, symbol in stooq_symbols.items():
            try:
                url = "https://stooq.com/q/l/"
                params = {"s": symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"}
                response = requests.get(url, params=params, timeout=10)
                if response.status_code != 200:
                    self.log(f"❌ {name} Stooq: HTTP {response.status_code}")
                    continue

                rows = list(csv.DictReader(io.StringIO(response.text)))
                if not rows:
                    self.log(f"⚠️ {name} Stooq: 空响应")
                    continue

                row = rows[0]
                close = row.get("Close")
                if not close or close == "N/D":
                    self.log(f"⚠️ {name} Stooq: 无价格数据")
                    continue

                price = float(close)
                commodities[name] = {
                    'price': round(price, 4),
                    'currency': 'USD',
                    'symbol': symbol,
                    'source': 'Stooq',
                    'date': row.get("Date"),
                    'time': row.get("Time"),
                }
                self.log(f"✅ {name} Stooq: ${price:.4f}")
            except Exception as e:
                self.log(f"❌ {name} Stooq: {e}")

        return commodities
    
    def fetch_forex_rates(self):
        """从 ExchangeRate API 获取汇率数据"""
        forex = {}
        
        # 主要货币对（以 USD 为基准）
        base_currency = 'USD'
        
        try:
            url = f"{self.exchange_api_base}/{base_currency}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                rates = data.get('rates', {})
                
                # 提取主要货币对
                major_pairs = ['EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'CAD', 'AUD', 'NZD', 'SGD', 'HKD']
                
                for currency in major_pairs:
                    if currency in rates:
                        forex[f'USD/{currency}'] = {
                            'rate': rates[currency],
                            'source': 'ExchangeRate API'
                        }
                        self.log(f"✅ USD/{currency}: {rates[currency]}")
                
                # 计算反向汇率（EUR/USD, GBP/USD 等）
                for currency in ['EUR', 'GBP', 'JPY', 'CNY']:
                    if currency in rates:
                        reverse_rate = 1 / rates[currency]
                        forex[f'{currency}/USD'] = {
                            'rate': round(reverse_rate, 4),
                            'source': 'ExchangeRate API (calculated)'
                        }
                        self.log(f"✅ {currency}/USD: {reverse_rate:.4f}")
            else:
                self.log(f"❌ 汇率数据: HTTP {response.status_code}")
        
        except Exception as e:
            self.log(f"❌ 汇率数据: {e}")
        
        return forex
    
    def run(self):
        """执行数据采集"""
        self.log("=" * 60)
        self.log("开始采集大宗商品和汇率数据")
        
        # 采集大宗商品
        self.log("📊 采集大宗商品数据（Yahoo Finance）")
        commodities = self.fetch_commodities_yahoo()
        if not commodities:
            self.log("📊 Yahoo Finance 无可用商品数据，切换 Stooq")
            commodities = self.fetch_commodities_stooq()
        
        # 采集汇率
        self.log("📊 采集汇率数据（ExchangeRate API）")
        forex = self.fetch_forex_rates()
        
        # 汇总数据
        output = {
            'timestamp': datetime.now().isoformat(),
            'commodities': commodities,
            'forex': forex,
            'sources': {
                'commodities': 'Yahoo Finance (免费无限制)',
                'forex': 'ExchangeRate API (免费 1500 次/月)'
            }
        }
        
        # 保存数据
        output_file = self.data_dir / "commodity_forex_data.json"
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 数据采集完成")
        self.log(f"   大宗商品: {len(commodities)} 个")
        self.log(f"   汇率: {len(forex)} 个")
        self.log(f"   保存到: {output_file}")
        self.log("=" * 60)
        
        return output

def main():
    collector = CommodityForexCollector()
    collector.run()

if __name__ == "__main__":
    main()
