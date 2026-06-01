"""Deterministic fail-closed leakage, bias, and repaint validation gate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from crypto_core.strategy.spec import StrategySpec, validate_strategy_spec


class LeakageBiasRepaintStatus(str, Enum):
    PASS = "PASS"  # noqa: S105 - status label, not a credential.
    REJECT = "REJECT"  # noqa: S105 - status label, not a credential.
    NEEDS_RESEARCH = "NEEDS_RESEARCH"  # noqa: S105 - status label, not a credential.
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # noqa: S105 - status label, not a credential.


@dataclass(frozen=True)
class ValidationFeatureTimestamp:
    feature_name: str
    event_time_ns: int
    available_at_ns: int
    finalized_at_ns: int | None = None
    is_candle_or_bar_derived: bool = False
    uses_current_bar: bool = False


@dataclass(frozen=True)
class ValidationFundingObservation:
    venue: str
    event_time_ns: int
    available_at_ns: int
    finalized_at_ns: int | None
    final_rate: float | None = None


@dataclass(frozen=True)
class ValidationIndicatorPolicy:
    indicator_name: str
    repaint_risk: bool = False
    confirmation_rule: str | None = None


@dataclass(frozen=True)
class LeakageBiasRepaintInput:
    strategy_spec: StrategySpec | Mapping[str, Any]
    decision_timestamp_ns: int
    pit_policy: Mapping[str, Any] | None
    feature_timestamps: tuple[ValidationFeatureTimestamp, ...] = ()
    funding_observations: tuple[ValidationFundingObservation, ...] = ()
    indicator_policies: tuple[ValidationIndicatorPolicy, ...] = ()
    payload: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] | None = None
    fee_assumption: str | None = None
    slippage_assumption: str | None = None
    funding_assumption: str | None = None
    needs_research_reasons: tuple[str, ...] = ()
    insufficient_evidence_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class LeakageBiasRepaintResult:
    accepted: bool
    status: LeakageBiasRepaintStatus
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        expected_accepted = (
            self.status is LeakageBiasRepaintStatus.PASS
            and self.rejection_reasons == ()
            and self.needs_research_reasons == ()
        )
        if self.accepted != expected_accepted:
            raise ValueError("accepted must be true only for PASS with empty reason tuples")


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


def evaluate_leakage_bias_repaint(input_: LeakageBiasRepaintInput) -> LeakageBiasRepaintResult:
    if not isinstance(input_, LeakageBiasRepaintInput):
        return _result(
            status=LeakageBiasRepaintStatus.REJECT,
            rejection_reasons=("leakage_bias_repaint:input_malformed",),
            needs_research_reasons=(),
        )

    spec, spec_rejections = _resolve_strategy_spec(input_.strategy_spec)
    if spec is None:
        return _result(
            status=LeakageBiasRepaintStatus.REJECT,
            rejection_reasons=spec_rejections,
            needs_research_reasons=(),
        )

    rejection_reasons: list[str] = []
    needs_research_reasons = list(input_.needs_research_reasons)

    if not _is_positive_int(input_.decision_timestamp_ns):
        rejection_reasons.append("leakage_bias_repaint:decision_timestamp_ns_invalid")

    if not isinstance(input_.pit_policy, Mapping) or not input_.pit_policy:
        rejection_reasons.append("leakage_bias_repaint:pit_policy_missing")

    _validate_feature_timestamps(input_.feature_timestamps, input_.decision_timestamp_ns, rejection_reasons)
    _validate_indicator_policies(input_.indicator_policies, rejection_reasons)
    _validate_funding_observations(input_.funding_observations, input_.decision_timestamp_ns, rejection_reasons)
    _validate_assumptions(spec, input_, rejection_reasons)
    _scan_payload_scope(input_.payload, rejection_reasons)
    _scan_payload_scope(input_.metadata, rejection_reasons)

    if input_.insufficient_evidence_reasons:
        rejection_reasons.extend(
            f"leakage_bias_repaint:insufficient_evidence:{reason}"
            for reason in input_.insufficient_evidence_reasons
            if isinstance(reason, str)
        )

    stable_rejections = _stable_unique(rejection_reasons)
    stable_needs_research = _stable_unique(
        tuple(
            f"leakage_bias_repaint:needs_research:{reason}"
            if not reason.startswith("leakage_bias_repaint:")
            else reason
            for reason in needs_research_reasons
            if isinstance(reason, str)
        )
    )

    if stable_rejections:
        if all(reason.startswith("leakage_bias_repaint:insufficient_evidence:") for reason in stable_rejections):
            return _result(
                status=LeakageBiasRepaintStatus.INSUFFICIENT_EVIDENCE,
                rejection_reasons=stable_rejections,
                needs_research_reasons=(),
            )
        return _result(
            status=LeakageBiasRepaintStatus.REJECT,
            rejection_reasons=stable_rejections,
            needs_research_reasons=(),
        )

    if stable_needs_research:
        return _result(
            status=LeakageBiasRepaintStatus.NEEDS_RESEARCH,
            rejection_reasons=(),
            needs_research_reasons=stable_needs_research,
        )

    return _result(status=LeakageBiasRepaintStatus.PASS, rejection_reasons=(), needs_research_reasons=())


def leakage_bias_repaint_result_to_dict(result: LeakageBiasRepaintResult) -> dict[str, Any]:
    return {
        "accepted": result.accepted,
        "status": result.status.value,
        "rejection_reasons": list(result.rejection_reasons),
        "needs_research_reasons": list(result.needs_research_reasons),
    }


def leakage_bias_repaint_result_from_dict(payload: Mapping[str, Any]) -> LeakageBiasRepaintResult:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")

    status_raw = payload.get("status")
    if not isinstance(status_raw, str):
        raise ValueError("status must be string")
    status = LeakageBiasRepaintStatus(status_raw)

    accepted = payload.get("accepted")
    if not isinstance(accepted, bool):
        raise ValueError("accepted must be bool")

    rejection_reasons = _parse_reason_list(payload.get("rejection_reasons"), "rejection_reasons")
    needs_research_reasons = _parse_reason_list(payload.get("needs_research_reasons"), "needs_research_reasons")

    return LeakageBiasRepaintResult(
        accepted=accepted,
        status=status,
        rejection_reasons=tuple(rejection_reasons),
        needs_research_reasons=tuple(needs_research_reasons),
    )


def _parse_reason_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    parsed: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} must contain only strings")
        parsed.append(item)
    return parsed


def _resolve_strategy_spec(
    strategy_spec: StrategySpec | Mapping[str, Any],
) -> tuple[StrategySpec | None, tuple[str, ...]]:
    if isinstance(strategy_spec, StrategySpec):
        return strategy_spec, ()
    if not isinstance(strategy_spec, Mapping):
        return None, ("leakage_bias_repaint:strategy_spec:payload_malformed",)

    validation = validate_strategy_spec(strategy_spec)
    if validation.accepted and validation.spec is not None:
        return validation.spec, ()

    prefixed = [f"leakage_bias_repaint:strategy_spec:{reason}" for reason in validation.rejection_reasons]
    prefixed.extend(f"leakage_bias_repaint:strategy_spec:{reason}" for reason in validation.needs_research_reasons)
    return None, _stable_unique(tuple(prefixed))


def _validate_feature_timestamps(
    feature_timestamps: tuple[ValidationFeatureTimestamp, ...],
    decision_timestamp_ns: int,
    rejection_reasons: list[str],
) -> None:
    if not isinstance(feature_timestamps, tuple):
        rejection_reasons.append("leakage_bias_repaint:feature_timestamps_malformed")
        return

    for feature in feature_timestamps:
        if not isinstance(feature, ValidationFeatureTimestamp):
            rejection_reasons.append("leakage_bias_repaint:feature_timestamp_item_malformed")
            continue
        if feature.event_time_ns > decision_timestamp_ns:
            rejection_reasons.append("leakage_bias_repaint:feature_event_time_after_decision")
        if feature.available_at_ns > decision_timestamp_ns:
            rejection_reasons.append("leakage_bias_repaint:feature_available_at_after_decision")
        if feature.is_candle_or_bar_derived and feature.finalized_at_ns is None:
            rejection_reasons.append("leakage_bias_repaint:feature_finalized_at_missing")
        if feature.finalized_at_ns is not None and feature.finalized_at_ns > decision_timestamp_ns:
            rejection_reasons.append("leakage_bias_repaint:feature_finalized_at_after_decision")
        if feature.uses_current_bar:
            rejection_reasons.append("leakage_bias_repaint:current_bar_usage_forbidden")


def _validate_indicator_policies(
    indicator_policies: tuple[ValidationIndicatorPolicy, ...],
    rejection_reasons: list[str],
) -> None:
    if not isinstance(indicator_policies, tuple):
        rejection_reasons.append("leakage_bias_repaint:indicator_policies_malformed")
        return

    for indicator_policy in indicator_policies:
        if not isinstance(indicator_policy, ValidationIndicatorPolicy):
            rejection_reasons.append("leakage_bias_repaint:indicator_policy_item_malformed")
            continue
        if indicator_policy.repaint_risk and not _is_non_empty_string(indicator_policy.confirmation_rule):
            rejection_reasons.append("leakage_bias_repaint:repaint_confirmation_rule_missing")


def _validate_funding_observations(
    funding_observations: tuple[ValidationFundingObservation, ...],
    decision_timestamp_ns: int,
    rejection_reasons: list[str],
) -> None:
    if not isinstance(funding_observations, tuple):
        rejection_reasons.append("leakage_bias_repaint:funding_observations_malformed")
        return

    for funding_observation in funding_observations:
        if not isinstance(funding_observation, ValidationFundingObservation):
            rejection_reasons.append("leakage_bias_repaint:funding_observation_item_malformed")
            continue
        if funding_observation.available_at_ns > decision_timestamp_ns:
            rejection_reasons.append("leakage_bias_repaint:funding_available_at_after_decision")
        if funding_observation.finalized_at_ns is None or funding_observation.finalized_at_ns > decision_timestamp_ns:
            rejection_reasons.append("leakage_bias_repaint:funding_unfinalized_at_decision")
        if funding_observation.final_rate is None:
            rejection_reasons.append("leakage_bias_repaint:funding_final_rate_unavailable")


def _validate_assumptions(
    strategy_spec: StrategySpec,
    input_: LeakageBiasRepaintInput,
    rejection_reasons: list[str],
) -> None:
    if _requires_assumption(strategy_spec.fee_model_requirement) and not _is_non_empty_string(input_.fee_assumption):
        rejection_reasons.append("leakage_bias_repaint:fee_assumption_missing")
    if _requires_assumption(strategy_spec.slippage_model_requirement) and not _is_non_empty_string(
        input_.slippage_assumption
    ):
        rejection_reasons.append("leakage_bias_repaint:slippage_assumption_missing")
    if _requires_assumption(strategy_spec.funding_sensitivity) and not _is_non_empty_string(input_.funding_assumption):
        rejection_reasons.append("leakage_bias_repaint:funding_assumption_missing")


def _scan_payload_scope(payload: Mapping[str, Any] | None, rejection_reasons: list[str]) -> None:
    if not isinstance(payload, Mapping):
        return

    seen_bist = False
    seen_forbidden = dict.fromkeys(_FORBIDDEN_SCOPE_TOKENS, False)

    def _consume_text(text: str) -> None:
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
                    _consume_text(key)
                _walk(value)
        elif isinstance(node, list | tuple):
            for item in node:
                _walk(item)
        elif isinstance(node, str):
            _consume_text(node)

    _walk(payload)

    if seen_bist:
        rejection_reasons.append("leakage_bias_repaint:bist_scope_leakage")
    for token in _FORBIDDEN_SCOPE_TOKENS:
        if seen_forbidden[token]:
            rejection_reasons.append(f"leakage_bias_repaint:forbidden_field_{token}")


def _requires_assumption(value: object) -> bool:
    if not _is_non_empty_string(value):
        return False
    return value.strip().lower() not in {"none", "not_required", "optional", "unknown"}


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _stable_unique(reasons: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if reason}))


def _result(
    *,
    status: LeakageBiasRepaintStatus,
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
) -> LeakageBiasRepaintResult:
    accepted = status is LeakageBiasRepaintStatus.PASS and rejection_reasons == () and needs_research_reasons == ()
    return LeakageBiasRepaintResult(
        accepted=accepted,
        status=status,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
    )
