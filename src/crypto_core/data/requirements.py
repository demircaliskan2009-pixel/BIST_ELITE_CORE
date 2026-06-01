from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class DataRequirementKey(str, Enum):
    FUNDING_RATE = "funding_rate"
    MARK_PRICE = "mark_price"
    INDEX_PRICE = "index_price"
    LAST_TRADE = "last_trade"
    ORDER_BOOK = "order_book"
    LIQUIDATION = "liquidation"


class DataAvailabilityMode(str, Enum):
    HISTORICAL_ONLY = "historical_only"
    PAPER_PARITY = "paper_parity"


@dataclass(frozen=True)
class DataRequirement:
    key: DataRequirementKey
    availability_mode: DataAvailabilityMode
    historical_source: str
    paper_observation_source: str | None
    event_time_policy: str
    available_at_policy: str
    finalized_at_policy: str
    funding_semantics: str | None
    price_semantics: str | None
    order_book_level: str | None
    order_book_depth: int | None
    sequence_policy: str | None
    resync_policy: str | None
    liquidation_source: str | None
    finality_policy: str | None
    fee_assumption: str
    slippage_assumption: str
    latency_assumption: str


@dataclass(frozen=True)
class DataRequirementRegistry:
    schema_version: str
    requirements: dict[DataRequirementKey, DataRequirement]


@dataclass(frozen=True)
class DataRequirementValidationResult:
    accepted: bool
    registry: DataRequirementRegistry | None
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.needs_research_reasons and self.accepted:
            raise ValueError("accepted must be False when needs_research_reasons is non-empty")


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

_VALID_FUNDING = frozenset({"predicted", "final"})
_VALID_PRICE = frozenset({"mark_price", "index_price", "last_trade"})
_VALID_OB_LEVEL = frozenset({"l1", "l2", "l3"})


def default_perp_data_requirement_registry() -> DataRequirementRegistry:
    requirements = {
        DataRequirementKey.FUNDING_RATE: DataRequirement(
            key=DataRequirementKey.FUNDING_RATE,
            availability_mode=DataAvailabilityMode.PAPER_PARITY,
            historical_source="funding_history_v1",
            paper_observation_source="funding_observer_v1",
            event_time_policy="funding_window_open_ns",
            available_at_policy="funding_published_ns",
            finalized_at_policy="funding_finalized_ns",
            funding_semantics="final",
            price_semantics=None,
            order_book_level=None,
            order_book_depth=None,
            sequence_policy=None,
            resync_policy=None,
            liquidation_source=None,
            finality_policy="funding_cycle_closed",
            fee_assumption="maker_taker",
            slippage_assumption="book_impact_v1",
            latency_assumption="feed_latency_profile_v1",
        ),
        DataRequirementKey.MARK_PRICE: DataRequirement(
            key=DataRequirementKey.MARK_PRICE,
            availability_mode=DataAvailabilityMode.PAPER_PARITY,
            historical_source="mark_price_history_v1",
            paper_observation_source="mark_price_stream_v1",
            event_time_policy="mark_event_ns",
            available_at_policy="mark_available_ns",
            finalized_at_policy="mark_finalized_ns",
            funding_semantics=None,
            price_semantics="mark_price",
            order_book_level=None,
            order_book_depth=None,
            sequence_policy=None,
            resync_policy=None,
            liquidation_source=None,
            finality_policy="mark_snapshot_final",
            fee_assumption="maker_taker",
            slippage_assumption="book_impact_v1",
            latency_assumption="feed_latency_profile_v1",
        ),
        DataRequirementKey.INDEX_PRICE: DataRequirement(
            key=DataRequirementKey.INDEX_PRICE,
            availability_mode=DataAvailabilityMode.PAPER_PARITY,
            historical_source="index_price_history_v1",
            paper_observation_source="index_price_stream_v1",
            event_time_policy="index_event_ns",
            available_at_policy="index_available_ns",
            finalized_at_policy="index_finalized_ns",
            funding_semantics=None,
            price_semantics="index_price",
            order_book_level=None,
            order_book_depth=None,
            sequence_policy=None,
            resync_policy=None,
            liquidation_source=None,
            finality_policy="index_snapshot_final",
            fee_assumption="maker_taker",
            slippage_assumption="book_impact_v1",
            latency_assumption="feed_latency_profile_v1",
        ),
        DataRequirementKey.LAST_TRADE: DataRequirement(
            key=DataRequirementKey.LAST_TRADE,
            availability_mode=DataAvailabilityMode.PAPER_PARITY,
            historical_source="trade_history_v1",
            paper_observation_source="trade_stream_v1",
            event_time_policy="trade_event_ns",
            available_at_policy="trade_available_ns",
            finalized_at_policy="trade_finalized_ns",
            funding_semantics=None,
            price_semantics="last_trade",
            order_book_level=None,
            order_book_depth=None,
            sequence_policy=None,
            resync_policy=None,
            liquidation_source=None,
            finality_policy="trade_tick_final",
            fee_assumption="maker_taker",
            slippage_assumption="book_impact_v1",
            latency_assumption="feed_latency_profile_v1",
        ),
        DataRequirementKey.ORDER_BOOK: DataRequirement(
            key=DataRequirementKey.ORDER_BOOK,
            availability_mode=DataAvailabilityMode.PAPER_PARITY,
            historical_source="order_book_snapshot_delta_v1",
            paper_observation_source="order_book_stream_v1",
            event_time_policy="book_event_ns",
            available_at_policy="book_available_ns",
            finalized_at_policy="book_sequence_finalized_ns",
            funding_semantics=None,
            price_semantics=None,
            order_book_level="l2",
            order_book_depth=50,
            sequence_policy="strict_monotonic",
            resync_policy="snapshot_then_delta",
            liquidation_source=None,
            finality_policy="sequence_gap_reject",
            fee_assumption="maker_taker",
            slippage_assumption="book_impact_v1",
            latency_assumption="feed_latency_profile_v1",
        ),
        DataRequirementKey.LIQUIDATION: DataRequirement(
            key=DataRequirementKey.LIQUIDATION,
            availability_mode=DataAvailabilityMode.PAPER_PARITY,
            historical_source="liquidation_history_v1",
            paper_observation_source="liquidation_stream_v1",
            event_time_policy="liquidation_event_ns",
            available_at_policy="liquidation_available_ns",
            finalized_at_policy="liquidation_finalized_ns",
            funding_semantics=None,
            price_semantics=None,
            order_book_level=None,
            order_book_depth=None,
            sequence_policy=None,
            resync_policy=None,
            liquidation_source="force_order_feed_v1",
            finality_policy="liquidation_event_final",
            fee_assumption="maker_taker",
            slippage_assumption="book_impact_v1",
            latency_assumption="feed_latency_profile_v1",
        ),
    }
    return DataRequirementRegistry(schema_version="1.0", requirements=requirements)


def data_requirement_registry_to_dict(registry: DataRequirementRegistry) -> dict[str, Any]:
    return {
        "schema_version": registry.schema_version,
        "requirements": {
            key.value: {
                "key": requirement.key.value,
                "availability_mode": requirement.availability_mode.value,
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


def data_requirement_registry_from_dict(payload: Mapping[str, Any]) -> DataRequirementValidationResult:
    if not isinstance(payload, Mapping):
        return _result(False, None, ("data_requirement_registry:payload_malformed",), ())

    rejection_reasons: list[str] = []
    needs_research_reasons: list[str] = []
    rejection_reasons.extend(_scan_for_scope_violations(payload))

    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        rejection_reasons.append("data_requirement_registry:schema_version_invalid")
        schema_version = ""

    requirements_payload = payload.get("requirements")
    if not isinstance(requirements_payload, Mapping) or not requirements_payload:
        rejection_reasons.append("data_requirement_registry:requirements_missing")
        return _result(False, None, _stable_unique(rejection_reasons), _stable_unique(needs_research_reasons))

    parsed_requirements: dict[DataRequirementKey, DataRequirement] = {}
    for key_name in sorted(requirements_payload.keys()):
        if not isinstance(key_name, str):
            rejection_reasons.append("data_requirement_registry:key_malformed")
            continue
        try:
            key = DataRequirementKey(key_name)
        except ValueError:
            rejection_reasons.append(f"data_requirement_registry:unknown_key:{key_name}")
            continue

        value = requirements_payload.get(key_name)
        if not isinstance(value, Mapping):
            rejection_reasons.append(f"data_requirement_registry:requirement_malformed:{key_name}")
            continue
        requirement, requirement_reasons = _parse_requirement(key, value)
        rejection_reasons.extend(requirement_reasons)
        if requirement is not None:
            parsed_requirements[key] = requirement

    stable_rejections = _stable_unique(rejection_reasons)
    stable_needs = _stable_unique(needs_research_reasons)
    if stable_rejections or stable_needs:
        return _result(False, None, stable_rejections, stable_needs)

    registry = DataRequirementRegistry(
        schema_version=schema_version,
        requirements=parsed_requirements,
    )
    return _result(True, registry, (), ())


def canonical_data_requirement_registry_json(registry: DataRequirementRegistry) -> str:
    return json.dumps(
        data_requirement_registry_to_dict(registry),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def data_requirement_registry_digest(registry: DataRequirementRegistry) -> str:
    canonical = canonical_data_requirement_registry_json(registry)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_requirement(
    key: DataRequirementKey,
    payload: Mapping[str, Any],
) -> tuple[DataRequirement | None, list[str]]:
    reasons: list[str] = []

    raw_key = payload.get("key")
    if not isinstance(raw_key, str):
        reasons.append(f"data_requirement_registry:key_missing:{key.value}")
    elif raw_key != key.value:
        reasons.append(f"data_requirement_registry:key_mismatch:{key.value}")

    availability_mode = _parse_enum(
        DataAvailabilityMode,
        payload.get("availability_mode"),
        reasons,
        f"data_requirement_registry:availability_mode_invalid:{key.value}",
        default=DataAvailabilityMode.PAPER_PARITY,
    )

    historical_source = _non_empty_str(
        payload.get("historical_source"), reasons, f"data_requirement_registry:historical_source_missing:{key.value}"
    )
    paper_observation_source = _optional_non_empty_str(
        payload.get("paper_observation_source"),
        reasons,
        f"data_requirement_registry:paper_observation_source_invalid:{key.value}",
    )
    event_time_policy = _non_empty_str(
        payload.get("event_time_policy"), reasons, f"data_requirement_registry:event_time_policy_missing:{key.value}"
    )
    available_at_policy = _non_empty_str(
        payload.get("available_at_policy"),
        reasons,
        f"data_requirement_registry:available_at_policy_missing:{key.value}",
    )
    finalized_at_policy = _non_empty_str(
        payload.get("finalized_at_policy"),
        reasons,
        f"data_requirement_registry:finalized_at_policy_missing:{key.value}",
    )

    funding_semantics = _optional_non_empty_str(
        payload.get("funding_semantics"), reasons, f"data_requirement_registry:funding_semantics_invalid:{key.value}"
    )
    price_semantics = _optional_non_empty_str(
        payload.get("price_semantics"), reasons, f"data_requirement_registry:price_semantics_invalid:{key.value}"
    )
    order_book_level = _optional_non_empty_str(
        payload.get("order_book_level"), reasons, f"data_requirement_registry:order_book_level_invalid:{key.value}"
    )
    order_book_depth = _optional_positive_int(
        payload.get("order_book_depth"), reasons, f"data_requirement_registry:order_book_depth_invalid:{key.value}"
    )
    sequence_policy = _optional_non_empty_str(
        payload.get("sequence_policy"), reasons, f"data_requirement_registry:sequence_policy_invalid:{key.value}"
    )
    resync_policy = _optional_non_empty_str(
        payload.get("resync_policy"), reasons, f"data_requirement_registry:resync_policy_invalid:{key.value}"
    )
    liquidation_source = _optional_non_empty_str(
        payload.get("liquidation_source"), reasons, f"data_requirement_registry:liquidation_source_invalid:{key.value}"
    )
    finality_policy = _optional_non_empty_str(
        payload.get("finality_policy"), reasons, f"data_requirement_registry:finality_policy_invalid:{key.value}"
    )

    fee_assumption = _non_empty_non_zero_assumption(
        payload.get("fee_assumption"), reasons, f"data_requirement_registry:fee_assumption_invalid:{key.value}"
    )
    slippage_assumption = _non_empty_non_zero_assumption(
        payload.get("slippage_assumption"),
        reasons,
        f"data_requirement_registry:slippage_assumption_invalid:{key.value}",
    )
    latency_assumption = _non_empty_non_zero_assumption(
        payload.get("latency_assumption"), reasons, f"data_requirement_registry:latency_assumption_invalid:{key.value}"
    )

    if key is DataRequirementKey.FUNDING_RATE:
        if funding_semantics not in _VALID_FUNDING:
            reasons.append(f"data_requirement_registry:funding_semantics_ambiguous:{key.value}")
    elif funding_semantics is not None:
        reasons.append(f"data_requirement_registry:funding_semantics_unexpected:{key.value}")

    if key in (DataRequirementKey.MARK_PRICE, DataRequirementKey.INDEX_PRICE, DataRequirementKey.LAST_TRADE):
        if price_semantics not in _VALID_PRICE:
            reasons.append(f"data_requirement_registry:price_semantics_ambiguous:{key.value}")
    elif price_semantics is not None:
        reasons.append(f"data_requirement_registry:price_semantics_unexpected:{key.value}")

    if key is DataRequirementKey.ORDER_BOOK:
        if order_book_level not in _VALID_OB_LEVEL:
            reasons.append("data_requirement_registry:order_book_level_missing")
        if order_book_depth is None or order_book_depth <= 0:
            reasons.append("data_requirement_registry:order_book_depth_missing")
        if not sequence_policy:
            reasons.append("data_requirement_registry:sequence_policy_missing")
        if not resync_policy:
            reasons.append("data_requirement_registry:resync_policy_missing")
    elif any(value is not None for value in (order_book_level, order_book_depth, sequence_policy, resync_policy)):
        reasons.append(f"data_requirement_registry:order_book_fields_unexpected:{key.value}")

    if key is DataRequirementKey.LIQUIDATION:
        if not liquidation_source:
            reasons.append("data_requirement_registry:liquidation_source_missing")
        if not finality_policy:
            reasons.append("data_requirement_registry:liquidation_finality_policy_missing")

    if reasons:
        return None, reasons

    return (
        DataRequirement(
            key=key,
            availability_mode=availability_mode,
            historical_source=historical_source,
            paper_observation_source=paper_observation_source,
            event_time_policy=event_time_policy,
            available_at_policy=available_at_policy,
            finalized_at_policy=finalized_at_policy,
            funding_semantics=funding_semantics,
            price_semantics=price_semantics,
            order_book_level=order_book_level,
            order_book_depth=order_book_depth,
            sequence_policy=sequence_policy,
            resync_policy=resync_policy,
            liquidation_source=liquidation_source,
            finality_policy=finality_policy,
            fee_assumption=fee_assumption,
            slippage_assumption=slippage_assumption,
            latency_assumption=latency_assumption,
        ),
        reasons,
    )


def _parse_enum(
    enum_cls: type[Enum],
    value: object,
    reasons: list[str],
    reason: str,
    *,
    default: Any,
) -> Any:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError:
            reasons.append(reason)
            return default
    reasons.append(reason)
    return default


def _non_empty_str(value: object, reasons: list[str], reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        reasons.append(reason)
        return ""
    return value.strip()


def _optional_non_empty_str(value: object, reasons: list[str], reason: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        reasons.append(reason)
        return None
    trimmed = value.strip()
    if not trimmed:
        reasons.append(reason)
        return None
    return trimmed


def _optional_positive_int(value: object, reasons: list[str], reason: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        reasons.append(reason)
        return None
    return value


def _non_empty_non_zero_assumption(value: object, reasons: list[str], reason: str) -> str:
    if not isinstance(value, str):
        reasons.append(reason)
        return ""
    normalized = value.strip().lower()
    if normalized in {"", "none", "0", "zero"}:
        reasons.append(reason)
        return ""
    return value.strip()


def _scan_for_scope_violations(payload: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
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
        reasons.append("data_requirement_registry:bist_scope_leakage")
    for token in _FORBIDDEN_SCOPE_TOKENS:
        if seen_forbidden[token]:
            reasons.append(f"data_requirement_registry:forbidden_field_{token}")
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


__all__ = [
    "DataAvailabilityMode",
    "DataRequirement",
    "DataRequirementKey",
    "DataRequirementRegistry",
    "DataRequirementValidationResult",
    "canonical_data_requirement_registry_json",
    "data_requirement_registry_digest",
    "data_requirement_registry_from_dict",
    "data_requirement_registry_to_dict",
    "default_perp_data_requirement_registry",
]
