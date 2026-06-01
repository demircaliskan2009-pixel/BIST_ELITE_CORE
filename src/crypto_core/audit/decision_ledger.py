"""Canonical decision ledger records for validation evidence traces."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from crypto_core.data.requirements import (
    DataRequirementValidationResult,
    data_requirement_registry_digest,
)
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest
from crypto_core.validation.leakage_bias_repaint import (
    LeakageBiasRepaintResult,
    LeakageBiasRepaintStatus,
    leakage_bias_repaint_result_to_dict,
)

_SCHEMA_VERSION = "1.0"

_BIST_LEAKAGE_TOKENS = (
    "bist",
    "bist30",
    "bist100",
    "borsa",
    "kap",
    "ideal",
    "i\u0307deal",
    "matriks",
)

_FORBIDDEN_SCOPE_TOKENS = (
    "live",
    "private_api",
    "credentials",
    "order_router",
    "scheduler",
    "auto_loop",
    "shadow_live_execution",
)

_FORBIDDEN_METADATA_TIMESTAMP_TOKENS = (
    "now",
    "wall_clock",
    "datetime.now",
    "utcnow",
)


class DecisionLedgerStage(str, Enum):
    STRATEGY_SPEC = "STRATEGY_SPEC"
    LEAKAGE_BIAS_REPAINT = "LEAKAGE_BIAS_REPAINT"
    PIT_PARITY = "PIT_PARITY"


class DecisionLedgerStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class DecisionEvidenceRef:
    source_type: str
    digest: str
    source_id: str | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DecisionLedgerRecord:
    schema_version: str
    stage: DecisionLedgerStage
    status: DecisionLedgerStatus
    strategy_id: str
    strategy_digest: str
    input_digest: str
    output_digest: str
    accepted: bool
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    evidence_refs: tuple[DecisionEvidenceRef, ...]
    correlation_id: str
    previous_record_digest: str | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DecisionLedgerValidationResult:
    accepted: bool
    record: DecisionLedgerRecord | None
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...] = ()


def build_strategy_spec_decision_record(
    strategy_spec: StrategySpec | None = None,
    *,
    input_digest: str,
    correlation_id: str,
    status: DecisionLedgerStatus | str | None = None,
    strategy_id: str | None = None,
    strategy_digest_: str | None = None,
    strategy_digest: str | None = None,
    output_digest: str | None = None,
    accepted: bool | None = None,
    rejection_reasons: Iterable[str] = (),
    needs_research_reasons: Iterable[str] = (),
    evidence_refs: Iterable[DecisionEvidenceRef | Mapping[str, Any]] = (),
    previous_record_digest: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    schema_version: str = _SCHEMA_VERSION,
) -> DecisionLedgerValidationResult:
    """Build a canonical StrategySpec ledger record without revalidating the spec."""
    resolved_strategy_id = strategy_id
    resolved_strategy_digest = strategy_digest or strategy_digest_
    if strategy_spec is not None:
        resolved_strategy_id = resolved_strategy_id or strategy_spec.strategy_id
        resolved_strategy_digest = resolved_strategy_digest or strategy_spec_digest(strategy_spec)

    stable_rejections = _stable_unique(rejection_reasons)
    stable_needs = _stable_unique(needs_research_reasons)
    resolved_status = _resolve_status(status, accepted, stable_rejections, stable_needs)
    resolved_accepted = accepted if accepted is not None else resolved_status is DecisionLedgerStatus.ACCEPTED
    resolved_output_digest = output_digest or resolved_strategy_digest or ""

    parsed_refs, ref_rejections = _parse_evidence_refs(evidence_refs)
    record = DecisionLedgerRecord(
        schema_version=schema_version,
        stage=DecisionLedgerStage.STRATEGY_SPEC,
        status=resolved_status,
        strategy_id=resolved_strategy_id or "",
        strategy_digest=resolved_strategy_digest or "",
        input_digest=input_digest,
        output_digest=resolved_output_digest,
        accepted=resolved_accepted,
        rejection_reasons=stable_rejections,
        needs_research_reasons=stable_needs,
        evidence_refs=parsed_refs,
        correlation_id=correlation_id,
        previous_record_digest=previous_record_digest,
        metadata=metadata,
    )
    return _merge_validation_rejections(validate_decision_ledger_record(record), ref_rejections)


def build_validation_decision_record(
    stage: DecisionLedgerStage | str,
    validation_result: LeakageBiasRepaintResult | DataRequirementValidationResult,
    *,
    strategy_id: str,
    strategy_digest: str,
    input_digest: str,
    correlation_id: str,
    output_digest: str | None = None,
    evidence_refs: Iterable[DecisionEvidenceRef | Mapping[str, Any]] = (),
    previous_record_digest: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    schema_version: str = _SCHEMA_VERSION,
) -> DecisionLedgerValidationResult:
    """Build a validation decision record from LBR or PIT parity result objects."""
    parsed_stage = _parse_stage(stage)
    output_payload, status, accepted, rejections, needs = _validation_result_facts(validation_result)
    stable_rejections = _stable_unique(rejections)
    stable_needs = _stable_unique(needs)
    parsed_refs, ref_rejections = _parse_evidence_refs(evidence_refs)

    record = DecisionLedgerRecord(
        schema_version=schema_version,
        stage=parsed_stage,
        status=status,
        strategy_id=strategy_id,
        strategy_digest=strategy_digest,
        input_digest=input_digest,
        output_digest=output_digest or _digest_payload(output_payload),
        accepted=accepted,
        rejection_reasons=stable_rejections,
        needs_research_reasons=stable_needs,
        evidence_refs=parsed_refs,
        correlation_id=correlation_id,
        previous_record_digest=previous_record_digest,
        metadata=metadata,
    )
    return _merge_validation_rejections(validate_decision_ledger_record(record), ref_rejections)


def validate_decision_ledger_record(
    payload_or_record: Mapping[str, Any] | DecisionLedgerRecord,
) -> DecisionLedgerValidationResult:
    """Validate a ledger record contract without executing runtime systems."""
    if isinstance(payload_or_record, DecisionLedgerRecord):
        record_result = DecisionLedgerValidationResult(True, payload_or_record, ())
    else:
        record_result = decision_ledger_record_from_dict(payload_or_record)
    if not record_result.accepted or record_result.record is None:
        return record_result

    record = record_result.record
    rejection_reasons: list[str] = []

    stage = _parse_stage_or_none(record.stage)
    status = _parse_status_or_none(record.status)
    if stage is None:
        rejection_reasons.append("decision_ledger:stage_unknown")
    if status is None:
        rejection_reasons.append("decision_ledger:status_unknown")

    for field_name in (
        "schema_version",
        "strategy_id",
        "strategy_digest",
        "input_digest",
        "output_digest",
        "correlation_id",
    ):
        if not _is_non_empty_string(getattr(record, field_name)):
            rejection_reasons.append(f"decision_ledger:{field_name}_missing")

    if not isinstance(record.accepted, bool):
        rejection_reasons.append("decision_ledger:accepted_malformed")

    if record.accepted and record.rejection_reasons:
        rejection_reasons.append("decision_ledger:accepted_with_rejection_reasons")
    if record.accepted and record.needs_research_reasons:
        rejection_reasons.append("decision_ledger:accepted_with_needs_research_reasons")

    if status is DecisionLedgerStatus.ACCEPTED and record.accepted is not True:
        rejection_reasons.append("decision_ledger:accepted_status_mismatch")
    if (
        status
        in {
            DecisionLedgerStatus.REJECTED,
            DecisionLedgerStatus.NEEDS_RESEARCH,
            DecisionLedgerStatus.INSUFFICIENT_EVIDENCE,
        }
        and record.accepted is not False
    ):
        rejection_reasons.append("decision_ledger:non_accepted_status_mismatch")

    if record.rejection_reasons != _stable_unique(record.rejection_reasons):
        rejection_reasons.append("decision_ledger:rejection_reasons_not_canonical")
    if record.needs_research_reasons != _stable_unique(record.needs_research_reasons):
        rejection_reasons.append("decision_ledger:needs_research_reasons_not_canonical")

    if stage in {DecisionLedgerStage.LEAKAGE_BIAS_REPAINT, DecisionLedgerStage.PIT_PARITY} and not record.evidence_refs:
        rejection_reasons.append("decision_ledger:evidence_refs_missing")

    rejection_reasons.extend(_validate_evidence_refs(record.evidence_refs))
    rejection_reasons.extend(_validate_metadata(record.metadata))
    rejection_reasons.extend(_scan_for_scope_violations(decision_ledger_record_to_dict(record)))

    stable_rejections = _stable_unique(rejection_reasons)
    if stable_rejections:
        return DecisionLedgerValidationResult(False, None, stable_rejections)
    return DecisionLedgerValidationResult(True, record, ())


def decision_ledger_record_to_dict(record: DecisionLedgerRecord) -> dict[str, Any]:
    return {
        "schema_version": record.schema_version,
        "stage": _enum_value(record.stage),
        "status": _enum_value(record.status),
        "strategy_id": record.strategy_id,
        "strategy_digest": record.strategy_digest,
        "input_digest": record.input_digest,
        "output_digest": record.output_digest,
        "accepted": record.accepted,
        "rejection_reasons": list(record.rejection_reasons),
        "needs_research_reasons": list(record.needs_research_reasons),
        "evidence_refs": [_evidence_ref_to_dict(ref) for ref in record.evidence_refs],
        "correlation_id": record.correlation_id,
        "previous_record_digest": record.previous_record_digest,
        "metadata": _normalize_json_value(record.metadata or {}),
    }


def decision_ledger_record_from_dict(payload: Mapping[str, Any]) -> DecisionLedgerValidationResult:
    if not isinstance(payload, Mapping):
        return DecisionLedgerValidationResult(False, None, ("decision_ledger:payload_malformed",))

    rejection_reasons: list[str] = []
    stage = _parse_stage_or_none(payload.get("stage"))
    if stage is None:
        rejection_reasons.append("decision_ledger:stage_unknown")
        stage = DecisionLedgerStage.STRATEGY_SPEC

    status = _parse_status_or_none(payload.get("status"))
    if status is None:
        rejection_reasons.append("decision_ledger:status_unknown")
        status = DecisionLedgerStatus.REJECTED

    evidence_refs, evidence_ref_rejections = _parse_evidence_refs(payload.get("evidence_refs", ()))
    rejection_reasons.extend(evidence_ref_rejections)

    rejection_reasons.extend(_validate_metadata(payload.get("metadata")))

    record = DecisionLedgerRecord(
        schema_version=_string_or_empty(payload.get("schema_version")),
        stage=stage,
        status=status,
        strategy_id=_string_or_empty(payload.get("strategy_id")),
        strategy_digest=_string_or_empty(payload.get("strategy_digest")),
        input_digest=_string_or_empty(payload.get("input_digest")),
        output_digest=_string_or_empty(payload.get("output_digest")),
        accepted=payload.get("accepted") if isinstance(payload.get("accepted"), bool) else False,
        rejection_reasons=_stable_unique(_parse_reason_list(payload.get("rejection_reasons"))),
        needs_research_reasons=_stable_unique(_parse_reason_list(payload.get("needs_research_reasons"))),
        evidence_refs=evidence_refs,
        correlation_id=_string_or_empty(payload.get("correlation_id")),
        previous_record_digest=_optional_string(payload.get("previous_record_digest")),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {},
    )

    if "accepted" not in payload or not isinstance(payload.get("accepted"), bool):
        rejection_reasons.append("decision_ledger:accepted_malformed")

    stable_rejections = _stable_unique(rejection_reasons)
    if stable_rejections:
        return DecisionLedgerValidationResult(False, None, stable_rejections)
    return validate_decision_ledger_record(record)


def canonical_decision_ledger_json(record: DecisionLedgerRecord) -> str:
    validation = validate_decision_ledger_record(record)
    if not validation.accepted or validation.record is None:
        raise ValueError(";".join(validation.rejection_reasons))
    return _canonical_json(decision_ledger_record_to_dict(validation.record))


def decision_ledger_digest(record: DecisionLedgerRecord) -> str:
    canonical = canonical_decision_ledger_json(record)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validation_result_facts(
    validation_result: LeakageBiasRepaintResult | DataRequirementValidationResult,
) -> tuple[dict[str, Any], DecisionLedgerStatus, bool, tuple[str, ...], tuple[str, ...]]:
    if isinstance(validation_result, LeakageBiasRepaintResult):
        payload = leakage_bias_repaint_result_to_dict(validation_result)
        status = _lbr_status_to_decision_status(validation_result.status)
        return (
            payload,
            status,
            validation_result.accepted,
            validation_result.rejection_reasons,
            validation_result.needs_research_reasons,
        )

    if isinstance(validation_result, DataRequirementValidationResult):
        registry_digest = (
            data_requirement_registry_digest(validation_result.registry)
            if validation_result.registry is not None
            else None
        )
        payload = {
            "accepted": validation_result.accepted,
            "registry_digest": registry_digest,
            "rejection_reasons": list(validation_result.rejection_reasons),
            "needs_research_reasons": list(validation_result.needs_research_reasons),
        }
        return (
            payload,
            _data_requirement_status_to_decision_status(validation_result),
            validation_result.accepted,
            validation_result.rejection_reasons,
            validation_result.needs_research_reasons,
        )

    payload = {"type": type(validation_result).__name__}
    return (
        payload,
        DecisionLedgerStatus.REJECTED,
        False,
        ("decision_ledger:validation_result_malformed",),
        (),
    )


def _lbr_status_to_decision_status(status: LeakageBiasRepaintStatus) -> DecisionLedgerStatus:
    if status is LeakageBiasRepaintStatus.PASS:
        return DecisionLedgerStatus.ACCEPTED
    if status is LeakageBiasRepaintStatus.NEEDS_RESEARCH:
        return DecisionLedgerStatus.NEEDS_RESEARCH
    if status is LeakageBiasRepaintStatus.INSUFFICIENT_EVIDENCE:
        return DecisionLedgerStatus.INSUFFICIENT_EVIDENCE
    return DecisionLedgerStatus.REJECTED


def _data_requirement_status_to_decision_status(result: DataRequirementValidationResult) -> DecisionLedgerStatus:
    if result.accepted:
        return DecisionLedgerStatus.ACCEPTED
    if result.needs_research_reasons:
        return DecisionLedgerStatus.NEEDS_RESEARCH
    if result.rejection_reasons:
        return DecisionLedgerStatus.REJECTED
    return DecisionLedgerStatus.INSUFFICIENT_EVIDENCE


def _resolve_status(
    status: DecisionLedgerStatus | str | None,
    accepted: bool | None,
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
) -> DecisionLedgerStatus:
    parsed = _parse_status_or_none(status)
    if parsed is not None:
        return parsed
    if accepted is True:
        return DecisionLedgerStatus.ACCEPTED
    if rejection_reasons:
        return DecisionLedgerStatus.REJECTED
    if needs_research_reasons:
        return DecisionLedgerStatus.NEEDS_RESEARCH
    if accepted is False:
        return DecisionLedgerStatus.INSUFFICIENT_EVIDENCE
    return DecisionLedgerStatus.ACCEPTED


def _parse_stage(stage: DecisionLedgerStage | str) -> DecisionLedgerStage:
    parsed = _parse_stage_or_none(stage)
    return parsed or DecisionLedgerStage.STRATEGY_SPEC


def _parse_stage_or_none(stage: object) -> DecisionLedgerStage | None:
    if isinstance(stage, DecisionLedgerStage):
        return stage
    if isinstance(stage, str):
        try:
            return DecisionLedgerStage(stage)
        except ValueError:
            return None
    return None


def _parse_status_or_none(status: object) -> DecisionLedgerStatus | None:
    if isinstance(status, DecisionLedgerStatus):
        return status
    if isinstance(status, str):
        try:
            return DecisionLedgerStatus(status)
        except ValueError:
            return None
    return None


def _parse_evidence_refs(
    evidence_refs: object,
) -> tuple[tuple[DecisionEvidenceRef, ...], tuple[str, ...]]:
    if evidence_refs is None:
        return (), ()
    if not isinstance(evidence_refs, Iterable) or isinstance(evidence_refs, str | bytes | Mapping):
        return (), ("decision_ledger:evidence_refs_malformed",)

    parsed: list[DecisionEvidenceRef] = []
    rejection_reasons: list[str] = []
    for item in evidence_refs:
        if isinstance(item, DecisionEvidenceRef):
            parsed.append(item)
            continue
        if not isinstance(item, Mapping):
            rejection_reasons.append("decision_ledger:evidence_ref_malformed")
            continue
        source_type = item.get("source_type")
        digest = item.get("digest")
        parsed.append(
            DecisionEvidenceRef(
                source_type=_string_or_empty(source_type),
                digest=_string_or_empty(digest),
                source_id=_optional_string(item.get("source_id")),
                metadata=item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {},
            )
        )
    return tuple(parsed), _stable_unique(rejection_reasons)


def _validate_evidence_refs(evidence_refs: tuple[DecisionEvidenceRef, ...]) -> tuple[str, ...]:
    rejection_reasons: list[str] = []
    if not isinstance(evidence_refs, tuple):
        return ("decision_ledger:evidence_refs_malformed",)
    for ref in evidence_refs:
        if not isinstance(ref, DecisionEvidenceRef):
            rejection_reasons.append("decision_ledger:evidence_ref_malformed")
            continue
        if not _is_non_empty_string(ref.source_type):
            rejection_reasons.append("decision_ledger:evidence_ref_source_type_missing")
        if not _is_non_empty_string(ref.digest):
            rejection_reasons.append("decision_ledger:evidence_ref_digest_missing")
        rejection_reasons.extend(_validate_metadata(ref.metadata))
    return _stable_unique(rejection_reasons)


def _evidence_ref_to_dict(ref: DecisionEvidenceRef) -> dict[str, Any]:
    return {
        "source_type": ref.source_type,
        "digest": ref.digest,
        "source_id": ref.source_id,
        "metadata": _normalize_json_value(ref.metadata or {}),
    }


def _validate_metadata(metadata: object) -> tuple[str, ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        return ("decision_ledger:metadata_malformed",)

    rejection_reasons: list[str] = []

    def _walk(node: object) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if not isinstance(key, str):
                    rejection_reasons.append("decision_ledger:metadata_key_malformed")
                    continue
                _consume_metadata_text(key)
                _walk(value)
        elif isinstance(node, list | tuple):
            for item in node:
                _walk(item)
        elif isinstance(node, str):
            _consume_metadata_text(node)
        elif node is None or isinstance(node, bool | int | float):
            return
        else:
            rejection_reasons.append("decision_ledger:metadata_value_malformed")

    def _consume_metadata_text(text: str) -> None:
        lowered = text.lower()
        if any(token in lowered for token in _FORBIDDEN_METADATA_TIMESTAMP_TOKENS):
            rejection_reasons.append("decision_ledger:metadata_runtime_timestamp_forbidden")

    _walk(metadata)
    return _stable_unique(rejection_reasons)


def _scan_for_scope_violations(payload: Mapping[str, Any]) -> tuple[str, ...]:
    rejection_reasons: list[str] = []
    seen_bist = False
    seen_forbidden = dict.fromkeys(_FORBIDDEN_SCOPE_TOKENS, False)

    def _consume(text: str) -> None:
        nonlocal seen_bist
        lowered = text.lower()
        if any(token in lowered for token in _BIST_LEAKAGE_TOKENS):
            seen_bist = True
        for token in _FORBIDDEN_SCOPE_TOKENS:
            if token in lowered:
                seen_forbidden[token] = True

    def _walk(node: object) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(key, str):
                    _consume(key)
                _walk(value)
        elif isinstance(node, list | tuple):
            for item in node:
                _walk(item)
        elif isinstance(node, str):
            _consume(node)

    _walk(payload)

    if seen_bist:
        rejection_reasons.append("decision_ledger:bist_scope_leakage")
    for token in _FORBIDDEN_SCOPE_TOKENS:
        if seen_forbidden[token]:
            rejection_reasons.append(f"decision_ledger:forbidden_field_{token}")
    return _stable_unique(rejection_reasons)


def _merge_validation_rejections(
    validation: DecisionLedgerValidationResult,
    extra_rejections: tuple[str, ...],
) -> DecisionLedgerValidationResult:
    if not extra_rejections:
        return validation
    return DecisionLedgerValidationResult(
        accepted=False,
        record=None,
        rejection_reasons=_stable_unique(validation.rejection_reasons + extra_rejections),
    )


def _parse_reason_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _stable_unique(reasons: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _string_or_empty(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return ""
    return value.strip()


def _enum_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    return value


def _normalize_json_value(value: object) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_json_value(val) for key, val in value.items()}
    if isinstance(value, tuple | list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, str | bool | int | float):
        return value
    return str(value)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_normalize_json_value(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest_payload(payload: Mapping[str, Any]) -> str:
    canonical = _canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "DecisionEvidenceRef",
    "DecisionLedgerRecord",
    "DecisionLedgerStage",
    "DecisionLedgerStatus",
    "DecisionLedgerValidationResult",
    "build_strategy_spec_decision_record",
    "build_validation_decision_record",
    "canonical_decision_ledger_json",
    "decision_ledger_digest",
    "decision_ledger_record_from_dict",
    "decision_ledger_record_to_dict",
    "validate_decision_ledger_record",
]
