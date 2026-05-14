#!/usr/bin/env python3
"""
Alpha Vantage 数据采集器
支持股票、外汇、大宗商品数据
作为 Yahoo Finance 的备份数据源
"""

import json
import requests
import time
from pathlib import Path
from datetime import datetime

class AlphaVantageCollector:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.config_file = self.base_dir / "config" / "broker_config.json"
        
        # 加载 API Key
        with open(self.config_file, 'r') as f:
            config = json.load(f)
            self.api_key = config['brokers']['alpha_vantage']['api_key']
        
        self.base_url = "https://www.alphavantage.co/query"
        
        # 速率限制：5 次/分钟
        self.rate_limit_delay = 12  # 秒
    
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [AlphaVantage] {message}", flush=True)
    
    def fetch_commodity(self, function_name, commodity_name):
        """
        获取大宗商品数据
        function_name: WTI, BRENT, NATURAL_GAS, COPPER, ALUMINUM
        """
        self.log(f"获取 {commodity_name}...")
        
        try:
            params = {
                'function': function_name,
                'interval': 'daily',
                'apikey': self.api_key
            }
            
            response = requests.get(self.base_url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'data' in data:
                    self.log(f"✅ {commodity_name}: {len(data['data'])} 条数据")
                    return data['data']
                elif 'Information' in data:
                    self.log(f"⚠️ {commodity_name}: {data['Information']}")
                    return None
                elif 'Note' in data:
                    self.log(f"⚠️ {commodity_name}: API 限流 - {data['Note']}")
                    return None
                else:
                    self.log(f"⚠️ {commodity_name}: 未知响应格式")
                    return None
            else:
                self.log(f"❌ {commodity_name}: HTTP {response.status_code}")
                return None
        
        except Exception as e:
            self.log(f"❌ {commodity_name}: {e}")
            return None
    
    def fetch_forex(self, from_currency, to_currency):
        """
        获取外汇数据
        """
        self.log(f"获取 {from_currency}/{to_currency}...")
        
        try:
            params = {
                'function': 'FX_DAILY',
                'from_symbol': from_currency,
                'to_symbol': to_currency,
                'apikey': self.api_key
            }
            
            response = requests.get(self.base_url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'Time Series FX (Daily)' in data:
                    time_series = data['Time Series FX (Daily)']
                    self.log(f"✅ {from_currency}/{to_currency}: {len(time_series)} 条数据")
                    return time_series
                elif 'Information' in data:
                    self.log(f"⚠️ {from_currency}/{to_currency}: {data['Information']}")
                    return None
                elif 'Note' in data:
                    self.log(f"⚠️ {from_currency}/{to_currency}: API 限流")
                    return None
                else:
                    self.log(f"⚠️ {from_currency}/{to_currency}: 未知响应格式")
                    return None
            else:
                self.log(f"❌ {from_currency}/{to_currency}: HTTP {response.status_code}")
                return None
        
        except Exception as e:
            self.log(f"❌ {from_currency}/{to_currency}: {e}")
            return None
    
    def fetch_stock(self, symbol):
        """
        获取股票数据
        """
        self.log(f"获取股票 {symbol}...")
        
        try:
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': symbol,
                'apikey': self.api_key
            }
            
            response = requests.get(self.base_url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'Time Series (Daily)' in data:
                    time_series = data['Time Series (Daily)']
                    self.log(f"✅ {symbol}: {len(time_series)} 条数据")
                    return time_series
                elif 'Information' in data:
                    self.log(f"⚠️ {symbol}: {data['Information']}")
                    return None
                elif 'Note' in data:
                    self.log(f"⚠️ {symbol}: API 限流")
                    return None
                else:
                    self.log(f"⚠️ {symbol}: 未知响应格式")
                    return None
            else:
                self.log(f"❌ {symbol}: HTTP {response.status_code}")
                return None
        
        except Exception as e:
            self.log(f"❌ {symbol}: {e}")
            return None
    
    def test_connection(self):
        """测试 API 连接"""
        self.log("=" * 80)
        self.log("测试 Alpha Vantage API 连接")
        self.log("=" * 80)
        
        # 测试股票数据
        self.log("\n【测试股票数据】")
        stock_data = self.fetch_stock('IBM')
        if stock_data:
            self.log(f"✓ 股票 API 可用")
        
        time.sleep(self.rate_limit_delay)
        
        # 测试大宗商品数据
        self.log("\n【测试大宗商品数据】")
        commodity_data = self.fetch_commodity('WTI', 'WTI 原油')
        if commodity_data:
            self.log(f"✓ 大宗商品 API 可用")
        
        time.sleep(self.rate_limit_delay)
        
        # 测试外汇数据
        self.log("\n【测试外汇数据】")
        forex_data = self.fetch_forex('USD', 'EUR')
        if forex_data:
            self.log(f"✓ 外汇 API 可用")
        
        self.log("\n" + "=" * 80)
        self.log("测试完成")
        self.log("=" * 80)
    
    def collect_commodities_backup(self):
        """
        采集大宗商品数据（作为 Yahoo Finance 备份）
        """
        self.log("=" * 80)
        self.log("采集大宗商品数据（Alpha Vantage）")
        self.log("=" * 80)
        
        commodities = {
            'WTI': 'WTI 原油',
            'BRENT': '布伦特原油',
            'NATURAL_GAS': '天然气',
            'COPPER': '铜',
            'ALUMINUM': '铝'
        }
        
        results = {}
        
        for function, name in commodities.items():
            data = self.fetch_commodity(function, name)
            if data:
                results[function.lower()] = {
                    'name': name,
                    'data': data
                }
            
            # 速率限制
            time.sleep(self.rate_limit_delay)
        
        # 保存数据
        if results:
            output_file = self.data_dir / "alpha_vantage_commodities.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            self.log(f"\n✓ 数据已保存到: {output_file}")
            self.log(f"✓ 共采集 {len(results)} 个商品")
        else:
            self.log("\n✗ 未采集到任何数据")

if __name__ == "__main__":
    collector = AlphaVantageCollector()
    
    # 测试连接
    collector.test_connection()
