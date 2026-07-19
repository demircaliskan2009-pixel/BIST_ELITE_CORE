"""Digest-bound UTC-window evidence for paper secondary metrics.

This validation-only artifact closes the SM-4/SM-6 window-lineage gap.  It consumes the
already-reconciled SM record inventory and the exact 30-day gate used by the Stage-4 chain, then
re-proves every record -> episode -> fill -> market-snapshot link.  The timestamp authority is the
digest-bound ``PaperFillMarketSnapshot.observed_at_ns``; containment is start-inclusive and
end-exclusive.  It performs no metric calculation, threshold enforcement, comparison, runtime IO,
execution, scheduling, or capital action.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum

from crypto_core.validation.paper_30day_evidence_gate_decision import (
    PaperThirtyDayEvidenceGateDecision,
    PaperThirtyDayEvidenceGateDecisionStatus,
    paper_30day_evidence_gate_decision_digest,
)
from crypto_core.validation.paper_episode_runner import (
    PaperEpisodeRunResult,
    paper_episode_run_result_digest,
)
from crypto_core.validation.paper_fill_simulator import (
    PaperFillMarketSnapshot,
    PaperFillSimulationResult,
    PaperFillSimulationStatus,
    paper_fill_market_snapshot_digest,
    paper_fill_simulation_result_digest,
)
from crypto_core.validation.paper_secondary_metrics_substrate_reconciliation import (
    PaperSecondaryMetricsSubstrateReconciliation,
    PaperSecondaryMetricsSubstrateReconciliationStatus,
    paper_secondary_metrics_substrate_reconciliation_digest,
)
from crypto_core.validation.trade_record_evidence import (
    TradeRecordEvidence,
    trade_record_evidence_digest,
)

_SCHEMA_VERSION = "paper-secondary-metrics-window-evidence.v1"
_EVIDENCE_VERSION = "paper-secondary-metrics-window-evidence.v1"
_REASON_PREFIX = "paper_secondary_metrics_window_evidence"
_EXPECTED_RECONCILIATION_SCHEMA = "paper-secondary-metrics-substrate-reconciliation.v1"
_EXPECTED_GATE_SCHEMA = "paper-30day-evidence-gate-decision.v1"
_EXPECTED_RECORD_SCHEMA = "trade-record-evidence.v1"
_EXPECTED_EPISODE_SCHEMA = "paper-episode-run-result.v1"
_EXPECTED_FILL_SCHEMA = "paper-fill-simulation-result.v1"
_EXPECTED_SNAPSHOT_SCHEMA = "paper-fill-market-snapshot.v1"
_DAY_NS = 86_400_000_000_000
_REQUIRED_DAY_COUNT = 30
_MAX_RECORDS = 100_000
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


class PaperSecondaryMetricsWindowEvidenceError(RuntimeError):
    """Raised for malformed caller-level inputs at the window-evidence boundary."""


class PaperSecondaryMetricsWindowEvidenceStatus(str, Enum):
    """WINDOW_READY proves only exact paper record-to-gate UTC-window lineage."""

    WINDOW_READY = "WINDOW_READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperSecondaryMetricsWindowRecordInput:
    """One reconciled record and its digest-linked timestamp authority."""

    record: TradeRecordEvidence
    episode_run: PaperEpisodeRunResult
    fill_result: PaperFillSimulationResult
    market_snapshot: PaperFillMarketSnapshot


@dataclass(frozen=True)
class PaperSecondaryMetricsWindowEvidence:
    """Immutable proof that every reconciled SM member belongs to one exact gate window."""

    schema_version: str
    evidence_version: str
    status: PaperSecondaryMetricsWindowEvidenceStatus
    ready: bool
    window_evidence_id: str
    correlation_id: str
    policy_id: str
    market_symbol: str
    window_id: str
    reconciliation_id: str
    gate_id: str
    expected_reconciliation_digest: str
    verified_reconciliation_digest: str
    expected_gate_decision_digest: str
    verified_gate_decision_digest: str
    verified_policy_digest: str
    verified_metrics_evidence_digest: str
    verified_session_sequence_digest: str
    gate_window_start_ns: int
    gate_window_end_ns: int
    gate_window_start_utc_day_index: int
    gate_window_end_utc_day_index: int
    gate_utc_day_indices: tuple[int, ...]
    observed_at_ns: tuple[int, ...]
    observed_utc_day_indices: tuple[int, ...]
    record_digests: tuple[str, ...]
    episode_run_digests: tuple[str, ...]
    fill_result_digests: tuple[str, ...]
    market_snapshot_digests: tuple[str, ...]
    record_count: int
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    window_evidence_digest: str
    paper_only: bool = True
    validation_only: bool = True
    reconciliation_consumed: bool = False
    gate_decision_consumed: bool = False
    exact_window_bound: bool = False
    record_set_reconciled: bool = False
    timestamps_digest_bound: bool = False
    stage4_comparator_invoked: bool = False
    secondary_metrics_enforced: bool = False
    stage4_completion_decided: bool = False
    prdv4_stage4_complete: bool = False
    machine_time_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    operational_readiness: bool = False
    production_execution: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    capital_mutation_enabled: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    real_wall_clock_used: bool = False


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
    return type(value) is str and len(value) == 64 and all(char in _HEX_CHARS for char in value)


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


# Exact-type-before-operation rule: no anchor-carried value may participate in equality, ordering,
# arithmetic, sorting, set construction, or hashing until its exact built-in runtime type is proven. A
# JSON-serializable ``str``/``int`` subclass survives every digest recompute byte-identically, so digest
# validity can never substitute for these gates, and a custom ``__eq__``/``__hash__`` must never be
# reachable from a coherently resealed anchor.


def _eq_plain_str(value: object, expected: str) -> bool:
    return type(value) is str and value == expected


def _eq_exact_int(value: object, expected: int) -> bool:
    return _is_exact_int(value) and value == expected


def _is_empty_tuple(value: object) -> bool:
    return type(value) is tuple and len(value) == 0


def _is_hex64_tuple(value: object) -> bool:
    return type(value) is tuple and all(_is_hex64_string(item) for item in value)


def _plain_strings_equal(*values: object) -> bool:
    return all(_is_plain_non_empty_string(value) for value in values) and len({*values}) == 1


def _hex64_strings_equal(*values: object) -> bool:
    return all(_is_hex64_string(value) for value in values) and len({*values}) == 1


def _is_canonical_metadata(value: object) -> bool:
    if type(value) is not tuple:
        return False
    if any(
        type(pair) is not tuple
        or len(pair) != 2
        or not _is_plain_non_empty_string(pair[0])
        or type(pair[1]) is not str
        or pair[1] != pair[1].strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in pair[1])
        for pair in value
    ):
        return False
    return value == tuple(sorted(value)) and len({key for key, _ in value}) == len(value)


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperSecondaryMetricsWindowEvidenceError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _require_hex64(value: object, field_name: str) -> str:
    if not _is_hex64_string(value):
        raise PaperSecondaryMetricsWindowEvidenceError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSecondaryMetricsWindowEvidenceError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not _is_plain_non_empty_string(key) or type(value) is not str or value != value.strip():
            raise PaperSecondaryMetricsWindowEvidenceError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperSecondaryMetricsWindowEvidenceError(_reason("metadata_malformed"))
        items.append((key, value))
    normalized = tuple(sorted(items))
    if len({key for key, _ in normalized}) != len(normalized):
        raise PaperSecondaryMetricsWindowEvidenceError(_reason("metadata_malformed"))
    return normalized


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
    return any(
        type(text) is str and text != "" and any(token in text.lower() for token in _CLOCK_TOKENS) for text in texts
    )


def _recomputed_digest_or_none(compute: object, artifact: object) -> str | None:
    try:
        return compute(artifact)  # type: ignore[operator]
    except Exception:  # noqa: BLE001 - serializer failures are deterministic REJECTED evidence
        return None


def _digest_reproof_failures(
    *, artifact: object, carried_digest: object, expected_digest: str, compute: object, reason_code: str
) -> tuple[list[str], str]:
    recomputed = _recomputed_digest_or_none(compute, artifact)
    if (
        recomputed is None
        or not _is_hex64_string(carried_digest)
        or recomputed != carried_digest
        or recomputed != expected_digest
    ):
        return [_reason(reason_code)], ""
    return [], recomputed


def _reconciliation_failures(reconciliation: PaperSecondaryMetricsSubstrateReconciliation) -> list[str]:
    records = reconciliation.reconciled_record_digests
    episodes = reconciliation.reconciled_episode_run_digests
    valid_inventory = (
        _is_hex64_tuple(records)
        and _is_hex64_tuple(episodes)
        and _is_exact_int(reconciliation.episode_count)
        and 1 <= len(records) <= _MAX_RECORDS
        and len(records) == len(episodes) == reconciliation.episode_count
        and records == tuple(sorted(records))
        and len(set(records)) == len(records)
        and len(set(episodes)) == len(episodes)
    )
    if not (
        _eq_plain_str(reconciliation.schema_version, _EXPECTED_RECONCILIATION_SCHEMA)
        and _eq_plain_str(reconciliation.reconciliation_version, _EXPECTED_RECONCILIATION_SCHEMA)
        and reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.RECONCILED
        and reconciliation.ready is True
        and _is_empty_tuple(reconciliation.reason_codes)
        and _is_plain_non_empty_string(reconciliation.reconciliation_id)
        and _is_plain_non_empty_string(reconciliation.correlation_id)
        and _is_plain_non_empty_string(reconciliation.policy_id)
        and _is_plain_non_empty_string(reconciliation.market_symbol)
        and _is_hex64_string(reconciliation.verified_policy_digest)
        and _is_hex64_string(reconciliation.verified_metrics_evidence_digest)
        and _is_hex64_string(reconciliation.verified_session_sequence_digest)
        and _is_canonical_metadata(reconciliation.metadata)
        and reconciliation.paper_only is True
        and reconciliation.validation_only is True
        and all(
            getattr(reconciliation, flag) is False
            for flag in (
                "live_ready",
                "shadow_ready",
                "connector_ready",
                "orders_enabled",
                "real_fills_used",
                "authoritative_pnl",
                "capital_mutation_enabled",
                "scheduler_enabled",
                "stage4_complete",
                "sm5_enabled",
                "sm6_enabled",
            )
        )
        and valid_inventory
    ):
        return [_reason("reconciliation_contract_invalid")]
    return []


def _gate_window_values(
    gate: PaperThirtyDayEvidenceGateDecision,
) -> tuple[list[str], int, int, int, int, tuple[int, ...]]:
    hard: list[str] = []
    start = gate.gate_used_first_bucket_start_ns
    end = gate.gate_used_last_bucket_end_ns
    if not (
        _eq_plain_str(gate.schema_version, _EXPECTED_GATE_SCHEMA)
        and _eq_plain_str(gate.decision_version, _EXPECTED_GATE_SCHEMA)
        and gate.status is PaperThirtyDayEvidenceGateDecisionStatus.READY
        and gate.ready is True
        and _is_empty_tuple(gate.reason_codes)
        and gate.thirty_day_gate_satisfied is True
        and _is_plain_non_empty_string(gate.gate_id)
        and _is_plain_non_empty_string(gate.window_id)
        and _is_plain_non_empty_string(gate.correlation_id)
        and _is_plain_non_empty_string(gate.market_symbol)
        and _is_canonical_metadata(gate.metadata)
        and gate.paper_only is True
    ):
        hard.append(_reason("gate_decision_contract_invalid"))
    valid_window = (
        _is_exact_int(start)
        and _is_exact_int(end)
        and start >= 0
        and end > start
        and start % _DAY_NS == 0
        and end % _DAY_NS == 0
        and end - start == _REQUIRED_DAY_COUNT * _DAY_NS
        and _eq_exact_int(gate.gate_bucket_count_used, _REQUIRED_DAY_COUNT)
        and _eq_exact_int(gate.gate_minimum_consecutive_bucket_count, _REQUIRED_DAY_COUNT)
    )
    if not valid_window:
        hard.append(_reason("gate_window_invalid"))
        return hard, 0, 0, 0, 0, ()
    start_day = start // _DAY_NS
    end_day = (end // _DAY_NS) - 1
    days = tuple(range(start_day, end_day + 1))
    if len(days) != _REQUIRED_DAY_COUNT:
        hard.append(_reason("gate_window_day_indices_invalid"))
        return hard, start, end, 0, 0, ()
    return hard, start, end, start_day, end_day, days


@dataclass(frozen=True)
class _MemberProof:
    record_digest: str
    episode_digest: str
    fill_digest: str
    snapshot_digest: str
    observed_at_ns: int


def _member_failures(
    item: PaperSecondaryMetricsWindowRecordInput,
    *,
    correlation_id: str,
    policy_id: str,
    market_symbol: str,
    start_ns: int,
    end_ns: int,
) -> tuple[list[str], _MemberProof]:
    hard: list[str] = []
    record = item.record
    episode = item.episode_run
    fill = item.fill_result
    snapshot = item.market_snapshot
    record_digest = _recomputed_digest_or_none(trade_record_evidence_digest, record)
    episode_digest = _recomputed_digest_or_none(paper_episode_run_result_digest, episode)
    fill_digest = _recomputed_digest_or_none(paper_fill_simulation_result_digest, fill)
    snapshot_digest = _recomputed_digest_or_none(paper_fill_market_snapshot_digest, snapshot)
    if record_digest is None or not _hex64_strings_equal(record_digest, record.record_digest):
        hard.append(_reason("record_digest_mismatch"))
        record_digest = ""
    if episode_digest is None or not _hex64_strings_equal(episode_digest, episode.episode_run_digest):
        hard.append(_reason("episode_run_digest_mismatch"))
        episode_digest = ""
    if fill_digest is None or not _hex64_strings_equal(fill_digest, fill.result_digest):
        hard.append(_reason("fill_result_digest_mismatch"))
        fill_digest = ""
    if snapshot_digest is None or not _hex64_strings_equal(snapshot_digest, snapshot.snapshot_digest):
        hard.append(_reason("market_snapshot_digest_mismatch"))
        snapshot_digest = ""
    if not (
        _eq_plain_str(record.schema_version, _EXPECTED_RECORD_SCHEMA)
        and _eq_plain_str(episode.schema_version, _EXPECTED_EPISODE_SCHEMA)
    ):
        hard.append(_reason("member_schema_invalid"))
    if not (
        _eq_plain_str(fill.schema_version, _EXPECTED_FILL_SCHEMA)
        and _eq_plain_str(snapshot.schema_version, _EXPECTED_SNAPSHOT_SCHEMA)
    ):
        hard.append(_reason("member_schema_invalid"))
    if not _plain_strings_equal(record.episode_id, episode.episode_run_id):
        hard.append(_reason("record_episode_binding_mismatch"))
    # Exact enum/runtime type is proven BEFORE any ``.value`` access or status equality: a forged exact-type
    # fill carrying a malformed status (``None``/int/bool/plain string/foreign enum/equality-raising object)
    # must become deterministic REJECTED evidence, never a raw exception. A foreign ``str``-enum whose
    # ``.value`` matches a valid member is digest-equivalent through the upstream serializer, so digest
    # validity can never substitute for this gate. The same rule covers the carried member-link digests: a
    # digest recompute failure never licenses a later direct comparison over the malformed carried value.
    fill_status_canonical = type(fill.status) is PaperFillSimulationStatus
    episode_fill_status_canonical = _is_plain_non_empty_string(episode.fill_status)
    if not fill_status_canonical or not episode_fill_status_canonical:
        hard.append(_reason("fill_status_contract_invalid"))
    if not _hex64_strings_equal(episode.fill_simulation_result_digest, fill_digest) or (
        fill_status_canonical and episode_fill_status_canonical and episode.fill_status != fill.status.value
    ):
        hard.append(_reason("episode_fill_binding_mismatch"))
    if not _hex64_strings_equal(episode.fill_market_snapshot_digest, snapshot_digest) or not _hex64_strings_equal(
        fill.market_snapshot_digest, snapshot_digest
    ):
        hard.append(_reason("snapshot_binding_mismatch"))
    if not all(
        _eq_plain_str(value, correlation_id)
        for value in (record.correlation_id, episode.correlation_id, fill.correlation_id)
    ):
        hard.append(_reason("correlation_id_mismatch"))
    if not _plain_strings_equal(record.policy_id, policy_id):
        hard.append(_reason("policy_id_mismatch"))
    if not all(
        _plain_strings_equal(value, market_symbol)
        for value in (episode.market_symbol, fill.market_symbol, snapshot.market_symbol)
    ):
        hard.append(_reason("market_symbol_mismatch"))
    observed = snapshot.observed_at_ns
    if not _is_exact_int(observed) or observed < 0:
        hard.append(_reason("snapshot_timestamp_missing_or_invalid"))
        observed_value = 0
    else:
        observed_value = observed
        if not (start_ns <= observed < end_ns):
            hard.append(_reason("snapshot_outside_gate_window"))
    identities = (
        record.record_id,
        record.episode_id,
        episode.episode_run_id,
        fill.fill_simulation_id,
        snapshot.snapshot_id,
    )
    metadata_values = (record.metadata, episode.metadata, fill.metadata, snapshot.metadata)
    if any(not _is_plain_non_empty_string(value) for value in identities) or any(
        not _is_canonical_metadata(value) for value in metadata_values
    ):
        hard.append(_reason("member_contract_invalid"))
    texts = [*identities]
    for metadata in metadata_values:
        if _is_canonical_metadata(metadata):
            texts.extend(_metadata_texts(metadata))
    if _has_scope_violation(*texts) or _has_clock_token(*texts):
        hard.append(_reason("anchor_scope_violation"))
    return hard, _MemberProof(
        record_digest=record_digest,
        episode_digest=episode_digest,
        fill_digest=fill_digest,
        snapshot_digest=snapshot_digest,
        observed_at_ns=observed_value,
    )


def build_paper_secondary_metrics_window_evidence(
    reconciliation: PaperSecondaryMetricsSubstrateReconciliation,
    gate_decision: PaperThirtyDayEvidenceGateDecision,
    record_inputs: Sequence[PaperSecondaryMetricsWindowRecordInput],
    *,
    expected_reconciliation_digest: str,
    expected_gate_decision_digest: str,
    window_evidence_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSecondaryMetricsWindowEvidence:
    """Build exact reconciled-record lineage into the gate-used UTC interval."""

    if type(reconciliation) is not PaperSecondaryMetricsSubstrateReconciliation:
        raise PaperSecondaryMetricsWindowEvidenceError(_reason("reconciliation_malformed"))
    if type(gate_decision) is not PaperThirtyDayEvidenceGateDecision:
        raise PaperSecondaryMetricsWindowEvidenceError(_reason("gate_decision_malformed"))
    if isinstance(record_inputs, (str, bytes, bytearray)) or not isinstance(record_inputs, Sequence):
        raise PaperSecondaryMetricsWindowEvidenceError(_reason("record_inputs_malformed"))
    inputs = tuple(record_inputs)
    if (
        not inputs
        or len(inputs) > _MAX_RECORDS
        or any(type(item) is not PaperSecondaryMetricsWindowRecordInput for item in inputs)
    ):
        raise PaperSecondaryMetricsWindowEvidenceError(_reason("record_inputs_malformed"))
    if any(
        type(item.record) is not TradeRecordEvidence
        or type(item.episode_run) is not PaperEpisodeRunResult
        or type(item.fill_result) is not PaperFillSimulationResult
        or type(item.market_snapshot) is not PaperFillMarketSnapshot
        for item in inputs
    ):
        raise PaperSecondaryMetricsWindowEvidenceError(_reason("window_record_input_malformed"))
    expected_reconciliation_digest = _require_hex64(expected_reconciliation_digest, "expected_reconciliation_digest")
    expected_gate_decision_digest = _require_hex64(expected_gate_decision_digest, "expected_gate_decision_digest")
    window_evidence_id = _require_plain_non_empty_string(window_evidence_id, "window_evidence_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(window_evidence_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperSecondaryMetricsWindowEvidenceError(_reason("scope_violation"))
    if _has_clock_token(window_evidence_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperSecondaryMetricsWindowEvidenceError(_reason("clock_token_forbidden"))

    hard: list[str] = []
    reconciliation_digest_failures, verified_reconciliation_digest = _digest_reproof_failures(
        artifact=reconciliation,
        carried_digest=reconciliation.reconciliation_digest,
        expected_digest=expected_reconciliation_digest,
        compute=paper_secondary_metrics_substrate_reconciliation_digest,
        reason_code="reconciliation_digest_mismatch",
    )
    hard.extend(reconciliation_digest_failures)
    gate_digest_failures, verified_gate_digest = _digest_reproof_failures(
        artifact=gate_decision,
        carried_digest=gate_decision.decision_digest,
        expected_digest=expected_gate_decision_digest,
        compute=paper_30day_evidence_gate_decision_digest,
        reason_code="gate_decision_digest_mismatch",
    )
    hard.extend(gate_digest_failures)
    hard.extend(_reconciliation_failures(reconciliation))
    gate_failures, start_ns, end_ns, start_day, end_day, gate_days = _gate_window_values(gate_decision)
    hard.extend(gate_failures)
    if not (
        _eq_plain_str(reconciliation.correlation_id, correlation_id)
        and _eq_plain_str(gate_decision.correlation_id, correlation_id)
    ):
        hard.append(_reason("correlation_id_mismatch"))
    if not _plain_strings_equal(reconciliation.market_symbol, gate_decision.market_symbol):
        hard.append(_reason("market_symbol_mismatch"))

    proofs: list[_MemberProof] = []
    for item in inputs:
        member_failures, proof = _member_failures(
            item,
            correlation_id=correlation_id,
            policy_id=reconciliation.policy_id,
            market_symbol=reconciliation.market_symbol,
            start_ns=start_ns,
            end_ns=end_ns,
        )
        hard.extend(member_failures)
        proofs.append(proof)

    record_digests = tuple(proof.record_digest for proof in proofs)
    episode_digests = tuple(proof.episode_digest for proof in proofs)
    fill_digests = tuple(proof.fill_digest for proof in proofs)
    snapshot_digests = tuple(proof.snapshot_digest for proof in proofs)
    observed_values = tuple(proof.observed_at_ns for proof in proofs)
    observed_days = tuple(value // _DAY_NS for value in observed_values)
    # The reconciliation-carried inventories are proven exact hex64 tuples BEFORE any equality touches
    # their items; the recomputed member digests on the left are plain strings by construction.
    if (
        not _is_hex64_tuple(reconciliation.reconciled_record_digests)
        or tuple(sorted(record_digests)) != reconciliation.reconciled_record_digests
        or len(set(record_digests)) != len(record_digests)
    ):
        hard.append(_reason("reconciliation_record_inventory_mismatch"))
    if (
        not _is_hex64_tuple(reconciliation.reconciled_episode_run_digests)
        or episode_digests != reconciliation.reconciled_episode_run_digests
        or len(set(episode_digests)) != len(episode_digests)
    ):
        hard.append(_reason("reconciliation_episode_inventory_mismatch"))
    if not (
        _is_exact_int(reconciliation.episode_count)
        and len(inputs) == reconciliation.episode_count
        and len(inputs)
        == len(record_digests)
        == len(episode_digests)
        == len(fill_digests)
        == len(snapshot_digests)
        == len(observed_values)
    ):
        hard.append(_reason("window_inventory_count_mismatch"))
    if any(day not in gate_days for day in observed_days):
        hard.append(_reason("observed_day_index_outside_gate"))

    anchor_texts = (
        reconciliation.reconciliation_id,
        reconciliation.correlation_id,
        reconciliation.policy_id,
        reconciliation.market_symbol,
        gate_decision.gate_id,
        gate_decision.window_id,
        gate_decision.correlation_id,
        gate_decision.market_symbol,
    )
    if _has_scope_violation(*anchor_texts) or _has_clock_token(*anchor_texts):
        hard.append(_reason("anchor_scope_violation"))

    hard = sorted(set(hard))
    ready = not hard
    status = (
        PaperSecondaryMetricsWindowEvidenceStatus.WINDOW_READY
        if ready
        else PaperSecondaryMetricsWindowEvidenceStatus.REJECTED
    )
    evidence_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "evidence_version": _EVIDENCE_VERSION,
        "status": status,
        "ready": ready,
        "window_evidence_id": window_evidence_id,
        "correlation_id": correlation_id,
        "policy_id": reconciliation.policy_id if _is_plain_non_empty_string(reconciliation.policy_id) else "",
        "market_symbol": reconciliation.market_symbol
        if _is_plain_non_empty_string(reconciliation.market_symbol)
        else "",
        "window_id": gate_decision.window_id if _is_plain_non_empty_string(gate_decision.window_id) else "",
        "reconciliation_id": (
            reconciliation.reconciliation_id if _is_plain_non_empty_string(reconciliation.reconciliation_id) else ""
        ),
        "gate_id": gate_decision.gate_id if _is_plain_non_empty_string(gate_decision.gate_id) else "",
        "expected_reconciliation_digest": expected_reconciliation_digest,
        "verified_reconciliation_digest": verified_reconciliation_digest,
        "expected_gate_decision_digest": expected_gate_decision_digest,
        "verified_gate_decision_digest": verified_gate_digest,
        "verified_policy_digest": reconciliation.verified_policy_digest
        if _is_hex64_string(reconciliation.verified_policy_digest)
        else "",
        "verified_metrics_evidence_digest": reconciliation.verified_metrics_evidence_digest
        if _is_hex64_string(reconciliation.verified_metrics_evidence_digest)
        else "",
        "verified_session_sequence_digest": reconciliation.verified_session_sequence_digest
        if _is_hex64_string(reconciliation.verified_session_sequence_digest)
        else "",
        "gate_window_start_ns": start_ns,
        "gate_window_end_ns": end_ns,
        "gate_window_start_utc_day_index": start_day,
        "gate_window_end_utc_day_index": end_day,
        "gate_utc_day_indices": gate_days,
        "observed_at_ns": observed_values,
        "observed_utc_day_indices": observed_days,
        "record_digests": tuple(sorted(record_digests)),
        "episode_run_digests": episode_digests,
        "fill_result_digests": fill_digests,
        "market_snapshot_digests": snapshot_digests,
        "record_count": len(inputs),
        "reason_codes": tuple(hard),
        "metadata": metadata_pairs,
        "reconciliation_consumed": ready,
        "gate_decision_consumed": ready,
        "exact_window_bound": ready,
        "record_set_reconciled": ready,
        "timestamps_digest_bound": ready,
    }
    seed = PaperSecondaryMetricsWindowEvidence(window_evidence_digest="", **evidence_fields)  # type: ignore[arg-type]
    return replace(seed, window_evidence_digest=paper_secondary_metrics_window_evidence_digest(seed))


def _evidence_payload_from(evidence: PaperSecondaryMetricsWindowEvidence) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in fields(evidence):
        if field.name == "window_evidence_digest":
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


def paper_secondary_metrics_window_evidence_to_dict(
    evidence: PaperSecondaryMetricsWindowEvidence,
) -> dict[str, object]:
    """Return the canonical JSON-ready public representation including the self-digest."""

    payload = _evidence_payload_from(evidence)
    payload["window_evidence_digest"] = evidence.window_evidence_digest
    return payload


def paper_secondary_metrics_window_evidence_digest(evidence: PaperSecondaryMetricsWindowEvidence) -> str:
    """Recompute the canonical digest over every public field except the self-digest."""

    return _canonical_digest(_evidence_payload_from(evidence))


__all__ = [
    "PaperSecondaryMetricsWindowEvidence",
    "PaperSecondaryMetricsWindowEvidenceError",
    "PaperSecondaryMetricsWindowEvidenceStatus",
    "PaperSecondaryMetricsWindowRecordInput",
    "build_paper_secondary_metrics_window_evidence",
    "paper_secondary_metrics_window_evidence_digest",
    "paper_secondary_metrics_window_evidence_to_dict",
]
