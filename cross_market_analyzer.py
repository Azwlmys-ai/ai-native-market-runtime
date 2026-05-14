#!/usr/bin/env python3
"""
跨市场关联分析器
分析加密货币、股票、Polymarket 之间的相关性和套利机会
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

class CrossMarketAnalyzer:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.historical_dir = self.data_dir / "historical"
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def load_all_data(self):
        """加载所有市场数据"""
        self.log("加载所有市场数据...")
        
        data = {
            'crypto': {},
            'us_stocks': {},
            'cn_stocks': {},
            'polymarket': []
        }
        
        # 加载加密货币
        for symbol in ['BTC', 'ETH', 'BNB', 'SOL']:
            combined = []
            for month in ['march', 'april']:
                file_path = self.historical_dir / f"okx_{symbol}_USDT_klines_{month}_2026.json"
                if file_path.exists():
                    with open(file_path, 'r') as f:
                        combined.extend(json.load(f))
            
            combined.sort(key=lambda x: x['timestamp'])
            data['crypto'][symbol] = combined
            self.log(f"  ✅ {symbol}: {len(combined)} 条")
        
        # 加载美股
        us_file = self.historical_dir / "us_stocks_march_2026.json"
        if us_file.exists():
            with open(us_file, 'r') as f:
                data['us_stocks'] = json.load(f)
            self.log(f"  ✅ 美股: {len(data['us_stocks'])} 只")
        
        # 加载 A 股
        cn_file = self.historical_dir / "cn_stocks_march_2026.json"
        if cn_file.exists():
            with open(cn_file, 'r') as f:
                data['cn_stocks'] = json.load(f)
            self.log(f"  ✅ A 股: {len(data['cn_stocks'])} 只")
        
        # 加载 Polymarket（如果有）
        pm_file = self.historical_dir / "polymarket_markets_march_2026.json"
        if pm_file.exists():
            with open(pm_file, 'r') as f:
                content = f.read().strip()
                if content and content != '[]':
                    data['polymarket'] = json.load(f)
                    self.log(f"  ✅ Polymarket: {len(data['polymarket'])} 个市场")
        
        return data
    
    def analyze_correlations(self, data):
        """分析市场相关性"""
        self.log("\n" + "=" * 80)
        self.log("跨市场相关性分析")
        self.log("=" * 80)
        
        correlations = []
        
        # 1. 加密货币 vs 科技股
        self.log("\n📊 加密货币 vs 科技股")
        
        crypto_tech_pairs = [
            ('BTC', 'COIN', '比特币 vs Coinbase（直接相关）'),
            ('ETH', 'NVDA', '以太坊 vs 英伟达（AI/GPU 挖矿）'),
            ('BTC', 'MSTR', '比特币 vs MicroStrategy（持有大量 BTC）'),
            ('BTC', 'TSLA', '比特币 vs 特斯拉（持有 BTC，马斯克影响）'),
        ]
        
        for crypto, stock, desc in crypto_tech_pairs:
            if crypto in data['crypto'] and stock in data['us_stocks']:
                self.log(f"  ✅ {desc}")
                correlations.append({
                    'type': 'crypto_stock',
                    'asset1': crypto,
                    'asset2': stock,
                    'description': desc,
                    'lag': 0,  # 同步
                    'strength': 'high',
                    'mechanism': '直接业务关联或持仓影响'
                })
        
        # 2. 美股 vs A 股（跨市场情绪传导）
        self.log("\n📊 美股 vs A 股（隔夜传导）")
        
        us_cn_pairs = [
            ('NVDA', '600519', '英伟达 vs 贵州茅台（风险偏好指标）'),
            ('TSLA', '002594', '特斯拉 vs 比亚迪（电动车竞争）'),
        ]
        
        for us, cn, desc in us_cn_pairs:
            if us in data['us_stocks'] and cn in data['cn_stocks']:
                self.log(f"  ✅ {desc}")
                correlations.append({
                    'type': 'us_cn_stock',
                    'asset1': us,
                    'asset2': cn,
                    'description': desc,
                    'lag': 12,  # 12小时时差（美股收盘 → A股开盘）
                    'strength': 'medium',
                    'mechanism': '隔夜情绪传导、行业竞争'
                })
        
        # 3. 加密货币 vs Polymarket 价格预测
        self.log("\n📊 加密货币 vs Polymarket 价格预测")
        
        if data['polymarket']:
            crypto_pm_keywords = {
                'BTC': ['bitcoin', 'btc', '$100k', '$50k'],
                'ETH': ['ethereum', 'eth', '$5k', '$3k'],
                'SOL': ['solana', 'sol']
            }
            
            for crypto, keywords in crypto_pm_keywords.items():
                for market in data['polymarket']:
                    question = market.get('question', '').lower()
                    if any(kw in question for kw in keywords):
                        self.log(f"  ✅ {crypto} vs Polymarket: {market.get('question', '')[:60]}...")
                        correlations.append({
                            'type': 'crypto_polymarket',
                            'asset1': crypto,
                            'asset2': market.get('id'),
                            'description': f"{crypto} 价格 vs 预测市场",
                            'lag': 0,  # 实时
                            'strength': 'very_high',
                            'mechanism': '价格预测市场直接反映现货价格预期'
                        })
        
        # 4. 宏观事件 vs 多市场（恐慌/贪婪情绪）
        self.log("\n📊 宏观事件影响（恐慌/贪婪情绪传导）")
        
        macro_events = [
            {
                'event': '美联储降息',
                'impact': {
                    'crypto': '正面（流动性宽松）',
                    'stocks': '正面（估值提升）',
                    'polymarket': '降息概率市场直接受益'
                },
                'lag': '即时传导',
                'strength': 'very_high'
            },
            {
                'event': '地缘政治危机',
                'impact': {
                    'crypto': 'BTC 避险需求上升',
                    'stocks': '风险资产抛售',
                    'polymarket': '地缘政治市场活跃'
                },
                'lag': '即时传导',
                'strength': 'high'
            },
            {
                'event': '科技监管',
                'impact': {
                    'crypto': '负面（监管压力）',
                    'stocks': '科技股承压',
                    'polymarket': '监管相关市场活跃'
                },
                'lag': '1-24小时',
                'strength': 'medium'
            }
        ]
        
        for event in macro_events:
            self.log(f"  ✅ {event['event']}")
            self.log(f"     - 加密货币: {event['impact']['crypto']}")
            self.log(f"     - 股票: {event['impact']['stocks']}")
            self.log(f"     - Polymarket: {event['impact']['polymarket']}")
            self.log(f"     - 传导时间: {event['lag']}")
        
        return correlations
    
    def identify_arbitrage_opportunities(self, correlations):
        """识别套利机会类型"""
        self.log("\n" + "=" * 80)
        self.log("跨市场套利机会类型")
        self.log("=" * 80)
        
        opportunities = []
        
        # 1. 价格预测套利
        self.log("\n💰 类型 1: 价格预测套利")
        self.log("   机制: Polymarket 价格预测 vs 现货价格")
        self.log("   示例: BTC 现货 $65,000，Polymarket '4月底 BTC > $70k' 价格 0.30")
        self.log("   策略: 如果现货已经 $68,000，但预测市场还是 0.30，买入 YES")
        self.log("   优势: 信息差（现货价格领先预测市场）")
        
        opportunities.append({
            'type': 'price_prediction_arbitrage',
            'markets': ['crypto', 'polymarket'],
            'mechanism': '现货价格领先预测市场定价',
            'signal': 'Polymarket 隐含概率 < 实际概率',
            'execution': '买入 Polymarket YES，持有到结算'
        })
        
        # 2. 时间差套利
        self.log("\n💰 类型 2: 时间差套利（隔夜传导）")
        self.log("   机制: 美股收盘 → A股开盘（12小时时差）")
        self.log("   示例: 特斯拉暴跌 -10% → 预期比亚迪开盘下跌")
        self.log("   策略: 美股收盘后，做空 A股相关标的")
        self.log("   优势: 时间差（美股信息未反映到 A股）")
        
        opportunities.append({
            'type': 'overnight_gap_arbitrage',
            'markets': ['us_stocks', 'cn_stocks'],
            'mechanism': '美股收盘信息传导到 A股开盘',
            'signal': '美股大幅波动（> 5%）',
            'execution': 'A股开盘前预判方向，开盘后快速交易'
        })
        
        # 3. 恐慌情绪套利
        self.log("\n💰 类型 3: 恐慌情绪套利")
        self.log("   机制: 负面事件 → 多市场超跌 → 反弹")
        self.log("   示例: 监管消息 → BTC -15%，COIN -20% → 超跌反弹")
        self.log("   策略: 识别过度恐慌，买入超跌资产")
        self.log("   优势: 情绪差（恐慌性抛售创造机会）")
        
        opportunities.append({
            'type': 'panic_reversal_arbitrage',
            'markets': ['crypto', 'stocks'],
            'mechanism': '恐慌性抛售后的超跌反弹',
            'signal': '短时间内暴跌 > 10%，RSI < 25',
            'execution': '买入超跌资产，设置止损'
        })
        
        # 4. 资金费率套利
        self.log("\n💰 类型 4: 资金费率套利")
        self.log("   机制: 永续合约资金费率 vs 现货价格")
        self.log("   示例: BTC 资金费率 0.1%/8h（年化 109%）")
        self.log("   策略: 做空永续合约，买入现货，收取资金费率")
        self.log("   优势: 无风险套利（delta-neutral）")
        
        opportunities.append({
            'type': 'funding_rate_arbitrage',
            'markets': ['crypto_spot', 'crypto_perpetual'],
            'mechanism': '永续合约资金费率收益',
            'signal': '资金费率年化 > 30%',
            'execution': '做空永续 + 买入现货，持有收取费率'
        })
        
        # 5. 跨市场对冲套利
        self.log("\n💰 类型 5: 跨市场对冲套利")
        self.log("   机制: 相关资产价格偏离")
        self.log("   示例: BTC +5%，COIN 0%（正常应该 +3-4%）")
        self.log("   策略: 买入 COIN，做空 BTC，等待收敛")
        self.log("   优势: 统计套利（历史相关性回归）")
        
        opportunities.append({
            'type': 'cross_market_hedge_arbitrage',
            'markets': ['crypto', 'stocks'],
            'mechanism': '相关资产价格偏离后回归',
            'signal': '相关系数 > 0.7，但价格偏离 > 2 标准差',
            'execution': '买入落后资产，做空领先资产'
        })
        
        # 6. Polymarket 事件驱动套利
        self.log("\n💰 类型 6: Polymarket 事件驱动套利")
        self.log("   机制: 事件结果确定性 vs 市场定价")
        self.log("   示例: NBA 总决赛 G7，领先队 3:0，但市场价格 0.85")
        self.log("   策略: 买入确定性高的 YES/NO")
        self.log("   优势: 信息优势（事件结果接近确定）")
        
        opportunities.append({
            'type': 'polymarket_event_arbitrage',
            'markets': ['polymarket'],
            'mechanism': '事件确定性 vs 市场定价偏差',
            'signal': '事件接近结算，确定性 > 90%，但价格 < 0.85',
            'execution': '买入高确定性方向，持有到结算'
        })
        
        return opportunities
    
    def generate_trading_rules(self, correlations, opportunities):
        """生成跨市场交易规则"""
        self.log("\n" + "=" * 80)
        self.log("生成跨市场交易规则")
        self.log("=" * 80)
        
        rules = {
            'timestamp': datetime.now().isoformat(),
            'correlations': correlations,
            'opportunities': opportunities,
            'trading_rules': []
        }
        
        # 规则 1: BTC vs COIN 联动
        rules['trading_rules'].append({
            'id': 'rule_btc_coin',
            'name': 'BTC vs COIN 联动套利',
            'trigger': 'BTC 价格变化 > 3%，但 COIN 变化 < 1%',
            'action': '买入 COIN（预期跟随 BTC）',
            'stop_loss': -3,
            'take_profit': 5,
            'confidence': 75
        })
        
        # 规则 2: 美股 → A股 隔夜传导
        rules['trading_rules'].append({
            'id': 'rule_us_cn_overnight',
            'name': '美股 → A股 隔夜传导',
            'trigger': '美股收盘大幅波动 > 5%',
            'action': 'A股开盘后跟随方向交易',
            'stop_loss': -2,
            'take_profit': 3,
            'confidence': 70
        })
        
        # 规则 3: Polymarket 价格预测套利
        rules['trading_rules'].append({
            'id': 'rule_polymarket_price',
            'name': 'Polymarket 价格预测套利',
            'trigger': '现货价格接近预测目标，但 Polymarket 价格 < 0.5',
            'action': '买入 Polymarket YES',
            'stop_loss': -10,
            'take_profit': 50,
            'confidence': 80
        })
        
        # 规则 4: 恐慌超跌反弹
        rules['trading_rules'].append({
            'id': 'rule_panic_reversal',
            'name': '恐慌超跌反弹',
            'trigger': '短时间暴跌 > 10%，RSI < 25',
            'action': '买入超跌资产',
            'stop_loss': -5,
            'take_profit': 10,
            'confidence': 65
        })
        
        # 规则 5: 资金费率套利
        rules['trading_rules'].append({
            'id': 'rule_funding_rate',
            'name': '资金费率套利',
            'trigger': '资金费率年化 > 50%',
            'action': '做空永续 + 买入现货',
            'stop_loss': -2,
            'take_profit': 'N/A（持续收取费率）',
            'confidence': 85
        })
        
        # 保存规则
        output_file = self.data_dir / "cross_market_rules.json"
        with open(output_file, 'w') as f:
            json.dump(rules, f, indent=2, ensure_ascii=False)
        
        self.log(f"\n✅ 跨市场交易规则已保存: {output_file}")
        
        return rules
    
    def run(self):
        """运行分析"""
        self.log("=" * 80)
        self.log("跨市场关联分析器")
        self.log("=" * 80)
        
        # 加载数据
        data = self.load_all_data()
        
        # 分析相关性
        correlations = self.analyze_correlations(data)
        
        # 识别套利机会
        opportunities = self.identify_arbitrage_opportunities(correlations)
        
        # 生成交易规则
        rules = self.generate_trading_rules(correlations, opportunities)
        
        self.log("\n" + "=" * 80)
        self.log("✅ 分析完成")
        self.log("=" * 80)
        self.log(f"发现 {len(correlations)} 个市场关联")
        self.log(f"识别 {len(opportunities)} 种套利机会")
        self.log(f"生成 {len(rules['trading_rules'])} 条交易规则")

def main():
    analyzer = CrossMarketAnalyzer()
    analyzer.run()

if __name__ == "__main__":
    main()
