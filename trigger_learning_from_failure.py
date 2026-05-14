"""
触发 Agent G 学习：分析 Agent M 的审查失败
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime

def main():
    base_dir = Path("/opt/data/polymarket_arbitrage")
    data_dir = base_dir / "data"
    
    print("=" * 60)
    print("触发 Agent G 学习（蒸馏学习）")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 加载对比报告
    report_file = data_dir / "learning_integration_report.json"
    
    if not report_file.exists():
        print("❌ 对比报告不存在")
        return
    
    with open(report_file, 'r') as f:
        report = json.load(f)
    
    print(f"📊 加载对比报告")
    print(f"   总信号数: {report['total_signals']}")
    print(f"   正确决策: {report['correct']}")
    print(f"   错误决策: {report['incorrect']}")
    print(f"   准确率: {report['accuracy']}")
    print()
    
    # 构造学习输入
    learning_input = {
        "timestamp": datetime.now().isoformat(),
        "learning_type": "agent_m_failure_analysis",
        "context": "Agent M 在历史信号测试中准确率仅 50%，错误拒绝了所有符合学习成果的 NHL 信号",
        "test_results": report,
        "key_findings": [
            "✅ 黑名单规则生效：正确拒绝加密空投、地缘政治、法律案件（3/3）",
            "❌ 白名单规则未生效：错误拒绝所有 NHL 信号（0/3）",
            "❌ 最优定价区间规则未生效：0.85-0.97 的高价 NO 应该优先通过，但被拒绝",
            "根本原因：rejection_prompt_enhancement 只包含拒绝规则，缺少正向指导"
        ],
        "failed_signals": [
            {
                "market": "Will Buffalo Sabres win 2026 Stanley Cup?",
                "price": 0.92,
                "direction": "NO",
                "expected": "APPROVE",
                "agent_decision": "REJECT",
                "actual_result": "Sabres 未进季后赛，信号正确",
                "agent_reason": "价格优势论证不足，缺少明确 EV 计算"
            },
            {
                "market": "Will Minnesota Wild win 2026 Stanley Cup?",
                "price": 0.89,
                "direction": "NO",
                "expected": "APPROVE",
                "agent_decision": "REJECT",
                "actual_result": "Wild 第二轮被淘汰，信号正确",
                "agent_reason": "推理存在外推风险，历史数据不能直接推导远期概率"
            },
            {
                "market": "Will Philadelphia Flyers win 2026 Stanley Cup?",
                "price": 0.94,
                "direction": "NO",
                "expected": "APPROVE",
                "agent_decision": "REJECT",
                "actual_result": "Flyers 未进季后赛，信号正确",
                "agent_reason": "数据支撑不足，缺少流动性验证"
            }
        ],
        "question_for_agent_g": "基于这次测试结果，Agent M 的审查标准存在什么问题？应该如何调整 rejection_prompt_enhancement 才能让 Agent M 正确识别高质量的 NHL 高价 NO 信号？"
    }
    
    # 保存学习输入
    learning_input_file = data_dir / "agent_m_failure_analysis.json"
    with open(learning_input_file, 'w') as f:
        json.dump(learning_input, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 学习输入已保存到: {learning_input_file}")
    print()
    
    # 运行 Agent G
    print("🧠 运行 Agent G 学习...")
    print("-" * 60)
    
    result = subprocess.run(
        ["python3", "agents/agent_g.py"],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=300
    )
    
    if result.returncode != 0:
        print(f"❌ Agent G 运行失败: {result.stderr}")
        return
    
    print(result.stdout)
    print()
    
    # 加载学习报告
    learning_report_file = data_dir / "learning_report.json"
    
    if not learning_report_file.exists():
        print("❌ 学习报告不存在")
        return
    
    with open(learning_report_file, 'r') as f:
        learning_report = json.load(f)
    
    print("=" * 60)
    print("Agent G 学习成果")
    print("=" * 60)
    print()
    
    # 显示关键洞察
    if "key_insights" in learning_report:
        print("关键洞察:")
        for insight in learning_report["key_insights"]:
            print(f"  • {insight}")
        print()
    
    # 显示改进建议
    if "recommendations" in learning_report:
        print("改进建议:")
        for rec in learning_report["recommendations"]:
            print(f"  • {rec}")
        print()
    
    # 显示新的审查标准
    if "updated_rejection_criteria" in learning_report:
        print("更新后的审查标准:")
        print(json.dumps(learning_report["updated_rejection_criteria"], indent=2, ensure_ascii=False))
        print()
    
    print("=" * 60)
    print("下一步：重新生成知识库，然后再次测试")
    print("=" * 60)
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
