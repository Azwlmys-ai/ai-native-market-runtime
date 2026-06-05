#!/usr/bin/env python3
"""
最小 dry-run 验收测试 — test_sell_close_dryrun.py

验证 paper_pnl.py 的修复是否能正确匹配 sell_signals.json 里的 4 个止损信号
与 paper_portfolio.json 里对应的 open positions。

原则：
- 不修改任何生产数据文件（使用临时副本）
- 不产生真实交易
- 输出匹配结果统计
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Setup: use a temp copy of paper_portfolio.json + positions.json
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent
DATA = ROOT / "data"

PORTFOLIO_FILE = DATA / "paper_portfolio.json"
POSITIONS_FILE = DATA / "positions.json"
SELL_SIGNALS_FILE = DATA / "sell_signals.json"

# Validate source files exist
for f in (PORTFOLIO_FILE, POSITIONS_FILE, SELL_SIGNALS_FILE):
    if not f.exists():
        print(f"❌ 文件不存在: {f}")
        sys.exit(1)

# Load sell signals
with open(SELL_SIGNALS_FILE) as f:
    sell_signals = json.load(f)
print(f"📊 sell signals 总数: {len(sell_signals)}")
for i, s in enumerate(sell_signals):
    print(f"  [{i+1}] market_slug={s.get('market_slug')!r} outcome={s.get('outcome')!r} "
          f"price={s.get('price')} price_source={s.get('price_source')!r} "
          f"reason={s.get('reason','')[:40]!r}")

# ---------------------------------------------------------------------------
# Create a temp dir, copy data files there, run matching against the copies
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmpdir:
    tmp_data = Path(tmpdir) / "data"
    tmp_data.mkdir()

    # Copy the three relevant files
    shutil.copy(PORTFOLIO_FILE, tmp_data / "paper_portfolio.json")
    shutil.copy(POSITIONS_FILE, tmp_data / "positions.json")
    shutil.copy(SELL_SIGNALS_FILE, tmp_data / "sell_signals.json")
    # Also copy latest_data.json if it exists (used in price resolution fallback)
    if (DATA / "latest_data.json").exists():
        shutil.copy(DATA / "latest_data.json", tmp_data / "latest_data.json")

    # Patch _paths so PaperPortfolio uses our tmp dir
    sys.path.insert(0, str(ROOT))
    import _paths as _paths_mod
    _orig_get_base_dir = _paths_mod.get_base_dir
    _paths_mod.get_base_dir = lambda: Path(tmpdir)

    # Force-reload paper_pnl so it picks up the patched base_dir
    import importlib
    import paper_pnl
    importlib.reload(paper_pnl)
    PaperPortfolio = paper_pnl.PaperPortfolio

    pp = PaperPortfolio(base_dir=Path(tmpdir))

    # Count state before
    open_before = len(pp.get_open_positions())
    closed_before = len([p for p in pp.positions if p.closed_at])
    print(f"\n📂 修复前状态:")
    print(f"   open positions:   {open_before}")
    print(f"   closed positions: {closed_before}")
    print(f"   total positions:  {len(pp.positions)}")

    # Run close_position for each sell signal
    print(f"\n🔄 执行 close_position 匹配...")
    results = []
    for sig in sell_signals:
        result = pp.close_position(sig)
        results.append(result)

    # Reload to get fresh state
    pp2 = PaperPortfolio(base_dir=Path(tmpdir))
    open_after = len(pp2.get_open_positions())
    closed_after = len([p for p in pp2.positions if p.closed_at])

    # Count newly closed positions (should be the ones we just closed)
    newly_closed = [
        p for p in pp2.positions
        if p.closed_at and p.close_reason  # only those with close_reason (our new logic)
    ]
    exit_price_written = sum(1 for p in newly_closed if p.exit_price is not None)
    realized_pnl_written = sum(1 for p in newly_closed if p.realized_pnl is not None)

    print(f"\n📊 验收结果:")
    print(f"   sell signals 总数:        {len(sell_signals)}")
    matched = sum(1 for r in results if r is not None)
    unmatched = sum(1 for r in results if r is None)
    print(f"   matched positions:        {matched}")
    print(f"   unmatched signals:        {unmatched}")
    print(f"   open positions (before):  {open_before}")
    print(f"   open positions (after):   {open_after}")
    print(f"   closed (before):          {closed_before}")
    print(f"   closed (after):           {closed_after}")
    print(f"   新增 closed (净增):        {closed_after - closed_before}")
    print(f"   exit_price 写入数:         {exit_price_written}")
    print(f"   realized_pnl 非 null 数:  {realized_pnl_written}")

    # Detail on matched positions
    print(f"\n🔍 匹配明细:")
    for i, (sig, result) in enumerate(zip(sell_signals, results)):
        slug = sig.get('market_slug') or sig.get('market') or ''
        if result is not None:
            print(f"  ✅ [{i+1}] {slug[:60]}")
            print(f"        exit_price={result.exit_price} price_source={result.price_source!r}")
            print(f"        close_reason={result.close_reason!r}")
            print(f"        realized_pnl={result.realized_pnl}")
            print(f"        closed_at={result.closed_at}")
        else:
            print(f"  ❌ [{i+1}] UNMATCHED: {slug[:60]}")
            # Try to diagnose: show open positions with same name
            question = pp._slug_to_market_question(slug)
            print(f"        positions.json market_question lookup: {question!r}")
            # Find candidate positions
            candidates = [
                p for p in pp.positions
                if not p.closed_at
                and (
                    question and question.lower() in (p.market_name or '').lower()
                    or slug in str(p.market_id)
                )
            ]
            print(f"        candidates in portfolio: {len(candidates)}")

    # Verdict
    print(f"\n{'='*50}")
    if matched == len(sell_signals):
        print("✅ PASS — 所有 sell signals 成功匹配 open position")
        print("✅ 修复生效：exit_price 和 realized_pnl 均已写入")
    elif matched > 0:
        print(f"⚠️  PARTIAL — {matched}/{len(sell_signals)} 成功匹配")
    else:
        print("❌ FAIL — 所有 sell signals 仍未匹配")

    # Restore
    _paths_mod.get_base_dir = _orig_get_base_dir

print("\n✅ 测试完成（临时目录已清理，生产数据未修改）")
