#!/usr/bin/env python3
"""
OKX Paper Trader - OKX 模拟交易执行器
职责：执行 OKX 套利信号的模拟交易
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

class OKXPaperTrader:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.db_path = self.data_dir / "okx_paper_trading.db"
        
        # 初始资金
        self.initial_balance = 10000.0
        
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 初始化数据库
        self.init_db()
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [OKX Paper Trader] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"okx_paper_trader_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 账户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY,
                cash REAL NOT NULL,
                starting_balance REAL NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # 交易表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                amount_usd REAL NOT NULL,
                quantity REAL NOT NULL,
                market_id TEXT,
                market_question TEXT,
                strategy TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # 持仓表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin TEXT NOT NULL UNIQUE,
                quantity REAL NOT NULL,
                avg_entry_price REAL NOT NULL,
                total_cost REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # 检查账户是否存在
        cursor.execute("SELECT COUNT(*) FROM account")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO account (id, cash, starting_balance, created_at)
                VALUES (1, ?, ?, ?)
            """, (self.initial_balance, self.initial_balance, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_account(self):
        """获取账户信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT cash, starting_balance FROM account WHERE id = 1")
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return {"cash": row[0], "starting_balance": row[1]}
        return None
    
    def update_cash(self, amount):
        """更新现金余额"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE account SET cash = cash + ? WHERE id = 1", (amount,))
        
        conn.commit()
        conn.close()
    
    def execute_buy(self, signal, current_price):
        """执行买入"""
        coin = signal.get('coin')
        amount_usd = signal.get('position_size', 0.10) * self.initial_balance
        
        # 检查现金余额
        account = self.get_account()
        if account['cash'] < amount_usd:
            self.log(f"❌ 现金不足: 需要 ${amount_usd:.2f}, 可用 ${account['cash']:.2f}")
            return False
        
        # 计算购买数量
        quantity = amount_usd / current_price
        
        # 记录交易
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO trades (coin, side, price, amount_usd, quantity, market_id, market_question, strategy, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            coin,
            'BUY',
            current_price,
            amount_usd,
            quantity,
            signal.get('market_id'),
            signal.get('market_name'),
            signal.get('strategy'),
            datetime.now().isoformat()
        ))
        
        # 更新持仓
        cursor.execute("SELECT quantity, avg_entry_price, total_cost FROM positions WHERE coin = ?", (coin,))
        row = cursor.fetchone()
        
        if row:
            # 更新现有持仓
            old_quantity, old_avg_price, old_cost = row
            new_quantity = old_quantity + quantity
            new_cost = old_cost + amount_usd
            new_avg_price = new_cost / new_quantity
            
            cursor.execute("""
                UPDATE positions 
                SET quantity = ?, avg_entry_price = ?, total_cost = ?, updated_at = ?
                WHERE coin = ?
            """, (new_quantity, new_avg_price, new_cost, datetime.now().isoformat(), coin))
        else:
            # 新建持仓
            cursor.execute("""
                INSERT INTO positions (coin, quantity, avg_entry_price, total_cost, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (coin, quantity, current_price, amount_usd, datetime.now().isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        # 更新现金
        self.update_cash(-amount_usd)
        
        self.log(f"✅ 买入 {coin}: {quantity:.6f} 个 @ ${current_price:,.2f}, 总计 ${amount_usd:.2f}")
        return True
    
    def execute_sell(self, coin, quantity, current_price):
        """执行卖出"""
        # 检查持仓
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT quantity FROM positions WHERE coin = ?", (coin,))
        row = cursor.fetchone()
        
        if not row or row[0] < quantity:
            self.log(f"❌ 持仓不足: {coin}")
            conn.close()
            return False
        
        amount_usd = quantity * current_price
        
        # 记录交易
        cursor.execute("""
            INSERT INTO trades (coin, side, price, amount_usd, quantity, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (coin, 'SELL', current_price, amount_usd, quantity, datetime.now().isoformat()))
        
        # 更新持仓
        cursor.execute("UPDATE positions SET quantity = quantity - ?, updated_at = ? WHERE coin = ?", 
                      (quantity, datetime.now().isoformat(), coin))
        
        # 删除空持仓
        cursor.execute("DELETE FROM positions WHERE quantity <= 0")
        
        conn.commit()
        conn.close()
        
        # 更新现金
        self.update_cash(amount_usd)
        
        self.log(f"✅ 卖出 {coin}: {quantity:.6f} 个 @ ${current_price:,.2f}, 总计 ${amount_usd:.2f}")
        return True
    
    def get_current_price(self, coin):
        """获取当前价格（从 latest_data.json）"""
        data_file = self.data_dir / "latest_data.json"
        
        if not data_file.exists():
            return None
        
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            okx_raw = data.get('okx', {})
            okx_data_list = okx_raw.get('data', [])
            
            for item in okx_data_list:
                if item.get('symbol') == coin:
                    return item.get('spot_price')
            
            return None
        except Exception as e:
            self.log(f"❌ 获取价格失败: {e}")
            return None
    
    def run(self):
        """主流程"""
        self.log("=" * 60)
        self.log("开始 OKX 模拟交易")
        
        # 读取信号
        signals_file = self.data_dir / "okx_arbitrage_signals.json"
        
        if not signals_file.exists():
            self.log("ℹ️ 无 OKX 套利信号")
            return
        
        try:
            with open(signals_file, 'r') as f:
                signals = json.load(f)
        except Exception as e:
            self.log(f"❌ 读取信号失败: {e}")
            return
        
        if not signals:
            self.log("ℹ️ 信号列表为空")
            return
        
        self.log(f"📊 发现 {len(signals)} 个 OKX 套利信号")
        
        # 执行交易
        executed_count = 0
        
        for signal in signals:
            coin = signal.get('coin')
            okx_action = signal.get('okx_action')
            
            # 获取当前价格
            current_price = self.get_current_price(coin)
            
            if not current_price:
                self.log(f"⚠️ 无法获取 {coin} 价格")
                continue
            
            # 执行买入
            if okx_action == 'BUY':
                success = self.execute_buy(signal, current_price)
                if success:
                    executed_count += 1
        
        self.log(f"✅ OKX 模拟交易完成: {executed_count} 笔")
        self.log("=" * 60)

def main():
    trader = OKXPaperTrader()
    trader.run()

if __name__ == "__main__":
    main()
