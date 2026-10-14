"""Tests for the governed pre-paper validation policy (EDGE_PRE_PAPER_VALIDATION_POLICY_V1).

Every value below is a SYNTHETIC TEST VALUE. The policy holds no production number: it refuses any value looser than
PRDV4 §1.13 Stage 3 / §1.20 and only a HUMAN_GOVERNANCE approval of the exact values establishes it.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from crypto_core.validation.edge_artifact_core import EdgeEvidenceStatus, EdgeGateVerdict, edge_canonical_json
from crypto_core.validation.edge_pre_paper_validation_policy import (
    EDGE_PRE_PAPER_VALIDATION_POLICY_NON_CLAIM_FLAGS,
    EDGE_PRE_PAPER_VALIDATION_POLICY_RULE_SET_DIGEST,
    EdgePrePaperApprovalKind,
    EdgePrePaperValidationPolicyError,
    build_edge_pre_paper_validation_policy,
    edge_pre_paper_stress_scenarios,
    edge_pre_paper_validation_policy_digest,
    edge_pre_paper_validation_policy_from_payload,
    edge_pre_paper_validation_policy_payload_is_well_formed,
    edge_pre_paper_validation_policy_rule_set,
    edge_pre_paper_validation_policy_to_dict,
    verify_edge_pre_paper_validation_policy,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionStressScenarioKind,
    canonical_historical_execution_stress_scenario,
)

try:  # the module object pytest collects (basename import)
    import test_edge_pre_paper_validation_evidence as pret
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_pre_paper_validation_evidence as pret

_PREFIX = "edge_pre_paper_validation_policy"
GENESIS = "a" * 64


def values(**overrides: object) -> dict[str, object]:
    return {**pret.POLICY_VALUES, "approved_trial_chain_genesis_digest": GENESIS, **overrides}


def build(*, approve: object = "human", **overrides: object):
    draft = build_edge_pre_paper_validation_policy(**values(**overrides))  # type: ignore[arg-type]
    if approve is None:
        return draft
    kind = (
        EdgePrePaperApprovalKind.TEST_ONLY_SYNTHETIC
        if approve == "synthetic"
        else EdgePrePaperApprovalKind.HUMAN_GOVERNANCE
    )
    return build_edge_pre_paper_validation_policy(**values(**overrides), approval=pret.policy_approval(draft, kind))  # type: ignore[arg-type]


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def test_an_exactly_approved_policy_at_the_prdv4_limits_advances_and_re_proves() -> None:
    policy = build()
    assert (policy.status, policy.gate_verdict, policy.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert (policy.admission_scope, policy.regime_conditional_pbo_status) == ("LIMITED_S1_PAPER_V1", "UNPROVEN")
    verification = verify_edge_pre_paper_validation_policy(policy)
    assert verification.intact is True and verification.recomputed_digest == policy.policy_digest
    payload = json.loads(verification.canonical_json)
    assert edge_pre_paper_validation_policy_payload_is_well_formed(payload)
    assert edge_pre_paper_validation_policy_from_payload(payload) == policy
    assert {name: getattr(policy, name) for name, _ in EDGE_PRE_PAPER_VALIDATION_POLICY_NON_CLAIM_FLAGS} == dict(
        EDGE_PRE_PAPER_VALIDATION_POLICY_NON_CLAIM_FLAGS
    )
    assert policy.rule_set_digest == EDGE_PRE_PAPER_VALIDATION_POLICY_RULE_SET_DIGEST


@pytest.mark.parametrize(
    ("approve", "codes", "synthetic"),
    [
        (None, ("policy_approval_missing",), False),
        ("synthetic", ("policy_approval_not_human_governance",), True),
    ],
)
def test_a_missing_or_synthetic_approval_needs_governance(approve, codes, synthetic: bool) -> None:
    policy = build(approve=approve)
    assert policy.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert policy.verdict_reason_codes == tuple(_code(code) for code in codes)
    assert policy.synthetic_test_approval_used is synthetic


def test_an_approval_of_other_values_needs_governance() -> None:
    approval = build().approval
    changed = build_edge_pre_paper_validation_policy(
        **values(monte_carlo_p_value_max="0.010000000000000000"),
        approval=approval,  # type: ignore[arg-type]
    )
    assert changed.verdict_reason_codes == (_code("policy_approval_values_digest_mismatch"),)
    other_rules = build_edge_pre_paper_validation_policy(
        **values(),
        approval=replace(approval, approved_rule_set_digest="f" * 64),  # type: ignore[arg-type]
    )
    assert other_rules.verdict_reason_codes == (_code("policy_approval_rule_set_digest_mismatch"),)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("pbo_normal_max_exclusive", "0.200000000000000001"),
        ("pbo_capped_max_exclusive", "0.400000000000000001"),
        ("pbo_additional_oos_max_inclusive", "0.600000000000000001"),
        ("pbo_capped_allocation_fraction", "0.500000000000000001"),
        ("regime_allocation_fraction", "0.250000000000000001"),
        ("monte_carlo_p_value_max", "0.050000000000000001"),
        ("sensitivity_min_retention_ratio", "0.499999999999999999"),
        ("high_volatility_slippage_multiplier", "1.999999999999999999"),
        ("low_liquidity_depth_multiplier", "0.200000000000000001"),
        ("low_liquidity_slippage_multiplier", "2.999999999999999999"),
        ("flash_crash_gap_fraction", "0.099999999999999999"),
        ("flash_crash_depth_multiplier", "1.000000000000000001"),
        ("flash_crash_slippage_multiplier", "0.999999999999999999"),
        ("flash_crash_maintenance_margin_fraction", "1.000000000000000000"),
        ("pbo_normal_max_exclusive", "0.000000000000000000"),
        ("regime_allocation_fraction", "0.000000000000000000"),
        ("monte_carlo_min_closed_trade_count", 49),
        ("flash_crash_recovery_ns", 299_999_999_999),
    ],
)
def test_a_value_looser_than_prdv4_is_refused_never_clamped(name: str, value: object) -> None:
    with pytest.raises(EdgePrePaperValidationPolicyError, match=f"value_looser_than_prdv4:{name}$"):
        build_edge_pre_paper_validation_policy(**values(**{name: value}))  # type: ignore[arg-type]


def test_stricter_values_are_accepted() -> None:
    policy = build(
        pbo_normal_max_exclusive="0.100000000000000000",
        pbo_capped_max_exclusive="0.300000000000000000",
        pbo_additional_oos_max_inclusive="0.500000000000000000",
        regime_allocation_fraction="0.100000000000000000",
        monte_carlo_p_value_max="0.010000000000000000",
        monte_carlo_min_closed_trade_count=100,
        sensitivity_min_retention_ratio="0.800000000000000000",
        high_volatility_slippage_multiplier="3.000000000000000000",
        flash_crash_recovery_ns=600_000_000_000,
    )
    assert policy.gate_verdict is EdgeGateVerdict.PASS


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"pbo_normal_max_exclusive": "0.300000000000000000"}, "value_looser_than_prdv4:pbo_normal_max_exclusive"),
        (
            {"pbo_capped_max_exclusive": "0.100000000000000000", "pbo_normal_max_exclusive": "0.150000000000000000"},
            "pbo_band_thresholds_not_ordered",
        ),
        ({"pbo_capped_allocation_fraction": 0.5}, "pbo_capped_allocation_fraction_invalid"),
        ({"monte_carlo_min_closed_trade_count": True}, "monte_carlo_min_closed_trade_count_invalid"),
        ({"flash_crash_recovery_ns": "300000000000"}, "flash_crash_recovery_ns_invalid"),
        ({"approved_trial_chain_genesis_digest": "A" * 64}, "approved_trial_chain_genesis_digest_invalid"),
        ({"policy_id": "Policy"}, "policy_id_invalid"),
        ({"policy_version": "live"}, "forbidden_scope_token"),
    ],
)
def test_malformed_values_are_construction_errors(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgePrePaperValidationPolicyError, match=code):
        build_edge_pre_paper_validation_policy(**values(**overrides))  # type: ignore[arg-type]


def test_the_three_governed_stress_scenarios_are_exact_and_engine_valid() -> None:
    policy = build()
    high, low, flash = edge_pre_paper_stress_scenarios(policy)
    kinds = HistoricalExecutionStressScenarioKind
    assert (high.scenario_kind, low.scenario_kind, flash.scenario_kind) == (
        kinds.HIGH_VOLATILITY,
        kinds.LOW_LIQUIDITY,
        kinds.FLASH_CRASH,
    )
    assert (high.return_multiplier, high.slippage_multiplier) == ("1.500000000000000000", "2.000000000000000000")
    assert (low.depth_multiplier, low.slippage_multiplier) == ("0.200000000000000000", "3.000000000000000000")
    assert (flash.gap_fraction, flash.recovery_ns, flash.maintenance_margin_fraction) == (
        "0.100000000000000000",
        300_000_000_000,
        "0.005000000000000000",
    )
    for item in (high, low, flash):
        assert canonical_historical_execution_stress_scenario(item) == item


@pytest.mark.parametrize(
    "changes",
    [
        {"monte_carlo_p_value_max": "0.010000000000000000"},
        {"admission_scope": "FULL_PRDV4_V1"},
        {"regime_conditional_pbo_status": "PROVEN"},
        {"gate_verdict": EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, "advances": False},
        {"production_values_approved": True},
    ],
)
def test_a_resealed_forged_policy_never_verifies(changes: dict[str, object]) -> None:
    policy = build()
    changed = replace(policy, **changes)
    forged = replace(changed, policy_digest=edge_pre_paper_validation_policy_digest(changed))
    assert verify_edge_pre_paper_validation_policy(forged).intact is False


def test_the_rule_set_pins_the_method_constants_and_the_prdv4_limits() -> None:
    rules = edge_pre_paper_validation_policy_rule_set()
    assert (rules["cscv_block_count"], rules["monte_carlo_sample_count"]) == (16, 10_000)
    assert rules["prdv4_pbo_capped_max_exclusive"] == "0.400000000000000000"
    assert rules["limited_s1_regime_allocation_fraction_max"] == "0.250000000000000000"
    payload = json.loads(edge_canonical_json(edge_pre_paper_validation_policy_to_dict(build())))
    payload["extra"] = True
    assert edge_pre_paper_validation_policy_payload_is_well_formed(payload) is False
