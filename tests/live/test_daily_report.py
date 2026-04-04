"""Tests for daily report generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.live.report import generate_daily_report


def test_daily_report_generation(tmp_path: Path) -> None:
    trades_path = tmp_path / "paper_trades.jsonl"
    trades_path.write_text(
        '{"timestamp":"2024-01-15T10:00:00Z","symbol":"GARAN","entry":100,"exit":105,"pnl":5,"exit_reason":"target","action":"BUY","score":1.0,"regime":"trending"}\n'
        '{"timestamp":"2024-01-15T11:00:00Z","symbol":"ASELS","entry":50,"exit":48,"pnl":-2,"exit_reason":"stop","action":"BUY","score":0.8,"regime":"ranging"}\n'
    )
    out_path = generate_daily_report(
        date_str="2024-01-15",
        trades_path=str(trades_path),
        output_dir=str(tmp_path),
    )
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert data["date"] == "2024-01-15"
    assert data["total_trades"] == 2
    assert data["pnl"] == 3.0
    assert "GARAN" in data["per_symbol"]
    assert "ASELS" in data["per_symbol"]
    assert "trending" in data["per_regime"]
    assert "ranging" in data["per_regime"]
