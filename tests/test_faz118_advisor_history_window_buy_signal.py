"""
FAZ118-STEP1: Advisor momentum/volume sinyalleri için rolling window.
25 gün snapshot ile yükseliş trendi + volume spike -> BUY kararı ve plan.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path


from bist_core.services.advisor import build_advice_for_symbol


def _make_snapshot_row(symbol: str, d: date, close: float, volume: int) -> str:
    high = close * 1.02
    low = close * 0.98
    open_ = (high + low) / 2
    return f"{symbol},{open_:.2f},{high:.2f},{low:.2f},{close:.2f},{volume}\n"


def test_faz118_advisor_history_window_buy_signal(tmp_path: Path) -> None:
    """
    25 gün snapshot (open,high,low,close,volume).
    Son gün: close yükseliş trendi + volume spike.
    build_advice_for_symbol -> decision_raw == BUY, plan(entry/stop/t1) not None.
    """
    snap_root = tmp_path / "snap"
    base = date(2099, 1, 1)

    # 25 gün: ilk 15 gün düşük fiyat (90-95), son 10 gün yükseliş (96-105)
    # mom_fast=5, mom_slow=20 -> son 5 gün MA > son 20 gün MA için yeterli
    # vol_window=20 -> son gün hacim spike (1.5x ortalama)
    for i in range(25):
        d = base + timedelta(days=i)
        day_dir = snap_root / d.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)

        if i < 15:
            close = 90.0 + i * 0.3  # 90.0 - 94.2
            volume = 100_000
        elif i < 24:
            close = 96.0 + (i - 15) * 1.0  # 96 - 104
            volume = 100_000
        else:
            # Son gün: yüksek close + volume spike
            close = 105.0
            volume = 250_000  # 2.5x ortalama -> vol_signal=1

        header = "symbol,open,high,low,close,volume\n"
        row = _make_snapshot_row("AAA", d, close, volume)
        (day_dir / "snapshot.csv").write_text(header + row, encoding="utf-8")

    last_day = base + timedelta(days=24)

    advice = build_advice_for_symbol("AAA", last_day.isoformat(), root=snap_root)

    assert advice.decision_raw == "BUY", (
        f"Expected BUY, got {advice.decision_raw}; score={advice.score}; text={advice.text[:200]}"
    )
    assert advice.plan is not None
    assert advice.plan.get("entry") is not None
    assert advice.plan.get("stop") is not None
    assert advice.plan.get("t1") is not None
