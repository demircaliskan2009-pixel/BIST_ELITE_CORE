from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from bist_core.services.advisor import _overlay_live_bridge_context, _render_advice_text
from bist_core.vendors.ideal_bridge_runtime import clear_bridge_runtime_cache, get_live_bridge_row


def _write_bridge_csv(p: Path) -> None:
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "has_g",
                "has_60",
                "has_05",
                "has_01",
                "current_close_source",
                "current_close",
                "g_open",
                "g_high",
                "g_low",
                "g_close",
                "g_volume",
                "g_turnover_tl",
                "close_60",
                "close_05",
                "close_01",
                "ts_code_g",
                "ts_code_60",
                "ts_code_05",
                "ts_code_01",
                "delta_current_vs_g_close_pct",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "symbol": "ASELS",
                "has_g": "True",
                "has_60": "True",
                "has_05": "True",
                "has_01": "True",
                "current_close_source": "01",
                "current_close": "101.5",
                "g_open": "100",
                "g_high": "102",
                "g_low": "99",
                "g_close": "100.0",
                "g_volume": "1000000",
                "g_turnover_tl": "100000000",
                "close_60": "101.2",
                "close_05": "101.4",
                "close_01": "101.5",
                "ts_code_g": "778060",
                "ts_code_60": "333618",
                "ts_code_05": "20017085",
                "ts_code_01": "20017085",
                "delta_current_vs_g_close_pct": "1.5",
            }
        )


def test_runtime_bridge_loader(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "bridge.csv"
    _write_bridge_csv(p)
    monkeypatch.setenv("BIST_CORE_IDEAL_BRIDGE_CSV", str(p))
    clear_bridge_runtime_cache()

    row = get_live_bridge_row("ASELS")
    assert row is not None
    assert row["symbol"] == "ASELS"
    assert row["current_close_source"] == "01"


def test_overlay_live_bridge_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "bridge.csv"
    _write_bridge_csv(p)
    monkeypatch.setenv("BIST_CORE_IDEAL_BRIDGE_CSV", str(p))
    clear_bridge_runtime_cache()

    result = {
        "signals": {"mom": 1, "news": 0, "vol": 0},
        "plan": {"entry": 100.0, "stop": 97.0, "t1": 105.0},
    }
    out = _overlay_live_bridge_context(result, "ASELS")

    assert out["plan"]["current_close"] == pytest.approx(101.5)
    assert out["plan"]["live_current_close_source"] == "01"
    assert out["plan"]["live_vs_g_close_pct"] == pytest.approx(1.5)
    assert out["signals"]["live_vs_g_close_pct"] == pytest.approx(1.5)


def test_render_advice_text_mentions_live_bridge() -> None:
    txt = _render_advice_text(
        "ASELS",
        date(2026, 3, 12),
        "WATCH",
        1.0,
        {
            "mom": 1,
            "news": 0,
            "vol": 0,
            "live_current_close_source": "01",
            "live_vs_g_close_pct": 1.5,
        },
        {
            "entry": 100.0,
            "stop": 97.0,
            "t1": 105.0,
            "current_close": 101.5,
            "entry_status": "extended_above_entry",
            "live_current_close_source": "01",
            "live_vs_g_close_pct": 1.5,
        },
        True,
        [],
        [],
    )
    assert "Canlı fiyat (01) 101.5" in txt
    assert "Canlı/EOD farkı +1.50%" in txt
