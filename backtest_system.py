#!/usr/bin/env python3
"""
历史回测系统 - 使用 3 月份数据进行模拟交易
- 从 3 月 1 日开始
- 使用学习知识库的策略
- 执行 100 笔交易
- 计算胜率和收益
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

from llm_helper import call_llm_sync

class HistoricalBacktest:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.historical_dir = self.data_dir / "historical"
        self.logs_dir = self.base_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # 回测参数
        self.initial_capital = 10000  # 初始资金 $10,000
        self.current_capital = self.initial_capital
        self.positions = []  # 持仓
        self.trades = []  # 交易记录
        self.target_trades = 100  # 目标交易数
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Backtest] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"backtest_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_historical_data(self):
        """加载历史数据（3月 + 4月 + 5月）"""
        self.log("加载历史数据...")
        
        data = {
            'okx_btc': [],
            'okx_eth': [],
            'okx_bnb': [],
            'okx_sol': [],
            'okx_btc_funding': [],
            'okx_eth_funding': [],
            'us_stocks': {},
            'cn_stocks': {}
        }
        
        # 加载 OKX K 线数据（3月 + 4月 + 5月）
        for symbol in ['BTC', 'ETH', 'BNB', 'SOL']:
            combined_klines = []
            
            # 3月数据
            march_file = self.historical_dir / f"okx_{symbol}_USDT_klines_march_2026.json"
            if march_file.exists():
                with open(march_file, 'r') as f:
                    klines = json.load(f)
                    combined_klines.extend(klines)
            
            # 4月数据
            april_file = self.historical_dir / f"okx_{symbol}_USDT_klines_april_2026.json"
            if april_file.exists():
                with open(april_file, 'r') as f:
                    klines = json.load(f)
                    combined_klines.extend(klines)
            
            # 5月数据
            may_file = self.historical_dir / f"okx_{symbol}_USDT_klines_may_2026.json"
            if may_file.exists():
                with open(may_file, 'r') as f:
                    klines = json.load(f)
                    combined_klines.extend(klines)
            
            # 按时间排序
            combined_klines.sort(key=lambda x: x['timestamp'])
            data[f'okx_{symbol.lower()}'] = combined_klines
            self.log(f"✅ 加载 {symbol}: {len(combined_klines)} 条 K 线")
        
        # 加载 OKX 资金费率（3月 + 4月）
        for symbol in ['BTC', 'ETH']:
            combined_rates = []
            
            # 3月数据
            march_file = self.historical_dir / f"okx_{symbol}_USDT_SWAP_funding_rate_march_2026.json"
            if march_file.exists():
                with open(march_file, 'r') as f:
                    rates = json.load(f)
                    combined_rates.extend(rates)
            
            # 4月数据
            april_file = self.historical_dir / f"okx_{symbol}_USDT_SWAP_funding_rate_april_2026.json"
            if april_file.exists():
                with open(april_file, 'r') as f:
                    rates = json.load(f)
                    combined_rates.extend(rates)
            
            # 按时间排序
            combined_rates.sort(key=lambda x: x['timestamp'])
            data[f'okx_{symbol.lower()}_funding'] = combined_rates
            self.log(f"✅ 加载 {symbol} 资金费率: {len(combined_rates)} 条")
        
        # 加载美股数据
        us_stocks_file = self.historical_dir / "us_stocks_march_2026.json"
        if us_stocks_file.exists():
            with open(us_stocks_file, 'r') as f:
                data['us_stocks'] = json.load(f)
                self.log(f"✅ 加载美股: {len(data['us_stocks'])} 只股票")
        
        # 加载 A 股数据
        cn_stocks_file = self.historical_dir / "cn_stocks_march_2026.json"
        if cn_stocks_file.exists():
            with open(cn_stocks_file, 'r') as f:
                data['cn_stocks'] = json.load(f)
                self.log(f"✅ 加载 A 股: {len(data['cn_stocks'])} 只股票")
        
        return data
    
    def load_learning_knowledge(self):
        """加载学习知识库"""
        kb_file = self.data_dir / "learning_knowledge_base.json"
        
        if not kb_file.exists():
            self.log("⚠️ 无学习知识库，使用默认策略")
            return None
        
        try:
            with open(kb_file, 'r') as f:
                kb = json.load(f)
            self.log("✅ 加载学习知识库")
            return kb
        except Exception as e:
            self.log(f"⚠️ 加载学习知识库失败: {e}")
            return None
    
    def analyze_market_opportunity(self, data, timestamp_index, knowledge_base):
        """分析市场机会（规则引擎 + LLM 验证）"""
        import json
        
        # 获取当前时间点的数据
        current_data = {}
        
        # 获取多个资产的数据
        for asset in ['btc', 'eth', 'bnb', 'sol']:
            key = f'okx_{asset}'
            if timestamp_index < len(data.get(key, [])):
                current_data[asset] = data[key][timestamp_index]
        
        # 规则引擎：筛选候选信号
        candidates = []
        
        # 扫描加密货币
        for asset in ['eth', 'sol', 'btc', 'bnb']:  # 按优先级排序
            if asset not in current_data:
                continue
            
            current = current_data[asset]
            
            # 计算技术指标
            lookback = 20
            if timestamp_index < lookback:
                continue
            
            # 获取历史价格
            prices = [data[f'okx_{asset}'][i]['close'] for i in range(max(0, timestamp_index - lookback), timestamp_index + 1)]
            
            if len(prices) < lookback:
                continue
            
            # 计算指标
            current_price = prices[-1]
            ma20 = sum(prices) / len(prices)
            high_20 = max(prices)
            low_20 = min(prices)
            
            # 计算 RSI（简化版）
            gains = []
            losses = []
            for i in range(1, len(prices)):
                change = prices[i] - prices[i-1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))
            
            avg_gain = sum(gains[-14:]) / 14 if len(gains) >= 14 else 0
            avg_loss = sum(losses[-14:]) / 14 if len(losses) >= 14 else 0
            
            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            
            # 计算价格变化
            price_change_pct = (current_price / prices[-2] - 1) * 100 if len(prices) >= 2 else 0
            
            # 规则 1：超卖反弹（RSI < 40，价格接近 20 日低点）
            if rsi < 40 and current_price < low_20 * 1.08:
                candidates.append({
                    'asset': asset.upper(),
                    'strategy': '超卖反弹',
                    'reason': f'RSI {rsi:.1f} 超卖，价格接近 20 日低点',
                    'confidence': 75,
                    'amount': 120,
                    'indicators': {
                        'rsi': rsi,
                        'price': current_price,
                        'ma20': ma20,
                        'distance_from_low': (current_price / low_20 - 1) * 100
                    }
                })
            
            # 规则 2：回调买入（价格回调 1.5-6%，RSI 35-65）
            elif -6 < price_change_pct < -1.5 and 35 < rsi < 65:
                candidates.append({
                    'asset': asset.upper(),
                    'strategy': '回调买入',
                    'reason': f'价格回调 {abs(price_change_pct):.1f}%，RSI {rsi:.1f} 中性',
                    'confidence': 70,
                    'amount': 120,
                    'indicators': {
                        'rsi': rsi,
                        'price_change': price_change_pct,
                        'price': current_price,
                        'ma20': ma20
                    }
                })
            
            # 规则 3：突破买入（价格突破 MA20 > 1.5%，RSI > 45）
            elif current_price > ma20 * 1.015 and rsi > 45 and price_change_pct > 0.5:
                candidates.append({
                    'asset': asset.upper(),
                    'strategy': '突破买入',
                    'reason': f'价格突破 MA20 {((current_price/ma20-1)*100):.1f}%，RSI {rsi:.1f}',
                    'confidence': 65,
                    'amount': 120,
                    'indicators': {
                        'rsi': rsi,
                        'price': current_price,
                        'ma20': ma20,
                        'breakout': (current_price / ma20 - 1) * 100
                    }
                })
            
            # 规则 4：强势反弹（价格从低点反弹 > 3%，RSI 45-70）
            elif current_price > low_20 * 1.03 and 45 < rsi < 70 and price_change_pct > 1:
                candidates.append({
                    'asset': asset.upper(),
                    'strategy': '强势反弹',
                    'reason': f'从低点反弹 {((current_price/low_20-1)*100):.1f}%，RSI {rsi:.1f}',
                    'confidence': 68,
                    'amount': 120,
                    'indicators': {
                        'rsi': rsi,
                        'price': current_price,
                        'low_20': low_20,
                        'bounce': (current_price / low_20 - 1) * 100
                    }
                })
        
        # 扫描美股（如果有数据）
        if 'us_stocks' in data and data['us_stocks']:
            for symbol, stock_data in data['us_stocks'].items():
                if timestamp_index >= len(stock_data):
                    continue
                
                lookback = 20
                if timestamp_index < lookback:
                    continue
                
                prices = [stock_data[i]['close'] for i in range(max(0, timestamp_index - lookback), timestamp_index + 1)]
                if len(prices) < lookback:
                    continue
                
                current_price = prices[-1]
                ma20 = sum(prices) / len(prices)
                low_20 = min(prices)
                price_change_pct = (current_price / prices[-2] - 1) * 100 if len(prices) >= 2 else 0
                
                # 美股策略：回调买入（-2% 至 -5%）
                if -5 < price_change_pct < -2:
                    candidates.append({
                        'asset': symbol,
                        'market': 'US',
                        'strategy': '美股回调',
                        'reason': f'{symbol} 回调 {abs(price_change_pct):.1f}%',
                        'confidence': 60,
                        'amount': 120,
                        'indicators': {
                            'price': current_price,
                            'ma20': ma20,
                            'price_change': price_change_pct
                        }
                    })
        
        # 扫描 A 股（如果有数据）
        if 'cn_stocks' in data and data['cn_stocks']:
            for symbol, stock_data in data['cn_stocks'].items():
                if timestamp_index >= len(stock_data):
                    continue
                
                lookback = 20
                if timestamp_index < lookback:
                    continue
                
                prices = [stock_data[i]['close'] for i in range(max(0, timestamp_index - lookback), timestamp_index + 1)]
                if len(prices) < lookback:
                    continue
                
                current_price = prices[-1]
                ma20 = sum(prices) / len(prices)
                low_20 = min(prices)
                price_change_pct = (current_price / prices[-2] - 1) * 100 if len(prices) >= 2 else 0
                
                # A 股策略：超卖反弹（接近 20 日低点）
                if current_price < low_20 * 1.05 and price_change_pct > -3:
                    candidates.append({
                        'asset': symbol,
                        'market': 'CN',
                        'strategy': 'A股超卖',
                        'reason': f'{symbol} 接近 20 日低点',
                        'confidence': 55,
                        'amount': 120,
                        'indicators': {
                            'price': current_price,
                            'low_20': low_20,
                            'distance_from_low': (current_price / low_20 - 1) * 100
                        }
                    })
        
        # 如果没有候选信号，返回 hold
        if not candidates:
            return {"action": "hold"}
        
        # 选择最佳候选（优先加密货币 > 美股 > A股，其次高置信度）
        def score_candidate(c):
            # 加密货币优先级
            if c.get('market') is None:
                asset_score = {'ETH': 400, 'SOL': 300, 'BTC': 200, 'BNB': 100}.get(c['asset'], 0)
            # 美股次优先
            elif c.get('market') == 'US':
                asset_score = 50
            # A 股最低优先
            else:
                asset_score = 10
            
            return asset_score + c['confidence']
        
        best_candidate = max(candidates, key=score_candidate)
        
        # LLM 验证（简化版，只做最终确认）
        prompt = f"""你是量化交易专家。规则引擎已筛选出一个交易信号，请验证是否合理。

## 候选信号
资产: {best_candidate['asset']}
策略: {best_candidate['strategy']}
理由: {best_candidate['reason']}
置信度: {best_candidate['confidence']}
建议仓位: ${best_candidate['amount']}

## 技术指标
{json.dumps(best_candidate['indicators'], indent=2)}

## 历史经验
- ETH 胜率最高（46.9%）
- 回调买入策略胜率 43.6%
- 止损 -3%，止盈 15%

## 验证要点
1. 信号是否符合历史经验？
2. 当前市场环境是否适合？
3. 风险是否可控？

请回复 JSON：
{{
  "action": "buy" 或 "reject",
  "reason": "验证理由"
}}

如果信号合理，返回 "buy"。如果有明显问题，返回 "reject"。
"""
        
        try:
            response = call_llm_sync("backtest_analyzer", prompt, timeout=30)
            
            # 解析 JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                verification = json.loads(json_match.group())
                
                if verification.get('action') == 'buy':
                    return {
                        'action': 'buy',
                        'asset': best_candidate['asset'],
                        'amount': best_candidate['amount'],
                        'reason': best_candidate['reason'],
                        'confidence': best_candidate['confidence'],
                        'strategy': best_candidate['strategy']
                    }
            
            return {"action": "hold"}
        
        except Exception as e:
            self.log(f"⚠️ LLM 验证失败: {e}，使用规则引擎信号")
            # LLM 失败时，直接使用规则引擎信号
            return {
                'action': 'buy',
                'asset': best_candidate['asset'],
                'amount': best_candidate['amount'],
                'reason': best_candidate['reason'],
                'confidence': best_candidate['confidence'],
                'strategy': best_candidate['strategy']
            }
    
    def execute_trade(self, signal, data, timestamp_index):
        """执行交易"""
        if signal.get('action') != 'buy':
            return False
        
        asset = signal.get('asset', 'BTC')
        amount = signal.get('amount', 100)
        
        # 检查资金
        if amount > self.current_capital:
            self.log(f"⚠️ 资金不足: 需要 ${amount}, 可用 ${self.current_capital:.2f}")
            return False
        
        # 获取当前价格
        asset_key = f'okx_{asset.lower()}'
        if asset_key in data and timestamp_index < len(data[asset_key]):
            price = data[asset_key][timestamp_index]['close']
            timestamp = data[asset_key][timestamp_index]['timestamp']
        else:
            return False
        
        # 计算交易成本
        fee_rate = 0.001  # 0.1% 手续费
        slippage_rate = 0.005  # 0.5% 滑点
        total_cost_rate = fee_rate + slippage_rate  # 总成本 0.6%
        
        # 实际成交价格（考虑滑点）
        actual_price = price * (1 + slippage_rate)
        
        # 计算份额（扣除手续费后）
        shares = (amount * (1 - fee_rate)) / actual_price
        
        # 扣除资金
        self.current_capital -= amount
        
        # 添加持仓
        position = {
            'asset': asset,
            'entry_price': actual_price,  # 使用实际成交价
            'shares': shares,
            'amount': amount,
            'entry_time': timestamp,
            'entry_index': timestamp_index,
            'reason': signal.get('reason', ''),
            'confidence': signal.get('confidence', 0),
            'strategy': signal.get('strategy', 'unknown'),
            'fee_paid': amount * fee_rate,  # 记录手续费
            'slippage_cost': amount * slippage_rate  # 记录滑点成本
        }
        
        self.positions.append(position)
        
        self.log(f"✅ 买入 {asset}: ${amount:.2f} @ ${actual_price:.2f} (份额 {shares:.6f}, 成本 {total_cost_rate*100:.1f}%)")
        
        return True
    
    def check_exit_conditions(self, data, timestamp_index):
        """检查持仓是否需要平仓"""
        exits = []
        
        for i, pos in enumerate(self.positions):
            asset = pos['asset']
            
            # 获取当前价格
            asset_key = f'okx_{asset.lower()}'
            if asset_key in data and timestamp_index < len(data[asset_key]):
                current_price = data[asset_key][timestamp_index]['close']
            else:
                continue
            
            # 计算盈亏
            pnl_percent = (current_price / pos['entry_price'] - 1)
            
            # 止盈 15%
            if pnl_percent >= 0.15:
                exits.append((i, pos, current_price, pnl_percent, '止盈'))
            
            # 止损 -1.5%（从 -3% 收紧，控制最大回撤）
            elif pnl_percent <= -0.015:
                exits.append((i, pos, current_price, pnl_percent, '止损'))
        
        # 执行平仓
        for i, pos, exit_price, pnl_percent, reason in reversed(exits):
            # 计算卖出成本
            fee_rate = 0.001  # 0.1% 手续费
            slippage_rate = 0.005  # 0.5% 滑点
            
            # 实际卖出价格（考虑滑点）
            actual_exit_price = exit_price * (1 - slippage_rate)
            
            # 计算收益（扣除卖出手续费）
            exit_amount = pos['shares'] * actual_exit_price
            exit_fee = exit_amount * fee_rate
            net_exit_amount = exit_amount - exit_fee
            
            profit = net_exit_amount - pos['amount']
            
            # 回收资金
            self.current_capital += net_exit_amount
            
            # 记录交易
            trade = {
                'asset': pos['asset'],
                'entry_price': pos['entry_price'],
                'exit_price': actual_exit_price,
                'entry_time': pos['entry_time'],
                'exit_time': data[f"okx_{pos['asset'].lower()}"][timestamp_index]['timestamp'],
                'amount': pos['amount'],
                'profit': profit,
                'pnl_percent': profit / pos['amount'],  # 真实盈亏百分比
                'reason': reason,
                'confidence': pos['confidence'],
                'strategy': pos.get('strategy', 'unknown'),
                'total_fees': pos.get('fee_paid', 0) + exit_fee,  # 总手续费
                'total_slippage': pos.get('slippage_cost', 0) + exit_amount * slippage_rate  # 总滑点成本
            }
            
            self.trades.append(trade)
            
            self.log(f"✅ 卖出 {pos['asset']}: ${net_exit_amount:.2f} @ ${actual_exit_price:.2f} ({reason}, 净收益 {profit/pos['amount']:.2%})")
            
            # 移除持仓
            self.positions.pop(i)
    
    def run_backtest(self):
        """运行回测"""
        self.log("=" * 80)
        self.log("开始历史回测（2026 年 3-5 月）")
        self.log("=" * 80)
        
        # 加载数据
        data = self.load_historical_data()
        kb = self.load_learning_knowledge()
        
        # 获取最长的时间序列长度
        max_length = max(len(data['okx_btc']), len(data['okx_eth']))
        
        self.log(f"\n初始资金: ${self.initial_capital:,.2f}")
        self.log(f"目标交易: {self.target_trades} 笔")
        self.log(f"数据长度: {max_length} 个时间点\n")
        
        # 遍历时间序列
        for i in range(max_length):
            # 检查是否达到目标交易数
            if len(self.trades) >= self.target_trades:
                self.log(f"\n✅ 达到目标交易数 {self.target_trades} 笔，停止回测")
                break
            
            # 检查持仓平仓条件
            self.check_exit_conditions(data, i)
            
            # 每 10 个时间点分析一次（避免过度交易）
            if i % 10 == 0:
                # 分析市场机会
                signal = self.analyze_market_opportunity(data, i, kb)
                
                # 执行交易
                if signal.get('action') == 'buy':
                    self.execute_trade(signal, data, i)
            
            # 每 100 个时间点输出进度
            if i % 100 == 0:
                self.log(f"进度: {i}/{max_length} ({i/max_length*100:.1f}%), 交易: {len(self.trades)}/{self.target_trades}, 资金: ${self.current_capital:,.2f}")
        
        # 回测结束，剩余持仓按最后价格计算（不强制平仓）
        final_index = max_length - 1
        if self.positions:
            self.log(f"\n⚠️ 回测结束，剩余 {len(self.positions)} 个未平仓持仓")
            for pos in self.positions:
                asset = pos['asset']
                asset_key = f'okx_{asset.lower()}'
                if asset_key in data and final_index < len(data[asset_key]):
                    current_price = data[asset_key][final_index]['close']
                    unrealized_pnl = (current_price / pos['entry_price'] - 1) * 100
                    self.log(f"  {asset}: 浮动盈亏 {unrealized_pnl:.2f}%")
        
        self.positions = []
        
        # 生成报告
        self.generate_report()
    
    def generate_report(self):
        """生成回测报告"""
        self.log("\n" + "=" * 80)
        self.log("回测报告")
        self.log("=" * 80)
        
        # 基本统计
        total_trades = len(self.trades)
        
        # 防止除零错误
        if total_trades == 0:
            self.log("\n⚠️ 警告: 没有生成任何交易")
            self.log(f"最终资金: ${self.current_capital:,.2f}")
            self.log(f"持仓数: {len(self.positions)}")
            return
        
        profitable_trades = len([t for t in self.trades if t['profit'] > 0])
        losing_trades = len([t for t in self.trades if t['profit'] < 0])
        win_rate = profitable_trades / total_trades if total_trades > 0 else 0
        
        total_profit = sum(t['profit'] for t in self.trades)
        total_return = (self.current_capital / self.initial_capital - 1) * 100
        
        avg_profit = sum(t['profit'] for t in self.trades if t['profit'] > 0) / profitable_trades if profitable_trades > 0 else 0
        avg_loss = sum(t['profit'] for t in self.trades if t['profit'] < 0) / losing_trades if losing_trades > 0 else 0
        
        self.log(f"\n总交易数: {total_trades}")
        self.log(f"盈利交易: {profitable_trades} ({profitable_trades/total_trades*100:.1f}%)")
        self.log(f"亏损交易: {losing_trades} ({losing_trades/total_trades*100:.1f}%)")
        self.log(f"胜率: {win_rate:.2%}")
        
        self.log(f"\n初始资金: ${self.initial_capital:,.2f}")
        self.log(f"最终资金: ${self.current_capital:,.2f}")
        self.log(f"总收益: ${total_profit:,.2f}")
        self.log(f"总回报率: {total_return:.2f}%")
        
        self.log(f"\n平均盈利: ${avg_profit:.2f}")
        self.log(f"平均亏损: ${avg_loss:.2f}")
        self.log(f"盈亏比: {abs(avg_profit/avg_loss):.2f}" if avg_loss != 0 else "盈亏比: N/A")
        
        # 计算最大回撤
        capital_curve = [self.initial_capital]
        running_capital = self.initial_capital
        
        for trade in self.trades:
            running_capital += trade['profit']
            capital_curve.append(running_capital)
        
        max_drawdown = 0
        peak = capital_curve[0]
        
        for capital in capital_curve:
            if capital > peak:
                peak = capital
            drawdown = (peak - capital) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        self.log(f"\n最大回撤: {max_drawdown:.2%}")
        
        # 计算总交易成本
        total_fees = sum(t.get('total_fees', 0) for t in self.trades)
        total_slippage = sum(t.get('total_slippage', 0) for t in self.trades)
        total_costs = total_fees + total_slippage
        
        self.log(f"\n交易成本统计:")
        self.log(f"  总手续费: ${total_fees:.2f}")
        self.log(f"  总滑点成本: ${total_slippage:.2f}")
        self.log(f"  总交易成本: ${total_costs:.2f} ({total_costs/self.initial_capital*100:.2f}%)")
        self.log(f"  扣除成本前收益: ${total_profit + total_costs:.2f}")
        self.log(f"  扣除成本后收益: ${total_profit:.2f}")
        
        # 按资产统计
        self.log("\n按资产统计:")
        asset_stats = defaultdict(lambda: {'trades': 0, 'profit': 0})
        for trade in self.trades:
            asset = trade['asset']
            asset_stats[asset]['trades'] += 1
            asset_stats[asset]['profit'] += trade['profit']
        
        for asset, stats in asset_stats.items():
            self.log(f"  {asset}: {stats['trades']} 笔, 收益 ${stats['profit']:.2f}")
        
        # 保存详细交易记录
        output_file = self.data_dir / "backtest_trades.json"
        with open(output_file, 'w') as f:
            json.dump({
                'summary': {
                    'total_trades': total_trades,
                    'profitable_trades': profitable_trades,
                    'losing_trades': losing_trades,
                    'win_rate': win_rate,
                    'initial_capital': self.initial_capital,
                    'final_capital': self.current_capital,
                    'total_profit': total_profit,
                    'total_return': total_return,
                    'avg_profit': avg_profit,
                    'avg_loss': avg_loss,
                    'max_drawdown': max_drawdown,
                    'total_fees': total_fees,
                    'total_slippage': total_slippage,
                    'total_costs': total_costs
                },
                'trades': self.trades
            }, f, indent=2, ensure_ascii=False)
        
        self.log(f"\n✅ 详细交易记录已保存: {output_file}")
        self.log("=" * 80)

def main():
    backtest = HistoricalBacktest()
    backtest.run_backtest()

if __name__ == "__main__":
    main()
