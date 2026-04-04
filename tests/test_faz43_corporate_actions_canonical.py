"""FAZ43: Corporate actions canonicalization; event_id stable and sorted; bound to instrument_id."""

from __future__ import annotations

import json
from pathlib import Path


def test_faz43_event_id_stable_and_sorted(tmp_path: Path) -> None:
    """Canonical output has event_id stable (deterministic) and rows sorted by event_id."""
    from bist_core.services.corporate_actions_canon import (
        build_canonical,
        canonicalize_row,
        _event_id,
    )

    symbol_to_id = {"AAA": "ID1", "BBB": "ID2"}
    row = {
        "symbol": "AAA",
        "effective_date": "2099-10-01",
        "kind": "split",
        "ratio": 2.0,
        "cash": None,
        "source": "test",
    }
    canon, err = canonicalize_row(row, symbol_to_id)
    assert err is None
    assert canon is not None
    expected_eid = _event_id("ID1", "2099-10-01", "split", 2.0, None)
    assert canon["event_id"] == expected_eid
    assert canon["instrument_id"] == "ID1"
    assert canon["ex_date"] == "2099-10-01"
    assert canon["kind"] == "split"
    assert canon.get("ratio") == 2.0
    assert canon.get("raw_source") == "test"

    records = [row, {"symbol": "BBB", "effective_date": "2099-10-02", "kind": "other"}]
    canonical, errors = build_canonical(records, symbol_to_id)
    assert errors == 0
    assert len(canonical) == 2
    eids = [r["event_id"] for r in canonical]
    assert eids == sorted(eids)
    assert canonical[0]["instrument_id"] in ("ID1", "ID2")
    assert canonical[1]["instrument_id"] in ("ID1", "ID2")


def test_faz43_tmp_actions_tmp_master_resolves_instrument_id(tmp_path: Path) -> None:
    """Tmp actions + tmp master: resolve symbol to instrument_id; output event_id stable and sorted."""
    from bist_core.services import instrument_master
    from bist_core.services.corporate_actions_canon import (
        canonicalize_actions_file,
        build_canonical,
    )

    master_csv = tmp_path / "master.csv"
    master_csv.write_text(
        "instrument_id,symbol,aliases\nID1,SYM1,\n",
        encoding="utf-8",
    )
    _, _, symbol_to_id = instrument_master.load_instrument_master(master_csv)
    assert symbol_to_id.get("SYM1") == "ID1"

    actions_path = tmp_path / "actions.jsonl"
    actions_path.write_text(
        '{"symbol":"SYM1","effective_date":"2099-10-05","kind":"split","ratio":3.0}\n',
        encoding="utf-8",
    )
    out_path = tmp_path / "actions_canonical.jsonl"
    count, err_count = canonicalize_actions_file(actions_path, out_path, symbol_to_id)
    assert count == 1
    assert err_count == 0
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["instrument_id"] == "ID1"
    assert row["ex_date"] == "2099-10-05"
    assert row["kind"] == "split"
    assert row.get("ratio") == 3.0
    eid1 = row["event_id"]
    assert len(eid1) == 16

    canonical, _ = build_canonical(
        [{"symbol": "SYM1", "effective_date": "2099-10-05", "kind": "split", "ratio": 3.0}],
        symbol_to_id,
    )
    assert len(canonical) == 1
    assert canonical[0]["event_id"] == eid1


def test_faz43_unresolved_symbol_canonical_errors(tmp_path: Path) -> None:
    """Action with symbol not in master -> canonical error count > 0."""
    from bist_core.services.corporate_actions_canon import build_canonical

    symbol_to_id = {"AAA": "ID1"}
    records = [
        {"symbol": "AAA", "effective_date": "2099-10-01", "kind": "other"},
        {"symbol": "UNKNOWN", "effective_date": "2099-10-02", "kind": "other"},
    ]
    canonical, errors = build_canonical(records, symbol_to_id)
    assert errors == 1
    assert len(canonical) == 1
    assert canonical[0]["instrument_id"] == "ID1"
