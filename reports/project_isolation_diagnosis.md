# 项目混淆排查诊断报告

生成时间：2026-05-12  
生成会话：Claude Code（只读诊断 + 最小安全清理）

---

## A. 当前真实项目路径

| 项目 | 主机路径 | 容器路径 |
|---|---|---|
| polymarket_arbitrage（本项目）| `/Users/libo/.hermes/polymarket_arbitrage` | `/opt/data/polymarket_arbitrage` |
| polymarket_okx（独立项目）| `/Users/libo/polymarket_okx` | 无 Docker 映射 |

当前 Claude Code 工作目录：`/Users/libo/.hermes/polymarket_arbitrage`  
Git 状态：非 Git 仓库

---

## B. 是否与 polymarket_okx 混用？

**代码层面：不混用。**  
`polymarket_arbitrage` 内无任何对 `polymarket_okx` 路径的引用（grep 全空）。

**运行层面：两个项目同时在跑，各自独立。**

| 进程 | PID | cwd | 状态 |
|---|---|---|---|
| `mvp_runner.py --duration 900` | 44312 | `/Users/libo/polymarket_okx` | 运行中（polymarket_okx 项目） |
| `monitor_2h.sh` | 7123 | `/Users/libo/.hermes/polymarket_arbitrage` | 运行中（本项目，dry-run 模式） |

**Claude 权限层面：存在跨项目读写授权。**  
全局 `~/.claude/settings.json` 同时 `allow` 了两个项目的 `Read` 和 `Bash` 权限，Claude Code 在任一项目会话内均可操作另一个项目。

---

## C. 是否与 `~/.hermes/polymarket_arbitrage` 混用？

**不混用。** 当前操作目标正是该目录。  
`monitor_2h.sh` 通过 `$ROOT` 动态解析自身路径，实际落在正确目录。

容器路径 hardcode 问题（`/opt/data/polymarket_arbitrage`）属于 FIX_PLAN #1，与混用无关。

---

## D. 日语输出来源排查

经逐一检查，**未发现任何日语触发源**：

- `CLAUDE.md`：全中文，无日语指令
- `polymarket_okx`：无 `CLAUDE.md`，`PROJECT_CONTEXT_V2.md` 全英文
- `~/.claude/settings.json`：无 `language`/locale 设置
- `polymarket_okx/.claude/settings.local.json`：无语言设置
- 两个项目均无 `lang: ja`、`locale: ja` 类配置

**结论**：日语输出为历史会话 system prompt 残留，非配置文件导致。  
**已修复**：本次在 `CLAUDE.md` 顶部写入语言强制规范，后续会话默认读取。

---

## E. 入口混乱风险点

| 风险点 | 文件 | 问题说明 |
|---|---|---|
| 三个 orchestrator | `orchestrator.py` / `orchestrator_advanced.py` / `orchestrator_realtime.py` | 各自调用不同 executor，互不同步（FIX_PLAN P0-pre） |
| 两套 executor | 根目录 `signal_executor.py` + `executors/signal_executor.py` | MD5 不同，改一处不等于改另一处（FIX_PLAN #1） |
| Hardcode Docker 路径 | 大量 `.py` 文件 | `/opt/data/polymarket_arbitrage` 在主机直接运行报错（FIX_PLAN #1） |
| 跨项目 Claude 权限 | `~/.claude/settings.json` | polymarket_okx 权限混入全局，在本项目会话内可误操作另一项目 |
| `trigger_learning_okx_arbitrage.py` | 根目录 | 文件名含 `okx_arbitrage`，路径仍指向本项目，命名易造成误解 |

---

## F. 密钥风险扫描结果

扫描目标：`data/latest_data.json`（181 KB）  
扫描关键词：`api_key / api_secret / secret_key / private_key / access_token / auth_token / bearer / password / credential / token`

**结论：未发现疑似明文密钥字段。**

> 注：`config/llm_config.json` 含明文 xAI key 和 pawmaas key（FIX_PLAN #2），用户已确认本轮不轮换，此次未扫描。

---

## 已执行的最小安全清理

| 操作 | 文件 | 内容 |
|---|---|---|
| 写入语言锁 | `CLAUDE.md` 顶部 | 强制简体中文，禁止日语 |
| 生成本报告 | `reports/project_isolation_diagnosis.md` | 诊断存档 |

---

## 后续建议（按优先级）

### 优先级 P1（低成本，防误操作）

**隔离 Claude 权限**  
将 `~/.claude/settings.json` 里 `polymarket_okx` 相关条目移到 `/Users/libo/polymarket_okx/.claude/settings.json`（目前该文件不存在）。  
操作方式：`/update-config`，不手工改 JSON。

### 优先级 P2（对应 FIX_PLAN P0-pre）

**确认 polymarket_arbitrage 使用哪条 orchestrator 链路**  
当前本项目侧只有 `monitor_2h.sh` 在跑（dry-run）。正式启用前需先完成 P0-pre 入口确认，结果填入 `FIX_PLAN.md` 执行记录区。

### 优先级 P3（对应 FIX_PLAN #1）

**executor 二合一**  
将根目录 `signal_executor.py` / `sell_executor.py` 改为 thin wrapper，内部 `import executors/` 下的版本，消除双副本分叉。

### 优先级 P4（对应 FIX_PLAN #2）

**轮换 `config/llm_config.json` 明文密钥**  
当前用户明确表示本轮不轮换，待决策时机到位再处理。

---

*本报告为只读诊断存档，不作为操作授权依据。*
