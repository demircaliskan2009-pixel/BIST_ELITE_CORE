"""Deterministic paper secondary-metrics substrate reconciliation (validation-only denominator completeness).

SM-3 ``TradeRecordEvidence`` and SM-4 ``PaperSecondaryMetricsEvidence`` aggregate only the records a caller
CHOOSES to supply — nothing there proves the supplied record set is the COMPLETE set of paper episodes. A
caller could silently drop losing, rejected, or unfilled episodes before SM-5/SM-6 consumes the metrics,
inflating hit-rate / fill-rate. This artifact closes that gap: it binds the SM-2 policy, the SM-4 evidence,
the SM-3 records, the digest-bound ``PaperSessionSequenceResult`` (the ordered episode denominator ROOT),
and per-episode paper substrate (``PaperEpisodeRunResult`` / ``PaperFillSimulationResult`` / optional
``PaperRealizedPnlEvent``), and fails closed unless EVERY session episode maps to EXACTLY ONE supplied
record and no extra record exists — with each record's filled quantity / intended quantity / realized fill
price / realized PnL re-proven against the substrate it claims to summarize.

It is validation-only. It re-proves every consumed self-digest via the public serializers; it never
constructs substrate, never enforces a threshold, never runs a comparator, never touches runtime / execution
/ service / venue / orchestrator / portfolio, and never claims Stage-4 completion, SM-5/SM-6, edge,
profitability, authoritative PnL, or live / shadow / Deribit / connector readiness. ``RECONCILED`` means only
that the supplied SM record set is complete and consistent with the proven paper substrate; it is NOT a
trading authorization of any kind.

Fields deliberately NOT asserted against substrate (no clean source in the record-input contract, so
asserting them would invent semantics): ``record.expected_fill_price`` (a policy/model reference price, not a
fill output), ``record.strategy_id`` and ``record.decision_id`` (``PaperEpisodeRunResult`` carries neither),
and the SM-3 derived flags ``decided_episode`` / ``hit_flag`` / ``fill_flag`` / ``slippage_bps`` (SM-4 already
recomputes those from the record's raw fields).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_episode_runner import (
    PaperEpisodeRunResult,
    paper_episode_run_result_digest,
)
from crypto_core.validation.paper_fill_simulator import (
    PaperFillSimulationResult,
    PaperFillSimulationStatus,
    paper_fill_simulation_result_digest,
)
from crypto_core.validation.paper_realized_pnl import (
    PaperRealizedPnlEvent,
    PaperRealizedPnlStatus,
    paper_realized_pnl_event_digest,
)
from crypto_core.validation.paper_secondary_metrics_evidence import (
    PaperSecondaryMetricsEvidence,
    paper_secondary_metrics_evidence_digest,
)
from crypto_core.validation.paper_session_sequence import (
    PaperSessionSequenceResult,
    PaperSessionSequenceStatus,
    paper_session_sequence_result_digest,
)
from crypto_core.validation.secondary_metrics_policy import (
    SecondaryMetricsPolicy,
    secondary_metrics_policy_digest,
)
from crypto_core.validation.trade_record_evidence import (
    TradeRecordEvidence,
    TradeRecordEvidenceStatus,
    trade_record_evidence_digest,
)

_SCHEMA_VERSION = "paper-secondary-metrics-substrate-reconciliation.v1"
_RECONCILIATION_VERSION = "paper-secondary-metrics-substrate-reconciliation.v1"
_REASON_PREFIX = "paper_secondary_metrics_substrate_reconciliation"

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
# Bounds the reconciled set so the artifact stays deterministic and cheap; far above any real paper window.
_MAX_EPISODES = 100_000

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


class PaperSecondaryMetricsSubstrateReconciliationError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed artifacts / ids / metadata / tokens)."""


class PaperSecondaryMetricsSubstrateReconciliationStatus(str, Enum):
    """Reconciliation status. RECONCILED is denominator-completeness evidence only, never a trading claim."""

    RECONCILED = "RECONCILED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperSecondaryMetricsSubstrateRecordInput:
    """One SM-3 record bundled with the paper substrate that produced its episode.

    ``realized_pnl_event`` is REQUIRED whenever the record reports a non-zero ``realized_pnl`` (a realized
    gain or loss was computed for a closing/reducing fill) — this prevents a losing close from being hidden
    by omitting its event — and MUST be omitted for a rejected/unfilled episode; a zero-PnL filled episode
    (e.g. an opening or same-side fill) may omit it. Whenever it is supplied it is fully re-proven against the
    bound ``episode_run`` / ``fill_result``. Realized PnL is bound DIRECTLY to the event and the record, never
    to the episode's ``realized_pnl_computed`` flag (which the runner always leaves False and the session
    sequence rejects when set true, so it can never gate a real paper episode).
    """

    record: TradeRecordEvidence
    episode_run: PaperEpisodeRunResult
    fill_result: PaperFillSimulationResult
    realized_pnl_event: PaperRealizedPnlEvent | None = None


@dataclass(frozen=True)
class PaperSecondaryMetricsSubstrateReconciliation:
    """Immutable, digest-bound proof that an SM record set is complete vs the paper substrate inventory.

    ``status=RECONCILED`` only when the policy / SM-4 evidence / session sequence re-prove their digests, the
    SM-4 record-digest set equals the supplied record set, every session episode maps 1:1 (order + count +
    bijection) to a supplied record, and each record's filled quantity / intended quantity / realized fill
    price / realized PnL re-prove against its bound substrate. It enforces no threshold and authorizes
    nothing.
    """

    schema_version: str
    reconciliation_version: str
    status: PaperSecondaryMetricsSubstrateReconciliationStatus
    ready: bool
    reconciliation_id: str
    correlation_id: str
    policy_id: str
    market_symbol: str
    verified_policy_digest: str
    verified_metrics_evidence_digest: str
    verified_session_sequence_digest: str
    episode_count: int
    reconciled_episode_run_digests: tuple[str, ...]
    reconciled_record_digests: tuple[str, ...]
    filled_episode_count: int
    rejected_or_unfilled_episode_count: int
    positive_pnl_episode_count: int
    negative_pnl_episode_count: int
    zero_pnl_episode_count: int
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    reconciliation_digest: str
    paper_only: bool = True
    validation_only: bool = True
    live_ready: bool = False
    shadow_ready: bool = False
    connector_ready: bool = False
    orders_enabled: bool = False
    real_fills_used: bool = False
    authoritative_pnl: bool = False
    capital_mutation_enabled: bool = False
    scheduler_enabled: bool = False
    stage4_complete: bool = False
    sm5_enabled: bool = False
    sm6_enabled: bool = False


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperSecondaryMetricsSubstrateReconciliationError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _decimal_or_none(value: object) -> Decimal | None:
    """Parse a substrate/record numeric string to Decimal for value comparison (format-independent)."""

    if type(value) is not str or value == "":
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _decimals_equal(left: object, right: object) -> bool:
    left_decimal = _decimal_or_none(left)
    right_decimal = _decimal_or_none(right)
    return left_decimal is not None and right_decimal is not None and left_decimal == right_decimal


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("metadata_malformed"))
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in metadata]


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


def _sorted_unique(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _recomputed_digest_or_none(compute: object, artifact: object) -> str | None:
    try:
        return compute(artifact)  # type: ignore[operator]
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        return None


@dataclass(frozen=True)
class _InputProof:
    episode_run_digest: str
    record_digest: str
    episode_id: str
    classification: str  # "positive" | "negative" | "zero" | "rejected"


def _input_member_types_ok(item: PaperSecondaryMetricsSubstrateRecordInput) -> bool:
    return (
        type(item.record) is TradeRecordEvidence
        and type(item.episode_run) is PaperEpisodeRunResult
        and type(item.fill_result) is PaperFillSimulationResult
        and (item.realized_pnl_event is None or type(item.realized_pnl_event) is PaperRealizedPnlEvent)
    )


def _input_failures(
    item: PaperSecondaryMetricsSubstrateRecordInput,
    *,
    correlation_id: str,
    policy_id: str,
    market_symbol: str,
) -> tuple[list[str], _InputProof]:
    """Re-prove one record against its bound substrate. Returns (failures, proof) — proof fields are best-effort."""

    hard: list[str] = []
    record = item.record
    episode_run = item.episode_run
    fill_result = item.fill_result
    event = item.realized_pnl_event

    # Self-digest re-proof of every consumed substrate artifact.
    record_digest = _recomputed_digest_or_none(trade_record_evidence_digest, record)
    if record_digest is None or not _is_hex64_string(record.record_digest) or record.record_digest != record_digest:
        hard.append(_reason("record_digest_mismatch"))
        record_digest = ""
    episode_digest = _recomputed_digest_or_none(paper_episode_run_result_digest, episode_run)
    if (
        episode_digest is None
        or not _is_hex64_string(episode_run.episode_run_digest)
        or episode_run.episode_run_digest != episode_digest
    ):
        hard.append(_reason("episode_run_digest_mismatch"))
        episode_digest = ""
    fill_digest = _recomputed_digest_or_none(paper_fill_simulation_result_digest, fill_result)
    if fill_digest is None or episode_run.fill_simulation_result_digest != fill_digest:
        hard.append(_reason("fill_result_digest_mismatch"))

    # Record status / identity binding.
    if (
        record.status is not TradeRecordEvidenceStatus.RECORD_READY
        or record.ready is not True
        or record.reason_codes != ()
    ):
        hard.append(_reason("record_not_ready"))
    if record.policy_id != policy_id:
        hard.append(_reason("record_policy_id_mismatch"))
    if not _is_plain_non_empty_string(episode_run.episode_run_id) or record.episode_id != episode_run.episode_run_id:
        hard.append(_reason("record_episode_id_mismatch"))
    if any(artifact.correlation_id != correlation_id for artifact in (record, episode_run, fill_result)) or (
        event is not None and event.correlation_id != correlation_id
    ):
        hard.append(_reason("correlation_id_mismatch"))
    if episode_run.market_symbol != market_symbol or fill_result.market_symbol != market_symbol:
        hard.append(_reason("market_symbol_mismatch"))

    # Fill outcome binding (Decimal value comparison — the two artifacts canonicalize numbers independently).
    filled = _decimal_or_none(fill_result.filled_units)
    unfilled = _decimal_or_none(fill_result.unfilled_units)
    if filled is None or unfilled is None:
        hard.append(_reason("fill_units_unparseable"))
    else:
        if not _decimals_equal(record.filled_quantity, fill_result.filled_units):
            hard.append(_reason("filled_quantity_mismatch"))
        # Simulator invariant (paper_fill_simulator): filled_units + unfilled_units == requested (intended).
        intended = _decimal_or_none(record.intended_quantity)
        if intended is None or intended != filled + unfilled:
            hard.append(_reason("intended_quantity_mismatch"))

    is_rejected = fill_result.status is PaperFillSimulationStatus.REJECTED
    is_filled = filled is not None and filled > 0
    if is_rejected or not is_filled:
        # Rejected / unfilled episode: no fill price, no realized PnL, no realized event — must not be hidden.
        if record.realized_fill_price is not None:
            hard.append(_reason("rejected_fill_record_mismatch"))
        if not _decimals_equal(record.filled_quantity, "0") or filled not in (None, Decimal(0)):
            hard.append(_reason("rejected_fill_record_mismatch"))
    else:
        if record.realized_fill_price is None or not _decimals_equal(
            record.realized_fill_price, fill_result.fill_price
        ):
            hard.append(_reason("realized_fill_price_mismatch"))

    # Realized-PnL binding — bound DIRECTLY to the supplied event and the record's own realized PnL, never
    # to ``episode_run.realized_pnl_computed``. The paper episode runner computes only unrealized/MTM PnL and
    # always leaves ``realized_pnl_computed`` False (``build_paper_session_sequence`` rejects any episode that
    # sets it true), so realized PnL for an episode lives ONLY in a separately-computed ``PaperRealizedPnlEvent``.
    # Rules: a non-zero ``record.realized_pnl`` MUST be backed by a COMPUTED event that binds this episode's
    # fill/transition and reports the same PnL (a losing close cannot be hidden by omitting its event); a
    # supplied event is ALWAYS fully re-proven; a zero ``record.realized_pnl`` needs no event (an opening /
    # same-side fill legitimately realizes nothing and the substrate cannot prove an event exists) — a
    # documented completeness boundary, not an overclaim — but any supplied event must still bind and match.
    realized_pnl_value = Decimal(0)
    record_pnl = _decimal_or_none(record.realized_pnl)
    if is_rejected or not is_filled:
        # Rejected / unfilled episode: realized PnL must be exactly zero and no realized event may exist.
        if record_pnl is None or record_pnl != 0:
            hard.append(_reason("realized_pnl_mismatch"))
        if event is not None:
            hard.append(_reason("unexpected_realized_event"))
    elif event is not None:
        # Filled episode WITH an event: re-prove the event fully against THIS episode and record.
        event_digest = _recomputed_digest_or_none(paper_realized_pnl_event_digest, event)
        if (
            event_digest is None
            or not _is_hex64_string(event.realized_pnl_event_digest)
            or event.realized_pnl_event_digest != event_digest
        ):
            hard.append(_reason("realized_event_digest_mismatch"))
        if (
            event.fill_simulation_result_digest != episode_run.fill_simulation_result_digest
            or event.position_transition_digest != episode_run.position_transition_digest
        ):
            hard.append(_reason("realized_event_binding_mismatch"))
        if event.market_symbol != market_symbol or not _decimals_equal(event.filled_units, fill_result.filled_units):
            hard.append(_reason("realized_event_binding_mismatch"))
        if not _decimals_equal(event.fill_price, fill_result.fill_price) or (
            record.realized_fill_price is not None and not _decimals_equal(event.fill_price, record.realized_fill_price)
        ):
            hard.append(_reason("realized_event_binding_mismatch"))
        if event.status is PaperRealizedPnlStatus.REJECTED:
            hard.append(_reason("realized_event_not_computed"))
        if not _decimals_equal(record.realized_pnl, event.realized_pnl):
            hard.append(_reason("realized_pnl_mismatch"))
        if record_pnl is not None and record_pnl != 0 and event.status is not PaperRealizedPnlStatus.COMPUTED:
            # A non-zero realized PnL can only be produced by a COMPUTED event.
            hard.append(_reason("realized_event_not_computed"))
        parsed_event_pnl = _decimal_or_none(event.realized_pnl)
        if parsed_event_pnl is not None:
            realized_pnl_value = parsed_event_pnl
    else:
        # Filled episode with NO event: a non-zero realized PnL is unbacked; zero realized PnL is allowed.
        if record_pnl is None:
            hard.append(_reason("realized_pnl_mismatch"))
        elif record_pnl != 0:
            hard.append(_reason("realized_event_required"))

    # Scope hygiene over this input's identifiers/metadata (defence in depth over the merged artifacts).
    if _has_scope_violation(
        record.record_id,
        episode_run.episode_run_id,
        *_metadata_texts(record.metadata),
        *_metadata_texts(episode_run.metadata),
    ):
        hard.append(_reason("scope_violation"))
    if _has_clock_token(
        record.record_id,
        episode_run.episode_run_id,
        *_metadata_texts(record.metadata),
        *_metadata_texts(episode_run.metadata),
    ):
        hard.append(_reason("clock_token_forbidden"))

    if is_rejected or not is_filled:
        classification = "rejected"
    elif realized_pnl_value > 0:
        classification = "positive"
    elif realized_pnl_value < 0:
        classification = "negative"
    else:
        classification = "zero"

    proof = _InputProof(
        episode_run_digest=episode_digest,
        record_digest=record_digest,
        episode_id=episode_run.episode_run_id if _is_plain_non_empty_string(episode_run.episode_run_id) else "",
        classification=classification,
    )
    return hard, proof


def build_paper_secondary_metrics_substrate_reconciliation(
    policy: SecondaryMetricsPolicy,
    metrics_evidence: PaperSecondaryMetricsEvidence,
    inputs: Sequence[PaperSecondaryMetricsSubstrateRecordInput],
    session_sequence: PaperSessionSequenceResult,
    *,
    reconciliation_id: str,
    correlation_id: str,
    expected_policy_digest: str,
    expected_metrics_evidence_digest: str,
    expected_session_sequence_digest: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSecondaryMetricsSubstrateReconciliation:
    """Prove the supplied SM record set is complete and consistent with the paper substrate inventory.

    Wrong-typed inputs, malformed ids/metadata, or forbidden BIST/live/order/scheduler/clock tokens raise
    ``PaperSecondaryMetricsSubstrateReconciliationError``; every trust / completeness / value failure maps to
    ``status=REJECTED`` with deterministic reason codes. ``RECONCILED`` requires the full bijection and every
    per-record substrate re-proof to pass.
    """

    if type(policy) is not SecondaryMetricsPolicy:
        raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("policy_malformed"))
    if type(metrics_evidence) is not PaperSecondaryMetricsEvidence:
        raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("metrics_evidence_malformed"))
    if type(session_sequence) is not PaperSessionSequenceResult:
        raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("session_sequence_malformed"))
    if type(inputs) not in (tuple, list):
        raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("inputs_malformed"))
    input_tuple = tuple(inputs)
    if len(input_tuple) == 0:
        raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("inputs_empty"))
    if len(input_tuple) > _MAX_EPISODES:
        raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("inputs_too_many"))
    for item in input_tuple:
        if type(item) is not PaperSecondaryMetricsSubstrateRecordInput or not _input_member_types_ok(item):
            raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("record_input_malformed"))
    reconciliation_id = _require_plain_non_empty_string(reconciliation_id, "reconciliation_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    expected_policy_digest = _require_plain_non_empty_string(expected_policy_digest, "expected_policy_digest")
    expected_metrics_evidence_digest = _require_plain_non_empty_string(
        expected_metrics_evidence_digest, "expected_metrics_evidence_digest"
    )
    expected_session_sequence_digest = _require_plain_non_empty_string(
        expected_session_sequence_digest, "expected_session_sequence_digest"
    )
    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (reconciliation_id, correlation_id, *_metadata_texts(metadata_pairs))
    if _has_scope_violation(*scope_texts):
        raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("scope_violation"))
    if _has_clock_token(*scope_texts):
        raise PaperSecondaryMetricsSubstrateReconciliationError(_reason("clock_token_forbidden"))

    hard: list[str] = []

    # Provenance: recompute policy / SM-4 evidence / session digests == carried == caller anchor.
    recomputed_policy = _recomputed_digest_or_none(secondary_metrics_policy_digest, policy)
    if (
        recomputed_policy is None
        or not _is_hex64_string(policy.policy_digest)
        or policy.policy_digest != recomputed_policy
        or policy.policy_digest != expected_policy_digest
    ):
        hard.append(_reason("policy_digest_mismatch"))
    recomputed_metrics = _recomputed_digest_or_none(paper_secondary_metrics_evidence_digest, metrics_evidence)
    if (
        recomputed_metrics is None
        or not _is_hex64_string(metrics_evidence.evidence_digest)
        or metrics_evidence.evidence_digest != recomputed_metrics
        or metrics_evidence.evidence_digest != expected_metrics_evidence_digest
    ):
        hard.append(_reason("metrics_evidence_digest_mismatch"))
    recomputed_session = _recomputed_digest_or_none(paper_session_sequence_result_digest, session_sequence)
    if (
        recomputed_session is None
        or not _is_hex64_string(session_sequence.paper_session_sequence_digest)
        or session_sequence.paper_session_sequence_digest != recomputed_session
        or session_sequence.paper_session_sequence_digest != expected_session_sequence_digest
    ):
        hard.append(_reason("session_sequence_digest_mismatch"))

    # SM-4 <-> SM-2 binding: the evidence must be bound to THIS policy.
    policy_id = policy.policy_id if _is_plain_non_empty_string(policy.policy_id) else ""
    if (
        metrics_evidence.policy_id != policy_id
        or not _is_hex64_string(metrics_evidence.verified_policy_digest)
        or metrics_evidence.verified_policy_digest != policy.policy_digest
    ):
        hard.append(_reason("metrics_evidence_policy_mismatch"))

    # Session structural sanity.
    market_symbol = session_sequence.market_symbol if _is_plain_non_empty_string(session_sequence.market_symbol) else ""
    if session_sequence.status is not PaperSessionSequenceStatus.COMPUTED or market_symbol == "":
        hard.append(_reason("session_sequence_not_computed"))
    if session_sequence.correlation_id != correlation_id:
        hard.append(_reason("correlation_id_mismatch"))
    session_episode_digests = (
        session_sequence.episode_run_digests if type(session_sequence.episode_run_digests) is tuple else ()
    )
    if not _is_exact_int(session_sequence.episode_count) or session_sequence.episode_count != len(
        session_episode_digests
    ):
        hard.append(_reason("session_episode_count_incoherent"))
    if len(session_episode_digests) != len(input_tuple):
        hard.append(_reason("episode_count_mismatch"))

    # Per-input substrate re-proof.
    proofs: list[_InputProof] = []
    for item in input_tuple:
        item_failures, proof = _input_failures(
            item, correlation_id=correlation_id, policy_id=policy_id, market_symbol=market_symbol
        )
        hard.extend(item_failures)
        proofs.append(proof)

    ordered_episode_digests = tuple(proof.episode_run_digest for proof in proofs)
    ordered_record_digests = tuple(proof.record_digest for proof in proofs)
    episode_ids = [proof.episode_id for proof in proofs]

    # Bijection against the session denominator ROOT (order + count + no dup + no missing + no extra).
    all_episodes_proven = all(digest != "" for digest in ordered_episode_digests)
    if all_episodes_proven and len(ordered_episode_digests) == len(session_episode_digests):
        if ordered_episode_digests != session_episode_digests:
            hard.append(_reason("episode_order_mismatch"))
    present_episode_digests = [digest for digest in ordered_episode_digests if digest != ""]
    present_record_digests = [digest for digest in ordered_record_digests if digest != ""]
    present_episode_ids = [episode_id for episode_id in episode_ids if episode_id != ""]
    if len(set(present_episode_digests)) != len(present_episode_digests):
        hard.append(_reason("duplicate_substrate_episode"))
    if len(set(present_record_digests)) != len(present_record_digests):
        hard.append(_reason("duplicate_record_digest"))
    if len(set(present_episode_ids)) != len(present_episode_ids):
        hard.append(_reason("duplicate_record_episode_id"))

    session_set = set(session_episode_digests)
    input_episode_set = set(present_episode_digests)
    if all_episodes_proven:
        if session_set - input_episode_set:
            hard.append(_reason("missing_record_for_episode"))
        if input_episode_set - session_set:
            hard.append(_reason("extra_record_without_episode"))

    # SM-4 aggregated EXACTLY this record set (no dropped/added record between SM-4 and the substrate).
    evidence_record_digests = (
        set(metrics_evidence.record_digests) if type(metrics_evidence.record_digests) is tuple else set()
    )
    input_record_set = set(present_record_digests)
    if len(present_record_digests) != len(ordered_record_digests) or input_record_set != evidence_record_digests:
        hard.append(_reason("records_not_metrics_evidence"))

    reason_codes = _sorted_unique(hard)
    status = (
        PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
        if reason_codes
        else PaperSecondaryMetricsSubstrateReconciliationStatus.RECONCILED
    )
    ready = status is PaperSecondaryMetricsSubstrateReconciliationStatus.RECONCILED

    if ready:
        reconciled_episode_digests = ordered_episode_digests
        reconciled_record_digests = tuple(sorted(input_record_set))
        filled_count = sum(1 for proof in proofs if proof.classification != "rejected")
        rejected_count = sum(1 for proof in proofs if proof.classification == "rejected")
        positive_count = sum(1 for proof in proofs if proof.classification == "positive")
        negative_count = sum(1 for proof in proofs if proof.classification == "negative")
        zero_count = sum(1 for proof in proofs if proof.classification == "zero")
    else:
        reconciled_episode_digests = ()
        reconciled_record_digests = ()
        filled_count = rejected_count = positive_count = negative_count = zero_count = 0

    reconciliation_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "reconciliation_version": _RECONCILIATION_VERSION,
        "status": status,
        "ready": ready,
        "reconciliation_id": reconciliation_id,
        "correlation_id": correlation_id,
        "policy_id": policy_id,
        "market_symbol": market_symbol,
        "verified_policy_digest": policy.policy_digest if _is_hex64_string(policy.policy_digest) else "",
        "verified_metrics_evidence_digest": (
            metrics_evidence.evidence_digest if _is_hex64_string(metrics_evidence.evidence_digest) else ""
        ),
        "verified_session_sequence_digest": (
            session_sequence.paper_session_sequence_digest
            if _is_hex64_string(session_sequence.paper_session_sequence_digest)
            else ""
        ),
        "episode_count": len(input_tuple),
        "reconciled_episode_run_digests": reconciled_episode_digests,
        "reconciled_record_digests": reconciled_record_digests,
        "filled_episode_count": filled_count,
        "rejected_or_unfilled_episode_count": rejected_count,
        "positive_pnl_episode_count": positive_count,
        "negative_pnl_episode_count": negative_count,
        "zero_pnl_episode_count": zero_count,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = PaperSecondaryMetricsSubstrateReconciliation(reconciliation_digest="", **reconciliation_fields)  # type: ignore[arg-type]
    return _replace_reconciliation_digest(seed, paper_secondary_metrics_substrate_reconciliation_digest(seed))


def _replace_reconciliation_digest(
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation, digest: str
) -> PaperSecondaryMetricsSubstrateReconciliation:
    values = {
        field.name: getattr(reconciliation, field.name)
        for field in fields(reconciliation)
        if field.name != "reconciliation_digest"
    }
    values["reconciliation_digest"] = digest
    return PaperSecondaryMetricsSubstrateReconciliation(**values)  # type: ignore[arg-type]


def _reconciliation_payload_from(
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in fields(reconciliation):
        if field.name == "reconciliation_digest":
            continue
        value = getattr(reconciliation, field.name)
        if field.name == "status":
            payload[field.name] = (
                value.value if isinstance(value, PaperSecondaryMetricsSubstrateReconciliationStatus) else value
            )
        elif field.name == "reason_codes":
            payload[field.name] = list(reconciliation.reason_codes)
        elif field.name == "reconciled_episode_run_digests":
            payload[field.name] = list(reconciliation.reconciled_episode_run_digests)
        elif field.name == "reconciled_record_digests":
            payload[field.name] = list(reconciliation.reconciled_record_digests)
        elif field.name == "metadata":
            payload[field.name] = _serialize_metadata(reconciliation.metadata)
        else:
            payload[field.name] = value
    return payload


def paper_secondary_metrics_substrate_reconciliation_to_dict(
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation,
) -> dict[str, object]:
    """Canonical JSON-ready mapping for the reconciliation, including its self-digest."""

    payload = _reconciliation_payload_from(reconciliation)
    payload["reconciliation_digest"] = reconciliation.reconciliation_digest
    return payload


def paper_secondary_metrics_substrate_reconciliation_digest(
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation,
) -> str:
    """Recompute the canonical reconciliation digest, excluding only the self-digest field."""

    return _canonical_digest(_reconciliation_payload_from(reconciliation))


__all__ = [
    "PaperSecondaryMetricsSubstrateReconciliation",
    "PaperSecondaryMetricsSubstrateReconciliationError",
    "PaperSecondaryMetricsSubstrateReconciliationStatus",
    "PaperSecondaryMetricsSubstrateRecordInput",
    "build_paper_secondary_metrics_substrate_reconciliation",
    "paper_secondary_metrics_substrate_reconciliation_digest",
    "paper_secondary_metrics_substrate_reconciliation_to_dict",
]
