"""
Strategy Manager - 策略管理器
职责：动态调整止盈止损参数，生成策略配置
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync
from _paths import get_base_dir

class StrategyManager:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Strategy Manager] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"strategy_manager_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_learning_report(self):
        """加载学习报告"""
        report_file = self.data_dir / "learning_report.json"
        
        if not report_file.exists():
            self.log("⚠️  无学习报告")
            return {}
        
        try:
            with open(report_file, 'r') as f:
                report = json.load(f)
            
            self.log(f"📊 加载学习报告成功")
            return report
        
        except Exception as e:
            self.log(f"❌ 加载学习报告失败: {e}")
            return {}
    
    def load_positions(self):
        """加载当前持仓"""
        positions_file = self.data_dir / "positions.json"
        
        if not positions_file.exists():
            self.log("⚠️  无持仓数据")
            return []
        
        try:
            with open(positions_file, 'r') as f:
                positions = json.load(f)
            
            self.log(f"📊 加载 {len(positions)} 个持仓")
            return positions
        
        except Exception as e:
            self.log(f"❌ 加载持仓失败: {e}")
            return []
    
    def generate_strategy_config(self, learning_report, positions):
        """生成策略配置"""
        # 15 分钟缓存：策略参数不需要每个周期都重新生成
        cache_file = self.data_dir / "strategy_config_cache.json"
        if cache_file.exists():
            try:
                cache = json.loads(cache_file.read_text())
                cache_time = datetime.fromisoformat(cache.get("timestamp", ""))
                if (datetime.now() - cache_time).total_seconds() < 900:
                    self.log("使用缓存的策略配置")
                    return cache
            except Exception:
                pass

        self.log("生成策略配置...")
        
        prompt = f"""你是交易策略管理专家。根据历史学习和当前持仓，生成动态策略配置。

## 学习报告摘要
{json.dumps(learning_report.get('summary', {}), indent=2, ensure_ascii=False)}

## 当前持仓
持仓数量：{len(positions)}

## 配置任务
根据历史表现，为不同类型的市场设置动态参数：

1. **止盈参数**
   - 体育市场（NHL/NBA 等）：历史表现好，可以设置较高止盈（+15% ~ +25%）
   - 娱乐/政治市场：历史表现差，设置较低止盈（+8% ~ +12%）
   - 加密市场：波动大，设置中等止盈（+10% ~ +18%）

2. **止损参数**
   - 高置信度信号（>80）：可以容忍较大回撤（-12% ~ -15%）
   - 中等置信度（60-80）：设置中等止损（-8% ~ -12%）
   - 低置信度（<60）：设置严格止损（-5% ~ -8%）

3. **获利回撤**
   - 当浮盈达到 +20% 后，设置回撤止盈（从最高点回撤 -5% 就卖出）

4. **相关性控制**
   - 单一锚点事件（如 GTA VI）最多持仓 3 个市场
   - 单一类别（如 NHL）最多持仓 5 个市场

请以 JSON 格式输出完整配置：
{{
  "take_profit": {{
    "sports": {{"min": 0.15, "max": 0.25}},
    "entertainment": {{"min": 0.08, "max": 0.12}},
    "politics": {{"min": 0.08, "max": 0.12}},
    "crypto": {{"min": 0.10, "max": 0.18}},
    "default": {{"min": 0.10, "max": 0.15}}
  }},
  "stop_loss": {{
    "high_confidence": -0.15,
    "medium_confidence": -0.12,
    "low_confidence": -0.08
  }},
  "trailing_stop": {{
    "trigger_profit": 0.20,
    "trailing_percent": 0.05
  }},
  "correlation_limits": {{
    "single_anchor": 3,
    "single_category": 5
  }},
  "position_sizing": {{
    "high_confidence": 200,
    "medium_confidence": 150,
    "low_confidence": 100
  }}
}}
"""
        
        try:
            response = call_llm_sync("strategy_manager", prompt, timeout=60, max_retries=1)

            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                config = json.loads(json_match.group())
                config["timestamp"] = datetime.now().isoformat()
                with open(cache_file, 'w') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                return config

        except Exception as e:
            self.log(f"⚠️  LLM 生成配置失败({e})，使用默认配置")

        # 规则兜底：返回稳健默认策略配置
        return self._default_strategy_config()

    def _default_strategy_config(self):
        """默认策略配置：LLM 失败时使用"""
        config = {
            "take_profit": {"sports": [0.15, 0.25], "entertainment_politics": [0.08, 0.12], "crypto": [0.10, 0.18], "default": [0.10, 0.15]},
            "stop_loss": {"high_confidence": -0.15, "medium_confidence": -0.12, "low_confidence": -0.08},
            "trailing_stop": {"trigger_profit": 0.20, "trail_pct": 0.05},
            "correlation_limits": {"single_anchor_event": 3, "single_category": 5},
            "position_sizing": {"high_confidence": 200, "medium_confidence": 150, "low_confidence": 100},
            "reason": "[默认兜底] LLM 调用失败，使用保守默认参数",
            "timestamp": datetime.now().isoformat(),
        }
        cache_file = self.data_dir / "strategy_config_cache.json"
        with open(cache_file, 'w') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return config
    
    def save_strategy_config(self, config):
        """保存策略配置"""
        if not config:
            self.log("⚠️  无配置可保存")
            return
        
        config_file = self.data_dir / "strategy_config.json"
        
        config["timestamp"] = datetime.now().isoformat()
        config["version"] = "v1.0"
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 策略配置已保存到 {config_file}")
        
        # 输出关键参数
        self.log(f"📊 止盈范围: {config.get('take_profit', {})}")
        self.log(f"📊 止损参数: {config.get('stop_loss', {})}")
        self.log(f"📊 相关性限制: {config.get('correlation_limits', {})}")
    
    def run(self):
        """执行策略管理"""
        self.log("开始策略管理...")
        
        # 加载学习报告
        learning_report = self.load_learning_report()
        
        # 加载持仓
        positions = self.load_positions()
        
        # 生成策略配置
        config = self.generate_strategy_config(learning_report, positions)
        
        # 保存配置
        self.save_strategy_config(config)
        
        self.log("✅ 策略管理完成")

def main():
    manager = StrategyManager()
    manager.run()

if __name__ == "__main__":
    main()
