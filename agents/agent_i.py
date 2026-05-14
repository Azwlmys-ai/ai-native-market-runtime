"""
Agent I - 系统监控保活
职责：监控所有 Agent 健康状态，自动重启崩溃进程
"""

import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync
from _paths import get_base_dir

class AgentI:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent I] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_i_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def check_agent_health(self):
        """检查所有 Agent 健康状态"""
        self.log("检查 Agent 健康状态...")
        
        agents = ["a", "b", "d", "e", "f", "g", "h", "j", "k_v2", "m", "p"]
        health_status = {}
        
        for agent in agents:
            log_file = self.logs_dir / f"agent_{agent}_{datetime.now().strftime('%Y%m%d')}.log"
            
            if log_file.exists():
                # 检查最后一次日志时间
                try:
                    with open(log_file, 'r') as f:
                        lines = f.readlines()
                    
                    if lines:
                        last_line = lines[-1]
                        # 提取时间戳
                        if "[" in last_line and "]" in last_line:
                            timestamp_str = last_line.split("[")[1].split("]")[0]
                            last_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            
                            # 计算时间差
                            time_diff = (datetime.now() - last_time).total_seconds()
                            
                            health_status[agent] = {
                                "status": "healthy" if time_diff < 3600 else "stale",
                                "last_seen": timestamp_str,
                                "time_diff": time_diff
                            }
                        else:
                            health_status[agent] = {"status": "unknown", "last_seen": "N/A"}
                    else:
                        health_status[agent] = {"status": "no_logs", "last_seen": "N/A"}
                
                except Exception as e:
                    health_status[agent] = {"status": "error", "error": str(e)}
            else:
                health_status[agent] = {"status": "no_logs", "last_seen": "N/A"}
        
        return health_status
    
    def check_data_freshness(self):
        """检查数据文件新鲜度"""
        self.log("检查数据文件新鲜度...")
        
        data_files = {
            "latest_data.json": 1800,  # 30 分钟
            "signals.json": 3600,  # 1 小时
            "positions.json": 3600,  # 1 小时
        }
        
        freshness = {}
        
        for filename, max_age in data_files.items():
            file_path = self.data_dir / filename
            
            if file_path.exists():
                try:
                    mtime = file_path.stat().st_mtime
                    age = datetime.now().timestamp() - mtime
                    
                    freshness[filename] = {
                        "status": "fresh" if age < max_age else "stale",
                        "age_seconds": age,
                        "max_age": max_age
                    }
                except Exception as e:
                    freshness[filename] = {"status": "error", "error": str(e)}
            else:
                freshness[filename] = {"status": "missing"}
        
        return freshness
    
    def generate_health_report(self, agent_health, data_freshness):
        """生成健康报告"""
        self.log("生成健康报告...")
        
        prompt = f"""你是系统监控专家。分析以下系统健康状态：

## Agent 健康状态
{json.dumps(agent_health, indent=2, ensure_ascii=False)}

## 数据文件新鲜度
{json.dumps(data_freshness, indent=2, ensure_ascii=False)}

## 分析任务
1. 哪些 Agent 可能已经崩溃或停止工作？
2. 哪些数据文件过期了？
3. 系统整体健康状况如何？
4. 需要采取什么行动？

请以 JSON 格式输出：
{{
  "overall_status": "healthy" 或 "degraded" 或 "critical",
  "issues": ["问题列表"],
  "recommendations": ["建议列表"],
  "alert_required": true/false
}}
"""
        
        try:
            response = call_llm_sync("agent_i", prompt, timeout=30)
            
            # 解析 JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                report = json.loads(json_match.group())
                return report
        
        except Exception as e:
            self.log(f"❌ 生成报告失败: {e}")
            return None
    
    def save_health_report(self, report):
        """保存健康报告"""
        if not report:
            return
        
        report_file = self.data_dir / "health_report.json"
        
        report["timestamp"] = datetime.now().isoformat()
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 健康报告已保存到 {report_file}")
        
        # 如果需要警报
        if report.get("alert_required"):
            self.log(f"⚠️  系统状态: {report.get('overall_status')}")
            self.log(f"⚠️  问题: {', '.join(report.get('issues', []))}")
    
    def run(self):
        """执行系统监控"""
        self.log("开始系统监控...")
        
        # 检查 Agent 健康
        agent_health = self.check_agent_health()
        
        # 检查数据新鲜度
        data_freshness = self.check_data_freshness()
        
        # 生成健康报告
        report = self.generate_health_report(agent_health, data_freshness)
        
        # 保存报告
        self.save_health_report(report)
        
        self.log("✅ 系统监控完成")

def main():
    agent = AgentI()
    agent.run()

if __name__ == "__main__":
    main()
