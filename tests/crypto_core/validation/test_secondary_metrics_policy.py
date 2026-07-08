"""Tests for the SM-2 secondary metrics policy artifact."""

from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation import secondary_metrics_policy as policy_module
from crypto_core.validation.secondary_metrics_policy import (
    SecondaryMetricsPolicyError,
    SecondaryMetricsPolicyStatus,
    build_secondary_metrics_policy,
    secondary_metrics_policy_digest,
    secondary_metrics_policy_to_dict,
)

_MODEL_REFERENCE = "crypto_core.execution.fill_pricer.FillPricer.mid_plus_half_spread_plus_size_impact.v1"
_MODEL_PARAMETERS_DIGEST = "a" * 64
_APPROVAL_DIGEST = "b" * 64
_REASON_PREFIX = "secondary_metrics_policy:"

_STRUCTURAL_FALSE_FLAGS = (
    "secondary_metrics_enforced",
    "trade_records_consumed",
    "episodes_consumed",
    "fills_consumed",
    "pnl_consumed",
    "comparator_invoked",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "private_api_ready",
    "live_api_called",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "scheduler_enabled",
    "auto_loop_enabled",
    "edge_proven",
    "profitability_proven",
)


class _LiarStr(str):
    """A string subclass rejected by exact string checks."""


def _rc(code: str) -> str:
    return f"{_REASON_PREFIX}{code}"


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _build(**overrides: object):
    payload: dict[str, object] = {
        "policy_id": "sm-policy-1",
        "correlation_id": "corr-1",
        "expected_fill_model_parameters_digest": _MODEL_PARAMETERS_DIGEST,
        "approved_hit_rate_floor": "0.500000000000000000",
        "approved_fill_rate_floor": "0.900000000000000000",
        "approved_slippage_ceiling_bps": "25.000000000000000000",
        "approved_min_decided_episode_count": 30,
        "approval_reference": "governance-approval-sm2-1",
        "approval_digest": _APPROVAL_DIGEST,
        "thresholds_approved": True,
        "metadata": {"purpose": "secondary metrics policy"},
    }
    payload.update(overrides)
    return build_secondary_metrics_policy(**payload)  # type: ignore[arg-type]


# --- 1. Public API / happy path -----------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert set(policy_module.__all__) == {
        "SecondaryMetricsPolicy",
        "SecondaryMetricsPolicyError",
        "SecondaryMetricsPolicyStatus",
        "build_secondary_metrics_policy",
        "secondary_metrics_policy_digest",
        "secondary_metrics_policy_to_dict",
    }


def test_happy_policy_ready() -> None:
    policy = _build()
    payload = secondary_metrics_policy_to_dict(policy)

    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_READY
    assert policy.ready is True
    assert policy.secondary_metrics_policy_ready is True
    assert policy.secondary_metrics_enforced is False
    assert policy.schema_version == "secondary-metrics-policy.v1"
    assert policy.policy_version == "secondary-metrics-policy.v1"
    assert policy.hit_rate_definition == "realized_pnl_positive_episode_over_decided_episodes.v1"
    assert policy.fill_rate_definition == "filled_quantity_over_intended_quantity_and_filled_episode_ratio.v1"
    assert policy.slippage_definition == "signed_bps_vs_expected_fill_reference_price.v1"
    assert policy.expected_fill_model_reference == _MODEL_REFERENCE
    assert policy.expected_fill_model_parameters_digest == _MODEL_PARAMETERS_DIGEST
    assert policy.decimal_policy == "decimal_quantized_scale_18_round_half_even_fraction_intermediates.v1"
    assert policy.decimal_scale == 18
    assert policy.decimal_rounding == "ROUND_HALF_EVEN"
    assert policy.fraction_intermediates_required is True
    assert policy.thresholds_approved is True
    assert policy.reason_codes == ()
    assert _is_hex64(policy.policy_digest)
    assert payload["status"] == "POLICY_READY"
    assert payload["policy_digest"] == secondary_metrics_policy_digest(policy)


def test_output_is_frozen() -> None:
    policy = _build()
    with pytest.raises(FrozenInstanceError):
        policy.ready = False  # type: ignore[misc]


# --- 2. Digest / serializer ---------------------------------------------------------------------------------


def test_repeated_build_deterministic() -> None:
    assert _build().policy_digest == _build().policy_digest


def test_serializer_excludes_self_digest_from_recompute() -> None:
    policy = _build()
    resealed = replace(policy, policy_digest="0" * 64)

    assert secondary_metrics_policy_digest(policy) == policy.policy_digest
    assert secondary_metrics_policy_digest(resealed) == policy.policy_digest


def test_serializer_matches_dataclass_fields() -> None:
    policy = _build()
    payload = secondary_metrics_policy_to_dict(policy)

    assert set(payload) == {field.name for field in fields(policy)}
    assert payload["status"] == policy.status.value
    assert payload["metadata"] == [["purpose", "secondary metrics policy"]]


def test_metadata_canonicalization_deterministic() -> None:
    first = _build(metadata={"b": "2", "a": "1"})
    second = _build(metadata={"a": "1", "b": "2"})
    changed = _build(metadata={"a": "1", "b": "3"})

    assert first.metadata == (("a", "1"), ("b", "2"))
    assert first.policy_digest == second.policy_digest
    assert changed.policy_digest != first.policy_digest


@pytest.mark.parametrize(
    "override",
    [
        {"approved_hit_rate_floor": "0.400000000000000000"},
        {"approved_fill_rate_floor": "0.800000000000000000"},
        {"approved_slippage_ceiling_bps": "30.000000000000000000"},
        {"approved_min_decided_episode_count": 31},
        {"expected_fill_model_parameters_digest": "c" * 64},
        {"secondary_metrics_enforced": True},
    ],
)
def test_every_policy_field_is_digest_bound(override: dict[str, object]) -> None:
    policy = _build()
    tampered = replace(policy, **override)
    assert secondary_metrics_policy_digest(tampered) != policy.policy_digest


# --- 3. Governance approval / threshold rejection -----------------------------------------------------------


def test_missing_approval_rejects() -> None:
    policy = _build(approval_reference=None, approval_digest=None)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert policy.ready is False
    assert _rc("approval_reference_missing") in policy.reason_codes
    assert _rc("approval_digest_invalid") in policy.reason_codes


def test_thresholds_approved_false_rejects() -> None:
    policy = _build(thresholds_approved=False)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("thresholds_not_approved") in policy.reason_codes
    assert policy.secondary_metrics_policy_ready is False


@pytest.mark.parametrize(
    ("field_name", "reason_code"),
    [
        ("approved_hit_rate_floor", "approved_hit_rate_floor_missing"),
        ("approved_fill_rate_floor", "approved_fill_rate_floor_missing"),
        ("approved_slippage_ceiling_bps", "approved_slippage_ceiling_missing"),
        ("approved_min_decided_episode_count", "approved_min_decided_episode_count_missing"),
    ],
)
def test_each_missing_threshold_rejects(field_name: str, reason_code: str) -> None:
    policy = _build(**{field_name: None})
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc(reason_code) in policy.reason_codes


@pytest.mark.parametrize("bad", ["abc", "NaN", "1e-3", "0.", ".5", ""])
def test_invalid_decimal_threshold_rejects(bad: str) -> None:
    policy = _build(approved_hit_rate_floor=bad)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("approved_value_invalid") in policy.reason_codes


@pytest.mark.parametrize("bad", ["1.000000000000000001", "-0.000000000000000001", "2"])
def test_hit_rate_floor_outside_rate_range_rejects(bad: str) -> None:
    policy = _build(approved_hit_rate_floor=bad)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("approved_value_invalid") in policy.reason_codes


@pytest.mark.parametrize("bad", ["1.000000000000000001", "-0", "2"])
def test_fill_rate_floor_outside_rate_range_rejects(bad: str) -> None:
    policy = _build(approved_fill_rate_floor=bad)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("approved_value_invalid") in policy.reason_codes


def test_slippage_ceiling_negative_rejects() -> None:
    policy = _build(approved_slippage_ceiling_bps="-0.000000000000000001")
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("approved_value_invalid") in policy.reason_codes


# --- 3b. Scale-18 canonical encoding (Codex P2: reject non-scale-18 approved thresholds) --------------------

_NON_SCALE_18_THRESHOLDS = (
    "0.5",
    "1",
    "1.0",
    "25",
    "25.0",
    "0.50000000000000000",  # 17 fractional digits
    "0.5000000000000000000",  # 19 fractional digits
)


@pytest.mark.parametrize("bad", _NON_SCALE_18_THRESHOLDS)
def test_non_scale_18_hit_rate_floor_rejects(bad: str) -> None:
    policy = _build(approved_hit_rate_floor=bad)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert policy.ready is False
    assert policy.secondary_metrics_policy_ready is False
    assert _rc("approved_value_invalid") in policy.reason_codes


@pytest.mark.parametrize("bad", _NON_SCALE_18_THRESHOLDS)
def test_non_scale_18_fill_rate_floor_rejects(bad: str) -> None:
    policy = _build(approved_fill_rate_floor=bad)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert policy.ready is False
    assert policy.secondary_metrics_policy_ready is False
    assert _rc("approved_value_invalid") in policy.reason_codes


@pytest.mark.parametrize("bad", _NON_SCALE_18_THRESHOLDS)
def test_non_scale_18_slippage_ceiling_rejects(bad: str) -> None:
    policy = _build(approved_slippage_ceiling_bps=bad)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert policy.ready is False
    assert policy.secondary_metrics_policy_ready is False
    assert _rc("approved_value_invalid") in policy.reason_codes


@pytest.mark.parametrize("field_name", ["approved_hit_rate_floor", "approved_fill_rate_floor"])
@pytest.mark.parametrize("bad", ["1", "25"])
def test_integer_looking_threshold_strings_reject(field_name: str, bad: str) -> None:
    policy = _build(**{field_name: bad})
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("approved_value_invalid") in policy.reason_codes


@pytest.mark.parametrize(
    "overrides",
    [
        {"approved_hit_rate_floor": "0.000000000000000000"},
        {"approved_hit_rate_floor": "1.000000000000000000"},
        {"approved_fill_rate_floor": "0.000000000000000000"},
        {"approved_fill_rate_floor": "1.000000000000000000"},
        {"approved_slippage_ceiling_bps": "0.000000000000000000"},
        {"approved_slippage_ceiling_bps": "25.000000000000000000"},
    ],
)
def test_scale_18_boundary_values_remain_ready(overrides: dict[str, object]) -> None:
    policy = _build(**overrides)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_READY
    assert policy.ready is True
    assert policy.reason_codes == ()


def test_rejected_non_canonical_threshold_never_ready() -> None:
    for bad in _NON_SCALE_18_THRESHOLDS:
        policy = _build(approved_hit_rate_floor=bad)
        assert policy.status is not SecondaryMetricsPolicyStatus.POLICY_READY
        assert policy.ready is False


def test_scale_18_rejection_digest_and_serializer_deterministic() -> None:
    first = _build(approved_hit_rate_floor="0.5")
    second = _build(approved_hit_rate_floor="0.5")

    assert first.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert first.policy_digest == second.policy_digest
    assert secondary_metrics_policy_digest(first) == first.policy_digest

    ready = _build()
    payload = secondary_metrics_policy_to_dict(ready)
    assert payload["policy_digest"] == secondary_metrics_policy_digest(ready)


@pytest.mark.parametrize("bad", [0, -1, True])
def test_min_decided_episode_count_below_one_rejects(bad: object) -> None:
    policy = _build(approved_min_decided_episode_count=bad)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("approved_value_invalid") in policy.reason_codes


def test_approval_reference_missing_rejects() -> None:
    policy = _build(approval_reference="")
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("approval_reference_missing") in policy.reason_codes


def test_approval_digest_invalid_rejects() -> None:
    policy = _build(approval_digest="abc")
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("approval_digest_invalid") in policy.reason_codes


# --- 4. Definition/model/decimal guardrails -----------------------------------------------------------------


def test_expected_fill_model_reference_wrong_rejects() -> None:
    policy = _build(expected_fill_model_reference="crypto_core.execution.fill_pricer.FillPricer.v2")
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("expected_fill_model_reference_invalid") in policy.reason_codes


def test_expected_fill_model_parameters_digest_invalid_rejects() -> None:
    policy = _build(expected_fill_model_parameters_digest="A" * 64)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("expected_fill_model_parameters_digest_invalid") in policy.reason_codes


@pytest.mark.parametrize(
    "override",
    [
        {"decimal_policy": "decimal_quantized_scale_9_round_half_even_fraction_intermediates.v1"},
        {"decimal_scale": 9},
        {"decimal_rounding": "ROUND_HALF_UP"},
        {"fraction_intermediates_required": False},
    ],
)
def test_decimal_policy_mismatch_rejects(override: dict[str, object]) -> None:
    policy = _build(**override)
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("decimal_policy_mismatch") in policy.reason_codes


def test_definition_mismatch_rejects() -> None:
    policy = _build(hit_rate_definition="wins_over_trades.v1")
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("definition_mismatch") in policy.reason_codes


# --- 5. IDs / metadata / forbidden tokens -------------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"policy_id": "  "},
        {"policy_id": _LiarStr("policy-1")},
        {"correlation_id": "corr\t1"},
    ],
)
def test_malformed_ids_raise(override: dict[str, object]) -> None:
    with pytest.raises(SecondaryMetricsPolicyError):
        _build(**override)


@pytest.mark.parametrize(
    "override",
    [
        {"policy_id": 123},
        {"thresholds_approved": "yes"},
        {"metadata": {"ok": 1}},
    ],
)
def test_wrong_type_caller_input_raises(override: dict[str, object]) -> None:
    with pytest.raises(SecondaryMetricsPolicyError):
        _build(**override)


@pytest.mark.parametrize(
    "token",
    [
        "crypto_core.execution.paper_adapter",
        "crypto_core.execution.fill_pricer",
    ],
)
def test_metadata_unsafe_token_rejects(token: str) -> None:
    policy = _build(metadata={"source": token})
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("scope_violation") in policy.reason_codes


@pytest.mark.parametrize("token", ["BIST", "KAP", "Matriks", "Borsa"])
def test_bist_kap_matriks_borsa_token_rejected(token: str) -> None:
    policy = _build(metadata={"venue": token})
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("bist_token_forbidden") in policy.reason_codes


@pytest.mark.parametrize("token", ["time.time_ns", "datetime.now", "server_time"])
def test_clock_token_rejected(token: str) -> None:
    policy = _build(metadata={"source": token})
    assert policy.status is SecondaryMetricsPolicyStatus.POLICY_REJECTED
    assert _rc("clock_token_forbidden") in policy.reason_codes


def test_reason_code_prefix_consistency() -> None:
    policy = _build(thresholds_approved=False, approval_digest="bad")
    assert policy.reason_codes
    assert all(reason.startswith(_REASON_PREFIX) for reason in policy.reason_codes)


# --- 6. Non-claims / policy-only ----------------------------------------------------------------------------


def test_structural_false_non_claim_flags() -> None:
    policy = _build()
    payload = secondary_metrics_policy_to_dict(policy)

    assert payload["paper_only"] is True
    assert payload["policy_only"] is True
    for flag in _STRUCTURAL_FALSE_FLAGS:
        assert payload[flag] is False

    tampered = replace(policy, prdv4_stage4_complete=True)
    assert secondary_metrics_policy_digest(tampered) != policy.policy_digest


def test_no_governance_numbers_hardcoded_as_defaults() -> None:
    signature = inspect.signature(build_secondary_metrics_policy)
    for name in (
        "approved_hit_rate_floor",
        "approved_fill_rate_floor",
        "approved_slippage_ceiling_bps",
        "approved_min_decided_episode_count",
        "approval_reference",
        "approval_digest",
        "expected_fill_model_parameters_digest",
    ):
        assert signature.parameters[name].default is None
    assert signature.parameters["thresholds_approved"].default is False


def test_policy_only_no_episode_fill_or_pnl_objects_accepted_or_consumed() -> None:
    signature = inspect.signature(build_secondary_metrics_policy)
    forbidden_params = {"episode", "episodes", "fill", "fills", "pnl", "realized_pnl", "comparator_result"}
    assert forbidden_params.isdisjoint(signature.parameters)

    source = Path(policy_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_names = {
        "PaperEndToEndEpisode",
        "PaperFillSimulationResult",
        "PaperRealizedPnlEvent",
        "compare_stage4",
        "Stage4PaperSummary",
        "Stage4BacktestBaseline",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(name in node.module for name in ("episode", "fill", "pnl", "stage4_comparator"))
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(name in alias.name for name in ("episode", "fill", "pnl", "stage4_comparator"))
        if isinstance(node, ast.Name):
            assert node.id not in forbidden_names
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_names
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_names


# --- 7. AST forbidden surface -------------------------------------------------------------------------------


def test_source_has_no_forbidden_imports_or_calls() -> None:
    source = Path(policy_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "time",
        "datetime",
        "random",
        "secrets",
        "uuid",
        "socket",
        "requests",
        "urllib",
        "httpx",
        "aiohttp",
        "threading",
        "asyncio",
        "multiprocessing",
        "subprocess",
        "os",
        "pathlib",
        "shutil",
        "sqlite3",
        "duckdb",
        "crypto_core.service",
        "crypto_core.execution",
        "crypto_core.venue",
        "crypto_core.runtime",
        "crypto_core.orchestrator",
        "crypto_core.temporal",
        "crypto_core.session",
        "crypto_core.data",
        "crypto_core.portfolio",
        "crypto_core.validation.stage4_comparator",
    )
    forbidden_call_names = {
        "open",
        "Path",
        "float",
        "compare_stage4",
        "Stage4PaperSummary",
        "Stage4BacktestBaseline",
        "FillPricer",
        "FillPricerConfig",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == module or alias.name.startswith(f"{module}.") for module in forbidden_modules
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(
                node.module == module or node.module.startswith(f"{module}.") for module in forbidden_modules
            )
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names


def test_literal_expected_fill_model_reference_has_no_execution_import_or_call() -> None:
    policy = _build()
    source = Path(policy_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert policy.expected_fill_model_reference == _MODEL_REFERENCE
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not node.module.startswith("crypto_core.execution")
        if isinstance(node, ast.Import):
            assert all(not alias.name.startswith("crypto_core.execution") for alias in node.names)
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in {"FillPricer", "FillPricerConfig"}
            if isinstance(function, ast.Attribute):
                assert function.attr not in {"FillPricer", "FillPricerConfig", "price_fill"}
