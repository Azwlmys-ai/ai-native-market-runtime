"""Phase 3 historical replay learning — unit tests (learning-only)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from analytics.historical_replay_joiner import join_event
from analytics.hypothesis_generator import generate_hypotheses
from analytics.theme_learning_engine import learn_patterns


def test_join_event_shape():
    ev = {
        "event": "NFP",
        "date": "2024-01-05",
        "theme": "RATES",
        "actual": 216000,
        "expected": 180000,
        "surprise": 36000,
        "QQQ_1D": -1.8,
        "SOXL_1D": -4.9,
        "BTC_1D": -2.2,
        "QQQ_3D": -2.1,
        "BTC_3D": -3.0,
    }
    row = join_event(ev)
    assert row["theme"] == "RATES"
    assert row["QQQ_1D"] == -1.8
    assert "PM_PROXY_1D" in row


def test_hypothesis_generator_min_sample():
    rows = []
    for i in range(12):
        rows.append({
            "theme": "AI",
            "SOXL_1D": -4.0 + (i % 3) * 0.5,
            "QQQ_1D": -1.0,
        })
    hyps = generate_hypotheses(rows)
    assert len(hyps) >= 1
    assert hyps[0]["sample_size"] >= 10
    assert hyps[0]["status"] == "Pending Validation"


def test_theme_learning_patterns():
    rows = [{"theme": "RATES", "BTC_1D": -1.0, "ETH_1D": -0.5} for _ in range(8)]
    report = learn_patterns(rows)
    assert report["n_events"] == 8
    assert len(report["patterns"]) >= 1
