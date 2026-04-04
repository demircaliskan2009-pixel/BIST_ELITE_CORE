"""FAZ42: Instrument master instrument_id + alias resolution; deterministic; manifest instrument_resolution."""

from __future__ import annotations

from pathlib import Path


def test_faz42_master_id_alias_resolves_old_to_id1(tmp_path: Path) -> None:
    """Master has ID1 with symbol NEW and alias OLD; snapshot contains OLD -> resolves to ID1; unknowns empty; deterministic."""
    from bist_core.services.instrument_master import load_instrument_master, resolve_symbols

    master_csv = tmp_path / "master.csv"
    master_csv.write_text(
        "instrument_id,symbol,aliases\nID1,NEW,OLD\n",
        encoding="utf-8",
    )
    master_set, meta, symbol_to_id = load_instrument_master(master_csv)
    assert "NEW" in master_set
    assert symbol_to_id.get("NEW") == "ID1"
    assert symbol_to_id.get("OLD") == "ID1"
    result = resolve_symbols(["OLD"], symbol_to_id)
    assert result["instrument_ids"] == ["ID1"]
    assert result["alias_map"] == {"OLD": "ID1"}
    assert result["unknown"] == []
    result2 = resolve_symbols(["OLD", "OLD"], symbol_to_id)
    assert result2["instrument_ids"] == ["ID1"]
    assert result2["unknown"] == []


def test_faz42_eod_run_manifest_has_instrument_resolution(tmp_path: Path) -> None:
    """EOD run with instrument master (ID1/NEW/OLD): snapshot OLD -> manifest has instrument_resolution, OLD->ID1, unknown empty."""
    from bist_core.services.eod_pipeline import run_eod_pipeline

    day = "2099-09-01"
    snapshot_root = tmp_path / "snapshots"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text(
        "symbol,close\nOLD,10.0\n",
        encoding="utf-8",
    )

    master_csv = tmp_path / "master.csv"
    master_csv.write_text(
        "instrument_id,symbol,aliases\nID1,NEW,OLD\n",
        encoding="utf-8",
    )

    outdir = tmp_path / "out"
    manifest, code = run_eod_pipeline(
        day,
        snapshot_root=snapshot_root,
        outdir=outdir,
        ignore_calendar=True,
        instrument_master=master_csv,
    )
    assert code == 0
    assert "instrument_resolution" in manifest
    res = manifest["instrument_resolution"]
    assert res["instrument_ids"] == ["ID1"]
    assert res["alias_map"].get("OLD") == "ID1"
    assert res["unknown"] == []
