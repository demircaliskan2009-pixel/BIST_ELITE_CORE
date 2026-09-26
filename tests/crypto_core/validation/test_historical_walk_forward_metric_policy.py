"""Tests for the governed historical walk-forward metric policy (HISTORICAL_WALK_FORWARD_METRICS_V1)."""

from __future__ import annotations

import ast
import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.historical_walk_forward_metric_policy as policy_module
from crypto_core.validation.edge_artifact_core import EDGE_STRUCTURAL_NON_CLAIM_FLAGS, edge_canonical_json
from crypto_core.validation.historical_walk_forward_metric_policy import (
    HISTORICAL_WALK_FORWARD_METRIC_POLICY_NON_CLAIM_FLAGS,
    HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1,
    HistoricalWalkForwardMetricNumericPolicy,
    HistoricalWalkForwardMetricPolicy,
    HistoricalWalkForwardMetricPolicyError,
    build_historical_walk_forward_metric_policy,
    historical_walk_forward_metric_policy_digest,
    historical_walk_forward_metric_policy_from_payload,
    historical_walk_forward_metric_policy_payload_is_well_formed,
    historical_walk_forward_metric_policy_to_dict,
    verify_historical_walk_forward_metric_policy,
)

_PREFIX = "historical_walk_forward_metric_policy"
INT64_MAX = 9223372036854775807


def policy(**overrides: str) -> HistoricalWalkForwardMetricPolicy:
    arguments = {"policy_id": "walk-forward-metric-policy-1", "policy_version": "1"}
    arguments.update(overrides)
    return build_historical_walk_forward_metric_policy(**arguments)


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _reseal(value: HistoricalWalkForwardMetricPolicy, **changes: object) -> HistoricalWalkForwardMetricPolicy:
    changed = replace(value, **changes)
    return replace(changed, policy_digest=historical_walk_forward_metric_policy_digest(changed))


def _flag_names() -> set[str]:
    return {name for name, _ in HISTORICAL_WALK_FORWARD_METRIC_POLICY_NON_CLAIM_FLAGS}


# --- canonical V1 -------------------------------------------------------------------------------------------------------


def test_canonical_policy_is_deterministic_and_carries_the_governed_v1_values() -> None:
    first, second = policy(), policy()
    assert first == second
    assert first.policy_digest == second.policy_digest == historical_walk_forward_metric_policy_digest(first)
    assert edge_canonical_json(historical_walk_forward_metric_policy_to_dict(first)) == edge_canonical_json(
        historical_walk_forward_metric_policy_to_dict(second)
    )
    assert (first.calendar, first.bucket_frequency, first.day_ns) == ("UTC", "1d_utc", 86_400_000_000_000)
    assert (
        first.in_sample_duration_days,
        first.out_of_sample_duration_days,
        first.window_stride_days,
        first.embargo_days,
    ) == (365, 90, 90, 0)
    assert first.min_daily_return_count == 2
    assert (first.risk_free_policy, first.risk_free_policy_id, first.risk_free_daily_return) == (
        "constant_zero_daily_review_only",
        "constant_zero_daily_review_only.v1",
        "0.000000000000000000",
    )
    assert first.sharpe_stddev_policy_id == "sample_stddev_n_minus_1.v1"
    assert (first.sharpe_annualization_factor, first.sharpe_annualization_formula) == (365, "daily_sharpe * sqrt(365)")
    assert first.window_count_rule_id == "generic_one_or_more_windows_no_fixed_count.v1"
    assert first.numeric_policy == HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1
    assert (first.numeric_policy.decimal_scale, first.numeric_policy.max_decimal_text_length) == (18, 60)
    assert first.numeric_policy.near_zero_epsilon_policy_id == "none.v1"


def test_policy_round_trips_and_re_proves() -> None:
    value = policy()
    payload = historical_walk_forward_metric_policy_to_dict(value)
    assert historical_walk_forward_metric_policy_payload_is_well_formed(payload)
    assert historical_walk_forward_metric_policy_from_payload(json.loads(edge_canonical_json(payload))) == value
    verification = verify_historical_walk_forward_metric_policy(value)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == value.policy_digest
    assert historical_walk_forward_metric_policy_from_payload(json.loads(verification.canonical_json)) == value


def test_caller_identity_text_is_digest_bound() -> None:
    assert policy(policy_id="other").policy_digest != policy().policy_digest
    assert policy(policy_version="2").policy_digest != policy().policy_digest


def _changed(value: object) -> object:
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if type(value) is str:
        return value + "x"
    raise AssertionError(type(value))


def test_every_load_bearing_policy_field_changes_the_digest() -> None:
    base = policy()
    base_digest = historical_walk_forward_metric_policy_digest(base)
    checked = 0
    for item in fields(HistoricalWalkForwardMetricPolicy):
        if item.name in ("policy_digest", "numeric_policy"):
            continue
        changed = replace(base, **{item.name: _changed(getattr(base, item.name))})
        assert historical_walk_forward_metric_policy_digest(changed) != base_digest, item.name
        checked += 1
    for item in fields(HistoricalWalkForwardMetricNumericPolicy):
        numeric = replace(base.numeric_policy, **{item.name: _changed(getattr(base.numeric_policy, item.name))})
        assert historical_walk_forward_metric_policy_digest(replace(base, numeric_policy=numeric)) != base_digest
        checked += 1
    assert checked == len(fields(HistoricalWalkForwardMetricPolicy)) - 2 + len(
        fields(HistoricalWalkForwardMetricNumericPolicy)
    )


@pytest.mark.parametrize(
    "change",
    [
        {"in_sample_duration_days": 364},
        {"out_of_sample_duration_days": 91},
        {"window_stride_days": 30},
        {"embargo_days": 1},
        {"day_ns": 3_600_000_000_000},
        {"min_daily_return_count": 1},
        {"sharpe_annualization_factor": 252},
        {"risk_free_daily_return": "0.000100000000000000"},
        {"sharpe_stddev_policy_id": "population_stddev_n.v1"},
        {"sharpe_zero_variance_rule_id": "epsilon.v1"},
        {"profit_factor_undefined_rule_id": "infinity.v1"},
        {"window_count_rule_id": "exactly_sixteen_windows.v1"},
        {"calendar": "EXCHANGE_LOCAL"},
    ],
)
def test_an_unsupported_policy_identity_never_verifies_even_when_resealed(change: dict[str, object]) -> None:
    forged = _reseal(policy(), **change)
    verification = verify_historical_walk_forward_metric_policy(forged)
    assert verification.intact is False
    assert {_code(f"field_mismatch:{name}") for name in change} <= set(verification.reason_codes)


def test_an_unsupported_numeric_identity_never_verifies() -> None:
    base = policy()
    for change in ({"decimal_scale": 8}, {"sqrt_id": "decimal_precision_80.v1"}, {"max_decimal_text_length": 61}):
        forged = _reseal(base, numeric_policy=replace(base.numeric_policy, **change))
        verification = verify_historical_walk_forward_metric_policy(forged)
        assert verification.intact is False
        assert _code("field_mismatch:numeric_policy") in verification.reason_codes


def test_a_tampered_field_with_a_stale_digest_is_detected() -> None:
    tampered = replace(policy(), in_sample_duration_days=364)
    verification = verify_historical_walk_forward_metric_policy(tampered)
    assert verification.intact is False
    assert _code("self_digest_mismatch") in verification.reason_codes


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"policy_id": ""}, "policy_id_invalid"),
        ({"policy_id": " padded"}, "policy_id_invalid"),
        ({"policy_id": "x" * 257}, "policy_id_invalid"),
        ({"policy_id": "tab\tinside"}, "policy_id_invalid"),
        ({"policy_id": 7}, "policy_id_invalid"),
        ({"policy_id": None}, "policy_id_invalid"),
        ({"policy_version": ""}, "policy_version_invalid"),
        ({"policy_id": "bist-walk-forward"}, "bist_scope_leakage:policy_id"),
        ({"policy_id": "live-walk-forward"}, "forbidden_scope_token:policy_id"),
        ({"policy_version": "scheduler-1"}, "forbidden_scope_token:policy_version"),
    ],
)
def test_malformed_identity_text_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(HistoricalWalkForwardMetricPolicyError) as raised:
        policy(**overrides)  # type: ignore[arg-type]
    assert str(raised.value) == _code(code)


def _payload(**changes: object) -> dict[str, object]:
    payload = historical_walk_forward_metric_policy_to_dict(policy())
    payload.update(changes)
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "policy",
        {},
        _payload(unexpected=True),
        {key: value for key, value in _payload().items() if key != "embargo_days"},
        _payload(in_sample_duration_days=True),
        _payload(in_sample_duration_days="365"),
        _payload(in_sample_duration_days=-1),
        _payload(in_sample_duration_days=INT64_MAX + 1),
        _payload(policy_id=7),
        _payload(edge_proven="false"),
        _payload(numeric_policy=None),
        _payload(numeric_policy={"decimal_scale": 18}),
        _payload(
            numeric_policy={
                **historical_walk_forward_metric_policy_to_dict(policy())["numeric_policy"],
                "decimal_scale": 1.5,
            }
        ),  # type: ignore[dict-item]
    ],
)
def test_strict_parser_refuses_every_malformed_payload(payload: object) -> None:
    assert historical_walk_forward_metric_policy_payload_is_well_formed(payload) is False
    with pytest.raises(Exception):  # noqa: B017, PT011 - any refusal is correct; acceptance is the defect
        historical_walk_forward_metric_policy_from_payload(payload)


class _Unserializable:
    pass


@pytest.mark.parametrize(
    "artifact",
    [
        None,
        0,
        "policy",
        b"policy",
        {"policy_id": "x"},
        object(),
        _Unserializable(),
        replace(policy(), policy_id=None),  # type: ignore[arg-type]
        replace(policy(), numeric_policy=None),  # type: ignore[arg-type]
        replace(policy(), numeric_policy=object()),  # type: ignore[arg-type]
        replace(policy(), day_ns=True),
        replace(policy(), day_ns=INT64_MAX + 1),
        replace(policy(), in_sample_duration_days=float("inf")),  # type: ignore[arg-type]
        replace(policy(), policy_id="bist-leak"),
        replace(policy(), edge_proven=True),
        replace(policy(), performance_metrics_computed=True),
    ],
)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify_historical_walk_forward_metric_policy(artifact)
    assert verification.intact is False
    assert verification.reason_codes


def test_non_claim_flags_are_structural_defaults() -> None:
    value = policy()
    names = _flag_names()
    assert {name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS} <= names
    assert {"pbo_passed", "stress_passed", "performance_metrics_computed", "admission_decided"} <= names
    for name, expected in HISTORICAL_WALK_FORWARD_METRIC_POLICY_NON_CLAIM_FLAGS:
        assert getattr(value, name) is expected
    assert value.paper_only is True
    assert [name for name, expected in HISTORICAL_WALK_FORWARD_METRIC_POLICY_NON_CLAIM_FLAGS if expected] == [
        "paper_only"
    ]


# --- purity -------------------------------------------------------------------------------------------------------------


def _tree() -> ast.Module:
    return ast.parse(Path(policy_module.__file__).read_text(encoding="utf-8"))


def test_policy_module_is_pure_and_float_free() -> None:
    tree = _tree()
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and type(node.value) is float]
    modules = {
        alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }
    modules |= {
        node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert modules <= {"__future__", "collections", "dataclasses", "enum", "crypto_core"}
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert {name for name in imported if name.startswith("crypto_core")} == {
        "crypto_core.validation.edge_artifact_core"
    }
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"float", "open", "eval"}
    ]
    assert "bist_core" not in Path(policy_module.__file__).read_text(encoding="utf-8")
