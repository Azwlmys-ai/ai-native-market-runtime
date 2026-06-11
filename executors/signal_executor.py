"""
Signal Executor - 执行层买入
职责：执行通过审查的交易信号
"""

import json
import os
import subprocess
from pathlib import Path
from datetime import datetime, timezone
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir, get_pm_trader, get_pm_trader_env
from event_logger import write_event
from paper_pnl import get_paper_portfolio
from runtime import live_probe as _live

class SignalExecutor:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)

        # 组合作用域：生产（base_dir=None）走全局单例，行为不变；显式传 base_dir
        # （如测试 tmp）作用域到该目录 → 去重/开仓不再泄漏到真实全局组合。
        # 在**调用时**经 get_paper_portfolio 解析（而非 init 时缓存），以兼容测试对该函数的 patch。
        self._scoped_base = Path(base_dir) if base_dir else None

        self.trader_path = get_pm_trader()

    def _get_portfolio(self):
        """调用时解析 PaperPortfolio：生产=全局单例；显式 base_dir=该目录作用域实例。"""
        return get_paper_portfolio(self._scoped_base)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [Signal Executor] {message}")

    def _write_paper_trade(self, signal: dict, cycle_id: str) -> None:
        trade = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "cycle_id": cycle_id,
            "market_id": signal.get("market_id", ""),
            "market_slug": signal.get("market_slug") or signal.get("slug") or "",
            "market": signal.get("market", ""),
            "market_name": signal.get("market_name", ""),
            "side": signal.get("direction", ""),
            "entry_price": float(signal.get("price", 0) or 0),
            "size": float(signal.get("position_size", 0) or 0),
            "source_agent": signal.get("source", ""),
            "execution_type": "paper",
        }
        # Phase 0 写入收敛：经 runtime.datastore 门面 append（行格式不变）
        from runtime import datastore as _ds
        _ds.append_paper_trade(trade, base_dir=self.base_dir)
    
    def _has_open_position(self, signal: dict) -> bool:
        """同 market_id/slug + direction 已有未平仓 → 跳过，防每周期重复 dry-run 开仓。"""
        mid = str(signal.get("market_id") or "").strip()
        slug = str(
            signal.get("market_slug")
            or signal.get("slug")
            or signal.get("market_evidence", {}).get("market_slug")
            or ""
        ).strip()
        direction = (signal.get("direction") or "").upper()
        if not direction:
            self.log("⚠️  dedup 检查跳过：signal 无 direction")
            return False
        if not mid and not slug:
            self.log("⚠️  dedup 检查跳过：signal 无 market_id/slug")
            return False
        try:
            for pos in self._get_portfolio().get_open_positions():
                pos_mid = str(pos.market_id or "").strip()
                pos_slug = str(pos.market_slug or pos.slug or "").strip()
                pos_dir = (pos.direction or "").upper()
                if pos_dir != direction:
                    continue
                if mid and pos_mid and mid == pos_mid:
                    return True
                if slug and pos_slug and slug == pos_slug:
                    return True
        except Exception as exc:
            self.log(f"❌ dedup 检查异常（不静默放行）: {exc}")
            raise
        return False

    def load_approved_signals(self):
        """加载通过审查的信号（拒绝 partial / 跨周期 stale review_results）。"""
        review_file = self.data_dir / "review_results.json"
        if review_file.exists():
            try:
                review = json.loads(review_file.read_text())
                if review.get("partial"):
                    self.log("⚠️  review_results partial=true，跳过执行（防超时误用旧批次）")
                    return []
                cycle_id = os.environ.get("PA_CYCLE_ID", "")
                review_cycle = str(review.get("generated_cycle_id") or "")
                if cycle_id and review_cycle and review_cycle != cycle_id:
                    self.log(
                        f"⚠️  review_results cycle mismatch "
                        f"(expected={cycle_id} got={review_cycle})，跳过执行"
                    )
                    return []
            except Exception as exc:
                self.log(f"⚠️  读取 review_results 失败: {exc}")

        approved_file = self.data_dir / "approved_signals.json"

        if not approved_file.exists():
            self.log("❌ approved_signals.json 不存在")
            return []

        try:
            with open(approved_file, "r") as f:
                signals = json.load(f)

            return signals

        except Exception as e:
            self.log(f"❌ 加载审查通过的信号失败: {e}")
            return []
    
    def execute_trade(self, signal, *, live_prechecked: bool = False, live_order_usd: float = 0.0):
        """执行单个交易"""
        market_id = signal.get("market_id")
        market_name = signal.get("market_name", "Unknown")
        direction = signal.get("direction")
        price = signal.get("price")
        position_size = signal.get("position_size", 0.10)
        cfg = _live.gates()
        account_balance = cfg["account_balance"]
        amount = int(live_order_usd) if live_prechecked and live_order_usd > 0 else int(account_balance * position_size)
        if live_prechecked and live_order_usd > 0:
            amount = max(1, min(amount, int(cfg["max_usd"])))
        
        self.log(f"执行交易: {market_name[:60]}")
        self.log(f"  Market ID: {market_id}")
        self.log(f"  方向: {direction}, 金额: ${amount}, 价格: {price}")

        if os.environ.get("EXECUTOR_DRY_RUN", "").lower() in ("1", "true", "yes"):
            self.log(f"[DRY_RUN] would execute: {market_id} {direction} size={position_size}")
            cycle_id = os.environ.get("PA_CYCLE_ID", f"exec_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}")
            write_event(
                cycle_id=cycle_id,
                type="execution.dry_run",
                agent="signal_executor",
                payload={
                    "market_id": signal.get("market_id", ""),
                    "market_name": signal.get("market_name", ""),
                    "direction": signal.get("direction", ""),
                    "position_size": position_size,
                    "source": signal.get("source", ""),
                },
            )
            self._write_paper_trade(signal, cycle_id)
            # 记录虚拟持仓到 PaperPortfolio
            try:
                pp = self._get_portfolio()
                pp.open_position(signal)
            except Exception as e:
                self.log(f"⚠️ paper_pnl 记录失败: {e}")
            return {
                "status": "dry_run",
                "signal": signal,
                "timestamp": datetime.now().isoformat()
            }

        # Phase 4：无 PA_LIVE_PROBE 授权 → 绝不真实下单（防误关 DRY_RUN）
        if not _live.live_enabled(cfg):
            self.log("🛑 未授权 live probe（需 PA_LIVE_PROBE=1 且非 DRY_RUN），跳过真实下单")
            return {
                "status": "blocked_no_live_gate",
                "signal": signal,
                "error": "PA_LIVE_PROBE not enabled",
                "timestamp": datetime.now().isoformat(),
            }
        
        try:
            # 使用 pm-trader 执行交易
            cmd = [
                self.trader_path,
                "buy",
                market_id,
                direction,
                str(amount)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=get_pm_trader_env()
            )
            
            if result.returncode == 0:
                self.log(f"✅ 交易成功 (live probe)")
                cycle_id = os.environ.get("PA_CYCLE_ID", "")
                if live_prechecked and live_order_usd > 0:
                    _live.commit_live_buy(live_order_usd, signal, base_dir=self.base_dir, cycle_id=cycle_id)
                return {
                    "status": "success",
                    "signal": signal,
                    "output": result.stdout,
                    "live_probe": True,
                    "order_usd": live_order_usd or amount,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                self.log(f"❌ 交易失败: {result.stderr}")
                return {
                    "status": "failed",
                    "signal": signal,
                    "error": result.stderr,
                    "timestamp": datetime.now().isoformat()
                }
        
        except subprocess.TimeoutExpired:
            self.log(f"❌ 交易超时")
            return {
                "status": "timeout",
                "signal": signal,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            self.log(f"❌ 交易异常: {e}")
            return {
                "status": "error",
                "signal": signal,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def execute_signal(self, signal_data):
        """兼容旧根目录执行器的嵌套 review_results.json schema"""
        return self.execute_trade(signal_data.get("signal", signal_data))

    def _write_execution_results(
        self,
        total,
        success_count,
        dry_run_count,
        simulated_count,
        failed_count,
        results,
    ):
        output = {
            "timestamp": datetime.now().isoformat(),
            "total": total,
            "success": success_count,
            "dry_run": dry_run_count,
            "simulated": simulated_count,
            "failed": failed_count,
            "results": results
        }

        # Phase 0 写入收敛：经 runtime.datastore 门面（json 输出不变）
        from runtime import datastore as _ds
        _ds.record_executions(output.get("timestamp") or "signal_executor", output,
                              side="BUY", base_dir=self.base_dir)
        return self.data_dir / "execution_results.json"
    
    def run(self):
        """执行所有通过审查的信号"""
        self.log("=" * 60)
        self.log("开始执行交易信号...")
        
        signals = self.load_approved_signals()
        
        if not signals:
            self.log("ℹ️  无待执行信号")
            cycle_id = os.environ.get("PA_CYCLE_ID", f"exec_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}")
            write_event(
                cycle_id=cycle_id,
                type="execution.skipped",
                agent="signal_executor",
                payload={"reason": "no_signals"},
            )
            output_file = self._write_execution_results(
                total=0,
                success_count=0,
                dry_run_count=0,
                simulated_count=0,
                failed_count=0,
                results=[],
            )
            self.log(f"结果已保存到 {output_file}")
            self.log("=" * 60)
            return
        
        self.log(f"📊 发现 {len(signals)} 个待执行信号")
        
        results = []
        success_count = 0
        dry_run_count = 0
        simulated_count = 0
        failed_count = 0
        
        skipped_dup = 0
        blocked_live = 0
        cycle_id = os.environ.get("PA_CYCLE_ID", f"exec_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}")
        live_cfg = _live.gates()
        live_audit = []

        work_signals = signals
        live_usd_by_key: dict[str, float] = {}
        if _live.live_enabled(live_cfg):
            work_signals, live_audit = _live.filter_signals_for_live(
                signals, cycle_id=cycle_id, base_dir=self.base_dir, cfg=live_cfg,
            )
            blocked_live = len(signals) - len(work_signals)
            for entry in live_audit:
                if entry.get("allowed"):
                    key = f"{entry.get('market_id')}|{entry.get('source')}"
                    live_usd_by_key[key] = float(entry.get("order_usd") or 0)
            if blocked_live:
                self.log(f"⚖️  live probe 门控：放行 {len(work_signals)}/{len(signals)} 条")
            _live.write_audit(_live.build_cycle_report(
                phase="buy_filter",
                allowed=[a for a in live_audit if a.get("allowed")],
                blocked=[a for a in live_audit if not a.get("allowed")],
                cfg=live_cfg,
            ), base_dir=self.base_dir)

        for i, signal in enumerate(work_signals, 1):
            self.log(f"\n[{i}/{len(work_signals)}]")
            if self._has_open_position(signal):
                mid = signal.get("market_id", "")
                direction = signal.get("direction", "")
                self.log(f"⏭️  跳过重复开仓: {mid} {direction}（已有 open 持仓）")
                results.append({
                    "status": "skipped_duplicate",
                    "signal": signal,
                    "timestamp": datetime.now().isoformat(),
                })
                skipped_dup += 1
                continue

            live_usd = 0.0
            if _live.live_enabled(live_cfg):
                key = f"{signal.get('market_id')}|{signal.get('source')}"
                live_usd = live_usd_by_key.get(key, _live.order_usd(signal, live_cfg))

            result = self.execute_trade(
                signal,
                live_prechecked=_live.live_enabled(live_cfg),
                live_order_usd=live_usd,
            )
            results.append(result)
            
            if result["status"] == "success":
                success_count += 1
            elif result["status"] == "dry_run":
                dry_run_count += 1
            elif result["status"] == "simulated":
                simulated_count += 1
            elif result["status"] in ("blocked_no_live_gate", "blocked_live_probe"):
                blocked_live += 1
            else:
                failed_count += 1
        
        output_file = self._write_execution_results(
            total=len(signals),
            success_count=success_count,
            dry_run_count=dry_run_count,
            simulated_count=simulated_count,
            failed_count=failed_count,
            results=results,
        )
        
        self.log(
            f"\n✅ 执行完成: {success_count} 成功, {dry_run_count} dry-run, "
            f"{simulated_count} simulated, {failed_count} 失败, {skipped_dup} 跳过重复, "
            f"{blocked_live} live门控阻断"
        )
        self.log(f"结果已保存到 {output_file}")
        self.log("=" * 60)

def main():
    executor = SignalExecutor()
    executor.run()

if __name__ == "__main__":
    main()
