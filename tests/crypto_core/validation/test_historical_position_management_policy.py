"""Tests for the versioned protective position-management policy (PROTECTIVE_POSITION_LIFECYCLE_V1).

SYNTHETIC TEST VALUES ONLY. Every governed input and approval here is a synthetic fixture: none is a production value
or a real human decision.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.historical_position_management_policy as policy_module
from crypto_core.validation.edge_artifact_core import edge_canonical_json, edge_sha256_text
from crypto_core.validation.historical_execution_economics_policy import HistoricalExecutionApprovalKind
from crypto_core.validation.historical_ohlc_bar_archive import WILDER_ATR_METHOD_ID, HistoricalOhlcPriceSemantics
from crypto_core.validation.historical_position_management_policy import (
    ATR_INTERVAL_NS,
    MAX_HOLD_NS,
    MAX_HOLD_RULE_V1,
    POSITION_MANAGEMENT_METHOD_AUTHORITY,
    POSITION_MANAGEMENT_RULE_SET,
    POSITION_MANAGEMENT_RULE_SET_DIGEST,
    PROTECTIVE_EXECUTION_RULE_V1,
    STOP_ATR_MULTIPLE,
    STOP_RULE_V1,
    STOP_TRIGGER_RULE_V1,
    TIGHTENING_DEC9_READING_V1,
    TIGHTENING_FACTOR,
    TIGHTENING_NOT_APPLIED_PENDING_DEC9,
    TIGHTENING_PERIOD_NS,
    HistoricalPositionManagementApproval,
    HistoricalPositionManagementPolicyError,
    PositionManagementMethodAuthority,
    build_historical_position_management_policy,
    canonical_historical_position_management_approval,
    historical_position_management_approval_from_payload,
    historical_position_management_approval_mismatches,
    historical_position_management_methods_requiring_human_approval,
    historical_position_management_policy_digest,
    historical_position_management_policy_from_payload,
    historical_position_management_policy_payload_is_well_formed,
    historical_position_management_policy_to_dict,
    historical_position_management_tightening_applied,
    verify_historical_position_management_policy,
)

try:  # the module object pytest collects (basename import)
    import test_historical_pit_dataset as pit
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_historical_pit_dataset as pit

_PREFIX = "historical_position_management_policy"
HOUR = 3_600_000_000_000
INS = "BTC-USDT-PERP"


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def policy(**changes: object):  # noqa: ANN201
    arguments: dict[str, object] = {
        "policy_id": "pm-policy-1",
        "policy_version": "synthetic-v1",
        "instrument": INS,
        "atr_bar_price_semantics": HistoricalOhlcPriceSemantics.MARK_PRICE,
        "atr_max_bar_age_ns": 8 * HOUR,
        "stop_tightening_method_id": TIGHTENING_NOT_APPLIED_PENDING_DEC9,
    }
    arguments.update(changes)
    return build_historical_position_management_policy(**arguments)  # type: ignore[arg-type]


def approval(target, **changes: object) -> HistoricalPositionManagementApproval:  # noqa: ANN001
    values: dict[str, object] = {
        "approval_reference": "synthetic-pm-approval-1",
        "approval_digest": "f" * 64,
        "approval_kind": HistoricalExecutionApprovalKind.TEST_ONLY_SYNTHETIC,
        "approved_policy_digest": target.policy_digest,
        "approved_rule_set_digest": target.rule_set_digest,
        "approved_instrument": INS,
        "approved_strategy_spec_digest": "a" * 64,
        "approved_ohlc_source_digest": "b" * 64,
    }
    values.update(changes)
    return HistoricalPositionManagementApproval(**values)  # type: ignore[arg-type]


def test_the_doctrine_values_and_rule_identities_are_code_defined() -> None:
    built = policy()
    assert (built.max_hold_ns, built.atr_interval_ns, built.atr_period, built.stop_tightening_period_ns) == (
        24 * HOUR,
        4 * HOUR,
        14,
        8 * HOUR,
    )
    assert (MAX_HOLD_NS, ATR_INTERVAL_NS, TIGHTENING_PERIOD_NS) == (24 * HOUR, 4 * HOUR, 8 * HOUR)
    assert (STOP_ATR_MULTIPLE, TIGHTENING_FACTOR) == (Fraction(3, 2), Fraction(4, 5))
    assert (built.stop_atr_multiple, built.stop_tightening_factor) == ("1.500000000000000000", "0.800000000000000000")
    assert built.atr_method_id == WILDER_ATR_METHOD_ID
    assert (
        built.rule_set_digest
        == POSITION_MANAGEMENT_RULE_SET_DIGEST
        == edge_sha256_text(edge_canonical_json(POSITION_MANAGEMENT_RULE_SET))
    )


def test_the_builder_has_no_default_for_any_governed_input() -> None:
    parameters = inspect.signature(build_historical_position_management_policy).parameters
    assert all(item.default is inspect.Parameter.empty for item in parameters.values())
    assert set(parameters) == {
        "policy_id",
        "policy_version",
        "instrument",
        "atr_bar_price_semantics",
        "atr_max_bar_age_ns",
        "stop_tightening_method_id",
    }


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"atr_bar_price_semantics": "mark_price"}, "atr_bar_price_semantics_invalid"),
        ({"atr_max_bar_age_ns": 0}, "atr_max_bar_age_ns_invalid"),
        ({"atr_max_bar_age_ns": True}, "atr_max_bar_age_ns_invalid"),
        ({"stop_tightening_method_id": "TIGHTEN_LINEAR_20PCT"}, "stop_tightening_method_unsupported"),
        ({"instrument": "btc usdt"}, "instrument_invalid"),
        ({"policy_id": "bist-policy"}, "bist_scope_leakage:policy_id"),
    ],
)
def test_a_malformed_or_unsupported_governed_input_is_refused(changes: dict[str, object], reason: str) -> None:
    with pytest.raises(HistoricalPositionManagementPolicyError, match=f"^{code(reason)}$"):
        policy(**changes)


def test_the_policy_is_digest_bound_and_reverifies_totally() -> None:
    built = policy()
    verification = verify_historical_position_management_policy(built)
    assert verification.intact and verification.recomputed_digest == built.policy_digest
    assert built.policy_digest == historical_position_management_policy_digest(built)
    payload = historical_position_management_policy_to_dict(built)
    assert historical_position_management_policy_payload_is_well_formed(payload)
    assert historical_position_management_policy_from_payload(payload) == built
    for value in (None, "policy", object()):
        assert not verify_historical_position_management_policy(value).intact


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("max_hold_ns", 48 * HOUR),
        ("stop_atr_multiple", "2.000000000000000000"),
        ("atr_period", 20),
        ("stop_tightening_factor", "0.900000000000000000"),
        ("rule_set_digest", "0" * 64),
        ("atr_method_id", "SIMPLE_ATR_V1"),
    ],
)
def test_a_resealed_doctrine_value_never_verifies(name: str, value: object) -> None:
    built = policy()
    forged = replace(built, **{name: value})
    forged = replace(forged, policy_digest=historical_position_management_policy_digest(forged))
    assert not verify_historical_position_management_policy(forged).intact


def test_every_governed_value_change_changes_the_digest() -> None:
    base = policy().policy_digest
    for changes in (
        {"atr_bar_price_semantics": HistoricalOhlcPriceSemantics.LAST_TRADE},
        {"atr_max_bar_age_ns": 9 * HOUR},
        {"stop_tightening_method_id": TIGHTENING_DEC9_READING_V1},
        {"policy_version": "synthetic-v2"},
    ):
        assert policy(**changes).policy_digest != base


def test_dec9_is_a_reading_no_human_has_authorized() -> None:
    authority = POSITION_MANAGEMENT_METHOD_AUTHORITY
    assert authority[TIGHTENING_DEC9_READING_V1] is PositionManagementMethodAuthority.HUMAN_APPROVAL_REQUIRED
    assert authority[WILDER_ATR_METHOD_ID] is PositionManagementMethodAuthority.HUMAN_AUTHORIZED
    assert authority[TIGHTENING_NOT_APPLIED_PENDING_DEC9] is PositionManagementMethodAuthority.NOT_APPLIED
    assert {authority[MAX_HOLD_RULE_V1], authority[STOP_RULE_V1]} == {PositionManagementMethodAuthority.PRDV4_DOCTRINE}
    # the trigger and execution rules are this contract's specification, never relabelled as a human authorization
    assert {authority[STOP_TRIGGER_RULE_V1], authority[PROTECTIVE_EXECUTION_RULE_V1]} == {
        PositionManagementMethodAuthority.CONTRACT_SPECIFIED
    }
    assert POSITION_MANAGEMENT_RULE_SET["method_authority"][TIGHTENING_DEC9_READING_V1] == "HUMAN_APPROVAL_REQUIRED"  # type: ignore[index]
    reading = policy(stop_tightening_method_id=TIGHTENING_DEC9_READING_V1)
    assert historical_position_management_tightening_applied(reading)
    assert historical_position_management_methods_requiring_human_approval(reading) == (TIGHTENING_DEC9_READING_V1,)
    pending = policy()
    assert not historical_position_management_tightening_applied(pending)
    assert historical_position_management_methods_requiring_human_approval(pending) == ()


WITHDRAWN_BOUNDED_ATR_METHOD_ID = "WILDER_ATR_14_OVER_THE_LAST_280_CONTIGUOUS_TRUE_RANGES_V1"


def test_the_human_authorized_atr_method_is_the_exact_dec7_recurrence_and_no_bounded_variant() -> None:
    """P2-DEC7-280-TR-RESEED: the id labelled HUMAN_AUTHORIZED is the full recurrence, and the 280-TR re-seed is gone."""

    assert WILDER_ATR_METHOD_ID == "WILDER_ATR_14_EXACT_OVER_THE_FULL_CONTIGUOUS_RUN_V1"
    authority = POSITION_MANAGEMENT_METHOD_AUTHORITY
    assert authority[WILDER_ATR_METHOD_ID] is PositionManagementMethodAuthority.HUMAN_AUTHORIZED
    assert WITHDRAWN_BOUNDED_ATR_METHOD_ID not in authority
    assert POSITION_MANAGEMENT_RULE_SET["atr_method_id"] == WILDER_ATR_METHOD_ID
    assert WITHDRAWN_BOUNDED_ATR_METHOD_ID not in edge_canonical_json(POSITION_MANAGEMENT_RULE_SET)
    built = policy()
    assert built.atr_method_id == WILDER_ATR_METHOD_ID
    # a policy that names the withdrawn bounded method never verifies, even resealed
    forged = replace(built, atr_method_id=WITHDRAWN_BOUNDED_ATR_METHOD_ID)
    forged = replace(forged, policy_digest=historical_position_management_policy_digest(forged))
    assert not verify_historical_position_management_policy(forged).intact


def test_an_approval_matches_only_the_exact_policy_and_context() -> None:
    built = policy()
    record = canonical_historical_position_management_approval(approval(built))
    assert record is not None
    context = {"policy": built, "strategy_spec_digest": "a" * 64, "instrument": INS, "ohlc_source_digest": "b" * 64}
    assert historical_position_management_approval_mismatches(record, **context) == ()  # type: ignore[arg-type]
    other = policy(atr_max_bar_age_ns=9 * HOUR)
    assert historical_position_management_approval_mismatches(record, **{**context, "policy": other}) == (  # type: ignore[arg-type]
        "approved_policy_digest",
    )
    assert historical_position_management_approval_mismatches(  # type: ignore[arg-type]
        record, **{**context, "ohlc_source_digest": "c" * 64, "instrument": "ETH-USDT-PERP"}
    ) == ("approved_instrument", "approved_ohlc_source_digest")
    payload = json.loads(edge_canonical_json(policy_module._to_payload(record)))  # noqa: SLF001
    assert historical_position_management_approval_from_payload(payload) == record
    assert canonical_historical_position_management_approval(None) is None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"approval_kind": "HUMAN_GOVERNANCE"}, "approval_kind_invalid"),
        ({"approval_digest": "x"}, "approval_digest_invalid"),
        ({"approved_ohlc_source_digest": "B" * 64}, "approved_ohlc_source_digest_invalid"),
    ],
)
def test_a_malformed_approval_is_refused(changes: dict[str, object], reason: str) -> None:
    with pytest.raises(HistoricalPositionManagementPolicyError, match=f"^{code(reason)}$"):
        canonical_historical_position_management_approval(approval(policy(), **changes))


def test_the_module_is_pure_exact_and_offline() -> None:
    source_text = Path(policy_module.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source_text)):
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0] in pit.FORBIDDEN_MODULES for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] not in pit.FORBIDDEN_MODULES and node.module != "decimal"
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in pit.FORBIDDEN_CALLS, name
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
