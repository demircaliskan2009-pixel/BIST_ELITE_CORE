from __future__ import annotations

import datetime as dt
from pathlib import Path

from bist_core.services import advisor as advisor_mod


def test_iter_available_snapshot_dates_reads_sorted_dates(tmp_path: Path) -> None:
    snap = tmp_path / "eod" / "snapshots"
    (snap / "2025-12-16").mkdir(parents=True)
    (snap / "2025-12-10").mkdir(parents=True)
    (snap / "junk").mkdir(parents=True)

    got = advisor_mod._iter_available_snapshot_dates(tmp_path)
    assert [str(x) for x in got] == ["2025-12-10", "2025-12-16"]


def test_resolve_effective_snapshot_date_falls_back_to_latest_lte(tmp_path: Path) -> None:
    snap = tmp_path / "eod" / "snapshots"
    (snap / "2025-12-10").mkdir(parents=True)
    (snap / "2025-12-16").mkdir(parents=True)

    got = advisor_mod._resolve_effective_snapshot_date("2026-03-14", root=tmp_path)
    assert str(got) == "2025-12-16"


def test_resolve_effective_snapshot_date_returns_exact_when_present(tmp_path: Path) -> None:
    snap = tmp_path / "eod" / "snapshots"
    (snap / "2026-03-14").mkdir(parents=True)
    (snap / "2025-12-16").mkdir(parents=True)

    got = advisor_mod._resolve_effective_snapshot_date(dt.date(2026, 3, 14), root=tmp_path)
    assert str(got) == "2026-03-14"


def test_public_chat_entrypoint_still_returns_contract_after_asof_fallback() -> None:
    got = advisor_mod.build_chat_response_for_text(
        "scan top 2",
        "2026-03-14",
        known_symbols=["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"],
        scan_universe=["ASELS", "AKBNK", "GARAN"],
    )
    assert got["route"] == "scan"
    assert isinstance(got["text"], str) and got["text"].strip()
