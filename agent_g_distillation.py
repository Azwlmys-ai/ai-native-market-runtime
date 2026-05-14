"""
Agent G - 蒸馏学习专用版本
职责：分析 Agent K v2 被拒绝的信号，生成改进建议
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_helper import call_llm_sync

class AgentGDistillation:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent G Distillation] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_g_distillation_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_rejected_signals(self):
        """加载被拒绝的信号"""
        rejected_file = self.data_dir / "rejected_signals_for_learning.json"
        
        if not rejected_file.exists():
            self.log("⚠️  未找到拒绝信号文件")
            return []
        
        try:
            with open(rejected_file, 'r') as f:
                rejected = json.load(f)
            
            self.log(f"📊 加载了 {len(rejected)} 个被拒绝的信号")
            return rejected
        
        except Exception as e:
            self.log(f"❌ 加载拒绝信号失败: {e}")
            return []
    
    def analyze_rejection_patterns(self, rejected_signals):
        """分析拒绝模式"""
        self.log("分析拒绝模式...")
        
        if not rejected_signals:
            self.log("ℹ️  无拒绝信号可分析")
            return None
        
        prompt = f"""
你是交易系统评估专家，负责分析 Agent K v2（价值投资策略）被 Agent M（风险审查）拒绝的信号，找出改进方向。

## 被拒绝的信号

{json.dumps(rejected_signals, indent=2, ensure_ascii=False)}

## Agent K v2 当前策略

**规则引擎逻辑**：
1. 识别弱队（重建期球队、战绩垫底）
2. NO 价格 > 0.90（极端价格）
3. 交易量 > $100k（流动性充足）
4. EV > 3%（扣除成本后有利润）
5. 真实夺冠概率：0.1%-0.5%

**弱队数据库**：
- Detroit Pistons: 0.1% 夺冠概率
- Montreal Canadiens: 0.4% 夺冠概率
- Anaheim Ducks: 0.3% 夺冠概率（已通过审查）

## Agent M 审查标准（推测）

基于通过的信号（Agent B）：
- Oakland Athletics NO @ 0.965（失败概率 42%）
- Chicago Blackhawks NO @ 0.952（失败概率 18%）
- Portland Trail Blazers NO @ 0.918（失败概率 22%）

## 分析任务

1. **拒绝原因分析**：
   - Montreal Canadiens 和 Detroit Pistons 为什么被拒绝？
   - Anaheim Ducks 为什么通过？
   - 三者的关键差异是什么？

2. **改进建议**：
   - 应该调整哪些参数？（价格阈值、EV 阈值、真实概率估计）
   - 应该增加哪些规则？（数据时效性检查、安全边际计算）
   - 应该删除哪些弱队？（通过率过低的球队）

3. **具体行动**：
   - 更新弱队数据库（调整真实概率、删除问题球队）
   - 更新规则引擎（调整阈值、增加检查）
   - 生成测试计划（如何验证改进效果）

输出 JSON 格式：
{{
  "rejection_analysis": {{
    "montreal_canadiens": "拒绝原因分析",
    "detroit_pistons": "拒绝原因分析",
    "anaheim_ducks": "通过原因分析",
    "key_differences": "三者的关键差异"
  }},
  "improvement_suggestions": {{
    "parameter_adjustments": [
      {{"parameter": "参数名", "current": "当前值", "suggested": "建议值", "reason": "原因"}}
    ],
    "rule_additions": [
      {{"rule": "新规则描述", "implementation": "实现方式", "expected_impact": "预期影响"}}
    ],
    "weak_teams_updates": [
      {{"team": "球队名", "action": "keep/remove/adjust", "reason": "原因", "new_probability": 0.xxx}}
    ]
  }},
  "action_plan": {{
    "code_changes": [
      {{"file": "文件路径", "change": "修改描述", "priority": "high/medium/low"}}
    ],
    "test_plan": [
      {{"test": "测试描述", "expected_result": "预期结果"}}
    ]
  }}
}}

只输出 JSON，不要其他文字。
"""
        
        try:
            response = call_llm_sync(
                agent_id="agent_g",
                prompt=prompt,
                timeout=120
            )
            
            # 解析响应
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(0))
                self.log("✅ 分析完成")
                return analysis
            else:
                self.log("❌ 无法解析 LLM 响应")
                return None
        
        except Exception as e:
            self.log(f"❌ 分析失败: {e}")
            return None
    
    def save_learning_report(self, analysis):
        """保存学习报告"""
        if not analysis:
            self.log("⚠️  无分析结果可保存")
            return
        
        report_file = self.data_dir / "agent_k_v2_learning_report.json"
        
        try:
            report = {
                "timestamp": datetime.now().isoformat(),
                "analysis": analysis,
                "status": "pending_implementation"
            }
            
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            self.log(f"✅ 学习报告已保存到 {report_file}")
            
            # 打印摘要
            print("\n" + "=" * 60)
            print("Agent K v2 蒸馏学习报告")
            print("=" * 60)
            print()
            
            if "rejection_analysis" in analysis:
                print("📊 拒绝原因分析:")
                for key, value in analysis["rejection_analysis"].items():
                    print(f"  - {key}: {value[:100]}...")
                print()
            
            if "improvement_suggestions" in analysis:
                print("💡 改进建议:")
                
                if "parameter_adjustments" in analysis["improvement_suggestions"]:
                    print("  参数调整:")
                    for adj in analysis["improvement_suggestions"]["parameter_adjustments"]:
                        print(f"    - {adj['parameter']}: {adj['current']} → {adj['suggested']}")
                
                if "weak_teams_updates" in analysis["improvement_suggestions"]:
                    print("  弱队数据库更新:")
                    for update in analysis["improvement_suggestions"]["weak_teams_updates"]:
                        print(f"    - {update['team']}: {update['action']}")
                print()
            
            if "action_plan" in analysis:
                print("🎯 行动计划:")
                if "code_changes" in analysis["action_plan"]:
                    for change in analysis["action_plan"]["code_changes"]:
                        print(f"  - [{change['priority']}] {change['file']}: {change['change']}")
                print()
        
        except Exception as e:
            self.log(f"❌ 保存学习报告失败: {e}")
    
    def run(self):
        """执行蒸馏学习"""
        self.log("开始蒸馏学习...")
        
        # 1. 加载被拒绝的信号
        rejected_signals = self.load_rejected_signals()
        
        if not rejected_signals:
            self.log("ℹ️  无拒绝信号，跳过学习")
            return
        
        # 2. 分析拒绝模式
        analysis = self.analyze_rejection_patterns(rejected_signals)
        
        # 3. 保存学习报告
        self.save_learning_report(analysis)

def main():
    agent = AgentGDistillation()
    agent.run()

if __name__ == "__main__":
    main()
