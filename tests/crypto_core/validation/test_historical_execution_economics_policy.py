"""Tests for the governed historical execution-economics policy (DETERMINISTIC_HISTORICAL_EXECUTION_ECONOMICS_V2).

Also the shared policy/approval fixtures for the historical execution economics result tests.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import fields, replace
from fractions import Fraction

import pytest

import crypto_core.validation.historical_execution_economics_policy as policy_module
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HISTORICAL_EXECUTION_CONFORMANCE_V1,
    HISTORICAL_EXECUTION_NUMERIC_POLICY_V1,
    HISTORICAL_EXECUTION_POLICY_NON_CLAIM_FLAGS,
    LATENCY_TIER_PRDV4_T1,
    HistoricalExecutionApprovalKind,
    HistoricalExecutionCitationKind,
    HistoricalExecutionEconomicsApproval,
    HistoricalExecutionEconomicsPolicy,
    HistoricalExecutionEconomicsPolicyError,
    HistoricalExecutionExternalFactCitation,
    HistoricalExecutionFactId,
    build_historical_execution_economics_policy,
    build_historical_execution_external_fact_citation,
    canonical_historical_execution_economics_approval,
    historical_execution_cited_value,
    historical_execution_decimal,
    historical_execution_decimal_is_canonical,
    historical_execution_economics_approval_mismatches,
    historical_execution_economics_policy_digest,
    historical_execution_economics_policy_from_payload,
    historical_execution_economics_policy_payload_is_well_formed,
    historical_execution_economics_policy_to_dict,
    historical_execution_external_fact_citation_digest,
    historical_execution_policy_identity_digests,
    historical_execution_quantize_price,
    historical_execution_quantize_quantity,
    historical_execution_render_amount,
    historical_execution_render_quantity,
    verify_historical_execution_economics_policy,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

_PREFIX = "historical_execution_economics_policy"
INSTRUMENT = "BTC-USDT-PERP"
INTERVAL_NS = 10_000
INT64_MAX = 9223372036854775807
SIXTY_POSITIVE = "9" * 41 + "." + "9" * 18
SIXTY_NEGATIVE = "-" + "9" * 40 + "." + "9" * 18
SIXTY_ONE = "1" * 42 + "." + "0" * 18
EIGHTY_DIGITS = "1" * 80 + "." + "0" * 18


def d(value: object) -> str:
    """Canonical scale-18 text of an exact value (test helper)."""

    rendered = historical_execution_render_amount(Fraction(value))  # type: ignore[arg-type]
    assert rendered is not None
    return rendered


def policy_args(**overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "policy_id": "historical-economics-policy-1",
        "policy_version": "1",
        "instrument": INSTRUMENT,
        "market_type": "usdt_perp",
        "latency_tier_id": LATENCY_TIER_PRDV4_T1,
        "latency_ns": 100,
        "max_execution_delay_ns": 5_000,
        "max_mark_staleness_ns": 5_000,
        "visible_depth_cap_fraction": d("0.02"),
        "max_spread_bps": d(50),
        "slippage_floor_bps": d(5),
        "impact_coefficient_bps_per_participation_pct": d("0.5"),
        "taker_fee_bps": d(5),
        "funding_interval_ns": INTERVAL_NS,
        "initial_equity": d(10_000),
        "satisfies_fee_model_requirement": "maker_taker_schedule",
        "satisfies_slippage_model_requirement": "book_impact_v1",
        "satisfies_latency_sensitivity": "low",
        "external_fact_citations": (),
    }
    arguments.update(overrides)
    return arguments


def citation(
    fact_id: HistoricalExecutionFactId,
    value: str,
    *,
    kind: HistoricalExecutionCitationKind = HistoricalExecutionCitationKind.TEST_ONLY_SYNTHETIC,
    instrument: str = INSTRUMENT,
) -> HistoricalExecutionExternalFactCitation:
    return build_historical_execution_external_fact_citation(
        fact_id=fact_id,
        instrument=instrument,
        cited_value=value,
        citation_kind=kind,
        citation_reference="TEST_ONLY synthetic citation, never production truth",
        evidence_digest="a" * 64,
    )


def citations_for(
    policy: HistoricalExecutionEconomicsPolicy,
    *,
    kind: HistoricalExecutionCitationKind = HistoricalExecutionCitationKind.TEST_ONLY_SYNTHETIC,
    skip: tuple[HistoricalExecutionFactId, ...] = (),
) -> tuple[HistoricalExecutionExternalFactCitation, ...]:
    return tuple(
        citation(fact_id, historical_execution_cited_value(policy, fact_id), kind=kind, instrument=policy.instrument)
        for fact_id in HistoricalExecutionFactId
        if fact_id not in skip
    )


def cited_policy(
    *,
    kind: HistoricalExecutionCitationKind = HistoricalExecutionCitationKind.TEST_ONLY_SYNTHETIC,
    skip: tuple[HistoricalExecutionFactId, ...] = (),
    **overrides: object,
) -> HistoricalExecutionEconomicsPolicy:
    """A policy whose venue facts carry exact synthetic citations (TEST_ONLY unless another kind is given)."""

    arguments = policy_args(**overrides)
    probe = build_historical_execution_economics_policy(**arguments)  # type: ignore[arg-type]
    arguments["external_fact_citations"] = citations_for(probe, kind=kind, skip=skip)
    return build_historical_execution_economics_policy(**arguments)  # type: ignore[arg-type]


def approval_for(
    policy: HistoricalExecutionEconomicsPolicy,
    *,
    strategy_spec_digest: str,
    data_requirement_registry_digest: str,
    instrument: str = INSTRUMENT,
    market_type: str = "usdt_perp",
    **overrides: object,
) -> HistoricalExecutionEconomicsApproval:
    execution, funding = historical_execution_policy_identity_digests(policy)
    arguments: dict[str, object] = {
        "approval_reference": "governance-economics-1",
        "approval_digest": "b" * 64,
        "approval_kind": HistoricalExecutionApprovalKind.TEST_ONLY_SYNTHETIC,
        "approved_economics_policy_digest": policy.policy_digest,
        "approved_strategy_spec_digest": strategy_spec_digest,
        "approved_instrument": instrument,
        "approved_market_type": market_type,
        "approved_data_requirement_registry_digest": data_requirement_registry_digest,
        "approved_quantity_semantics_id": policy.quantity_semantics_id,
        "approved_execution_identity_digest": execution,
        "approved_funding_identity_digest": funding,
    }
    arguments.update(overrides)
    return HistoricalExecutionEconomicsApproval(**arguments)  # type: ignore[arg-type]


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _reseal(policy: HistoricalExecutionEconomicsPolicy, **changes: object) -> HistoricalExecutionEconomicsPolicy:
    changed = replace(policy, **changes)
    return replace(changed, policy_digest=historical_execution_economics_policy_digest(changed))


def _assert_receipt_invariants(policy: HistoricalExecutionEconomicsPolicy) -> None:
    verification = verify_historical_execution_economics_policy(policy)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == policy.policy_digest
    assert historical_execution_economics_policy_from_payload(json.loads(verification.canonical_json)) == policy
    assert historical_execution_economics_policy_payload_is_well_formed(
        historical_execution_economics_policy_to_dict(policy)
    )
    assert policy.advances is (
        policy.status is EdgeEvidenceStatus.READY and policy.gate_verdict is EdgeGateVerdict.PASS
    )
    if policy.status is EdgeEvidenceStatus.REJECTED:
        assert policy.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert policy.integrity_reason_codes
        assert policy.verdict_reason_codes == ()
    else:
        assert policy.integrity_reason_codes == ()


# --- happy path and committed semantics ---------------------------------------------------------------------------------


def test_fully_cited_policy_is_ready_pass_and_re_proves() -> None:
    policy = cited_policy()
    _assert_receipt_invariants(policy)
    assert (policy.status, policy.gate_verdict, policy.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert policy.synthetic_test_facts_used is True
    assert len(policy.external_fact_citations) == len(HistoricalExecutionFactId)


def test_deep_research_cited_policy_is_not_flagged_synthetic() -> None:
    policy = cited_policy(kind=HistoricalExecutionCitationKind.DEEP_RESEARCH_CITED)
    _assert_receipt_invariants(policy)
    assert policy.advances is True
    assert policy.synthetic_test_facts_used is False


def test_policy_commits_every_identity_and_value() -> None:
    payload = historical_execution_economics_policy_to_dict(cited_policy())
    assert {key: payload[key] for key in payload if key.endswith(("_id", "_key", "_name", "market_type"))} == {
        "policy_id": "historical-economics-policy-1",
        "market_type": "usdt_perp",
        "contract_model_id": "linear_usdt_perpetual_v1",
        "quantity_semantics_id": "base_asset_quantity_v1",
        "data_series_contract_id": "final_funding_mark_price_order_book_top_of_book_v1",
        "funding_data_key": "funding_rate",
        "funding_value_name": "funding_rate",
        "mark_data_key": "mark_price",
        "mark_value_name": "mark_price",
        "order_book_data_key": "order_book",
        "best_bid_price_name": "best_bid_price",
        "best_ask_price_name": "best_ask_price",
        "best_bid_quantity_name": "best_bid_quantity",
        "best_ask_quantity_name": "best_ask_quantity",
        "execution_timing_policy_id": "pit_visibility_after_latency_next_observation_v1",
        "latency_tier_id": "prdv4_t1_critical",
        "fill_ratio_model_id": "visible_depth_linear_v1",
        "slippage_model_id": "max_floor_vs_half_spread_plus_impact_v1",
        "impact_model_id": "participation_linear_v1",
        "fee_model_id": "all_taker_bps_on_fill_notional_v1",
        "funding_model_id": "linear_final_funding_settlement_v1",
        "funding_liability_rule_id": "event_time_plus_interval_v1",
        "funding_notional_price_source_id": "mark_price_at_liability_time_v1",
        "funding_sign_convention_id": "positive_rate_long_pays_v1",
        "funding_coverage_rule_id": "every_governed_grid_liability_of_every_liable_interval_v1",
        "same_timestamp_priority_id": "funding_settlement_before_fill_v1",
        "valuation_schedule_id": "events_plus_utc_day_boundaries_v1",
        "terminal_rule_id": "mark_to_market_no_forced_close_v1",
        "divergence_rule_id": "target_delta_close_only_clamp_v1",
        "leverage_rule_id": "strategy_spec_max_leverage_post_fill_mark_notional_v1",
        "accounting_state_rule_id": "exact_signed_quantity_and_cost_basis_v1",
    }
    assert payload["required_revision_policy"] == "immutable_after_finalization"
    assert payload["numeric_policy"] == {
        "numeric_policy_id": "historical_execution_numeric_policy.v1",
        "decimal_grammar_id": "ascii_signed_canonical_integer_dot_fixed_scale_no_exponent_no_plus_no_negative_zero.v1",
        "decimal_scale": 18,
        "max_decimal_text_length": 60,
        "integer_grammar_id": "native_int_bounded_signed_int64.v1",
        "max_wire_integer": INT64_MAX,
        "arithmetic_id": "exact_fraction_arithmetic.v1",
        "state_representation_id": "exact_fraction_internal_state_render_is_output_only.v1",
        "executed_price_grid_id": "round_half_even_scale18_executed_price_grid.v1",
        "amount_rounding_id": "round_half_even",
        "quantity_rounding_id": "round_toward_zero",
        "render_id": "exact_integer_divmod_fixed_scale_render.v1",
    }


def test_conformance_vector_keeps_false_fields_false() -> None:
    assert historical_execution_economics_policy_to_dict(cited_policy())["conformance"] == {
        "same_observation_fill_prohibited": True,
        "fill_ratio_model_enforced": True,
        "zero_slippage_prohibited": True,
        "positive_latency_enforced": True,
        "visible_depth_cap_enforced": True,
        "time_varying_spread_enforced": True,
        "actual_final_funding_stream_required": True,
        "exact_internal_cost_basis_enforced": True,
        "almgren_chriss_modeled": False,
        "maker_rebate_modeled": False,
        "lot_tick_rounding_modeled": False,
        "margin_liquidation_modeled": False,
        "inverse_contract_modeled": False,
        "prdv4_min_slippage_floor_bps": "5.000000000000000000",
        "prdv4_max_visible_depth_cap_fraction": "0.020000000000000000",
    }
    forged = _reseal(
        cited_policy(), conformance=replace(HISTORICAL_EXECUTION_CONFORMANCE_V1, almgren_chriss_modeled=True)
    )
    assert _code("field_mismatch:conformance") in verify_historical_execution_economics_policy(forged).reason_codes


def test_every_governed_value_change_changes_the_digest() -> None:
    base = cited_policy()
    for change in (
        {"latency_ns": 101},
        {"max_execution_delay_ns": 5_001},
        {"max_mark_staleness_ns": 5_001},
        {"visible_depth_cap_fraction": d("0.01")},
        {"max_spread_bps": d(51)},
        {"slippage_floor_bps": d(6)},
        {"impact_coefficient_bps_per_participation_pct": d("0.6")},
        {"taker_fee_bps": d(6)},
        {"funding_interval_ns": INTERVAL_NS + 1},
        {"initial_equity": d(20_000)},
        {"satisfies_fee_model_requirement": "other_fee_model"},
    ):
        assert cited_policy(**change).policy_digest != base.policy_digest


def test_identity_digests_are_stable_and_distinct() -> None:
    execution, funding = historical_execution_policy_identity_digests(cited_policy())
    assert (execution, funding) == historical_execution_policy_identity_digests(cited_policy(latency_ns=999))
    assert execution != funding


# --- external facts ----------------------------------------------------------------------------------------------------


def test_uncited_policy_needs_external_facts_for_every_venue_fact() -> None:
    policy = build_historical_execution_economics_policy(**policy_args())  # type: ignore[arg-type]
    _assert_receipt_invariants(policy)
    assert policy.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert set(policy.verdict_reason_codes) == {
        _code(f"external_fact_missing:{fact_id.value}") for fact_id in HistoricalExecutionFactId
    }


@pytest.mark.parametrize("fact_id", list(HistoricalExecutionFactId), ids=lambda item: item.value)
def test_each_missing_citation_blocks_advancement(fact_id: HistoricalExecutionFactId) -> None:
    policy = cited_policy(skip=(fact_id,))
    assert policy.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert policy.verdict_reason_codes == (_code(f"external_fact_missing:{fact_id.value}"),)


def test_citation_must_cite_the_exact_policy_value_and_instrument() -> None:
    policy = cited_policy()
    wrong_value = [
        c if c.fact_id is not HistoricalExecutionFactId.TAKER_FEE_BPS else citation(c.fact_id, d(4))
        for c in policy.external_fact_citations
    ]
    mismatch = build_historical_execution_economics_policy(**policy_args(external_fact_citations=wrong_value))  # type: ignore[arg-type]
    assert mismatch.verdict_reason_codes == (_code("external_fact_value_mismatch:taker_fee_bps"),)
    foreign = [
        c
        if c.fact_id is not HistoricalExecutionFactId.FUNDING_INTERVAL_NS
        else citation(c.fact_id, c.cited_value, instrument="ETH-USDT-PERP")
        for c in policy.external_fact_citations
    ]
    wrong_instrument = build_historical_execution_economics_policy(**policy_args(external_fact_citations=foreign))  # type: ignore[arg-type]
    assert wrong_instrument.verdict_reason_codes == (_code("external_fact_instrument_mismatch:funding_interval_ns"),)


def test_citation_digest_tamper_rejects_the_policy() -> None:
    policy = cited_policy()
    tampered = [
        replace(c, evidence_digest="c" * 64) if c.fact_id is HistoricalExecutionFactId.TAKER_FEE_BPS else c
        for c in policy.external_fact_citations
    ]
    rejected = build_historical_execution_economics_policy(**policy_args(external_fact_citations=tampered))  # type: ignore[arg-type]
    _assert_receipt_invariants(rejected)
    assert rejected.status is EdgeEvidenceStatus.REJECTED
    assert rejected.integrity_reason_codes == (_code("external_fact_citation_digest_mismatch:taker_fee_bps"),)
    resealed = _reseal(policy, external_fact_citations=tuple(tampered))
    assert verify_historical_execution_economics_policy(resealed).intact is False


def test_citation_digest_is_computed_and_covers_every_field() -> None:
    item = citation(HistoricalExecutionFactId.TAKER_FEE_BPS, d(5))
    assert item.citation_digest == historical_execution_external_fact_citation_digest(replace(item, citation_digest=""))
    for change in ({"cited_value": d(6)}, {"instrument": "ETH-USDT-PERP"}, {"evidence_digest": "c" * 64}):
        assert historical_execution_external_fact_citation_digest(replace(item, **change, citation_digest="")) != (
            item.citation_digest
        )


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"fact_id": "fee_schedule"}, "citation_fact_id_invalid"),
        ({"citation_kind": "MODEL_MEMORY"}, "citation_kind_invalid"),
        ({"citation_reference": ""}, "citation_reference_invalid"),
        ({"citation_reference": "live venue scrape"}, "citation_reference"),
        ({"evidence_digest": "A" * 64}, "citation_evidence_digest_invalid"),
        ({"cited_value": None}, "citation_cited_value_invalid"),
        ({"instrument": "BTC USDT"}, "citation_instrument_invalid"),
    ],
)
def test_malformed_citation_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    arguments: dict[str, object] = {
        "fact_id": HistoricalExecutionFactId.TAKER_FEE_BPS,
        "instrument": INSTRUMENT,
        "cited_value": d(5),
        "citation_kind": HistoricalExecutionCitationKind.TEST_ONLY_SYNTHETIC,
        "citation_reference": "TEST_ONLY",
        "evidence_digest": "a" * 64,
    }
    arguments.update(overrides)
    with pytest.raises(HistoricalExecutionEconomicsPolicyError, match=code):
        build_historical_execution_external_fact_citation(**arguments)  # type: ignore[arg-type]


def test_malformed_and_duplicate_citation_sets_are_construction_errors() -> None:
    policy = cited_policy()
    for citations, code in (
        (None, "external_fact_citations_malformed"),
        (("taker_fee_bps",), "external_fact_citation_malformed"),
        ((replace(policy.external_fact_citations[0], citation_digest="z"),), "external_fact_citation_digest_invalid"),
        (policy.external_fact_citations + policy.external_fact_citations[:1], "external_fact_citation_duplicate"),
    ):
        with pytest.raises(HistoricalExecutionEconomicsPolicyError, match=code):
            build_historical_execution_economics_policy(**policy_args(external_fact_citations=citations))  # type: ignore[arg-type]


# --- PRDV4 §12.2 prohibitions and governed-value domains ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"latency_ns": 0}, "latency_ns_invalid"),
        ({"latency_ns": -1}, "latency_ns_invalid"),
        ({"latency_ns": True}, "latency_ns_invalid"),
        ({"latency_ns": INT64_MAX + 1}, "latency_ns_invalid"),
        ({"max_execution_delay_ns": 99}, "max_execution_delay_ns_invalid"),
        ({"max_mark_staleness_ns": 0}, "max_mark_staleness_ns_invalid"),
        ({"funding_interval_ns": 0}, "funding_interval_ns_invalid"),
        ({"funding_interval_ns": 10**5000}, "funding_interval_ns_invalid"),
        ({"slippage_floor_bps": d("4.999999999999999999")}, "slippage_floor_below_prdv4_minimum"),
        ({"slippage_floor_bps": d(0)}, "slippage_floor_below_prdv4_minimum"),
        ({"visible_depth_cap_fraction": d("0.020000000000000001")}, "visible_depth_cap_exceeds_prdv4_bound"),
        ({"visible_depth_cap_fraction": d(1)}, "visible_depth_cap_exceeds_prdv4_bound"),
        ({"visible_depth_cap_fraction": d(0)}, "visible_depth_cap_fraction_invalid"),
        ({"max_spread_bps": d(0)}, "max_spread_bps_invalid"),
        (
            {"impact_coefficient_bps_per_participation_pct": d(-1)},
            "impact_coefficient_bps_per_participation_pct_invalid",
        ),
        ({"taker_fee_bps": d(-1)}, "taker_fee_bps_invalid"),
        ({"initial_equity": d(0)}, "initial_equity_invalid"),
        ({"initial_equity": d(-1)}, "initial_equity_invalid"),
        ({"initial_equity": None}, "initial_equity_invalid"),
        ({"market_type": "inverse_perp"}, "market_type_unsupported_for_economics_v1"),
        ({"market_type": "spot"}, "market_type_unsupported_for_economics_v1"),
        ({"latency_tier_id": "prdv4_t0_ultra_critical"}, "latency_tier_unsupported"),
        ({"instrument": "BTC USDT"}, "instrument_invalid"),
        ({"policy_id": "policy scheduler"}, "policy_id"),
        ({"satisfies_fee_model_requirement": ""}, "satisfies_fee_model_requirement_invalid"),
    ],
    ids=lambda value: str(value)[:40] if not isinstance(value, dict) else next(iter(value)),
)
def test_prohibited_or_ungoverned_values_are_construction_errors(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(HistoricalExecutionEconomicsPolicyError, match=code):
        build_historical_execution_economics_policy(**policy_args(**overrides))  # type: ignore[arg-type]


def test_prdv4_boundaries_are_accepted_exactly() -> None:
    policy = cited_policy(slippage_floor_bps=d(5), visible_depth_cap_fraction=d("0.02"), latency_ns=1)
    assert policy.advances is True
    maximum = cited_policy(latency_ns=INT64_MAX, max_execution_delay_ns=INT64_MAX, initial_equity=SIXTY_POSITIVE)
    assert (maximum.latency_ns, maximum.initial_equity) == (INT64_MAX, SIXTY_POSITIVE)


def test_no_production_defaults_exist() -> None:
    parameters = inspect.signature(build_historical_execution_economics_policy).parameters
    assert all(parameter.default is inspect.Parameter.empty for parameter in parameters.values())
    for name in ("taker_fee_bps", "latency_ns", "funding_interval_ns", "initial_equity", "slippage_floor_bps"):
        arguments = policy_args()
        del arguments[name]
        with pytest.raises(TypeError):
            build_historical_execution_economics_policy(**arguments)  # type: ignore[arg-type]


# --- numeric authority -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [SIXTY_POSITIVE, SIXTY_NEGATIVE, "0.000000000000000001", "-0.000000000000000001", "0.000000000000000000"],
)
def test_canonical_scale18_boundary_is_accepted(value: str) -> None:
    assert historical_execution_decimal_is_canonical(value) is True
    assert historical_execution_decimal(value) == Fraction(value)


@pytest.mark.parametrize(
    "value",
    [
        SIXTY_ONE,
        EIGHTY_DIGITS,
        "1e-4",
        "1.000000000000000000e0",
        "+1.000000000000000000",
        "-0.000000000000000000",
        "１.000000000000000000",
        "1.٠٠٠000000000000000",
        "01.000000000000000000",
        "1.00000000000000000",
        "1.0000000000000000000",
        "NaN",
        " 1.000000000000000000",
        1,
        True,
        None,
    ],
    ids=lambda value: repr(value)[:24],
)
def test_noncanonical_decimals_are_refused_everywhere(value: object) -> None:
    assert historical_execution_decimal_is_canonical(value) is False
    with pytest.raises(HistoricalExecutionEconomicsPolicyError, match="decimal_noncanonical"):
        historical_execution_decimal(value)
    with pytest.raises(HistoricalExecutionEconomicsPolicyError, match="taker_fee_bps_invalid"):
        build_historical_execution_economics_policy(**policy_args(taker_fee_bps=value))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "rendered"),
    [
        (Fraction(5, 10**19), "0.000000000000000000"),
        (Fraction(15, 10**19), "0.000000000000000002"),
        (Fraction(25, 10**19), "0.000000000000000002"),
        (Fraction(35, 10**19), "0.000000000000000004"),
        (Fraction(-25, 10**19), "-0.000000000000000002"),
        (Fraction(-5, 10**19), "0.000000000000000000"),
        (Fraction(1, 3), "0.333333333333333333"),
        (Fraction(2, 3), "0.666666666666666667"),
    ],
)
def test_amount_render_is_exact_round_half_even_without_negative_zero(value: Fraction, rendered: str) -> None:
    assert historical_execution_render_amount(value) == rendered


def test_quantity_render_truncates_toward_zero_and_both_renders_bound_length() -> None:
    assert historical_execution_render_quantity(Fraction(2, 3)) == "0.666666666666666666"
    assert historical_execution_render_quantity(Fraction(-2, 3)) == "-0.666666666666666666"
    assert historical_execution_render_amount(Fraction(SIXTY_POSITIVE)) == SIXTY_POSITIVE
    assert historical_execution_render_amount(Fraction(SIXTY_POSITIVE) + Fraction(1, 10**18)) is None
    assert historical_execution_render_quantity(Fraction(10) ** 42) is None


@pytest.mark.parametrize(
    "value",
    [Fraction(1, 3), Fraction(-2, 3), Fraction(100), Fraction(-1, 10**19), Fraction(SIXTY_POSITIVE)],
    ids=lambda value: str(value)[:24],
)
def test_quantization_returns_one_exact_grid_value_and_its_own_text(value: Fraction) -> None:
    """The grid value and its text come from ONE unit count: the artifact text is never re-parsed into state."""

    price = historical_execution_quantize_price(value)
    quantity = historical_execution_quantize_quantity(value)
    assert price is not None and quantity is not None
    price_value, price_text = price
    quantity_value, quantity_text = quantity
    assert price_text == historical_execution_render_amount(value)
    assert quantity_text == historical_execution_render_quantity(value)
    assert price_value == Fraction(price_text)
    assert quantity_value == Fraction(quantity_text)
    assert abs(quantity_value) <= abs(value)
    assert abs(price_value - value) <= Fraction(1, 2 * 10**18)


def test_quantization_is_none_outside_the_representation_domain() -> None:
    too_large = Fraction(SIXTY_POSITIVE) + Fraction(1, 10**18)
    assert historical_execution_quantize_price(too_large) is None
    assert historical_execution_quantize_quantity(Fraction(10) ** 42) is None


# --- approval ----------------------------------------------------------------------------------------------------------


def _approval(**overrides: object) -> HistoricalExecutionEconomicsApproval:
    return approval_for(
        cited_policy(), strategy_spec_digest="e" * 64, data_requirement_registry_digest="f" * 64, **overrides
    )


def test_approval_matches_only_the_exact_policy_and_context() -> None:
    policy = cited_policy()
    context = {
        "strategy_spec_digest": "e" * 64,
        "instrument": INSTRUMENT,
        "market_type": "usdt_perp",
        "data_requirement_registry_digest": "f" * 64,
    }
    approval = approval_for(policy, strategy_spec_digest="e" * 64, data_requirement_registry_digest="f" * 64)
    assert historical_execution_economics_approval_mismatches(approval, policy=policy, **context) == ()
    for field_name, value in (
        ("approved_economics_policy_digest", "1" * 64),
        ("approved_strategy_spec_digest", "2" * 64),
        ("approved_instrument", "ETH-USDT-PERP"),
        ("approved_market_type", "inverse_perp"),
        ("approved_data_requirement_registry_digest", "3" * 64),
        ("approved_quantity_semantics_id", "contracts_v1"),
        ("approved_execution_identity_digest", "4" * 64),
        ("approved_funding_identity_digest", "5" * 64),
    ):
        changed = replace(approval, **{field_name: value})
        assert historical_execution_economics_approval_mismatches(changed, policy=policy, **context) == (field_name,)
    other_policy = cited_policy(taker_fee_bps=d(6))
    assert historical_execution_economics_approval_mismatches(approval, policy=other_policy, **context) == (
        "approved_economics_policy_digest",
    )


def test_approval_canonicalization() -> None:
    approval = _approval()
    assert canonical_historical_execution_economics_approval(None) is None
    assert canonical_historical_execution_economics_approval(approval) == approval
    assert canonical_historical_execution_economics_approval(replace(approval, approval_kind="HUMAN_GOVERNANCE")) == (
        replace(approval, approval_kind=HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE)
    )


@pytest.mark.parametrize(
    ("candidate", "code"),
    [
        ("approved", "economics_approval_malformed"),
        ({"approval_reference": "x"}, "economics_approval_malformed"),
        ("hollow", "approval_reference_invalid"),
        ({"approval_digest": "B" * 64}, "approval_digest_invalid"),
        ({"approval_kind": "MODEL_SELF_APPROVAL"}, "approval_kind_invalid"),
        ({"approval_reference": "approval scheduler"}, "approval_reference"),
        ({"approved_instrument": "BTC USDT"}, "approved_instrument_invalid"),
        ({"approved_economics_policy_digest": None}, "approved_economics_policy_digest_invalid"),
    ],
)
def test_malformed_approval_is_a_construction_error(candidate: object, code: str) -> None:
    if candidate == "hollow":
        candidate = object.__new__(HistoricalExecutionEconomicsApproval)
    elif (
        type(candidate) is dict
        and set(candidate) <= {item.name for item in fields(HistoricalExecutionEconomicsApproval)}
        and (candidate != {"approval_reference": "x"})
    ):
        candidate = _approval(**candidate)
    with pytest.raises(HistoricalExecutionEconomicsPolicyError, match=code):
        canonical_historical_execution_economics_approval(candidate)


# --- totality, parity, determinism --------------------------------------------------------------------------------------


def _corrupted(**changes: object) -> HistoricalExecutionEconomicsPolicy:
    copy = replace(cited_policy())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


@pytest.mark.parametrize(
    "artifact",
    [
        None,
        1,
        "policy",
        b"policy",
        {},
        object(),
        object.__new__(HistoricalExecutionEconomicsPolicy),
        _corrupted(latency_ns=10**5000),
        _corrupted(latency_ns=0),
        _corrupted(taker_fee_bps=0.0005),
        _corrupted(external_fact_citations=None),
        _corrupted(external_fact_citations=({"fact_id": "taker_fee_bps"},)),
        _corrupted(numeric_policy=None),
        _corrupted(conformance="ok"),
        _corrupted(status="ACCEPTED"),
        _corrupted(market_type="inverse_perp"),
        _corrupted(venue_facts_proven=True),
    ],
    ids=lambda value: type(value).__name__,
)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify_historical_execution_economics_policy(artifact)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("latency_ns",), INT64_MAX + 1),
        (("latency_ns",), -1),
        (("latency_ns",), True),
        (("taker_fee_bps",), 5),
        (("taker_fee_bps",), "5"),
        (("initial_equity",), SIXTY_ONE),
        (("numeric_policy", "decimal_scale"), "18"),
        (("numeric_policy", "state_representation_id"), 18),
        (("conformance", "exact_internal_cost_basis_enforced"), 1),
        (("conformance", "almgren_chriss_modeled"), 0),
        (("external_fact_citations", 0, "fact_id"), "fee"),
        (("external_fact_citations", 0, "citation_kind"), "MEMORY"),
        (("status",), "ACCEPTED"),
        (("venue_facts_proven",), None),
    ],
    ids=lambda value: str(value)[:30],
)
def test_parser_refuses_states_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    payload = historical_execution_economics_policy_to_dict(cited_policy())
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    assert historical_execution_economics_policy_payload_is_well_formed(payload) is False


def test_every_builder_state_round_trips_through_the_verifier() -> None:
    tampered = [replace(c, evidence_digest="c" * 64) for c in cited_policy().external_fact_citations]
    for policy in (
        cited_policy(),
        cited_policy(kind=HistoricalExecutionCitationKind.DEEP_RESEARCH_CITED),
        build_historical_execution_economics_policy(**policy_args()),  # type: ignore[arg-type]
        build_historical_execution_economics_policy(**policy_args(external_fact_citations=tampered)),  # type: ignore[arg-type]
    ):
        _assert_receipt_invariants(policy)


def test_policy_is_byte_identical_deterministic_and_citation_order_insensitive() -> None:
    first = cited_policy()
    reversed_citations = build_historical_execution_economics_policy(
        **policy_args(external_fact_citations=tuple(reversed(first.external_fact_citations)))  # type: ignore[arg-type]
    )
    assert json.dumps(historical_execution_economics_policy_to_dict(first), sort_keys=True) == json.dumps(
        historical_execution_economics_policy_to_dict(reversed_citations), sort_keys=True
    )


@pytest.mark.parametrize("flag", ["venue_facts_proven", "production_values_approved", "edge_proven", "live_ready"])
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    verification = verify_historical_execution_economics_policy(_reseal(cited_policy(), **{flag: True}))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flags = dict(HISTORICAL_EXECUTION_POLICY_NON_CLAIM_FLAGS)
    assert set(dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)) <= set(flags)
    defaults = {item.name: item.default for item in fields(HistoricalExecutionEconomicsPolicy) if item.name in flags}
    assert defaults == flags
    assert not set(flags) & set(inspect.signature(build_historical_execution_economics_policy).parameters)
    assert HISTORICAL_EXECUTION_NUMERIC_POLICY_V1.max_wire_integer == INT64_MAX


def test_module_is_pure_and_consumes_only_the_edge_kernel() -> None:
    pit.assert_module_is_pure(policy_module, {"crypto_core.validation.edge_artifact_core"})


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    pit.assert_single_assembly_path(
        policy_module,
        "HistoricalExecutionEconomicsPolicy",
        "_assemble_policy",
        "build_historical_execution_economics_policy",
        "_reassemble_policy",
    )
