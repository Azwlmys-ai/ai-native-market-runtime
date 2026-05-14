#!/usr/bin/env python3
"""
Stock Paper Trader - 美股/港股模拟交易执行器
职责：执行股票套利信号的模拟交易
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

class StockPaperTrader:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.db_path = self.data_dir / "stock_paper_trading.db"
        
        # 初始资金
        self.initial_balance = 10000.0
        
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 初始化数据库
        self.init_db()
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Stock Paper Trader] {message}"
        print(log_msg, flush=True)
        
        log_file = self.logs_dir / f"stock_paper_trader_{datetime.now().strftime('%Y%m%d')}.log"
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
                ticker TEXT NOT NULL,
                company TEXT,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                amount_usd REAL NOT NULL,
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
                ticker TEXT NOT NULL UNIQUE,
                company TEXT,
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
        ticker = signal.get('ticker')
        company = signal.get('company')
        amount_usd = signal.get('position_size', 0.08) * self.initial_balance
        
        # 检查现金余额
        account = self.get_account()
        if account['cash'] < amount_usd:
            self.log(f"❌ 现金不足: 需要 ${amount_usd:.2f}, 可用 ${account['cash']:.2f}")
            return False
        
        # 计算购买股数（整数）
        shares = int(amount_usd / current_price)
        
        if shares == 0:
            self.log(f"❌ 资金不足购买 1 股 {ticker}")
            return False
        
        actual_cost = shares * current_price
        
        # 记录交易
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO trades (ticker, company, side, price, amount_usd, shares, market_id, market_question, strategy, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker,
            company,
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
        cursor.execute("SELECT shares, avg_entry_price, total_cost FROM positions WHERE ticker = ?", (ticker,))
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
                WHERE ticker = ?
            """, (new_shares, new_avg_price, new_cost, datetime.now().isoformat(), ticker))
        else:
            # 新建持仓
            cursor.execute("""
                INSERT INTO positions (ticker, company, shares, avg_entry_price, total_cost, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ticker, company, shares, current_price, actual_cost, datetime.now().isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        # 更新现金
        self.update_cash(-actual_cost)
        
        self.log(f"✅ 买入 {ticker} ({company}): {shares} 股 @ ${current_price:.2f}, 总计 ${actual_cost:.2f}")
        return True
    
    def execute_sell(self, ticker, shares, current_price):
        """执行卖出"""
        # 检查持仓
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT shares, company FROM positions WHERE ticker = ?", (ticker,))
        row = cursor.fetchone()
        
        if not row or row[0] < shares:
            self.log(f"❌ 持仓不足: {ticker}")
            conn.close()
            return False
        
        company = row[1]
        amount_usd = shares * current_price
        
        # 记录交易
        cursor.execute("""
            INSERT INTO trades (ticker, company, side, price, amount_usd, shares, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (ticker, company, 'SELL', current_price, amount_usd, shares, datetime.now().isoformat()))
        
        # 更新持仓
        cursor.execute("UPDATE positions SET shares = shares - ?, updated_at = ? WHERE ticker = ?", 
                      (shares, datetime.now().isoformat(), ticker))
        
        # 删除空持仓
        cursor.execute("DELETE FROM positions WHERE shares <= 0")
        
        conn.commit()
        conn.close()
        
        # 更新现金
        self.update_cash(amount_usd)
        
        self.log(f"✅ 卖出 {ticker} ({company}): {shares} 股 @ ${current_price:.2f}, 总计 ${amount_usd:.2f}")
        return True
    
    def get_current_price(self, ticker):
        """获取当前价格（从 latest_data.json）"""
        data_file = self.data_dir / "latest_data.json"
        
        if not data_file.exists():
            return None
        
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            us_stocks = data.get('us_stocks', {})
            stock_data = us_stocks.get(ticker, {})
            
            return stock_data.get('price')
        except Exception as e:
            self.log(f"❌ 获取价格失败: {e}")
            return None
    
    def run(self):
        """主流程"""
        self.log("=" * 60)
        self.log("开始美股/港股模拟交易")
        
        # 读取信号
        signals_file = self.data_dir / "stock_arbitrage_signals.json"
        
        if not signals_file.exists():
            self.log("ℹ️ 无股票套利信号")
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
        
        self.log(f"📊 发现 {len(signals)} 个股票套利信号")
        
        # 执行交易
        executed_count = 0
        
        for signal in signals:
            ticker = signal.get('ticker')
            stock_action = signal.get('stock_action')
            
            # 获取当前价格
            current_price = self.get_current_price(ticker)
            
            if not current_price:
                self.log(f"⚠️ 无法获取 {ticker} 价格")
                continue
            
            # 执行买入
            if stock_action == 'BUY':
                success = self.execute_buy(signal, current_price)
                if success:
                    executed_count += 1
            # 卖出需要单独处理（做空）
            elif stock_action == 'SELL':
                self.log(f"⚠️ 做空 {ticker} 需要融券，暂不支持")
        
        self.log(f"✅ 股票模拟交易完成: {executed_count} 笔")
        self.log("=" * 60)

def main():
    trader = StockPaperTrader()
    trader.run()

if __name__ == "__main__":
    main()
