"""
observation_backfill_gate — Phase 3e host loop 门控

Env: PA_OBSERVATION_BACKFILL=1 → best-effort 增量导出 observation 文件
默认关闭；失败不得影响主循环；不写 signals/review/execution。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional


def is_enabled() -> bool:
    return os.environ.get("PA_OBSERVATION_BACKFILL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def maybe_run(
    base_dir: Optional[Path] = None,
    log: Optional[Callable[[str], None]] = None,
) -> dict:
    if not is_enabled():
        return {"enabled": False, "skipped": True, "reason": "PA_OBSERVATION_BACKFILL off"}

    _log = log or (lambda _m: None)
    try:
        from runtime.observation_continuity import run_phase3e

        root = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
        result = run_phase3e(base_dir=root)
        pm = result.get("pm_crypto_tape", {})
        fund = result.get("funding", {})
        _log(
            f"📡 Observation 增量导出: pm_tape +{pm.get('appended_rows', 0)} "
            f"funding +{fund.get('appended_rows', 0)}"
        )
        return {
            "enabled": True,
            "ok": True,
            "skipped": False,
            "pm_appended": pm.get("appended_rows", 0),
            "funding_appended": fund.get("appended_rows", 0),
            "continuity_reports": result.get("continuity_reports", {}),
        }
    except Exception as exc:
        _log(f"⚠️  Observation 导出失败（非致命）: {exc}")
        return {"enabled": True, "ok": False, "skipped": False, "error": str(exc)}
