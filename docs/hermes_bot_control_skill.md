# Hermes Bot Control Skill

Project-local copy of the Polymarket control skill instructions. Any future
changes to this project's bot/control behavior should be made here first, inside
the project directory.

## Scope

Use these instructions when Telegram/Hermes asks about:

- System status: `系统状态`, `status`, `怎么样了`, `运行情况`
- Health: `health`, `健康检查`, `告警`
- Metrics: `metrics`, `执行了多少`, `成交`
- Agent status: `agents`, `agent 状态`, `进程状态`
- One-shot dry-run: `run once`, `跑一次`, `执行一次`, `单次扫描`, `干跑`
- Run diagnostics: `诊断卡死`, `卡在哪`, `run-status`, `运行进度`
- Sell feasibility: `能不能自己执行`, `自动卖出`, `止损执行`, `卖出计划`, `sell-plan`
- Research hypotheses: `假设`, `研究`, `hypothesis`, `当前判断`, `失败条件`
- Postmortems / failures: `复盘`, `失败原因`, `亏在哪`, `postmortem`, `教训`
- Mobile research snapshot: `报告`, `研究快照`, `HTML`, `report`, `手机报告`

## Required Command Path

All control commands must run from this project directory:

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
venv/bin/python3 scripts/local_gateway_control.py <command> --telegram
```

## Command Mapping

| User intent | Allowed command |
| --- | --- |
| View system status | `venv/bin/python3 scripts/local_gateway_control.py status --telegram` |
| View health | `venv/bin/python3 scripts/local_gateway_control.py health --telegram` |
| View metrics | `venv/bin/python3 scripts/local_gateway_control.py metrics --telegram` |
| View agents | `venv/bin/python3 scripts/local_gateway_control.py agents --telegram` |
| Trigger one dry-run cycle | `venv/bin/python3 scripts/local_gateway_control.py run-once --dry-run --telegram` |
| View run progress / diagnose stuck run | `venv/bin/python3 scripts/local_gateway_control.py run-status --telegram` |
| View sell feasibility | `venv/bin/python3 scripts/local_gateway_control.py sell-plan --telegram` |
| View research hypotheses | `venv/bin/python3 scripts/local_gateway_control.py hypotheses --telegram` |
| View postmortems / failures | `venv/bin/python3 scripts/local_gateway_control.py postmortems --telegram` |
| Generate mobile HTML snapshot | `venv/bin/python3 scripts/local_gateway_control.py report --telegram` |

## Hard Safety Rules

1. `run-once` must include `--dry-run`.
2. Do not start live trading from Telegram/Hermes.
3. Do not call `pm-trader` directly from the bot.
4. Do not read raw `data/*.json` or raw logs for Telegram replies.
5. Only forward output from `local_gateway_control.py --telegram`.
6. If the user asks to restart the system, run `run-once --dry-run --telegram`.
7. If the user asks whether it can execute or sell by itself, run
   `sell-plan --telegram`; this is read-only and must not place orders.

## Status Interpretation

- `agent_m 执行成功` only means the process exited successfully. It does not
  mean Agent M approved any signals.
- Approval must be read from `status` or `metrics` fields:
  `审查通过:<n> 试错:<n> 拒绝:<n> 待执行:<n>`.
- Agent M is now **three-tier** (Phase 3d): `审查通过`(approve, normal paper) /
  `试错`(paper_probe, small probe ×0.25) / `拒绝`(reject). **Both approve and 试错
  are executed** (as dry_run paper) and count toward `待执行`. So `审查通过:0 试错:5`
  means 5 small probes are pending — NOT "nothing approved".
- Only say there were no actionable signals when **both** `审查通过:0` AND `试错:0`
  AND execution `total:0`; do not guess dedupe, cooldown, duplicate position, or
  executor failure.
- All `试错`(paper_probe) execution is `dry_run` paper — it never places a real order.
- If sell execution shows `dry:<n>`, no real sell order was placed.
- `postmortems` counts are **deduped by `postmortem_uid`** (the jsonl is append-only and
  accumulates multiple versions per trade), so `盈/亏/平` reflect canonical closed trades,
  not raw line count. Each entry may carry a **Phase 3c-2 failure-condition verdict** chip:
  `假设证伪`(refuted = predicted failure actually happened), `假设成立`(confirmed),
  `亏损·预测外`(loss_unexplained = lost but not for the predicted reason — high-value signal),
  `无定论`(inconclusive). Header shows `对照 证伪:<n> 预测外:<n>` when present.
- `report` prints a path under `data/reports/research_*.html` and a short Chinese
  summary (`评级 通过/试错/拒绝`, `复盘 盈/亏`). Send that file as a Telegram document;
  the HTML is self-contained (offline, no server). Display labels in bot/HTML are
  Chinese: 通过 / 试错 / 拒绝, 盈 / 亏 / 平, 原生 / 派生.

## Output

For Telegram, send the command output as-is. Do not rewrite it into a long
report; the command output is already capped for Telegram.
