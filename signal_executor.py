"""DEPRECATED: use executors/signal_executor.py.

Compatibility wrapper retained for old cron/shell/orchestrator calls.
Planned removal after 2026-06-08 once all entrypoints use executors/.
"""

import warnings

warnings.warn(
    "signal_executor.py at project root is deprecated; use executors.signal_executor instead",
    DeprecationWarning,
    stacklevel=2,
)

from executors.signal_executor import *  # noqa: F401,F403
from executors.signal_executor import SignalExecutor


if __name__ == "__main__":
    SignalExecutor().run()
