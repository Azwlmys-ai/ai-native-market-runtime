#!/usr/bin/env python3
"""
OKX Data Collector - OKX 交易所数据采集器
采集: 现货价格、永续合约、资金费率、季度期货
"""

import json
import sys
import requests
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# OKX 公开 API (无需 API Key)
OKX_BASE_URL = "https://www.okx.com"

def get_spot_price(symbol='BTC-USDT'):
    """获取现货价格"""
    try:
        url = f"{OKX_BASE_URL}/api/v5/market/ticker"
        params = {'instId': symbol}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data['code'] == '0' and data['data']:
            ticker = data['data'][0]
            return {
                'symbol': symbol,
                'last_price': float(ticker['last']),
                'bid_price': float(ticker['bidPx']),
                'ask_price': float(ticker['askPx']),
                'volume_24h': float(ticker['vol24h']),
                'timestamp': ticker['ts']
            }
        else:
            return None
    except Exception as e:
        print(f"   ❌ 获取现货价格失败: {e}")
        return None

def get_perpetual_swap(symbol='BTC-USDT-SWAP'):
    """获取永续合约价格"""
    try:
        url = f"{OKX_BASE_URL}/api/v5/market/ticker"
        params = {'instId': symbol}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data['code'] == '0' and data['data']:
            ticker = data['data'][0]
            return {
                'symbol': symbol,
                'last_price': float(ticker['last']),
                'bid_price': float(ticker['bidPx']),
                'ask_price': float(ticker['askPx']),
                'volume_24h': float(ticker['vol24h']),
                'timestamp': ticker['ts']
            }
        else:
            return None
    except Exception as e:
        print(f"   ❌ 获取永续合约价格失败: {e}")
        return None

def get_funding_rate(symbol='BTC-USDT-SWAP'):
    """获取资金费率"""
    try:
        url = f"{OKX_BASE_URL}/api/v5/public/funding-rate"
        params = {'instId': symbol}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data['code'] == '0' and data['data']:
            funding = data['data'][0]
            return {
                'symbol': symbol,
                'funding_rate': float(funding['fundingRate']),
                'next_funding_time': funding['nextFundingTime'],
                'funding_rate_8h': float(funding['fundingRate']) * 3,  # 转换为 8 小时费率
                'timestamp': funding['fundingTime']
            }
        else:
            return None
    except Exception as e:
        print(f"   ❌ 获取资金费率失败: {e}")
        return None

def get_futures_price(symbol='BTC-USDT-250627'):
    """获取季度期货价格"""
    try:
        url = f"{OKX_BASE_URL}/api/v5/market/ticker"
        params = {'instId': symbol}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data['code'] == '0' and data['data']:
            ticker = data['data'][0]
            return {
                'symbol': symbol,
                'last_price': float(ticker['last']),
                'bid_price': float(ticker['bidPx']),
                'ask_price': float(ticker['askPx']),
                'volume_24h': float(ticker['vol24h']),
                'timestamp': ticker['ts']
            }
        else:
            return None
    except Exception as e:
        print(f"   ❌ 获取期货价格失败: {e}")
        return None

def calculate_arbitrage_opportunities(spot, perpetual, futures, funding):
    """计算套利机会"""
    opportunities = []
    
    if not all([spot, perpetual, futures, funding]):
        return opportunities
    
    # 1. 现货-永续套利
    spot_perp_spread = ((perpetual['last_price'] - spot['last_price']) / spot['last_price']) * 100
    
    # 考虑资金费率成本
    funding_cost_8h = funding['funding_rate_8h'] * 100
    net_spread = spot_perp_spread - abs(funding_cost_8h)
    
    if abs(net_spread) > 0.5:  # 净价差 > 0.5%
        opportunities.append({
            'type': 'spot_perpetual_arbitrage',
            'direction': 'long_spot_short_perp' if net_spread > 0 else 'short_spot_long_perp',
            'spread_pct': spot_perp_spread,
            'funding_cost_8h_pct': funding_cost_8h,
            'net_spread_pct': net_spread,
            'confidence': 85 if abs(net_spread) > 1 else 70
        })
    
    # 2. 现货-期货套利
    spot_futures_spread = ((futures['last_price'] - spot['last_price']) / spot['last_price']) * 100
    
    if abs(spot_futures_spread) > 1:  # 价差 > 1%
        opportunities.append({
            'type': 'spot_futures_arbitrage',
            'direction': 'long_spot_short_futures' if spot_futures_spread > 0 else 'short_spot_long_futures',
            'spread_pct': spot_futures_spread,
            'confidence': 80 if abs(spot_futures_spread) > 2 else 65
        })
    
    # 3. 永续-期货套利
    perp_futures_spread = ((futures['last_price'] - perpetual['last_price']) / perpetual['last_price']) * 100
    
    if abs(perp_futures_spread) > 0.8:  # 价差 > 0.8%
        opportunities.append({
            'type': 'perpetual_futures_arbitrage',
            'direction': 'long_perp_short_futures' if perp_futures_spread > 0 else 'short_perp_long_futures',
            'spread_pct': perp_futures_spread,
            'confidence': 75
        })
    
    return opportunities

def main():
    print("📊 OKX Data Collector - 采集交易数据")
    print("="*60)
    
    # 1. 测试 API 连通性
    print("\n1️⃣ 测试 OKX API 连通性...")
    try:
        response = requests.get(f"{OKX_BASE_URL}/api/v5/public/time", timeout=5)
        if response.status_code == 200:
            print("   ✅ OKX API 连接成功")
        else:
            print(f"   ❌ OKX API 连接失败: HTTP {response.status_code}")
            return
    except Exception as e:
        print(f"   ❌ OKX API 连接失败: {e}")
        return
    
    # 2. 采集 BTC 数据
    print("\n2️⃣ 采集 BTC 市场数据...")
    
    print("   - 现货价格 (BTC-USDT)...")
    btc_spot = get_spot_price('BTC-USDT')
    if btc_spot:
        print(f"     ✅ ${btc_spot['last_price']:,.2f}")
    
    print("   - 永续合约 (BTC-USDT-SWAP)...")
    btc_perpetual = get_perpetual_swap('BTC-USDT-SWAP')
    if btc_perpetual:
        print(f"     ✅ ${btc_perpetual['last_price']:,.2f}")
    
    print("   - 资金费率...")
    btc_funding = get_funding_rate('BTC-USDT-SWAP')
    if btc_funding:
        print(f"     ✅ {btc_funding['funding_rate']*100:.4f}% (8h: {btc_funding['funding_rate_8h']*100:.4f}%)")
    
    print("   - 季度期货 (BTC-USDT-250627)...")
    btc_futures = get_futures_price('BTC-USDT-250627')
    if btc_futures:
        print(f"     ✅ ${btc_futures['last_price']:,.2f}")
    
    # 3. 采集 ETH 数据
    print("\n3️⃣ 采集 ETH 市场数据...")
    
    print("   - 现货价格 (ETH-USDT)...")
    eth_spot = get_spot_price('ETH-USDT')
    if eth_spot:
        print(f"     ✅ ${eth_spot['last_price']:,.2f}")
    
    print("   - 永续合约 (ETH-USDT-SWAP)...")
    eth_perpetual = get_perpetual_swap('ETH-USDT-SWAP')
    if eth_perpetual:
        print(f"     ✅ ${eth_perpetual['last_price']:,.2f}")
    
    print("   - 资金费率...")
    eth_funding = get_funding_rate('ETH-USDT-SWAP')
    if eth_funding:
        print(f"     ✅ {eth_funding['funding_rate']*100:.4f}% (8h: {eth_funding['funding_rate_8h']*100:.4f}%)")
    
    # 4. 采集 BNB 数据
    print("\n4️⃣ 采集 BNB 市场数据...")
    
    print("   - 现货价格 (BNB-USDT)...")
    bnb_spot = get_spot_price('BNB-USDT')
    if bnb_spot:
        print(f"     ✅ ${bnb_spot['last_price']:,.2f}")
    
    print("   - 永续合约 (BNB-USDT-SWAP)...")
    bnb_perpetual = get_perpetual_swap('BNB-USDT-SWAP')
    if bnb_perpetual:
        print(f"     ✅ ${bnb_perpetual['last_price']:,.2f}")
    
    print("   - 资金费率...")
    bnb_funding = get_funding_rate('BNB-USDT-SWAP')
    if bnb_funding:
        print(f"     ✅ {bnb_funding['funding_rate']*100:.4f}% (8h: {bnb_funding['funding_rate_8h']*100:.4f}%)")
    
    # 5. 采集 SOL 数据
    print("\n5️⃣ 采集 SOL 市场数据...")
    
    print("   - 现货价格 (SOL-USDT)...")
    sol_spot = get_spot_price('SOL-USDT')
    if sol_spot:
        print(f"     ✅ ${sol_spot['last_price']:,.2f}")
    
    print("   - 永续合约 (SOL-USDT-SWAP)...")
    sol_perpetual = get_perpetual_swap('SOL-USDT-SWAP')
    if sol_perpetual:
        print(f"     ✅ ${sol_perpetual['last_price']:,.2f}")
    
    print("   - 资金费率...")
    sol_funding = get_funding_rate('SOL-USDT-SWAP')
    if sol_funding:
        print(f"     ✅ {sol_funding['funding_rate']*100:.4f}% (8h: {sol_funding['funding_rate_8h']*100:.4f}%)")
    
    # 6. 计算套利机会
    print("\n6️⃣ 计算套利机会...")
    
    btc_opportunities = calculate_arbitrage_opportunities(
        btc_spot, btc_perpetual, btc_futures, btc_funding
    )
    
    eth_opportunities = calculate_arbitrage_opportunities(
        eth_spot, eth_perpetual, None, eth_funding
    )
    
    bnb_opportunities = calculate_arbitrage_opportunities(
        bnb_spot, bnb_perpetual, None, bnb_funding
    )
    
    sol_opportunities = calculate_arbitrage_opportunities(
        sol_spot, sol_perpetual, None, sol_funding
    )
    
    all_opportunities = btc_opportunities + eth_opportunities + bnb_opportunities + sol_opportunities
    
    if all_opportunities:
        print(f"   ✅ 发现 {len(all_opportunities)} 个套利机会")
        for opp in all_opportunities:
            print(f"\n   📈 {opp['type']}")
            print(f"      方向: {opp['direction']}")
            print(f"      价差: {opp.get('spread_pct', 0):.2f}%")
            if 'net_spread_pct' in opp:
                print(f"      净价差: {opp['net_spread_pct']:.2f}%")
            print(f"      置信度: {opp['confidence']}%")
    else:
        print("   ⚠️  当前无套利机会")
    
    # 5. 保存数据
    output = {
        'timestamp': datetime.now().isoformat(),
        'btc': {
            'spot': btc_spot,
            'perpetual': btc_perpetual,
            'futures': btc_futures,
            'funding': btc_funding
        },
        'eth': {
            'spot': eth_spot,
            'perpetual': eth_perpetual,
            'funding': eth_funding
        },
        'bnb': {
            'spot': bnb_spot,
            'perpetual': bnb_perpetual,
            'funding': bnb_funding
        },
        'sol': {
            'spot': sol_spot,
            'perpetual': sol_perpetual,
            'funding': sol_funding
        },
        'arbitrage_opportunities': all_opportunities
    }
    
    with open('data/okx_data.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ 数据保存到 data/okx_data.json")
    
    # 6. 集成到 latest_data.json
    print("\n5️⃣ 集成到 latest_data.json...")
    try:
        with open('data/latest_data.json', 'r') as f:
            latest_data = json.load(f)
        
        latest_data['okx'] = output
        latest_data['timestamp'] = datetime.now().isoformat()
        
        with open('data/latest_data.json', 'w') as f:
            json.dump(latest_data, f, indent=2)
        
        print("   ✅ OKX 数据已集成到 latest_data.json")
    except Exception as e:
        print(f"   ⚠️  集成失败: {e}")

if __name__ == '__main__':
    main()
