"""
model_effectiveness — 模型/规则有效性聚合器（Phase 3e：Learning Runtime 第一块）
============================================================================
定位
----
PRD 第十三节「learning agent 新职责」要求学习：哪个模型有效 / 哪个市场关联有效 /
哪些 edge 已失效。本模块是其中**模型(=策略规则)有效性**的确定性聚合底座：
把【已平仓复盘 postmortems】按产生信号的「模型标签」分组，算出每个模型的
胜率 / 盈亏 / edge 兑现 / 假设裁定分布 / 问题归因率 / 失效(decay)信号。

模型标签从哪来（当前真实可用的归因）
----------------------------------
当前信号并无 PRD §8 的结构化 `models_used`（量化模型协整/HMM/GARCH 等尚未实现），
真实可用的「模型/策略标签」是信号上的：
  * learned_rule_match —— 规则匹配命中的具体规则（如 `mid_range_GTA_VI`），即 de-facto 策略
  * source            —— 产生信号的 agent（如 `agent_b`）
本模块经 signal_uid 把 postmortem join 回 signals(影子表) 取这两个字段，
并派生三个聚合尺度：
  * by_rule    —— 完整 learned_rule_match（最细，"这条规则有效吗"）
  * by_family  —— 规则族（去掉市场类型后缀，如 `mid_range`，"这类策略有效吗"）
  * by_agent   —— 产生信号的 agent（"哪个研究 agent 的信号有效"）
未来接入真正的 models_used 后，只需把标签来源从 learned_rule_match 换/并成 models_used，
聚合骨架不变。

设计纪律（与 postmortem/hypothesis 一致）
----------------------------------------
* 纯确定性：无 LLM、无随机，沙箱可复现。
* 加法产物：不改审批/执行/学习的任何行为；只新增分析产物。
* JSON 事实源 data/model_effectiveness.json + 影子表 model_effectiveness（PA_SHADOW_DB 时）。
* dry_run/simulated 不污染：postmortems 只来自真实已平仓 paper 持仓的复盘，
  本模块只读 postmortems，天然不碰 dry_run 执行结果。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from runtime import datastore as _ds

SCHEMA_VERSION = "0.3.4-phase3e"

# 样本阈值：低于此判 insufficient，不下「有效/无效」结论（避免小样本噪声学坏）。
MIN_SAMPLES = 3
# decay 检测：近半窗胜率较早半窗下滑超过该阈值且总样本够，才标 edge_decayed。
DECAY_WINRATE_DROP = 0.20
DECAY_MIN_SAMPLES = 6


# ---------------------------------------------------------------------------
# 输入装载：postmortems + 模型标签归因
# ---------------------------------------------------------------------------

def _f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_from_shadow() -> Optional[list]:
    """影子库路径：postmortems LEFT JOIN signals 取 learned_rule_match/source。
    PA_SHADOW_DB 未开或库不可用时返回 None，由调用方回退 jsonl。"""
    if os.environ.get("PA_SHADOW_DB", "").lower() not in ("1", "true", "yes"):
        return None
    try:
        from runtime import _shadow
        rows = _shadow._rows(  # noqa: SLF001  内部读，复用其 _conn/_rows
            """SELECT m.*, s.learned_rule_match AS sig_rule, s.source AS sig_source,
                      s.models_used AS sig_models
               FROM postmortems m
               LEFT JOIN signals s ON s.signal_uid = m.signal_uid"""
        )
        return rows
    except Exception as exc:  # noqa: BLE001
        print(f"[model_effectiveness] 影子库读取失败，回退 jsonl: {exc}", flush=True)
        return None


def _load_from_jsonl(base_dir: Optional[Path]) -> list:
    """事实源回退路径：读 data/postmortems.jsonl。
    无影子库时拿不到 learned_rule_match，归因降级为 hypothesis_source + 市场类型解析。"""
    base = Path(base_dir) if base_dir else _ds.get_base_dir()
    p = base / "data" / "postmortems.jsonl"
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            rec["sig_rule"] = None
            rec["sig_source"] = rec.get("hypothesis_source") or rec.get("source")
            out.append(rec)
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# 模型标签派生
# ---------------------------------------------------------------------------

def _rule_family(rule: str) -> str:
    """从完整规则名派生规则族：保留前导小写段，去掉尾部大写的市场类型 token。
    例：mid_range_GTA_VI -> mid_range；mid_range_NHL -> mid_range。
    无法切分时原样返回。"""
    parts = rule.split("_")
    head = []
    for seg in parts:
        if seg and seg.islower():
            head.append(seg)
        else:
            break
    return "_".join(head) if head else rule


def _market_type_from_name(name: str) -> Optional[str]:
    """jsonl 降级路径下，从市场名粗略推断市场类型，作为最后兜底标签。"""
    if not name:
        return None
    low = name.lower()
    table = {
        "nhl": "NHL", "nba": "NBA", "stanley cup": "NHL", "bitcoin": "BTC",
        "gta": "GTA_VI", "ethereum": "ETH", "election": "ELECTION",
    }
    for k, v in table.items():
        if k in low:
            return v
    return None


def _unwrap(v) -> Optional[str]:
    """signals 影子表里 learned_rule_match 经 _j() 存成 json 文本（如 '"mid_range_GTA_VI"'），
    读回需去掉外层引号。对裸字符串/None 安全 no-op。"""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            d = json.loads(s)
            if isinstance(d, str):
                return d.strip() or None
        except Exception:
            pass
    return s


def _parse_models(rec: dict) -> list:
    """解析 signals.models_used（Phase 3f-loop：真实模型标签）。
    影子表存 _j(list) → JSON 数组文本（如 '["cointegration"]'）；裸字符串也兼容。
    无则返回 []（该笔无真实模型归因，by_model 不计）。"""
    raw = rec.get("sig_models")
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        s = str(raw).strip()
        if not s:
            return []
        try:
            d = json.loads(s)
            items = d if isinstance(d, list) else [d]
        except Exception:
            items = [s]
    return [str(x).strip() for x in items if str(x).strip()]


def _labels(rec: dict) -> dict:
    """从一条 postmortem(已附 sig_rule/sig_source) 派生三尺度模型标签。"""
    rule = _unwrap(rec.get("sig_rule"))
    agent = _unwrap(rec.get("sig_source"))
    if rule:
        family = _rule_family(rule)
    else:
        # 降级：无规则名时，用市场类型当 rule 兜底，family 同值
        mt = _market_type_from_name(rec.get("market_name") or "")
        rule = f"mkt:{mt}" if mt else "unknown"
        family = rule
    return {"rule": rule, "family": family, "agent": agent or "unknown"}


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------

def _realized_return(rec: dict) -> Optional[float]:
    """方向感知的**无量纲**已实现收益率（Fix2）。
    postmortem 的 entry/exit 是市场（yes）价：
      YES → (exit-entry)/entry；NO → 取反（yes 价跌时 NO 盈利）。
    缺价或 entry<=0 时返回 None。与 cointegration 的 expected_value（预期收益率）同量纲。"""
    en = _f(rec.get("entry_price"))
    ex = _f(rec.get("exit_price"))
    if en is None or ex is None or en <= 0:
        return None
    base = (ex - en) / en
    direction = str(rec.get("direction") or "").upper()
    return -base if direction == "NO" else base


def _blank_acc() -> dict:
    return {
        "n_trades": 0, "n_win": 0, "n_loss": 0, "n_flat": 0,
        "total_realized_pnl": 0.0, "sum_expected_edge": 0.0, "n_expected_edge": 0,
        "sum_realized_return": 0.0, "n_realized_return": 0,
        "sum_confidence": 0.0, "n_confidence": 0,
        "liquidity_issues": 0, "timing_issues": 0, "model_issues": 0,
        "verdicts": {}, "_ordered": [],  # _ordered: [(closed_at, outcome)] 供 decay 检测
    }


def _accumulate(acc: dict, rec: dict) -> None:
    acc["n_trades"] += 1
    outcome = rec.get("outcome") or "flat"
    if outcome == "win":
        acc["n_win"] += 1
    elif outcome == "loss":
        acc["n_loss"] += 1
    else:
        acc["n_flat"] += 1

    pnl = _f(rec.get("realized_pnl"))
    if pnl is not None:
        acc["total_realized_pnl"] += pnl
    ee = _f(rec.get("expected_edge"))
    if ee is not None:
        acc["sum_expected_edge"] += ee
        acc["n_expected_edge"] += 1
    rr = _realized_return(rec)
    if rr is not None:
        acc["sum_realized_return"] += rr
        acc["n_realized_return"] += 1
    cf = _f(rec.get("confidence"))
    if cf is not None:
        acc["sum_confidence"] += cf
        acc["n_confidence"] += 1

    if rec.get("liquidity_issue"):
        acc["liquidity_issues"] += 1
    if rec.get("timing_issue"):
        acc["timing_issues"] += 1
    if rec.get("model_issue"):
        acc["model_issues"] += 1

    v = rec.get("hypothesis_verdict") or "no_prediction"
    acc["verdicts"][v] = acc["verdicts"].get(v, 0) + 1
    acc["_ordered"].append((rec.get("closed_at") or "", outcome))


def _round(x: Optional[float], n: int = 4) -> Optional[float]:
    return None if x is None else round(x, n)


def _decay_signal(ordered: list) -> dict:
    """按 closed_at 排序后，比较近半窗 vs 早半窗已决出胜负交易的胜率。
    近窗显著下滑 → edge_decayed=True（提示该规则的边可能已失效）。"""
    decided = [(t, o) for (t, o) in sorted(ordered, key=lambda x: x[0]) if o in ("win", "loss")]
    if len(decided) < DECAY_MIN_SAMPLES:
        return {"edge_decayed": False, "reason": "样本不足", "early_win_rate": None, "recent_win_rate": None}
    mid = len(decided) // 2
    early = decided[:mid]
    recent = decided[mid:]
    ewr = sum(1 for _, o in early if o == "win") / len(early)
    rwr = sum(1 for _, o in recent if o == "win") / len(recent)
    decayed = (ewr - rwr) >= DECAY_WINRATE_DROP
    return {
        "edge_decayed": bool(decayed),
        "reason": "近窗胜率显著下滑" if decayed else "无显著下滑",
        "early_win_rate": _round(ewr), "recent_win_rate": _round(rwr),
    }


def _finalize(key: str, acc: dict) -> dict:
    n = acc["n_trades"]
    decided = acc["n_win"] + acc["n_loss"]
    win_rate = (acc["n_win"] / decided) if decided else None
    avg_pnl = (acc["total_realized_pnl"] / n) if n else None
    avg_edge = (acc["sum_expected_edge"] / acc["n_expected_edge"]) if acc["n_expected_edge"] else None
    avg_ret = (acc["sum_realized_return"] / acc["n_realized_return"]) if acc["n_realized_return"] else None
    avg_conf = (acc["sum_confidence"] / acc["n_confidence"]) if acc["n_confidence"] else None
    # edge 兑现（Fix2）：**无量纲** 已实现收益率均值 / 预期收益率均值（>1 超预期，<0 反向）。
    # 两侧同量纲（收益率），避免旧版「美元盈亏 ÷ 价差单位」的口径错配。
    edge_realization = None
    if avg_edge not in (None, 0) and avg_ret is not None:
        edge_realization = avg_ret / avg_edge

    decay = _decay_signal(acc["_ordered"])
    verdict = _effectiveness_verdict(n, decided, win_rate, acc["total_realized_pnl"], decay)

    return {
        "key": key,
        "n_trades": n,
        "n_win": acc["n_win"], "n_loss": acc["n_loss"], "n_flat": acc["n_flat"],
        "win_rate": _round(win_rate),
        "total_realized_pnl": _round(acc["total_realized_pnl"]),
        "avg_realized_pnl": _round(avg_pnl),
        "avg_realized_return": _round(avg_ret),
        "avg_expected_edge": _round(avg_edge),
        "avg_confidence": _round(avg_conf),
        "edge_realization": _round(edge_realization),
        "liquidity_issue_rate": _round(acc["liquidity_issues"] / n) if n else None,
        "timing_issue_rate": _round(acc["timing_issues"] / n) if n else None,
        "model_issue_rate": _round(acc["model_issues"] / n) if n else None,
        "verdict_distribution": acc["verdicts"],
        "decay": decay,
        "effectiveness": verdict,
    }


def _effectiveness_verdict(n: int, decided: int, win_rate: Optional[float],
                           total_pnl: float, decay: dict) -> str:
    """确定性有效性裁定（硬规则，可解释）：
      insufficient  —— 样本 < MIN_SAMPLES，不下结论
      inconclusive  —— 有样本但全 flat（无胜负决出）
      decayed       —— 近窗胜率显著下滑（边可能已失效）
      effective     —— 胜率>=0.55 且 总盈亏>0
      ineffective   —— 胜率<=0.35 或 总盈亏<0
      marginal      —— 其余
    """
    if n < MIN_SAMPLES:
        return "insufficient"
    if decided == 0:
        return "inconclusive"
    if decay.get("edge_decayed"):
        return "decayed"
    if win_rate is not None and win_rate >= 0.55 and total_pnl > 0:
        return "effective"
    if (win_rate is not None and win_rate <= 0.35) or total_pnl < 0:
        return "ineffective"
    return "marginal"


def _aggregate_scope(records: list, label_key: str) -> list:
    buckets: dict = {}
    for rec in records:
        key = _labels(rec)[label_key]
        buckets.setdefault(key, _blank_acc())
        _accumulate(buckets[key], rec)
    out = [_finalize(k, acc) for k, acc in buckets.items()]
    # 排序：样本多者在前，其次按总盈亏降序，便于人/agent 取头部
    out.sort(key=lambda e: (e["n_trades"], e["total_realized_pnl"] or 0), reverse=True)
    return out


def _aggregate_by_model(records: list) -> list:
    """按真实模型标签（signals.models_used）聚合——「真实模型」尺度。
    一笔可用多个模型 → 计入每个模型桶。无 models_used 的笔不计（这是 by_rule 的范畴）。
    这是 Phase 3f-loop 闭环的归因终点：协整等真实模型在此被学习。"""
    buckets: dict = {}
    for rec in records:
        for model in _parse_models(rec):
            buckets.setdefault(model, _blank_acc())
            _accumulate(buckets[model], rec)
    out = [_finalize(k, acc) for k, acc in buckets.items()]
    out.sort(key=lambda e: (e["n_trades"], e["total_realized_pnl"] or 0), reverse=True)
    return out


# ---------------------------------------------------------------------------
# 顶层入口
# ---------------------------------------------------------------------------

def compute(base_dir=None) -> dict:
    """聚合所有 postmortems，产出模型有效性报告并落盘（JSON 事实源 + 影子表）。

    返回报告 dict。best-effort：分析产物，任何子步骤失败都不应中断主流程
    （由 datastore 门面的 shadow 写做兜底，本函数只在装载层吞异常）。
    """
    rows = _load_from_shadow()
    attribution = "shadow_join_signals"
    if rows is None:
        rows = _load_from_jsonl(base_dir)
        attribution = "jsonl_degraded"

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution_source": attribution,
        "n_postmortems": len(rows),
        "by_model": _aggregate_by_model(rows),     # Phase 3f-loop：真实模型标签（models_used）
        "by_rule": _aggregate_scope(rows, "rule"),
        "by_family": _aggregate_scope(rows, "family"),
        "by_agent": _aggregate_scope(rows, "agent"),
    }

    # 落盘：事实源 json + 影子表（经门面，shadow best-effort）
    _ds.write_model_effectiveness(report, base_dir=base_dir)
    return report


def main():
    rep = compute()
    print(json.dumps({
        "n_postmortems": rep["n_postmortems"],
        "attribution_source": rep["attribution_source"],
        "rules": [(e["key"], e["n_trades"], e["effectiveness"]) for e in rep["by_rule"]],
        "families": [(e["key"], e["n_trades"], e["effectiveness"]) for e in rep["by_family"]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
