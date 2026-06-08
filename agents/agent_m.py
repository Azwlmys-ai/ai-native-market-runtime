"""
Agent M - 风险审查员（弹性负载均衡）
职责：审查所有交易信号，强制找出 3 个失败原因
支持批次处理模式（由 Agent N 调用）
支持缓存机制（提高数据一致性）
支持弹性负载均衡（信号数 ≥ 3 时自动并发处理）
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir
from llm_helper import call_llm_sync, LLMModelError
from review_cache import ReviewCache
from event_logger import write_event

class AgentM:
    def __init__(self, base_dir=None, batch_file=None, output_file=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 批次处理模式
        self.batch_file = Path(batch_file) if batch_file else None
        self.output_file = Path(output_file) if output_file else None
        
        # 缓存管理
        self.cache = ReviewCache(str(self.base_dir))
        self.cache_hits = 0
        self.cache_misses = 0
        
        # 负载均衡配置
        self.CONCURRENT_THRESHOLD = 3  # 信号数 ≥ 3 时启用并发
        self.MAX_WORKERS = 3  # 最大并发数
        self.PARTIAL_FLUSH_EVERY = max(1, int(os.environ.get("PA_AGENT_M_PARTIAL_EVERY", "5")))
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent M] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_m_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_signals(self):
        """加载待审查的交易信号"""
        # 批次模式：从指定文件加载
        if self.batch_file:
            if not self.batch_file.exists():
                self.log(f"⚠️  批次文件不存在: {self.batch_file}")
                return []
            
            try:
                with open(self.batch_file, 'r') as f:
                    data = json.load(f)
                
                if isinstance(data, list):
                    return data
                else:
                    return [data]
            
            except Exception as e:
                self.log(f"❌ 加载批次文件失败: {e}")
                return []
        
        # 标准模式：从主信号文件加载
        signals_file = self.data_dir / "signals.json"
        
        if not signals_file.exists():
            self.log("⚠️  无信号文件")
            return []
        
        try:
            with open(signals_file, 'r') as f:
                data = json.load(f)
            
            # 兼容多种格式
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # 如果是对象格式，提取信号列表
                if "signals" in data:
                    return data["signals"]
                else:
                    return [data]  # 单个信号对象
            else:
                self.log(f"⚠️  未知信号格式: {type(data)}")
                return []
        
        except Exception as e:
            self.log(f"❌ 加载信号失败: {e}")
            return []
    
    # ------------------------------------------------------------------
    # 预处理：仓位上限 + 分类（纯 Python，无 LLM，可离线单测）
    # ------------------------------------------------------------------

    @staticmethod
    def classify_signal(signal: dict) -> dict:
        """
        返回信号分类信息（纯函数，无副作用，供测试和预处理使用）。

        返回：
          {
            "is_whitelist": bool,
            "is_extreme_price": bool,
            "is_whitelist_extreme": bool,
            "is_arbitrage": bool,
          }
        """
        market_name = signal.get("market_name", signal.get("market", ""))
        price = signal.get("price", 0)
        direction = signal.get("direction", "")

        whitelist_keywords = ["NHL Stanley Cup", "NBA Finals", "MLB World Series", "NFL Super Bowl"]
        is_whitelist = any(kw in market_name for kw in whitelist_keywords)
        is_extreme_price = (
            (direction == "NO" and price >= 0.85) or
            (direction == "YES" and price <= 0.15)
        )
        is_whitelist_extreme = is_whitelist and is_extreme_price
        is_arbitrage = direction == "ARBITRAGE"

        return {
            "is_whitelist": is_whitelist,
            "is_extreme_price": is_extreme_price,
            "is_whitelist_extreme": is_whitelist_extreme,
            "is_arbitrage": is_arbitrage,
        }

    def _preprocess_signal(self, signal: dict, cls: dict) -> dict:
        """
        FIX_PLAN #9: 仓位 ≥ 20% 对白名单/套利信号「强制下调」而非拒绝。

        做法：在送入 LLM 前把 position_size 降到 0.19，让 LLM 在合规仓位下
        做实质性评估，而非直接触发「仓位超限」硬拒。
        原始仓位记入 _original_position_size，供审计/日志使用。
        对普通信号不做任何修改。
        """
        if not (cls["is_whitelist_extreme"] or cls["is_arbitrage"]):
            return signal

        pos = signal.get("position_size", 0)
        if pos < 0.20:
            return signal

        # 需要下调：浅拷贝后修改
        capped = dict(signal)
        capped["position_size"] = 0.19
        capped["_original_position_size"] = pos
        self.log(
            f"⚠️ [仓位上限] {'白名单极端' if cls['is_whitelist_extreme'] else '套利'}信号 "
            f"position_size={pos:.1%} → 降至 19% 后送审"
        )
        return capped

    def _deterministic_rejection(self, signal: dict, cls: dict):
        """Fail closed before LLM for rules that must not be overridden."""
        risk_rejection = self._risk_violation_rejection(signal)
        if risk_rejection:
            return risk_rejection

        if cls["is_whitelist_extreme"]:
            missing = []
            if not signal.get("data_sources"):
                missing.append("data_sources")
            if not signal.get("logic_chain"):
                missing.append("logic_chain")
            if missing:
                reason = (
                    "白名单极端价格信号缺少可审计字段: "
                    + ", ".join(missing)
                    + "；拒绝，避免 NHL/NBA 等高价 NO 旧策略绕过风控。"
                )
                return {
                    "market_id": signal.get("market_id"),
                    "market_name": signal.get("market_name"),
                    "signal": signal,
                    "decision": "REJECT",
                    "review": {
                        "risk_points": [
                            reason,
                            "缺少数据源或逻辑链时，无法验证球队实力、伤病、赛程、赔率或外部统计依据。",
                        ],
                        "failure_probability": 100,
                        "decision": "REJECT",
                        "explanation": reason,
                    },
                    "reason": reason,
                }
        return None

    def _risk_violation_rejection(self, signal: dict):
        risk_file = self.base_dir / "data" / "risk_snapshot.json"
        if not risk_file.exists():
            return None

        try:
            risk_data = json.loads(risk_file.read_text())
        except Exception:
            return None

        exposure = risk_data.get("exposure", {})
        violations = exposure.get("violations", [])
        if not violations:
            return None

        signal_theme = self._signal_theme_key(signal)
        signal_text = " ".join([
            str(signal.get("market_name", "")),
            str(signal.get("market", "")),
            str(signal.get("market_slug", "")),
            str(signal.get("slug", "")),
        ]).lower()

        for violation in violations:
            vtype = violation.get("type")
            if vtype == "total_exposure":
                reason = (
                    f"账户总暴露 ${violation.get('value')} 已超过上限 "
                    f"{self._format_limit_pct(violation.get('limit'))}；拒绝新增仓位。"
                )
                return self._reject_result(signal, reason, failure_probability=100)

            if vtype == "single_theme_exposure" and violation.get("theme") == signal_theme:
                reason = (
                    f"主题 {signal_theme} 暴露 ${violation.get('value')} 已超过上限 "
                    f"{self._format_limit_pct(violation.get('limit'))}；拒绝继续加仓相关市场。"
                )
                return self._reject_result(signal, reason, failure_probability=100)

            asset = str(violation.get("asset", "")).lower()
            if vtype == "single_asset_exposure" and asset and asset in signal_text:
                reason = (
                    f"标的 {violation.get('asset')} 暴露 ${violation.get('value')} 已超过上限 "
                    f"{self._format_limit_pct(violation.get('limit'))}；拒绝继续加仓。"
                )
                return self._reject_result(signal, reason, failure_probability=100)

        return None

    @staticmethod
    def _signal_theme_key(signal: dict) -> str:
        text = " ".join([
            str(signal.get("market_name", "")),
            str(signal.get("market", "")),
            str(signal.get("market_slug", "")),
            str(signal.get("slug", "")),
        ]).lower()

        if "2028" in text and "democratic" in text and "presidential" in text:
            return "2028_democratic_presidential_nomination"
        if "nhl stanley cup" in text:
            return "nhl_stanley_cup"
        if "nba finals" in text:
            return "nba_finals"
        if "gta vi" in text:
            return "gta_vi_related"
        return signal.get("market_slug", signal.get("slug", "unknown"))

    @staticmethod
    def _reject_result(signal: dict, reason: str, failure_probability: int = 100):
        return {
            "market_id": signal.get("market_id"),
            "market_name": signal.get("market_name"),
            "signal": signal,
            "decision": "REJECT",
            "review_status": "risk_reject",
            "review": {
                "risk_points": [reason],
                "failure_probability": failure_probability,
                "decision": "REJECT",
                "review_status": "risk_reject",
                "explanation": reason,
            },
            "reason": reason,
        }

    @staticmethod
    def _model_error_result(signal: dict, error: LLMModelError):
        explanation = str(error)
        return {
            "market_id": signal.get("market_id"),
            "market_name": signal.get("market_name"),
            "signal": signal,
            "decision": "DEFER",
            "review_status": "model_error",
            "review": {
                "risk_points": [],
                "failure_probability": None,
                "decision": "DEFER",
                "review_status": "model_error",
                "error_type": error.error_type,
                "models_tried": error.models_tried,
                "fallback_used": error.fallback_used,
                "explanation": explanation,
            },
            "reason": explanation,
        }

    @staticmethod
    def _format_limit_pct(value):
        try:
            return f"{float(value):.0%}"
        except (TypeError, ValueError):
            return str(value)

    # ------------------------------------------------------------------

    @staticmethod
    def _is_cointegration_probe(signal: dict) -> bool:
        src = str(signal.get("source_agent") or signal.get("source") or "").lower()
        if src != "cointegration":
            return False
        return signal.get("probe") is True or signal.get("tier") in ("research", "exploration")

    def _lightweight_coint_review(self, signal: dict) -> dict:
        """协整 probe 轻量审查：硬规则 + 结构化评分，不调用 LLM。"""
        market = signal.get("market_name", signal.get("market", "unknown"))
        cls = self.classify_signal(signal)
        signal = self._preprocess_signal(signal, cls)

        deterministic = self._deterministic_rejection(signal, cls)
        if deterministic:
            self.log(f"⛔ risk_reject(coint): {market[:60]} - {deterministic['reason']}")
            return deterministic

        if not self._signal_sound(signal):
            reason = "协整 probe 信号缺少 data_sources/logic_chain"
            return self._reject_result(signal, reason, failure_probability=100)

        ev = signal.get("evidence") or {}
        try:
            confidence = float(signal.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            zscore = abs(float(ev.get("zscore") or 0))
        except (TypeError, ValueError):
            zscore = 0.0
        try:
            corr = abs(float(ev.get("corr") or 0))
        except (TypeError, ValueError):
            corr = 0.0

        data_sufficiency = signal.get("data_sufficiency") or ev.get("data_sufficiency") or "low"
        tier = signal.get("tier", "research")

        fp = 45.0 if tier == "exploration" else 40.0
        if data_sufficiency == "low":
            fp += 10.0
        if confidence < 40:
            fp += 10.0
        if zscore < 1.5:
            fp += 15.0
        fp = min(99.0, max(0.0, fp))

        if fp >= self.PROBE_MAX_FP:
            decision = "REJECT"
        elif fp >= self.PROBE_MIN_FP:
            decision = "PAPER_PROBE"
        else:
            decision = "PAPER_PROBE"
            fp = self.PROBE_MIN_FP

        explanation = (
            f"lightweight coint review: tier={tier} conf={confidence:.1f} "
            f"z={zscore:.2f} corr={corr:.2f} fp={fp:.1f}"
        )
        self.log(f"⚡ lightweight coint: {market[:60]} → {decision}")
        return {
            "market_id": signal.get("market_id"),
            "market_name": signal.get("market_name"),
            "signal": signal,
            "decision": decision,
            "review_status": "lightweight_coint",
            "review": {
                "risk_points": [],
                "failure_probability": fp,
                "decision": decision,
                "review_status": "lightweight_coint",
                "explanation": explanation,
                "structured_scores": {
                    "confidence": confidence,
                    "zscore": zscore,
                    "corr": corr,
                    "data_sufficiency": data_sufficiency,
                },
            },
            "reason": explanation,
        }

    def review_signal(self, signal):
        """审查单个信号（单模型验证 + 缓存 + 学习成果）"""
        market = signal.get('market_name', signal.get('market', 'unknown'))

        # 预分类（纯 Python，无 LLM）
        cls = self.classify_signal(signal)
        is_whitelist_extreme = cls["is_whitelist_extreme"]
        is_arbitrage = cls["is_arbitrage"]

        # FIX_PLAN #9: 仓位上限预处理（白名单/套利 position>=20% → 降至 19%）
        signal = self._preprocess_signal(signal, cls)

        deterministic = self._deterministic_rejection(signal, cls)
        if deterministic:
            self.log(f"⛔ risk_reject: {market[:60]} - {deterministic['reason']}")
            return deterministic

        if self._is_cointegration_probe(signal):
            return self._lightweight_coint_review(signal)

        # 检查缓存
        cached_result = self.cache.get(signal)
        if cached_result is not None:
            self.cache_hits += 1
            self.log(f"✅ 缓存命中: {market[:60]}")
            return cached_result
        
        self.cache_misses += 1
        self.log(f"审查信号: {market[:60]}")

        # 加载学习成果
        kb_file = self.base_dir / "data" / "learning_knowledge_base.json"
        learning_enhancement = ""
        if kb_file.exists():
            try:
                with open(kb_file, 'r') as f:
                    kb = json.load(f)
                    learning_enhancement = kb.get("rejection_prompt_enhancement", "")
            except Exception:
                pass
        
        # P0: 加载 risk_snapshot.json（定量风险层）
        risk_summary = ""
        risk_file = self.base_dir / "data" / "risk_snapshot.json"
        if risk_file.exists():
            try:
                with open(risk_file, 'r') as f:
                    risk_data = json.load(f)
                # 精简摘要，不超过 800 字符
                summary_parts = []
                summary_parts.append("\n## 📊 当前风险环境（RiskEngine 快照）\n")
                summary_parts.append(f"- 数据可用: {risk_data.get('data_available', False)}")
                summary_parts.append(f"- 资产数量: {risk_data.get('asset_count', 0)}")
                exposures = risk_data.get("exposure", {})
                violations = exposures.get("violations", [])
                if violations:
                    summary_parts.append("- ⚠️ 风险敞口违规:")
                    for v in violations[:3]:
                        summary_parts.append(f"  * {v.get('asset','?')}: {v.get('value','?')} (上限 {v.get('limit','?')})")
                else:
                    summary_parts.append("- ✅ 无风险敞口违规")
                var_data = risk_data.get("var", {})
                if var_data.get("VaR_95_daily") is not None:
                    summary_parts.append(f"- VaR 95% (日): {var_data.get('VaR_95_daily', 'N/A')}")
                    summary_parts.append(f"- VaR 标签: {var_data.get('label', 'N/A')}")
                corr_count = len(risk_data.get("correlations", []))
                summary_parts.append(f"- 高相关性资产对: {corr_count}")
                # 压缩到 800 字符
                raw = "\n".join(summary_parts)
                risk_summary = raw[:800]
            except Exception:
                pass
        
        prompt = f"""
你是风险审查员，需要客观评估这个交易信号的质量。

信号详情：
{json.dumps(signal, indent=2, ensure_ascii=False)}

评估标准（严格版 - 确保信号质量）：
1. 数据支撑：数据源是否具体、时效性强、与标的直接相关？
2. 逻辑完整性：推理链条是否清晰、合理、可验证？
3. EV 合理性：EV 是否在合理范围内（< 100%）？
4. 风险可控：仓位是否合理（< 20%）？失败概率是否可接受（< 35%）？

评估要求（严格标准）：
- 列出 2-3 个主要风险点
- 评估失败概率（0-100）
- 给出最终建议（三级 risk grading，不再一票否决）：
  * APPROVE：正常 paper 仓位。必须同时满足以下所有条件
    - 有具体数据源（data_sources）且与标的直接相关
    - 有完整逻辑链（logic_chain）且推理合理
    - EV 在合理范围内（0% < EV < 100%）
    - 失败概率 < 35%
    - 仓位 < 20%
  * PAPER_PROBE：小仓试错。信号其余健全（数据源/逻辑链完整、EV 合理、仓位<20%），
    但失败概率处于中等区间（35% <= 失败概率 < 60%）——不直接否决，给小额受控试错以沉淀学习。
  * REJECT：满足以下任一条件即拒绝
    - 数据源泛化或与标的无关
    - EV > 100%（不合理）或 EV < 0%（亏损）
    - 失败概率 >= 60%
    - 仓位 >= 20%
    - 逻辑链不完整或推理不合理

特殊规则（白名单市场 + 极端价格）：
{'✅ 当前信号属于白名单市场（NHL/NBA/MLB/NFL）且价格极端（NO >= 0.85 或 YES <= 0.15）' if is_whitelist_extreme else ''}
{'此类信号仍必须满足 data_sources 和 logic_chain 可审计要求；不得仅凭“高价 NO/低价 YES”直接 APPROVE。' if is_whitelist_extreme else ''}
{'如果数据源和逻辑链完整，可在仓位已预处理至 ≤ 19% 的前提下继续评估；否则必须 REJECT。' if is_whitelist_extreme else ''}

特殊规则（跨平台套利）：
{'✅ 当前信号为跨平台套利（ARBITRAGE），应用以下宽松标准：' if is_arbitrage else ''}
{'1. 不受 0.40-0.60 价格区间限制' if is_arbitrage else ''}
{'2. 不要求精确的 EV > 8% 计算，套利本身就是锁定价差' if is_arbitrage else ''}
{'3. 重点验证：对冲方向互补性、价差优势（现货价差 > 5% 或资金费率年化 > 50%）、数据完整性（必须有 OKX 价格）' if is_arbitrage else ''}
{'4. 风险点：基差风险、流动性风险、保证金风险' if is_arbitrage else ''}
{'5. 如果数据完整且对冲逻辑合理，应倾向于 APPROVE' if is_arbitrage else ''}

{risk_summary}

{learning_enhancement}

输出 JSON 格式（decision 取 APPROVE / PAPER_PROBE / REJECT 之一）：
{{
  "risk_points": ["风险点1", "风险点2"],
  "failure_probability": 35,
  "decision": "APPROVE",
  "explanation": "详细说明"
}}
"""
        
        try:
            # 单模型验证（只用 gpt-5.4，temperature=0.1）
            response = call_llm_sync(
                agent_id="agent_m_primary",
                prompt=prompt,
                timeout=60,
                temperature=0.1  # 低温度提高一致性
            )
            
            # 解析响应
            result = self._parse_response(response)
            
            self.log(f"模型决策: {result.get('decision')} - {market[:60]}")
            
            review_result = {
                "market_id": signal.get("market_id"),
                "market_name": signal.get("market_name"),
                "signal": signal,
                "decision": result.get("decision", "REJECT"),
                "review": result,
                "reason": result.get("explanation", "")
            }
            
            # 保存到缓存
            self.cache.set(signal, review_result)
            
            return review_result
        
        except LLMModelError as e:
            tag = e.error_type or "model_error"
            fb = " fallback_used" if e.fallback_used else ""
            self.log(f"⚠️ model_error ({tag}{fb}): {market[:60]} - {e}")
            return self._model_error_result(signal, e)
        except Exception as e:
            wrapped = LLMModelError(
                str(e),
                error_type="model_error",
                agent_id="agent_m_primary",
            )
            self.log(f"⚠️ model_error: {market[:60]} - {e}")
            return self._model_error_result(signal, wrapped)
    
    def _parse_response(self, response_text):
        """解析 LLM 响应"""
        try:
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            
            if start >= 0 and end > start:
                json_str = response_text[start:end]
                return json.loads(json_str)
            else:
                return {
                    "risk_points": ["响应格式错误"],
                    "failure_probability": 100,
                    "decision": "REJECT",
                    "explanation": "无法解析模型响应"
                }
        
        except Exception as e:
            return {
                "risk_points": [f"解析失败: {e}"],
                "failure_probability": 100,
                "decision": "REJECT",
                "explanation": f"响应解析错误: {e}"
            }
    
    # --- Phase 3d 三级 risk grading 参数 ---
    PROBE_MIN_FP = 35.0     # 失败概率下界（含），进入 PAPER_PROBE
    PROBE_MAX_FP = 60.0     # 失败概率上界（不含），>= 此值直接 REJECT
    PROBE_SIZE_FACTOR = 0.25  # paper_probe 仓位 = 正常仓 × 0.25

    @staticmethod
    def _signal_sound(signal: dict) -> bool:
        """可审计健全性：有具体数据源 + 完整逻辑链（probe 也要求健全，不试错垃圾信号）。"""
        return bool(signal.get("data_sources")) and bool(signal.get("logic_chain"))

    def _grade(self, result: dict) -> str:
        """确定性三级裁定（两者结合：LLM 提议 + failure_probability band）。

        硬规则拒绝（_deterministic_rejection）已在 review_signal 前置；这里只对过了硬规则的信号分级。
        model_error 不在此分级，直接 DEFER。
        - 失败概率 >= 60%                          → REJECT
        - 35% <= 失败概率 < 60% 且信号健全          → PAPER_PROBE（不再一票否决；不健全则 REJECT）
        - 失败概率 < 35% 且 LLM=APPROVE 且信号健全   → APPROVE（否则 REJECT：LLM 有数据/逻辑顾虑）
        """
        if result.get("review_status") == "model_error":
            return "DEFER"
        review = result.get("review", {}) or {}
        signal = result.get("signal", {}) or {}
        llm_decision = str(result.get("decision", "REJECT")).upper()
        try:
            fp = float(review.get("failure_probability"))
        except (TypeError, ValueError):
            fp = 100.0

        if fp >= self.PROBE_MAX_FP:
            return "REJECT"
        if self.PROBE_MIN_FP <= fp < self.PROBE_MAX_FP:
            return "PAPER_PROBE" if self._signal_sound(signal) else "REJECT"
        # fp < 35
        if llm_decision == "APPROVE" and self._signal_sound(signal):
            return "APPROVE"
        return "REJECT"

    def _bucket_review_results(self, signals: list, results: list):
        approved = []
        probes = []
        rejected = []
        model_errors = []

        for result in results:
            signal = result.get("signal", {})
            grade = self._grade(result)
            result["grade"] = grade
            if grade != "DEFER":
                result["decision"] = grade

            if grade == "APPROVE":
                signal["grade"] = "approve"
                approved.append(result)
            elif grade == "PAPER_PROBE":
                try:
                    ps = float(signal.get("position_size", 0.1) or 0.1)
                except (TypeError, ValueError):
                    ps = 0.1
                signal["position_size"] = round(ps * self.PROBE_SIZE_FACTOR, 4)
                signal["grade"] = "paper_probe"
                probes.append(result)
            elif grade == "DEFER":
                model_errors.append(result)
            else:
                rejected.append(result)

        def _is_paper(sig: dict) -> bool:
            return sig.get("paper", False) or str(sig.get("source", "")).startswith("paper")

        approved_real = [r for r in approved if not _is_paper(r["signal"])]
        approved_paper = [r for r in approved if _is_paper(r["signal"])]
        rejected_real = [r for r in rejected if not _is_paper(r["signal"])]
        rejected_paper = [r for r in rejected if _is_paper(r["signal"])]
        real_total = sum(1 for s in signals if not _is_paper(s))
        paper_total = sum(1 for s in signals if _is_paper(s))

        return {
            "approved": approved,
            "probes": probes,
            "rejected": rejected,
            "model_errors": model_errors,
            "approved_real": approved_real,
            "approved_paper": approved_paper,
            "rejected_real": rejected_real,
            "rejected_paper": rejected_paper,
            "real_total": real_total,
            "paper_total": paper_total,
        }

    def _emit_review_events(self, buckets: dict, cycle_id: str):
        for bucket_name, event_type in (
            ("approved", "signal.reviewed"),
            ("probes", "risk.paper_probe"),
            ("model_errors", "risk.model_error"),
            ("rejected", "risk.rejected"),
        ):
            for result in buckets[bucket_name]:
                signal = result.get("signal", {})
                write_event(
                    cycle_id=cycle_id,
                    type=event_type,
                    agent="agent_m",
                    payload={
                        "decision": result.get("grade", result.get("decision")),
                        "market_id": signal.get("market_id", ""),
                        "market_name": signal.get("market_name", ""),
                        "direction": signal.get("direction", ""),
                        "review": result.get("review", {}),
                    },
                )

    def _build_review_output(
        self,
        signals: list,
        buckets: dict,
        cycle_id: str,
        *,
        partial: bool = False,
        processed_count: int | None = None,
    ) -> tuple[dict, list]:
        approved = buckets["approved"]
        probes = buckets["probes"]
        rejected = buckets["rejected"]
        model_errors = buckets["model_errors"]

        output = {
            "timestamp": datetime.now().isoformat(),
            "total": len(signals),
            "processed_count": processed_count if processed_count is not None else len(signals),
            "partial": partial,
            "generated_cycle_id": cycle_id,
            "real_signals": buckets["real_total"],
            "paper_signals": buckets["paper_total"],
            "approved": len(approved),
            "paper_probe": len(probes),
            "rejected": len(rejected),
            "model_error": len(model_errors),
            "approved_real": len(buckets["approved_real"]),
            "approved_paper": len(buckets["approved_paper"]),
            "rejected_real": len(buckets["rejected_real"]),
            "rejected_paper": len(buckets["rejected_paper"]),
            "approved_signals": approved,
            "probe_signals": probes,
            "rejected_signals": rejected,
            "model_error_signals": model_errors,
            "cache_stats": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate": (
                    f"{self.cache_hits / len(signals) * 100:.1f}%"
                    if signals else "0%"
                ),
            },
        }
        approved_signals_only = [] if partial else (
            [r["signal"] for r in approved] + [r["signal"] for r in probes]
        )
        return output, approved_signals_only

    def _persist_review_output(self, output: dict, approved_signals_only: list):
        approved_signals_file = self.data_dir / "approved_signals.json"
        if self.output_file:
            output_file = self.output_file
            with open(output_file, "w") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            with open(approved_signals_file, "w") as f:
                json.dump(approved_signals_only, f, indent=2, ensure_ascii=False)
            return output_file

        output_file = self.data_dir / "review_results.json"
        from runtime import datastore as _ds
        _ds.put_review(
            output.get("generated_cycle_id") or output.get("timestamp") or "agent_m",
            output,
            approved_signals=approved_signals_only,
            base_dir=self.base_dir,
        )
        return output_file

    def run(self):
        """主流程（弹性负载均衡）"""
        self.log("开始风险审查...")

        signals = self.load_signals()

        if not signals:
            self.log("ℹ️  无待审查信号")
            return

        signal_count = len(signals)
        self.log(f"📊 发现 {signal_count} 个信号")

        cycle_id = os.environ.get(
            "PA_CYCLE_ID",
            f"review_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
        )

        def _flush_partial(results_so_far: list, processed_count: int):
            buckets = self._bucket_review_results(signals, results_so_far)
            output, approved_only = self._build_review_output(
                signals,
                buckets,
                cycle_id,
                partial=True,
                processed_count=processed_count,
            )
            self._persist_review_output(output, approved_only)
            self.log(
                f"💾 partial review_results: processed={processed_count}/{signal_count}"
            )

        if signal_count >= self.CONCURRENT_THRESHOLD:
            self.log(f"🚀 启用并发处理（{self.MAX_WORKERS} 线程）")
            results = self._review_concurrent(signals, on_partial=_flush_partial)
        else:
            self.log("📝 使用串行处理")
            results = self._review_sequential(signals, on_partial=_flush_partial)

        buckets = self._bucket_review_results(signals, results)
        self._emit_review_events(buckets, cycle_id)
        self.log(
            f"  [real]  通过 {len(buckets['approved_real'])}, "
            f"risk_reject {len(buckets['rejected_real'])}"
        )
        self.log(
            f"  [paper] 通过 {len(buckets['approved_paper'])}, "
            f"risk_reject {len(buckets['rejected_paper'])}"
        )
        self.log(
            f"  [grade] approve {len(buckets['approved'])}, "
            f"paper_probe {len(buckets['probes'])}, "
            f"risk_reject {len(buckets['rejected'])}, "
            f"model_error {len(buckets['model_errors'])}"
        )

        output, approved_signals_only = self._build_review_output(
            signals,
            buckets,
            cycle_id,
            partial=False,
            processed_count=len(results),
        )
        output_file = self._persist_review_output(output, approved_signals_only)

        self.log(
            f"✅ 审查完成: {len(buckets['approved'])} 通过, "
            f"{len(buckets['rejected'])} risk_reject, "
            f"{len(buckets['model_errors'])} model_error"
        )
        self.log(
            f"📊 缓存命中率: {self.cache_hits}/{len(signals)} "
            f"({self.cache_hits / len(signals) * 100:.1f}%)"
        )
        self.log(f"结果已保存到 {output_file}")
        self.log(f"通过的信号已保存到 {self.data_dir / 'approved_signals.json'}")
    
    def _review_sequential(self, signals, on_partial=None):
        """串行处理（信号数 < 3）"""
        results = []
        for idx, signal in enumerate(signals, 1):
            result = self.review_signal(signal)
            results.append(result)
            if on_partial and idx % self.PARTIAL_FLUSH_EVERY == 0:
                on_partial(results, idx)
        return results

    def _review_concurrent(self, signals, on_partial=None):
        """并发处理（信号数 ≥ 3）"""
        results = []
        processed = 0

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            future_to_signal = {
                executor.submit(self.review_signal, signal): signal
                for signal in signals
            }

            for future in as_completed(future_to_signal):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    signal = future_to_signal[future]
                    self.log(f"❌ 并发审查失败: {signal.get('market', 'unknown')} - {e}")
                    results.append({
                        "market_id": signal.get("market_id"),
                        "market_name": signal.get("market_name"),
                        "signal": signal,
                        "decision": "REJECT",
                        "review": {
                            "risk_points": [f"并发处理异常: {e}"],
                            "failure_probability": 100,
                            "decision": "REJECT",
                            "explanation": f"并发处理出错: {e}",
                        },
                        "reason": f"并发处理出错: {e}",
                    })
                processed += 1
                if on_partial and processed % self.PARTIAL_FLUSH_EVERY == 0:
                    on_partial(results, processed)

        return results

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Agent M - 风险审查员（弹性负载均衡）")
    parser.add_argument("--batch-file", type=str, help="批次信号文件路径")
    parser.add_argument("--output-file", type=str, help="输出结果文件路径")
    
    args = parser.parse_args()
    
    agent = AgentM(
        batch_file=args.batch_file,
        output_file=args.output_file
    )
    agent.run()

if __name__ == "__main__":
    main()
