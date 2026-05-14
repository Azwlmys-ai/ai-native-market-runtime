"""
Agent N - 负载均衡器（反对层协调员）
职责：动态分配信号给多个 Agent M 实例，实现弹性扩缩容
"""

import json
import math
import subprocess
import time
from pathlib import Path
from datetime import datetime

class AgentN:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.temp_dir = self.data_dir / "temp"
        
        # 创建临时目录
        self.temp_dir.mkdir(exist_ok=True)
        
        # 配置参数
        self.max_agents = 6  # 最多 6 个 Agent M（可处理 18 个信号）
        self.signals_per_agent = 3  # 每个 Agent 处理 3 个信号
        self.agent_timeout = 180  # 每个 Agent 超时时间（秒）
    
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent N] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_n_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_signals(self):
        """加载待审查的交易信号"""
        signals_file = self.data_dir / "signals.json"
        
        if not signals_file.exists():
            self.log("⚠️  无信号文件")
            return []
        
        try:
            with open(signals_file, 'r') as f:
                data = json.load(f)
            
            # 兼容多种格式
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                if "signals" in data:
                    return data["signals"]
                else:
                    return [data]
            else:
                return []
        
        except Exception as e:
            self.log(f"❌ 加载信号失败: {e}")
            return []
    
    def balance_load(self, signals):
        """负载均衡：计算所需 Agent 数量并分配信号"""
        signal_count = len(signals)
        
        if signal_count == 0:
            return []
        
        # 计算所需 Agent 数量
        agent_count = min(
            math.ceil(signal_count / self.signals_per_agent),
            self.max_agents
        )
        
        self.log(f"📊 信号数量: {signal_count}, 启动 Agent 数量: {agent_count}")
        
        # 分配信号到各个批次
        batches = []
        for i in range(agent_count):
            start = i * self.signals_per_agent
            end = min(start + self.signals_per_agent, signal_count)
            batch = signals[start:end]
            batches.append({
                "batch_id": i,
                "signals": batch,
                "count": len(batch)
            })
        
        return batches
    
    def run_agent_m_batch(self, batch_id, signals):
        """运行单个 Agent M 实例处理一批信号"""
        # 保存批次到临时文件
        batch_file = self.temp_dir / f"signals_batch_{batch_id}.json"
        result_file = self.temp_dir / f"review_batch_{batch_id}.json"
        
        try:
            # 写入批次信号
            with open(batch_file, 'w') as f:
                json.dump(signals, f, indent=2, ensure_ascii=False)
            
            self.log(f"🚀 启动 Agent M #{batch_id} (处理 {len(signals)} 个信号)")
            
            # 启动 Agent M 子进程
            start_time = time.time()
            result = subprocess.run(
                [
                    "python3",
                    str(self.base_dir / "agents" / "agent_m.py"),
                    "--batch-file", str(batch_file),
                    "--output-file", str(result_file)
                ],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=self.agent_timeout
            )
            
            elapsed = time.time() - start_time
            
            if result.returncode == 0:
                self.log(f"✅ Agent M #{batch_id} 完成 (耗时 {elapsed:.1f} 秒)")
                return {
                    "batch_id": batch_id,
                    "success": True,
                    "elapsed": elapsed,
                    "result_file": str(result_file)
                }
            else:
                self.log(f"❌ Agent M #{batch_id} 失败: {result.stderr[:200]}")
                return {
                    "batch_id": batch_id,
                    "success": False,
                    "error": result.stderr
                }
        
        except subprocess.TimeoutExpired:
            self.log(f"⏱️  Agent M #{batch_id} 超时")
            return {
                "batch_id": batch_id,
                "success": False,
                "error": "timeout"
            }
        
        except Exception as e:
            self.log(f"❌ Agent M #{batch_id} 异常: {e}")
            return {
                "batch_id": batch_id,
                "success": False,
                "error": str(e)
            }
    
    def merge_results(self, batch_results):
        """汇总所有批次的审查结果"""
        self.log("📦 汇总审查结果...")
        
        all_approved = []
        all_rejected = []
        
        for batch_result in batch_results:
            if not batch_result["success"]:
                continue
            
            result_file = Path(batch_result["result_file"])
            if not result_file.exists():
                continue
            
            try:
                with open(result_file, 'r') as f:
                    data = json.load(f)
                
                all_approved.extend(data.get("approved_signals", []))
                all_rejected.extend(data.get("rejected_signals", []))
            
            except Exception as e:
                self.log(f"⚠️  读取批次结果失败: {e}")
        
        # 保存汇总结果
        final_result = {
            "timestamp": datetime.now().isoformat(),
            "total": len(all_approved) + len(all_rejected),
            "approved": len(all_approved),
            "rejected": len(all_rejected),
            "approved_signals": all_approved,
            "rejected_signals": all_rejected
        }
        
        output_file = self.data_dir / "review_results.json"
        with open(output_file, 'w') as f:
            json.dump(final_result, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 汇总完成: {len(all_approved)} 通过, {len(all_rejected)} 拒绝")
        return final_result
    
    def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            for file in self.temp_dir.glob("*_batch_*.json"):
                file.unlink()
            self.log("🧹 临时文件已清理")
        except Exception as e:
            self.log(f"⚠️  清理临时文件失败: {e}")
    
    def run(self):
        """执行负载均衡审查"""
        self.log("=" * 60)
        self.log("开始负载均衡审查...")
        
        start_time = time.time()
        
        # 1. 加载信号
        signals = self.load_signals()
        
        if not signals:
            self.log("⚠️  无信号需要审查")
            # 创建空结果文件
            empty_result = {
                "timestamp": datetime.now().isoformat(),
                "total": 0,
                "approved": 0,
                "rejected": 0,
                "approved_signals": [],
                "rejected_signals": []
            }
            with open(self.data_dir / "review_results.json", 'w') as f:
                json.dump(empty_result, f, indent=2)
            return
        
        # 2. 负载均衡
        batches = self.balance_load(signals)
        
        # 3. 并行执行多个 Agent M
        import concurrent.futures
        
        batch_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_agents) as executor:
            futures = []
            for batch in batches:
                future = executor.submit(
                    self.run_agent_m_batch,
                    batch["batch_id"],
                    batch["signals"]
                )
                futures.append(future)
            
            # 等待所有任务完成
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                batch_results.append(result)
        
        # 4. 汇总结果
        final_result = self.merge_results(batch_results)
        
        # 5. 清理临时文件
        self.cleanup_temp_files()
        
        elapsed = time.time() - start_time
        self.log(f"✅ 负载均衡审查完成 (总耗时 {elapsed:.1f} 秒)")
        self.log("=" * 60)

def main():
    agent_n = AgentN()
    agent_n.run()

if __name__ == "__main__":
    main()
