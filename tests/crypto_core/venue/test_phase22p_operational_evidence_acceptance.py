from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.official_claim_reviews import (
    OfficialClaimReviewDecision,
    OfficialClaimReviewStatus,
    validate_official_claim_review,
)
from crypto_core.venue.official_source_snapshots import OfficialSourceSnapshot, validate_official_source_snapshot
from crypto_core.venue.operational_evidence_readiness import (
    OPERATIONAL_EVIDENCE_ACCEPTANCE_REQUIRED_POLICY_IDS,
    OperationalEvidenceAcceptanceInput,
    OperationalEvidenceReadinessError,
    OperationalPolicyApproval,
    OperationalPolicyApprovalStatus,
    evaluate_operational_evidence_acceptance,
    operational_evidence_acceptance_input_from_dict,
    operational_evidence_acceptance_input_to_dict,
    operational_evidence_acceptance_ready,
    operational_evidence_acceptance_result_from_dict,
    operational_evidence_acceptance_result_to_dict,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

ACCEPTANCE_CONTRACT_PATH = Path("src/crypto_core/venue/operational_evidence_readiness.py")
VALID_HASH = "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd"


def test_all_source_snapshots_claims_and_policies_approved_accepts():
    result = evaluate_operational_evidence_acceptance(_acceptance_input(static_registry_verified=False))

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert operational_evidence_acceptance_ready(result) is True
    assert connector_ready_dialects() == ()


def test_missing_source_snapshot_rejects():
    result = evaluate_operational_evidence_acceptance(_acceptance_input(source_snapshot_results=()))

    assert result.accepted is False
    assert "operational_evidence:missing_source_snapshot" in result.rejection_reasons


def test_rejected_source_snapshot_rejects():
    result = evaluate_operational_evidence_acceptance(
        _acceptance_input(
            source_snapshot_results=(
                validate_official_source_snapshot(replace(_snapshot(), manual_review_status="PENDING")),
            )
        )
    )

    assert result.accepted is False
    assert "operational_evidence:source_snapshot_rejected" in result.rejection_reasons
    assert "official_snapshot:manual_review_not_approved" in result.rejection_reasons


def test_missing_claim_review_rejects():
    result = evaluate_operational_evidence_acceptance(_acceptance_input(claim_review_results=()))

    assert result.accepted is False
    assert "operational_evidence:missing_claim_review" in result.rejection_reasons


def test_pending_claim_review_rejects():
    result = evaluate_operational_evidence_acceptance(
        _acceptance_input(
            claim_review_results=(
                validate_official_claim_review(
                    _claim(
                        review_status=OfficialClaimReviewStatus.PENDING,
                        decision=OfficialClaimReviewStatus.PENDING,
                    )
                ),
            )
        )
    )

    assert result.accepted is False
    assert "operational_evidence:claim_review_rejected" in result.rejection_reasons
    assert "official_claim_review:pending" in result.rejection_reasons


def test_rejected_claim_review_rejects():
    result = evaluate_operational_evidence_acceptance(
        _acceptance_input(
            claim_review_results=(
                validate_official_claim_review(
                    _claim(
                        review_status=OfficialClaimReviewStatus.REJECTED,
                        decision=OfficialClaimReviewStatus.REJECTED,
                    )
                ),
            )
        )
    )

    assert result.accepted is False
    assert "operational_evidence:claim_review_rejected" in result.rejection_reasons
    assert "official_claim_review:rejected" in result.rejection_reasons


@pytest.mark.parametrize(
    ("missing_policy_id", "expected_reason"),
    (
        ("checksum_decision", "operational_policy:checksum_decision_missing"),
        ("liveness_policy", "operational_policy:liveness_policy_missing"),
        ("staleness_budget", "operational_policy:staleness_budget_missing"),
        ("receive_lag_budget", "operational_policy:receive_lag_budget_missing"),
        ("testnet_prod_review", "operational_policy:testnet_prod_review_missing"),
        ("regional_legal_access_review", "operational_policy:regional_legal_access_review_missing"),
    ),
)
def test_missing_required_policy_rejects(missing_policy_id: str, expected_reason: str):
    result = evaluate_operational_evidence_acceptance(
        _acceptance_input(
            policy_approvals=tuple(policy for policy in _policy_approvals() if policy.policy_id != missing_policy_id)
        )
    )

    assert result.accepted is False
    assert expected_reason in result.rejection_reasons


def test_missing_policy_reviewer_rejects():
    result = evaluate_operational_evidence_acceptance(
        _acceptance_input(
            policy_approvals=(replace(_policy("checksum_decision"), reviewer_id=""), *_non_checksum_policies())
        )
    )

    assert result.accepted is False
    assert "operational_policy:missing_reviewer" in result.rejection_reasons


def test_missing_policy_review_time_rejects():
    result = evaluate_operational_evidence_acceptance(
        _acceptance_input(
            policy_approvals=(replace(_policy("checksum_decision"), reviewed_at_iso=""), *_non_checksum_policies())
        )
    )

    assert result.accepted is False
    assert "operational_policy:missing_review_time" in result.rejection_reasons


def test_connector_enablement_requested_rejects():
    result = evaluate_operational_evidence_acceptance(_acceptance_input(connector_enablement_requested=True))

    assert result.accepted is False
    assert "operational_policy:separate_connector_enablement_required" in result.rejection_reasons


def test_preexisting_acceptance_rejection_rejects():
    result = evaluate_operational_evidence_acceptance(
        _acceptance_input(rejection_reasons=("operational_evidence:manual_blocker",))
    )

    assert result.accepted is False
    assert "operational_evidence:preexisting_rejection" in result.rejection_reasons


def test_operational_evidence_acceptance_serializers_roundtrip_json_safe():
    acceptance_input = _acceptance_input()
    input_payload = operational_evidence_acceptance_input_to_dict(acceptance_input)

    assert json.loads(json.dumps(input_payload)) == input_payload
    assert operational_evidence_acceptance_input_from_dict(input_payload) == acceptance_input

    result = evaluate_operational_evidence_acceptance(acceptance_input)
    result_payload = operational_evidence_acceptance_result_to_dict(result)

    assert json.loads(json.dumps(result_payload)) == result_payload
    assert operational_evidence_acceptance_result_from_dict(result_payload) == result


def test_malformed_operational_evidence_acceptance_payloads_fail_closed():
    result = evaluate_operational_evidence_acceptance({"venue_id": "deribit"})

    assert result.accepted is False
    assert result.rejection_reasons == ("operational_evidence:malformed",)
    with pytest.raises(OperationalEvidenceReadinessError):
        operational_evidence_acceptance_input_from_dict({"venue_id": "deribit"})
    with pytest.raises(OperationalEvidenceReadinessError):
        operational_evidence_acceptance_result_from_dict({"accepted": "yes"})


def test_operational_evidence_acceptance_is_deterministic_on_replay():
    acceptance_input = _acceptance_input()

    assert evaluate_operational_evidence_acceptance(acceptance_input) == evaluate_operational_evidence_acceptance(
        acceptance_input
    )
    assert operational_evidence_acceptance_result_to_dict(
        evaluate_operational_evidence_acceptance(acceptance_input)
    ) == operational_evidence_acceptance_result_to_dict(evaluate_operational_evidence_acceptance(acceptance_input))


def test_operational_evidence_acceptance_module_has_no_network_file_or_client_imports():
    source = ACCEPTANCE_CONTRACT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_import_roots = {
        "aiohttp",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "socket",
        "urllib",
        "websocket",
        "websockets",
    }
    imports: set[str] = set()
    function_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.FunctionDef):
            function_names.add(node.name)

    assert forbidden_import_roots.isdisjoint(imports)
    assert {"open", "connect", "recv", "receive", "send", "subscribe", "start", "stop"}.isdisjoint(function_names)
    assert {"place_order", "cancel_order"}.isdisjoint(function_names)
    assert "endpoint" not in source.lower()
    assert "client" not in source.lower()
    assert "api_key" not in source.lower()
    assert "api_secret" not in source.lower()
    assert "getenv" not in source.lower()
    assert "os.environ" not in source.lower()
    assert "executionmode.live" not in source.lower()
    assert "orderintent" not in source.lower()


def test_operational_evidence_acceptance_does_not_enable_ready_dialects_or_live_order_paths():
    assert connector_ready_dialects() == ()

    source = ACCEPTANCE_CONTRACT_PATH.read_text(encoding="utf-8").lower()
    assert "enabled_for_connector=true" not in source
    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "orderintent" not in source
    assert "executionmode.live" not in source


def _acceptance_input(**overrides: object) -> OperationalEvidenceAcceptanceInput:
    values = {
        "venue_id": VenueId.DERIBIT,
        "source_snapshot_results": (validate_official_source_snapshot(_snapshot()),),
        "claim_review_results": (validate_official_claim_review(_claim()),),
        "policy_approvals": _policy_approvals(),
        "static_registry_verified": False,
        "connector_enablement_requested": False,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return OperationalEvidenceAcceptanceInput(**values)  # type: ignore[arg-type]


def _snapshot() -> OfficialSourceSnapshot:
    return OfficialSourceSnapshot(
        snapshot_id="deribit-source-snapshot",
        source_id="DERIBIT_NOTIFICATIONS",
        venue_id=VenueId.DERIBIT,
        official_url="https://docs.deribit.com/#notifications",
        retrieved_at_iso="2026-05-10T07:51:21Z",
        content_sha256=VALID_HASH,
        content_size_bytes=939_778,
        reviewer_id="phase22p-reviewer",
        reviewed_at_iso="2026-05-10T12:00:00Z",
        manual_review_status="APPROVED",
        rejection_reasons=(),
    )


def _claim(**overrides: object) -> OfficialClaimReviewDecision:
    values = {
        "claim_id": "orderbook_channel_feed",
        "source_id": "DERIBIT_NOTIFICATIONS",
        "venue_id": VenueId.DERIBIT,
        "source_sha256": VALID_HASH,
        "official_url": "https://docs.deribit.com/#notifications",
        "doc_section_or_anchor": "#notifications",
        "reviewer_id": "phase22p-reviewer",
        "reviewed_at_iso": "2026-05-10T12:00:00Z",
        "review_status": OfficialClaimReviewStatus.APPROVED,
        "decision": OfficialClaimReviewStatus.APPROVED,
        "evidence_refs": ("DERIBIT_NOTIFICATIONS:#notifications",),
        "rejection_reasons": (),
    }
    values.update(overrides)
    return OfficialClaimReviewDecision(**values)  # type: ignore[arg-type]


def _policy_approvals() -> tuple[OperationalPolicyApproval, ...]:
    return tuple(_policy(policy_id) for policy_id in OPERATIONAL_EVIDENCE_ACCEPTANCE_REQUIRED_POLICY_IDS)


def _non_checksum_policies() -> tuple[OperationalPolicyApproval, ...]:
    return tuple(policy for policy in _policy_approvals() if policy.policy_id != "checksum_decision")


def _policy(policy_id: str) -> OperationalPolicyApproval:
    return OperationalPolicyApproval(
        policy_id=policy_id,
        venue_id=VenueId.DERIBIT,
        policy_status=OperationalPolicyApprovalStatus.APPROVED,
        reviewer_id="phase22p-reviewer",
        reviewed_at_iso="2026-05-10T12:00:00Z",
        rejection_reasons=(),
    )
