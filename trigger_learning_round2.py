"""
第二轮蒸馏学习：分析 Agent M 的改进和剩余问题
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime

def main():
    base_dir = Path("/opt/data/polymarket_arbitrage")
    data_dir = base_dir / "data"
    
    print("=" * 60)
    print("第二轮蒸馏学习")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 构造第二轮学习输入
    learning_input = {
        "timestamp": datetime.now().isoformat(),
        "learning_type": "agent_m_improvement_analysis",
        "context": "Agent M 经过第一轮学习后，准确率从 50% 提升到 66.7%，但仍有 2 个高质量 NHL 信号被错误拒绝",
        "round_1_results": {
            "accuracy": "50%",
            "correct": 3,
            "incorrect": 3,
            "problem": "所有 NHL 信号都被拒绝（0/3）"
        },
        "round_2_results": {
            "accuracy": "66.7%",
            "correct": 4,
            "incorrect": 2,
            "improvement": "Buffalo Sabres (0.92 NO) 通过审查 ✅",
            "remaining_problem": "Minnesota Wild (0.89 NO) 和 Philadelphia Flyers (0.94 NO) 仍被拒绝 ❌"
        },
        "successful_case": {
            "market": "Will Buffalo Sabres win 2026 Stanley Cup?",
            "price": 0.92,
            "direction": "NO",
            "confidence": 88,
            "reason": "Sabres 过去 15 年未进季后赛，当前战绩 25-35-8（东部第 13），伤病名单 5 人，ESPN 夺冠概率 < 0.5%",
            "data_sources": ["NHL.com Stats", "ESPN Power Rankings", "Injury Report"],
            "agent_m_decision": "APPROVE",
            "actual_result": "Sabres 未进季后赛，信号正确 ✅",
            "why_approved": "Agent M 识别出这是高价 NO 策略的典型案例"
        },
        "failed_cases": [
            {
                "market": "Will Minnesota Wild win 2026 Stanley Cup?",
                "price": 0.89,
                "direction": "NO",
                "confidence": 85,
                "reason": "Wild 季后赛首轮出局概率 75%（过去 10 年 8 次首轮出局），当前阵容深度不足，对阵强队胜率仅 35%",
                "data_sources": ["NHL.com", "Hockey Reference", "MoneyPuck Analytics"],
                "agent_m_decision": "REJECT",
                "agent_m_reason": "EV 论证不足，历史数据不能直接推导远期概率，缺少明确 EV 计算",
                "actual_result": "Wild 第二轮被淘汰，信号正确 ✅",
                "problem": "Agent M 要求显式 EV 公式和量化模型，但这是常识判断的高概率事件"
            },
            {
                "market": "Will Philadelphia Flyers win 2026 Stanley Cup?",
                "price": 0.94,
                "direction": "NO",
                "confidence": 90,
                "reason": "Flyers 重建期（平均年龄 24.5 岁），防守效率排名第 28，门将 Carter Hart 伤停，替补门将扑救率仅 0.885",
                "data_sources": ["NHL.com", "Natural Stat Trick", "CapFriendly"],
                "agent_m_decision": "REJECT",
                "agent_m_reason": "时间维度不一致，当前数据对 2026 结果解释力下降，缺少外部赔率比较和模拟结果",
                "actual_result": "Flyers 未进季后赛，信号正确 ✅",
                "problem": "Agent M 要求量化证明，但忽略了'重建期球队极低夺冠概率'是常识"
            }
        ],
        "key_contradiction": {
            "agent_g_insight": "你的盈利模式更像是'在高确定性、弱效率的长尾市场里反向买入/卖出'，成功交易普遍具有高置信度、低不确定性、可用常识快速判断的特征；不需要复杂信息挖掘即可形成优势",
            "agent_m_behavior": "要求显式 EV 公式、量化模型、外部赔率比较、实时验证，审查标准过于学术化",
            "contradiction": "Agent G 说'不需要复杂信息挖掘'，但 Agent M 要求'复杂的量化证明'"
        },
        "question_for_agent_g": [
            "为什么 Buffalo Sabres (0.92) 通过了，但 Minnesota Wild (0.89) 和 Philadelphia Flyers (0.94) 被拒绝？",
            "这三个信号有什么本质区别？还是 Agent M 的审查标准不一致？",
            "对于 NHL 高价 NO 信号（0.85-0.97），什么样的证据强度是'足够的'？",
            "Agent M 要求的'显式 EV 计算'和'量化模型'是否必要？还是应该信任'常识判断'？",
            "如何让 Agent M 理解：对于白名单市场（NHL）+ 最优定价区间（0.85-0.97）+ 可靠数据源（NHL.com），应该降低审查门槛？"
        ],
        "expected_learning_outcome": "Agent G 应该明确指出：对于白名单市场的高价 NO 信号，如果满足（1）市场类型在白名单（NHL/NBA），（2）价格在最优区间（0.85-0.97），（3）数据源可靠（官方 API），就应该通过，不需要复杂的 EV 计算和量化模型。Agent M 的审查标准应该分层：黑名单市场严格审查，白名单市场宽松审查。"
    }
    
    # 保存学习输入
    learning_input_file = data_dir / "agent_m_round2_analysis.json"
    with open(learning_input_file, 'w') as f:
        json.dump(learning_input, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 第二轮学习输入已保存到: {learning_input_file}")
    print()
    
    print("📊 第二轮测试结果摘要:")
    print(f"   准确率提升: 50% → 66.7% (+16.7%)")
    print(f"   进步: Buffalo Sabres 通过审查 ✅")
    print(f"   问题: Wild 和 Flyers 仍被拒绝 ❌")
    print()
    
    print("🔍 关键矛盾:")
    print("   Agent G: '不需要复杂信息挖掘即可形成优势'")
    print("   Agent M: '要求显式 EV 公式、量化模型、外部赔率比较'")
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
    print("Agent G 第二轮学习成果")
    print("=" * 60)
    print()
    
    # 显示关键洞察
    if "rejection_analysis" in learning_report and "key_insights" in learning_report["rejection_analysis"]:
        print("关键洞察:")
        print(f"  {learning_report['rejection_analysis']['key_insights']}")
        print()
    
    # 显示改进建议
    if "rejection_analysis" in learning_report and "improvement_suggestions" in learning_report["rejection_analysis"]:
        print("改进建议:")
        for rec in learning_report["rejection_analysis"]["improvement_suggestions"]:
            print(f"  • {rec}")
        print()
    
    print("=" * 60)
    print("下一步：重新生成知识库，第三轮测试")
    print("=" * 60)
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
