"""Paper session metrics summary — deterministic, paper-only, TIME-FREE summary that binds an existing
session realized-PnL aggregate to its §7.7 readiness verdict.

Phase-map slice §10.4.1 (``docs/crypto_core/paper_trading_phase_map.md``): the first post-§7 product slice.
A small, immutable, fail-closed *summary / probe* that consumes the **existing**
``PaperSessionRealizedPnlAggregate`` (its already-computed gross / count metrics) and the §7.7
``PaperStage4ReadinessDecision`` (the readiness verdict context), re-proves both at their digest trust
boundaries, proves they describe the **same paper chain**, and emits ONE operator-readable, digest-bound
**time-free** metrics summary. It is **additive, not duplicative**: it recomputes **no** aggregation — it
reads the aggregate's bound gross totals / counts by value (the only derived value is the absolute magnitude
of the already-bound gross realized-PnL total) and binds the readiness verdict as context.

It is **time-free by construction**: it computes no Sharpe, no annualized / time-weighted return, no
return series, no wall-clock or session duration, and no 30-day gate — those are explicit digest-bound
``False`` flags, and the module imports no time / clock surface at all (alias-resistant import tests enforce
this).

Trust boundary (fail-closed): the aggregate self-digest is re-proven via the PUBLIC
``paper_session_realized_pnl_aggregate_digest`` and the readiness self-digest via
``paper_stage4_readiness_decision_digest`` (each stored digest must equal the recompute AND the caller's
INDEPENDENT expected anchor). Same-chain binding: the readiness decision's bound
``realized_pnl_event_digest`` must be a **member** of the aggregate's ``source_event_digests`` (the realized
event the readiness chain produced is among the events the aggregate summed), and aggregate / readiness must
agree on ``market_symbol`` and the caller's ids. Both must be paper-safe and non-over-claiming, the aggregate
``COMPUTED`` with non-negative counts, the readiness ``DECIDED``. ``status=READY`` only over fully trusted,
same-chain inputs. ``ready`` (the headline candidate flag) is True **only** when the readiness verdict is
``PAPER_STAGE4_CANDIDATE`` — a ``REVIEW_REQUIRED`` / ``BLOCK_PAPER`` verdict yields ``status=READY`` (the
metrics are summarized) with ``ready=False`` and a recorded context reason; no readiness verdict is upgraded.
Any digest / trust / id / same-chain failure (incl. a non-``DECIDED`` readiness) maps to ``status=REJECTED``.

Non-overclaim: a READY summary proves only a deterministic, time-free, gross/count paper-session metrics
summary for the supplied artifacts. It is NOT PRDV4 Stage 4 completion, NOT live readiness, NOT shadow
readiness, NOT production / operational readiness, NOT Deribit / connector readiness, NOT a Sharpe /
return-series / 30-day-gate computation, and NOT a profitability / edge proof; it reserves NO real capital —
all carried as explicit ``False`` flags, digest-bound. It does NOT import or use
``crypto_core.service.readiness`` or ``crypto_core.execution.paper_adapter`` (or any shadow/live/runtime/venue
surface), no Deribit, no BIST. Deterministic and immutable; no wall-clock/random/IO; inputs unmutated.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_session_realized_pnl_aggregate import (
    PaperSessionRealizedPnlAggregate,
    PaperSessionRealizedPnlAggregateStatus,
    paper_session_realized_pnl_aggregate_digest,
)
from crypto_core.validation.paper_stage4_readiness_decision import (
    PaperStage4ReadinessDecision,
    PaperStage4ReadinessStatus,
    PaperStage4ReadinessVerdict,
    paper_stage4_readiness_decision_digest,
)

_SCHEMA_VERSION = "paper-session-metrics-summary.v1"
_METRICS_VERSION = "paper-session-metrics.v1"
_EXPECTED_AGGREGATE_SCHEMA_VERSION = "paper-session-realized-pnl-aggregate.v1"
_EXPECTED_READINESS_SCHEMA_VERSION = "paper-stage4-readiness-decision.v1"

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Strict decimal-string grammar (mirrors the sibling realized-PnL modules).
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling validation modules (word-bounded). Market-data terms scrubbed first.
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


class PaperSessionMetricsSummaryError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed artifacts / ids / digests / metadata)."""


class PaperSessionMetricsSummaryStatus(str, Enum):
    """Whether a trusted, same-chain metrics summary could be produced. Never an execution / live action."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperSessionMetricsSummary:
    """Deterministic, immutable, digest-bound time-free paper-session metrics summary.

    ``status`` READY only when the aggregate + readiness re-prove, cross-bind to the same chain, and are
    trusted. ``ready`` (headline candidate flag) True only when the readiness verdict is
    ``PAPER_STAGE4_CANDIDATE``; a REVIEW/BLOCK verdict still yields READY with ``ready=False`` and a context
    reason (no verdict is upgraded). ``paper_only`` True; every safety / non-overclaim attestation False,
    incl. ``sharpe_computed`` / ``return_series_computed`` / ``thirty_day_gate_satisfied``. TIME-FREE,
    gross/count only — NOT PRDV4 Stage 4, NOT live/shadow readiness, NOT a profitability/edge proof.
    """

    schema_version: str
    metrics_version: str
    status: PaperSessionMetricsSummaryStatus
    ready: bool
    run_id: str
    aggregate_id: str
    correlation_id: str
    market_symbol: str
    expected_session_aggregate_digest: str
    expected_readiness_decision_digest: str
    session_aggregate_digest: str
    readiness_decision_digest: str
    readiness_status: str
    readiness_verdict: str
    session_bridge_count: int
    episode_count_total: int
    event_count: int
    computed_event_count: int
    no_realized_event_count: int
    source_event_digest_count: int
    closed_units_total: str
    realized_pnl_total: str
    abs_realized_pnl_total: str
    realized_pnl_event_digest: str
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    summary_digest: str
    paper_only: bool = True
    prdv4_stage4_complete: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    production_execution: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    deribit_ready: bool = False
    operational_readiness: bool = False
    sharpe_computed: bool = False
    return_series_computed: bool = False
    thirty_day_gate_satisfied: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    return type(value) is str and value.strip() != ""


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _plain_str_or_empty(value: object) -> str:
    """Return ``value`` only if it is an exact plain ``str`` (no subclass); else ``""`` (fail-closed)."""
    return value if type(value) is str else ""


def _parse_decimal(value: object) -> Decimal | None:
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _render_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _canonical_decimal(value: object) -> Decimal | None:
    """Parse a strict decimal string that is ALSO already in canonical render form, else ``None``."""
    parsed = _parse_decimal(value)
    if parsed is None or _render_decimal(parsed) != value:
        return None
    return parsed


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSessionMetricsSummaryError("paper_session_metrics_summary:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperSessionMetricsSummaryError("paper_session_metrics_summary:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise PaperSessionMetricsSummaryError("paper_session_metrics_summary:metadata_malformed")
        pairs.append([pair[0], pair[1]])
    return pairs


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


def _aggregate_is_paper_safe(aggregate: PaperSessionRealizedPnlAggregate) -> bool:
    return (
        aggregate.paper_only is True
        and aggregate.aggregate_computed is True
        and aggregate.gross_only is True
        and aggregate.fees_included is False
        and aggregate.unrealized_pnl_included is False
        and aggregate.total_pnl_computed is False
        and aggregate.equity_or_capital_computed is False
        and aggregate.capital_reserved is False
        and aggregate.capital_mutated is False
        and aggregate.balance_mutated is False
        and aggregate.live_position_mutated is False
        and aggregate.real_money_enabled is False
        and aggregate.real_orders_enabled is False
        and aggregate.order_routed is False
        and aggregate.venue_order_id_created is False
        and aggregate.exchange_order_id_created is False
        and aggregate.client_order_id_created is False
        and aggregate.route_id_created is False
        and aggregate.execution_instruction_created is False
        and aggregate.live_api_called is False
        and aggregate.scheduler_enabled is False
        and aggregate.auto_loop_enabled is False
        and aggregate.connector_invoked is False
    )


def _readiness_is_paper_safe(readiness: PaperStage4ReadinessDecision) -> bool:
    return (
        readiness.paper_only is True
        and readiness.prdv4_stage4_complete is False
        and readiness.live_ready is False
        and readiness.shadow_ready is False
        and readiness.profitability_proven is False
        and readiness.edge_proven is False
        and readiness.production_execution is False
        and readiness.real_orders_enabled is False
        and readiness.real_money_enabled is False
        and readiness.real_capital_reserved is False
        and readiness.live_api_called is False
        and readiness.scheduler_enabled is False
        and readiness.auto_loop_enabled is False
        and readiness.connector_invoked is False
        and readiness.deribit_ready is False
        and readiness.operational_readiness is False
    )


def _reprove_self_digest(artifact: object, recompute, stored: object, expected: str, label: str) -> str | None:
    """Re-prove an artifact self-digest via its PUBLIC serializer AND the caller anchor. Reason or ``None``."""
    try:
        recomputed = recompute(artifact)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        return f"paper_session_metrics_summary:{label}_malformed"
    if not _is_hex64_string(stored) or stored != recomputed or stored != expected:
        return f"paper_session_metrics_summary:{label}_digest_mismatch"
    return None


def _source_event_digests(aggregate: PaperSessionRealizedPnlAggregate) -> frozenset[str]:
    raw = aggregate.source_event_digests
    if not isinstance(raw, tuple):
        return frozenset()
    return frozenset(item for item in raw if _is_hex64_string(item))


def summarize_paper_session_metrics(
    session_aggregate: PaperSessionRealizedPnlAggregate,
    readiness_decision: PaperStage4ReadinessDecision,
    *,
    expected_session_aggregate_digest: str,
    expected_readiness_decision_digest: str,
    run_id: str,
    aggregate_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSessionMetricsSummary:
    """Summarize a paper session's deterministic time-free gross/count metrics + its §7.7 readiness verdict.

    ``session_aggregate`` must be a ``PaperSessionRealizedPnlAggregate`` and ``readiness_decision`` a
    ``PaperStage4ReadinessDecision``; ``expected_session_aggregate_digest`` /
    ``expected_readiness_decision_digest`` exact plain 64-lowercase-hex ``str`` (the caller's INDEPENDENT
    anchors); ``run_id`` (the readiness run), ``aggregate_id`` (the aggregate's own id), ``correlation_id``
    (shared) exact plain non-empty ``str``; ``metadata`` ``Mapping[str, str]`` or ``None``. A wrong type,
    malformed digest, empty id, a forbidden BIST/live/order token, or malformed metadata raises
    ``PaperSessionMetricsSummaryError`` before any work.

    Each artifact self-digest is re-proven via its PUBLIC serializer (== stored == expected anchor); the
    aggregate must be COMPUTED + paper-safe with non-negative counts, the readiness DECIDED + paper-safe +
    non-over-claiming; both must agree on ``market_symbol`` and the caller ids, and the readiness's
    ``realized_pnl_event_digest`` must be a member of the aggregate's ``source_event_digests`` (same chain).
    ``status=READY`` over fully trusted same-chain inputs; ``ready`` True only when the readiness verdict is
    ``PAPER_STAGE4_CANDIDATE`` (REVIEW/BLOCK → READY, ``ready=False``, context reason). Any trust/id/same-chain
    failure → ``status=REJECTED``. No aggregation is recomputed (the only derived value is the absolute
    magnitude of the already-bound gross realized-PnL total). Deterministic and immutable; no
    wall-clock/random/IO; time-free; reserves NO real capital; inputs unmutated.
    """
    if not isinstance(session_aggregate, PaperSessionRealizedPnlAggregate):
        raise PaperSessionMetricsSummaryError("paper_session_metrics_summary:session_aggregate_malformed")
    if not isinstance(readiness_decision, PaperStage4ReadinessDecision):
        raise PaperSessionMetricsSummaryError("paper_session_metrics_summary:readiness_decision_malformed")
    if not _is_hex64_string(expected_session_aggregate_digest):
        raise PaperSessionMetricsSummaryError("paper_session_metrics_summary:expected_session_aggregate_digest_invalid")
    if not _is_hex64_string(expected_readiness_decision_digest):
        raise PaperSessionMetricsSummaryError(
            "paper_session_metrics_summary:expected_readiness_decision_digest_invalid"
        )
    for name, value in (
        ("run_id", run_id),
        ("aggregate_id", aggregate_id),
        ("correlation_id", correlation_id),
    ):
        if not _is_plain_non_empty_string(value):
            raise PaperSessionMetricsSummaryError(f"paper_session_metrics_summary:{name}_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(run_id, aggregate_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperSessionMetricsSummaryError("paper_session_metrics_summary:scope_violation")

    hard: list[str] = []

    # Trust boundaries: re-prove each artifact self-digest via its PUBLIC serializer AND the caller anchor.
    aggregate_reason = _reprove_self_digest(
        session_aggregate,
        paper_session_realized_pnl_aggregate_digest,
        session_aggregate.aggregate_digest,
        expected_session_aggregate_digest,
        "session_aggregate",
    )
    if aggregate_reason is not None:
        hard.append(aggregate_reason)
    readiness_reason = _reprove_self_digest(
        readiness_decision,
        paper_stage4_readiness_decision_digest,
        readiness_decision.readiness_decision_digest,
        expected_readiness_decision_digest,
        "readiness_decision",
    )
    if readiness_reason is not None:
        hard.append(readiness_reason)

    # Schema + status + safety per artifact.
    if session_aggregate.schema_version != _EXPECTED_AGGREGATE_SCHEMA_VERSION:
        hard.append("paper_session_metrics_summary:session_aggregate_schema_invalid")
    elif session_aggregate.status is not PaperSessionRealizedPnlAggregateStatus.COMPUTED:
        hard.append("paper_session_metrics_summary:session_aggregate_not_computed")
    if not _aggregate_is_paper_safe(session_aggregate):
        hard.append("paper_session_metrics_summary:session_aggregate_unsafe_flags")
    if readiness_decision.schema_version != _EXPECTED_READINESS_SCHEMA_VERSION:
        hard.append("paper_session_metrics_summary:readiness_decision_schema_invalid")
    if not (
        isinstance(readiness_decision.status, PaperStage4ReadinessStatus)
        and readiness_decision.status is PaperStage4ReadinessStatus.DECIDED
        and readiness_decision.decided is True
    ):
        hard.append("paper_session_metrics_summary:readiness_decision_not_decided")
    if not _readiness_is_paper_safe(readiness_decision):
        hard.append("paper_session_metrics_summary:readiness_decision_unsafe_flags")

    # Non-negative deterministic counts (well-formed; a real session has >=1 bridge).
    if not _is_int(session_aggregate.session_bridge_count) or session_aggregate.session_bridge_count < 1:
        hard.append("paper_session_metrics_summary:session_bridge_count_invalid")
    for count_name in ("episode_count_total", "event_count", "computed_event_count", "no_realized_event_count"):
        count_value = getattr(session_aggregate, count_name)
        if not _is_int(count_value) or count_value < 0:
            hard.append(f"paper_session_metrics_summary:{count_name}_invalid")

    # Gross totals well-formed (canonical decimals). The only derived metric is abs(realized).
    realized = _canonical_decimal(session_aggregate.realized_pnl_total)
    closed = _canonical_decimal(session_aggregate.closed_units_total)
    if realized is None or closed is None or closed < 0:
        hard.append("paper_session_metrics_summary:session_aggregate_totals_malformed")
        abs_realized_total = ""
    else:
        abs_realized_total = _render_decimal(abs(realized))

    # Caller ids must match: the aggregate by its own ``aggregate_id``; the readiness run/episode by ``run_id``
    # and ``correlation_id``. The aggregate carries its OWN audit ``correlation_id`` (independent of the run
    # correlation), so it is bound transitively via the re-proven aggregate digest, not required to equal the
    # run correlation — the genuine cross-artifact link is the realized-event-digest membership + market below.
    if _plain_str_or_empty(session_aggregate.aggregate_id) != aggregate_id:
        hard.append("paper_session_metrics_summary:aggregate_id_mismatch")
    if _plain_str_or_empty(readiness_decision.run_id) != run_id:
        hard.append("paper_session_metrics_summary:readiness_run_id_mismatch")
    if _plain_str_or_empty(readiness_decision.correlation_id) != correlation_id:
        hard.append("paper_session_metrics_summary:readiness_correlation_id_mismatch")

    # Same-chain binding: same market, and the readiness chain's realized event is among the aggregate's
    # summed source events (the genuine link between the readiness verdict and the aggregate economics).
    aggregate_symbol = _plain_str_or_empty(session_aggregate.market_symbol)
    if aggregate_symbol == "" or aggregate_symbol != _plain_str_or_empty(readiness_decision.market_symbol):
        hard.append("paper_session_metrics_summary:market_symbol_mismatch")
    readiness_event_digest = _plain_str_or_empty(readiness_decision.realized_pnl_event_digest)
    if not _is_hex64_string(readiness_event_digest) or readiness_event_digest not in _source_event_digests(
        session_aggregate
    ):
        hard.append("paper_session_metrics_summary:realized_pnl_event_not_in_aggregate")

    verdict = readiness_decision.verdict
    if hard:
        status = PaperSessionMetricsSummaryStatus.REJECTED
        ready = False
        reason_codes = tuple(sorted(set(hard)))
    else:
        # Trusted same-chain inputs: a well-formed metrics summary is produced. The headline ``ready`` flag is
        # gated on a CANDIDATE readiness verdict; REVIEW/BLOCK is summarized (READY) with ready=False and a
        # context reason — no verdict is upgraded.
        status = PaperSessionMetricsSummaryStatus.READY
        if verdict is PaperStage4ReadinessVerdict.PAPER_STAGE4_CANDIDATE:
            ready = True
            reason_codes = ()
        elif verdict is PaperStage4ReadinessVerdict.PAPER_REVIEW_REQUIRED:
            ready = False
            reason_codes = ("paper_session_metrics_summary:readiness_review_required",)
        elif verdict is PaperStage4ReadinessVerdict.PAPER_BLOCKED:
            ready = False
            reason_codes = ("paper_session_metrics_summary:readiness_blocked",)
        else:  # unknown verdict enum -> untrusted, fail closed
            status = PaperSessionMetricsSummaryStatus.REJECTED
            ready = False
            reason_codes = ("paper_session_metrics_summary:readiness_verdict_invalid",)

    return _finalize_summary(
        status=status,
        ready=ready,
        session_aggregate=session_aggregate,
        readiness_decision=readiness_decision,
        expected_session_aggregate_digest=expected_session_aggregate_digest,
        expected_readiness_decision_digest=expected_readiness_decision_digest,
        run_id=run_id,
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        abs_realized_total=abs_realized_total,
        reason_codes=reason_codes,
        metadata=metadata_pairs,
    )


def _finalize_summary(
    *,
    status: PaperSessionMetricsSummaryStatus,
    ready: bool,
    session_aggregate: PaperSessionRealizedPnlAggregate,
    readiness_decision: PaperStage4ReadinessDecision,
    expected_session_aggregate_digest: str,
    expected_readiness_decision_digest: str,
    run_id: str,
    aggregate_id: str,
    correlation_id: str,
    abs_realized_total: str,
    reason_codes: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> PaperSessionMetricsSummary:
    readiness_status = (
        readiness_decision.status.value if isinstance(readiness_decision.status, PaperStage4ReadinessStatus) else ""
    )
    readiness_verdict = (
        readiness_decision.verdict.value if isinstance(readiness_decision.verdict, PaperStage4ReadinessVerdict) else ""
    )
    source_event_digest_count = (
        len(session_aggregate.source_event_digests) if isinstance(session_aggregate.source_event_digests, tuple) else 0
    )
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "metrics_version": _METRICS_VERSION,
        "status": status,
        "ready": ready,
        "run_id": run_id,
        "aggregate_id": aggregate_id,
        "correlation_id": correlation_id,
        "market_symbol": _plain_str_or_empty(session_aggregate.market_symbol),
        "expected_session_aggregate_digest": expected_session_aggregate_digest,
        "expected_readiness_decision_digest": expected_readiness_decision_digest,
        "session_aggregate_digest": _plain_str_or_empty(session_aggregate.aggregate_digest),
        "readiness_decision_digest": _plain_str_or_empty(readiness_decision.readiness_decision_digest),
        "readiness_status": readiness_status,
        "readiness_verdict": readiness_verdict,
        "session_bridge_count": session_aggregate.session_bridge_count
        if _is_int(session_aggregate.session_bridge_count)
        else 0,
        "episode_count_total": session_aggregate.episode_count_total
        if _is_int(session_aggregate.episode_count_total)
        else 0,
        "event_count": session_aggregate.event_count if _is_int(session_aggregate.event_count) else 0,
        "computed_event_count": session_aggregate.computed_event_count
        if _is_int(session_aggregate.computed_event_count)
        else 0,
        "no_realized_event_count": session_aggregate.no_realized_event_count
        if _is_int(session_aggregate.no_realized_event_count)
        else 0,
        "source_event_digest_count": source_event_digest_count,
        "closed_units_total": _plain_str_or_empty(session_aggregate.closed_units_total),
        "realized_pnl_total": _plain_str_or_empty(session_aggregate.realized_pnl_total),
        "abs_realized_pnl_total": abs_realized_total,
        "realized_pnl_event_digest": _plain_str_or_empty(readiness_decision.realized_pnl_event_digest),
        "reason_codes": reason_codes,
        "metadata": metadata,
    }
    seed = PaperSessionMetricsSummary(summary_digest="", **fields)  # type: ignore[arg-type]
    return _replace_summary_digest(seed, paper_session_metrics_summary_digest(seed))


def _replace_summary_digest(summary: PaperSessionMetricsSummary, digest: str) -> PaperSessionMetricsSummary:
    fields = _summary_fields(summary)
    fields["summary_digest"] = digest
    return PaperSessionMetricsSummary(**fields)  # type: ignore[arg-type]


def _summary_fields(summary: PaperSessionMetricsSummary) -> dict[str, object]:
    return {
        "schema_version": summary.schema_version,
        "metrics_version": summary.metrics_version,
        "status": summary.status,
        "ready": summary.ready,
        "run_id": summary.run_id,
        "aggregate_id": summary.aggregate_id,
        "correlation_id": summary.correlation_id,
        "market_symbol": summary.market_symbol,
        "expected_session_aggregate_digest": summary.expected_session_aggregate_digest,
        "expected_readiness_decision_digest": summary.expected_readiness_decision_digest,
        "session_aggregate_digest": summary.session_aggregate_digest,
        "readiness_decision_digest": summary.readiness_decision_digest,
        "readiness_status": summary.readiness_status,
        "readiness_verdict": summary.readiness_verdict,
        "session_bridge_count": summary.session_bridge_count,
        "episode_count_total": summary.episode_count_total,
        "event_count": summary.event_count,
        "computed_event_count": summary.computed_event_count,
        "no_realized_event_count": summary.no_realized_event_count,
        "source_event_digest_count": summary.source_event_digest_count,
        "closed_units_total": summary.closed_units_total,
        "realized_pnl_total": summary.realized_pnl_total,
        "abs_realized_pnl_total": summary.abs_realized_pnl_total,
        "realized_pnl_event_digest": summary.realized_pnl_event_digest,
        "reason_codes": summary.reason_codes,
        "metadata": summary.metadata,
    }


def _summary_payload_from(summary: PaperSessionMetricsSummary) -> dict[str, object]:
    return {
        "schema_version": summary.schema_version,
        "metrics_version": summary.metrics_version,
        "status": summary.status.value,
        "ready": summary.ready,
        "run_id": summary.run_id,
        "aggregate_id": summary.aggregate_id,
        "correlation_id": summary.correlation_id,
        "market_symbol": summary.market_symbol,
        "expected_session_aggregate_digest": summary.expected_session_aggregate_digest,
        "expected_readiness_decision_digest": summary.expected_readiness_decision_digest,
        "session_aggregate_digest": summary.session_aggregate_digest,
        "readiness_decision_digest": summary.readiness_decision_digest,
        "readiness_status": summary.readiness_status,
        "readiness_verdict": summary.readiness_verdict,
        "session_bridge_count": summary.session_bridge_count,
        "episode_count_total": summary.episode_count_total,
        "event_count": summary.event_count,
        "computed_event_count": summary.computed_event_count,
        "no_realized_event_count": summary.no_realized_event_count,
        "source_event_digest_count": summary.source_event_digest_count,
        "closed_units_total": summary.closed_units_total,
        "realized_pnl_total": summary.realized_pnl_total,
        "abs_realized_pnl_total": summary.abs_realized_pnl_total,
        "realized_pnl_event_digest": summary.realized_pnl_event_digest,
        "reason_codes": list(summary.reason_codes),
        "metadata": _serialize_metadata(summary.metadata),
        "paper_only": summary.paper_only,
        "prdv4_stage4_complete": summary.prdv4_stage4_complete,
        "live_ready": summary.live_ready,
        "shadow_ready": summary.shadow_ready,
        "profitability_proven": summary.profitability_proven,
        "edge_proven": summary.edge_proven,
        "production_execution": summary.production_execution,
        "real_orders_enabled": summary.real_orders_enabled,
        "real_money_enabled": summary.real_money_enabled,
        "real_capital_reserved": summary.real_capital_reserved,
        "live_api_called": summary.live_api_called,
        "scheduler_enabled": summary.scheduler_enabled,
        "auto_loop_enabled": summary.auto_loop_enabled,
        "connector_invoked": summary.connector_invoked,
        "deribit_ready": summary.deribit_ready,
        "operational_readiness": summary.operational_readiness,
        "sharpe_computed": summary.sharpe_computed,
        "return_series_computed": summary.return_series_computed,
        "thirty_day_gate_satisfied": summary.thirty_day_gate_satisfied,
    }


def paper_session_metrics_summary_to_dict(summary: PaperSessionMetricsSummary) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for a summary (deterministic shape, includes self-digest)."""
    payload = _summary_payload_from(summary)
    payload["summary_digest"] = summary.summary_digest
    return payload


def paper_session_metrics_summary_digest(summary: PaperSessionMetricsSummary) -> str:
    """Recompute the canonical summary digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_summary_payload_from(summary))


__all__ = [
    "PaperSessionMetricsSummary",
    "PaperSessionMetricsSummaryError",
    "PaperSessionMetricsSummaryStatus",
    "paper_session_metrics_summary_digest",
    "paper_session_metrics_summary_to_dict",
    "summarize_paper_session_metrics",
]
