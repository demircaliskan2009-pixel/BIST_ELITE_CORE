from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from crypto_core.data.requirements import (
    DataRequirementKey,
    DataRequirementRegistry,
    DataRequirementValidationResult,
    data_requirement_registry_from_dict,
)
from crypto_core.strategy.spec import StrategySpec, validate_strategy_spec


@dataclass(frozen=True)
class PitParityPolicy:
    require_paper_parity: bool = True
    needs_research_reasons: tuple[str, ...] = ()


def validate_strategy_data_requirements(
    spec_or_mapping: StrategySpec | Mapping[str, Any],
    registry: DataRequirementRegistry | Mapping[str, Any],
    policy: PitParityPolicy | None = None,
) -> DataRequirementValidationResult:
    active_policy = policy if policy is not None else PitParityPolicy()
    if not isinstance(active_policy, PitParityPolicy):
        return _result(
            accepted=False,
            registry=None,
            rejection_reasons=("pit_parity:policy_malformed",),
            needs_research_reasons=(),
        )

    spec, spec_rejections = _resolve_strategy_spec(spec_or_mapping)
    if spec is None:
        return _result(False, None, spec_rejections, ())

    resolved_registry, registry_rejections, registry_needs = _resolve_registry(registry)
    if resolved_registry is None:
        prefixed_rejections = tuple(f"pit_parity:registry:{reason}" for reason in registry_rejections)
        prefixed_needs = tuple(f"pit_parity:registry:{reason}" for reason in registry_needs)
        return _result(False, None, _stable_unique(prefixed_rejections), _stable_unique(prefixed_needs))

    rejection_reasons: list[str] = []
    needs_research_reasons: list[str] = [
        reason if reason.startswith("pit_parity:") else f"pit_parity:needs_research:{reason}"
        for reason in active_policy.needs_research_reasons
        if isinstance(reason, str)
    ]

    if not isinstance(spec.data_requirements, Mapping) or not spec.data_requirements:
        rejection_reasons.append("pit_parity:data_requirements_missing")
        return _result(
            False, resolved_registry, _stable_unique(rejection_reasons), _stable_unique(needs_research_reasons)
        )

    rejection_reasons.extend(_scan_for_scope_violations(spec.data_requirements, prefix="pit_parity"))
    rejection_reasons.extend(_scan_for_scope_violations(_registry_to_mapping(resolved_registry), prefix="pit_parity"))

    registry_map = {key.value: requirement for key, requirement in resolved_registry.requirements.items()}

    for data_key in sorted(spec.data_requirements.keys(), key=str):
        if not isinstance(data_key, str):
            rejection_reasons.append("pit_parity:data_requirement_key_malformed")
            continue
        normalized_key = data_key.strip().lower()
        if not normalized_key:
            rejection_reasons.append("pit_parity:data_requirement_key_empty")
            continue
        if normalized_key == "price":
            rejection_reasons.append("pit_parity:generic_price_key_forbidden")
            continue
        if normalized_key == "funding":
            rejection_reasons.append("pit_parity:generic_funding_key_forbidden")
            continue

        requirement = registry_map.get(normalized_key)
        if requirement is None:
            rejection_reasons.append(f"pit_parity:unknown_data_key:{normalized_key}")
            continue

        if not requirement.historical_source.strip():
            rejection_reasons.append(f"pit_parity:historical_source_missing:{normalized_key}")
        if active_policy.require_paper_parity and not requirement.paper_observation_source:
            rejection_reasons.append(f"pit_parity:paper_parity_source_missing:{normalized_key}")

        if not requirement.event_time_policy.strip():
            rejection_reasons.append(f"pit_parity:event_time_policy_missing:{normalized_key}")
        if not requirement.available_at_policy.strip():
            rejection_reasons.append(f"pit_parity:available_at_policy_missing:{normalized_key}")
        if not requirement.finalized_at_policy.strip():
            rejection_reasons.append(f"pit_parity:finalized_at_policy_missing:{normalized_key}")

        if normalized_key == DataRequirementKey.FUNDING_RATE.value:
            if requirement.funding_semantics not in {"predicted", "final"}:
                rejection_reasons.append("pit_parity:funding_semantics_ambiguous")

        if normalized_key in {
            DataRequirementKey.MARK_PRICE.value,
            DataRequirementKey.INDEX_PRICE.value,
            DataRequirementKey.LAST_TRADE.value,
        }:
            if requirement.price_semantics not in {"mark_price", "index_price", "last_trade"}:
                rejection_reasons.append("pit_parity:price_semantics_ambiguous")

        if normalized_key == DataRequirementKey.ORDER_BOOK.value:
            if requirement.order_book_level not in {"l1", "l2", "l3"}:
                rejection_reasons.append("pit_parity:order_book_level_missing")
            if requirement.order_book_depth is None or requirement.order_book_depth <= 0:
                rejection_reasons.append("pit_parity:order_book_depth_missing")
            if not _valid_assumption(requirement.sequence_policy):
                rejection_reasons.append("pit_parity:sequence_policy_missing")
            if not _valid_assumption(requirement.resync_policy):
                rejection_reasons.append("pit_parity:resync_policy_missing")

        if normalized_key == DataRequirementKey.LIQUIDATION.value:
            if not _valid_assumption(requirement.liquidation_source):
                rejection_reasons.append("pit_parity:liquidation_source_missing")
            if not _valid_assumption(requirement.finality_policy):
                rejection_reasons.append("pit_parity:liquidation_finality_missing")

        if not _valid_assumption(requirement.fee_assumption):
            rejection_reasons.append("pit_parity:fee_assumption_invalid")
        if not _valid_assumption(requirement.slippage_assumption):
            rejection_reasons.append("pit_parity:slippage_assumption_invalid")
        if not _valid_assumption(requirement.latency_assumption):
            rejection_reasons.append("pit_parity:latency_assumption_invalid")

    return _result(
        accepted=not rejection_reasons and not needs_research_reasons,
        registry=resolved_registry,
        rejection_reasons=_stable_unique(rejection_reasons),
        needs_research_reasons=_stable_unique(needs_research_reasons),
    )


def _resolve_strategy_spec(
    spec_or_mapping: StrategySpec | Mapping[str, Any],
) -> tuple[StrategySpec | None, tuple[str, ...]]:
    if isinstance(spec_or_mapping, StrategySpec):
        return spec_or_mapping, ()
    if not isinstance(spec_or_mapping, Mapping):
        return None, ("pit_parity:strategy_spec:payload_malformed",)

    validation = validate_strategy_spec(spec_or_mapping)
    if validation.accepted and validation.spec is not None:
        return validation.spec, ()

    prefixed = [f"pit_parity:strategy_spec:{reason}" for reason in validation.rejection_reasons]
    prefixed.extend(f"pit_parity:strategy_spec:{reason}" for reason in validation.needs_research_reasons)
    return None, _stable_unique(prefixed)


def _resolve_registry(
    registry: DataRequirementRegistry | Mapping[str, Any],
) -> tuple[DataRequirementRegistry | None, tuple[str, ...], tuple[str, ...]]:
    if isinstance(registry, DataRequirementRegistry):
        return registry, (), ()
    if not isinstance(registry, Mapping):
        return None, ("pit_parity:registry_malformed",), ()

    result = data_requirement_registry_from_dict(registry)
    if not result.accepted or result.registry is None:
        return None, result.rejection_reasons, result.needs_research_reasons
    return result.registry, (), ()


def _valid_assumption(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized not in {"", "none", "0", "zero"}


def _registry_to_mapping(registry: DataRequirementRegistry) -> Mapping[str, Any]:
    return {
        "schema_version": registry.schema_version,
        "requirements": {
            key.value: {
                "historical_source": requirement.historical_source,
                "paper_observation_source": requirement.paper_observation_source,
                "event_time_policy": requirement.event_time_policy,
                "available_at_policy": requirement.available_at_policy,
                "finalized_at_policy": requirement.finalized_at_policy,
                "funding_semantics": requirement.funding_semantics,
                "price_semantics": requirement.price_semantics,
                "order_book_level": requirement.order_book_level,
                "order_book_depth": requirement.order_book_depth,
                "sequence_policy": requirement.sequence_policy,
                "resync_policy": requirement.resync_policy,
                "liquidation_source": requirement.liquidation_source,
                "finality_policy": requirement.finality_policy,
                "fee_assumption": requirement.fee_assumption,
                "slippage_assumption": requirement.slippage_assumption,
                "latency_assumption": requirement.latency_assumption,
            }
            for key, requirement in registry.requirements.items()
        },
    }


def _scan_for_scope_violations(payload: Mapping[str, Any], *, prefix: str) -> list[str]:
    bist_tokens = ("bist", "bist30", "bist100", "borsa", "kap", "ideal", "i\u0307deal", "matriks")
    forbidden_tokens = (
        "live",
        "private_api",
        "credentials",
        "order_router",
        "scheduler",
        "auto_loop",
        "shadow_live_execution",
    )

    reasons: list[str] = []
    seen_bist = False
    seen_forbidden = dict.fromkeys(forbidden_tokens, False)

    def _consume(text: str) -> None:
        nonlocal seen_bist
        lowered = text.lower()
        if any(token in lowered for token in bist_tokens):
            seen_bist = True
        for token in forbidden_tokens:
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
        reasons.append(f"{prefix}:bist_scope_leakage")
    for token in forbidden_tokens:
        if seen_forbidden[token]:
            reasons.append(f"{prefix}:forbidden_field_{token}")

    return reasons


def _stable_unique(reasons: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if reason}))


def _result(
    accepted: bool,
    registry: DataRequirementRegistry | None,
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
) -> DataRequirementValidationResult:
    if needs_research_reasons:
        accepted = False
    return DataRequirementValidationResult(
        accepted=accepted,
        registry=registry,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
    )


__all__ = ["PitParityPolicy", "validate_strategy_data_requirements"]
