"""
rotate_logs.py — safe log rotation utility for the Polymarket Arbitrage project.

Default mode is DRY-RUN: reports what would be archived without modifying any file.
Pass --apply to actually move and gzip old logs into the archive directory.

Usage examples:
    # Dry-run (default): show what would be archived
    python3 scripts/rotate_logs.py

    # Dry-run against a specific logs dir
    python3 scripts/rotate_logs.py --logs-dir /tmp/test-logs

    # Actually archive logs older than 14 days
    python3 scripts/rotate_logs.py --retention-days 14 --apply
"""

import argparse
import gzip
import os
import shutil
import sys
import time
from pathlib import Path


def _find_project_logs_dir() -> Path:
    """Return the default logs/ directory relative to this script."""
    return Path(__file__).resolve().parent.parent / "logs"


def _archive_path(archive_dir: Path, log_path: Path) -> Path:
    """Return a collision-free .gz path under archive_dir for log_path."""
    base = archive_dir / (log_path.name + ".gz")
    if not base.exists():
        return base
    stem = log_path.name
    counter = 1
    while True:
        candidate = archive_dir / f"{stem}.{counter}.gz"
        if not candidate.exists():
            return candidate
        counter += 1


def rotate_logs(
    logs_dir: Path,
    retention_days: int,
    archive_dir: Path,
    apply: bool,
) -> dict:
    """
    Core rotation logic.

    Returns a summary dict:
        {
            "archived": [list of (src, dst) pairs that were/would be archived],
            "skipped":  [list of paths that are recent enough to keep],
            "ignored":  [list of paths that are non-.log files],
        }
    """
    cutoff = time.time() - retention_days * 86400

    archived = []
    skipped = []
    ignored = []

    if not logs_dir.exists():
        print(f"[rotate_logs] logs-dir does not exist: {logs_dir}")
        return {"archived": archived, "skipped": skipped, "ignored": ignored}

    for entry in sorted(logs_dir.iterdir()):
        # Only process regular *.log files directly under logs_dir (no recursion)
        if not entry.is_file():
            continue
        if entry.suffix != ".log":
            ignored.append(entry)
            continue

        mtime = entry.stat().st_mtime
        if mtime >= cutoff:
            skipped.append(entry)
            continue

        dst = _archive_path(archive_dir, entry)
        archived.append((entry, dst))

        if apply:
            archive_dir.mkdir(parents=True, exist_ok=True)
            with open(entry, "rb") as f_in, gzip.open(dst, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            entry.unlink()
            print(f"[rotate_logs] archived: {entry.name} -> {dst.name}")
        else:
            print(f"[rotate_logs] dry-run: would archive {entry.name} -> {dst.name}")

    return {"archived": archived, "skipped": skipped, "ignored": ignored}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Rotate old project logs into a gzip archive (dry-run by default)."
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=None,
        help="Directory containing .log files (default: project logs/).",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Keep logs newer than this many days (default: 30).",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=None,
        help="Destination for archived logs (default: <logs-dir>/archive).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually archive files. Without this flag the script is a dry-run.",
    )
    args = parser.parse_args(argv)

    logs_dir = args.logs_dir if args.logs_dir is not None else _find_project_logs_dir()
    archive_dir = args.archive_dir if args.archive_dir is not None else logs_dir / "archive"

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[rotate_logs] mode={mode} logs-dir={logs_dir} "
        f"retention={args.retention_days}d archive-dir={archive_dir}"
    )

    summary = rotate_logs(
        logs_dir=logs_dir,
        retention_days=args.retention_days,
        archive_dir=archive_dir,
        apply=args.apply,
    )

    print(
        f"[rotate_logs] done: {len(summary['archived'])} archived, "
        f"{len(summary['skipped'])} kept, {len(summary['ignored'])} ignored."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
