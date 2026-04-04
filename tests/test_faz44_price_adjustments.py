"""
FAZ44: Build adjusted prices from snapshot + canonical corporate actions.
Tiny 2-day example verifying adj_factor and close_adj math; fail-closed for unknown kind.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


from bist_core.services import price_adjust


def test_faz44_two_day_adj_factor_math(tmp_path: Path) -> None:
    """2-day snapshot + split and cash_dividend; verify close_adj and adj_factor."""
    day1, day2 = "2024-01-01", "2024-01-02"
    snapshot_root = tmp_path / "snap"
    snapshot_root.mkdir()
    (snapshot_root / day1).mkdir()
    (snapshot_root / day2).mkdir()

    # Snapshot: A close 100 on day1, 60 on day2 (post-split); B close 50 on day1, 49 on day2 (post-div)
    for day, rows in (
        (day1, [{"symbol": "A", "close": 100.0}, {"symbol": "B", "close": 50.0}]),
        (day2, [{"symbol": "A", "close": 60.0}, {"symbol": "B", "close": 49.0}]),
    ):
        path = snapshot_root / day / "snapshot.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["symbol", "close"])
            w.writeheader()
            w.writerows(rows)

    # Canonical actions: A split ex_date day2 ratio 2; B cash_dividend ex_date day2 cash 1.0
    canon_path = tmp_path / "actions_canonical.jsonl"
    actions = [
        {"instrument_id": "id_a", "ex_date": day2, "kind": "split", "ratio": 2.0},
        {"instrument_id": "id_b", "ex_date": day2, "kind": "cash_dividend", "cash": 1.0},
    ]
    with canon_path.open("w", encoding="utf-8") as f:
        for a in actions:
            f.write(json.dumps(a) + "\n")

    symbol_to_id = {"A": "id_a", "B": "id_b"}
    out_dir = tmp_path / "out"
    err_count, notes = price_adjust.build_adjusted_prices(
        snapshot_root=snapshot_root,
        days=[day1, day2],
        canonical_actions_path=canon_path,
        symbol_to_id=symbol_to_id,
        out_dir=out_dir,
        strict=False,
    )
    assert err_count == 0, notes

    # prices_raw: instrument_id, date, close
    raw_path = out_dir / "prices_raw.csv"
    assert raw_path.is_file()
    with raw_path.open(newline="", encoding="utf-8") as f:
        raw_rows = list(csv.DictReader(f))
    raw_by_key = {(r["instrument_id"], r["date"]): float(r["close"]) for r in raw_rows}
    assert raw_by_key[("id_a", day1)] == 100.0
    assert raw_by_key[("id_a", day2)] == 60.0
    assert raw_by_key[("id_b", day1)] == 50.0
    assert raw_by_key[("id_b", day2)] == 49.0

    # prices_adj: close_adj = (close - cash_subtract) / ratio_factor; adj_factor = ratio_factor
    # Day1 id_a: only action ex_date day2 > day1 -> ratio_factor = 1/2 = 0.5 -> close_adj = 100/0.5 = 200, adj_factor 0.5
    # Day2 id_a: no future actions -> close_adj = 60, adj_factor 1
    # Day1 id_b: cash_dividend ex_date day2 -> cash_subtract=1, ratio_factor=1 -> close_adj = (50-1)/1 = 49, adj_factor 1
    # Day2 id_b: no future actions -> close_adj = 49, adj_factor 1
    adj_path = out_dir / "prices_adj.csv"
    assert adj_path.is_file()
    with adj_path.open(newline="", encoding="utf-8") as f:
        adj_rows = list(csv.DictReader(f))
    adj_by_key = {(r["instrument_id"], r["date"]): (float(r["close_adj"]), float(r["adj_factor"])) for r in adj_rows}
    assert adj_by_key[("id_a", day1)] == (200.0, 0.5)
    assert adj_by_key[("id_a", day2)] == (60.0, 1.0)
    assert adj_by_key[("id_b", day1)] == (49.0, 1.0)
    assert adj_by_key[("id_b", day2)] == (49.0, 1.0)


def test_faz44_strict_unknown_kind_fail_closed(tmp_path: Path) -> None:
    """Unknown action kind with strict=True yields error and note."""
    day1 = "2024-01-01"
    snapshot_root = tmp_path / "snap"
    snapshot_root.mkdir()
    (snapshot_root / day1).mkdir()
    path = snapshot_root / day1 / "snapshot.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=["symbol", "close"]).writeheader()
        csv.DictWriter(f, fieldnames=["symbol", "close"]).writerow({"symbol": "X", "close": 10.0})

    canon_path = tmp_path / "actions_canonical.jsonl"
    with canon_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"instrument_id": "id_x", "ex_date": "2024-01-02", "kind": "unknown_thing"}) + "\n")

    symbol_to_id = {"X": "id_x"}
    out_dir = tmp_path / "out"
    err_count, notes = price_adjust.build_adjusted_prices(
        snapshot_root=snapshot_root,
        days=[day1],
        canonical_actions_path=canon_path,
        symbol_to_id=symbol_to_id,
        out_dir=out_dir,
        strict=True,
    )
    assert err_count > 0
    assert any("unknown_kind:unknown_thing" in n for n in notes)
