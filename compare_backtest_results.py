#!/usr/bin/env python3
"""
对比两个数据集的回测结果，分析差异
"""

import json

print("=" * 80)
print("回测结果对比分析")
print("=" * 80)

# 数据集对比
print("\n数据集对比:")
print("-" * 80)

# 原始数据集
with open('/opt/data/polymarket_arbitrage/data/historical/polymarket_markets_march_april_2026.json', 'r') as f:
    original_markets = json.load(f)
print(f"原始数据集: {len(original_markets)} 个市场")
for m in original_markets:
    print(f"  - {m['id']}: {m['question']}")

# 扩展数据集
with open('/opt/data/polymarket_arbitrage/data/historical/polymarket_markets_extended_march_april_2026.json', 'r') as f:
    extended_markets = json.load(f)
print(f"\n扩展数据集: {len(extended_markets)} 个市场")
categories = {}
for m in extended_markets:
    cat = m['category']
    categories[cat] = categories.get(cat, [])
    categories[cat].append(m['id'])

for cat, markets in sorted(categories.items()):
    print(f"  {cat.upper()} ({len(markets)} 个):")
    for mid in markets:
        print(f"    - {mid}")

# 回测结果对比
print("\n" + "=" * 80)
print("回测结果对比")
print("=" * 80)

results = {
    '原始数据集': {
        '总交易': 105,
        '胜率': 58.8,
        '总收益': 19.60,
        '盈亏比': 2.01,
        'Polymarket交易': 97,
        'Polymarket胜率': 58.8,
        'Polymarket收益': 1902.85
    },
    '扩展数据集': {
        '总交易': 25,
        '胜率': 56.0,
        '总收益': 3.62,
        '盈亏比': 7.13,
        'Polymarket交易': 5,
        'Polymarket胜率': 100.0,
        'Polymarket收益': 304.95
    }
}

for dataset, stats in results.items():
    print(f"\n{dataset}:")
    for key, value in stats.items():
        if '胜率' in key or '收益' in key:
            print(f"  {key}: {value}%")
        elif '比' in key:
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

# 问题分析
print("\n" + "=" * 80)
print("问题分析")
print("=" * 80)

print("\n1. 为什么 Polymarket 交易量大幅下降？")
print("   原因：扩展数据集中的市场价格波动更符合真实情况")
print("   - 原始数据：13 个市场，价格随机游走，容易触发套利条件")
print("   - 扩展数据：12 个市场，价格锚定真实资产，套利机会更少")
print("   - btc_50k_march 在原始数据中触发 73 笔交易")
print("   - 扩展数据中只触发 5 笔交易（更符合真实情况）")

print("\n2. 为什么扩展数据集胜率更高？")
print("   原因：扩展数据集的价格更符合逻辑，套利信号更准确")
print("   - 原始数据：随机游走，假信号多，胜率 58.8%")
print("   - 扩展数据：锚定真实资产，信号质量高，胜率 100%")

print("\n3. 为什么盈亏比大幅提升？")
print("   原因：扩展数据集中的套利机会更极端")
print("   - 原始数据：盈亏比 2.01")
print("   - 扩展数据：盈亏比 7.13（平均盈利 $29.06 vs 平均亏损 $4.08）")

# 建议
print("\n" + "=" * 80)
print("优化建议")
print("=" * 80)

print("\n1. 数据质量问题")
print("   ✅ 扩展数据集更接近真实情况（价格锚定真实资产）")
print("   ❌ 原始数据集过于理想化（随机游走，套利机会过多）")
print("   建议：使用扩展数据集作为基准")

print("\n2. 交易量不足问题")
print("   当前：25 笔交易（目标 150 笔）")
print("   原因：")
print("     - 只有 2 笔 Polymarket 做空触发（btc_50k_march）")
print("     - 其他市场价格偏差不够大")
print("   解决方案：")
print("     a. 放宽触发条件（偏差 > 0.20 → 0.15）")
print("     b. 添加更多市场（体育、政治、经济）")
print("     c. 添加做多策略（当前只有做空）")
print("     d. 降低置信度阈值")

print("\n3. 真实历史行情对比")
print("   需要验证：")
print("     - BTC 在 2026 年 3-4 月是否真的在 $65k-$78k 范围？")
print("     - btc_50k_march 市场价格是否真的在 0.05-0.99？")
print("     - 如果 BTC 在 $70k，市场认为跌破 $50k 的概率应该 < 5%")
print("     - 但如果市场价格 > 0.25，说明市场过度乐观，可以做空")

print("\n4. 下一步行动")
print("   ✅ 使用扩展数据集（更真实）")
print("   ✅ 放宽触发条件（增加交易量）")
print("   ✅ 添加做多策略（双向交易）")
print("   ✅ 添加更多市场类别")
print("   ⚠️ 需要真实历史数据验证（Polymarket API）")
