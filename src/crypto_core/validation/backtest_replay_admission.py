"""Deterministic Backtest/Replay admission gate for StrategySpec contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from crypto_core.data.requirements import DataRequirementValidationResult
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.leakage_bias_repaint import (
    LeakageBiasRepaintResult,
    LeakageBiasRepaintStatus,
    leakage_bias_repaint_result_from_dict,
)

if TYPE_CHECKING:
    from crypto_core.audit.decision_ledger import DecisionLedgerRecord, DecisionLedgerStage


class BacktestReplayAdmissionStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class BacktestReplayWindow:
    start_ns: int
    end_ns: int


@dataclass(frozen=True)
class BacktestReplayAdmissionPolicy:
    event_time_ns_policy: str
    available_at_ns_policy: str
    finalized_at_ns_policy: str
    fee_assumption: str
    slippage_assumption: str
    funding_assumption: str
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BacktestReplayAdmissionInput:
    strategy_spec: StrategySpec | Mapping[str, Any]
    leakage_bias_repaint_result: LeakageBiasRepaintResult | Mapping[str, Any]
    pit_parity_result: DataRequirementValidationResult
    decision_ledger_records: (
        tuple[DecisionLedgerRecord | Mapping[str, Any], ...] | list[DecisionLedgerRecord | Mapping[str, Any]]
    )
    replay_source_id: str
    historical_data_source_id: str
    replay_window: BacktestReplayWindow
    admission_policy: BacktestReplayAdmissionPolicy
    evidence_digest_by_stage: Mapping[DecisionLedgerStage | str, str] | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BacktestReplayAdmissionResult:
    accepted: bool
    status: BacktestReplayAdmissionStatus
    strategy_id: str | None
    strategy_digest: str | None
    replay_source_id: str | None
    historical_data_source_id: str | None
    replay_window: BacktestReplayWindow | None
    decision_ledger_digests: Mapping[str, str]
    evidence_digest_by_stage: Mapping[str, str]
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        expected_accepted = (
            self.status is BacktestReplayAdmissionStatus.ACCEPTED
            and self.rejection_reasons == ()
            and self.needs_research_reasons == ()
        )
        if self.accepted != expected_accepted:
            raise ValueError("accepted must be true only for ACCEPTED with empty reason tuples")


_REQUIRED_LEDGER_STAGE_VALUES = ("STRATEGY_SPEC", "LEAKAGE_BIAS_REPAINT", "PIT_PARITY")

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

_FORBIDDEN_TIMESTAMP_TOKENS = (
    "wall_clock",
    "datetime.now",
    "utcnow",
)


def evaluate_backtest_replay_admission(
    input_: BacktestReplayAdmissionInput,
) -> BacktestReplayAdmissionResult:
    if not isinstance(input_, BacktestReplayAdmissionInput):
        return _result(
            status=BacktestReplayAdmissionStatus.REJECTED,
            rejection_reasons=("backtest_replay_admission:input_malformed",),
        )

    rejection_reasons: list[str] = []
    needs_research_reasons: list[str] = []
    insufficient_evidence_reasons: list[str] = []

    spec, spec_digest, spec_rejections, spec_needs = _resolve_strategy_spec(input_.strategy_spec)
    rejection_reasons.extend(spec_rejections)
    needs_research_reasons.extend(spec_needs)

    lbr_result, lbr_rejections = _resolve_lbr_result(input_.leakage_bias_repaint_result)
    rejection_reasons.extend(lbr_rejections)
    if lbr_result is not None:
        _validate_lbr_result(lbr_result, rejection_reasons, needs_research_reasons, insufficient_evidence_reasons)

    _validate_pit_parity_result(
        input_.pit_parity_result,
        rejection_reasons,
        needs_research_reasons,
        insufficient_evidence_reasons,
    )

    _validate_replay_metadata(input_, rejection_reasons)
    _validate_window(input_.replay_window, rejection_reasons)
    _validate_policy(input_.admission_policy, rejection_reasons)
    _scan_scope(input_.metadata, rejection_reasons, prefix="backtest_replay_admission")
    _scan_scope(input_.evidence_digest_by_stage, rejection_reasons, prefix="backtest_replay_admission")

    ledger_by_stage, ledger_digests = _resolve_decision_ledger_records(
        input_.decision_ledger_records,
        strategy_digest_=spec_digest,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        insufficient_evidence_reasons=insufficient_evidence_reasons,
    )
    evidence_digest_by_stage = _validate_evidence_digest_by_stage(
        input_.evidence_digest_by_stage,
        ledger_by_stage,
        rejection_reasons,
    )

    stable_rejections = _stable_unique(rejection_reasons)
    stable_needs = _stable_unique(needs_research_reasons)
    stable_insufficient = _stable_unique(insufficient_evidence_reasons)

    if stable_rejections:
        status = BacktestReplayAdmissionStatus.REJECTED
    elif stable_needs:
        status = BacktestReplayAdmissionStatus.NEEDS_RESEARCH
    elif stable_insufficient:
        status = BacktestReplayAdmissionStatus.INSUFFICIENT_EVIDENCE
        stable_rejections = stable_insufficient
    else:
        status = BacktestReplayAdmissionStatus.ACCEPTED

    return _result(
        status=status,
        strategy_id=spec.strategy_id if spec is not None else None,
        strategy_digest_=spec_digest,
        replay_source_id=input_.replay_source_id if isinstance(input_.replay_source_id, str) else None,
        historical_data_source_id=(
            input_.historical_data_source_id if isinstance(input_.historical_data_source_id, str) else None
        ),
        replay_window=input_.replay_window if isinstance(input_.replay_window, BacktestReplayWindow) else None,
        decision_ledger_digests=ledger_digests,
        evidence_digest_by_stage=evidence_digest_by_stage,
        rejection_reasons=stable_rejections,
        needs_research_reasons=stable_needs,
    )


def backtest_replay_admission_to_dict(result: BacktestReplayAdmissionResult) -> dict[str, Any]:
    return {
        "accepted": result.accepted,
        "status": result.status.value,
        "strategy_id": result.strategy_id,
        "strategy_digest": result.strategy_digest,
        "replay_source_id": result.replay_source_id,
        "historical_data_source_id": result.historical_data_source_id,
        "replay_window": _window_to_dict(result.replay_window),
        "decision_ledger_digests": dict(sorted(result.decision_ledger_digests.items())),
        "evidence_digest_by_stage": dict(sorted(result.evidence_digest_by_stage.items())),
        "rejection_reasons": list(result.rejection_reasons),
        "needs_research_reasons": list(result.needs_research_reasons),
    }


def backtest_replay_admission_from_dict(payload: Mapping[str, Any]) -> BacktestReplayAdmissionResult:
    if not isinstance(payload, Mapping):
        return _result(
            status=BacktestReplayAdmissionStatus.REJECTED,
            rejection_reasons=("backtest_replay_admission:payload_malformed",),
        )

    rejection_reasons: list[str] = []
    status = _parse_status(payload.get("status"))
    if status is None:
        rejection_reasons.append("backtest_replay_admission:status_unknown")
        status = BacktestReplayAdmissionStatus.REJECTED

    accepted = payload.get("accepted")
    if not isinstance(accepted, bool):
        rejection_reasons.append("backtest_replay_admission:accepted_malformed")

    result_rejections = _reason_tuple(payload.get("rejection_reasons"))
    result_needs = _reason_tuple(payload.get("needs_research_reasons"))
    if payload.get("rejection_reasons") is not None and result_rejections is None:
        rejection_reasons.append("backtest_replay_admission:rejection_reasons_malformed")
        result_rejections = ()
    if payload.get("needs_research_reasons") is not None and result_needs is None:
        rejection_reasons.append("backtest_replay_admission:needs_research_reasons_malformed")
        result_needs = ()

    replay_window = _window_from_payload(payload.get("replay_window"), rejection_reasons)
    decision_ledger_digests = _digest_mapping(payload.get("decision_ledger_digests"), rejection_reasons)
    evidence_digest_by_stage = _digest_mapping(payload.get("evidence_digest_by_stage"), rejection_reasons)

    combined_rejections = _stable_unique((*rejection_reasons, *(result_rejections or ())))
    status = status if not rejection_reasons else BacktestReplayAdmissionStatus.REJECTED
    if accepted is True and status is BacktestReplayAdmissionStatus.ACCEPTED and combined_rejections:
        status = BacktestReplayAdmissionStatus.REJECTED

    return _result(
        status=status,
        strategy_id=_optional_string(payload.get("strategy_id")),
        strategy_digest_=_optional_string(payload.get("strategy_digest")),
        replay_source_id=_optional_string(payload.get("replay_source_id")),
        historical_data_source_id=_optional_string(payload.get("historical_data_source_id")),
        replay_window=replay_window,
        decision_ledger_digests=decision_ledger_digests,
        evidence_digest_by_stage=evidence_digest_by_stage,
        rejection_reasons=combined_rejections,
        needs_research_reasons=_stable_unique(result_needs or ()),
    )


def canonical_backtest_replay_admission_json(result: BacktestReplayAdmissionResult) -> str:
    return json.dumps(
        _normalize_json_value(backtest_replay_admission_to_dict(result)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def backtest_replay_admission_digest(result: BacktestReplayAdmissionResult) -> str:
    canonical = canonical_backtest_replay_admission_json(result)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_strategy_spec(
    spec_or_mapping: StrategySpec | Mapping[str, Any],
) -> tuple[StrategySpec | None, str | None, tuple[str, ...], tuple[str, ...]]:
    if isinstance(spec_or_mapping, StrategySpec):
        return spec_or_mapping, strategy_spec_digest(spec_or_mapping), (), ()

    if not isinstance(spec_or_mapping, Mapping):
        return None, None, ("backtest_replay_admission:strategy_spec:payload_malformed",), ()

    validation = validate_strategy_spec(spec_or_mapping)
    if validation.accepted and validation.spec is not None:
        return validation.spec, strategy_spec_digest(validation.spec), (), ()

    rejections = tuple(f"backtest_replay_admission:strategy_spec:{reason}" for reason in validation.rejection_reasons)
    needs = tuple(f"backtest_replay_admission:strategy_spec:{reason}" for reason in validation.needs_research_reasons)
    return None, None, _stable_unique(rejections), _stable_unique(needs)


def _resolve_lbr_result(
    result_or_mapping: LeakageBiasRepaintResult | Mapping[str, Any],
) -> tuple[LeakageBiasRepaintResult | None, tuple[str, ...]]:
    if isinstance(result_or_mapping, LeakageBiasRepaintResult):
        return result_or_mapping, ()
    if not isinstance(result_or_mapping, Mapping):
        return None, ("backtest_replay_admission:lbr_result_malformed",)
    try:
        return leakage_bias_repaint_result_from_dict(result_or_mapping), ()
    except (TypeError, ValueError) as exc:
        return None, (f"backtest_replay_admission:lbr_result_malformed:{exc}",)


def _validate_lbr_result(
    lbr_result: LeakageBiasRepaintResult,
    rejection_reasons: list[str],
    needs_research_reasons: list[str],
    insufficient_evidence_reasons: list[str],
) -> None:
    if lbr_result.status is LeakageBiasRepaintStatus.NEEDS_RESEARCH:
        needs_research_reasons.extend(
            f"backtest_replay_admission:lbr:{reason}" for reason in lbr_result.needs_research_reasons
        )
        if not lbr_result.needs_research_reasons:
            needs_research_reasons.append("backtest_replay_admission:lbr_needs_research")
    elif lbr_result.status is LeakageBiasRepaintStatus.INSUFFICIENT_EVIDENCE:
        insufficient_evidence_reasons.extend(
            f"backtest_replay_admission:lbr:{reason}" for reason in lbr_result.rejection_reasons
        )
        if not lbr_result.rejection_reasons:
            insufficient_evidence_reasons.append("backtest_replay_admission:lbr_insufficient_evidence")
    elif lbr_result.status is not LeakageBiasRepaintStatus.PASS:
        rejection_reasons.append("backtest_replay_admission:lbr_status_not_pass")

    if lbr_result.accepted is not True:
        if lbr_result.status is LeakageBiasRepaintStatus.REJECT:
            rejection_reasons.append("backtest_replay_admission:lbr_not_accepted")
    if lbr_result.rejection_reasons and lbr_result.status is not LeakageBiasRepaintStatus.INSUFFICIENT_EVIDENCE:
        rejection_reasons.extend(f"backtest_replay_admission:lbr:{reason}" for reason in lbr_result.rejection_reasons)
    if lbr_result.needs_research_reasons:
        needs_research_reasons.extend(
            f"backtest_replay_admission:lbr:{reason}" for reason in lbr_result.needs_research_reasons
        )


def _validate_pit_parity_result(
    pit_result: DataRequirementValidationResult,
    rejection_reasons: list[str],
    needs_research_reasons: list[str],
    insufficient_evidence_reasons: list[str],
) -> None:
    if not isinstance(pit_result, DataRequirementValidationResult):
        rejection_reasons.append("backtest_replay_admission:pit_parity_result_malformed")
        return

    if pit_result.rejection_reasons:
        rejection_reasons.extend(
            f"backtest_replay_admission:pit_parity:{reason}" for reason in pit_result.rejection_reasons
        )
    if pit_result.needs_research_reasons:
        needs_research_reasons.extend(
            f"backtest_replay_admission:pit_parity:{reason}" for reason in pit_result.needs_research_reasons
        )
    if pit_result.accepted is not True and not pit_result.rejection_reasons and not pit_result.needs_research_reasons:
        insufficient_evidence_reasons.append("backtest_replay_admission:pit_parity_insufficient_evidence")
    if pit_result.accepted is True and pit_result.registry is None:
        rejection_reasons.append("backtest_replay_admission:pit_parity_registry_missing")


def _validate_replay_metadata(input_: BacktestReplayAdmissionInput, rejection_reasons: list[str]) -> None:
    if not _is_non_empty_string(input_.replay_source_id):
        rejection_reasons.append("backtest_replay_admission:replay_source_id_missing")
    if not _is_non_empty_string(input_.historical_data_source_id):
        rejection_reasons.append("backtest_replay_admission:historical_data_source_id_missing")
    _scan_scope({"replay_source_id": input_.replay_source_id}, rejection_reasons, prefix="backtest_replay_admission")
    _scan_scope(
        {"historical_data_source_id": input_.historical_data_source_id},
        rejection_reasons,
        prefix="backtest_replay_admission",
    )


def _validate_window(window: BacktestReplayWindow, rejection_reasons: list[str]) -> None:
    if not isinstance(window, BacktestReplayWindow):
        rejection_reasons.append("backtest_replay_admission:replay_window_malformed")
        return
    if not _is_positive_int(window.start_ns):
        rejection_reasons.append("backtest_replay_admission:replay_window_start_ns_invalid")
    if not _is_positive_int(window.end_ns):
        rejection_reasons.append("backtest_replay_admission:replay_window_end_ns_invalid")
    if _is_positive_int(window.start_ns) and _is_positive_int(window.end_ns) and window.end_ns <= window.start_ns:
        rejection_reasons.append("backtest_replay_admission:replay_window_end_not_after_start")


def _validate_policy(policy: BacktestReplayAdmissionPolicy, rejection_reasons: list[str]) -> None:
    if not isinstance(policy, BacktestReplayAdmissionPolicy):
        rejection_reasons.append("backtest_replay_admission:admission_policy_malformed")
        return

    required_fields = (
        ("event_time_ns_policy", policy.event_time_ns_policy),
        ("available_at_ns_policy", policy.available_at_ns_policy),
        ("finalized_at_ns_policy", policy.finalized_at_ns_policy),
        ("fee_assumption", policy.fee_assumption),
        ("slippage_assumption", policy.slippage_assumption),
        ("funding_assumption", policy.funding_assumption),
    )
    for field_name, value in required_fields:
        if not _is_valid_policy_text(value):
            rejection_reasons.append(f"backtest_replay_admission:{field_name}_missing")
    _scan_scope(_policy_to_dict(policy), rejection_reasons, prefix="backtest_replay_admission")


def _resolve_decision_ledger_records(
    records: tuple[DecisionLedgerRecord | Mapping[str, Any], ...] | list[DecisionLedgerRecord | Mapping[str, Any]],
    *,
    strategy_digest_: str | None,
    rejection_reasons: list[str],
    needs_research_reasons: list[str],
    insufficient_evidence_reasons: list[str],
) -> tuple[dict[DecisionLedgerStage, DecisionLedgerRecord], dict[str, str]]:
    from crypto_core.audit.decision_ledger import (
        DecisionLedgerStatus,
        decision_ledger_digest,
        validate_decision_ledger_record,
    )

    if not isinstance(records, tuple | list):
        rejection_reasons.append("backtest_replay_admission:decision_ledger_records_malformed")
        return {}, {}

    ledger_by_stage: dict[DecisionLedgerStage, DecisionLedgerRecord] = {}
    ledger_digests: dict[str, str] = {}
    for item in records:
        validation = validate_decision_ledger_record(item)
        if not validation.accepted or validation.record is None:
            rejection_reasons.extend(
                f"backtest_replay_admission:decision_ledger:{reason}" for reason in validation.rejection_reasons
            )
            continue

        record = validation.record
        stage = record.stage
        if stage in ledger_by_stage:
            rejection_reasons.append(f"backtest_replay_admission:decision_ledger_stage_duplicate:{stage.value}")
            continue
        ledger_by_stage[stage] = record
        ledger_digests[stage.value] = decision_ledger_digest(record)

        if strategy_digest_ is not None and record.strategy_digest != strategy_digest_:
            rejection_reasons.append(f"backtest_replay_admission:strategy_digest_mismatch:{stage.value}")

        if record.status is DecisionLedgerStatus.NEEDS_RESEARCH:
            needs_research_reasons.extend(
                f"backtest_replay_admission:decision_ledger:{reason}" for reason in record.needs_research_reasons
            )
            if not record.needs_research_reasons:
                needs_research_reasons.append(f"backtest_replay_admission:decision_ledger_needs_research:{stage.value}")
        elif record.status is DecisionLedgerStatus.INSUFFICIENT_EVIDENCE:
            insufficient_evidence_reasons.extend(
                f"backtest_replay_admission:decision_ledger:{reason}" for reason in record.rejection_reasons
            )
            if not record.rejection_reasons:
                insufficient_evidence_reasons.append(
                    f"backtest_replay_admission:decision_ledger_insufficient_evidence:{stage.value}"
                )
        elif record.status is not DecisionLedgerStatus.ACCEPTED or record.accepted is not True:
            rejection_reasons.append(f"backtest_replay_admission:decision_ledger_not_accepted:{stage.value}")

    seen_stage_values = {stage.value for stage in ledger_by_stage}
    for stage_value in _REQUIRED_LEDGER_STAGE_VALUES:
        if stage_value not in seen_stage_values:
            rejection_reasons.append(f"backtest_replay_admission:decision_ledger_missing_stage:{stage_value}")

    return ledger_by_stage, dict(sorted(ledger_digests.items()))


def _validate_evidence_digest_by_stage(
    evidence_digest_by_stage: Mapping[DecisionLedgerStage | str, str] | None,
    ledger_by_stage: Mapping[DecisionLedgerStage, DecisionLedgerRecord],
    rejection_reasons: list[str],
) -> dict[str, str]:
    from crypto_core.audit.decision_ledger import decision_ledger_digest

    if evidence_digest_by_stage is None:
        return {}
    if not isinstance(evidence_digest_by_stage, Mapping):
        rejection_reasons.append("backtest_replay_admission:evidence_digest_by_stage_malformed")
        return {}

    normalized: dict[str, str] = {}
    for raw_stage, raw_digest in evidence_digest_by_stage.items():
        stage = _parse_stage(raw_stage)
        if stage is None:
            rejection_reasons.append("backtest_replay_admission:evidence_digest_stage_unknown")
            continue
        if not _is_sha256_digest(raw_digest):
            rejection_reasons.append(f"backtest_replay_admission:evidence_digest_malformed:{stage.value}")
            continue
        normalized[stage.value] = raw_digest
        record = ledger_by_stage.get(stage)
        if record is None:
            continue
        expected_digest = decision_ledger_digest(record)
        if raw_digest != expected_digest:
            rejection_reasons.append(f"backtest_replay_admission:evidence_digest_mismatch:{stage.value}")
    return dict(sorted(normalized.items()))


def _parse_stage(value: object) -> DecisionLedgerStage | None:
    from crypto_core.audit.decision_ledger import DecisionLedgerStage

    if isinstance(value, DecisionLedgerStage):
        return value
    if isinstance(value, str):
        try:
            return DecisionLedgerStage(value)
        except ValueError:
            return None
    return None


def _parse_status(value: object) -> BacktestReplayAdmissionStatus | None:
    if isinstance(value, BacktestReplayAdmissionStatus):
        return value
    if isinstance(value, str):
        try:
            return BacktestReplayAdmissionStatus(value)
        except ValueError:
            return None
    return None


def _window_to_dict(window: BacktestReplayWindow | None) -> dict[str, int] | None:
    if window is None:
        return None
    return {"start_ns": window.start_ns, "end_ns": window.end_ns}


def _window_from_payload(payload: object, rejection_reasons: list[str]) -> BacktestReplayWindow | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        rejection_reasons.append("backtest_replay_admission:replay_window_malformed")
        return None
    start_ns = payload.get("start_ns")
    end_ns = payload.get("end_ns")
    if not isinstance(start_ns, int) or isinstance(start_ns, bool):
        rejection_reasons.append("backtest_replay_admission:replay_window_start_ns_invalid")
        return None
    if not isinstance(end_ns, int) or isinstance(end_ns, bool):
        rejection_reasons.append("backtest_replay_admission:replay_window_end_ns_invalid")
        return None
    return BacktestReplayWindow(start_ns=start_ns, end_ns=end_ns)


def _policy_to_dict(policy: BacktestReplayAdmissionPolicy) -> dict[str, Any]:
    return {
        "event_time_ns_policy": policy.event_time_ns_policy,
        "available_at_ns_policy": policy.available_at_ns_policy,
        "finalized_at_ns_policy": policy.finalized_at_ns_policy,
        "fee_assumption": policy.fee_assumption,
        "slippage_assumption": policy.slippage_assumption,
        "funding_assumption": policy.funding_assumption,
        "metadata": _normalize_json_value(policy.metadata or {}),
    }


def _digest_mapping(payload: object, rejection_reasons: list[str]) -> dict[str, str]:
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        rejection_reasons.append("backtest_replay_admission:digest_mapping_malformed")
        return {}
    parsed: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, str):
            rejection_reasons.append("backtest_replay_admission:digest_mapping_malformed")
            return {}
        parsed[key] = value
    return dict(sorted(parsed.items()))


def _scan_scope(payload: object, rejection_reasons: list[str], *, prefix: str) -> None:
    seen_bist = False
    seen_forbidden = dict.fromkeys(_FORBIDDEN_SCOPE_TOKENS, False)
    seen_timestamp = False

    def _consume(text: str) -> None:
        nonlocal seen_bist, seen_timestamp
        lowered = text.lower()
        if any(token in lowered for token in _BIST_LEAKAGE_TOKENS):
            seen_bist = True
        if any(token in lowered for token in _FORBIDDEN_TIMESTAMP_TOKENS):
            seen_timestamp = True
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
        rejection_reasons.append(f"{prefix}:bist_scope_leakage")
    if seen_timestamp:
        rejection_reasons.append(f"{prefix}:wall_clock_timestamp_policy_forbidden")
    for token in _FORBIDDEN_SCOPE_TOKENS:
        if seen_forbidden[token]:
            rejection_reasons.append(f"{prefix}:forbidden_field_{token}")


def _result(
    *,
    status: BacktestReplayAdmissionStatus,
    strategy_id: str | None = None,
    strategy_digest_: str | None = None,
    replay_source_id: str | None = None,
    historical_data_source_id: str | None = None,
    replay_window: BacktestReplayWindow | None = None,
    decision_ledger_digests: Mapping[str, str] | None = None,
    evidence_digest_by_stage: Mapping[str, str] | None = None,
    rejection_reasons: tuple[str, ...] = (),
    needs_research_reasons: tuple[str, ...] = (),
) -> BacktestReplayAdmissionResult:
    accepted = (
        status is BacktestReplayAdmissionStatus.ACCEPTED and rejection_reasons == () and needs_research_reasons == ()
    )
    return BacktestReplayAdmissionResult(
        accepted=accepted,
        status=status,
        strategy_id=strategy_id,
        strategy_digest=strategy_digest_,
        replay_source_id=replay_source_id,
        historical_data_source_id=historical_data_source_id,
        replay_window=replay_window,
        decision_ledger_digests=dict(sorted((decision_ledger_digests or {}).items())),
        evidence_digest_by_stage=dict(sorted((evidence_digest_by_stage or {}).items())),
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
    )


def _reason_tuple(value: object) -> tuple[str, ...] | None:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        return None
    parsed = tuple(item for item in value if isinstance(item, str) and item)
    if len(parsed) != len(value):
        return None
    return parsed


def _stable_unique(reasons: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_valid_policy_text(value: object) -> bool:
    if not _is_non_empty_string(value):
        return False
    return value.strip().lower() not in {"none", "0", "zero"}


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_sha256_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else None


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


__all__ = [
    "BacktestReplayAdmissionInput",
    "BacktestReplayAdmissionPolicy",
    "BacktestReplayAdmissionResult",
    "BacktestReplayAdmissionStatus",
    "BacktestReplayWindow",
    "backtest_replay_admission_digest",
    "backtest_replay_admission_from_dict",
    "backtest_replay_admission_to_dict",
    "canonical_backtest_replay_admission_json",
    "evaluate_backtest_replay_admission",
]
