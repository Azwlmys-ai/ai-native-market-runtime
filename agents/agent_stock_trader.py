#!/usr/bin/env python3
"""
Agent Stock Trader - 美股/港股交易
职责：基于 Polymarket 公司相关预测市场，在股票市场执行对冲交易
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

class AgentStockTrader:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 公司-股票映射
        self.company_ticker_map = {
            # 游戏公司
            'Take-Two': 'TTWO',
            'Take Two': 'TTWO',
            'Rockstar': 'TTWO',  # Rockstar 是 Take-Two 子公司
            'GTA': 'TTWO',
            'Grand Theft Auto': 'TTWO',
            'Electronic Arts': 'EA',
            'EA': 'EA',
            'Activision': 'ATVI',
            'Blizzard': 'ATVI',
            
            # 科技公司
            'Apple': 'AAPL',
            'Microsoft': 'MSFT',
            'Google': 'GOOGL',
            'Alphabet': 'GOOGL',
            'Amazon': 'AMZN',
            'Meta': 'META',
            'Facebook': 'META',
            'Tesla': 'TSLA',
            'Nvidia': 'NVDA',
            'AMD': 'AMD',
            
            # 其他
            'Disney': 'DIS',
            'Netflix': 'NFLX',
            'Spotify': 'SPOT',
        }
        
        # 交易阈值
        self.min_liquidity = 10000  # $10k 最低流动性
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent Stock Trader] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"agent_stock_trader_{datetime.now().strftime('%Y%m%d')}.log"
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
    
    def find_stock_arbitrage(self, data):
        """寻找股票套利机会"""
        polymarket_markets = data.get('polymarket_markets', [])
        us_stocks = data.get('us_stocks', {})
        
        signals = []
        
        # 遍历 Polymarket 市场
        for market in polymarket_markets:
            question = market.get('question', '')
            
            # 识别公司相关市场
            for company, ticker in self.company_ticker_map.items():
                if company.lower() in question.lower():
                    signal = self.analyze_stock_market(market, company, ticker, us_stocks)
                    if signal:
                        signals.append(signal)
                    break  # 避免重复匹配
        
        return signals
    
    def analyze_stock_market(self, market, company, ticker, us_stocks):
        """分析单个股票市场"""
        question = market.get('question', '')
        outcomes = market.get('outcomes', [])
        outcome_prices = market.get('outcome_prices', [])
        liquidity = market.get('liquidity', 0)
        
        # 检查流动性
        if liquidity < self.min_liquidity:
            return None
        
        # 获取股票价格（支持两种数据格式）
        stock_price = None
        
        # 格式 1: us_stocks 是字典，ticker 作为 key
        if isinstance(us_stocks, dict):
            # 检查是否有 stocks 列表
            if 'stocks' in us_stocks:
                stocks_list = us_stocks['stocks']
                for stock in stocks_list:
                    if stock.get('symbol') == ticker:
                        stock_price = stock.get('price')
                        break
            # 或者直接是 ticker: data 格式
            elif ticker in us_stocks:
                stock_data = us_stocks[ticker]
                stock_price = stock_data.get('price')
        
        if not stock_price:
            return None
        
        # 分析策略
        # 例如: "GTA VI released before June 2026?"
        # 当前市场: YES 0.0055, NO 0.9945（市场预期延期）
        # 策略: 市场预期延期 → 做空 TTWO 股票（游戏延期对股价负面）
        
        if len(outcomes) == 2 and len(outcome_prices) == 2:
            yes_price = outcome_prices[0] if outcomes[0].upper() == 'YES' else outcome_prices[1]
            no_price = outcome_prices[1] if outcomes[0].upper() == 'YES' else outcome_prices[0]
            
            # 策略 1: 市场预期延期/取消（NO > 0.85），做空股票
            # 适用于游戏发布、产品发布等正面事件
            if no_price > 0.85 and ('release' in question.lower() or 'launch' in question.lower()):
                return {
                    'market_id': market.get('slug'),
                    'market_name': question,
                    'market_type': 'Stock_Arbitrage',
                    'strategy': 'Polymarket_Stock_Hedge',
                    'company': company,
                    'ticker': ticker,
                    'polymarket_direction': 'NO',
                    'polymarket_price': no_price,
                    'stock_action': 'SELL',  # 做空
                    'stock_price': stock_price,
                    'liquidity': liquidity,
                    'confidence': 70,
                    'position_size': 0.05,  # 做空风险较高，仓位较小
                    'reason': f'{company} ({ticker}) 市场预期延期，Polymarket NO {no_price:.2f}，股价 ${stock_price:.2f}，做空对冲'
                }
            
            # 策略 2: 市场预期正面事件（YES > 0.7），做多股票
            elif yes_price > 0.7 and ('release' in question.lower() or 'launch' in question.lower()):
                return {
                    'market_id': market.get('slug'),
                    'market_name': question,
                    'market_type': 'Stock_Arbitrage',
                    'strategy': 'Polymarket_Stock_Hedge',
                    'company': company,
                    'ticker': ticker,
                    'polymarket_direction': 'YES',
                    'polymarket_price': yes_price,
                    'stock_action': 'BUY',
                    'stock_price': stock_price,
                    'liquidity': liquidity,
                    'confidence': 70,
                    'position_size': 0.08,
                    'reason': f'{company} ({ticker}) 市场预期发布，Polymarket YES {yes_price:.2f}，股价 ${stock_price:.2f}，做多对冲'
                }
            
            # 策略 3: 市场预期负面事件（YES > 0.7），做空股票
            elif yes_price > 0.7 and ('delay' in question.lower() or 'cancel' in question.lower()):
                return {
                    'market_id': market.get('slug'),
                    'market_name': question,
                    'market_type': 'Stock_Arbitrage',
                    'strategy': 'Polymarket_Stock_Hedge',
                    'company': company,
                    'ticker': ticker,
                    'polymarket_direction': 'NO',
                    'polymarket_price': no_price,
                    'stock_action': 'SELL',
                    'stock_price': stock_price,
                    'liquidity': liquidity,
                    'confidence': 65,
                    'position_size': 0.08,
                    'reason': f'{company} ({ticker}) 市场预期负面事件，Polymarket NO {no_price:.2f}，股价 ${stock_price:.2f}'
                }
        
        return None
    
    def run(self):
        """主流程"""
        self.log("=" * 60)
        self.log("开始美股/港股套利分析")
        
        # 加载数据
        data = self.load_data()
        if not data:
            self.log("❌ 无数据")
            return
        
        # 寻找套利机会
        signals = self.find_stock_arbitrage(data)
        
        self.log(f"📊 发现 {len(signals)} 个股票套利机会")
        
        # 保存信号
        if signals:
            output_file = self.data_dir / "stock_arbitrage_signals.json"
            with open(output_file, 'w') as f:
                json.dump(signals, f, indent=2, ensure_ascii=False)
            
            self.log(f"✅ 信号已保存到 {output_file}")
        
        self.log("=" * 60)

def main():
    agent = AgentStockTrader()
    agent.run()

if __name__ == "__main__":
    main()
