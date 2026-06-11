"""
Agent E - BTC 短期套利监控
职责：监控 BTC 价格预测市场与实时价格的滞后套利机会
"""

import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync, LLMModelError
from _paths import get_base_dir
from utils.market_data import get_okx_btc_context, get_polymarket_markets
from utils.signals import ensure_signal_timestamps

class AgentE:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._model_errors = []

    def _record_model_error(self, market_slug: str, error: LLMModelError):
        entry = {
            "agent": "agent_e",
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
        status_file = self.data_dir / "agent_e_run_status.json"
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
        log_msg = f"[{timestamp}] [Agent E] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_e_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_market_data(self):
        """加载市场数据"""
        data_file = self.data_dir / "latest_data.json"
        
        if not data_file.exists():
            self.log("⚠️  无市场数据文件")
            return []
        
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            markets = get_polymarket_markets(data)
            
            # 筛选 BTC 相关市场
            btc_markets = [
                m for m in markets
                if "btc" in m.get("question", "").lower() or 
                   "bitcoin" in m.get("question", "").lower()
            ]
            
            self.log(f"📊 发现 {len(btc_markets)} 个 BTC 相关市场")
            return btc_markets
        
        except Exception as e:
            self.log(f"❌ 加载市场数据失败: {e}")
            return []
    
    def get_btc_price(self):
        """获取实时 BTC 价格"""
        try:
            # 从 latest_data.json 读取 OKX 数据
            data_file = self.data_dir / "latest_data.json"
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            btc_price, _ = get_okx_btc_context(data)
            if btc_price:
                self.log(f"💰 BTC 实时价格: ${btc_price:,.2f}")
                return float(btc_price)
            
            self.log("⚠️  无 BTC 价格数据")
            return None
        
        except Exception as e:
            self.log(f"❌ 获取 BTC 价格失败: {e}")
            return None
    
    def analyze_btc_markets(self, markets, btc_price):
        """分析 BTC 市场套利机会"""
        if not markets or not btc_price:
            self.log("ℹ️  无足够数据")
            return []
        
        self.log(f"分析 {len(markets)} 个 BTC 市场...")
        
        signals = []
        
        for market in markets:
            prompt = f"""你是 BTC 价格预测市场套利专家。分析以下市场：

市场：{market.get('question', '')}
YES 价格：${market.get('yes_price', 0):.4f}
NO 价格：${market.get('no_price', 0):.4f}
交易量：${market.get('volume', 0):,.0f}

当前 BTC 实时价格：${btc_price:,.2f}

## 分析任务
1. 市场隐含的 BTC 价格预期是多少？
2. 与实时价格 ${btc_price:,.2f} 相比，是否存在明显偏差？
3. 这个偏差是否可以套利？
4. 建议的交易方向和金额？

请以 JSON 格式输出：
{{
  "has_opportunity": true/false,
  "direction": "buy_yes" 或 "buy_no",
  "amount": 金额,
  "confidence": 0-100,
  "reason": "原因"
}}
"""
            
            try:
                response = call_llm_sync("agent_e", prompt, timeout=30)
                
                # 解析 JSON
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    
                    if analysis.get("has_opportunity") and analysis.get("confidence", 0) >= 60:
                        signals.append({
                            "market": market.get("slug", ""),
                            "direction": analysis.get("direction"),
                            "amount": analysis.get("amount", 100),
                            "confidence": analysis.get("confidence"),
                            "reason": analysis.get("reason"),
                            "btc_price": btc_price,
                            "source": "agent_e",
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        self.log(f"✅ 发现套利: {market.get('slug', '')[:50]}... (置信度 {analysis.get('confidence')})")
            
            except LLMModelError as e:
                self._record_model_error(market.get("slug", ""), e)
                continue
            except Exception as e:
                wrapped = LLMModelError(str(e), error_type="model_error", agent_id="agent_e")
                self._record_model_error(market.get("slug", ""), wrapped)
                continue
        
        return signals
    
    def run(self):
        """执行 BTC 套利扫描"""
        self.log("开始 BTC 套利扫描...")
        
        # 加载 BTC 市场
        markets = self.load_market_data()
        
        if not markets:
            self.log("ℹ️  无 BTC 市场")
            return
        
        # 获取 BTC 价格
        btc_price = self.get_btc_price()
        
        # 分析市场
        signals = self.analyze_btc_markets(markets, btc_price)
        
        # 保存信号
        if signals:
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
            
            existing_signals.extend(ensure_signal_timestamps(signals))
            
            with open(output_file, 'w') as f:
                json.dump(existing_signals, f, indent=2, ensure_ascii=False)
            
            self.log(f"✅ 已保存 {len(signals)} 个 BTC 套利信号到 {output_file}")
        else:
            if self._model_errors:
                self.log(f"ℹ️  无 BTC 套利信号（{len(self._model_errors)} 次 model_error）")
            else:
                self.log("ℹ️  无 BTC 套利信号")
        self._write_run_status()

def main():
    agent = AgentE()
    agent.run()

if __name__ == "__main__":
    main()
