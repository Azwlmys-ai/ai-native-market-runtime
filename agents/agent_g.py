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
try:
    from llm_helper import call_llm
    _LLM_IMPORT_ERROR = None
except Exception as e:
    call_llm = None
    _LLM_IMPORT_ERROR = e

LLM_TIMEOUT_SECONDS = 20
PM_HISTORY_TIMEOUT_SECONDS = 20

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

    def _get_llm_model(self) -> str:
        """从 config/llm_config.json 的 agent_models 读取 agent_g 专属模型名。
        如果缺失，回退到统一默认模型 deepseek-v4-pro。
        """
        _default_model = "deepseek-v4-pro"
        try:
            from llm_helper import load_llm_config
            config = load_llm_config()
            agent_models = config.get("agent_models", {})
            return agent_models.get("agent_g", _default_model)
        except Exception:
            return _default_model

    def _get_llm_provider(self) -> dict:
        """agent_g 专属 provider（model / api_base / api_key），不影响其他 Agent。"""
        try:
            from llm_helper import load_llm_config
            config = load_llm_config()
            provider = config.get("agent_providers", {}).get("agent_g", {})
            return provider if isinstance(provider, dict) else {}
        except Exception:
            return {}

    def _invoke_llm(self, prompt: str, temperature: float, max_tokens: int, timeout: int) -> str:
        """仅替换 model / api_url / api_key_source；prompt 与 timeout 保持不变。"""
        if call_llm is None:
            raise RuntimeError(f"LLM helper unavailable: {_LLM_IMPORT_ERROR}")

        provider = self._get_llm_provider()
        api_base = provider.get("api_base")
        api_key = provider.get("api_key")
        if api_base and api_key:
            import httpx
            from openai import OpenAI

            model = provider.get("model") or self._get_llm_model()
            proxy = provider.get("proxy")
            http_client = httpx.Client(
                trust_env=False,
                timeout=timeout,
                proxy=proxy if proxy else None,
            )
            client = OpenAI(
                api_key=api_key,
                base_url=api_base,
                timeout=timeout,
                http_client=http_client,
            )
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content

        return call_llm(
            prompt=prompt,
            model=self._get_llm_model(),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

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
                timeout=PM_HISTORY_TIMEOUT_SECONDS,
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
        
        trade_stats = self._build_trade_stats(trades)

        if trade_stats["dry_run"] or trade_stats["synthetic"]:
            self.log("🔧 [DRY-RUN] 跳过 LLM 交易分析，使用 deterministic fallback")
            return self._fallback_trade_analysis(
                trades,
                trade_stats,
                "dry_run_deterministic_fallback",
            )
        
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
            if call_llm is None:
                raise RuntimeError(f"LLM helper unavailable: {_LLM_IMPORT_ERROR}")
            response = self._invoke_llm(
                prompt=prompt,
                temperature=0.3,
                max_tokens=2000,
                timeout=LLM_TIMEOUT_SECONDS,
            )
            
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                analysis.update({
                    "llm_available": True,
                    "fallback_used": False,
                    "dry_run": trade_stats["dry_run"],
                    "synthetic": trade_stats["synthetic"],
                    "trade_stats": trade_stats,
                })
                self.log("✅ 交易分析完成")
                return analysis
            else:
                self.log("⚠️  无法解析分析结果")
                return self._fallback_trade_analysis(trades, trade_stats, "llm_parse_error")
        
        except Exception as e:
            self.log(f"❌ 交易分析失败: {e}")
            return self._fallback_trade_analysis(trades, trade_stats, str(e))

    def _build_trade_stats(self, trades):
        """汇总交易数据，供 LLM 和 deterministic fallback 共用。"""
        closed_trades = [t for t in trades if t.get("outcome") == "closed"]
        open_trades = [t for t in trades if t.get("outcome") == "open"]
        winning_trades = [t for t in closed_trades if t.get("pnl", 0) > 0]
        losing_trades = [t for t in closed_trades if t.get("pnl", 0) < 0]
        flat_trades = [t for t in closed_trades if t.get("pnl", 0) == 0]
        total_pnl = sum(t.get("pnl", 0) for t in closed_trades)
        total_closed_amount = sum(t.get("amount_usd", 0) for t in closed_trades)
        avg_pnl = total_pnl / len(closed_trades) if closed_trades else 0
        win_rate = len(winning_trades) / len(closed_trades) if closed_trades else 0

        market_pnl = {}
        for trade in closed_trades:
            market = trade.get("market_slug", "unknown")
            market_pnl[market] = market_pnl.get(market, 0) + trade.get("pnl", 0)

        best_markets = sorted(
            [{"market_slug": k, "pnl": v} for k, v in market_pnl.items()],
            key=lambda item: item["pnl"],
            reverse=True,
        )
        worst_markets = sorted(
            [{"market_slug": k, "pnl": v} for k, v in market_pnl.items()],
            key=lambda item: item["pnl"],
        )

        return {
            "total_trades": len(trades),
            "closed_trades": len(closed_trades),
            "open_trades": len(open_trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "flat_trades": len(flat_trades),
            "win_rate": round(win_rate, 4),
            "total_pnl": round(total_pnl, 4),
            "avg_closed_trade_pnl": round(avg_pnl, 4),
            "total_closed_amount_usd": round(total_closed_amount, 4),
            "best_markets": best_markets[:3],
            "worst_markets": worst_markets[:3],
            "dry_run": self._is_dry_run_mode() or any(t.get("dry_run") for t in trades),
            "synthetic": any(t.get("synthetic") for t in trades),
        }

    def _fallback_trade_analysis(self, trades, trade_stats, reason):
        """LLM 不可用时的确定性复盘摘要，基于 closed trades 统计生成。"""
        closed_count = trade_stats["closed_trades"]
        win_rate_pct = trade_stats["win_rate"] * 100
        total_pnl = trade_stats["total_pnl"]
        best = trade_stats["best_markets"]
        worst = trade_stats["worst_markets"]

        success_patterns = []
        failure_patterns = []
        recommendations = []

        if best and best[0]["pnl"] > 0:
            success_patterns.append(
                f"正收益市场集中在 {best[0]['market_slug']}，closed PnL={best[0]['pnl']:.2f}"
            )
        if trade_stats["winning_trades"]:
            success_patterns.append(
                f"{trade_stats['winning_trades']}/{closed_count} 笔已平仓交易盈利，胜率 {win_rate_pct:.1f}%"
            )

        if worst and worst[0]["pnl"] < 0:
            failure_patterns.append(
                f"亏损市场集中在 {worst[0]['market_slug']}，closed PnL={worst[0]['pnl']:.2f}"
            )
        if trade_stats["losing_trades"]:
            failure_patterns.append(
                f"{trade_stats['losing_trades']}/{closed_count} 笔已平仓交易亏损，需要限制同类信号仓位"
            )

        if not success_patterns:
            success_patterns.append("暂无稳定成功模式；样本量仍需继续累积")
        if not failure_patterns:
            failure_patterns.append("暂无显著失败模式；保持 dry-run 观察")

        if total_pnl >= 0:
            recommendations.append("继续保留正收益市场类型，但维持 dry-run 小额验证")
        else:
            recommendations.append("暂停放大同类策略，优先复核亏损市场的价格与流动性假设")
        recommendations.append("对亏损 closed trades 对应市场增加二次数据源校验")
        recommendations.append("保持 EXECUTOR_DRY_RUN=1 时只刷新学习文件，不触发真实交易")

        return {
            "success_patterns": success_patterns,
            "failure_patterns": failure_patterns,
            "recommendations": recommendations,
            "key_insights": (
                f"LLM unavailable; fallback summary used closed-trade stats: "
                f"{closed_count} closed, win_rate={win_rate_pct:.1f}%, total_pnl={total_pnl:.2f}."
            ),
            "llm_available": False,
            "fallback_used": True,
            "fallback_reason": reason,
            "dry_run": trade_stats["dry_run"],
            "synthetic": trade_stats["synthetic"],
            "trade_stats": trade_stats,
        }
    
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

        if self._is_dry_run_mode():
            self.log("🔧 [DRY-RUN] 跳过 LLM 拒绝分析，使用 deterministic fallback")
            return self._fallback_rejection_analysis(
                rejected_signals,
                rejection_reasons,
                "dry_run_deterministic_fallback",
            )
        
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
            if call_llm is None:
                raise RuntimeError(f"LLM helper unavailable: {_LLM_IMPORT_ERROR}")
            response = self._invoke_llm(
                prompt=prompt,
                temperature=0.3,
                max_tokens=4000,
                timeout=LLM_TIMEOUT_SECONDS,
            )
            
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                analysis.update({
                    "llm_available": True,
                    "fallback_used": False,
                    "dry_run": self._is_dry_run_mode(),
                    "synthetic": self._is_dry_run_mode(),
                    "rejection_stats": {
                        "total_rejected": len(rejected_signals),
                        "reason_distribution": rejection_reasons,
                    },
                })
                self.log("✅ 拒绝信号分析完成")
                return analysis
            else:
                self.log("⚠️  无法解析分析结果")
                return self._fallback_rejection_analysis(
                    rejected_signals,
                    rejection_reasons,
                    "llm_parse_error",
                )
        
        except Exception as e:
            self.log(f"❌ 拒绝信号分析失败: {e}")
            return self._fallback_rejection_analysis(
                rejected_signals,
                rejection_reasons,
                str(e),
            )

    def _fallback_rejection_analysis(self, rejected_signals, rejection_reasons, reason):
        """LLM 不可用时基于拒绝原因分布生成确定性摘要。"""
        sorted_reasons = sorted(
            rejection_reasons.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        top_reason = sorted_reasons[0][0] if sorted_reasons else "其他"
        common_mistakes = [
            f"主要拒绝原因为 {name}（{count} 次）"
            for name, count in sorted_reasons[:3]
        ]
        if not common_mistakes:
            common_mistakes.append("暂无足够拒绝原因样本")

        unreliable_sources = []
        if "数据质量问题" in rejection_reasons:
            unreliable_sources.append("信号中未充分交叉验证的数据源")
        if not unreliable_sources:
            unreliable_sources.append("未识别出特定不可靠数据源")

        suggestions = [
            f"优先减少触发 {top_reason} 的信号进入执行链路",
            "保留 Agent M fail-closed 行为，LLM 异常时继续拒绝而不是放行",
            "dry-run 阶段继续记录 rejected_signals，用于下一轮统计复盘",
        ]

        return {
            "common_mistakes": common_mistakes,
            "unreliable_sources": unreliable_sources,
            "improvement_suggestions": suggestions,
            "key_insights": (
                f"LLM unavailable; fallback summary used {len(rejected_signals)} "
                f"rejected signals and reason distribution."
            ),
            "llm_available": False,
            "fallback_used": True,
            "fallback_reason": reason,
            "dry_run": self._is_dry_run_mode(),
            "synthetic": self._is_dry_run_mode(),
            "rejection_stats": {
                "total_rejected": len(rejected_signals),
                "reason_distribution": rejection_reasons,
            },
        }
    
    def save_learning_report(self, trade_analysis, rejection_analysis):
        """保存学习报告"""
        analyses = [a for a in (trade_analysis, rejection_analysis) if a]
        llm_available = all(a.get("llm_available", True) for a in analyses)
        fallback_used = any(a.get("fallback_used", False) for a in analyses)
        dry_run = self._is_dry_run_mode() or any(a.get("dry_run", False) for a in analyses)
        synthetic = any(a.get("synthetic", False) for a in analyses)
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "llm_available": llm_available,
            "fallback_used": fallback_used,
            "dry_run": dry_run,
            "synthetic": synthetic,
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
        self._save_learning_knowledge_base(rejection_analysis, report)
    
    def _save_learning_knowledge_base(self, rejection_analysis, report=None):
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
        if report:
            kb["llm_available"] = report.get("llm_available", True)
            kb["fallback_used"] = report.get("fallback_used", False)
            kb["dry_run"] = report.get("dry_run", False)
            kb["synthetic"] = report.get("synthetic", False)
            trade_analysis = report.get("trade_analysis") or {}
            rejection_summary = report.get("rejection_analysis") or {}
            kb["agent_g_latest_summary"] = {
                "timestamp": report.get("timestamp"),
                "llm_available": report.get("llm_available", True),
                "fallback_used": report.get("fallback_used", False),
                "dry_run": report.get("dry_run", False),
                "synthetic": report.get("synthetic", False),
                "trade_key_insights": trade_analysis.get("key_insights"),
                "trade_stats": trade_analysis.get("trade_stats"),
                "rejection_key_insights": rejection_summary.get("key_insights"),
                "rejection_stats": rejection_summary.get("rejection_stats"),
            }
        
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
