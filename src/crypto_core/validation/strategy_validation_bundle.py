"""Strategy validation bundle — deterministic paper-only validation pipeline consumer.

A single, deterministic, fail-closed consumer that runs an existing StrategySpec through the existing
data-requirement / PIT-parity and leakage/bias/repaint gates and collapses the outcome — together with
the existing DecisionLedger record builders and optional SourcePacket provenance — into one auditable
bundle. It *derives*, never mirrors: it reimplements no spec/registry/PIT/leakage/ledger logic and adds
no runtime/orchestrator/persistence/live path.

Design rules:
  - Consume, don't duplicate: StrategySpec via ``validate_strategy_spec``, PIT via
    ``validate_strategy_data_requirements``, leakage via ``evaluate_leakage_bias_repaint``, evidence via
    the DecisionLedger builders. No contract is re-authored.
  - Safe coercion only: ``strategy_spec``/``registry`` accept a mapping because their validators safely
    validate mappings; ``leakage_input``/``source_packet`` must be the typed objects — reconstructing
    their nested timestamp / rights proof from a loose mapping would fabricate PIT/leakage evidence.
  - Fail closed: a wrong-typed input or an invalid correlation id / previous-record digest raises
    ``StrategyValidationBundleError``; a validation outcome (invalid spec, PIT/leakage rejection,
    not-usable source packet, missing leakage proof) yields a deterministic non-ACCEPTED bundle.
  - Terminal precedence: any hard rejection → REJECTED; else missing/insufficient leakage proof →
    INSUFFICIENT_EVIDENCE; else any needs-research → NEEDS_RESEARCH; else (spec valid + PIT accepted +
    leakage PASS + source usable/absent) → ACCEPTED. ``accepted`` is true only for ACCEPTED.
  - Deterministic: ledger digests and the bundle digest are canonical SHA-256; no wall-clock/random/IO.
  - PAPER ONLY: no order intent, live route, venue execution, scheduler, persistence, or execution field.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from crypto_core.audit.decision_ledger import (
    DecisionEvidenceRef,
    DecisionLedgerStage,
    DecisionLedgerStatus,
    DecisionLedgerValidationResult,
    build_strategy_spec_decision_record,
    build_validation_decision_record,
    decision_ledger_digest,
)
from crypto_core.data.requirements import (
    DataRequirementRegistry,
    DataRequirementValidationResult,
    data_requirement_registry_digest,
    default_perp_data_requirement_registry,
)
from crypto_core.strategy.source_packet import SourcePacket, source_packet_to_dict
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.leakage_bias_repaint import (
    LeakageBiasRepaintInput,
    LeakageBiasRepaintResult,
    LeakageBiasRepaintStatus,
    evaluate_leakage_bias_repaint,
)
from crypto_core.validation.pit_parity import validate_strategy_data_requirements

_SCHEMA_VERSION = "strategy-validation-bundle.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

_SOURCE_PACKET_NOT_USABLE = "strategy_validation_bundle:source_packet_not_usable"
_SOURCE_PACKET_DIGEST_MISMATCH = "strategy_validation_bundle:source_packet_digest_mismatch"
_LEAKAGE_STRATEGY_MISMATCH = "strategy_validation_bundle:leakage_strategy_mismatch"


class StrategyValidationBundleError(RuntimeError):
    """Raised when bundle inputs are malformed at the call level (wrong type / bad id or digest)."""


class StrategyValidationBundleStatus(str, Enum):
    """Terminal verdict of the strategy validation pipeline. Never an order/live action."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class StrategyValidationBundle:
    """Deterministic, immutable summary of a StrategySpec run through the validation gates. PAPER ONLY."""

    schema_version: str
    status: StrategyValidationBundleStatus
    accepted: bool
    strategy_id: str
    strategy_digest: str
    source_packet_digest: str | None
    data_registry_digest: str | None
    pit_status: str
    pit_rejection_reasons: tuple[str, ...]
    pit_needs_research_reasons: tuple[str, ...]
    leakage_status: str
    leakage_rejection_reasons: tuple[str, ...]
    leakage_needs_research_reasons: tuple[str, ...]
    decision_record_digests: tuple[str, ...]
    terminal_rejection_reasons: tuple[str, ...]
    terminal_needs_research_reasons: tuple[str, ...]
    correlation_id: str
    bundle_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _pit_status(result: DataRequirementValidationResult) -> StrategyValidationBundleStatus:
    if result.accepted:
        return StrategyValidationBundleStatus.ACCEPTED
    if result.needs_research_reasons:
        return StrategyValidationBundleStatus.NEEDS_RESEARCH
    if result.rejection_reasons:
        return StrategyValidationBundleStatus.REJECTED
    return StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE


def _resolve_spec(strategy_spec: object) -> tuple[StrategySpec | None, tuple[str, ...], tuple[str, ...]]:
    if isinstance(strategy_spec, StrategySpec):
        return strategy_spec, (), ()
    if isinstance(strategy_spec, Mapping):
        result = validate_strategy_spec(strategy_spec)
        if result.accepted and result.spec is not None:
            return result.spec, (), ()
        return None, tuple(result.rejection_reasons), tuple(result.needs_research_reasons)
    raise StrategyValidationBundleError("strategy_validation_bundle:strategy_spec_malformed")


def _expected_source_packet_digest(source_packet: SourcePacket) -> str | None:
    try:
        payload = source_packet_to_dict(source_packet)
    except Exception:
        return None
    payload.pop("packet_digest", None)
    return _canonical_digest(payload)


def _resolve_source_packet(source_packet: object) -> tuple[str | None, tuple[str, ...]]:
    if source_packet is None:
        return None, ()
    if isinstance(source_packet, SourcePacket):
        expected_digest = _expected_source_packet_digest(source_packet)
        if not _is_sha256_hex(source_packet.packet_digest) or expected_digest != source_packet.packet_digest:
            return None, (_SOURCE_PACKET_DIGEST_MISMATCH,)
        if source_packet.usable_for_compilation:
            return source_packet.packet_digest, ()
        return source_packet.packet_digest, (_SOURCE_PACKET_NOT_USABLE,)
    raise StrategyValidationBundleError("strategy_validation_bundle:source_packet_malformed")


def _resolve_leakage(leakage_input: object) -> LeakageBiasRepaintResult | None:
    if leakage_input is None:
        return None
    if isinstance(leakage_input, LeakageBiasRepaintInput):
        return evaluate_leakage_bias_repaint(leakage_input)
    raise StrategyValidationBundleError("strategy_validation_bundle:leakage_input_malformed")


def _spec_digest_or_none(spec_or_mapping: object) -> str | None:
    """Resolve a leakage input's strategy to its canonical digest without raising (None if unresolvable)."""
    if isinstance(spec_or_mapping, StrategySpec):
        return strategy_spec_digest(spec_or_mapping)
    if isinstance(spec_or_mapping, Mapping):
        result = validate_strategy_spec(spec_or_mapping)
        if result.accepted and result.spec is not None:
            return strategy_spec_digest(result.spec)
    return None


def _append_record(
    result: DecisionLedgerValidationResult,
    digests: list[str],
    last_digest: str | None,
) -> str | None:
    if result.accepted and result.record is not None:
        digest = decision_ledger_digest(result.record)
        digests.append(digest)
        return digest
    return last_digest


def _build_ledger_chain(
    spec: StrategySpec,
    *,
    strategy_id: str,
    strategy_digest: str,
    source_packet_digest: str | None,
    data_registry_digest: str | None,
    pit_result: DataRequirementValidationResult,
    leakage_result: LeakageBiasRepaintResult | None,
    correlation_id: str,
    previous_record_digest: str | None,
) -> tuple[str, ...]:
    """Build the STRATEGY_SPEC → PIT_PARITY → LEAKAGE chain best-effort; collect digests of valid records.

    A record whose reasons carry a forbidden/BIST token fails ledger validation by design; such a record
    is skipped (its digest is absent) while the bundle still reports the rejection from the gate results.
    """
    digests: list[str] = []
    last = previous_record_digest

    spec_evidence: tuple[DecisionEvidenceRef, ...] = ()
    if source_packet_digest:
        spec_evidence = (DecisionEvidenceRef(source_type="source_packet", digest=source_packet_digest),)
    spec_record = build_strategy_spec_decision_record(
        spec,
        input_digest=source_packet_digest or strategy_digest,
        correlation_id=correlation_id,
        status=DecisionLedgerStatus.ACCEPTED,
        accepted=True,
        evidence_refs=spec_evidence,
        previous_record_digest=last,
    )
    last = _append_record(spec_record, digests, last)

    pit_evidence = [DecisionEvidenceRef(source_type="strategy_spec", digest=strategy_digest)]
    if data_registry_digest:
        pit_evidence.append(DecisionEvidenceRef(source_type="data_requirement_registry", digest=data_registry_digest))
    pit_record = build_validation_decision_record(
        DecisionLedgerStage.PIT_PARITY,
        pit_result,
        strategy_id=strategy_id,
        strategy_digest=strategy_digest,
        input_digest=strategy_digest,
        correlation_id=correlation_id,
        evidence_refs=tuple(pit_evidence),
        previous_record_digest=last,
    )
    last = _append_record(pit_record, digests, last)

    if leakage_result is not None:
        leakage_record = build_validation_decision_record(
            DecisionLedgerStage.LEAKAGE_BIAS_REPAINT,
            leakage_result,
            strategy_id=strategy_id,
            strategy_digest=strategy_digest,
            input_digest=strategy_digest,
            correlation_id=correlation_id,
            evidence_refs=(DecisionEvidenceRef(source_type="strategy_spec", digest=strategy_digest),),
            previous_record_digest=last,
        )
        _append_record(leakage_record, digests, last)

    return tuple(digests)


def build_strategy_validation_bundle(
    strategy_spec: StrategySpec | Mapping[str, Any],
    *,
    registry: DataRequirementRegistry | Mapping[str, Any] | None = None,
    leakage_input: LeakageBiasRepaintInput | None = None,
    source_packet: SourcePacket | None = None,
    correlation_id: str,
    previous_record_digest: str | None = None,
) -> StrategyValidationBundle:
    """Run a StrategySpec through the PIT and leakage gates and collapse the result into one bundle.

    ``strategy_spec`` and ``registry`` may be the typed object or a mapping (their validators handle
    mappings safely); ``leakage_input`` and ``source_packet`` must be the typed objects. A wrong-typed
    input or an invalid ``correlation_id`` / ``previous_record_digest`` raises
    ``StrategyValidationBundleError``; every validation outcome yields a deterministic, immutable bundle.
    No live/order/scheduler/runtime/persistence path is produced.
    """
    if not _is_non_empty_string(correlation_id):
        raise StrategyValidationBundleError("strategy_validation_bundle:correlation_id_invalid")
    if previous_record_digest is not None and not _is_sha256_hex(previous_record_digest):
        raise StrategyValidationBundleError("strategy_validation_bundle:previous_record_digest_invalid")

    source_packet_digest, source_blockers = _resolve_source_packet(source_packet)
    spec, spec_rejections, spec_needs = _resolve_spec(strategy_spec)

    if spec is None:
        hard = _sorted_unique(spec_rejections + source_blockers)
        needs = _sorted_unique(spec_needs)
        if hard:
            status = StrategyValidationBundleStatus.REJECTED
        elif needs:
            status = StrategyValidationBundleStatus.NEEDS_RESEARCH
        else:
            status = StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE
        return _assemble(
            status=status,
            strategy_id="",
            strategy_digest="",
            source_packet_digest=source_packet_digest,
            data_registry_digest=None,
            pit_status=StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE.value,
            pit_rejection_reasons=(),
            pit_needs_research_reasons=(),
            leakage_status=StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE.value,
            leakage_rejection_reasons=(),
            leakage_needs_research_reasons=(),
            decision_record_digests=(),
            terminal_rejection_reasons=hard,
            terminal_needs_research_reasons=needs,
            correlation_id=correlation_id,
        )

    strategy_id = spec.strategy_id
    strategy_digest = strategy_spec_digest(spec)

    active_registry = registry if registry is not None else default_perp_data_requirement_registry()
    pit_result = validate_strategy_data_requirements(spec, active_registry)
    data_registry_digest = (
        data_requirement_registry_digest(pit_result.registry) if pit_result.registry is not None else None
    )

    leakage_result = _resolve_leakage(leakage_input)
    leakage_present = leakage_result is not None

    # Fail closed on cross-strategy evidence: a leakage proof built for a different StrategySpec must not
    # certify this one. The mismatch is a hard rejection and the foreign proof never enters the ledger chain.
    leakage_mismatch: tuple[str, ...] = ()
    if leakage_present:
        leakage_strategy_digest = _spec_digest_or_none(leakage_input.strategy_spec)
        if leakage_strategy_digest is not None and leakage_strategy_digest != strategy_digest:
            leakage_mismatch = (_LEAKAGE_STRATEGY_MISMATCH,)

    decision_record_digests = _build_ledger_chain(
        spec,
        strategy_id=strategy_id,
        strategy_digest=strategy_digest,
        source_packet_digest=source_packet_digest,
        data_registry_digest=data_registry_digest,
        pit_result=pit_result,
        leakage_result=None if leakage_mismatch else leakage_result,
        correlation_id=correlation_id,
        previous_record_digest=previous_record_digest,
    )

    leakage_rejections = leakage_result.rejection_reasons if leakage_present else ()
    leakage_needs = leakage_result.needs_research_reasons if leakage_present else ()
    leakage_status = (
        leakage_result.status.value if leakage_present else StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE.value
    )

    hard = _sorted_unique(pit_result.rejection_reasons + leakage_rejections + source_blockers + leakage_mismatch)
    needs = _sorted_unique(pit_result.needs_research_reasons + leakage_needs)
    insufficient = (not leakage_present) or leakage_result.status is LeakageBiasRepaintStatus.INSUFFICIENT_EVIDENCE

    if hard:
        status = StrategyValidationBundleStatus.REJECTED
    elif insufficient:
        status = StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE
    elif needs:
        status = StrategyValidationBundleStatus.NEEDS_RESEARCH
    elif pit_result.accepted and leakage_present and leakage_result.status is LeakageBiasRepaintStatus.PASS:
        status = StrategyValidationBundleStatus.ACCEPTED
    else:
        status = StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE

    return _assemble(
        status=status,
        strategy_id=strategy_id,
        strategy_digest=strategy_digest,
        source_packet_digest=source_packet_digest,
        data_registry_digest=data_registry_digest,
        pit_status=_pit_status(pit_result).value,
        pit_rejection_reasons=pit_result.rejection_reasons,
        pit_needs_research_reasons=pit_result.needs_research_reasons,
        leakage_status=leakage_status,
        leakage_rejection_reasons=leakage_rejections,
        leakage_needs_research_reasons=leakage_needs,
        decision_record_digests=decision_record_digests,
        terminal_rejection_reasons=hard,
        terminal_needs_research_reasons=needs,
        correlation_id=correlation_id,
    )


def _assemble(
    *,
    status: StrategyValidationBundleStatus,
    strategy_id: str,
    strategy_digest: str,
    source_packet_digest: str | None,
    data_registry_digest: str | None,
    pit_status: str,
    pit_rejection_reasons: tuple[str, ...],
    pit_needs_research_reasons: tuple[str, ...],
    leakage_status: str,
    leakage_rejection_reasons: tuple[str, ...],
    leakage_needs_research_reasons: tuple[str, ...],
    decision_record_digests: tuple[str, ...],
    terminal_rejection_reasons: tuple[str, ...],
    terminal_needs_research_reasons: tuple[str, ...],
    correlation_id: str,
) -> StrategyValidationBundle:
    accepted = status is StrategyValidationBundleStatus.ACCEPTED
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "accepted": accepted,
        "strategy_id": strategy_id,
        "strategy_digest": strategy_digest,
        "source_packet_digest": source_packet_digest,
        "data_registry_digest": data_registry_digest,
        "pit_status": pit_status,
        "pit_rejection_reasons": list(pit_rejection_reasons),
        "pit_needs_research_reasons": list(pit_needs_research_reasons),
        "leakage_status": leakage_status,
        "leakage_rejection_reasons": list(leakage_rejection_reasons),
        "leakage_needs_research_reasons": list(leakage_needs_research_reasons),
        "decision_record_digests": list(decision_record_digests),
        "terminal_rejection_reasons": list(terminal_rejection_reasons),
        "terminal_needs_research_reasons": list(terminal_needs_research_reasons),
        "correlation_id": correlation_id,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return StrategyValidationBundle(
        schema_version=_SCHEMA_VERSION,
        status=status,
        accepted=accepted,
        strategy_id=strategy_id,
        strategy_digest=strategy_digest,
        source_packet_digest=source_packet_digest,
        data_registry_digest=data_registry_digest,
        pit_status=pit_status,
        pit_rejection_reasons=pit_rejection_reasons,
        pit_needs_research_reasons=pit_needs_research_reasons,
        leakage_status=leakage_status,
        leakage_rejection_reasons=leakage_rejection_reasons,
        leakage_needs_research_reasons=leakage_needs_research_reasons,
        decision_record_digests=decision_record_digests,
        terminal_rejection_reasons=terminal_rejection_reasons,
        terminal_needs_research_reasons=terminal_needs_research_reasons,
        correlation_id=correlation_id,
        bundle_digest=_canonical_digest(payload),
    )


def strategy_validation_bundle_to_dict(bundle: StrategyValidationBundle) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a strategy validation bundle (deterministic shape)."""
    return {
        "schema_version": bundle.schema_version,
        "status": bundle.status.value,
        "accepted": bundle.accepted,
        "strategy_id": bundle.strategy_id,
        "strategy_digest": bundle.strategy_digest,
        "source_packet_digest": bundle.source_packet_digest,
        "data_registry_digest": bundle.data_registry_digest,
        "pit_status": bundle.pit_status,
        "pit_rejection_reasons": list(bundle.pit_rejection_reasons),
        "pit_needs_research_reasons": list(bundle.pit_needs_research_reasons),
        "leakage_status": bundle.leakage_status,
        "leakage_rejection_reasons": list(bundle.leakage_rejection_reasons),
        "leakage_needs_research_reasons": list(bundle.leakage_needs_research_reasons),
        "decision_record_digests": list(bundle.decision_record_digests),
        "terminal_rejection_reasons": list(bundle.terminal_rejection_reasons),
        "terminal_needs_research_reasons": list(bundle.terminal_needs_research_reasons),
        "correlation_id": bundle.correlation_id,
        "bundle_digest": bundle.bundle_digest,
        "paper_only": bundle.paper_only,
        "real_orders_enabled": bundle.real_orders_enabled,
        "real_money_enabled": bundle.real_money_enabled,
    }


__all__ = [
    "StrategyValidationBundle",
    "StrategyValidationBundleError",
    "StrategyValidationBundleStatus",
    "build_strategy_validation_bundle",
    "strategy_validation_bundle_to_dict",
]
