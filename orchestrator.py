"""
Orchestrator - Multi-Agent 系统调度器
职责：协调所有 Agent 的执行顺序和数据流
"""

import json
import os
import sys
import time
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from _paths import get_base_dir, get_pm_trader, get_pm_trader_env
from event_logger import write_event
from paper_pnl import get_paper_portfolio

try:
    import fcntl
except ImportError:
    fcntl = None

SIGNAL_MAX_AGE_SECONDS = 2 * 60 * 60
PYTHON_BIN = sys.executable


class Orchestrator:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.status_file = self.data_dir / "orchestrator_status.json"
        self.lock_file = self.data_dir / "orchestrator.lock"
        self._lock_handle = None
        self._bootstrap_runtime_files()
    
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Orchestrator] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"orchestrator_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
        self._write_status_from_log(message, timestamp)
    
    def run_once(self):
        """执行一次完整的扫描周期"""
        if not self._acquire_run_lock():
            self.log("⏭️  已有扫描周期在运行，本次启动跳过")
            return

        cycle_id = (
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
            f"_pid{os.getpid()}"
        )
        self._current_cycle_id = cycle_id
        self._agent_b_ok_this_cycle = None
        self._agent_m_ok_this_cycle = None
        dry = os.environ.get("EXECUTOR_DRY_RUN", "").lower() in ("1", "true", "yes")
        try:
            from runtime import live_probe as _lp
            live_on = _lp.live_enabled()
        except Exception:
            live_on = False
        mode = "dry_run" if dry else ("live_probe" if live_on else "live_unauthorized")
        write_event(
            cycle_id=cycle_id,
            type="orchestrator.cycle_started",
            agent="orchestrator",
            payload={"mode": mode, "live_probe": live_on},
        )

        self.log("=" * 60)
        self.log("开始新的扫描周期")
        if live_on:
            self.log("🔴 Phase 4 LIVE PROBE 已开启（真实小额下单；见 PA_LIVE_PROBE_* 上限）")
        elif not dry:
            self.log("⚠️  非 dry-run 但未设 PA_LIVE_PROBE=1 — 买入将被 executor 阻断")
        
        try:
            # 第 0 步：美股数据采集（US Stocks Updater）
            self.log("步骤 0/17: 美股数据采集 (US Stocks)")
            self._run_collector("us_stocks_updater")
            self.log("步骤 0.5/17: 大宗商品与汇率采集 (Commodity/Forex)")
            self._run_collector("commodity_forex_collector")
            
            # 第 1 步：数据采集（Agent A）
            self.log("步骤 1/17: 数据采集 (Agent A)")
            self._run_agent("agent_a")

            # 第 1.5 步：记录每市场价格快照（Phase 3b，供 Agent P 波动退出/真实最高水位）
            # 无条件写 data/market_price_history.json 事实源；best-effort，绝不影响主流程。
            self._record_market_prices()

            # 第 2 步：市场状态识别（Regime Detector）
            self.log("步骤 2/16: 市场状态识别 (Regime Detector)")
            self._run_agent("regime_detector")

            # 第 2.5 步：市场情报层（Market Intelligence — Phase 1 Shadow Mode）
            # 仅产出 data/market_intelligence.json 供观察，不被任何下游消费。
            # 任何异常被吞掉，绝不影响主流程。
            try:
                from market_intelligence import safe_run as _mi_safe_run
                _mi_result = _mi_safe_run()
                self.log(f"步骤 2.5/16: 市场情报层 (shadow) — {_mi_result.get('markets_processed', 0)} markets, success={_mi_result.get('success')}")
            except Exception as _mi_exc:
                self.log(f"步骤 2.5/16: 市场情报层 (shadow) FAILED but ignored — {_mi_exc}")

            # 第 3 步：策略管理（Strategy Manager）
            self.log("步骤 3/16: 策略管理 (Strategy Manager)")
            self._run_agent("strategy_manager")
            
            # 第 4 步：资金分配（Capital Adapter）
            self.log("步骤 4/16: 资金分配 (Capital Adapter)")
            self._run_agent("capital_adapter")
            
            # 第 5 步：情报研究（Agent B）
            self.log("步骤 5/16: 情报研究 (Agent B)")
            self._run_agent("agent_b")
            
            # 第 6 步：价值投资（Agent K v2）
            self.log("步骤 6/16: 价值投资 (Agent K v2)")
            self._run_agent("agent_k_v2")
            
            # 第 7 步：无风险套利（Agent D）
            self.log("步骤 7/16: 无风险套利 (Agent D)")
            self._run_agent("agent_d")
            
            # 第 8 步：BTC 套利（Agent E）
            self.log("步骤 8/16: BTC 套利 (Agent E)")
            self._run_agent("agent_e")
            
            # 第 9 步：跨平台套利（Agent F）
            self.log("步骤 9/16: 跨平台套利 (Agent F)")
            self._run_agent("agent_f")
            
            # 第 10 步：钱包跟单（Agent H）
            self.log("步骤 10/16: 钱包跟单 (Agent H)")
            self._run_agent("agent_h")
            
            # 第 11 步：资金费率套利（Agent OKX Funding）
            self.log("步骤 11/16: 资金费率套利 (Agent OKX Funding)")
            self._run_agent("agent_okx_funding")
            
            # 第 12 步：交叉验证（Agent J）
            self.log("步骤 12/16: 交叉验证 (Agent J)")
            self._run_agent("agent_j")
            
            # 步骤 12.5：汇总各 agent 信号到 signals.json（仅当本轮产出>0 才写盘）
            fresh_batch = self._consolidate_signals_for_review()

            # 步骤 12.5b：从信号派生研究假设（Phase 3c，加法、best-effort、不改交易决策）
            try:
                from runtime import hypothesis as _hyp
                _hres = _hyp.generate(base_dir=self.base_dir, cycle_id=cycle_id)
                if _hres.get("generated"):
                    self.log(f"🔬 派生 {_hres['generated']} 条研究假设 (hypotheses)")
            except Exception as _he:
                self.log(f"⚠️  研究假设派生失败（非致命）: {_he}")

            # 步骤 12.6：定量风险引擎（P0 Risk Engine）
            self.log("步骤 12.6/17: 定量风险引擎 (RiskEngine)")
            self._run_risk_engine()

            # 第 13 步：风险审查（Agent M）
            self.log("步骤 13/17: 风险审查 (Agent M)")
            signals_ready, skip_reason = self._signals_ready_for_review()
            # 护栏：本轮 consolidate 未写出新批次 → 禁止 Agent M / 买入（防旧 signals.json
            # 在 2h 窗口内被反复审查+重复执行，堆 open 持仓）。
            if not fresh_batch:
                signals_ready = False
                skip_reason = "no fresh signals this cycle (consolidate produced 0)"
            if signals_ready:
                self._run_agent("agent_m")
                if getattr(self, "_agent_m_ok_this_cycle", None) is False:
                    skip_reason = "agent_m timeout or failure (stale review_results not reused)"
                    signals_ready = False
                    self.log(f"⏭️  跳过 Agent M 后续链路: {skip_reason}")
                    self._write_skipped_review(skip_reason)
                else:
                    usable, review_reason = self._review_results_usable()
                    if not usable:
                        skip_reason = review_reason
                        signals_ready = False
                        self.log(f"⏭️  审查结果不可用: {review_reason}")
                        self._write_skipped_review(review_reason)
            else:
                self.log(f"⏭️  跳过 Agent M: {skip_reason}")
                self._write_skipped_review(skip_reason)
            
            # 步骤 13.5（Phase 3f-loop Fix1）：协整配对原子完整性执行门（env 门控，默认关）。
            # Agent M 审查后、执行前：协整两腿必须同时获批，否则整对丢弃（绝不留裸方向腿）。
            if signals_ready and os.environ.get("PA_COINT_SIGNALS", "").lower() in ("1", "true", "yes"):
                try:
                    from runtime import cointegration as _coint
                    from runtime import datastore as _ds2
                    appr_file = self.data_dir / "approved_signals.json"
                    if appr_file.exists():
                        approved = json.loads(appr_file.read_text())
                        kept, dropped = _coint.enforce_pair_integrity(approved)
                        if dropped:
                            _ds2.put_approved_signals(kept, base_dir=self.base_dir)
                            self.log(f"🔗 配对完整性门：丢弃 {len(dropped)} 条协整裸腿（partner 未获批）")
                except Exception as _pe:
                    self.log(f"⚠️  配对完整性门失败（非致命，跳过）: {_pe}")

            # 第 14 步：信号执行（买入）
            self.log("步骤 14/16: 信号执行（买入）")
            if signals_ready:
                self._execute_signals()
            else:
                self.log(f"⏭️  跳过买入执行: {skip_reason}")
                self._write_skipped_execution_results(skip_reason)
            
            # 第 15 步：持仓管理（Agent P）
            self.log("步骤 15/16: 持仓管理 (Agent P)")
            self._run_agent("agent_p")
            
            # 第 16 步：卖出执行
            self.log("步骤 16/16: 卖出执行")
            self._execute_sell_signals()
            
            # ---- Paper P&L 快照 ----
            try:
                pp = get_paper_portfolio()
                summary = pp.snapshot()
                self.log(f"📊 Paper P&L 快照: {pp.report()}")
            except Exception as e:
                self.log(f"⚠️  Paper P&L 快照失败: {e}")

            # 第 17 步：交易复盘（Agent G）
            self.log("步骤 17/18: 交易复盘 (Agent G)")
            self._run_agent("agent_g")
            
            # 第 18 步：系统监控（Agent I）
            self.log("步骤 18/18: 系统监控 (Agent I)")
            self._run_agent("agent_i")
            
            self.log("✅ 扫描周期完成")

            # 可视化快照刷新（read-only，best-effort，无条件）：dashboard 读 visualization_state.json，
            # 此前因不在 pipeline 而 stale；接回周期末保持新鲜。任何失败都不影响周期。
            try:
                from agents.agent_visualization import build_state, OUTPUT_PATH
                import json as _json
                OUTPUT_PATH.write_text(
                    _json.dumps(build_state(), indent=2, ensure_ascii=False), encoding="utf-8"
                )
                self.log("🖼️  可视化快照已刷新 (visualization_state.json)")
            except Exception as _ve:
                self.log(f"⚠️  可视化快照刷新失败（非致命）: {_ve}")

            # 影子库刷新（Phase 1）：只读本周期已落盘的 json，回填 SQLite 影子库。
            # 仅当 PA_SHADOW_DB=1 时生效；best-effort，任何失败都不影响周期成功。
            # 不改任何 json 写入路径——零行为变化，dry-run 链路完全不经过 DB。
            if os.environ.get("PA_SHADOW_DB", "").lower() in ("1", "true", "yes"):
                try:
                    from runtime import ingest as _ingest
                    _ingest.backfill()
                    self.log("🗃️  影子库已刷新 (runtime.db)")
                    # Phase 3a：逐笔复盘（确定性，best-effort，加法产物，不改交易行为）
                    from runtime import postmortem as _pm
                    _pmres = _pm.generate(base_dir=self.base_dir)
                    if _pmres.get("generated"):
                        self.log(f"🧾 新增 {_pmres['generated']} 笔复盘 (postmortems)")
                    # Phase 3e：复盘之后重算模型/规则有效性（确定性，加法，不改交易行为）
                    from runtime import model_effectiveness as _me
                    _mer = _me.compute(base_dir=self.base_dir)
                    self.log(f"📊 模型有效性已刷新 (model_effectiveness)：{_mer.get('n_postmortems',0)} 笔复盘")
                    # Phase 3e-2：从有效性派生规则权重建议（仅建议产物 enforced=False，不接入交易链路）
                    from runtime import rule_weights as _rw
                    _rwr = _rw.compute(base_dir=self.base_dir)
                    _rc = _rwr.get("summary", {}).get("retire_candidates", [])
                    self.log(f"⚖️  规则权重建议已刷新 (rule_effectiveness)：retire_candidates={len(_rc)}")
                    # Phase 3f：协整/spread 研究模型（真实 models_used；研究产物 enforced=False，不接入交易链路）
                    from runtime import cointegration as _coint
                    _cr = _coint.compute(base_dir=self.base_dir)
                    self.log(f"🔗 协整研究已刷新 (correlation_signals)：候选={_cr.get('n_candidates',0)} / 评估对={_cr.get('n_pairs_evaluated',0)}")
                    # Phase 3g：HMM 市场状态识别（真实 models_used=hmm；研究产物 enforced=False，不接入交易链路）
                    from runtime import regime_hmm as _hmm
                    _hr = _hmm.compute(base_dir=self.base_dir)
                    self.log(f"🌀 regime 识别已刷新 (regime_states)：regimes={_hr.get('n_regimes',0)} / turbulent={_hr.get('n_turbulent',0)} / shift={_hr.get('n_regime_shift',0)}")
                    # Phase 3g-loop：regime 有效性学习（postmortems × regime；学习产物 enforced=False，numpy-free）
                    from runtime import regime_effectiveness as _re
                    _rer = _re.compute(base_dir=self.base_dir)
                    self.log(f"🎯 regime 有效性已刷新 (regime_effectiveness)：匹配={_rer.get('n_regime_matched',0)}/{_rer.get('n_postmortems',0)} 笔")
                    # Phase 3h：GARCH 波动率聚集（真实 models_used=garch；研究产物 enforced=False，不接入交易链路）
                    from runtime import garch as _garch
                    _gr = _garch.compute(base_dir=self.base_dir)
                    self.log(f"📈 波动率识别已刷新 (volatility_states)：states={_gr.get('n_states',0)} / elevated={_gr.get('n_elevated',0)} / clustering={_gr.get('n_clustering',0)}")
                    # Phase 3i：Kelly+Markowitz 仓位建议（cointegration 边 × GARCH 方差 × regime；建议产物 enforced=False，不接入仓位）
                    from runtime import position_sizing as _ps
                    _psr = _ps.compute(base_dir=self.base_dir)
                    self.log(f"📐 仓位建议已刷新 (sizing_suggestions)：建议={_psr.get('n_suggestions',0)} / GARCH方差={_psr.get('n_var_from_garch',0)}")
                except Exception as _e:
                    self.log(f"⚠️  影子库刷新失败（非致命）: {_e}")

            write_event(
                cycle_id=cycle_id,
                type="orchestrator.cycle_completed",
                agent="orchestrator",
                payload={"status": "success"},
            )
        
        except Exception as e:
            self.log(f"❌ 扫描周期失败: {e}")
            write_event(
                cycle_id=cycle_id,
                type="orchestrator.cycle_completed",
                agent="orchestrator",
                payload={"status": "failed", "error": str(e)},
            )
        finally:
            self._release_run_lock()

    def _write_status_from_log(self, message, timestamp):
        """Persist a compact heartbeat for external monitors and bots."""
        try:
            previous = {}
            if self.status_file.exists():
                try:
                    previous = json.loads(self.status_file.read_text())
                except Exception:
                    previous = {}

            state = previous.get("state", "running")
            current_step = previous.get("current_step")
            if message == "开始新的扫描周期":
                state = "running"
                current_step = None
            elif message.startswith("步骤 "):
                state = "running"
                current_step = message
            elif "扫描周期完成" in message:
                state = "completed"
            elif "扫描周期失败" in message:
                state = "failed"
            elif "已有扫描周期在运行" in message:
                state = "skipped_locked"

            payload = {
                "state": state,
                "pid": os.getpid(),
                "updated_at": datetime.now().isoformat(),
                "log_timestamp": timestamp,
                "current_step": current_step,
                "last_log": message,
            }
            # Phase 0 写入收敛：经 datastore 门面写 orchestrator_status.json
            from runtime import datastore as _ds
            _ds.write_status(payload, base_dir=self.base_dir)
        except Exception:
            pass

    def _record_market_prices(self):
        """Phase 3b：把本周期 latest_data.polymarket_markets 的价格快照记入历史。

        无条件写 data/market_price_history.json（agent_p 读的事实源）+ 影子表（PA_SHADOW_DB 时）。
        best-effort：任何异常只记日志，绝不影响周期。
        """
        try:
            latest = self.data_dir / "latest_data.json"
            if not latest.exists():
                return
            data = json.loads(latest.read_text())
            ts = data.get("timestamp")
            points = []
            for m in data.get("polymarket_markets", []) or []:
                prices = m.get("outcome_prices") or []
                yes_p = prices[0] if len(prices) > 0 else None
                no_p = prices[1] if len(prices) > 1 else None
                points.append({
                    "market_id": m.get("id"), "slug": m.get("slug"), "ts": ts,
                    "yes_price": yes_p, "no_price": no_p, "liquidity": m.get("liquidity"),
                })
            if points:
                from runtime import datastore as _ds
                _ds.record_market_prices(points, base_dir=self.base_dir)
                self.log(f"💹 记录 {len(points)} 个市场价格快照")

            # Phase 3f-x：外部资产价格快照（加密/美股/宏观）→ asset_price_history.json，
            # 供跨资产协整（PRD §9：BTC→Polymarket 概率）。无条件 best-effort。
            asset_points = []
            for c in (data.get("okx", {}) or {}).get("data", []) or []:
                if c.get("symbol") and c.get("spot_price") is not None:
                    asset_points.append({"symbol": c["symbol"], "ts": ts,
                                         "price": c["spot_price"], "kind": "crypto"})
            for s in (data.get("us_stocks", {}) or {}).get("stocks", []) or []:
                if s.get("symbol") and s.get("price") is not None:
                    asset_points.append({"symbol": s["symbol"], "ts": ts,
                                         "price": s["price"], "kind": "us_stock"})
            if data.get("btc_funding_rate") is not None:
                asset_points.append({"symbol": "BTC_FUNDING", "ts": ts,
                                     "price": data["btc_funding_rate"], "kind": "macro"})
            if asset_points:
                from runtime import datastore as _ds
                _ds.record_asset_prices(asset_points, base_dir=self.base_dir)
                self.log(f"💱 记录 {len(asset_points)} 个外部资产价格快照")
        except Exception as _e:
            self.log(f"⚠️  价格快照记录失败（非致命）: {_e}")

    def _acquire_run_lock(self):
        """Prevent overlapping runs from cron, Hermes, VS Code, or manual shells."""
        if fcntl is None:
            return True
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_file, "w")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False

        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\nstarted_at={datetime.now().isoformat()}\n")
        handle.flush()
        self._lock_handle = handle
        return True

    def _release_run_lock(self):
        if not self._lock_handle or fcntl is None:
            return
        try:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._lock_handle.close()
            self._lock_handle = None

    def _bootstrap_runtime_files(self):
        """Create minimal runtime files that downstream agents expect."""
        positions_file = self.data_dir / "positions.json"
        if not positions_file.exists():
            with open(positions_file, "w") as f:
                json.dump([], f, indent=2, ensure_ascii=False)

    def _run_risk_engine(self):
        """P0: 运行定量风险引擎，生成 data/risk_snapshot.json"""
        try:
            from risk.risk_engine import RiskEngine
            engine = RiskEngine(self.base_dir)
            output = engine.run()
            self.log(f"✅ RiskEngine 快照已生成: {output}")
        except Exception as e:
            self.log(f"⚠️  RiskEngine 执行失败（不中断流水线）: {e}")

    def _signal_max_age_seconds(self):
        raw_value = os.environ.get("SIGNAL_MAX_AGE_SECONDS", str(SIGNAL_MAX_AGE_SECONDS))
        try:
            return max(0, int(raw_value))
        except ValueError:
            return SIGNAL_MAX_AGE_SECONDS

    def _parse_signal_time(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None

    def _signals_ready_for_review(self):
        """Fail closed when the signal batch is empty, invalid, or stale."""
        signals_file = self.data_dir / "signals.json"
        if not signals_file.exists():
            return False, "signals.json missing"

        try:
            with open(signals_file, "r") as f:
                signals = json.load(f)
        except Exception as exc:
            return False, f"signals.json unreadable: {exc}"

        if not isinstance(signals, list):
            return False, f"signals.json schema is {type(signals).__name__}, expected list"
        if not signals:
            return False, "signals.json has no signals"

        missing_time_count = 0
        signal_times = []
        for signal in signals:
            if not isinstance(signal, dict):
                return False, "signals.json contains non-object signal"
            parsed = self._parse_signal_time(signal.get("generated_at") or signal.get("timestamp"))
            if parsed is None:
                missing_time_count += 1
            else:
                signal_times.append(parsed)

        if missing_time_count:
            return False, f"signals missing generated_at: count={missing_time_count}"

        newest_signal_ts = max(signal_times)
        age_seconds = datetime.now().timestamp() - newest_signal_ts
        max_age = self._signal_max_age_seconds()

        if age_seconds > max_age:
            return (
                False,
                f"signals stale: age={int(age_seconds)}s exceeds max_age={max_age}s",
            )

        return True, "signals fresh"

    def _review_results_usable(self):
        """Reject partial or stale-cycle review_results before execution."""
        review_file = self.data_dir / "review_results.json"
        if not review_file.exists():
            return False, "review_results.json missing"

        try:
            review = json.loads(review_file.read_text())
        except Exception as exc:
            return False, f"review_results unreadable: {exc}"

        if review.get("partial"):
            return False, "review_results partial=true (incomplete review batch)"

        cycle_id = getattr(self, "_current_cycle_id", "")
        review_cycle = str(review.get("generated_cycle_id") or "")
        if cycle_id and review_cycle and review_cycle != cycle_id:
            return (
                False,
                f"review_results cycle mismatch: expected={cycle_id} got={review_cycle}",
            )

        return True, "review_results fresh"

    def _consolidate_signals_for_review(self) -> bool:
        """把各 agent 本轮产出的信号汇总到 signals.json，供 Agent M 审查。
        各 agent 输出格式不统一，这里做 schema 归一化。
        Agent B 来自 intelligence_report；D/E/F/H/J/K 来自本轮 append 的 signals.json。
        返回 True 仅当本轮写出非空批次；False 时 signals.json 保持不变。
        """
        now = datetime.now().isoformat()
        cycle_id = getattr(self, "_current_cycle_id", "") or now
        b_signals = []
        stale_b_signals_skipped = 0
        agent_b_ok = getattr(self, "_agent_b_ok_this_cycle", None)

        # --- Agent B: intelligence_report.json（仅当本轮 B 成功完成）---
        intel_file = self.data_dir / "intelligence_report.json"
        if agent_b_ok is False:
            if intel_file.exists():
                try:
                    intel = json.loads(intel_file.read_text())
                    raw_list = intel.get("signals", []) if isinstance(intel, dict) else intel
                    stale_b_signals_skipped = sum(1 for s in raw_list if isinstance(s, dict))
                except Exception:
                    pass
            self.log(
                f"⏭️ Agent B timeout: current_cycle_b_signals=0 "
                f"stale_b_signals_skipped={stale_b_signals_skipped}"
            )
        elif intel_file.exists():
            try:
                intel = json.loads(intel_file.read_text())
                # intel 可能是 {"signals": [...]} 或直接 [...]
                raw_list = intel.get("signals", []) if isinstance(intel, dict) else intel
                # 尝试找市场名称映射（用 latest_data.json）
                market_name_map = {}
                latest = self.data_dir / "latest_data.json"
                if latest.exists():
                    ld = json.loads(latest.read_text())
                    for m in ld.get("polymarket_markets", ld.get("markets", [])):
                        slug = m.get("slug", "")
                        qid = m.get("id", "")
                        name = m.get("question", "")
                        if slug:
                            market_name_map[slug] = (qid or slug, name)

                for sig in raw_list:
                    if not isinstance(sig, dict):
                        continue
                    slug = sig.get("market_slug", "")
                    mid, mname = market_name_map.get(slug, (slug, slug))
                    side = sig.get("side", "")
                    direction = "NO" if "no" in side.lower() else "YES"
                    generated_at = sig.get("generated_at", now)
                    normalized = {
                        "market_id": mid,
                        "market_name": mname,
                        "market": mname,
                        "market_slug": slug,
                        "direction": direction,
                        "price": sig.get("price", 0.5),
                        "position_size": sig.get("position_size", 0.02 if sig.get("probe") else 0.1),
                        "expected_value": sig.get("ev", sig.get("expected_value", 0)),
                        "confidence": sig.get("confidence", 70),
                        "source": "agent_b",
                        "source_agent": "agent_b",
                        "signal_origin": "intelligence_report",
                        "generated_cycle_id": cycle_id,
                        "signal_merge_reason": "agent_b_primary",
                        "generated_at": generated_at,
                        "timestamp": generated_at,
                    }
                    for field in (
                        "data_sources",
                        "logic_chain",
                        "risk_notes",
                        "market_evidence",
                        "learned_rule_match",
                        "reason",
                        # Phase 3c-2：透传 Agent B 原生研究假设字段到 signals.json，
                        # 供 hypothesis 提取器优先采用（source derived→agent_b）。
                        "holding_horizon_days",
                        "failure_conditions",
                        # Agent B paper_probe 可解释字段（加法透传，不改汇总流程）
                        "probe",
                        "models_used",
                        "source_markets",
                        "evidence",
                        "tier",
                    ):
                        if field in sig:
                            normalized[field] = sig[field]
                    b_signals.append(normalized)
                self.log(f"📡 current_cycle_b_signals={len(b_signals)}")
            except Exception as e:
                self.log(f"⚠️  读取 intelligence_report.json 失败: {e}")

        # --- D/E/F/H/J/K: 本轮 append 到 signals.json 的非 B 信号（fresh + cycle_id）---
        file_signals = []
        signals_path = self.data_dir / "signals.json"
        if signals_path.exists():
            try:
                raw_file = json.loads(signals_path.read_text())
                if isinstance(raw_file, list):
                    file_signals = raw_file
            except Exception as e:
                self.log(f"⚠️  读取 signals.json 用于 merge 失败: {e}")

        from runtime import signal_merge as _sm
        max_total = max(1, int(os.environ.get("SIGNAL_MERGE_MAX_TOTAL", "20")))
        max_per = max(1, int(os.environ.get("SIGNAL_MERGE_MAX_PER_AGENT", "3")))
        fresh_signals = _sm.consolidate_merge(
            b_signals,
            file_signals,
            max_age_seconds=self._signal_max_age_seconds(),
            max_total=max_total,
            max_per_non_b_agent=max_per,
            cycle_id=cycle_id,
        )
        n_b = sum(1 for s in fresh_signals if _sm.is_agent_b_signal(s))
        n_other = len(fresh_signals) - n_b
        if n_other:
            self.log(f"🔀 信号 merge: B={n_b} 非B={n_other} (cap total={max_total}, per_agent={max_per})")

        # Phase 3f-loop：env 门控的协整→信号桥（默认关）。
        # PA_COINT_SIGNALS=1 时把协整研究候选作为带 models_used 的小仓位 probe 信号合入信号链路，
        # 端到端流经 review→execute→postmortem→model_effectiveness（真实模型可学习）。
        # ⚠ 这些是可成交信号：仅应在 EXECUTOR_DRY_RUN=1 的受控验证下开启。
        if os.environ.get("PA_COINT_SIGNALS", "").lower() in ("1", "true", "yes"):
            try:
                from runtime import cointegration as _coint
                _rep = _coint.find_candidates(self.base_dir)
                _meta = {}
                latest = self.data_dir / "latest_data.json"
                if latest.exists():
                    _meta = _coint.market_meta_from_latest(json.loads(latest.read_text()))
                _csigs = _coint.to_pipeline_signals(_rep, _meta)
                if _csigs:
                    for _cs in _csigs:
                        _cs.setdefault("source_agent", _cs.get("source", "cointegration"))
                        _cs.setdefault("signal_origin", "cointegration_bridge")
                        _cs.setdefault("generated_cycle_id", cycle_id)
                        _cs.setdefault("signal_merge_reason", "cointegration_env_gate")
                    coint_cap = max(0, int(os.environ.get("PA_COINT_SIGNAL_CAP", "8")))
                    _csigs, _cstats = _sm.cap_cointegration_probe_signals(_csigs, cap=coint_cap)
                    fresh_signals.extend(_csigs)
                    self.log(
                        f"🔗 协整桥 cap: candidate_total={_cstats['candidate_total']} "
                        f"selected={_cstats['selected']} dropped={_cstats['dropped']} "
                        f"cap={_cstats['cap']}"
                    )
            except Exception as _ce:
                self.log(f"⚠️  协整信号桥失败（非致命，跳过）: {_ce}")

        if fresh_signals:
            before_cap = len(fresh_signals)
            fresh_signals = _sm.apply_max_total_cap(fresh_signals, max_total)
            if len(fresh_signals) < before_cap:
                self.log(
                    f"✂️  信号总量 cap: {before_cap} → {len(fresh_signals)} (max_total={max_total})"
                )

        if not fresh_signals:
            self.log("⚠️  本轮无新信号，signals.json 不更新")
            return False

        # Phase 5：纸面强制层（env 门控 PA_ENFORCE_SIZING/PA_ENFORCE_WEIGHTS，默认全关）。
        # 把学习产物（rule_weights / sizing_suggestions）反馈回信号 position_size：
        # 门控关 → 恒等（零回归）；开 → 只降险 + 不归零探针，仍受 Agent M / dry-run 护栏。
        try:
            from runtime import enforcement as _enf
            if _enf.any_enabled():
                fresh_signals, _erep = _enf.enforce_signals(fresh_signals, base_dir=self.base_dir)
                self.log(
                    f"⚖️  纸面强制层：调整 {_erep.get('applied_count', 0)}/{len(fresh_signals)} 条信号 "
                    f"(sizing={_erep.get('n_sizing_applied', 0)}, weight={_erep.get('n_weight_applied', 0)})")
        except Exception as _ee:
            self.log(f"⚠️  纸面强制层失败（非致命，按原始信号继续）: {_ee}")

        # 写入 signals.json（完整替换，不追加旧信号）—— Phase 0 写入收敛，经 datastore 门面
        from runtime import datastore as _ds
        _ds.put_signals("orchestrator_consolidate", fresh_signals, base_dir=self.base_dir)
        self.log(f"✅ 汇总 {len(fresh_signals)} 个新信号到 signals.json")
        return True

    def _write_skipped_review(self, reason):
        timestamp = datetime.now().isoformat()
        review_file = self.data_dir / "review_results.json"
        approved_file = self.data_dir / "approved_signals.json"
        review = {
            "timestamp": timestamp,
            "status": "skipped",
            "reason": reason,
            "total": 0,
            "approved": 0,
            "rejected": 0,
            "approved_signals": [],
            "rejected_signals": [],
            "cache_stats": {"hits": 0, "misses": 0, "hit_rate": "0%"},
        }
        # Phase 0 写入收敛：经 datastore 门面写 review_results + approved_signals（[]）
        from runtime import datastore as _ds
        _ds.put_review("orchestrator_skipped", review, approved_signals=[], base_dir=self.base_dir)

    def _write_skipped_execution_results(self, reason):
        output = {
            "timestamp": datetime.now().isoformat(),
            "status": "skipped",
            "reason": reason,
            "total": 0,
            "success": 0,
            "dry_run": 0,
            "simulated": 0,
            "failed": 0,
            "results": [],
        }
        # Phase 0 写入收敛：经 datastore 门面写 execution_results.json
        from runtime import datastore as _ds
        _ds.record_executions("orchestrator_skipped", output, side="BUY", base_dir=self.base_dir)
    
    def _run_agent(self, agent_name):
        """运行单个 Agent；返回 True 仅当子进程在时限内且 exit 0。"""
        agent_file = self.base_dir / "agents" / f"{agent_name}.py"
        ok = False

        if not agent_file.exists():
            self.log(f"⚠️  Agent 文件不存在: {agent_file}")
            if agent_name == "agent_b":
                self._agent_b_ok_this_cycle = False
            elif agent_name == "agent_m":
                self._agent_m_ok_this_cycle = False
            return ok

        # agent_m 并发审查多信号，需长于单条 LLM；agent_f 多市场串行 LLM
        if agent_name == "agent_m":
            timeout = 600
        elif agent_name == "agent_f":
            timeout = 180
        elif agent_name in ("regime_detector", "capital_adapter"):
            timeout = 150
        else:
            timeout = 120

        env = os.environ.copy()
        cycle_id = getattr(self, "_current_cycle_id", "")
        if cycle_id:
            env["PA_CYCLE_ID"] = cycle_id

        try:
            import subprocess
            result = subprocess.run(
                [PYTHON_BIN, str(agent_file)],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

            ok = result.returncode == 0
            if ok:
                self.log(f"✅ {agent_name} 执行成功")
            else:
                self.log(f"❌ {agent_name} 执行失败: {result.stderr}")

        except subprocess.TimeoutExpired:
            self.log(f"⏱️  {agent_name} 执行超时")
            ok = False
        except Exception as e:
            self.log(f"❌ {agent_name} 执行异常: {e}")
            ok = False

        if agent_name == "agent_b":
            self._agent_b_ok_this_cycle = ok
        elif agent_name == "agent_m":
            self._agent_m_ok_this_cycle = ok
        return ok
    
    def _run_collector(self, collector_name):
        """运行数据采集器"""
        try:
            import subprocess
            
            collector_file = self.base_dir / "collectors" / f"{collector_name}.py"
            if collector_file.exists():
                result = subprocess.run(
                    [PYTHON_BIN, str(collector_file)],
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    self.log(f"✅ {collector_name} 执行成功")
                else:
                    self.log(f"❌ {collector_name} 执行失败: {result.stderr}")
            else:
                self.log(f"⚠️  {collector_name} 不存在")
        
        except subprocess.TimeoutExpired:
            self.log(f"⏱️  {collector_name} 执行超时")
        except Exception as e:
            self.log(f"❌ {collector_name} 执行异常: {e}")
    
    def _is_stop_trading_active(self):
        """检查 STOP_TRADING 文件是否存在（不抛出异常）。"""
        try:
            stop_file = self.data_dir / "STOP_TRADING"
            if stop_file.exists():
                content = stop_file.read_text()[:120].strip()
                self.log(f"🛑 STOP_TRADING 激活: {content}")
                return True
        except Exception as e:
            self.log(f"⚠️  STOP_TRADING 检查异常: {e}")
        return False

    def _execute_signals(self):
        """执行买入信号"""
        # STOP_TRADING 护栏：dry-run 继续，真实交易被阻断
        if self._is_stop_trading_active():
            dry_run = os.environ.get("EXECUTOR_DRY_RUN", "").lower() in ("1", "true", "yes")
            if dry_run:
                self.log("⚠️  STOP_TRADING active，但 DRY_RUN 模式继续")
            else:
                self.log("🛑 买入执行已被 STOP_TRADING 阻断，跳过")
                self._write_skipped_execution_results("STOP_TRADING active")
                return
        try:
            import subprocess

            executor_file = self.base_dir / "signal_executor.py"
            if executor_file.exists():
                env = os.environ.copy()
                cycle_id = getattr(self, "_current_cycle_id", "")
                if cycle_id:
                    env["PA_CYCLE_ID"] = cycle_id
                result = subprocess.run(
                    [PYTHON_BIN, str(executor_file)],
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env=env,
                )
                
                if result.returncode == 0:
                    self.log("✅ 买入信号执行完成")
                else:
                    self.log(f"⚠️  买入信号执行失败: {result.stderr}")
            else:
                self.log("⚠️  买入执行器不存在")
            
        except Exception as e:
            self.log(f"❌ 买入信号执行异常: {e}")
    
    def _execute_sell_signals(self):
        """执行卖出信号（STOP_TRADING 时 sell_executor 仍放行 urgent 止损）。"""
        if self._is_stop_trading_active():
            dry_run = os.environ.get("EXECUTOR_DRY_RUN", "").lower() in ("1", "true", "yes")
            if dry_run:
                self.log("⚠️  STOP_TRADING active（dry-run 继续）")
            else:
                self.log("🛑 STOP_TRADING active — 仅 urgent 止损卖单可执行")
        try:
            import subprocess

            sell_executor_file = self.base_dir / "sell_executor.py"
            if sell_executor_file.exists():
                result = subprocess.run(
                    [PYTHON_BIN, str(sell_executor_file)],
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    self.log("✅ 卖出执行完成")
                else:
                    self.log(f"⚠️  卖出执行失败: {result.stderr}")
            else:
                self.log("⚠️  卖出执行器不存在")
        
        except Exception as e:
            self.log(f"❌ 卖出执行异常: {e}")
    
    def _generate_report(self):
        """生成周期报告"""
        try:
            import subprocess
            
            # 获取账户余额
            config_file = self.base_dir / "config" / "system_config.json"
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            result = subprocess.run(
                [get_pm_trader(), "balance"],
                capture_output=True,
                text=True,
                timeout=30,
                env=get_pm_trader_env()
            )
            
            if result.returncode == 0:
                balance_data = json.loads(result.stdout)
                if balance_data.get("ok"):
                    data = balance_data.get("data", {})
                    self.log(f"💰 账户余额: ${data.get('total_value', 0):.2f}")
                    self.log(f"📊 盈亏: ${data.get('pnl', 0):.2f}")
        
        except Exception as e:
            self.log(f"⚠️  生成报告失败: {e}")

def main():
    orchestrator = Orchestrator()
    orchestrator.run_once()

if __name__ == "__main__":
    main()
