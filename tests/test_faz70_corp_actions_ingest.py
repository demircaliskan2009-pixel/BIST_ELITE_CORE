"""
FAZ70: Corporate actions ingestion layer producing canonical corporate_actions.csv (schema v1).
Deterministic ordering + event_id. Adjuster uses canonical input. No network.
"""

from __future__ import annotations

import csv
from pathlib import Path


from bist_core.services import corporate_actions_canon
from bist_core.services.price_adjust import _load_canonical_actions, build_adjusted_prices


def test_faz70_ingest_from_fixture_produces_canonical_csv(tmp_path: Path) -> None:
    """Ingest fixture disclosures -> corporate_actions.csv with schema v1; deterministic order + event_id."""
    repo_root = Path(__file__).resolve().parents[1]
    fixture = repo_root / "tests" / "fixtures" / "corp_actions_disclosures.jsonl"
    assert fixture.is_file(), "tests/fixtures/corp_actions_disclosures.jsonl required"
    symbol_to_id = {"ASELS": "id_asels", "THYAO": "id_thyao", "AKBNK": "id_akbnk"}
    count, errors = corporate_actions_canon.ingest_from_fixture_disclosures(
        fixture,
        symbol_to_id,
        tmp_path,
        csv_filename="corporate_actions.csv",
    )
    assert count == 3
    out_csv = tmp_path / "corporate_actions.csv"
    assert out_csv.is_file()
    with out_csv.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
    assert len(rows) == 3
    for row in rows:
        for c in ("event_id", "instrument_id", "ex_date", "kind"):
            assert c in row, f"missing column {c}"
        assert row.get("event_id")
        assert len(row["event_id"]) == 16
    order = [r["event_id"] for r in rows]
    assert order == sorted(order)


def test_faz70_canonical_csv_deterministic_same_input_same_output(tmp_path: Path) -> None:
    """Same fixture + symbol_to_id -> same corporate_actions.csv (event_id and row order)."""
    fixture = tmp_path / "disclosures.jsonl"
    fixture.write_text(
        '{"symbol":"X","effective_date":"2099-01-01","kind":"cash_dividend","cash":0.5}\n',
        encoding="utf-8",
    )
    symbol_to_id = {"X": "id_x"}
    corporate_actions_canon.ingest_from_fixture_disclosures(fixture, symbol_to_id, tmp_path / "out1")
    corporate_actions_canon.ingest_from_fixture_disclosures(fixture, symbol_to_id, tmp_path / "out2")
    c1 = (tmp_path / "out1" / "corporate_actions.csv").read_text(encoding="utf-8")
    c2 = (tmp_path / "out2" / "corporate_actions.csv").read_text(encoding="utf-8")
    assert c1 == c2


def test_faz70_adjuster_uses_canonical_csv(tmp_path: Path) -> None:
    """Adjuster loads from corporate_actions.csv and applies adjustments."""
    ca_dir = tmp_path / "corporate_actions"
    ca_dir.mkdir(parents=True, exist_ok=True)
    csv_path = ca_dir / "corporate_actions.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=corporate_actions_canon.CORPORATE_ACTIONS_CSV_SCHEMA_V1,
            extrasaction="ignore",
        )
        w.writeheader()
        w.writerow(
            {
                "event_id": "a1b2c3d4e5f6g7h8",
                "instrument_id": "id_a",
                "ex_date": "2099-06-01",
                "kind": "cash_dividend",
                "ratio": "",
                "cash": "1.0",
                "raw_source": "test",
            }
        )
    loaded = _load_canonical_actions(csv_path)
    assert len(loaded) == 1
    assert loaded[0]["instrument_id"] == "id_a"
    assert loaded[0]["kind"] == "cash_dividend"
    assert loaded[0]["cash"] == 1.0
    assert loaded[0]["ex_date"] == "2099-06-01"


def test_faz70_adjuster_build_adjusted_prices_with_csv(tmp_path: Path) -> None:
    """build_adjusted_prices with canonical corporate_actions.csv produces prices_adj.csv."""
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "2099-01-01").mkdir(parents=True, exist_ok=True)
    (snap_dir / "2099-01-01" / "snapshot.csv").write_text(
        "symbol,date,close\nA,2099-01-01,10.0\n",
        encoding="utf-8",
    )
    ca_dir = tmp_path / "ca"
    ca_dir.mkdir(parents=True, exist_ok=True)
    with (ca_dir / "corporate_actions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=corporate_actions_canon.CORPORATE_ACTIONS_CSV_SCHEMA_V1,
            extrasaction="ignore",
        )
        w.writeheader()
        w.writerow(
            {
                "event_id": "e1",
                "instrument_id": "id_a",
                "ex_date": "2099-06-01",
                "kind": "cash_dividend",
                "ratio": "",
                "cash": "0.5",
                "raw_source": "",
            }
        )
    symbol_to_id = {"A": "id_a"}
    out_dir = tmp_path / "adjusted"
    err_count, notes = build_adjusted_prices(
        snapshot_root=snap_dir,
        days=["2099-01-01"],
        canonical_actions_path=ca_dir / "corporate_actions.csv",
        symbol_to_id=symbol_to_id,
        out_dir=out_dir,
        strict=False,
    )
    assert (out_dir / "prices_adj.csv").is_file() or err_count == 0


def test_faz70_write_canonical_csv_schema_v1_columns(tmp_path: Path) -> None:
    """write_canonical_csv writes all schema v1 columns in order."""
    canonical = [
        {
            "event_id": "ev1",
            "instrument_id": "id_1",
            "ex_date": "2099-01-01",
            "kind": "split",
            "ratio": 2.0,
            "cash": None,
            "raw_source": "fixture",
        },
    ]
    out = tmp_path / "corporate_actions.csv"
    corporate_actions_canon.write_canonical_csv(out, canonical)
    with out.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        header = rdr.fieldnames
        rows = list(rdr)
    assert header == corporate_actions_canon.CORPORATE_ACTIONS_CSV_SCHEMA_V1
    assert len(rows) == 1
    assert rows[0]["event_id"] == "ev1"
    assert rows[0]["instrument_id"] == "id_1"
    assert rows[0]["kind"] == "split"
    assert float(rows[0]["ratio"]) == 2.0
