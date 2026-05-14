"""
Agent P - 持仓管理监控
职责：监控持仓，生成止盈止损信号
"""

import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir, get_pm_trader, get_pm_trader_env

class AgentP:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.config_dir = self.base_dir / "config"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent P] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_p_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_config(self):
        """加载系统配置"""
        config_file = self.config_dir / "system_config.json"
        
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.log(f"⚠️  加载配置失败: {e}")
            return {}
    
    def get_portfolio(self):
        """获取当前持仓"""
        try:
            result = subprocess.run(
                [get_pm_trader(), "portfolio"],
                capture_output=True,
                text=True,
                timeout=30,
                env=get_pm_trader_env()
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("ok"):
                    positions = data.get("data", [])
                    self.log(f"📊 当前持仓：{len(positions)} 个")
                    self.save_positions(positions)
                    return positions
            
            self.log(f"❌ 获取持仓失败: {result.stderr}")
            return []
        
        except Exception as e:
            self.log(f"❌ 获取持仓异常: {e}")
            return []

    def save_positions(self, positions):
        """保存最新持仓快照，供策略和健康检查使用"""
        output_file = self.data_dir / "positions.json"
        with open(output_file, 'w') as f:
            json.dump(positions, f, indent=2, ensure_ascii=False)
        self.log(f"✅ 持仓快照已保存到 {output_file}")
    
    def load_strategy_config(self):
        """加载动态策略配置"""
        config_file = self.data_dir / "strategy_config.json"
        
        if not config_file.exists():
            self.log("⚠️  无策略配置，使用默认参数")
            return None
        
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            self.log("✅ 加载动态策略配置")
            return config
        except Exception as e:
            self.log(f"⚠️  加载策略配置失败: {e}")
            return None
    
    def load_learning_knowledge(self):
        """加载学习知识库"""
        kb_file = self.data_dir / "learning_knowledge_base.json"
        
        if not kb_file.exists():
            self.log("⚠️  无学习知识库")
            return None
        
        try:
            with open(kb_file, 'r') as f:
                kb = json.load(f)
            self.log("✅ 加载学习知识库")
            return kb
        except Exception as e:
            self.log(f"⚠️  加载学习知识库失败: {e}")
            return None
    
    def get_market_category(self, market_slug):
        """识别市场类别"""
        market_lower = market_slug.lower()
        
        if any(sport in market_lower for sport in ['nhl', 'nba', 'nfl', 'mlb', 'soccer', 'football']):
            return 'sports'
        elif any(crypto in market_lower for crypto in ['btc', 'bitcoin', 'eth', 'ethereum', 'crypto']):
            return 'crypto'
        elif any(pol in market_lower for pol in ['trump', 'biden', 'election', 'president', 'democrat', 'republican']):
            return 'politics'
        elif any(ent in market_lower for ent in ['gta', 'movie', 'album', 'celebrity']):
            return 'entertainment'
        else:
            return 'default'
    
    def analyze_positions(self, positions):
        """分析持仓，生成卖出信号（使用动态策略）"""
        self.log("分析持仓...")
        
        # 加载动态策略配置
        strategy_config = self.load_strategy_config()
        learning_kb = self.load_learning_knowledge()
        
        # 默认参数（如果没有动态配置）
        default_take_profit = 0.15
        default_stop_loss = -0.10
        trailing_trigger = 0.20
        trailing_percent = 0.05
        
        sell_signals = []
        gta_vi_positions = []
        
        for pos in positions:
            market_slug = pos.get("market_slug", "")
            pnl_percent = pos.get("percent_pnl", 0) / 100
            category = self.get_market_category(market_slug)
            
            # 检查 GTA VI 相关性
            if "gta" in market_slug.lower() and "vi" in market_slug.lower():
                gta_vi_positions.append(pos)
            
            # 根据市场类别和策略配置，动态设置止盈止损
            if strategy_config:
                take_profit_range = strategy_config.get("take_profit", {}).get(category, strategy_config.get("take_profit", {}).get("default", {"min": 0.10, "max": 0.15}))
                take_profit = take_profit_range.get("max", default_take_profit)
                
                # 根据置信度设置止损（这里简化处理，使用中等置信度）
                stop_loss = strategy_config.get("stop_loss", {}).get("medium_confidence", default_stop_loss)
                
                # 获利回撤参数
                trailing_config = strategy_config.get("trailing_stop", {})
                trailing_trigger = trailing_config.get("trigger_profit", 0.20)
                trailing_percent = trailing_config.get("trailing_percent", 0.05)
            else:
                take_profit = default_take_profit
                stop_loss = default_stop_loss
            
            # 止盈
            if pnl_percent >= take_profit:
                sell_signals.append({
                    "market": market_slug,
                    "outcome": pos.get("outcome"),
                    "shares": pos.get("shares"),
                    "reason": f"止盈 ({pnl_percent:.2%}, 目标 {take_profit:.0%})",
                    "priority": "high",
                    "pnl": pnl_percent,
                    "category": category
                })
            
            # 止损
            elif pnl_percent <= stop_loss:
                sell_signals.append({
                    "market": market_slug,
                    "outcome": pos.get("outcome"),
                    "shares": pos.get("shares"),
                    "reason": f"止损 ({pnl_percent:.2%}, 阈值 {stop_loss:.0%})",
                    "priority": "urgent",
                    "pnl": pnl_percent,
                    "category": category
                })
            
            # 获利回撤止盈（当浮盈达到 20% 后，从最高点回撤 5% 就卖出）
            elif pnl_percent >= trailing_trigger:
                # 这里简化处理，假设当前价格就是最高点附近
                # 实际应该跟踪历史最高价格
                sell_signals.append({
                    "market": market_slug,
                    "outcome": pos.get("outcome"),
                    "shares": pos.get("shares"),
                    "reason": f"获利回撤止盈 ({pnl_percent:.2%})",
                    "priority": "high",
                    "pnl": pnl_percent,
                    "category": category
                })
            
            # 小幅盈利但接近止损（保护利润）
            elif 0.02 <= pnl_percent < take_profit:
                # 检查是否有回撤风险
                if pos.get("live_price", 0) < pos.get("avg_entry_price", 0) * 0.98:
                    sell_signals.append({
                        "market": market_slug,
                        "outcome": pos.get("outcome"),
                        "shares": pos.get("shares"),
                        "reason": f"保护利润 ({pnl_percent:.2%})",
                        "priority": "medium",
                        "pnl": pnl_percent,
                        "category": category
                    })
        
        # GTA VI 相关性风险检查
        if len(gta_vi_positions) >= 3:
            self.log(f"⚠️  GTA VI 相关性风险：{len(gta_vi_positions)} 个持仓")
            
            # 平仓表现最差的 GTA VI 持仓
            gta_vi_positions.sort(key=lambda x: x.get("percent_pnl", 0))
            
            for pos in gta_vi_positions[:2]:  # 平仓最差的 2 个
                if pos.get("market_slug") not in [s["market"] for s in sell_signals]:
                    sell_signals.append({
                        "market": pos.get("market_slug"),
                        "outcome": pos.get("outcome"),
                        "shares": pos.get("shares"),
                        "reason": "降低 GTA VI 相关性风险",
                        "priority": "high",
                        "pnl": pos.get("percent_pnl", 0) / 100
                    })
        
        self.log(f"✅ 生成 {len(sell_signals)} 个卖出信号")
        
        return sell_signals
    
    def run(self):
        """执行持仓管理"""
        self.log("开始持仓管理...")
        
        positions = self.get_portfolio()
        
        if not positions:
            self.log("ℹ️  无持仓")
            return
        
        sell_signals = self.analyze_positions(positions)
        
        # 保存卖出信号（即使为空也保存，方便调试）
        output_file = self.data_dir / "sell_signals.json"
        with open(output_file, 'w') as f:
            json.dump(sell_signals, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ 生成 {len(sell_signals)} 个卖出信号")
        
        if sell_signals:
            # 按优先级分类
            urgent = [s for s in sell_signals if s["priority"] == "urgent"]
            high = [s for s in sell_signals if s["priority"] == "high"]
            medium = [s for s in sell_signals if s["priority"] == "medium"]
            
            if urgent:
                self.log(f"🚨 紧急止损：{len(urgent)} 个")
            if high:
                self.log(f"⚠️  高优先级：{len(high)} 个")
            if medium:
                self.log(f"ℹ️  中优先级：{len(medium)} 个")
        else:
            self.log("ℹ️  无卖出信号")

def main():
    agent = AgentP()
    agent.run()

if __name__ == "__main__":
    main()
