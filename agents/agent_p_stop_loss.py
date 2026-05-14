#!/usr/bin/env python3
"""
Agent P - 持仓管理（止损增强版）
职责：监控持仓，自动止损
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir, get_pm_trader, get_pm_trader_env

class AgentPStopLoss:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 止损规则
        self.stop_loss_threshold = -0.40  # -40% 止损
        self.trailing_stop = -0.20  # -20% 移动止损
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent P Stop Loss] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"agent_p_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def get_portfolio(self):
        """获取持仓"""
        try:
            result = subprocess.run(
                [get_pm_trader(), "portfolio"],
                capture_output=True,
                text=True,
                timeout=15,
                env=get_pm_trader_env()
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get('data', [])
            else:
                self.log(f"❌ 获取持仓失败: {result.stderr}")
                return []
        
        except Exception as e:
            self.log(f"❌ 获取持仓异常: {e}")
            return []
    
    def check_stop_loss(self, position):
        """检查是否需要止损"""
        market_slug = position.get('market_slug')
        market_question = position.get('market_question', '')
        percent_pnl = position.get('percent_pnl', 0)
        unrealized_pnl = position.get('unrealized_pnl', 0)
        
        # 止损条件：亏损 >= 40%
        if percent_pnl <= self.stop_loss_threshold * 100:
            self.log(f"🚨 触发止损: {market_question[:60]}")
            self.log(f"   亏损: {percent_pnl:.2f}% (${unrealized_pnl:.2f})")
            self.log(f"   止损阈值: {self.stop_loss_threshold * 100}%")
            return True, "stop_loss"
        
        # 移动止损：从盈利回撤 >= 20%
        # TODO: 需要记录最高盈利点
        
        return False, None
    
    def execute_sell(self, position, reason):
        """执行卖出"""
        market_slug = position.get('market_slug')
        outcome = position.get('outcome')
        shares = position.get('shares')
        
        self.log(f"执行止损卖出: {market_slug}")
        self.log(f"  方向: {outcome}, 股数: {shares:.0f}")
        
        try:
            result = subprocess.run(
                [
                    get_pm_trader(),
                    "sell",
                    market_slug,
                    outcome.upper(),
                    str(int(shares))
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=get_pm_trader_env()
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get('ok'):
                    trade = data.get('data', {}).get('trade', {})
                    amount = trade.get('amount_usd', 0)
                    self.log(f"✅ 止损成功: 回收 ${amount:.2f}")
                    return True
                else:
                    error = data.get('error', 'Unknown error')
                    self.log(f"❌ 止损失败: {error}")
                    return False
            else:
                self.log(f"❌ 止损失败: {result.stderr}")
                return False
        
        except Exception as e:
            self.log(f"❌ 止损异常: {e}")
            return False
    
    def run(self):
        """主流程"""
        self.log("=" * 60)
        self.log("开始持仓管理（止损检查）")
        
        # 获取持仓
        positions = self.get_portfolio()
        self.log(f"📊 当前持仓: {len(positions)} 个")
        
        if not positions:
            self.log("ℹ️ 无持仓")
            return
        
        # 检查每个持仓
        stop_loss_count = 0
        
        for position in positions:
            market_question = position.get('market_question', '')
            percent_pnl = position.get('percent_pnl', 0)
            
            # 检查止损
            should_stop, reason = self.check_stop_loss(position)
            
            if should_stop:
                # 执行止损
                success = self.execute_sell(position, reason)
                if success:
                    stop_loss_count += 1
        
        self.log(f"✅ 持仓管理完成")
        self.log(f"   止损笔数: {stop_loss_count}")
        self.log("=" * 60)

def main():
    agent = AgentPStopLoss()
    agent.run()

if __name__ == "__main__":
    main()
