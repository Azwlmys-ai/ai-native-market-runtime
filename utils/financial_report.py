#!/usr/bin/env python3
"""
财务核算工具
职责：统一报告所有市场的资金状况
"""

import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

class FinancialReport:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.pm_trader = "/opt/data/home/.local/bin/pm-trader"
    
    def get_polymarket_balance(self):
        """获取 Polymarket 账户余额"""
        try:
            result = subprocess.run(
                [self.pm_trader, "balance"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get('ok'):
                    balance_data = data['data']
                    return {
                        'cash': balance_data['cash'],
                        'positions_value': balance_data['positions_value'],
                        'total_value': balance_data['total_value'],
                        'pnl': balance_data['pnl'],
                        'starting_balance': balance_data['starting_balance']
                    }
        except Exception as e:
            print(f"❌ Polymarket 余额查询失败: {e}")
        
        return None
    
    def get_okx_balance(self):
        """获取 OKX 模拟账户余额"""
        try:
            db_path = self.data_dir / "okx_paper_trading.db"
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 账户余额
            cursor.execute("SELECT cash, starting_balance FROM account WHERE id = 1")
            account = cursor.fetchone()
            
            if not account:
                return None
            
            cash = account[0]
            starting_balance = account[1]
            
            # 持仓价值（简化：使用成本价）
            cursor.execute("SELECT SUM(total_cost) FROM positions WHERE quantity != 0")
            positions_value = cursor.fetchone()[0] or 0
            
            total_value = cash + positions_value
            pnl = total_value - starting_balance
            
            conn.close()
            
            return {
                'cash': cash,
                'positions_value': positions_value,
                'total_value': total_value,
                'pnl': pnl,
                'starting_balance': starting_balance
            }
        except Exception as e:
            print(f"❌ OKX 余额查询失败: {e}")
        
        return None
    
    def get_stock_balance(self):
        """获取美股模拟账户余额"""
        try:
            db_path = self.data_dir / "stock_paper_trading.db"
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 账户余额
            cursor.execute("SELECT cash, starting_balance FROM account WHERE id = 1")
            account = cursor.fetchone()
            
            if not account:
                return None
            
            cash = account[0]
            starting_balance = account[1]
            
            # 持仓价值（简化：使用成本价）
            cursor.execute("SELECT SUM(total_cost) FROM positions WHERE shares != 0")
            positions_value = cursor.fetchone()[0] or 0
            
            total_value = cash + positions_value
            pnl = total_value - starting_balance
            
            conn.close()
            
            return {
                'cash': cash,
                'positions_value': positions_value,
                'total_value': total_value,
                'pnl': pnl,
                'starting_balance': starting_balance
            }
        except Exception as e:
            print(f"❌ 美股余额查询失败: {e}")
        
        return None
    
    def get_cn_stocks_balance(self):
        """获取 A 股模拟账户余额"""
        try:
            db_path = self.data_dir / "cn_stocks_paper_trading.db"
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 账户余额
            cursor.execute("SELECT cash, starting_balance FROM account WHERE id = 1")
            account = cursor.fetchone()
            
            if not account:
                return None
            
            cash = account[0]
            starting_balance = account[1]
            
            # 持仓价值（简化：使用成本价）
            cursor.execute("SELECT SUM(total_cost) FROM positions WHERE shares != 0")
            positions_value = cursor.fetchone()[0] or 0
            
            total_value = cash + positions_value
            pnl = total_value - starting_balance
            
            conn.close()
            
            return {
                'cash': cash,
                'positions_value': positions_value,
                'total_value': total_value,
                'pnl': pnl,
                'starting_balance': starting_balance
            }
        except Exception as e:
            print(f"❌ A 股余额查询失败: {e}")
        
        return None
    
    def generate_report(self):
        """生成财务报告"""
        print("=" * 60)
        print("📊 多市场财务核算报告")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print()
        
        # Polymarket（真实账户）
        pm_balance = self.get_polymarket_balance()
        if pm_balance:
            print("💰 Polymarket（真实账户）:")
            print(f"   现金: ${pm_balance['cash']:.2f}")
            print(f"   持仓价值: ${pm_balance['positions_value']:.2f}")
            print(f"   总资产: ${pm_balance['total_value']:.2f}")
            pnl_pct = (pm_balance['pnl'] / pm_balance['starting_balance']) * 100
            print(f"   盈亏: ${pm_balance['pnl']:.2f} ({pnl_pct:+.2f}%)")
        else:
            print("💰 Polymarket: ❌ 数据获取失败")
        print()
        
        # OKX（模拟账户）
        okx_balance = self.get_okx_balance()
        if okx_balance:
            print("🪙 OKX 加密货币（模拟账户）:")
            print(f"   现金: ${okx_balance['cash']:.2f}")
            print(f"   持仓价值: ${okx_balance['positions_value']:.2f}")
            print(f"   总资产: ${okx_balance['total_value']:.2f}")
            pnl_pct = (okx_balance['pnl'] / okx_balance['starting_balance']) * 100
            print(f"   盈亏: ${okx_balance['pnl']:.2f} ({pnl_pct:+.2f}%)")
        else:
            print("🪙 OKX: ❌ 数据获取失败")
        print()
        
        # 美股（模拟账户）
        stock_balance = self.get_stock_balance()
        if stock_balance:
            print("📈 美股（模拟账户）:")
            print(f"   现金: ${stock_balance['cash']:.2f}")
            print(f"   持仓价值: ${stock_balance['positions_value']:.2f}")
            print(f"   总资产: ${stock_balance['total_value']:.2f}")
            pnl_pct = (stock_balance['pnl'] / stock_balance['starting_balance']) * 100
            print(f"   盈亏: ${stock_balance['pnl']:.2f} ({pnl_pct:+.2f}%)")
        else:
            print("📈 美股: ❌ 数据获取失败")
        print()
        
        # A 股（模拟账户）
        cn_balance = self.get_cn_stocks_balance()
        if cn_balance:
            print("📊 A 股（模拟账户）:")
            print(f"   现金: ¥{cn_balance['cash']:.2f}")
            print(f"   持仓价值: ¥{cn_balance['positions_value']:.2f}")
            print(f"   总资产: ¥{cn_balance['total_value']:.2f}")
            pnl_pct = (cn_balance['pnl'] / cn_balance['starting_balance']) * 100
            print(f"   盈亏: ¥{cn_balance['pnl']:.2f} ({pnl_pct:+.2f}%)")
        else:
            print("📊 A 股: ❌ 数据获取失败")
        print()
        
        # 汇总
        print("=" * 60)
        print("📊 资金汇总:")
        
        total_usd = 0
        if pm_balance:
            total_usd += pm_balance['total_value']
            print(f"   Polymarket: ${pm_balance['total_value']:.2f}")
        
        if okx_balance:
            total_usd += okx_balance['total_value']
            print(f"   OKX: ${okx_balance['total_value']:.2f}")
        
        if stock_balance:
            total_usd += stock_balance['total_value']
            print(f"   美股: ${stock_balance['total_value']:.2f}")
        
        if cn_balance:
            # 假设汇率 1 USD = 7.2 CNY
            cn_usd = cn_balance['total_value'] / 7.2
            total_usd += cn_usd
            print(f"   A 股: ¥{cn_balance['total_value']:.2f} (≈ ${cn_usd:.2f})")
        
        print(f"\n   总计（USD）: ${total_usd:.2f}")
        print("=" * 60)

def main():
    report = FinancialReport()
    report.generate_report()

if __name__ == "__main__":
    main()
