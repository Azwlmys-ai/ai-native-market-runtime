#!/usr/bin/env python3
"""
分析回测结果，评估风险，优化资金分配
"""

import json
from collections import defaultdict
import statistics

# 加载交易记录
with open('/opt/data/polymarket_arbitrage/data/cross_market_backtest_trades.json', 'r') as f:
    trades = json.load(f)

print("=" * 80)
print("跨市场交易系统风险评估与优化建议")
print("=" * 80)

# 1. 按市场统计
markets = defaultdict(lambda: {
    'trades': [],
    'wins': 0,
    'losses': 0,
    'total_profit': 0,
    'max_profit': 0,
    'max_loss': 0,
    'avg_profit': 0,
    'avg_loss': 0
})

for t in trades:
    market = t['market']
    markets[market]['trades'].append(t)
    markets[market]['total_profit'] += t['profit']
    
    if t['profit'] > 0:
        markets[market]['wins'] += 1
        markets[market]['max_profit'] = max(markets[market]['max_profit'], t['profit'])
    else:
        markets[market]['losses'] += 1
        markets[market]['max_loss'] = min(markets[market]['max_loss'], t['profit'])

print("\n1. 市场表现分析")
print("-" * 80)

for market, stats in sorted(markets.items()):
    total = len(stats['trades'])
    win_rate = stats['wins'] / total if total > 0 else 0
    
    profits = [t['profit'] for t in stats['trades'] if t['profit'] > 0]
    losses = [t['profit'] for t in stats['trades'] if t['profit'] < 0]
    
    avg_profit = statistics.mean(profits) if profits else 0
    avg_loss = statistics.mean(losses) if losses else 0
    profit_factor = abs(avg_profit / avg_loss) if avg_loss != 0 else 0
    
    print(f"\n{market.upper()}:")
    print(f"  交易数: {total} 笔")
    print(f"  胜率: {win_rate*100:.1f}%")
    print(f"  总收益: ${stats['total_profit']:.2f}")
    print(f"  平均盈利: ${avg_profit:.2f}")
    print(f"  平均亏损: ${avg_loss:.2f}")
    print(f"  盈亏比: {profit_factor:.2f}")
    print(f"  最大盈利: ${stats['max_profit']:.2f}")
    print(f"  最大亏损: ${stats['max_loss']:.2f}")
    
    # 风险评估
    if win_rate >= 0.50 and profit_factor >= 2.0:
        risk_level = "✅ 低风险"
    elif win_rate >= 0.40 and profit_factor >= 1.5:
        risk_level = "⚠️ 中风险"
    else:
        risk_level = "❌ 高风险"
    
    print(f"  风险等级: {risk_level}")

# 2. Polymarket 详细分析
print("\n" + "=" * 80)
print("2. Polymarket 详细分析")
print("-" * 80)

pm_trades = [t for t in trades if t['market'] == 'polymarket']
pm_assets = defaultdict(lambda: {'trades': [], 'profit': 0, 'wins': 0})

for t in pm_trades:
    asset = t['asset']
    pm_assets[asset]['trades'].append(t)
    pm_assets[asset]['profit'] += t['profit']
    if t['profit'] > 0:
        pm_assets[asset]['wins'] += 1

print("\n按资产统计:")
for asset, stats in sorted(pm_assets.items(), key=lambda x: x[1]['profit'], reverse=True):
    total = len(stats['trades'])
    win_rate = stats['wins'] / total if total > 0 else 0
    print(f"  {asset}: {total} 笔, 胜率 {win_rate*100:.1f}%, ${stats['profit']:.2f}")

# 分析做多 vs 做空
longs = [t for t in pm_trades if not t.get('is_short', False)]
shorts = [t for t in pm_trades if t.get('is_short', False)]

print(f"\n做多 vs 做空:")
print(f"  做多: {len(longs)} 笔, ${sum(t['profit'] for t in longs):.2f}")
print(f"  做空: {len(shorts)} 笔, ${sum(t['profit'] for t in shorts):.2f}")

# 3. 风险指标
print("\n" + "=" * 80)
print("3. 风险指标")
print("-" * 80)

all_profits = [t['profit'] for t in trades]
all_pnl_pct = [t['pnl_percent'] for t in trades]

print(f"\n收益波动性:")
print(f"  标准差: ${statistics.stdev(all_profits):.2f}")
print(f"  最大回撤: {min(all_pnl_pct)*100:.2f}%")
print(f"  最大盈利: {max(all_pnl_pct)*100:.2f}%")

# 连续亏损分析
max_consecutive_losses = 0
current_consecutive_losses = 0

for t in trades:
    if t['profit'] < 0:
        current_consecutive_losses += 1
        max_consecutive_losses = max(max_consecutive_losses, current_consecutive_losses)
    else:
        current_consecutive_losses = 0

print(f"\n连续亏损:")
print(f"  最大连续亏损: {max_consecutive_losses} 笔")

# 4. 资金分配优化建议
print("\n" + "=" * 80)
print("4. 资金分配优化建议")
print("-" * 80)

total_trades = len(trades)
total_profit = sum(t['profit'] for t in trades)

print(f"\n当前配置:")
print(f"  Polymarket: 30% (4 持仓)")
print(f"  加密货币: 40% (4 持仓)")
print(f"  美股: 20% (2 持仓)")
print(f"  A股: 10% (2 持仓)")

# 计算每个市场的收益贡献
market_contributions = {}
for market, stats in markets.items():
    contribution = stats['total_profit'] / total_profit if total_profit > 0 else 0
    market_contributions[market] = contribution

print(f"\n实际收益贡献:")
for market, contribution in sorted(market_contributions.items(), key=lambda x: x[1], reverse=True):
    print(f"  {market}: {contribution*100:.1f}%")

# 优化建议
print(f"\n优化建议:")

pm_win_rate = markets['polymarket']['wins'] / len(markets['polymarket']['trades'])
pm_profit_factor = abs(
    statistics.mean([t['profit'] for t in markets['polymarket']['trades'] if t['profit'] > 0]) /
    statistics.mean([t['profit'] for t in markets['polymarket']['trades'] if t['profit'] < 0])
)

if pm_win_rate >= 0.50 and pm_profit_factor >= 2.0:
    print(f"  ✅ Polymarket 表现优异（胜率 {pm_win_rate*100:.1f}%，盈亏比 {pm_profit_factor:.2f}）")
    print(f"  建议: 提高 Polymarket 权重至 50-60%")
    print(f"  建议: 增加持仓限制至 6-8 个")
    print(f"  建议: 提高交易总量至 150-200 笔")
else:
    print(f"  ⚠️ Polymarket 需要进一步优化")

# 美股建议
if len(markets['us_stocks']['trades']) < 5:
    print(f"\n  ⚠️ 美股交易量过低（{len(markets['us_stocks']['trades'])} 笔）")
    print(f"  建议: 放宽 BTC vs COIN 联动阈值")
    print(f"  建议: 添加更多美股策略（MSTR、RIOT、MARA）")

# A股建议
if 'cn_stocks' not in markets or len(markets['cn_stocks']['trades']) == 0:
    print(f"\n  ❌ A股无交易")
    print(f"  建议: 添加 A股 vs 港股联动策略")
    print(f"  建议: 注意 T+1 限制，只做日内买入，次日卖出")
    print(f"  建议: 降低 A股权重至 5%")

# 5. 优化后的配置
print("\n" + "=" * 80)
print("5. 推荐配置（基于回测结果）")
print("-" * 80)

print(f"\n资金分配:")
print(f"  Polymarket: 55% (6 持仓) - 核心策略")
print(f"  加密货币: 30% (4 持仓) - 辅助策略")
print(f"  美股: 10% (2 持仓) - 探索策略")
print(f"  A股: 5% (1 持仓) - 试验策略")

print(f"\n交易目标:")
print(f"  总交易量: 150-200 笔")
print(f"  Polymarket: 100-120 笔（做空为主）")
print(f"  加密货币: 30-40 笔（超卖反弹）")
print(f"  美股: 10-20 笔（联动套利）")
print(f"  A股: 10-20 笔（T+1 套利）")

print(f"\n风险控制:")
print(f"  单笔最大亏损: -10%")
print(f"  最大连续亏损: 5 笔（暂停交易）")
print(f"  日内最大回撤: -5%（降低仓位）")
print(f"  Polymarket 集中度: 单一市场 < 30%")
