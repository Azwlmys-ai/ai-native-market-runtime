#!/usr/bin/env python3
"""
Agent Validator - 在测试集上验证学习到的策略
使用学习到的规则模拟交易决策，对比实际结果
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def load_test_data():
    """加载测试集"""
    with open('data/test_trades.json', 'r') as f:
        data = json.load(f)
    return data['trades']

def load_learned_rules():
    """加载学习到的规则"""
    with open('data/learned_rules.json', 'r') as f:
        data = json.load(f)
    return data['learned_rules']

def classify_market(question):
    """分类市场类型"""
    question_lower = question.lower()
    if 'nhl' in question_lower or 'stanley cup' in question_lower:
        return 'NHL'
    elif 'gta vi' in question_lower or 'gta 6' in question_lower:
        return 'GTA_VI'
    elif 'nba' in question_lower:
        return 'NBA'
    else:
        return 'Other'

def should_trade(trade, rules):
    """根据学习到的规则判断是否应该交易"""
    market_type = classify_market(trade['market_question'])
    price = trade['avg_price']
    
    # 检查市场类型
    avoid_markets = [m['market_type'] for m in rules['market_rules']['avoid']]
    if market_type in avoid_markets:
        return False, f"避免 {market_type} 市场（流动性问题）"
    
    recommended_markets = [m['market_type'] for m in rules['market_rules']['recommended']]
    if market_type not in recommended_markets:
        return False, f"{market_type} 不在推荐市场列表"
    
    # 检查价格区间
    if 0.4 <= price <= 0.6:
        expected_action = 'buy_NO'
        if trade['side'] == 'buy' and trade['outcome'] == 'no':
            return True, f"符合中间价格区间策略（买 NO）"
        else:
            return False, f"中间价格区间应买 NO，实际 {trade['side']} {trade['outcome']}"
    
    if price >= 0.8:
        if market_type == 'NHL' and abs(trade['slippage']) < 50:
            expected_action = 'buy_NO'
            if trade['side'] == 'buy' and trade['outcome'] == 'no':
                return True, f"符合极端高价 NHL 策略（买 NO，低滑点）"
            else:
                return False, f"极端高价 NHL 应买 NO，实际 {trade['side']} {trade['outcome']}"
        else:
            return False, f"极端高价需 NHL + 低滑点条件"
    
    # 检查滑点
    max_slippage = 600  # 默认阈值
    for market_rule in rules['market_rules']['recommended']:
        if market_rule['market_type'] == market_type:
            max_slippage = market_rule['max_slippage']
            break
    
    if abs(trade['slippage']) > max_slippage:
        return False, f"滑点 {abs(trade['slippage']):.1f} bps 超过阈值 {max_slippage} bps"
    
    return True, "符合基本交易条件"

def validate_strategy():
    """验证策略准确性"""
    print("🔍 Agent Validator - 验证学习到的策略")
    print("="*60)
    
    # 1. 加载数据
    print("\n1️⃣ 加载测试集和学习规则...")
    test_trades = load_test_data()
    learned_rules = load_learned_rules()
    print(f"   ✅ 测试集: {len(test_trades)} 条交易")
    
    # 2. 逐笔验证
    print("\n2️⃣ 逐笔验证交易决策...")
    results = []
    
    for i, trade in enumerate(test_trades, 1):
        should_execute, reason = should_trade(trade, learned_rules)
        
        # 实际是否执行（买入 = 执行，卖出 = 未执行或平仓）
        actually_executed = trade['is_buy']
        
        # 判断预测是否正确
        correct = (should_execute == actually_executed)
        
        result = {
            'trade_id': i,
            'market': trade['market_question'][:50] + '...',
            'market_type': classify_market(trade['market_question']),
            'price': trade['avg_price'],
            'slippage': trade['slippage'],
            'actual_side': trade['side'],
            'predicted': 'TRADE' if should_execute else 'SKIP',
            'actual': 'TRADE' if actually_executed else 'SKIP',
            'correct': correct,
            'reason': reason
        }
        
        results.append(result)
        
        status = "✅" if correct else "❌"
        print(f"   {status} 交易 {i}: {result['market']}")
        print(f"      预测: {result['predicted']}, 实际: {result['actual']}")
        print(f"      原因: {reason}")
    
    # 3. 统计准确率
    print("\n3️⃣ 统计验证结果...")
    total = len(results)
    correct_count = sum(1 for r in results if r['correct'])
    accuracy = correct_count / total * 100
    
    print(f"   总交易数: {total}")
    print(f"   预测正确: {correct_count}")
    print(f"   预测错误: {total - correct_count}")
    print(f"   准确率: {accuracy:.1f}%")
    
    # 4. 分市场类型统计
    print("\n4️⃣ 分市场类型统计...")
    from collections import defaultdict
    market_stats = defaultdict(lambda: {'total': 0, 'correct': 0})
    
    for result in results:
        market_type = result['market_type']
        market_stats[market_type]['total'] += 1
        if result['correct']:
            market_stats[market_type]['correct'] += 1
    
    for market_type, stats in market_stats.items():
        acc = stats['correct'] / stats['total'] * 100
        print(f"   {market_type}: {stats['correct']}/{stats['total']} ({acc:.1f}%)")
    
    # 5. 保存验证结果
    output = {
        'timestamp': datetime.now().isoformat(),
        'test_size': total,
        'accuracy': accuracy,
        'correct_count': correct_count,
        'results': results,
        'market_stats': {k: {'total': v['total'], 'correct': v['correct'], 'accuracy': v['correct']/v['total']*100} 
                        for k, v in market_stats.items()}
    }
    
    with open('data/validation_results.json', 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 验证完成，结果保存到 data/validation_results.json")
    
    # 6. 结论
    print("\n" + "="*60)
    if accuracy >= 70:
        print(f"🎉 策略验证通过！准确率 {accuracy:.1f}% >= 70%")
        print("   建议：可以将学习到的规则集成到生产系统")
    elif accuracy >= 50:
        print(f"⚠️  策略表现一般，准确率 {accuracy:.1f}%")
        print("   建议：需要更多训练数据或调整规则")
    else:
        print(f"❌ 策略验证失败，准确率 {accuracy:.1f}% < 50%")
        print("   建议：重新分析训练数据，调整学习方法")
    
    return accuracy

if __name__ == '__main__':
    validate_strategy()
