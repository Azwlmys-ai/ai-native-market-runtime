"""
Agent OKX Funding - OKX 资金费率套利
职责：监控 OKX 资金费率，发现套利机会
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync
from _paths import get_base_dir
from utils.signals import ensure_signal_timestamps

class AgentOKXFunding:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent OKX Funding] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_okx_funding_{datetime.now().strftime('%Y%m%d')}.log"
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
    
    def analyze_funding_rate(self, data):
        """分析资金费率套利机会"""
        self.log("分析资金费率套利机会...")
        
        okx_funding_rate = data.get("okx_funding_rate")
        btc_price = data.get("btc_price")
        
        if not okx_funding_rate or not btc_price:
            self.log("⚠️  无 OKX 数据")
            return []
        
        self.log(f"💰 BTC 价格: ${btc_price:,.2f}")
        self.log(f"📊 资金费率: {okx_funding_rate:.4%}")
        
        # 获取 Polymarket BTC 相关市场
        markets = data.get("markets", [])
        btc_markets = [
            m for m in markets
            if "btc" in m.get("question", "").lower() or 
               "bitcoin" in m.get("question", "").lower()
        ]
        
        if not btc_markets:
            self.log("ℹ️  无 BTC 市场")
            return []
        
        self.log(f"📊 发现 {len(btc_markets)} 个 BTC 市场")
        
        signals = []
        
        for market in btc_markets:
            prompt = f"""你是 OKX 资金费率套利专家。分析以下套利机会：

## OKX 数据
BTC 价格：${btc_price:,.2f}
资金费率：{okx_funding_rate:.4%}
（正费率 = 多头支付空头 = 市场看多；负费率 = 空头支付多头 = 市场看空）

## Polymarket 市场
市场：{market.get('question', '')}
YES 价格：${market.get('yes_price', 0):.4f}
NO 价格：${market.get('no_price', 0):.4f}
交易量：${market.get('volume', 0):,.0f}

## 套利策略
1. 如果资金费率极端（>0.1% 或 <-0.1%），说明市场情绪极端
2. 可以在 Polymarket 做反向操作（资金费率高 → 买 NO，资金费率低 → 买 YES）
3. 同时在 OKX 做对冲（收取资金费率）

## 分析任务
1. 当前资金费率是否极端？
2. Polymarket 市场是否适合套利？
3. 预期收益是多少？
4. 建议的交易策略？

请以 JSON 格式输出：
{{
  "has_opportunity": true/false,
  "polymarket_action": "buy_yes" 或 "buy_no",
  "amount": 金额,
  "expected_return": 预期收益率,
  "confidence": 0-100,
  "reason": "原因"
}}
"""
            
            try:
                response = call_llm_sync("agent_okx_funding", prompt, timeout=30)
                
                # 解析 JSON
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    
                    if analysis.get("has_opportunity") and analysis.get("confidence", 0) >= 65:
                        signals.append({
                            "market": market.get("slug", ""),
                            "direction": analysis.get("polymarket_action"),
                            "amount": analysis.get("amount", 100),
                            "expected_return": analysis.get("expected_return", 0),
                            "confidence": analysis.get("confidence"),
                            "reason": analysis.get("reason"),
                            "okx_funding_rate": okx_funding_rate,
                            "btc_price": btc_price,
                            "source": "agent_okx_funding",
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        self.log(f"✅ 发现机会: {market.get('slug', '')[:50]}... (置信度 {analysis.get('confidence')})")
            
            except Exception as e:
                self.log(f"⚠️  分析失败: {e}")
                continue
        
        return signals
    
    def run(self):
        """执行资金费率套利扫描"""
        self.log("开始资金费率套利扫描...")
        
        # 加载市场数据
        data = self.load_market_data()
        
        if not data:
            self.log("ℹ️  无市场数据")
            return
        
        # 分析资金费率
        signals = self.analyze_funding_rate(data)
        
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
            
            self.log(f"✅ 已保存 {len(signals)} 个资金费率套利信号到 {output_file}")
        else:
            self.log("ℹ️  无资金费率套利信号")

def main():
    agent = AgentOKXFunding()
    agent.run()

if __name__ == "__main__":
    main()
