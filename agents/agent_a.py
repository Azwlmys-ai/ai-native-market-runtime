"""
Agent A - 市场数据采集器
职责：采集 Polymarket、OKX、新闻、天气等多源数据
"""

import json
import asyncio
import ssl
import aiohttp
import certifi
import sys
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from _paths import get_base_dir


def _aiohttp_ssl_connector():
    """macOS 自带 Python 常缺根证书；用 certifi _bundle 避免 SSLCertVerificationError。"""
    ctx = ssl.create_default_context(cafile=certifi.where())
    return aiohttp.TCPConnector(ssl=ctx)


class AgentA:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent A] {message}"
        print(log_msg)
        
        # 写入日志文件
        log_file = self.logs_dir / f"agent_a_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    async def fetch_polymarket_markets(self):
        """采集 Polymarket 市场数据"""
        self.log("采集 Polymarket 市场数据...")
        
        try:
            async with aiohttp.ClientSession(connector=_aiohttp_ssl_connector()) as session:
                params = {
                    "limit": 100,
                    "active": "true",
                    "closed": "false"
                }
                endpoints = [
                    "https://gamma-api.polymarket.com/markets/keyset",
                    "https://gamma-api.polymarket.com/markets",
                ]

                raw_data = None
                last_status = None
                for url in endpoints:
                    async with session.get(url, params=params, timeout=30) as resp:
                        last_status = resp.status
                        if resp.status == 200:
                            payload = await resp.json()
                            raw_data = payload.get("markets", payload) if isinstance(payload, dict) else payload
                            break
                        self.log(f"⚠️ Polymarket API {url} 错误: {resp.status}")

                if raw_data is None:
                    self.log(f"❌ Polymarket API 错误: {last_status}")
                    return None

                if not isinstance(raw_data, list):
                    self.log(f"❌ Polymarket API schema 异常: {type(raw_data).__name__}")
                    return None

                # 解析和规范化数据
                markets = []
                for m in raw_data:
                    try:
                        # 解析字符串格式的 JSON 字段
                        outcomes = json.loads(m.get('outcomes', '[]'))
                        outcome_prices = json.loads(m.get('outcomePrices', '[]'))

                        # 转换价格为浮点数
                        prices = [float(p) for p in outcome_prices]

                        markets.append({
                            'id': m.get('id'),
                            'slug': m.get('slug'),  # 交易时使用 slug
                            'question': m.get('question'),
                            'outcomes': outcomes,
                            'outcome_prices': prices,
                            'liquidity': float(m.get('liquidityNum', 0)),
                            'volume': float(m.get('volumeNum', 0)),
                            'end_date': m.get('endDate')
                        })
                    except Exception as e:
                        self.log(f"⚠️ 解析市场失败: {e}")
                        continue

                self.log(f"✅ 采集到 {len(markets)} 个市场")
                return markets
        
        except Exception as e:
            self.log(f"❌ Polymarket 采集失败: {e}")
            return None
    
    async def fetch_google_news(self):
        """采集 Google News RSS"""
        self.log("采集 Google News...")
        
        try:
            async with aiohttp.ClientSession(connector=_aiohttp_ssl_connector()) as session:
                url = "https://news.google.com/rss/search?q=cryptocurrency+OR+bitcoin+OR+prediction+market&hl=en-US&gl=US&ceid=US:en"
                
                async with session.get(url, timeout=30) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        self.log(f"✅ 采集到新闻数据 ({len(text)} 字节)")
                        return text  # 返回完整文本
                    else:
                        self.log(f"❌ Google News 错误: {resp.status}")
                        return ""
        
        except Exception as e:
            self.log(f"❌ Google News 采集失败: {e}")
            return ""
    
    async def fetch_fred_rates(self):
        """采集 FRED 联邦基金利率"""
        self.log("采集 FRED 利率数据...")
        
        try:
            # FRED API 需要 API Key，这里使用公开数据端点
            async with aiohttp.ClientSession(connector=_aiohttp_ssl_connector()) as session:
                url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"
                
                async with session.get(url, timeout=30) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        lines = text.strip().split('\n')
                        if len(lines) > 1:
                            latest = lines[-1].split(',')
                            self.log(f"✅ 最新利率: {latest}")
                            return latest  # 返回 [date, rate]
                    else:
                        self.log(f"❌ FRED 错误: {resp.status}")
                        return []
        
        except Exception as e:
            self.log(f"❌ FRED 采集失败: {e}")
            return []
    
    async def fetch_okx_data(self):
        """采集 OKX 完整数据（调用 okx_collector.py）"""
        self.log("采集 OKX 完整数据...")
        
        try:
            okx_collector = self.base_dir / "collectors" / "okx_collector.py"
            result = subprocess.run(
                [sys.executable, str(okx_collector)],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                # 读取 okx_data.json
                okx_data_file = self.data_dir / "okx_data.json"
                if okx_data_file.exists():
                    with open(okx_data_file, 'r') as f:
                        okx_data = json.load(f)
                    
                    # 转换为 Agent 需要的格式
                    formatted_data = {
                        "data": [],
                        "timestamp": okx_data.get("timestamp")
                    }
                    
                    for coin in ['btc', 'eth', 'bnb', 'sol']:
                        if coin in okx_data:
                            coin_data = okx_data[coin]
                            if coin_data.get('spot') and coin_data.get('perpetual'):
                                formatted_data["data"].append({
                                    "symbol": coin.upper(),
                                    "spot_price": coin_data['spot']['last_price'],
                                    "swap_price": coin_data['perpetual']['last_price'],
                                    "funding_rate": coin_data.get('funding', {}).get('funding_rate', 0)
                                })
                    
                    self.log(f"✅ OKX 数据: {len(formatted_data['data'])} 个币种")
                    return formatted_data
                else:
                    self.log("❌ okx_data.json 不存在")
                    return {"data": [], "timestamp": datetime.now().isoformat()}
            else:
                self.log(f"❌ OKX 采集器执行失败: {result.stderr}")
                return {"data": [], "timestamp": datetime.now().isoformat()}
        
        except Exception as e:
            self.log(f"❌ OKX 采集失败: {e}")
            return {"data": [], "timestamp": datetime.now().isoformat()}
    
    async def fetch_okx_funding(self):
        """采集 OKX 资金费率（保留用于向后兼容）"""
        self.log("采集 OKX 资金费率...")
        
        try:
            async with aiohttp.ClientSession(connector=_aiohttp_ssl_connector()) as session:
                url = "https://www.okx.com/api/v5/public/funding-rate"
                params = {"instId": "BTC-USDT-SWAP"}
                
                async with session.get(url, params=params, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("code") == "0" and data.get("data"):
                            rate = data["data"][0]
                            funding_rate = float(rate.get('fundingRate', 0))
                            self.log(f"✅ BTC 资金费率: {funding_rate}")
                            return funding_rate
                    else:
                        self.log(f"❌ OKX 错误: {resp.status}")
                        return None
        
        except Exception as e:
            self.log(f"❌ OKX 采集失败: {e}")
            return None
    
    async def run(self):
        """并发采集所有数据源"""
        self.log("开始数据采集...")
        
        # 顺序执行：避免并发 getaddrinfo 压垮 Clash/Surge fake-IP DNS
        # 原 asyncio.gather 会同时发起 4 个 DNS 查询，触发本地 DNS 解析失败
        results = []
        for coro in [
            self.fetch_polymarket_markets(),
            self.fetch_google_news(),
            self.fetch_fred_rates(),
            self.fetch_okx_funding(),
        ]:
            try:
                results.append(await coro)
            except Exception as e:
                results.append(e)
        
        # 同步调用 OKX 完整数据采集（因为使用 subprocess）
        okx_data = await self.fetch_okx_data()
        
        # 保存数据
        existing = {}
        output_file = self.data_dir / "latest_data.json"
        if output_file.exists():
            try:
                with open(output_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        polymarket_markets = results[0] if not isinstance(results[0], Exception) else None
        polymarket_status = "ok"
        if polymarket_markets is None:
            polymarket_markets = existing.get("polymarket_markets", [])
            polymarket_status = "stale" if polymarket_markets else "unavailable"
            self.log(
                f"⚠️ Polymarket 本轮采集失败，"
                f"{'保留旧市场数据' if polymarket_markets else '无旧市场数据可保留'}"
            )

        data = {
            "timestamp": datetime.now().isoformat(),
            "polymarket_markets": polymarket_markets,
            "polymarket_status": polymarket_status,
            "google_news": results[1] if not isinstance(results[1], Exception) else "",
            "fed_rate": results[2] if not isinstance(results[2], Exception) else [],
            "btc_funding_rate": results[3] if not isinstance(results[3], Exception) else None,
            "okx": okx_data
        }
        
        # Preserve fields written by other collectors (e.g. us_stocks from
        # us_stocks_updater at step 0) so Agent A's write does not drop them.
        # Agent A's own fields always win; only non-overlapping keys are kept.
        merged = {**existing, **data}

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)

        self.log(f"✅ 数据已保存到 {output_file}")

def main():
    agent = AgentA()
    asyncio.run(agent.run())

if __name__ == "__main__":
    main()
