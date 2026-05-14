#!/usr/bin/env python3
"""
综合压力测试脚本
测试：1. 负载压力  2. 数据一致性  3. 执行层拥堵
"""

import json
import time
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime

class ComprehensiveTest:
    def __init__(self):
        self.base_dir = Path("/opt/data/polymarket_arbitrage")
        self.data_dir = self.base_dir / "data"
        self.temp_dir = self.data_dir / "temp"
        self.results = []
    
    def log(self, message):
        """打印日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def create_test_signals(self, count, approved_ratio=0.3):
        """
        创建测试信号
        approved_ratio: 预期通过率（0-1）
        """
        signals = []
        markets = [
            "will-bitcoin-reach-100k-by-2026",
            "will-ethereum-reach-10k-by-2026",
            "will-trump-win-2024-election",
            "will-fed-cut-rates-in-q2-2026",
            "will-sp500-reach-6000-by-2026",
            "will-tesla-stock-double-in-2026",
            "will-apple-launch-vr-headset-in-2026",
            "will-openai-release-gpt5-in-2026",
            "will-spacex-land-on-mars-in-2026",
            "will-china-invade-taiwan-in-2026",
            "will-nuclear-fusion-breakthrough-in-2026",
            "will-quantum-computer-break-rsa-in-2026",
        ]
        
        for i in range(count):
            market = markets[i % len(markets)]
            
            # 构造不同质量的信号
            if i % 10 < approved_ratio * 10:
                # 高质量信号（可能通过）
                confidence = 85 + (i % 10)
                reason = f"Strong data support: historical correlation 0.85+, volume $50M+, clear resolution criteria, low volatility market. Signal {i+1}"
            else:
                # 低质量信号（可能拒绝）
                confidence = 60 + (i % 20)
                reason = f"Test signal {i+1} with weak evidence and unclear logic"
            
            signals.append({
                "market": f"{market}-test-{i}",
                "direction": "buy_yes" if i % 2 == 0 else "buy_no",
                "price": 0.3 + (i * 0.02) % 0.6,
                "amount": 100 + (i * 20),
                "confidence": confidence,
                "reason": reason,
                "source": "test",
                "timestamp": datetime.now().isoformat(),
                "test_id": i  # 用于追踪
            })
        
        return signals
    
    def calculate_hash(self, data):
        """计算数据哈希值"""
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(json_str.encode()).hexdigest()
    
    def test_1_load_balancer_stress(self):
        """测试 1：负载均衡器压力测试"""
        self.log("=" * 60)
        self.log("测试 1：负载均衡器压力测试")
        self.log("=" * 60)
        
        test_cases = [
            {"count": 6, "name": "中等负载"},
            {"count": 12, "name": "高负载"},
            {"count": 18, "name": "超高负载（超出上限）"},
        ]
        
        for case in test_cases:
            self.log(f"\n📊 {case['name']}: {case['count']} 个信号")
            
            # 创建信号
            signals = self.create_test_signals(case["count"])
            signals_file = self.data_dir / "signals.json"
            
            with open(signals_file, 'w') as f:
                json.dump(signals, f, indent=2)
            
            # 记录输入哈希
            input_hash = self.calculate_hash(signals)
            self.log(f"   输入哈希: {input_hash[:8]}")
            
            # 运行 Agent N
            start_time = time.time()
            
            try:
                result = subprocess.run(
                    ["python3", str(self.base_dir / "agents" / "agent_n.py")],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                elapsed = time.time() - start_time
                
                if result.returncode == 0:
                    self.log(f"   ✅ 完成 (耗时 {elapsed:.1f} 秒)")
                    
                    # 验证结果
                    review_file = self.data_dir / "review_results.json"
                    if review_file.exists():
                        with open(review_file, 'r') as f:
                            results = json.load(f)
                        
                        self.log(f"   📊 审查: {results['total']} 个, 通过: {results['approved']}, 拒绝: {results['rejected']}")
                        
                        # 数据一致性检查
                        total_reviewed = results['approved'] + results['rejected']
                        if total_reviewed == case["count"]:
                            self.log(f"   ✅ 数据一致性: 通过")
                        else:
                            self.log(f"   ❌ 数据一致性: 失败 (输入 {case['count']}, 输出 {total_reviewed})")
                        
                        self.results.append({
                            "test": "load_balancer_stress",
                            "signal_count": case["count"],
                            "elapsed": elapsed,
                            "success": True,
                            "data_consistent": total_reviewed == case["count"]
                        })
                    else:
                        self.log(f"   ❌ 结果文件不存在")
                else:
                    self.log(f"   ❌ 失败: {result.stderr[:100]}")
            
            except subprocess.TimeoutExpired:
                elapsed = time.time() - start_time
                self.log(f"   ⏱️  超时 (>{elapsed:.1f} 秒)")
                self.results.append({
                    "test": "load_balancer_stress",
                    "signal_count": case["count"],
                    "elapsed": elapsed,
                    "success": False,
                    "error": "timeout"
                })
            
            time.sleep(2)
    
    def test_2_data_consistency(self):
        """测试 2：数据一致性和缓存"""
        self.log("\n" + "=" * 60)
        self.log("测试 2：数据一致性和缓存测试")
        self.log("=" * 60)
        
        # 创建 9 个信号
        signals = self.create_test_signals(9)
        signals_file = self.data_dir / "signals.json"
        
        with open(signals_file, 'w') as f:
            json.dump(signals, f, indent=2)
        
        self.log(f"\n📊 创建 9 个信号")
        
        # 第一次运行
        self.log("\n🔄 第一次运行...")
        result1 = subprocess.run(
            ["python3", str(self.base_dir / "agents" / "agent_n.py")],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # 读取第一次结果
        review_file = self.data_dir / "review_results.json"
        with open(review_file, 'r') as f:
            results1 = json.load(f)
        
        hash1 = self.calculate_hash(results1)
        self.log(f"   结果哈希: {hash1[:8]}")
        self.log(f"   通过: {results1['approved']}, 拒绝: {results1['rejected']}")
        
        time.sleep(2)
        
        # 第二次运行（相同输入）
        self.log("\n🔄 第二次运行（相同输入）...")
        result2 = subprocess.run(
            ["python3", str(self.base_dir / "agents" / "agent_n.py")],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # 读取第二次结果
        with open(review_file, 'r') as f:
            results2 = json.load(f)
        
        hash2 = self.calculate_hash(results2)
        self.log(f"   结果哈希: {hash2[:8]}")
        self.log(f"   通过: {results2['approved']}, 拒绝: {results2['rejected']}")
        
        # 对比结果（忽略 timestamp）
        results1_copy = {k: v for k, v in results1.items() if k != 'timestamp'}
        results2_copy = {k: v for k, v in results2.items() if k != 'timestamp'}
        
        if results1_copy == results2_copy:
            self.log(f"\n   ✅ 数据一致性: 两次运行结果完全一致")
            consistent = True
        else:
            self.log(f"\n   ❌ 数据一致性: 两次运行结果不一致")
            self.log(f"      第一次: 通过 {results1['approved']}, 拒绝 {results1['rejected']}")
            self.log(f"      第二次: 通过 {results2['approved']}, 拒绝 {results2['rejected']}")
            consistent = False
        
        # 检查临时文件是否清理
        temp_files = list(self.temp_dir.glob("*_batch_*.json"))
        if len(temp_files) == 0:
            self.log(f"   ✅ 临时文件清理: 通过")
            cache_clean = True
        else:
            self.log(f"   ⚠️  临时文件清理: 发现 {len(temp_files)} 个残留文件")
            cache_clean = False
        
        self.results.append({
            "test": "data_consistency",
            "consistent": consistent,
            "cache_clean": cache_clean
        })
    
    def test_3_execution_layer_congestion(self):
        """测试 3：执行层拥堵测试"""
        self.log("\n" + "=" * 60)
        self.log("测试 3：执行层拥堵测试")
        self.log("=" * 60)
        
        # 创建 12 个高质量信号（预期通过率 80%）
        signals = self.create_test_signals(12, approved_ratio=0.8)
        signals_file = self.data_dir / "signals.json"
        
        with open(signals_file, 'w') as f:
            json.dump(signals, f, indent=2)
        
        self.log(f"\n📊 创建 12 个信号（预期 80% 通过）")
        
        # 运行 Agent N
        self.log("\n🔄 运行 Agent N...")
        start_time = time.time()
        
        result = subprocess.run(
            ["python3", str(self.base_dir / "agents" / "agent_n.py")],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        review_elapsed = time.time() - start_time
        self.log(f"   ✅ Agent N 完成 (耗时 {review_elapsed:.1f} 秒)")
        
        # 读取审查结果
        review_file = self.data_dir / "review_results.json"
        with open(review_file, 'r') as f:
            review_results = json.load(f)
        
        approved_count = review_results['approved']
        self.log(f"   📊 通过信号: {approved_count} 个")
        
        # 模拟执行层处理
        if approved_count > 0:
            self.log(f"\n🔄 模拟执行层处理 {approved_count} 个信号...")
            
            # 假设每个信号执行需要 2 秒
            execution_time_per_signal = 2
            
            # 串行执行
            serial_time = approved_count * execution_time_per_signal
            self.log(f"   串行执行预计: {serial_time} 秒")
            
            # 并行执行（假设最多 3 个并发）
            max_concurrent = 3
            parallel_time = (approved_count / max_concurrent) * execution_time_per_signal
            self.log(f"   并行执行预计: {parallel_time:.1f} 秒 (最多 {max_concurrent} 并发)")
            
            # 判断是否会拥堵
            if approved_count > 5:
                self.log(f"   ⚠️  执行层可能拥堵: {approved_count} 个信号需要排队")
                congestion_risk = True
            else:
                self.log(f"   ✅ 执行层不会拥堵: {approved_count} 个信号可快速处理")
                congestion_risk = False
            
            self.results.append({
                "test": "execution_layer_congestion",
                "approved_count": approved_count,
                "serial_time": serial_time,
                "parallel_time": parallel_time,
                "congestion_risk": congestion_risk
            })
        else:
            self.log(f"   ℹ️  无通过信号，执行层无压力")
            self.results.append({
                "test": "execution_layer_congestion",
                "approved_count": 0,
                "congestion_risk": False
            })
    
    def generate_report(self):
        """生成测试报告"""
        self.log("\n" + "=" * 60)
        self.log("📊 综合测试报告")
        self.log("=" * 60)
        
        # 测试 1：负载压力
        self.log("\n【测试 1：负载压力】")
        stress_tests = [r for r in self.results if r.get("test") == "load_balancer_stress"]
        for t in stress_tests:
            status = "✅" if t["success"] else "❌"
            consistency = "✅" if t.get("data_consistent", False) else "❌"
            self.log(f"  {status} {t['signal_count']} 个信号: {t['elapsed']:.1f} 秒, 数据一致性 {consistency}")
        
        # 测试 2：数据一致性
        self.log("\n【测试 2：数据一致性】")
        consistency_test = next((r for r in self.results if r.get("test") == "data_consistency"), None)
        if consistency_test:
            self.log(f"  {'✅' if consistency_test['consistent'] else '❌'} 两次运行结果一致性")
            self.log(f"  {'✅' if consistency_test['cache_clean'] else '⚠️ '} 临时文件清理")
        
        # 测试 3：执行层拥堵
        self.log("\n【测试 3：执行层拥堵】")
        congestion_test = next((r for r in self.results if r.get("test") == "execution_layer_congestion"), None)
        if congestion_test:
            self.log(f"  通过信号数量: {congestion_test['approved_count']}")
            if congestion_test['approved_count'] > 0:
                self.log(f"  串行执行时间: {congestion_test['serial_time']} 秒")
                self.log(f"  并行执行时间: {congestion_test['parallel_time']:.1f} 秒")
                self.log(f"  {'⚠️ ' if congestion_test['congestion_risk'] else '✅'} 拥堵风险")
        
        # 保存报告
        report_file = self.base_dir / "comprehensive_test_report.json"
        with open(report_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "results": self.results
            }, f, indent=2)
        
        self.log(f"\n✅ 测试报告已保存到: {report_file}")
    
    def run(self):
        """运行所有测试"""
        self.log("🚀 开始综合压力测试")
        
        # 测试 1：负载压力
        self.test_1_load_balancer_stress()
        
        # 测试 2：数据一致性
        self.test_2_data_consistency()
        
        # 测试 3：执行层拥堵
        self.test_3_execution_layer_congestion()
        
        # 生成报告
        self.generate_report()

def main():
    test = ComprehensiveTest()
    test.run()

if __name__ == "__main__":
    main()
