# Runbook — 跑出第一批协整候选喂闭环

目标：让 `cointegration` 产出真实候选 → 经 review/execute(dry-run)/postmortem → 喂 `model_effectiveness.by_model` 学习闭环。

闭环链路（PRD §7）：
```
价格历史累积 → cointegration 候选 → to_pipeline_signals(probe) → Agent M 审查
→ executor(dry-run) → postmortem(models_used=cointegration) → model_effectiveness.by_model → rule_weights
```

---

## 0. 前置：为什么现在 0 候选？

协整需要**真实联动**的价格序列。当前 `data/market_price_history.json` 只有少量近似常量快照（多数 flat），无联动结构 → `|corr|` 上不了 0.8（甚至 0.5），模型**正确地**拒绝造边。

诊断（沙箱、不碰线上 `data/`，需 numpy）：
```bash
python3 scripts/bootstrap_cointegration_from_cache.py --stride 24
# 看 “无候选诊断”：|corr| 分布、卡在哪个护栏、top 配对
```

演示探索层端到端（合成共动配对，证明 tier→pipeline 接线正常）：
```bash
python3 scripts/bootstrap_cointegration_from_cache.py --stride 24 --explore --demo
# 期望：n_candidates_exploration=1，tier=exploration，conf≤35，to_pipeline_signals 出 2 条 ps=0.02 probe
```

---

## 1. 真实路径（推荐）：在主机累积真实价格历史

> ⚠ **必须在你自己的终端（Terminal.app / iTerm）跑，不要在 Cursor agent 里跑。**
> agent 的 shell 被强制走代理 `127.0.0.1:61275`，外部行情/数据 API 不可达（实测 bypass 后 DNS 也不解析）；
> 你的终端没有这个代理，网络正常。

### 一键（推荐）
```bash
cd /Users/libo/.hermes/polymarket_arbitrage
bash scripts/run_host_loop.sh                # 无限循环、每 300s 一周期、dry-run、含探索层
# 变体：
PA_LOOP_INTERVAL=600 PA_LOOP_CYCLES=12 bash scripts/run_host_loop.sh   # 12 周期、间隔 600s
PA_COINT_EXPLORE=0 bash scripts/run_host_loop.sh                       # 只要研究层严格候选
```
脚本会自愈 venv（当前 `venv` 指向旧部署路径 `/opt/...` 已失效，会自动重建 + 装 `requirements.txt`），
设好闭环 env 门控（`EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PA_COINT_SIGNALS=1 PA_COINT_EXPLORE=1`），
每周期跑 `orchestrator.run_once` 并打印协整候选概况。**全程 dry-run，绝不真实下单。**

下面 1a–1c / 2 是脚本内部等价的手动分解，便于排障。需在**有网络 + 已配置采集器**的主机执行。

### 1a. 让 orchestrator 正常周期跑，累积真实 PM 价格历史
每周期 `datastore.record_market_prices` 给每市场滚动追加一个 yes/no 价格点（cap 60）。
真实市场**会动**（流动性、新闻、临近结算），积累若干周期后联动结构浮现。
```bash
# 主机，常规 dry-run 周期（不下真实单）
EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 python3 orchestrator.py   # 或既有的周期入口
```

### 1b.（可选）回填真实外部资产价格，启用跨资产协整（PRD §9）
真实 BTC/ETH/SOL 等币价波动大、与 crypto 类 PM 市场天然联动。
确保 `data/asset_price_history.json`（`{symbol:[{ts,price,kind}]}`）由采集器/步骤1.5 持续写入。

### 1c. 每周期末协整自动重算
orchestrator 周期末（`PA_SHADOW_DB=1`，需 numpy）自动跑 `cointegration.compute` →
`data/correlation_signals.json`。`n_candidates>0` 即第一批真实候选到位。
```bash
curl -s localhost:8000/correlation-signals | jq '.n_candidates, .candidates[0]'
```

---

## 2. 把候选喂进交易闭环（dry-run）

```bash
# 研究层严格候选（corr≥0.8）→ 小额 probe 进信号链路
EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PA_COINT_SIGNALS=1 python3 orchestrator.py
```
- `PA_COINT_SIGNALS=1`：`to_pipeline_signals` 把候选转成带真实 `models_used=["cointegration"]` 的小仓位方向性 probe，门控合入信号链路（步骤 12.5）。
- 仍走 Agent M 审查 + 配对原子完整性（步骤 13.5）+ executor **dry-run**（`success` 由 `EXECUTOR_DRY_RUN` 决定，绝不真实下单）。
- 闭环回灌：postmortem 带 `models_used` → `model_effectiveness` 的 `by_model` 尺度按真实模型聚合 → `rule_weights`。

### 2b.（冷启动加速，可选）启用探索层拿弱关联反馈
真实数据初期严格阈值仍可能 0 候选。PRD §6 主张**大量低风险试错**：开探索层产出弱关联低置信 probe，让闭环先转起来攒反馈。
```bash
EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PA_COINT_SIGNALS=1 \
  PA_COINT_EXPLORE=1 python3 orchestrator.py
# 阈值可调：PA_COINT_EXPLORE_CORR=0.5 PA_COINT_EXPLORE_Z=1.5
```
- 探索候选 `tier=exploration`、置信≤35（Agent M 倾向 paper_probe）、probe 仓位 0.02（比研究层 0.05 更小）。
- **半衰期(平稳性)过滤仍生效**——只放松相关/偏离，不放松“价差必须均值回归”。
- 由 `model_effectiveness.by_model` 事后验证：弱关联边若不兑现 → 经 `rule_weights` 降权/淘汰候选。这是 PRD §13「学习哪些 edge 已失效」的设计闭环。

### 2c. Phase 5 纸面强制层（learning → position_size）

`scripts/run_host_loop.sh` **默认已开** `PA_ENFORCE_LEARNING=1`（全程 `EXECUTOR_DRY_RUN=1`）。
关闸：`PA_ENFORCE_LEARNING=0 bash scripts/run_host_loop.sh`。

开闸前只读演练（不写 signals，默认不写 audit）：
```bash
PA_ENFORCE_LEARNING=1 python3 scripts/verify_enforcement_live.py
```

单周期带强制层：
```bash
EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PA_COINT_SIGNALS=1 PA_ENFORCE_LEARNING=1 python3 orchestrator.py
# 默认只降险；floor 0.005 绝不归零探针；硬上限 0.10。详见 PHASE5_ENFORCEMENT.md
```

周期末日志会打印 `[enforce] applied=… net_change=…`；`data/enforcement_audit.json` 记录每条命中。

---

## 2d. Phase 4 Live Probe（已授权，与 dry-run 分离）

**不要**在 `run_host_loop.sh` 里开 live——该脚本恒定 `EXECUTOR_DRY_RUN=1`。

```bash
pm-trader balance   # 确认账户
bash scripts/run_live_probe_loop.sh
# 紧急停机：echo halt > data/STOP_TRADING
```

默认：仅 `paper_probe` / `exploration` / 小仓协整；单笔 ≤$25，每周期 ≤2 笔，日买入 ≤$100；日亏 ≥$50 写 `STOP_TRADING`（新买入停，urgent 止损仍可卖）。详见 `PHASE4_LIVE_PROBE.md`。

---

## 3. 安全边界（始终成立）

- 所有 env 门控**默认关** → 不开 = 行为零回归。
- 真实下单只在去掉 `EXECUTOR_DRY_RUN=1` 且明确授权时发生；本 runbook 全程 dry-run。
- 探索层/强制层**不绕过** Agent M 审查与 executor dry-run；只影响候选生成阈值与 `position_size`。
- 绝不放水阈值去“制造”研究层候选：研究层 corr≥0.8 是诚实门槛；弱关联只走显式 `tier=exploration` 且低置信小额。

---

## 4. 验证产出

```bash
curl -s localhost:8000/correlation-signals | jq '{n:.n_candidates, research:.n_candidates_research, explore:.n_candidates_exploration, explore_on:.explore_enabled}'
curl -s localhost:8000/model-effectiveness?scope=by_model | jq '.'   # 闭环归因终点
```
`by_model` 出现 `cointegration` 行（带胜率/edge兑现/裁定）= 闭环已转起来。
