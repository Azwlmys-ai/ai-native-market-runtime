#!/usr/bin/env python3
"""
Polygon.io 免费数据采集器
采集美股实时行情（免费额度: 5 次/分钟）
官网: https://polygon.io/
"""

import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path

# 输出路径
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "polygon_data.json"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "broker_config.json"

# 监控股票列表（限制数量以节省免费额度）
WATCH_SYMBOLS = [
    "AAPL",   # 苹果
    "MSFT",   # 微软
    "NVDA",   # 英伟达
    "TSLA",   # 特斯拉
    "COIN",   # Coinbase
]


async def fetch_quote(session, symbol, api_key):
    """获取单个股票报价（使用前一日收盘价）"""
    try:
        # 使用 previous close endpoint（免费版可用）
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev"
        params = {
            "adjusted": "true",
            "apiKey": api_key
        }
        
        async with session.get(url, params=params, timeout=10) as response:
            if response.status != 200:
                return None
            
            data = await response.json()
            results = data.get("results", [])
            
            if not results:
                return None
            
            result = results[0]
            
            return {
                "symbol": symbol,
                "price": result.get("c", 0),  # close
                "change": result.get("c", 0) - result.get("o", 0),  # close - open
                "change_percent": ((result.get("c", 0) - result.get("o", 0)) / result.get("o", 1)) * 100,
                "volume": result.get("v", 0),
                "high": result.get("h", 0),
                "low": result.get("l", 0),
                "open": result.get("o", 0),
                "vwap": result.get("vw", 0),  # volume weighted average price
                "timestamp": datetime.fromtimestamp(result.get("t", 0) / 1000).isoformat() if result.get("t") else yesterday
            }
            
    except Exception as e:
        print(f"❌ 获取 {symbol} 失败: {e}")
        return None


async def collect_polygon_data():
    """采集 Polygon.io 数据"""
    
    try:
        # 读取 API Key
        api_key = "demo"  # 默认使用 demo key
        
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                api_key = config_data.get("brokers", {}).get("polygon", {}).get("api_key", "demo")
        
        async with aiohttp.ClientSession() as session:
            # 串行获取（免费版限制: 5 次/分钟）
            stocks_data = []
            for i, symbol in enumerate(WATCH_SYMBOLS, 1):
                print(f"采集 {symbol} ({i}/{len(WATCH_SYMBOLS)})...")
                result = await fetch_quote(session, symbol, api_key)
                if result:
                    stocks_data.append(result)
                
                # 只在非最后一个时等待
                if i < len(WATCH_SYMBOLS):
                    await asyncio.sleep(12)  # 5 次/分钟 = 12 秒/次
            
            result = {
                "status": "success",
                "source": "polygon",
                "stocks": stocks_data,
                "total_symbols": len(stocks_data),
                "failed_symbols": len(WATCH_SYMBOLS) - len(stocks_data),
                "api_key_type": "demo" if api_key == "demo" else "custom",
                "note": "使用前一日收盘价（免费版限制）",
                "timestamp": datetime.now().isoformat()
            }
            
            # 保存到文件
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Polygon.io 数据采集成功: {len(stocks_data)}/{len(WATCH_SYMBOLS)} 个股票")
            return result
            
    except Exception as e:
        error_result = {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }
        
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, indent=2, ensure_ascii=False)
        
        print(f"❌ Polygon.io 数据采集失败: {e}")
        return error_result


if __name__ == "__main__":
    result = asyncio.run(collect_polygon_data())
    print(json.dumps(result, indent=2, ensure_ascii=False))
