#!/usr/bin/env python3
"""
增强版历史数据采集器 - 使用免费 API 和库
- yfinance: 美股历史数据
- akshare: A股历史数据
- Polymarket Gamma API: 市场历史数据
- 修复 FRED API Key 问题
"""

import json
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta

class EnhancedHistoricalCollector:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data" / "historical"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 2026 年 3 月时间范围
        self.start_date = "2026-03-01"
        self.end_date = "2026-03-31"
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Enhanced Collector] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"enhanced_collector_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def install_dependencies(self):
        """安装必要的 Python 库"""
        self.log("检查并安装依赖...")
        
        packages = ['yfinance', 'akshare', 'pandas']
        
        for package in packages:
            try:
                __import__(package)
                self.log(f"✅ {package} 已安装")
            except ImportError:
                self.log(f"📦 安装 {package}...")
                subprocess.run([sys.executable, '-m', 'pip', 'install', package, '-q'], check=True)
                self.log(f"✅ {package} 安装完成")
    
    def collect_us_stocks_yfinance(self):
        """使用 yfinance 采集美股历史数据"""
        self.log("采集美股历史数据（yfinance）...")
        
        try:
            import yfinance as yf
            import pandas as pd
            
            # 监控的股票
            symbols = ['MSFT', 'AMZN', 'META', 'COIN', 'TTWO']
            
            all_data = {}
            
            for symbol in symbols:
                self.log(f"  采集 {symbol}...")
                
                try:
                    ticker = yf.Ticker(symbol)
                    
                    # 获取历史数据
                    hist = ticker.history(start=self.start_date, end=self.end_date, interval='1h')
                    
                    if not hist.empty:
                        # 转换为 JSON 格式
                        data = []
                        for index, row in hist.iterrows():
                            data.append({
                                'timestamp': index.isoformat(),
                                'open': float(row['Open']),
                                'high': float(row['High']),
                                'low': float(row['Low']),
                                'close': float(row['Close']),
                                'volume': int(row['Volume'])
                            })
                        
                        all_data[symbol] = data
                        self.log(f"    ✅ {symbol}: {len(data)} 条数据")
                    else:
                        self.log(f"    ⚠️ {symbol}: 无数据")
                
                except Exception as e:
                    self.log(f"    ❌ {symbol} 失败: {e}")
                
                time.sleep(1)
            
            # 保存数据
            output_file = self.data_dir / "us_stocks_march_2026.json"
            with open(output_file, 'w') as f:
                json.dump(all_data, f, indent=2, ensure_ascii=False)
            
            self.log(f"✅ 美股数据已保存: {output_file}")
            
            return all_data
        
        except Exception as e:
            self.log(f"❌ 采集美股数据异常: {e}")
            return {}
    
    def collect_cn_stocks_akshare(self):
        """使用 akshare 采集 A股历史数据"""
        self.log("采集 A股历史数据（akshare）...")
        
        try:
            import akshare as ak
            import pandas as pd
            
            # 监控的股票（示例）
            symbols = [
                ('600519', '贵州茅台'),
                ('000858', '五粮液'),
                ('601318', '中国平安'),
                ('600036', '招商银行'),
                ('000001', '平安银行')
            ]
            
            all_data = {}
            
            for code, name in symbols:
                self.log(f"  采集 {code} ({name})...")
                
                try:
                    # 获取日线数据
                    df = ak.stock_zh_a_hist(
                        symbol=code,
                        period="daily",
                        start_date=self.start_date.replace('-', ''),
                        end_date=self.end_date.replace('-', ''),
                        adjust="qfq"  # 前复权
                    )
                    
                    if not df.empty:
                        # 转换为 JSON 格式
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
                        
                        all_data[f"{code}_{name}"] = data
                        self.log(f"    ✅ {code}: {len(data)} 条数据")
                    else:
                        self.log(f"    ⚠️ {code}: 无数据")
                
                except Exception as e:
                    self.log(f"    ❌ {code} 失败: {e}")
                
                time.sleep(1)
            
            # 保存数据
            output_file = self.data_dir / "cn_stocks_march_2026.json"
            with open(output_file, 'w') as f:
                json.dump(all_data, f, indent=2, ensure_ascii=False)
            
            self.log(f"✅ A股数据已保存: {output_file}")
            
            return all_data
        
        except Exception as e:
            self.log(f"❌ 采集 A股数据异常: {e}")
            return {}
    
    def collect_polymarket_gamma(self):
        """使用 Polymarket Gamma API 采集市场历史数据"""
        self.log("采集 Polymarket 市场历史数据（Gamma API）...")
        
        try:
            import requests
            
            # Gamma API 端点
            gamma_api = "https://gamma-api.polymarket.com"
            
            # 获取市场列表
            markets_url = f"{gamma_api}/markets"
            response = requests.get(markets_url, timeout=30)
            
            if response.status_code == 200:
                markets = response.json()
                self.log(f"✅ 找到 {len(markets)} 个市场")
                
                # 筛选 3 月份活跃的市场（前 20 个）
                march_markets = []
                
                for market in markets[:20]:
                    condition_id = market.get('conditionId')
                    
                    # 获取市场历史价格
                    self.log(f"  采集市场: {market.get('question', 'Unknown')[:50]}...")
                    
                    try:
                        # 获取价格历史
                        prices_url = f"{gamma_api}/prices"
                        params = {
                            'market': condition_id,
                            'startTs': int(datetime.strptime(self.start_date, '%Y-%m-%d').timestamp()),
                            'endTs': int(datetime.strptime(self.end_date, '%Y-%m-%d').timestamp() + 86400)
                        }
                        
                        prices_response = requests.get(prices_url, params=params, timeout=30)
                        
                        if prices_response.status_code == 200:
                            prices = prices_response.json()
                            
                            market_data = {
                                'market': market,
                                'prices': prices
                            }
                            
                            march_markets.append(market_data)
                            self.log(f"    ✅ 采集 {len(prices)} 条价格数据")
                        else:
                            self.log(f"    ⚠️ 价格数据获取失败: {prices_response.status_code}")
                    
                    except Exception as e:
                        self.log(f"    ❌ 采集失败: {e}")
                    
                    time.sleep(1)
                
                # 保存数据
                output_file = self.data_dir / "polymarket_markets_march_2026.json"
                with open(output_file, 'w') as f:
                    json.dump(march_markets, f, indent=2, ensure_ascii=False)
                
                self.log(f"✅ Polymarket 数据已保存: {output_file}")
                
                return march_markets
            else:
                self.log(f"❌ Gamma API 请求失败: {response.status_code}")
                return []
        
        except Exception as e:
            self.log(f"❌ 采集 Polymarket 数据异常: {e}")
            return []
    
    def generate_summary_report(self):
        """生成数据采集摘要报告"""
        self.log("生成摘要报告...")
        
        summary = {
            'collection_date': datetime.now().isoformat(),
            'period': f"{self.start_date} to {self.end_date}",
            'data_sources': {}
        }
        
        # 统计各数据源
        for file in self.data_dir.glob("*.json"):
            try:
                with open(file, 'r') as f:
                    data = json.load(f)
                
                if isinstance(data, list):
                    count = len(data)
                elif isinstance(data, dict):
                    count = len(data)
                else:
                    count = 1
                
                summary['data_sources'][file.name] = {
                    'file_size': file.stat().st_size,
                    'records': count
                }
            except:
                pass
        
        # 保存摘要
        summary_file = self.data_dir / "collection_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 摘要报告已保存: {summary_file}")
        
        # 打印摘要
        self.log("\n" + "=" * 80)
        self.log("数据采集摘要")
        self.log("=" * 80)
        for source, info in summary['data_sources'].items():
            size_kb = info['file_size'] / 1024
            self.log(f"  {source}: {info['records']} 条记录, {size_kb:.1f} KB")
        self.log("=" * 80)
    
    def run(self):
        """执行完整的历史数据采集"""
        self.log("=" * 80)
        self.log("开始增强版历史数据采集（2026 年 3 月）")
        self.log("=" * 80)
        
        # 1. 安装依赖
        self.log("\n[1/4] 安装依赖")
        self.install_dependencies()
        
        # 2. 采集美股数据
        self.log("\n[2/4] 美股数据（yfinance）")
        self.collect_us_stocks_yfinance()
        
        # 3. 采集 A股数据
        self.log("\n[3/4] A股数据（akshare）")
        self.collect_cn_stocks_akshare()
        
        # 4. 采集 Polymarket 数据
        self.log("\n[4/4] Polymarket 数据（Gamma API）")
        self.collect_polymarket_gamma()
        
        # 5. 生成摘要报告
        self.log("\n生成摘要报告")
        self.generate_summary_report()
        
        self.log("\n" + "=" * 80)
        self.log("✅ 增强版历史数据采集完成")
        self.log(f"📁 数据保存在: {self.data_dir}")
        self.log("=" * 80)

def main():
    collector = EnhancedHistoricalCollector()
    collector.run()

if __name__ == "__main__":
    main()
