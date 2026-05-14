#!/usr/bin/env python3
"""
跨市场回测系统 v2.0
- 支持加密货币、美股、A股、Polymarket 多市场
- 实现跨市场套利策略
- 基于 cross_market_rules.json 规则
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

from llm_helper import call_llm_sync

class CrossMarketBacktest:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.historical_dir = self.data_dir / "historical"
        self.logs_dir = self.base_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # 回测参数
        self.initial_capital = 30000  # 增加初始资金（A股 $20k + 其他 $10k）
        self.current_capital = 30000
        self.positions = []
        self.trades = []
        self.peak_capital = 30000
        
        # 资金分配（按市场）
        self.capital_allocation = {
            'polymarket': 0.20,  # 20% 给 Polymarket（$6000，胜率 100%）
            'crypto': 0.10,      # 10% 给加密货币（$3000）
            'us_stocks': 0.067,  # 6.7% 给美股（$2000）
            'cn_stocks': 0.50,   # 50% 给 A 股（$15000）
            'hk_stocks': 0.133   # 13.3% 给港股（$4000）
        }
        
        # 持仓限制（按市场）
        self.max_positions_per_market = {
            'polymarket': 8,     # Polymarket 持仓限制
            'crypto': 4,         # 加密货币持仓
            'us_stocks': 3,      # 美股 3 个持仓
            'cn_stocks': 4,      # A 股 4 个持仓（全部股票）
            'hk_stocks': 5       # 港股 5 个持仓（全部股票）
        }
        
        # 交易目标
        self.target_trades = 150  # 提高至150笔
        
        # 风险控制
        self.max_consecutive_losses = 5
        self.consecutive_losses = 0
        self.max_drawdown_pct = 0.10  # 放宽回撤限制到 10%
        self.peak_capital = self.initial_capital
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [CrossMarket] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"cross_market_backtest_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_historical_data(self):
        """加载所有市场历史数据"""
        self.log("加载跨市场历史数据...")
        
        data = {
            'crypto': {},
            'us_stocks': {},
            'cn_stocks': {},
            'hk_stocks': {},
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
        
        # 加载资金费率
        for symbol in ['BTC', 'ETH']:
            combined = []
            for month in ['march', 'april']:
                file_path = self.historical_dir / f"okx_{symbol}_USDT_SWAP_funding_rate_{month}_2026.json"
                if file_path.exists():
                    with open(file_path, 'r') as f:
                        combined.extend(json.load(f))
            
            combined.sort(key=lambda x: x['timestamp'])
            data['crypto'][f'{symbol}_FUNDING'] = combined
            self.log(f"  ✅ {symbol} 资金费率: {len(combined)} 条")
        
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
        
        # 加载港股
        hk_file = self.historical_dir / "hk_stocks_march_2026.json"
        if hk_file.exists():
            with open(hk_file, 'r') as f:
                data['hk_stocks'] = json.load(f)
            self.log(f"  ✅ 港股: {len(data['hk_stocks'])} 只")
        
        # 加载 Polymarket 数据
        try:
            with open('data/historical/polymarket_markets_extended_march_april_2026.json', 'r') as f:
                data['polymarket'] = json.load(f)
                self.log(f"  ✅ Polymarket 扩展: {len(data['polymarket'])} 个市场")
        except Exception as e:
            self.log(f"  ⚠️ 加载 Polymarket 扩展数据失败: {e}")
            try:
                with open('data/historical/polymarket_markets_march_april_2026.json', 'r') as f:
                    data['polymarket'] = json.load(f)
                    self.log(f"  ✅ Polymarket 原始: {len(data['polymarket'])} 个市场")
            except Exception as e2:
                self.log(f"  ❌ 加载 Polymarket 数据失败: {e2}")
                data['polymarket'] = []
        
        return data
    
    def load_cross_market_rules(self):
        """加载跨市场交易规则"""
        rules_file = self.data_dir / "cross_market_rules.json"
        
        if not rules_file.exists():
            self.log("⚠️ 无跨市场规则文件")
            return None
        
        with open(rules_file, 'r') as f:
            rules = json.load(f)
        
        self.log(f"✅ 加载跨市场规则: {len(rules['trading_rules'])} 条")
        return rules
    
    def calculate_rsi(self, prices, period=14):
        """计算 RSI"""
        if len(prices) < period + 1:
            return 50
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def check_rule_btc_coin(self, data, index):
        """规则 1: BTC vs COIN 联动套利"""
        if 'BTC' not in data['crypto'] or 'COIN' not in data['us_stocks']:
            return None
        
        if index < 20:
            return None
        
    def check_rule_btc_coin(self, data, index):
        """检查 BTC vs COIN 联动规则（放宽阈值）"""
        if 'BTC' not in data['crypto'] or 'COIN' not in data['us_stocks']:
            return None
        
        if index < 10 or index >= len(data['crypto']['BTC']) or index >= len(data['us_stocks']['COIN']):
            return None
        
        # 计算 BTC 涨跌幅
        btc_current = data['crypto']['BTC'][index]['close']
        btc_prev = data['crypto']['BTC'][index - 10]['close']
        btc_change = (btc_current - btc_prev) / btc_prev
        
        # 计算 COIN 涨跌幅
        coin_current = data['us_stocks']['COIN'][index]['close']
        coin_prev = data['us_stocks']['COIN'][index - 10]['close']
        coin_change = (coin_current - coin_prev) / coin_prev
        
        # 放宽条件：BTC 涨 > 4%，COIN 涨幅 < BTC 一半（联动滞后）
        if btc_change > 0.04 and coin_change < btc_change * 0.5:
            return {
                'rule': 'rule_btc_coin',
                'action': 'buy',
                'asset': 'COIN',
                'market': 'us_stocks',
                'price': coin_current,
                'amount': 150,  # 增加单笔金额（美股资金 $2000）
                'stop_loss': -0.03,
                'take_profit': 0.10,
                'confidence': 75,
                'reason': f'BTC {btc_change*100:.1f}%, COIN {coin_change*100:.1f}%（联动滞后）'
            }
        
        return None
    
    def check_rule_panic_reversal(self, data, index):
        """规则 4: 恐慌超跌反弹"""
        signals = []
        
        # 检查加密货币
        for symbol in ['BTC', 'ETH', 'SOL', 'BNB']:
            if symbol not in data['crypto']:
                continue
            
            crypto_data = data['crypto'][symbol]
            if index < 20 or index >= len(crypto_data):
                continue
            
            current_price = crypto_data[index]['close']
            prev_price = crypto_data[index - 5]['close']
            price_change = (current_price - prev_price) / prev_price
            
            # 计算 RSI
            prices = [crypto_data[i]['close'] for i in range(max(0, index-20), index+1)]
            rsi = self.calculate_rsi(prices)
            
            # 触发条件: 暴跌 > 15%, RSI < 20（收紧条件）
            if price_change < -0.15 and rsi < 20:
                signals.append({
                    'rule': 'rule_panic_reversal',
                    'action': 'buy',
                    'asset': symbol,
                    'market': 'crypto',
                    'price': current_price,
                    'amount': 80,  # 减少单笔金额
                    'stop_loss': -0.05,
                    'take_profit': 0.10,
                    'confidence': 65,
                    'reason': f'{symbol} 暴跌 {price_change*100:.1f}%, RSI {rsi:.1f}（超跌反弹）'
                })
        
        # 检查美股
        for symbol in data['us_stocks'].keys():
            stock_data = data['us_stocks'][symbol]
            if index < 20 or index >= len(stock_data):
                continue
            
            current_price = stock_data[index]['close']
            prev_price = stock_data[index - 5]['close']
            price_change = (current_price - prev_price) / prev_price
            
            # 触发条件: 暴跌 > 8%（放宽条件，增加交易机会）
            if price_change < -0.08:
                signals.append({
                    'rule': 'rule_panic_reversal',
                    'action': 'buy',
                    'asset': symbol,
                    'market': 'us_stocks',
                    'price': current_price,
                    'amount': 150,  # 增加单笔金额（美股资金 $2000）
                    'stop_loss': -0.05,
                    'take_profit': 0.10,
                    'confidence': 65,
                    'reason': f'{symbol} 暴跌 {price_change*100:.1f}%（超跌反弹）'
                })
        
        # 检查 A股（T+1 限制）
        for symbol in data['cn_stocks'].keys():
            stock_data = data['cn_stocks'][symbol]
            if index < 20 or index >= len(stock_data):
                continue
            
            current_price = stock_data[index]['close']
            prev_price = stock_data[index - 5]['close']
            price_change = (current_price - prev_price) / prev_price
            
            # A股 T+1：暴跌 > 8% 时买入，次日卖出（放宽条件）
            if price_change < -0.08:
                signals.append({
                    'rule': 'rule_cn_stocks_t1',
                    'action': 'buy',
                    'asset': symbol,
                    'market': 'cn_stocks',
                    'price': current_price,
                    'amount': 3000,  # A股单笔 $3000（总资金 $15000）
                    'stop_loss': -0.05,
                    'take_profit': 0.10,
                    'confidence': 60,
                    'reason': f'{symbol} 暴跌 {price_change*100:.1f}%（T+1 反弹）'
                })
        
        # 检查港股
        for symbol in data['hk_stocks'].keys():
            stock_data = data['hk_stocks'][symbol]
            if index < 20 or index >= len(stock_data):
                continue
            
            current_price = stock_data[index]['close']
            prev_price = stock_data[index - 5]['close']
            price_change = (current_price - prev_price) / prev_price
            
            # 港股：暴跌 > 7% 时买入（T+0，可当日卖出）
            if price_change < -0.07:
                signals.append({
                    'rule': 'rule_hk_stocks_panic',
                    'action': 'buy',
                    'asset': symbol,
                    'market': 'hk_stocks',
                    'price': current_price,
                    'amount': 800,  # 港股单笔 $800（总资金 $4000）
                    'stop_loss': -0.05,
                    'take_profit': 0.10,
                    'confidence': 65,
                    'reason': f'{symbol} 暴跌 {price_change*100:.1f}%（恐慌反弹）'
                })
        
        return signals[0] if signals else None
    
    def check_rule_funding_rate(self, data, index):
        """规则 5: 资金费率套利"""
        signals = []
        
        for symbol in ['BTC', 'ETH']:
            funding_key = f'{symbol}_FUNDING'
            if funding_key not in data['crypto']:
                continue
            
            funding_data = data['crypto'][funding_key]
            if index >= len(funding_data):
                continue
            
            funding_rate = funding_data[index].get('funding_rate', 0)
            
            # 年化资金费率 = 费率 * (365 * 24 / 8)
            annualized_rate = float(funding_rate) * 365 * 3
            
            # 触发条件: 年化 > 50%
            if annualized_rate > 0.50:
                signals.append({
                    'rule': 'rule_funding_rate',
                    'action': 'buy',
                    'asset': symbol,
                    'market': 'crypto',
                    'price': data['crypto'][symbol][index]['close'],
                    'amount': 120,
                    'stop_loss': -0.02,
                    'take_profit': None,  # 持续收取费率
                    'confidence': 85,
                    'reason': f'{symbol} 资金费率年化 {annualized_rate*100:.1f}%（套利机会）'
                })
        
        return signals[0] if signals else None
    
    def check_polymarket_price_arbitrage(self, data, index):
        """规则 3: Polymarket 价格预测套利"""
        if not data['polymarket']:
            return None
        
        signals = []
        
        for market in data['polymarket']:
            if market['category'] != 'crypto':
                continue
            
            market_id = market['id']
            question = market['question']
            price_history = market.get('price_history', [])
            
            if index >= len(price_history):
                continue
            
            pm_price = price_history[index]['price']
            
            # 检查 BTC 相关市场
            if 'bitcoin' in question.lower() or 'btc' in question.lower():
                if 'BTC' not in data['crypto'] or index >= len(data['crypto']['BTC']):
                    continue
                
                btc_price = data['crypto']['BTC'][index]['close']
                
                # 示例: "Will Bitcoin hit $100k by April 30?"
                if '$100k' in question or '100k' in question:
                    target_price = 100000
                    distance = (target_price - btc_price) / btc_price
                    
                    # 放宽条件：距离 < 30%，且 PM 价格与实际概率偏差 > 20%
                    # 简单模型：距离越小，概率越高
                    implied_prob = max(0.1, 1 - distance / 0.5)  # 距离 0% = 100% 概率，距离 50% = 0% 概率
                    
                    # 只在明显低估时买入，或明显高估时做空
                    if distance < 0.30:
                        if pm_price < implied_prob - 0.25:
                            # 市场低估，买入 YES
                            signals.append({
                                'rule': 'rule_polymarket_price',
                                'action': 'buy',
                                'asset': market_id,
                                'market': 'polymarket',
                                'price': pm_price,
                                'amount': 80,  # 减少单笔金额
                                'stop_loss': -0.10,
                                'take_profit': 0.50,
                                'confidence': 75,
                                'reason': f'BTC ${btc_price:.0f}，距离 $100k {distance*100:.1f}%，隐含概率 {implied_prob:.2f}，PM {pm_price:.2f}（低估买入）'
                            })
                        elif pm_price > implied_prob + 0.25:
                            # 市场高估，做空 YES
                            signals.append({
                                'rule': 'rule_polymarket_price',
                                'action': 'sell',
                                'asset': market_id,
                                'market': 'polymarket',
                                'price': pm_price,
                                'amount': 80,  # 减少单笔金额
                                'stop_loss': -0.10,
                                'take_profit': 0.50,
                                'confidence': 75,
                                'reason': f'BTC ${btc_price:.0f}，距离 $100k {distance*100:.1f}%，隐含概率 {implied_prob:.2f}，PM {pm_price:.2f}（高估做空）'
                            })
                
                # "Will Bitcoin drop below $50k?"
                elif '$50k' in question or '50k' in question:
                    if 'drop' in question.lower() or 'below' in question.lower():
                        target_price = 50000
                        distance = (btc_price - target_price) / btc_price
                        
                        # 距离越大，跌破概率越低
                        implied_prob = max(0.05, 1 - distance / 0.3)
                        
                        # 放宽条件：只要市场价格 > 隐含概率 + 0.20 就做空
                        if pm_price > implied_prob + 0.20:
                            signals.append({
                                'rule': 'rule_polymarket_price',
                                'action': 'sell',  # 做空 YES
                                'asset': market_id,
                                'market': 'polymarket',
                                'price': pm_price,
                                'amount': 120,
                                'stop_loss': -0.15,  # 放宽止损至 -15%
                                'take_profit': 0.30,
                                'confidence': 75,
                                'reason': f'BTC ${btc_price:.0f}，距离 $50k {distance*100:.1f}%，隐含概率 {implied_prob:.2f}，PM {pm_price:.2f}（高估做空）'
                            })
            
            # 检查 ETH 相关市场
            elif 'ethereum' in question.lower() or 'eth' in question.lower():
                if 'ETH' not in data['crypto'] or index >= len(data['crypto']['ETH']):
                    continue
                
                eth_price = data['crypto']['ETH'][index]['close']
                
                if '$5k' in question or '5k' in question or '5000' in question:
                    target_price = 5000
                    distance = (target_price - eth_price) / eth_price
                    implied_prob = max(0.1, 1 - distance / 0.5)
                    
                    if distance < 0.30 and abs(pm_price - implied_prob) > 0.20:
                        signals.append({
                            'rule': 'rule_polymarket_price',
                            'action': 'buy',
                            'asset': market_id,
                            'market': 'polymarket',
                            'price': pm_price,
                            'amount': 120,
                            'stop_loss': -0.10,
                            'take_profit': 0.50,
                            'confidence': 70,
                            'reason': f'ETH ${eth_price:.0f}，距离 $5k {distance*100:.1f}%，隐含概率 {implied_prob:.2f}，PM {pm_price:.2f}'
                        })
            
            # 检查 SOL 相关市场
            elif 'solana' in question.lower() or 'sol' in question.lower():
                if 'SOL' not in data['crypto'] or index >= len(data['crypto']['SOL']):
                    continue
                
                sol_price = data['crypto']['SOL'][index]['close']
                
                if '$200' in question or '200' in question:
                    target_price = 200
                    distance = (target_price - sol_price) / sol_price
                    implied_prob = max(0.1, 1 - distance / 0.5)
                    
                    if distance < 0.30 and abs(pm_price - implied_prob) > 0.20:
                        signals.append({
                            'rule': 'rule_polymarket_price',
                            'action': 'buy',
                            'asset': market_id,
                            'market': 'polymarket',
                            'price': pm_price,
                            'amount': 120,
                            'stop_loss': -0.10,
                            'take_profit': 0.50,
                            'confidence': 70,
                            'reason': f'SOL ${sol_price:.0f}，距离 $200 {distance*100:.1f}%，隐含概率 {implied_prob:.2f}，PM {pm_price:.2f}'
                        })
        
        return signals[0] if signals else None
    
    def check_crypto_rules(self, data, index):
        """检查加密货币规则（原有策略）"""
        signals = []
        
        for symbol in ['BTC', 'ETH', 'SOL', 'BNB']:
            if symbol not in data['crypto']:
                continue
            
            crypto_data = data['crypto'][symbol]
            if index < 20 or index >= len(crypto_data):
                continue
            
            current_price = crypto_data[index]['close']
            prices = [crypto_data[i]['close'] for i in range(max(0, index-20), index+1)]
            rsi = self.calculate_rsi(prices)
            
            # 超卖反弹（收紧条件：RSI < 30，且价格接近 20 日低点）
            if rsi < 30:
                low_20 = min(prices[-20:])
                if current_price < low_20 * 1.05:
                    signals.append({
                        'rule': 'crypto_oversold',
                        'action': 'buy',
                        'asset': symbol,
                        'market': 'crypto',
                        'price': current_price,
                        'amount': 80,  # 减少单笔金额
                        'stop_loss': -0.03,
                        'take_profit': 0.15,
                        'confidence': 75,
                        'reason': f'{symbol} RSI {rsi:.1f} 超卖反弹'
                    })
        
        return signals[0] if signals else None
    
    def analyze_market_opportunity(self, data, index, rules):
        """分析跨市场机会 - 轮询所有市场"""
        # 收集所有市场的信号
        all_signals = []
        
        # 1. 资金费率套利（最高优先级，85 置信度）
        signal = self.check_rule_funding_rate(data, index)
        if signal:
            all_signals.append(signal)
        
        # 2. Polymarket 价格预测套利（70 置信度）
        signal = self.check_polymarket_price_arbitrage(data, index)
        if signal:
            all_signals.append(signal)
        
        # 3. BTC vs COIN 联动（75 置信度）
        signal = self.check_rule_btc_coin(data, index)
        if signal:
            all_signals.append(signal)
        
        # 4. 加密货币超卖反弹（75 置信度）
        signal = self.check_crypto_rules(data, index)
        if signal:
            all_signals.append(signal)
        
        # 5. 恐慌超跌反弹（65 置信度）
        signal = self.check_rule_panic_reversal(data, index)
        if signal:
            all_signals.append(signal)
        
        # 按置信度排序，返回最高置信度的信号
        if all_signals:
            all_signals.sort(key=lambda x: x['confidence'], reverse=True)
            return all_signals[0]
        
        return None
    
    def execute_trade(self, signal, data, index):
        """执行交易"""
        # 检查资金
        if self.current_capital < signal['amount']:
            return
        
        # 检查市场持仓限制
        market = signal['market']
        current_positions_in_market = len([p for p in self.positions if p['market'] == market])
        
        if current_positions_in_market >= self.max_positions_per_market.get(market, 10):
            return
        
        # 检查市场资金分配
        market_capital_used = sum(p['amount'] for p in self.positions if p['market'] == market)
        market_capital_limit = self.initial_capital * self.capital_allocation.get(market, 0.25)
        
        if market_capital_used + signal['amount'] > market_capital_limit:
            return
        
        # 检查连续亏损（风险控制）
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.log(f"⚠️ 连续亏损 {self.consecutive_losses} 笔，暂停交易")
            return
        
        # 检查最大回撤（风险控制）
        self.peak_capital = max(self.peak_capital, self.current_capital)
        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        if drawdown > self.max_drawdown_pct:
            self.log(f"⚠️ 回撤 {drawdown*100:.2f}% 超过限制，暂停交易")
            return
        
        # 判断交易方向
        action = signal.get('action', 'buy')
        is_short = (action == 'sell')
        
        # 执行买入或做空
        shares = signal['amount'] / signal['price']
        
        position = {
            'asset': signal['asset'],
            'market': signal['market'],
            'entry_price': signal['price'],
            'entry_time': self.get_timestamp(data, signal['market'], signal['asset'], index),
            'shares': shares,
            'amount': signal['amount'],
            'stop_loss': signal['stop_loss'],
            'take_profit': signal['take_profit'],
            'rule': signal['rule'],
            'reason': signal['reason'],
            'is_short': is_short,  # 标记是否做空
            't1_entry_index': signal.get('t1_entry_index', index)  # A股 T+1 记录
        }
        
        self.positions.append(position)
        self.current_capital -= signal['amount']
        
        direction = "📉 做空" if is_short else "📈 买入"
        self.log(f"{direction} {signal['asset']} ({signal['market']}): ${signal['price']:.2f}, 数量: {shares:.4f}, 原因: {signal['reason']}")
    
    def get_timestamp(self, data, market, asset, index):
        """获取时间戳"""
        if market == 'crypto':
            if asset in data['crypto'] and index < len(data['crypto'][asset]):
                return data['crypto'][asset][index]['timestamp']
        elif market == 'us_stocks':
            if asset in data['us_stocks'] and index < len(data['us_stocks'][asset]):
                return data['us_stocks'][asset][index]['timestamp']
        elif market == 'cn_stocks':
            if asset in data['cn_stocks'] and index < len(data['cn_stocks'][asset]):
                return data['cn_stocks'][asset][index]['timestamp']
        elif market == 'hk_stocks':
            if asset in data['hk_stocks'] and index < len(data['hk_stocks'][asset]):
                return data['hk_stocks'][asset][index]['timestamp']
        
        return datetime.now().isoformat()
    
    def get_current_price(self, data, market, asset, index):
        """获取当前价格"""
        if market == 'crypto':
            if asset in data['crypto'] and index < len(data['crypto'][asset]):
                return data['crypto'][asset][index]['close']
        elif market == 'us_stocks':
            if asset in data['us_stocks'] and index < len(data['us_stocks'][asset]):
                return data['us_stocks'][asset][index]['close']
        elif market == 'cn_stocks':
            if asset in data['cn_stocks'] and index < len(data['cn_stocks'][asset]):
                return data['cn_stocks'][asset][index]['close']
        elif market == 'hk_stocks':
            if asset in data['hk_stocks'] and index < len(data['hk_stocks'][asset]):
                return data['hk_stocks'][asset][index]['close']
        elif market == 'polymarket':
            # Polymarket 使用 asset 作为 market_id
            for pm_market in data['polymarket']:
                if pm_market['id'] == asset:
                    price_history = pm_market.get('price_history', [])
                    if index < len(price_history):
                        return price_history[index]['price']
        
        return None
    
    def check_exit_conditions(self, data, index):
        """检查平仓条件"""
        positions_to_close = []
        
        for pos in self.positions:
            current_price = self.get_current_price(data, pos['market'], pos['asset'], index)
            
            if current_price is None:
                continue
            
            # 判断是否做空
            is_short = pos.get('is_short', False)
            
            if is_short:
                # 做空：价格下跌盈利，价格上涨亏损
                pnl_percent = (pos['entry_price'] - current_price) / pos['entry_price']
            else:
                # 做多：价格上涨盈利，价格下跌亏损
                pnl_percent = (current_price - pos['entry_price']) / pos['entry_price']
            
            # A股 T+1 检查：必须持有至少 24 小时（1 天）
            if pos['market'] == 'cn_stocks':
                t1_entry_index = pos.get('t1_entry_index', index)
                if index - t1_entry_index < 24:  # 未满 24 小时（1 天）
                    continue
            
            # 止损
            if pos['stop_loss'] and pnl_percent <= pos['stop_loss']:
                positions_to_close.append((pos, current_price, 'stop_loss'))
            
            # 止盈
            elif pos['take_profit'] and pnl_percent >= pos['take_profit']:
                positions_to_close.append((pos, current_price, 'take_profit'))
        
        # 执行平仓
        for pos, exit_price, reason in positions_to_close:
            self.close_position(pos, exit_price, reason, data, index)
    
    def close_position(self, pos, exit_price, reason, data, index):
        """平仓"""
        # 判断是否做空
        is_short = pos.get('is_short', False)
        
        if is_short:
            # 做空：入场卖出，出场买入
            # 盈利 = 入场金额 - 出场金额
            exit_amount = pos['shares'] * exit_price
            profit = pos['amount'] - exit_amount
        else:
            # 做多：入场买入，出场卖出
            # 盈利 = 出场金额 - 入场金额
            exit_amount = pos['shares'] * exit_price
            profit = exit_amount - pos['amount']
        
        pnl_percent = profit / pos['amount']
        
        # 更新连续亏损计数
        if profit < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        trade = {
            'asset': pos['asset'],
            'market': pos['market'],
            'entry_price': pos['entry_price'],
            'entry_time': pos['entry_time'],
            'exit_price': exit_price,
            'exit_time': self.get_timestamp(data, pos['market'], pos['asset'], index),
            'shares': pos['shares'],
            'entry_amount': pos['amount'],
            'exit_amount': exit_amount,
            'profit': profit,
            'pnl_percent': pnl_percent,
            'exit_reason': reason,
            'rule': pos['rule'],
            'reason': pos['reason'],
            'is_short': is_short
        }
        
        self.trades.append(trade)
        self.current_capital += pos['amount'] + profit  # 返还本金 + 盈亏
        self.positions.remove(pos)
        
        direction = "平空" if is_short else "卖出"
        self.log(f"📉 {direction} {pos['asset']} ({pos['market']}): ${exit_price:.2f}, 盈亏: ${profit:.2f} ({pnl_percent*100:.2f}%), 原因: {reason}")
    
    def run_backtest(self):
        """运行回测"""
        self.log("=" * 80)
        self.log("开始跨市场回测")
        self.log("=" * 80)
        
        # 加载数据
        data = self.load_historical_data()
        rules = self.load_cross_market_rules()
        
        # 确定最大时间长度
        max_length = 0
        for symbol in data['crypto'].keys():
            if not symbol.endswith('_FUNDING'):
                max_length = max(max_length, len(data['crypto'][symbol]))
        
        self.log(f"\n回测时间范围: {max_length} 小时")
        self.log(f"初始资金: ${self.initial_capital:,.2f}")
        self.log(f"目标交易: {self.target_trades} 笔\n")
        
        # 回测循环
        for i in range(max_length):
            # 检查是否达到目标
            if len(self.trades) >= self.target_trades:
                self.log(f"\n✅ 达到目标交易数 {self.target_trades} 笔")
                break
            
            # 检查平仓
            self.check_exit_conditions(data, i)
            
            # 每 10 小时分析一次
            if i % 10 == 0:
                signal = self.analyze_market_opportunity(data, i, rules)
                if signal:
                    self.execute_trade(signal, data, i)
            
            # 进度
            if i % 100 == 0:
                self.log(f"进度: {i}/{max_length} ({i/max_length*100:.1f}%), 交易: {len(self.trades)}/{self.target_trades}, 资金: ${self.current_capital:,.2f}")
        
        # 强制平仓
        self.log("\n强制平仓所有持仓...")
        for pos in list(self.positions):
            exit_price = self.get_current_price(data, pos['market'], pos['asset'], max_length - 1)
            if exit_price:
                self.close_position(pos, exit_price, 'forced', data, max_length - 1)
        
        # 保存结果
        self.save_results()
        
        # 生成报告
        self.generate_report()
    
    def save_results(self):
        """保存回测结果"""
        output_file = self.data_dir / "cross_market_backtest_trades.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.trades, f, indent=2, ensure_ascii=False)
        
        self.log(f"\n✅ 交易记录已保存: {output_file}")
    
    def generate_report(self):
        """生成回测报告"""
        self.log("\n" + "=" * 80)
        self.log("跨市场回测报告")
        self.log("=" * 80)
        
        if not self.trades:
            self.log("无交易记录")
            return
        
        # 总体统计
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t['profit'] > 0]
        losing_trades = [t for t in self.trades if t['profit'] <= 0]
        
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        total_profit = sum(t['profit'] for t in self.trades)
        total_return = total_profit / self.initial_capital
        
        avg_win = sum(t['profit'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t['profit'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        self.log(f"\n总交易数: {total_trades}")
        self.log(f"盈利交易: {len(winning_trades)} ({win_rate*100:.1f}%)")
        self.log(f"亏损交易: {len(losing_trades)} ({(1-win_rate)*100:.1f}%)")
        self.log(f"总收益: ${total_profit:.2f} ({total_return*100:.2f}%)")
        self.log(f"最终资金: ${self.current_capital:.2f}")
        self.log(f"平均盈利: ${avg_win:.2f}")
        self.log(f"平均亏损: ${avg_loss:.2f}")
        self.log(f"盈亏比: {profit_factor:.2f}")
        
        # 按市场统计
        self.log("\n" + "-" * 80)
        self.log("按市场统计")
        self.log("-" * 80)
        
        market_stats = defaultdict(lambda: {'trades': 0, 'profit': 0})
        for t in self.trades:
            market_stats[t['market']]['trades'] += 1
            market_stats[t['market']]['profit'] += t['profit']
        
        for market, stats in sorted(market_stats.items()):
            self.log(f"{market}: {stats['trades']} 笔, ${stats['profit']:.2f}")
        
        # 按规则统计
        self.log("\n" + "-" * 80)
        self.log("按规则统计")
        self.log("-" * 80)
        
        rule_stats = defaultdict(lambda: {'trades': 0, 'profit': 0, 'wins': 0})
        for t in self.trades:
            rule_stats[t['rule']]['trades'] += 1
            rule_stats[t['rule']]['profit'] += t['profit']
            if t['profit'] > 0:
                rule_stats[t['rule']]['wins'] += 1
        
        for rule, stats in sorted(rule_stats.items()):
            win_rate = stats['wins'] / stats['trades'] if stats['trades'] > 0 else 0
            self.log(f"{rule}: {stats['trades']} 笔, 胜率 {win_rate*100:.1f}%, ${stats['profit']:.2f}")

def main():
    backtest = CrossMarketBacktest()
    backtest.run_backtest()

if __name__ == "__main__":
    main()
