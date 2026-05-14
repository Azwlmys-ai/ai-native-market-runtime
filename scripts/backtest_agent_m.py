"""
scripts/backtest_agent_m.py — Agent M 离线回测评估器

用途：
  对存量测试信号文件（含 expected_outcome 字段）运行 Agent M 的
  「纯 Python 可测部分」（分类逻辑、仓位预处理），不调用 LLM。
  同时加载已捕获的 review_results.json，比对 LLM 实际决策与期望结果，
  量化漏批率（FN）和误批率（FP）。

不做：
  - 不调用任何 LLM API
  - 不修改任何数据文件
  - 不下单、不部署

运行方式：
  python3 scripts/backtest_agent_m.py [--data-dir data/]

输出：
  - 各测试集分类统计
  - 仓位超限信号清单
  - 对比 review_results.json 的实际 vs 期望矩阵
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 延迟导入：只用纯 Python 部分，不触发 openai/llm_helper 依赖
def _load_classify():
    """把 classify_signal 从 agent_m 里单独加载出来（规避 openai import）。"""
    import importlib.util, types

    src_path = PROJECT_ROOT / "agents" / "agent_m.py"
    source = src_path.read_text(encoding="utf-8")

    # 把顶层 import 替换成 stub，只保留纯 Python 部分
    stub_source = "\n".join(
        f"# STUBBED: {line}" if line.startswith(("from llm_helper", "from review_cache", "import llm_helper"))
        else line
        for line in source.splitlines()
    )
    # 提供 call_llm_sync stub，避免 NameError
    # Provide stubs so exec doesn't fail on missing imports or __file__
    stub_globals: dict = {
        "__file__": str(src_path),
        "__name__": "agent_m_stub",
        "call_llm_sync": None,
        "ReviewCache": None,
    }
    stub_source = (
        "call_llm_sync = None\n"
        "class ReviewCache:\n"
        "    def __init__(self, *a, **kw): pass\n"
        "    def get(self, *a): return None\n"
        "    def set(self, *a): pass\n"
        + stub_source
    )
    mod = types.ModuleType("agent_m_stub")
    mod.__dict__.update(stub_globals)
    exec(compile(stub_source, str(src_path), "exec"), mod.__dict__)  # noqa: S102
    return mod.AgentM.classify_signal


classify_signal = _load_classify()


# ---------------------------------------------------------------------------
# 测试数据集定义
# ---------------------------------------------------------------------------

TEST_DATASETS = [
    {
        "name": "historical_test_signals",
        "file": "data/historical_test_signals.json",
        # expected_outcome 字段值映射：原始文件用 "NO"/"REJECT"，统一成 APPROVE/REJECT
        "outcome_map": {"NO": "APPROVE", "APPROVE": "APPROVE", "REJECT": "REJECT"},
    },
    {
        "name": "test_signals_round2",
        "file": "data/test_signals_round2.json",
        "outcome_map": {"APPROVE": "APPROVE", "REJECT": "REJECT"},
    },
    {
        "name": "test_signals_round3",
        "file": "data/test_signals_round3.json",
        "outcome_map": {"APPROVE": "APPROVE", "REJECT": "REJECT"},
    },
]

REVIEW_RESULTS_FILE = "data/review_results.json"


# ---------------------------------------------------------------------------
# 分析辅助
# ---------------------------------------------------------------------------

def _normalize_expected(raw: str | None, mapping: dict) -> str:
    return mapping.get(raw or "", raw or "UNKNOWN")


def analyze_dataset(path: Path, outcome_map: dict) -> dict:
    """分析单个测试集：分类统计 + 仓位违规。"""
    if not path.exists():
        return {"error": f"{path} not found"}

    signals: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))

    rows = []
    for sig in signals:
        cls = classify_signal(sig)
        pos = sig.get("position_size", 0)
        expected = _normalize_expected(sig.get("expected_outcome"), outcome_map)
        pos_violation = pos >= 0.20 and not (cls["is_whitelist_extreme"] or cls["is_arbitrage"])
        pos_capped = pos >= 0.20 and (cls["is_whitelist_extreme"] or cls["is_arbitrage"])
        rows.append(
            {
                "market": sig.get("market_name", sig.get("market", ""))[:70],
                "direction": sig.get("direction"),
                "price": sig.get("price"),
                "position_size": pos,
                "expected": expected,
                "is_whitelist_extreme": cls["is_whitelist_extreme"],
                "is_arbitrage": cls["is_arbitrage"],
                "pos_violation": pos_violation,
                "pos_capped": pos_capped,
            }
        )

    total = len(rows)
    whitelist_extreme_count = sum(1 for r in rows if r["is_whitelist_extreme"])
    arbitrage_count = sum(1 for r in rows if r["is_arbitrage"])
    pos_violations = [r for r in rows if r["pos_violation"]]
    pos_capped_list = [r for r in rows if r["pos_capped"]]
    expected_approve = sum(1 for r in rows if r["expected"] == "APPROVE")
    expected_reject = sum(1 for r in rows if r["expected"] == "REJECT")

    return {
        "total": total,
        "expected_approve": expected_approve,
        "expected_reject": expected_reject,
        "whitelist_extreme": whitelist_extreme_count,
        "arbitrage": arbitrage_count,
        "pos_violations": len(pos_violations),
        "pos_violations_detail": [f"{r['market']} pos={r['position_size']:.1%}" for r in pos_violations],
        "pos_capped": len(pos_capped_list),
        "pos_capped_detail": [f"{r['market']} pos={r['position_size']:.1%}" for r in pos_capped_list],
        "rows": rows,
    }


def analyze_review_results(path: Path) -> dict:
    """
    对比 review_results.json（已捕获的 LLM 实际决策）与信号自带的
    expected_outcome 或常识判断，统计：
      - 真阳性 TP（expected=APPROVE, actual=APPROVE）
      - 假阴性 FN（expected=APPROVE, actual=REJECT）—— 漏批
      - 真阴性 TN（expected=REJECT, actual=REJECT）
      - 假阳性 FP（expected=APPROVE, actual=APPROVE 但方向错误，暂不区分）
    """
    if not path.exists():
        return {"error": f"{path} not found"}

    data: dict = json.loads(path.read_text(encoding="utf-8"))
    timestamp = data.get("timestamp", "unknown")
    total = data.get("total", 0)
    approved_list: list[dict] = data.get("approved_signals", [])
    rejected_list: list[dict] = data.get("rejected_signals", [])

    # 构建逐信号分析
    rows = []
    for entry in approved_list + rejected_list:
        sig = entry.get("signal", {})
        cls = classify_signal(sig)
        actual = entry.get("decision", "REJECT")
        failure_prob = entry.get("review", {}).get("failure_probability")
        pos = sig.get("position_size", 0)

        # 启发式期望值：whitelist_extreme + failure_prob<35 → 应该 APPROVE
        heuristic_expected = None
        if cls["is_whitelist_extreme"] and failure_prob is not None and failure_prob < 35:
            heuristic_expected = "APPROVE"

        rows.append(
            {
                "market": sig.get("market_name", sig.get("market", ""))[:70],
                "direction": sig.get("direction"),
                "price": sig.get("price"),
                "position_size": pos,
                "actual": actual,
                "failure_prob": failure_prob,
                "is_whitelist_extreme": cls["is_whitelist_extreme"],
                "is_arbitrage": cls["is_arbitrage"],
                "heuristic_expected": heuristic_expected,
                "pos_would_be_capped": pos >= 0.20 and (cls["is_whitelist_extreme"] or cls["is_arbitrage"]),
            }
        )

    # 启发式漏批（whitelist_extreme + low failure_prob + actual=REJECT）
    false_negatives = [
        r for r in rows
        if r["heuristic_expected"] == "APPROVE" and r["actual"] == "REJECT"
    ]
    # 仓位超限导致的拒绝（after fix，这些应消失）
    pos_caused_reject = [
        r for r in false_negatives
        if r["pos_would_be_capped"]
    ]

    return {
        "timestamp": timestamp,
        "total": total,
        "approved": len(approved_list),
        "rejected": len(rejected_list),
        "approval_rate": f"{len(approved_list)/total*100:.1f}%" if total else "0%",
        "heuristic_false_negatives": len(false_negatives),
        "heuristic_fn_detail": [
            f"{r['market']}  pos={r['position_size']:.1%}  failure_prob={r['failure_prob']}"
            for r in false_negatives
        ],
        "pos_caused_reject": len(pos_caused_reject),
        "pos_caused_reject_detail": [
            f"{r['market']}  pos={r['position_size']:.1%}"
            for r in pos_caused_reject
        ],
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Agent M 离线回测评估器（无 LLM 调用）")
    parser.add_argument("--data-dir", default="data", help="数据目录路径（相对于项目根目录）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式（供脚本消费）")
    args = parser.parse_args()

    data_dir = PROJECT_ROOT / args.data_dir
    results: dict[str, Any] = {}

    # ---- 各测试集分析 ----
    print("\n========== Agent M 离线回测评估器 ==========\n")
    for ds in TEST_DATASETS:
        path = data_dir / Path(ds["file"]).name
        r = analyze_dataset(path, ds["outcome_map"])
        results[ds["name"]] = r
        if "error" in r:
            print(f"[{ds['name']}] ⚠️  {r['error']}")
            continue
        print(f"[{ds['name']}]")
        print(f"  总信号: {r['total']}  期望通过: {r['expected_approve']}  期望拒绝: {r['expected_reject']}")
        print(f"  白名单极端: {r['whitelist_extreme']}  套利: {r['arbitrage']}")
        print(f"  仓位超限（非白名单/非套利，真正违规）: {r['pos_violations']}")
        if r["pos_violations_detail"]:
            for d in r["pos_violations_detail"]:
                print(f"    ⛔  {d}")
        print(f"  仓位超限→预处理降至19%（白名单/套利）: {r['pos_capped']}")
        if r["pos_capped_detail"]:
            for d in r["pos_capped_detail"]:
                print(f"    ✂️  {d}")
        print()

    # ---- review_results.json 实际决策分析 ----
    rr_path = data_dir / Path(REVIEW_RESULTS_FILE).name
    rr = analyze_review_results(rr_path)
    results["review_results"] = rr
    if "error" in rr:
        print(f"[review_results] ⚠️  {rr['error']}")
    else:
        print(f"[review_results] 时间戳: {rr['timestamp']}")
        print(f"  总计: {rr['total']}  通过: {rr['approved']}  拒绝: {rr['rejected']}  通过率: {rr['approval_rate']}")
        print(f"  启发式漏批（whitelist_extreme + failure_prob<35 + 实际REJECT）: {rr['heuristic_false_negatives']}")
        if rr["heuristic_fn_detail"]:
            for d in rr["heuristic_fn_detail"]:
                print(f"    ❌  {d}")
        print(f"  其中仓位超限导致的拒绝（fix后应消失）: {rr['pos_caused_reject']}")
        if rr["pos_caused_reject_detail"]:
            for d in rr["pos_caused_reject_detail"]:
                print(f"    🔧  {d}")

    print("\n========== 评估完成 ==========\n")

    if args.json:
        # 移除 rows 大列表，保持输出精简
        for v in results.values():
            v.pop("rows", None)
        print(json.dumps(results, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
