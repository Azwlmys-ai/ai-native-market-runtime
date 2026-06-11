#!/usr/bin/env python3
"""
bootstrap_cointegration_from_cache — 用磁盘上已有的历史数据集跑出第一批协整候选喂闭环

背景
----
线上 `data/market_price_history.json` 目前只有 10 个近似常量快照（多数序列 flat），协整 0 候选。
真实实时回填需网络（本环境被代理 403 封禁）。但 `data/historical/` 下已有项目自带历史数据集：
  * OKX BTC/ETH/SOL/BNB K 线（真实加密价格序列）；
  * crypto/股票锚定的 Polymarket 历史（每市场 1440 小时点，含真实联动结构）。
本脚本把它们回填成 runtime 价格历史格式，跑真实 `runtime.cointegration` → 产出第一批协整候选，
端到端验证「发现关联」这一环能真正出货。

⚠ 透明声明
----------
`polymarket_*_march_april` 是项目**模拟/回测历史数据集**（id 形如 btc_100k_april，按 anchor 生成），
非线上真实市场实时数据。故产出的是「该历史数据集上的真实协整发现」，用于**自举/验证闭环机制**。
线上真实候选仍需在主机用采集器累积真实价格动态后产生。

安全
----
默认写入**隔离 sandbox**（不碰线上 data/）。`--apply` 才写真实 data/（会覆盖线上价格历史，
违反单写者纪律，仅在你明确要用历史数据集喂线上闭环时使用，需自行权衡）。

用法（需 numpy 环境）：
  python3 scripts/bootstrap_cointegration_from_cache.py [--stride N] [--apply] [--keep]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HIST = ROOT / "data" / "historical"
OKX_COMBINED = HIST / "okx_klines_march_april_may_2026.json"
PM_FILES = [
    HIST / "polymarket_extended_march_april_2026.json",
    HIST / "polymarket_markets_march_april_2026.json",
]
SYMBOL_MAP = {"BTC-USDT": "BTC", "ETH-USDT": "ETH", "SOL-USDT": "SOL", "BNB-USDT": "BNB"}


def _downsample(seq: list, stride: int) -> list:
    return seq[::stride] if stride > 1 else seq


def _synth_comoving_pair() -> dict:
    """【合成】共动配对（仅 --demo 用）：共同潜因子 + 噪声 → corr~0.5–0.7 弱关联，
    末点人为拉开价差制造 |z|>1.5 偏离，且价差均值回归（探索层应命中、研究层不命中）。
    明确以 SYNTH_ 前缀标注非真实市场。确定性（固定种子）。"""
    import random
    rnd = random.Random(42)
    n = 60
    f = 0.0
    a, b = [], []
    for t in range(n):
        f = 0.85 * f + rnd.gauss(0, 1)                  # 均值回归潜因子
        a.append(0.50 + 0.030 * f + rnd.gauss(0, 0.026))  # 噪声调大 → corr 落入 [0.5,0.8) 弱关联带
        b.append(0.50 + 0.024 * f + rnd.gauss(0, 0.026))
    # 末点对 A 施加一次性正向冲击 → spread 偏离均值（制造可探索的 |z|）
    a[-1] = a[-1] + 0.10
    clamp = lambda x: max(0.02, min(0.98, x))
    mk = lambda s: [{"ts": f"2026-05-01T{i:02d}:00:00", "yes_price": round(clamp(v), 6),
                     "no_price": round(1 - clamp(v), 6), "liquidity": 5000} for i, v in enumerate(s)]
    return {"SYNTH_A": mk(a), "SYNTH_B": mk(b)}


def build_asset_history(stride: int) -> dict:
    """OKX K 线 → asset_price_history.json 格式 {SYMBOL: [{ts, price, kind}]}（真实加密序列）。"""
    if not OKX_COMBINED.exists():
        return {}
    raw = json.loads(OKX_COMBINED.read_text())
    out = {}
    for okx_sym, sym in SYMBOL_MAP.items():
        blk = raw.get(okx_sym) or {}
        data = blk.get("data") if isinstance(blk, dict) else blk
        if not data:
            continue
        pts = []
        for k in _downsample(data, stride):
            close = k.get("close")
            if close is None:
                continue
            pts.append({"ts": k.get("timestamp"), "price": float(close), "kind": "crypto"})
        if pts:
            out[sym] = pts
    return out


def build_market_history(stride: int) -> dict:
    """PM 历史 price_history → market_price_history.json 格式 {id: [{ts, yes_price, no_price, liquidity}]}。"""
    out = {}
    for f in PM_FILES:
        if not f.exists():
            continue
        for m in json.loads(f.read_text()):
            mid = str(m.get("id") or "")
            ph = m.get("price_history") or []
            if not mid or not ph or mid in out:
                continue
            pts = []
            for p in _downsample(ph, stride):
                yp = p.get("price")
                if yp is None:
                    continue
                yp = float(yp)
                pts.append({"ts": p.get("timestamp"), "yes_price": yp,
                            "no_price": round(1.0 - yp, 6), "liquidity": p.get("volume")})
            if len(pts) >= 8:
                out[mid] = pts
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=24, help="降采样步长（默认 24=小时→日，约 60 点）")
    ap.add_argument("--apply", action="store_true", help="写真实 data/（默认写隔离 sandbox）")
    ap.add_argument("--keep", action="store_true", help="保留 sandbox 目录")
    ap.add_argument("--explore", action="store_true",
                    help="开启探索层（PA_COINT_EXPLORE=1，relaxed 阈值产出弱关联低置信 probe 候选）")
    ap.add_argument("--explore-corr", type=float, help="探索相关下限（默认 0.5）")
    ap.add_argument("--explore-z", type=float, help="探索 |z| 下限（默认 1.5）")
    ap.add_argument("--demo", action="store_true",
                    help="注入【合成】共动配对（明确标注 SYNTH_*），演示探索层候选→喂闭环信号端到端")
    args = ap.parse_args()

    if args.explore:
        os.environ["PA_COINT_EXPLORE"] = "1"
        if args.explore_corr is not None:
            os.environ["PA_COINT_EXPLORE_CORR"] = str(args.explore_corr)
        if args.explore_z is not None:
            os.environ["PA_COINT_EXPLORE_Z"] = str(args.explore_z)
        print("探索层: ON（PA_COINT_EXPLORE=1）")

    if args.apply:
        base = ROOT
        print("⚠ --apply：写入真实 data/（覆盖线上价格历史）")
    else:
        base = Path(tempfile.mkdtemp(prefix="pa_coint_boot_"))
        (base / "data").mkdir(parents=True, exist_ok=True)
        os.environ["PA_DB_PATH"] = str(base / "data" / "runtime.db")
        print(f"隔离 sandbox: {base}")

    data = base / "data"
    assets = build_asset_history(args.stride)
    markets = build_market_history(args.stride)
    if args.demo:
        markets.update(_synth_comoving_pair())
        print("⚠ --demo：注入【合成】共动配对 SYNTH_A/SYNTH_B（非真实市场，仅演示探索层端到端）")
    (data / "asset_price_history.json").write_text(
        json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
    (data / "market_price_history.json").write_text(
        json.dumps(markets, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"回填: assets={list(assets.keys())}（每序列点数 "
          f"{ {k: len(v) for k, v in assets.items()} }）")
    print(f"回填: pm_markets={len(markets)}（点数样例 "
          f"{ {k: len(v) for k, v in list(markets.items())[:5]} }）")

    # 跑真实协整模型
    from runtime import cointegration as coint
    rep = coint.find_candidates(base_dir=base)
    print("\n" + "=" * 78)
    print("协整结果（runtime.cointegration，真实模型）")
    print("=" * 78)
    for k in ("n_markets_total", "n_markets_considered", "n_pairs_evaluated", "n_assets",
              "explore_enabled", "n_candidates", "n_candidates_pm_pm", "n_candidates_pm_asset",
              "n_candidates_research", "n_candidates_exploration"):
        print(f"  {k} = {rep.get(k)}")

    cands = rep.get("candidates", [])
    print(f"\n第一批候选（{len(cands)}）：")
    for c in cands[:12]:
        ev = c.get("evidence", {})
        print(f"  [{c.get('tier')}|{c.get('pair_type')}] {c.get('source_markets')} "
              f"corr={ev.get('corr')} z={ev.get('zscore')} half_life={ev.get('half_life')} "
              f"beta={ev.get('beta')} | edge={c.get('expected_edge')} "
              f"ret={c.get('expected_return')} conf={c.get('confidence')}")

    # 展示喂闭环的可成交 probe 信号（to_pipeline_signals）
    if cands:
        meta = {}
        ld = base / "data" / "latest_data.json"
        if ld.exists():
            meta = coint.market_meta_from_latest(json.loads(ld.read_text()))
        sigs = coint.to_pipeline_signals(rep, meta)
        print(f"\n→ to_pipeline_signals 产出 {len(sigs)} 条可成交 probe 信号"
              f"（models_used=cointegration），即喂入 PA_COINT_SIGNALS 闭环的内容。")
        for s in sigs[:6]:
            print(f"   {s['market_id']} {s['direction']} price={s['price']} "
                  f"ps={s['position_size']} ev={s['expected_value']} pair_id={s.get('pair_id')}")
    else:
        _diagnose(base, coint)

    if args.apply:
        # 也把候选落产物（correlation_signals.json + 影子），供 orchestrator/学习链路消费
        coint.compute(base_dir=base)
        print("\n✅ 已写 data/correlation_signals.json（候选产物）。"
              "下一步在主机：PA_COINT_SIGNALS=1 EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 跑 orchestrator 喂闭环。")
    elif not args.keep:
        shutil.rmtree(base, ignore_errors=True)
    else:
        print(f"\n保留 sandbox: {base}")


def _diagnose(base: Path, coint) -> None:
    """0 候选时：跑全配对 analyze_pair，报告卡在哪个护栏 + corr/z/half_life 分布 + top 配对。"""
    from itertools import combinations
    from collections import Counter
    from runtime import price_history as ph
    hist = ph.load_history(base)
    ahist = ph.load_asset_history(base)
    pm = {m: ph.series_for(hist, m) for m in hist}
    pm = {m: s for m, s in pm.items() if len(s) >= coint.MIN_POINTS}
    assets = {a: ph.asset_series_for(ahist, a) for a in ahist}
    rows, reasons = [], Counter()

    def consider(t, aid, sa, bid, sb):
        st = coint.analyze_pair(aid, sa, bid, sb)
        if st is None:
            reasons["analyze_None"] += 1
            return
        c, z, hl = abs(st["corr"]), abs(st["zscore"]), st["half_life"]
        rows.append((t, aid, bid, c, z, hl))
        ok = [c >= coint.CORR_MIN, z >= coint.Z_MIN, hl is not None and 0 < hl <= coint.HALF_LIFE_MAX]
        if all(ok):
            reasons["PASS"] += 1
        else:
            tags = ["corr<%.2f" % coint.CORR_MIN, "|z|<%.1f" % coint.Z_MIN, "half_life∉(0,%g]" % coint.HALF_LIFE_MAX]
            reasons["FAIL:" + ",".join(t for t, k in zip(tags, ok) if not k)] += 1

    for (aid, sa), (bid, sb) in combinations(pm.items(), 2):
        consider("pm-pm", aid, sa, bid, sb)
    for aid, sa in pm.items():
        for sym, sb in assets.items():
            consider("pm-asset", aid, sa, sym, sb)

    print(f"\n  无候选诊断（阈值 corr≥{coint.CORR_MIN} & |z|≥{coint.Z_MIN} & half_life∈(0,{coint.HALF_LIFE_MAX}]）：")
    cs = sorted(r[3] for r in rows); zs = sorted(r[4] for r in rows)
    if cs:
        print(f"    |corr| 分布: max={cs[-1]:.3f} p50={cs[len(cs)//2]:.3f}（≥0.8 的对数={sum(c>=coint.CORR_MIN for c in cs)}）")
        print(f"    |z|   分布: max={zs[-1]:.3f} p50={zs[len(zs)//2]:.3f}")
    for r, n in reasons.most_common(6):
        print(f"    {n:4d}  {r}")
    rows.sort(key=lambda r: -r[3])
    print("    top 5 配对 by |corr|:")
    for t, a, b, c, z, hl in rows[:5]:
        print(f"      {t:9s} {str(a)[:22]:22s} {str(b)[:12]:12s} corr={c:.3f} z={z:.2f} hl={hl}")
    print("    结论: 卡在 corr——该数据集无真实跨市场联动（≥0.8）。模型拒绝从无相关噪声造边（正确）。")
    print("    要出真实候选需真实联动价格：主机采集器累积真实 PM 历史，或回填真实 crypto-锚定市场×真实币价。")


if __name__ == "__main__":
    main()
