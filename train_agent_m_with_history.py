"""
使用历史交易数据训练 Agent M
采样 100 条历史交易，70 条训练，30 条测试
"""

import json
import random
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent))
from llm_helper import call_llm_sync

class AgentMTrainer:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent M Trainer] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_m_trainer_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_trade_history(self):
        """加载交易历史"""
        import subprocess
        
        self.log("加载交易历史...")
        
        result = subprocess.run(
            ["/opt/data/home/.local/bin/pm-trader", "history", "--limit", "100"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            self.log(f"❌ 加载失败: {result.stderr}")
            return []
        
        try:
            data = json.loads(result.stdout)
            trades = data.get("data", [])
            self.log(f"✅ 加载 {len(trades)} 笔交易")
            return trades
        except Exception as e:
            self.log(f"❌ 解析失败: {e}")
            return []
    
    def convert_trade_to_signal(self, trade):
        """将交易记录转换为信号格式"""
        # 判断交易结果（简化版：根据 slippage 和 side 判断）
        side = trade.get("side", "")
        slippage = trade.get("slippage", 0)
        avg_price = trade.get("avg_price", 0.5)
        
        # 买入交易：slippage < 50 认为是好交易
        # 卖出交易：slippage < -50 认为是坏交易
        if side == "buy":
            is_good = slippage < 50
        else:
            is_good = slippage > -100
        
        signal = {
            "market": trade.get("market_question", ""),
            "slug": trade.get("market_slug", ""),
            "direction": trade.get("outcome", "").upper(),
            "price": avg_price,
            "amount": trade.get("amount_usd", 100),
            "confidence": 70,
            "reason": f"历史交易 #{trade.get('id')}",
            "source": "historical_trade",
            "actual_result": "GOOD" if is_good else "BAD",
            "slippage": slippage,
            "levels_filled": trade.get("levels_filled", 1)
        }
        
        return signal
    
    def build_training_prompt(self, signals):
        """构建训练提示词"""
        examples = []
        
        for sig in signals:
            result = sig["actual_result"]
            decision = "APPROVE" if result == "GOOD" else "REJECT"
            
            examples.append(f"""
信号: {sig['market']}
方向: {sig['direction']}
价格: {sig['price']:.3f}
滑点: {sig['slippage']:.1f} bps
成交档位: {sig['levels_filled']}
实际结果: {result}
正确决策: {decision}
""")
        
        prompt = f"""你是 Agent M，负责审查交易信号。

以下是 {len(signals)} 个历史案例，每个案例都标注了实际结果和正确决策：

{''.join(examples)}

请总结规律：
1. 什么样的信号应该 APPROVE？
2. 什么样的信号应该 REJECT？
3. 关键判断指标是什么？

以 JSON 格式输出学习结果：
{{
  "approve_rules": ["规则1", "规则2", ...],
  "reject_rules": ["规则1", "规则2", ...],
  "key_indicators": ["指标1", "指标2", ...]
}}
"""
        return prompt
    
    def train(self, training_signals):
        """训练 Agent M"""
        self.log(f"开始训练，使用 {len(training_signals)} 个样本...")
        
        prompt = self.build_training_prompt(training_signals)
        
        try:
            response = call_llm_sync("agent_m_trainer", prompt, timeout=60)
            
            # 解析 JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                rules = json.loads(json_match.group())
                self.log("✅ 训练完成")
                return rules
            else:
                self.log("❌ 无法解析训练结果")
                return None
        
        except Exception as e:
            self.log(f"❌ 训练失败: {e}")
            return None
    
    def test_signal(self, signal, rules):
        """测试单个信号"""
        prompt = f"""你是 Agent M，负责审查交易信号。

你已经学习了以下规则：

通过规则：
{json.dumps(rules.get('approve_rules', []), indent=2, ensure_ascii=False)}

拒绝规则：
{json.dumps(rules.get('reject_rules', []), indent=2, ensure_ascii=False)}

关键指标：
{json.dumps(rules.get('key_indicators', []), indent=2, ensure_ascii=False)}

现在请审查以下信号：

市场: {signal['market']}
方向: {signal['direction']}
价格: {signal['price']:.3f}
金额: ${signal['amount']:.0f}

请根据学习的规则做出决策，只输出 APPROVE 或 REJECT。
"""
        
        try:
            response = call_llm_sync("agent_m_test", prompt, timeout=30)
            decision = "APPROVE" if "APPROVE" in response.upper() else "REJECT"
            return decision
        
        except Exception as e:
            self.log(f"❌ 测试失败: {e}")
            return "REJECT"
    
    def evaluate(self, test_signals, rules):
        """评估测试集"""
        self.log(f"开始评估，测试 {len(test_signals)} 个样本...")
        
        correct = 0
        results = []
        
        for sig in test_signals:
            decision = self.test_signal(sig, rules)
            expected = "APPROVE" if sig["actual_result"] == "GOOD" else "REJECT"
            is_correct = (decision == expected)
            
            if is_correct:
                correct += 1
            
            results.append({
                "market": sig["market"],
                "decision": decision,
                "expected": expected,
                "correct": is_correct,
                "actual_result": sig["actual_result"]
            })
            
            self.log(f"  {sig['market'][:50]}: {decision} (期望 {expected}) {'✅' if is_correct else '❌'}")
        
        accuracy = correct / len(test_signals) * 100
        self.log(f"✅ 准确率: {accuracy:.1f}% ({correct}/{len(test_signals)})")
        
        return accuracy, results
    
    def run(self):
        """执行完整训练和测试流程"""
        self.log("=" * 60)
        self.log("开始 Agent M 历史数据训练")
        self.log("=" * 60)
        
        # 1. 加载交易历史
        trades = self.load_trade_history()
        
        if len(trades) < 30:
            self.log(f"❌ 交易数据不足（需要至少 30 条，当前 {len(trades)} 条）")
            return
        
        # 2. 转换为信号格式
        signals = [self.convert_trade_to_signal(t) for t in trades]
        
        # 3. 随机打乱并分割数据集（使用当前时间戳作为随机种子）
        import time
        random.seed(int(time.time() * 1000))
        random.shuffle(signals)
        
        split_point = int(len(signals) * 0.7)
        training_set = signals[:split_point]
        test_set = signals[split_point:]
        
        self.log(f"📊 数据集划分: 训练集 {len(training_set)} 条, 测试集 {len(test_set)} 条")
        
        # 4. 训练
        rules = self.train(training_set)
        
        if not rules:
            self.log("❌ 训练失败")
            return
        
        # 保存规则
        rules_file = self.data_dir / "agent_m_learned_rules.json"
        with open(rules_file, 'w') as f:
            json.dump(rules, f, indent=2, ensure_ascii=False)
        self.log(f"✅ 规则已保存到 {rules_file}")
        
        # 5. 测试
        accuracy, results = self.evaluate(test_set, rules)
        
        # 6. 保存结果
        report = {
            "timestamp": datetime.now().isoformat(),
            "training_size": len(training_set),
            "test_size": len(test_set),
            "accuracy": accuracy,
            "rules": rules,
            "test_results": results
        }
        
        report_file = self.data_dir / "agent_m_training_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 报告已保存到 {report_file}")
        self.log("=" * 60)
        self.log(f"训练完成！准确率: {accuracy:.1f}%")
        self.log("=" * 60)

def main():
    trainer = AgentMTrainer()
    trainer.run()

if __name__ == "__main__":
    main()
