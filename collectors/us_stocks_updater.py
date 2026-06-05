#!/usr/bin/env python3
"""
美股数据采集器 - 集成到 Orchestrator
定期采集 Finnhub 和 Polygon 美股数据，带超时保护和降级兜底。
"""

from __future__ import annotations

import json
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from _paths import get_base_dir
from collectors.finnhub_collector import collect_finnhub_data
from collectors.polygon_collector import collect_polygon_data

# Total budget for the entire updater run — must complete (or degrade) well
# within the orchestrator's per-collector timeout (~60s).  25s leaves headroom.
UPDATER_TOTAL_TIMEOUT = 25
FINNHUB_TIMEOUT = 15
POLYGON_TIMEOUT = 20   # reduced from 60 so it cannot dominate the total budget


def _has_stock_rows(data) -> bool:
    return bool(
        isinstance(data, dict)
        and data.get("status") == "success"
        and data.get("total_symbols", 0) > 0
        and data.get("stocks")
    )


async def _fetch_sources():
    """并发采集两个数据源；各自有独立超时；异常返回 None 而不向上抛。"""
    finnhub_task = asyncio.wait_for(collect_finnhub_data(), timeout=FINNHUB_TIMEOUT)
    polygon_task = asyncio.wait_for(collect_polygon_data(), timeout=POLYGON_TIMEOUT)

    finnhub_raw, polygon_raw = await asyncio.gather(
        finnhub_task, polygon_task, return_exceptions=True
    )

    finnhub_data = None
    if isinstance(finnhub_raw, Exception):
        print(f"❌ Finnhub 数据采集失败: {finnhub_raw}")
    elif _has_stock_rows(finnhub_raw):
        finnhub_data = finnhub_raw
        print(f"✅ Finnhub 数据: {finnhub_raw.get('total_symbols', '?')} 个股票")
    else:
        print(f"❌ Finnhub 数据采集失败: 状态异常 ({finnhub_raw!r})")

    polygon_data = None
    if isinstance(polygon_raw, Exception):
        print(f"❌ Polygon 数据采集失败: {polygon_raw}")
    elif _has_stock_rows(polygon_raw):
        polygon_data = polygon_raw
        print(f"✅ Polygon 数据: {polygon_raw.get('total_symbols', '?')} 个股票（备用）")
    else:
        print(f"❌ Polygon 数据采集失败: 状态异常 ({polygon_raw!r})")

    return finnhub_data, polygon_data


async def update_latest_data():
    """更新 latest_data.json 里的 us_stocks 字段。

    保证:
    - 在 UPDATER_TOTAL_TIMEOUT 秒内完成（成功或降级），不会拖慢整个 orchestrator 周期。
    - 至少一个数据源成功时：正常写入 us_stocks。
    - 所有数据源失败时：保留现有 us_stocks 并打 degraded/stale 标记，正常退出（exit 0）。
    """
    now_iso = datetime.now().isoformat()
    latest_data_path = get_base_dir() / "data" / "latest_data.json"

    # 检查缓存
    cache_file = get_base_dir() / "data" / "us_stocks_cache.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            cache_time = datetime.fromisoformat(cache.get("timestamp", ""))
            if (
                (datetime.now() - cache_time).total_seconds() < 1800
                and (
                    len(cache.get("stocks") or []) > 0
                    or len((cache.get("polygon_backup") or {}).get("stocks") or []) > 0
                )
            ):  # 30分钟缓存
                print("使用缓存的美股数据")
                existing_latest = {}
                if latest_data_path.exists():
                    try:
                        with open(latest_data_path, "r", encoding="utf-8") as f:
                            existing_latest = json.load(f)
                    except Exception:
                        pass
                existing_latest["us_stocks"] = cache
                with open(latest_data_path, "w", encoding="utf-8") as f:
                    json.dump(existing_latest, f, indent=2, ensure_ascii=False)
                return
        except Exception:
            pass

    # 读取现有数据，以备 all-fail 时回退
    existing_latest: dict = {}
    if latest_data_path.exists():
        try:
            with open(latest_data_path, "r", encoding="utf-8") as f:
                existing_latest = json.load(f)
        except Exception as exc:
            print(f"⚠️ 无法读取现有 latest_data.json: {exc}")

    # 带总预算的并发采集
    finnhub_data = None
    polygon_data = None
    last_error: str | None = None
    try:
        finnhub_data, polygon_data = await asyncio.wait_for(
            _fetch_sources(), timeout=UPDATER_TOTAL_TIMEOUT
        )
    except asyncio.TimeoutError:
        last_error = f"updater total timeout after {UPDATER_TOTAL_TIMEOUT}s"
        print(f"❌ 美股数据采集总超时（{UPDATER_TOTAL_TIMEOUT}s）")
    except Exception as exc:
        last_error = str(exc)
        print(f"❌ 美股数据采集异常: {exc}")

    latest_data_path.parent.mkdir(parents=True, exist_ok=True)

    if not finnhub_data and not polygon_data:
        # 所有数据源失败 — 保留旧数据，打降级标记
        print("❌ 所有美股数据源采集失败，保留现有数据并标记 stale")
        existing_us_stocks = existing_latest.get("us_stocks", {})
        existing_latest["us_stocks"] = {
            **existing_us_stocks,
            "degraded": True,
            "status": "stale",
            "last_error": last_error or "all sources failed",
            "last_attempt_timestamp": now_iso,
        }
        with open(latest_data_path, "w", encoding="utf-8") as f:
            json.dump(existing_latest, f, indent=2, ensure_ascii=False)
        return

    # 至少一个数据源成功
    us_stocks: dict = {}
    if finnhub_data:
        us_stocks = {
            "source": "finnhub",
            "stocks": finnhub_data["stocks"],
            "total_symbols": finnhub_data["total_symbols"],
            "timestamp": finnhub_data["timestamp"],
        }
    elif polygon_data:
        us_stocks = {
            "source": "polygon",
            "stocks": polygon_data["stocks"],
            "total_symbols": polygon_data["total_symbols"],
            "timestamp": polygon_data["timestamp"],
            "note": polygon_data.get("note", "polygon backup used as primary"),
        }

    if polygon_data and finnhub_data:
        us_stocks["polygon_backup"] = {
            "stocks": polygon_data["stocks"],
            "total_symbols": polygon_data["total_symbols"],
            "timestamp": polygon_data["timestamp"],
        }

    # 保存到缓存
    us_stocks["timestamp"] = now_iso
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(us_stocks, f, indent=2, ensure_ascii=False)

    existing_latest["us_stocks"] = us_stocks
    with open(latest_data_path, "w", encoding="utf-8") as f:
        json.dump(existing_latest, f, indent=2, ensure_ascii=False)

    total_count = (
        (finnhub_data or {}).get("total_symbols", 0)
        + (polygon_data or {}).get("total_symbols", 0)
    )
    print(f"✅ 美股数据已更新到 latest_data.json: 总计 {total_count} 个数据点")


if __name__ == "__main__":
    asyncio.run(update_latest_data())
