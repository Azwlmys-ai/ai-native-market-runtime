"""
完整流程测试：反对层 → 执行层 → 评估层
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime

def main():
    base_dir = Path("/opt/data/polymarket_arbitrage")
    data_dir = base_dir / "data"
    
    print("=" * 60)
    print("完整流程测试：18 个信号")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 步骤 1: 反对层（Agent N）
    print("📋 步骤 1/3: 反对层审查（Agent N + 6x Agent M）")
    print("-" * 60)
    
    result = subprocess.run(
        ["python3", "agents/agent_n.py"],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=600
    )
    
    if result.returncode != 0:
        print(f"❌ 反对层失败: {result.stderr}")
        return
    
    # 读取审查结果
    review_file = data_dir / "review_results.json"
    with open(review_file, 'r') as f:
        review_results = json.load(f)
    
    print(f"✅ 反对层完成")
    print(f"   总信号: {review_results['total']}")
    print(f"   通过: {review_results['approved']}")
    print(f"   拒绝: {review_results['rejected']}")
    print(f"   缓存命中率: {review_results['cache_stats']['hit_rate']}")
    print()
    
    if review_results['approved'] == 0:
        print("⚠️  没有信号通过审查，无法继续测试执行层")
        return
    
    # 步骤 2: 执行层（Signal Executor）
    print("📋 步骤 2/3: 执行层买入（Signal Executor）")
    print("-" * 60)
    
    # 将通过的信号保存到 approved_signals.json
    approved_file = data_dir / "approved_signals.json"
    with open(approved_file, 'w') as f:
        json.dump(review_results['approved_signals'], f, indent=2, ensure_ascii=False)
    
    result = subprocess.run(
        ["python3", "executors/signal_executor.py"],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=300
    )
    
    if result.returncode != 0:
        print(f"❌ 执行层失败: {result.stderr}")
        print(f"输出: {result.stdout}")
        return
    
    print(f"✅ 执行层完成")
    print(result.stdout)
    print()
    
    # 步骤 3: 评估层（Agent G）
    print("📋 步骤 3/3: 评估层复盘（Agent G）")
    print("-" * 60)
    
    result = subprocess.run(
        ["python3", "agents/agent_g.py"],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=180
    )
    
    if result.returncode != 0:
        print(f"❌ 评估层失败: {result.stderr}")
        return
    
    print(f"✅ 评估层完成")
    print()
    
    # 读取学习报告
    learning_file = data_dir / "learning_report.json"
    if learning_file.exists():
        with open(learning_file, 'r') as f:
            learning = json.load(f)
        
        print("📊 学习报告摘要:")
        print(f"   分析交易数: {learning.get('total_trades', 0)}")
        print(f"   成功率: {learning.get('success_rate', 'N/A')}")
        print(f"   平均收益: {learning.get('avg_profit', 'N/A')}")
        
        if 'key_insights' in learning:
            print("\n💡 关键洞察:")
            for insight in learning['key_insights'][:3]:
                print(f"   • {insight}")
    
    print()
    print("=" * 60)
    print("完整流程测试完成")
    print("=" * 60)
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
