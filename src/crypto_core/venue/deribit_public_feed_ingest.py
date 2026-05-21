from __future__ import annotations

from dataclasses import dataclass

from crypto_core.data.public_feed_ingest import PublicFeedIngestPlan, PublicFeedIngestResult, ingest_public_feed_events
from crypto_core.data.public_feed_policy import PublicFeedPolicy
from crypto_core.data.public_feed_source import PublicFeedBatch, PublicFeedSubscription, RawPublicFeedEnvelope
from crypto_core.venue.contracts import OrderBookSnapshot, PublicFeedHealth, PublicMarketDataEvent
from crypto_core.venue.deribit_public_data_quality import DeribitPublicDataQualityResult
from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, DERIBIT_PUBLIC_BOOK_DIALECT_ID
from crypto_core.venue.public_feed_dialects import get_public_feed_dialect

DERIBIT_PUBLIC_FEED_INGEST_WIRING_ID = "deribit_public_feed_ingest_wiring_v1"


@dataclass(frozen=True)
class DeribitPublicFeedIngestResult:
    accepted: bool
    ingest_plan: PublicFeedIngestPlan | None
    ingest_result: PublicFeedIngestResult | None
    rejection_reasons: tuple[str, ...]


def ingest_deribit_public_data_quality_result(
    quality_result: object,
    *,
    now_ns: int | None = None,
) -> DeribitPublicFeedIngestResult:
    if not isinstance(quality_result, DeribitPublicDataQualityResult):
        return _result(None, None, ("deribit_public_feed_ingest:quality_result_malformed",))

    reasons = list(_quality_result_rejection_reasons(quality_result))
    if now_ns is not None and not _positive_int(now_ns):
        reasons.append("deribit_public_feed_ingest:now_ns_invalid")
    if reasons:
        return _result(None, None, reasons)

    plan, plan_reasons = _build_ingest_plan(quality_result)
    reasons.extend(plan_reasons)
    if plan is None:
        return _result(None, None, reasons)

    assert quality_result.market_event is not None
    batch = _build_batch(quality_result.market_event, plan.subscription)
    effective_now_ns = now_ns if _positive_int(now_ns) else quality_result.market_event.receive_time_ns
    ingest_result = ingest_public_feed_events(plan, batch, (quality_result.market_event,), now_ns=effective_now_ns)

    if ingest_result.accepted is not True:
        reasons.append("deribit_public_feed_ingest:ingest_rejected")
        reasons.extend(ingest_result.rejection_reasons)
    if ingest_result.readiness_snapshot.replay_ready is not True:
        reasons.append("deribit_public_feed_ingest:replay_not_ready")
    if ingest_result.readiness_snapshot.order_book_ready is True:
        reasons.append("deribit_public_feed_ingest:order_book_state_out_of_scope")
    if ingest_result.readiness_snapshot.accepted_for_paper is True:
        reasons.append("deribit_public_feed_ingest:paper_readiness_out_of_scope")

    return _result(plan, ingest_result, reasons)


def _quality_result_rejection_reasons(quality_result: DeribitPublicDataQualityResult) -> tuple[str, ...]:
    reasons: list[str] = []
    if quality_result.accepted is not True:
        reasons.append("deribit_public_feed_ingest:quality_gate_rejected")
        reasons.extend(quality_result.rejection_reasons)
    if not isinstance(quality_result.market_event, PublicMarketDataEvent):
        reasons.append("deribit_public_feed_ingest:market_event_missing")
    if not isinstance(quality_result.public_feed_health, PublicFeedHealth):
        reasons.append("deribit_public_feed_ingest:public_feed_health_missing")
    elif quality_result.public_feed_health.healthy is not True or quality_result.public_feed_health.rejection_reasons:
        reasons.append("deribit_public_feed_ingest:public_feed_health_rejected")
    if quality_result.order_book_snapshot is not None and quality_result.order_book_delta is not None:
        reasons.append("deribit_public_feed_ingest:book_contract_ambiguous")
    if quality_result.order_book_snapshot is None and quality_result.order_book_delta is None:
        reasons.append("deribit_public_feed_ingest:book_contract_missing")

    event = quality_result.market_event
    health = quality_result.public_feed_health
    if isinstance(event, PublicMarketDataEvent) and isinstance(health, PublicFeedHealth):
        if health.venue_id != event.venue_id or health.symbol != event.symbol or health.feed_type != event.feed_type:
            reasons.append("deribit_public_feed_ingest:quality_event_health_mismatch")
    return tuple(dict.fromkeys(reasons))


def _build_ingest_plan(
    quality_result: DeribitPublicDataQualityResult,
) -> tuple[PublicFeedIngestPlan | None, tuple[str, ...]]:
    try:
        spec = get_public_feed_dialect(DERIBIT_PUBLIC_BOOK_DIALECT_ID)
    except ValueError:
        return None, ("deribit_public_feed_ingest:dialect_not_ready",)

    depth = _subscription_depth(quality_result.order_book_snapshot)
    if depth is None:
        return None, ("deribit_public_feed_ingest:channel_depth_unresolved",)

    assert quality_result.market_event is not None
    event = quality_result.market_event
    base_id = f"{DERIBIT_PUBLIC_FEED_INGEST_WIRING_ID}:{event.symbol}:{event.feed_type.value}"
    subscription = PublicFeedSubscription(
        subscription_id=f"{base_id}:subscription",
        venue_id=event.venue_id,
        symbol=event.symbol,
        canonical_symbol=event.canonical_symbol,
        feed_type=event.feed_type,
        depth=depth,
        enabled=True,
        created_at_ns=event.receive_time_ns,
    )
    return (
        PublicFeedIngestPlan(
            plan_id=f"{base_id}:plan",
            policy=PublicFeedPolicy(
                venue_id=event.venue_id,
                symbol=event.symbol,
                canonical_symbol=event.canonical_symbol,
                feed_type=event.feed_type,
                max_staleness_ns=spec.max_staleness_ns,
                max_receive_lag_ns=spec.max_receive_lag_ns,
                require_replay_cursor=True,
                require_order_book=True,
                reject_on_gap=True,
                reject_on_resync=True,
                reject_on_stale=True,
            ),
            subscription=subscription,
            max_receive_lag_ns=spec.max_receive_lag_ns,
            require_batch_ready=True,
            require_replay_ready=True,
            require_public_data_ready=False,
        ),
        (),
    )


def _build_batch(event: PublicMarketDataEvent, subscription: PublicFeedSubscription) -> PublicFeedBatch:
    base_id = f"{DERIBIT_PUBLIC_FEED_INGEST_WIRING_ID}:{event.symbol}:{event.feed_type.value}:seq:{event.sequence_id}"
    return PublicFeedBatch(
        batch_id=f"{base_id}:batch",
        subscription=subscription,
        envelopes=(
            RawPublicFeedEnvelope(
                envelope_id=f"{base_id}:envelope",
                subscription_id=subscription.subscription_id,
                venue_id=event.venue_id,
                symbol=event.symbol,
                canonical_symbol=event.canonical_symbol,
                feed_type=event.feed_type,
                event_time_ns=event.event_time_ns,
                receive_time_ns=event.receive_time_ns,
                sequence_id=event.sequence_id,
                payload_hash=event.payload_hash,
                raw_payload_ref=event.raw_payload_ref,
                normalized=event.normalized,
                rejection_reasons=(),
            ),
        ),
        created_at_ns=event.receive_time_ns,
        rejection_reasons=(),
    )


def _subscription_depth(snapshot: OrderBookSnapshot | None) -> int | None:
    parts = DERIBIT_PUBLIC_BOOK_CHANNEL.split(".")
    if len(parts) >= 4:
        try:
            depth = int(parts[3])
        except ValueError:
            depth = None
        if _positive_int(depth):
            return depth
    if isinstance(snapshot, OrderBookSnapshot) and _positive_int(snapshot.depth):
        return snapshot.depth
    return None


def _result(
    ingest_plan: PublicFeedIngestPlan | None,
    ingest_result: PublicFeedIngestResult | None,
    reasons: tuple[str, ...] | list[str],
) -> DeribitPublicFeedIngestResult:
    normalized_reasons = tuple(dict.fromkeys(reasons))
    return DeribitPublicFeedIngestResult(
        accepted=normalized_reasons == () and ingest_result is not None and ingest_result.accepted is True,
        ingest_plan=ingest_plan,
        ingest_result=ingest_result,
        rejection_reasons=normalized_reasons,
    )


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


__all__ = [
    "DERIBIT_PUBLIC_FEED_INGEST_WIRING_ID",
    "DeribitPublicFeedIngestResult",
    "ingest_deribit_public_data_quality_result",
]
