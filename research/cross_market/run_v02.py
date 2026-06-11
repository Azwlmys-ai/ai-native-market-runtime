#!/usr/bin/env python3
"""Cross Market Research V0.2 — install docs + manual run verification."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from research.cross_market.brief_cron import run_brief
from research.cross_market.health_check import run_health_check
from research.cross_market.paths import (
    REPORTS_ARCHIVE_DIR,
    REPORTS_DIR,
    RESEARCH_ROOT,
    V01_DELIVERABLES,
)

V02_DELIVERABLES = RESEARCH_ROOT / "V0_2_DELIVERABLES.md"
LAUNCHD_DIR = Path(__file__).parent / "launchd"


def _manual_run() -> dict:
    r1 = run_brief("us-cn")
    r2 = run_brief("cn-us")
    health = run_health_check(max_stale_hours=9999)
    return {"us_cn": r1, "cn_us": r2, "health": health}


def _build_deliverables(manual: dict) -> str:
    lines = [
        "# Cross Market Research V0.2 — 交付\n",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        "## 1. 新增/修改文件清单\n",
        "- `research/cross_market/brief_cron.py` — 独立 Research Cron 入口",
        "- `research/cross_market/brief_format.py` — Brief 格式与固定声明",
        "- `research/cross_market/health_check.py` — 健康检查",
        "- `research/cross_market/reports.py` — Research Brief 标题/归档/索引",
        "- `research/cross_market/paths.py` — archive/log/index 路径",
        "- `research/cross_market/run_v02.py` — 本交付脚本",
        "- `scripts/cross_market_brief_cron.sh` — shell 包装",
        "- `scripts/cross_market_brief_health.sh` — 健康检查包装",
        "- `research/cross_market/launchd/com.libo.cross-market-brief-us-cn.plist`",
        "- `research/cross_market/launchd/com.libo.cross-market-brief-cn-us.plist`\n",
        "## 2. launchd 配置说明\n",
        "```bash",
        "# 安装（用户级 LaunchAgents）",
        "cp research/cross_market/launchd/com.libo.cross-market-brief-us-cn.plist ~/Library/LaunchAgents/",
        "cp research/cross_market/launchd/com.libo.cross-market-brief-cn-us.plist ~/Library/LaunchAgents/",
        "launchctl load ~/Library/LaunchAgents/com.libo.cross-market-brief-us-cn.plist",
        "launchctl load ~/Library/LaunchAgents/com.libo.cross-market-brief-cn-us.plist",
        "",
        "# 卸载",
        "launchctl unload ~/Library/LaunchAgents/com.libo.cross-market-brief-us-cn.plist",
        "launchctl unload ~/Library/LaunchAgents/com.libo.cross-market-brief-cn-us.plist",
        "```",
        "- **08:00**（本地/北京时间）→ US Close → CN Open Brief",
        "- **21:30**（本地/北京时间）→ CN Close → US Open Brief",
        "- 使用系统本地时区；请确认 Mac 时区为 Asia/Shanghai\n",
        "## 3. 日报归档路径\n",
        f"`{REPORTS_ARCHIVE_DIR}/`",
        "- 文件名：`us_close_cn_open_YYYYMMDD_HHMMSS.md`",
        "- 文件名：`cn_close_us_open_YYYYMMDD_HHMMSS.md`\n",
        "## 4. latest 报告路径\n",
        f"- `{REPORTS_DIR}/us_close_cn_open_latest.md`",
        f"- `{REPORTS_DIR}/cn_close_us_open_latest.md`\n",
        "## 5. 健康检查命令\n",
        "```bash",
        "./scripts/cross_market_brief_health.sh",
        "# 或",
        "python3 research/cross_market/health_check.py",
        "```\n",
        "## 6. 手动运行\n",
        "```bash",
        "./scripts/cross_market_brief_cron.sh us-cn",
        "./scripts/cross_market_brief_cron.sh cn-us",
        "./scripts/cross_market_brief_cron.sh all",
        "```\n",
        "### 本次手动运行结果\n",
        f"- us-cn: success={manual['us_cn'].get('success')} archive={manual['us_cn'].get('archive_path')}",
        f"- cn-us: success={manual['cn_us'].get('success')} archive={manual['cn_us'].get('archive_path')}",
        f"- health: {manual['health'].get('healthy')} issues={manual['health'].get('issues')}\n",
        "## 7. 确认未触碰交易系统\n",
        "- Cron **不**调用 `main.py` / `orchestrator` / `signal_executor`",
        "- Cron **不**设置 `EXECUTOR_DRY_RUN` 或写入 `data/signals.json`",
        "- 每次运行前后校验 `TRADING_GUARD_PATHS` mtime",
        f"- 本次 touched_trading_paths: {manual['us_cn'].get('touched_trading_paths')} / {manual['cn_us'].get('touched_trading_paths')}\n",
        "---\n*Research Brief only. 完全隔离于交易系统。*\n",
    ]
    return "\n".join(lines)


def main():
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    manual = _manual_run()
    V02_DELIVERABLES.write_text(_build_deliverables(manual), encoding="utf-8")
    print(f"V0.2 deliverables: {V02_DELIVERABLES}")
    print(json.dumps(manual, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
