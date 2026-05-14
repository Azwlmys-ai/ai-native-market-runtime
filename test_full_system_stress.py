"""
完整系统压力测试
测试场景：
1. 完整扫描周期
2. 20 个交易信号压力测试
3. 反对层负载均衡验证
4. 执行层并发处理
"""

import json
import time
from pathlib import Path
from datetime import datetime

def generate_test_signals(count=20):
    """生成测试信号"""
    signals = []
    
    markets = [
        ("philadelphia-flyers-nhl-2025", "Philadelphia Flyers NHL 2025", 0.0085, 0.9915),
        ("anaheim-ducks-nhl-2025", "Anaheim Ducks NHL 2025", 0.0225, 0.9775),
        ("chicago-blackhawks-nhl-2025", "Chicago Blackhawks NHL 2025", 0.015, 0.985),
        ("san-jose-sharks-nhl-2025", "San Jose Sharks NHL 2025", 0.012, 0.988),
        ("columbus-blue-jackets-nhl-2025", "Columbus Blue Jackets NHL 2025", 0.018, 0.982),
        ("harvey-weinstein-prison-5yrs", "Harvey Weinstein <5 years", 0.038, 0.962),
        ("harvey-weinstein-prison-10yrs", "Harvey Weinstein 5-10 years", 0.039, 0.961),
        ("btc-100k-june-2026", "BTC $100k by June 2026", 0.45, 0.55),
        ("eth-5k-june-2026", "ETH $5k by June 2026", 0.38, 0.62),
        ("trump-reelection-2028", "Trump Re-election 2028", 0.52, 0.48),
    ]
    
    for i in range(count):
        market_idx = i % len(markets)
        slug, question, yes_price, no_price = markets[market_idx]
        
        # 交替生成 YES 和 NO 信号
        direction = "YES" if i % 2 == 0 else "NO"
        price = yes_price if direction == "YES" else no_price
        
        # 模拟不同置信度
        if i < 7:
            confidence = 85 + (i % 5)
            ev = 0.15 + (i % 5) * 0.02
        elif i < 14:
            confidence = 70 + (i % 5)
            ev = 0.10 + (i % 5) * 0.01
        else:
            confidence = 50 + (i % 5)
            ev = 0.08 + (i % 5) * 0.005
        
        signal = {
            "market": f"{slug}-{i}",
            "question": f"{question} (Test {i+1})",
            "direction": direction,
            "price": price,
            "amount": 100 if confidence > 80 else 80 if confidence > 65 else 50,
            "confidence": confidence,
            "ev": ev,
            "reason": f"测试信号 {i+1}: 置信度 {confidence}, EV {ev:.1%}",
            "data_sources": ["test_generator"],
            "orderbook_depth": 50000 + i * 1000,
            "slippage_bps": 10 + i % 20,
            "levels": 1 + i % 3,
            "timestamp": datetime.now().isoformat()
        }
        
        signals.append(signal)
    
    return signals

def save_test_signals(signals):
    """保存测试信号到 signals.json"""
    signals_file = Path("/opt/data/polymarket_arbitrage/data/signals.json")
    
    with open(signals_file, 'w') as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 已生成 {len(signals)} 个测试信号")
    print(f"   高置信度 (>80): {sum(1 for s in signals if s['confidence'] > 80)}")
    print(f"   中置信度 (65-80): {sum(1 for s in signals if 65 < s['confidence'] <= 80)}")
    print(f"   低置信度 (<65): {sum(1 for s in signals if s['confidence'] <= 65)}")
    print(f"   YES 信号: {sum(1 for s in signals if s['direction'] == 'YES')}")
    print(f"   NO 信号: {sum(1 for s in signals if s['direction'] == 'NO')}")

def run_orchestrator():
    """运行完整扫描周期"""
    import subprocess
    
    print("\n" + "="*60)
    print("开始完整系统测试")
    print("="*60)
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            ["python3", "orchestrator.py"],
            cwd="/opt/data/polymarket_arbitrage",
            capture_output=True,
            text=True,
            timeout=300
        )
        
        duration = time.time() - start_time
        
        print(f"\n⏱️  总耗时: {duration:.1f}秒")
        
        if result.returncode == 0:
            print("✅ 系统扫描完成")
        else:
            print(f"❌ 系统扫描失败: {result.stderr}")
        
        return result.returncode == 0, duration
    
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        print(f"⏱️  超时: {duration:.1f}秒")
        return False, duration
    except Exception as e:
        duration = time.time() - start_time
        print(f"❌ 异常: {e}")
        return False, duration

def analyze_agent_m_performance():
    """分析 Agent M 性能"""
    log_file = Path("/opt/data/polymarket_arbitrage/logs/agent_m_20260505.log")
    
    if not log_file.exists():
        print("⚠️  Agent M 日志不存在")
        return
    
    with open(log_file, 'r') as f:
        lines = f.readlines()
    
    # 提取最后一次运行的日志
    last_run_lines = []
    for line in reversed(lines):
        last_run_lines.insert(0, line)
        if "开始审查" in line:
            break
    
    print("\n" + "="*60)
    print("Agent M (反对层) 性能分析")
    print("="*60)
    
    # 统计信号数量
    signal_count = 0
    for line in last_run_lines:
        if "收到" in line and "个信号" in line:
            import re
            match = re.search(r'(\d+)\s*个信号', line)
            if match:
                signal_count = int(match.group(1))
    
    # 检测并发模式
    concurrent = any("并发审查" in line for line in last_run_lines)
    
    # 提取审查结果
    approved = sum(1 for line in last_run_lines if "✅ APPROVE" in line)
    rejected = sum(1 for line in last_run_lines if "❌ REJECT" in line)
    
    print(f"信号数量: {signal_count}")
    print(f"处理模式: {'🔀 并发' if concurrent else '➡️  串行'}")
    print(f"审查结果: APPROVE {approved}, REJECT {rejected}")
    
    # 提取耗时
    start_time = None
    end_time = None
    for line in last_run_lines:
        if "开始审查" in line:
            start_time = line.split("]")[0].strip("[")
        if "审查完成" in line:
            end_time = line.split("]")[0].strip("[")
    
    if start_time and end_time:
        from datetime import datetime
        start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        duration = (end_dt - start_dt).total_seconds()
        print(f"总耗时: {duration:.1f}秒")
        if signal_count > 0:
            print(f"平均每信号: {duration/signal_count:.1f}秒")

def analyze_execution_performance():
    """分析执行层性能"""
    executor_log = Path("/opt/data/polymarket_arbitrage/logs/executor_20260505.log")
    
    if not executor_log.exists():
        print("⚠️  执行器日志不存在")
        return
    
    with open(executor_log, 'r') as f:
        lines = f.readlines()
    
    print("\n" + "="*60)
    print("执行层性能分析")
    print("="*60)
    
    # 统计执行结果
    executed = sum(1 for line in lines if "✅ 执行成功" in line)
    failed = sum(1 for line in lines if "❌ 执行失败" in line)
    skipped = sum(1 for line in lines if "⏭️  跳过" in line)
    
    print(f"执行成功: {executed}")
    print(f"执行失败: {failed}")
    print(f"跳过: {skipped}")

def main():
    print("Polymarket 套利系统 - 完整压力测试")
    print("="*60)
    
    # 1. 生成 20 个测试信号
    print("\n步骤 1: 生成测试信号")
    signals = generate_test_signals(20)
    save_test_signals(signals)
    
    # 2. 运行完整扫描周期
    print("\n步骤 2: 运行完整扫描周期")
    success, duration = run_orchestrator()
    
    if not success:
        print("\n❌ 系统测试失败")
        return
    
    # 3. 分析性能
    print("\n步骤 3: 性能分析")
    analyze_agent_m_performance()
    analyze_execution_performance()
    
    print("\n" + "="*60)
    print("✅ 压力测试完成")
    print("="*60)

if __name__ == "__main__":
    main()
