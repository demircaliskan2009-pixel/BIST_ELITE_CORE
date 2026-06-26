"""Tests for the paper return-series methodology snapshot.

This is the first split artifact for section 10.4.4. It defines the daily UTC paper return-series methodology
only; it must not compute returns, Sharpe, a 30-day gate decision, or invoke the Stage-4 comparator.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_return_series_methodology as methodology_module
from crypto_core.validation.paper_return_series_methodology import (
    PaperReturnSeriesMethodologyError,
    PaperReturnSeriesMethodologyStatus,
    build_paper_return_series_methodology,
    paper_return_series_methodology_digest,
    paper_return_series_methodology_to_dict,
)

_MODULE_PATH = Path("src/crypto_core/validation/paper_return_series_methodology.py")


class _LiarStr(str):
    """A str subclass that lies about equality; exact type checks must reject it."""

    def __eq__(self, other: object) -> bool:  # noqa: D401 - test double
        return True

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


def _build(**overrides: object):
    payload: dict[str, object] = {
        "methodology_id": "paper-return-methodology-1",
        "correlation_id": "corr-methodology-1",
        "mtm_policy_id": "mtm-policy-1",
        "fee_policy_id": "fee-policy-1",
        "funding_policy_id": "funding-policy-1",
        "mark_policy_id": "mark-policy-1",
        "exposure_policy_id": "exposure-policy-1",
        "liquidation_policy_id": "liquidation-policy-1",
        "risk_free_policy_id": "risk-free-policy-1",
        "metadata": {"purpose": "daily utc paper methodology"},
    }
    payload.update(overrides)
    return build_paper_return_series_methodology(**payload)  # type: ignore[arg-type]


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def test_happy_path_builds_methodology_only_snapshot() -> None:
    methodology = _build()
    payload = paper_return_series_methodology_to_dict(methodology)

    assert methodology.status is PaperReturnSeriesMethodologyStatus.READY
    assert methodology.ready is True
    assert methodology.schema_version == "paper-return-series-methodology.v1"
    assert methodology.calendar == "UTC"
    assert methodology.bucket_frequency == "1d_utc"
    assert methodology.bucket_duration_ns == 86_400_000_000_000
    assert methodology.required_consecutive_bucket_count == 30
    assert methodology.duration_sufficiency_assessed is False
    assert methodology.sample_sufficiency_assessed is False
    assert methodology.return_basis == "normalized_paper_equity_index"
    assert methodology.return_value_kind == "unitless_decimal_return"
    assert methodology.normalized_index_start == "1"
    assert methodology.annualization_policy == "daily_utc_365_review_only"
    assert methodology.annualization_factor == 365
    assert methodology.paper_sharpe_policy == "deferred_not_computed"
    assert methodology.missing_policy_input_status == "BLOCKED"
    assert methodology.sparse_window_status == "BLOCKED"
    assert methodology.insufficient_sample_status == "BLOCKED"
    assert methodology.no_trade_status == "NOT_COMPUTABLE"
    assert methodology.zero_variance_status == "NOT_COMPUTABLE"
    assert methodology.methodology_mismatch_status == "BLOCKED"
    assert methodology.fee_policy_required is True
    assert methodology.funding_policy_required is True
    assert methodology.mark_policy_required is True
    assert methodology.exposure_policy_required is True
    assert methodology.liquidation_policy_required is True
    assert _is_hex64(methodology.methodology_digest)
    assert payload["status"] == "READY"
    assert payload["metadata"] == [["purpose", "daily utc paper methodology"]]
    assert payload["methodology_digest"] == paper_return_series_methodology_digest(methodology)


def test_snapshot_has_no_return_series_sharpe_gate_or_stage4_claim() -> None:
    payload = paper_return_series_methodology_to_dict(_build())

    assert payload["return_series_computed"] is False
    assert payload["daily_returns_computed"] is False
    assert payload["sharpe_computed"] is False
    assert payload["paper_sharpe_computed"] is False
    assert payload["thirty_day_gate_satisfied"] is False
    assert payload["thirty_day_gate_decided"] is False
    assert payload["comparison_ready"] is False
    assert payload["stage4_comparator_invoked"] is False
    assert payload["prdv4_stage4_complete"] is False
    assert "daily_returns" not in payload
    assert "paper_sharpe" not in payload
    assert "return_series" not in payload
    assert "thirty_day_gate_decision" not in payload
    assert "Stage4PaperSummary" not in payload


def test_non_overclaim_flags_are_false_and_digest_bound() -> None:
    methodology = _build()
    payload = paper_return_series_methodology_to_dict(methodology)
    false_flags = {
        "real_account_equity_used",
        "real_capital_used",
        "live_ready",
        "shadow_ready",
        "operational_readiness",
        "deribit_ready",
        "profitability_proven",
        "edge_proven",
        "production_execution",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
        "real_wall_clock_used",
        "timestamp_origin_proven",
    }
    for flag in false_flags:
        assert payload[flag] is False

    forged = replace(methodology, live_ready=True)
    assert paper_return_series_methodology_digest(forged) != methodology.methodology_digest


def test_digest_is_deterministic_and_excludes_self_digest() -> None:
    first = _build(metadata={"b": "2", "a": "1"})
    second = _build(metadata={"a": "1", "b": "2"})
    assert first.methodology_digest == second.methodology_digest
    assert paper_return_series_methodology_digest(first) == first.methodology_digest

    resealed = replace(first, methodology_digest="0" * 64)
    assert paper_return_series_methodology_digest(resealed) == first.methodology_digest


def test_digest_changes_when_critical_fields_change() -> None:
    base = _build()
    variants = [
        _build(methodology_id="paper-return-methodology-2"),
        _build(correlation_id="corr-methodology-2"),
        _build(fee_policy_id="fee-policy-2"),
        _build(funding_policy_id="funding-policy-2"),
        _build(mark_policy_id="mark-policy-2"),
        _build(exposure_policy_id="exposure-policy-2"),
        _build(liquidation_policy_id="liquidation-policy-2"),
        _build(risk_free_policy_id="risk-free-policy-2"),
        _build(metadata={"purpose": "daily utc paper methodology", "review": "one"}),
    ]

    assert all(variant.methodology_digest != base.methodology_digest for variant in variants)


def test_reason_codes_are_sorted_unique_and_digest_bound() -> None:
    methodology = _build(reason_codes=["z_reason", "a_reason", "z_reason"])
    payload = paper_return_series_methodology_to_dict(methodology)

    assert methodology.reason_codes == ("a_reason", "z_reason")
    assert payload["reason_codes"] == ["a_reason", "z_reason"]
    assert methodology.methodology_digest != _build().methodology_digest


@pytest.mark.parametrize(
    "field_name",
    [
        "methodology_id",
        "correlation_id",
        "mtm_policy_id",
        "fee_policy_id",
        "funding_policy_id",
        "mark_policy_id",
        "exposure_policy_id",
        "liquidation_policy_id",
        "risk_free_policy_id",
    ],
)
def test_rejects_empty_or_non_plain_string_ids(field_name: str) -> None:
    with pytest.raises(PaperReturnSeriesMethodologyError, match=f"{field_name}_invalid"):
        _build(**{field_name: ""})
    with pytest.raises(PaperReturnSeriesMethodologyError, match=f"{field_name}_invalid"):
        _build(**{field_name: _LiarStr("paper-return-methodology-1")})


@pytest.mark.parametrize(
    "override",
    [
        {"methodology_id": "live-methodology"},
        {"correlation_id": "shadow-context"},
        {"fee_policy_id": "capital-fee-policy"},
        {"funding_policy_id": "deribit-funding-policy"},
        {"mark_policy_id": "service-readiness-mark"},
        {"exposure_policy_id": "equity-exposure-policy"},
        {"liquidation_policy_id": "bist-liquidation-policy"},
        {"risk_free_policy_id": "real_money-risk-free"},
        {"metadata": {"path": "crypto_core.execution.paper_adapter"}},
        {"metadata": {"venue": "BIST"}},
    ],
)
def test_rejects_forbidden_scope_tokens(override: dict[str, object]) -> None:
    with pytest.raises(PaperReturnSeriesMethodologyError, match="scope_violation"):
        _build(**override)


def test_controlled_return_basis_can_contain_equity_but_user_equity_tokens_reject() -> None:
    methodology = _build()
    assert methodology.return_basis == "normalized_paper_equity_index"

    with pytest.raises(PaperReturnSeriesMethodologyError, match="scope_violation"):
        _build(methodology_id="equity-methodology")


@pytest.mark.parametrize(
    "override",
    [
        {"methodology_id": "wall_clock-methodology"},
        {"correlation_id": "datetime.now-context"},
        {"metadata": {"source": "time.time_ns"}},
        {"metadata": {"source": "exchange_time"}},
        {"metadata": {"source": "clock"}},
    ],
)
def test_rejects_clock_suggesting_tokens(override: dict[str, object]) -> None:
    with pytest.raises(PaperReturnSeriesMethodologyError, match="clock_token_forbidden"):
        _build(**override)


def test_safe_market_data_terms_are_allowed() -> None:
    methodology = _build(metadata={"source": "limit_order_book market data policy"})
    assert methodology.metadata == (("source", "limit_order_book market data policy"),)


@pytest.mark.parametrize(
    "metadata",
    [
        [("a", "b")],
        {"a": 1},
        {1: "b"},
        {"a": _LiarStr("b")},
    ],
)
def test_rejects_malformed_metadata(metadata: object) -> None:
    with pytest.raises(PaperReturnSeriesMethodologyError, match="metadata_malformed"):
        _build(metadata=metadata)


@pytest.mark.parametrize("reason_codes", [["ok", ""], ["ok", _LiarStr("bad")], "bad"])
def test_rejects_malformed_reason_codes(reason_codes: object) -> None:
    with pytest.raises(PaperReturnSeriesMethodologyError, match="reason_codes_malformed"):
        _build(reason_codes=reason_codes)


def test_output_is_frozen_and_inputs_are_not_mutated() -> None:
    metadata = {"b": "2", "a": "1"}
    methodology = _build(metadata=metadata)

    with pytest.raises(FrozenInstanceError):
        methodology.methodology_id = "changed"  # type: ignore[misc]
    assert metadata == {"b": "2", "a": "1"}
    assert methodology.metadata == (("a", "1"), ("b", "2"))


def test_serializer_is_json_ready_and_matches_dataclass_fields() -> None:
    methodology = _build()
    payload = paper_return_series_methodology_to_dict(methodology)
    dataclass_field_names = {field.name for field in fields(methodology)}

    assert set(payload) == dataclass_field_names
    assert payload["status"] == methodology.status.value
    assert payload["metadata"] == [["purpose", "daily utc paper methodology"]]


def test_no_existing_duplicate_methodology_artifact_names() -> None:
    # The artifact is intentionally new and lives in exactly one validation module/test pair.
    assert methodology_module.__name__.endswith("paper_return_series_methodology")


def test_source_has_no_forbidden_runtime_or_stage4_execution_surfaces() -> None:
    source = _MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
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
        "compare_stage4",
        "Stage4PaperSummary",
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
