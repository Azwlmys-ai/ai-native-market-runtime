"""
从历史交易中随机选择 10 个信号进行蒸馏学习
包含 Polymarket 实际交易，模拟 OKX 跨平台对冲场景
"""

import json
import random
from pathlib import Path
from datetime import datetime

class HistoricalTradeSignalGenerator:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
    
    def generate_signals_from_history(self):
        """
        基于历史交易生成 10 个测试信号
        包含：
        - 7 个 Polymarket 实际交易（已执行）
        - 3 个模拟 OKX 跨平台对冲信号
        """
        
        # Polymarket 实际交易（从历史记录中提取）
        polymarket_trades = [
            {
                "market": "Will the Buffalo Sabres win the 2026 NHL Stanley Cup?",
                "direction": "NO",
                "price": 0.928,
                "amount": 100,
                "confidence": 88,
                "reason": "Sabres 过去 15 年未进季后赛，当前战绩 25-35-8（东部第 13），伤病名单 5 人，ESPN 夺冠概率 < 0.5%",
                "source": "Agent B",
                "data_sources": ["NHL.com Stats", "ESPN Power Rankings", "Injury Report"],
                "market_type": "NHL Stanley Cup",
                "actual_execution": "BUY NO @ 0.928, $100, slippage 27%",
                "expected_outcome": "APPROVE",
                "actual_result": "已执行，持仓中",
                "learning_match": "✅ 高价 NO 策略，白名单市场"
            },
            {
                "market": "Will the Philadelphia Flyers win the 2026 NHL Stanley Cup?",
                "direction": "NO",
                "price": 0.964,
                "amount": 100,
                "confidence": 90,
                "reason": "Flyers 重建期（平均年龄 24.5 岁），防守效率排名第 28，门将 Carter Hart 伤停，替补门将扑救率仅 0.885",
                "source": "Agent B",
                "data_sources": ["NHL.com", "Natural Stat Trick", "CapFriendly"],
                "market_type": "NHL Stanley Cup",
                "actual_execution": "BUY NO @ 0.964, $100, slippage 5%",
                "expected_outcome": "APPROVE",
                "actual_result": "已执行，持仓中",
                "learning_match": "✅ 高价 NO 策略，白名单市场"
            },
            {
                "market": "Will the Minnesota Wild win the 2026 NHL Stanley Cup?",
                "direction": "NO",
                "price": 0.899,
                "amount": 100,
                "confidence": 85,
                "reason": "Wild 季后赛首轮出局概率 75%（过去 10 年 8 次首轮出局），当前阵容深度不足，对阵强队胜率仅 35%",
                "source": "Agent B",
                "data_sources": ["NHL.com", "Hockey Reference", "MoneyPuck Analytics"],
                "market_type": "NHL Stanley Cup",
                "actual_execution": "BUY NO @ 0.899, $100, slippage 5.6%",
                "expected_outcome": "APPROVE",
                "actual_result": "已执行，持仓中",
                "learning_match": "✅ 高价 NO 策略，白名单市场"
            },
            {
                "market": "Will the Oklahoma City Thunder win the 2026 NBA Finals?",
                "direction": "NO",
                "price": 0.42,
                "amount": 175,
                "confidence": 65,
                "reason": "Thunder 年轻阵容季后赛经验不足，对阵湖人/掘金胜率低，历史上年轻球队夺冠概率 < 15%",
                "source": "Agent B",
                "data_sources": ["NBA.com", "ESPN Analytics"],
                "market_type": "NBA Finals",
                "actual_execution": "SELL NO @ 0.42, $175, slippage -117%",
                "expected_outcome": "REJECT",
                "actual_result": "已执行，但滑点极高（危险区间 0.40-0.60）",
                "learning_match": "❌ 违反：价格在危险区间，滑点过高"
            },
            {
                "market": "Will MegaETH perform an airdrop by June 30?",
                "direction": "NO",
                "price": 0.449,
                "amount": 125,
                "confidence": 60,
                "reason": "社交媒体热度下降，Discord 活跃用户减少 20%，项目方未公布明确时间表",
                "source": "Agent K",
                "data_sources": ["Twitter Sentiment", "Discord Analytics"],
                "market_type": "加密空投",
                "actual_execution": "SELL NO @ 0.449, $125, slippage -2095%, levels_filled=9",
                "expected_outcome": "REJECT",
                "actual_result": "已执行，但滑点灾难性（9 层扫单）",
                "learning_match": "❌ 违反：黑名单市场，流动性极差"
            },
            {
                "market": "Will China invades Taiwan before GTA VI?",
                "direction": "NO",
                "price": 0.49,
                "amount": 196,
                "confidence": 70,
                "reason": "地缘政治分析：美国军事威慑增强，台海军演频率下降 30%，经济制裁风险过高",
                "source": "Agent K",
                "data_sources": ["CSIS Analysis", "Military Times", "Bloomberg"],
                "market_type": "地缘政治",
                "actual_execution": "SELL NO @ 0.49, $196, slippage -101%",
                "expected_outcome": "REJECT",
                "actual_result": "已执行，但滑点高（危险区间 + 黑名单）",
                "learning_match": "❌ 违反：黑名单市场，价格在危险区间"
            },
            {
                "market": "Will Harvey Weinstein be sentenced to no prison time?",
                "direction": "NO",
                "price": 0.595,
                "amount": 172,
                "confidence": 70,
                "reason": "法律专家分析：上诉成功率低于 15%，纽约州对性犯罪案件量刑严格",
                "source": "Agent B",
                "data_sources": ["Legal Expert Opinion", "NY Court Records"],
                "market_type": "法律案件",
                "actual_execution": "SELL NO @ 0.595, $172, slippage -435%, levels_filled=2",
                "expected_outcome": "REJECT",
                "actual_result": "已执行，但滑点高（危险区间 + 黑名单）",
                "learning_match": "❌ 违反：黑名单市场，价格在危险区间"
            }
        ]
        
        # 模拟 OKX 跨平台对冲信号
        okx_arbitrage_signals = [
            {
                "market": "BTC 价格 > $95,000 by June 30, 2026 (Polymarket) vs BTC-USDT Perpetual (OKX)",
                "direction": "ARBITRAGE",
                "price": 0.62,
                "okx_funding_rate": 0.0008,
                "okx_spot_price": 92000,  # 添加现货价格
                "okx_perpetual_price": 92150,  # 添加永续价格
                "hedge_direction": "买入 Polymarket NO（BTC 不会突破 $95k）+ 做多 OKX 永续（收资金费率）",
                "hedge_ratio": "1:1（$200 Polymarket + $200 OKX 保证金）",
                "funding_rate_annualized": "87%",
                "amount": 200,
                "confidence": 75,
                "reason": "Polymarket 隐含概率 62%（BTC 会突破 $95k），OKX 永续合约资金费率 0.08%（年化 87%），买入 Polymarket NO（押注不突破）+ 做多 OKX 永续（收资金费率），双重收益：如果 BTC 不突破，Polymarket 获利；如果 BTC 上涨，OKX 永续获利 + 持续收资金费率",
                "source": "Agent OKX Funding",
                "data_sources": ["Polymarket API", "OKX Funding Rate API", "CoinGecko BTC Price"],
                "market_type": "跨平台套利",
                "expected_outcome": "APPROVE",
                "actual_result": "模拟信号：资金费率套利机会",
                "learning_match": "✅ 跨平台对冲，资金费率优势明显"
            },
            {
                "market": "ETH 价格 < $3,000 by May 31, 2026 (Polymarket) vs ETH-USDT Spot (OKX)",
                "direction": "ARBITRAGE",
                "price": 0.35,
                "okx_spot_price": 3420,
                "okx_funding_rate": None,
                "hedge_direction": "买入 Polymarket YES（ETH 会跌破 $3k）+ 做空 OKX 永续（对冲下跌风险）",
                "hedge_ratio": "1:0.8（$150 Polymarket + $120 OKX 保证金，考虑杠杆）",
                "price_spread": "12.3%（$3420 → $3000）",
                "amount": 150,
                "confidence": 80,
                "reason": "Polymarket YES 价格 0.35（隐含 ETH 跌破 $3,000 概率 35%），OKX 现货价格 $3,420，买入 Polymarket YES + 做空 OKX 永续，对冲下跌风险。如果 ETH 跌破 $3k，Polymarket 获利 + OKX 空头获利；如果 ETH 不跌破，Polymarket 亏损但 OKX 空头可能获利（取决于期末价格）",
                "source": "Agent K",
                "data_sources": ["Polymarket API", "OKX Spot API", "Glassnode ETH Metrics"],
                "market_type": "跨平台套利",
                "expected_outcome": "APPROVE",
                "actual_result": "模拟信号：现货对冲机会",
                "learning_match": "✅ 跨平台对冲，价格差异明显"
            },
            {
                "market": "SOL 价格 > $200 by June 15, 2026 (Polymarket) vs SOL-USDT Perpetual (OKX)",
                "direction": "ARBITRAGE",
                "price": 0.48,
                "okx_funding_rate": -0.0003,
                "okx_spot_price": None,
                "amount": 180,
                "confidence": 70,
                "reason": "Polymarket 隐含概率 48%，OKX 永续合约资金费率 -0.03%（负费率，做空收费），买入 Polymarket YES + 做多 OKX 永续，双向收益",
                "source": "Agent OKX Funding",
                "data_sources": ["Polymarket API", "OKX Funding Rate API", "Solana Network Stats"],
                "market_type": "跨平台套利",
                "expected_outcome": "REJECT",
                "actual_result": "模拟信号：价格在危险区间 0.48，资金费率优势不足",
                "learning_match": "❌ 违反：价格在危险区间，资金费率优势不明显"
            }
        ]
        
        # 合并并随机打乱
        all_signals = polymarket_trades + okx_arbitrage_signals
        random.shuffle(all_signals)
        
        return all_signals
    
    def save_signals(self, signals):
        """保存信号到文件"""
        signals_file = self.data_dir / "historical_trade_signals.json"
        
        with open(signals_file, 'w') as f:
            json.dump(signals, f, indent=2, ensure_ascii=False)
        
        return signals_file

def main():
    generator = HistoricalTradeSignalGenerator()
    
    print("=" * 60)
    print("从历史交易生成测试信号")
    print("=" * 60)
    print()
    
    # 生成信号
    signals = generator.generate_signals_from_history()
    
    print(f"📊 生成 {len(signals)} 个测试信号")
    print()
    
    # 分类统计
    polymarket_count = sum(1 for s in signals if s.get("market_type") != "跨平台套利")
    okx_count = sum(1 for s in signals if s.get("market_type") == "跨平台套利")
    
    print(f"信号分类:")
    print(f"  📈 Polymarket 实际交易: {polymarket_count} 个")
    print(f"  🔄 OKX 跨平台对冲: {okx_count} 个")
    print()
    
    # 保存信号
    signals_file = generator.save_signals(signals)
    print(f"✅ 信号已保存到: {signals_file}")
    print()
    
    # 显示信号详情
    print("信号详情:")
    for i, signal in enumerate(signals, 1):
        market = signal.get("market", "")
        if len(market) > 60:
            market = market[:57] + "..."
        
        print(f"\n{i}. {market}")
        print(f"   类型: {signal.get('market_type', 'N/A')}")
        
        if signal.get("market_type") == "跨平台套利":
            print(f"   Polymarket 价格: {signal.get('polymarket_price', 'N/A')}")
            if "okx_funding_rate" in signal:
                print(f"   OKX 资金费率: {signal.get('okx_funding_rate', 'N/A')}")
            if "okx_spot_price" in signal:
                print(f"   OKX 现货价格: ${signal.get('okx_spot_price', 'N/A')}")
        else:
            print(f"   方向: {signal.get('direction', 'N/A')} @ {signal.get('price', 'N/A')}")
            if "actual_execution" in signal:
                print(f"   实际执行: {signal['actual_execution']}")
        
        print(f"   预期: {signal.get('expected_outcome', 'N/A')}")
        print(f"   学习匹配: {signal.get('learning_match', 'N/A')}")
    
    print()
    print("=" * 60)
    print("下一步：运行 Agent M 审查这些信号")
    print("命令：cd /opt/data/polymarket_arbitrage && python3 test_historical_trades.py")
    print("=" * 60)

if __name__ == "__main__":
    main()
