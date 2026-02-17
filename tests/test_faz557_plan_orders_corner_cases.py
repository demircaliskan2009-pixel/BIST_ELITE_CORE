"""FAZ557: Plan/orders corner cases — empty symbols, empty plan, invalid date."""
from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.strategy.equal_weight import (
    build_equal_weight_plan,
    generate_equal_weight_orders,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz557_plan_empty_symbols_writes_headers_only(tmp_path: Path) -> None:
    """Plan with empty symbol list writes CSV with headers only."""
    day_dir = tmp_path / "2025-01-15"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\n", encoding="utf-8")
    plan_path = build_equal_weight_plan("2025-01-15", base=tmp_path)
    assert plan_path.exists()
    rows = list(csv.DictReader(plan_path.open(encoding="utf-8")))
    assert len(rows) == 0
    content = plan_path.read_text(encoding="utf-8")
    assert "symbol" in content
    assert "weight" in content


def test_faz557_orders_empty_plan_returns_none(tmp_path: Path) -> None:
    """Orders with empty plan (0 rows) returns None, writes meta FAIL."""
    day_dir = tmp_path / "2025-01-15"
    day_dir.mkdir(parents=True)
    (day_dir / "plan_equal_weight.csv").write_text("symbol,weight\n", encoding="utf-8")
    result = generate_equal_weight_orders("2025-01-15", base=tmp_path)
    assert result is None
    meta_path = day_dir / "orders_meta.txt"
    assert meta_path.exists()
    assert meta_path.read_text(encoding="utf-8").strip() == "FAIL"
    assert not (day_dir / "orders_equal_weight.csv").exists()
    assert not (day_dir / "orders_equal_weight.json").exists()


def test_faz557_plan_invalid_date_raises() -> None:
    """build_equal_weight_plan with invalid date raises ValueError."""
    with pytest.raises(ValueError, match="Invalid date format"):
        build_equal_weight_plan("not-a-date", base=Path("/nonexistent"))


def test_faz557_orders_plan_not_found_raises(tmp_path: Path) -> None:
    """generate_equal_weight_orders with missing plan raises FileNotFoundError."""
    (tmp_path / "2025-01-15").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="Plan not found"):
        generate_equal_weight_orders("2025-01-15", base=tmp_path)


def test_faz557_plan_single_symbol_weight_one(tmp_path: Path) -> None:
    """Plan with single symbol has weight 1.0."""
    day_dir = tmp_path / "2025-01-15"
    day_dir.mkdir(parents=True)
    (day_dir / "snapshot.csv").write_text("symbol,close\nX,10.0\n", encoding="utf-8")
    plan_path = build_equal_weight_plan("2025-01-15", base=tmp_path)
    rows = list(csv.DictReader(plan_path.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["symbol"] == "X"
    assert abs(float(rows[0]["weight"]) - 1.0) < 1e-9


def test_faz557_orders_empty_plan_writes_to_out_dir(tmp_path: Path) -> None:
    """Empty plan with out_dir writes meta FAIL to out_dir/day/."""
    base = tmp_path / "snap"
    out = tmp_path / "export"
    day_dir = base / "2025-01-15"
    day_dir.mkdir(parents=True)
    (day_dir / "plan_equal_weight.csv").write_text("symbol,weight\n", encoding="utf-8")
    result = generate_equal_weight_orders("2025-01-15", base=base, out_dir=out)
    assert result is None
    meta_path = out / "2025-01-15" / "orders_meta.txt"
    assert meta_path.exists()
    assert meta_path.read_text(encoding="utf-8").strip() == "FAIL"


def test_faz557_orders_single_symbol_fail(tmp_path: Path) -> None:
    """Orders with single symbol (weight 1.0 > 0.5) returns None, meta FAIL."""
    day_dir = tmp_path / "2025-01-15"
    day_dir.mkdir(parents=True)
    (day_dir / "plan_equal_weight.csv").write_text(
        "symbol,weight\nX,1.000000\n",
        encoding="utf-8",
    )
    result = generate_equal_weight_orders("2025-01-15", base=tmp_path)
    assert result is None
    assert (day_dir / "orders_meta.txt").read_text(encoding="utf-8").strip() == "FAIL"
