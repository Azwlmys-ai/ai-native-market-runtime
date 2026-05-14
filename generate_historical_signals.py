#!/usr/bin/env python3
"""
从 Polymarket API 获取历史市场数据，生成模拟交易信号用于训练测试
"""
import asyncio
import aiohttp
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

class HistoricalSignalGenerator:
    def __init__(self):
        self.base_url = "https://gamma-api.polymarket.com"
        self.signals = []
        
    def log(self, msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {msg}")
    
    async def fetch_markets(self, session, limit=200):
        """获取市场列表"""
        url = f"{self.base_url}/markets"
        params = {
            "limit": limit,
            "closed": "false"  # 获取活跃市场
        }
        
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.log(f"✅ 获取 {len(data)} 个市场")
                    return data
                else:
                    self.log(f"❌ 获取市场失败: {resp.status}")
                    return []
        except Exception as e:
            self.log(f"❌ 请求异常: {e}")
            return []
    
    async def fetch_market_orderbook(self, session, token_id):
        """获取市场订单簿"""
        url = f"{self.base_url}/book"
        params = {"token_id": token_id}
        
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except:
            return None
    
    def calculate_signal_quality(self, market, orderbook):
        """根据市场数据计算信号质量（模拟 Agent 决策）"""
        # 提取关键指标
        outcome_prices_raw = market.get("outcomePrices", ["0.5", "0.5"])
        
        # outcomePrices 可能是字符串或列表
        if isinstance(outcome_prices_raw, str):
            try:
                outcome_prices = json.loads(outcome_prices_raw)
            except:
                outcome_prices = ["0.5", "0.5"]
        else:
            outcome_prices = outcome_prices_raw
        
        yes_price = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.5
        no_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.5
        
        volume = float(market.get("volume", 0))
        liquidity = float(market.get("liquidity", 0))
        
        # 订单簿深度
        if orderbook:
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])
            depth = len(bids) + len(asks)
        else:
            depth = 0
        
        # 判断信号质量（放宽规则，模拟真实 Agent 决策）
        is_good = False
        reasons = []
        
        # 规则 1: 高价 NO（≥0.90）- 强 APPROVE
        if no_price >= 0.90:
            is_good = True
            reasons.append("高价NO≥0.90")
        
        # 规则 2: 高价 NO（0.85-0.89）+ 高流动性 - APPROVE
        elif no_price >= 0.85 and liquidity >= 10000:
            is_good = True
            reasons.append("高价NO+高流动性")
        
        # 规则 3: 中高价 NO（0.75-0.84）+ 高成交量 - APPROVE
        elif no_price >= 0.75 and volume >= 50000:
            is_good = True
            reasons.append("中高价NO+高成交量")
        
        # 规则 4: 低价 YES（≤0.15）- REJECT
        elif yes_price <= 0.15:
            reasons.append("低价YES风险高")
        
        # 规则 5: 流动性不足 - REJECT
        elif liquidity < 5000:
            reasons.append("流动性不足")
        
        # 规则 6: 中间价位（0.4-0.6）- REJECT
        elif 0.4 <= no_price <= 0.6:
            reasons.append("中间价位风险高")
        
        # 其他情况：根据综合评分
        else:
            score = 0
            if no_price >= 0.65:
                score += 1
            if liquidity >= 10000:
                score += 1
            if volume >= 20000:
                score += 1
            if depth >= 5:
                score += 1
            
            if score >= 3:
                is_good = True
                reasons.append("综合评分通过")
            else:
                reasons.append("综合评分不足")
        
        return is_good, reasons
    
    def generate_signal(self, market, orderbook, signal_id):
        """生成交易信号"""
        outcome_prices_raw = market.get("outcomePrices", ["0.5", "0.5"])
        
        # outcomePrices 可能是字符串或列表
        if isinstance(outcome_prices_raw, str):
            try:
                outcome_prices = json.loads(outcome_prices_raw)
            except:
                outcome_prices = ["0.5", "0.5"]
        else:
            outcome_prices = outcome_prices_raw
        
        yes_price = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.5
        no_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.5
        
        # 选择方向（偏好高价 NO）
        if no_price >= 0.85:
            side = "NO"
            price = no_price
        elif yes_price <= 0.15:
            side = "YES"
            price = yes_price
        else:
            # 随机选择
            side = random.choice(["YES", "NO"])
            price = yes_price if side == "YES" else no_price
        
        # 计算信号质量
        is_good, reasons = self.calculate_signal_quality(market, orderbook)
        
        # 生成信号
        signal = {
            "id": signal_id,
            "market": market.get("question", "Unknown"),
            "market_slug": market.get("slug", "unknown"),
            "side": side,
            "price": price,
            "amount": random.randint(80, 200),
            "volume": float(market.get("volume", 0)),
            "liquidity": float(market.get("liquidity", 0)),
            "orderbook_depth": len(orderbook.get("bids", [])) + len(orderbook.get("asks", [])) if orderbook else 0,
            "expected_outcome": "APPROVE" if is_good else "REJECT",
            "reasons": reasons,
            "timestamp": datetime.now().isoformat()
        }
        
        return signal
    
    async def generate_signals(self, target_count=100):
        """生成指定数量的交易信号"""
        self.log(f"开始生成 {target_count} 个历史交易信号...")
        
        async with aiohttp.ClientSession() as session:
            # 1. 获取市场列表
            markets = await self.fetch_markets(session, limit=200)
            
            if len(markets) < 50:
                self.log(f"❌ 市场数量不足: {len(markets)}")
                return []
            
            # 2. 随机选择市场并生成信号
            selected_markets = random.sample(markets, min(target_count, len(markets)))
            
            signal_id = 1
            for market in selected_markets:
                # 获取订单簿
                condition_id = market.get("conditionId")
                if not condition_id:
                    continue
                
                # Polymarket 使用 clobTokenIds [YES_token_id, NO_token_id]
                clob_token_ids = market.get("clobTokenIds")
                if not clob_token_ids:
                    continue
                
                try:
                    token_ids = json.loads(clob_token_ids)
                    if len(token_ids) < 2:
                        continue
                    token_id = token_ids[1]  # NO token
                except:
                    continue
                
                orderbook = await self.fetch_market_orderbook(session, token_id)
                
                # 生成信号
                signal = self.generate_signal(market, orderbook, signal_id)
                self.signals.append(signal)
                signal_id += 1
                
                if len(self.signals) >= target_count:
                    break
                
                # 避免请求过快
                await asyncio.sleep(0.1)
            
            self.log(f"✅ 生成 {len(self.signals)} 个信号")
            return self.signals
    
    def save_signals(self, output_path):
        """保存信号到文件"""
        with open(output_path, 'w') as f:
            json.dump(self.signals, f, indent=2)
        self.log(f"✅ 信号已保存到 {output_path}")
    
    def split_dataset(self, train_ratio=0.5):
        """划分训练集和测试集"""
        random.shuffle(self.signals)
        split_point = int(len(self.signals) * train_ratio)
        
        train_set = self.signals[:split_point]
        test_set = self.signals[split_point:]
        
        self.log(f"📊 数据集划分: 训练集 {len(train_set)} 条, 测试集 {len(test_set)} 条")
        
        return train_set, test_set

async def main():
    generator = HistoricalSignalGenerator()
    
    # 生成 100 个信号
    signals = await generator.generate_signals(target_count=100)
    
    if len(signals) < 50:
        print(f"❌ 信号数量不足: {len(signals)}")
        return
    
    # 保存完整信号
    output_dir = Path("/opt/data/polymarket_arbitrage/data")
    output_dir.mkdir(exist_ok=True)
    
    generator.save_signals(output_dir / "historical_signals.json")
    
    # 划分数据集
    train_set, test_set = generator.split_dataset(train_ratio=0.5)
    
    # 保存训练集和测试集
    with open(output_dir / "train_signals.json", 'w') as f:
        json.dump(train_set, f, indent=2)
    
    with open(output_dir / "test_signals.json", 'w') as f:
        json.dump(test_set, f, indent=2)
    
    print("\n" + "="*60)
    print("✅ 历史信号生成完成")
    print(f"总信号数: {len(signals)}")
    print(f"训练集: {len(train_set)} 条")
    print(f"测试集: {len(test_set)} 条")
    print(f"预期 APPROVE: {sum(1 for s in signals if s['expected_outcome'] == 'APPROVE')}")
    print(f"预期 REJECT: {sum(1 for s in signals if s['expected_outcome'] == 'REJECT')}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
