#!/usr/bin/env python3
"""
负载均衡器压力测试脚本
测试不同信号数量下的性能表现
"""

import json
import time
import subprocess
from pathlib import Path

def create_test_signals(count):
    """创建测试信号"""
    signals = []
    markets = [
        "will-the-los-angeles-lakers-win-the-2026-nba-finals",
        "will-harvey-weinstein-be-sentenced-to-more-than-30-years-in-prison",
        "will-the-colorado-avalanche-win-the-2026-nhl-stanley-cup",
        "will-the-anaheim-ducks-win-the-2026-nhl-stanley-cup",
        "will-the-san-antonio-spurs-win-the-2026-nba-finals",
        "will-the-golden-state-warriors-win-the-2026-nba-finals",
        "will-the-tampa-bay-lightning-win-the-2026-nhl-stanley-cup",
        "will-the-vegas-golden-knights-win-the-2026-nhl-stanley-cup",
        "will-the-boston-celtics-win-the-2026-nba-finals",
        "will-the-miami-heat-win-the-2026-nba-finals",
        "will-the-toronto-maple-leafs-win-the-2026-nhl-stanley-cup",
        "will-the-new-york-rangers-win-the-2026-nhl-stanley-cup",
    ]
    
    for i in range(count):
        market = markets[i % len(markets)]
        signals.append({
            "market": f"{market}-test-{i}",
            "direction": "buy_no",
            "price": 0.05 + (i * 0.01),
            "amount": 100 + (i * 10),
            "confidence": 70 + (i % 20),
            "reason": f"Test signal {i+1} for load balancer stress test",
            "source": "test",
            "timestamp": "2026-05-03T12:00:00"
        })
    
    return signals

def run_test(signal_count, use_load_balancer=True):
    """运行单次测试"""
    print(f"\n{'='*60}")
    print(f"测试: {signal_count} 个信号")
    print(f"模式: {'负载均衡 (Agent N)' if use_load_balancer else '单 Agent M'}")
    print(f"{'='*60}")
    
    # 创建测试信号
    signals = create_test_signals(signal_count)
    signals_file = Path("/opt/data/polymarket_arbitrage/data/signals.json")
    
    with open(signals_file, 'w') as f:
        json.dump(signals, f, indent=2)
    
    print(f"✅ 已创建 {signal_count} 个测试信号")
    
    # 运行测试
    start_time = time.time()
    
    if use_load_balancer:
        # 使用 Agent N 负载均衡
        cmd = ["python3", "/opt/data/polymarket_arbitrage/agents/agent_n.py"]
    else:
        # 使用单个 Agent M
        cmd = ["python3", "/opt/data/polymarket_arbitrage/agents/agent_m.py"]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print(f"✅ 测试完成")
            print(f"⏱️  执行时间: {elapsed:.1f} 秒")
            
            # 解析结果
            review_file = Path("/opt/data/polymarket_arbitrage/data/review_results.json")
            if review_file.exists():
                with open(review_file, 'r') as f:
                    results = json.load(f)
                
                print(f"📊 审查结果:")
                print(f"   - 总信号: {results['total']}")
                print(f"   - 通过: {results['approved']}")
                print(f"   - 拒绝: {results['rejected']}")
            
            return {
                "signal_count": signal_count,
                "mode": "load_balancer" if use_load_balancer else "single_agent",
                "elapsed": elapsed,
                "success": True
            }
        else:
            print(f"❌ 测试失败")
            print(f"错误: {result.stderr[:200]}")
            return {
                "signal_count": signal_count,
                "mode": "load_balancer" if use_load_balancer else "single_agent",
                "elapsed": elapsed,
                "success": False,
                "error": result.stderr[:200]
            }
    
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        print(f"⏱️  测试超时 (>{elapsed:.1f} 秒)")
        return {
            "signal_count": signal_count,
            "mode": "load_balancer" if use_load_balancer else "single_agent",
            "elapsed": elapsed,
            "success": False,
            "error": "timeout"
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 测试异常: {e}")
        return {
            "signal_count": signal_count,
            "mode": "load_balancer" if use_load_balancer else "single_agent",
            "elapsed": elapsed,
            "success": False,
            "error": str(e)
        }

def main():
    print("🚀 负载均衡器压力测试")
    print("="*60)
    
    # 测试场景
    test_cases = [
        {"count": 3, "name": "轻负载（3 个信号）"},
        {"count": 6, "name": "中负载（6 个信号）"},
        {"count": 9, "name": "重负载（9 个信号）"},
        {"count": 12, "name": "超重负载（12 个信号）"},
    ]
    
    results = []
    
    # 对比测试：负载均衡 vs 单 Agent
    for test_case in test_cases:
        print(f"\n\n{'#'*60}")
        print(f"# {test_case['name']}")
        print(f"{'#'*60}")
        
        # 测试负载均衡模式
        result_lb = run_test(test_case["count"], use_load_balancer=True)
        results.append(result_lb)
        
        time.sleep(2)  # 等待 2 秒
        
        # 测试单 Agent 模式（仅测试 ≤9 个信号，避免超时）
        if test_case["count"] <= 9:
            result_single = run_test(test_case["count"], use_load_balancer=False)
            results.append(result_single)
            
            # 对比
            if result_lb["success"] and result_single["success"]:
                speedup = result_single["elapsed"] / result_lb["elapsed"]
                print(f"\n📈 性能对比:")
                print(f"   - 单 Agent: {result_single['elapsed']:.1f} 秒")
                print(f"   - 负载均衡: {result_lb['elapsed']:.1f} 秒")
                print(f"   - 加速比: {speedup:.2f}x")
        
        time.sleep(2)  # 等待 2 秒
    
    # 汇总报告
    print(f"\n\n{'='*60}")
    print("📊 测试汇总报告")
    print(f"{'='*60}")
    
    print(f"\n{'信号数':<10} {'模式':<15} {'耗时(秒)':<12} {'状态':<10}")
    print("-" * 60)
    
    for r in results:
        mode_name = "负载均衡" if r["mode"] == "load_balancer" else "单Agent"
        status = "✅ 成功" if r["success"] else "❌ 失败"
        elapsed_str = f"{r['elapsed']:.1f}" if r["success"] else "N/A"
        
        print(f"{r['signal_count']:<10} {mode_name:<15} {elapsed_str:<12} {status:<10}")
    
    # 保存结果
    report_file = Path("/opt/data/polymarket_arbitrage/load_balancer_test_report.json")
    with open(report_file, 'w') as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "results": results
        }, f, indent=2)
    
    print(f"\n✅ 测试报告已保存到: {report_file}")

if __name__ == "__main__":
    main()
