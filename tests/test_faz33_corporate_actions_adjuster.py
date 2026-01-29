"""FAZ33: Corporate actions adjuster core; minimal schema; build_adjust_factors; deterministic."""
from __future__ import annotations

import json
from pathlib import Path

from bist_core.services import castore
from bist_core.services.adjustments import apply_close_adjustments, build_adjust_factors
from bist_core.services.eod_pipeline import run_eod_pipeline


def test_faz33_minimal_schema_ex_date_type(tmp_path: Path) -> None:
    """Parse actions with minimal schema: type, ex_date, ratio/amount, symbol."""
    path = tmp_path / "actions.jsonl"
    path.write_text(
        '{"symbol":"X","type":"split","ex_date":"2099-05-01","ratio":2.0,"source":"test"}\n'
        + '{"symbol":"Y","kind":"cash_dividend","effective_date":"2099-05-02","amount":1.5}\n',
        encoding="utf-8",
    )
    records, errors = castore.parse_actions(path)
    assert len(records) == 2
    assert records[0]["symbol"] == "X"
    assert records[0]["effective_date"] == "2099-05-01"
    assert records[0]["kind"] == "split"
    assert records[0]["ratio"] == 2.0
    assert records[1]["kind"] == "cash_dividend"
    assert records[1].get("cash") == 1.5


def test_faz33_build_adjust_factors_split_deterministic() -> None:
    """build_adjust_factors: split => factor 2.0 for dates before ex_date; deterministic order."""
    series = [
        {"symbol": "A", "date": "2099-06-01"},
        {"symbol": "A", "date": "2099-06-02"},
        {"symbol": "A", "date": "2099-06-03"},
    ]
    actions = [
        {"symbol": "A", "effective_date": "2099-06-02", "kind": "split", "ratio": 2.0},
    ]
    factors_list, notes = build_adjust_factors(series, actions)
    assert len(factors_list) == 3
    by_date = {(r["symbol"], r["date"]): r["factor"] for r in factors_list}
    assert by_date[("A", "2099-06-01")] == 2.0
    assert by_date[("A", "2099-06-02")] == 1.0
    assert by_date[("A", "2099-06-03")] == 1.0
    assert factors_list == sorted(factors_list, key=lambda r: (r["symbol"], r["date"]))


def test_faz33_build_adjust_factors_reverse_split_and_bedelsiz() -> None:
    """reverse_split divides factor; bonus_issue (bedelsiz) multiplies factor."""
    series = [
        {"symbol": "B", "date": "2099-07-01"},
        {"symbol": "B", "date": "2099-07-02"},
    ]
    actions = [
        {"symbol": "B", "effective_date": "2099-07-02", "kind": "reverse_split", "ratio": 10.0},
    ]
    factors_list, _ = build_adjust_factors(series, actions)
    by_date = {(r["symbol"], r["date"]): r["factor"] for r in factors_list}
    assert by_date[("B", "2099-07-01")] == 0.1
    assert by_date[("B", "2099-07-02")] == 1.0

    series2 = [{"symbol": "C", "date": "2099-08-01"}]
    actions2 = [
        {"symbol": "C", "effective_date": "2099-08-02", "kind": "bonus_issue", "ratio": 1.5},
    ]
    factors2, _ = build_adjust_factors(series2, actions2)
    assert factors2[0]["factor"] == 1.5


def test_faz33_cash_dividend_placeholder() -> None:
    """cash_dividend: factor 1.0; note placeholder."""
    series = [{"symbol": "D", "date": "2099-09-01"}]
    actions = [
        {"symbol": "D", "effective_date": "2099-09-02", "kind": "cash_dividend", "cash": 0.5},
    ]
    factors_list, notes = build_adjust_factors(series, actions)
    assert factors_list[0]["factor"] == 1.0
    assert any("cash_dividend" in str(n) for n in notes)


def test_faz33_apply_close_using_factors_deterministic() -> None:
    """apply_close_adjustments with synthetic series + actions; deterministic adjusted close."""
    bars = [
        {"symbol": "E", "date": "2099-10-01", "close": 100.0},
        {"symbol": "E", "date": "2099-10-02", "close": 110.0},
        {"symbol": "E", "date": "2099-10-03", "close": 105.0},
    ]
    actions = [
        {"symbol": "E", "effective_date": "2099-10-02", "kind": "split", "ratio": 2.0},
    ]
    adjusted, _ = apply_close_adjustments(bars, actions)
    assert len(adjusted) == 3
    assert adjusted[0]["close"] == 50.0
    assert adjusted[1]["close"] == 110.0
    assert adjusted[2]["close"] == 105.0
    adjusted2, _ = apply_close_adjustments(bars, actions)
    assert adjusted == adjusted2


def test_faz33_pipeline_writes_corporate_actions_manifest_and_factors_path(tmp_path: Path) -> None:
    """Pipeline with CA: writes corporate_actions_manifest + factors path when snapshot exists."""
    day_str = "2099-11-01"
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True)
    (snapshot_root / day_str).mkdir(parents=True)
    (snapshot_root / day_str / "snapshot.csv").write_text(
        "symbol,close\nG,10.0\nH,20.0\n",
        encoding="utf-8",
    )
    ca_input_file = tmp_path / "ca_input.jsonl"
    ca_input_file.write_text(
        '{"symbol":"G","type":"split","ex_date":"2099-11-02","ratio":2.0}\n',
        encoding="utf-8",
    )
    ca_dir = tmp_path / "ca" / day_str
    ca_dir.mkdir(parents=True)
    outdir = tmp_path / "run"
    outdir.mkdir(parents=True)
    manifest, code = run_eod_pipeline(
        day_str,
        snapshot_root,
        outdir,
        strict=False,
        ignore_calendar=True,
        ca_provider="offline_file",
        ca_input=str(ca_input_file),
        ca_outdir=ca_dir,
    )
    assert code == 0
    ca_manifest = manifest.get("corporate_actions_manifest")
    assert ca_manifest is not None
    factors_path_str = ca_manifest.get("factors_path")
    assert factors_path_str
    factors_path = Path(factors_path_str)
    assert factors_path.is_file()
    data = json.loads(factors_path.read_text(encoding="utf-8"))
    assert data.get("day") == day_str
    assert "factors" in data
    factors_list = data["factors"]
    assert len(factors_list) >= 2
    by_sym = {r["symbol"]: r["factor"] for r in factors_list}
    assert by_sym.get("G") == 2.0
    assert by_sym.get("H") == 1.0
