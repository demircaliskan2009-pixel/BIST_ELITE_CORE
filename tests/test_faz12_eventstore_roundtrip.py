from __future__ import annotations

from pathlib import Path

from bist_core.services import eventstore


def test_eventstore_roundtrip(tmp_path: Path) -> None:
    base = tmp_path / "data" / "events"
    day_dir = base / "2099-01-01"
    day_dir.mkdir(parents=True)
    (day_dir / "events.jsonl").write_text(
        "\n".join(
            [
                '{"symbol":"AAA","ts":"2099-01-01T10:00:00","kind":"KAP","title":"AAA-1"}',
                '{"symbol":"AAA","ts":"2099-01-01T12:00:00","kind":"KAP","title":"AAA-2"}',
                '{"symbol":"BBB","ts":"2099-01-01T09:00:00","kind":"KAP","title":"BBB-1"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    events, errors = eventstore.load_events_for_symbol_day(
        "AAA", "2099-01-01", base_dir=base
    )
    assert not errors
    assert len(events) == 2
    assert events[0].title == "AAA-2"
    assert events[1].title == "AAA-1"
