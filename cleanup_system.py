#!/usr/bin/env python3
"""
系统清理脚本
清理过期、无用、重复的文件，优化系统资源
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta

print("🧹 系统清理脚本")
print("=" * 60)

base_dir = Path("/opt/data/polymarket_arbitrage")
os.chdir(base_dir)

# 清理计数
removed_count = 0
freed_space = 0

# 1. 清理失败的 API 数据文件
print("\n1️⃣ 清理失败的 API 数据文件")
failed_api_files = [
    "data/yahoo_finance_data.json",      # Yahoo Finance 429 限流
    "data/alpha_vantage_data.json",      # Alpha Vantage 额度太少
    "data/iex_data.json",                # IEX Cloud 未注册
    "data/longbridge_data.json"          # 长桥 API 404 错误
]

for file_path in failed_api_files:
    file = base_dir / file_path
    if file.exists():
        size = file.stat().st_size
        file.unlink()
        removed_count += 1
        freed_space += size
        print(f"   ✅ 删除: {file_path} ({size} bytes)")

# 2. 清理备份文件
print("\n2️⃣ 清理备份文件")
backup_files = list(base_dir.rglob("*.bak"))
for file in backup_files:
    size = file.stat().st_size
    file.unlink()
    removed_count += 1
    freed_space += size
    print(f"   ✅ 删除: {file.relative_to(base_dir)} ({size} bytes)")

# 3. 清理失败的采集器
print("\n3️⃣ 清理失败的采集器")
failed_collectors = [
    "collectors/yahoo_finance_collector.py",
    "collectors/alpha_vantage_collector.py",
    "collectors/iex_collector.py",
    "collectors/longbridge_collector.py",
    "collectors/longbridge_collector_sdk.py",
    "collectors/longbridge_collector_rest.py"
]

for file_path in failed_collectors:
    file = base_dir / file_path
    if file.exists():
        size = file.stat().st_size
        file.unlink()
        removed_count += 1
        freed_space += size
        print(f"   ✅ 删除: {file_path} ({size} bytes)")

# 4. 清理过期日志（保留最近 7 天）
print("\n4️⃣ 清理过期日志（保留最近 7 天）")
logs_dir = base_dir / "logs"
if logs_dir.exists():
    cutoff_date = datetime.now() - timedelta(days=7)
    for log_file in logs_dir.glob("*.log"):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        if mtime < cutoff_date:
            size = log_file.stat().st_size
            log_file.unlink()
            removed_count += 1
            freed_space += size
            print(f"   ✅ 删除: {log_file.name} ({size} bytes)")

# 5. 清理重复的文档
print("\n5️⃣ 清理重复和过期的文档")
redundant_docs = [
    "STOCK_API_INTEGRATION_REPORT.md",
    "LONGBRIDGE_API_FAILURE_REPORT.md",
    "FREE_STOCK_API_REGISTRATION_GUIDE.md",
    "FINNHUB_INTEGRATION_SUCCESS.md",
    "setup_longbridge_docker.sh"
]

for file_path in redundant_docs:
    file = base_dir / file_path
    if file.exists():
        size = file.stat().st_size
        file.unlink()
        removed_count += 1
        freed_space += size
        print(f"   ✅ 删除: {file_path} ({size} bytes)")

# 6. 清理配置文件中的失败 API
print("\n6️⃣ 清理配置文件中的失败 API")
config_file = base_dir / "config" / "broker_config.json"
if config_file.exists():
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # 移除失败的 API 配置
    brokers_to_remove = []
    if "brokers" in config:
        for broker in ["iex_cloud", "alpha_vantage"]:
            if broker in config["brokers"] and not config["brokers"][broker].get("enabled"):
                brokers_to_remove.append(broker)
    
    for broker in brokers_to_remove:
        del config["brokers"][broker]
        print(f"   ✅ 移除配置: {broker}")
    
    # 保存清理后的配置
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

# 7. 清理未使用的脚本
print("\n7️⃣ 清理未使用的脚本")
unused_scripts = [
    "scripts/configure_api_keys.py"  # 已手动配置完成
]

for file_path in unused_scripts:
    file = base_dir / file_path
    if file.exists():
        size = file.stat().st_size
        file.unlink()
        removed_count += 1
        freed_space += size
        print(f"   ✅ 删除: {file_path} ({size} bytes)")

# 8. 总结
print("\n" + "=" * 60)
print(f"🎉 清理完成！")
print(f"   删除文件: {removed_count} 个")
print(f"   释放空间: {freed_space:,} bytes ({freed_space/1024:.2f} KB)")
print("=" * 60)
