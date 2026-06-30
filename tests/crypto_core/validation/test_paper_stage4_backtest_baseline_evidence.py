"""Tests for deterministic paper Stage-4 backtest-baseline evidence."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.strategy.spec import (
    StrategySpec,
    strategy_spec_digest,
    validate_strategy_spec,
)
from crypto_core.validation import paper_stage4_backtest_baseline_evidence as baseline_module
from crypto_core.validation.paper_edge_identity_evidence import (
    PaperEdgeIdentityEvidence,
    build_paper_edge_identity_evidence,
    paper_edge_identity_evidence_digest,
    paper_edge_identity_evidence_to_dict,
)
from crypto_core.validation.paper_stage4_backtest_baseline_evidence import (
    PaperStage4BacktestBaselineEvidence,
    PaperStage4BacktestBaselineEvidenceError,
    PaperStage4BacktestBaselineEvidenceStatus,
    build_paper_stage4_backtest_baseline_evidence,
    paper_stage4_backtest_baseline_evidence_digest,
    paper_stage4_backtest_baseline_evidence_to_dict,
)
from crypto_core.validation.paper_vs_backtest_comparator_bridge import (
    _backtest_baseline_digest as bridge_baseline_digest,
)
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    build_stage4_backtest_baseline,
    stage4_backtest_baseline_to_dict,
)

_MARKET = "BTC-PERPETUAL"


class _LiarStr(str):
    """A ``str`` subclass rejected by exact ``type(x) is str`` checks."""


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _canonical(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _spec(**overrides: object) -> StrategySpec:
    payload: dict[str, object] = {
        "schema_version": "strategy-spec.v1",
        "strategy_id": "alpha-funding-carry",
        "strategy_version": "1.0.0",
        "strategy_family": "carry",
        "edge_family": "funding_basis_carry",
        "instrument_universe": ["BTC-PERPETUAL", "ETH-PERPETUAL"],
        "market_type": "usdt_perp",
        "venue_assumptions": ["perp_linear"],
        "timeframe": "1h",
        "bar_definition": "time_1h",
        "entry_conditions": ["funding_positive"],
        "exit_conditions": ["funding_neutral"],
        "invalidation_conditions": ["regime_break"],
        "risk_caps": {"max_leverage": 2.0},
        "data_requirements": {"funding_rate": "1h"},
        "feature_requirements": {"funding_zscore": "rolling"},
        "latency_sensitivity": "low",
        "funding_sensitivity": "high",
        "fee_model_requirement": "taker_10bps",
        "slippage_model_requirement": "depth_aware",
        "expected_regime": "ranging",
        "failure_modes": ["funding_flip"],
        "kill_switch_triggers": ["max_dd"],
        "telemetry_fields": ["funding"],
        "promotion_requirements": ["walk_forward"],
    }
    payload.update(overrides)
    result = validate_strategy_spec(payload)
    assert result.accepted, result.rejection_reasons + result.needs_research_reasons
    assert result.spec is not None
    return result.spec


def _edge_identity(**overrides: object) -> PaperEdgeIdentityEvidence:
    spec = _spec()
    payload: dict[str, object] = {
        "expected_strategy_spec_digest": strategy_spec_digest(spec),
        "market_symbol": _MARKET,
        "edge_identity_id": "edge-identity-1",
        "paper_id": "paper-1",
        "correlation_id": "corr-1",
        "metadata": {"purpose": "paper edge identity"},
    }
    payload.update(overrides)
    return build_paper_edge_identity_evidence(spec, **payload)  # type: ignore[arg-type]


def _baseline(edge_id: str, **overrides: object) -> Stage4BacktestBaseline:
    kwargs: dict[str, object] = {
        "baseline_id": "baseline-1",
        "edge_id": edge_id,
        "as_of_ns": 1_700_000_000_000_000_000,
        "backtest_sharpe": 1.5,
        "backtest_hit_rate": 0.55,
        "backtest_slippage_bps": 2.0,
        "backtest_fill_rate": 0.9,
        "source_window_ids": ("wf-1", "wf-2"),
    }
    kwargs.update(overrides)
    return build_stage4_backtest_baseline(**kwargs)  # type: ignore[arg-type]


def _baseline_digest(baseline: Stage4BacktestBaseline) -> str:
    return _canonical(stage4_backtest_baseline_to_dict(baseline))


def _build(**overrides: object) -> PaperStage4BacktestBaselineEvidence:
    edge = overrides.pop("edge_identity", None) or _edge_identity()
    baseline = overrides.pop("backtest_baseline", None)
    if baseline is None:
        baseline = _baseline(edge.paper_edge_id)
    # Compute defaults lazily: a deliberately non-finite baseline cannot be canonicalized, so the caller must
    # supply an explicit anchor (evaluating ``_baseline_digest`` eagerly would raise before the build runs).
    if "expected_baseline_digest" in overrides:
        expected_baseline_digest = overrides.pop("expected_baseline_digest")
    else:
        expected_baseline_digest = _baseline_digest(baseline)
    if "expected_edge_identity_digest" in overrides:
        expected_edge_identity_digest = overrides.pop("expected_edge_identity_digest")
    else:
        expected_edge_identity_digest = edge.edge_identity_digest
    payload: dict[str, object] = {
        "expected_baseline_digest": expected_baseline_digest,
        "edge_identity": edge,
        "expected_edge_identity_digest": expected_edge_identity_digest,
        "baseline_evidence_id": "baseline-evidence-1",
        "correlation_id": "corr-1",
        "metadata": {"purpose": "stage4 baseline binding"},
    }
    payload.update(overrides)
    return build_paper_stage4_backtest_baseline_evidence(baseline, **payload)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# 1. Public API / duplicate
# --------------------------------------------------------------------------------------------------


def test_public_api_exports_present() -> None:
    assert set(baseline_module.__all__) == {
        "PaperStage4BacktestBaselineEvidence",
        "PaperStage4BacktestBaselineEvidenceError",
        "PaperStage4BacktestBaselineEvidenceStatus",
        "build_paper_stage4_backtest_baseline_evidence",
        "paper_stage4_backtest_baseline_evidence_digest",
        "paper_stage4_backtest_baseline_evidence_to_dict",
    }


def test_output_is_frozen() -> None:
    evidence = _build()
    with pytest.raises(FrozenInstanceError):
        evidence.ready = False  # type: ignore[misc]


def test_status_enum_values() -> None:
    assert PaperStage4BacktestBaselineEvidenceStatus.READY.value == "READY"
    assert PaperStage4BacktestBaselineEvidenceStatus.REJECTED.value == "REJECTED"


# --------------------------------------------------------------------------------------------------
# 2. Happy READY
# --------------------------------------------------------------------------------------------------


def test_happy_ready() -> None:
    evidence = _build()
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.READY
    assert evidence.ready is True
    assert evidence.reason_codes == ()
    assert evidence.baseline_bound is True
    assert evidence.same_edge_identity_equal is True
    assert evidence.baseline_constructed is False
    assert evidence.binding_strength == "BASELINE_EDGE_ID_IDENTITY_BOUND"
    assert evidence.baseline_source == "caller_supplied_stage4_backtest_baseline.v1"
    assert evidence.same_edge_identity_policy == "baseline_edge_id_equals_paper_edge_identity.v1"
    assert evidence.schema_id == "paper-stage4-backtest-baseline-evidence.v1"


def test_ready_binds_identity_echo_fields() -> None:
    edge = _edge_identity()
    evidence = _build(edge_identity=edge)
    assert evidence.edge_id == edge.paper_edge_id
    assert evidence.paper_edge_id == edge.paper_edge_id
    assert _is_hex64(evidence.edge_id)
    assert evidence.strategy_id == edge.strategy_id
    assert evidence.strategy_version == edge.strategy_version
    assert evidence.edge_family == edge.edge_family
    assert evidence.market_type == edge.market_type
    assert evidence.market_symbol == edge.market_symbol
    assert evidence.edge_identity_id == edge.edge_identity_id
    assert evidence.paper_id == edge.paper_id


def test_ready_binds_baseline_echo_fields() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, source_window_ids=("wf-1", "wf-2", "wf-3"))
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.baseline_id == "baseline-1"
    assert evidence.baseline_as_of_ns == 1_700_000_000_000_000_000
    assert evidence.baseline_source_window_ids == ("wf-1", "wf-2", "wf-3")
    assert evidence.baseline_source_window_id_count == 3
    assert evidence.baseline_digest == _baseline_digest(baseline)


# --------------------------------------------------------------------------------------------------
# 3. Baseline digest / provenance
# --------------------------------------------------------------------------------------------------


def test_baseline_digest_matches_bridge_local_representation() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id)
    assert _baseline_digest(baseline) == bridge_baseline_digest(baseline)
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.baseline_digest == bridge_baseline_digest(baseline)


def test_baseline_digest_mismatch_rejects() -> None:
    evidence = _build(expected_baseline_digest="b" * 64)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:baseline_digest_mismatch" in evidence.reason_codes
    assert evidence.baseline_bound is False
    assert evidence.same_edge_identity_equal is False
    assert evidence.binding_strength == "UNRESOLVED"


def test_expected_baseline_digest_malformed_raises() -> None:
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        _build(expected_baseline_digest="not-hex")


def test_expected_baseline_digest_uppercase_raises() -> None:
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        _build(expected_baseline_digest="A" * 64)


def test_baseline_input_not_mutated() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id)
    before = stage4_backtest_baseline_to_dict(baseline)
    _build(edge_identity=edge, backtest_baseline=baseline)
    assert stage4_backtest_baseline_to_dict(baseline) == before


# --------------------------------------------------------------------------------------------------
# 4. Edge identity reproof
# --------------------------------------------------------------------------------------------------


def test_expected_edge_identity_digest_malformed_raises() -> None:
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        _build(expected_edge_identity_digest="not-hex")


def test_edge_identity_digest_mismatch_rejects() -> None:
    evidence = _build(expected_edge_identity_digest="c" * 64)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:edge_identity_digest_mismatch" in evidence.reason_codes


def test_edge_identity_not_ready_rejects() -> None:
    edge = _edge_identity(expected_strategy_spec_digest="d" * 64)  # forces REJECTED edge identity
    assert edge.ready is False
    # Re-seal so the (rejected) edge identity self-digest is internally consistent.
    expected = paper_edge_identity_evidence_digest(edge)
    evidence = _build(edge_identity=edge, expected_edge_identity_digest=expected)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:edge_identity_not_ready" in evidence.reason_codes


def test_edge_identity_unsafe_flag_tamper_rejects() -> None:
    edge = _edge_identity()
    tampered = replace(edge, edge_proven=True)
    resealed = replace(tampered, edge_identity_digest=paper_edge_identity_evidence_digest(tampered))
    evidence = _build(edge_identity=resealed, expected_edge_identity_digest=resealed.edge_identity_digest)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:edge_identity_unsafe_flags" in evidence.reason_codes


def test_edge_identity_derivation_policy_tamper_rejects() -> None:
    edge = _edge_identity()
    tampered = replace(edge, edge_id_derivation_policy="some_other_policy.v1")
    resealed = replace(tampered, edge_identity_digest=paper_edge_identity_evidence_digest(tampered))
    evidence = _build(edge_identity=resealed, expected_edge_identity_digest=resealed.edge_identity_digest)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:edge_identity_derivation_policy_mismatch" in evidence.reason_codes


def test_edge_identity_paper_edge_id_tamper_rejects() -> None:
    edge = _edge_identity()
    tampered = replace(edge, paper_edge_id="not-a-hex64")
    resealed = replace(tampered, edge_identity_digest=paper_edge_identity_evidence_digest(tampered))
    baseline = _baseline("not-a-hex64")
    evidence = _build(
        edge_identity=resealed,
        backtest_baseline=baseline,
        expected_edge_identity_digest=resealed.edge_identity_digest,
    )
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:edge_identity_paper_edge_id_invalid" in evidence.reason_codes


def test_edge_identity_forged_paper_edge_id_recompute_rejects() -> None:
    # P1 regression: a resealed edge identity whose paper_edge_id is a VALID lowercase hex64 but NOT the real
    # sha256(canonical_json({strategy_id, market_symbol})) derivation, with a baseline carrying the same value,
    # must NOT be certified READY. The consumer re-derives the edge_id and fails closed.
    edge = _edge_identity()
    forged = "f" * 64
    assert forged != edge.paper_edge_id
    tampered = replace(edge, paper_edge_id=forged)
    resealed = replace(tampered, edge_identity_digest=paper_edge_identity_evidence_digest(tampered))
    baseline = _baseline(forged)
    evidence = _build(
        edge_identity=resealed,
        backtest_baseline=baseline,
        expected_edge_identity_digest=resealed.edge_identity_digest,
    )
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:edge_identity_edge_id_derivation_mismatch" in evidence.reason_codes


def test_edge_identity_wrong_type_raises() -> None:
    baseline = _baseline("a" * 64)
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        build_paper_stage4_backtest_baseline_evidence(
            baseline,
            expected_baseline_digest=_baseline_digest(baseline),
            edge_identity=object(),  # type: ignore[arg-type]
            expected_edge_identity_digest="a" * 64,
            baseline_evidence_id="be-1",
            correlation_id="corr-1",
        )


def test_edge_identity_input_not_mutated() -> None:
    edge = _edge_identity()
    before = paper_edge_identity_evidence_to_dict(edge)
    _build(edge_identity=edge)
    assert paper_edge_identity_evidence_to_dict(edge) == before


# --------------------------------------------------------------------------------------------------
# 5. Same-edge identity
# --------------------------------------------------------------------------------------------------


def test_same_edge_identity_equality_passes() -> None:
    evidence = _build()
    assert evidence.same_edge_identity_equal is True
    assert evidence.edge_id == evidence.paper_edge_id


def test_same_edge_identity_mismatch_rejects() -> None:
    edge = _edge_identity()
    baseline = _baseline("e" * 64)  # valid hex64 but not the paper edge id
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:same_edge_identity_mismatch" in evidence.reason_codes


def test_baseline_edge_id_non_hex64_rejects() -> None:
    edge = _edge_identity()
    baseline = _baseline("NOT-HEX")
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:baseline_edge_id_invalid" in evidence.reason_codes


def test_same_edge_equality_is_identity_only_not_performance_proof() -> None:
    evidence = _build()
    assert evidence.same_edge_identity_equal is True
    assert evidence.same_edge_as_backtest_proven is False
    assert evidence.backtest_validity_proven is False
    assert evidence.baseline_profitability_proven is False


# --------------------------------------------------------------------------------------------------
# 6. Numeric baseline validation
# --------------------------------------------------------------------------------------------------


def test_non_positive_sharpe_rejects() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, backtest_sharpe=0.0)
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:backtest_sharpe_non_positive" in evidence.reason_codes


def test_negative_sharpe_rejects() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, backtest_sharpe=-1.0)
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:backtest_sharpe_non_positive" in evidence.reason_codes


def test_non_finite_sharpe_rejects() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, backtest_sharpe=float("inf"))
    # A non-finite float breaks the canonical baseline digest (allow_nan=False), so the caller anchor cannot
    # be computed from it; an explicit anchor is supplied and the build fails closed.
    evidence = _build(edge_identity=edge, backtest_baseline=baseline, expected_baseline_digest="0" * 64)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:backtest_sharpe_non_positive" in evidence.reason_codes
    assert "paper_stage4_backtest_baseline_evidence:baseline_digest_mismatch" in evidence.reason_codes


def test_hit_rate_out_of_range_rejects() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, backtest_hit_rate=1.5)
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:backtest_hit_rate_invalid" in evidence.reason_codes


def test_negative_slippage_rejects() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, backtest_slippage_bps=-0.5)
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:backtest_slippage_invalid" in evidence.reason_codes


def test_fill_rate_out_of_range_rejects() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, backtest_fill_rate=2.0)
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:backtest_fill_rate_invalid" in evidence.reason_codes


def test_optional_slippage_and_fill_none_allowed() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, backtest_slippage_bps=None, backtest_fill_rate=None)
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.READY


def test_non_positive_as_of_rejects() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, as_of_ns=0)
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:baseline_as_of_ns_invalid" in evidence.reason_codes


def test_no_profitability_threshold_invented() -> None:
    # A very small positive sharpe is still accepted: the artifact invents no performance gate.
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, backtest_sharpe=0.0001)
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.READY


# --------------------------------------------------------------------------------------------------
# 7. IDs / metadata / scope
# --------------------------------------------------------------------------------------------------


def test_empty_baseline_evidence_id_raises() -> None:
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        _build(baseline_evidence_id="")


def test_subclass_correlation_id_raises() -> None:
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        _build(correlation_id=_LiarStr("corr-1"))


def test_control_char_id_raises() -> None:
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        _build(baseline_evidence_id="be\n1")


def test_scope_token_in_id_raises() -> None:
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        _build(correlation_id="corr-live-order")


def test_clock_token_in_id_raises() -> None:
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        _build(baseline_evidence_id="be-wall_clock")


def test_malformed_metadata_raises() -> None:
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        _build(metadata={"k": 1})  # type: ignore[dict-item]


def test_metadata_scope_token_raises() -> None:
    with pytest.raises(PaperStage4BacktestBaselineEvidenceError):
        _build(metadata={"note": "deribit"})


def test_baseline_string_field_scope_token_rejects() -> None:
    edge = _edge_identity()
    baseline = _baseline(edge.paper_edge_id, baseline_id="baseline-deribit")
    evidence = _build(edge_identity=edge, backtest_baseline=baseline)
    assert evidence.status is PaperStage4BacktestBaselineEvidenceStatus.REJECTED
    assert "paper_stage4_backtest_baseline_evidence:baseline_scope_violation" in evidence.reason_codes


def test_metadata_copied_and_frozen() -> None:
    evidence = _build(metadata={"b": "2", "a": "1"})
    assert evidence.metadata == (("a", "1"), ("b", "2"))


# --------------------------------------------------------------------------------------------------
# 8. Digest / provenance
# --------------------------------------------------------------------------------------------------


def test_to_dict_keys_equal_dataclass_fields() -> None:
    evidence = _build()
    assert set(paper_stage4_backtest_baseline_evidence_to_dict(evidence)) == {field.name for field in fields(evidence)}


def test_self_digest_excluded_and_only_self_digest_excluded() -> None:
    evidence = _build()
    payload = paper_stage4_backtest_baseline_evidence_to_dict(evidence)
    assert payload["baseline_evidence_digest"] == evidence.baseline_evidence_digest
    recomputed = paper_stage4_backtest_baseline_evidence_digest(evidence)
    assert recomputed == evidence.baseline_evidence_digest
    # Tampering any non-self field changes the recomputed digest.
    tampered = replace(evidence, market_symbol="OTHER")
    assert paper_stage4_backtest_baseline_evidence_digest(tampered) != evidence.baseline_evidence_digest


def test_digest_deterministic_and_idempotent() -> None:
    first = _build()
    second = _build()
    assert first.baseline_evidence_digest == second.baseline_evidence_digest
    assert paper_stage4_backtest_baseline_evidence_digest(first) == first.baseline_evidence_digest


def test_metadata_changes_digest() -> None:
    a = _build(metadata={"purpose": "one"})
    b = _build(metadata={"purpose": "two"})
    assert a.baseline_evidence_digest != b.baseline_evidence_digest


def test_metadata_order_independent() -> None:
    a = _build(metadata={"a": "1", "b": "2"})
    b = _build(metadata={"b": "2", "a": "1"})
    assert a.baseline_evidence_digest == b.baseline_evidence_digest


def test_every_baseline_field_digest_bound() -> None:
    edge = _edge_identity()
    base = _build(edge_identity=edge, backtest_baseline=_baseline(edge.paper_edge_id))
    variants = (
        _baseline(edge.paper_edge_id, baseline_id="baseline-2"),
        _baseline(edge.paper_edge_id, as_of_ns=1_700_000_000_000_000_001),
        _baseline(edge.paper_edge_id, backtest_sharpe=1.6),
        _baseline(edge.paper_edge_id, backtest_hit_rate=0.6),
        _baseline(edge.paper_edge_id, backtest_slippage_bps=3.0),
        _baseline(edge.paper_edge_id, backtest_fill_rate=0.8),
        _baseline(edge.paper_edge_id, source_window_ids=("wf-1",)),
    )
    for variant in variants:
        evidence = _build(edge_identity=edge, backtest_baseline=variant)
        assert evidence.baseline_evidence_digest != base.baseline_evidence_digest


def test_rejection_reason_codes_digest_bound() -> None:
    ready = _build()
    rejected = _build(expected_baseline_digest="0" * 64)
    assert ready.baseline_evidence_digest != rejected.baseline_evidence_digest
    assert rejected.reason_codes
    assert rejected.reason_codes == tuple(sorted(rejected.reason_codes))


# --------------------------------------------------------------------------------------------------
# 9. Non-overclaim
# --------------------------------------------------------------------------------------------------


def test_non_overclaim_flags_all_false_when_ready() -> None:
    evidence = _build()
    for flag in (
        "baseline_constructed",
        "same_edge_as_backtest_proven",
        "backtest_validity_proven",
        "baseline_profitability_proven",
        "edge_proven",
        "profitability_proven",
        "comparison_ready",
        "paper_vs_backtest_comparison_ready",
        "stage4_comparator_invoked",
        "thirty_day_gate_satisfied",
        "prdv4_stage4_complete",
        "operational_readiness",
        "live_ready",
        "shadow_ready",
        "deribit_ready",
        "production_execution",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
        "private_api_ready",
        "live_api_called",
        "real_wall_clock_used",
        "real_account_equity_used",
        "real_capital_used",
        "paper_chain_link_cryptographic",
        "paper_chain_spec_digest_carried",
    ):
        assert getattr(evidence, flag) is False, flag
    assert evidence.paper_only is True


def test_limitation_fields_present_and_bound() -> None:
    evidence = _build()
    assert evidence.paper_chain_link == "edge_id_identity_only"
    assert (
        evidence.paper_chain_link_limitation
        == "baseline_bound_by_edge_id_identity_not_backtest_validity_or_performance.v1"
    )


# --------------------------------------------------------------------------------------------------
# 10. AST forbidden surface
# --------------------------------------------------------------------------------------------------


def _module_source() -> str:
    return Path(baseline_module.__file__).read_text(encoding="utf-8")


def _module_tree() -> ast.Module:
    return ast.parse(_module_source())


def test_ast_import_allowlist() -> None:
    tree = _module_tree()
    allowed_from = {
        "collections.abc",
        "dataclasses",
        "enum",
        "crypto_core.validation.paper_edge_identity_evidence",
        "crypto_core.validation.stage4_comparator",
    }
    allowed_import = {"hashlib", "json", "math", "re"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            assert node.module in allowed_from, node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in allowed_import, alias.name


def test_ast_no_forbidden_identifiers() -> None:
    tree = _module_tree()
    forbidden = {
        "compare_stage4",
        "Stage4PaperSummary",
        "build_stage4_backtest_baseline",
        "build_stage4_backtest_baseline_from_windows",
        "stage4_paper_summary_to_dict",
        "sqrt",
        "now",
        "utcnow",
        "time_ns",
        "perf_counter",
        "monotonic",
        "uuid4",
        "urandom",
    }
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
    assert seen.isdisjoint(forbidden), seen & forbidden


def test_ast_baseline_type_referenced_but_never_constructed() -> None:
    tree = _module_tree()
    # The baseline type may be referenced (isinstance/type guard) but never CALLED (constructed).
    name_refs = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "Stage4BacktestBaseline" in name_refs
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id != "Stage4BacktestBaseline"
            if isinstance(func, ast.Attribute):
                assert func.attr != "Stage4BacktestBaseline"


def test_ast_only_math_isfinite_used() -> None:
    tree = _module_tree()
    math_attrs = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "math"
    }
    assert math_attrs == {"isfinite"}


def test_ast_no_consumed_stage4_chain_modules() -> None:
    # Inspect IMPORTS (not raw text): a docstring may explain the bridge digest mirror, but the module must
    # never IMPORT / consume the wider Stage-4 paper chain or operational-day modules.
    tree = _module_tree()
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
    blob = "\n".join(imported_modules)
    for forbidden in (
        "paper_sharpe_evidence",
        "paper_vs_backtest_methodology",
        "paper_daily_return_series_evidence",
        "paper_30day_evidence_gate_decision",
        "paper_stage4_comparison",
        "paper_stage4_completion",
        "operational_day",
        "paper_vs_backtest_comparator_bridge",
    ):
        assert forbidden not in blob, forbidden
