#!/usr/bin/env python3
"""
历史数据采集器 - 采集 2026 年 3 月份的所有数据
- Polymarket 市场数据（K线、交易量、价格）
- OKX 加密货币数据（K线、交易量、资金费率）
- 美股数据（价格、交易量）
- A股数据（价格、交易量）
- 新闻数据（BBC、Google News）
- 宏观数据（FRED 利率、汇率）
"""

import json
import time
import requests
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from _paths import get_base_dir

class HistoricalDataCollector:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data" / "historical"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 2026 年 3 月时间范围
        self.start_date = datetime(2026, 3, 1)
        self.end_date = datetime(2026, 3, 31, 23, 59, 59)
        
        # API 配置
        self.polymarket_api = "https://clob.polymarket.com"
        self.okx_api = "https://www.okx.com"
        self.fred_api_key = "YOUR_FRED_API_KEY"  # 需要申请
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Historical Collector] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"historical_collector_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def collect_polymarket_markets(self):
        """采集 Polymarket 市场列表"""
        self.log("采集 Polymarket 市场列表...")
        
        try:
            # 获取所有市场
            url = f"{self.polymarket_api}/markets"
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                markets = response.json()
                
                # 筛选 3 月份活跃的市场
                march_markets = []
                for market in markets:
                    # 检查市场是否在 3 月份活跃
                    created_at = market.get('created_at')
                    if created_at:
                        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        if created_date <= self.end_date:
                            march_markets.append(market)
                
                self.log(f"✅ 找到 {len(march_markets)} 个 3 月份市场")
                
                # 保存市场列表
                output_file = self.data_dir / "polymarket_markets_march_2026.json"
                with open(output_file, 'w') as f:
                    json.dump(march_markets, f, indent=2, ensure_ascii=False)
                
                return march_markets
            else:
                self.log(f"❌ 获取市场列表失败: {response.status_code}")
                return []
        
        except Exception as e:
            self.log(f"❌ 采集市场列表异常: {e}")
            return []
    
    def collect_polymarket_trades(self, market_id):
        """采集单个市场的交易历史"""
        try:
            url = f"{self.polymarket_api}/trades"
            params = {
                "market": market_id,
                "start_ts": int(self.start_date.timestamp()),
                "end_ts": int(self.end_date.timestamp())
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                trades = response.json()
                return trades
            else:
                return []
        
        except Exception as e:
            self.log(f"⚠️ 采集市场 {market_id} 交易失败: {e}")
            return []
    
    def calculate_klines(self, trades, interval='1h'):
        """从交易数据计算 K 线"""
        if not trades:
            return []
        
        # 按时间分组
        klines = defaultdict(lambda: {
            'open': None,
            'high': 0,
            'low': float('inf'),
            'close': None,
            'volume': 0,
            'trades': 0
        })
        
        # 时间间隔（小时）
        interval_hours = 1 if interval == '1h' else 24
        
        for trade in trades:
            timestamp = trade.get('timestamp', 0)
            price = float(trade.get('price', 0))
            size = float(trade.get('size', 0))
            
            # 计算时间桶
            dt = datetime.fromtimestamp(timestamp)
            bucket = dt.replace(minute=0, second=0, microsecond=0)
            if interval == '1d':
                bucket = bucket.replace(hour=0)
            
            bucket_key = bucket.isoformat()
            
            # 更新 K 线数据
            if klines[bucket_key]['open'] is None:
                klines[bucket_key]['open'] = price
            
            klines[bucket_key]['high'] = max(klines[bucket_key]['high'], price)
            klines[bucket_key]['low'] = min(klines[bucket_key]['low'], price)
            klines[bucket_key]['close'] = price
            klines[bucket_key]['volume'] += size
            klines[bucket_key]['trades'] += 1
        
        # 转换为列表
        result = []
        for timestamp, data in sorted(klines.items()):
            result.append({
                'timestamp': timestamp,
                'open': data['open'],
                'high': data['high'],
                'low': data['low'],
                'close': data['close'],
                'volume': data['volume'],
                'trades': data['trades']
            })
        
        return result
    
    def calculate_bollinger_bands(self, klines, period=20, std_dev=2):
        """计算布林线"""
        if len(klines) < period:
            return []
        
        result = []
        
        for i in range(len(klines)):
            if i < period - 1:
                result.append({
                    'timestamp': klines[i]['timestamp'],
                    'middle': None,
                    'upper': None,
                    'lower': None
                })
                continue
            
            # 计算移动平均
            prices = [klines[j]['close'] for j in range(i - period + 1, i + 1)]
            mean = sum(prices) / period
            
            # 计算标准差
            variance = sum((p - mean) ** 2 for p in prices) / period
            std = variance ** 0.5
            
            result.append({
                'timestamp': klines[i]['timestamp'],
                'middle': mean,
                'upper': mean + std_dev * std,
                'lower': mean - std_dev * std
            })
        
        return result
    
    def collect_okx_klines(self, symbol='BTC-USDT', interval='1H'):
        """采集 OKX K 线数据"""
        self.log(f"采集 OKX {symbol} K 线数据...")
        
        try:
            url = f"{self.okx_api}/api/v5/market/history-candles"
            
            # OKX API 限制每次最多 100 条
            all_klines = []
            current_end = int(self.end_date.timestamp() * 1000)
            
            while True:
                params = {
                    'instId': symbol,
                    'bar': interval,
                    'after': current_end,
                    'limit': 100
                }
                
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('code') == '0':
                        klines = data.get('data', [])
                        
                        if not klines:
                            break
                        
                        # 筛选 3 月份数据
                        for kline in klines:
                            timestamp = int(kline[0]) / 1000
                            if self.start_date.timestamp() <= timestamp <= self.end_date.timestamp():
                                all_klines.append({
                                    'timestamp': datetime.fromtimestamp(timestamp).isoformat(),
                                    'open': float(kline[1]),
                                    'high': float(kline[2]),
                                    'low': float(kline[3]),
                                    'close': float(kline[4]),
                                    'volume': float(kline[5]),
                                    'volume_currency': float(kline[6])
                                })
                        
                        # 更新结束时间
                        current_end = int(klines[-1][0])
                        
                        # 如果已经到达 3 月 1 日之前，停止
                        if timestamp < self.start_date.timestamp():
                            break
                        
                        time.sleep(0.2)  # 避免触发限流
                    else:
                        self.log(f"❌ OKX API 错误: {data.get('msg')}")
                        break
                else:
                    self.log(f"❌ OKX API 请求失败: {response.status_code}")
                    break
            
            self.log(f"✅ 采集 {len(all_klines)} 条 {symbol} K 线数据")
            
            # 保存数据
            output_file = self.data_dir / f"okx_{symbol.replace('-', '_')}_klines_march_2026.json"
            with open(output_file, 'w') as f:
                json.dump(all_klines, f, indent=2, ensure_ascii=False)
            
            return all_klines
        
        except Exception as e:
            self.log(f"❌ 采集 OKX K 线异常: {e}")
            return []
    
    def collect_okx_funding_rate(self, symbol='BTC-USDT-SWAP'):
        """采集 OKX 资金费率历史"""
        self.log(f"采集 OKX {symbol} 资金费率...")
        
        try:
            url = f"{self.okx_api}/api/v5/public/funding-rate-history"
            
            all_rates = []
            current_end = int(self.end_date.timestamp() * 1000)
            
            while True:
                params = {
                    'instId': symbol,
                    'after': current_end,
                    'limit': 100
                }
                
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('code') == '0':
                        rates = data.get('data', [])
                        
                        if not rates:
                            break
                        
                        # 筛选 3 月份数据
                        for rate in rates:
                            timestamp = int(rate['fundingTime']) / 1000
                            if self.start_date.timestamp() <= timestamp <= self.end_date.timestamp():
                                all_rates.append({
                                    'timestamp': datetime.fromtimestamp(timestamp).isoformat(),
                                    'funding_rate': float(rate['fundingRate']),
                                    'realized_rate': float(rate.get('realizedRate', 0))
                                })
                        
                        # 更新结束时间
                        current_end = int(rates[-1]['fundingTime'])
                        
                        # 如果已经到达 3 月 1 日之前，停止
                        if timestamp < self.start_date.timestamp():
                            break
                        
                        time.sleep(0.2)
                    else:
                        self.log(f"❌ OKX API 错误: {data.get('msg')}")
                        break
                else:
                    self.log(f"❌ OKX API 请求失败: {response.status_code}")
                    break
            
            self.log(f"✅ 采集 {len(all_rates)} 条资金费率数据")
            
            # 保存数据
            output_file = self.data_dir / f"okx_{symbol.replace('-', '_')}_funding_rate_march_2026.json"
            with open(output_file, 'w') as f:
                json.dump(all_rates, f, indent=2, ensure_ascii=False)
            
            return all_rates
        
        except Exception as e:
            self.log(f"❌ 采集资金费率异常: {e}")
            return []
    
    def collect_fred_data(self, series_id='DFF'):
        """采集 FRED 宏观数据（联邦基金利率）"""
        self.log(f"采集 FRED {series_id} 数据...")
        
        try:
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                'series_id': series_id,
                'api_key': self.fred_api_key,
                'file_type': 'json',
                'observation_start': self.start_date.strftime('%Y-%m-%d'),
                'observation_end': self.end_date.strftime('%Y-%m-%d')
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                observations = data.get('observations', [])
                
                result = []
                for obs in observations:
                    if obs.get('value') != '.':
                        result.append({
                            'date': obs['date'],
                            'value': float(obs['value'])
                        })
                
                self.log(f"✅ 采集 {len(result)} 条 {series_id} 数据")
                
                # 保存数据
                output_file = self.data_dir / f"fred_{series_id}_march_2026.json"
                with open(output_file, 'w') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                
                return result
            else:
                self.log(f"❌ FRED API 请求失败: {response.status_code}")
                return []
        
        except Exception as e:
            self.log(f"❌ 采集 FRED 数据异常: {e}")
            return []
    
    def collect_news_archive(self):
        """采集新闻存档（BBC RSS）"""
        self.log("采集新闻存档...")
        
        # 注意：RSS 通常只提供最近的新闻，历史新闻需要其他方式
        # 这里提供一个框架，实际需要使用新闻 API 或爬虫
        
        try:
            rss_urls = [
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                "https://feeds.bbci.co.uk/news/business/rss.xml",
                "https://feeds.bbci.co.uk/news/technology/rss.xml"
            ]
            
            all_news = []
            
            for rss_url in rss_urls:
                response = requests.get(rss_url, timeout=30)
                
                if response.status_code == 200:
                    # 简单解析（实际应该使用 feedparser）
                    self.log(f"✅ 获取 RSS: {rss_url}")
                    # 这里需要解析 XML 并筛选 3 月份的新闻
                    # 由于 RSS 只有最近新闻，这里只是示例
            
            self.log(f"⚠️ RSS 只提供最近新闻，无法获取 3 月份历史新闻")
            self.log("💡 建议使用 News API 或 Google News API 获取历史新闻")
            
            return all_news
        
        except Exception as e:
            self.log(f"❌ 采集新闻异常: {e}")
            return []
    
    def run(self):
        """执行完整的历史数据采集"""
        self.log("=" * 80)
        self.log("开始采集 2026 年 3 月份历史数据")
        self.log("=" * 80)
        
        # 1. Polymarket 市场数据
        self.log("\n[1/7] Polymarket 市场数据")
        markets = self.collect_polymarket_markets()
        
        # 采集前 10 个市场的交易数据（示例）
        self.log("\n采集市场交易数据（前 10 个市场）...")
        for i, market in enumerate(markets[:10]):
            market_id = market.get('id')
            self.log(f"  [{i+1}/10] 市场: {market.get('question', 'Unknown')}")
            
            trades = self.collect_polymarket_trades(market_id)
            
            if trades:
                # 计算 K 线
                klines_1h = self.calculate_klines(trades, interval='1h')
                klines_1d = self.calculate_klines(trades, interval='1d')
                
                # 计算布林线
                bollinger = self.calculate_bollinger_bands(klines_1d)
                
                # 保存数据
                market_data = {
                    'market': market,
                    'trades': trades,
                    'klines_1h': klines_1h,
                    'klines_1d': klines_1d,
                    'bollinger_bands': bollinger
                }
                
                output_file = self.data_dir / f"polymarket_market_{market_id}_march_2026.json"
                with open(output_file, 'w') as f:
                    json.dump(market_data, f, indent=2, ensure_ascii=False)
                
                self.log(f"    ✅ 保存 {len(trades)} 笔交易, {len(klines_1h)} 条 1h K线, {len(klines_1d)} 条 1d K线")
            
            time.sleep(1)  # 避免触发限流
        
        # 2. OKX 加密货币数据
        self.log("\n[2/7] OKX 加密货币数据")
        crypto_symbols = ['BTC-USDT', 'ETH-USDT', 'BNB-USDT', 'SOL-USDT']
        for symbol in crypto_symbols:
            self.collect_okx_klines(symbol, interval='1H')
            time.sleep(1)
        
        # 3. OKX 资金费率
        self.log("\n[3/7] OKX 资金费率")
        swap_symbols = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP']
        for symbol in swap_symbols:
            self.collect_okx_funding_rate(symbol)
            time.sleep(1)
        
        # 4. FRED 宏观数据
        self.log("\n[4/7] FRED 宏观数据")
        fred_series = [
            ('DFF', '联邦基金利率'),
            ('DEXUSEU', '美元/欧元汇率'),
            ('DEXCHUS', '人民币/美元汇率')
        ]
        for series_id, name in fred_series:
            self.log(f"  采集 {name}...")
            self.collect_fred_data(series_id)
            time.sleep(1)
        
        # 5. 新闻数据
        self.log("\n[5/7] 新闻数据")
        self.collect_news_archive()
        
        # 6. 美股数据（需要 API）
        self.log("\n[6/7] 美股数据")
        self.log("⚠️ 美股历史数据需要 API（如 Alpha Vantage、IEX Cloud）")
        self.log("💡 建议使用 yfinance 库获取历史数据")
        
        # 7. A股数据（需要 API）
        self.log("\n[7/7] A股数据")
        self.log("⚠️ A股历史数据需要 API（如东方财富、新浪财经）")
        self.log("💡 建议使用 akshare 库获取历史数据")
        
        self.log("\n" + "=" * 80)
        self.log("✅ 历史数据采集完成")
        self.log(f"📁 数据保存在: {self.data_dir}")
        self.log("=" * 80)

def main():
    collector = HistoricalDataCollector()
    collector.run()

if __name__ == "__main__":
    main()
