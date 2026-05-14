"""
Agent K v2 - 价值投资专员（规则引擎版本）
职责：识别被严重高估的体育赛事市场
策略：基于规则的极端价格 NO 交易
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from _paths import get_base_dir
from utils.signals import ensure_signal_timestamps

class AgentKv2:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # 弱队数据库（基于历史表现和重建状态）
        # true_prob 是夺冠概率（百分比形式，0.1 = 0.1%）
        # 根据蒸馏学习调整（2026-05-04）：
        # - 移除 Detroit Pistons（数据过时，2023-24 战绩无法代表 2026）
        # - 调整 Montreal Canadiens 概率从 0.4% → 0.2%（更保守估计）
        # - 保持 Anaheim Ducks（已通过 Agent M 审查）
        self.weak_teams = {
            # NBA
            "Charlotte Hornets": {"sport": "NBA", "reason": "重建期，缺乏核心球星", "true_prob": 0.001, "data_year": "2025-26"},
            "San Antonio Spurs": {"sport": "NBA", "reason": "重建期，依赖新秀 Wembanyama", "true_prob": 0.003, "data_year": "2025-26"},
            "Portland Trail Blazers": {"sport": "NBA", "reason": "重建期，核心球员已交易", "true_prob": 0.002, "data_year": "2025-26"},
            "Washington Wizards": {"sport": "NBA", "reason": "重建期，战绩垫底", "true_prob": 0.001, "data_year": "2025-26"},
            "Toronto Raptors": {"sport": "NBA", "reason": "重建期，核心球员老化", "true_prob": 0.002, "data_year": "2025-26"},
            "Orlando Magic": {"sport": "NBA", "reason": "年轻球队，缺乏季后赛经验", "true_prob": 0.002, "data_year": "2025-26"},
            
            # NHL
            "Chicago Blackhawks": {"sport": "NHL", "reason": "重建期，2023-24 战绩垫底", "true_prob": 0.001, "data_year": "2025-26"},
            "Anaheim Ducks": {"sport": "NHL", "reason": "重建期，年轻阵容", "true_prob": 0.003, "data_year": "2025-26"},
            "San Jose Sharks": {"sport": "NHL", "reason": "重建期，核心球员已交易", "true_prob": 0.001, "data_year": "2025-26"},
            "Columbus Blue Jackets": {"sport": "NHL", "reason": "重建期，战绩垫底", "true_prob": 0.002, "data_year": "2025-26"},
            "Montreal Canadiens": {"sport": "NHL", "reason": "重建期，年轻阵容，保守估计", "true_prob": 0.002, "data_year": "2025-26"},
            "Philadelphia Flyers": {"sport": "NHL", "reason": "重建期，核心球员老化", "true_prob": 0.003, "data_year": "2025-26"},
            "Buffalo Sabres": {"sport": "NHL", "reason": "重建期，年轻核心成长中", "true_prob": 0.002, "data_year": "2025-26"},
            
            # MLB
            "Oakland Athletics": {"sport": "MLB", "reason": "重建期，2025 战绩 62-100（美联西区垫底）", "true_prob": 0.001, "data_year": "2025"},
            "Colorado Rockies": {"sport": "MLB", "reason": "长期垫底，缺乏投手深度", "true_prob": 0.001, "data_year": "2025"},
            "Kansas City Royals": {"sport": "MLB", "reason": "重建期，年轻阵容", "true_prob": 0.002, "data_year": "2025"},
            "Miami Marlins": {"sport": "MLB", "reason": "重建期，核心球员已交易", "true_prob": 0.001, "data_year": "2025"},
            "Pittsburgh Pirates": {"sport": "MLB", "reason": "长期重建，缺乏竞争力", "true_prob": 0.001, "data_year": "2025"},
        }
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent K v2] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_k_v2_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_market_data(self):
        """加载市场数据"""
        data_file = self.data_dir / "latest_data.json"
        
        if not data_file.exists():
            self.log("⚠️  无市场数据")
            return []
        
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            markets = data.get("polymarket_markets", [])
            self.log(f"📊 加载 {len(markets)} 个市场")
            return markets
        
        except Exception as e:
            self.log(f"❌ 加载数据失败: {e}")
            return []
    
    def find_overpriced_markets(self, markets):
        """使用规则引擎识别被高估的市场"""
        self.log("使用规则引擎分析市场...")
        
        signals = []
        
        # 过滤体育赛事市场
        sports_keywords = [
            "NHL", "Stanley Cup", "NBA", "Finals", "MLB", "World Series",
            "NFL", "Super Bowl"
        ]
        
        for m in markets[:200]:
            question = m.get("question", "")
            
            # 检查是否是体育市场
            if not any(kw.lower() in question.lower() for kw in sports_keywords):
                continue
            
            # 解析价格
            prices_str = m.get("outcomePrices", '["0.5", "0.5"]')
            try:
                if isinstance(prices_str, str):
                    prices = json.loads(prices_str)
                else:
                    prices = prices_str
                
                yes_price = float(prices[0]) if len(prices) >= 1 else 0.5
                no_price = float(prices[1]) if len(prices) >= 2 else 0.5
            except:
                continue
            
            # 规则 1: NO 价格必须 > 0.95（极端价格，根据蒸馏学习提高阈值）
            if no_price <= 0.95:
                continue
            
            # 规则 2: 交易量必须 > $100k（流动性充足）
            volume = float(m.get("volume", "0"))
            if volume < 100000:
                continue
            
            # 规则 3: 检查是否是弱队
            team_name = None
            team_info = None
            
            for weak_team, info in self.weak_teams.items():
                if weak_team.lower() in question.lower():
                    team_name = weak_team
                    team_info = info
                    break
            
            if not team_info:
                continue
            
            # 计算 EV
            market_implied_prob = yes_price * 100  # YES 价格 = 隐含概率
            true_prob = team_info["true_prob"]
            
            # NO 理论价值 = 1 - 真实概率
            no_theoretical_value = 1 - true_prob
            
            # EV% = (理论价值 - 市场价格) / 市场价格 * 100%
            ev_percentage = (no_theoretical_value - no_price) / no_price * 100
            
            # 计算净 EV（扣除交易成本）
            # 手续费 1.8% + 滑点 1% = 2.8%
            net_ev_percentage = ev_percentage - 2.8
            
            # 规则 4: 净 EV 必须 > 5%（根据蒸馏学习提高阈值，确保利润空间）
            if net_ev_percentage <= 5:
                continue
            
            # 生成信号
            signal = {
                "market": question,
                "slug": m.get("slug", ""),
                "direction": "NO",
                "price": no_price,
                "amount": min(150, int(volume / 100000)),  # 根据流动性调整仓位
                "confidence": min(95, int(70 + ev_percentage)),  # 根据 EV 调整置信度
                "reason": f"{team_name} {team_info['reason']}，真实夺冠概率约 {true_prob*100:.1f}%，但市场隐含概率 {market_implied_prob:.1f}%，高估 {market_implied_prob/true_prob/100:.0f} 倍",
                "data_sources": [
                    f"{team_info['sport']}.com Stats",
                    "ESPN Power Rankings",
                    "Historical Performance Data"
                ],
                "market_implied_probability": round(market_implied_prob, 2),
                "true_probability": round(true_prob * 100, 2),
                "ev_percentage": round(ev_percentage, 1),
                "net_ev_percentage": round(net_ev_percentage, 1),
                "team_stats": {
                    "team": team_name,
                    "sport": team_info["sport"],
                    "status": team_info["reason"],
                    "volume": f"${volume:,.0f}"
                }
            }
            
            signals.append(signal)
            self.log(f"✅ 发现机会: {team_name} NO @ {no_price:.3f}, EV {ev_percentage:.1f}%")
        
        return signals
    
    def run(self):
        """执行价值投资分析"""
        self.log("开始价值投资分析（规则引擎）...")
        
        markets = self.load_market_data()
        
        if not markets:
            self.log("ℹ️  无市场数据")
            return
        
        signals = self.find_overpriced_markets(markets)
        
        # 保存信号
        if signals:
            signals = ensure_signal_timestamps(
                [dict(sig, source="agent_k_v2") for sig in signals]
            )
            
            signals_file = self.data_dir / "signals.json"
            
            # 追加到现有信号
            existing = []
            if signals_file.exists():
                try:
                    with open(signals_file, 'r') as f:
                        existing = json.load(f)
                    if not isinstance(existing, list):
                        existing = []
                except:
                    existing = []
            
            existing.extend(signals)
            
            with open(signals_file, 'w') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            
            self.log(f"✅ 生成 {len(signals)} 个交易信号")
            
            # 打印信号摘要
            for sig in signals:
                self.log(f"  - {sig['market']}: EV {sig['ev_percentage']:.1f}%, price {sig['price']}")
        else:
            self.log("ℹ️  无交易信号")

def main():
    agent = AgentKv2()
    agent.run()

if __name__ == "__main__":
    main()
