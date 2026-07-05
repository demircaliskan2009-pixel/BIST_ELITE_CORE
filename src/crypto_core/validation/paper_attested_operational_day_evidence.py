"""Deterministic paper attested operational-day evidence (PRDV4 Stage 4 operational prerequisite, v1).

This validation artifact binds one or more already-proven ``PaperDeterministicTimeWindowEvidence`` windows to
ONE operator-attested UTC epoch day. It is paper-only, deterministic, digest-bound, and fail-closed. It is an
ATTESTATION artifact — an operator asserts that the supplied digest-bound deterministic paper windows belong
to one real UTC day; the module does NOT and CANNOT prove that assertion from a machine clock.

Governance (user-approved, Codex-repaired design for this slice):

* the operational-day origin is ``operator_attested_not_machine_proven.v1`` — a caller-supplied attestation
  (``attestor_id`` / ``attestation_id`` plus fixed enumerated ``attestation_source`` / ``attestation_scope`` /
  ``attestation_version`` constants), never a free-text proof and never a wall-clock reading;
* each consumed window is re-proven at its digest boundary (recompute == carried == caller anchor), required
  ``READY`` / ``ready`` / empty ``reason_codes`` / ``sample_eligible`` / positive-duration /
  ``source_event_digest_count > 0`` / paper-only / non-over-claiming, and required to fall FULLY inside the
  attested UTC day bucket ``[day_index * 86_400_000_000_000, (day_index + 1) * 86_400_000_000_000)``;
* windows must share one ``market_symbol``, be ordered by ``started_at_ns``, non-overlapping (adjacent
  allowed), digest-distinct, and ``run_id``-distinct;
* machine time origin is explicitly NOT proven: ``machine_time_origin_proven`` / ``timestamp_origin_proven`` /
  ``real_wall_clock_used`` / ``real_time_paper_operation_proven`` / ``operational_day_machine_proven`` are
  fixed ``False`` and no code path may set them True.

Status semantics: ``status=READY`` means only that an operator attested ONE UTC day whose supplied
deterministic paper windows re-prove their digests and fall inside that day. READY does NOT mean
machine-proven real-time paper operation, does NOT mean operational readiness, does NOT mean the >=30-day gate
is satisfied, does NOT mean PRDV4 Stage-4 completion, and does NOT mean live / shadow / Deribit readiness.
This artifact cannot prove real orders, real capital, or profitability. Any digest / schema / status / trust /
inclusion / ordering failure maps to ``status=REJECTED`` (fail-closed); wrong-typed or malformed caller input
raises ``PaperAttestedOperationalDayEvidenceError``.

Roadmap (non-binding, encoded for later slices): a future ``PaperOperationalThirtyDayGateDecision`` MUST
require CONSECUTIVE UTC day indices across >=30 attested operational-day evidences; and completion v2 MUST
align operational day indices with the exact return-series / Sharpe bucket day indices before PRDV4 Stage-4
completion can be considered. This artifact preserves the day/window fields needed for that alignment.

It does NOT decide a 30-day gate, does NOT run the Stage-4 comparator, does NOT construct any Stage-4 object,
does NOT set ``prdv4_stage4_complete``, and calls no wall-clock, runtime, service, execution, venue, scheduler,
filesystem, network, or random surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from enum import Enum

from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)

_SCHEMA_VERSION = "paper-attested-operational-day-evidence.v1"
_EVIDENCE_VERSION = "paper-attested-operational-day-evidence.v1"
_REASON_PREFIX = "paper_attested_operational_day_evidence"

_EXPECTED_WINDOW_SCHEMA_VERSION = "paper-deterministic-time-window-evidence.v1"
_EXPECTED_WINDOW_TIME_VERSION = "paper-deterministic-time-window.v1"

_UTC_DAY_POLICY = "utc_epoch_day_index.v1"
_NANOSECONDS_PER_DAY = 86_400_000_000_000
_MINIMUM_SESSIONS_PER_DAY = 1

_ATTESTATION_SOURCE = "operator_attested_not_machine_proven.v1"
_ATTESTATION_SCOPE = "single_utc_day_digest_bound_paper_windows.v1"
_ATTESTATION_VERSION = "paper-attested-operational-day-attestation.v1"
_OPERATIONAL_ORIGIN = "operator_attested_not_machine_proven.v1"

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

# Window flags that must be exactly ``True`` / ``False`` for a window to be a trusted operational-day session.
_WINDOW_TRUE_FLAGS = ("paper_only", "injected_deterministic_time_window")
_WINDOW_FALSE_FLAGS = (
    "prdv4_stage4_complete",
    "live_ready",
    "shadow_ready",
    "profitability_proven",
    "edge_proven",
    "production_execution",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "deribit_ready",
    "operational_readiness",
    "sharpe_computed",
    "return_series_computed",
    "thirty_day_gate_satisfied",
    "stage4_comparator_invoked",
    "real_wall_clock_used",
    "timestamp_origin_proven",
)


class PaperAttestedOperationalDayEvidenceError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed windows / ids / digests / day index / metadata / tokens)."""


class PaperAttestedOperationalDayEvidenceStatus(str, Enum):
    """Attested operational-day status. READY is operator attestation, never machine-proven real-time operation."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperAttestedOperationalDayEvidence:
    """Immutable, digest-bound paper attested operational-day evidence (operator-attested, not machine-proven).

    ``status=READY`` only when every consumed window re-proves its digest, is READY / eligible / paper-safe /
    source-event-backed, falls fully inside the single attested UTC day, and the windows are same-market,
    ordered, non-overlapping, digest-distinct and run_id-distinct. READY reflects an OPERATOR ATTESTATION —
    ``machine_time_origin_proven`` / ``timestamp_origin_proven`` / ``real_wall_clock_used`` /
    ``real_time_paper_operation_proven`` / ``operational_day_machine_proven`` are constant False. READY does
    NOT mean operational readiness, the >=30-day gate, PRDV4 Stage-4 completion, or live/shadow/Deribit
    readiness; it proves no real orders, no real capital, and no profitability.
    """

    schema_version: str
    evidence_version: str
    status: PaperAttestedOperationalDayEvidenceStatus
    ready: bool
    operational_day_evidence_id: str
    correlation_id: str
    market_symbol: str
    attested_utc_day_index: int
    day_start_ns: int
    day_end_ns: int
    day_duration_ns: int
    utc_day_policy: str
    session_count: int
    minimum_sessions_per_day: int
    expected_session_window_digests: tuple[str, ...]
    verified_session_window_digests: tuple[str, ...]
    session_window_ids: tuple[str, ...]
    session_run_ids: tuple[str, ...]
    session_aggregate_ids: tuple[str, ...]
    session_started_at_ns_list: tuple[int, ...]
    session_stopped_at_ns_list: tuple[int, ...]
    session_window_duration_ns_list: tuple[int, ...]
    session_metrics_summary_digests: tuple[str, ...]
    source_event_digest_counts: tuple[int, ...]
    attestor_id: str
    attestation_id: str
    attestation_source: str
    attestation_scope: str
    attestation_version: str
    operational_origin: str
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    attested_operational_day_evidence_digest: str
    paper_only: bool = True
    session_windows_consumed: bool = True
    operator_attested_operational_day: bool = False
    operational_day_machine_proven: bool = False
    machine_time_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    real_wall_clock_used: bool = False
    real_time_paper_operation_proven: bool = False
    operational_readiness: bool = False
    prdv4_stage4_complete: bool = False
    thirty_day_gate_satisfied: bool = False
    thirty_day_gate_decided: bool = False
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


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperAttestedOperationalDayEvidenceError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperAttestedOperationalDayEvidenceError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperAttestedOperationalDayEvidenceError(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperAttestedOperationalDayEvidenceError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperAttestedOperationalDayEvidenceError(_reason("metadata_malformed"))
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


def _recomputed_window_digest_or_none(window: PaperDeterministicTimeWindowEvidence) -> str | None:
    try:
        return paper_deterministic_time_window_evidence_digest(window)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        return None


def _window_failures(
    window: PaperDeterministicTimeWindowEvidence,
    expected_digest: str,
    day_start_ns: int,
    day_end_ns: int,
) -> list[str]:
    """Trust + inclusion boundary for a single window. Value failures are REJECTED reasons, never raises."""

    hard: list[str] = []

    recomputed = _recomputed_window_digest_or_none(window)
    if (
        recomputed is None
        or not _is_hex64_string(window.time_window_digest)
        or window.time_window_digest != recomputed
        or window.time_window_digest != expected_digest
    ):
        hard.append(_reason("session_window_digest_mismatch"))

    if (
        window.schema_version != _EXPECTED_WINDOW_SCHEMA_VERSION
        or window.time_window_version != _EXPECTED_WINDOW_TIME_VERSION
    ):
        hard.append(_reason("session_window_schema_invalid"))
    if (
        window.status is not PaperDeterministicTimeWindowEvidenceStatus.READY
        or window.ready is not True
        or window.reason_codes != ()
    ):
        hard.append(_reason("session_window_not_ready"))
    if window.sample_eligible is not True:
        hard.append(_reason("session_window_not_sample_eligible"))
    if not _is_positive_int(window.source_event_digest_count):
        hard.append(_reason("session_window_source_events_missing"))

    if any(getattr(window, flag) is not True for flag in _WINDOW_TRUE_FLAGS) or any(
        getattr(window, flag) is not False for flag in _WINDOW_FALSE_FLAGS
    ):
        hard.append(_reason("session_window_unsafe_flags"))

    started = window.started_at_ns
    stopped = window.stopped_at_ns
    duration = window.window_duration_ns
    if (
        not _is_positive_int(started)
        or not _is_positive_int(stopped)
        or not _is_positive_int(duration)
        or stopped <= started
        or duration != stopped - started
    ):
        hard.append(_reason("session_window_timestamps_invalid"))
    elif started < day_start_ns or stopped > day_end_ns:
        hard.append(_reason("session_window_outside_attested_day"))

    return hard


def build_paper_attested_operational_day_evidence(
    session_windows: tuple[PaperDeterministicTimeWindowEvidence, ...],
    *,
    expected_session_window_digests: tuple[str, ...],
    attested_utc_day_index: int,
    attestor_id: str,
    attestation_id: str,
    operational_day_evidence_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperAttestedOperationalDayEvidence:
    """Bind digest-proven deterministic paper windows to ONE operator-attested UTC day (v1, attestation-only).

    ``session_windows`` must be a non-empty exact tuple of exact ``PaperDeterministicTimeWindowEvidence``;
    ``expected_session_window_digests`` an equal-length tuple of lowercase hex64 anchors positionally aligned
    to the windows. Each window re-proves its digest (recompute == carried == anchor), is READY / eligible /
    source-event-backed / paper-safe, and falls fully inside the attested UTC day. Windows must be same-market,
    ordered by ``started_at_ns``, non-overlapping (adjacent allowed), digest-distinct and run_id-distinct.
    READY reflects an OPERATOR ATTESTATION, never machine-proven real-time operation. Wrong-typed inputs,
    malformed anchors/ids/metadata, or forbidden BIST/live/order/capital/readiness/clock tokens raise
    ``PaperAttestedOperationalDayEvidenceError``; every trust/value failure maps to ``status=REJECTED``.
    """
    if type(session_windows) is not tuple or len(session_windows) == 0:
        raise PaperAttestedOperationalDayEvidenceError(_reason("windows_malformed"))
    if any(type(window) is not PaperDeterministicTimeWindowEvidence for window in session_windows):
        raise PaperAttestedOperationalDayEvidenceError(_reason("windows_malformed"))
    if type(expected_session_window_digests) is not tuple:
        raise PaperAttestedOperationalDayEvidenceError(_reason("anchor_count_mismatch"))
    if len(expected_session_window_digests) != len(session_windows):
        raise PaperAttestedOperationalDayEvidenceError(_reason("anchor_count_mismatch"))
    for anchor in expected_session_window_digests:
        if not _is_hex64_string(anchor):
            raise PaperAttestedOperationalDayEvidenceError(_reason("expected_session_window_digest_invalid"))
    if not _is_positive_int(attested_utc_day_index):
        raise PaperAttestedOperationalDayEvidenceError(_reason("attested_utc_day_index_invalid"))
    attestor_id = _require_plain_non_empty_string(attestor_id, "attestor_id")
    attestation_id = _require_plain_non_empty_string(attestation_id, "attestation_id")
    operational_day_evidence_id = _require_plain_non_empty_string(
        operational_day_evidence_id, "operational_day_evidence_id"
    )
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (
        attestor_id,
        attestation_id,
        operational_day_evidence_id,
        correlation_id,
        *_metadata_texts(metadata_pairs),
    )
    if _has_scope_violation(*scope_texts):
        raise PaperAttestedOperationalDayEvidenceError(_reason("scope_violation"))
    if _has_clock_token(*scope_texts):
        raise PaperAttestedOperationalDayEvidenceError(_reason("clock_token_forbidden"))

    day_start_ns = attested_utc_day_index * _NANOSECONDS_PER_DAY
    day_end_ns = (attested_utc_day_index + 1) * _NANOSECONDS_PER_DAY

    hard: list[str] = []

    # Per-window trust + inclusion boundary (deterministic order over the caller-supplied window order).
    for window, expected_digest in zip(session_windows, expected_session_window_digests, strict=True):
        hard.extend(_window_failures(window, expected_digest, day_start_ns, day_end_ns))

    # Cross-window rules: same market, ordered, non-overlapping, distinct run_id, distinct digest.
    market_symbols = {_plain_str_or_empty(window.market_symbol) for window in session_windows}
    if len(market_symbols) != 1 or "" in market_symbols:
        hard.append(_reason("market_symbol_mismatch"))

    run_ids = [_plain_str_or_empty(window.run_id) for window in session_windows]
    if len(set(run_ids)) != len(run_ids) or any(rid == "" for rid in run_ids):
        hard.append(_reason("duplicate_session_run_id"))

    verified_digests = [_safe_digest_value(window.time_window_digest) for window in session_windows]
    if (
        len(set(expected_session_window_digests)) != len(expected_session_window_digests)
        or any(digest == "" for digest in verified_digests)
        or len(set(verified_digests)) != len(verified_digests)
    ):
        hard.append(_reason("duplicate_session_window_digest"))

    ordered = True
    non_overlapping = True
    for previous, current in zip(session_windows, session_windows[1:], strict=False):
        prev_start = previous.started_at_ns
        cur_start = current.started_at_ns
        if not _is_exact_int(prev_start) or not _is_exact_int(cur_start) or cur_start < prev_start:
            ordered = False
        prev_stop = previous.stopped_at_ns
        if _is_exact_int(prev_stop) and _is_exact_int(cur_start) and prev_stop > cur_start:
            non_overlapping = False
    if not ordered:
        hard.append(_reason("session_windows_unordered"))
    if not non_overlapping:
        hard.append(_reason("session_windows_overlap"))

    hard = sorted(set(hard))
    if hard:
        status = PaperAttestedOperationalDayEvidenceStatus.REJECTED
        ready = False
        reason_codes = tuple(hard)
        operator_attested_operational_day = False
    else:
        status = PaperAttestedOperationalDayEvidenceStatus.READY
        ready = True
        reason_codes = ()
        operator_attested_operational_day = True

    evidence_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "evidence_version": _EVIDENCE_VERSION,
        "status": status,
        "ready": ready,
        "operational_day_evidence_id": operational_day_evidence_id,
        "correlation_id": correlation_id,
        "market_symbol": next(iter(market_symbols)) if len(market_symbols) == 1 else "",
        "attested_utc_day_index": attested_utc_day_index,
        "day_start_ns": day_start_ns,
        "day_end_ns": day_end_ns,
        "day_duration_ns": _NANOSECONDS_PER_DAY,
        "utc_day_policy": _UTC_DAY_POLICY,
        "session_count": len(session_windows),
        "minimum_sessions_per_day": _MINIMUM_SESSIONS_PER_DAY,
        "expected_session_window_digests": tuple(expected_session_window_digests),
        "verified_session_window_digests": tuple(verified_digests),
        "session_window_ids": tuple(_plain_str_or_empty(window.window_id) for window in session_windows),
        "session_run_ids": tuple(run_ids),
        "session_aggregate_ids": tuple(_plain_str_or_empty(window.aggregate_id) for window in session_windows),
        "session_started_at_ns_list": tuple(
            window.started_at_ns if _is_exact_int(window.started_at_ns) else 0 for window in session_windows
        ),
        "session_stopped_at_ns_list": tuple(
            window.stopped_at_ns if _is_exact_int(window.stopped_at_ns) else 0 for window in session_windows
        ),
        "session_window_duration_ns_list": tuple(
            window.window_duration_ns if _is_exact_int(window.window_duration_ns) else 0 for window in session_windows
        ),
        "session_metrics_summary_digests": tuple(
            _safe_digest_value(window.metrics_summary_digest) for window in session_windows
        ),
        "source_event_digest_counts": tuple(
            window.source_event_digest_count if _is_exact_int(window.source_event_digest_count) else 0
            for window in session_windows
        ),
        "attestor_id": attestor_id,
        "attestation_id": attestation_id,
        "attestation_source": _ATTESTATION_SOURCE,
        "attestation_scope": _ATTESTATION_SCOPE,
        "attestation_version": _ATTESTATION_VERSION,
        "operational_origin": _OPERATIONAL_ORIGIN,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
        "operator_attested_operational_day": operator_attested_operational_day,
    }
    seed = PaperAttestedOperationalDayEvidence(attested_operational_day_evidence_digest="", **evidence_fields)  # type: ignore[arg-type]
    return replace(seed, attested_operational_day_evidence_digest=paper_attested_operational_day_evidence_digest(seed))


def _evidence_payload_from(evidence: PaperAttestedOperationalDayEvidence) -> dict[str, object]:
    """Canonical payload over EVERY public field except the self-digest (complete by construction)."""

    payload: dict[str, object] = {}
    for field in fields(evidence):
        if field.name == "attested_operational_day_evidence_digest":
            continue
        value = getattr(evidence, field.name)
        if field.name == "status":
            payload[field.name] = evidence.status.value
        elif field.name == "metadata":
            payload[field.name] = [[key, item] for key, item in evidence.metadata]
        elif type(value) is tuple:
            payload[field.name] = list(value)
        else:
            payload[field.name] = value
    return payload


def paper_attested_operational_day_evidence_to_dict(
    evidence: PaperAttestedOperationalDayEvidence,
) -> dict[str, object]:
    """Canonical JSON-ready mapping for the attested operational-day evidence, including its self-digest."""

    payload = _evidence_payload_from(evidence)
    payload["attested_operational_day_evidence_digest"] = evidence.attested_operational_day_evidence_digest
    return payload


def paper_attested_operational_day_evidence_digest(evidence: PaperAttestedOperationalDayEvidence) -> str:
    """Recompute the canonical attested operational-day evidence digest, excluding only the self-digest field."""

    return _canonical_digest(_evidence_payload_from(evidence))


__all__ = [
    "PaperAttestedOperationalDayEvidence",
    "PaperAttestedOperationalDayEvidenceError",
    "PaperAttestedOperationalDayEvidenceStatus",
    "build_paper_attested_operational_day_evidence",
    "paper_attested_operational_day_evidence_digest",
    "paper_attested_operational_day_evidence_to_dict",
]
