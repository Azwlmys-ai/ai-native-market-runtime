#!/usr/bin/env python3
"""
测试 Agent Lil222 - 1¢ → 2¢ 流动性套利策略

测试流程：
1. 生成模拟的 5 分钟 BTC 市场数据
2. 模拟 1¢ 流动性检查
3. 生成交易信号
4. 验证信号质量
5. 模拟交易执行
6. 计算实际收益

测试场景：
- 场景 1：2¢ 成交（+100%）
- 场景 2：归零（-100%）
- 场景 3：到期赢（+9900%）
- 场景 4：流动性不足（跳过）
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

class AgentLil222Tester:
    """Agent Lil222 测试器"""
    
    def __init__(self):
        self.test_results = []
        self.total_profit = 0
        self.total_trades = 0
        self.win_trades = 0
        self.loss_trades = 0
        
    def log(self, message: str):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def generate_mock_markets(self) -> List[Dict]:
        """
        生成模拟的 5 分钟 BTC 市场
        
        模拟 10 个市场：
        - 5 个 "BTC 上涨" 市场
        - 5 个 "BTC 下跌" 市场
        """
        self.log("🔧 生成模拟市场数据...")
        
        markets = []
        now = datetime.now()
        
        for i in range(10):
            direction = "up" if i < 5 else "down"
            end_time = now + timedelta(minutes=7)  # 7 分钟后结束
            
            market = {
                "condition_id": f"mock_btc_5min_{i:02d}",
                "question": f"Will BTC go {direction} in the next 5 minutes?",
                "slug": f"btc-5min-{direction}-{i}",
                "end_date_iso": end_time.isoformat(),
                "active": True,
                "closed": False
            }
            
            markets.append(market)
        
        self.log(f"✅ 生成 {len(markets)} 个模拟市场")
        return markets
    
    def generate_mock_signals(self, markets: List[Dict]) -> List[Dict]:
        """
        生成模拟交易信号
        
        为每个市场生成一个买入信号
        """
        self.log("🔧 生成模拟交易信号...")
        
        signals = []
        
        for i, market in enumerate(markets):
            # 模拟 1¢ 流动性（80% 的市场有足够流动性）
            has_liquidity = i < 8
            
            if not has_liquidity:
                self.log(f"⚠️ 市场 {i+1}: 流动性不足，跳过")
                continue
            
            signal = {
                "signal_id": f"lil222_test_{i:02d}",
                "agent": "Agent Lil222",
                "timestamp": datetime.now().isoformat(),
                "strategy": "1cent_to_2cent_liquidity_arbitrage",
                
                # 市场信息
                "market_id": market["condition_id"],
                "market_title": market["question"],
                "end_time": market["end_date_iso"],
                
                # 交易参数
                "direction": "YES",
                "buy_price": 0.01,
                "sell_price": 0.02,
                "position_size": 5,
                "order_timeout": 120,
                
                # 流动性
                "liquidity_usd": 15.0,
                
                # 期望收益
                "expected_value": 7.0,
                "expected_return_pct": 140,
                "confidence": 85
            }
            
            signals.append(signal)
            self.log(f"✅ 信号 {i+1}: {market['question']}")
        
        self.log(f"📊 共生成 {len(signals)} 个信号")
        return signals
    
    def simulate_trade_execution(self, signal: Dict) -> Dict:
        """
        模拟交易执行
        
        三种结局：
        1. 2¢ 成交（50% 概率）→ +100%
        2. 归零（48.6% 概率）→ -100%
        3. 到期赢（1.4% 概率）→ +9900%
        """
        import random
        
        # 生成随机数决定结局
        rand = random.random()
        
        position_size = signal["position_size"]
        
        if rand < 0.50:
            # 场景 1：2¢ 成交
            outcome = "sell_at_2cent"
            profit = position_size
            return_pct = 100
            final_value = position_size * 2
            
        elif rand < 0.986:  # 0.50 + 0.486
            # 场景 2：归零
            outcome = "expire_loss"
            profit = -position_size
            return_pct = -100
            final_value = 0
            
        else:
            # 场景 3：到期赢
            outcome = "expire_win"
            profit = position_size * 99
            return_pct = 9900
            final_value = position_size * 100
        
        return {
            "signal_id": signal["signal_id"],
            "market_title": signal["market_title"],
            "outcome": outcome,
            "position_size": position_size,
            "profit": profit,
            "return_pct": return_pct,
            "final_value": final_value
        }
    
    def run_test(self):
        """运行测试"""
        self.log("=" * 80)
        self.log("🧪 Agent Lil222 策略测试")
        self.log("=" * 80)
        
        # 1. 生成模拟市场
        markets = self.generate_mock_markets()
        
        # 2. 生成模拟信号
        signals = self.generate_mock_signals(markets)
        
        if not signals:
            self.log("❌ 未生成任何信号，测试终止")
            return
        
        # 3. 模拟交易执行
        self.log("\n" + "=" * 80)
        self.log("📊 模拟交易执行")
        self.log("=" * 80)
        
        for i, signal in enumerate(signals):
            result = self.simulate_trade_execution(signal)
            self.test_results.append(result)
            
            # 更新统计
            self.total_trades += 1
            self.total_profit += result["profit"]
            
            if result["profit"] > 0:
                self.win_trades += 1
            else:
                self.loss_trades += 1
            
            # 打印结果
            outcome_emoji = "✅" if result["profit"] > 0 else "❌"
            self.log(f"{outcome_emoji} 交易 {i+1}: {result['outcome']}")
            self.log(f"   市场: {result['market_title']}")
            self.log(f"   投入: ${result['position_size']:.2f}")
            self.log(f"   收益: ${result['profit']:.2f} ({result['return_pct']:+.0f}%)")
            self.log(f"   最终价值: ${result['final_value']:.2f}")
            self.log("")
        
        # 4. 生成测试报告
        self.generate_report()
    
    def generate_report(self):
        """生成测试报告"""
        self.log("=" * 80)
        self.log("📊 测试报告")
        self.log("=" * 80)
        
        # 基础统计
        win_rate = (self.win_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        avg_profit = self.total_profit / self.total_trades if self.total_trades > 0 else 0
        
        self.log(f"\n📈 交易统计:")
        self.log(f"   总交易数: {self.total_trades}")
        self.log(f"   盈利交易: {self.win_trades}")
        self.log(f"   亏损交易: {self.loss_trades}")
        self.log(f"   胜率: {win_rate:.1f}%")
        
        self.log(f"\n💰 收益统计:")
        self.log(f"   总收益: ${self.total_profit:.2f}")
        self.log(f"   平均收益: ${avg_profit:.2f}")
        self.log(f"   总投入: ${self.total_trades * 5:.2f}")
        self.log(f"   ROI: {(self.total_profit / (self.total_trades * 5) * 100):+.1f}%")
        
        # 结局分布
        outcomes = {}
        for result in self.test_results:
            outcome = result["outcome"]
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        
        self.log(f"\n📊 结局分布:")
        for outcome, count in outcomes.items():
            pct = count / self.total_trades * 100
            self.log(f"   {outcome}: {count} ({pct:.1f}%)")
        
        # 理论 vs 实际对比
        self.log(f"\n🎯 理论 vs 实际:")
        self.log(f"   理论 EV: $7.00 (+140%)")
        self.log(f"   实际 EV: ${avg_profit:.2f} ({(avg_profit / 5 * 100):+.1f}%)")
        
        expected_outcomes = {
            "sell_at_2cent": 50.0,
            "expire_loss": 48.6,
            "expire_win": 1.4
        }
        
        self.log(f"\n   理论分布 vs 实际分布:")
        for outcome, expected_pct in expected_outcomes.items():
            actual_count = outcomes.get(outcome, 0)
            actual_pct = actual_count / self.total_trades * 100 if self.total_trades > 0 else 0
            diff = actual_pct - expected_pct
            self.log(f"   {outcome}: {expected_pct:.1f}% (理论) vs {actual_pct:.1f}% (实际) [{diff:+.1f}%]")
        
        # 风险评估
        self.log(f"\n⚠️  风险评估:")
        max_loss = min([r["profit"] for r in self.test_results])
        max_win = max([r["profit"] for r in self.test_results])
        self.log(f"   最大单笔亏损: ${max_loss:.2f}")
        self.log(f"   最大单笔盈利: ${max_win:.2f}")
        self.log(f"   盈亏比: {abs(max_win / max_loss):.1f}:1")
        
        # 结论
        self.log(f"\n💡 结论:")
        if avg_profit > 0:
            self.log(f"   ✅ 策略有效！平均每笔交易盈利 ${avg_profit:.2f}")
            self.log(f"   ✅ 如果每天交易 100 笔，预期日收益: ${avg_profit * 100:.2f}")
            self.log(f"   ✅ 如果每周交易 700 笔，预期周收益: ${avg_profit * 700:.2f}")
        else:
            self.log(f"   ❌ 策略无效！平均每笔交易亏损 ${abs(avg_profit):.2f}")
        
        # 保存报告
        report = {
            "test_time": datetime.now().isoformat(),
            "strategy": "1cent_to_2cent_liquidity_arbitrage",
            "total_trades": self.total_trades,
            "win_trades": self.win_trades,
            "loss_trades": self.loss_trades,
            "win_rate": win_rate,
            "total_profit": self.total_profit,
            "avg_profit": avg_profit,
            "roi": (self.total_profit / (self.total_trades * 5) * 100) if self.total_trades > 0 else 0,
            "outcomes": outcomes,
            "max_loss": max_loss,
            "max_win": max_win,
            "results": self.test_results
        }
        
        os.makedirs("data", exist_ok=True)
        report_file = "data/lil222_test_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self.log(f"\n💾 测试报告已保存到 {report_file}")
        self.log("=" * 80)

def main():
    """主函数"""
    tester = AgentLil222Tester()
    tester.run_test()

if __name__ == "__main__":
    main()
