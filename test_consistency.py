"""
测试 Agent M 的数据一致性（方案 A + D）
验证：
1. 低温度（temperature=0.1）是否提高一致性
2. 缓存机制是否正常工作
3. 相同信号是否产生相同结果
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime

def generate_test_signals():
    """生成 9 个测试信号"""
    return [
        {
            "market": "Will Bitcoin reach $100k by June 2026?",
            "direction": "YES",
            "price": 0.65,
            "amount": 150,
            "confidence": 75,
            "reason": "Strong technical breakout + institutional adoption",
            "source": "Agent K"
        },
        {
            "market": "Will Trump win 2026 midterms?",
            "direction": "NO",
            "price": 0.45,
            "amount": 200,
            "confidence": 60,
            "reason": "Historical midterm patterns favor opposition",
            "source": "Agent B"
        },
        {
            "market": "Will Fed cut rates in Q2 2026?",
            "direction": "YES",
            "price": 0.70,
            "amount": 180,
            "confidence": 80,
            "reason": "Inflation cooling + recession signals",
            "source": "Agent K"
        },
        {
            "market": "Will Lakers win NBA championship 2026?",
            "direction": "NO",
            "price": 0.25,
            "amount": 100,
            "confidence": 55,
            "reason": "Injury concerns + tough Western Conference",
            "source": "Agent B"
        },
        {
            "market": "Will Ethereum merge to PoS succeed?",
            "direction": "YES",
            "price": 0.85,
            "amount": 250,
            "confidence": 90,
            "reason": "Successful testnet + developer consensus",
            "source": "Agent K"
        },
        {
            "market": "Will Apple release AR glasses in 2026?",
            "direction": "NO",
            "price": 0.40,
            "amount": 120,
            "confidence": 65,
            "reason": "Supply chain delays + tech not ready",
            "source": "Agent B"
        },
        {
            "market": "Will oil prices exceed $120 by summer?",
            "direction": "YES",
            "price": 0.55,
            "amount": 160,
            "confidence": 70,
            "reason": "OPEC cuts + geopolitical tensions",
            "source": "Agent K"
        },
        {
            "market": "Will Tesla stock hit $300 in 2026?",
            "direction": "YES",
            "price": 0.60,
            "amount": 140,
            "confidence": 68,
            "reason": "Production ramp + new model launch",
            "source": "Agent B"
        },
        {
            "market": "Will unemployment rate drop below 3%?",
            "direction": "NO",
            "price": 0.35,
            "amount": 110,
            "confidence": 62,
            "reason": "Economic slowdown + layoffs increasing",
            "source": "Agent K"
        }
    ]

def calculate_result_hash(results):
    """计算结果哈希（只关注决策，不关注时间戳）"""
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
    data_dir = base_dir / "data"
    
    signals = generate_test_signals()
    
    print("=" * 60)
    print("测试 Agent M 数据一致性（方案 A + D）")
    print("=" * 60)
    print(f"测试信号数量: {len(signals)}")
    print(f"方案 A: temperature=0.1（低温度提高一致性）")
    print(f"方案 D: 缓存机制（相同信号返回相同结果）")
    print()
    
    # 第一次运行（清空缓存）
    print("🧪 第一次运行（清空缓存）...")
    cache_file = data_dir / "review_cache" / "cache.json"
    if cache_file.exists():
        cache_file.unlink()
        print("✅ 缓存已清空")
    
    signals_file = data_dir / "signals.json"
    with open(signals_file, 'w') as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)
    
    import subprocess
    result1 = subprocess.run(
        ["python3", "agents/agent_m.py"],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result1.returncode != 0:
        print(f"❌ 第一次运行失败: {result1.stderr}")
        return
    
    with open(data_dir / "review_results.json", 'r') as f:
        results1 = json.load(f)
    
    hash1 = calculate_result_hash(results1["approved_signals"] + results1["rejected_signals"])
    
    print(f"✅ 第一次运行完成")
    print(f"   通过: {results1['approved']}, 拒绝: {results1['rejected']}")
    print(f"   缓存命中率: {results1['cache_stats']['hit_rate']}")
    print(f"   结果哈希: {hash1}")
    print()
    
    # 第二次运行（使用缓存）
    print("🧪 第二次运行（使用缓存）...")
    
    result2 = subprocess.run(
        ["python3", "agents/agent_m.py"],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result2.returncode != 0:
        print(f"❌ 第二次运行失败: {result2.stderr}")
        return
    
    with open(data_dir / "review_results.json", 'r') as f:
        results2 = json.load(f)
    
    hash2 = calculate_result_hash(results2["approved_signals"] + results2["rejected_signals"])
    
    print(f"✅ 第二次运行完成")
    print(f"   通过: {results2['approved']}, 拒绝: {results2['rejected']}")
    print(f"   缓存命中率: {results2['cache_stats']['hit_rate']}")
    print(f"   结果哈希: {hash2}")
    print()
    
    # 第三次运行（清空缓存，验证低温度一致性）
    print("🧪 第三次运行（清空缓存，验证低温度一致性）...")
    if cache_file.exists():
        cache_file.unlink()
        print("✅ 缓存已清空")
    
    result3 = subprocess.run(
        ["python3", "agents/agent_m.py"],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=120
    )
    
    if result3.returncode != 0:
        print(f"❌ 第三次运行失败: {result3.stderr}")
        return
    
    with open(data_dir / "review_results.json", 'r') as f:
        results3 = json.load(f)
    
    hash3 = calculate_result_hash(results3["approved_signals"] + results3["rejected_signals"])
    
    print(f"✅ 第三次运行完成")
    print(f"   通过: {results3['approved']}, 拒绝: {results3['rejected']}")
    print(f"   缓存命中率: {results3['cache_stats']['hit_rate']}")
    print(f"   结果哈希: {hash3}")
    print()
    
    # 验证结果
    print("=" * 60)
    print("验证结果")
    print("=" * 60)
    
    # 验证缓存机制
    if results2['cache_stats']['hit_rate'] == "100.0%":
        print("✅ 缓存机制正常：第二次运行 100% 命中缓存")
    else:
        print(f"⚠️  缓存机制异常：第二次运行命中率 {results2['cache_stats']['hit_rate']}")
    
    # 验证数据一致性（缓存）
    if hash1 == hash2:
        print("✅ 缓存一致性：第一次和第二次结果完全一致")
    else:
        print(f"❌ 缓存一致性失败：哈希不匹配")
        print(f"   第一次: {hash1}")
        print(f"   第二次: {hash2}")
    
    # 验证数据一致性（低温度）
    if hash1 == hash3:
        print("✅ 低温度一致性：第一次和第三次结果完全一致（temperature=0.1 生效）")
    else:
        print(f"⚠️  低温度一致性：哈希不同（LLM 仍有随机性）")
        print(f"   第一次: {hash1}")
        print(f"   第三次: {hash3}")
        
        # 检查决策数量是否一致
        if results1['approved'] == results3['approved'] and results1['rejected'] == results3['rejected']:
            print("   ✅ 但通过/拒绝数量一致，说明整体决策稳定")
        else:
            print("   ❌ 通过/拒绝数量不一致，说明决策不稳定")
    
    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
