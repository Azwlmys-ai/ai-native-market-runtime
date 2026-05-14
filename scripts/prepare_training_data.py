#!/usr/bin/env python3
"""
从历史交易数据中提取训练集和测试集
- 训练集: 前 70 条交易 (70%)
- 测试集: 后 30 条交易 (30%)
"""

import json
import subprocess
from datetime import datetime

def get_historical_trades():
    """获取历史交易数据"""
    result = subprocess.run(
        ['/opt/data/home/.local/bin/pm-trader', 'history', '--limit', '100'],
        capture_output=True,
        text=True,
        cwd='/opt/data/polymarket_arbitrage'
    )
    
    if result.returncode != 0:
        raise Exception(f"获取历史交易失败: {result.stderr}")
    
    data = json.loads(result.stdout)
    if not data.get('ok'):
        raise Exception("API 返回失败")
    
    return data['data']

def split_dataset(trades):
    """分割数据集"""
    # 按时间排序（最早的在前）
    trades_sorted = sorted(trades, key=lambda x: x['created_at'])
    
    total = len(trades_sorted)
    train_size = int(total * 0.7)
    
    train_set = trades_sorted[:train_size]
    test_set = trades_sorted[train_size:]
    
    return train_set, test_set

def extract_features(trade):
    """提取交易特征"""
    return {
        'market_slug': trade['market_slug'],
        'market_question': trade['market_question'],
        'outcome': trade['outcome'],
        'side': trade['side'],
        'avg_price': trade['avg_price'],
        'amount_usd': trade['amount_usd'],
        'shares': trade['shares'],
        'slippage': trade['slippage'],
        'levels_filled': trade['levels_filled'],
        'created_at': trade['created_at']
    }

def calculate_pnl(trade, portfolio):
    """计算交易盈亏（需要匹配买入/卖出）"""
    # 简化版本：仅记录交易信息，实际 PnL 需要匹配买卖对
    return {
        **extract_features(trade),
        'is_buy': trade['side'] == 'buy',
        'is_sell': trade['side'] == 'sell'
    }

def main():
    print("📊 开始准备训练数据...")
    print("="*60)
    
    # 1. 获取历史交易
    print("\n1️⃣ 获取历史交易数据...")
    trades = get_historical_trades()
    print(f"   ✅ 获取 {len(trades)} 条交易记录")
    
    # 2. 分割数据集
    print("\n2️⃣ 分割数据集...")
    train_set, test_set = split_dataset(trades)
    print(f"   ✅ 训练集: {len(train_set)} 条 (70%)")
    print(f"   ✅ 测试集: {len(test_set)} 条 (30%)")
    
    # 3. 提取特征
    print("\n3️⃣ 提取交易特征...")
    train_features = [calculate_pnl(t, {}) for t in train_set]
    test_features = [calculate_pnl(t, {}) for t in test_set]
    
    # 4. 保存数据集
    print("\n4️⃣ 保存数据集...")
    with open('data/train_trades.json', 'w') as f:
        json.dump({
            'total': len(train_features),
            'trades': train_features
        }, f, indent=2)
    print(f"   ✅ 训练集保存到 data/train_trades.json")
    
    with open('data/test_trades.json', 'w') as f:
        json.dump({
            'total': len(test_features),
            'trades': test_features
        }, f, indent=2)
    print(f"   ✅ 测试集保存到 data/test_trades.json")
    
    # 5. 统计分析
    print("\n5️⃣ 数据集统计:")
    print(f"   训练集时间范围: {train_set[0]['created_at']} → {train_set[-1]['created_at']}")
    print(f"   测试集时间范围: {test_set[0]['created_at']} → {test_set[-1]['created_at']}")
    
    train_buy = sum(1 for t in train_set if t['side'] == 'buy')
    train_sell = sum(1 for t in train_set if t['side'] == 'sell')
    test_buy = sum(1 for t in test_set if t['side'] == 'buy')
    test_sell = sum(1 for t in test_set if t['side'] == 'sell')
    
    print(f"\n   训练集: {train_buy} 买入, {train_sell} 卖出")
    print(f"   测试集: {test_buy} 买入, {test_sell} 卖出")
    
    print("\n✅ 数据准备完成")

if __name__ == '__main__':
    main()
