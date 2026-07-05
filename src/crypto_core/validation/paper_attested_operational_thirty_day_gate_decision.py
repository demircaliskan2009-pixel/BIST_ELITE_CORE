"""Deterministic paper attested operational 30-day gate decision (PRDV4 Stage 4 operational gate, v1).

This validation artifact evaluates a tuple of already-proven ``PaperAttestedOperationalDayEvidence`` artifacts
(PR #318) and decides whether they form a digest-proven, operator-attested, CONSECUTIVE 30 UTC epoch-day
sequence. It is paper-only, deterministic, digest-bound, attestation-only, and fail-closed. It re-proves every
day at its digest boundary, re-pins the approved day provenance, re-checks day boundary coherence, forbids any
cross-day replay of a day / window / run under multiple wrappers, requires a strictly-increasing gapless UTC
day-index sequence, and renders ONE deterministic gate decision.

Governance (user-approved, Codex-repaired design for this slice):

* the gate is ``consecutive_attested_utc_epoch_days.v1`` over ``attested_operational_days_only_not_machine_proven.v1``
  with policy ``minimum_30_consecutive_attested_utc_days.v1`` — the satisfiable field is
  ``attested_operational_thirty_day_gate_satisfied``, NOT the generic ``thirty_day_gate_satisfied`` (which
  belongs to the return-series gate namespace and stays False here);
* every supplied day (not only the selected first 30) must re-prove its digest, be READY / attested /
  paper-safe / coherent, share one ``market_symbol`` and the gate ``correlation_id``, and preserve every
  machine-proof flag False; a duplicate day index / digest / evidence-id / attestation-id, or a replayed
  session window digest / run-id / window-id across days, fails closed;
* input order is trusted, never silently sorted: days must arrive strictly increasing by
  ``attested_utc_day_index`` with no gaps, else REJECTED;
* outcome-evidence semantics (mirrors #316 / #317): >=30 valid consecutive days -> READY + satisfied;
  1..29 valid consecutive days -> READY + decided-but-not-satisfied (honest accumulation evidence); any
  trust / coherence / ordering failure -> REJECTED.

Status semantics: ``status=READY`` with ``attested_operational_thirty_day_gate_satisfied=True`` means only that
a digest-proven, operator-attested, consecutive >=30 UTC epoch-day paper sequence exists. It does NOT mean
machine-proven real-time operation, operational readiness, PRDV4 Stage-4 completion, live / shadow / Deribit
readiness, or any real orders / capital / profitability. Only a later ``PaperStage4CompletionDecision`` v2 may
decide completion, and it must align the selected UTC day indices and selected day digests with the exact
return-series / Sharpe bucket indices first. Existing machine-time proof remains unavailable unless a separate
wall-clock session recorder is authorized.

It does NOT run the Stage-4 comparator, does NOT construct any Stage-4 object, does NOT set
``prdv4_stage4_complete``, and calls no wall-clock, runtime, service, execution, venue, scheduler, filesystem,
network, or random surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from enum import Enum

from crypto_core.validation.paper_attested_operational_day_evidence import (
    PaperAttestedOperationalDayEvidence,
    PaperAttestedOperationalDayEvidenceStatus,
    paper_attested_operational_day_evidence_digest,
)

_SCHEMA_VERSION = "paper-attested-operational-thirty-day-gate-decision.v1"
_DECISION_VERSION = "paper-attested-operational-thirty-day-gate-decision.v1"
_REASON_PREFIX = "paper_attested_operational_thirty_day_gate_decision"

_EXPECTED_DAY_SCHEMA_VERSION = "paper-attested-operational-day-evidence.v1"
_EXPECTED_DAY_EVIDENCE_VERSION = "paper-attested-operational-day-evidence.v1"

_MINIMUM_CONSECUTIVE_UTC_DAYS = 30
_GATE_BASIS = "consecutive_attested_utc_epoch_days.v1"
_GATE_SCOPE = "attested_operational_days_only_not_machine_proven.v1"
_GATE_POLICY_ID = "minimum_30_consecutive_attested_utc_days.v1"
_UTC_DAY_POLICY = "utc_epoch_day_index.v1"
_NANOSECONDS_PER_DAY = 86_400_000_000_000

# The approved day provenance constants (mirror the merged PaperAttestedOperationalDayEvidence). Re-pinned here
# so a digest-resealed day cannot smuggle a different attestation policy past the gate boundary.
_EXPECTED_ATTESTATION_SOURCE = "operator_attested_not_machine_proven.v1"
_EXPECTED_ATTESTATION_SCOPE = "single_utc_day_digest_bound_paper_windows.v1"
_EXPECTED_ATTESTATION_VERSION = "paper-attested-operational-day-attestation.v1"
_EXPECTED_OPERATIONAL_ORIGIN = "operator_attested_not_machine_proven.v1"

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|readiness|service|real_money|paper_adapter|"
    r"capital|margin|balance|reservation|real_account_equity|account_equity|real_equity)\w*"
    r"|crypto_core\.(?:service|execution|venue|runtime|orchestrator|temporal|session|data|portfolio)\b"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")
_CLOCK_TOKENS = (
    "wall_clock",
    "wall-clock",
    "wallclock",
    "datetime.now",
    "datetime.utcnow",
    "utcnow",
    "time.time_ns",
    "time.time",
    "perf_counter",
    "monotonic",
    "server_time",
    "exchange_time",
    "live_time",
    "real_time",
    "realtime",
    "system_time",
    "clock",
    "now()",
)

_DAY_TRUE_FLAGS = ("paper_only", "session_windows_consumed", "operator_attested_operational_day")
_DAY_FALSE_FLAGS = (
    "operational_day_machine_proven",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "real_wall_clock_used",
    "real_time_paper_operation_proven",
    "operational_readiness",
    "prdv4_stage4_complete",
    "thirty_day_gate_satisfied",
    "thirty_day_gate_decided",
    "stage4_completion_decided",
    "comparison_ready",
    "paper_vs_backtest_comparison_ready",
    "stage4_comparator_invoked",
    "edge_proven",
    "profitability_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "connector_invoked",
    "private_api_ready",
    "scheduler_enabled",
    "auto_loop_enabled",
    "production_execution",
    "real_orders_enabled",
    "order_routed",
    "real_money_enabled",
    "real_capital_reserved",
    "real_account_equity_used",
    "real_capital_used",
    "live_api_called",
)

# Per-day list fields that must all have length == session_count (coherence re-check).
_DAY_SESSION_LIST_FIELDS = (
    "expected_session_window_digests",
    "verified_session_window_digests",
    "session_window_ids",
    "session_run_ids",
    "session_aggregate_ids",
    "session_started_at_ns_list",
    "session_stopped_at_ns_list",
    "session_window_duration_ns_list",
    "session_metrics_summary_digests",
    "source_event_digest_counts",
)


class PaperAttestedOperationalThirtyDayGateDecisionError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed days / ids / digests / metadata / tokens)."""


class PaperAttestedOperationalThirtyDayGateDecisionStatus(str, Enum):
    """Gate decision status. READY is a valid decision record, never PRDV4 Stage-4 completion."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperAttestedOperationalThirtyDayGateDecision:
    """Immutable, digest-bound paper attested operational 30-day gate decision (attestation-only).

    ``status=READY`` with ``attested_operational_thirty_day_gate_satisfied=True`` only when every supplied day
    re-proves its digest, is READY / attested / paper-safe / coherent, the days are same-market / same-caller-
    correlation, replay-free, strictly increasing and gapless, and there are >=30 of them. 1..29 valid
    consecutive days yield ``status=READY`` with the gate decided but not satisfied. READY / satisfied does NOT
    mean machine-proven real-time operation, operational readiness, PRDV4 Stage-4 completion, live / shadow /
    Deribit readiness, or any real orders / capital / profitability. The generic ``thirty_day_gate_*`` fields
    belong to the return-series gate namespace and are constant False here; this artifact's satisfiable field is
    ``attested_operational_thirty_day_gate_satisfied``.
    """

    schema_version: str
    decision_version: str
    status: PaperAttestedOperationalThirtyDayGateDecisionStatus
    ready: bool
    gate_decision_id: str
    correlation_id: str
    market_symbol: str
    minimum_consecutive_utc_days: int
    day_count: int
    consecutive_day_count: int
    gate_basis: str
    gate_scope: str
    gate_policy_id: str
    utc_day_policy: str
    selected_start_utc_day_index: int
    selected_end_utc_day_index: int
    selected_utc_day_indices: tuple[int, ...]
    supplied_utc_day_indices: tuple[int, ...]
    selected_operational_day_evidence_digests: tuple[str, ...]
    supplied_operational_day_evidence_digests: tuple[str, ...]
    expected_operational_day_evidence_digests: tuple[str, ...]
    verified_operational_day_evidence_digests: tuple[str, ...]
    operational_day_evidence_ids: tuple[str, ...]
    attestation_ids: tuple[str, ...]
    attestor_ids: tuple[str, ...]
    per_day_session_counts: tuple[int, ...]
    per_day_window_digests: tuple[tuple[str, ...], ...]
    per_day_window_ids: tuple[tuple[str, ...], ...]
    per_day_run_ids: tuple[tuple[str, ...], ...]
    per_day_metrics_summary_digests: tuple[tuple[str, ...], ...]
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    attested_operational_thirty_day_gate_decision_digest: str
    attested_operational_thirty_day_gate_decided: bool = False
    attested_operational_thirty_day_gate_satisfied: bool = False
    operational_days_consumed: bool = False
    paper_only: bool = True
    thirty_day_gate_decided: bool = False
    thirty_day_gate_satisfied: bool = False
    operational_day_machine_proven: bool = False
    machine_time_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    real_wall_clock_used: bool = False
    real_time_paper_operation_proven: bool = False
    operational_readiness: bool = False
    prdv4_stage4_complete: bool = False
    completion_ready: bool = False
    stage4_completion_decided: bool = False
    comparison_ready: bool = False
    paper_vs_backtest_comparison_ready: bool = False
    stage4_comparator_invoked: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    connector_invoked: bool = False
    private_api_ready: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    production_execution: bool = False
    real_orders_enabled: bool = False
    order_routed: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    real_account_equity_used: bool = False
    real_capital_used: bool = False
    live_api_called: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _is_plain_non_empty_string(value: object) -> bool:
    return (
        type(value) is str
        and value.strip() != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _is_positive_int(value: object) -> bool:
    return _is_exact_int(value) and value > 0


def _plain_str_or_empty(value: object) -> str:
    return value if type(value) is str else ""


def _safe_digest_value(value: object) -> str:
    return value if _is_hex64_string(value) else ""


def _safe_int_value(value: object) -> int:
    return value if _is_exact_int(value) else 0


def _str_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        return ()
    return tuple(item for item in value if type(item) is str)


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason("metadata_malformed"))
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        if _BIST_PATTERN.search(text):
            return True
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


def _has_clock_token(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        lowered = text.lower()
        if any(token in lowered for token in _CLOCK_TOKENS):
            return True
    return False


def _recomputed_day_digest_or_none(day: PaperAttestedOperationalDayEvidence) -> str | None:
    try:
        return paper_attested_operational_day_evidence_digest(day)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        return None


def _day_session_content_failures(day: PaperAttestedOperationalDayEvidence, session_count: int) -> list[str]:
    """Recompute the per-session arithmetic / count / digest-shape invariants a genuine day must satisfy.

    A digest-resealed day re-proves its own self-digest, so tuple lengths alone are not trust: this recomputes,
    for every session, that the window falls fully inside the attested UTC day with a coherent positive
    duration, is ordered and non-overlapping, has a hex64 window + metrics digest, positive source-event
    count, and non-empty ids — mirroring the upstream ``PaperAttestedOperationalDayEvidence`` window contract.
    """
    day_start = day.day_start_ns
    day_end = day.day_end_ns
    previous_stop: int | None = None
    for i in range(session_count):
        start = day.session_started_at_ns_list[i]
        stop = day.session_stopped_at_ns_list[i]
        duration = day.session_window_duration_ns_list[i]
        if (
            not _is_positive_int(start)
            or not _is_positive_int(stop)
            or not _is_positive_int(duration)
            or stop <= start
            or duration != stop - start
            or start < day_start
            or stop > day_end
            or (previous_stop is not None and start < previous_stop)
        ):
            return [_reason("operational_day_session_content_invalid")]
        previous_stop = stop
        if (
            not _is_hex64_string(day.verified_session_window_digests[i])
            or not _is_hex64_string(day.session_metrics_summary_digests[i])
            or not _is_positive_int(day.source_event_digest_counts[i])
            or not _is_plain_non_empty_string(day.session_run_ids[i])
            or not _is_plain_non_empty_string(day.session_window_ids[i])
            or not _is_plain_non_empty_string(day.session_aggregate_ids[i])
        ):
            return [_reason("operational_day_session_content_invalid")]
    return []


def _day_coherence_failures(day: PaperAttestedOperationalDayEvidence) -> list[str]:
    """Re-check the day's UTC-day boundary arithmetic, session-list lengths, and per-session content."""

    hard: list[str] = []
    index = day.attested_utc_day_index
    if (
        not _is_positive_int(index)
        or not _is_exact_int(day.day_start_ns)
        or not _is_exact_int(day.day_end_ns)
        or not _is_exact_int(day.day_duration_ns)
        or day.day_duration_ns != _NANOSECONDS_PER_DAY
        or day.day_start_ns != index * _NANOSECONDS_PER_DAY
        or day.day_end_ns != (index + 1) * _NANOSECONDS_PER_DAY
    ):
        hard.append(_reason("operational_day_coherence_invalid"))
        return hard
    session_count = day.session_count
    if (
        not _is_positive_int(session_count)
        or not _is_positive_int(day.minimum_sessions_per_day)
        or session_count < day.minimum_sessions_per_day
    ):
        hard.append(_reason("operational_day_coherence_invalid"))
        return hard
    for list_field in _DAY_SESSION_LIST_FIELDS:
        value = getattr(day, list_field)
        if type(value) is not tuple or len(value) != session_count:
            hard.append(_reason("operational_day_coherence_invalid"))
            return hard
    # Lengths are coherent; recompute the per-session content invariants (reseal defense, not a length trust).
    hard.extend(_day_session_content_failures(day, session_count))
    return hard


def _day_failures(day: PaperAttestedOperationalDayEvidence, expected_digest: str, correlation_id: str) -> list[str]:
    """Full per-day trust boundary: digest reproof, provenance re-pin, status, unsafe flags, coherence, scope."""

    hard: list[str] = []

    recomputed = _recomputed_day_digest_or_none(day)
    if (
        recomputed is None
        or not _is_hex64_string(day.attested_operational_day_evidence_digest)
        or day.attested_operational_day_evidence_digest != recomputed
        or day.attested_operational_day_evidence_digest != expected_digest
    ):
        hard.append(_reason("operational_day_digest_mismatch"))

    if day.schema_version != _EXPECTED_DAY_SCHEMA_VERSION or day.evidence_version != _EXPECTED_DAY_EVIDENCE_VERSION:
        hard.append(_reason("operational_day_schema_invalid"))
    if (
        day.attestation_source != _EXPECTED_ATTESTATION_SOURCE
        or day.attestation_scope != _EXPECTED_ATTESTATION_SCOPE
        or day.attestation_version != _EXPECTED_ATTESTATION_VERSION
        or day.operational_origin != _EXPECTED_OPERATIONAL_ORIGIN
        or day.utc_day_policy != _UTC_DAY_POLICY
    ):
        hard.append(_reason("operational_day_provenance_invalid"))
    if (
        day.status is not PaperAttestedOperationalDayEvidenceStatus.READY
        or day.ready is not True
        or day.reason_codes != ()
    ):
        hard.append(_reason("operational_day_not_ready"))
    if day.operator_attested_operational_day is not True:
        hard.append(_reason("operational_day_not_attested"))
    if any(getattr(day, flag) is not True for flag in _DAY_TRUE_FLAGS) or any(
        getattr(day, flag) is not False for flag in _DAY_FALSE_FLAGS
    ):
        hard.append(_reason("operational_day_unsafe_flags"))

    hard.extend(_day_coherence_failures(day))

    if _plain_str_or_empty(day.correlation_id) != correlation_id:
        hard.append(_reason("correlation_id_mismatch"))

    return hard


def build_paper_attested_operational_thirty_day_gate_decision(
    operational_days: tuple[PaperAttestedOperationalDayEvidence, ...],
    *,
    expected_operational_day_evidence_digests: tuple[str, ...],
    gate_decision_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperAttestedOperationalThirtyDayGateDecision:
    """Decide whether the supplied attested operational days form a consecutive >=30 UTC-epoch-day sequence.

    ``operational_days`` must be a non-empty exact tuple of exact ``PaperAttestedOperationalDayEvidence``;
    ``expected_operational_day_evidence_digests`` an equal-length tuple of lowercase hex64 anchors positionally
    aligned to the days. Every supplied day (not only the selected first 30) must re-prove its digest, be
    READY / attested / paper-safe / coherent, same-market, same-caller-correlation, replay-free, and the days
    must arrive strictly increasing by ``attested_utc_day_index`` with no gaps. Input order is never silently
    sorted. Wrong-typed inputs, malformed anchors/ids/metadata, or forbidden BIST/live/order/capital/readiness/
    clock tokens raise ``PaperAttestedOperationalThirtyDayGateDecisionError``; every trust/value failure maps to
    ``status=REJECTED``.
    """
    if type(operational_days) is not tuple or len(operational_days) == 0:
        raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason("days_malformed"))
    if any(type(day) is not PaperAttestedOperationalDayEvidence for day in operational_days):
        raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason("days_malformed"))
    if type(expected_operational_day_evidence_digests) is not tuple:
        raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason("anchor_count_mismatch"))
    if len(expected_operational_day_evidence_digests) != len(operational_days):
        raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason("anchor_count_mismatch"))
    for anchor in expected_operational_day_evidence_digests:
        if not _is_hex64_string(anchor):
            raise PaperAttestedOperationalThirtyDayGateDecisionError(
                _reason("expected_operational_day_evidence_digest_invalid")
            )
    gate_decision_id = _require_plain_non_empty_string(gate_decision_id, "gate_decision_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (gate_decision_id, correlation_id, *_metadata_texts(metadata_pairs))
    if _has_scope_violation(*scope_texts):
        raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason("scope_violation"))
    if _has_clock_token(*scope_texts):
        raise PaperAttestedOperationalThirtyDayGateDecisionError(_reason("clock_token_forbidden"))

    hard: list[str] = []

    # Per-day trust boundary (deterministic order over the caller-supplied day order).
    for day, expected_digest in zip(operational_days, expected_operational_day_evidence_digests, strict=True):
        hard.extend(_day_failures(day, expected_digest, correlation_id))

    # Supplied / verified echoes (safe extraction; used for output + cross-day rules).
    supplied_indices = tuple(_safe_int_value(day.attested_utc_day_index) for day in operational_days)
    verified_digests = tuple(
        _safe_digest_value(day.attested_operational_day_evidence_digest) for day in operational_days
    )
    evidence_ids = tuple(_plain_str_or_empty(day.operational_day_evidence_id) for day in operational_days)
    attestation_ids = tuple(_plain_str_or_empty(day.attestation_id) for day in operational_days)
    attestor_ids = tuple(_plain_str_or_empty(day.attestor_id) for day in operational_days)
    per_day_session_counts = tuple(_safe_int_value(day.session_count) for day in operational_days)
    per_day_window_digests = tuple(_str_tuple(day.verified_session_window_digests) for day in operational_days)
    per_day_window_ids = tuple(_str_tuple(day.session_window_ids) for day in operational_days)
    per_day_run_ids = tuple(_str_tuple(day.session_run_ids) for day in operational_days)
    per_day_metrics_summary_digests = tuple(_str_tuple(day.session_metrics_summary_digests) for day in operational_days)

    # Cross-day duplicate / replay rules. A duplicate attestor_id is allowed (one operator signs many days).
    def _has_dupes(values: tuple[object, ...]) -> bool:
        listed = [value for value in values if value != "" and value != 0]
        return len(set(listed)) != len(listed)

    if _has_dupes(supplied_indices):
        hard.append(_reason("duplicate_utc_day_index"))
    if _has_dupes(verified_digests):
        hard.append(_reason("duplicate_operational_day_digest"))
    if _has_dupes(evidence_ids):
        hard.append(_reason("duplicate_operational_day_evidence_id"))
    if _has_dupes(attestation_ids):
        hard.append(_reason("duplicate_attestation_id"))

    flat_window_digests = tuple(digest for day_digests in per_day_window_digests for digest in day_digests)
    if _has_dupes(flat_window_digests):
        hard.append(_reason("duplicate_session_window_digest_across_days"))
    flat_run_ids = tuple(run_id for day_run_ids in per_day_run_ids for run_id in day_run_ids)
    if _has_dupes(flat_run_ids):
        hard.append(_reason("duplicate_session_run_id_across_days"))
    flat_window_ids = tuple(window_id for day_window_ids in per_day_window_ids for window_id in day_window_ids)
    if _has_dupes(flat_window_ids):
        hard.append(_reason("duplicate_session_window_id_across_days"))

    # Common scope: one market across all days.
    market_symbols = {_plain_str_or_empty(day.market_symbol) for day in operational_days}
    if len(market_symbols) != 1 or "" in market_symbols:
        hard.append(_reason("market_symbol_mismatch"))

    # Order + consecutiveness (never silently sorted; strictly increasing, gapless).
    unsorted = False
    gapped = False
    for previous_index, current_index in zip(supplied_indices, supplied_indices[1:], strict=False):
        if not _is_exact_int(previous_index) or not _is_exact_int(current_index) or current_index <= previous_index:
            unsorted = True
        elif current_index != previous_index + 1:
            gapped = True
    if unsorted:
        hard.append(_reason("utc_day_indices_unsorted"))
    if gapped:
        hard.append(_reason("utc_day_indices_not_consecutive"))

    hard = sorted(set(hard))

    day_count = len(operational_days)
    if hard:
        status = PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
        ready = False
        reason_codes = tuple(hard)
        decided = False
        satisfied = False
        operational_days_consumed = False
        consecutive_day_count = 0
        selected_start = 0
        selected_end = 0
        selected_indices: tuple[int, ...] = ()
        selected_digests: tuple[str, ...] = ()
        market_symbol = ""
    else:
        status = PaperAttestedOperationalThirtyDayGateDecisionStatus.READY
        ready = True
        reason_codes = ()
        decided = True
        operational_days_consumed = True
        consecutive_day_count = day_count
        market_symbol = next(iter(market_symbols))
        satisfied = day_count >= _MINIMUM_CONSECUTIVE_UTC_DAYS
        if satisfied:
            selected_start = supplied_indices[0]
            selected_end = supplied_indices[_MINIMUM_CONSECUTIVE_UTC_DAYS - 1]
            selected_indices = supplied_indices[:_MINIMUM_CONSECUTIVE_UTC_DAYS]
            selected_digests = verified_digests[:_MINIMUM_CONSECUTIVE_UTC_DAYS]
        else:
            selected_start = 0
            selected_end = 0
            selected_indices = ()
            selected_digests = ()

    decision_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "decision_version": _DECISION_VERSION,
        "status": status,
        "ready": ready,
        "gate_decision_id": gate_decision_id,
        "correlation_id": correlation_id,
        "market_symbol": market_symbol,
        "minimum_consecutive_utc_days": _MINIMUM_CONSECUTIVE_UTC_DAYS,
        "day_count": day_count,
        "consecutive_day_count": consecutive_day_count,
        "gate_basis": _GATE_BASIS,
        "gate_scope": _GATE_SCOPE,
        "gate_policy_id": _GATE_POLICY_ID,
        "utc_day_policy": _UTC_DAY_POLICY,
        "selected_start_utc_day_index": selected_start,
        "selected_end_utc_day_index": selected_end,
        "selected_utc_day_indices": selected_indices,
        "supplied_utc_day_indices": supplied_indices,
        "selected_operational_day_evidence_digests": selected_digests,
        "supplied_operational_day_evidence_digests": verified_digests,
        "expected_operational_day_evidence_digests": tuple(expected_operational_day_evidence_digests),
        "verified_operational_day_evidence_digests": verified_digests,
        "operational_day_evidence_ids": evidence_ids,
        "attestation_ids": attestation_ids,
        "attestor_ids": attestor_ids,
        "per_day_session_counts": per_day_session_counts,
        "per_day_window_digests": per_day_window_digests,
        "per_day_window_ids": per_day_window_ids,
        "per_day_run_ids": per_day_run_ids,
        "per_day_metrics_summary_digests": per_day_metrics_summary_digests,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
        "attested_operational_thirty_day_gate_decided": decided,
        "attested_operational_thirty_day_gate_satisfied": satisfied,
        "operational_days_consumed": operational_days_consumed,
    }
    seed = PaperAttestedOperationalThirtyDayGateDecision(
        attested_operational_thirty_day_gate_decision_digest="", **decision_fields
    )  # type: ignore[arg-type]
    return replace(
        seed,
        attested_operational_thirty_day_gate_decision_digest=paper_attested_operational_thirty_day_gate_decision_digest(
            seed
        ),
    )


def _canonical_field_value(field_name: str, value: object) -> object:
    if field_name == "status":
        return value.value  # type: ignore[attr-defined]
    if field_name == "metadata":
        return [[key, item] for key, item in value]  # type: ignore[misc]
    if type(value) is tuple:
        return [list(item) if type(item) is tuple else item for item in value]
    return value


def _decision_payload_from(decision: PaperAttestedOperationalThirtyDayGateDecision) -> dict[str, object]:
    """Canonical payload over EVERY public field except the self-digest (complete by construction)."""

    payload: dict[str, object] = {}
    for field in fields(decision):
        if field.name == "attested_operational_thirty_day_gate_decision_digest":
            continue
        payload[field.name] = _canonical_field_value(field.name, getattr(decision, field.name))
    return payload


def paper_attested_operational_thirty_day_gate_decision_to_dict(
    decision: PaperAttestedOperationalThirtyDayGateDecision,
) -> dict[str, object]:
    """Canonical JSON-ready mapping for the gate decision, including its self-digest."""

    payload = _decision_payload_from(decision)
    payload["attested_operational_thirty_day_gate_decision_digest"] = (
        decision.attested_operational_thirty_day_gate_decision_digest
    )
    return payload


def paper_attested_operational_thirty_day_gate_decision_digest(
    decision: PaperAttestedOperationalThirtyDayGateDecision,
) -> str:
    """Recompute the canonical gate-decision digest, excluding only the self-digest field."""

    return _canonical_digest(_decision_payload_from(decision))


__all__ = [
    "PaperAttestedOperationalThirtyDayGateDecision",
    "PaperAttestedOperationalThirtyDayGateDecisionError",
    "PaperAttestedOperationalThirtyDayGateDecisionStatus",
    "build_paper_attested_operational_thirty_day_gate_decision",
    "paper_attested_operational_thirty_day_gate_decision_digest",
    "paper_attested_operational_thirty_day_gate_decision_to_dict",
]
