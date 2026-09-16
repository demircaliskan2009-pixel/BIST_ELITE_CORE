"""Tests for Edge Factory EF-6 ``crypto_core.validation.edge_walk_forward_oos_evidence``.

Every metric, bound, window count and digest below is a synthetic test fixture, never an approved production value.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import fields, replace
from functools import lru_cache
from pathlib import Path

import pytest

import crypto_core.validation.edge_walk_forward_oos_evidence as oos_module
from crypto_core.data.requirements import data_requirement_registry_digest, default_perp_data_requirement_registry
from crypto_core.strategy.source_packet import build_source_packet
from crypto_core.strategy.spec import strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EDGE_PERMANENT_NON_CLAIM_FLAGS,
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_gate_claim_profile,
    edge_payload_digest,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
    edge_idea_intake_evidence_to_dict,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeEvaluationAssumption,
    EdgeLabelThresholdStructure,
    EdgeLeakageBiasEvidence,
    EdgeLeakageProof,
    EdgeParameterAssignment,
    EdgeParameterBound,
    EdgePreregisteredWindow,
    EdgeUniverseMember,
    EdgeUniverseSnapshot,
    EdgeVariantRegistration,
    build_edge_leakage_bias_evidence,
    build_edge_preregistration_policy,
    edge_leakage_bias_evidence_digest,
    edge_leakage_bias_evidence_from_payload,
    edge_leakage_bias_evidence_to_dict,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeInputSeries,
    build_edge_source_packet_evidence,
    edge_source_packet_evidence_to_dict,
)
from crypto_core.validation.edge_strategy_spec_admission import (
    build_edge_strategy_spec_admission,
    edge_strategy_spec_admission_to_dict,
)
from crypto_core.validation.edge_walk_forward_oos_evidence import (
    EdgeVariantWindowResult,
    EdgeWalkForwardOOSEvidence,
    EdgeWalkForwardOOSEvidenceError,
    build_edge_walk_forward_oos_evidence,
    edge_walk_forward_oos_evidence_digest,
    edge_walk_forward_oos_evidence_from_payload,
    edge_walk_forward_oos_evidence_payload_is_well_formed,
    edge_walk_forward_oos_evidence_to_dict,
    verify_edge_walk_forward_oos_evidence,
)
from crypto_core.validation.leakage_bias_repaint import ValidationFeatureTimestamp, ValidationFundingObservation
from crypto_core.validation.walk_forward import WalkForwardWindow, validate_walk_forward

_PREFIX = "edge_walk_forward_oos_evidence"
_UNSET = object()
_CRITERIA = (
    EdgeKillCriterion(
        "max_drawdown_breach",
        "max_drawdown",
        EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE,
        "0.250000000000000000",
        "rolling_30_utc_days",
    ),
    EdgeKillCriterion(
        "funding_flip_persistence",
        "negative_funding_hours",
        EdgeKillCriterionComparator.KILL_IF_ABOVE,
        "12.000000000000000000",
        "rolling_7_utc_days",
    ),
)
_SPEC_PAYLOAD: dict[str, object] = {
    "schema_version": "1.0",
    "strategy_id": "alpha-funding-carry",
    "strategy_version": "1.0.0",
    "strategy_family": "carry",
    "edge_family": "funding_basis_carry",
    "instrument_universe": ["BTC-PERPETUAL", "ETH-PERPETUAL"],
    "market_type": "inverse_perp",
    "venue_assumptions": ["perpetual_funding_windows"],
    "timeframe": "1h",
    "bar_definition": "time_bars_utc",
    "entry_conditions": ["funding_positive_for_3_windows"],
    "exit_conditions": ["funding_non_positive"],
    "invalidation_conditions": ["basis_dislocation"],
    "risk_caps": {"max_leverage": 2},
    "data_requirements": {"funding_rate": "1h", "mark_price": "1m"},
    "feature_requirements": {"funding_zscore": "rolling_30d"},
    "latency_sensitivity": "low",
    "funding_sensitivity": "high",
    "fee_model_requirement": "maker_taker_schedule",
    "slippage_model_requirement": "book_impact_v1",
    "expected_regime": "positive_funding_regime",
    "failure_modes": ["funding_flip"],
    "kill_switch_triggers": ["funding_flip_persistence", "max_drawdown_breach"],
    "telemetry_fields": ["funding_rate"],
    "promotion_requirements": ["governance_review"],
}
_BOUNDS = (
    EdgeParameterBound("entry_zscore", "1.000000000000000000", "3.000000000000000000"),
    EdgeParameterBound("lookback_days", "7.000000000000000000", "30.000000000000000000"),
)
_STRUCTURES = (
    EdgeLabelThresholdStructure("entry_threshold", "threshold", "enter above the entry zscore", ("entry_zscore",)),
)
_ASSUMPTIONS = (
    EdgeEvaluationAssumption("fee_model", "maker-taker-schedule-v1", "1" * 64),
    EdgeEvaluationAssumption("slippage_model", "book-impact-v1", "2" * 64),
    EdgeEvaluationAssumption("funding_model", "final-funding-cycles-v1", "3" * 64),
)
_SNAPSHOT = EdgeUniverseSnapshot(
    "universe-a",
    1_000,
    (EdgeUniverseMember("BTC-PERPETUAL", 100, None), EdgeUniverseMember("ETH-PERPETUAL", 200, None)),
    "listing-archive:a",
    "4" * 64,
)
_WINDOWS = (
    EdgePreregisteredWindow("w1", 2_000, 3_000, 3_000, 4_000, "universe-a"),
    EdgePreregisteredWindow("w2", 3_000, 4_000, 4_000, 5_000, "universe-a"),
)
_THREE_WINDOWS = (*_WINDOWS, EdgePreregisteredWindow("w3", 4_000, 5_000, 5_000, 6_000, "universe-a"))
_VARIANTS = (
    EdgeVariantRegistration(
        "v-primary",
        (
            EdgeParameterAssignment("entry_zscore", "2.000000000000000000"),
            EdgeParameterAssignment("lookback_days", "14.000000000000000000"),
        ),
    ),
    EdgeVariantRegistration(
        "v-alt",
        (
            EdgeParameterAssignment("entry_zscore", "2.500000000000000000"),
            EdgeParameterAssignment("lookback_days", "14.000000000000000000"),
        ),
    ),
)
_PROOF = EdgeLeakageProof(
    10_000,
    (ValidationFeatureTimestamp("funding_zscore", 9_000, 9_500, 9_600, False, False),),
    (ValidationFundingObservation("perp-venue", 9_000, 9_100, 9_200, 0.0001),),
    (),
    (),
    (),
)


@lru_cache(maxsize=None)
def _chain(intake_id: str = "intake-1") -> tuple[object, object, object]:
    packet = build_source_packet(
        packet_id="pkt-funding-carry-001",
        source_type="academic_paper",
        source_reference="doi:10.0000/funding-carry",
        source_title="Perpetual funding carry",
        rights_status="own_research",
        edge_hypothesis="Persistent positive funding compensates passive carry.",
        content_digest="c" * 64,
        market_scope_tags=("crypto_perpetuals",),
    )
    kill_policy = build_edge_kill_criteria_policy(
        policy_id="kill-policy-1",
        correlation_id="corr-1",
        kill_criteria=_CRITERIA,
        thresholds_approved=True,
        approval_reference="governance-review-1",
        approval_digest="d" * 64,
    )
    intake = build_edge_idea_intake_evidence(
        packet,
        expected_source_packet_digest=packet.packet_digest,
        intake_id=intake_id,
        correlation_id="corr-1",
        candidate_strategy_id="alpha-funding-carry",
        edge_family="funding_basis_carry",
        economic_rationale="Persistent positive funding pays passive carry holders.",
        data_requirement_keys=("funding_rate", "mark_price"),
        declared_regime_dependence="positive_funding_regime",
        kill_criteria_draft=_CRITERIA,
        kill_criteria_policy=kill_policy,
        expected_kill_criteria_policy_digest=kill_policy.policy_digest,
    )
    registry = default_perp_data_requirement_registry()
    series = tuple(
        EdgeInputSeries(
            series_id,
            key,
            f"venue-archive:{key}",
            "own_research",
            "research-note-1",
            "finalized_only",
            "immutable_after_finalization",
            ("BTC-PERPETUAL", "ETH-PERPETUAL"),
        )
        for series_id, key in (("funding-btc-eth", "funding_rate"), ("mark-majors", "mark_price"))
    )
    manifest = build_edge_source_packet_evidence(
        intake,
        expected_root_intake_digest=intake.intake_digest,
        data_requirement_registry=registry,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        manifest_id="manifest-1",
        correlation_id="corr-1",
        input_series=series,
    )
    spec = validate_strategy_spec(_SPEC_PAYLOAD).spec
    admission = build_edge_strategy_spec_admission(
        manifest,
        expected_predecessor_digest=manifest.source_packet_evidence_digest,
        expected_root_intake_digest=intake.intake_digest,
        strategy_spec=spec,
        expected_strategy_spec_digest=strategy_spec_digest(spec),
        admission_id="admission-1",
        correlation_id="corr-1",
        admitted_kill_criteria=_CRITERIA,
        kill_criteria_policy=kill_policy,
        expected_kill_criteria_policy_digest=kill_policy.policy_digest,
    )
    return intake, manifest, admission


def _build_ledger(
    intake_id: str = "intake-1",
    *,
    approve: bool = True,
    min_oos_window_count: int = 2,
    policy_digest: object = _UNSET,
    **overrides: object,
) -> EdgeLeakageBiasEvidence:
    intake, _, admission = _chain(intake_id)
    arguments: dict[str, object] = {
        "expected_predecessor_digest": admission.admission_digest,  # type: ignore[attr-defined]
        "expected_root_intake_digest": intake.intake_digest,  # type: ignore[attr-defined]
        "ledger_id": "ledger-1",
        "correlation_id": "corr-1",
        "parameter_bounds": _BOUNDS,
        "label_threshold_structures": _STRUCTURES,
        "evaluation_assumptions": _ASSUMPTIONS,
        "universe_snapshots": (_SNAPSHOT,),
        "windows": _WINDOWS,
        "variants": _VARIANTS,
        "primary_variant_id": "v-primary",
        "leakage_proof": _PROOF,
    }
    arguments.update(overrides)
    draft = build_edge_leakage_bias_evidence(admission, **arguments)  # type: ignore[arg-type]
    if not approve:
        return draft
    policy = build_edge_preregistration_policy(
        policy_id="prereg-policy-1",
        correlation_id="corr-1",
        candidate_strategy_id="alpha-funding-carry",
        parameter_bounds=_BOUNDS,
        min_oos_window_count=min_oos_window_count,
        approved_variant_ledger_digest=draft.variant_ledger_digest,
        approved=True,
        approval_reference="governance-prereg-1",
        approval_digest="f" * 64,
    )
    arguments["preregistration_policy"] = policy
    arguments["expected_preregistration_policy_digest"] = (
        policy.policy_digest if policy_digest is _UNSET else policy_digest
    )
    return build_edge_leakage_bias_evidence(admission, **arguments)  # type: ignore[arg-type]


@lru_cache(maxsize=None)
def _ledger() -> EdgeLeakageBiasEvidence:
    return _build_ledger()


def _window(window_id: str, **overrides: object) -> WalkForwardWindow:
    values: dict[str, object] = {
        "window_id": window_id,
        "in_sample_sharpe": 1.5,
        "out_of_sample_sharpe": 1.2,
        "oos_expectancy": 0.02,
        "in_sample_hit_rate": 0.55,
        "out_of_sample_hit_rate": 0.53,
        "trade_count": 40,
        "evidence_count": 40,
        "in_sample_max_drawdown": 0.10,
        "oos_max_drawdown": 0.12,
        "oos_profit_factor": 1.4,
    }
    values.update(overrides)
    return WalkForwardWindow(**values)  # type: ignore[arg-type]


def _results(ledger: EdgeLeakageBiasEvidence | None = None, **window_overrides: object) -> tuple:
    ledger = _ledger() if ledger is None else ledger
    return tuple(
        EdgeVariantWindowResult(
            entry.variant_id, entry.variant_registration_digest, _window(window.window_id, **window_overrides)
        )
        for entry in ledger.ledger_entries
        for window in ledger.windows
    )


def _evaluation(ledger: EdgeLeakageBiasEvidence | None = None, **overrides: object) -> EdgeWalkForwardOOSEvidence:
    ledger = _ledger() if ledger is None else ledger
    arguments: dict[str, object] = {
        "expected_predecessor_digest": ledger.ledger_digest,
        "expected_root_intake_digest": _chain()[0].intake_digest,  # type: ignore[attr-defined]
        "evaluation_id": "evaluation-1",
        "correlation_id": "corr-1",
        "evaluation_assumptions": _ASSUMPTIONS,
        "window_results": _results(ledger),
    }
    arguments.update(overrides)
    return build_edge_walk_forward_oos_evidence(ledger, **arguments)  # type: ignore[arg-type]


def _redigest(evidence: EdgeWalkForwardOOSEvidence) -> EdgeWalkForwardOOSEvidence:
    return replace(evidence, evaluation_digest=edge_walk_forward_oos_evidence_digest(evidence))


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _assert_receipt_invariants(evidence: EdgeWalkForwardOOSEvidence) -> None:
    verification = verify_edge_walk_forward_oos_evidence(evidence)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == evidence.evaluation_digest
    assert edge_walk_forward_oos_evidence_from_payload(json.loads(verification.canonical_json)) == evidence
    assert evidence.advances is (
        evidence.status is EdgeEvidenceStatus.READY and evidence.gate_verdict is EdgeGateVerdict.PASS
    )
    assert evidence.preregistration_sealed is (evidence.status is EdgeEvidenceStatus.READY)
    assert evidence.performance_data_consumed is (evidence.walk_forward_result is not None)
    assert evidence.regime_split_report == EDGE_REGIME_EVIDENCE_UNAVAILABLE
    assert evidence.regime_evidence_available is False
    for name, value in EDGE_PERMANENT_NON_CLAIM_FLAGS:
        assert getattr(evidence, name) is value
    if evidence.status is EdgeEvidenceStatus.REJECTED:
        assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert evidence.integrity_reason_codes
        assert evidence.verdict_reason_codes == ()
        assert evidence.walk_forward_result is None
    else:
        assert evidence.integrity_reason_codes == ()


def _codes(evidence: EdgeWalkForwardOOSEvidence) -> set[str]:
    return set(evidence.verdict_reason_codes)


# --- happy path and milestone profile -----------------------------------------------------------------------------------


def test_registered_primary_evaluation_passes_and_re_proves() -> None:
    ledger = _ledger()
    intake, manifest, admission = _chain()
    evidence = _evaluation()
    assert (evidence.status, evidence.gate_verdict, evidence.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert evidence.gate_id == "EF-6"
    assert evidence.predecessor_gate_id == "EF-5"
    assert evidence.predecessor_digest == ledger.ledger_digest
    assert evidence.root_intake_digest == intake.intake_digest  # type: ignore[attr-defined]
    assert evidence.admission_digest == admission.admission_digest  # type: ignore[attr-defined]
    assert evidence.source_packet_digest == manifest.source_packet_evidence_digest  # type: ignore[attr-defined]
    assert evidence.primary_variant_id == ledger.primary_variant_id == "v-primary"
    assert evidence.multiple_testing_count == 2
    assert evidence.variant_ledger_digest == ledger.variant_ledger_digest
    assert evidence.approved_min_oos_window_count == 2
    primary_windows = [_window("w1"), _window("w2")]
    assert evidence.walk_forward_result == validate_walk_forward(primary_windows, min_oos_windows=2)
    assert evidence.walk_forward_result.supportive is True  # type: ignore[union-attr]
    assert evidence.regime_label_binding_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert (evidence.preregistration_sealed, evidence.performance_data_consumed) == (True, True)
    assert {name: getattr(evidence, name) for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS} == dict(
        edge_gate_claim_profile("EF-6")
    )
    _assert_receipt_invariants(evidence)
    assert edge_walk_forward_oos_evidence_payload_is_well_formed(edge_walk_forward_oos_evidence_to_dict(evidence))


def test_evaluation_is_deterministic_and_result_order_insensitive() -> None:
    assert _evaluation(window_results=tuple(reversed(_results()))) == _evaluation()


def test_supportive_oos_evidence_never_claims_edge_admission_or_readiness() -> None:
    evidence = _evaluation()
    for name in (
        "edge_proven",
        "profitability_proven",
        "candidate_admitted_to_paper",
        "kill_criteria_sealed",
        "oos_evidence_consumed",
        "operational_readiness",
        "live_ready",
        "shadow_ready",
        "deribit_ready",
        "private_api_ready",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "scheduler_enabled",
        "auto_loop_enabled",
        "regime_evidence_available",
    ):
        assert getattr(evidence, name) is False


# --- explicit approved minimum OOS window count (I17) -------------------------------------------------------------------


def test_approved_minimum_is_passed_explicitly_not_the_validator_default() -> None:
    windows = [_window("w1"), _window("w2")]
    assert validate_walk_forward(windows).supportive is False
    assert "insufficient_valid_oos_windows" in validate_walk_forward(windows).rejection_reasons
    assert _evaluation().gate_verdict is EdgeGateVerdict.PASS


@pytest.mark.parametrize(("approved_minimum", "expect_insufficient"), [(3, True), (2, False)])
def test_approved_minimum_controls_the_validator(approved_minimum: int, expect_insufficient: bool) -> None:
    ledger = _build_ledger(windows=_THREE_WINDOWS, min_oos_window_count=approved_minimum)
    assert ledger.gate_verdict is EdgeGateVerdict.PASS
    results = tuple(
        replace(result, window=_window(result.window.window_id, trade_count=0))
        if result.window.window_id == "w3"
        else result
        for result in _results(ledger)
    )
    evidence = _evaluation(ledger, window_results=results)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert (_code("walk_forward:insufficient_valid_oos_windows") in _codes(evidence)) is expect_insufficient
    assert evidence.walk_forward_result.valid_oos_window_count == 2  # type: ignore[union-attr]
    _assert_receipt_invariants(evidence)


def test_ledger_window_count_below_the_approved_minimum_is_never_interpreted() -> None:
    ledger = _build_ledger(min_oos_window_count=3)
    assert ledger.gate_verdict is EdgeGateVerdict.FAIL
    evidence = _evaluation(ledger)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _codes(evidence) == {_code("predecessor_not_advanced:FAIL")}
    assert (evidence.walk_forward_result, evidence.performance_data_consumed) == (None, False)


def test_validator_is_called_once_with_an_explicit_minimum_keyword() -> None:
    tree = ast.parse(Path(oos_module.__file__).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "validate_walk_forward"
    ]
    assert len(calls) == 1
    assert [keyword.arg for keyword in calls[0].keywords] == ["min_oos_windows"]


# --- registered-only interpretation (I6, I18) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("results_factory", "expected"),
    [
        (
            lambda: (*_results(), EdgeVariantWindowResult("v-winner", "a" * 64, _window("w1"))),
            {"unregistered_variant_result:v-winner"},
        ),
        (
            lambda: (
                *_results(),
                EdgeVariantWindowResult(
                    "v-primary", _ledger().ledger_entries[1].variant_registration_digest, _window("w9")
                ),
            ),
            {"unregistered_window_result:v-primary:w9"},
        ),
        (
            lambda: tuple(
                replace(result, variant_registration_digest=_ledger().ledger_entries[0].variant_registration_digest)
                if result.variant_id == "v-primary" and result.window.window_id == "w1"
                else result
                for result in _results()
            ),
            {"variant_registration_digest_mismatch:v-primary:w1"},
        ),
        (
            lambda: tuple(result for result in _results() if result.variant_id != "v-alt"),
            {"variant_window_result_missing:v-alt:w1", "variant_window_result_missing:v-alt:w2"},
        ),
    ],
)
def test_unregistered_or_incomplete_results_never_advance(results_factory: object, expected: set[str]) -> None:
    evidence = _evaluation(window_results=results_factory())  # type: ignore[operator]
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert {_code(code) for code in expected} <= _codes(evidence)
    assert evidence.advances is False
    _assert_receipt_invariants(evidence)


def test_missing_primary_window_is_both_incomplete_and_insufficient() -> None:
    results = tuple(
        result for result in _results() if not (result.variant_id == "v-primary" and result.window.window_id == "w2")
    )
    evidence = _evaluation(window_results=results)
    assert {
        _code("variant_window_result_missing:v-primary:w2"),
        _code("walk_forward:insufficient_valid_oos_windows"),
    } <= _codes(evidence)


def test_primary_variant_cannot_change_after_performance() -> None:
    evidence = _evaluation()
    forged = _redigest(replace(evidence, primary_variant_id="v-alt"))
    verification = verify_edge_walk_forward_oos_evidence(forged)
    assert verification.intact is False
    assert _code("field_mismatch:primary_variant_id") in verification.reason_codes
    assert "primary_variant_id" not in inspect.signature(build_edge_walk_forward_oos_evidence).parameters


def test_only_the_primary_variant_is_interpreted() -> None:
    results = tuple(
        replace(result, window=_window(result.window.window_id, out_of_sample_sharpe=-1.0))
        if result.variant_id == "v-alt"
        else result
        for result in _results()
    )
    evidence = _evaluation(window_results=results)
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    assert evidence.walk_forward_result == validate_walk_forward([_window("w1"), _window("w2")], min_oos_windows=2)


# --- walk-forward outcomes and numeric discipline -----------------------------------------------------------------------


def test_non_supportive_walk_forward_is_valid_negative_evidence() -> None:
    evidence = _evaluation(window_results=_results(out_of_sample_sharpe=0.1))
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code("walk_forward_not_supportive") in _codes(evidence)
    assert _code("walk_forward:window[0]:oos_sharpe_below_ratio") in _codes(evidence)
    assert evidence.performance_data_consumed is True
    _assert_receipt_invariants(evidence)


def test_copied_supportive_summary_cannot_override_the_recomputed_result() -> None:
    failing = _evaluation(window_results=_results(out_of_sample_sharpe=0.1))
    passing = _evaluation()
    forged = _redigest(
        replace(
            failing,
            walk_forward_result=passing.walk_forward_result,
            gate_verdict=EdgeGateVerdict.PASS,
            advances=True,
            verdict_reason_codes=(),
        )
    )
    verification = verify_edge_walk_forward_oos_evidence(forged)
    assert verification.intact is False
    assert _code("field_mismatch:walk_forward_result") in verification.reason_codes


@pytest.mark.parametrize(
    ("window_overrides", "code"),
    [
        ({"out_of_sample_sharpe": float("nan")}, "window_result_metric_invalid:out_of_sample_sharpe"),
        ({"oos_expectancy": float("inf")}, "window_result_metric_invalid:oos_expectancy"),
        ({"oos_profit_factor": True}, "window_result_metric_invalid:oos_profit_factor"),
        ({"in_sample_sharpe": "1.5"}, "window_result_metric_invalid:in_sample_sharpe"),
        ({"trade_count": 40.0}, "window_result_count_invalid:trade_count"),
        ({"evidence_count": False}, "window_result_count_invalid:evidence_count"),
    ],
)
def test_non_finite_or_mistyped_window_evidence_is_a_construction_error(
    window_overrides: dict[str, object], code: str
) -> None:
    with pytest.raises(EdgeWalkForwardOOSEvidenceError, match=f"^{_code(code)}$"):
        _evaluation(window_results=_results(**window_overrides))


@pytest.mark.parametrize(
    ("results", "code"),
    [
        ((), "window_results_empty"),
        ("results", "window_results_malformed"),
        (({"variant_id": "v-primary"},), "window_result_malformed"),
        ((EdgeVariantWindowResult("v-primary", "a" * 64, {"window_id": "w1"}),), "window_result_window_malformed"),  # type: ignore[arg-type]
        (
            (EdgeVariantWindowResult("v-primary", "A" * 64, _window("w1")),),
            "window_result_variant_registration_digest_invalid",
        ),
        ((EdgeVariantWindowResult("V", "a" * 64, _window("w1")),), "window_result_variant_id_invalid"),
        ((EdgeVariantWindowResult("v-primary", "a" * 64, _window("W1")),), "window_result_window_id_invalid"),
    ],
)
def test_malformed_results_are_construction_errors(results: object, code: str) -> None:
    with pytest.raises(EdgeWalkForwardOOSEvidenceError, match=f"^{_code(code)}$"):
        _evaluation(window_results=results)


def test_duplicate_result_entries_are_construction_errors() -> None:
    with pytest.raises(EdgeWalkForwardOOSEvidenceError, match=f"^{_code('window_result_duplicate')}$"):
        _evaluation(window_results=(*_results(), _results()[0]))


def test_integer_and_float_metrics_round_trip_exactly() -> None:
    results = _results(in_sample_sharpe=2, out_of_sample_sharpe=1.25, oos_max_drawdown=0)
    evidence = _evaluation(window_results=results)
    parsed = edge_walk_forward_oos_evidence_from_payload(
        json.loads(edge_canonical_json(edge_walk_forward_oos_evidence_to_dict(evidence)))
    )
    assert parsed == evidence
    assert type(parsed.window_results[0].window.in_sample_sharpe) is int
    assert type(parsed.window_results[0].window.out_of_sample_sharpe) is float


# --- cost assumption binding (I19) and propagation --------------------------------------------------------------------


@pytest.mark.parametrize(
    "assumptions",
    [
        _ASSUMPTIONS[:2],
        (replace(_ASSUMPTIONS[0], model_id="cheaper-fee-model-v2"), *_ASSUMPTIONS[1:]),
        (replace(_ASSUMPTIONS[2], model_digest=None), *_ASSUMPTIONS[:2]),
        (replace(_ASSUMPTIONS[1], model_digest="9" * 64), _ASSUMPTIONS[0], _ASSUMPTIONS[2]),
    ],
)
def test_evaluation_must_declare_exactly_the_preregistered_assumptions(assumptions: tuple) -> None:
    evidence = _evaluation(evaluation_assumptions=assumptions)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code("evaluation_assumptions_mismatch") in _codes(evidence)


@pytest.mark.parametrize(
    ("ledger_factory", "verdict"),
    [
        (
            lambda: _build_ledger(
                evaluation_assumptions=(replace(_ASSUMPTIONS[0], model_digest=None), *_ASSUMPTIONS[1:])
            ),
            EdgeGateVerdict.NEEDS_EXTERNAL_FACTS,
        ),
        (lambda: _build_ledger(approve=False), EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL),
        (lambda: _build_ledger(leakage_proof=replace(_PROOF, feature_timestamps=())), EdgeGateVerdict.FAIL),
    ],
)
def test_non_advancing_ledger_propagates_its_verdict_without_interpreting_results(
    ledger_factory: object, verdict: EdgeGateVerdict
) -> None:
    ledger = ledger_factory()  # type: ignore[operator]
    assert ledger.gate_verdict is verdict
    evidence = _evaluation(ledger)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is verdict
    assert _codes(evidence) == {_code(f"predecessor_not_advanced:{verdict.value}")}
    assert evidence.walk_forward_result is None
    assert (evidence.preregistration_sealed, evidence.performance_data_consumed) == (True, False)
    _assert_receipt_invariants(evidence)


# --- full back-chain re-proof and splice matrix (I2, I16) ---------------------------------------------------------------


def _json(payload: object) -> dict:
    return json.loads(edge_canonical_json(payload))


def _ledger_with_foreign_level(level: str) -> EdgeLeakageBiasEvidence:
    other_intake, other_manifest, other_admission = _chain("intake-2")
    payload = _json(edge_leakage_bias_evidence_to_dict(_ledger()))
    admission = payload["predecessor_binding"]["snapshot"]
    manifest = admission["predecessor_binding"]["snapshot"]
    if level == "EF-2":
        manifest["root_intake_binding"] = {
            "expected_digest": other_intake.intake_digest,  # type: ignore[attr-defined]
            "snapshot": _json(edge_idea_intake_evidence_to_dict(other_intake)),  # type: ignore[arg-type]
        }
        manifest["root_intake_digest"] = manifest["predecessor_digest"] = other_intake.intake_digest  # type: ignore[attr-defined]
        manifest["source_packet_evidence_digest"] = edge_payload_digest(manifest, "source_packet_evidence_digest")
    if level in ("EF-2", "EF-3"):
        if level == "EF-3":
            manifest = _json(edge_source_packet_evidence_to_dict(other_manifest))  # type: ignore[arg-type]
        admission["predecessor_binding"] = {
            "expected_digest": manifest["source_packet_evidence_digest"],
            "snapshot": manifest,
        }
        admission["predecessor_digest"] = manifest["source_packet_evidence_digest"]
        admission["admission_digest"] = edge_payload_digest(admission, "admission_digest")
    if level == "EF-4":
        admission = _json(edge_strategy_spec_admission_to_dict(other_admission))  # type: ignore[arg-type]
    payload["predecessor_binding"] = {"expected_digest": admission["admission_digest"], "snapshot": admission}
    payload["predecessor_digest"] = admission["admission_digest"]
    payload["ledger_digest"] = edge_payload_digest(payload, "ledger_digest")
    return edge_leakage_bias_evidence_from_payload(payload)


@pytest.mark.parametrize("level", ["EF-2", "EF-3", "EF-4"])
def test_foreign_artifact_at_any_nested_level_is_rejected(level: str) -> None:
    forged = _ledger_with_foreign_level(level)
    evidence = _evaluation(forged, window_results=_results())
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.integrity_reason_codes
    assert evidence.walk_forward_result is None
    _assert_receipt_invariants(evidence)


def test_foreign_ledger_at_ef5_is_rejected_under_either_anchor() -> None:
    foreign = _build_ledger("intake-2")
    assert foreign.gate_verdict is EdgeGateVerdict.PASS
    spliced = _evaluation(foreign, window_results=_results(foreign))
    assert spliced.integrity_reason_codes == (_code("chain_splice_root_intake_mismatch"),)
    swapped = _evaluation(
        foreign, expected_predecessor_digest=_ledger().ledger_digest, window_results=_results(foreign)
    )
    assert swapped.integrity_reason_codes == (_code("ledger_digest_mismatch"),)


def test_locally_redigested_ledger_with_an_appended_variant_is_rejected() -> None:
    ledger = _ledger()
    appended = replace(
        ledger,
        variants=(
            *ledger.variants,
            EdgeVariantRegistration(
                "v-winner",
                (
                    EdgeParameterAssignment("entry_zscore", "2.900000000000000000"),
                    EdgeParameterAssignment("lookback_days", "7.000000000000000000"),
                ),
            ),
        ),
    )
    appended = replace(appended, ledger_digest=edge_leakage_bias_evidence_digest(appended))
    for anchor in (ledger.ledger_digest, appended.ledger_digest):
        evidence = _evaluation(appended, expected_predecessor_digest=anchor, window_results=_results())
        assert evidence.status is EdgeEvidenceStatus.REJECTED
        assert any(code.startswith(_code("ledger_")) for code in evidence.integrity_reason_codes)


@pytest.mark.parametrize(
    ("ledger_factory", "overrides", "expected"),
    [
        (lambda: _ledger(), {"correlation_id": "corr-2"}, "ledger_correlation_mismatch"),
        (lambda: _build_ledger(policy_digest="0" * 64), {}, "ledger_rejected"),
    ],
)
def test_ledger_authority_failures_are_truthful_rejected_receipts(
    ledger_factory: object, overrides: dict[str, object], expected: str
) -> None:
    ledger = ledger_factory()  # type: ignore[operator]
    evidence = _evaluation(ledger, **overrides)
    assert evidence.integrity_reason_codes == (_code(expected),)
    assert (evidence.preregistration_sealed, evidence.performance_data_consumed) == (False, False)
    _assert_receipt_invariants(evidence)


# --- construction errors ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("predecessor", "code"),
    [
        (None, "predecessor_malformed"),
        ({"ledger_id": "ledger-1"}, "predecessor_malformed"),
        (object.__new__(EdgeLeakageBiasEvidence), "predecessor_not_serializable"),
    ],
)
def test_malformed_predecessor_is_a_construction_error(predecessor: object, code: str) -> None:
    with pytest.raises(EdgeWalkForwardOOSEvidenceError, match=f"^{_code(code)}$"):
        build_edge_walk_forward_oos_evidence(
            predecessor,  # type: ignore[arg-type]
            expected_predecessor_digest="a" * 64,
            expected_root_intake_digest="a" * 64,
            evaluation_id="evaluation-1",
            correlation_id="corr-1",
            evaluation_assumptions=_ASSUMPTIONS,
            window_results=_results(),
        )


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"expected_predecessor_digest": "A" * 64}, "predecessor_expected_digest_invalid"),
        ({"expected_root_intake_digest": None}, "root_intake_digest_invalid"),
        ({"evaluation_id": "evaluation live"}, "forbidden_scope_token:evaluation_id"),
        ({"correlation_id": " corr-1"}, "correlation_id_invalid"),
        ({"evaluation_assumptions": "fee_model"}, "evaluation_assumptions_invalid"),
        ({"evaluation_assumptions": (_ASSUMPTIONS[0], _ASSUMPTIONS[0])}, "evaluation_assumptions_invalid"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeWalkForwardOOSEvidenceError, match=f"^{_code(code)}$"):
        _evaluation(**overrides)


# --- RC1: builder domain equals verifier reassembly domain ------------------------------------------------------------


@pytest.mark.parametrize(
    "replacement",
    [
        {"predecessor_binding": EdgeAuthorityBinding(snapshot_json="", expected_digest="")},
        {"predecessor_binding": EdgeAuthorityBinding(snapshot_json='{"a":1}', expected_digest="a" * 64)},
        {"predecessor_binding": None},
        {"root_intake_digest": "not-a-digest"},
    ],
)
def test_partial_binding_and_anchor_states_never_verify(replacement: dict[str, object]) -> None:
    verification = verify_edge_walk_forward_oos_evidence(replace(_evaluation(), **replacement))
    assert verification.intact is False
    assert len(verification.reason_codes) == 1


def _mutated_payload(path: tuple[object, ...], value: object) -> dict:
    payload = _json(edge_walk_forward_oos_evidence_to_dict(_evaluation()))
    node = payload
    for key in path[:-1]:
        node = node[key]
    if value is _UNSET:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return payload


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("predecessor_binding", "snapshot"), {}),
        (("predecessor_binding", "snapshot", "preregistration_sealed"), "true"),
        (("window_results", 0, "window", "out_of_sample_sharpe"), "1.2"),
        (("window_results", 0, "window", "trade_count"), 40.5),
        (("window_results", 0, "window", "oos_profit_factor"), None),
        (("window_results", 0, "variant_id"), _UNSET),
        (("walk_forward_result", "supportive"), "yes"),
        (("walk_forward_result", "window_results", 0, "valid"), 1),
        (("walk_forward_result", "total_window_count"), 2.0),
        (("performance_data_consumed",), None),
    ],
)
def test_parser_refuses_every_state_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    assert edge_walk_forward_oos_evidence_payload_is_well_formed(_mutated_payload(path, value)) is False


# --- RC2: public verifier totality ------------------------------------------------------------------------------------


def _corrupted(**changes: object) -> EdgeWalkForwardOOSEvidence:
    copy = replace(_evaluation())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


@lru_cache(maxsize=None)
def _totality_objects() -> tuple[object, ...]:
    first = _results()[0]
    return (
        None,
        3,
        "evaluation",
        object(),
        {},
        _ledger(),
        object.__new__(EdgeWalkForwardOOSEvidence),
        _corrupted(window_results=None),
        _corrupted(window_results=(replace(first, window=replace(first.window, out_of_sample_sharpe=float("nan"))),)),
        _corrupted(window_results=({"variant_id": "v-primary"},)),
        _corrupted(walk_forward_result="supportive"),
        _corrupted(predecessor_binding=object.__new__(EdgeAuthorityBinding)),
        _corrupted(evaluation_assumptions=(object(),)),
        _corrupted(multiple_testing_count=float("inf")),
        _corrupted(evaluation_id="evaluation scheduler"),
    )


@pytest.mark.parametrize("index", range(15))
def test_public_verifier_is_total_for_any_object(index: int) -> None:
    verification = verify_edge_walk_forward_oos_evidence(_totality_objects()[index])
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


# --- RC3: builder/verifier round trips for every state ----------------------------------------------------------------

_STATE_BUILDERS = {
    "pass": lambda: _evaluation(),
    "fail": lambda: _evaluation(window_results=_results(out_of_sample_sharpe=0.1)),
    "needs_external_facts": lambda: _evaluation(
        _build_ledger(universe_snapshots=(replace(_SNAPSHOT, membership_evidence_digest=None),))
    ),
    "needs_governance_approval": lambda: _evaluation(_build_ledger(approve=False)),
    "rejected_splice": lambda: _evaluation(_build_ledger("intake-2")),
    "rejected_ledger": lambda: _evaluation(expected_predecessor_digest="0" * 64),
}


@pytest.mark.parametrize("state", sorted(_STATE_BUILDERS))
def test_every_builder_state_round_trips_through_the_verifier(state: str) -> None:
    evidence = _STATE_BUILDERS[state]()
    _assert_receipt_invariants(evidence)
    expected = EdgeEvidenceStatus.REJECTED if state.startswith("rejected") else EdgeEvidenceStatus.READY
    assert evidence.status is expected


# --- RC4: binding canonicality ----------------------------------------------------------------------------------------


def test_binding_is_canonical_and_noncanonical_in_memory_binding_never_verifies() -> None:
    evidence = _evaluation()
    binding = evidence.predecessor_binding
    assert binding.snapshot_json == edge_canonical_json(json.loads(binding.snapshot_json))
    pretty = replace(binding, snapshot_json=json.dumps(json.loads(binding.snapshot_json), indent=2))
    verification = verify_edge_walk_forward_oos_evidence(replace(evidence, predecessor_binding=pretty))
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)


# --- regime pending pattern and structural non-claims -----------------------------------------------------------------


def test_regime_split_report_is_the_digest_bound_pending_pattern() -> None:
    evidence = _evaluation()
    assert not {"regime", "regime_split_report"} & set(
        inspect.signature(build_edge_walk_forward_oos_evidence).parameters
    )
    for changes in (
        {"regime_split_report": "bull:supportive"},
        {"regime_label_binding_status": "RF_BOUND"},
        {"regime_evidence_available": True},
    ):
        assert verify_edge_walk_forward_oos_evidence(_redigest(replace(evidence, **changes))).intact is False


def test_permanent_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    defaults = {field.name: field.default for field in fields(EdgeWalkForwardOOSEvidence)}
    assert {name: defaults[name] for name, _ in EDGE_PERMANENT_NON_CLAIM_FLAGS} == dict(EDGE_PERMANENT_NON_CLAIM_FLAGS)
    flag_names = {name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS}
    assert not flag_names & set(inspect.signature(build_edge_walk_forward_oos_evidence).parameters)


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("edge_proven", True),
        ("profitability_proven", True),
        ("candidate_admitted_to_paper", True),
        ("oos_evidence_consumed", True),
        ("operational_readiness", True),
        ("performance_data_consumed", False),
    ],
)
def test_forged_claims_fail_verification(flag: str, value: bool) -> None:
    verification = verify_edge_walk_forward_oos_evidence(_redigest(replace(_evaluation(), **{flag: value})))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


# --- structural purity ------------------------------------------------------------------------------------------------

_FORBIDDEN_MODULES = (
    "math",
    "time",
    "datetime",
    "random",
    "secrets",
    "uuid",
    "socket",
    "ssl",
    "urllib",
    "http",
    "requests",
    "httpx",
    "aiohttp",
    "threading",
    "asyncio",
    "multiprocessing",
    "subprocess",
    "os",
    "sys",
    "pathlib",
    "shutil",
    "tempfile",
    "sqlite3",
    "logging",
)
_FORBIDDEN_CALLS = frozenset(
    {"open", "Path", "float", "now", "utcnow", "time", "time_ns", "perf_counter", "monotonic", "getenv", "print"}
)


def _module_tree() -> ast.Module:
    return ast.parse(Path(oos_module.__file__).read_text(encoding="utf-8"))


def test_module_has_no_io_clock_randomness_or_float_literal() -> None:
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in _FORBIDDEN_CALLS
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
        if isinstance(node, ast.Attribute):
            assert node.attr != "environ"


def test_module_consumes_only_public_substrate_names() -> None:
    crypto_imports: dict[str, set[str]] = {}
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("crypto_core"):
            crypto_imports.setdefault(node.module, set()).update(alias.name for alias in node.names)
    assert set(crypto_imports) == {
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.edge_leakage_bias_evidence",
        "crypto_core.validation.walk_forward",
    }
    for names in crypto_imports.values():
        assert not {name for name in names if name.startswith("_")}


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    constructor_calls = 0
    calls_by_function: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(_module_tree()) if isinstance(node, ast.FunctionDef)):
        names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        calls_by_function[function.name] = set(names)
        constructor_calls += names.count("EdgeWalkForwardOOSEvidence")
    assert constructor_calls == 1
    assert "EdgeWalkForwardOOSEvidence" in calls_by_function["_assemble_evaluation"]
    assert "_assemble_evaluation" in calls_by_function["build_edge_walk_forward_oos_evidence"]
    assert "_assemble_evaluation" in calls_by_function["_reassemble_evaluation"]
    assert "reprove_edge_admitted_chain" in calls_by_function["_chain_authority"]
    assert "verify_edge_leakage_bias_evidence" in calls_by_function["_chain_authority"]
