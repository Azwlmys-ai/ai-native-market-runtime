"""
触发 Agent G 从历史交易测试失败中学习
重点：NHL 高价 NO 策略失效 + OKX 跨平台套利被误判
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime

def main():
    base_dir = Path("/opt/data/polymarket_arbitrage")
    data_dir = base_dir / "data"
    
    print("=" * 60)
    print("触发 Agent G 学习：历史交易测试失败")
    print("=" * 60)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 加载测试报告
    report_file = data_dir / "historical_trades_report.json"
    with open(report_file, 'r') as f:
        report = json.load(f)
    
    print(f"📊 测试结果: {report['accuracy']} 准确率")
    print(f"   正确: {report['correct']}/{report['total_signals']}")
    print(f"   错误: {report['incorrect']}/{report['total_signals']}")
    print()
    
    # 识别关键失败
    print("关键失败:")
    
    failed_cases = [r for r in report['results'] if not r['is_correct']]
    
    # 按市场类型分组
    nhl_failures = [r for r in failed_cases if r['market_type'] == 'NHL Stanley Cup']
    okx_failures = [r for r in failed_cases if r['market_type'] == '跨平台套利']
    
    print(f"  NHL 高价 NO 策略失效: {len(nhl_failures)} 个")
    for r in nhl_failures:
        print(f"    - {r['market'][:60]}... @ {r['price']}")
    
    print(f"  OKX 跨平台套利误判: {len(okx_failures)} 个")
    for r in okx_failures:
        print(f"    - {r['market'][:60]}... @ {r['price']}")
    
    print()
    
    # 构造学习输入
    learning_input = {
        "test_type": "historical_trades",
        "timestamp": datetime.now().isoformat(),
        "accuracy": report['accuracy'],
        "total_signals": report['total_signals'],
        "correct": report['correct'],
        "incorrect": report['incorrect'],
        "key_failures": {
            "nhl_high_price_no": {
                "count": len(nhl_failures),
                "cases": [
                    {
                        "market": r['market'],
                        "price": r['price'],
                        "expected": r['expected'],
                        "agent_decision": r['agent_decision'],
                        "actual_result": r['actual_result']
                    }
                    for r in nhl_failures
                ]
            },
            "okx_arbitrage": {
                "count": len(okx_failures),
                "cases": [
                    {
                        "market": r['market'],
                        "price": r['price'],
                        "expected": r['expected'],
                        "agent_decision": r['agent_decision'],
                        "actual_result": r['actual_result']
                    }
                    for r in okx_failures
                ]
            }
        },
        "learning_effectiveness": report['learning_effectiveness'],
        "type_stats": report['type_stats']
    }
    
    # 保存学习输入
    learning_input_file = data_dir / "learning_input_historical_trades.json"
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
    with open(learning_report_file, 'r') as f:
        learning_report = json.load(f)
    
    print("=" * 60)
    print("Agent G 学习报告")
    print("=" * 60)
    print()
    
    print(f"识别的问题:")
    for i, issue in enumerate(learning_report.get('identified_issues', []), 1):
        print(f"{i}. {issue}")
    print()
    
    print(f"建议的改进:")
    for i, improvement in enumerate(learning_report.get('suggested_improvements', []), 1):
        print(f"{i}. {improvement}")
    print()
    
    print("=" * 60)
    print("下一步：重新生成知识库")
    print("命令：cd /opt/data/polymarket_arbitrage && python3 learning_knowledge_base.py")
    print("=" * 60)

if __name__ == "__main__":
    main()
