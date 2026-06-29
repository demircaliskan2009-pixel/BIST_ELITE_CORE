"""Tests for the deterministic paper-vs-backtest comparison-methodology snapshot."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_sharpe_evidence as sharpe_module
from crypto_core.validation import paper_vs_backtest_methodology as methodology_module
from crypto_core.validation.paper_vs_backtest_methodology import (
    PaperVsBacktestMethodologyError,
    PaperVsBacktestMethodologyStatus,
    build_paper_vs_backtest_methodology,
    paper_vs_backtest_methodology_digest,
    paper_vs_backtest_methodology_to_dict,
)

_RETENTION = "0.500000000000000000"
_RISK_FREE_POLICY_ID = "constant_zero_daily_review_only.v1"


class _LiarStr(str):
    """A string subclass rejected by exact string checks."""


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _build(**overrides: object):
    payload: dict[str, object] = {
        "methodology_id": "methodology-1",
        "correlation_id": "corr-1",
        "sharpe_retention_ratio": _RETENTION,
        "min_duration_days": 30,
        "risk_free_policy_id": _RISK_FREE_POLICY_ID,
        "metadata": {"purpose": "paper vs backtest methodology"},
    }
    payload.update(overrides)
    return build_paper_vs_backtest_methodology(**payload)  # type: ignore[arg-type]


# --- 1. Public API / duplicate ------------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert set(methodology_module.__all__) == {
        "PaperVsBacktestMethodology",
        "PaperVsBacktestMethodologyError",
        "PaperVsBacktestMethodologyStatus",
        "build_paper_vs_backtest_methodology",
        "paper_vs_backtest_methodology_digest",
        "paper_vs_backtest_methodology_to_dict",
    }


def test_no_equivalent_artifact_exists() -> None:
    validation_dir = Path(methodology_module.__file__).parent
    builders = sorted(
        path.name
        for path in validation_dir.glob("*.py")
        if "build_paper_vs_backtest_methodology" in path.read_text(encoding="utf-8")
    )
    assert builders == ["paper_vs_backtest_methodology.py"]


def test_output_is_frozen() -> None:
    result = _build()
    with pytest.raises(FrozenInstanceError):
        result.ready = False  # type: ignore[misc]


# --- 2. Happy READY ----------------------------------------------------------------------------------------


def test_happy_path_methodology_snapshot() -> None:
    result = _build()
    payload = paper_vs_backtest_methodology_to_dict(result)

    assert result.status is PaperVsBacktestMethodologyStatus.READY
    assert result.ready is True
    assert result.paper_only is True
    assert result.methodology_snapshot is True
    assert result.policy_declared is True
    assert result.comparison_basis == "paper_vs_backtest_sharpe_retention.v1"
    assert result.enforced_guardrail_policy == "sharpe_retention_and_min_duration_only.v1"
    assert result.secondary_guardrail_policy == "declared_not_enforced_review_only.v1"
    assert result.sharpe_retention_ratio == _RETENTION
    assert result.min_duration_days == 30
    assert result.risk_free_policy_id == _RISK_FREE_POLICY_ID
    assert result.annualization_factor == 365
    assert result.annualization_policy == "daily_utc_365_review_only"
    assert result.stddev_policy == "sample_stddev_n_minus_1.v1"
    assert result.decimal_policy == "decimal_quantized_scale_18_round_half_even_internal_precision_80.v1"
    assert result.decimal_scale == 18
    assert result.decimal_rounding == "ROUND_HALF_EVEN"
    assert result.decimal_internal_precision == 80
    assert result.reason_codes == ()
    assert _is_hex64(result.methodology_digest)
    assert payload["status"] == "READY"
    assert payload["methodology_digest"] == paper_vs_backtest_methodology_digest(result)


def test_only_sharpe_retention_and_duration_enforced() -> None:
    result = _build()

    assert result.hit_rate_guardrail_policy == "declared_not_enforced_review_only.v1"
    assert result.fill_rate_guardrail_policy == "declared_not_enforced_review_only.v1"
    assert result.slippage_guardrail_policy == "declared_not_enforced_review_only.v1"
    assert result.drawdown_guardrail_policy == "declared_not_enforced_review_only.v1"
    assert result.hit_rate_floor_enforced is False
    assert result.fill_rate_floor_enforced is False
    assert result.slippage_ceiling_enforced is False
    assert result.drawdown_ceiling_enforced is False


def test_consistency_anchor_matches_merged_sharpe_methodology() -> None:
    # The pinned policy constants must equal what the merged paper_sharpe_evidence artifact computes under, so a
    # later comparison can prove the paper Sharpe used this exact methodology.
    result = _build()
    assert result.risk_free_policy_id == sharpe_module._RISK_FREE_POLICY_ID  # noqa: SLF001
    assert result.annualization_factor == sharpe_module._ANNUALIZATION_FACTOR  # noqa: SLF001
    assert result.annualization_policy == sharpe_module._ANNUALIZATION_POLICY  # noqa: SLF001
    assert result.stddev_policy == sharpe_module._STDDEV_POLICY  # noqa: SLF001
    assert result.decimal_policy == sharpe_module._DECIMAL_POLICY  # noqa: SLF001
    assert result.decimal_scale == sharpe_module._DECIMAL_SCALE  # noqa: SLF001
    assert result.decimal_rounding == sharpe_module._DECIMAL_ROUNDING  # noqa: SLF001
    assert result.decimal_internal_precision == sharpe_module._DECIMAL_INTERNAL_PRECISION  # noqa: SLF001


# --- 3. Governance validation ------------------------------------------------------------------------------


def test_unapproved_risk_free_policy_raises() -> None:
    with pytest.raises(PaperVsBacktestMethodologyError, match="risk_free_policy_unapproved"):
        _build(risk_free_policy_id="constant_zero_daily_review_only.v2")


@pytest.mark.parametrize("bad", ["0.5", "0.50000000000000000", "1", "abc", "0.5000000000000000000"])
def test_malformed_retention_raises(bad: str) -> None:
    with pytest.raises(PaperVsBacktestMethodologyError, match="sharpe_retention_ratio_invalid"):
        _build(sharpe_retention_ratio=bad)


def test_non_string_retention_raises() -> None:
    with pytest.raises(PaperVsBacktestMethodologyError, match="sharpe_retention_ratio_invalid"):
        _build(sharpe_retention_ratio=0.5)


@pytest.mark.parametrize("value", ["0.600000000000000000", "0.400000000000000000"])
def test_retention_in_range_but_not_approved_rejects(value: str) -> None:
    result = _build(sharpe_retention_ratio=value)
    assert result.status is PaperVsBacktestMethodologyStatus.REJECTED
    assert result.ready is False
    assert "paper_vs_backtest_methodology:sharpe_retention_ratio_not_approved" in result.reason_codes


@pytest.mark.parametrize("value", ["2.000000000000000000", "-0.500000000000000000"])
def test_retention_out_of_range_rejects(value: str) -> None:
    result = _build(sharpe_retention_ratio=value)
    assert result.status is PaperVsBacktestMethodologyStatus.REJECTED
    assert "paper_vs_backtest_methodology:sharpe_retention_ratio_out_of_range" in result.reason_codes
    assert "paper_vs_backtest_methodology:sharpe_retention_ratio_not_approved" in result.reason_codes


def test_non_int_min_duration_raises() -> None:
    with pytest.raises(PaperVsBacktestMethodologyError, match="min_duration_days_invalid"):
        _build(min_duration_days="30")
    with pytest.raises(PaperVsBacktestMethodologyError, match="min_duration_days_invalid"):
        _build(min_duration_days=True)


@pytest.mark.parametrize("days", [29, 31, 0])
def test_min_duration_not_approved_rejects(days: int) -> None:
    result = _build(min_duration_days=days)
    assert result.status is PaperVsBacktestMethodologyStatus.REJECTED
    assert "paper_vs_backtest_methodology:min_duration_days_not_approved" in result.reason_codes


def test_rejected_snapshot_is_digest_bound_and_not_ready() -> None:
    result = _build(min_duration_days=29)
    payload = paper_vs_backtest_methodology_to_dict(result)
    assert payload["status"] == "REJECTED"
    assert payload["ready"] is False
    assert payload["methodology_digest"] == paper_vs_backtest_methodology_digest(result)
    assert result.comparison_ready is False
    assert result.prdv4_stage4_complete is False


# --- 4. Digest / provenance --------------------------------------------------------------------------------


def test_repeated_build_deterministic() -> None:
    assert _build().methodology_digest == _build().methodology_digest


def test_metadata_changes_digest_and_is_order_independent() -> None:
    first = _build(metadata={"b": "2", "a": "1"})
    second = _build(metadata={"a": "1", "b": "2"})
    changed = _build(metadata={"a": "1", "b": "3"})

    assert first.methodology_digest == second.methodology_digest
    assert changed.methodology_digest != first.methodology_digest


def test_digest_excludes_only_self_digest() -> None:
    result = _build()
    assert paper_vs_backtest_methodology_digest(result) == result.methodology_digest
    resealed = replace(result, methodology_digest="0" * 64)
    assert paper_vs_backtest_methodology_digest(resealed) == result.methodology_digest


def test_serializer_matches_dataclass_fields() -> None:
    result = _build()
    payload = paper_vs_backtest_methodology_to_dict(result)
    dataclass_field_names = {field.name for field in fields(result)}

    assert set(payload) == dataclass_field_names
    assert payload["status"] == result.status.value
    assert payload["metadata"] == [["purpose", "paper vs backtest methodology"]]


@pytest.mark.parametrize(
    "override",
    [
        {"sharpe_retention_ratio": "0.250000000000000000"},
        {"min_duration_days": 45},
        {"annualization_factor": 252},
        {"hit_rate_floor_enforced": True},
        {"comparison_ready": True},
        {"decimal_scale": 9},
    ],
)
def test_every_policy_field_is_digest_bound(override: dict[str, object]) -> None:
    result = _build()
    tampered = replace(result, **override)
    assert paper_vs_backtest_methodology_digest(tampered) != result.methodology_digest


def test_inputs_not_mutated() -> None:
    metadata = {"b": "2", "a": "1"}
    _build(metadata=metadata)
    assert metadata == {"b": "2", "a": "1"}


# --- 5. IDs / metadata -------------------------------------------------------------------------------------


def test_empty_and_subclass_ids_raise() -> None:
    with pytest.raises(PaperVsBacktestMethodologyError, match="methodology_id_invalid"):
        _build(methodology_id="  ")
    with pytest.raises(PaperVsBacktestMethodologyError, match="correlation_id_invalid"):
        _build(correlation_id=_LiarStr("corr-1"))
    with pytest.raises(PaperVsBacktestMethodologyError, match="risk_free_policy_id_invalid"):
        _build(risk_free_policy_id="")


def test_control_character_id_raises() -> None:
    with pytest.raises(PaperVsBacktestMethodologyError, match="methodology_id_invalid"):
        _build(methodology_id="method\t1")


def test_malformed_metadata_raises() -> None:
    with pytest.raises(PaperVsBacktestMethodologyError, match="metadata_malformed"):
        _build(metadata={"ok": 1})


@pytest.mark.parametrize(
    "override",
    [
        {"methodology_id": "live-methodology"},
        {"correlation_id": "shadow-corr"},
        {"metadata": {"path": "crypto_core.execution.paper_adapter"}},
        {"metadata": {"venue": "BIST"}},
        {"metadata": {"source": "time.time_ns"}},
        {"metadata": {"source": "datetime.now"}},
    ],
)
def test_forbidden_scope_and_clock_tokens_raise(override: dict[str, object]) -> None:
    with pytest.raises(PaperVsBacktestMethodologyError):
        _build(**override)


def test_metadata_is_copied_and_frozen() -> None:
    result = _build()
    payload = paper_vs_backtest_methodology_to_dict(result)
    assert payload["metadata"] == [["purpose", "paper vs backtest methodology"]]
    with pytest.raises(FrozenInstanceError):
        result.metadata = ()  # type: ignore[misc]


# --- 6. Non-overclaim --------------------------------------------------------------------------------------


def test_non_overclaim_flags_are_false_and_digest_bound() -> None:
    result = _build()
    payload = paper_vs_backtest_methodology_to_dict(result)

    assert payload["paper_only"] is True
    assert payload["methodology_snapshot"] is True
    assert payload["policy_declared"] is True
    for flag in (
        "hit_rate_floor_enforced",
        "fill_rate_floor_enforced",
        "slippage_ceiling_enforced",
        "drawdown_ceiling_enforced",
        "comparison_ready",
        "paper_vs_backtest_comparison_ready",
        "comparison_performed",
        "stage4_comparator_invoked",
        "thirty_day_gate_satisfied",
        "thirty_day_gate_decided",
        "prdv4_stage4_complete",
        "operational_readiness",
        "live_ready",
        "shadow_ready",
        "deribit_ready",
        "profitability_proven",
        "edge_proven",
        "edge_identity_proven",
        "production_execution",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
        "private_api_ready",
        "real_wall_clock_used",
        "real_account_equity_used",
        "real_capital_used",
    ):
        assert payload[flag] is False
    for forbidden_key in ("compare_stage4", "Stage4PaperSummary", "Stage4BacktestBaseline", "paper_sharpe"):
        assert forbidden_key not in payload

    tampered = replace(result, prdv4_stage4_complete=True)
    assert paper_vs_backtest_methodology_digest(tampered) != result.methodology_digest


# --- 7. AST forbidden surface ------------------------------------------------------------------------------


def test_source_has_no_forbidden_runtime_or_stage4_execution_surfaces() -> None:
    source = Path(methodology_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "math",
        "numpy",
        "pandas",
        "time",
        "datetime",
        "random",
        "secrets",
        "uuid",
        "socket",
        "requests",
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
