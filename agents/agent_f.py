"""
Agent F - OKX 跨平台套利监控
职责：监控 Polymarket 与 OKX 之间的跨平台套利机会
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync, LLMModelError
from _paths import get_base_dir
from utils.market_data import get_okx_btc_context, get_polymarket_markets
from utils.signals import ensure_signal_timestamps

class AgentF:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._model_errors = []

    def _record_model_error(self, market_slug: str, error: LLMModelError):
        entry = {
            "agent": "agent_f",
            "market": market_slug,
            "error_type": error.error_type,
            "fallback_used": error.fallback_used,
            "models_tried": error.models_tried,
            "message": str(error),
            "timestamp": datetime.now().isoformat(),
        }
        self._model_errors.append(entry)
        fb = " fallback_used" if error.fallback_used else ""
        self.log(f"⚠️ model_error ({error.error_type}{fb}): {market_slug[:50]} - {error}")

    def _write_run_status(self):
        if not self._model_errors:
            return
        status_file = self.data_dir / "agent_f_run_status.json"
        with open(status_file, "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "signals_produced": 0,
                    "model_errors": self._model_errors,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        self.log(f"ℹ️  model_error 元数据已写入 {status_file}（未写入 signals.json）")
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent F] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_f_{datetime.now().strftime('%Y%m%d')}.log"
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
    
    def find_cross_platform_opportunities(self, data):
        """发现跨平台套利机会"""
        self.log("扫描跨平台套利机会...")
        
        # 获取 OKX 数据
        btc_price, okx_funding_rate = get_okx_btc_context(data)
        
        if not okx_funding_rate or not btc_price:
            self.log("⚠️  无 OKX 数据")
            return []
        
        # 获取 Polymarket 加密货币相关市场
        markets = get_polymarket_markets(data)
        crypto_markets = [
            m for m in markets
            if any(keyword in m.get("question", "").lower() 
                   for keyword in ["btc", "bitcoin", "eth", "ethereum", "crypto"])
        ]
        
        self.log(f"📊 发现 {len(crypto_markets)} 个加密货币市场")
        
        opportunities = []
        
        for market in crypto_markets:
            prompt = f"""你是跨平台套利专家。分析 Polymarket 与 OKX 之间的套利机会：

## Polymarket 市场
市场：{market.get('question', '')}
YES 价格：${market.get('yes_price', 0):.4f}
NO 价格：${market.get('no_price', 0):.4f}
交易量：${market.get('volume', 0):,.0f}

## OKX 数据
BTC 价格：${btc_price:,.2f}
资金费率：{okx_funding_rate:.4%}

## 分析任务
1. Polymarket 市场隐含的价格预期与 OKX 实时数据是否存在偏差？
2. 资金费率是否暗示市场情绪（正费率=看多，负费率=看空）？
3. 是否存在跨平台套利机会？
4. 建议的交易策略？

请以 JSON 格式输出：
{{
  "has_opportunity": true/false,
  "strategy": "描述",
  "polymarket_action": "buy_yes" 或 "buy_no",
  "amount": 金额,
  "confidence": 0-100,
  "reason": "原因"
}}
"""
            
            try:
                response = call_llm_sync("agent_f", prompt, timeout=30)
                
                # 解析 JSON
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    
                    if analysis.get("has_opportunity") and analysis.get("confidence", 0) >= 65:
                        opportunities.append({
                            "market": market.get("slug", ""),
                            "strategy": analysis.get("strategy"),
                            "direction": analysis.get("polymarket_action"),
                            "amount": analysis.get("amount", 100),
                            "confidence": analysis.get("confidence"),
                            "reason": analysis.get("reason"),
                            "okx_funding_rate": okx_funding_rate,
                            "btc_price": btc_price,
                            "source": "agent_f",
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        self.log(f"✅ 发现机会: {market.get('slug', '')[:50]}... (置信度 {analysis.get('confidence')})")
            
            except LLMModelError as e:
                self._record_model_error(market.get("slug", ""), e)
                continue
            except Exception as e:
                wrapped = LLMModelError(str(e), error_type="model_error", agent_id="agent_f")
                self._record_model_error(market.get("slug", ""), wrapped)
                continue
        
        return opportunities
    
    def run(self):
        """执行跨平台套利扫描"""
        self.log("开始跨平台套利扫描...")
        
        # 加载市场数据
        data = self.load_market_data()
        
        if not data:
            self.log("ℹ️  无市场数据")
            return
        
        # 发现套利机会
        opportunities = self.find_cross_platform_opportunities(data)
        
        # 保存信号
        if opportunities:
            output_file = self.data_dir / "signals.json"
            
            # 追加到现有信号
            existing_signals = []
            if output_file.exists():
                try:
                    with open(output_file, 'r') as f:
                        existing_signals = json.load(f)
                    if not isinstance(existing_signals, list):
                        existing_signals = []
                except:
                    existing_signals = []
            
            existing_signals.extend(ensure_signal_timestamps(opportunities))
            
            with open(output_file, 'w') as f:
                json.dump(existing_signals, f, indent=2, ensure_ascii=False)
            
            self.log(f"✅ 已保存 {len(opportunities)} 个跨平台套利信号到 {output_file}")
        else:
            if self._model_errors:
                self.log(f"ℹ️  无跨平台套利信号（{len(self._model_errors)} 次 model_error）")
            else:
                self.log("ℹ️  无跨平台套利信号")
        self._write_run_status()

def main():
    agent = AgentF()
    agent.run()

if __name__ == "__main__":
    main()
