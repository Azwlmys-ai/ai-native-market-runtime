#!/usr/bin/env python3
"""
使用 API 历史数据训练和测试 Agent M
"""
import json
import os
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime

class AgentMTrainerWithAPIData:
    def __init__(self):
        self.base_dir = Path("/opt/data/polymarket_arbitrage")
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.config_path = self.base_dir / "config" / "llm_config.json"
        
        # 加载 LLM 配置
        with open(self.config_path) as f:
            self.llm_config = json.load(f)
        
        # 直接使用配置
        self.api_base = self.llm_config["api_base"]
        self.api_key = (
            self.llm_config.get("api_key")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("PAWMAAS_API_KEY")
        )
        if not self.api_key:
            raise RuntimeError("Missing API key: set OPENAI_API_KEY or PAWMAAS_API_KEY")
        self.model = self.llm_config["agent_models"]["agent_m_trainer"]
    
    def log(self, msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent M API Trainer] {msg}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_m_api_trainer_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_signals(self, signal_type):
        """加载训练集或测试集"""
        file_path = self.data_dir / f"{signal_type}_signals.json"
        
        if not file_path.exists():
            self.log(f"❌ 文件不存在: {file_path}")
            return []
        
        with open(file_path) as f:
            signals = json.load(f)
        
        self.log(f"✅ 加载 {len(signals)} 个{signal_type}信号")
        return signals
    
    async def call_agent_m(self, signal):
        """调用 Agent M 审查信号"""
        prompt = f"""你是 Polymarket 交易风险审查专家 Agent M。

请审查以下交易信号：

市场: {signal['market']}
方向: {signal['side']}
价格: {signal['price']}
金额: ${signal['amount']}
成交量: ${signal['volume']:.0f}
流动性: ${signal['liquidity']:.0f}
订单簿深度: {signal['orderbook_depth']} 层

请根据以下规则判断是否批准（APPROVE）或拒绝（REJECT）：

1. 高价 NO（≥0.90）- 强烈推荐
2. 高价 NO（0.85-0.89）+ 高流动性（≥$10,000）- 推荐
3. 中高价 NO（0.75-0.84）+ 高成交量（≥$50,000）- 推荐
4. 低价 YES（≤0.15）- 拒绝（风险高）
5. 流动性不足（<$5,000）- 拒绝
6. 中间价位（0.4-0.6）- 拒绝（风险高）
7. 综合评分：NO价格≥0.65 + 流动性≥$10,000 + 成交量≥$20,000 + 订单簿深度≥5层，满足3项以上推荐

请只回复 APPROVE 或 REJECT，不要解释。"""

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 10
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"].strip().upper()
                        
                        # 提取 APPROVE 或 REJECT
                        if "APPROVE" in content:
                            return "APPROVE"
                        elif "REJECT" in content:
                            return "REJECT"
                        else:
                            self.log(f"⚠️ 无法解析响应: {content}")
                            return "UNKNOWN"
                    else:
                        self.log(f"❌ API 调用失败: {resp.status}")
                        return "ERROR"
        except Exception as e:
            self.log(f"❌ 调用异常: {e}")
            return "ERROR"
    
    async def train(self, train_signals):
        """训练阶段：让 Agent M 学习训练集"""
        self.log("=" * 60)
        self.log("开始训练阶段")
        self.log("=" * 60)
        
        correct = 0
        total = len(train_signals)
        
        for i, signal in enumerate(train_signals, 1):
            self.log(f"训练 {i}/{total}: {signal['market'][:50]}...")
            
            prediction = await self.call_agent_m(signal)
            expected = signal['expected_outcome']
            
            is_correct = prediction == expected
            if is_correct:
                correct += 1
            
            self.log(f"  预测: {prediction}, 预期: {expected}, {'✅' if is_correct else '❌'}")
        
        accuracy = correct / total * 100
        self.log(f"✅ 训练完成，准确率: {accuracy:.1f}% ({correct}/{total})")
        
        return accuracy
    
    async def test(self, test_signals):
        """测试阶段：在测试集上评估 Agent M"""
        self.log("=" * 60)
        self.log("开始测试阶段")
        self.log("=" * 60)
        
        correct = 0
        total = len(test_signals)
        errors = []
        
        for i, signal in enumerate(test_signals, 1):
            self.log(f"测试 {i}/{total}: {signal['market'][:50]}...")
            
            prediction = await self.call_agent_m(signal)
            expected = signal['expected_outcome']
            
            is_correct = prediction == expected
            if is_correct:
                correct += 1
            else:
                errors.append({
                    "signal": signal,
                    "prediction": prediction,
                    "expected": expected
                })
            
            self.log(f"  预测: {prediction}, 预期: {expected}, {'✅' if is_correct else '❌'}")
        
        accuracy = correct / total * 100
        self.log(f"✅ 测试完成，准确率: {accuracy:.1f}% ({correct}/{total})")
        
        # 保存测试报告
        report = {
            "timestamp": datetime.now().isoformat(),
            "total": total,
            "correct": correct,
            "accuracy": accuracy,
            "errors": errors
        }
        
        report_path = self.data_dir / "agent_m_api_test_report.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.log(f"📊 测试报告已保存: {report_path}")
        
        return accuracy, errors
    
    async def run(self):
        """执行完整训练和测试流程"""
        self.log("=" * 60)
        self.log("Agent M API 数据训练测试")
        self.log("=" * 60)
        
        # 1. 加载数据集
        train_signals = self.load_signals("train")
        test_signals = self.load_signals("test")
        
        if len(train_signals) == 0 or len(test_signals) == 0:
            self.log("❌ 数据集加载失败")
            return
        
        self.log(f"📊 数据集: 训练集 {len(train_signals)} 条, 测试集 {len(test_signals)} 条")
        
        # 2. 训练阶段
        train_accuracy = await self.train(train_signals)
        
        # 3. 测试阶段
        test_accuracy, errors = await self.test(test_signals)
        
        # 4. 总结
        self.log("=" * 60)
        self.log("训练测试完成")
        self.log(f"训练集准确率: {train_accuracy:.1f}%")
        self.log(f"测试集准确率: {test_accuracy:.1f}%")
        self.log(f"错误数量: {len(errors)}")
        self.log("=" * 60)

async def main():
    trainer = AgentMTrainerWithAPIData()
    await trainer.run()

if __name__ == "__main__":
    asyncio.run(main())
