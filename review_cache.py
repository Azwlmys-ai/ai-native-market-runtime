"""
Agent M 审查缓存管理
用于提高数据一致性和加速重复信号审查
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

class ReviewCache:
    def __init__(self, base_dir="/opt/data/polymarket_arbitrage"):
        self.base_dir = Path(base_dir)
        self.cache_dir = self.base_dir / "data" / "review_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.cache_file = self.cache_dir / "cache.json"
        self.cache_ttl = 24 * 3600  # 24 小时过期
    
    def calculate_signal_hash(self, signal):
        """
        计算信号哈希（忽略 timestamp 和 source）
        只关注核心交易参数
        """
        key_fields = {
            "market_id": signal.get("market_id"),
            "market": signal.get("market") or signal.get("market_name"),
            "direction": signal.get("direction"),
            "price": round(signal.get("price", 0), 4),  # 保留 4 位小数
            "position_size": signal.get("position_size"),
            "amount": signal.get("amount"),
            "reason": signal.get("reason", "")
        }
        json_str = json.dumps(key_fields, sort_keys=True)
        return hashlib.md5(json_str.encode()).hexdigest()
    
    def load_cache(self):
        """加载缓存"""
        if not self.cache_file.exists():
            return {}
        
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def save_cache(self, cache):
        """保存缓存"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  保存缓存失败: {e}")
    
    def get(self, signal):
        """获取缓存结果"""
        signal_hash = self.calculate_signal_hash(signal)
        cache = self.load_cache()
        
        if signal_hash not in cache:
            return None
        
        entry = cache[signal_hash]
        
        # 检查是否过期
        cached_time = datetime.fromisoformat(entry["timestamp"])
        if datetime.now() - cached_time > timedelta(seconds=self.cache_ttl):
            # 过期，删除
            del cache[signal_hash]
            self.save_cache(cache)
            return None
        
        return entry["result"]
    
    def set(self, signal, result):
        """设置缓存"""
        signal_hash = self.calculate_signal_hash(signal)
        cache = self.load_cache()
        
        cache[signal_hash] = {
            "timestamp": datetime.now().isoformat(),
            "signal_hash": signal_hash,
            "result": result
        }
        
        self.save_cache(cache)
    
    def cleanup_expired(self):
        """清理过期缓存"""
        cache = self.load_cache()
        now = datetime.now()
        
        expired_keys = []
        for key, entry in cache.items():
            cached_time = datetime.fromisoformat(entry["timestamp"])
            if now - cached_time > timedelta(seconds=self.cache_ttl):
                expired_keys.append(key)
        
        for key in expired_keys:
            del cache[key]
        
        if expired_keys:
            self.save_cache(cache)
            print(f"🧹 清理 {len(expired_keys)} 个过期缓存")
    
    def clear(self):
        """清空所有缓存"""
        if self.cache_file.exists():
            self.cache_file.unlink()
        print("🧹 缓存已清空")
    
    def stats(self):
        """缓存统计"""
        cache = self.load_cache()
        now = datetime.now()
        
        total = len(cache)
        expired = 0
        
        for entry in cache.values():
            cached_time = datetime.fromisoformat(entry["timestamp"])
            if now - cached_time > timedelta(seconds=self.cache_ttl):
                expired += 1
        
        return {
            "total": total,
            "valid": total - expired,
            "expired": expired
        }
