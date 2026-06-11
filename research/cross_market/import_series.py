"""Import P0 series into shared_intelligence — reuse a_share, fetch gaps."""

from __future__ import annotations

import json
import os
import sqlite3
import ssl
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import CN_TARGETS, MACRO_SERIES, US_TARGETS
from .fetch_yahoo import fetch_yahoo_daily
from .paths import (
    ASHARE_DB,
    CHINA_DIR,
    CHINA_HISTORY_START,
    FLOWS_DIR,
    MACRO_DIR,
    MARKETS_DIR,
    VALIDATION_START,
    VALIDATION_END,
)

# 东方财富 kamt 北向序列中的额度占位符（非真实净流入）
_NB_SENTINELS = frozenset({1_040_000.0, 520_000.0, 420_000.0, 1_300_000.0, 5_200_000.0, 4_200_000.0})
_NB_SENTINELS |= {x * 10 for x in _NB_SENTINELS}  # 10400000 等

# avoid proxy for domestic APIs
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)
os.environ.setdefault("NO_PROXY", "*")


def _write_series(path: Path, symbol: str, source: str, bars: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dates = [b["date"] for b in bars]
    payload = {
        "symbol": symbol,
        "source": source,
        "start": min(dates) if dates else None,
        "end": max(dates) if dates else None,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "bars": bars,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [ok] {path.name}: {len(bars)} bars ({payload['start']} → {payload['end']})")


def _load_json_bars(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("bars") or []


def _merge_bars(*series: list[dict]) -> list[dict]:
    by_date: dict[str, float] = {}
    for bars in series:
        for b in bars:
            d, c = b.get("date"), b.get("close")
            if d and c is not None:
                by_date[d] = float(c)
    return [{"date": d, "close": c} for d, c in sorted(by_date.items())]


# Eastmoney secid: sh prefix=1, sz prefix=0
_EASTMONEY_INDEX: dict[str, str] = {
    "000001": "1.000001",
    "399001": "0.399001",
    "399006": "0.399006",
    "000300": "1.000300",
}


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


_SINA_INDEX: dict[str, str] = {
    "000001": "sh000001",
    "399001": "sz399001",
    "399006": "sz399006",
    "000300": "sh000300",
}


def fetch_china_index_sina(code: str, start: str, datalen: int = 3000) -> list[dict]:
    """Daily index closes via Sina finance API."""
    sym = _SINA_INDEX.get(code)
    if not sym:
        return []
    qs = urllib.parse.urlencode({"symbol": sym, "scale": "240", "ma": "no", "datalen": str(datalen)})
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"})
        with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [warn] sina index {code}: {exc}")
        return []
    out = []
    for row in payload or []:
        d = str(row.get("day", ""))[:10]
        if not d or d < start:
            continue
        try:
            close = float(row.get("close"))
        except (TypeError, ValueError):
            continue
        out.append({"date": d, "close": round(close, 4)})
    return sorted(out, key=lambda x: x["date"])


def fetch_china_index_eastmoney(code: str, start: str) -> list[dict]:
    """Daily index closes via Eastmoney kline API (no akshare)."""
    secid = _EASTMONEY_INDEX.get(code)
    if not secid:
        return []
    qs = urllib.parse.urlencode({
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "0",
        "end": "20500101",
        "lmt": "2000",
    })
    url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [warn] eastmoney index {code}: {exc}")
        return []
    klines = ((payload.get("data") or {}).get("klines")) or []
    out = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 3:
            continue
        d = parts[0][:10]
        if d < start:
            continue
        try:
            close = float(parts[2])
        except (TypeError, ValueError):
            continue
        out.append({"date": d, "close": round(close, 4)})
    return sorted(out, key=lambda x: x["date"])


def _valid_northbound_value(v: float) -> bool:
    if v == 0:
        return False
    if v in _NB_SENTINELS:
        return False
    if abs(v) > 5_000_000:  # 异常大值（百万元口径）
        return False
    return True


def fetch_northbound_kamt(start: str, lmt: int = 3000) -> list[dict]:
    """北向资金净流入 — push2his kamt.kline s2n 序列（百万元）."""
    qs = urllib.parse.urlencode({
        "lmt": str(lmt),
        "klt": "101",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
    })
    url = f"https://push2his.eastmoney.com/api/qt/kamt.kline/get?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60, context=_ssl_ctx()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [warn] northbound kamt: {exc}")
        return []
    lines = ((payload.get("data") or {}).get("s2n")) or []
    out = []
    for line in lines:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d = parts[0][:10]
        if d < start:
            continue
        try:
            v = float(parts[1])
        except (TypeError, ValueError):
            continue
        if not _valid_northbound_value(v):
            continue
        out.append({"date": d, "close": round(v, 4)})
    return sorted(out, key=lambda x: x["date"])


def fetch_northbound_deal_history(start: str) -> list[dict]:
    """北向资金 — RPT_MUTUAL_DEAL_HISTORY MUTUAL_TYPE=005（与 akshare 一致）."""
    out: list[dict] = []
    for page in range(1, 60):
        qs = urllib.parse.urlencode({
            "reportName": "RPT_MUTUAL_DEAL_HISTORY",
            "columns": "TRADE_DATE,NET_DEAL_AMT,FUND_INFLOW",
            "pageSize": "500",
            "pageNumber": str(page),
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
            "filter": '(MUTUAL_TYPE="005")',
        })
        url = f"https://datacenter-web.eastmoney.com/api/data/v1/get?{qs}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx()) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            print(f"  [warn] northbound deal page {page}: {exc}")
            break
        rows = (payload.get("result") or {}).get("data") or []
        if not rows:
            break
        oldest = None
        for row in rows:
            d = str(row.get("TRADE_DATE", ""))[:10]
            if not d:
                continue
            oldest = d
            if d < start:
                continue
            raw = row.get("NET_DEAL_AMT")
            if raw is None:
                raw = row.get("FUND_INFLOW")
            if raw is None:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            if not _valid_northbound_value(v):
                continue
            out.append({"date": d, "close": round(v, 4)})
        if oldest and oldest < start:
            break
        if len(rows) < 500:
            break
    return sorted(out, key=lambda x: x["date"])


def fetch_northbound_eastmoney(start: str) -> list[dict]:
    """合并 kamt s2n（主）+ deal history（补全）."""
    kamt = fetch_northbound_kamt(start)
    deal = fetch_northbound_deal_history(start)
    return _merge_bars(kamt, deal)


def export_from_ashare(code: str, start: str = VALIDATION_START) -> list[dict]:
    if not ASHARE_DB.exists():
        return []
    conn = sqlite3.connect(ASHARE_DB)
    try:
        rows = conn.execute(
            "SELECT trade_date, close FROM daily_bars WHERE symbol = ? AND trade_date >= ? ORDER BY trade_date",
            (code, start),
        ).fetchall()
        return [{"date": r[0], "close": round(float(r[1]), 6)} for r in rows]
    finally:
        conn.close()


def fetch_china_index_akshare(code: str, ak_symbol: str, start: str) -> list[dict]:
    try:
        import akshare as ak
    except ImportError:
        print("  [warn] akshare not installed")
        return []
    try:
        df = ak.stock_zh_index_daily(symbol=ak_symbol)
    except Exception as exc:
        print(f"  [warn] akshare index {ak_symbol}: {exc}")
        return []
    if df is None or df.empty:
        return []
    out = []
    date_col = "date" if "date" in df.columns else df.columns[0]
    close_col = "close" if "close" in df.columns else "close"
    for _, row in df.iterrows():
        d = str(row[date_col])[:10]
        if d < start:
            continue
        out.append({"date": d, "close": round(float(row[close_col]), 6)})
    return sorted(out, key=lambda x: x["date"])


def fetch_china_index_baostock(bs_code: str, start: str) -> list[dict]:
    try:
        import baostock as bs
    except ImportError:
        return []
    lg = bs.login()
    if lg.error_code != "0":
        print(f"  [warn] baostock login: {lg.error_msg}")
        return []
    try:
        rs = bs.query_history_k_data_plus(
            bs_code, "date,close", start_date=start, end_date=VALIDATION_END, frequency="d", adjustflag="3"
        )
        out = []
        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()
            if row[1]:
                out.append({"date": row[0], "close": round(float(row[1]), 6)})
        return out
    finally:
        bs.logout()


def fetch_northbound(start: str) -> list[dict]:
    """北向资金净流入（百万元）— Eastmoney kamt + deal history."""
    bars = fetch_northbound_eastmoney(start)
    if bars:
        return bars
    try:
        import akshare as ak
        df = ak.stock_hsgt_hist_em(symbol="北向资金")
    except Exception:
        return []
    if df is None or df.empty:
        return []
    date_col = [c for c in df.columns if "日期" in c or c.lower() == "date"]
    val_col = [c for c in df.columns if "净买" in c or "净流入" in c]
    if not date_col or not val_col:
        return []
    out = []
    for _, row in df.iterrows():
        d = str(row[date_col[0]])[:10]
        if d < start:
            continue
        try:
            v = float(row[val_col[0]])
        except (TypeError, ValueError):
            continue
        out.append({"date": d, "close": round(v, 4)})
    return sorted(out, key=lambda x: x["date"])


def import_macro(start: str = VALIDATION_START, end: str = VALIDATION_END) -> dict[str, int]:
    counts = {}
    for key, ticker in MACRO_SERIES.items():
        path = MACRO_DIR / f"{key}.json"
        existing = _load_json_bars(path)
        fetched = fetch_yahoo_daily(ticker, start, end)
        bars = _merge_bars(existing, fetched)
        if bars:
            _write_series(path, key, "yfinance", bars)
            counts[key] = len(bars)
    return counts


def import_china_indices(start: str = CHINA_HISTORY_START) -> dict[str, int]:
    counts = {}
    CHINA_DIR.mkdir(parents=True, exist_ok=True)
    for code, meta in CN_TARGETS.items():
        path = CHINA_DIR / f"{code}.json"
        existing = _load_json_bars(path)
        reused: list[dict] = []
        if meta.get("source", "").startswith("a_share"):
            reused = export_from_ashare(code, max(start, VALIDATION_START))
            if reused:
                print(f"  [reuse] {code} from a_share_research_db: {len(reused)} bars")

        fetched = fetch_china_index_sina(code, start)
        if not fetched:
            fetched = fetch_china_index_eastmoney(code, start)
        if not fetched:
            ak_sym = meta.get("akshare")
            if ak_sym:
                fetched = fetch_china_index_akshare(code, ak_sym, start)
        if not fetched and meta.get("baostock"):
            fetched = fetch_china_index_baostock(meta["baostock"], start)

        bars = _merge_bars(existing, reused, fetched)
        source = "sina+baostock+a_share" if reused and fetched else ("sina/baostock" if fetched else "a_share_research_db")
        if bars:
            _write_series(path, code, source, bars)
            counts[code] = len(bars)
    return counts


def import_flows(start: str = CHINA_HISTORY_START) -> dict[str, int]:
    path = FLOWS_DIR / "northbound.json"
    fetched = fetch_northbound(start)
    if fetched:
        _write_series(path, "northbound", "eastmoney_kamt+deal005", fetched)
        return {"northbound": len(fetched)}
    return {}


def import_us_markets(start: str = VALIDATION_START, end: str = VALIDATION_END) -> dict[str, int]:
    """Ensure US targets + factor components exist in history/markets/."""
    from .config import FACTORS

    tickers: dict[str, str] = {}
    for sym, yf in US_TARGETS.items():
        tickers[sym] = yf
    for fdef in FACTORS.values():
        for label, yf in fdef["symbols"].items():
            if label not in tickers:
                tickers[label] = yf

    counts = {}
    MARKETS_DIR.mkdir(parents=True, exist_ok=True)
    for sym, yf_ticker in tickers.items():
        path = MARKETS_DIR / f"{sym}.json"
        existing = _load_json_bars(path)
        if existing and len(existing) > 400:
            counts[sym] = len(existing)
            continue
        fetched = fetch_yahoo_daily(yf_ticker, start, end)
        bars = _merge_bars(existing, fetched)
        if bars:
            _write_series(path, sym, "yfinance", bars)
            counts[sym] = len(bars)
    return counts


def run_import(
    start: str = CHINA_HISTORY_START,
    end: str = VALIDATION_END,
    china_start: str | None = None,
) -> dict[str, Any]:
    print("=== Cross Market Import ===")
    cs = china_start or start
    result = {
        "macro": import_macro(start, end),
        "china": import_china_indices(cs),
        "flows": import_flows(cs),
        "markets": import_us_markets(start, end),
    }
    print("=== Import complete ===")
    return result
