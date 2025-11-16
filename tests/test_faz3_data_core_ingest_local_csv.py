from __future__ import annotations
import pytest
from pathlib import Path
from bist_core.data.ingest import read_csv, register_dataset, load_registered_dataset

def _write_sample_csv(tmp_path: Path) -> Path:
    p = tmp_path / "eod" / "quotes.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "symbol,date,close,volume\n"
        "AAA,2025-01-13,10.5,1000\n"
        "AAA,2025-01-14,11.0,2000\n"
        "BBB,2025-01-13,20.0,500\n",
        encoding="utf-8",
    )
    return p

def test_load_csv_basic(tmp_path: Path) -> None:
    csv_path = _write_sample_csv(tmp_path)
    rows = list(
        read_csv(
            csv_path,
            required_columns=["symbol", "date", "close"],
            schema={"close": float, "volume": int},
            date_field="date",
        )
    )
    assert [r["date"] for r in rows] == ["2025-01-13", "2025-01-14", "2025-01-13"]
    row0 = rows[0]
    assert isinstance(row0["close"], float)
    assert isinstance(row0["volume"], int)

def test_registry_load(tmp_path: Path) -> None:
    # dataset registry 'db' ve veri 'eod' aynı kökün altında
    base_root = tmp_path
    _write_sample_csv(base_root)

    spec = {
        "required_columns": ["symbol", "date", "close"],
        "schema": {"close": float, "volume": int},
        "date_field": "date",
        # path belirtmesen de kod 'eod/quotes.csv' i bulmalı
    }
    db = base_root / "db"
    register_dataset("quotes", spec, base_dir=db)
    rows = load_registered_dataset("quotes", base_dir=db)
    assert len(rows) == 3
    assert {r["symbol"] for r in rows} == {"AAA", "BBB"}

def test_missing_column_raises(tmp_path: Path) -> None:
    bad = tmp_path / "eod" / "quotes_bad.csv"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text(
        "symbol,date,volume\n"
        "AAA,2025-01-13,1000\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as e:
        list(
            read_csv(
                bad,
                required_columns=["symbol", "date", "close", "nonexistent"],
                date_field="date",
            )
        )
    assert "missing required columns" in str(e.value)
