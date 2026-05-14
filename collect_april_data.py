#!/usr/bin/env python3
"""
采集 2026 年 4 月份历史数据
"""

import json
import time
from pathlib import Path
from datetime import datetime, timedelta
import requests

class AprilDataCollector:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.historical_dir = self.base_dir / "data" / "historical"
        self.historical_dir.mkdir(parents=True, exist_ok=True)
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def collect_okx_klines(self, symbol, start_date, end_date):
        """采集 OKX K 线数据"""
        self.log(f"采集 {symbol} K 线数据...")
        
        url = "https://www.okx.com/api/v5/market/history-candles"
        
        # 转换为时间戳（毫秒）
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        
        all_klines = []
        current_ts = end_ts
        
        while current_ts > start_ts:
            params = {
                "instId": f"{symbol}-USDT",
                "bar": "1H",  # 1 小时 K 线
                "after": current_ts,
                "limit": 100
            }
            
            try:
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                
                if data.get("code") != "0":
                    self.log(f"⚠️ API 错误: {data.get('msg')}")
                    break
                
                klines = data.get("data", [])
                
                if not klines:
                    break
                
                # 转换格式
                for k in klines:
                    timestamp = int(k[0])
                    if timestamp < start_ts:
                        continue
                    
                    all_klines.append({
                        "timestamp": datetime.fromtimestamp(timestamp / 1000).isoformat(),
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5])
                    })
                
                # 更新时间戳
                current_ts = int(klines[-1][0]) - 1
                
                self.log(f"  已采集 {len(all_klines)} 条")
                time.sleep(0.2)  # 避免频率限制
                
            except Exception as e:
                self.log(f"⚠️ 采集失败: {e}")
                break
        
        # 按时间排序
        all_klines.sort(key=lambda x: x["timestamp"])
        
        # 保存
        output_file = self.historical_dir / f"okx_{symbol}_USDT_klines_april_2026.json"
        with open(output_file, 'w') as f:
            json.dump(all_klines, f, indent=2)
        
        self.log(f"✅ {symbol} K 线数据已保存: {len(all_klines)} 条")
        return len(all_klines)
    
    def collect_okx_funding_rate(self, symbol, start_date, end_date):
        """采集 OKX 资金费率"""
        self.log(f"采集 {symbol} 资金费率...")
        
        url = "https://www.okx.com/api/v5/public/funding-rate-history"
        
        # 转换为时间戳（毫秒）
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        
        all_rates = []
        current_ts = end_ts
        
        while current_ts > start_ts:
            params = {
                "instId": f"{symbol}-USDT-SWAP",
                "after": current_ts,
                "limit": 100
            }
            
            try:
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                
                if data.get("code") != "0":
                    self.log(f"⚠️ API 错误: {data.get('msg')}")
                    break
                
                rates = data.get("data", [])
                
                if not rates:
                    break
                
                # 转换格式
                for r in rates:
                    timestamp = int(r["fundingTime"])
                    if timestamp < start_ts:
                        continue
                    
                    all_rates.append({
                        "timestamp": datetime.fromtimestamp(timestamp / 1000).isoformat(),
                        "funding_rate": float(r["fundingRate"]),
                        "realized_rate": float(r.get("realizedRate", 0))
                    })
                
                # 更新时间戳
                current_ts = int(rates[-1]["fundingTime"]) - 1
                
                self.log(f"  已采集 {len(all_rates)} 条")
                time.sleep(0.2)
                
            except Exception as e:
                self.log(f"⚠️ 采集失败: {e}")
                break
        
        # 按时间排序
        all_rates.sort(key=lambda x: x["timestamp"])
        
        # 保存
        output_file = self.historical_dir / f"okx_{symbol}_USDT_SWAP_funding_rate_april_2026.json"
        with open(output_file, 'w') as f:
            json.dump(all_rates, f, indent=2)
        
        self.log(f"✅ {symbol} 资金费率已保存: {len(all_rates)} 条")
        return len(all_rates)
    
    def run(self):
        """运行采集"""
        self.log("=" * 80)
        self.log("开始采集 2026 年 4 月份数据")
        self.log("=" * 80)
        
        start_date = "2026-04-01"
        end_date = "2026-04-30"
        
        # 采集 K 线数据
        for symbol in ["BTC", "ETH", "BNB", "SOL"]:
            self.collect_okx_klines(symbol, start_date, end_date)
        
        # 采集资金费率
        for symbol in ["BTC", "ETH"]:
            self.collect_okx_funding_rate(symbol, start_date, end_date)
        
        self.log("\n" + "=" * 80)
        self.log("✅ 4 月份数据采集完成")
        self.log("=" * 80)

def main():
    collector = AprilDataCollector()
    collector.run()

if __name__ == "__main__":
    main()
