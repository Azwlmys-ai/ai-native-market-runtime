#!/usr/bin/env python3
"""
Agent Learning - 从历史交易中学习策略模式
分析训练集，提取成功交易的特征，生成决策规则
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm, load_llm_config

DEFAULT_MODEL = "deepseek-v4-pro"


def _get_model_for_agent_learning() -> str:
    """从 config/llm_config.json 的 agent_models 读取 agent_learning 专属模型名。
    如果缺失，回退到统一默认模型 deepseek-v4-pro。
    """
    try:
        config = load_llm_config()
        agent_models = config.get("agent_models", {})
        return agent_models.get("agent_learning", DEFAULT_MODEL)
    except Exception:
        return DEFAULT_MODEL

def load_training_data():
    """加载训练集"""
    with open('data/train_trades.json', 'r') as f:
        data = json.load(f)
    return data['trades']

def analyze_trade_patterns(trades):
    """分析交易模式"""
    patterns = {
        'market_types': defaultdict(list),
        'price_ranges': defaultdict(list),
        'slippage_stats': [],
        'outcome_distribution': defaultdict(int)
    }
    
    for trade in trades:
        # 市场类型分类
        question = trade['market_question'].lower()
        if 'nhl' in question or 'stanley cup' in question:
            market_type = 'NHL'
        elif 'gta vi' in question or 'gta 6' in question:
            market_type = 'GTA_VI'
        elif 'nba' in question:
            market_type = 'NBA'
        elif 'bitcoin' in question or 'btc' in question:
            market_type = 'Crypto'
        else:
            market_type = 'Other'
        
        patterns['market_types'][market_type].append({
            'price': trade['avg_price'],
            'slippage': trade['slippage'],
            'side': trade['side']
        })
        
        # 价格区间
        price = trade['avg_price']
        if price < 0.1:
            price_range = 'extreme_low'
        elif price < 0.3:
            price_range = 'low'
        elif price < 0.7:
            price_range = 'mid'
        elif price < 0.9:
            price_range = 'high'
        else:
            price_range = 'extreme_high'
        
        patterns['price_ranges'][price_range].append(trade)
        
        # 滑点统计
        patterns['slippage_stats'].append(abs(trade['slippage']))
        
        # 结果分布
        patterns['outcome_distribution'][trade['outcome']] += 1
    
    return patterns

def generate_learning_prompt(trades, patterns):
    """生成学习 Prompt"""
    # 计算统计数据
    total_trades = len(trades)
    buy_trades = sum(1 for t in trades if t['side'] == 'buy')
    sell_trades = total_trades - buy_trades
    
    avg_slippage = sum(patterns['slippage_stats']) / len(patterns['slippage_stats']) if patterns['slippage_stats'] else 0
    
    market_summary = []
    for market_type, trades_list in patterns['market_types'].items():
        avg_price = sum(t['price'] for t in trades_list) / len(trades_list)
        avg_slip = sum(abs(t['slippage']) for t in trades_list) / len(trades_list)
        market_summary.append(f"  - {market_type}: {len(trades_list)} 笔, 平均价格 {avg_price:.3f}, 平均滑点 {avg_slip:.1f} bps")
    
    prompt = f"""你是 Polymarket 交易策略学习专家。分析以下历史交易数据，提取成功的交易模式和决策规则。

## 训练集概况
- 总交易数: {total_trades} 笔
- 买入: {buy_trades} 笔, 卖出: {sell_trades} 笔
- 平均滑点: {avg_slippage:.1f} bps

## 市场类型分布
{chr(10).join(market_summary)}

## 价格区间分布
{json.dumps({k: len(v) for k, v in patterns['price_ranges'].items()}, indent=2)}

## 结果分布
{json.dumps(dict(patterns['outcome_distribution']), indent=2)}

## 任务
基于以上数据，提取以下决策规则：

1. **市场选择规则**: 哪些市场类型值得交易？哪些应该避免？
2. **价格区间策略**: 不同价格区间的最佳交易方向（买 YES/NO）
3. **滑点控制**: 可接受的滑点范围
4. **仓位管理**: 不同市场类型的建议仓位大小
5. **风险信号**: 哪些特征预示高风险交易？

输出 JSON 格式的决策规则，包含：
- market_rules: 市场类型规则
- price_rules: 价格区间规则
- risk_thresholds: 风险阈值
- position_sizing: 仓位管理规则

要求：
- 基于数据事实，不要臆测
- 规则必须可量化、可执行
- 考虑滑点、流动性等实际交易成本
"""
    
    return prompt

def learn_from_history():
    """从历史中学习"""
    print("🧠 Agent Learning - 从历史交易中学习策略")
    print("="*60)
    
    # 1. 加载训练数据
    print("\n1️⃣ 加载训练集...")
    trades = load_training_data()
    print(f"   ✅ 加载 {len(trades)} 条交易记录")
    
    # 2. 分析交易模式
    print("\n2️⃣ 分析交易模式...")
    patterns = analyze_trade_patterns(trades)
    print(f"   ✅ 识别 {len(patterns['market_types'])} 种市场类型")
    print(f"   ✅ 识别 {len(patterns['price_ranges'])} 个价格区间")
    
    # 3. 调用 LLM 学习
    print("\n3️⃣ 调用 LLM 学习决策规则...")
    prompt = generate_learning_prompt(trades, patterns)

    _model = _get_model_for_agent_learning()
    learned_rules = None
    raw_response = None
    llm_available = True
    fallback_used = False

    try:
        response_text = call_llm(
            prompt=prompt,
            model=_model,
            temperature=0.1,
            max_tokens=4000,
            timeout=120,
        )
        raw_response = response_text
    except Exception as e:
        print(f"   ⚠️  LLM 调用失败: {e}")
        llm_available = False
        fallback_used = True

    # 4. 解析学习结果
    print("\n4️⃣ 解析学习结果...")
    if llm_available and raw_response:
        try:
            content = raw_response
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()

            learned_rules = json.loads(content)
        except Exception as e:
            print(f"   ❌ 解析失败: {e}")
            print(f"\n原始响应:\n{raw_response[:500]}")
            learned_rules = None

    if learned_rules is None:
        # Structured learning_skipped fallback
        learned_rules = {"learning_skipped": True, "fallback_used": True, "reason": "LLM unavailable or parse error"}

    # 5. 保存学习结果
    output = {
        'timestamp': datetime.now().isoformat(),
        'training_size': len(trades),
        'learned_rules': learned_rules,
        'raw_response': raw_response,
        'llm_available': llm_available,
        'fallback_used': fallback_used,
    }

    try:
        Path('data').mkdir(exist_ok=True)
        with open('data/learned_rules.json', 'w') as f:
            json.dump(output, f, indent=2)
    except Exception as e:
        print(f"   ⚠️  保存结果失败: {e}")

    print("   ✅ 学习完成")
    print(f"\n📋 学习到的规则:")
    print(json.dumps(learned_rules, indent=2, ensure_ascii=False))

    return learned_rules

if __name__ == '__main__':
    learn_from_history()
