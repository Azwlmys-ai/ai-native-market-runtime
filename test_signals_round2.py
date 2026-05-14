"""
第二轮测试框架
测试 10 个信号（5 个跨平台套利 + 5 个 Polymarket 单边）
目标准确率：>= 80%
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime

def main():
    base_dir = Path("/opt/data/polymarket_arbitrage")
    data_dir = base_dir / "data"
    
    print("=" * 60)
    print("第二轮测试：跨平台套利专项")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 加载测试信号
    signals_file = data_dir / "test_signals_round2.json"
    
    if not signals_file.exists():
        print("❌ 测试信号文件不存在")
        print("请先运行: python3 generate_test_signals_round2.py")
        return
    
    with open(signals_file, 'r') as f:
        signals = json.load(f)
    
    print(f"📊 加载 {len(signals)} 个测试信号")
    
    # 分类统计
    arbitrage_count = sum(1 for s in signals if s.get("market_type") == "跨平台套利")
    polymarket_count = sum(1 for s in signals if s.get("market_type") != "跨平台套利")
    
    print(f"   跨平台套利: {arbitrage_count} 个")
    print(f"   Polymarket 单边: {polymarket_count} 个")
    print()
    
    # 将信号转换为 Agent M 可识别的格式
    agent_signals = []
    for signal in signals:
        agent_signal = {
            "market": signal["market"],
            "direction": signal["direction"],
            "price": signal.get("price", 0),
            "amount": signal["amount"],
            "confidence": signal["confidence"],
            "reason": signal["reason"],
            "source": signal["source"],
            "data_sources": signal["data_sources"]
        }
        
        # 添加跨平台套利特有字段
        if signal.get("market_type") == "跨平台套利":
            agent_signal.update({
                "okx_funding_rate": signal.get("okx_funding_rate"),
                "okx_spot_price": signal.get("okx_spot_price"),
                "hedge_direction": signal.get("hedge_direction"),
                "hedge_ratio": signal.get("hedge_ratio"),
                "price_spread": signal.get("price_spread"),
                "funding_rate_annualized": signal.get("funding_rate_annualized"),
                "okx_perpetual_price": signal.get("okx_perpetual_price")
            })
        
        agent_signals.append(agent_signal)
    
    # 保存为 signals.json
    with open(data_dir / "signals.json", 'w') as f:
        json.dump(agent_signals, f, indent=2, ensure_ascii=False)
    
    # 清空缓存
    cache_file = data_dir / "review_cache" / "cache.json"
    if cache_file.exists():
        cache_file.unlink()
        print("✅ 缓存已清空")
    
    print()
    print("🧠 运行 Agent M 审查...")
    print("-" * 60)
    
    # 运行 Agent M
    result = subprocess.run(
        ["python3", "agents/agent_m.py"],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=300
    )
    
    if result.returncode != 0:
        print(f"❌ Agent M 运行失败: {result.stderr}")
        return
    
    print(result.stdout)
    print()
    
    # 加载审查结果
    review_file = data_dir / "review_results.json"
    with open(review_file, 'r') as f:
        review_data = json.load(f)
    
    # 对比预期和实际结果
    print("=" * 60)
    print("对比预期和实际结果")
    print("=" * 60)
    print()
    
    all_reviews = review_data.get('approved_signals', []) + review_data.get('rejected_signals', [])
    
    correct_count = 0
    total_count = len(signals)
    
    results = []
    
    for i, signal in enumerate(signals, 1):
        # 找到对应的审查结果
        review = None
        for r in all_reviews:
            if r['signal']['market'] == signal['market']:
                review = r
                break
        
        if not review:
            print(f"{i}. ❓ {signal['market'][:70]}...")
            print(f"   未找到审查结果")
            print()
            continue
        
        expected = signal.get('expected_outcome')
        actual = review.get('decision')
        is_correct = (expected == actual)
        
        if is_correct:
            correct_count += 1
        
        icon = "✅" if is_correct else "❌"
        
        print(f"{i}. {icon} {signal['market'][:70]}...")
        print(f"   市场类型: {signal.get('market_type')}")
        print(f"   价格: {signal.get('price')}")
        print(f"   预期决策: {expected}")
        print(f"   Agent M 决策: {actual}")
        
        if signal.get('market_type') == '跨平台套利':
            print(f"   对冲方向: {signal.get('hedge_direction', 'N/A')[:60]}...")
            print(f"   资金费率: {signal.get('okx_funding_rate')} (年化 {signal.get('funding_rate_annualized')})")
        
        print(f"   学习匹配: {signal.get('learning_match')}")
        
        if not is_correct:
            print(f"   失败概率: {review.get('review', {}).get('failure_probability')}%")
            risk_points = review.get('review', {}).get('risk_points', [])
            if risk_points:
                print(f"   主要风险: {risk_points[0][:150]}...")
        
        print()
        
        results.append({
            "market": signal['market'],
            "market_type": signal.get('market_type'),
            "expected": expected,
            "actual": actual,
            "is_correct": is_correct
        })
    
    # 统计摘要
    print("=" * 60)
    print("统计摘要")
    print("=" * 60)
    print(f"总信号数: {total_count}")
    print(f"正确决策: {correct_count} ({correct_count/total_count*100:.1f}%)")
    print(f"错误决策: {total_count - correct_count} ({(total_count - correct_count)/total_count*100:.1f}%)")
    print()
    
    # 按市场类型分析
    print("按市场类型分析:")
    market_types = {}
    for r in results:
        mt = r['market_type']
        if mt not in market_types:
            market_types[mt] = {'correct': 0, 'total': 0}
        market_types[mt]['total'] += 1
        if r['is_correct']:
            market_types[mt]['correct'] += 1
    
    for mt, stats in market_types.items():
        accuracy = stats['correct'] / stats['total'] * 100
        print(f"  {mt}: {stats['correct']}/{stats['total']} ({accuracy:.1f}%)")
    print()
    
    # 跨平台套利专项分析
    arbitrage_results = [r for r in results if r['market_type'] == '跨平台套利']
    arbitrage_correct = sum(1 for r in arbitrage_results if r['is_correct'])
    arbitrage_total = len(arbitrage_results)
    
    print("跨平台套利专项分析:")
    print(f"  准确率: {arbitrage_correct}/{arbitrage_total} ({arbitrage_correct/arbitrage_total*100:.1f}%)")
    print(f"  应该通过的信号: {arbitrage_correct}/{arbitrage_total}")
    print()
    
    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "total": total_count,
        "correct": correct_count,
        "accuracy": correct_count / total_count * 100,
        "market_types": market_types,
        "arbitrage_accuracy": arbitrage_correct / arbitrage_total * 100 if arbitrage_total > 0 else 0,
        "results": results
    }
    
    report_file = data_dir / "test_report_round2.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print("=" * 60)
    print("测试完成")
    print("=" * 60)
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print(f"📊 测试报告已保存到: {report_file}")
    print()
    
    # 判断是否达到目标
    if correct_count / total_count >= 0.8:
        print("✅ 达到目标准确率（>= 80%），可以进入真实交易状态")
    else:
        print("❌ 未达到目标准确率（< 80%），需要继续优化")

if __name__ == "__main__":
    main()
