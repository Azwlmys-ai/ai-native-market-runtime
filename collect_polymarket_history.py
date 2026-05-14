#!/usr/bin/env python3
"""
采集 Polymarket 历史数据（3-4 月）
- 使用 Polymarket API
- 采集市场快照、价格历史
- 保存到 historical/ 目录
"""

import json
import requests
import time
from pathlib import Path
from datetime import datetime, timedelta

class PolymarketHistoryCollector:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.historical_dir = self.base_dir / "data" / "historical"
        self.historical_dir.mkdir(parents=True, exist_ok=True)
        
        self.api_base = "https://gamma-api.polymarket.com"
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def fetch_markets(self, limit=100, offset=0):
        """获取市场列表"""
        url = f"{self.api_base}/markets"
        params = {
            'limit': limit,
            'offset': offset,
            'closed': 'false'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.log(f"❌ 获取市场列表失败: {e}")
            return []
    
    def fetch_market_trades(self, condition_id, start_ts, end_ts):
        """获取市场交易历史"""
        url = f"{self.api_base}/trades"
        params = {
            'condition_id': condition_id,
            'start_ts': start_ts,
            'end_ts': end_ts
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.log(f"❌ 获取交易历史失败: {e}")
            return []
    
    def fetch_market_prices(self, token_id):
        """获取市场价格历史 - 使用正确的 API 端点"""
        # 尝试多个可能的端点
        endpoints = [
            f"{self.api_base}/prices-history?market={token_id}&interval=1h&fidelity=1",
            f"{self.api_base}/markets/{token_id}/prices",
            f"https://clob.polymarket.com/prices-history?market={token_id}",
        ]
        
        for url in endpoints:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    return response.json()
            except:
                continue
        
        return []
    
    def collect_march_april_data(self):
        """采集 3-4 月数据"""
        self.log("=" * 80)
        self.log("开始采集 Polymarket 历史数据（3-4 月）")
        self.log("=" * 80)
        
        # 时间范围
        march_start = int(datetime(2026, 3, 1).timestamp())
        april_end = int(datetime(2026, 4, 30, 23, 59, 59).timestamp())
        
        self.log(f"\n时间范围: 2026-03-01 至 2026-04-30")
        
        # 获取市场列表
        self.log("\n📊 获取市场列表...")
        all_markets = []
        offset = 0
        
        while True:
            markets = self.fetch_markets(limit=100, offset=offset)
            if not markets:
                break
            
            all_markets.extend(markets)
            self.log(f"  已获取 {len(all_markets)} 个市场...")
            
            offset += 100
            time.sleep(0.5)
            
            # 限制最多 500 个市场
            if len(all_markets) >= 500:
                break
        
        self.log(f"✅ 共获取 {len(all_markets)} 个市场")
        
        # 筛选相关市场（加密货币、体育、政治）
        self.log("\n🔍 筛选相关市场...")
        
        keywords = [
            'bitcoin', 'btc', 'ethereum', 'eth', 'crypto',
            'nba', 'nfl', 'nhl', 'mlb', 'soccer', 'football',
            'trump', 'biden', 'election', 'president',
            'stock', 'market', 'economy', 'fed', 'rate'
        ]
        
        relevant_markets = []
        for market in all_markets:
            question = market.get('question', '').lower()
            if any(kw in question for kw in keywords):
                relevant_markets.append(market)
        
        self.log(f"✅ 筛选出 {len(relevant_markets)} 个相关市场")
        
        # 采集每个市场的价格历史
        self.log("\n📈 采集价格历史...")
        
        markets_with_history = []
        for i, market in enumerate(relevant_markets[:100]):  # 限制 100 个
            market_id = market.get('id')
            question = market.get('question', '')
            
            self.log(f"  [{i+1}/{min(100, len(relevant_markets))}] {question[:60]}...")
            
            # 获取价格历史
            prices = self.fetch_market_prices(market_id)
            
            if prices:
                market['price_history'] = prices
                markets_with_history.append(market)
                self.log(f"    ✅ 获取 {len(prices)} 条价格记录")
            else:
                self.log(f"    ⚠️ 无价格历史")
            
            time.sleep(0.5)
        
        self.log(f"\n✅ 成功采集 {len(markets_with_history)} 个市场的价格历史")
        
        # 保存数据
        self.save_data(markets_with_history)
        
        return markets_with_history
    
    def save_data(self, markets):
        """保存数据"""
        # 保存完整数据
        output_file = self.historical_dir / "polymarket_markets_march_april_2026.json"
        
        with open(output_file, 'w') as f:
            json.dump(markets, f, indent=2, ensure_ascii=False)
        
        self.log(f"\n✅ 数据已保存: {output_file}")
        self.log(f"   文件大小: {output_file.stat().st_size / 1024:.1f} KB")
        
        # 生成统计报告
        self.generate_report(markets)
    
    def generate_report(self, markets):
        """生成统计报告"""
        self.log("\n" + "=" * 80)
        self.log("数据统计报告")
        self.log("=" * 80)
        
        # 按类别统计
        categories = {}
        for market in markets:
            question = market.get('question', '').lower()
            
            if any(kw in question for kw in ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto']):
                category = 'crypto'
            elif any(kw in question for kw in ['nba', 'nfl', 'nhl', 'mlb', 'soccer', 'football']):
                category = 'sports'
            elif any(kw in question for kw in ['trump', 'biden', 'election', 'president']):
                category = 'politics'
            elif any(kw in question for kw in ['stock', 'market', 'economy', 'fed', 'rate']):
                category = 'economy'
            else:
                category = 'other'
            
            if category not in categories:
                categories[category] = []
            categories[category].append(market)
        
        self.log("\n按类别统计:")
        for category, markets_list in sorted(categories.items()):
            self.log(f"  {category}: {len(markets_list)} 个市场")
        
        # 价格历史统计
        total_prices = sum(len(m.get('price_history', [])) for m in markets)
        avg_prices = total_prices / len(markets) if markets else 0
        
        self.log(f"\n价格历史统计:")
        self.log(f"  总价格记录: {total_prices} 条")
        self.log(f"  平均每市场: {avg_prices:.1f} 条")
        
        # 示例市场
        self.log("\n示例市场:")
        for i, market in enumerate(markets[:5]):
            question = market.get('question', '')
            prices = len(market.get('price_history', []))
            self.log(f"  {i+1}. {question[:60]}... ({prices} 条价格)")

def main():
    collector = PolymarketHistoryCollector()
    collector.collect_march_april_data()

if __name__ == "__main__":
    main()
