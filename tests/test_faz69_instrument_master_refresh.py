"""
FAZ69: Instrument master refresh — merge new symbols/aliases from fixture dataset
into existing identity timeline deterministically (stable id, alias intervals).
No network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.services.instrument_master_refresh import (
    IDENTITY_TIMELINE_SCHEMA_VERSION,
    load_identity_timeline,
    save_identity_timeline,
    load_fixture_dataset,
    merge_fixture_into_timeline,
    refresh_instrument_master,
)


def test_faz69_load_identity_timeline_missing_returns_empty(tmp_path: Path) -> None:
    """Missing file -> empty default timeline."""
    t = load_identity_timeline(tmp_path / "nonexistent.json")
    assert t["schema_version"] == IDENTITY_TIMELINE_SCHEMA_VERSION
    assert t["identities"] == []
    assert t["alias_map"] == {}


def test_faz69_load_fixture_dataset_parses_csv(tmp_path: Path) -> None:
    """Fixture CSV (instrument_id, symbol, aliases) -> list of rows."""
    csv_path = tmp_path / "fixture.csv"
    csv_path.write_text(
        "instrument_id,symbol,aliases\nid_A,A,A1;A2\nid_B,B,\n",
        encoding="utf-8",
    )
    rows = load_fixture_dataset(csv_path)
    assert len(rows) == 2
    assert rows[0]["instrument_id"].upper() == "ID_A"
    assert rows[0]["symbol"].upper() == "A"
    assert set(a.upper() for a in rows[0]["aliases"]) == {"A1", "A2"}
    assert rows[1]["aliases"] == []


def test_faz69_merge_fixture_into_empty_timeline() -> None:
    """Empty existing + fixture rows -> identities and alias_map; stable id, alias_intervals."""
    existing = {"schema_version": 1, "identities": [], "alias_map": {}}
    fixture_rows = [
        {"instrument_id": "id_X", "symbol": "X", "aliases": ["XOLD"]},
        {"instrument_id": "id_Y", "symbol": "Y", "aliases": []},
    ]
    merged = merge_fixture_into_timeline(existing, fixture_rows, effective_date="2099-01-01")
    assert merged["schema_version"] == IDENTITY_TIMELINE_SCHEMA_VERSION
    assert len(merged["identities"]) == 2
    ids = {e["id"] for e in merged["identities"]}
    assert "ID_X" in ids or "id_x" in ids or "id_X" in ids
    assert "ID_Y" in ids or "id_y" in ids or "id_Y" in ids
    for ent in merged["identities"]:
        assert "id" in ent and "symbol" in ent and "aliases" in ent
        assert "alias_intervals" in ent
    assert "x" in merged["alias_map"] or "X" in merged["alias_map"]
    assert len(merged["alias_map"]) >= 2


def test_faz69_merge_preserves_existing_id_and_adds_aliases() -> None:
    """Existing identity + fixture with same id -> aliases merged; new alias gets interval."""
    existing = {
        "schema_version": 1,
        "identities": [
            {"id": "id_A", "symbol": "A", "aliases": ["A"], "alias_intervals": []},
        ],
        "alias_map": {"a": "id_a", "A": "id_a"},
    }
    fixture_rows = [
        {"instrument_id": "id_A", "symbol": "A", "aliases": ["AOLD", "A_ALT"]},
    ]
    merged = merge_fixture_into_timeline(existing, fixture_rows, effective_date="2099-06-01")
    assert len(merged["identities"]) == 1
    ent = merged["identities"][0]
    assert ent["id"].upper() == "ID_A"
    assert "aold" in (a.lower() for a in ent["aliases"]) or "AOLD" in ent["aliases"]
    intervals = ent["alias_intervals"]
    assert len(intervals) >= 1
    one = next((i for i in intervals if (i.get("alias") or "").lower() in ("aold", "a_alt")), None)
    assert one is not None
    assert one.get("valid_from") == "2099-06-01"
    assert one.get("valid_to") is None


def test_faz69_deterministic_same_inputs_same_output() -> None:
    """Same existing + fixture -> same identities order and alias_map."""
    existing = {"schema_version": 1, "identities": [], "alias_map": {}}
    fixture_rows = [
        {"instrument_id": "id_B", "symbol": "B", "aliases": []},
        {"instrument_id": "id_A", "symbol": "A", "aliases": ["A1"]},
    ]
    m1 = merge_fixture_into_timeline(existing, fixture_rows, "2099-01-01")
    m2 = merge_fixture_into_timeline(existing, fixture_rows, "2099-01-01")
    assert [e["id"] for e in m1["identities"]] == [e["id"] for e in m2["identities"]]
    assert m1["alias_map"] == m2["alias_map"]


def test_faz69_refresh_step_saves_to_output(tmp_path: Path) -> None:
    """refresh_instrument_master: no existing, fixture present -> merged timeline written to output_path."""
    fixture = tmp_path / "new.csv"
    fixture.write_text(
        "instrument_id,symbol,aliases\nid_K,K,K1\n",
        encoding="utf-8",
    )
    out = tmp_path / "timeline.json"
    timeline, err = refresh_instrument_master(
        tmp_path / "nonexistent.json",
        fixture,
        out,
        effective_date="2099-01-15",
    )
    assert err is None
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["identities"]
    assert loaded["alias_map"]


def test_faz69_refresh_step_fixture_missing_returns_error(tmp_path: Path) -> None:
    """Fixture file missing -> error, existing timeline returned."""
    existing = tmp_path / "existing.json"
    save_identity_timeline(existing, {"schema_version": 1, "identities": [], "alias_map": {}})
    timeline, err = refresh_instrument_master(
        existing,
        tmp_path / "missing.csv",
        tmp_path / "out.json",
    )
    assert err == "fixture_not_found"


def test_faz69_repo_fixture_integration() -> None:
    """Use repo fixture CSV if present; assert stable id and alias_intervals."""
    repo_root = Path(__file__).resolve().parents[1]
    fixture = repo_root / "tests" / "fixtures" / "instrument_master_fixture.csv"
    if not fixture.is_file():
        pytest.skip("tests/fixtures/instrument_master_fixture.csv not found")
    rows = load_fixture_dataset(fixture)
    assert len(rows) >= 1
    existing = {"schema_version": 1, "identities": [], "alias_map": {}}
    merged = merge_fixture_into_timeline(existing, rows, "2099-01-01")
    assert len(merged["identities"]) >= 1
    for ent in merged["identities"]:
        assert ent.get("id") and ent.get("symbol")
        assert isinstance(ent.get("alias_intervals"), list)
