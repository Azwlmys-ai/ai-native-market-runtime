"""
Agent J - 交叉分析员
职责：交叉验证多个数据源，发现一致性信号
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync
from _paths import get_base_dir
from utils.signals import ensure_signal_timestamps

class AgentJ:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent J] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_j_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_all_data(self):
        """加载所有数据源"""
        data_file = self.data_dir / "latest_data.json"
        
        if not data_file.exists():
            self.log("⚠️  无市场数据文件")
            return {}
        
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            self.log(f"📊 加载数据成功")
            return data
        
        except Exception as e:
            self.log(f"❌ 加载数据失败: {e}")
            return {}
    
    def load_intelligence_report(self):
        """加载情报报告"""
        report_file = self.data_dir / "intelligence_report.json"
        
        if not report_file.exists():
            self.log("⚠️  无情报报告")
            return {}
        
        try:
            with open(report_file, 'r') as f:
                report = json.load(f)
            
            self.log(f"📊 加载情报报告成功")
            return report
        
        except Exception as e:
            self.log(f"❌ 加载情报报告失败: {e}")
            return {}
    
    def cross_validate_signals(self, data, intelligence):
        """交叉验证信号"""
        self.log("交叉验证多源信号...")
        
        # 获取各类数据
        markets = data.get("markets", [])
        news = data.get("news", [])
        btc_price = data.get("btc_price")
        okx_funding = data.get("okx_funding_rate")
        whale_trades = data.get("whale_trades", [])
        
        # 获取情报报告中的机会
        opportunities = intelligence.get("opportunities", [])
        
        if not opportunities:
            self.log("ℹ️  无情报机会")
            return []
        
        self.log(f"📊 交叉验证 {len(opportunities)} 个机会...")
        
        validated_signals = []
        
        for opp in opportunities[:5]:  # 只验证前 5 个
            prompt = f"""你是多源数据交叉验证专家。验证以下交易机会：

## 情报报告机会
市场：{opp.get('market', '')}
方向：{opp.get('direction', '')}
置信度：{opp.get('confidence', 0)}
理由：{opp.get('reason', '')}

## 可用数据源
- Polymarket 市场数据：{len(markets)} 个市场
- 新闻数据：{len(news)} 条
- BTC 价格：${btc_price:,.2f if btc_price else 0}
- OKX 资金费率：{okx_funding:.4% if okx_funding else 'N/A'}
- 巨鲸交易：{len(whale_trades)} 笔

## 验证任务
1. 这个机会是否得到多个数据源的支持？
2. 是否存在矛盾的信号？
3. 综合评估后的置信度是多少？
4. 是否应该执行这个交易？

请以 JSON 格式输出：
{{
  "is_validated": true/false,
  "supporting_sources": ["数据源列表"],
  "conflicting_signals": ["矛盾信号"],
  "adjusted_confidence": 0-100,
  "recommended_amount": 金额,
  "reason": "原因"
}}
"""
            
            try:
                response = call_llm_sync("agent_j", prompt, timeout=30)
                
                # 解析 JSON
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    validation = json.loads(json_match.group())
                    
                    if validation.get("is_validated") and validation.get("adjusted_confidence", 0) >= 70:
                        generated_at = datetime.now().isoformat()
                        validated_signals.append({
                            "market": opp.get("market", ""),
                            "direction": opp.get("direction", ""),
                            "amount": validation.get("recommended_amount", 100),
                            "confidence": validation.get("adjusted_confidence"),
                            "supporting_sources": validation.get("supporting_sources", []),
                            "reason": validation.get("reason"),
                            "source": "agent_j",
                            "timestamp": generated_at,
                            "generated_at": generated_at
                        })
                        
                        self.log(f"✅ 验证通过: {opp.get('market', '')[:50]}... (置信度 {validation.get('adjusted_confidence')})")
                    else:
                        self.log(f"❌ 验证失败: {opp.get('market', '')[:50]}...")
            
            except Exception as e:
                self.log(f"⚠️  验证失败: {e}")
                continue
        
        return validated_signals
    
    def run(self):
        """执行交叉验证"""
        self.log("开始交叉验证...")
        
        # 加载所有数据
        data = self.load_all_data()
        intelligence = self.load_intelligence_report()
        
        if not data or not intelligence:
            self.log("ℹ️  数据不足")
            return
        
        # 交叉验证信号
        signals = self.cross_validate_signals(data, intelligence)
        
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
            
            self.log(f"✅ 已保存 {len(signals)} 个验证信号到 {output_file}")
        else:
            self.log("ℹ️  无验证信号")

def main():
    agent = AgentJ()
    agent.run()

if __name__ == "__main__":
    main()
