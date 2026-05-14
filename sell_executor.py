"""DEPRECATED: use executors/sell_executor.py.

Compatibility wrapper retained for old cron/shell/orchestrator calls.
Planned removal after 2026-06-08 once all entrypoints use executors/.
"""

import warnings

warnings.warn(
    "sell_executor.py at project root is deprecated; use executors.sell_executor instead",
    DeprecationWarning,
    stacklevel=2,
)

from executors.sell_executor import *  # noqa: F401,F403
from executors.sell_executor import SellExecutor


if __name__ == "__main__":
    SellExecutor().run()
