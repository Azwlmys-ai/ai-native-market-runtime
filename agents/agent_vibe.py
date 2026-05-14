#!/usr/bin/env python3
"""
Agent Vibe - 集成 Vibe-Trading 的策略生成
职责：调用 Vibe-Trading API 生成策略，并转换为 Polymarket 信号
"""

import json
import requests
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir

class AgentVibe:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Vibe-Trading API 配置
        self.vibe_url = "http://127.0.0.1:8899"
        self.api_key = "test-key"  # 本地开发用

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent Vibe] {message}"
        print(log_msg, flush=True)

        log_file = self.logs_dir / f"agent_vibe_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")

    def call_vibe_api(self, prompt):
        """调用 Vibe-Trading API 生成策略"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            # 使用 swarm/runs 接口
            payload = {
                "preset_name": "crypto_trading_desk",
                "user_vars": {
                    "target": "ETH",  # 目标资产
                    "timeframe": "1w"  # 时间框架
                }
            }

            response = requests.post(
                f"{self.vibe_url}/swarm/runs",
                headers=headers,
                json=payload,
                timeout=300  # 5分钟超时
            )

            if response.status_code in [200, 201]:
                run_data = response.json()
                run_id = run_data.get("id") or run_data.get("run_id")
                if not run_id:
                    self.log(f"Vibe-Trading run response missing id: {run_data}")
                    return None
                self.log(f"启动 Vibe-Trading run: {run_id}")

                # 等待完成（简化版，实际应异步）
                import time
                polling_minutes = 30
                polling_interval = 10
                max_checks = int(polling_minutes * 60 / polling_interval)
                for i in range(max_checks):
                    status_resp = requests.get(
                        f"{self.vibe_url}/swarm/runs/{run_id}",
                        headers=headers,
                        timeout=30,
                    )
                    if status_resp.status_code == 200:
                        status_data = status_resp.json()
                        status = status_data.get("status")
                        self.log(f"Vibe-Trading run status={status} (poll {i + 1}/{max_checks})")
                        if status == "completed":
                            return status_data
                        elif status in ("failed", "timeout", "cancelled"):
                            self.log(f"Vibe-Trading run 失败: {status_data}")
                            return None
                    else:
                        self.log(f"查询 run 状态失败: {status_resp.status_code} {status_resp.text}")
                    time.sleep(polling_interval)

                self.log(f"Vibe-Trading run 超时 after {polling_minutes} minutes")
                return None
            else:
                self.log(f"Vibe-Trading API 错误: {response.status_code} {response.text}")
                return None

        except Exception as e:
            self.log(f"Vibe-Trading 调用失败: {e}")
            return None

    def generate_signals(self, prompt):
        """生成 Polymarket 信号"""
        self.log(f"生成策略: {prompt}")

        vibe_result = self.call_vibe_api(prompt)
        if not vibe_result:
            return []

        # 解析 Vibe-Trading 结果，转换为 Polymarket 信号格式
        signals = []

        # 从 final_report 提取信号
        if "final_report" in vibe_result and vibe_result["final_report"]:
            report = vibe_result["final_report"]
            self.log(f"收到 Vibe-Trading 报告: {len(report)} 字符")

            # 解析交易建议
            if "LONG" in report.upper() and "SHORT" not in report.upper().split("LONG")[0][-100:]:
                direction = "YES"  # 做多对应YES
                confidence = 0.6
            elif "SHORT" in report.upper():
                direction = "NO"   # 做空对应NO
                confidence = 0.6
            else:
                direction = "YES"  # 默认
                confidence = 0.5

            # 提取关键信息
            signal = {
                "market_id": f"ETH-{datetime.now().strftime('%Y%m%d')}",
                "question": prompt,
                "direction": direction,
                "position_size": 0.1,
                "confidence": confidence,
                "reason": f"Vibe-Trading分析: {report[:500]}...",  # 截取前500字符
                "generated_at": datetime.now().isoformat(),
                "source": "vibe-trading",
                "full_report": report
            }
            signals.append(signal)
        else:
            self.log("Vibe-Trading 未返回 final_report")

        return signals

    def run(self):
        """执行 Agent Vibe"""
        self.log("开始 Agent Vibe 执行")

        # 示例 prompt
        prompt = "ETH 这周有啥机会？考虑技术面和资金费率"

        signals = self.generate_signals(prompt)

        if signals:
            # 保存到 signals.json
            signals_file = self.data_dir / "signals.json"
            existing_signals = []
            if signals_file.exists():
                try:
                    with open(signals_file, 'r') as f:
                        existing_signals = json.load(f)
                except:
                    pass

            existing_signals.extend(signals)

            with open(signals_file, 'w') as f:
                json.dump(existing_signals, f, indent=2, ensure_ascii=False)

            self.log(f"生成 {len(signals)} 个信号")
        else:
            self.log("未生成信号")

        self.log("Agent Vibe 执行完成")

def main():
    agent = AgentVibe()
    agent.run()

if __name__ == "__main__":
    main()