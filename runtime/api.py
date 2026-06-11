"""
api — Paper Runtime API（Phase 2b，FastAPI）
============================================================================
路线：保留 Next.js 只读 Dashboard + Python 单写者 Runtime。

* GET 端读 **影子 DB（canonical）**：positions 是去重后的 canonical 视图（按
  canonical_market_id），不是膨胀的原始 json。
* POST /paper/open|close **复用 orchestrator.lock 单写者锁**：扫描周期正在跑就
  返回 409，绝不与周期并发写 paper —— 守住 Phase 0 的单写者不变量。
* 写仍经 paper_pnl → runtime.datastore 门面：**JSON 仍是事实源**，shadow 同步。

运行（主机 venv）：
    PA_SHADOW_DB=1 PA_BASE_DIR=/Users/libo/.hermes/polymarket_arbitrage \\
      venv/bin/python3 -m uvicorn runtime.api:app --host 127.0.0.1 --port 8848
"""

from __future__ import annotations

import json
import os
from typing import Optional

# API 进程默认开 shadow，使 POST 写入同步落 DB（GET 读 DB 才新鲜）
os.environ.setdefault("PA_SHADOW_DB", "1")

from fastapi import Body, FastAPI, HTTPException, Query

from _paths import get_base_dir
from runtime import _shadow
from runtime.locking import WriterBusy, single_writer_lock

app = FastAPI(title="Polymarket Paper Runtime API", version="0.2b")


def _base():
    return get_base_dir()


# ---------------------------------------------------------------------------
# 只读（影子 DB / json 事实源）
# ---------------------------------------------------------------------------

@app.get("/runtime/status")
def runtime_status():
    """orchestrator 周期状态（读 json 事实源，永远最新）。"""
    p = _base() / "data" / "orchestrator_status.json"
    if not p.exists():
        return {"state": "unknown"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"status unreadable: {exc}")


@app.get("/paper/positions")
def paper_positions(status: Optional[str] = Query(None, pattern="^(open|closed)$"),
                    limit: int = Query(500, ge=1, le=5000)):
    """canonical 持仓视图（影子 DB，已按 canonical_market_id 去重）。"""
    return {"summary": _shadow.positions_summary(),
            "positions": _shadow.query_positions(status=status, limit=limit)}


@app.get("/paper/trades")
def paper_trades(limit: int = Query(200, ge=1, le=5000)):
    return {"trades": _shadow.query_trades(limit=limit)}


@app.get("/signals")
def signals(limit: int = Query(200, ge=1, le=5000)):
    return {"signals": _shadow.query_signals(limit=limit)}


@app.get("/reviews")
def reviews(limit: int = Query(200, ge=1, le=5000)):
    return {"reviews": _shadow.query_reviews(limit=limit)}


@app.get("/markets")
def markets(limit: int = Query(500, ge=1, le=5000)):
    return {"markets": _shadow.query_markets(limit=limit)}


@app.get("/postmortems")
def postmortems(outcome: Optional[str] = Query(None, pattern="^(win|loss|flat)$"),
                limit: int = Query(200, ge=1, le=5000)):
    """逐笔复盘（Phase 3a）。影子 DB。"""
    return {"postmortems": _shadow.query_postmortems(outcome=outcome, limit=limit)}


@app.get("/hypotheses")
def hypotheses(limit: int = Query(200, ge=1, le=5000)):
    """研究假设（Phase 3c）。影子 DB。"""
    return {"hypotheses": _shadow.query_hypotheses(limit=limit)}


@app.get("/model-effectiveness")
def model_effectiveness(scope: Optional[str] = Query(None, pattern="^(model|rule|family|agent)$"),
                        limit: int = Query(500, ge=1, le=5000)):
    """模型/规则有效性聚合（Phase 3e/3f-loop）。影子 DB。scope ∈ model/rule/family/agent。
    scope=model 是真实模型标签（models_used，如 cointegration）的有效性。"""
    return {"model_effectiveness": _shadow.query_model_effectiveness(scope=scope, limit=limit)}


@app.get("/rule-weights")
def rule_weights(scope: Optional[str] = Query(None, pattern="^(rule|family)$"),
                 limit: int = Query(500, ge=1, le=5000)):
    """规则权重建议（Phase 3e-2）。影子 DB。⚠ 仅建议，未接入 live 交易链路。"""
    return {"rule_weights": _shadow.query_rule_weights(scope=scope, limit=limit)}


@app.get("/correlation-signals")
def correlation_signals(limit: int = Query(500, ge=1, le=5000)):
    """协整/spread 研究候选（Phase 3f，真实模型）。影子 DB。⚠ 研究产物，未接入 live 交易链路。"""
    return {"correlation_signals": _shadow.query_correlation_signals(limit=limit)}


@app.get("/regime-states")
def regime_states(regime: Optional[str] = Query(None, pattern="^(calm|normal|turbulent)$"),
                  limit: int = Query(500, ge=1, le=5000)):
    """HMM 市场状态识别（Phase 3g，真实模型 hmm）。影子 DB。regime ∈ calm/normal/turbulent。
    ⚠ 研究产物，未接入 live 交易链路。"""
    return {"regime_states": _shadow.query_regime_states(regime=regime, limit=limit)}


@app.get("/regime-effectiveness")
def regime_effectiveness(limit: int = Query(500, ge=1, le=5000)):
    """regime 有效性聚合（Phase 3g-loop，PRD §13「哪个 regime 有效」）。影子 DB。
    ⚠ 学习产物，未接入 live 交易链路。"""
    return {"regime_effectiveness": _shadow.query_regime_effectiveness(limit=limit)}


@app.get("/volatility-states")
def volatility_states(risk_state: Optional[str] = Query(None, pattern="^(elevated|normal|calm)$"),
                      limit: int = Query(500, ge=1, le=5000)):
    """GARCH(1,1) 波动率/风险状态（Phase 3h，真实模型 garch）。影子 DB。
    risk_state ∈ elevated/normal/calm。⚠ 研究产物，未接入 live 交易链路。"""
    return {"volatility_states": _shadow.query_volatility_states(risk_state=risk_state, limit=limit)}


@app.get("/sizing-suggestions")
def sizing_suggestions(limit: int = Query(500, ge=1, le=5000)):
    """Kelly+Markowitz 仓位建议（Phase 3i，PRD §11 优先级 4/5）。影子 DB。
    ⚠ 建议产物，未接入 agent_m/executor/probe 仓位。"""
    return {"sizing_suggestions": _shadow.query_sizing_suggestions(limit=limit)}


@app.get("/enforcement-audit")
def enforcement_audit(limit: int = Query(500, ge=1, le=5000)):
    """纸面强制层逐条 position_size 调整审计（Phase 5：动态权重 + sizing 接入）。影子 DB。
    ⚠ 仅 env 门控 PA_ENFORCE_* 开启时有数据；只改 position_size，不绕过 Agent M/dry-run。"""
    return {"enforcement_audit": _shadow.query_enforcement_audit(limit=limit)}


# ---------------------------------------------------------------------------
# 写（单写者锁；周期跑时 409）
# ---------------------------------------------------------------------------

@app.post("/paper/open")
def paper_open(signal: dict = Body(...)):
    """开 paper 仓。复用 orchestrator.lock：周期正在跑则 409。"""
    from paper_pnl import PaperPortfolio
    try:
        with single_writer_lock(_base()):
            pos = PaperPortfolio().open_position(signal)
            return {"ok": True, "position": pos.to_dict()}
    except WriterBusy as e:
        raise HTTPException(409, str(e))


@app.post("/paper/close")
def paper_close(sell_signal: dict = Body(...)):
    """平 paper 仓。周期正在跑则 409；无匹配持仓则 404。"""
    from paper_pnl import PaperPortfolio
    try:
        with single_writer_lock(_base()):
            pos = PaperPortfolio().close_position(sell_signal)
            if pos is None:
                raise HTTPException(404, "无匹配持仓可平")
            return {"ok": True, "position": pos.to_dict()}
    except WriterBusy as e:
        raise HTTPException(409, str(e))


# ---------------------------------------------------------------------------
# 运维工具
# ---------------------------------------------------------------------------

@app.post("/admin/reconcile-provisional")
def reconcile_provisional():
    """把历史临时键 slug:<x> 持仓升级到权威 id（Phase 2a 尾巴）。"""
    n = _shadow.upgrade_provisional_positions()
    return {"ok": True, "upgraded": n}


@app.post("/admin/generate-postmortems")
def generate_postmortems(use_llm: bool = Query(False)):
    """对未复盘的已平仓持仓逐笔生成复盘（Phase 3a）。use_llm=true 走 LLM 叙述增强。"""
    from runtime import postmortem
    return postmortem.generate(base_dir=_base(), use_llm=use_llm)


@app.get("/healthz")
def healthz():
    return {"ok": True}
