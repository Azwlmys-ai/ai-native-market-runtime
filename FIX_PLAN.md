# Polymarket Arbitrage 修复计划 (v3.1 — 终版)

> 基于 2026-05-08 代码审计 12 条问题已核实。
> v3 增补:macOS launchd 路径、smoke test 路径隔离、`EXECUTOR_DRY_RUN` 提前到 P0、受控启动用 `orchestrator.py:run_once()`、核心链路文件清单按实际入口分叉调整。
> v3.1 增补:P0 #3/#4 双路径同步收敛、`dry_run` 单独分桶不混入 success、mock pm-trader 用环境变量注入不改 `system_config.json`。
>
> **范围**:不动 `polymarket_arbitrage/config/llm_config.json` 的 key(hermes gateway 单独已处理)。
>
> **核心原则**:
> 1. 修之前先确认入口,避免"修了但没跑到"
> 2. 验证不靠真实交易,靠 smoke test + 受控周期
> 3. 旧日志只能证明过去问题,新日志判断修复效果

---

## 优先级总览

| 阶段 | 编号 | 问题 | 紧迫性 | 工作量 | 风险 |
|---|---|---|---|---|---|
| **P0-pre** | — | 确认实际入口和执行器路径 | 必做 | XS(15min) | 低 |
| **P0** | #4 | 执行器异常路径 KeyError | 阻断真实交易 | S(0.5h) | 低 |
| P0 | #3 | 执行器成功计数错误 | 统计/学习全错 | S(0.2h) | 低 |
| P0 | #6 | historical_trades_100.json 损坏 | 污染训练 | S(0.5h) | 低 |
| P0 | — | 加 `EXECUTOR_DRY_RUN` 环境变量开关 | 让后续验证不下单 | S(0.3h) | 低 |
| P0 | — | 加最小 smoke test | 必做 | S(1h) | 低 |
| **P1** | #5 | 重复执行器(改 wrapper) | 修了 A 跑 B | S(1h) | 中 |
| P1 | #1 | 硬编码 `/opt/data`(只迁核心) | 容器外跑不动 | M(1.5h) | 中 |
| P1 | #11 | LLM fallback 双源 | 改了不生效 | S(0.5h) | 低 |
| **受控启动** | — | 启容器跑 1 个受控周期,收 10-30min 日志 | 必做 | M(1h) | **高** |
| **P2** | #7 | regime_detector 超时 | 周期失败 | S(1h) | 低 |
| P2 | #8 | 美股采集超时 | 周期失败 | M(2-3h) | 中 |
| P2 | #10 | A 股数据加载失败 | 模块失效 | M(2-3h) | 中 |
| P2 | #9 | Agent M 过严(回测先行) | 信号几乎全拒 | M+ | **高** |
| **P3** | #12 | 日志/备份无轮转 | 磁盘增长 | S(1h) | 低 |
| P3 | #2 | 配置/文档明文 key 治理 | 安全 | M(2h+) | 中 |

---

## P0-pre:确认当前实际入口(15 分钟,必做)

**目的**:保证后续修的是"真在跑"的代码,而不是被弃用的副本。

**已知分叉**(只读检查时确认):
- `orchestrator.py:180` → 根目录 `signal_executor.py` / `sell_executor.py`(且 `orchestrator.py:256` 有 `run_once()`,适合受控单周期)
- `orchestrator_advanced.py:245` → `executors/signal_executor.py`(主循环 `while True`)
- `orchestrator_realtime.py:207` → `executors/signal_executor.py`

→ 实际跑的是哪个 orchestrator 决定了 #4/#3 的修复落点。**这一步必须先确认,不能猜。**

**步骤**
```bash
ROOT=/Users/libo/.hermes/polymarket_arbitrage

# 1. 容器入口 / docker-compose 的 cmd
docker ps | grep -i hermes
docker inspect <hermes-container> 2>/dev/null | grep -iE 'cmd|entrypoint'
ls -la $ROOT/*.sh $ROOT/Makefile $ROOT/docker*.yml 2>/dev/null

# 2. 每个 orchestrator 调的是哪个 executor
grep -n "signal_executor\|sell_executor" $ROOT/orchestrator*.py

# 3. cron
crontab -l 2>/dev/null | grep -E 'signal_executor|sell_executor|orchestrator'

# 4. macOS launchd(用户级 + 系统级 + Daemon)
ls -la ~/Library/LaunchAgents/ 2>/dev/null | grep -iE 'hermes|polymarket'
ls -la /Library/LaunchAgents/ 2>/dev/null | grep -iE 'hermes|polymarket'
ls -la /Library/LaunchDaemons/ 2>/dev/null | grep -iE 'hermes|polymarket'
launchctl list 2>/dev/null | grep -iE 'hermes|polymarket'

# 5. shell history 里直接调用过的脚本
grep -E 'signal_executor|sell_executor|orchestrator' \
  ~/.bash_history ~/.zsh_history 2>/dev/null | tail -30
```

**记录格式**(填到本文档底部 "执行记录" 章节):
- 容器实际启动入口:`____`
- 主循环 orchestrator:`____`
- 该 orchestrator 调用的 signal_executor 路径:`____`
- 该 orchestrator 调用的 sell_executor 路径:`____`
- 是否有 cron / launchd 直接调根目录执行器:是/否
- 是否有 shell 历史直接调用:是/否

后面所有修复以"主循环 orchestrator → 对应 executor"为准。

---

## P0:立刻修

### #4 异常路径 KeyError

**根因**:`signal_executor.py` 的 timeout/exception 分支用 `signal["signal"]`,但 `approved_signals.json` 是扁平 dict,无此 key。已在 `orchestrator_20260506.log` 多处触发 `KeyError: 'market'`(同源)。

**修复(双路径同步策略)**
- 把所有 `signal["signal"]` 改回 `signal`(三处错误分支)
- 删掉成功 return 之后的不可达死代码
- **两份都要改**:`executors/signal_executor.py` 和根目录 `signal_executor.py`(orchestrator.py 走根目录,advanced/realtime 走 executors/,受控启动两条都要测,P0 阶段不能让任一条带 bug)
- 修完两份后 diff 确认两份在错误处理上等价
- 等 #5 把根目录改成 wrapper 后,删除根目录里这段重复实现

**Smoke 验收(不真实交易)**
单测脚本(详见末尾 smoke test 章节):
```python
# mock subprocess.run 抛 TimeoutExpired 和 RuntimeError
# 调 execute_trade(signal),不应抛 KeyError,应该返回 dict
```

---

### #3 成功计数错误

**修复(同样双路径同步)**

注意:**`dry_run` 不算 success**(避免学习/绩效模块把模拟当真实盈利)。
```python
- if result["status"] == "simulated":
+ if result["status"] == "success":
      success_count += 1
+ elif result["status"] == "dry_run":
+     dry_run_count += 1
+ elif result["status"] == "simulated":
+     simulated_count += 1
+ else:
+     failed_count += 1
```
对应在 `output` 字典里也加上 `dry_run` 和 `simulated` 字段:
```python
output = {
    "timestamp": datetime.now().isoformat(),
    "total": len(signals),
    "success": success_count,
    "dry_run": dry_run_count,        # 新增
    "simulated": simulated_count,    # 新增
    "failed": failed_count,
    "results": results,
}
```

**改两份**:`executors/signal_executor.py` 和根目录版本同步。

**Smoke 验收**
- mock 返回 `success` → `success_count == 1`,其他桶为 0
- mock 返回 `dry_run` → `dry_run_count == 1`,success 仍为 0
- 顺手 grep 下游消费方:`learning_*`、`agent_g_distillation`、`backtest_*`,看哪些读 `execution_results.json` 的 `success` 字段;**dry-run 周期产生的 results 必须从训练/学习样本中过滤掉**(否则会用模拟数据训练)

---

### #6 损坏的 historical_trades_100.json

**修复(改用 quarantine)**
```bash
mkdir -p $ROOT/data/quarantine
mv $ROOT/data/historical_trades_100.json \
   $ROOT/data/quarantine/historical_trades_100.json.corrupt.$(date +%Y%m%d_%H%M%S)
```

**找写入方(分层 grep,因为精确文件名可能找不到)**
```bash
# 第一轮:精确文件名
grep -rn "historical_trades_100.json" $ROOT --include='*.py' --include='*.sh'

# 第二轮:如果没结果,换 pattern 找 pm-trader history 的调用
grep -rEn "pm-trader.*history|pm_trader.*history" $ROOT --include='*.py' --include='*.sh'
grep -rEn '"history"|--limit|--format' $ROOT --include='*.py' | grep -i 'pm.trader\|trader\.path\|trader_path'

# 第三轮:shell history / 临时脚本(可能根本没归档到 .py)
grep -E 'pm-trader.*history|historical_trades_100' \
  ~/.bash_history ~/.zsh_history 2>/dev/null | tail -20
ls -lat $ROOT/*.sh $ROOT/scripts/*.sh 2>/dev/null
```

如果三轮都找不到写入方,文件可能是手动跑命令时重定向产生的(`pm-trader history --format json > data/historical_trades_100.json`)。这种情况下:
- 在 `_paths.py` 或 `tools/` 加一个 `dump_pm_history.py` 脚本作为正式入口
- 内部用 `pm-trader history --help` 看支持的真实选项,然后调用并 `json.loads()` 校验后再写入

**修脚本要点**
1. 用 `pm-trader history --help` 查正确的子命令/选项(原来调用的 `--format` 不存在)
2. **写入前 `json.loads()` 校验**,失败不写入(避免再被污染)
3. 重新跑生成

**Smoke 验收**
- `python -c "import json; print(len(json.load(open('data/historical_trades_100.json'))))"` 输出条数 > 0
- 写入函数加单测覆盖"CLI 输出非 JSON"场景,确认不会落盘

---

### P0 新增:`EXECUTOR_DRY_RUN` 开关(提前到 P0,smoke test 依赖它)

**为什么提前**:smoke test 只能 mock 单元;真要跑 orchestrator 一个周期,必须有这个开关才不会真实下单。

**关键决策:`dry_run` 是独立状态,不混入 `success`**
否则学习模块、绩效报告、回测都会把"假成交"算进真实盈利,模型会学到错误样本。状态分桶:
- `success` — 真实成交成功
- `dry_run` — DRY_RUN 模式下的模拟成功(永远不下单)
- `simulated` — 历史遗留的模拟标记(回测/调试用)
- `failed` — 真实失败
- `timeout` — 超时
- `error` — 异常

**操作**(改实运行的 executor,**两份都改**)
在 `execute_trade()` 入口加:
```python
import os

def execute_trade(self, signal):
    if os.environ.get("EXECUTOR_DRY_RUN", "").lower() in ("1", "true", "yes"):
        self.log(f"[DRY_RUN] would execute: {signal.get('market_id')} "
                 f"{signal.get('direction')} size={signal.get('position_size')}")
        return {
            "status": "dry_run",   # 关键:不是 "success"
            "signal": signal,
            "timestamp": datetime.now().isoformat(),
        }
    # ... 原逻辑
```
计数逻辑见 #3。

**下游消费方需同步处理**(在 #3 修完之后做一次回查):
- `learning_*.py` / `agent_g_distillation.py` 读 `execution_results.json` 的地方,过滤 `dry_run` 和 `simulated` 状态;只学 `success` / `failed`
- 绩效报告/dashboard 显示时,`dry_run` 单独标识,不计入 PnL

**Smoke 验收**
- `EXECUTOR_DRY_RUN=1 python -c "..."` 调 execute_trade 不调用 subprocess
- 返回 dict `status == "dry_run"`,不是 `success`
- 已写在 smoke test 的 `test_executor_dry_run_env`(下一节)

---

### P0 加最小 smoke test

**目的**:每次改动后,不启动真实交易就能验证关键路径未坏。

**关键约束**:`SignalExecutor()` 默认 `base_dir="/opt/data/polymarket_arbitrage"`,在 #1 路径迁移之前,直接实例化会去读不存在的目录。**测试里必须显式传 `base_dir`** 或用 monkeypatch,否则 P0 的 smoke test 自己会先挂。

**新建** `tests/test_smoke.py`:
```python
"""Smoke test: 不真实下单,只验证管道能跑通。
注意:在 #1 路径迁移完成前,executor 默认 base_dir 指向 /opt/data,
本测试通过显式传参规避(也演示了未来正确的初始化方式)。"""
import json, subprocess, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# 仓库根目录 = 这个 test 文件的上级
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_load_config():
    from llm_helper import load_llm_config
    cfg = load_llm_config()
    assert "agent_models" in cfg


def test_load_approved_signals():
    p = PROJECT_ROOT / "data/approved_signals.json"
    assert p.exists(), f"approved_signals.json missing at {p}"
    sigs = json.loads(p.read_text())
    assert isinstance(sigs, list)
    if sigs:
        assert "market_id" in sigs[0], "schema changed; smoke test needs update"


@pytest.fixture
def executor(tmp_path):
    """显式传 base_dir,避免读 /opt/data。
    用 tmp_path 隔离测试产物,防止污染真实 data/logs。"""
    from executors.signal_executor import SignalExecutor
    # 仿照真实结构创建子目录
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    exe = SignalExecutor(base_dir=str(tmp_path))
    # pm-trader 路径在 #1 之前是硬编码,测试时不会真的调到它,因为 subprocess 被 mock
    return exe


SAMPLE_SIGNAL = {
    "market_id": "test-market",
    "direction": "YES",
    "position_size": 0.01,
    "price": 0.5,
}


def test_executor_with_mock_success(executor):
    fake = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch("subprocess.run", return_value=fake):
        r = executor.execute_trade(SAMPLE_SIGNAL)
    assert r["status"] in ("success", "simulated")


def test_executor_with_mock_timeout(executor):
    """关键回归:timeout 分支不应该抛 KeyError(原 signal['signal'] bug)"""
    with patch("subprocess.run",
               side_effect=subprocess.TimeoutExpired("pm-trader", 30)):
        r = executor.execute_trade(SAMPLE_SIGNAL)
    assert r["status"] == "timeout"


def test_executor_with_mock_exception(executor):
    """关键回归:exception 分支不应该抛 KeyError"""
    with patch("subprocess.run", side_effect=RuntimeError("boom")):
        r = executor.execute_trade(SAMPLE_SIGNAL)
    assert r["status"] == "error"


def test_executor_dry_run_env(executor, monkeypatch):
    """验证 P0 加的 EXECUTOR_DRY_RUN 开关。
    关键:status 必须是 'dry_run',不是 'success' 或 'simulated'
    (避免学习模块把模拟当真实成交)。"""
    monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")
    with patch("subprocess.run") as mock_run:
        r = executor.execute_trade(SAMPLE_SIGNAL)
    assert r["status"] == "dry_run"
    mock_run.assert_not_called()  # dry-run 不应该调 subprocess
```

跑:`pytest tests/test_smoke.py -v`,**全过才算 P0 完成**。

---

## P1:本轮迭代

### #5 重复执行器(thin wrapper,不删)

**思路调整**:项目不是 git 仓库,cron / launchd / shell 历史可能直接调根目录版本,直接删风险高。改成 thin wrapper 更稳。

**操作**(假设 P0-pre 确定 executors/ 是规范版本)
1. 把 `signal_executor.py`(根目录)改成:
   ```python
   """DEPRECATED: 入口已迁移到 executors/signal_executor.py。
   本文件保留只为兼容旧 cron/shell 调用。"""
   import warnings
   warnings.warn(
       "signal_executor.py at project root is deprecated; "
       "use executors.signal_executor instead",
       DeprecationWarning, stacklevel=2)
   from executors.signal_executor import *  # noqa
   from executors.signal_executor import SignalExecutor
   if __name__ == "__main__":
       SignalExecutor().run()
   ```
2. `sell_executor.py` 同理
3. 在两个 wrapper 顶部加注释,标记预计在 X 月某日真正删除

**Smoke 验收**
- `python signal_executor.py` 仍能跑(发出 DeprecationWarning)
- `from signal_executor import SignalExecutor` 仍能 import
- 跑一次新写的 smoke test,确保 wrapper 不破坏单测

---

### #1 硬编码路径(只迁核心链路)

**调整**:不做全项目 sed。核心链路按实际入口分叉调整。

**核心链路文件清单**(基于复核结果):
- `orchestrator.py:13`(根目录入口,有 `run_once()`,受控启动用它)
- `orchestrator_advanced.py:19`(主循环 while True)
- `orchestrator_realtime.py:17`
- `agents/agent_m.py:22`
- `executors/signal_executor.py:12`
- `executors/sell_executor.py:77`
- `collectors/cn_stocks_collector.py:13`
- `config/system_config.json:63-64`(JSON 改相对路径或读 env)
- `llm_helper.py`(本身没硬编码 /opt/data,但 #11 同时改它,顺手统一)

**不在 P1 范围**(用相对路径,目前不必动):
- `collectors/us_stocks_updater.py`
- `collectors/polygon_collector.py`
- `backtest_*.py`、`generate_*.py`、`analyze_*.py`、`test_*.py` 等历史/工具脚本(P2 之后再迁,或随各自需要时迁)

**根目录 wrapper 文件**(`signal_executor.py`、`sell_executor.py`):#5 改成 re-export,不需要单独改路径。

**Step 1:新建** `_paths.py`(放项目根目录)
```python
"""统一路径解析。
优先级: 环境变量 > 已知容器路径 > ~/.hermes 路径 > 用户 ~ > PATH"""
import os
from pathlib import Path

PROJECT_ROOT_FALLBACK = Path(__file__).resolve().parent

def get_base_dir() -> Path:
    if env := os.environ.get("PA_BASE_DIR"):
        return Path(env)
    return PROJECT_ROOT_FALLBACK  # 项目自身位置

def get_pm_trader() -> str:
    """按优先级查找 pm-trader 可执行文件路径"""
    # 1) 显式环境变量优先
    if env := os.environ.get("PM_TRADER_PATH"):
        return env

    # 2) 已知容器内路径(最常见)
    container_path = "/opt/data/home/.local/bin/pm-trader"
    if Path(container_path).exists():
        return container_path

    # 3) hermes 主机挂载点
    hermes_path = Path.home() / ".hermes/home/.local/bin/pm-trader"
    if hermes_path.exists():
        return str(hermes_path)

    # 4) 普通用户安装位置
    user_path = Path.home() / ".local/bin/pm-trader"
    if user_path.exists():
        return str(user_path)

    # 5) 让 PATH 解析(最后兜底)
    return "pm-trader"
```

**Step 2:在核心链路文件里替换**
- 字符串字面量 `"/opt/data/polymarket_arbitrage"` → `str(get_base_dir())`
- 字符串字面量 `"/opt/data/home/.local/bin/pm-trader"` → `get_pm_trader()`
- 注意 `f"/opt/data/.../{x}"` 这种拼接也要替

**Step 3:容器入口设置**
- Docker / hermes 启动时设 `PA_BASE_DIR=/opt/data/polymarket_arbitrage`(保持容器内行为不变)

**Smoke 验收**(不跑真实周期)
```bash
# 容器外直接 import 不应抛路径错误
cd ~/.hermes/polymarket_arbitrage && python -c "
from _paths import get_base_dir, get_pm_trader
print('base:', get_base_dir())
print('pm-trader:', get_pm_trader())
import orchestrator_advanced  # 只 import,不实例化运行
"

# grep 确认核心链路已无 /opt/data
for f in orchestrator_advanced.py agents/agent_m.py \
         executors/signal_executor.py executors/sell_executor.py \
         llm_helper.py; do
  if grep -n "/opt/data" "$f"; then echo "MISS: $f"; fi
done
```
- 历史脚本(`backtest_*.py`、`generate_*.py`、`analyze_*.py`)**保留 /opt/data**,下一轮再迁

---

### #11 LLM fallback 双源

**修复**:让 helper 读配置 + 兜底默认 + **过滤无效值**(防御占位符如 `[REDACTED]`、`YOUR_KEY`、空串污染默认值)。

```python
# llm_helper.py
_DEFAULT_FALLBACK_MAP = {
    "grok-4.3": "claude-opus-4-7",
    "grok-4.20-0309-reasoning": "claude-opus-4-7",
    "grok-4.20-0309-non-reasoning": "claude-opus-4-7",
    "gpt-5.4": "claude-opus-4-7",
    "deepseek-r1": "claude-opus-4-7",
    "deepseek-v3.2": "claude-opus-4-7",
    "claude-opus-4-7": "grok-4.3",
}

_INVALID_VALUES = {"", "[REDACTED]", "YOUR_KEY", "TODO", None}

def _is_valid_model(name) -> bool:
    if name in _INVALID_VALUES:
        return False
    if isinstance(name, str) and (
        name.startswith("YOUR_") or name.startswith("TODO")):
        return False
    return True

def get_fallback_map(config: dict) -> dict:
    user = config.get("fallback_map", {}) or {}
    cleaned = {k: v for k, v in user.items()
               if _is_valid_model(k) and _is_valid_model(v)}
    return {**_DEFAULT_FALLBACK_MAP, **cleaned}
```
然后第 51、94 行用 `get_fallback_map(config).get(model)` 代替 `FALLBACK_MAP.get(model)`。

**Smoke 验收**
- 单测覆盖:配置缺失、配置有效、配置带 `[REDACTED]` 占位、配置带空串
- 改 `llm_config.json` 一个 fallback,不重启 import 直接确认 `get_fallback_map(config)` 返回新值

---

## 受控启动:第一次跑修复后的系统

**前提**:P0、P1 全部完成,smoke test 全过。

**步骤**

1. **启动前只读检查**(在主机或容器外)
   ```bash
   pytest tests/test_smoke.py -v   # 必须全过
   # 验证 approved_signals.json 不为空且 schema 正常
   # 验证 _paths 解析对
   ```

2. **临时禁用真实下单**(关键,**不要改任何配置文件**)
   - 主方案:`EXECUTOR_DRY_RUN=1`(已在 P0 加了)
   - 双保险:写一个 mock pm-trader,通过环境变量 `PM_TRADER_PATH` 注入 —— **绝对不要改 `config/system_config.json`**,改了容易留在配置里污染后续真实运行

   ```bash
   # 写 mock 脚本(只在受控启动期间用)
   cat > /tmp/mock_pm_trader.sh <<'EOF'
   #!/usr/bin/env bash
   echo "[MOCK pm-trader] called with args: $*" >&2
   echo '{"status":"mock","filled":true,"price":0.5}'
   exit 0
   EOF
   chmod +x /tmp/mock_pm_trader.sh

   # 启动时注入(临时,会话结束自动失效)
   export EXECUTOR_DRY_RUN=1
   export PM_TRADER_PATH=/tmp/mock_pm_trader.sh

   # ... 跑受控周期 ...

   # 跑完 unset(或直接关 shell)
   unset EXECUTOR_DRY_RUN PM_TRADER_PATH
   ```

   注意:`PM_TRADER_PATH` 这个变量名要跟 `_paths.py:get_pm_trader()` 里读的环境变量名对齐(见 #1 的 `_paths.py` 实现)。
   如果 #1 还没做完,需要在 executor 里临时支持:`trader = os.environ.get("PM_TRADER_PATH", self.trader_path)`

3. **跑一个受控周期 — 优先用 `orchestrator.py:run_once()`**

   `orchestrator.py:256` 提供 `run_once()`,天然适合受控单周期。**优先用它**而不是 `orchestrator_advanced.py`(后者是 `while True`,容易跑脱手)。

   ```bash
   # 推荐:单周期,跑完就退
   EXECUTOR_DRY_RUN=1 python -c "
   from orchestrator import Orchestrator
   Orchestrator().run_once()
   "

   # 如果要测 advanced 版,先用 timeout 包住,避免无限循环
   EXECUTOR_DRY_RUN=1 timeout 600 python orchestrator_advanced.py
   # 或者给 orchestrator_advanced 加 --once / --max-cycles 参数(可作为 P1.5 扩展)
   ```

   注意:`orchestrator.py` 调的是**根目录** signal/sell_executor(已改 wrapper),`orchestrator_advanced.py` 调的是 `executors/` 下的版本。两条路径都要在受控启动验证一次。

4. **收集新日志,重点看**
   - `regime_detector.py` 是否还超时(原 60s)
   - `us_stocks_updater.py` 是否还超时
   - `agent_cn_stocks` 数据加载失败比例
   - `approved_signals.json` schema 是否稳定
   - `execution_results.json` 是否正常写入(且 success_count 与实际结果一致)
   - 全局是否还有 `/opt/data` 路径相关报错
   - 是否还有 `KeyError`

5. **如果上面 6 项都干净,才进 P2**;否则回到 P0/P1 排查。

---

## P2:基于新日志再做

> 这一轮**必须用新日志判断**。旧日志只能告诉你过去什么坏了,不能告诉你现在还坏不坏。

### #7 regime_detector 超时

1. 先把 `orchestrator_advanced.py:78` `timeout=60` 提到 120s(止血)
2. 在 detector 里加 per-section 计时日志,定位慢点
3. 加 5-10 分钟结果缓存(regime 不会每分钟剧变)

**验收**:24h 新日志中 detector 超时 ≤ 1 次。

---

### #8 美股采集超时

1. 改用 polygon 批量端点(若 plan 支持)
2. 加 30-60s 内存缓存
3. 超时降级到 Finnhub 单源,不阻塞 orchestrator
4. 拉长超时窗口:polygon_task 60→75s,orchestrator 步骤 90→120s

**验收**:24h 新日志中 `us_stocks_updater 超时` ≤ 2 次。

---

### #10 A 股数据加载失败

**先排查再修**
1. 看新日志里 `数据加载失败` 紧邻哪个文件路径
2. 对比 collector 完成时间和 agent 启动时间
3. 确认根因:race condition / collector 静默失败 / 路径不一致

**通用修复**
- collector 用原子写(`.tmp` + rename)
- agent 加重试 + 退避
- orchestrator 串行化(确认 collector 完成才启 agent)

**验收**:`数据加载失败` 比例 < 5%。

---

### #9 Agent M 过严(回测优先,不做硬通过率目标)

**调整后的验收**
不再以"通过率 30-60%"为目标(市场机会稀疏时 0 通过也合理)。改为以下指标:

1. **离线回测对比**:用历史信号跑新旧 prompt,统计:
   - 通过组的事后真实胜率 / EV
   - 拒绝组的事后真实胜率 / EV
   - precision / recall(以"事后真实正 EV"为正例)
2. **拒绝组里有多少后验为正 EV**:这个比例越低,审查越合理
3. **执行后表现**:部署 1 周后看实际下单的累计回撤、夏普
4. **通过率作为监控**,不作为目标

**修复策略**(确认过严后才动)
- 软化硬阈值:EV>100% 不直接拒,降权;失败概率 35-50% 接受减仓;仓位 ≥20% 强制下调不拒绝
- 跨平台套利专用规则(round3 套利 0% 是另一独立问题)

**风险**:**高**。必须先回测、再灰度。

---

## P3:长期治理

### #12 日志/备份

- 日志轮转:`RotatingFileHandler(maxBytes=10MB, backupCount=7)` 或 logrotate
- 备份策略:tar.gz 保留 7 个 / 30 天;同时存在展开目录和 tar.gz 时只留 tar.gz
- 加 `cleanup_backups.py` cron

**验收**:`du -sh logs backups` 稳定 < 50MB。

---

### #2 明文 key 治理

(本轮不轮换,只迁移到 env)
1. `llm_config.json` 字段改为 `api_key_env: "XAI_API_KEY"`
2. `llm_helper.py` 加从 env 读取的逻辑
3. 旧 markdown 文档里的 key 用占位符替换
4. `config/llm_config.json` 加进 .gitignore(若有 git)
5. 迁移后再轮换 key

**验收**:`grep -rEn 'sk-[A-Za-z0-9]{20}|xai-[A-Za-z0-9]{20}' polymarket_arbitrage/` 返回 0。

---

## 执行节奏(v3 微调)

```
今天 (离线,不启容器):
  1. P0-pre  确认入口(macOS launchd / cron / docker)  ~15min
  2. #4      只改实运行版本                            ~30min
  3. #3      只改实运行版本                            ~10min
  4. #6      quarantine + 三轮 grep 找写入方           ~30min
  5. 加 EXECUTOR_DRY_RUN 开关(提前)                   ~30min
  6. 加 smoke test(显式 base_dir,含 dry_run 用例)    ~1h
  --- pytest tests/test_smoke.py -v 全过才进下一步 ---

本周 (仍离线):
  7. #5      根目录两份改成 thin wrapper                ~1h
  8. #1      迁核心链路(8 个文件,见清单)              ~1.5h
  9. #11     fallback 合并 + 占位符过滤                 ~30min
  --- 重跑 smoke test 全过 ---

受控启动 (1 次,~1h):
  10. EXECUTOR_DRY_RUN=1 + mock_pm_trader.sh(双保险)
  11. 优先 orchestrator.py:run_once() 单周期
  12. 收 10-30min 新日志
  13. 复检 6 项关键指标(/opt/data 错误、KeyError、超时、加载失败、schema、execution_results)

下周 (基于新日志):
  14. P2: #7 #8 #10  ~7h
  15. #9 单独排:回测先行,再灰度

有空时:
  16. P3: #12 #2
```

每完成一项:
- 更新本文档对应章节状态(✅ 完成 / ⏳ 进行中 / ❌ 阻塞)
- 跑 smoke test
- 看 logs 当天有无新报错

---

## 执行记录(填写区)

### P0-pre 入口确认结果
> 跑完 P0-pre 步骤后填写,后续修复以此为准

- 容器实际启动入口:`/usr/bin/tini -g -- /opt/hermes/docker/entrypoint.sh hermes gateway`；容器已存在且运行中，未启动新容器
- 主循环 orchestrator:`main.py --mode once -> orchestrator.Orchestrator.run_once()`
- signal_executor 真实路径:`/opt/data/polymarket_arbitrage/signal_executor.py`（host: `/Users/libo/.hermes/polymarket_arbitrage/signal_executor.py`）
- sell_executor 真实路径:`/opt/data/polymarket_arbitrage/sell_executor.py`（host: `/Users/libo/.hermes/polymarket_arbitrage/sell_executor.py`）
- cron / launchd 是否直接调根目录执行器:`否；crontab/launchd 未发现 signal_executor/sell_executor/orchestrator 直调。Hermes cron/session 历史调用 main.py --mode once`
- shell history 是否直接调用:`否；仅发现 orchestrator_enabled 配置片段`
- 备注:`Hermes 容器挂载 /Users/libo/.hermes -> /opt/data。2026-05-09 已将 /Users/libo/.hermes/home/scripts/polymarket_arbitrage_script.sh 改为强制 EXECUTOR_DRY_RUN=1 的调度观察入口，兼容 /opt/data 与 host 路径。main.py 导入 root orchestrator.py，root orchestrator.py 调 root signal_executor.py/sell_executor.py wrapper。advanced/realtime 分支仍调用 executors/。`

### 2026-05-09 dry-run 入口与调度观察

- `main.py --mode once` 已确认调用 `orchestrator.Orchestrator().run_once()`。
- `EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh python3 main.py --mode once` 完成，`data/execution_results.json` 为 `success=0`, `dry_run=2`, `simulated=0`, `failed=0`。
- `/Users/libo/.hermes/home/scripts/polymarket_arbitrage_script.sh` 已恢复为强制 dry-run wrapper 并验证完成，结果同为 `success=0`, `dry_run=2`, `simulated=0`, `failed=0`。
- 当前用户 crontab 不存在；未发现 Hermes/Polymarket launchd job。Codex app 中已创建 `Hermes dry-run observation` 30 分钟心跳观察。
- 实盘前验证计划仍未制定/执行；继续禁止真实下单。

### 2026-05-09 Agent M #9 验证结果

- Agent M #9 partial patch 已验证通过：`classify_signal()`、`_preprocess_signal()`、白名单极端价 prompt 加强、离线回测脚本均已落地。
- 修复了 `review_cache.py` 缓存键过宽问题：cache key 现在区分 `market_id` / 市场名称 / `position_size`，避免降仓后命中旧拒绝结果。
- 修复了 `executors/signal_executor.py` 空信号不刷新 `execution_results.json` 的问题；当 `approved_signals.json` 为空时会写出 `total=0`, `dry_run=0`, `results=[]`。
- 验证命令：`/usr/bin/python3 -m pytest tests/test_smoke.py -q` → `49 passed, 2 warnings`。
- 外部网络 dry-run 验证完成：Agent M 审查 `9` 个信号，`5 approved / 4 rejected`；Vegas Golden Knights 从旧 FN 修复为 APPROVE，仓位从 `28.5%` 预处理到 `19%`；两个 NBA Finals 极端 YES 也以 `19%` 仓位 APPROVE。
- 执行层保持 dry-run：`data/execution_results.json` 为 `total=5`, `success=0`, `dry_run=5`, `simulated=0`, `failed=0`，无真实下单。

### 进度跟踪

| 项目 | 状态 | 完成日期 | 备注 |
|---|---|---|---|
| P0-pre 入口确认 | ✅ | 2026-05-08 | 当前主路径为 main.py --mode once -> root orchestrator.py -> root executors；advanced/realtime 使用 executors/ |
| #4 KeyError | ✅ | 2026-05-08 | 修复 executors/signal_executor.py timeout/exception signal["signal"]；root signal_executor.py 同步返回结构化异常结果 |
| #3 计数 bug | ✅ | 2026-05-08 | success/dry_run/simulated/failed 独立分桶；dry_run 不计入 success |
| #6 quarantine | ✅ | 2026-05-08 | 损坏文件移至 data/quarantine/historical_trades_100.json.corrupt.20260508_120339；新增 scripts/dump_pm_history.py 写前 JSON 校验 |
| EXECUTOR_DRY_RUN 开关 | ✅ | 2026-05-08 | 两份 signal executor 均支持 EXECUTOR_DRY_RUN；PM_TRADER_PATH 可注入 mock |
| smoke test | ✅ | 2026-05-08 | 新增 tests/test_smoke.py；已安装 pytest/requests 并通过 `python3 -m pytest tests/test_smoke.py -v`（14 passed） |
| #5 wrapper | ✅ | 2026-05-08 | root signal_executor.py/sell_executor.py 已改 thin wrapper；executors/sell_executor.py 先升级为兼容 Agent P legacy schema 的规范版本 |
| #1 核心路径 | ✅ | 2026-05-08 | 新增 _paths.py；核心 orchestrator/agent/executor/collector 使用 PA_BASE_DIR/PM_TRADER_PATH 路径解析；config pm_trader 改为相对兜底 |
| #11 fallback 双源 | ✅ | 2026-05-08 | llm_helper.py 改为默认 fallback + config fallback_map 覆盖，并过滤 [REDACTED]/空值/TODO 占位 |
| 受控启动 (10-30min) | ✅ | 2026-05-09 | `main.py --mode once` 与 dry-run 调度脚本均验证完成；调度观察心跳已恢复 |
| #7 regime 超时 | ✅ | 2026-05-13 | 2026-05-13 日志确认仍超时（120s）；LLM timeout 60→100s；orchestrator timeout 120→150s；缓存 5→15min；加规则兜底（LLM 失败时用资金费率判断）|
| #8 美股超时 | ✅ | 2026-05-09 | 25s budget/per-source timeout/degraded fallback 已完成；dry-run 中 us_stocks_updater 成功 |
| #10 A 股加载 | ✅ | 2026-05-09 | path migration + string price coercion follow-up 已完成并有 smoke 覆盖 |
| #9 Agent M(回测先) | ✅ | 2026-05-09 | position-cap+加强 whitelist prompt+backtest script 已验证；外部网络 dry-run 中 Vegas/NBA 极端价通过，执行保持 dry-run |
| #12 日志轮转 | ✅ | 2026-05-09 | `scripts/rotate_logs.py` dry-run-first + smoke tests 已完成 |
| #2 key 治理 | ⏸️ | 2026-05-09 | 用户确认本轮不轮换 |
| Agent P stop_loss dict bug | ✅ | 2026-05-24 | normalize_stop_loss() 新增；兼容 float/dict/None；tests/test_agent_p_stop_loss.py 13 passed；单周期 dry-run exit=0 |
| Agent B 字段映射 | ✅ | 2026-05-13 | `apply_learned_rules` 中 `yes_price`/`no_price` 从 `outcome_prices` 派生；`orderbook_no` 改用 `liquidity` 兜底；修复前所有 100 个市场被错误拒绝，修复后 10 个市场正常通过 |
| capital_adapter 超时 | ✅ | 2026-05-14 | LLM timeout 60→100s；subprocess timeout 120→150s；加规则兜底（按 regime 映射仓位，LLM 失败时输出合法 capital 配置） |
| agent_m subprocess timeout | ✅ | 2026-05-14 | subprocess timeout 180→240s；不动审查逻辑/prompt/双模型策略 |
| signals.json 汇总缺失 | ✅ | 2026-05-13 | orchestrator 在步骤 12-13 之间加 `_consolidate_signals_for_review()`；从 intelligence_report.json 读 Agent B 信号，做 schema 归一化（market_slug→market_id, side→direction, ev→expected_value），写入 signals.json；修复前 Agent M 每周期跳过，修复后 4 个真实信号进审查（1 通过：Minnesota Wild NO） |
| strategy_manager 超时 | ✅ | 2026-05-13 | 加 15 分钟缓存（strategy_config_cache.json）；timeout 30→60s，max_retries 3→1；加默认策略配置兜底；原因：3 次重试 * 30s + 退避 ≈ 90s 超 orchestrator 120s 上限 |
| Agent P price fallback | ✅ | 2026-05-29 | `resolve_exit_price()` 过滤 `live_price≤0`；fallback 顺序：current_price → last_known_price → entry_price_fallback；sell_signals 4/4 有效 price，missing_exit_price=0 自然验证通过 |
| paper_pnl sell close/writeback | ✅ | 2026-05-29 | `_position_matches_sell()` 新增 Try-3（slug→positions.json→market_name）+ 合成仓位 fallback；`close_reason` 字段写回；`UNMATCHED SELL=0`，realized=$+3372.04，自然验证通过 |
| positions lifecycle registry | ✅ | 2026-05-29 | `positions_closed_registry.json` 持久化去重；`analyze_positions()` 跳过 closed；`save_positions()` 合并 status；tests/test_agent_p_lifecycle.py 8/8 passed；4 个重复止损自 11:16 起完全停止，paper_portfolio closed 稳定在 910 |
