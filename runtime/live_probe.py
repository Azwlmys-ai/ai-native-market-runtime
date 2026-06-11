"""
live_probe — Phase 4 小额 live probe + live 风控门控（stdlib-only）
============================================================================
PRD Phase 4：在显式授权下，用极小仓位验证真实下单链路，同时保留可解释审计。

安全纪律（不可破坏）
--------------------
  * **默认全关**：未设 PA_LIVE_PROBE=1 → 即使去掉 EXECUTOR_DRY_RUN 也**绝不**真实下单。
  * **双重门控**：真实下单需 PA_LIVE_PROBE=1 且 EXECUTOR_DRY_RUN 未开启。
  * **只 probe**：默认 PA_LIVE_PROBE_ONLY_PROBE=1，仅 grade=paper_probe / probe=true / tier=exploration。
  * **硬上限**：单笔 USD、每周期笔数、每日累计 USD、每日亏损熔断（触发写 STOP_TRADING）。
  * **风控快照**：PA_LIVE_RISK_ENFORCE=1 时，risk_snapshot 有 exposure violations → 阻断新买入。
  * **止损优先**：STOP_TRADING 阻断新买入，但 **urgent** 优先级卖出（止损）仍放行。

env 门控
--------
  PA_LIVE_PROBE=1              开启 Phase 4 live probe（必需）
  PA_LIVE_PROBE_ONLY_PROBE=1   仅 probe 级信号（默认开）
  PA_LIVE_PROBE_MAX_USD=25     单笔最大 USD
  PA_LIVE_PROBE_MAX_PER_CYCLE=2  每周期最多真实买入笔数
  PA_LIVE_PROBE_MAX_DAILY_USD=100  每日累计买入 USD 上限
  PA_LIVE_PROBE_MAX_DAILY_LOSS_USD=50  每日已实现亏损熔断（写 STOP_TRADING）
  PA_LIVE_PROBE_ACCOUNT=10000  position_size 换算账户基数
  PA_LIVE_RISK_ENFORCE=1       读 risk_snapshot 阻断违规 exposure
  PA_LIVE_STOP_LOSS_ALLOW=1    STOP_TRADING 时仍允许 urgent 卖出（默认开）
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from runtime import datastore as _ds

SCHEMA_VERSION = "0.4.0-phase4-live-probe"

DEFAULT_MAX_USD = 25.0
DEFAULT_MAX_PER_CYCLE = 2
DEFAULT_MAX_DAILY_USD = 100.0
DEFAULT_MAX_DAILY_LOSS_USD = 50.0
DEFAULT_ACCOUNT = 10_000.0


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def is_dry_run() -> bool:
    return os.environ.get("EXECUTOR_DRY_RUN", "").lower() in ("1", "true", "yes")


def gates() -> dict:
    return {
        "live_probe": _truthy("PA_LIVE_PROBE"),
        "only_probe": _truthy("PA_LIVE_PROBE_ONLY_PROBE", default=True),
        "risk_enforce": _truthy("PA_LIVE_RISK_ENFORCE", default=True),
        "stop_loss_allow": _truthy("PA_LIVE_STOP_LOSS_ALLOW", default=True),
        "max_usd": _env_float("PA_LIVE_PROBE_MAX_USD", DEFAULT_MAX_USD),
        "max_per_cycle": _env_int("PA_LIVE_PROBE_MAX_PER_CYCLE", DEFAULT_MAX_PER_CYCLE),
        "max_daily_usd": _env_float("PA_LIVE_PROBE_MAX_DAILY_USD", DEFAULT_MAX_DAILY_USD),
        "max_daily_loss_usd": _env_float("PA_LIVE_PROBE_MAX_DAILY_LOSS_USD", DEFAULT_MAX_DAILY_LOSS_USD),
        "account_balance": _env_float("PA_LIVE_PROBE_ACCOUNT", DEFAULT_ACCOUNT),
    }


def live_enabled(cfg: Optional[dict] = None) -> bool:
    """真实下单授权：PA_LIVE_PROBE=1 且非 dry-run。"""
    cfg = cfg or gates()
    return bool(cfg["live_probe"]) and not is_dry_run()


def _load_json(base_dir: Optional[Path], name: str) -> dict:
    base = Path(base_dir) if base_dir else _ds.get_base_dir()
    p = base / "data" / name
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _state_path(base_dir: Optional[Path]) -> Path:
    return (Path(base_dir) if base_dir else _ds.get_base_dir()) / "data" / "live_probe_state.json"


def load_state(base_dir: Optional[Path] = None) -> dict:
    p = _state_path(base_dir)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(state: dict, base_dir: Optional[Path] = None) -> None:
    p = _state_path(base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _rolling_state(state: dict) -> dict:
    """跨日重置 daily 计数。"""
    today = _today_utc()
    if state.get("day") != today:
        return {
            "day": today,
            "daily_buy_usd": 0.0,
            "daily_realized_pnl": 0.0,
            "daily_orders": 0,
            "cycle_orders": 0,
            "last_cycle_id": "",
        }
    return state


def is_probe_signal(signal: dict) -> bool:
    """是否属于小额 probe 级信号（Phase 4 默认只允许这类）。"""
    if signal.get("probe") is True:
        return True
    grade = str(signal.get("grade") or "").lower()
    if grade in ("paper_probe", "probe"):
        return True
    tier = str(signal.get("tier") or "").lower()
    if tier == "exploration":
        return True
    # 协整 pipeline 默认 research probe 仓位，无 grade 时看 source+小仓
    if signal.get("source") == "cointegration":
        try:
            ps = float(signal.get("position_size", 0) or 0)
        except (TypeError, ValueError):
            ps = 0.0
        if ps > 0 and ps <= 0.06:
            return True
    return False


def order_usd(signal: dict, cfg: dict) -> float:
    try:
        ps = float(signal.get("position_size", 0) or 0)
    except (TypeError, ValueError):
        ps = 0.0
    raw = cfg["account_balance"] * ps
    return min(max(0.0, raw), cfg["max_usd"])


def cap_signal_amount(signal: dict, cfg: Optional[dict] = None) -> tuple[dict, float]:
    """返回 (新信号,  capped_usd)。position_size 按硬上限重算。"""
    cfg = cfg or gates()
    usd = order_usd(signal, cfg)
    if cfg["account_balance"] <= 0:
        return signal, usd
    capped_ps = round(usd / cfg["account_balance"], 6)
    if capped_ps == signal.get("position_size"):
        return signal, usd
    return {**signal, "position_size": capped_ps, "live_probe_capped": True}, usd


def risk_blocks_new_buys(base_dir: Optional[Path], cfg: Optional[dict] = None) -> tuple[bool, str]:
    cfg = cfg or gates()
    if not cfg["risk_enforce"]:
        return False, ""
    snap = _load_json(base_dir, "risk_snapshot.json")
    violations = (snap.get("exposure") or {}).get("violations") or []
    if violations:
        return True, f"risk_snapshot violations={len(violations)}"
    return False, ""


def daily_loss_tripped(state: dict, cfg: dict) -> bool:
    try:
        pnl = float(state.get("daily_realized_pnl", 0) or 0)
    except (TypeError, ValueError):
        pnl = 0.0
    return pnl <= -abs(cfg["max_daily_loss_usd"])


def _write_stop_trading(reason: str, base_dir: Optional[Path]) -> None:
    base = Path(base_dir) if base_dir else _ds.get_base_dir()
    p = base / "data" / "STOP_TRADING"
    p.write_text(
        f"live_probe circuit breaker {datetime.now(timezone.utc).isoformat()}: {reason}\n",
        encoding="utf-8",
    )


def pre_trade_check(
    signal: dict,
    *,
    cycle_id: str = "",
    base_dir: Optional[Path] = None,
    cfg: Optional[dict] = None,
    state: Optional[dict] = None,
    cycle_count: int = 0,
) -> tuple[bool, str, dict, float]:
    """返回 (allowed, reason, capped_signal, usd)。"""
    cfg = cfg or gates()
    if not live_enabled(cfg):
        return False, "live_probe_disabled", signal, 0.0

    if cfg["only_probe"] and not is_probe_signal(signal):
        return False, "not_probe_signal", signal, 0.0

    blocked, why = risk_blocks_new_buys(base_dir, cfg)
    if blocked:
        return False, why, signal, 0.0

    state = _rolling_state(state or load_state(base_dir))
    if daily_loss_tripped(state, cfg):
        return False, "daily_loss_circuit_breaker", signal, 0.0

    if cycle_count >= cfg["max_per_cycle"]:
        return False, "max_per_cycle", signal, 0.0

    capped, usd = cap_signal_amount(signal, cfg)
    if usd <= 0:
        return False, "zero_order_usd", capped, 0.0

    if state.get("daily_buy_usd", 0) + usd > cfg["max_daily_usd"]:
        return False, "max_daily_usd", capped, usd

    if cycle_id and state.get("last_cycle_id") != cycle_id:
        state["cycle_orders"] = 0
        state["last_cycle_id"] = cycle_id

    return True, "ok", capped, usd


def record_live_buy(usd: float, signal: dict, *, base_dir: Optional[Path] = None, cycle_id: str = "") -> dict:
    state = _rolling_state(load_state(base_dir))
    state["daily_buy_usd"] = round(float(state.get("daily_buy_usd", 0)) + usd, 2)
    state["daily_orders"] = int(state.get("daily_orders", 0)) + 1
    state["cycle_orders"] = int(state.get("cycle_orders", 0)) + 1
    if cycle_id:
        state["last_cycle_id"] = cycle_id
    save_state(state, base_dir)
    return state


def record_live_sell_pnl(pnl_usd: float, *, base_dir: Optional[Path] = None, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or gates()
    state = _rolling_state(load_state(base_dir))
    state["daily_realized_pnl"] = round(float(state.get("daily_realized_pnl", 0)) + pnl_usd, 2)
    save_state(state, base_dir)
    if daily_loss_tripped(state, cfg):
        _write_stop_trading(f"daily_loss {state['daily_realized_pnl']}", base_dir)
    return state


def filter_signals_for_live(
    signals: list,
    *,
    cycle_id: str = "",
    base_dir: Optional[Path] = None,
    cfg: Optional[dict] = None,
) -> tuple[list, list]:
    """返回 (allowed_signals, audit_entries)。仅内存预占额度，成交后须 commit_live_buy。"""
    cfg = cfg or gates()
    if not live_enabled(cfg):
        return [], []

    state = _rolling_state(load_state(base_dir))
    if cycle_id and state.get("last_cycle_id") != cycle_id:
        state["cycle_orders"] = 0
        state["last_cycle_id"] = cycle_id

    allowed, audit, cycle_count = [], [], int(state.get("cycle_orders", 0))
    sim_daily = float(state.get("daily_buy_usd", 0))

    for sig in signals:
        if not isinstance(sig, dict):
            continue
        sim_state = {**state, "daily_buy_usd": sim_daily}
        ok, reason, capped, usd = pre_trade_check(
            sig,
            cycle_id=cycle_id,
            base_dir=base_dir,
            cfg=cfg,
            state=sim_state,
            cycle_count=cycle_count,
        )
        entry = {
            "market_id": sig.get("market_id"),
            "source": sig.get("source"),
            "grade": sig.get("grade"),
            "tier": sig.get("tier"),
            "allowed": ok,
            "reason": reason,
            "order_usd": round(usd, 2),
            "position_size": capped.get("position_size"),
        }
        audit.append(entry)
        if ok:
            allowed.append(capped)
            cycle_count += 1
            sim_daily = round(sim_daily + usd, 2)

    return allowed, audit


def commit_live_buy(usd: float, signal: dict, *, base_dir: Optional[Path] = None, cycle_id: str = "") -> None:
    """真实成交后落状态与计数。"""
    record_live_buy(usd, signal, base_dir=base_dir, cycle_id=cycle_id)


def should_block_live_buy(stop_trading_active: bool) -> bool:
    return stop_trading_active and live_enabled()


def estimate_sell_pnl_usd(signal: dict, cfg: Optional[dict] = None) -> float:
    """从 Agent P 卖出信号的 pnl（比例）估算 USD 盈亏，供日亏损熔断。"""
    cfg = cfg or gates()
    try:
        pct = float(signal.get("pnl", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    # probe 仓位上限作名义本金代理
    return round(pct * cfg["max_usd"], 2)


def should_allow_live_sell(signal: dict, stop_trading_active: bool, cfg: Optional[dict] = None) -> bool:
    """STOP_TRADING 时：默认仅放行 urgent 止损卖单。"""
    if is_dry_run():
        return True
    if not stop_trading_active:
        return True
    cfg = cfg or gates()
    if not cfg["stop_loss_allow"]:
        return False
    return str(signal.get("priority") or "").lower() == "urgent"


def write_audit(report: dict, base_dir: Optional[Path] = None) -> None:
    base = Path(base_dir) if base_dir else _ds.get_base_dir()
    p = base / "data" / "live_probe_audit.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def build_cycle_report(
    *,
    phase: str,
    allowed: list,
    blocked: list,
    cfg: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> dict:
    cfg = cfg or gates()
    rep = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase": phase,
        "live_enabled": live_enabled(cfg),
        "dry_run": is_dry_run(),
        "gates": cfg,
        "allowed_count": len(allowed),
        "blocked_count": len(blocked),
        "allowed": allowed,
        "blocked": blocked,
    }
    if extra:
        rep.update(extra)
    return rep
