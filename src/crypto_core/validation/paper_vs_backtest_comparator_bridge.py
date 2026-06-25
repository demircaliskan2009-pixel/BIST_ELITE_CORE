"""Paper-vs-backtest comparator bridge — deterministic, paper-only, fail-closed BRIDGE-READINESS evidence that
records whether the deterministic paper substrate has sufficient inputs to safely feed the existing
``stage4_comparator.py`` contract LATER.

Phase-map slice §10.4.3 (``docs/crypto_core/paper_trading_phase_map.md`` §10.4): the fail-closed bridge between
the deterministic injected-time paper evidence (§10.4.2 ``PaperDeterministicTimeWindowEvidence``) and the
Stage-4 paper-vs-backtest comparator. It is a *validation / audit evidence artifact*, NOT a comparator and NOT
a metrics engine. It consumes ONE already-proven ``PaperDeterministicTimeWindowEvidence``, re-proves its
self-digest via the PUBLIC ``paper_deterministic_time_window_evidence_digest``, re-checks the window's
invariants (schema / status / paper-safety / injected-time flags / timestamp + count coherence), OPTIONALLY
binds a caller ``Stage4BacktestBaseline`` by a bridge-local canonical digest, and emits one frozen,
digest-bound ``PaperVsBacktestComparatorBridgeEvidence``.

It does NOT run the comparator. The Stage-4 ``Stage4PaperSummary`` requires a computable ``paper_sharpe``, a
paper ``edge_id``, a session duration that satisfies the ≥30-day gate, and (for the full gate) hit-rate /
slippage / fill-rate methodology — NONE of which the deterministic substrate produces today (the consumed
window carries ``sharpe_computed=False`` / ``return_series_computed=False`` / ``thirty_day_gate_satisfied=False``
and no edge identity). Therefore this bridge fails closed: it records the explicit ``missing_comparator_inputs``,
keeps ``comparison_ready=False`` and ``stage4_comparator_invoked=False``, and NEVER calls ``compare_stage4`` or
constructs ``Stage4PaperSummary``. ``status=READY`` means only that trusted bridge-readiness evidence was
constructed deterministically — it does NOT imply Stage-4 readiness.

Trust boundary (fail-closed): the consumed window self-digest must re-prove (recompute == stored == caller
``expected_time_window_digest``); the window must be the expected schema + ``READY`` + paper-safe +
non-over-claiming (no live/shadow/Deribit/operational/Sharpe/return-series/30-day/Stage-4 flags, no real
wall-clock, no proven timestamp origin) with exact non-negative integer timestamps
(``window_duration_ns == stopped_at_ns - started_at_ns``), a coherent event partition
(``event_count == computed_event_count + no_realized_event_count`` and
``source_event_digest_count == event_count``), and a ``ready`` flag consistent with its status. A supplied
baseline must be an exact ``Stage4BacktestBaseline``, re-prove its bridge-local digest, be well-formed, and
match the caller ``baseline_id``. A ``sample_eligible=False`` window is still trusted (``status=READY``) but
contributes a blocking reason — comparison stays not ready. Any trust / value failure maps to
``status=REJECTED``. Call-level malformed input (wrong-typed window / ids / digests / baseline / metadata,
forbidden BIST/live/order/capital/service/readiness token, clock-suggesting token) raises
``PaperVsBacktestComparatorBridgeError``.

Same edge is NEVER claimed: the deterministic substrate carries no digest-bound paper edge identity, so
``edge_id_unproven`` is always True and ``paper_edge_id`` remains a missing comparator input even when a
baseline is supplied — the bridge refuses to assert a same-edge relation it cannot prove.

Non-overclaim: a READY bridge proves only that deterministic bridge-readiness evidence was constructed for the
supplied artifacts. It is NOT PRDV4 Stage 4 completion, NOT live/shadow/operational readiness, NOT
Deribit/connector readiness, NOT a Sharpe / return-series / 30-day-gate computation, NOT an actual
paper-vs-backtest comparison, and NOT a profitability/edge proof; it reserves NO real capital — all carried as
explicit ``False`` flags, digest-bound. It does NOT import or use ``crypto_core.service.readiness`` or
``crypto_core.execution.paper_adapter`` (or any shadow/live/runtime/venue surface), no Deribit, no BIST, and it
imports neither ``compare_stage4`` nor ``Stage4PaperSummary`` (only the baseline data type + its public
serializer, used solely to bind a baseline digest). Deterministic and immutable; no wall-clock/random/IO;
inputs unmutated.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    stage4_backtest_baseline_to_dict,
)

_SCHEMA_VERSION = "paper-vs-backtest-comparator-bridge.v1"
_BRIDGE_VERSION = "paper-vs-backtest-comparator-bridge.v1"
_EXPECTED_WINDOW_SCHEMA_VERSION = "paper-deterministic-time-window-evidence.v1"

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Paper-side comparator inputs the deterministic substrate cannot supply today. Constant and non-empty by
# construction, so ``comparison_ready`` is structurally False in v1 (a comparison can only become ready once
# every one of these is explicit, deterministic, and digest-bound — which requires later, separately authorized
# methodology work, NOT this bridge).
_MISSING_COMPARATOR_INPUTS_V1 = (
    "paper_sharpe",
    "paper_edge_id",
    "paper_return_series",
    "paper_vs_backtest_methodology",
    "thirty_day_gate",
)

# Scope guard mirrors the sibling validation modules (word-bounded) and additionally rejects
# capital/equity/margin/balance/service/readiness tokens (this bridge must never carry capital or
# live-readiness identifiers). Market-data terms are scrubbed first.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|"
    r"readiness|service|capital|equity|margin|balance|reservation|real_money)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")

# Real-clock-suggesting tokens forbidden in caller ids / metadata: this bridge is time-adjacent but proves no
# real wall-clock origin, so any string hinting at a live/system clock is rejected (the module calls no clock).
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


class PaperVsBacktestComparatorBridgeError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed window / ids / digests / baseline / metadata / tokens)."""


class PaperVsBacktestComparatorBridgeStatus(str, Enum):
    """Whether trusted bridge-readiness evidence could be produced. Never an execution / live action and never a
    Stage-4 readiness verdict — ``READY`` means only that deterministic bridge evidence was constructed."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperVsBacktestComparatorBridgeEvidence:
    """Deterministic, immutable, digest-bound paper-vs-backtest comparator bridge-readiness evidence.

    ``status`` READY only when the consumed time-window evidence re-proves + re-checks and any supplied baseline
    re-proves + is well-formed. ``ready`` mirrors ``status == READY`` (well-formed evidence). ``comparison_ready``
    is structurally False in v1 (the constant ``missing_comparator_inputs`` is non-empty), and
    ``stage4_comparator_invoked`` is always False — the comparator is NEVER run here. ``edge_id_unproven`` is
    always True (no digest-bound paper edge identity exists in the deterministic substrate). ``paper_only`` True;
    every safety / non-overclaim attestation False. Bridge-readiness evidence ONLY — NOT PRDV4 Stage 4, NOT
    live/shadow readiness, NOT an actual comparison, NOT a Sharpe/30-day proof.
    """

    schema_version: str
    bridge_version: str
    status: PaperVsBacktestComparatorBridgeStatus
    ready: bool
    bridge_id: str
    paper_id: str
    baseline_id: str
    edge_id: str
    edge_id_unproven: bool
    correlation_id: str
    market_symbol: str
    expected_time_window_digest: str
    time_window_digest: str
    metrics_summary_digest: str
    expected_backtest_baseline_digest: str
    backtest_baseline_digest: str
    backtest_baseline_present: bool
    started_at_ns: int
    stopped_at_ns: int
    window_duration_ns: int
    sample_eligible: bool
    comparison_ready: bool
    stage4_comparator_invoked: bool
    missing_comparator_inputs: tuple[str, ...]
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    bridge_digest: str
    paper_only: bool = True
    bridge_readiness_evidence: bool = True
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
    real_wall_clock_used: bool = False
    timestamp_origin_proven: bool = False
    paper_vs_backtest_comparison_ready: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    return type(value) is str and value.strip() != ""


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _is_finite_number(value: object) -> bool:
    return type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(float(value))


def _plain_str_or_empty(value: object) -> str:
    """Return ``value`` only if it is an exact plain ``str`` (no subclass); else ``""`` (fail-closed)."""
    return value if type(value) is str else ""


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperVsBacktestComparatorBridgeError("paper_vs_backtest_comparator_bridge:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperVsBacktestComparatorBridgeError("paper_vs_backtest_comparator_bridge:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise PaperVsBacktestComparatorBridgeError("paper_vs_backtest_comparator_bridge:metadata_malformed")
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


def _window_is_paper_safe(window: PaperDeterministicTimeWindowEvidence) -> bool:
    return (
        window.paper_only is True
        and window.injected_deterministic_time_window is True
        and window.prdv4_stage4_complete is False
        and window.live_ready is False
        and window.shadow_ready is False
        and window.profitability_proven is False
        and window.edge_proven is False
        and window.production_execution is False
        and window.real_orders_enabled is False
        and window.real_money_enabled is False
        and window.real_capital_reserved is False
        and window.live_api_called is False
        and window.scheduler_enabled is False
        and window.auto_loop_enabled is False
        and window.connector_invoked is False
        and window.deribit_ready is False
        and window.operational_readiness is False
        and window.sharpe_computed is False
        and window.return_series_computed is False
        and window.thirty_day_gate_satisfied is False
        and window.stage4_comparator_invoked is False
        and window.real_wall_clock_used is False
        and window.timestamp_origin_proven is False
    )


def _window_timestamps_valid(window: PaperDeterministicTimeWindowEvidence) -> bool:
    return (
        _is_exact_int(window.started_at_ns)
        and window.started_at_ns >= 0
        and _is_exact_int(window.stopped_at_ns)
        and window.stopped_at_ns >= window.started_at_ns
        and _is_exact_int(window.window_duration_ns)
        and window.window_duration_ns == window.stopped_at_ns - window.started_at_ns
    )


def _window_counts_coherent(window: PaperDeterministicTimeWindowEvidence) -> bool:
    counts = (
        window.event_count,
        window.computed_event_count,
        window.no_realized_event_count,
        window.source_event_digest_count,
    )
    if not all(_is_exact_int(count) and count >= 0 for count in counts):
        return False
    if window.event_count != window.computed_event_count + window.no_realized_event_count:
        return False
    return window.source_event_digest_count == window.event_count


def _baseline_well_formed(baseline: Stage4BacktestBaseline) -> bool:
    return (
        _is_plain_non_empty_string(baseline.baseline_id)
        and _is_plain_non_empty_string(baseline.edge_id)
        and _is_exact_int(baseline.as_of_ns)
        and baseline.as_of_ns > 0
        and _is_finite_number(baseline.backtest_sharpe)
        and float(baseline.backtest_sharpe) > 0.0
        and _is_finite_number(baseline.backtest_hit_rate)
        and 0.0 <= float(baseline.backtest_hit_rate) <= 1.0
    )


def _backtest_baseline_digest(baseline: Stage4BacktestBaseline) -> str:
    """Bridge-local canonical digest of a baseline via the PUBLIC ``stage4_backtest_baseline_to_dict`` serializer.

    ``Stage4BacktestBaseline`` carries no self-digest, so the bridge binds its own canonical digest (excludes
    nothing; the baseline has no self-digest field). Used only to bind / re-prove a supplied baseline — never to
    run the comparator.
    """
    return _canonical_digest(stage4_backtest_baseline_to_dict(baseline))


def build_paper_vs_backtest_comparator_bridge(
    time_window_evidence: PaperDeterministicTimeWindowEvidence,
    *,
    expected_time_window_digest: str,
    bridge_id: str,
    paper_id: str,
    correlation_id: str,
    baseline_id: str | None = None,
    edge_id: str | None = None,
    backtest_baseline: Stage4BacktestBaseline | None = None,
    expected_backtest_baseline_digest: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> PaperVsBacktestComparatorBridgeEvidence:
    """Build fail-closed paper-vs-backtest comparator bridge-readiness evidence over a trusted time window.

    ``time_window_evidence`` must be a ``PaperDeterministicTimeWindowEvidence``; ``expected_time_window_digest``
    an exact plain 64-lowercase-hex ``str`` (the caller's INDEPENDENT anchor); ``bridge_id`` / ``paper_id`` /
    ``correlation_id`` exact plain non-empty ``str``; ``baseline_id`` / ``edge_id`` either ``None`` or exact
    plain non-empty ``str``; ``backtest_baseline`` either ``None`` or an exact ``Stage4BacktestBaseline`` (with
    ``expected_backtest_baseline_digest`` a hex64 ``str`` iff a baseline is supplied, else ``None``); ``metadata``
    ``Mapping[str, str]`` or ``None``. A wrong type, malformed digest, empty id, a forbidden BIST/live/order/
    capital/service/readiness token, a clock-suggesting token, or malformed metadata raises
    ``PaperVsBacktestComparatorBridgeError`` before any work.

    The window self-digest is re-proven via the PUBLIC ``paper_deterministic_time_window_evidence_digest`` (==
    stored == expected anchor); the window must be the expected schema + READY + paper-safe + non-over-claiming
    with exact non-negative integer timestamps (``window_duration_ns == stopped_at_ns - started_at_ns``), a
    coherent event partition, and a ``ready`` flag consistent with its status. A supplied baseline must re-prove
    its bridge-local digest, be well-formed, and match ``baseline_id``. ``status=READY`` over fully trusted
    inputs; the comparator is NEVER run — ``comparison_ready`` is structurally False (the constant
    ``missing_comparator_inputs`` is non-empty) and ``stage4_comparator_invoked`` is always False. A
    ``sample_eligible=False`` window stays trusted (READY) but adds a blocking reason. Any trust / value failure
    maps to ``status=REJECTED``. Deterministic and immutable; no wall-clock/random/IO; inputs unmutated; same
    edge is never claimed (``edge_id_unproven`` always True).
    """
    if not isinstance(time_window_evidence, PaperDeterministicTimeWindowEvidence):
        raise PaperVsBacktestComparatorBridgeError("paper_vs_backtest_comparator_bridge:time_window_evidence_malformed")
    if not _is_hex64_string(expected_time_window_digest):
        raise PaperVsBacktestComparatorBridgeError(
            "paper_vs_backtest_comparator_bridge:expected_time_window_digest_invalid"
        )
    for name, value in (("bridge_id", bridge_id), ("paper_id", paper_id), ("correlation_id", correlation_id)):
        if not _is_plain_non_empty_string(value):
            raise PaperVsBacktestComparatorBridgeError(f"paper_vs_backtest_comparator_bridge:{name}_invalid")
    if baseline_id is not None and not _is_plain_non_empty_string(baseline_id):
        raise PaperVsBacktestComparatorBridgeError("paper_vs_backtest_comparator_bridge:baseline_id_invalid")
    if edge_id is not None and not _is_plain_non_empty_string(edge_id):
        raise PaperVsBacktestComparatorBridgeError("paper_vs_backtest_comparator_bridge:edge_id_invalid")
    if backtest_baseline is not None and not isinstance(backtest_baseline, Stage4BacktestBaseline):
        raise PaperVsBacktestComparatorBridgeError("paper_vs_backtest_comparator_bridge:backtest_baseline_malformed")
    if backtest_baseline is None:
        if expected_backtest_baseline_digest is not None:
            raise PaperVsBacktestComparatorBridgeError(
                "paper_vs_backtest_comparator_bridge:expected_backtest_baseline_digest_unexpected"
            )
    elif not _is_hex64_string(expected_backtest_baseline_digest):
        raise PaperVsBacktestComparatorBridgeError(
            "paper_vs_backtest_comparator_bridge:expected_backtest_baseline_digest_invalid"
        )
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(
        bridge_id,
        paper_id,
        correlation_id,
        baseline_id if baseline_id is not None else "",
        edge_id if edge_id is not None else "",
        *_metadata_texts(metadata_pairs),
    ):
        raise PaperVsBacktestComparatorBridgeError("paper_vs_backtest_comparator_bridge:scope_violation")
    if _has_clock_token(
        bridge_id,
        paper_id,
        baseline_id if baseline_id is not None else "",
        edge_id if edge_id is not None else "",
        *_metadata_texts(metadata_pairs),
    ):
        raise PaperVsBacktestComparatorBridgeError("paper_vs_backtest_comparator_bridge:clock_token_forbidden")

    hard: list[str] = []

    # Trust boundary: re-prove the window self-digest via its PUBLIC serializer AND the caller anchor.
    try:
        recomputed_window = paper_deterministic_time_window_evidence_digest(time_window_evidence)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        recomputed_window = None
    stored_window = time_window_evidence.time_window_digest
    if recomputed_window is None:
        hard.append("paper_vs_backtest_comparator_bridge:time_window_evidence_malformed")
    elif (
        not _is_hex64_string(stored_window)
        or stored_window != recomputed_window
        or stored_window != expected_time_window_digest
    ):
        hard.append("paper_vs_backtest_comparator_bridge:time_window_digest_mismatch")

    # Window schema + status re-check (do not trust window bytes after digest re-proof alone).
    if time_window_evidence.schema_version != _EXPECTED_WINDOW_SCHEMA_VERSION:
        hard.append("paper_vs_backtest_comparator_bridge:time_window_schema_invalid")
    elif time_window_evidence.status is not PaperDeterministicTimeWindowEvidenceStatus.READY:
        hard.append("paper_vs_backtest_comparator_bridge:time_window_not_ready")
    if not _window_is_paper_safe(time_window_evidence):
        hard.append("paper_vs_backtest_comparator_bridge:time_window_unsafe_flags")
    if not _window_timestamps_valid(time_window_evidence):
        hard.append("paper_vs_backtest_comparator_bridge:time_window_timestamps_invalid")
    if not _window_counts_coherent(time_window_evidence):
        hard.append("paper_vs_backtest_comparator_bridge:time_window_counts_incoherent")

    # Window ``ready`` flag must be consistent with its own status (a resealed ready/status mismatch fails here).
    window_ready = time_window_evidence.ready if type(time_window_evidence.ready) is bool else None
    expected_window_ready = time_window_evidence.status is PaperDeterministicTimeWindowEvidenceStatus.READY
    if window_ready is not expected_window_ready:
        hard.append("paper_vs_backtest_comparator_bridge:time_window_ready_inconsistent")

    if _plain_str_or_empty(time_window_evidence.market_symbol) == "":
        hard.append("paper_vs_backtest_comparator_bridge:time_window_market_symbol_invalid")

    # Optional baseline: re-prove its bridge-local digest, well-formedness, and caller id match. Even a valid
    # baseline cannot make the comparison ready (the paper side is missing) and can never be matched on edge.
    baseline_present = backtest_baseline is not None
    backtest_baseline_digest = ""
    if baseline_present:
        try:
            recomputed_baseline = _backtest_baseline_digest(backtest_baseline)
        except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
            recomputed_baseline = None
        if recomputed_baseline is None or recomputed_baseline != expected_backtest_baseline_digest:
            hard.append("paper_vs_backtest_comparator_bridge:backtest_baseline_digest_mismatch")
        else:
            backtest_baseline_digest = recomputed_baseline
        if not _baseline_well_formed(backtest_baseline):
            hard.append("paper_vs_backtest_comparator_bridge:backtest_baseline_invalid")
        if baseline_id is not None and baseline_id != _plain_str_or_empty(backtest_baseline.baseline_id):
            hard.append("paper_vs_backtest_comparator_bridge:baseline_id_mismatch")

    sample_eligible = time_window_evidence.sample_eligible is True

    if hard:
        status = PaperVsBacktestComparatorBridgeStatus.REJECTED
        ready = False
        comparison_ready = False
        missing_inputs: tuple[str, ...] = ()
        reason_codes = tuple(sorted(set(hard)))
    else:
        status = PaperVsBacktestComparatorBridgeStatus.READY
        ready = True
        # Enumerate the missing paper-side comparator inputs. The v1 set is constant and non-empty, so comparison
        # can NEVER be ready here; a non-eligible window and an absent baseline add further blocking inputs.
        missing = list(_MISSING_COMPARATOR_INPUTS_V1)
        if not sample_eligible:
            missing.append("paper_sample_eligibility")
        if not baseline_present:
            missing.append("backtest_baseline")
        missing_inputs = tuple(sorted(set(missing)))
        comparison_ready = False  # structural: missing_inputs is non-empty in v1
        reasons = ["paper_vs_backtest_comparator_bridge:comparison_not_ready_missing_inputs"]
        if not sample_eligible:
            reasons.append("paper_vs_backtest_comparator_bridge:time_window_not_sample_eligible")
        reason_codes = tuple(sorted(set(reasons)))

    return _finalize_bridge(
        status=status,
        ready=ready,
        time_window_evidence=time_window_evidence,
        expected_time_window_digest=expected_time_window_digest,
        bridge_id=bridge_id,
        paper_id=paper_id,
        baseline_id=_plain_str_or_empty(baseline_id) if baseline_id is not None else "",
        edge_id=_plain_str_or_empty(edge_id) if edge_id is not None else "",
        correlation_id=correlation_id,
        expected_backtest_baseline_digest=_plain_str_or_empty(expected_backtest_baseline_digest)
        if expected_backtest_baseline_digest is not None
        else "",
        backtest_baseline_digest=backtest_baseline_digest,
        backtest_baseline_present=baseline_present,
        sample_eligible=sample_eligible,
        comparison_ready=comparison_ready,
        missing_comparator_inputs=missing_inputs,
        reason_codes=reason_codes,
        metadata=metadata_pairs,
    )


def _finalize_bridge(
    *,
    status: PaperVsBacktestComparatorBridgeStatus,
    ready: bool,
    time_window_evidence: PaperDeterministicTimeWindowEvidence,
    expected_time_window_digest: str,
    bridge_id: str,
    paper_id: str,
    baseline_id: str,
    edge_id: str,
    correlation_id: str,
    expected_backtest_baseline_digest: str,
    backtest_baseline_digest: str,
    backtest_baseline_present: bool,
    sample_eligible: bool,
    comparison_ready: bool,
    missing_comparator_inputs: tuple[str, ...],
    reason_codes: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> PaperVsBacktestComparatorBridgeEvidence:
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "bridge_version": _BRIDGE_VERSION,
        "status": status,
        "ready": ready,
        "bridge_id": bridge_id,
        "paper_id": paper_id,
        "baseline_id": baseline_id,
        "edge_id": edge_id,
        "edge_id_unproven": True,
        "correlation_id": correlation_id,
        "market_symbol": _plain_str_or_empty(time_window_evidence.market_symbol),
        "expected_time_window_digest": expected_time_window_digest,
        "time_window_digest": _plain_str_or_empty(time_window_evidence.time_window_digest),
        "metrics_summary_digest": _plain_str_or_empty(time_window_evidence.metrics_summary_digest),
        "expected_backtest_baseline_digest": expected_backtest_baseline_digest,
        "backtest_baseline_digest": backtest_baseline_digest,
        "backtest_baseline_present": backtest_baseline_present,
        "started_at_ns": time_window_evidence.started_at_ns if _is_exact_int(time_window_evidence.started_at_ns) else 0,
        "stopped_at_ns": time_window_evidence.stopped_at_ns if _is_exact_int(time_window_evidence.stopped_at_ns) else 0,
        "window_duration_ns": time_window_evidence.window_duration_ns
        if _is_exact_int(time_window_evidence.window_duration_ns)
        else 0,
        "sample_eligible": sample_eligible,
        "comparison_ready": comparison_ready,
        "stage4_comparator_invoked": False,
        "missing_comparator_inputs": missing_comparator_inputs,
        "reason_codes": reason_codes,
        "metadata": metadata,
    }
    seed = PaperVsBacktestComparatorBridgeEvidence(bridge_digest="", **fields)  # type: ignore[arg-type]
    return _replace_bridge_digest(seed, paper_vs_backtest_comparator_bridge_digest(seed))


def _replace_bridge_digest(
    evidence: PaperVsBacktestComparatorBridgeEvidence, digest: str
) -> PaperVsBacktestComparatorBridgeEvidence:
    fields = _bridge_fields(evidence)
    fields["bridge_digest"] = digest
    return PaperVsBacktestComparatorBridgeEvidence(**fields)  # type: ignore[arg-type]


def _bridge_fields(evidence: PaperVsBacktestComparatorBridgeEvidence) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "bridge_version": evidence.bridge_version,
        "status": evidence.status,
        "ready": evidence.ready,
        "bridge_id": evidence.bridge_id,
        "paper_id": evidence.paper_id,
        "baseline_id": evidence.baseline_id,
        "edge_id": evidence.edge_id,
        "edge_id_unproven": evidence.edge_id_unproven,
        "correlation_id": evidence.correlation_id,
        "market_symbol": evidence.market_symbol,
        "expected_time_window_digest": evidence.expected_time_window_digest,
        "time_window_digest": evidence.time_window_digest,
        "metrics_summary_digest": evidence.metrics_summary_digest,
        "expected_backtest_baseline_digest": evidence.expected_backtest_baseline_digest,
        "backtest_baseline_digest": evidence.backtest_baseline_digest,
        "backtest_baseline_present": evidence.backtest_baseline_present,
        "started_at_ns": evidence.started_at_ns,
        "stopped_at_ns": evidence.stopped_at_ns,
        "window_duration_ns": evidence.window_duration_ns,
        "sample_eligible": evidence.sample_eligible,
        "comparison_ready": evidence.comparison_ready,
        "stage4_comparator_invoked": evidence.stage4_comparator_invoked,
        "missing_comparator_inputs": evidence.missing_comparator_inputs,
        "reason_codes": evidence.reason_codes,
        "metadata": evidence.metadata,
    }


def _bridge_payload_from(evidence: PaperVsBacktestComparatorBridgeEvidence) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "bridge_version": evidence.bridge_version,
        "status": evidence.status.value,
        "ready": evidence.ready,
        "bridge_id": evidence.bridge_id,
        "paper_id": evidence.paper_id,
        "baseline_id": evidence.baseline_id,
        "edge_id": evidence.edge_id,
        "edge_id_unproven": evidence.edge_id_unproven,
        "correlation_id": evidence.correlation_id,
        "market_symbol": evidence.market_symbol,
        "expected_time_window_digest": evidence.expected_time_window_digest,
        "time_window_digest": evidence.time_window_digest,
        "metrics_summary_digest": evidence.metrics_summary_digest,
        "expected_backtest_baseline_digest": evidence.expected_backtest_baseline_digest,
        "backtest_baseline_digest": evidence.backtest_baseline_digest,
        "backtest_baseline_present": evidence.backtest_baseline_present,
        "started_at_ns": evidence.started_at_ns,
        "stopped_at_ns": evidence.stopped_at_ns,
        "window_duration_ns": evidence.window_duration_ns,
        "sample_eligible": evidence.sample_eligible,
        "comparison_ready": evidence.comparison_ready,
        "stage4_comparator_invoked": evidence.stage4_comparator_invoked,
        "missing_comparator_inputs": list(evidence.missing_comparator_inputs),
        "reason_codes": list(evidence.reason_codes),
        "metadata": _serialize_metadata(evidence.metadata),
        "paper_only": evidence.paper_only,
        "bridge_readiness_evidence": evidence.bridge_readiness_evidence,
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
        "real_wall_clock_used": evidence.real_wall_clock_used,
        "timestamp_origin_proven": evidence.timestamp_origin_proven,
        "paper_vs_backtest_comparison_ready": evidence.paper_vs_backtest_comparison_ready,
    }


def paper_vs_backtest_comparator_bridge_to_dict(
    evidence: PaperVsBacktestComparatorBridgeEvidence,
) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for the evidence (deterministic shape, includes self-digest)."""
    payload = _bridge_payload_from(evidence)
    payload["bridge_digest"] = evidence.bridge_digest
    return payload


def paper_vs_backtest_comparator_bridge_digest(evidence: PaperVsBacktestComparatorBridgeEvidence) -> str:
    """Recompute the canonical bridge digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_bridge_payload_from(evidence))


__all__ = [
    "PaperVsBacktestComparatorBridgeEvidence",
    "PaperVsBacktestComparatorBridgeError",
    "PaperVsBacktestComparatorBridgeStatus",
    "build_paper_vs_backtest_comparator_bridge",
    "paper_vs_backtest_comparator_bridge_digest",
    "paper_vs_backtest_comparator_bridge_to_dict",
]
