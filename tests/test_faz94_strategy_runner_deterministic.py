"""FAZ94: Strategy runner — offline bars + signals -> strategy_report.json; deterministic."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path


from bist_core.models import EODBar, PriceBand
from bist_core.strategy.runner import run, write_strategy_report


def _make_bars(symbol: str, day: str, count: int = 25, base_close: float = 100.0) -> list[EODBar]:
    """Build count bars ending on day (date-ordered); last bar has date=day."""
    d = date.fromisoformat(day)
    bars: list[EODBar] = []
    for i in range(count):
        # Simulate history: dates before day
        from datetime import timedelta

        bar_date = d - timedelta(days=count - 1 - i)
        close = base_close + (i * 0.5)  # Slight uptrend for momentum
        bars.append(
            EODBar(
                symbol=symbol,
                date=bar_date,
                close=close,
                high=close * 1.02,
                low=close * 0.98,
                volume=1_000_000,
                turnover_tl=int(close * 1_000_000),
            )
        )
    return bars


def _default_bands() -> list[PriceBand]:
    return [
        PriceBand(
            price_min=0.01,
            price_max=1_000_000.0,
            tick=0.01,
            up_limit_pct=20.0,
            down_limit_pct=20.0,
        )
    ]


def _default_strat_cfg() -> dict:
    return {
        "mom_fast": 5,
        "mom_slow": 20,
        "vol_window": 20,
        "mom_weight": 1.0,
        "kap_weight": 1.0,
        "vol_weight": 0.5,
        "score_buy": 1.5,
        "score_watch": 0.5,
    }


def test_faz94_run_deterministic() -> None:
    """Same offline bars + config -> same strategy report."""
    day = "2025-01-15"
    bars = _make_bars("ASELS", day) + _make_bars("THYAO", day, base_close=50.0)
    bands = _default_bands()
    strat_cfg = _default_strat_cfg()

    report1 = run(bars, bands, strat_cfg)
    report2 = run(bars, bands, strat_cfg)
    assert report1 == report2
    assert report1["schema_version"] == 1
    assert report1["day"] == day
    assert "decisions" in report1
    assert "summary" in report1
    assert report1["summary"]["symbols"] == ["ASELS", "THYAO"]


def test_faz94_strategy_report_json_deterministic(tmp_path: Path) -> None:
    """Same report written twice -> byte-identical strategy_report.json."""
    day = "2025-01-20"
    bars = _make_bars("X", day)
    bands = _default_bands()
    strat_cfg = _default_strat_cfg()
    report = run(bars, bands, strat_cfg)

    p1 = tmp_path / "out1" / "strategy_report.json"
    p2 = tmp_path / "out2" / "strategy_report.json"
    write_strategy_report(p1, report)
    write_strategy_report(p2, report)
    h1 = hashlib.sha256(p1.read_bytes()).hexdigest()
    h2 = hashlib.sha256(p2.read_bytes()).hexdigest()
    assert h1 == h2


def test_faz94_report_has_decisions_and_signals() -> None:
    """Report decisions include signals (mom, news, vol) when scored."""
    day = "2025-02-01"
    bars = _make_bars("ASELS", day)
    bands = _default_bands()
    strat_cfg = _default_strat_cfg()
    report = run(bars, bands, strat_cfg)

    assert len(report["decisions"]) >= 1
    for d in report["decisions"]:
        assert "symbol" in d
        assert "decision" in d
        assert "decision_raw" in d
        if d.get("reason") is None and d.get("score") is not None:
            assert "signals" in d
            sig = d["signals"]
            assert "mom" in sig
            assert "news" in sig
            assert "vol" in sig


def test_faz94_write_strategy_report_readback(tmp_path: Path) -> None:
    """write_strategy_report then read back -> same content."""
    bars = _make_bars("A", "2025-03-01")
    report = run(bars, _default_bands(), _default_strat_cfg())
    out = tmp_path / "strategy_report.json"
    write_strategy_report(out, report)
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == report["schema_version"]
    assert loaded["day"] == report["day"]
    assert loaded["summary"]["symbols"] == report["summary"]["symbols"]
