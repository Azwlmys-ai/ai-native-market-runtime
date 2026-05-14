#!/usr/bin/env python3
"""
Finnhub 免费数据采集器
采集美股实时行情（免费额度: 60 次/分钟）
官网: https://finnhub.io/
"""

import json
import asyncio
import aiohttp
from datetime import datetime
from pathlib import Path

# 输出路径
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "finnhub_data.json"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "broker_config.json"

# 监控股票列表
WATCH_SYMBOLS = [
    # 美股科技
    "AAPL",   # 苹果
    "MSFT",   # 微软
    "GOOGL",  # 谷歌
    "AMZN",   # 亚马逊
    "NVDA",   # 英伟达
    "TSLA",   # 特斯拉
    "META",   # Meta
    
    # 加密货币相关
    "COIN",   # Coinbase
    
    # 游戏公司
    "TTWO",   # Take-Two (GTA VI 开发商)
    "MSTR",   # MicroStrategy
]


async def fetch_quote(session, symbol, api_key):
    """获取单个股票报价"""
    try:
        url = "https://finnhub.io/api/v1/quote"
        params = {
            "symbol": symbol,
            "token": api_key
        }
        
        async with session.get(url, params=params, timeout=10) as response:
            if response.status != 200:
                return None
            
            data = await response.json()
            
            # Finnhub 返回格式: {c: current, h: high, l: low, o: open, pc: prev_close, t: timestamp}
            if not data or data.get("c") == 0:
                return None
            
            price = data.get("c", 0)
            prev_close = data.get("pc", 0)
            change = price - prev_close
            change_percent = (change / prev_close * 100) if prev_close > 0 else 0
            
            return {
                "symbol": symbol,
                "price": price,
                "change": change,
                "change_percent": change_percent,
                "high": data.get("h", 0),
                "low": data.get("l", 0),
                "open": data.get("o", 0),
                "prev_close": prev_close,
                "timestamp": datetime.fromtimestamp(data.get("t", 0)).isoformat() if data.get("t") else datetime.now().isoformat()
            }
            
    except Exception as e:
        print(f"❌ 获取 {symbol} 失败: {e}")
        return None


async def collect_finnhub_data():
    """采集 Finnhub 数据"""
    
    try:
        # 读取 API Key
        api_key = "demo"  # 默认使用 demo key
        
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                api_key = config_data.get("brokers", {}).get("finnhub", {}).get("api_key", "demo")
        
        async with aiohttp.ClientSession() as session:
            # 并发获取所有股票（免费版支持 60 次/分钟）
            tasks = [fetch_quote(session, symbol, api_key) for symbol in WATCH_SYMBOLS]
            results = await asyncio.gather(*tasks)
            
            # 过滤失败的请求
            stocks_data = [r for r in results if r is not None]
            
            result = {
                "status": "success",
                "source": "finnhub",
                "stocks": stocks_data,
                "total_symbols": len(stocks_data),
                "failed_symbols": len(WATCH_SYMBOLS) - len(stocks_data),
                "api_key_type": "demo" if api_key == "demo" else "custom",
                "timestamp": datetime.now().isoformat()
            }
            
            # 保存到文件
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Finnhub 数据采集成功: {len(stocks_data)}/{len(WATCH_SYMBOLS)} 个股票")
            return result
            
    except Exception as e:
        error_result = {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }
        
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, indent=2, ensure_ascii=False)
        
        print(f"❌ Finnhub 数据采集失败: {e}")
        return error_result


if __name__ == "__main__":
    result = asyncio.run(collect_finnhub_data())
    print(json.dumps(result, indent=2, ensure_ascii=False))
