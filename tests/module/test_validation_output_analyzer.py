"""validation_run.txt parser and stress classification."""

from __future__ import annotations

import tempfile
from pathlib import Path

from bist_core.validation.output_analyzer import (
    compute_derived,
    detect_failures,
    parse_validation_file,
    run_analysis,
)


def test_parse_extracts_summary_blocks_json_line() -> None:
    """live_runner may emit single-line JSON for validation blocks."""
    sample = """
{"stage":"decision","action":"hold","symbol":"X"}
{"SIMULATION_SUMMARY":{"actions_generated":10,"total_cycles":800}}
{"MARKET_REALISM":{"avg_slippage_fraction":0.001,"fill_success_rate":0.5,"missed_trades":2}}
{"EXECUTION_METRICS":{"fill_attempts":5}}
{"RISK_METRICS":{"max_drawdown":0.02}}
{"SYSTEM_STATUS_REPORT":{"total_cycles":800}}
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(sample)
        p = Path(f.name)
    try:
        parsed = parse_validation_file(p)
        assert parsed["SIMULATION_SUMMARY"]["total_cycles"] == 800
        assert parsed["MARKET_REALISM"]["missed_trades"] == 2
    finally:
        p.unlink(missing_ok=True)


def test_parse_extracts_summary_blocks() -> None:
    sample = """
{'stage': 'decision', 'symbol': 'ASELS', 'action': 'hold'}
{'stage': 'decision', 'symbol': 'THYAO', 'action': 'enter'}
{'SIMULATION_SUMMARY': {'total_cycles': 800, 'actions_generated': 50, 'active_symbols': ['A', 'B']}}
{'MARKET_REALISM': {'fill_success_rate': 0.55, 'missed_trades': 3, 'avg_slippage_fraction': 0.0012}}
{'EXECUTION_METRICS': {'avg_slippage': 0.001}}
{'RISK_METRICS': {'max_drawdown': 0.04, 'winrate': 0.45}}
{'SYSTEM_STATUS_REPORT': {'ok': True}}
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(sample)
        p = Path(f.name)
    try:
        parsed = parse_validation_file(p)
        assert parsed["SIMULATION_SUMMARY"] is not None
        assert parsed["MARKET_REALISM"]["missed_trades"] == 3
        d = compute_derived(parsed)
        assert d["actions_per_cycle"] > 0
        flags = detect_failures(parsed, d)
        assert not any("short_run" in f for f in flags)
    finally:
        p.unlink(missing_ok=True)


def test_run_analysis_missing_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        rc = run_analysis(Path(td) / "nope.txt")
        assert rc == 2


def test_classify_fake_edge_flags() -> None:
    parsed = {
        "SIMULATION_SUMMARY": {
            "total_cycles": 800,
            "actions_generated": 100,
            "active_symbols": ["A"],
        },
        "MARKET_REALISM": {
            "fill_success_rate": 0.95,
            "missed_trades": 0,
            "avg_slippage_fraction": 0.0,
        },
        "EXECUTION_METRICS": {},
        "RISK_METRICS": {"max_drawdown": 0.02, "winrate": 0.5},
        "SYSTEM_STATUS_REPORT": {},
        "decision_actions": ["hold"] * 20,
    }
    from bist_core.validation.output_analyzer import (
        classify_edge,
        compute_derived,
        detect_failures,
    )

    d = compute_derived(parsed)
    flags = detect_failures(parsed, d)
    t = classify_edge(parsed, d, flags)
    assert t == "FAKE_EDGE"
