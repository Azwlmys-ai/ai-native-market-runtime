#!/usr/bin/env python3
"""
Agent OKX Trader - OKX 加密货币交易
职责：基于 Polymarket 加密货币预测市场，在 OKX 执行对冲交易
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

class AgentOKXTrader:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 支持的币种
        self.supported_coins = ['BTC', 'ETH', 'BNB', 'SOL']
        
        # 币种别名映射
        self.coin_aliases = {
            'BTC': ['btc', 'bitcoin'],
            'ETH': ['eth', 'ethereum'],
            'BNB': ['bnb', 'binance coin'],
            'SOL': ['sol', 'solana']
        }
        
        # 交易阈值
        self.min_price_diff = 0.05  # 5% 价差
        self.min_liquidity = 10000  # $10k 最低流动性
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent OKX Trader] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"agent_okx_trader_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_data(self):
        """加载市场数据"""
        data_file = self.data_dir / "latest_data.json"
        
        if not data_file.exists():
            self.log("⚠️ 无市场数据")
            return None
        
        try:
            with open(data_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.log(f"❌ 加载数据失败: {e}")
            return None
    
    def find_crypto_arbitrage(self, data):
        """寻找加密货币套利机会"""
        polymarket_markets = data.get('polymarket_markets', [])
        okx_raw = data.get('okx', {})
        okx_data_list = okx_raw.get('data', [])
        
        # 转换为字典格式
        okx_data = {}
        for item in okx_data_list:
            symbol = item.get('symbol')
            okx_data[symbol] = item
        
        signals = []
        
        # 遍历 Polymarket 加密货币市场
        for market in polymarket_markets:
            question = market.get('question', '').lower()
            
            # 识别加密货币价格预测市场
            for coin in self.supported_coins:
                # 检查币种别名
                coin_found = False
                for alias in self.coin_aliases.get(coin, []):
                    if alias in question:
                        coin_found = True
                        break
                
                if coin_found and ('price' in question or 'hit' in question):
                    signal = self.analyze_crypto_market(market, coin, okx_data)
                    if signal:
                        signals.append(signal)
                    break  # 避免重复匹配
        
        return signals
    
    def analyze_crypto_market(self, market, coin, okx_data):
        """分析单个加密货币市场"""
        question = market.get('question', '')
        outcomes = market.get('outcomes', [])
        outcome_prices = market.get('outcome_prices', [])
        liquidity = market.get('liquidity', 0)
        
        # 检查流动性
        if liquidity < self.min_liquidity:
            return None
        
        # 获取 OKX 现货价格
        coin_data = okx_data.get(coin, {})
        okx_price = coin_data.get('spot_price')
        
        if not okx_price:
            return None
        
        # 解析 Polymarket 隐含价格
        # 例如: "Will Bitcoin hit $150k by Dec 2026?"
        # 需要从问题中提取目标价格
        target_price = self.extract_target_price(question)
        
        if not target_price:
            return None
        
        # 计算套利机会
        # 如果 OKX 现货价格远低于目标价格，且 Polymarket YES 价格高
        # 可以做空 Polymarket YES，做多 OKX 现货
        
        if len(outcomes) == 2 and len(outcome_prices) == 2:
            yes_price = outcome_prices[0] if outcomes[0].upper() == 'YES' else outcome_prices[1]
            
            # 计算隐含概率 vs 实际价格差距
            price_ratio = okx_price / target_price
            
            # 如果当前价格远低于目标（< 50%），但 YES 价格高（> 0.3）
            # 说明市场过于乐观
            if price_ratio < 0.5 and yes_price > 0.3:
                ev = ((1 - yes_price) / yes_price - 1) * 100  # 简化 EV 计算
                
                return {
                    'market_id': market.get('slug'),
                    'market_name': question,
                    'market_type': 'Crypto_Arbitrage',
                    'strategy': 'OKX_Polymarket_Hedge',
                    'coin': coin,
                    'polymarket_direction': 'NO',  # 做空 Polymarket YES
                    'polymarket_price': yes_price,
                    'okx_action': 'BUY',  # 做多 OKX 现货（可选）
                    'okx_price': okx_price,
                    'target_price': target_price,
                    'price_ratio': price_ratio,
                    'liquidity': liquidity,
                    'confidence': 75,
                    'position_size': 0.15,
                    'expected_value': ev,
                    'data_sources': [
                        f'OKX 现货价格 API',
                        f'Polymarket 市场数据',
                        f'目标价格分析'
                    ],
                    'logic_chain': [
                        f'{coin} 当前价格 ${okx_price:,.0f}',
                        f'目标价格 ${target_price:,.0f}',
                        f'价格比例 {price_ratio*100:.1f}%（远低于 50%）',
                        f'Polymarket YES 价格 {yes_price:.2f}（隐含概率 {yes_price*100:.1f}%）',
                        f'市场过于乐观，做空 YES 有利',
                        f'EV: {ev:.2f}%'
                    ],
                    'reason': f'{coin} 当前 ${okx_price:,.0f}，目标 ${target_price:,.0f}（{price_ratio*100:.1f}%），Polymarket YES {yes_price:.2f} 过高，EV {ev:.2f}%'
                }
        
        return None
    
    def extract_target_price(self, question):
        """从问题中提取目标价格"""
        import re
        
        # 匹配 $1m, $100k, $150,000 等格式
        patterns = [
            (r'\$(\d+)m\b', 1000000),  # $1m
            (r'\$(\d+)k\b', 1000),      # $100k
            (r'\$(\d{1,3}(?:,\d{3})+)', 1),  # $150,000
            (r'\$(\d+)', 1),            # $100
        ]
        
        for pattern, multiplier in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                value = float(value_str) * multiplier
                return value
        
        return None
    
    def run(self):
        """主流程"""
        self.log("=" * 60)
        self.log("开始 OKX 加密货币套利分析")
        
        # 加载数据
        data = self.load_data()
        if not data:
            self.log("❌ 无数据")
            return
        
        # 寻找套利机会
        signals = self.find_crypto_arbitrage(data)
        
        self.log(f"📊 发现 {len(signals)} 个 OKX 套利机会")
        
        # 保存信号
        if signals:
            output_file = self.data_dir / "okx_arbitrage_signals.json"
            with open(output_file, 'w') as f:
                json.dump(signals, f, indent=2, ensure_ascii=False)
            
            self.log(f"✅ 信号已保存到 {output_file}")
        
        self.log("=" * 60)

def main():
    agent = AgentOKXTrader()
    agent.run()

if __name__ == "__main__":
    main()
