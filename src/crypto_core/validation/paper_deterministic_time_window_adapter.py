"""Paper deterministic time-window adapter — deterministic, paper-only, fail-closed evidence that attaches an
explicit INJECTED nanosecond time window to a ``PaperSessionMetricsSummary``.

Phase-map slice §10.4.2 (``docs/crypto_core/paper_trading_phase_map.md`` §10.4): the time/methodology adapter
that makes deterministic window evidence available to a LATER paper-vs-backtest bridge (§10.4.3) — WITHOUT
crossing the deterministic boundary. It is a *validation / audit evidence artifact*, NOT a clock and NOT a
metrics engine: it consumes one already-proven ``PaperSessionMetricsSummary`` (§10.4.1), re-proves its
self-digest via the PUBLIC ``paper_session_metrics_summary_digest``, re-checks the summary's invariants, takes
CALLER-INJECTED ``started_at_ns`` / ``stopped_at_ns`` integers, and binds one frozen, digest-bound
``PaperDeterministicTimeWindowEvidence``.

INJECTED TIME ONLY — no real wall-clock. The timestamps are caller-supplied integers; their origin is NOT
proven (``timestamp_origin_proven=False``, ``real_wall_clock_used=False``). The module imports and calls no
clock surface at all (``time`` / ``datetime`` / ``perf_counter`` / ``monotonic``) — alias-resistant AST tests
enforce this — and it rejects clock-suggesting tokens (``wall_clock`` / ``datetime.now`` / ``time.time_ns`` /
``perf_counter`` / ``server_time`` / ``exchange_time`` / ``clock`` / …) in the supplied ``window_id`` /
``methodology_id`` / metadata. It computes only the integer ``window_duration_ns = stopped_at_ns -
started_at_ns``: NO float days, NO annualization, NO Sharpe, NO return series, NO 30-day-gate satisfaction, and
it never imports or invokes ``stage4_comparator`` / ``Stage4PaperSummary`` / ``compare_stage4``.

Trust boundary (fail-closed): the summary self-digest must re-prove (recompute == stored ==
``expected_metrics_summary_digest``); the summary must be the expected schema + ``READY`` + paper-safe +
non-over-claiming with coherent non-negative counts, canonical gross totals (``abs_realized_pnl_total ==
abs(realized_pnl_total)``), caller-matching ids, and a ``ready`` flag consistent with its readiness verdict.
``status=READY`` over a fully trusted summary + a valid window. ``sample_eligible`` is True ONLY for a
positive-duration window with ≥1 observation over a CANDIDATE summary — a zero-duration / zero-observation /
non-candidate window is represented (``status=READY``) but ``sample_eligible=False`` with a context reason; no
verdict is upgraded. Call-level malformed input (wrong-typed summary, malformed digest/ids, non-exact-int
timestamps, malformed metadata, forbidden BIST/live/order or clock token) raises
``PaperDeterministicTimeWindowEvidenceError``; trust / value failures map to ``status=REJECTED``.

Non-overclaim: this evidence proves only that a deterministic injected time window was attached to a trusted
paper metrics summary. It is NOT PRDV4 Stage 4 completion, NOT live/shadow/operational readiness, NOT
Deribit/connector readiness, NOT a Sharpe / return-series / 30-day-gate / Stage-4-comparator computation, NOT a
profitability/edge proof; it proves NO timestamp origin and uses NO real wall-clock — all carried as explicit
``False`` flags, digest-bound. It does NOT import or use ``crypto_core.service.readiness`` or
``crypto_core.execution.paper_adapter`` (or any shadow/live/runtime/venue surface), no Deribit, no BIST.
Deterministic and immutable; no wall-clock/random/IO; inputs unmutated.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_session_metrics_summary import (
    PaperSessionMetricsSummary,
    PaperSessionMetricsSummaryStatus,
    paper_session_metrics_summary_digest,
)

_SCHEMA_VERSION = "paper-deterministic-time-window-evidence.v1"
_TIME_WINDOW_VERSION = "paper-deterministic-time-window.v1"
_TIMESTAMP_POLICY = "injected_deterministic_ns.v1"
_EXPECTED_SUMMARY_SCHEMA_VERSION = "paper-session-metrics-summary.v1"

_VERDICT_CANDIDATE = "PAPER_STAGE4_CANDIDATE"
_VERDICT_REVIEW = "PAPER_REVIEW_REQUIRED"
_VERDICT_BLOCKED = "PAPER_BLOCKED"

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

# Real-clock-suggesting tokens forbidden in caller ids / metadata: a real wall-clock origin cannot be proven
# from an int, so any string hinting at a live/system clock is rejected (the module itself calls no clock).
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


class PaperDeterministicTimeWindowEvidenceError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed summary / ids / digests / timestamps / metadata / tokens)."""


class PaperDeterministicTimeWindowEvidenceStatus(str, Enum):
    """Whether a trusted injected time-window evidence could be produced. Never an execution / live action."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperDeterministicTimeWindowEvidence:
    """Deterministic, immutable, digest-bound injected nanosecond time-window evidence over a metrics summary.

    ``status`` READY only when the summary re-proves + re-checks and the injected window is value-valid.
    ``ready`` mirrors ``status == READY`` (well-formed evidence). ``sample_eligible`` True ONLY for a
    positive-duration window with ≥1 observation over a CANDIDATE summary; otherwise the window is represented
    but not eligible. INJECTED time only — ``real_wall_clock_used`` / ``timestamp_origin_proven`` False;
    ``injected_deterministic_time_window`` True. ``paper_only`` True; every safety / non-overclaim attestation
    False. TIME injected, not measured — NOT PRDV4 Stage 4, NOT live/shadow readiness, NOT a Sharpe/30-day proof.
    """

    schema_version: str
    time_window_version: str
    status: PaperDeterministicTimeWindowEvidenceStatus
    ready: bool
    window_id: str
    methodology_id: str
    timestamp_policy: str
    run_id: str
    aggregate_id: str
    correlation_id: str
    market_symbol: str
    expected_metrics_summary_digest: str
    metrics_summary_digest: str
    summary_ready: bool
    summary_readiness_verdict: str
    started_at_ns: int
    stopped_at_ns: int
    window_duration_ns: int
    sample_observation_count: int
    sample_eligible: bool
    session_bridge_count: int
    episode_count_total: int
    event_count: int
    computed_event_count: int
    no_realized_event_count: int
    source_event_digest_count: int
    closed_units_total: str
    realized_pnl_total: str
    abs_realized_pnl_total: str
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    time_window_digest: str
    paper_only: bool = True
    injected_deterministic_time_window: bool = True
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
    stage4_comparator_invoked: bool = False
    real_wall_clock_used: bool = False
    timestamp_origin_proven: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    return type(value) is str and value.strip() != ""


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_exact_int(value: object) -> bool:
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
        raise PaperDeterministicTimeWindowEvidenceError("paper_deterministic_time_window_evidence:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperDeterministicTimeWindowEvidenceError(
                "paper_deterministic_time_window_evidence:metadata_malformed"
            )
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise PaperDeterministicTimeWindowEvidenceError(
                "paper_deterministic_time_window_evidence:metadata_malformed"
            )
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


def _has_clock_token(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        lowered = text.lower()
        if any(token in lowered for token in _CLOCK_TOKENS):
            return True
    return False


def _summary_is_paper_safe(summary: PaperSessionMetricsSummary) -> bool:
    return (
        summary.paper_only is True
        and summary.prdv4_stage4_complete is False
        and summary.live_ready is False
        and summary.shadow_ready is False
        and summary.profitability_proven is False
        and summary.edge_proven is False
        and summary.production_execution is False
        and summary.real_orders_enabled is False
        and summary.real_money_enabled is False
        and summary.real_capital_reserved is False
        and summary.live_api_called is False
        and summary.scheduler_enabled is False
        and summary.auto_loop_enabled is False
        and summary.connector_invoked is False
        and summary.deribit_ready is False
        and summary.operational_readiness is False
        and summary.sharpe_computed is False
        and summary.return_series_computed is False
        and summary.thirty_day_gate_satisfied is False
    )


def build_paper_deterministic_time_window_evidence(
    metrics_summary: PaperSessionMetricsSummary,
    *,
    expected_metrics_summary_digest: str,
    started_at_ns: int,
    stopped_at_ns: int,
    window_id: str,
    methodology_id: str,
    run_id: str,
    aggregate_id: str,
    correlation_id: str,
    sample_observation_count: int = 0,
    metadata: Mapping[str, str] | None = None,
) -> PaperDeterministicTimeWindowEvidence:
    """Attach a deterministic INJECTED nanosecond window to a trusted ``PaperSessionMetricsSummary``.

    ``metrics_summary`` must be a ``PaperSessionMetricsSummary``; ``expected_metrics_summary_digest`` an exact
    plain 64-lowercase-hex ``str`` (the caller's INDEPENDENT anchor); ``started_at_ns`` / ``stopped_at_ns`` /
    ``sample_observation_count`` EXACT plain ``int`` (``bool`` / ``float`` / ``str`` / ``int`` subclass
    rejected); ``window_id`` / ``methodology_id`` / ``run_id`` / ``aggregate_id`` / ``correlation_id`` exact
    plain non-empty ``str``; ``metadata`` ``Mapping[str, str]`` or ``None``. A wrong type, malformed digest,
    empty id, a forbidden BIST/live/order token, a clock-suggesting token, malformed metadata, or a non-exact-int
    timestamp/count raises ``PaperDeterministicTimeWindowEvidenceError`` before any work.

    The summary self-digest is re-proven via the PUBLIC ``paper_session_metrics_summary_digest`` (== stored ==
    expected anchor); the summary must be the expected schema + READY + paper-safe + non-over-claiming with
    coherent non-negative counts, canonical gross totals (``abs_realized_pnl_total == abs(realized_pnl_total)``),
    caller-matching ids, and a ``ready`` flag consistent with its readiness verdict. The injected window is
    value-valid only when ``started_at_ns >= 0`` and ``stopped_at_ns >= started_at_ns`` (integer
    ``window_duration_ns`` only — no float days, no annualization). ``status=READY`` over a fully trusted
    summary + value-valid window; ``sample_eligible`` is True ONLY for a positive-duration, ≥1-observation
    window over a CANDIDATE summary (otherwise represented but not eligible, with a context reason). Any trust /
    value failure maps to ``status=REJECTED``. Deterministic and immutable; no wall-clock/random/IO; the
    summary is never mutated.
    """
    if not isinstance(metrics_summary, PaperSessionMetricsSummary):
        raise PaperDeterministicTimeWindowEvidenceError(
            "paper_deterministic_time_window_evidence:metrics_summary_malformed"
        )
    if not _is_hex64_string(expected_metrics_summary_digest):
        raise PaperDeterministicTimeWindowEvidenceError(
            "paper_deterministic_time_window_evidence:expected_metrics_summary_digest_invalid"
        )
    for name, value in (
        ("window_id", window_id),
        ("methodology_id", methodology_id),
        ("run_id", run_id),
        ("aggregate_id", aggregate_id),
        ("correlation_id", correlation_id),
    ):
        if not _is_plain_non_empty_string(value):
            raise PaperDeterministicTimeWindowEvidenceError(f"paper_deterministic_time_window_evidence:{name}_invalid")
    if not _is_exact_int(started_at_ns):
        raise PaperDeterministicTimeWindowEvidenceError(
            "paper_deterministic_time_window_evidence:started_at_ns_invalid"
        )
    if not _is_exact_int(stopped_at_ns):
        raise PaperDeterministicTimeWindowEvidenceError(
            "paper_deterministic_time_window_evidence:stopped_at_ns_invalid"
        )
    if not _is_exact_int(sample_observation_count):
        raise PaperDeterministicTimeWindowEvidenceError(
            "paper_deterministic_time_window_evidence:sample_observation_count_invalid"
        )
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(
        window_id, methodology_id, run_id, aggregate_id, correlation_id, *_metadata_texts(metadata_pairs)
    ):
        raise PaperDeterministicTimeWindowEvidenceError("paper_deterministic_time_window_evidence:scope_violation")
    if _has_clock_token(window_id, methodology_id, *_metadata_texts(metadata_pairs)):
        raise PaperDeterministicTimeWindowEvidenceError(
            "paper_deterministic_time_window_evidence:clock_token_forbidden"
        )

    hard: list[str] = []

    # Trust boundary: re-prove the summary self-digest via its PUBLIC serializer AND the caller anchor.
    try:
        recomputed_summary = paper_session_metrics_summary_digest(metrics_summary)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        recomputed_summary = None
    stored_summary = metrics_summary.summary_digest
    if recomputed_summary is None:
        hard.append("paper_deterministic_time_window_evidence:metrics_summary_malformed")
    elif (
        not _is_hex64_string(stored_summary)
        or stored_summary != recomputed_summary
        or stored_summary != expected_metrics_summary_digest
    ):
        hard.append("paper_deterministic_time_window_evidence:metrics_summary_digest_mismatch")

    # Summary schema + status + paper-safety re-check (do not trust summary bytes after digest re-proof alone).
    if metrics_summary.schema_version != _EXPECTED_SUMMARY_SCHEMA_VERSION:
        hard.append("paper_deterministic_time_window_evidence:summary_schema_invalid")
    elif metrics_summary.status is not PaperSessionMetricsSummaryStatus.READY:
        hard.append("paper_deterministic_time_window_evidence:summary_not_ready")
    if not _summary_is_paper_safe(metrics_summary):
        hard.append("paper_deterministic_time_window_evidence:summary_unsafe_flags")

    # Summary counts: exact non-negative ints + coherence; >=1 bridge; >=1 source event for a CANDIDATE summary.
    counts_ok = (
        _is_exact_int(metrics_summary.session_bridge_count)
        and metrics_summary.session_bridge_count >= 1
        and _is_exact_int(metrics_summary.episode_count_total)
        and metrics_summary.episode_count_total >= 0
        and _is_exact_int(metrics_summary.event_count)
        and metrics_summary.event_count >= 0
        and _is_exact_int(metrics_summary.computed_event_count)
        and metrics_summary.computed_event_count >= 0
        and _is_exact_int(metrics_summary.no_realized_event_count)
        and metrics_summary.no_realized_event_count >= 0
        and _is_exact_int(metrics_summary.source_event_digest_count)
        and metrics_summary.source_event_digest_count >= 0
        and metrics_summary.event_count >= metrics_summary.computed_event_count
        and metrics_summary.event_count >= metrics_summary.no_realized_event_count
    )
    if not counts_ok:
        hard.append("paper_deterministic_time_window_evidence:summary_counts_invalid")

    # Canonical gross totals + abs consistency (no recomputation of economics — only a canonical-form check).
    realized = _canonical_decimal(metrics_summary.realized_pnl_total)
    closed = _canonical_decimal(metrics_summary.closed_units_total)
    abs_total = _canonical_decimal(metrics_summary.abs_realized_pnl_total)
    if realized is None or closed is None or closed < 0 or abs_total is None:
        hard.append("paper_deterministic_time_window_evidence:summary_totals_malformed")
    elif _render_decimal(abs(realized)) != metrics_summary.abs_realized_pnl_total:
        hard.append("paper_deterministic_time_window_evidence:summary_abs_mismatch")

    # Caller ids must match the (digest-proven) summary; market is carried from the summary.
    if _plain_str_or_empty(metrics_summary.run_id) != run_id:
        hard.append("paper_deterministic_time_window_evidence:run_id_mismatch")
    if _plain_str_or_empty(metrics_summary.aggregate_id) != aggregate_id:
        hard.append("paper_deterministic_time_window_evidence:aggregate_id_mismatch")
    if _plain_str_or_empty(metrics_summary.correlation_id) != correlation_id:
        hard.append("paper_deterministic_time_window_evidence:correlation_id_mismatch")
    if _plain_str_or_empty(metrics_summary.market_symbol) == "":
        hard.append("paper_deterministic_time_window_evidence:summary_market_symbol_invalid")

    # Summary ready/verdict consistency (do not upgrade a non-candidate verdict).
    verdict = _plain_str_or_empty(metrics_summary.readiness_verdict)
    summary_ready = metrics_summary.ready if type(metrics_summary.ready) is bool else None
    expected_summary_ready = verdict == _VERDICT_CANDIDATE
    if (
        verdict not in (_VERDICT_CANDIDATE, _VERDICT_REVIEW, _VERDICT_BLOCKED)
        or summary_ready is not expected_summary_ready
    ):
        hard.append("paper_deterministic_time_window_evidence:summary_ready_verdict_inconsistent")

    # Injected window value validity (integer ns only).
    if started_at_ns < 0:
        hard.append("paper_deterministic_time_window_evidence:started_at_ns_negative")
    if stopped_at_ns < 0:
        hard.append("paper_deterministic_time_window_evidence:stopped_at_ns_negative")
    if stopped_at_ns < started_at_ns:
        hard.append("paper_deterministic_time_window_evidence:window_order_invalid")
    if sample_observation_count < 0:
        hard.append("paper_deterministic_time_window_evidence:sample_observation_count_negative")

    window_valid = started_at_ns >= 0 and stopped_at_ns >= started_at_ns
    window_duration_ns = stopped_at_ns - started_at_ns if window_valid else 0

    if hard:
        status = PaperDeterministicTimeWindowEvidenceStatus.REJECTED
        ready = False
        sample_eligible = False
        reason_codes = tuple(sorted(set(hard)))
    else:
        status = PaperDeterministicTimeWindowEvidenceStatus.READY
        ready = True
        sample_eligible = window_duration_ns > 0 and sample_observation_count >= 1 and verdict == _VERDICT_CANDIDATE
        reason_codes = (
            () if sample_eligible else ("paper_deterministic_time_window_evidence:window_not_sample_eligible",)
        )

    return _finalize_evidence(
        status=status,
        ready=ready,
        sample_eligible=sample_eligible,
        metrics_summary=metrics_summary,
        expected_metrics_summary_digest=expected_metrics_summary_digest,
        window_id=window_id,
        methodology_id=methodology_id,
        run_id=run_id,
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        started_at_ns=started_at_ns,
        stopped_at_ns=stopped_at_ns,
        window_duration_ns=window_duration_ns,
        sample_observation_count=sample_observation_count,
        reason_codes=reason_codes,
        metadata=metadata_pairs,
    )


def _finalize_evidence(
    *,
    status: PaperDeterministicTimeWindowEvidenceStatus,
    ready: bool,
    sample_eligible: bool,
    metrics_summary: PaperSessionMetricsSummary,
    expected_metrics_summary_digest: str,
    window_id: str,
    methodology_id: str,
    run_id: str,
    aggregate_id: str,
    correlation_id: str,
    started_at_ns: int,
    stopped_at_ns: int,
    window_duration_ns: int,
    sample_observation_count: int,
    reason_codes: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> PaperDeterministicTimeWindowEvidence:
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "time_window_version": _TIME_WINDOW_VERSION,
        "status": status,
        "ready": ready,
        "window_id": window_id,
        "methodology_id": methodology_id,
        "timestamp_policy": _TIMESTAMP_POLICY,
        "run_id": run_id,
        "aggregate_id": aggregate_id,
        "correlation_id": correlation_id,
        "market_symbol": _plain_str_or_empty(metrics_summary.market_symbol),
        "expected_metrics_summary_digest": expected_metrics_summary_digest,
        "metrics_summary_digest": _plain_str_or_empty(metrics_summary.summary_digest),
        "summary_ready": metrics_summary.ready if type(metrics_summary.ready) is bool else False,
        "summary_readiness_verdict": _plain_str_or_empty(metrics_summary.readiness_verdict),
        "started_at_ns": started_at_ns,
        "stopped_at_ns": stopped_at_ns,
        "window_duration_ns": window_duration_ns,
        "sample_observation_count": sample_observation_count,
        "sample_eligible": sample_eligible,
        "session_bridge_count": metrics_summary.session_bridge_count
        if _is_exact_int(metrics_summary.session_bridge_count)
        else 0,
        "episode_count_total": metrics_summary.episode_count_total
        if _is_exact_int(metrics_summary.episode_count_total)
        else 0,
        "event_count": metrics_summary.event_count if _is_exact_int(metrics_summary.event_count) else 0,
        "computed_event_count": metrics_summary.computed_event_count
        if _is_exact_int(metrics_summary.computed_event_count)
        else 0,
        "no_realized_event_count": metrics_summary.no_realized_event_count
        if _is_exact_int(metrics_summary.no_realized_event_count)
        else 0,
        "source_event_digest_count": metrics_summary.source_event_digest_count
        if _is_exact_int(metrics_summary.source_event_digest_count)
        else 0,
        "closed_units_total": _plain_str_or_empty(metrics_summary.closed_units_total),
        "realized_pnl_total": _plain_str_or_empty(metrics_summary.realized_pnl_total),
        "abs_realized_pnl_total": _plain_str_or_empty(metrics_summary.abs_realized_pnl_total),
        "reason_codes": reason_codes,
        "metadata": metadata,
    }
    seed = PaperDeterministicTimeWindowEvidence(time_window_digest="", **fields)  # type: ignore[arg-type]
    return _replace_window_digest(seed, paper_deterministic_time_window_evidence_digest(seed))


def _replace_window_digest(
    evidence: PaperDeterministicTimeWindowEvidence, digest: str
) -> PaperDeterministicTimeWindowEvidence:
    fields = _evidence_fields(evidence)
    fields["time_window_digest"] = digest
    return PaperDeterministicTimeWindowEvidence(**fields)  # type: ignore[arg-type]


def _evidence_fields(evidence: PaperDeterministicTimeWindowEvidence) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "time_window_version": evidence.time_window_version,
        "status": evidence.status,
        "ready": evidence.ready,
        "window_id": evidence.window_id,
        "methodology_id": evidence.methodology_id,
        "timestamp_policy": evidence.timestamp_policy,
        "run_id": evidence.run_id,
        "aggregate_id": evidence.aggregate_id,
        "correlation_id": evidence.correlation_id,
        "market_symbol": evidence.market_symbol,
        "expected_metrics_summary_digest": evidence.expected_metrics_summary_digest,
        "metrics_summary_digest": evidence.metrics_summary_digest,
        "summary_ready": evidence.summary_ready,
        "summary_readiness_verdict": evidence.summary_readiness_verdict,
        "started_at_ns": evidence.started_at_ns,
        "stopped_at_ns": evidence.stopped_at_ns,
        "window_duration_ns": evidence.window_duration_ns,
        "sample_observation_count": evidence.sample_observation_count,
        "sample_eligible": evidence.sample_eligible,
        "session_bridge_count": evidence.session_bridge_count,
        "episode_count_total": evidence.episode_count_total,
        "event_count": evidence.event_count,
        "computed_event_count": evidence.computed_event_count,
        "no_realized_event_count": evidence.no_realized_event_count,
        "source_event_digest_count": evidence.source_event_digest_count,
        "closed_units_total": evidence.closed_units_total,
        "realized_pnl_total": evidence.realized_pnl_total,
        "abs_realized_pnl_total": evidence.abs_realized_pnl_total,
        "reason_codes": evidence.reason_codes,
        "metadata": evidence.metadata,
    }


def _evidence_payload_from(evidence: PaperDeterministicTimeWindowEvidence) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "time_window_version": evidence.time_window_version,
        "status": evidence.status.value,
        "ready": evidence.ready,
        "window_id": evidence.window_id,
        "methodology_id": evidence.methodology_id,
        "timestamp_policy": evidence.timestamp_policy,
        "run_id": evidence.run_id,
        "aggregate_id": evidence.aggregate_id,
        "correlation_id": evidence.correlation_id,
        "market_symbol": evidence.market_symbol,
        "expected_metrics_summary_digest": evidence.expected_metrics_summary_digest,
        "metrics_summary_digest": evidence.metrics_summary_digest,
        "summary_ready": evidence.summary_ready,
        "summary_readiness_verdict": evidence.summary_readiness_verdict,
        "started_at_ns": evidence.started_at_ns,
        "stopped_at_ns": evidence.stopped_at_ns,
        "window_duration_ns": evidence.window_duration_ns,
        "sample_observation_count": evidence.sample_observation_count,
        "sample_eligible": evidence.sample_eligible,
        "session_bridge_count": evidence.session_bridge_count,
        "episode_count_total": evidence.episode_count_total,
        "event_count": evidence.event_count,
        "computed_event_count": evidence.computed_event_count,
        "no_realized_event_count": evidence.no_realized_event_count,
        "source_event_digest_count": evidence.source_event_digest_count,
        "closed_units_total": evidence.closed_units_total,
        "realized_pnl_total": evidence.realized_pnl_total,
        "abs_realized_pnl_total": evidence.abs_realized_pnl_total,
        "reason_codes": list(evidence.reason_codes),
        "metadata": _serialize_metadata(evidence.metadata),
        "paper_only": evidence.paper_only,
        "injected_deterministic_time_window": evidence.injected_deterministic_time_window,
        "prdv4_stage4_complete": evidence.prdv4_stage4_complete,
        "live_ready": evidence.live_ready,
        "shadow_ready": evidence.shadow_ready,
        "profitability_proven": evidence.profitability_proven,
        "edge_proven": evidence.edge_proven,
        "production_execution": evidence.production_execution,
        "real_orders_enabled": evidence.real_orders_enabled,
        "real_money_enabled": evidence.real_money_enabled,
        "real_capital_reserved": evidence.real_capital_reserved,
        "live_api_called": evidence.live_api_called,
        "scheduler_enabled": evidence.scheduler_enabled,
        "auto_loop_enabled": evidence.auto_loop_enabled,
        "connector_invoked": evidence.connector_invoked,
        "deribit_ready": evidence.deribit_ready,
        "operational_readiness": evidence.operational_readiness,
        "sharpe_computed": evidence.sharpe_computed,
        "return_series_computed": evidence.return_series_computed,
        "thirty_day_gate_satisfied": evidence.thirty_day_gate_satisfied,
        "stage4_comparator_invoked": evidence.stage4_comparator_invoked,
        "real_wall_clock_used": evidence.real_wall_clock_used,
        "timestamp_origin_proven": evidence.timestamp_origin_proven,
    }


def paper_deterministic_time_window_evidence_to_dict(
    evidence: PaperDeterministicTimeWindowEvidence,
) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for the evidence (deterministic shape, includes self-digest)."""
    payload = _evidence_payload_from(evidence)
    payload["time_window_digest"] = evidence.time_window_digest
    return payload


def paper_deterministic_time_window_evidence_digest(evidence: PaperDeterministicTimeWindowEvidence) -> str:
    """Recompute the canonical evidence digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_evidence_payload_from(evidence))


__all__ = [
    "PaperDeterministicTimeWindowEvidence",
    "PaperDeterministicTimeWindowEvidenceError",
    "PaperDeterministicTimeWindowEvidenceStatus",
    "build_paper_deterministic_time_window_evidence",
    "paper_deterministic_time_window_evidence_digest",
    "paper_deterministic_time_window_evidence_to_dict",
]
