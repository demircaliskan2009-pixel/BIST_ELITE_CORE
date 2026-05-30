from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import (
    EVENT_TIME_NS,
    accepted_replay_result,
    rejected_replay_result,
)


def test_phase33c_rejected_replay_result_does_not_produce_paper_feed_input() -> None:
    result = build_deribit_paper_feed_input(rejected_replay_result())

    assert result.accepted is False
    assert result.frame is None
    assert "deribit_paper_feed:replay_rejected" in result.rejection_reasons


def test_phase33c_missing_book_state_fails_closed() -> None:
    replay = accepted_replay_result()

    result = build_deribit_paper_feed_input(replace(replay, state=None))

    assert result.accepted is False
    assert result.frame is None
    assert "deribit_paper_feed:book_state_missing" in result.rejection_reasons


def test_phase33c_unhealthy_book_state_fails_closed() -> None:
    replay = accepted_replay_result()
    assert replay.state is not None
    unhealthy = replace(replay.state, healthy=False, rejection_reasons=("unit:book_rejected",))

    result = build_deribit_paper_feed_input(replace(replay, state=unhealthy))

    assert result.accepted is False
    assert result.frame is None
    assert "order_book:unhealthy" in result.rejection_reasons
    assert "unit:book_rejected" in result.rejection_reasons


def test_phase33c_stale_or_receive_lag_breached_state_fails_closed() -> None:
    replay = accepted_replay_result()

    result = build_deribit_paper_feed_input(replay, now_ns=EVENT_TIME_NS + 3_000_000_000)

    assert result.accepted is False
    assert result.frame is None
    assert "deribit_paper_feed:public_data_not_ready" in result.rejection_reasons
    assert "public_feed:stale" in result.rejection_reasons
    assert "public_feed:receive_lag_exceeded" in result.rejection_reasons


def test_phase33c_scope_contaminated_book_state_fails_closed() -> None:
    replay = accepted_replay_result()
    assert replay.state is not None
    contaminated = replace(replay.state, source="private-channel")

    result = build_deribit_paper_feed_input(replace(replay, state=contaminated))

    assert result.accepted is False
    assert result.frame is None
    assert "deribit_paper_feed:scope_contamination" in result.rejection_reasons
