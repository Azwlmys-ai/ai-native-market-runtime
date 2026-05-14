#!/usr/bin/env python3
"""
分析 Polymarket 策略失败原因
"""

import json
from pathlib import Path
from collections import defaultdict

# 加载交易记录
with open('/opt/data/polymarket_arbitrage/data/cross_market_backtest_trades.json', 'r') as f:
    trades = json.load(f)

# 分析 Polymarket 交易
pm_trades = [t for t in trades if t['market'] == 'polymarket']

print(f"Polymarket 交易分析")
print("=" * 80)
print(f"总交易: {len(pm_trades)} 笔")

# 按资产统计
assets = defaultdict(lambda: {'count': 0, 'profit': 0, 'wins': 0})
for t in pm_trades:
    asset = t['asset']
    assets[asset]['count'] += 1
    assets[asset]['profit'] += t['profit']
    if t['profit'] > 0:
        assets[asset]['wins'] += 1

print("\n按资产统计:")
for asset, stats in sorted(assets.items()):
    win_rate = stats['wins'] / stats['count'] if stats['count'] > 0 else 0
    print(f"  {asset}: {stats['count']} 笔, 胜率 {win_rate*100:.1f}%, ${stats['profit']:.2f}")

# 分析价格范围
print("\n价格分析:")
entry_prices = [t['entry_price'] for t in pm_trades]
exit_prices = [t['exit_price'] for t in pm_trades]
print(f"  入场价格范围: {min(entry_prices):.2f} - {max(entry_prices):.2f}")
print(f"  出场价格范围: {min(exit_prices):.2f} - {max(exit_prices):.2f}")

# 分析盈亏分布
profits = [t['profit'] for t in pm_trades]
print(f"\n盈亏分布:")
print(f"  最大盈利: ${max(profits):.2f}")
print(f"  最大亏损: ${min(profits):.2f}")
print(f"  平均盈利: ${sum(p for p in profits if p > 0) / len([p for p in profits if p > 0]):.2f}")
print(f"  平均亏损: ${sum(p for p in profits if p < 0) / len([p for p in profits if p < 0]):.2f}")

# 分析退出原因
exit_reasons = defaultdict(lambda: {'count': 0, 'profit': 0})
for t in pm_trades:
    reason = t['exit_reason']
    exit_reasons[reason]['count'] += 1
    exit_reasons[reason]['profit'] += t['profit']

print(f"\n退出原因:")
for reason, stats in sorted(exit_reasons.items()):
    print(f"  {reason}: {stats['count']} 笔, ${stats['profit']:.2f}")

# 分析问题
print("\n" + "=" * 80)
print("问题诊断:")

# 检查 btc_50k_march 市场
btc_50k_trades = [t for t in pm_trades if t['asset'] == 'btc_50k_march']
if btc_50k_trades:
    print(f"\n1. btc_50k_march 市场问题:")
    print(f"   - 这是一个 'BTC 跌破 $50k' 的市场")
    print(f"   - BTC 价格范围: $65k - $76k（远高于 $50k）")
    print(f"   - 隐含概率应该很低（< 0.10），但市场价格很高（0.45 - 0.99）")
    print(f"   - 策略买入高价 NO（认为不会跌破），但市场继续上涨")
    print(f"   - 问题: 买入方向错误！应该卖出 YES（做空），而不是买入")
