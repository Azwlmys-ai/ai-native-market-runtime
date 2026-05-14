# CLAUDE.md — Polymarket Arbitrage 项目记忆

> **语言规范（强制）**：所有输出统一使用简体中文；禁止日语；代码注释、报告、总结、终端解释全部使用中文，保留必要英文技术术语。

> 给未来 Claude 会话的项目入门文档。新会话开头读这个文件 + 最新的 `SESSION_STATE_*.md`,就能快速接续工作,不必重新审计。
>
> 修改原则:本文件只放**长期不变**的事实和规约。每次会话的进度/决定写到 `SESSION_STATE_<YYYYMMDD>.md`。

---

## 项目是什么

Polymarket 套利系统:多 agent + LLM 驱动,采集 Polymarket 行情 + 加密 + 美股 + A 股 + 港股 + 大宗商品,生成跨平台套利信号,经 Agent M 风险审查后由 `pm-trader` 执行下单。

主要目录:
- `agents/` — 各路 LLM agent(Agent A/B/D/E/F/G/H/I/J/K/M/P 等)
- `collectors/` — 行情采集(polygon/finnhub/yfinance/sina/tencent/longbridge/okx 等)
- `executors/` — 下单执行(`signal_executor.py`、`sell_executor.py`)
- `config/` — `system_config.json`(系统路径)、`llm_config.json`(LLM 路由)
- `data/` — 信号、审查结果、执行结果、历史数据
- `logs/` — 各 agent 和 orchestrator 的日志(每日一个文件)
- `backups/` — 整系统备份

---

## 关键路径

**这是个 Docker 项目**,容器内路径 ≠ 主机路径:

| 用途 | 容器内 | macOS 主机 |
|---|---|---|
| 项目根 | `/opt/data/polymarket_arbitrage` | `/Users/libo/.hermes/polymarket_arbitrage` |
| pm-trader | `/opt/data/home/.local/bin/pm-trader` | `/Users/libo/.hermes/home/.local/bin/pm-trader` |

代码里大量 hardcode `/opt/data/...`,这是 #1 待修问题。在主机上直接跑会找不到路径(已在 FIX_PLAN.md 里有迁移方案)。

---

## 入口分叉(重要)

**不止一个 orchestrator,且调用的 executor 不一致**(P0-pre 必须确认实际跑的是哪条):

| Orchestrator | 调用的 executor | 模式 |
|---|---|---|
| `orchestrator.py:180` | 根目录 `signal_executor.py` / `sell_executor.py` | 有 `run_once()`,适合受控单周期 |
| `orchestrator_advanced.py:245` | `executors/signal_executor.py` / `executors/sell_executor.py` | `while True` 主循环 |
| `orchestrator_realtime.py:207` | `executors/...` 下版本 | 实时 |

四个执行器文件(根目录 2 个 + executors/ 下 2 个)**MD5 都不同**,功能有差异。**修一处不能假设另一处也修了**。

---

## 配置和 LLM 路由

- 项目用 `polymarket_arbitrage/config/llm_config.json` 路由 LLM(里面有 xAI key + pawmaas 中转 key 的明文,#2 待治理,**用户已确认本轮不轮换**)
- LLM 调用入口:`llm_helper.py`,函数 `call_llm_sync(agent_id, prompt, ...)`
- fallback 逻辑当前**只走代码内 `FALLBACK_MAP`**,`llm_config.json` 里的 `fallback_map` 是死配置(#11 待修)

**注意区分**(这是历史教训):
- `~/.hermes/config.yaml` 和 `~/.hermes/.env` 是 **Hermes Gateway 自己的配置**,跟本项目独立
- 本项目的 LLM 调用**不读** Hermes gateway 的 .env / config.yaml,只读 `polymarket_arbitrage/config/llm_config.json`
- 2026-05-08 把 Hermes gateway 主模型改成 pawmaas/claude-opus-4-7 时,**没动** `polymarket_arbitrage/config/llm_config.json`,这是用户决策

---

## 当前修复状态

参见 [FIX_PLAN.md](./FIX_PLAN.md) v3.1 — 12 条已核实问题、优先级、smoke test、受控启动方案。

下一步入口:**先做 P0-pre 入口确认**,跑完把结果填到 FIX_PLAN.md 底部"执行记录"区,然后才动代码。

---

## 工作纪律(必读,踩过坑总结)

### 不要做
- ❌ **不要直接跑 orchestrator 真实交易循环**做"验证"。要测必须 `EXECUTOR_DRY_RUN=1`,并优先用 `orchestrator.py:run_once()` 单周期
- ❌ **不要为了 mock pm-trader 改 `config/system_config.json`**,会污染长期配置。改用环境变量 `PM_TRADER_PATH=/tmp/mock_pm_trader.sh`,跑完 unset
- ❌ **不要全项目大面积 sed 替换 `/opt/data`**。只迁核心链路(8 个文件,清单在 FIX_PLAN #1)
- ❌ **不要直接删重复执行器**,改 thin wrapper(可能有 cron / launchd / shell 历史调根目录)
- ❌ **不要把 `dry_run` 计入 `success`**。学习/绩效模块会把模拟当真实成交学坏

### 要做
- ✅ 改任何执行器代码,**两份都改**(根目录 + executors/),除非已经做过 wrapper 收敛
- ✅ 每次改完跑 `pytest tests/test_smoke.py -v`,全过才继续
- ✅ 每次会话结束写 `SESSION_STATE_<YYYYMMDD>.md`(沿用项目已有命名)
- ✅ 修复一项 → 更新 FIX_PLAN 底部"进度跟踪"表

### 状态分桶约定(避免污染学习样本)
执行结果 `status` 分 6 桶,**不可混用**:
- `success` — 真实成交成功
- `dry_run` — DRY_RUN 模式模拟,绝不下单
- `simulated` — 历史回测/调试模拟
- `failed` — 真实失败
- `timeout` — 超时
- `error` — 异常

下游学习模块**只学 `success` / `failed`**,必须过滤掉 `dry_run` / `simulated`。

---

## 常用命令

```bash
ROOT=/Users/libo/.hermes/polymarket_arbitrage

# 受控单周期(主推)
EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
  python -c "from orchestrator import Orchestrator; Orchestrator().run_once()"

# Smoke test
pytest "$ROOT/tests/test_smoke.py" -v   # 全过才能继续

# 看核心链路日志
tail -f "$ROOT/logs/orchestrator_advanced_$(date +%Y%m%d).log"

# 跑完受控启动后 unset 环境变量
unset EXECUTOR_DRY_RUN PM_TRADER_PATH
```

---

## 历史会话索引

按时间倒序,看最近的就行:
- `SESSION_STATE_20260508.md` — 审计 12 条问题、定 FIX_PLAN v3.1、Hermes gateway 改 pawmaas
- `SESSION_STATE_20260507_0230.md`
- `SESSION_STATE_20260507.md`
- `SESSION_STATE_20260503.md`(注:有明文 key 痕迹,#2 治理时要清)

---

## 给未来 Claude 的 onboarding 指引

新会话第一步:
1. 读本文件(`CLAUDE.md`)
2. 读最新 `SESSION_STATE_*.md`(看上次到哪里)
3. 读 `FIX_PLAN.md` 的"执行记录"区,看 P0-pre 是否已确认入口
4. 如果用户没明确指令,从 FIX_PLAN 进度跟踪表里挑一项 ⏳ 状态的工作
