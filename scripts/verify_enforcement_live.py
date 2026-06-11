#!/usr/bin/env python3
"""
verify_enforcement_live — Phase 5 纸面强制层「主机开闸前」只读演练

在真实 data/ 上模拟 PA_ENFORCE_LEARNING=1 会对当前 signals 做什么：
  - 默认只读：调用 enforcement.apply()，不写 signals.json / enforcement_audit.json
  - --write-audit：落盘 enforcement_audit.json（与 orchestrator 周期一致）

用法：
  PA_ENFORCE_LEARNING=1 python3 scripts/verify_enforcement_live.py
  PA_ENFORCE_LEARNING=1 python3 scripts/verify_enforcement_live.py --write-audit
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime import datastore as ds
from runtime import enforcement


def _load_signals(base: Path) -> list:
    p = base / "data" / "signals.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else d.get("signals", [])
    except Exception:
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 5 enforcement dry-run on live data")
    parser.add_argument("--write-audit", action="store_true", help="落盘 enforcement_audit.json")
    args = parser.parse_args()

    base = ds.get_base_dir()
    signals = _load_signals(base)
    cfg = enforcement.gates()

    if not enforcement.any_enabled(cfg):
        print(json.dumps({
            "ok": False,
            "error": "PA_ENFORCE_LEARNING / PA_ENFORCE_SIZING / PA_ENFORCE_WEIGHTS 均未开启",
            "hint": "PA_ENFORCE_LEARNING=1 python3 scripts/verify_enforcement_live.py",
        }, ensure_ascii=False, indent=2))
        return 1

    rule_report = enforcement._load_json(base, "rule_effectiveness.json") if cfg["enforce_weights"] else {}
    sizing_report = enforcement._load_json(base, "sizing_suggestions.json") if cfg["enforce_sizing"] else {}
    out, audit = enforcement.apply(signals, rule_report, sizing_report, cfg)

    changed = [
        a for a in audit
        if a.get("final_position_size") != a.get("original_position_size")
    ]
    by_source: dict[str, dict] = {}
    for a in audit:
        src = str(a.get("source") or "unknown")
        bucket = by_source.setdefault(src, {"hit": 0, "changed": 0})
        bucket["hit"] += 1
        if a.get("final_position_size") != a.get("original_position_size"):
            bucket["changed"] += 1

    report = {
        "ok": True,
        "n_signals": len(signals),
        "n_sizing_suggestions": len(sizing_report.get("suggestions") or []),
        "gates": cfg,
        "applied_count": len(audit),
        "n_sizing_applied": sum(1 for a in audit if "sizing" in a["applied"]),
        "n_weight_applied": sum(1 for a in audit if "weight" in a["applied"]),
        "net_position_changes": len(changed),
        "by_source": by_source,
        "note": (
            "命中但净改动为 0 通常因「默认只降险」：Kelly sized_fraction > 原始 probe 仓位时不放大；"
            "weight 全为 1.0(explore) 时也不缩放。随 turbulent regime / down_weight 积累会出现真实改动。"
        ),
        "samples": [
            {
                "market_id": a.get("market_id"),
                "source": a.get("source"),
                "orig": a.get("original_position_size"),
                "final": a.get("final_position_size"),
                "applied": a.get("applied"),
            }
            for a in (changed[:6] or audit[:6])
        ],
    }

    if args.write_audit:
        full = {
            "schema_version": enforcement.SCHEMA_VERSION,
            "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "enforced": True,
            "gates": report["gates"],
            "n_signals": len(signals),
            "applied_count": len(audit),
            "n_sizing_applied": report["n_sizing_applied"],
            "n_weight_applied": report["n_weight_applied"],
            "source_rule_weights_generated_at": rule_report.get("generated_at"),
            "source_sizing_generated_at": sizing_report.get("generated_at"),
            "adjustments": audit,
        }
        ds.write_enforcement_audit(full, base_dir=base)
        report["audit_written"] = True

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
