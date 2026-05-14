"""
Agent G - 交易复盘与经验学习
职责：分析每笔交易的胜败原因，积累经验教训，反馈给决策层
"""

import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from _paths import get_base_dir, get_pm_trader, get_pm_trader_env
from llm_helper import call_llm

class AgentG:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.config_dir = self.base_dir / "config"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent G] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_g_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_config(self):
        """加载系统配置"""
        config_file = self.config_dir / "system_config.json"
        
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.log(f"⚠️  加载配置失败: {e}")
            return {}
    
    def load_trade_history(self):
        """加载交易历史"""
        try:
            result = subprocess.run(
                [get_pm_trader(), "history", "--limit", "50"],
                capture_output=True,
                text=True,
                timeout=30,
                env=get_pm_trader_env()
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("ok"):
                    trades = data.get("data", [])
                    self.log(f"📊 加载了 {len(trades)} 笔交易历史")
                    return trades
            
            self.log(f"❌ 加载交易历史失败: {result.stderr}")
            return []
        
        except Exception as e:
            self.log(f"❌ 加载交易历史异常: {e}")
            return []
    
    def load_rejected_signals(self):
        """加载被拒绝的信号"""
        review_file = self.data_dir / "review_results.json"
        
        if not review_file.exists():
            return []
        
        try:
            with open(review_file, 'r') as f:
                data = json.load(f)
            
            rejected = data.get("rejected_signals", [])
            self.log(f"📊 加载了 {len(rejected)} 个被拒绝的信号")
            return rejected
        
        except Exception as e:
            self.log(f"❌ 加载拒绝信号失败: {e}")
            return []
    
    def analyze_trades(self, trades):
        """分析交易表现"""
        if not trades:
            self.log("ℹ️  无交易数据")
            return None
        
        self.log("分析交易表现...")
        
        # 统计数据
        buy_trades = [t for t in trades if t.get("side") == "buy"]
        sell_trades = [t for t in trades if t.get("side") == "sell"]
        
        total_buy_amount = sum(t.get("amount_usd", 0) for t in buy_trades)
        total_sell_amount = sum(t.get("amount_usd", 0) for t in sell_trades)
        
        # 按市场分组
        markets = {}
        for trade in trades:
            market = trade.get("market_slug", "unknown")
            if market not in markets:
                markets[market] = []
            markets[market].append(trade)
        
        # 构建分析提示词
        prompt = f"""你是 Polymarket 交易系统的复盘分析师。请分析以下交易数据，找出成功和失败的模式。

## 交易统计
- 总交易数：{len(trades)}
- 买入交易：{len(buy_trades)} 笔，总金额 ${total_buy_amount:.2f}
- 卖出交易：{len(sell_trades)} 笔，总金额 ${total_sell_amount:.2f}
- 涉及市场：{len(markets)} 个

## 最近 10 笔交易
{json.dumps(trades[:10], indent=2, ensure_ascii=False)}

## 分析任务
1. **成功模式识别**
   - 哪些类型的市场表现好？
   - 哪些交易策略有效？
   - 成功交易的共同特征是什么？

2. **失败模式识别**
   - 哪些市场亏损严重？
   - 哪些策略失效？
   - 失败交易的共同特征是什么？

3. **改进建议**
   - 应该避免什么？
   - 应该加强什么？
   - 具体的参数调整建议

请以 JSON 格式输出分析结果：
{{
  "success_patterns": ["模式1", "模式2"],
  "failure_patterns": ["模式1", "模式2"],
  "recommendations": ["建议1", "建议2"],
  "key_insights": "核心洞察"
}}
"""
        
        try:
            response = call_llm(
                prompt=prompt,
                model="gpt-5.4-mini",
                temperature=0.3,
                max_tokens=2000
            )
            
            # 解析 JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                self.log("✅ 交易分析完成")
                return analysis
            else:
                self.log("⚠️  无法解析分析结果")
                return None
        
        except Exception as e:
            self.log(f"❌ 交易分析失败: {e}")
            return None
    
    def analyze_rejections(self, rejected_signals):
        """分析被拒绝的信号"""
        if not rejected_signals:
            self.log("ℹ️  无拒绝信号数据")
            return None
        
        self.log("分析拒绝信号...")
        
        # 统计拒绝原因
        rejection_reasons = {}
        for signal_data in rejected_signals:
            reviews = signal_data.get("reviews", [])
            for review in reviews:
                reason = review.get("explanation", "未知原因")
                # 提取关键词
                if "数据不足" in reason or "数据来源" in reason:
                    key = "数据质量问题"
                elif "逻辑" in reason or "相关性" in reason:
                    key = "逻辑缺陷"
                elif "时间" in reason or "过长" in reason:
                    key = "时间跨度问题"
                elif "流动性" in reason or "滑点" in reason:
                    key = "流动性风险"
                elif "价格" in reason or "上涨空间" in reason:
                    key = "价格风险"
                else:
                    key = "其他"
                
                rejection_reasons[key] = rejection_reasons.get(key, 0) + 1
        
        prompt = f"""你是 Polymarket 交易系统的风险审查分析师。请分析以下被拒绝的信号，找出决策层的系统性问题。

## 拒绝统计
- 总拒绝数：{len(rejected_signals)}
- 拒绝原因分布：{json.dumps(rejection_reasons, indent=2, ensure_ascii=False)}

## 最近 5 个被拒绝的信号
{json.dumps(rejected_signals[:5], indent=2, ensure_ascii=False)}

## 分析任务
1. **决策层问题诊断**
   - 决策层最常犯的错误是什么？
   - 哪些数据源不可靠？
   - 哪些逻辑推理有缺陷？

2. **改进建议**
   - 决策层应该如何改进？
   - 需要增加哪些数据源？
   - 需要调整哪些策略参数？

请以 JSON 格式输出分析结果：
{{
  "common_mistakes": ["错误1", "错误2"],
  "unreliable_sources": ["数据源1", "数据源2"],
  "improvement_suggestions": ["建议1", "建议2"],
  "key_insights": "核心洞察"
}}
"""
        
        try:
            response = call_llm(
                prompt=prompt,
                model="deepseek-r1",
                temperature=0.3,
                max_tokens=4000
            )
            
            # 解析 JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                self.log("✅ 拒绝信号分析完成")
                return analysis
            else:
                self.log("⚠️  无法解析分析结果")
                return None
        
        except Exception as e:
            self.log(f"❌ 拒绝信号分析失败: {e}")
            return None
    
    def save_learning_report(self, trade_analysis, rejection_analysis):
        """保存学习报告"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "trade_analysis": trade_analysis,
            "rejection_analysis": rejection_analysis
        }
        
        output_file = self.data_dir / "learning_report.json"
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 已保存学习报告到 {output_file}")
        
        # 追加到历史记录
        history_file = self.data_dir / "learning_history.json"
        history = []
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    history = json.load(f)
                if not isinstance(history, list):
                    history = []
            except:
                history = []
        
        history.append(report)
        
        # 只保留最近 30 天的记录
        cutoff = datetime.now() - timedelta(days=30)
        history = [
            h for h in history
            if datetime.fromisoformat(h["timestamp"]) > cutoff
        ]
        
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 已更新学习历史（保留 {len(history)} 条记录）")
    
    def run(self):
        """执行复盘分析"""
        self.log("开始交易复盘...")
        
        # 加载数据
        trades = self.load_trade_history()
        rejected_signals = self.load_rejected_signals()
        
        # 检查是否有足够数据
        if len(trades) < 10:
            self.log(f"ℹ️  交易数据不足（{len(trades)} 笔），需要至少 10 笔")
            return
        
        if len(rejected_signals) < 3:
            self.log(f"ℹ️  拒绝信号数据不足（{len(rejected_signals)} 个），需要至少 3 个")
            return
        
        # 分析交易（使用更快的模型）
        try:
            self.log("分析交易表现（使用 gpt-5.4-mini）...")
            trade_analysis = self.analyze_trades(trades)
        except Exception as e:
            self.log(f"⚠️  交易分析跳过: {e}")
            trade_analysis = None
        
        # 分析拒绝信号（使用更快的模型）
        try:
            self.log("分析拒绝信号（使用 gpt-5.4-mini）...")
            rejection_analysis = self.analyze_rejections(rejected_signals)
        except Exception as e:
            self.log(f"⚠️  拒绝信号分析跳过: {e}")
            rejection_analysis = None
        
        # 保存报告
        if trade_analysis or rejection_analysis:
            self.save_learning_report(trade_analysis, rejection_analysis)
            self.log("✅ 复盘完成")
        else:
            self.log("ℹ️  无足够数据进行复盘")

def main():
    agent = AgentG()
    agent.run()

if __name__ == "__main__":
    main()
