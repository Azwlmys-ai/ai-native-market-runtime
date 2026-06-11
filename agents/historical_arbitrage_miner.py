#!/usr/bin/env python3
"""
Historical Arbitrage Miner - 从历史数据中挖掘套利机会
支持多平台：Polymarket, OKX, 老虎证券, 长桥, 富途, 盈透
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync

def load_polymarket_history():
    """加载 Polymarket 历史交易"""
    with open('data/train_trades.json', 'r') as f:
        train_data = json.load(f)
    with open('data/test_trades.json', 'r') as f:
        test_data = json.load(f)
    
    all_trades = train_data['trades'] + test_data['trades']
    
    # 按市场分组
    markets = defaultdict(list)
    for trade in all_trades:
        markets[trade['market_slug']].append(trade)
    
    return markets

def analyze_price_movements(market_trades):
    """分析价格波动，识别套利机会"""
    # 按时间排序
    trades_sorted = sorted(market_trades, key=lambda x: x['created_at'])
    
    opportunities = []
    
    for i in range(len(trades_sorted) - 1):
        current = trades_sorted[i]
        next_trade = trades_sorted[i + 1]
        
        # 只分析买入交易（有价格信息）
        if current['side'] != 'buy' or next_trade['side'] != 'buy':
            continue
        
        # 计算价格变化
        price_change = next_trade['avg_price'] - current['avg_price']
        price_change_pct = (price_change / current['avg_price']) * 100
        
        # 计算时间间隔
        time_diff = datetime.strptime(next_trade['created_at'], '%Y-%m-%d %H:%M:%S') - \
                   datetime.strptime(current['created_at'], '%Y-%m-%d %H:%M:%S')
        
        # 识别套利机会：价格波动 > 5% 且时间间隔 < 24 小时
        if abs(price_change_pct) > 5 and time_diff.total_seconds() < 86400:
            opportunity = {
                'market': current['market_question'],
                'market_slug': current['market_slug'],
                'outcome': current['outcome'],
                'buy_time': current['created_at'],
                'buy_price': current['avg_price'],
                'sell_time': next_trade['created_at'],
                'sell_price': next_trade['avg_price'],
                'price_change_pct': price_change_pct,
                'time_window_hours': time_diff.total_seconds() / 3600,
                'potential_profit_pct': abs(price_change_pct) - 2,  # 扣除 2% 交易成本
                'direction': 'long' if price_change > 0 else 'short'
            }
            
            opportunities.append(opportunity)
    
    return opportunities

def generate_arbitrage_mining_prompt(opportunities):
    """生成套利挖掘 Prompt"""
    
    # 按潜在收益排序
    top_opportunities = sorted(opportunities, key=lambda x: x['potential_profit_pct'], reverse=True)[:20]
    
    prompt = f"""你是跨平台套利专家。分析以下 Polymarket 历史价格波动数据，识别可复现的套利模式。

## 历史套利机会（Top 20）
{json.dumps(top_opportunities, indent=2, ensure_ascii=False)}

## 任务
1. 识别可复现的套利模式（价格波动规律、时间窗口、触发条件）
2. 评估每个机会的可行性（流动性、滑点、交易成本）
3. 提出跨平台套利策略（如果相关市场在其他平台有对应标的）

## 跨平台映射建议
- **NHL/NBA 赛事**: 可在老虎证券、盈透证券交易相关球队股票或期权
- **加密货币价格预测**: 可在 OKX 交易现货/合约对冲
- **宏观经济事件**: 可在富途、长桥交易相关 ETF 或指数期权

输出 JSON 格式：
{{
  "arbitrage_patterns": [
    {{
      "pattern_name": "...",
      "description": "...",
      "historical_success_rate": 0.75,
      "avg_profit_pct": 8.5,
      "time_window_hours": 12,
      "trigger_conditions": ["..."],
      "cross_platform_strategy": {{
        "polymarket_side": "buy_no",
        "other_platform": "OKX",
        "other_platform_action": "short BTC perpetual",
        "hedge_ratio": 1.2
      }}
    }}
  ],
  "top_opportunities": [
    {{
      "market": "...",
      "entry_price": 0.45,
      "exit_price": 0.52,
      "profit_pct": 13.5,
      "confidence": 85,
      "reason": "..."
    }}
  ]
}}
"""
    
    return prompt

def mine_arbitrage_opportunities():
    """挖掘套利机会"""
    print("⛏️  Historical Arbitrage Miner - 挖掘历史套利机会")
    print("="*60)
    
    # 1. 加载历史数据
    print("\n1️⃣ 加载 Polymarket 历史交易...")
    markets = load_polymarket_history()
    print(f"   ✅ 加载 {len(markets)} 个市场的交易数据")
    
    # 2. 分析价格波动
    print("\n2️⃣ 分析价格波动，识别套利机会...")
    all_opportunities = []
    
    for market_slug, trades in markets.items():
        if len(trades) < 2:
            continue
        
        opportunities = analyze_price_movements(trades)
        all_opportunities.extend(opportunities)
    
    print(f"   ✅ 识别 {len(all_opportunities)} 个潜在套利机会")
    
    if not all_opportunities:
        print("   ⚠️  未发现套利机会")
        return
    
    # 3. 统计分析
    print("\n3️⃣ 统计分析...")
    avg_profit = sum(o['potential_profit_pct'] for o in all_opportunities) / len(all_opportunities)
    max_profit = max(o['potential_profit_pct'] for o in all_opportunities)
    avg_time = sum(o['time_window_hours'] for o in all_opportunities) / len(all_opportunities)
    
    print(f"   平均潜在收益: {avg_profit:.2f}%")
    print(f"   最大潜在收益: {max_profit:.2f}%")
    print(f"   平均时间窗口: {avg_time:.1f} 小时")
    
    # 4. 调用 LLM 分析
    print("\n4️⃣ 调用 LLM 分析套利模式...")
    prompt = generate_arbitrage_mining_prompt(all_opportunities)
    
    try:
        response = call_llm_sync(
            agent_id='agent_historical_miner',
            prompt=prompt,
            timeout=180,
            temperature=0.1
        )
        
        # 5. 解析结果
        print("\n5️⃣ 解析套利模式...")
        if '```json' in response:
            response = response.split('```json')[1].split('```')[0].strip()
        elif '```' in response:
            response = response.split('```')[1].split('```')[0].strip()
        
        result = json.loads(response)
        
        patterns = result.get('arbitrage_patterns', [])
        top_opps = result.get('top_opportunities', [])
        
        print(f"   ✅ 识别 {len(patterns)} 个可复现套利模式")
        print(f"   ✅ 推荐 {len(top_opps)} 个高置信度机会")
        
        # 6. 保存结果
        output = {
            'timestamp': datetime.now().isoformat(),
            'total_opportunities': len(all_opportunities),
            'avg_profit_pct': avg_profit,
            'max_profit_pct': max_profit,
            'avg_time_window_hours': avg_time,
            'arbitrage_patterns': patterns,
            'top_opportunities': top_opps,
            'raw_opportunities': all_opportunities[:50]  # 保存前 50 个原始数据
        }
        
        with open('data/arbitrage_opportunities.json', 'w') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ 结果保存到 data/arbitrage_opportunities.json")
        
        # 7. 展示结果
        print("\n" + "="*60)
        print("📊 套利模式总结:")
        for i, pattern in enumerate(patterns, 1):
            print(f"\n{i}. {pattern.get('pattern_name', 'N/A')}")
            print(f"   描述: {pattern.get('description', 'N/A')}")
            print(f"   历史成功率: {pattern.get('historical_success_rate', 0)*100:.1f}%")
            print(f"   平均收益: {pattern.get('avg_profit_pct', 0):.2f}%")
            print(f"   时间窗口: {pattern.get('time_window_hours', 0):.1f} 小时")
            
            if 'cross_platform_strategy' in pattern:
                cross = pattern['cross_platform_strategy']
                print(f"   跨平台策略: {cross.get('polymarket_side', 'N/A')} @ Polymarket + {cross.get('other_platform_action', 'N/A')} @ {cross.get('other_platform', 'N/A')}")
        
        return result
        
    except Exception as e:
        print(f"   ❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    mine_arbitrage_opportunities()
