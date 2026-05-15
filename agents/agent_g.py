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
    
    def _is_dry_run_mode(self) -> bool:
        """检测是否为 dry-run 模式"""
        import os
        pm_trader = os.environ.get("PM_TRADER_PATH", "")
        if "mock" in pm_trader.lower():
            return True
        return os.environ.get("EXECUTOR_DRY_RUN", "0") == "1"

    def _generate_mock_trade_history(self) -> list:
        """在 dry-run 模式下生成合成交易历史，供学习循环使用。

        所有数据明确标记 synthetic=True、dry_run=True，绝不产生真实交易。
        """
        self.log("🔧 [DRY-RUN] 生成合成交易历史...")
        mock_trades = [
            {
                "trade_id": "mock-dryrun-001",
                "market_slug": "will-btc-hit-150k-by-2026-05-01",
                "side": "buy",
                "amount_usd": 50.0,
                "price": 0.12,
                "direction": "YES",
                "outcome": "open",
                "pnl": 0.0,
                "timestamp": (datetime.now() - timedelta(hours=4)).isoformat(),
                "synthetic": True,
                "dry_run": True,
            },
            {
                "trade_id": "mock-dryrun-002",
                "market_slug": "will-btc-hit-150k-by-2026-05-01",
                "side": "sell",
                "amount_usd": 50.0,
                "price": 0.38,
                "direction": "YES",
                "outcome": "closed",
                "pnl": 13.0,
                "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
                "synthetic": True,
                "dry_run": True,
            },
            {
                "trade_id": "mock-dryrun-003",
                "market_slug": "will-nba-champion-be-celtics-2026",
                "side": "buy",
                "amount_usd": 100.0,
                "price": 0.45,
                "direction": "YES",
                "outcome": "open",
                "pnl": 0.0,
                "timestamp": (datetime.now() - timedelta(hours=3)).isoformat(),
                "synthetic": True,
                "dry_run": True,
            },
            {
                "trade_id": "mock-dryrun-004",
                "market_slug": "will-nba-champion-be-celtics-2026",
                "side": "sell",
                "amount_usd": 100.0,
                "price": 0.62,
                "direction": "YES",
                "outcome": "closed",
                "pnl": 17.0,
                "timestamp": (datetime.now() - timedelta(hours=1)).isoformat(),
                "synthetic": True,
                "dry_run": True,
            },
            {
                "trade_id": "mock-dryrun-005",
                "market_slug": "fed-cut-rates-june-2026",
                "side": "buy",
                "amount_usd": 75.0,
                "price": 0.28,
                "direction": "YES",
                "outcome": "open",
                "pnl": 0.0,
                "timestamp": (datetime.now() - timedelta(hours=5)).isoformat(),
                "synthetic": True,
                "dry_run": True,
            },
            {
                "trade_id": "mock-dryrun-006",
                "market_slug": "fed-cut-rates-june-2026",
                "side": "sell",
                "amount_usd": 60.0,
                "price": 0.18,
                "direction": "YES",
                "outcome": "closed",
                "pnl": -7.5,
                "timestamp": (datetime.now() - timedelta(hours=1, minutes=30)).isoformat(),
                "synthetic": True,
                "dry_run": True,
            },
            {
                "trade_id": "mock-dryrun-007",
                "market_slug": "trump-tariff-announce-may-2026",
                "side": "buy",
                "amount_usd": 40.0,
                "price": 0.55,
                "direction": "NO",
                "outcome": "open",
                "pnl": 0.0,
                "timestamp": (datetime.now() - timedelta(hours=2, minutes=30)).isoformat(),
                "synthetic": True,
                "dry_run": True,
            },
            {
                "trade_id": "mock-dryrun-008",
                "market_slug": "trump-tariff-announce-may-2026",
                "side": "sell",
                "amount_usd": 40.0,
                "price": 0.70,
                "direction": "NO",
                "outcome": "closed",
                "pnl": -6.0,
                "timestamp": (datetime.now() - timedelta(hours=1, minutes=15)).isoformat(),
                "synthetic": True,
                "dry_run": True,
            },
            {
                "trade_id": "mock-dryrun-009",
                "market_slug": "nhl-stanley-cup-oilers-2026",
                "side": "buy",
                "amount_usd": 30.0,
                "price": 0.08,
                "direction": "YES",
                "outcome": "open",
                "pnl": 0.0,
                "timestamp": (datetime.now() - timedelta(hours=1, minutes=45)).isoformat(),
                "synthetic": True,
                "dry_run": True,
            },
            {
                "trade_id": "mock-dryrun-010",
                "market_slug": "nhl-stanley-cup-oilers-2026",
                "side": "sell",
                "amount_usd": 30.0,
                "price": 0.04,
                "direction": "YES",
                "outcome": "closed",
                "pnl": -1.2,
                "timestamp": (datetime.now() - timedelta(minutes=45)).isoformat(),
                "synthetic": True,
                "dry_run": True,
            },
        ]
        return mock_trades

    def load_trade_history(self):
        """加载交易历史。dry-run 模式下使用合成数据。"""
        if self._is_dry_run_mode():
            trades = self._generate_mock_trade_history()
            self.log(f"📊 [DRY-RUN] 加载了 {len(trades)} 笔合成交易历史")
            return trades

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
        
        buy_trades = [t for t in trades if t.get("side") == "buy"]
        sell_trades = [t for t in trades if t.get("side") == "sell"]
        
        total_buy_amount = sum(t.get("amount_usd", 0) for t in buy_trades)
        total_sell_amount = sum(t.get("amount_usd", 0) for t in sell_trades)
        
        markets = {}
        for trade in trades:
            market = trade.get("market_slug", "unknown")
            if market not in markets:
                markets[market] = []
            markets[market].append(trade)
        
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
        
        rejection_reasons = {}
        for signal_data in rejected_signals:
            reviews = signal_data.get("reviews", [])
            for review in reviews:
                reason = review.get("explanation", "未知原因")
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
        
        history_file = self.data_dir / "learning_history.json"
        history = []
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    history = json.load(f)
                if not isinstance(history, list):
                    history = []
            except Exception:
                history = []
        
        history.append(report)
        
        cutoff = datetime.now() - timedelta(days=30)
        history = [
            h for h in history
            if datetime.fromisoformat(h["timestamp"]) > cutoff
        ]
        
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 已更新学习历史（保留 {len(history)} 条记录）")
        
        # P0: 同时更新 learning_knowledge_base.json（Agent M / Agent P / Strategy Manager 读取）
        self._save_learning_knowledge_base(rejection_analysis)
    
    def _save_learning_knowledge_base(self, rejection_analysis):
        """P0 修复：将 Agent G 的复盘洞察写入 learning_knowledge_base.json
        下游 Agent M 在信号审查时读取 rejection_prompt_enhancement 注入 prompt。"""
        kb_file = self.data_dir / "learning_knowledge_base.json"
        
        # 加载已有知识库（如果存在）
        kb = {}
        if kb_file.exists():
            try:
                with open(kb_file, 'r') as f:
                    kb = json.load(f)
            except Exception:
                kb = {}
        
        # 从 rejection_analysis 提炼增强 prompt
        if rejection_analysis:
            common_mistakes = rejection_analysis.get("common_mistakes", [])
            unreliable = rejection_analysis.get("unreliable_sources", [])
            suggestions = rejection_analysis.get("improvement_suggestions", [])
            insights = rejection_analysis.get("key_insights", "")
            
            enhancement_parts = []
            enhancement_parts.append("\n## 🔄 决策层复盘发现（来自 Agent G 最新一轮）\n")
            if common_mistakes:
                enhancement_parts.append("**决策层常犯错误**：")
                enhancement_parts.extend([f"- {m}" for m in common_mistakes[:5]])
            if unreliable:
                enhancement_parts.append("\n**不可靠数据源**：")
                enhancement_parts.extend([f"- {s}" for s in unreliable[:5]])
            if suggestions:
                enhancement_parts.append("\n**改进建议**：")
                enhancement_parts.extend([f"- {s}" for s in suggestions[:5]])
            if insights:
                enhancement_parts.append(f"\n**核心洞察**：{insights}")
            
            enhancement_parts.append("\n**⚠️ 提示**：审查信号时，请结合以上复盘发现进行判断。")
            
            kb["rejection_prompt_enhancement"] = "\n".join(enhancement_parts)
        
        kb["last_updated"] = datetime.now().isoformat()
        kb["source"] = "agent_g_post_mortem"
        
        with open(kb_file, 'w') as f:
            json.dump(kb, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 已更新 learning_knowledge_base.json → rejection_prompt_enhancement")
    
    def run(self):
        """执行复盘分析"""
        self.log("开始交易复盘...")
        
        trades = self.load_trade_history()
        rejected_signals = self.load_rejected_signals()
        
        min_trades = 5 if self._is_dry_run_mode() else 10
        min_rejections = 1 if self._is_dry_run_mode() else 3
        
        trade_analysis = None
        rejection_analysis = None
        
        if len(trades) < min_trades:
            self.log(f"ℹ️  交易数据不足（{len(trades)}/{min_trades} 笔），跳过交易分析")
        else:
            try:
                self.log("分析交易表现...")
                trade_analysis = self.analyze_trades(trades)
            except Exception as e:
                self.log(f"⚠️  交易分析跳过: {e}")
        
        if len(rejected_signals) < min_rejections:
            self.log(f"ℹ️  拒绝信号数据不足（{len(rejected_signals)}/{min_rejections} 个），跳过拒绝分析")
        else:
            try:
                self.log("分析拒绝信号...")
                rejection_analysis = self.analyze_rejections(rejected_signals)
            except Exception as e:
                self.log(f"⚠️  拒绝信号分析跳过: {e}")
        
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