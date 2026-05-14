#!/usr/bin/env python3
"""
Agent B Optimized - 优化版情报研究
目标：每天至少 10 笔交易，胜率 >= 80%

优化策略：
1. 降低置信度阈值（80% -> 70%）
2. 增加交易策略（NHL + 娱乐 + 政治 + 加密）
3. 优化学习规则（不完全拒绝，而是调整仓位）
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_helper import call_llm_sync

class AgentBOptimized:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        
        # 交易目标
        self.daily_target = 10
        self.min_confidence = 70  # 降低到 70%
        self.target_win_rate = 0.80
        
        # 市场分类
        self.market_categories = {
            'NHL': {'priority': 1, 'base_confidence': 85, 'max_position': 0.30},
            'NBA': {'priority': 2, 'base_confidence': 80, 'max_position': 0.25},
            'Entertainment': {'priority': 3, 'base_confidence': 75, 'max_position': 0.20},
            'Politics': {'priority': 3, 'base_confidence': 75, 'max_position': 0.20},
            'Crypto': {'priority': 2, 'base_confidence': 80, 'max_position': 0.25},
            'Other': {'priority': 4, 'base_confidence': 70, 'max_position': 0.15}
        }
    
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent B Optimized] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"agent_b_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def classify_market(self, question):
        """分类市场类型"""
        question_lower = question.lower()
        
        if 'nhl' in question_lower or 'stanley cup' in question_lower:
            return 'NHL'
        elif 'nba' in question_lower:
            return 'NBA'
        elif any(kw in question_lower for kw in ['gta', 'album', 'movie', 'release', 'carti', 'weinstein']):
            return 'Entertainment'
        elif any(kw in question_lower for kw in ['trump', 'election', 'president', 'congress', 'senate']):
            return 'Politics'
        elif any(kw in question_lower for kw in ['bitcoin', 'btc', 'eth', 'crypto', 'blockchain']):
            return 'Crypto'
        else:
            return 'Other'
    
    def calculate_position_size(self, market_type, confidence, liquidity):
        """计算仓位大小"""
        category = self.market_categories.get(market_type, self.market_categories['Other'])
        
        # 基础仓位
        base_position = category['max_position']
        
        # 根据置信度调整
        confidence_factor = confidence / 100
        
        # 转换流动性为数字
        try:
            liquidity_value = float(liquidity) if liquidity else 0
        except (ValueError, TypeError):
            liquidity_value = 0
        
        # 根据流动性调整
        if liquidity_value < 1000:
            liquidity_factor = 0.5
        elif liquidity_value < 5000:
            liquidity_factor = 0.75
        else:
            liquidity_factor = 1.0
        
        # 最终仓位
        position = base_position * confidence_factor * liquidity_factor
        
        # 限制在 5% - 30% 之间
        return max(0.05, min(0.30, position))
    
    def analyze_market(self, market):
        """分析单个市场"""
        question = market.get('question', '')
        yes_price = market.get('yes_price', 0.5)
        no_price = market.get('no_price', 0.5)
        liquidity = market.get('liquidity', 0)
        
        market_type = self.classify_market(question)
        category = self.market_categories[market_type]
        
        signals = []
        
        # 策略 1: NHL 高价 NO（历史验证 100% 成功率）
        if market_type == 'NHL' and no_price >= 0.85:
            confidence = min(95, category['base_confidence'] + 10)
            position = self.calculate_position_size(market_type, confidence, liquidity)
            
            signals.append({
                'market_id': market.get('id'),
                'market_name': question,
                'market_type': market_type,
                'strategy': 'NHL_high_NO',
                'direction': 'NO',
                'price': no_price,
                'confidence': confidence,
                'position_size': position,
                'expected_value': (1 - no_price) / no_price * 100,
                'liquidity': liquidity,
                'reason': f'NHL 高价 NO 策略（历史 100% 成功率），价格 {no_price:.3f}'
            })
        
        # 策略 2: 中间价格区间 NO（0.4-0.6）
        elif 0.4 <= no_price <= 0.6:
            confidence = category['base_confidence']
            position = self.calculate_position_size(market_type, confidence, liquidity)
            
            signals.append({
                'market_id': market.get('id'),
                'market_name': question,
                'market_type': market_type,
                'strategy': 'mid_range_NO',
                'direction': 'NO',
                'price': no_price,
                'confidence': confidence,
                'position_size': position,
                'expected_value': (1 - no_price) / no_price * 100,
                'liquidity': liquidity,
                'reason': f'中间价格区间策略，价格 {no_price:.3f}'
            })
        
        # 策略 3: 低价 YES（< 0.3）
        elif yes_price < 0.3 and market_type in ['Politics', 'Crypto', 'NBA']:
            confidence = category['base_confidence'] - 5
            position = self.calculate_position_size(market_type, confidence, liquidity)
            
            signals.append({
                'market_id': market.get('id'),
                'market_name': question,
                'market_type': market_type,
                'strategy': 'low_price_YES',
                'direction': 'YES',
                'price': yes_price,
                'confidence': confidence,
                'position_size': position,
                'expected_value': (1 - yes_price) / yes_price * 100,
                'liquidity': liquidity,
                'reason': f'低价 YES 策略，价格 {yes_price:.3f}'
            })
        
        # 策略 4: 高价 YES（> 0.7）- 顺势交易
        elif yes_price > 0.7 and market_type in ['Politics', 'NBA']:
            confidence = category['base_confidence'] - 10
            position = self.calculate_position_size(market_type, confidence, liquidity)
            
            signals.append({
                'market_id': market.get('id'),
                'market_name': question,
                'market_type': market_type,
                'strategy': 'high_price_YES',
                'direction': 'YES',
                'price': yes_price,
                'confidence': confidence,
                'position_size': position,
                'expected_value': (1 - yes_price) / yes_price * 100,
                'liquidity': liquidity,
                'reason': f'高价 YES 顺势策略，价格 {yes_price:.3f}'
            })
        
        return signals
    
    def filter_signals(self, signals):
        """过滤信号"""
        # 按优先级和置信度排序
        signals.sort(key=lambda x: (
            -self.market_categories[x['market_type']]['priority'],
            -x['confidence'],
            -float(x['liquidity']) if x['liquidity'] else 0
        ))
        
        # 过滤低置信度信号
        filtered = [s for s in signals if s['confidence'] >= self.min_confidence]
        
        # 过滤低流动性信号
        filtered = [s for s in filtered if (float(s['liquidity']) if s['liquidity'] else 0) >= 500]
        
        # 限制每个市场类型的数量
        type_counts = {}
        final_signals = []
        
        for signal in filtered:
            market_type = signal['market_type']
            count = type_counts.get(market_type, 0)
            
            # NHL 最多 5 个，其他类型最多 3 个
            max_per_type = 5 if market_type == 'NHL' else 3
            
            if count < max_per_type:
                final_signals.append(signal)
                type_counts[market_type] = count + 1
        
        # 限制总数量（最多 15 个信号）
        return final_signals[:15]
    
    def run(self):
        """执行情报分析"""
        self.log("=" * 60)
        self.log("开始情报分析（优化版）")
        
        # 读取最新数据
        latest_data_file = self.data_dir / "latest_data.json"
        if not latest_data_file.exists():
            self.log("❌ latest_data.json 不存在")
            return
        
        with open(latest_data_file, 'r') as f:
            latest_data = json.load(f)
        
        markets = latest_data.get('polymarket_markets', [])
        self.log(f"📊 加载 {len(markets)} 个市场")
        
        # 分析所有市场
        all_signals = []
        for market in markets:
            signals = self.analyze_market(market)
            all_signals.extend(signals)
        
        self.log(f"📊 生成 {len(all_signals)} 个原始信号")
        
        # 过滤信号
        filtered_signals = self.filter_signals(all_signals)
        
        self.log(f"📊 过滤后 {len(filtered_signals)} 个信号")
        
        # 统计市场类型分布
        type_counts = {}
        for signal in filtered_signals:
            market_type = signal['market_type']
            type_counts[market_type] = type_counts.get(market_type, 0) + 1
        
        self.log(f"📊 市场类型分布: {type_counts}")
        
        # 保存信号
        signals_file = self.data_dir / "signals.json"
        with open(signals_file, 'w') as f:
            json.dump(filtered_signals, f, indent=2, ensure_ascii=False)
        
        # 保存情报报告
        report = {
            'timestamp': datetime.now().isoformat(),
            'report': f'优化版策略生成 {len(filtered_signals)} 个信号',
            'signals_count': len(filtered_signals),
            'signals': filtered_signals,
            'market_type_distribution': type_counts,
            'optimization_notes': {
                'min_confidence': self.min_confidence,
                'daily_target': self.daily_target,
                'strategies_enabled': ['NHL_high_NO', 'mid_range_NO', 'low_price_YES', 'high_price_YES']
            }
        }
        
        report_file = self.data_dir / "intelligence_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 情报分析完成")
        self.log(f"   信号数量: {len(filtered_signals)}")
        self.log(f"   平均置信度: {sum(s['confidence'] for s in filtered_signals) / len(filtered_signals):.1f}%" if filtered_signals else "   平均置信度: N/A")
        self.log("=" * 60)

def main():
    agent = AgentBOptimized()
    agent.run()

if __name__ == "__main__":
    main()
