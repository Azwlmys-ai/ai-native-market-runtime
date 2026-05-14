#!/usr/bin/env python3
"""
A 股模拟交易执行器
职责：执行 A 股套利信号的模拟交易
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

class CNStocksPaperTrader:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.db_path = self.data_dir / "cn_stocks_paper_trading.db"
        
        # 初始资金
        self.initial_balance = 10000.0
        
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 初始化数据库
        self.init_db()
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [CN Stocks Paper Trader] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"cn_stocks_paper_trader_{datetime.now().strftime('%Y%m%d')}.log"
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
                stock_code TEXT NOT NULL,
                stock_name TEXT,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                amount_cny REAL NOT NULL,
                shares INTEGER NOT NULL,
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
                stock_code TEXT NOT NULL UNIQUE,
                stock_name TEXT,
                shares INTEGER NOT NULL,
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
        stock_code = signal.get('stock_code')
        stock_name = signal.get('stock_name')
        amount_cny = signal.get('position_size', 0.08) * self.initial_balance
        
        # 检查现金余额
        account = self.get_account()
        if account['cash'] < amount_cny:
            self.log(f"❌ 现金不足: 需要 ¥{amount_cny:.2f}, 可用 ¥{account['cash']:.2f}")
            return False
        
        # 计算购买股数（A 股最小 100 股，即 1 手）
        shares = int(amount_cny / current_price / 100) * 100
        
        if shares == 0:
            self.log(f"❌ 资金不足购买 1 手 {stock_code}")
            return False
        
        actual_cost = shares * current_price
        
        # 记录交易
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO trades (stock_code, stock_name, side, price, amount_cny, shares, market_id, market_question, strategy, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stock_code,
            stock_name,
            'BUY',
            current_price,
            actual_cost,
            shares,
            signal.get('market_id'),
            signal.get('market_name'),
            signal.get('strategy'),
            datetime.now().isoformat()
        ))
        
        # 更新持仓
        cursor.execute("SELECT shares, avg_entry_price, total_cost FROM positions WHERE stock_code = ?", (stock_code,))
        row = cursor.fetchone()
        
        if row:
            # 更新现有持仓
            old_shares, old_avg_price, old_cost = row
            new_shares = old_shares + shares
            new_cost = old_cost + actual_cost
            new_avg_price = new_cost / new_shares
            
            cursor.execute("""
                UPDATE positions 
                SET shares = ?, avg_entry_price = ?, total_cost = ?, updated_at = ?
                WHERE stock_code = ?
            """, (new_shares, new_avg_price, new_cost, datetime.now().isoformat(), stock_code))
        else:
            # 新建持仓
            cursor.execute("""
                INSERT INTO positions (stock_code, stock_name, shares, avg_entry_price, total_cost, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (stock_code, stock_name, shares, current_price, actual_cost, datetime.now().isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        # 更新现金
        self.update_cash(-actual_cost)
        
        self.log(f"✅ 买入 {stock_code} ({stock_name}): {shares} 股 @ ¥{current_price:.2f}, 总计 ¥{actual_cost:.2f}")
        return True
    
    def get_current_price(self, stock_code):
        """获取当前价格（从 latest_data.json）"""
        data_file = self.data_dir / "latest_data.json"
        
        if not data_file.exists():
            return None
        
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            cn_stocks_data = data.get('cn_stocks', {}).get('data', [])
            
            for stock in cn_stocks_data:
                if stock.get('code') == stock_code:
                    return stock.get('price')
            
            return None
        except Exception as e:
            self.log(f"❌ 获取价格失败: {e}")
            return None
    
    def run(self):
        """主流程"""
        self.log("=" * 60)
        self.log("开始 A 股模拟交易")
        
        # 读取信号
        signals_file = self.data_dir / "cn_stocks_arbitrage_signals.json"
        
        if not signals_file.exists():
            self.log("ℹ️ 无 A 股套利信号")
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
        
        self.log(f"📊 发现 {len(signals)} 个 A 股套利信号")
        
        # 执行交易
        executed_count = 0
        
        for signal in signals:
            stock_code = signal.get('stock_code')
            stock_action = signal.get('stock_action')
            
            # 只执行买入（做空需要融券）
            if stock_action != 'BUY':
                continue
            
            # 获取当前价格
            current_price = self.get_current_price(stock_code)
            
            if not current_price:
                self.log(f"⚠️ 无法获取 {stock_code} 价格")
                continue
            
            # 执行买入
            success = self.execute_buy(signal, current_price)
            if success:
                executed_count += 1
        
        self.log(f"✅ A 股模拟交易完成: {executed_count} 笔")
        self.log("=" * 60)

def main():
    trader = CNStocksPaperTrader()
    trader.run()

if __name__ == "__main__":
    main()
