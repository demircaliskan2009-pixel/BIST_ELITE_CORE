from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.official_claim_reviews import (
    OfficialClaimReviewDecision,
    OfficialClaimReviewError,
    OfficialClaimReviewStatus,
    aggregate_claim_review_results,
    official_claim_review_decision_from_dict,
    official_claim_review_decision_to_dict,
    official_claim_review_ready,
    official_claim_review_validation_result_from_dict,
    official_claim_review_validation_result_to_dict,
    validate_official_claim_review,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

CLAIM_REVIEW_CONTRACT_PATH = Path("src/crypto_core/venue/official_claim_reviews.py")
VALID_HASH = "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd"


def test_pending_claim_review_rejects():
    result = validate_official_claim_review(
        _decision(
            review_status=OfficialClaimReviewStatus.PENDING,
            decision=OfficialClaimReviewStatus.PENDING,
        )
    )

    assert result.accepted is False
    assert "official_claim_review:pending" in result.rejection_reasons
    assert official_claim_review_ready(result) is False


def test_rejected_claim_review_rejects():
    result = validate_official_claim_review(
        _decision(
            review_status=OfficialClaimReviewStatus.REJECTED,
            decision=OfficialClaimReviewStatus.REJECTED,
        )
    )

    assert result.accepted is False
    assert "official_claim_review:rejected" in result.rejection_reasons
    assert official_claim_review_ready(result) is False


def test_approved_claim_review_with_all_fields_accepts():
    result = validate_official_claim_review(_decision())

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.review_status is OfficialClaimReviewStatus.APPROVED
    assert official_claim_review_ready(result) is True


@pytest.mark.parametrize(
    ("field_name", "replacement_value", "expected_reason"),
    (
        ("claim_id", "", "official_claim_review:missing_claim_id"),
        ("source_id", "", "official_claim_review:missing_source_id"),
        ("venue_id", "PENDING", "official_claim_review:missing_venue_id"),
        ("official_url", "", "official_claim_review:missing_url"),
        ("doc_section_or_anchor", "", "official_claim_review:missing_section"),
        ("reviewer_id", "", "official_claim_review:missing_reviewer"),
        ("reviewed_at_iso", "", "official_claim_review:missing_review_time"),
        ("evidence_refs", (), "official_claim_review:missing_evidence_ref"),
        ("source_sha256", "", "official_claim_review:missing_hash"),
        ("source_sha256", "abc", "official_claim_review:invalid_hash"),
        ("source_sha256", VALID_HASH.upper(), "official_claim_review:invalid_hash"),
        (
            "rejection_reasons",
            ("manual_review:preexisting_blocker",),
            "official_claim_review:preexisting_rejection",
        ),
    ),
)
def test_claim_review_missing_or_invalid_fields_reject(
    field_name: str,
    replacement_value: object,
    expected_reason: str,
):
    result = validate_official_claim_review(replace(_decision(), **{field_name: replacement_value}))

    assert result.accepted is False
    assert expected_reason in result.rejection_reasons
    assert official_claim_review_ready(result) is False


def test_claim_review_serializer_roundtrip_is_json_safe():
    decision = _decision()
    payload = official_claim_review_decision_to_dict(decision)

    assert json.loads(json.dumps(payload)) == payload
    assert official_claim_review_decision_from_dict(payload) == decision

    result = validate_official_claim_review(decision)
    result_payload = official_claim_review_validation_result_to_dict(result)

    assert json.loads(json.dumps(result_payload)) == result_payload
    assert official_claim_review_validation_result_from_dict(result_payload) == result


def test_corrupt_claim_review_payloads_fail_closed():
    result = validate_official_claim_review({"claim_id": "claim"})

    assert result.accepted is False
    assert result.rejection_reasons == ("official_claim_review:malformed",)
    with pytest.raises(OfficialClaimReviewError):
        official_claim_review_decision_from_dict({"claim_id": "claim"})
    with pytest.raises(OfficialClaimReviewError):
        official_claim_review_validation_result_from_dict({"accepted": "yes"})
    assert aggregate_claim_review_results(()).rejection_reasons == ("official_claim_review:malformed",)


def test_aggregate_all_accepted_claim_reviews_accepts():
    results = (
        validate_official_claim_review(_decision(claim_id="claim_a")),
        validate_official_claim_review(_decision(claim_id="claim_b")),
    )
    aggregate = aggregate_claim_review_results(results)

    assert aggregate.accepted is True
    assert aggregate.review_status is OfficialClaimReviewStatus.APPROVED
    assert aggregate.venue_id is VenueId.DERIBIT
    assert aggregate.rejection_reasons == ()
    assert official_claim_review_ready(aggregate) is True


def test_aggregate_any_pending_or_rejected_claim_review_rejects():
    results = (
        validate_official_claim_review(_decision(claim_id="claim_a")),
        validate_official_claim_review(
            _decision(
                claim_id="claim_b",
                review_status=OfficialClaimReviewStatus.PENDING,
                decision=OfficialClaimReviewStatus.PENDING,
            )
        ),
        validate_official_claim_review(
            _decision(
                claim_id="claim_c",
                review_status=OfficialClaimReviewStatus.REJECTED,
                decision=OfficialClaimReviewStatus.REJECTED,
            )
        ),
    )
    aggregate = aggregate_claim_review_results(results)

    assert aggregate.accepted is False
    assert aggregate.review_status is OfficialClaimReviewStatus.REJECTED
    assert "official_claim_review:pending" in aggregate.rejection_reasons
    assert "official_claim_review:rejected" in aggregate.rejection_reasons
    assert official_claim_review_ready(aggregate) is False


def test_claim_review_validation_is_deterministic_on_replay():
    decision = _decision()

    assert validate_official_claim_review(decision) == validate_official_claim_review(decision)
    assert aggregate_claim_review_results(
        (
            validate_official_claim_review(decision),
            validate_official_claim_review(decision),
        )
    ) == aggregate_claim_review_results(
        (
            validate_official_claim_review(decision),
            validate_official_claim_review(decision),
        )
    )


def test_claim_review_contract_has_no_network_file_or_client_imports():
    source = CLAIM_REVIEW_CONTRACT_PATH.read_text(encoding="utf-8")
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
    assert "live" not in source.lower()
    assert "private" not in source.lower()
    assert "order" not in source.lower()


def test_claim_review_contract_does_not_enable_registry_or_live_order_paths():
    assert len(connector_ready_dialects()) == 1

    source = CLAIM_REVIEW_CONTRACT_PATH.read_text(encoding="utf-8").lower()
    assert "enabled_for_connector=true" not in source
    assert "operational_evidence_ready" not in source
    assert "executionmode.live" not in source
    assert "orderintent" not in source


def _decision(
    *,
    claim_id: str = "orderbook_channel_feed",
    source_id: str = "DERIBIT_NOTIFICATIONS",
    venue_id: VenueId = VenueId.DERIBIT,
    source_sha256: str = VALID_HASH,
    official_url: str = "https://docs.deribit.com/#notifications",
    doc_section_or_anchor: str = "#notifications",
    reviewer_id: str = "phase22n-reviewer",
    reviewed_at_iso: str = "2026-05-10T12:00:00Z",
    review_status: OfficialClaimReviewStatus = OfficialClaimReviewStatus.APPROVED,
    decision: OfficialClaimReviewStatus = OfficialClaimReviewStatus.APPROVED,
    evidence_refs: tuple[str, ...] = ("DERIBIT_NOTIFICATIONS:#notifications",),
    rejection_reasons: tuple[str, ...] = (),
) -> OfficialClaimReviewDecision:
    return OfficialClaimReviewDecision(
        claim_id=claim_id,
        source_id=source_id,
        venue_id=venue_id,
        source_sha256=source_sha256,
        official_url=official_url,
        doc_section_or_anchor=doc_section_or_anchor,
        reviewer_id=reviewer_id,
        reviewed_at_iso=reviewed_at_iso,
        review_status=review_status,
        decision=decision,
        evidence_refs=evidence_refs,
        rejection_reasons=rejection_reasons,
    )
