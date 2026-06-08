"""
model_sandbox_snapshot — Phase 3c 可选定时快照门控

Env: PA_MODEL_SANDBOX_SNAPSHOT=1 → best-effort 刷新 research/model_sandbox/*
默认关闭；失败不得影响主周期；不写 signals/review/execution。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional


def is_enabled() -> bool:
    return os.environ.get("PA_MODEL_SANDBOX_SNAPSHOT", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def maybe_refresh(
    base_dir: Optional[Path] = None,
    log: Optional[Callable[[str], None]] = None,
) -> dict:
    """若 env 开启则刷新模型沙盒报告；否则 no-op。"""
    if not is_enabled():
        return {"enabled": False, "skipped": True, "reason": "PA_MODEL_SANDBOX_SNAPSHOT off"}

    _log = log or (lambda _m: None)
    try:
        from runtime.model_sandbox import compute

        root = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
        result = compute(base_dir=root)
        _log("📦 模型沙盒快照已刷新 (research/model_sandbox/)")
        return {
            "enabled": True,
            "ok": True,
            "skipped": False,
            "output_paths": result.get("output_paths", {}),
            "summary": result.get("summary", {}),
        }
    except Exception as exc:
        _log(f"⚠️  模型沙盒快照失败（非致命）: {exc}")
        return {"enabled": True, "ok": False, "skipped": False, "error": str(exc)}
