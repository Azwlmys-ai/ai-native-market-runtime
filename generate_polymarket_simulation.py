#!/usr/bin/env python3
"""
生成 Polymarket 模拟历史数据
由于 API 限制，基于当前市场数据生成 3-4 月的模拟价格历史
"""

import json
import random
from pathlib import Path
from datetime import datetime, timedelta

class PolymarketSimulator:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.historical_dir = self.base_dir / "data" / "historical"
        self.historical_dir.mkdir(parents=True, exist_ok=True)
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def generate_price_history(self, initial_price, days=60, volatility=0.05):
        """生成价格历史（随机游走）"""
        prices = []
        current_price = initial_price
        
        start_date = datetime(2026, 3, 1)
        
        for hour in range(days * 24):
            timestamp = start_date + timedelta(hours=hour)
            
            # 随机游走
            change = random.gauss(0, volatility)
            current_price = max(0.01, min(0.99, current_price + change))
            
            prices.append({
                'timestamp': timestamp.isoformat(),
                'price': round(current_price, 4),
                'volume': random.randint(100, 10000)
            })
        
        return prices
    
    def create_simulated_markets(self):
        """创建模拟市场数据"""
        self.log("=" * 80)
        self.log("生成 Polymarket 模拟历史数据")
        self.log("=" * 80)
        
        markets = []
        
        # 1. 加密货币价格预测市场
        crypto_markets = [
            {
                'id': 'btc_100k_april',
                'question': 'Will Bitcoin hit $100k by April 30, 2026?',
                'category': 'crypto',
                'initial_price': 0.35,
                'volatility': 0.08
            },
            {
                'id': 'eth_5k_april',
                'question': 'Will Ethereum hit $5k by April 30, 2026?',
                'category': 'crypto',
                'initial_price': 0.25,
                'volatility': 0.10
            },
            {
                'id': 'btc_50k_march',
                'question': 'Will Bitcoin drop below $50k in March 2026?',
                'category': 'crypto',
                'initial_price': 0.15,
                'volatility': 0.12
            },
            {
                'id': 'sol_200_april',
                'question': 'Will Solana hit $200 by April 30, 2026?',
                'category': 'crypto',
                'initial_price': 0.40,
                'volatility': 0.15
            }
        ]
        
        # 2. NBA 季后赛市场
        nba_markets = [
            {
                'id': 'thunder_finals_2026',
                'question': 'Will the Oklahoma City Thunder win the 2026 NBA Finals?',
                'category': 'sports',
                'initial_price': 0.28,
                'volatility': 0.05
            },
            {
                'id': 'cavaliers_finals_2026',
                'question': 'Will the Cleveland Cavaliers win the 2026 NBA Finals?',
                'category': 'sports',
                'initial_price': 0.22,
                'volatility': 0.06
            },
            {
                'id': 'knicks_finals_2026',
                'question': 'Will the New York Knicks win the 2026 NBA Finals?',
                'category': 'sports',
                'initial_price': 0.18,
                'volatility': 0.07
            }
        ]
        
        # 3. NHL 季后赛市场
        nhl_markets = [
            {
                'id': 'hurricanes_cup_2026',
                'question': 'Will the Carolina Hurricanes win the 2026 NHL Stanley Cup?',
                'category': 'sports',
                'initial_price': 0.15,
                'volatility': 0.08
            },
            {
                'id': 'avalanche_cup_2026',
                'question': 'Will the Colorado Avalanche win the 2026 NHL Stanley Cup?',
                'category': 'sports',
                'initial_price': 0.12,
                'volatility': 0.09
            }
        ]
        
        # 4. 政治市场
        politics_markets = [
            {
                'id': 'trump_impeachment_2026',
                'question': 'Will Trump be impeached in 2026?',
                'category': 'politics',
                'initial_price': 0.08,
                'volatility': 0.03
            },
            {
                'id': 'vance_2028',
                'question': 'Will JD Vance win the 2028 US Presidential Election?',
                'category': 'politics',
                'initial_price': 0.22,
                'volatility': 0.04
            }
        ]
        
        # 5. 经济市场
        economy_markets = [
            {
                'id': 'fed_rate_cut_q2',
                'question': 'Will the Fed cut rates in Q2 2026?',
                'category': 'economy',
                'initial_price': 0.65,
                'volatility': 0.06
            },
            {
                'id': 'recession_2026',
                'question': 'Will the US enter recession in 2026?',
                'category': 'economy',
                'initial_price': 0.30,
                'volatility': 0.05
            }
        ]
        
        # 生成所有市场
        all_markets = crypto_markets + nba_markets + nhl_markets + politics_markets + economy_markets
        
        self.log(f"\n生成 {len(all_markets)} 个市场的价格历史...")
        
        for market in all_markets:
            self.log(f"  📊 {market['question'][:60]}...")
            
            # 生成价格历史
            price_history = self.generate_price_history(
                initial_price=market['initial_price'],
                days=60,
                volatility=market['volatility']
            )
            
            market['price_history'] = price_history
            market['current_price'] = price_history[-1]['price']
            
            markets.append(market)
            
            self.log(f"     ✅ 生成 {len(price_history)} 条价格记录")
        
        # 保存数据
        self.save_data(markets)
        
        return markets
    
    def save_data(self, markets):
        """保存数据"""
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
            category = market['category']
            if category not in categories:
                categories[category] = []
            categories[category].append(market)
        
        self.log("\n按类别统计:")
        for category, markets_list in sorted(categories.items()):
            self.log(f"  {category}: {len(markets_list)} 个市场")
        
        # 价格历史统计
        total_prices = sum(len(m['price_history']) for m in markets)
        avg_prices = total_prices / len(markets) if markets else 0
        
        self.log(f"\n价格历史统计:")
        self.log(f"  总价格记录: {total_prices} 条")
        self.log(f"  平均每市场: {avg_prices:.1f} 条")
        
        # 示例市场
        self.log("\n示例市场:")
        for i, market in enumerate(markets[:5]):
            question = market['question']
            current = market['current_price']
            initial = market['initial_price']
            change = (current - initial) / initial * 100
            self.log(f"  {i+1}. {question[:60]}...")
            self.log(f"     初始: {initial:.2f}, 当前: {current:.2f}, 变化: {change:+.1f}%")

def main():
    simulator = PolymarketSimulator()
    simulator.create_simulated_markets()

if __name__ == "__main__":
    main()
