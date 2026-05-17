"""
Market Intelligence Layer (Phase 1 — Shadow Mode)

为每个 Polymarket 市场生成画像（category / tier / 评分 / 影子参数）。

⚠️ Phase 1 仅产出 data/market_intelligence.json，**不被任何下游消费**：
   - 不参与资金分配
   - 不参与 review
   - 不参与买入/卖出执行
   - 不参与止损

由 orchestrator 在 step 2.5 调用，失败被外层 try/except 兜住，绝不阻断主流程。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import get_base_dir


SCHEMA_VERSION = "phase1.0"


class MarketIntelligence:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Market Intelligence] {message}"
        print(log_msg, flush=True)
        log_file = self.logs_dir / f"market_intelligence_{datetime.now().strftime('%Y%m%d')}.log"
        try:
            with open(log_file, "a") as f:
                f.write(log_msg + "\n")
        except Exception:
            # 日志失败不能影响主流程
            pass


if __name__ == "__main__":
    # Task 1 阶段仅冒烟，后续任务实现 run()
    mi = MarketIntelligence()
    mi.log("scaffold ready (Task 1)")
