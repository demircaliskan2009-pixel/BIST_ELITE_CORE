from __future__ import annotations

import json

from crypto_core.data.requirements import (
    DataAvailabilityMode,
    DataRequirementKey,
    DataRequirementRegistry,
    canonical_data_requirement_registry_json,
    data_requirement_registry_digest,
    data_requirement_registry_from_dict,
    data_requirement_registry_to_dict,
    default_perp_data_requirement_registry,
)


def test_default_perp_registry_is_deterministic_and_non_empty() -> None:
    registry_a = default_perp_data_requirement_registry()
    registry_b = default_perp_data_requirement_registry()

    assert isinstance(registry_a, DataRequirementRegistry)
    assert registry_a.requirements
    assert data_requirement_registry_to_dict(registry_a) == data_requirement_registry_to_dict(registry_b)
    assert registry_a.requirements[DataRequirementKey.ORDER_BOOK].availability_mode is DataAvailabilityMode.PAPER_PARITY


def test_registry_to_dict_from_dict_round_trip_stable() -> None:
    registry = default_perp_data_requirement_registry()
    payload = data_requirement_registry_to_dict(registry)
    result = data_requirement_registry_from_dict(payload)

    assert result.accepted is True
    assert result.registry is not None
    assert data_requirement_registry_to_dict(result.registry) == payload


def test_canonical_registry_json_is_stable_across_key_order() -> None:
    registry = default_perp_data_requirement_registry()
    payload = data_requirement_registry_to_dict(registry)
    reordered = {
        "schema_version": payload["schema_version"],
        "requirements": {k: payload["requirements"][k] for k in reversed(list(payload["requirements"].keys()))},
    }

    result = data_requirement_registry_from_dict(reordered)
    assert result.accepted is True
    assert result.registry is not None
    assert canonical_data_requirement_registry_json(registry) == canonical_data_requirement_registry_json(
        result.registry
    )


def test_registry_digest_is_stable() -> None:
    registry = default_perp_data_requirement_registry()
    payload = data_requirement_registry_to_dict(registry)

    result = data_requirement_registry_from_dict(payload)
    assert result.accepted is True
    assert result.registry is not None
    assert data_requirement_registry_digest(registry) == data_requirement_registry_digest(result.registry)


def test_bist_leakage_in_registry_rejects_fail_closed() -> None:
    payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    payload["requirements"]["mark_price"]["historical_source"] = "Matriks"

    result = data_requirement_registry_from_dict(payload)
    assert result.accepted is False
    assert "data_requirement_registry:bist_scope_leakage" in result.rejection_reasons


def test_forbidden_live_private_order_scheduler_fields_reject() -> None:
    payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    payload["requirements"]["mark_price"]["scheduler"] = "enabled"
    payload["requirements"]["mark_price"]["private_api"] = "x"

    result = data_requirement_registry_from_dict(payload)
    assert result.accepted is False
    assert "data_requirement_registry:forbidden_field_scheduler" in result.rejection_reasons
    assert "data_requirement_registry:forbidden_field_private_api" in result.rejection_reasons


def test_generic_funding_semantics_rejected() -> None:
    payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    payload["requirements"]["funding_rate"]["funding_semantics"] = "generic"

    result = data_requirement_registry_from_dict(payload)
    assert result.accepted is False
    assert "data_requirement_registry:funding_semantics_ambiguous:funding_rate" in result.rejection_reasons


def test_generic_price_semantics_rejected() -> None:
    payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    payload["requirements"]["mark_price"]["price_semantics"] = "price"

    result = data_requirement_registry_from_dict(payload)
    assert result.accepted is False
    assert "data_requirement_registry:price_semantics_ambiguous:mark_price" in result.rejection_reasons


def test_order_book_missing_sequence_or_resync_policy_rejected() -> None:
    payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    payload["requirements"]["order_book"]["sequence_policy"] = ""
    payload["requirements"]["order_book"]["resync_policy"] = ""

    result = data_requirement_registry_from_dict(payload)
    assert result.accepted is False
    assert "data_requirement_registry:sequence_policy_missing" in result.rejection_reasons
    assert "data_requirement_registry:resync_policy_missing" in result.rejection_reasons


def test_fee_slippage_latency_zero_or_none_rejected() -> None:
    payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    payload["requirements"]["order_book"]["fee_assumption"] = "0"
    payload["requirements"]["order_book"]["slippage_assumption"] = "none"
    payload["requirements"]["order_book"]["latency_assumption"] = ""

    result = data_requirement_registry_from_dict(payload)
    assert result.accepted is False
    assert "data_requirement_registry:fee_assumption_invalid:order_book" in result.rejection_reasons
    assert "data_requirement_registry:slippage_assumption_invalid:order_book" in result.rejection_reasons
    assert "data_requirement_registry:latency_assumption_invalid:order_book" in result.rejection_reasons


def test_registry_payload_is_json_safe() -> None:
    payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    assert json.loads(json.dumps(payload)) == payload
