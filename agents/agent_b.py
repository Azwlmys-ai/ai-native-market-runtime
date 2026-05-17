#!/usr/bin/env python3
"""
Agent B Enhanced - 集成学习到的策略规则
在原有情报研究基础上，应用历史学习的决策规则
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync
from _paths import get_base_dir


BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"


def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] [Agent B Enhanced] {message}"
    print(log_msg)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"agent_b_{datetime.now().strftime('%Y%m%d')}.log"
    with open(log_file, 'a') as f:
        f.write(log_msg + "\n")

def load_learned_rules():
    """加载学习到的规则"""
    rules_path = DATA_DIR / "learned_rules.json"
    if rules_path.exists():
        with open(rules_path, 'r') as f:
            data = json.load(f)
        return data['learned_rules']
    return None

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

def apply_learned_rules(market_data, learned_rules):
    """应用学习到的规则过滤市场"""
    if not learned_rules:
        return market_data, []
    
    filtered_markets = []
    rejected_markets = []
    
    # 获取避免的市场类型
    avoid_markets = [m['market_type'] for m in learned_rules['market_rules']['avoid']]
    recommended_markets = [m['market_type'] for m in learned_rules['market_rules']['recommended']]
    
    # 获取滑点阈值
    slippage_thresholds = {}
    for market_rule in learned_rules['market_rules']['recommended']:
        slippage_thresholds[market_rule['market_type']] = market_rule['max_slippage']
    
    for market in market_data:
        market_type = classify_market(market.get('question', ''))

        # 从 outcome_prices 派生 yes/no 价格（API 不直接返回这两个字段）
        if 'yes_price' not in market or 'no_price' not in market:
            outcome_prices = market.get('outcome_prices', [])
            outcomes = [o.lower() for o in market.get('outcomes', ['yes', 'no'])]
            try:
                yes_idx = outcomes.index('yes')
                no_idx = outcomes.index('no')
                market['yes_price'] = outcome_prices[yes_idx] if outcome_prices else 0.5
                market['no_price'] = outcome_prices[no_idx] if outcome_prices else 0.5
            except (ValueError, IndexError):
                market['yes_price'] = outcome_prices[0] if len(outcome_prices) > 0 else 0.5
                market['no_price'] = outcome_prices[1] if len(outcome_prices) > 1 else 0.5

        yes_price = market.get('yes_price', 0.5)
        no_price = market.get('no_price', 0.5)
        
        # 规则 1: 避免流动性差的市场
        if market_type in avoid_markets:
            rejected_markets.append({
                'market': market['question'][:50],
                'reason': f'避免 {market_type} 市场（历史数据显示流动性问题）'
            })
            continue
        
        # 规则 2: 只交易推荐市场
        if market_type not in recommended_markets:
            rejected_markets.append({
                'market': market['question'][:50],
                'reason': f'{market_type} 不在推荐市场列表'
            })
            continue
        
        # 规则 3: 价格区间策略
        # 中间价格区间 (0.4-0.6) 买 NO
        if 0.4 <= no_price <= 0.6:
            market['learned_strategy'] = 'buy_NO_mid_range'
            market['learned_confidence'] = 85
        # 极端高价 (>0.8) NHL 买 NO
        elif no_price >= 0.8 and market_type == 'NHL':
            market['learned_strategy'] = 'buy_NO_extreme_high'
            market['learned_confidence'] = 90
        else:
            # 不符合价格策略
            rejected_markets.append({
                'market': market['question'][:50],
                'reason': f'价格 {no_price:.3f} 不符合学习到的价格区间策略'
            })
            continue
        
        # 规则 4: 滑点预估（用 liquidity 作为深度代理，orderbook_no 已废弃）
        orderbook_depth = market.get('orderbook_no') or market.get('liquidity', 0)
        if orderbook_depth < 1000:
            rejected_markets.append({
                'market': market['question'][:50],
                'reason': f'流动性 ${orderbook_depth:.0f} < $1,000，预期滑点过高'
            })
            continue
        
        market['market_type'] = market_type
        filtered_markets.append(market)
    
    return filtered_markets, rejected_markets


def _market_index(latest_data):
    markets = latest_data.get('polymarket_markets', [])
    return {
        market.get('slug'): market
        for market in markets
        if isinstance(market, dict) and market.get('slug')
    }


def _signal_side_to_direction(side):
    return 'NO' if 'no' in str(side).lower() else 'YES'


def _signal_price(signal, market):
    explicit = signal.get('price')
    if explicit is not None:
        try:
            return float(explicit)
        except (TypeError, ValueError):
            return 0.5

    outcomes = [str(o).lower() for o in market.get('outcomes', ['yes', 'no'])]
    prices = market.get('outcome_prices', [])
    direction = _signal_side_to_direction(signal.get('side', ''))
    try:
        idx = outcomes.index(direction.lower())
        return float(prices[idx])
    except (ValueError, IndexError):
        return 0.5


def enrich_signals(signals, latest_data, learned_rules):
    """Attach auditable fields required by Agent M.

    This layer only uses data already present in latest_data/learned_rules. It
    skips signals that cannot be tied back to a real market row or learned rule.
    """
    markets = _market_index(latest_data)
    enriched = []
    skipped = []
    generated_at = datetime.now().isoformat()
    rules_available = bool(learned_rules)

    for signal in signals:
        if not isinstance(signal, dict):
            skipped.append({'signal': signal, 'reason': 'non_object_signal'})
            continue

        slug = signal.get('market_slug')
        market = markets.get(slug)
        if not market:
            skipped.append({'signal': signal, 'reason': 'missing_market_data'})
            continue

        rule_match = signal.get('learned_rule_match')
        if not rule_match or not rules_available:
            skipped.append({'signal': signal, 'reason': 'missing_learned_rule_match'})
            continue

        liquidity = float(market.get('liquidity') or 0)
        if liquidity < 1000:
            skipped.append({'signal': signal, 'reason': f'liquidity_below_threshold:{liquidity:.0f}'})
            continue

        direction = _signal_side_to_direction(signal.get('side', ''))
        price = _signal_price(signal, market)
        market_type = classify_market(market.get('question', ''))
        implied_probability = price if direction == 'YES' else 1 - price

        data_sources = [
            'latest_data.json:polymarket_markets',
            'latest_data.json:outcome_prices',
            'latest_data.json:liquidity',
            'learned_rules.json:market_rules',
            'learned_rules.json:price_rules',
        ]

        logic_chain = [
            f"market_type={market_type} from market question classification",
            f"selected direction={direction} from side={signal.get('side')}",
            f"price={price} and implied_probability={implied_probability:.4f} from outcome_prices",
            f"learned_rule_match={rule_match} from learned_rules.json",
            f"liquidity={liquidity:.2f} passes minimum $1000 filter",
            f"ev={signal.get('ev', signal.get('expected_value', 0))}, confidence={signal.get('confidence', 0)} from Agent B scoring",
        ]

        risk_notes = [
            f"liquidity_risk: liquidity=${liquidity:.2f}; lower depth may increase slippage",
            "strategy_risk: learned high-price NO rules can fail on long-tail sports outcomes",
            "correlation_risk: related sports positions may move together",
            f"time_risk: market end_date={market.get('end_date', 'unknown')}",
        ]

        market_evidence = {
            'market_slug': slug,
            'market_name': market.get('question'),
            'direction': direction,
            'price': price,
            'expected_value': signal.get('ev', signal.get('expected_value', 0)),
            'confidence': signal.get('confidence', 0),
            'liquidity': liquidity,
            'volume': market.get('volume'),
            'outcomes': market.get('outcomes'),
            'outcome_prices': market.get('outcome_prices'),
            'learned_rule_match': rule_match,
            'implied_probability': implied_probability,
        }

        enriched_signal = dict(signal)
        enriched_signal.update({
            'price': price,
            'generated_at': generated_at,
            'data_sources': data_sources,
            'logic_chain': logic_chain,
            'risk_notes': risk_notes,
            'market_evidence': market_evidence,
        })
        enriched.append(enriched_signal)

    return enriched, skipped


def generate_enhanced_prompt(latest_data, learned_rules):
    """生成增强版 Prompt（集成学习规则）"""
    
    # 应用学习规则预过滤（使用正确的键名 polymarket_markets）
    filtered_markets, rejected_markets = apply_learned_rules(
        latest_data.get('polymarket_markets', []),
        learned_rules
    )
    
    rules_summary = ""
    if learned_rules:
        rules_summary = f"""
## 历史学习规则（已验证 100% 准确率）

### 推荐市场
{json.dumps(learned_rules['market_rules']['recommended'], indent=2, ensure_ascii=False)}

### 价格策略
{json.dumps(learned_rules['price_rules'], indent=2, ensure_ascii=False)}

### 仓位管理
{json.dumps(learned_rules['position_sizing'], indent=2, ensure_ascii=False)}

### 预过滤结果
- 通过规则筛选: {len(filtered_markets)} 个市场
- 被规则拒绝: {len(rejected_markets)} 个市场
"""
    
    prompt = f"""你是 Polymarket 情报研究专家（Agent B Enhanced）。

{rules_summary}

## 当前市场数据
{json.dumps(filtered_markets[:10], indent=2, ensure_ascii=False)}

## 宏观数据
- 联邦基金利率: {latest_data.get('fed_rate', 'N/A')}
- BTC 资金费率: {latest_data.get('btc_funding_rate', 'N/A')}

## 任务
基于历史学习规则和当前市场数据，生成高置信度交易信号。

要求：
1. 优先选择已通过规则筛选的市场
2. 应用学习到的价格区间策略
3. 每个信号必须包含：市场、方向、价格、EV、置信度、学习规则匹配度
4. 置信度 >= 70 才生成信号
5. EV >= 8%
6. 不要为没有真实市场数据或学习规则匹配的市场生成信号
7. 每个信号必须可审计，并包含 data_sources、logic_chain、risk_notes、market_evidence、generated_at

输出 JSON 格式：
{{
  "signals": [
    {{
      "market_slug": "...",
      "side": "buy_no",
      "price": 0.95,
      "ev": 12.5,
      "confidence": 85,
      "learned_rule_match": "extreme_high_NHL",
      "reason": "...",
      "data_sources": ["latest_data.json:polymarket_markets", "learned_rules.json:price_rules"],
      "logic_chain": ["..."],
      "risk_notes": ["..."],
      "market_evidence": {{"price": 0.95, "direction": "NO"}},
      "generated_at": "ISO-8601"
    }}
  ]
}}
"""
    
    return prompt, rejected_markets

def main():
    log("启动情报研究（集成学习规则）")
    
    # 1. 加载学习规则
    learned_rules = load_learned_rules()
    if learned_rules:
        log("✅ 加载学习规则（验证准确率 100%）")
    else:
        log("⚠️  未找到学习规则，使用原始逻辑")
    
    # 2. 加载最新数据
    with open(DATA_DIR / 'latest_data.json', 'r') as f:
        latest_data = json.load(f)

    # 2a. 无 Polymarket 数据时早期退出，避免无效 LLM 调用
    if not latest_data.get('polymarket_markets'):
        log("ℹ️  无 Polymarket 市场数据，跳过情报研究")
        with open(DATA_DIR / 'intelligence_report.json', 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'status': 'skipped',
                'reason': 'no_polymarket_markets',
                'report': '无 Polymarket 市场数据，跳过情报研究',
                'signals_count': 0,
                'signals': []
            }, f, indent=2, ensure_ascii=False)
        return

    polymarket_status = latest_data.get('polymarket_status')
    if polymarket_status and polymarket_status != 'ok':
        log(f"ℹ️  Polymarket 数据状态为 {polymarket_status}，跳过情报研究")
        with open(DATA_DIR / 'intelligence_report.json', 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'status': 'skipped',
                'reason': f'polymarket_status={polymarket_status}',
                'report': f'Polymarket 数据状态为 {polymarket_status}，跳过情报研究',
                'signals_count': 0,
                'signals': []
            }, f, indent=2, ensure_ascii=False)
        return

    # 3. 生成增强 Prompt
    prompt, rejected_markets = generate_enhanced_prompt(latest_data, learned_rules)
    
    if rejected_markets:
        log(f"📋 规则预过滤拒绝 {len(rejected_markets)} 个市场:")
        for r in rejected_markets[:5]:
            log(f"  - {r['market']}: {r['reason']}")
    
    # 4. 调用 LLM
    try:
        response = call_llm_sync(
            agent_id='agent_b',
            prompt=prompt,
            timeout=120,
            temperature=0.1
        )
        
        # 5. 解析响应
        if '```json' in response:
            response = response.split('```json')[1].split('```')[0].strip()
        elif '```' in response:
            response = response.split('```')[1].split('```')[0].strip()
        
        result = json.loads(response)
        raw_signals = result.get('signals', [])
        signals, skipped_signals = enrich_signals(raw_signals, latest_data, learned_rules)
        if skipped_signals:
            log(f"⚠️  跳过 {len(skipped_signals)} 个不可审计信号")
            for item in skipped_signals[:5]:
                log(f"  - {item['reason']}")
        
        # 6. 保存结果
        output = {
            'timestamp': datetime.now().isoformat(),
            'report': f"应用学习规则生成 {len(signals)} 个信号",
            'signals_count': len(signals),
            'signals': signals,
            'raw_signals_count': len(raw_signals),
            'skipped_signals': skipped_signals,
            'rejected_by_rules': len(rejected_markets)
        }
        
        with open(DATA_DIR / 'intelligence_report.json', 'w') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        log(f"✅ 生成 {len(signals)} 个信号")
        
    except Exception as e:
        log(f"❌ 执行失败: {e}")
        # 保存空报告
        with open(DATA_DIR / 'intelligence_report.json', 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'status': 'error',
                'reason': 'llm_call_failed',
                'report': f"执行失败: {e}",
                'signals_count': 0,
                'signals': []
            }, f, indent=2, ensure_ascii=False)

if __name__ == '__main__':
    main()
