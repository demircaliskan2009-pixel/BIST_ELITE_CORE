"""FAZ104: Eventstore as-of guard — future-dated events dropped and reported."""
from __future__ import annotations

from pathlib import Path

from bist_core.services import eventstore


def test_faz104_future_ts_dropped_and_leakage_in_errors(tmp_path: Path) -> None:
    """load_events_for_symbol_day: only day event returned; errors contains EventLeakage:future_ts."""
    base = tmp_path / "events"
    day = "2024-01-15"
    day_plus_one = "2024-01-16"
    symbol = "X"
    day_dir = base / day
    day_dir.mkdir(parents=True)
    lines = [
        '{"symbol":"' + symbol + '","ts":"' + day + 'T10:00:00Z","kind":"KAP","title":"OnDay"}',
        '{"symbol":"' + symbol + '","ts":"' + day_plus_one + 'T09:00:00Z","kind":"KAP","title":"Future"}',
    ]
    (day_dir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    events, errors = eventstore.load_events_for_symbol_day(symbol, day, base_dir=base)

    assert len(events) == 1, "future event must be dropped"
    assert events[0].ts.startswith(day)
    assert events[0].title == "OnDay"
    assert any("EventLeakage:future_ts" in e for e in errors)
