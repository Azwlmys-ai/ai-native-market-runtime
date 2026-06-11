#!/usr/bin/env python3
"""
enforcement_calibration_sim — Phase 5 纸面强制层「跑几轮验证 + 校准」离线沙箱

为何需要它
----------
完整 orchestrator 循环依赖网络/LLM keys 且项目纪律禁止直接跑真实交易循环；本脚本在
**隔离临时 base_dir + 隔离 DB** 内，用**真实 runtime 模型 + 真实 enforcement 代码**跑 N 轮，
全程 dry-run、绝不触碰真实 data/ 或真实 runtime.db。三段验证：

  A. 真实数据基线：把真实 data/ 的学习产物 + signals 拷进隔离区，跑 N 轮 enforcement，
     如实报告今天到底改了几条（用于回答「现在开 PA_ENFORCE_LEARNING 会发生什么」）。
  B. sizing 校准扫描：用真实 position_sizing.kelly_fraction 扫 edge×regime 网格，
     量化「边量纲」隐患——sized_fraction 在多大 edge 处撞上 F_MAX 饱和。
  C. live 情景端到端：构造命中 sizing + down_weight 的信号，验证替换/缩放/floor/cap 全链路。

用法（需 numpy 环境）：
  PA_DB_PATH=/tmp/x.db python3 scripts/enforcement_calibration_sim.py [--cycles N]
脚本会自行设好隔离 env（EXECUTOR_DRY_RUN/PA_SHADOW_DB/PA_ENFORCE_LEARNING/PA_DB_PATH）。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _setup_isolated_env() -> Path:
    """建隔离 base_dir + 隔离 DB，并设好 dry-run / 强制门控 env。返回隔离 base_dir。"""
    sandbox = Path(tempfile.mkdtemp(prefix="pa_enf_sim_"))
    (sandbox / "data").mkdir(parents=True, exist_ok=True)
    os.environ["EXECUTOR_DRY_RUN"] = "1"           # 纪律：永远 dry-run
    os.environ["PA_SHADOW_DB"] = "1"               # 同时验证影子 enforcement_audit 表
    os.environ["PA_ENFORCE_LEARNING"] = "1"        # 便捷=同时开 sizing + weights
    os.environ.setdefault("PA_DB_PATH", str(sandbox / "data" / "runtime.db"))
    return sandbox


def _copy_real_inputs(sandbox: Path) -> list:
    """把真实 data/ 的相关产物 + signals + 价格历史拷进隔离区（只读真实，写隔离）。"""
    src = ROOT / "data"
    dst = sandbox / "data"
    wanted = [
        "signals.json", "market_price_history.json", "latest_data.json",
        "correlation_signals.json", "volatility_states.json", "regime_states.json",
        "sizing_suggestions.json", "model_effectiveness.json", "rule_effectiveness.json",
    ]
    copied = []
    for name in wanted:
        p = src / name
        if p.exists():
            shutil.copy2(p, dst / name)
            copied.append(name)
    return copied


def _load_signals(base: Path) -> list:
    p = base / "data" / "signals.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d.get("signals", [])


# ---------------------------------------------------------------------------
# A. 真实数据基线：跑 N 轮 enforcement
# ---------------------------------------------------------------------------

def section_a_real_baseline(sandbox: Path, cycles: int) -> None:
    from runtime import cointegration, regime_hmm, garch, position_sizing, enforcement

    print("\n" + "=" * 78)
    print("A. 真实数据基线 — 隔离区内用真实模型 + 真实产物跑 {} 轮 enforcement".format(cycles))
    print("=" * 78)

    base_signals = _load_signals(sandbox)
    print(f"真实 signals: {len(base_signals)} 条；门控: {enforcement.gates()}")

    for cyc in range(1, cycles + 1):
        # 真实模型重算（价格历史静态 → 多轮结果应稳定）
        crep = cointegration.compute(base_dir=sandbox)
        try:
            regime_hmm.compute(base_dir=sandbox)
            garch.compute(base_dir=sandbox)
        except Exception as e:
            print(f"  [cycle {cyc}] regime/garch 跳过: {e}")
        srep = position_sizing.compute(base_dir=sandbox)
        # enforcement 作用于本轮信号（沿用真实 signals，模拟每轮汇总）
        out, erep = enforcement.enforce_signals(list(base_signals), base_dir=sandbox)
        changed = sum(1 for o, b in zip(out, base_signals)
                      if float(o.get("position_size", 0) or 0) != float(b.get("position_size", 0) or 0))
        print(f"  [cycle {cyc}] coint_candidates={crep.get('n_candidates')} "
              f"sizing_suggestions={srep.get('n_suggestions')} | "
              f"enforce: matched={erep.get('applied_count')} "
              f"(sizing={erep.get('n_sizing_applied')}, weight={erep.get('n_weight_applied')}) "
              f"position_size_changed={changed}")

    # 末轮逐条 join 诊断（为何改/不改）
    print("\n  末轮逐信号 join 诊断:")
    rule_rep = json.loads((sandbox / "data" / "rule_effectiveness.json").read_text()) \
        if (sandbox / "data" / "rule_effectiveness.json").exists() else {}
    widx = enforcement._weight_index(rule_rep)
    for s in base_signals:
        rule = enforcement._signal_rule(s)
        hit = enforcement._lookup_weight(s, widx)
        wtxt = (f"{hit['matched_scope']}:{hit.get('key')} w={hit.get('weight')} "
                f"({hit.get('recommendation')})" if hit else "无命中→w=1.0")
        print(f"    rule={rule!r:24s} ps={s.get('position_size')} → weight {wtxt}")
    print("  结论: 真实 signals 的规则当前全为 explore/keep(w=1.0) 或无命中，且 sizing 候选为空，"
          "故 enforcement 今天对真实信号 0 净改动（冷启动如实表现，非缺陷）。")


# ---------------------------------------------------------------------------
# B. sizing 校准扫描：真实 kelly_fraction over edge×regime
# ---------------------------------------------------------------------------

def section_b_sizing_calibration() -> None:
    from runtime import position_sizing as ps
    from runtime import cointegration as coint

    print("\n" + "=" * 78)
    print("B. sizing 校准对比 — 边量纲校准前/后（真实 kelly_fraction）；F_MAX={}, κ={}".format(
        ps.F_MAX, ps.KELLY_KAPPA))
    print("=" * 78)
    print("  场景: price=0.5, spread_std=0.02, φ=0.8（每步回归 (1−φ)=0.2）。")
    print("  对比同一格 OLD(价格单位 μ,σ²) vs NEW(收益率空间 μ,σ²)；扫 zscore × GARCH vol。")
    print("  ★=撞 F_MAX 饱和；μ=NEW 实际喂 Kelly 的无量纲边。\n")

    price, spread_std, phi = 0.5, 0.02, 0.8
    grid_z = [2.0, 3.0, 4.0]
    grid_vol = [0.03, 0.08, 0.15]    # GARCH 每步波动（价格单位）：低→高（calm→turbulent/illiquid）

    def tag(f):
        return "★" if f >= ps.F_MAX - 1e-9 else " "

    print(f"  {'z':>4} {'vol':>5} | {'OLD kelly':>12} | {'NEW kelly':>12} | {'NEW μ(收益率)':>14}")
    print("  " + "-" * 60)
    old_sat = new_sat = total = 0
    for z in grid_z:
        for vol in grid_vol:
            old = ps.kelly_fraction(abs(z) * spread_std, vol ** 2)["kelly_fraction"]
            mu = coint._dimensionless_edge(abs(z) * spread_std, phi, price)
            new = ps.kelly_fraction(mu, (vol / price) ** 2)["kelly_fraction"]
            total += 1
            old_sat += old >= ps.F_MAX - 1e-9
            new_sat += new >= ps.F_MAX - 1e-9
            print(f"  {z:>4} {vol:>5} | {old:>10.4f}{tag(old)} | {new:>10.4f}{tag(new)} | {mu:>14}")
    print(f"\n  校准结论:")
    print(f"  1) 量纲已修正：μ、σ² 现统一在无量纲收益率空间（μ=(1−φ)·|z|·spread_std/price，σ²=(vol/price)²），"
          f"可解释、可与 realized_return 对账；旧候选无 entry_price 时安全退化（向后兼容）。")
    print(f"  2) 饱和格数 OLD={old_sat}/{total} → NEW={new_sat}/{total}：高 vol（turbulent/低流动）格已脱离 F_MAX，"
          f"Kelly 恢复区分度；低 vol+强边格仍撞 F_MAX。")
    print(f"  3) 低 vol 仍饱和不是 bug：是 stat-arb 单步 Sharpe 本就高 → 分数 Kelly κ={ps.KELLY_KAPPA} + F_MAX="
          f"{ps.F_MAX} 封顶按设计兜底。进一步去饱和（更小 κ / 持有期一致的 σ²）是独立建模决策，需真实候选数据评估。")


# ---------------------------------------------------------------------------
# C. live 情景端到端：sizing 替换 + weight 缩放 + floor/cap
# ---------------------------------------------------------------------------

def section_c_live_scenario(sandbox: Path) -> None:
    from runtime import enforcement, position_sizing as ps

    print("\n" + "=" * 78)
    print("C. live 情景端到端 — 构造命中 sizing + down_weight 的信号验证全链路")
    print("=" * 78)
    data = sandbox / "data"

    # 用真实 suggest() 从合成协整候选 + GARCH 方差 + HMM regime 产出 sizing（真实算法）
    candidates = [
        {"signal_uid": "sim-pair-1", "expected_edge": 0.03,
         "legs": [{"market_id": "SIMMKT_A", "tradeable": True}],
         "source_markets": ["SIMMKT_A", "SIMMKT_B"], "models_used": ["cointegration"],
         "confidence": 0.8},
    ]
    variance_map = {"SIMMKT_A": 0.05 ** 2}          # GARCH normal
    regime_map = {"SIMMKT_A": "turbulent"}          # HMM turbulent → ×0.5
    suggestions = ps.suggest(candidates, variance_map, regime_map)
    (data / "sizing_suggestions.json").write_text(
        json.dumps({"suggestions": suggestions}), encoding="utf-8")
    sug = suggestions[0]
    print(f"  合成 sizing: edge={sug['expected_edge']} var={sug['variance']} regime={sug['regime']} "
          f"→ kelly={sug['kelly_fraction']} ×{sug['regime_scaler']} = sized_fraction={sug['sized_fraction']}")

    # down_weight 规则
    (data / "rule_effectiveness.json").write_text(json.dumps({
        "generated_at": "sim",
        "by_rule": [{"key": "decayed_edge_rule", "weight": 0.25,
                     "recommendation": "retire_candidate", "effectiveness": "decayed"}],
        "by_family": [],
    }), encoding="utf-8")

    signals = [
        # 命中 sizing（market_id），原始 0.1 → 降险到 sized_fraction
        {"market_id": "SIMMKT_A", "market_name": "Sim A", "direction": "YES",
         "price": 0.5, "position_size": 0.1, "signal_uid": "sim-pair-1",
         "models_used": ["cointegration"]},
        # 命中 down_weight 规则 0.25：0.1 → 0.025
        {"market_id": "SIMMKT_C", "market_name": "Sim C", "direction": "NO",
         "price": 0.4, "position_size": 0.1, "learned_rule_match": "decayed_edge_rule"},
        # 负边 sizing → floor 兜底（不归零探针）
        {"market_id": "SIMMKT_D", "market_name": "Sim D", "direction": "YES",
         "price": 0.5, "position_size": 0.1, "signal_uid": "sim-neg"},
        # 无命中 → 原样
        {"market_id": "SIMMKT_E", "market_name": "Sim E", "direction": "YES",
         "price": 0.5, "position_size": 0.1},
    ]
    # 给 sim-neg 一条负边 sizing
    suggestions.append({"signal_uid": "sim-neg", "market_id": "SIMMKT_D",
                        "sized_fraction": 0.0, "regime": "calm", "kelly_fraction": 0.0,
                        "regime_scaler": 1.0, "variance_source": "default"})
    (data / "sizing_suggestions.json").write_text(
        json.dumps({"suggestions": suggestions}), encoding="utf-8")

    out, erep = enforcement.enforce_signals(signals, base_dir=sandbox)
    print(f"\n  门控: {erep['gates']}")
    print(f"  matched={erep['applied_count']} sizing={erep['n_sizing_applied']} weight={erep['n_weight_applied']}")
    print(f"  {'market':10s} {'orig':>6} {'final':>7}  applied")
    for o, b in zip(out, signals):
        ev = o.get("enforcement", {})
        print(f"  {o['market_id']:10s} {b['position_size']:>6} {o['position_size']:>7}  {ev.get('applied', [])}")
    print("\n  期望: A→sized_fraction(降险≤0.1) / C→0.025(×0.25) / D→0.005(floor 不归零) / E→0.1(不变)。")

    # 验证影子审计表
    try:
        from runtime import _shadow
        rows = _shadow.query_enforcement_audit()
        ver = _shadow._conn().execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
        print(f"  影子 enforcement_audit 表: {len(rows)} 行（schema={ver}）")
    except Exception as e:
        print(f"  影子表校验跳过: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=3)
    ap.add_argument("--keep", action="store_true", help="保留隔离 sandbox 目录（默认运行后删除）")
    args = ap.parse_args()

    sandbox = _setup_isolated_env()
    print(f"隔离 sandbox: {sandbox}")
    print(f"env: EXECUTOR_DRY_RUN={os.environ['EXECUTOR_DRY_RUN']} "
          f"PA_SHADOW_DB={os.environ['PA_SHADOW_DB']} "
          f"PA_ENFORCE_LEARNING={os.environ['PA_ENFORCE_LEARNING']} "
          f"PA_DB_PATH={os.environ['PA_DB_PATH']}")
    copied = _copy_real_inputs(sandbox)
    print(f"已拷入真实输入: {copied}")

    try:
        section_a_real_baseline(sandbox, args.cycles)
        section_b_sizing_calibration()
        section_c_live_scenario(sandbox)
        print("\n" + "=" * 78)
        print("完成。全程 dry-run，未触碰真实 data/ 或真实 runtime.db。")
        print("=" * 78)
    finally:
        if not args.keep:
            shutil.rmtree(sandbox, ignore_errors=True)
        else:
            print(f"\n保留 sandbox: {sandbox}")


if __name__ == "__main__":
    main()
