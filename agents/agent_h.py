"""
Agent H - 钱包跟单监控
职责：监控巨鲸钱包交易，发现跟单机会
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync
from _paths import get_base_dir
from utils.signals import ensure_signal_timestamps

class AgentH:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent H] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_h_{datetime.now().strftime('%Y%m%d')}.log"
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
    
    def analyze_whale_trades(self, data):
        """分析巨鲸交易"""
        self.log("分析巨鲸钱包交易...")
        
        whale_trades = data.get("whale_trades", [])
        
        if not whale_trades:
            self.log("ℹ️  无巨鲸交易数据")
            return []
        
        self.log(f"📊 发现 {len(whale_trades)} 笔巨鲸交易")
        
        signals = []
        
        for trade in whale_trades[:10]:  # 只分析最近 10 笔
            prompt = f"""你是 Polymarket 巨鲸跟单专家。分析以下巨鲸交易：

钱包地址：{trade.get('wallet', '')}
市场：{trade.get('market', '')}
方向：{trade.get('side', '')}
金额：${trade.get('amount', 0):,.2f}
价格：${trade.get('price', 0):.4f}
时间：{trade.get('timestamp', '')}

## 分析任务
1. 这个钱包的历史胜率如何？（如果有数据）
2. 这笔交易的逻辑是什么？
3. 是否值得跟单？
4. 建议的跟单金额和策略？

注意：根据研究，@elvenwisp 钱包（0x8c74b4eef9a894433B8126aA11d1345efb2B0488）胜率 57.1%，ROI -0.08%，不建议复制。

请以 JSON 格式输出：
{{
  "should_follow": true/false,
  "direction": "buy_yes" 或 "buy_no",
  "amount": 金额,
  "confidence": 0-100,
  "reason": "原因"
}}
"""
            
            try:
                response = call_llm_sync("agent_h", prompt, timeout=30)
                
                # 解析 JSON
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    
                    if analysis.get("should_follow") and analysis.get("confidence", 0) >= 70:
                        signals.append({
                            "market": trade.get("market", ""),
                            "direction": analysis.get("direction"),
                            "amount": analysis.get("amount", 50),  # 跟单金额较小
                            "confidence": analysis.get("confidence"),
                            "reason": analysis.get("reason"),
                            "whale_wallet": trade.get("wallet", ""),
                            "whale_amount": trade.get("amount", 0),
                            "source": "agent_h",
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        self.log(f"✅ 跟单信号: {trade.get('market', '')[:50]}... (置信度 {analysis.get('confidence')})")
            
            except Exception as e:
                self.log(f"⚠️  分析失败: {e}")
                continue
        
        return signals
    
    def run(self):
        """执行钱包跟单监控"""
        self.log("开始钱包跟单监控...")
        
        # 加载市场数据
        data = self.load_market_data()
        
        if not data:
            self.log("ℹ️  无市场数据")
            return
        
        # 分析巨鲸交易
        signals = self.analyze_whale_trades(data)
        
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
            
            self.log(f"✅ 已保存 {len(signals)} 个跟单信号到 {output_file}")
        else:
            self.log("ℹ️  无跟单信号")

def main():
    agent = AgentH()
    agent.run()

if __name__ == "__main__":
    main()
