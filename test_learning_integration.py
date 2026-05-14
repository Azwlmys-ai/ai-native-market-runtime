"""
测试学习成果集成
运行 Agent M 审查历史信号，对比结果与实际市场
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime

def main():
    base_dir = Path("/opt/data/polymarket_arbitrage")
    data_dir = base_dir / "data"
    
    print("=" * 60)
    print("测试学习成果集成")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 加载历史测试信号
    signals_file = data_dir / "historical_test_signals.json"
    
    if not signals_file.exists():
        print("❌ 历史测试信号文件不存在")
        print("请先运行: python3 generate_historical_signals.py")
        return
    
    with open(signals_file, 'r') as f:
        signals = json.load(f)
    
    print(f"📊 加载 {len(signals)} 个历史测试信号")
    print()
    
    # 将信号转换为 Agent M 可识别的格式
    agent_signals = []
    for signal in signals:
        agent_signals.append({
            "market": signal["market"],
            "direction": signal["direction"],
            "price": signal["price"],
            "amount": signal["amount"],
            "confidence": signal["confidence"],
            "reason": signal["reason"],
            "source": signal["source"],
            "data_sources": signal["data_sources"]
        })
    
    # 保存为 signals.json
    with open(data_dir / "signals.json", 'w') as f:
        json.dump(agent_signals, f, indent=2, ensure_ascii=False)
    
    # 清空缓存
    cache_file = data_dir / "review_cache" / "cache.json"
    if cache_file.exists():
        cache_file.unlink()
        print("✅ 缓存已清空")
    
    # 运行 Agent M
    print("🔍 运行 Agent M 审查...")
    print("-" * 60)
    
    result = subprocess.run(
        ["python3", "agents/agent_m.py"],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=180
    )
    
    if result.returncode != 0:
        print(f"❌ Agent M 运行失败: {result.stderr}")
        return
    
    print(result.stdout)
    print()
    
    # 加载审查结果
    review_file = data_dir / "review_results.json"
    with open(review_file, 'r') as f:
        review_results = json.load(f)
    
    print("=" * 60)
    print("对比分析：Agent M 决策 vs 实际市场结果")
    print("=" * 60)
    print()
    
    # 生成对比报告
    approved_markets = {r["signal"]["market"] for r in review_results.get("approved_signals", [])}
    rejected_markets = {r["signal"]["market"] for r in review_results.get("rejected_signals", [])}
    
    correct_count = 0
    incorrect_count = 0
    
    results = []
    
    for signal in signals:
        market = signal["market"]
        expected = signal["expected_outcome"]
        
        # Agent M 的决策
        if market in approved_markets:
            agent_decision = "APPROVE"
        elif market in rejected_markets:
            agent_decision = "REJECT"
        else:
            agent_decision = "UNKNOWN"
        
        # 判断是否正确
        if expected == "REJECT":
            is_correct = (agent_decision == "REJECT")
        else:
            is_correct = (agent_decision == "APPROVE")
        
        if is_correct:
            correct_count += 1
            status = "✅"
        else:
            incorrect_count += 1
            status = "❌"
        
        results.append({
            "market": market,
            "market_type": signal["market_type"],
            "price": signal["price"],
            "expected": expected,
            "agent_decision": agent_decision,
            "actual_result": signal["actual_result"],
            "learning_match": signal["learning_match"],
            "is_correct": is_correct,
            "status": status
        })
    
    # 显示结果
    print("详细对比:")
    print()
    
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['status']} {r['market'][:60]}")
        print(f"   市场类型: {r['market_type']}")
        print(f"   价格: {r['price']}")
        print(f"   预期决策: {r['expected']}")
        print(f"   Agent M 决策: {r['agent_decision']}")
        print(f"   实际结果: {r['actual_result']}")
        print(f"   学习匹配: {r['learning_match']}")
        print()
    
    # 统计摘要
    print("=" * 60)
    print("统计摘要")
    print("=" * 60)
    print(f"总信号数: {len(signals)}")
    print(f"正确决策: {correct_count} ({correct_count / len(signals) * 100:.1f}%)")
    print(f"错误决策: {incorrect_count} ({incorrect_count / len(signals) * 100:.1f}%)")
    print()
    
    # 按市场类型分析
    print("按市场类型分析:")
    
    type_stats = {}
    for r in results:
        market_type = r["market_type"]
        if market_type not in type_stats:
            type_stats[market_type] = {"correct": 0, "total": 0}
        
        type_stats[market_type]["total"] += 1
        if r["is_correct"]:
            type_stats[market_type]["correct"] += 1
    
    for market_type, stats in type_stats.items():
        accuracy = stats["correct"] / stats["total"] * 100
        print(f"  {market_type}: {stats['correct']}/{stats['total']} ({accuracy:.1f}%)")
    
    print()
    
    # 学习成果应用效果
    print("学习成果应用效果:")
    
    # 应该通过的信号（符合学习成果）
    good_signals = [r for r in results if "✅ 符合" in r["learning_match"]]
    good_correct = sum(1 for r in good_signals if r["is_correct"])
    
    # 应该拒绝的信号（违反学习成果）
    bad_signals = [r for r in results if "❌ 违反" in r["learning_match"]]
    bad_correct = sum(1 for r in bad_signals if r["is_correct"])
    
    print(f"  符合学习成果的信号: {good_correct}/{len(good_signals)} 正确 ({good_correct / len(good_signals) * 100:.1f}%)")
    print(f"  违反学习成果的信号: {bad_correct}/{len(bad_signals)} 正确 ({bad_correct / len(bad_signals) * 100:.1f}%)")
    
    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 保存对比报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_signals": len(signals),
        "correct": correct_count,
        "incorrect": incorrect_count,
        "accuracy": f"{correct_count / len(signals) * 100:.1f}%",
        "results": results,
        "type_stats": type_stats,
        "learning_effectiveness": {
            "符合学习成果": f"{good_correct}/{len(good_signals)} ({good_correct / len(good_signals) * 100:.1f}%)",
            "违反学习成果": f"{bad_correct}/{len(bad_signals)} ({bad_correct / len(bad_signals) * 100:.1f}%)"
        }
    }
    
    report_file = data_dir / "learning_integration_report.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n📊 对比报告已保存到: {report_file}")

if __name__ == "__main__":
    main()
