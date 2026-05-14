"""
Capital Adapter - 资金分配器
职责：根据市场状态和策略配置，动态分配资金
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync
from _paths import get_base_dir

class CapitalAdapter:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Capital Adapter] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"capital_adapter_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_market_regime(self):
        """加载市场状态"""
        regime_file = self.data_dir / "market_regime.json"
        
        if not regime_file.exists():
            self.log("⚠️  无市场状态数据")
            return {}
        
        try:
            with open(regime_file, 'r') as f:
                regime = json.load(f)
            
            self.log(f"📊 市场状态: {regime.get('regime')}")
            return regime
        
        except Exception as e:
            self.log(f"❌ 加载市场状态失败: {e}")
            return {}
    
    def load_strategy_config(self):
        """加载策略配置"""
        config_file = self.data_dir / "strategy_config.json"
        
        if not config_file.exists():
            self.log("⚠️  无策略配置")
            return {}
        
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            self.log(f"📊 加载策略配置成功")
            return config
        
        except Exception as e:
            self.log(f"❌ 加载策略配置失败: {e}")
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
            
            self.log(f"📊 当前持仓: {len(positions)} 个")
            return positions
        
        except Exception as e:
            self.log(f"❌ 加载持仓失败: {e}")
            return []
    
    def calculate_capital_allocation(self, regime, config, positions):
        """计算资金分配"""
        self.log("计算资金分配...")
        
        # 提取关键配置
        position_sizing = config.get('position_sizing', {
            'high_confidence': 200,
            'medium_confidence': 150,
            'low_confidence': 100
        })
        
        regime_name = regime.get('regime', 'unknown')
        position_multiplier = regime.get('strategy_adjustment', {}).get('position_size_multiplier', 1.0)
        
        # 计算持仓总价值
        positions_value = sum(p.get('current_value', 0) for p in positions)
        available_cash = 10000 - positions_value
        
        prompt = f"""你是资金分配专家。根据市场状态计算最优资金分配。

## 输入数据
- 市场状态: {regime_name}
- 仓位倍数: {position_multiplier}
- 持仓数量: {len(positions)}
- 持仓总值: ${positions_value:,.2f}
- 可用现金: ${available_cash:,.2f}
- 基准仓位: 高置信度${position_sizing['high_confidence']}, 中置信度${position_sizing['medium_confidence']}, 低置信度${position_sizing['low_confidence']}

## 任务
根据市场状态调整仓位大小，输出 JSON 格式：
{{
  "max_single_position": 单笔最大金额,
  "position_sizing": {{
    "high_confidence": 高置信度金额,
    "medium_confidence": 中置信度金额,
    "low_confidence": 低置信度金额
  }},
  "max_total_exposure": 最大总敞口,
  "reserve_cash": 预留现金,
  "reason": "调整原因"
}}
"""
        
        try:
            response = call_llm_sync("capital_adapter", prompt, timeout=100)

            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                allocation = json.loads(json_match.group())
                return allocation

        except Exception as e:
            self.log(f"⚠️  LLM 计算失败({e})，使用规则兜底")

        return self._rule_based_allocation(regime, position_sizing, positions_value, available_cash)

    def _rule_based_allocation(self, regime, base_sizing, positions_value, available_cash):
        """规则兜底：LLM 超时/失败时按 regime 输出合法 capital 配置"""
        regime_name = str(regime.get('regime', 'unknown')).lower()
        multiplier = regime.get('strategy_adjustment', {}).get('position_size_multiplier', 1.0)
        try:
            multiplier = float(multiplier)
        except (TypeError, ValueError):
            multiplier = 1.0

        # 按 regime 确定缩放系数
        if regime_name in ('bull', 'risk_on'):
            scale, label = min(multiplier, 1.5), 'bull/risk_on'
        elif regime_name in ('bear', 'risk_off'):
            scale, label = max(multiplier, 0.7), 'bear/risk_off'
        elif regime_name in ('chaos', 'high_vol'):
            scale, label = 0.5, 'chaos/high_vol'
        else:  # neutral / range / unknown
            scale, label = 1.0, 'neutral/range'

        high   = round(base_sizing.get('high_confidence',   200) * scale)
        medium = round(base_sizing.get('medium_confidence', 150) * scale)
        low    = round(base_sizing.get('low_confidence',    100) * scale)

        allocation = {
            "max_single_position": high,
            "position_sizing": {
                "high_confidence":   high,
                "medium_confidence": medium,
                "low_confidence":    low,
            },
            "max_total_exposure": round(min(available_cash * 0.5, 5000 * scale)),
            "reserve_cash":       round(max(available_cash * 0.5, 1000)),
            "reason": f"[规则兜底] regime={label} scale={scale:.1f}，LLM 不可用",
        }
        self.log(f"⚠️  规则兜底触发: regime={label} scale={scale:.1f} "
                 f"high={high} medium={medium} low={low}")
        return allocation
    
    def save_capital_allocation(self, allocation):
        """保存资金分配方案"""
        if not allocation:
            self.log("⚠️  无分配方案可保存")
            return
        
        allocation_file = self.data_dir / "capital_allocation.json"
        
        allocation["timestamp"] = datetime.now().isoformat()
        
        with open(allocation_file, 'w') as f:
            json.dump(allocation, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 资金分配方案已保存到 {allocation_file}")
        
        # 输出关键信息
        max_single = allocation.get('max_single_position', 0)
        max_exposure = allocation.get('max_total_exposure', 0)
        
        # 确保是数字类型
        if isinstance(max_single, str):
            max_single = float(max_single.replace(',', '').replace('$', ''))
        if isinstance(max_exposure, str):
            max_exposure = float(max_exposure.replace(',', '').replace('$', ''))
        
        self.log(f"📊 单笔最大: ${max_single:,.2f}")
        self.log(f"📊 仓位配置: {allocation.get('position_sizing', {})}")
        self.log(f"📊 最大敞口: ${max_exposure:,.2f}")
    
    def run(self):
        """执行资金分配"""
        self.log("开始资金分配...")
        
        # 加载市场状态
        regime = self.load_market_regime()
        
        # 加载策略配置
        config = self.load_strategy_config()
        
        # 加载持仓
        positions = self.load_positions()
        
        # 计算资金分配
        allocation = self.calculate_capital_allocation(regime, config, positions)
        
        # 保存分配方案
        self.save_capital_allocation(allocation)
        
        self.log("✅ 资金分配完成")

def main():
    adapter = CapitalAdapter()
    adapter.run()

if __name__ == "__main__":
    main()
