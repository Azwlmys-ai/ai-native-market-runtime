"""
快速测试 Agent M 数据一致性
对比三次运行的结果哈希
"""

import json
import hashlib
from pathlib import Path

def calculate_result_hash(results):
    """计算结果哈希（只关注决策）"""
    decisions = []
    for r in results:
        decisions.append({
            "market": r["signal"]["market"],
            "decision": r["decision"]
        })
    
    json_str = json.dumps(decisions, sort_keys=True)
    return hashlib.md5(json_str.encode()).hexdigest()

def main():
    base_dir = Path("/opt/data/polymarket_arbitrage")
    results_file = base_dir / "data" / "review_results.json"
    
    if not results_file.exists():
        print("❌ 结果文件不存在")
        return
    
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    all_results = results["approved_signals"] + results["rejected_signals"]
    result_hash = calculate_result_hash(all_results)
    
    print("=" * 60)
    print("Agent M 审查结果")
    print("=" * 60)
    print(f"通过: {results['approved']}")
    print(f"拒绝: {results['rejected']}")
    print(f"缓存命中率: {results['cache_stats']['hit_rate']}")
    print(f"结果哈希: {result_hash}")
    print()
    
    # 显示每个信号的决策
    print("详细决策:")
    for i, r in enumerate(all_results, 1):
        print(f"{i}. {r['signal']['market'][:50]}... → {r['decision']}")

if __name__ == "__main__":
    main()
