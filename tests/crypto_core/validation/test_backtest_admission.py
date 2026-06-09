"""Tests for the backtest admission gate (deterministic paper-only admissibility over a bundle)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from crypto_core.validation.backtest_admission import (
    BacktestAdmissionDecision,
    BacktestAdmissionError,
    BacktestAdmissionStatus,
    backtest_admission_decision_to_dict,
    build_backtest_admission_decision,
)
from crypto_core.validation.strategy_validation_bundle import (
    StrategyValidationBundle,
    StrategyValidationBundleStatus,
)

_CORR = "corr:backtest-admission-001"


def _bundle(**overrides) -> StrategyValidationBundle:
    kwargs = {
        "schema_version": "strategy-validation-bundle.v1",
        "status": StrategyValidationBundleStatus.ACCEPTED,
        "accepted": True,
        "strategy_id": "svb-s01",
        "strategy_digest": "a" * 64,
        "source_packet_digest": None,
        "data_registry_digest": "b" * 64,
        "pit_status": "ACCEPTED",
        "pit_rejection_reasons": (),
        "pit_needs_research_reasons": (),
        "leakage_status": "PASS",
        "leakage_rejection_reasons": (),
        "leakage_needs_research_reasons": (),
        "decision_record_digests": ("c" * 64, "d" * 64, "e" * 64),
        "terminal_rejection_reasons": (),
        "terminal_needs_research_reasons": (),
        "correlation_id": "corr:bundle-001",
        "bundle_digest": "f" * 64,
    }
    kwargs.update(overrides)
    return StrategyValidationBundle(**kwargs)


def _admit(bundle=None, **kwargs):
    bundle = _bundle() if bundle is None else bundle
    kwargs.setdefault("correlation_id", _CORR)
    return build_backtest_admission_decision(bundle, **kwargs)


def test_accepted_bundle_admitted():
    decision = _admit()
    assert isinstance(decision, BacktestAdmissionDecision)
    assert decision.status is BacktestAdmissionStatus.ADMITTED
    assert decision.admitted is True
    assert decision.strategy_id == "svb-s01"
    assert decision.bundle_status == "ACCEPTED"
    assert decision.decision_record_count == 3
    assert decision.rejection_reasons == ()
    assert decision.needs_research_reasons == ()
    assert len(decision.admission_digest) == 64
    assert decision.paper_only is True
    assert decision.real_orders_enabled is False
    assert decision.real_money_enabled is False


def test_rejected_bundle_rejected():
    bundle = _bundle(
        status=StrategyValidationBundleStatus.REJECTED,
        accepted=False,
        terminal_rejection_reasons=("pit_parity:unknown_data_key:foo",),
    )
    decision = _admit(bundle)
    assert decision.status is BacktestAdmissionStatus.REJECTED
    assert decision.admitted is False
    assert "backtest_admission:bundle_rejected" in decision.rejection_reasons
    assert "pit_parity:unknown_data_key:foo" in decision.rejection_reasons


def test_needs_research_propagates():
    bundle = _bundle(
        status=StrategyValidationBundleStatus.NEEDS_RESEARCH,
        accepted=False,
        leakage_status="NEEDS_RESEARCH",
        terminal_needs_research_reasons=("leakage_bias_repaint:needs_research:funding_regime",),
    )
    decision = _admit(bundle)
    assert decision.status is BacktestAdmissionStatus.NEEDS_RESEARCH
    assert decision.admitted is False
    assert "backtest_admission:bundle_needs_research" in decision.needs_research_reasons


def test_insufficient_evidence_propagates():
    bundle = _bundle(status=StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE, accepted=False)
    decision = _admit(bundle)
    assert decision.status is BacktestAdmissionStatus.INSUFFICIENT_EVIDENCE
    assert decision.admitted is False
    assert "backtest_admission:bundle_insufficient_evidence" in decision.rejection_reasons


def test_not_enough_decision_records_blocks():
    bundle = _bundle(decision_record_digests=("c" * 64,))
    decision = _admit(bundle, min_decision_records=3)
    assert decision.status is BacktestAdmissionStatus.INSUFFICIENT_EVIDENCE
    assert "backtest_admission:insufficient_decision_records" in decision.rejection_reasons


def test_require_source_packet_missing_blocks():
    decision = _admit(require_source_packet=True)
    assert decision.status is BacktestAdmissionStatus.INSUFFICIENT_EVIDENCE
    assert "backtest_admission:source_packet_required" in decision.rejection_reasons


def test_require_source_packet_present_admits():
    bundle = _bundle(source_packet_digest="1" * 64)
    decision = _admit(bundle, require_source_packet=True)
    assert decision.status is BacktestAdmissionStatus.ADMITTED
    assert decision.source_packet_digest == "1" * 64


def test_wrong_type_and_bad_inputs_raise():
    with pytest.raises(BacktestAdmissionError):
        build_backtest_admission_decision({"status": "ACCEPTED"}, correlation_id=_CORR)  # type: ignore[arg-type]
    with pytest.raises(BacktestAdmissionError):
        build_backtest_admission_decision(None, correlation_id=_CORR)  # type: ignore[arg-type]
    with pytest.raises(BacktestAdmissionError):
        _admit(correlation_id="")
    for bad in (0, -1, True, "3", 1.0):
        with pytest.raises(BacktestAdmissionError):
            _admit(min_decision_records=bad)


def test_real_flags_and_scope_leakage_block():
    assert _admit(_bundle(real_orders_enabled=True)).status is BacktestAdmissionStatus.REJECTED
    assert _admit(_bundle(real_money_enabled=True)).status is BacktestAdmissionStatus.REJECTED
    assert _admit(_bundle(paper_only=False)).status is BacktestAdmissionStatus.REJECTED
    assert _admit(_bundle(bundle_digest="not-a-digest")).status is BacktestAdmissionStatus.REJECTED
    assert _admit(_bundle(decision_record_digests=("c" * 64, "bad", "e" * 64))).status is (
        BacktestAdmissionStatus.REJECTED
    )

    live = _admit(_bundle(strategy_id="live_execution"))
    assert live.status is BacktestAdmissionStatus.REJECTED
    assert "backtest_admission:forbidden_scope_token" in live.rejection_reasons

    bist = _admit(_bundle(strategy_id="bist30_edge"))
    assert bist.status is BacktestAdmissionStatus.REJECTED
    assert "backtest_admission:bist_scope_leakage" in bist.rejection_reasons


def test_forged_accepted_bundle_rejected():
    # status claims ACCEPTED but accepted flag is False -> fail closed.
    decision = _admit(_bundle(accepted=False))
    assert decision.status is BacktestAdmissionStatus.REJECTED
    assert "backtest_admission:bundle_accepted_mismatch" in decision.rejection_reasons


def test_deterministic_digest_identical_input():
    first = _admit()
    second = _admit()
    assert first.admission_digest == second.admission_digest
    assert backtest_admission_decision_to_dict(first) == backtest_admission_decision_to_dict(second)
    assert backtest_admission_decision_to_dict(first)["admission_digest"] == first.admission_digest


def test_material_change_changes_digest():
    base = _admit()
    changed = _admit(correlation_id="corr:backtest-admission-002")
    assert changed.admission_digest != base.admission_digest
    policy_changed = _admit(min_decision_records=2)
    assert policy_changed.admission_digest != base.admission_digest


def test_immutable_and_no_leakage_fields():
    decision = _admit()
    with pytest.raises(FrozenInstanceError):
        decision.status = BacktestAdmissionStatus.REJECTED  # type: ignore[misc]
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert {field.name for field in fields(decision)}.isdisjoint(forbidden)
    payload = backtest_admission_decision_to_dict(decision)
    assert payload["schema_version"] == "backtest-admission.v1"
    assert set(payload).isdisjoint(forbidden)
