from __future__ import annotations

import csv
import pytest
from pathlib import Path
from bist_core.data.ingest import read_csv, register_dataset, load_registered_dataset

def _write_sample_csv(tmp_path: Path) -> Path:
    p = tmp_path / "quotes.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol","date","close","volume"])
        w.writerow(["AAA","2025-01-13","10.0","100"])
        w.writerow(["BBB","2025-01-13","11.0","200"])
        w.writerow(["AAA","2025-01-14","12.0","300"])
    return p

def test_load_csv_basic(tmp_path: Path) -> None:
    p = _write_sample_csv(tmp_path)
    rows = list(read_csv(p, required_columns=["symbol","date","close","volume"], date_field="date"))
    assert [r["date"][:10] for r in rows] == ["2025-01-13","2025-01-13","2025-01-14"]
    assert isinstance(rows[0]["close"], float)
    assert isinstance(rows[0]["volume"], int)

def test_registry_load(tmp_path: Path) -> None:
    p = _write_sample_csv(tmp_path)
    base = tmp_path / "db"
    base.mkdir()
    spec = {
        "path": str(p),
        "required_columns": ["symbol","date","close"],
        "date_field": "date",
        "unique_by": ["symbol","date"],
    }
    register_dataset("quotes", spec, base_dir=base)
    rows = load_registered_dataset("quotes", base_dir=base)
    assert len(rows) == 3
    assert {r["symbol"] for r in rows} == {"AAA","BBB"}

def test_missing_column_raises(tmp_path: Path) -> None:
    p = _write_sample_csv(tmp_path)
    with pytest.raises(ValueError) as e:
        list(read_csv(p, required_columns=["symbol","date","close","nonexistent"], date_field="date"))
    assert "missing required columns" in str(e.value)
