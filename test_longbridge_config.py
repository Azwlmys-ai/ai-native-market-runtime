#!/usr/bin/env python3
"""
测试长桥 SDK Config 初始化
"""

from longbridge.openapi import Config
import os

# 设置环境变量
os.environ['LONGBRIDGE_APP_KEY'] = '175ae71ba8fe412c5a057809485bd2f9'
os.environ['LONGBRIDGE_APP_SECRET'] = '6a58ef6c47fa9a70d3103aaa859ea70f3b8bff204d03c0a7a3ccb8f29e86273b'
os.environ['LONGBRIDGE_ACCESS_TOKEN'] = '***'

try:
    config = Config.from_env()
    print("✅ Config 创建成功")
    print(f"App Key: {config.app_key[:10]}...")
except Exception as e:
    print(f"❌ 失败: {e}")
    print(f"错误类型: {type(e)}")
