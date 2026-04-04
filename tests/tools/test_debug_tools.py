from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from bist_core.tools.debug_tools import inspect_comparison, inspect_ranking, inspect_symbol_state, validate_dataset


def _biz_days(start: date, count: int) -> list[str]:
    out: list[str] = []
    cur = start
    while len(out) < count:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _write_snapshots(root: Path) -> str:
    days = _biz_days(date(2025, 1, 2), 25)
    for i, day in enumerate(days):
        day_dir = root / day
        day_dir.mkdir(parents=True, exist_ok=True)

        asels_close = 100 + i * 2.0
        akfis_close = 50 + i * 0.35
        aefes_close = 80 - i * 0.9

        asels_vol = 1_000_000 + i * 60_000
        akfis_vol = 900_000 + i * 5_000
        aefes_vol = 1_100_000 - i * 20_000

        rows = [
            ("ASELS", asels_close - 1.0, asels_close + 1.2, asels_close - 1.5, asels_close, asels_vol),
            ("AKFIS", akfis_close - 0.4, akfis_close + 0.5, akfis_close - 0.6, akfis_close, akfis_vol),
            ("AEFES", aefes_close - 0.8, aefes_close + 0.4, aefes_close - 1.1, aefes_close, aefes_vol),
        ]

        lines = ["symbol,open,high,low,close,volume,turnover_tl"]
        for sym, o, h, l, c, v in rows:
            turnover = c * v
            lines.append(f"{sym},{o:.2f},{h:.2f},{l:.2f},{c:.2f},{int(v)},{turnover:.2f}")
        (day_dir / "snapshot.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return days[-1]


def test_inspect_symbol_state_returns_expected_structure(tmp_path: Path, monkeypatch) -> None:
    snap = tmp_path / "snapshots"
    _write_snapshots(snap)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snap))

    got = inspect_symbol_state("ASELS")

    assert got["status"] == "ok"
    assert got["symbol"] == "ASELS"
    assert isinstance(got["score_breakdown"], dict)
    assert isinstance(got["signals"], dict)
    assert "current_price_context" in got


def test_inspect_ranking_returns_sorted_ranking_and_dispersion(tmp_path: Path, monkeypatch) -> None:
    snap = tmp_path / "snapshots"
    _write_snapshots(snap)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snap))

    got = inspect_ranking(["ASELS", "AKFIS", "AEFES"])

    assert got["status"] == "ok"
    assert got["sorted_ranking"]
    assert got["score_dispersion"]["unique_scores"] >= 2
    assert isinstance(got["ranking_reasons"]["leader_reasons"], list)


def test_inspect_comparison_returns_matrix_and_reason(tmp_path: Path, monkeypatch) -> None:
    snap = tmp_path / "snapshots"
    _write_snapshots(snap)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snap))

    got = inspect_comparison(["ASELS", "AKFIS"])

    assert got["status"] == "ok"
    assert isinstance(got["comparison_matrix"], list)
    assert got["comparison_matrix"]
    assert got["leader_selection_reason"]["leader"] in {"ASELS", "AKFIS"}


def test_validate_dataset_returns_completeness_and_anomalies(tmp_path: Path, monkeypatch) -> None:
    snap = tmp_path / "snapshots"
    _write_snapshots(snap)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snap))

    got = validate_dataset("ASELS")

    assert got["status"] == "ok"
    assert isinstance(got["data_completeness"], dict)
    assert isinstance(got["missing_fields"], list)
    assert isinstance(got["anomalies"], list)


def test_tools_fail_closed_on_invalid_input(tmp_path: Path, monkeypatch) -> None:
    snap = tmp_path / "snapshots"
    _write_snapshots(snap)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snap))

    assert inspect_symbol_state("")["output"] == "INSUFFICIENT EVIDENCE"
    assert inspect_ranking([])["output"] == "INSUFFICIENT EVIDENCE"
    assert inspect_comparison(["ASELS"])["output"] == "INSUFFICIENT EVIDENCE"
    assert validate_dataset("MISSING")["output"] == "INSUFFICIENT EVIDENCE"
