"""
触发 Agent G 学习：OKX 跨平台套利误判
重点：Agent M 对跨平台套利逻辑理解不足
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime

def main():
    base_dir = Path("/opt/data/polymarket_arbitrage")
    data_dir = base_dir / "data"
    
    print("=" * 60)
    print("触发 Agent G 学习：OKX 跨平台套利误判")
    print("=" * 60)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 加载测试报告
    report_file = data_dir / "historical_trades_report.json"
    with open(report_file, 'r') as f:
        report = json.load(f)
    
    print(f"📊 当前准确率: {report['accuracy']}")
    print()
    
    # 识别 OKX 套利失败案例
    okx_failures = [
        r for r in report['results'] 
        if r['market_type'] == '跨平台套利' and not r['is_correct']
    ]
    
    print(f"🔍 OKX 跨平台套利误判: {len(okx_failures)} 个")
    for r in okx_failures:
        print(f"  ❌ {r['market'][:70]}...")
        print(f"     价格: {r['price']}, 预期: {r['expected']}, 实际: {r['agent_decision']}")
    print()
    
    # 构造学习输入（聚焦 OKX 套利）
    learning_input = {
        "focus": "okx_cross_platform_arbitrage",
        "timestamp": datetime.now().isoformat(),
        "problem": "Agent M 对跨平台套利的逻辑理解不足，误判为同向敞口而非对冲",
        "failed_cases": [
            {
                "market": r['market'],
                "price": r['price'],
                "expected": r['expected'],
                "agent_decision": r['agent_decision'],
                "actual_result": r['actual_result'],
                "learning_match": r['learning_match']
            }
            for r in okx_failures
        ],
        "key_insights": [
            "ETH 套利 (0.35)：买入 Polymarket YES（ETH < $3,000）+ 卖出 OKX 现货，是对冲而非同向",
            "BTC 套利 (0.62)：买入 Polymarket NO（BTC > $95,000）+ 做空 OKX 永续 + 收资金费率，是三重收益",
            "Agent M 的误判：认为'买 YES + 做多永续'是同向敞口，但实际上应该是'买 YES + 做空永续'或'买 NO + 做多永续'"
        ],
        "required_improvements": [
            "识别 ARBITRAGE 方向，降低 EV 量化要求",
            "验证对冲方向互补性（买 YES 对应做空，买 NO 对应做多）",
            "重点检查资金费率优势（年化 > 50%）和现货价差（> 5%）",
            "不要求精确的 EV 计算，套利本身就是锁定价差"
        ]
    }
    
    # 保存学习输入
    learning_input_file = data_dir / "learning_input_okx_arbitrage.json"
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
    print("Agent G 学习报告（聚焦 OKX 套利）")
    print("=" * 60)
    print()
    
    # 提取关键洞察
    rejection_analysis = learning_report.get('rejection_analysis', {})
    
    print("识别的问题:")
    for i, mistake in enumerate(rejection_analysis.get('common_mistakes', []), 1):
        print(f"{i}. {mistake}")
    print()
    
    print("改进建议:")
    for i, suggestion in enumerate(rejection_analysis.get('improvement_suggestions', []), 1):
        print(f"{i}. {suggestion}")
    print()
    
    print("关键洞察:")
    print(rejection_analysis.get('key_insights', ''))
    print()
    
    print("=" * 60)
    print("下一步：更新知识库并重新测试")
    print("=" * 60)

if __name__ == "__main__":
    main()
