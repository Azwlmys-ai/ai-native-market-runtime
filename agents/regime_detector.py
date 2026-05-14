"""
Regime Detector - 市场状态识别
职责：识别当前市场状态（牛市/熊市/震荡），调整策略
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync
from _paths import get_base_dir

class RegimeDetector:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Regime Detector] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"regime_detector_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_market_data(self):
        """加载市场数据"""
        data_file = self.data_dir / "latest_data.json"
        
        if not data_file.exists():
            self.log("⚠️  无市场数据文件")
            return {}
        
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            self.log(f"📊 加载市场数据成功")
            return data
        
        except Exception as e:
            self.log(f"❌ 加载市场数据失败: {e}")
            return {}
    
    def load_trade_history(self):
        """加载交易历史"""
        trade_file = self.data_dir / "trade_log.json"
        
        if not trade_file.exists():
            self.log("⚠️  无交易历史")
            return []
        
        try:
            with open(trade_file, 'r') as f:
                trades = json.load(f)
            
            self.log(f"📊 加载 {len(trades)} 笔交易历史")
            return trades
        
        except Exception as e:
            self.log(f"❌ 加载交易历史失败: {e}")
            return []
    
    def detect_market_regime(self, data, trade_history):
        """识别市场状态"""
        # 检查缓存
        cache_file = self.data_dir / "market_regime_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cache = json.load(f)
                cache_time = datetime.fromisoformat(cache.get("timestamp", ""))
                if (datetime.now() - cache_time).total_seconds() < 900:  # 15 分钟缓存
                    self.log("使用缓存的市场状态")
                    return cache
            except Exception:
                pass
        
        self.log("识别市场状态...")
        
        prompt = f"""你是市场状态识别专家。分析当前市场环境：

## 市场数据
- 市场数量：{len(data.get('markets', []))}
- BTC 价格：${data.get('btc_price', 0):,.2f}
- OKX 资金费率：{data.get('okx_funding_rate', 0):.4%}
- 新闻数量：{len(data.get('news', []))}

## 交易历史
- 总交易数：{len(trade_history)}
- 最近 10 笔交易：{json.dumps(trade_history[-10:], indent=2, ensure_ascii=False) if trade_history else '无'}

## 识别任务
1. 当前市场处于什么状态？
   - 牛市（Bull）：价格上涨，资金费率高，交易活跃
   - 熊市（Bear）：价格下跌，资金费率低，交易冷清
   - 震荡（Range）：价格横盘，方向不明

2. 这个状态对 Polymarket 套利有什么影响？

3. 应该采取什么策略？
   - 牛市：激进策略，增加仓位
   - 熊市：保守策略，减少仓位
   - 震荡：中性策略，正常仓位

请以 JSON 格式输出：
{{
  "regime": "bull" 或 "bear" 或 "range",
  "confidence": 0-100,
  "indicators": {{
    "btc_trend": "上涨/下跌/横盘",
    "funding_rate_signal": "看多/看空/中性",
    "market_activity": "活跃/冷清/正常"
  }},
  "strategy_adjustment": {{
    "position_size_multiplier": 0.5-1.5,
    "risk_tolerance": "aggressive" 或 "conservative" 或 "neutral"
  }},
  "reason": "原因"
}}
"""
        
        try:
            response = call_llm_sync("regime_detector", prompt, timeout=100)

            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                regime = json.loads(json_match.group())
                regime["timestamp"] = datetime.now().isoformat()
                with open(cache_file, 'w') as f:
                    json.dump(regime, f, indent=2, ensure_ascii=False)
                return regime

        except Exception as e:
            self.log(f"⚠️  LLM 识别失败({e})，使用规则兜底")

        # 规则兜底：LLM 超时/失败时用简单指标判断
        return self._rule_based_regime(data)

    def _rule_based_regime(self, data):
        """规则兜底：BTC 价格 + 资金费率简单判断"""
        funding_rate = data.get('okx_funding_rate') or data.get('btc_funding_rate') or 0
        try:
            funding_rate = float(funding_rate)
        except (TypeError, ValueError):
            funding_rate = 0

        if funding_rate > 0.001:
            regime, reason = "bull", f"资金费率 {funding_rate:.4%} 偏高，市场偏多"
        elif funding_rate < -0.001:
            regime, reason = "bear", f"资金费率 {funding_rate:.4%} 偏低，市场偏空"
        else:
            regime, reason = "range", f"资金费率 {funding_rate:.4%} 接近中性，市场震荡"

        result = {
            "regime": regime,
            "confidence": 60,
            "indicators": {
                "btc_trend": "横盘",
                "funding_rate_signal": "看多" if funding_rate > 0 else ("看空" if funding_rate < 0 else "中性"),
                "market_activity": "正常",
            },
            "strategy_adjustment": {
                "position_size_multiplier": 1.2 if regime == "bull" else (0.8 if regime == "bear" else 1.0),
                "risk_tolerance": "aggressive" if regime == "bull" else ("conservative" if regime == "bear" else "neutral"),
            },
            "reason": f"[规则兜底] {reason}",
            "timestamp": datetime.now().isoformat(),
        }
        cache_file = self.data_dir / "market_regime_cache.json"
        with open(cache_file, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        return result
    
    def save_regime_report(self, regime):
        """保存市场状态报告"""
        if not regime:
            self.log("⚠️  无状态可保存")
            return
        
        report_file = self.data_dir / "market_regime.json"
        
        regime["timestamp"] = datetime.now().isoformat()
        
        with open(report_file, 'w') as f:
            json.dump(regime, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 市场状态已保存到 {report_file}")
        
        # 输出关键信息
        self.log(f"📊 市场状态: {regime.get('regime')} (置信度 {regime.get('confidence')})")
        self.log(f"📊 策略调整: {regime.get('strategy_adjustment', {})}")
    
    def run(self):
        """执行市场状态识别"""
        self.log("开始市场状态识别...")
        
        # 加载市场数据
        data = self.load_market_data()
        
        # 加载交易历史
        trade_history = self.load_trade_history()
        
        # 识别市场状态
        regime = self.detect_market_regime(data, trade_history)
        
        # 保存报告
        self.save_regime_report(regime)
        
        self.log("✅ 市场状态识别完成")

def main():
    detector = RegimeDetector()
    detector.run()

if __name__ == "__main__":
    main()
