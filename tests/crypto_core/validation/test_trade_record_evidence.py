"""Tests for the SM-3 trade-record evidence artifact."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation import trade_record_evidence as record_module
from crypto_core.validation.trade_record_evidence import (
    TradeRecordEvidenceError,
    TradeRecordEvidenceStatus,
    build_trade_record_evidence,
    trade_record_evidence_digest,
    trade_record_evidence_to_dict,
)

_REASON_PREFIX = "trade_record_evidence:"

_STRUCTURAL_FALSE_FLAGS = (
    "execution_authorized",
    "order_created",
    "order_routed",
    "real_fill_created",
    "position_mutated",
    "pnl_authoritative",
    "secondary_metrics_enforced",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "edge_proven",
    "profitability_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "scheduler_enabled",
    "auto_loop_enabled",
)


class _LiarStr(str):
    """A string subclass rejected by exact string checks."""


def _rc(code: str) -> str:
    return f"{_REASON_PREFIX}{code}"


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _build(**overrides: object):
    payload: dict[str, object] = {
        "record_id": "rec-1",
        "correlation_id": "corr-1",
        "sleeve_id": "sleeve-1",
        "policy_id": "policy-1",
        "episode_id": "episode-1",
        "strategy_id": "strategy-1",
        "decision_id": "decision-1",
        "intended_quantity": "1.000000000000000000",
        "filled_quantity": "1.000000000000000000",
        "expected_fill_price": "100.000000000000000000",
        "realized_fill_price": "100.100000000000000000",
        "realized_pnl": "5.000000000000000000",
        "decided_episode": True,
        "metadata": {"purpose": "sm3 record"},
    }
    payload.update(overrides)
    return build_trade_record_evidence(**payload)  # type: ignore[arg-type]


# --- 1. Public API / happy path -----------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert set(record_module.__all__) == {
        "TradeRecordEvidence",
        "TradeRecordEvidenceError",
        "TradeRecordEvidenceStatus",
        "build_trade_record_evidence",
        "trade_record_evidence_digest",
        "trade_record_evidence_to_dict",
    }


def test_happy_record_ready_filled() -> None:
    record = _build()
    payload = trade_record_evidence_to_dict(record)

    assert record.status is TradeRecordEvidenceStatus.RECORD_READY
    assert record.ready is True
    assert record.hit_flag is True
    assert record.fill_flag is True
    assert record.slippage_bps == "10.000000000000000000"
    assert record.schema_version == "trade-record-evidence.v1"
    assert record.reason_codes == ()
    assert _is_hex64(record.record_digest)
    assert payload["status"] == "RECORD_READY"
    assert payload["record_digest"] == trade_record_evidence_digest(record)


def test_happy_record_ready_unfilled_episode() -> None:
    record = _build(
        filled_quantity="0.000000000000000000", realized_fill_price=None, realized_pnl="0.000000000000000000"
    )

    assert record.status is TradeRecordEvidenceStatus.RECORD_READY
    assert record.fill_flag is False
    assert record.hit_flag is False
    assert record.slippage_bps is None
    assert record.realized_fill_price is None


def test_output_is_frozen() -> None:
    record = _build()
    with pytest.raises(FrozenInstanceError):
        record.ready = False  # type: ignore[misc]


# --- 2. Digest / serializer ---------------------------------------------------------------------------------


def test_repeated_build_deterministic() -> None:
    assert _build().record_digest == _build().record_digest


def test_serializer_excludes_self_digest_from_recompute() -> None:
    record = _build()
    resealed = replace(record, record_digest="0" * 64)

    assert trade_record_evidence_digest(record) == record.record_digest
    assert trade_record_evidence_digest(resealed) == record.record_digest


def test_serializer_matches_dataclass_fields() -> None:
    record = _build()
    payload = trade_record_evidence_to_dict(record)

    assert set(payload) == {field.name for field in fields(record)}
    assert payload["status"] == record.status.value
    assert payload["metadata"] == [["purpose", "sm3 record"]]


@pytest.mark.parametrize(
    "override",
    [
        {"realized_pnl": "-1.000000000000000000"},
        {"realized_fill_price": "100.500000000000000000"},
        {"decided_episode": False},
        {"filled_quantity": "0.500000000000000000"},
    ],
)
def test_every_field_is_digest_bound(override: dict[str, object]) -> None:
    record = _build()
    tampered = replace(record, **override)
    assert trade_record_evidence_digest(tampered) != record.record_digest


def test_structural_false_flag_tamper_changes_digest() -> None:
    record = _build()
    tampered = replace(record, prdv4_stage4_complete=True)
    assert trade_record_evidence_digest(tampered) != record.record_digest


# --- 3. Malformed caller input (raise) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"record_id": "  "},
        {"record_id": _LiarStr("rec-1")},
        {"correlation_id": "corr\t1"},
        {"sleeve_id": ""},
    ],
)
def test_malformed_ids_raise(override: dict[str, object]) -> None:
    with pytest.raises(TradeRecordEvidenceError):
        _build(**override)


@pytest.mark.parametrize(
    "override",
    [
        {"record_id": 123},
        {"decided_episode": "yes"},
        {"decided_episode": 1},
        {"metadata": {"ok": 1}},
    ],
)
def test_wrong_type_caller_input_raises(override: dict[str, object]) -> None:
    with pytest.raises(TradeRecordEvidenceError):
        _build(**override)


@pytest.mark.parametrize("token", ["BIST", "KAP", "Matriks", "Borsa"])
def test_bist_token_raises(token: str) -> None:
    with pytest.raises(TradeRecordEvidenceError):
        _build(metadata={"venue": token})


@pytest.mark.parametrize("token", ["time.time_ns", "datetime.now", "server_time"])
def test_clock_token_raises(token: str) -> None:
    with pytest.raises(TradeRecordEvidenceError):
        _build(metadata={"source": token})


@pytest.mark.parametrize(
    "token",
    [
        "crypto_core.execution.fill_pricer",
        "order_router",
        "live_order",
        "scheduler",
        "deribit",
    ],
)
def test_forbidden_scope_token_raises(token: str) -> None:
    with pytest.raises(TradeRecordEvidenceError):
        _build(metadata={"source": token})


# --- 4. Numeric well-formedness / range / coherence (REJECTED) ----------------------------------------------


@pytest.mark.parametrize("bad", ["0.5", "1", "100", "abc", "NaN", "Infinity", "0.", ".5", ""])
def test_non_scale18_intended_quantity_rejects(bad: str) -> None:
    record = _build(intended_quantity=bad)
    assert record.status is TradeRecordEvidenceStatus.RECORD_REJECTED
    assert record.ready is False
    assert _rc("intended_quantity_invalid") in record.reason_codes


def test_negative_zero_string_rejects() -> None:
    record = _build(intended_quantity="-0.000000000000000000")
    assert record.status is TradeRecordEvidenceStatus.RECORD_REJECTED
    assert _rc("intended_quantity_invalid") in record.reason_codes


def test_intended_quantity_zero_rejects() -> None:
    record = _build(intended_quantity="0.000000000000000000")
    assert record.status is TradeRecordEvidenceStatus.RECORD_REJECTED
    assert _rc("intended_quantity_invalid") in record.reason_codes


def test_filled_exceeds_intended_rejects() -> None:
    record = _build(intended_quantity="1.000000000000000000", filled_quantity="2.000000000000000000")
    assert record.status is TradeRecordEvidenceStatus.RECORD_REJECTED
    assert _rc("filled_exceeds_intended") in record.reason_codes


def test_missing_realized_fill_price_with_fill_rejects() -> None:
    record = _build(filled_quantity="1.000000000000000000", realized_fill_price=None)
    assert record.status is TradeRecordEvidenceStatus.RECORD_REJECTED
    assert _rc("realized_fill_price_invalid") in record.reason_codes


def test_realized_fill_price_present_without_fill_rejects() -> None:
    record = _build(filled_quantity="0.000000000000000000", realized_fill_price="100.000000000000000000")
    assert record.status is TradeRecordEvidenceStatus.RECORD_REJECTED
    assert _rc("realized_fill_price_present_without_fill") in record.reason_codes


def test_invalid_realized_pnl_rejects() -> None:
    record = _build(realized_pnl="NaN")
    assert record.status is TradeRecordEvidenceStatus.RECORD_REJECTED
    assert _rc("realized_pnl_invalid") in record.reason_codes


# --- 5. Deterministic hit/fill/slippage derivation ----------------------------------------------------------


def test_slippage_derivation_is_recomputed_signed() -> None:
    positive = _build(expected_fill_price="100.000000000000000000", realized_fill_price="100.250000000000000000")
    negative = _build(expected_fill_price="100.000000000000000000", realized_fill_price="99.750000000000000000")
    assert positive.slippage_bps == "25.000000000000000000"
    assert negative.slippage_bps == "-25.000000000000000000"


@pytest.mark.parametrize(
    ("decided", "pnl", "expected_hit"),
    [
        (True, "5.000000000000000000", True),
        (False, "5.000000000000000000", False),
        (True, "0.000000000000000000", False),
        (True, "-5.000000000000000000", False),
    ],
)
def test_hit_flag_recomputed(decided: bool, pnl: str, expected_hit: bool) -> None:
    record = _build(decided_episode=decided, realized_pnl=pnl)
    assert record.hit_flag is expected_hit


def test_fill_flag_recomputed() -> None:
    filled = _build(filled_quantity="0.250000000000000000")
    unfilled = _build(filled_quantity="0.000000000000000000", realized_fill_price=None)
    assert filled.fill_flag is True
    assert unfilled.fill_flag is False


# --- 6. Non-claims / purity ---------------------------------------------------------------------------------


def test_structural_false_non_claim_flags() -> None:
    record = _build()
    payload = trade_record_evidence_to_dict(record)
    assert payload["paper_only"] is True
    assert payload["record_only"] is True
    for flag in _STRUCTURAL_FALSE_FLAGS:
        assert payload[flag] is False


def test_source_has_no_forbidden_imports_or_calls() -> None:
    source = Path(record_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "time",
        "datetime",
        "random",
        "secrets",
        "socket",
        "requests",
        "urllib",
        "httpx",
        "threading",
        "asyncio",
        "subprocess",
        "os",
        "pathlib",
        "sqlite3",
        "crypto_core.service",
        "crypto_core.execution",
        "crypto_core.venue",
        "crypto_core.runtime",
        "crypto_core.orchestrator",
        "crypto_core.portfolio",
        "crypto_core.validation.stage4_comparator",
    )
    forbidden_call_names = {"open", "float", "now", "utcnow", "time", "time_ns", "perf_counter", "monotonic"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == m or alias.name.startswith(f"{m}.") for m in forbidden_modules)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == m or node.module.startswith(f"{m}.") for m in forbidden_modules)
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names
