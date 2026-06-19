"""Paper session realized-PnL bridge — deterministic, paper-only audit bridge from a session sequence
to a provenance-bound realized-PnL rollup.

A small, immutable, fail-closed *bridge artifact* that binds an existing digest-verified
``PaperSessionSequenceResult`` (the paper session/episode context) to a provenance-bound
``PaperRealizedPnlRollup`` built from realized-PnL provenance bundles, emitting one frozen, digest-bound
``PaperSessionRealizedPnlBridge``. It introduces no new economics: it builds the rollup via the merged
PUBLIC ``build_paper_realized_pnl_rollup`` (which re-proves the full upstream provenance of every realized
event) and copies the rollup's already-computed gross totals/counts — it performs no Decimal arithmetic
of its own. It is gross only: no fees, no unrealized PnL, no total PnL, no equity/capital/margin/balance;
it reserves/mutates no capital; routes no order; creates no venue/exchange/client order id / route id /
execution instruction; calls no live/private API; schedules nothing; runs no auto-loop; and touches no
connector/scheduler/runtime/venue/execution/service/session/data/portfolio/orchestrator/temporal
surface, no Deribit, no BIST.

Binding semantics: the supplied ``PaperSessionSequenceResult`` is re-proven via its PUBLIC
``paper_session_sequence_result_digest`` (mismatch fails closed), re-proven paper-safe (status COMPUTED,
every negative attestation False), and token-scope-clean; the realized-PnL rollup is built from the
supplied ``PaperRealizedPnlRollupInput`` bundles (full per-event provenance reconstruction). The session
and the rollup must share one ``market_symbol``. The bridge digest binds the session-sequence digest, the
rollup digest, the ordered source event digests, the copied totals/counts, the episode count, and the
ids/correlation/metadata/attestations.

SCOPE / membership boundary: this bridge proves that a provenance-bound realized-PnL aggregation is
digest-bound to a verified paper session CONTEXT for the same market — it does **not** assert per-episode
membership (that each rolled-up realized event was produced by an episode of this exact session). A
``PaperSessionSequenceResult`` exposes only episode-run digests, final position/PnL digests, and counts —
not per-episode fill/transition/new-state provenance — so event-to-episode membership cannot be proven
from the session artifact alone and is intentionally NOT claimed here (no false membership proof).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_realized_pnl_rollup import (
    PaperRealizedPnlRollup,
    PaperRealizedPnlRollupError,
    PaperRealizedPnlRollupInput,
    build_paper_realized_pnl_rollup,
)
from crypto_core.validation.paper_session_sequence import (
    PaperSessionSequenceResult,
    PaperSessionSequenceStatus,
    paper_session_sequence_result_digest,
)

_BRIDGE_SCHEMA_VERSION = "paper-session-realized-pnl-bridge.v1"
_EXPECTED_SESSION_SCHEMA_VERSION = "paper-session-sequence.v1"

# Scope guard mirrors the sibling realized-PnL modules (word-bounded) and rejects bare
# ``connector``/``route_id``/``execution_instruction``/``deribit``/``venue|exchange|client_order_id``
# tokens. Market-data terms are scrubbed before the scan.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")


class PaperSessionRealizedPnlBridgeError(RuntimeError):
    """Raised when bridge/session/rollup inputs are wrong-typed/malformed/forged or fail re-proof (fail-closed)."""


class PaperSessionRealizedPnlBridgeStatus(str, Enum):
    """Deterministic paper session realized-PnL bridge outcome. Never an execution / capital / live action."""

    COMPUTED = "COMPUTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperSessionRealizedPnlBridge:
    """Deterministic, immutable digest-bound bridge from a paper session sequence to a realized-PnL rollup.

    Binds a verified ``PaperSessionSequenceResult`` (by digest) and a provenance-bound
    ``PaperRealizedPnlRollup`` (by digest) for one market, copying the rollup's gross totals/counts. Gross
    only; never computes fills, positions, fees, unrealized/total PnL, equity, capital, margin, or
    balances. Does NOT assert per-episode membership (see module docstring). ``bridge_computed`` is True;
    every hard-safety attestation is False and ``gross_only`` is True. PAPER ONLY.
    """

    schema_version: str
    bridge_id: str
    status: PaperSessionRealizedPnlBridgeStatus
    market_symbol: str
    paper_session_id: str
    session_sequence_digest: str
    rollup_digest: str
    episode_count: int
    event_count: int
    computed_event_count: int
    no_realized_event_count: int
    closed_units_total: str
    realized_pnl_total: str
    source_event_digests: tuple[str, ...]
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    bridge_digest: str
    paper_only: bool = True
    bridge_computed: bool = True
    gross_only: bool = True
    fees_included: bool = False
    unrealized_pnl_included: bool = False
    total_pnl_computed: bool = False
    equity_or_capital_computed: bool = False
    capital_reserved: bool = False
    capital_mutated: bool = False
    balance_mutated: bool = False
    live_position_mutated: bool = False
    real_money_enabled: bool = False
    real_orders_enabled: bool = False
    order_routed: bool = False
    venue_order_id_created: bool = False
    exchange_order_id_created: bool = False
    client_order_id_created: bool = False
    route_id_created: bool = False
    execution_instruction_created: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            return True
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


# --------------------------------------------------------------------------------------------------
# Session re-proof
# --------------------------------------------------------------------------------------------------


def _session_is_paper_safe(session: PaperSessionSequenceResult) -> bool:
    return (
        session.paper_only is True
        and session.session_sequence_computed is True
        and session.scheduler_enabled is False
        and session.auto_loop_enabled is False
        and session.live_api_called is False
        and session.connector_invoked is False
        and session.real_money_enabled is False
        and session.real_orders_enabled is False
        and session.order_routed is False
        and session.venue_order_id_created is False
        and session.exchange_order_id_created is False
        and session.client_order_id_created is False
        and session.route_id_created is False
        and session.execution_instruction_created is False
        and session.realized_pnl_computed is False
        and session.total_pnl_computed is False
        and session.capital_reserved is False
        and session.capital_mutated is False
        and session.balance_mutated is False
        and session.live_position_mutated is False
    )


def _reprove_session(session: PaperSessionSequenceResult) -> tuple[str, str, int, str]:
    """Re-prove a digest-valid paper session sequence's schema/safety/status and digest; return context.

    Returns (market_symbol, paper_session_id, episode_count, session_sequence_digest). A self-consistent
    forged session (digest recomputed over a tampered payload) is still rejected on the structural checks.
    """
    if not isinstance(session, PaperSessionSequenceResult):
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:session_malformed")
    if session.schema_version != _EXPECTED_SESSION_SCHEMA_VERSION:
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:session_malformed")
    if not isinstance(session.status, PaperSessionSequenceStatus):
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:session_malformed")
    if session.status is not PaperSessionSequenceStatus.COMPUTED:
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:session_status_invalid")
    if not (
        _is_non_empty_string(session.paper_session_id)
        and _is_non_empty_string(session.market_symbol)
        and _is_non_empty_string(session.correlation_id)
    ):
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:session_malformed")
    if not _is_int(session.episode_count) or session.episode_count < 0:
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:session_malformed")
    if not _session_is_paper_safe(session):
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:session_unsafe_flags")
    if _has_scope_violation(session.paper_session_id, session.market_symbol, session.correlation_id):
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:session_scope_violation")

    # Digest boundary: re-prove the session self-digest via its PUBLIC serializer.
    try:
        expected_digest = paper_session_sequence_result_digest(session)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:session_malformed") from exc
    if (
        not isinstance(session.paper_session_sequence_digest, str)
        or session.paper_session_sequence_digest != expected_digest
    ):
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:session_digest_mismatch")
    return session.market_symbol, session.paper_session_id, session.episode_count, session.paper_session_sequence_digest


# --------------------------------------------------------------------------------------------------
# Bridge construction
# --------------------------------------------------------------------------------------------------


def build_paper_session_realized_pnl_bridge(
    session_sequence: PaperSessionSequenceResult,
    rollup_entries: Sequence[PaperRealizedPnlRollupInput],
    *,
    bridge_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSessionRealizedPnlBridge:
    """Build a deterministic, digest-bound bridge from a paper session sequence to a realized-PnL rollup.

    The ``session_sequence`` is re-proven (schema, status COMPUTED, paper-safe attestations, token scope,
    public digest). The realized-PnL rollup is built from the supplied ``rollup_entries`` provenance
    bundles via the merged ``build_paper_realized_pnl_rollup`` (full per-event provenance reconstruction);
    any provenance/shape/duplicate/symbol failure propagates fail-closed. The session and the rollup must
    share one ``market_symbol``. The bridge copies the rollup's gross totals/counts (no Decimal arithmetic
    of its own) and binds the session-sequence digest, rollup digest, ordered source event digests,
    counts, and episode count. Per-episode membership is not asserted (see module docstring). Wrong-typed/
    malformed/forged inputs raise ``PaperSessionRealizedPnlBridgeError``; inputs are never mutated; no
    order routing, no live API, no scheduler/auto-loop, no connector/readiness transition, gross only.
    """
    if not _is_non_empty_string(bridge_id):
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:bridge_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:correlation_id_invalid")
    bridge_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(bridge_id, correlation_id, *_metadata_texts(bridge_metadata)):
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:scope_violation")

    session_market, paper_session_id, episode_count, session_digest = _reprove_session(session_sequence)

    # Build the realized-PnL rollup from provenance bundles. The rollup builder fully re-proves each
    # event's upstream provenance (reconstruction), de-duplicates, and validates shape; any failure is a
    # fail-closed rollup rejection surfaced here as a single bridge error.
    try:
        rollup: PaperRealizedPnlRollup = build_paper_realized_pnl_rollup(
            rollup_entries, rollup_id=bridge_id, correlation_id=correlation_id, metadata=None
        )
    except PaperRealizedPnlRollupError as exc:
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:rollup_invalid") from exc

    if rollup.market_symbol != session_market:
        raise PaperSessionRealizedPnlBridgeError("paper_session_realized_pnl_bridge:market_symbol_mismatch")

    return _finalize_bridge(
        bridge_id=bridge_id,
        market_symbol=session_market,
        paper_session_id=paper_session_id,
        session_sequence_digest=session_digest,
        rollup=rollup,
        episode_count=episode_count,
        correlation_id=correlation_id,
        metadata=bridge_metadata,
    )


def _finalize_bridge(
    *,
    bridge_id: str,
    market_symbol: str,
    paper_session_id: str,
    session_sequence_digest: str,
    rollup: PaperRealizedPnlRollup,
    episode_count: int,
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperSessionRealizedPnlBridge:
    fields: dict[str, object] = {
        "schema_version": _BRIDGE_SCHEMA_VERSION,
        "bridge_id": bridge_id,
        "status": PaperSessionRealizedPnlBridgeStatus.COMPUTED,
        "market_symbol": market_symbol,
        "paper_session_id": paper_session_id,
        "session_sequence_digest": session_sequence_digest,
        "rollup_digest": rollup.rollup_digest,
        "episode_count": episode_count,
        "event_count": rollup.event_count,
        "computed_event_count": rollup.computed_event_count,
        "no_realized_event_count": rollup.no_realized_event_count,
        "closed_units_total": rollup.closed_units_total,
        "realized_pnl_total": rollup.realized_pnl_total,
        "source_event_digests": rollup.source_event_digests,
        "reason_codes": (),
        "correlation_id": correlation_id,
        "metadata": metadata,
    }
    seed = PaperSessionRealizedPnlBridge(bridge_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_session_realized_pnl_bridge_digest(seed))


def _replace_digest(bridge: PaperSessionRealizedPnlBridge, digest: str) -> PaperSessionRealizedPnlBridge:
    fields = _bridge_fields(bridge)
    fields["bridge_digest"] = digest
    return PaperSessionRealizedPnlBridge(**fields)  # type: ignore[arg-type]


def _bridge_fields(bridge: PaperSessionRealizedPnlBridge) -> dict[str, object]:
    return {
        "schema_version": bridge.schema_version,
        "bridge_id": bridge.bridge_id,
        "status": bridge.status,
        "market_symbol": bridge.market_symbol,
        "paper_session_id": bridge.paper_session_id,
        "session_sequence_digest": bridge.session_sequence_digest,
        "rollup_digest": bridge.rollup_digest,
        "episode_count": bridge.episode_count,
        "event_count": bridge.event_count,
        "computed_event_count": bridge.computed_event_count,
        "no_realized_event_count": bridge.no_realized_event_count,
        "closed_units_total": bridge.closed_units_total,
        "realized_pnl_total": bridge.realized_pnl_total,
        "source_event_digests": bridge.source_event_digests,
        "reason_codes": bridge.reason_codes,
        "correlation_id": bridge.correlation_id,
        "metadata": bridge.metadata,
    }


def _bridge_payload_from(bridge: PaperSessionRealizedPnlBridge) -> dict[str, object]:
    return {
        "schema_version": bridge.schema_version,
        "bridge_id": bridge.bridge_id,
        "status": bridge.status.value,
        "market_symbol": bridge.market_symbol,
        "paper_session_id": bridge.paper_session_id,
        "session_sequence_digest": bridge.session_sequence_digest,
        "rollup_digest": bridge.rollup_digest,
        "episode_count": bridge.episode_count,
        "event_count": bridge.event_count,
        "computed_event_count": bridge.computed_event_count,
        "no_realized_event_count": bridge.no_realized_event_count,
        "closed_units_total": bridge.closed_units_total,
        "realized_pnl_total": bridge.realized_pnl_total,
        "source_event_digests": list(bridge.source_event_digests),
        "reason_codes": list(bridge.reason_codes),
        "correlation_id": bridge.correlation_id,
        "metadata": [list(pair) for pair in bridge.metadata],
        "paper_only": bridge.paper_only,
        "bridge_computed": bridge.bridge_computed,
        "gross_only": bridge.gross_only,
        "fees_included": bridge.fees_included,
        "unrealized_pnl_included": bridge.unrealized_pnl_included,
        "total_pnl_computed": bridge.total_pnl_computed,
        "equity_or_capital_computed": bridge.equity_or_capital_computed,
        "capital_reserved": bridge.capital_reserved,
        "capital_mutated": bridge.capital_mutated,
        "balance_mutated": bridge.balance_mutated,
        "live_position_mutated": bridge.live_position_mutated,
        "real_money_enabled": bridge.real_money_enabled,
        "real_orders_enabled": bridge.real_orders_enabled,
        "order_routed": bridge.order_routed,
        "venue_order_id_created": bridge.venue_order_id_created,
        "exchange_order_id_created": bridge.exchange_order_id_created,
        "client_order_id_created": bridge.client_order_id_created,
        "route_id_created": bridge.route_id_created,
        "execution_instruction_created": bridge.execution_instruction_created,
        "live_api_called": bridge.live_api_called,
        "scheduler_enabled": bridge.scheduler_enabled,
        "auto_loop_enabled": bridge.auto_loop_enabled,
        "connector_invoked": bridge.connector_invoked,
    }


def paper_session_realized_pnl_bridge_to_dict(bridge: PaperSessionRealizedPnlBridge) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a session realized-PnL bridge (deterministic shape, includes self-digest)."""
    payload = _bridge_payload_from(bridge)
    payload["bridge_digest"] = bridge.bridge_digest
    return payload


def paper_session_realized_pnl_bridge_digest(bridge: PaperSessionRealizedPnlBridge) -> str:
    """Recompute the canonical bridge digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_bridge_payload_from(bridge))


__all__ = [
    "PaperSessionRealizedPnlBridge",
    "PaperSessionRealizedPnlBridgeError",
    "PaperSessionRealizedPnlBridgeStatus",
    "build_paper_session_realized_pnl_bridge",
    "paper_session_realized_pnl_bridge_digest",
    "paper_session_realized_pnl_bridge_to_dict",
]
