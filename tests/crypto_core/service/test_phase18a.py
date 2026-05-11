from __future__ import annotations

import importlib
import json

import pytest

from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
    paper_shadow_activation_plan_to_dict,
)


def _activation_plan(
    *,
    activation_status: PaperShadowActivationStatus = PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW,
    source_manifest_status: PaperShadowSourceManifestStatus = PaperShadowSourceManifestStatus.READY,
    activation_blockers: tuple[str, ...] = (),
    evidence_blockers: tuple[str, ...] = (),
    governance_blockers: tuple[str, ...] = (),
    pbo_allocation_caps: tuple[tuple[str, float], ...] = (),
) -> PaperShadowActivationPlan:
    return PaperShadowActivationPlan(
        plan_id="paper-shadow-plan-18a",
        activation_status=activation_status,
        source_manifest_status=source_manifest_status,
        active_sleeves=("sleeve-alpha",),
        inactive_sleeves=("sleeve-inactive",),
        admitted_unallocated_sleeves=("sleeve-beta",),
        activation_blockers=activation_blockers,
        evidence_blockers=evidence_blockers,
        governance_blockers=governance_blockers,
        pbo_allocation_caps=pbo_allocation_caps,
        operator_summary="Paper/shadow activation plan ready.",
    )


def test_paper_shadow_session_controller_imports():
    module = importlib.import_module("crypto_core.service.paper_shadow_session_controller")
    assert module.PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW


def test_activation_plan_to_dict_is_json_safe():
    payload = paper_shadow_activation_plan_to_dict(_activation_plan())
    serialized = json.dumps(payload)
    assert len(serialized) > 0
    assert payload["activation_status"] == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW.value
    assert isinstance(payload["activation_status"], str)
    assert payload["active_sleeves"] == ["sleeve-alpha"]
    assert payload["inactive_sleeves"] == ["sleeve-inactive"]
    assert payload["admitted_unallocated_sleeves"] == ["sleeve-beta"]


def test_activation_plan_to_dict_preserves_blockers():
    payload = paper_shadow_activation_plan_to_dict(
        _activation_plan(
            activation_status=PaperShadowActivationStatus.BLOCKED,
            source_manifest_status=PaperShadowSourceManifestStatus.BLOCKED,
            activation_blockers=("activation:blocked",),
            evidence_blockers=("pbo:pbo_rejected", "stage3:stress_failed"),
            governance_blockers=("governance:pending_operator_review",),
        )
    )
    assert payload["activation_blockers"] == ["activation:blocked"]
    assert payload["evidence_blockers"] == ["pbo:pbo_rejected", "stage3:stress_failed"]
    assert payload["governance_blockers"] == ["governance:pending_operator_review"]


def test_activation_plan_pbo_caps_are_metadata_only():
    payload = paper_shadow_activation_plan_to_dict(_activation_plan(pbo_allocation_caps=(("sleeve-alpha", 0.5),)))
    assert payload["pbo_allocation_caps"] == [["sleeve-alpha", 0.5]]
    assert "allocation_decision" not in payload
    assert "allocation_amount" not in payload


def test_paper_shadow_controller_accepts_activation_plan_contract_if_existing_validator_available():
    module = importlib.import_module("crypto_core.service.paper_shadow_session_controller")
    validator = getattr(module, "_validate_activation_plan_for_session", None)
    if validator is None:
        pytest.skip("paper shadow activation plan validator is not exposed")

    validator(_activation_plan())
    validator(
        _activation_plan(
            activation_status=PaperShadowActivationStatus.BLOCKED,
            source_manifest_status=PaperShadowSourceManifestStatus.BLOCKED,
            activation_blockers=("activation:blocked",),
        )
    )


def test_no_stage4_comparator_added():
    payload = paper_shadow_activation_plan_to_dict(_activation_plan())
    comparator_fields = {
        "backtest_sharpe",
        "paper_sharpe",
        "hit_rate_delta",
        "slippage_delta",
        "fill_rate_delta",
    }
    assert comparator_fields.isdisjoint(payload)
