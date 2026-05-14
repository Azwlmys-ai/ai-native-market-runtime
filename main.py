#!/usr/bin/env python3
"""
Polymarket Multi-Agent 套利系统主程序
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import Orchestrator

def main():
    parser = argparse.ArgumentParser(description="Polymarket Multi-Agent 套利系统")
    parser.add_argument("--mode", choices=["once", "daemon"], default="once",
                        help="运行模式：once（单次扫描）或 daemon（持续运行）")
    
    args = parser.parse_args()
    
    orchestrator = Orchestrator()
    
    if args.mode == "once":
        orchestrator.run_once()
    else:
        print("Daemon 模式暂未实现")
        sys.exit(1)

if __name__ == "__main__":
    main()
