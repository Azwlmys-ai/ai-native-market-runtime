#!/usr/bin/env bash
# Smoke test for the minimal Visualization Agent.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

cd "$ROOT"
python3 agents/agent_visualization.py >/tmp/polymarket_visualization_state.json

python3 - <<'PYEOF'
import json
from pathlib import Path

root = Path.cwd()
state_path = root / "data" / "visualization_state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
required = {
    "timestamp",
    "signals_summary",
    "review_summary",
    "execution_summary",
    "agent_log_summary",
    "recent_runtime_events",
}
missing = sorted(required.difference(state))
if missing:
    raise SystemExit(f"missing visualization keys: {missing}")
print(f"visualization smoke ok: {state_path}")
PYEOF
