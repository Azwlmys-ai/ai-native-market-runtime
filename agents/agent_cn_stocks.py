#!/usr/bin/env python3
"""
A 股套利分析器 (Agent CN Stocks)
职责：分析 Polymarket 中国相关市场与 A 股的套利机会
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir

class AgentCNStocks:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # A 股公司映射（Polymarket 关键词 -> A 股代码）
        self.stock_mapping = {
            # 科技公司
            'huawei': ['002502', '600584'],  # 华为概念股：鼎龙股份、长电科技
            'xiaomi': ['002475', '300782'],  # 小米概念股：立讯精密、卓胜微
            'alibaba': ['002024', '002230'],  # 阿里概念股：苏宁易购、科大讯飞
            'tencent': ['300059', '002027'],  # 腾讯概念股：东方财富、分众传媒
            'bytedance': ['300059', '002027'],  # 字节跳动概念股
            'baidu': ['002230', '300033'],  # 百度概念股：科大讯飞、同花顺
            
            # 新能源汽车
            'byd': ['002594'],  # 比亚迪
            'nio': ['600104', '002594'],  # 蔚来概念股：上汽集团、比亚迪
            'xpeng': ['002594', '600104'],  # 小鹏概念股
            'li auto': ['002594', '600104'],  # 理想概念股
            'catl': ['300750'],  # 宁德时代
            
            # 芯片半导体
            'smic': ['688981'],  # 中芯国际
            'semiconductor': ['688041', '688396'],  # 半导体：海光信息、华润微
            'chip': ['688041', '688396', '688008'],  # 芯片
            
            # 房地产
            'evergrande': ['000002', '001979'],  # 恒大概念：万科、招商蛇口
            'country garden': ['000002', '001979'],  # 碧桂园概念
            'real estate': ['000002', '600048'],  # 房地产：万科、保利发展
            
            # 金融
            'china bank': ['601398', '601939'],  # 中国银行、建设银行
            'icbc': ['601398'],  # 工商银行
            'ping an': ['601318'],  # 中国平安
            
            # 消费品
            'moutai': ['600519'],  # 贵州茅台
            'wuliangye': ['000858'],  # 五粮液
            'luckin': ['600887', '002557'],  # 瑞幸概念股：伊利股份、洽洽食品
            
            # 医药
            'sinopharm': ['600276', '300015'],  # 医药：恒瑞医药、爱尔眼科
            'healthcare': ['600276', '300015'],  # 医疗
            
            # 能源
            'petrochina': ['601857'],  # 中国石油
            'sinopec': ['600028'],  # 中国石化
            
            # 航空航天
            'comac': ['600893', '600038'],  # 商飞概念：航发动力、中直股份
            'space': ['600893', '002025'],  # 航天概念
        }
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent CN Stocks] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"agent_cn_stocks_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_data(self):
        """加载数据，加重试"""
        import time
        
        data_file = self.data_dir / "latest_data.json"
        
        for attempt in range(3):  # 重试3次
            try:
                if not data_file.exists():
                    self.log("❌ latest_data.json 不存在")
                    if attempt < 2:
                        time.sleep(1)  # 退避1秒
                        continue
                    return None, None
                
                with open(data_file, 'r') as f:
                    data = json.load(f)
                
                # Polymarket 市场（兼容两种格式）
                polymarket_markets = data.get('polymarket', {}).get('markets', [])
                if not polymarket_markets:
                    polymarket_markets = data.get('polymarket_markets', [])
                
                if not polymarket_markets:
                    self.log("❌ Polymarket 市场数据为空")
                    if attempt < 2:
                        time.sleep(1)
                        continue
                    return None, None
                
                # A 股数据
                cn_stocks_data = data.get('cn_stocks', {}).get('data', [])
                
                if not cn_stocks_data:
                    self.log("❌ A 股数据为空")
                    if attempt < 2:
                        time.sleep(1)
                        continue
                    return None, None
                
                cn_stocks = {stock['code']: stock for stock in cn_stocks_data}
                
                self.log(f"✅ 加载 {len(polymarket_markets)} 个 Polymarket 市场，{len(cn_stocks)} 只 A 股")
                
                return polymarket_markets, cn_stocks
            
            except json.JSONDecodeError as e:
                self.log(f"⚠️ JSON 解析失败 (尝试 {attempt+1}/3): {e}")
                if attempt < 2:
                    time.sleep(2)  # JSON损坏，退避更长
                    continue
                return None, None
            except Exception as e:
                self.log(f"❌ 数据加载异常 (尝试 {attempt+1}/3): {e}")
                if attempt < 2:
                    time.sleep(1)
                    continue
                return None, None
        
        return None, None
    
    def find_related_stocks(self, market_question):
        """根据市场问题找到相关 A 股"""
        question_lower = market_question.lower()
        
        related_stocks = []
        for keyword, stock_codes in self.stock_mapping.items():
            if keyword in question_lower:
                related_stocks.extend(stock_codes)
        
        # 去重
        return list(set(related_stocks))
    
    def analyze_arbitrage(self, market, cn_stocks):
        """分析套利机会"""
        market_id = market.get('slug')
        market_question = market.get('question', '')
        outcomes = market.get('outcomes', [])
        outcome_prices = market.get('outcome_prices', [])
        
        if not outcomes or not outcome_prices:
            return None
        
        # 找到相关 A 股
        related_stock_codes = self.find_related_stocks(market_question)
        
        if not related_stock_codes:
            return None
        
        # 获取 A 股数据
        related_stocks = []
        for code in related_stock_codes:
            if code in cn_stocks:
                related_stocks.append(cn_stocks[code])
        
        if not related_stocks:
            return None
        
        # 分析逻辑：
        # 1. 如果 Polymarket 预测中国公司/事件看涨，但 A 股相关股票下跌 -> 套利机会
        # 2. 如果 Polymarket 预测看跌，但 A 股相关股票上涨 -> 套利机会
        
        signals = []
        
        for i, outcome in enumerate(outcomes):
            if i >= len(outcome_prices):
                continue
            
            price = outcome_prices[i]
            try:
                price = float(price)
            except (TypeError, ValueError):
                self.log(f"⚠️ 跳过非数字价格: outcome={outcome!r} price={price!r}")
                continue

            # YES 价格高（市场看涨）
            if outcome.upper() == 'YES' and price > 0.6:
                # 检查 A 股是否下跌
                for stock in related_stocks:
                    change_pct = stock.get('change_pct', 0)
                    
                    if change_pct < -3:  # A 股下跌超过 3%
                        # 套利机会：Polymarket 做空 YES，A 股做多
                        signal = {
                            'market_id': market_id,
                            'market_name': market_question,
                            'polymarket_outcome': outcome,
                            'polymarket_price': price,
                            'polymarket_action': 'SELL',  # 做空 YES
                            'stock_code': stock['code'],
                            'stock_name': stock['name'],
                            'stock_price': stock['price'],
                            'stock_change_pct': change_pct,
                            'stock_action': 'BUY',  # 做多 A 股
                            'strategy': 'Polymarket_CNStocks_Divergence',
                            'reasoning': f'Polymarket 预测看涨（YES {price:.2f}），但 A 股 {stock["name"]} 下跌 {change_pct:.2f}%，存在定价分歧',
                            'confidence': min(85, 60 + abs(change_pct) * 5),  # 跌幅越大，置信度越高
                            'position_size': 0.08,  # 8% 仓位
                            'timestamp': datetime.now().isoformat()
                        }
                        signals.append(signal)
            
            # NO 价格高（市场看跌）
            elif outcome.upper() == 'NO' and price > 0.6:
                # 检查 A 股是否上涨
                for stock in related_stocks:
                    change_pct = stock.get('change_pct', 0)
                    
                    if change_pct > 3:  # A 股上涨超过 3%
                        # 套利机会：Polymarket 做空 NO，A 股做空（或不操作）
                        signal = {
                            'market_id': market_id,
                            'market_name': market_question,
                            'polymarket_outcome': outcome,
                            'polymarket_price': price,
                            'polymarket_action': 'SELL',  # 做空 NO
                            'stock_code': stock['code'],
                            'stock_name': stock['name'],
                            'stock_price': stock['price'],
                            'stock_change_pct': change_pct,
                            'stock_action': 'HOLD',  # A 股不操作（做空需要融券）
                            'strategy': 'Polymarket_CNStocks_Divergence',
                            'reasoning': f'Polymarket 预测看跌（NO {price:.2f}），但 A 股 {stock["name"]} 上涨 {change_pct:.2f}%，存在定价分歧',
                            'confidence': min(85, 60 + abs(change_pct) * 5),
                            'position_size': 0.08,
                            'timestamp': datetime.now().isoformat()
                        }
                        signals.append(signal)
        
        return signals
    
    def run(self):
        """主流程"""
        self.log("=" * 60)
        self.log("开始 A 股套利分析")
        
        # 加载数据
        polymarket_markets, cn_stocks = self.load_data()
        
        if not polymarket_markets or not cn_stocks:
            self.log("❌ 数据加载失败")
            return
        
        self.log(f"📊 Polymarket 市场: {len(polymarket_markets)} 个")
        self.log(f"📊 A 股数据: {len(cn_stocks)} 只")
        
        # 分析套利机会
        all_signals = []
        
        for market in polymarket_markets:
            signals = self.analyze_arbitrage(market, cn_stocks)
            if signals:
                all_signals.extend(signals)
        
        # 保存信号
        signals_file = self.data_dir / "cn_stocks_arbitrage_signals.json"
        
        with open(signals_file, 'w') as f:
            json.dump(all_signals, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 发现 {len(all_signals)} 个 A 股套利信号")
        
        # 输出前 3 个信号
        for i, signal in enumerate(all_signals[:3], 1):
            self.log(f"  {i}. {signal['market_name'][:50]}...")
            self.log(f"     Polymarket: {signal['polymarket_action']} {signal['polymarket_outcome']} @ {signal['polymarket_price']:.2f}")
            self.log(f"     A 股: {signal['stock_action']} {signal['stock_name']} ({signal['stock_code']}) @ ¥{signal['stock_price']:.2f} ({signal['stock_change_pct']:+.2f}%)")
            self.log(f"     置信度: {signal['confidence']}%")
        
        self.log("=" * 60)

def main():
    agent = AgentCNStocks()
    agent.run()

if __name__ == "__main__":
    main()
