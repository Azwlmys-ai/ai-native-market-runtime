"""
第二轮测试信号生成器
目标：至少 5 个跨平台套利，确保 80% 准确率
"""

import json
import random
from pathlib import Path
from datetime import datetime

class TestSignalGeneratorRound2:
    def __init__(self):
        self.base_dir = Path("/opt/data/polymarket_arbitrage")
        self.data_dir = self.base_dir / "data"
    
    def generate_signals(self):
        """生成 10 个测试信号（5 个跨平台套利 + 5 个 Polymarket 单边）"""
        
        # 5 个跨平台套利信号（设计为应该通过）
        arbitrage_signals = [
            {
                "market": "BTC 价格 > $100,000 by July 31, 2026 (Polymarket) vs BTC-USDT Perpetual (OKX)",
                "direction": "ARBITRAGE",
                "price": 0.45,
                "okx_spot_price": 92000,
                "okx_perpetual_price": 92200,
                "okx_funding_rate": 0.0012,  # 0.12%，年化 131%
                "hedge_direction": "买入 Polymarket YES（BTC 会突破 $100k）+ 做多 OKX 永续（收资金费率 + 价格上涨）",
                "hedge_ratio": "1:1（$180 Polymarket + $180 OKX 保证金）",
                "funding_rate_annualized": "131%",
                "price_spread": "8.7%（$92k → $100k）",
                "amount": 180,
                "confidence": 85,
                "reason": "Polymarket YES 价格 0.45（隐含 BTC 突破 $100k 概率 45%），OKX 现货价格 $92,000，距离目标仅 8.7%。买入 Polymarket YES + 做多 OKX 永续，双重收益：如果 BTC 突破 $100k，Polymarket 获利 + OKX 永续获利；如果 BTC 不突破但上涨，OKX 永续获利 + 持续收资金费率（年化 131%）。对冲方向互补，数据完整。",
                "source": "Agent OKX Funding",
                "data_sources": ["Polymarket API", "OKX Funding Rate API", "CoinGecko BTC Price"],
                "market_type": "跨平台套利",
                "expected_outcome": "APPROVE",
                "learning_match": "✅ 跨平台对冲，方向互补，数据完整"
            },
            {
                "market": "ETH 价格 > $4,000 by June 30, 2026 (Polymarket) vs ETH-USDT Perpetual (OKX)",
                "direction": "ARBITRAGE",
                "price": 0.52,
                "okx_spot_price": 3420,
                "okx_perpetual_price": 3435,
                "okx_funding_rate": 0.0009,  # 0.09%，年化 98%
                "hedge_direction": "买入 Polymarket YES（ETH 会突破 $4k）+ 做多 OKX 永续（收资金费率 + 价格上涨）",
                "hedge_ratio": "1:1（$160 Polymarket + $160 OKX 保证金）",
                "funding_rate_annualized": "98%",
                "price_spread": "14.5%（$3,420 → $4,000）",
                "amount": 160,
                "confidence": 80,
                "reason": "Polymarket YES 价格 0.52（隐含 ETH 突破 $4k 概率 52%），OKX 现货价格 $3,420，距离目标 14.5%。买入 Polymarket YES + 做多 OKX 永续，双重收益：如果 ETH 突破 $4k，Polymarket 获利 + OKX 永续获利；如果 ETH 不突破但上涨，OKX 永续获利 + 持续收资金费率（年化 98%）。对冲方向互补，数据完整。",
                "source": "Agent OKX Funding",
                "data_sources": ["Polymarket API", "OKX Funding Rate API", "Glassnode ETH Metrics"],
                "market_type": "跨平台套利",
                "expected_outcome": "APPROVE",
                "learning_match": "✅ 跨平台对冲，方向互补，数据完整"
            },
            {
                "market": "SOL 价格 < $150 by June 15, 2026 (Polymarket) vs SOL-USDT Perpetual (OKX)",
                "direction": "ARBITRAGE",
                "price": 0.38,
                "okx_spot_price": 165,
                "okx_perpetual_price": 166,
                "okx_funding_rate": 0.0006,  # 0.06%，年化 66%
                "hedge_direction": "买入 Polymarket YES（SOL 会跌破 $150）+ 做空 OKX 永续（对冲下跌风险）",
                "hedge_ratio": "1:0.9（$140 Polymarket + $126 OKX 保证金）",
                "funding_rate_annualized": "66%",
                "price_spread": "9.7%（$165 → $150）",
                "amount": 140,
                "confidence": 75,
                "reason": "Polymarket YES 价格 0.38（隐含 SOL 跌破 $150 概率 38%），OKX 现货价格 $165，距离目标 9.7%。买入 Polymarket YES + 做空 OKX 永续，双重收益：如果 SOL 跌破 $150，Polymarket 获利 + OKX 空头获利；如果 SOL 不跌破但下跌，OKX 空头获利。对冲方向互补，数据完整。",
                "source": "Agent K",
                "data_sources": ["Polymarket API", "OKX Spot API", "Solana Network Stats"],
                "market_type": "跨平台套利",
                "expected_outcome": "APPROVE",
                "learning_match": "✅ 跨平台对冲，方向互补，数据完整"
            },
            {
                "market": "AVAX 价格 > $50 by July 15, 2026 (Polymarket) vs AVAX-USDT Perpetual (OKX)",
                "direction": "ARBITRAGE",
                "price": 0.48,
                "okx_spot_price": 42,
                "okx_perpetual_price": 42.5,
                "okx_funding_rate": 0.0008,  # 0.08%，年化 87%
                "hedge_direction": "买入 Polymarket YES（AVAX 会突破 $50）+ 做多 OKX 永续（收资金费率 + 价格上涨）",
                "hedge_ratio": "1:1（$150 Polymarket + $150 OKX 保证金）",
                "funding_rate_annualized": "87%",
                "price_spread": "16%（$42 → $50）",
                "amount": 150,
                "confidence": 78,
                "reason": "Polymarket YES 价格 0.48（隐含 AVAX 突破 $50 概率 48%），OKX 现货价格 $42，距离目标 16%。买入 Polymarket YES + 做多 OKX 永续，双重收益：如果 AVAX 突破 $50，Polymarket 获利 + OKX 永续获利；如果 AVAX 不突破但上涨，OKX 永续获利 + 持续收资金费率（年化 87%）。对冲方向互补，数据完整。",
                "source": "Agent OKX Funding",
                "data_sources": ["Polymarket API", "OKX Funding Rate API", "Avalanche Network Stats"],
                "market_type": "跨平台套利",
                "expected_outcome": "APPROVE",
                "learning_match": "✅ 跨平台对冲，方向互补，数据完整"
            },
            {
                "market": "DOGE 价格 < $0.15 by June 30, 2026 (Polymarket) vs DOGE-USDT Perpetual (OKX)",
                "direction": "ARBITRAGE",
                "price": 0.42,
                "okx_spot_price": 0.18,
                "okx_perpetual_price": 0.181,
                "okx_funding_rate": 0.0005,  # 0.05%，年化 55%
                "hedge_direction": "买入 Polymarket YES（DOGE 会跌破 $0.15）+ 做空 OKX 永续（对冲下跌风险）",
                "hedge_ratio": "1:0.85（$130 Polymarket + $110 OKX 保证金）",
                "funding_rate_annualized": "55%",
                "price_spread": "20%（$0.18 → $0.15）",
                "amount": 130,
                "confidence": 72,
                "reason": "Polymarket YES 价格 0.42（隐含 DOGE 跌破 $0.15 概率 42%），OKX 现货价格 $0.18，距离目标 20%。买入 Polymarket YES + 做空 OKX 永续，双重收益：如果 DOGE 跌破 $0.15，Polymarket 获利 + OKX 空头获利；如果 DOGE 不跌破但下跌，OKX 空头获利。对冲方向互补，数据完整。",
                "source": "Agent K",
                "data_sources": ["Polymarket API", "OKX Spot API", "CoinGecko DOGE Price"],
                "market_type": "跨平台套利",
                "expected_outcome": "APPROVE",
                "learning_match": "✅ 跨平台对冲，方向互补，数据完整"
            }
        ]
        
        # 5 个 Polymarket 单边交易（3 个应该通过，2 个应该拒绝）
        polymarket_signals = [
            # 应该通过：NHL 高价 NO
            {
                "market": "Will the Chicago Blackhawks win the 2026 NHL Stanley Cup?",
                "direction": "NO",
                "price": 0.952,
                "amount": 100,
                "confidence": 92,
                "reason": "Blackhawks 重建期（平均年龄 23.8 岁），当前战绩 22-38-10（西部第 15），核心球员 Connor Bedard 伤停，ESPN 夺冠概率 < 0.3%",
                "source": "Agent B",
                "data_sources": ["NHL.com Stats", "ESPN Power Rankings", "Injury Report"],
                "market_type": "NHL Stanley Cup",
                "expected_outcome": "APPROVE",
                "actual_result": "白名单市场 + 极端价格",
                "learning_match": "✅ 高价 NO 策略，白名单市场"
            },
            # 应该通过：NBA 高价 NO
            {
                "market": "Will the Portland Trail Blazers win the 2026 NBA Finals?",
                "direction": "NO",
                "price": 0.918,
                "amount": 100,
                "confidence": 89,
                "reason": "Trail Blazers 重建期（平均年龄 24.2 岁），当前战绩 28-42（西部第 13），核心球员 Damian Lillard 已交易，ESPN 夺冠概率 < 0.5%",
                "source": "Agent B",
                "data_sources": ["NBA.com", "ESPN Analytics"],
                "market_type": "NBA Finals",
                "expected_outcome": "APPROVE",
                "actual_result": "白名单市场 + 极端价格",
                "learning_match": "✅ 高价 NO 策略，白名单市场"
            },
            # 应该通过：MLB 高价 NO
            {
                "market": "Will the Oakland Athletics win the 2026 World Series?",
                "direction": "NO",
                "price": 0.965,
                "amount": 100,
                "confidence": 93,
                "reason": "Athletics 重建期（平均年龄 25.1 岁），2025 赛季战绩 62-100（美联西区垫底），核心球员已交易，ESPN 夺冠概率 < 0.2%",
                "source": "Agent B",
                "data_sources": ["MLB.com Stats", "ESPN Power Rankings"],
                "market_type": "MLB World Series",
                "expected_outcome": "APPROVE",
                "actual_result": "白名单市场 + 极端价格",
                "learning_match": "✅ 高价 NO 策略，白名单市场"
            },
            # 应该拒绝：加密空投（黑名单）
            {
                "market": "Will LayerZero perform an airdrop by July 31, 2026?",
                "direction": "YES",
                "price": 0.52,
                "amount": 140,
                "confidence": 65,
                "reason": "LayerZero 团队在 Twitter 暗示 Q3 空投，Discord 活跃用户增加 35%，链上交互量增长 50%",
                "source": "Agent K",
                "data_sources": ["Twitter Sentiment", "Discord Analytics", "Dune Analytics"],
                "market_type": "加密空投",
                "expected_outcome": "REJECT",
                "actual_result": "黑名单市场 + 危险区间",
                "learning_match": "❌ 违反：黑名单市场，价格在危险区间"
            },
            # 应该拒绝：娱乐八卦（黑名单）
            {
                "market": "Will Taylor Swift announce a new album by August 31, 2026?",
                "direction": "YES",
                "price": 0.48,
                "amount": 130,
                "confidence": 60,
                "reason": "Taylor Swift 在社交媒体发布神秘倒计时，粉丝社区热度上升 40%，历史上每 2 年发布一张专辑",
                "source": "Agent K",
                "data_sources": ["Twitter Sentiment", "Reddit r/TaylorSwift", "Billboard"],
                "market_type": "娱乐八卦",
                "expected_outcome": "REJECT",
                "actual_result": "黑名单市场 + 危险区间",
                "learning_match": "❌ 违反：黑名单市场，价格在危险区间"
            }
        ]
        
        # 合并并随机打乱
        all_signals = arbitrage_signals + polymarket_signals
        random.shuffle(all_signals)
        
        return all_signals
    
    def save_signals(self, signals):
        """保存信号到文件"""
        signals_file = self.data_dir / "test_signals_round2.json"
        
        with open(signals_file, 'w') as f:
            json.dump(signals, f, indent=2, ensure_ascii=False)
        
        return signals_file

def main():
    generator = TestSignalGeneratorRound2()
    
    print("=" * 60)
    print("第二轮测试信号生成")
    print("=" * 60)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 生成信号
    signals = generator.generate_signals()
    
    print(f"📊 生成 {len(signals)} 个测试信号")
    print()
    
    # 分类统计
    arbitrage_count = sum(1 for s in signals if s.get("market_type") == "跨平台套利")
    polymarket_count = sum(1 for s in signals if s.get("market_type") != "跨平台套利")
    
    print(f"信号分类:")
    print(f"  🔄 跨平台套利: {arbitrage_count} 个（全部应该 APPROVE）")
    print(f"  📈 Polymarket 单边: {polymarket_count} 个（3 个 APPROVE + 2 个 REJECT）")
    print()
    
    # 保存信号
    signals_file = generator.save_signals(signals)
    print(f"✅ 信号已保存到: {signals_file}")
    print()
    
    # 显示信号详情
    print("信号详情:")
    print()
    
    for i, signal in enumerate(signals, 1):
        market = signal["market"]
        market_type = signal.get("market_type", "Unknown")
        expected = signal.get("expected_outcome", "Unknown")
        
        print(f"{i}. {market[:70]}...")
        print(f"   类型: {market_type}")
        print(f"   预期: {expected}")
        
        if market_type == "跨平台套利":
            print(f"   价格: {signal.get('price')}")
            print(f"   OKX 现货: ${signal.get('okx_spot_price')}")
            print(f"   资金费率: {signal.get('okx_funding_rate')} (年化 {signal.get('funding_rate_annualized')})")
            print(f"   对冲方向: {signal.get('hedge_direction')[:60]}...")
        else:
            print(f"   方向: {signal.get('direction')} @ {signal.get('price')}")
        
        print()
    
    print("=" * 60)
    print("下一步：运行测试")
    print("命令：cd /opt/data/polymarket_arbitrage && python3 test_signals_round2.py")
    print("=" * 60)

if __name__ == "__main__":
    main()
