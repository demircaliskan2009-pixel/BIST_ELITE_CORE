"""FAZ32: Instruments master + alias timeline; standardized schema/loader; fail-closed gating."""
from __future__ import annotations

import json
from pathlib import Path

from bist_core.services import instrument_timeline, instrumentstore
from bist_core.services.eod_pipeline import run_eod_pipeline


def test_faz32_alias_map_remap(tmp_path: Path) -> None:
    """build_timeline produces deterministic alias_map; symbols remap to canonical."""
    day = "2099-02-01"
    instruments_path = tmp_path / "instruments.jsonl"
    instruments_path.write_text(
        "\n".join([
            '{"symbol":"X","isin":"TRX","name":"X","status":"active","source":"test","ts":"2099-02-01T00:00:00Z"}',
            '{"symbol":"Y","isin":"TRY","name":"Y","status":"active","source":"test","ts":"2099-02-01T00:00:00Z"}',
        ]) + "\n",
        encoding="utf-8",
    )
    actions_path = tmp_path / "actions.jsonl"
    actions_path.write_text(
        '{"symbol":"X","effective_date":"2099-02-01","kind":"symbol_change","old_symbol":"X","new_symbol":"Z","ts":"2099-02-01T01:00:00Z","source":"test"}\n',
        encoding="utf-8",
    )
    timeline, errors = instrument_timeline.build_timeline(day, instruments_path, actions_path)
    assert errors == []
    alias_map = timeline["alias_map"]
    assert alias_map.get("X") == "Z"
    resolved_symbols = [r["symbol"] for r in timeline["resolved"]]
    assert "Y" in resolved_symbols
    assert "Z" in resolved_symbols
    z_entry = [r for r in timeline["resolved"] if r["symbol"] == "Z"][0]
    assert "X" in z_entry["aliases"]
    assert dict(sorted(alias_map.items())) == alias_map


def test_faz32_load_instruments_jsonl_standard_schema(tmp_path: Path) -> None:
    """load_instruments_jsonl returns normalized schema; missing path => []."""
    empty = instrumentstore.load_instruments_jsonl(tmp_path / "nonexistent.jsonl")
    assert empty == []
    path = tmp_path / "instruments.jsonl"
    path.write_text(
        '{"symbol":"AAA","isin":"TRAAA","name":"AAA","status":"active","market":"EQ","source":"offline","ts":"2099-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    rows = instrumentstore.load_instruments_jsonl(path)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["status"] == "active"
    assert "source" in rows[0]


def test_faz32_resolve_aliases_missing_instruments_fail_closed(tmp_path: Path) -> None:
    """Pipeline with resolve_aliases but instruments/CA missing => universe not-ok; advice text contains güvenli mod."""
    day_str = "2099-03-01"
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True)
    (snapshot_root / day_str).mkdir(parents=True)
    (snapshot_root / day_str / "snapshot.csv").write_text(
        "symbol,close\nAAA,1.0\n",
        encoding="utf-8",
    )
    instruments_empty = tmp_path / "instruments_empty"
    instruments_empty.mkdir(parents=True)
    ca_empty = tmp_path / "ca_empty"
    ca_empty.mkdir(parents=True)
    outdir = tmp_path / "run"
    outdir.mkdir(parents=True)
    manifest, exit_code = run_eod_pipeline(
        day_str,
        snapshot_root,
        outdir,
        strict=False,
        resolve_aliases=True,
        ignore_calendar=True,
        instruments_outdir=instruments_empty,
        ca_outdir=ca_empty,
    )
    stages = manifest.get("stages", {})
    universe = stages.get("universe", {})
    assert universe.get("ok") is False
    assert universe.get("errors", 0) >= 1
    notes = universe.get("notes", [])
    assert "instruments_or_ca_missing" in notes
    advice_path = outdir / "advice.jsonl"
    assert advice_path.is_file()
    lines = advice_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    first = json.loads(lines[0])
    assert first.get("decision_raw") == "PASS"
    assert "güvenli mod" in (first.get("text") or "").lower() or "Güvenli mod" in (first.get("text") or "")


def test_faz32_manifest_notes_alias_resolution(tmp_path: Path) -> None:
    """When alias resolution runs successfully, manifest stages.universe has no instruments_or_ca_missing."""
    day_str = "2099-04-01"
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True)
    (snapshot_root / day_str).mkdir(parents=True)
    (snapshot_root / day_str / "snapshot.csv").write_text(
        "symbol,close\nAAA,1.0\nBBB,2.0\n",
        encoding="utf-8",
    )
    instruments_dir = tmp_path / "instruments" / day_str
    instruments_dir.mkdir(parents=True)
    (instruments_dir / "instruments.jsonl").write_text(
        '{"symbol":"AAA","isin":"TRAAA","name":"AAA","status":"active","source":"test","ts":"2099-04-01T00:00:00Z"}\n'
        + '{"symbol":"BBB","isin":"TRBBB","name":"BBB","status":"active","source":"test","ts":"2099-04-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    ca_dir = tmp_path / "ca" / day_str
    ca_dir.mkdir(parents=True)
    (ca_dir / "actions.jsonl").write_text("\n", encoding="utf-8")
    outdir = tmp_path / "run"
    outdir.mkdir(parents=True)
    manifest, _ = run_eod_pipeline(
        day_str,
        snapshot_root,
        outdir,
        strict=False,
        resolve_aliases=True,
        ignore_calendar=True,
        instruments_outdir=instruments_dir,
        ca_outdir=ca_dir,
    )
    universe = manifest.get("stages", {}).get("universe", {})
    assert "instruments_or_ca_missing" not in universe.get("notes", [])
