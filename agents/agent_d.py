"""
Agent D - 无风险套利审查员
职责：发现 YES + NO < $1.00 的无风险套利机会
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync
from _paths import get_base_dir
from utils.market_data import get_polymarket_markets
from utils.signals import ensure_signal_timestamps

class AgentD:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent D] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_d_{datetime.now().strftime('%Y%m%d')}.log"
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
            self.log(f"📊 加载了 {len(markets)} 个市场")
            return markets
        
        except Exception as e:
            self.log(f"❌ 加载市场数据失败: {e}")
            return []
    
    def find_arbitrage_opportunities(self, markets):
        """发现无风险套利机会"""
        self.log("扫描无风险套利机会...")
        
        opportunities = []
        
        for market in markets:
            try:
                yes_price = float(market.get("yes_price", 1.0))
                no_price = float(market.get("no_price", 1.0))
                total_price = yes_price + no_price
                
                # 无风险套利：YES + NO < $1.00
                if total_price < 0.98:  # 留 2% 安全边际
                    profit_margin = (1.0 - total_price) / total_price
                    
                    opportunities.append({
                        "market": market.get("slug", ""),
                        "question": market.get("question", ""),
                        "yes_price": yes_price,
                        "no_price": no_price,
                        "total_price": total_price,
                        "profit_margin": profit_margin,
                        "volume": market.get("volume", 0)
                    })
            
            except Exception as e:
                continue
        
        # 按利润率排序
        opportunities.sort(key=lambda x: x["profit_margin"], reverse=True)
        
        self.log(f"✅ 发现 {len(opportunities)} 个无风险套利机会")
        return opportunities
    
    def analyze_opportunities(self, opportunities):
        """分析套利机会"""
        if not opportunities:
            self.log("ℹ️  无套利机会")
            return []
        
        self.log(f"分析 {len(opportunities)} 个套利机会...")
        
        signals = []
        
        for opp in opportunities[:5]:  # 只分析前 5 个
            prompt = f"""你是 Polymarket 无风险套利专家。分析以下套利机会：

市场：{opp['question']}
YES 价格：${opp['yes_price']:.4f}
NO 价格：${opp['no_price']:.4f}
总价格：${opp['total_price']:.4f}
理论利润率：{opp['profit_margin']:.2%}
交易量：${opp['volume']:,.0f}

## 分析任务
1. 这是真正的无风险套利还是数据错误？
2. 流动性是否足够（能否成交）？
3. 是否有隐藏风险（市场即将关闭、争议解决等）？
4. 建议的交易金额是多少？

请以 JSON 格式输出：
{{
  "is_valid": true/false,
  "confidence": 0-100,
  "recommended_amount": 金额,
  "reason": "原因"
}}
"""
            
            try:
                response = call_llm_sync("agent_d", prompt, timeout=30)
                
                # 解析 JSON
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    
                    if analysis.get("is_valid") and analysis.get("confidence", 0) >= 70:
                        signals.append({
                            "market": opp["market"],
                            "strategy": "risk_free_arbitrage",
                            "yes_amount": analysis.get("recommended_amount", 100) / 2,
                            "no_amount": analysis.get("recommended_amount", 100) / 2,
                            "expected_profit": opp["profit_margin"],
                            "confidence": analysis.get("confidence"),
                            "reason": analysis.get("reason"),
                            "source": "agent_d",
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        self.log(f"✅ 有效套利: {opp['market'][:50]}... (置信度 {analysis.get('confidence')})")
            
            except Exception as e:
                self.log(f"⚠️  分析失败: {e}")
                continue
        
        return signals
    
    def run(self):
        """执行无风险套利扫描"""
        self.log("开始无风险套利扫描...")
        
        # 加载市场数据
        markets = self.load_market_data()
        
        if not markets:
            self.log("ℹ️  无市场数据")
            return
        
        # 发现套利机会
        opportunities = self.find_arbitrage_opportunities(markets)
        
        # 分析机会
        signals = self.analyze_opportunities(opportunities)
        
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
            
            self.log(f"✅ 已保存 {len(signals)} 个套利信号到 {output_file}")
        else:
            self.log("ℹ️  无有效套利信号")

def main():
    agent = AgentD()
    agent.run()

if __name__ == "__main__":
    main()
