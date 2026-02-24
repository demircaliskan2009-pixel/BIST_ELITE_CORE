from __future__ import annotations

from pathlib import Path

from bist_core.broker.manual import ManualBroker


def test_manual_broker_submit_order_ticket_valid(tmp_path: Path) -> None:
    broker = ManualBroker()
    ticket = tmp_path / "order_ticket_h3.txt"
    ticket.write_text("dummy ticket", encoding="utf-8")

    meta = broker.submit_order_ticket(str(ticket), day="2025-01-15")

    assert meta["broker"] == "manual"
    assert meta["day"] == "2025-01-15"
    assert meta["mode"] == "offline_manual"
    assert "instructions" in meta
    assert "order ticket" in str(meta["instructions"]).lower()
    assert Path(meta["ticket_path"]).is_file()


def test_manual_broker_submit_order_ticket_missing_file(tmp_path: Path) -> None:
    broker = ManualBroker()
    missing = tmp_path / "missing_ticket.txt"

    try:
        broker.submit_order_ticket(str(missing), day="2025-01-15")
    except FileNotFoundError as e:
        assert "order ticket not found" in str(e)
    else:
        raise AssertionError("expected FileNotFoundError for missing ticket")


def test_manual_broker_fetch_fills_requires_path() -> None:
    broker = ManualBroker()
    try:
        broker.fetch_fills(day="2025-01-15", fills_path=None)
    except ValueError as e:
        assert "fills_path is required" in str(e)
    else:
        raise AssertionError("expected ValueError when fills_path is None")


def test_manual_broker_fetch_fills_valid(tmp_path: Path) -> None:
    broker = ManualBroker()
    fills = tmp_path / "fills.csv"
    fills.write_text("dummy,fills\n", encoding="utf-8")

    resolved = broker.fetch_fills(day="2025-01-15", fills_path=str(fills))

    resolved_path = Path(resolved)
    assert resolved_path.is_file()
    assert resolved_path.samefile(fills)

