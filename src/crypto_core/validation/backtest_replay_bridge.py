"""Backtest replay bridge — connect an admitted bundle decision into the existing replay-admission gate.

A small, deterministic, fail-closed adapter that takes a high-level ``BacktestAdmissionDecision`` (the
collapsed StrategySpec → bundle → admission verdict) plus the explicit *raw* evidence objects, proves the
raw evidence is consistent with the admission verdict, and then **delegates** to the existing
``evaluate_backtest_replay_admission``. It does not re-implement replay window / source / policy /
currentness validation (the existing evaluator owns that), builds no ReplayPlan mirror, runs no backtest
engine, and adds no persistence/runtime/scheduler/live path.

Design rules:
  - Gate, then delegate: the bridge only adds the admission→evidence consistency proof (admission is
    ADMITTED + paper-safe, raw strategy digest equals the admission's, enough ledger records); all
    metadata/window/policy/currentness checks are delegated to ``evaluate_backtest_replay_admission``.
  - Fail closed: a wrong-typed ``admission_decision`` or empty ``correlation_id`` raises; a non-admitted
    decision, a strategy-digest mismatch, or unsafe flags yield REJECTED *before* the evaluator runs;
    insufficient raw ledger evidence yields INSUFFICIENT_EVIDENCE before the evaluator runs. No fabrication.
  - Traceable: the thin ``BacktestReplayBridgeResult`` carries the admission_digest alongside the existing
    replay-admission result, so the admitted-bundle → replay-admission link is auditable by one digest.
  - Deterministic: a canonical SHA-256 ``bridge_digest``; no wall-clock/random/IO. Frozen, paper-only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.backtest_admission import (
    BacktestAdmissionDecision,
    BacktestAdmissionStatus,
    backtest_admission_decision_to_dict,
)
from crypto_core.validation.backtest_replay_admission import (
    BacktestReplayAdmissionInput,
    BacktestReplayAdmissionPolicy,
    BacktestReplayAdmissionResult,
    BacktestReplayAdmissionStatus,
    BacktestReplayWindow,
    backtest_replay_admission_to_dict,
    evaluate_backtest_replay_admission,
)

_SCHEMA_VERSION = "backtest-replay-bridge.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


class BacktestReplayBridgeError(RuntimeError):
    """Raised when bridge inputs are malformed at the call level (wrong type / empty correlation id)."""


@dataclass(frozen=True)
class BacktestReplayBridgeResult:
    """Deterministic, immutable bridge result: the admission_digest plus the delegated replay verdict."""

    schema_version: str
    status: BacktestReplayAdmissionStatus
    accepted: bool
    admission_digest: str
    strategy_id: str | None
    strategy_digest: str | None
    replay_admission_status: str | None
    replay_admission_result: BacktestReplayAdmissionResult | None
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    correlation_id: str
    bridge_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _expected_admission_digest(admission_decision: BacktestAdmissionDecision) -> str | None:
    try:
        payload = backtest_admission_decision_to_dict(admission_decision)
        payload.pop("admission_digest", None)
        return _canonical_digest(payload)
    except Exception:
        return None


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _spec_digest_or_none(spec_or_mapping: object) -> str | None:
    """Resolve a raw strategy spec to its canonical digest without raising (None if unresolvable)."""
    if isinstance(spec_or_mapping, StrategySpec):
        return strategy_spec_digest(spec_or_mapping)
    if isinstance(spec_or_mapping, Mapping):
        result = validate_strategy_spec(spec_or_mapping)
        if result.accepted and result.spec is not None:
            return strategy_spec_digest(result.spec)
    return None


def build_backtest_replay_bridge(
    admission_decision: BacktestAdmissionDecision,
    *,
    strategy_spec: StrategySpec | Mapping[str, Any],
    leakage_bias_repaint_result: object,
    pit_parity_result: object,
    decision_ledger_records: object,
    replay_source_id: str,
    historical_data_source_id: str,
    replay_window: BacktestReplayWindow,
    admission_policy: BacktestReplayAdmissionPolicy,
    evidence_digest_by_stage: Mapping[Any, str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    correlation_id: str,
) -> BacktestReplayBridgeResult:
    """Bridge an ADMITTED ``BacktestAdmissionDecision`` into ``evaluate_backtest_replay_admission``.

    The bridge proves the raw evidence is consistent with the admission verdict — the decision is
    ADMITTED and paper-safe, the raw strategy digest equals ``admission_decision.strategy_digest``, and at
    least ``admission_decision.decision_record_count`` raw ledger records are supplied — then delegates the
    replay window / source / policy / currentness checks to the existing evaluator. A wrong-typed decision
    or empty ``correlation_id`` raises ``BacktestReplayBridgeError``; every other outcome is a deterministic
    bridge result that carries the admission_digest and the delegated replay-admission result.
    """
    if not isinstance(admission_decision, BacktestAdmissionDecision):
        raise BacktestReplayBridgeError("backtest_replay_bridge:admission_decision_malformed")
    if not _is_non_empty_string(correlation_id):
        raise BacktestReplayBridgeError("backtest_replay_bridge:correlation_id_invalid")

    strategy_digest = _spec_digest_or_none(strategy_spec)

    gate_rejections: list[str] = []
    gate_insufficient: list[str] = []

    if admission_decision.status is not BacktestAdmissionStatus.ADMITTED or not admission_decision.admitted:
        gate_rejections.append("backtest_replay_bridge:admission_not_admitted")
    if not admission_decision.paper_only:
        gate_rejections.append("backtest_replay_bridge:not_paper_only")
    if admission_decision.real_orders_enabled:
        gate_rejections.append("backtest_replay_bridge:real_orders_enabled")
    if admission_decision.real_money_enabled:
        gate_rejections.append("backtest_replay_bridge:real_money_enabled")
    if not _is_sha256_hex(admission_decision.admission_digest):
        gate_rejections.append("backtest_replay_bridge:admission_digest_invalid")
    elif admission_decision.admission_digest != _expected_admission_digest(admission_decision):
        gate_rejections.append("backtest_replay_bridge:admission_digest_mismatch")

    if strategy_digest is None:
        gate_rejections.append("backtest_replay_bridge:strategy_spec_unresolvable")
    elif strategy_digest != admission_decision.strategy_digest:
        gate_rejections.append("backtest_replay_bridge:strategy_digest_mismatch")

    record_count = len(decision_ledger_records) if isinstance(decision_ledger_records, (tuple, list)) else 0
    if record_count < admission_decision.decision_record_count:
        gate_insufficient.append("backtest_replay_bridge:ledger_evidence_insufficient")

    if gate_rejections:
        return _assemble(
            status=BacktestReplayAdmissionStatus.REJECTED,
            admission_decision=admission_decision,
            strategy_digest=strategy_digest,
            replay_result=None,
            rejection_reasons=_sorted_unique(tuple(gate_rejections)),
            needs_research_reasons=(),
            correlation_id=correlation_id,
        )
    if gate_insufficient:
        return _assemble(
            status=BacktestReplayAdmissionStatus.INSUFFICIENT_EVIDENCE,
            admission_decision=admission_decision,
            strategy_digest=strategy_digest,
            replay_result=None,
            rejection_reasons=_sorted_unique(tuple(gate_insufficient)),
            needs_research_reasons=(),
            correlation_id=correlation_id,
        )

    replay_input = BacktestReplayAdmissionInput(
        strategy_spec=strategy_spec,
        leakage_bias_repaint_result=leakage_bias_repaint_result,
        pit_parity_result=pit_parity_result,
        decision_ledger_records=decision_ledger_records,
        replay_source_id=replay_source_id,
        historical_data_source_id=historical_data_source_id,
        replay_window=replay_window,
        admission_policy=admission_policy,
        evidence_digest_by_stage=evidence_digest_by_stage,
        metadata=metadata,
    )
    replay_result = evaluate_backtest_replay_admission(replay_input)

    return _assemble(
        status=replay_result.status,
        admission_decision=admission_decision,
        strategy_digest=strategy_digest,
        replay_result=replay_result,
        rejection_reasons=replay_result.rejection_reasons,
        needs_research_reasons=replay_result.needs_research_reasons,
        correlation_id=correlation_id,
    )


def _assemble(
    *,
    status: BacktestReplayAdmissionStatus,
    admission_decision: BacktestAdmissionDecision,
    strategy_digest: str | None,
    replay_result: BacktestReplayAdmissionResult | None,
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
    correlation_id: str,
) -> BacktestReplayBridgeResult:
    accepted = status is BacktestReplayAdmissionStatus.ACCEPTED
    replay_payload = backtest_replay_admission_to_dict(replay_result) if replay_result is not None else None
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "accepted": accepted,
        "admission_digest": admission_decision.admission_digest,
        "strategy_id": admission_decision.strategy_id or None,
        "strategy_digest": strategy_digest,
        "replay_admission_status": replay_result.status.value if replay_result is not None else None,
        "replay_admission_result": replay_payload,
        "rejection_reasons": list(rejection_reasons),
        "needs_research_reasons": list(needs_research_reasons),
        "correlation_id": correlation_id,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return BacktestReplayBridgeResult(
        schema_version=_SCHEMA_VERSION,
        status=status,
        accepted=accepted,
        admission_digest=admission_decision.admission_digest,
        strategy_id=admission_decision.strategy_id or None,
        strategy_digest=strategy_digest,
        replay_admission_status=replay_result.status.value if replay_result is not None else None,
        replay_admission_result=replay_result,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        bridge_digest=_canonical_digest(payload),
    )


def backtest_replay_bridge_result_to_dict(result: BacktestReplayBridgeResult) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a bridge result (embeds the delegated replay-admission result)."""
    return {
        "schema_version": result.schema_version,
        "status": result.status.value,
        "accepted": result.accepted,
        "admission_digest": result.admission_digest,
        "strategy_id": result.strategy_id,
        "strategy_digest": result.strategy_digest,
        "replay_admission_status": result.replay_admission_status,
        "replay_admission_result": (
            backtest_replay_admission_to_dict(result.replay_admission_result)
            if result.replay_admission_result is not None
            else None
        ),
        "rejection_reasons": list(result.rejection_reasons),
        "needs_research_reasons": list(result.needs_research_reasons),
        "correlation_id": result.correlation_id,
        "bridge_digest": result.bridge_digest,
        "paper_only": result.paper_only,
        "real_orders_enabled": result.real_orders_enabled,
        "real_money_enabled": result.real_money_enabled,
    }


__all__ = [
    "BacktestReplayBridgeError",
    "BacktestReplayBridgeResult",
    "backtest_replay_bridge_result_to_dict",
    "build_backtest_replay_bridge",
]
