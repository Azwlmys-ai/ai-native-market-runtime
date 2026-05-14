#!/usr/bin/env python3
"""
Collect per-cycle metrics after a dry-run cycle.
Appends one JSON record to data/monitor_metrics.jsonl
"""
import json
import os
import sys
import re
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import get_base_dir

def count_log_patterns(log_path: Path, patterns: list) -> dict:
    counts = {p: 0 for p in patterns}
    if not log_path.exists():
        return counts
    text = log_path.read_text(errors="replace")
    for p in patterns:
        counts[p] = len(re.findall(p, text))
    return counts

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle", type=int, required=True)
    parser.add_argument("--cycle-start", type=str, required=True)
    args = parser.parse_args()

    base = get_base_dir()
    data = base / "data"
    logs = base / "logs"
    today = datetime.now().strftime("%Y%m%d")
    now_iso = datetime.now().isoformat()

    # ── signals ─────────────────────────────────────────────────────
    sig_count = 0
    signals_file = data / "signals.json"
    if signals_file.exists():
        try:
            sig_count = len(json.loads(signals_file.read_text()))
        except Exception:
            pass

    # ── review results ───────────────────────────────────────────────
    approved = rejected = 0
    cache_hits = cache_misses = 0
    review_file = data / "review_results.json"
    if review_file.exists():
        try:
            rv = json.loads(review_file.read_text())
            approved = rv.get("approved", 0)
            rejected = rv.get("rejected", 0)
            cs = rv.get("cache_stats", {})
            cache_hits = cs.get("hits", 0)
            cache_misses = cs.get("misses", 0)
        except Exception:
            pass

    # ── execution results ────────────────────────────────────────────
    dry_run_count = success_count = skipped_count = 0
    exec_file = data / "execution_results.json"
    if exec_file.exists():
        try:
            ev = json.loads(exec_file.read_text())
            results = ev.get("results", [])
            dry_run_count = sum(1 for r in results if r.get("status") == "dry_run")
            success_count = sum(1 for r in results if r.get("status") == "success")
            skipped_count = sum(1 for r in results if r.get("status") == "skipped")
        except Exception:
            pass

    # ── Agent M log: LLM calls, fallback, retry, errors ─────────────
    agent_m_log = logs / f"agent_m_{today}.log"
    llm_calls = 0
    fallback_count = 0
    retry_count = 0
    error_lines = []

    if agent_m_log.exists():
        text = agent_m_log.read_text(errors="replace")
        llm_calls = len(re.findall(r"审查信号:|缓存命中:", text))
        fallback_count = len(re.findall(r"已切换到", text))
        retry_count = len(re.findall(r"API 错误:|超时（", text))
        for line in text.splitlines():
            if "❌" in line or "ERROR" in line.upper():
                error_lines.append(line.strip())

    # ── orchestrator log errors ──────────────────────────────────────
    orch_log = logs / f"orchestrator_{today}.log"
    orch_errors = []
    if orch_log.exists():
        for line in orch_log.read_text(errors="replace").splitlines():
            if "❌" in line or ("ERROR" in line.upper() and "agent" in line.lower()):
                orch_errors.append(line.strip())

    # ── token estimate ───────────────────────────────────────────────
    # Prompt template ~850 tokens/signal (measured from API response), completion ~150 tokens
    PROMPT_TOKENS_PER_SIGNAL = 850
    COMPLETION_TOKENS_PER_SIGNAL = 150
    llm_actual_calls = cache_misses  # only non-cached calls consume tokens
    estimated_prompt_tokens = llm_actual_calls * PROMPT_TOKENS_PER_SIGNAL
    estimated_completion_tokens = llm_actual_calls * COMPLETION_TOKENS_PER_SIGNAL
    estimated_total_tokens = estimated_prompt_tokens + estimated_completion_tokens

    # ── build record ─────────────────────────────────────────────────
    record = {
        "cycle": args.cycle,
        "cycle_start": args.cycle_start,
        "cycle_end": now_iso,
        "signals": sig_count,
        "approved": approved,
        "rejected": rejected,
        "llm_calls": llm_calls,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "estimated_tokens": {
            "prompt": estimated_prompt_tokens,
            "completion": estimated_completion_tokens,
            "total": estimated_total_tokens,
        },
        "fallback_triggered": fallback_count,
        "retry_count": retry_count,
        "execution": {
            "dry_run": dry_run_count,
            "success": success_count,
            "skipped": skipped_count,
        },
        "errors": {
            "agent_m": error_lines[-5:] if error_lines else [],
            "orchestrator": orch_errors[-5:] if orch_errors else [],
        },
    }

    # ── append to JSONL ──────────────────────────────────────────────
    metrics_file = data / "monitor_metrics.jsonl"
    with open(metrics_file, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ── print summary ────────────────────────────────────────────────
    print(f"[Cycle {args.cycle}] signals={sig_count} approved={approved} rejected={rejected} "
          f"llm_calls={llm_calls}(cache_hit={cache_hits}) "
          f"tokens~{estimated_total_tokens} "
          f"fallback={fallback_count} retry={retry_count} "
          f"dry_run={dry_run_count} success={success_count} "
          f"errors_agentm={len(error_lines)}")

if __name__ == "__main__":
    main()
