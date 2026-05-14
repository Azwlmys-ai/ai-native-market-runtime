#!/usr/bin/env python3
"""
中国 A 股数据采集器
数据源：同花顺、东方财富、新浪财经
"""

import json
import requests
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir

class CNStocksCollector:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 代理配置
        self.proxies = {
            'http': 'http://host.docker.internal:17891',
            'https': 'http://host.docker.internal:17891'
        }
        
        # 请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.eastmoney.com/'
        }
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [CN Stocks Collector] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"cn_stocks_collector_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def fetch_eastmoney_stocks(self):
        """
        东方财富 - 沪深 A 股实时行情
        API: http://push2.eastmoney.com/api/qt/clist/get
        """
        self.log("📊 采集东方财富数据...")
        
        try:
            # 沪深 A 股主板
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': 1,  # 页码
                'pz': 100,  # 每页数量
                'po': 1,
                'np': 1,
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',  # 涨跌幅排序
                'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',  # 沪深 A 股
                'fields': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152'
            }
            
            response = requests.get(url, params=params, headers=self.headers, proxies=self.proxies, timeout=10)
            
            if response.status_code != 200:
                self.log(f"❌ 东方财富 API 返回 {response.status_code}")
                return []
            
            data = response.json()
            
            if data.get('rc') != 0:
                self.log(f"❌ 东方财富 API 错误: {data.get('message')}")
                return []
            
            stocks_data = data.get('data', {}).get('diff', [])
            
            stocks = []
            for item in stocks_data:
                stock = {
                    'source': 'eastmoney',
                    'code': item.get('f12'),  # 股票代码
                    'name': item.get('f14'),  # 股票名称
                    'price': item.get('f2'),  # 最新价
                    'change_pct': item.get('f3'),  # 涨跌幅 %
                    'change_amount': item.get('f4'),  # 涨跌额
                    'volume': item.get('f5'),  # 成交量（手）
                    'turnover': item.get('f6'),  # 成交额（元）
                    'amplitude': item.get('f7'),  # 振幅 %
                    'high': item.get('f15'),  # 最高价
                    'low': item.get('f16'),  # 最低价
                    'open': item.get('f17'),  # 今开
                    'close_prev': item.get('f18'),  # 昨收
                    'volume_ratio': item.get('f10'),  # 量比
                    'turnover_rate': item.get('f8'),  # 换手率 %
                    'pe_ratio': item.get('f9'),  # 市盈率
                    'pb_ratio': item.get('f23'),  # 市净率
                    'market_cap': item.get('f20'),  # 总市值
                    'circulation_market_cap': item.get('f21'),  # 流通市值
                    'timestamp': datetime.now().isoformat()
                }
                stocks.append(stock)
            
            self.log(f"✅ 东方财富: 采集 {len(stocks)} 只股票")
            return stocks
        
        except Exception as e:
            self.log(f"❌ 东方财富采集失败: {e}")
            return []
    
    def fetch_sina_stocks(self):
        """
        新浪财经 - A 股实时行情
        API: http://hq.sinajs.cn/list=
        使用更真实的浏览器头 + 随机延迟绕过反爬虫
        """
        self.log("📊 采集新浪财经数据...")
        
        try:
            import time
            import random
            
            # 更真实的浏览器头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Referer': 'http://finance.sina.com.cn/',
                'Connection': 'keep-alive',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
            
            # 热门股票代码（扩展列表）
            stock_codes = [
                # 白酒
                'sh600519',  # 贵州茅台
                'sz000858',  # 五粮液
                'sz000568',  # 泸州老窖
                # 金融
                'sh601318',  # 中国平安
                'sh600036',  # 招商银行
                'sh601166',  # 兴业银行
                # 科技
                'sz000333',  # 美的集团
                'sz002594',  # 比亚迪
                'sh600276',  # 恒瑞医药
                'sz300750',  # 宁德时代
                'sh601012',  # 隆基绿能
                'sz002475',  # 立讯精密
                'sz000725',  # 京东方A
                'sz002371',  # 北方华创
                # 新能源
                'sh688041',  # 海光信息
                'sh688981',  # 中芯国际
                'sh688008',  # 澜起科技
                # 消费
                'sh600887',  # 伊利股份
                'sz000651',  # 格力电器
                'sz002304',  # 洋河股份
            ]
            
            # 随机延迟 0.5-1.5 秒
            time.sleep(random.uniform(0.5, 1.5))
            
            url = f"http://hq.sinajs.cn/list={','.join(stock_codes)}"
            
            # 不使用代理（新浪可能屏蔽代理）
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                self.log(f"❌ 新浪财经 API 返回 {response.status_code}")
                return []
            
            # 解析响应
            lines = response.text.strip().split('\n')
            
            stocks = []
            for line in lines:
                if not line or '=' not in line:
                    continue
                
                # 格式: var hq_str_sh600519="贵州茅台,1650.00,..."
                parts = line.split('=')
                if len(parts) < 2:
                    continue
                
                code = parts[0].replace('var hq_str_', '').strip()
                data_str = parts[1].strip('";\n')
                data_parts = data_str.split(',')
                
                if len(data_parts) < 32:
                    continue
                
                try:
                    stock = {
                        'source': 'sina',
                        'code': code,
                        'name': data_parts[0],
                        'open': float(data_parts[1]) if data_parts[1] else 0,
                        'close_prev': float(data_parts[2]) if data_parts[2] else 0,
                        'price': float(data_parts[3]) if data_parts[3] else 0,
                        'high': float(data_parts[4]) if data_parts[4] else 0,
                        'low': float(data_parts[5]) if data_parts[5] else 0,
                        'bid_price': float(data_parts[6]) if data_parts[6] else 0,  # 买一价
                        'ask_price': float(data_parts[7]) if data_parts[7] else 0,  # 卖一价
                        'volume': int(data_parts[8]) if data_parts[8] else 0,  # 成交量（股）
                        'turnover': float(data_parts[9]) if data_parts[9] else 0,  # 成交额（元）
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # 计算涨跌幅
                    if stock['close_prev'] > 0:
                        stock['change_pct'] = ((stock['price'] - stock['close_prev']) / stock['close_prev']) * 100
                        stock['change_amount'] = stock['price'] - stock['close_prev']
                    else:
                        stock['change_pct'] = 0
                        stock['change_amount'] = 0
                    
                    stocks.append(stock)
                except (ValueError, IndexError) as e:
                    self.log(f"⚠️ 解析新浪数据失败: {code}, {e}")
                    continue
            
            self.log(f"✅ 新浪财经: 采集 {len(stocks)} 只股票")
            return stocks
        
        except Exception as e:
            self.log(f"❌ 新浪财经采集失败: {e}")
            return []
    
    def fetch_tonghuashun_stocks(self):
        """
        同花顺 - A 股实时行情
        使用 HTML 解析（新 API）
        """
        self.log("📊 采集同花顺数据...")
        
        try:
            import time
            import random
            from bs4 import BeautifulSoup
            
            # 随机延迟
            time.sleep(random.uniform(0.3, 0.8))
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': 'http://q.10jqka.com.cn/',
            }
            
            # 同花顺涨幅榜（HTML 格式）
            url = "http://q.10jqka.com.cn/index/index/board/all/field/zdf/order/desc/page/1/ajax/1/"
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                self.log(f"❌ 同花顺 API 返回 {response.status_code}")
                return []
            
            # 使用 BeautifulSoup 解析 HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找表格
            table = soup.find('table', class_='m-table')
            
            if not table:
                self.log("❌ 同花顺未找到数据表格")
                return []
            
            tbody = table.find('tbody')
            if not tbody:
                self.log("❌ 同花顺表格无数据")
                return []
            
            rows = tbody.find_all('tr')
            
            stocks = []
            for row in rows[:50]:  # 取前 50 只
                cols = row.find_all('td')
                
                if len(cols) < 10:
                    continue
                
                try:
                    # 提取数据（列索引：0=序号, 1=代码, 2=名称, 3=现价, 4=涨跌幅, 5=涨跌, 6=涨速, 7=换手, 8=量比, 9=振幅, 10=成交额, 11=流通股, 12=流通市值, 13=市盈率）
                    code = cols[1].text.strip()
                    name = cols[2].text.strip()
                    price = float(cols[3].text.strip())
                    change_pct = float(cols[4].text.strip())
                    
                    # 可选字段
                    try:
                        change_amount = float(cols[5].text.strip())
                    except:
                        change_amount = 0
                    
                    try:
                        # 涨速
                        speed = float(cols[6].text.strip())
                    except:
                        speed = 0
                    
                    try:
                        turnover = float(cols[7].text.strip())
                    except:
                        turnover = 0
                    
                    try:
                        # 量比
                        volume_ratio = float(cols[8].text.strip())
                    except:
                        volume_ratio = 0
                    
                    try:
                        # 振幅（可能是"--"）
                        amplitude_str = cols[9].text.strip()
                        if amplitude_str in ['--', '']:
                            amplitude = 0
                        else:
                            amplitude = float(amplitude_str)
                    except:
                        amplitude = 0
                    
                    try:
                        # 成交额（可能带单位：万、亿）
                        turnover_amount_str = cols[10].text.strip()
                        if '万' in turnover_amount_str:
                            turnover_amount = float(turnover_amount_str.replace('万', '').replace('亿', '')) * 10000
                        elif '亿' in turnover_amount_str:
                            turnover_amount = float(turnover_amount_str.replace('亿', '')) * 100000000
                        else:
                            turnover_amount = float(turnover_amount_str)
                    except:
                        turnover_amount = 0
                    
                    try:
                        # 市盈率（可能是"亏损"或"--"）
                        pe_str = cols[13].text.strip()
                        if pe_str in ['亏损', '--', '']:
                            pe = 0
                        else:
                            pe = float(pe_str)
                    except:
                        pe = 0
                    
                    stock = {
                        'source': 'tonghuashun',
                        'code': code,
                        'name': name,
                        'price': price,
                        'change_pct': change_pct,
                        'change_amount': change_amount,
                        'speed': speed,
                        'turnover': turnover,
                        'volume_ratio': volume_ratio,
                        'amplitude': amplitude,
                        'turnover_amount': turnover_amount,
                        'pe': pe,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    stocks.append(stock)
                
                except (ValueError, IndexError, AttributeError) as e:
                    self.log(f"⚠️ 解析失败: {e}")
                    continue
            
            self.log(f"✅ 同花顺: 采集 {len(stocks)} 只股票")
            return stocks
        
        except Exception as e:
            self.log(f"❌ 同花顺采集失败: {e}")
            return []
    
    def run(self):
        """主流程"""
        self.log("=" * 60)
        self.log("开始采集中国 A 股数据")
        
        all_stocks = {}
        
        # 1. 东方财富（主要数据源）
        eastmoney_stocks = self.fetch_eastmoney_stocks()
        for stock in eastmoney_stocks:
            code = stock.get('code')
            if code:
                all_stocks[code] = stock
        
        # 2. 新浪财经（补充数据）
        sina_stocks = self.fetch_sina_stocks()
        for stock in sina_stocks:
            code = stock.get('code')
            if code and code not in all_stocks:
                all_stocks[code] = stock
        
        # 3. 同花顺（补充数据，合并而不是跳过）
        tonghuashun_stocks = self.fetch_tonghuashun_stocks()
        for stock in tonghuashun_stocks:
            code = stock.get('code')
            if code:
                if code in all_stocks:
                    # 合并数据：保留原有数据，补充同花顺特有字段
                    all_stocks[code]['tonghuashun_speed'] = stock.get('speed', 0)
                    all_stocks[code]['tonghuashun_volume_ratio'] = stock.get('volume_ratio', 0)
                    all_stocks[code]['tonghuashun_turnover_amount'] = stock.get('turnover_amount', 0)
                    all_stocks[code]['tonghuashun_pe'] = stock.get('pe', 0)
                else:
                    all_stocks[code] = stock
        
        # 保存到 latest_data.json
        data_file = self.data_dir / "latest_data.json"
        tmp_file = self.data_dir / "latest_data.json.tmp"
        
        if data_file.exists():
            with open(data_file, 'r') as f:
                existing_data = json.load(f)
        else:
            existing_data = {}
        
        existing_data['cn_stocks'] = {
            'data': list(all_stocks.values()),
            'count': len(all_stocks),
            'timestamp': datetime.now().isoformat()
        }
        
        # 原子写：先写 .tmp，然后 rename
        with open(tmp_file, 'w') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
        tmp_file.rename(data_file)
        
        self.log(f"✅ 总计采集 {len(all_stocks)} 只 A 股数据")
        self.log("=" * 60)

def main():
    collector = CNStocksCollector()
    collector.run()

if __name__ == "__main__":
    main()
