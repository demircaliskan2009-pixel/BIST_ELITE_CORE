from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_public_feed_adapter import (
    DERIBIT_PUBLIC_BOOK_CHANNEL,
    DERIBIT_PUBLIC_PROD_WS_URL,
    DeribitPublicFeedSmokeRequest,
    build_deribit_public_feed_smoke_plan,
)


def test_phase28e_manual_smoke_plan_requires_explicit_bounded_public_request(tmp_path: Path) -> None:
    request = DeribitPublicFeedSmokeRequest(
        ws_url=DERIBIT_PUBLIC_PROD_WS_URL,
        channel=DERIBIT_PUBLIC_BOOK_CHANNEL,
        timeout_seconds=30,
        max_events=25,
        artifact_path=str(tmp_path / "deribit_public_smoke.json"),
    )

    plan = build_deribit_public_feed_smoke_plan(request)

    assert plan.accepted is True
    assert plan.network_auto_start is False
    assert plan.rejection_reasons == ()
    assert plan.subscription_message == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "public/subscribe",
        "params": {"channels": [DERIBIT_PUBLIC_BOOK_CHANNEL]},
    }


def test_phase28e_manual_smoke_plan_rejects_unbounded_or_implicit_network_use(tmp_path: Path) -> None:
    request = DeribitPublicFeedSmokeRequest(
        ws_url="wss://example.invalid/private",
        channel=DERIBIT_PUBLIC_BOOK_CHANNEL,
        timeout_seconds=120,
        max_events=101,
        artifact_path="relative.json",
        dry_run=False,
    )

    plan = build_deribit_public_feed_smoke_plan(request)

    assert plan.accepted is False
    assert plan.network_auto_start is False
    assert "deribit_public_feed:ws_url_not_approved_public" in plan.rejection_reasons
    assert "deribit_public_feed:timeout_invalid" in plan.rejection_reasons
    assert "deribit_public_feed:max_events_invalid" in plan.rejection_reasons
    assert "deribit_public_feed:artifact_path_must_be_explicit" in plan.rejection_reasons
    assert "deribit_public_feed:dry_run_required" in plan.rejection_reasons
