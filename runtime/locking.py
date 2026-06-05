"""
locking — 单写者锁（Phase 2b）
============================================================================
paper 写端（API POST /paper/open|close）与 orchestrator 周期**必须互斥**，否则
重新引入多写者。复用 orchestrator 已有的同一把锁文件 `data/orchestrator.lock`
（fcntl.flock LOCK_EX | LOCK_NB），保证"同一时刻只有一个写者"——无论它是一次
扫描周期，还是一次 API 写入。

用法：
    from runtime.locking import single_writer_lock, WriterBusy
    try:
        with single_writer_lock(base_dir):
            ...  # 安全写 paper（json + shadow）
    except WriterBusy:
        # 周期正在跑，返回 409 让调用方稍后重试
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Optional

try:
    import fcntl
except ImportError:  # 非 POSIX（理论上不会，主机是 macOS）
    fcntl = None


class WriterBusy(RuntimeError):
    """已有写者（扫描周期或另一次 API 写）持锁。"""


def _lock_path(base_dir: Optional[Path]) -> Path:
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    p = base / "data" / "orchestrator.lock"   # 与 orchestrator._acquire_run_lock 同一文件
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def single_writer_lock(base_dir: Optional[Path] = None):
    """非阻塞抢 orchestrator.lock；抢不到立即抛 WriterBusy。"""
    path = _lock_path(base_dir)
    handle = open(path, "w")
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            handle.close()
            raise WriterBusy("写者忙：扫描周期或另一次写入正在进行")
    try:
        yield
    finally:
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()
