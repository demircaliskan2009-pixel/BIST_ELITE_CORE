from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_connector_enablement import (
    PUBLIC_MARKET_DATA_ONLY_RUN_MODE,
    PublicConnectorEnablementError,
    PublicConnectorEnablementRequest,
    PublicConnectorEnablementStatus,
    aggregate_public_connector_enablement_decisions,
    evaluate_public_connector_enablement,
    public_connector_enablement_decision_from_dict,
    public_connector_enablement_decision_to_dict,
    public_connector_enablement_ready,
    public_connector_enablement_request_from_dict,
    public_connector_enablement_request_to_dict,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

CONTRACT_PATH = Path("src/crypto_core/venue/public_connector_enablement.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"


def test_public_connector_enablement_accepts_only_fully_approved_public_market_data_request():
    decision = evaluate_public_connector_enablement(_request())

    assert decision.accepted is True
    assert decision.rejection_reasons == ()
    assert public_connector_enablement_ready(decision) is True


def test_operational_evidence_not_accepted_rejects():
    decision = evaluate_public_connector_enablement(_request(operational_evidence_accepted=False))

    assert decision.accepted is False
    assert "public_connector_enablement:operational_evidence_not_accepted" in decision.rejection_reasons


def test_static_registry_unverified_rejects():
    decision = evaluate_public_connector_enablement(_request(static_registry_verified=False))

    assert decision.accepted is False
    assert "public_connector_enablement:static_registry_unverified" in decision.rejection_reasons


def test_pending_connector_enablement_rejects():
    decision = evaluate_public_connector_enablement(
        _request(connector_enablement_status=PublicConnectorEnablementStatus.PENDING)
    )

    assert decision.accepted is False
    assert "public_connector_enablement:pending" in decision.rejection_reasons


def test_rejected_connector_enablement_rejects():
    decision = evaluate_public_connector_enablement(
        _request(connector_enablement_status=PublicConnectorEnablementStatus.REJECTED)
    )

    assert decision.accepted is False
    assert "public_connector_enablement:rejected" in decision.rejection_reasons


def test_missing_reviewer_rejects():
    decision = evaluate_public_connector_enablement(_request(reviewer_id=""))

    assert decision.accepted is False
    assert "public_connector_enablement:missing_reviewer" in decision.rejection_reasons


def test_missing_reviewed_at_rejects():
    decision = evaluate_public_connector_enablement(_request(reviewed_at_iso=""))

    assert decision.accepted is False
    assert "public_connector_enablement:missing_review_time" in decision.rejection_reasons


def test_invalid_approved_run_mode_rejects():
    decision = evaluate_public_connector_enablement(_request(approved_run_mode="LIVE"))

    assert decision.accepted is False
    assert "public_connector_enablement:invalid_run_mode" in decision.rejection_reasons


def test_missing_evidence_refs_rejects():
    decision = evaluate_public_connector_enablement(_request(evidence_refs=()))

    assert decision.accepted is False
    assert "public_connector_enablement:missing_evidence_ref" in decision.rejection_reasons


def test_preexisting_rejection_rejects():
    decision = evaluate_public_connector_enablement(
        _request(rejection_reasons=("public_connector_enablement:manual_blocker",))
    )

    assert decision.accepted is False
    assert "public_connector_enablement:preexisting_rejection" in decision.rejection_reasons
    assert "public_connector_enablement:manual_blocker" in decision.rejection_reasons


def test_public_connector_enablement_serializers_roundtrip_json_safe():
    request = _request()
    request_payload = public_connector_enablement_request_to_dict(request)

    assert json.loads(json.dumps(request_payload)) == request_payload
    assert public_connector_enablement_request_from_dict(request_payload) == request

    decision = evaluate_public_connector_enablement(request)
    decision_payload = public_connector_enablement_decision_to_dict(decision)

    assert json.loads(json.dumps(decision_payload)) == decision_payload
    assert public_connector_enablement_decision_from_dict(decision_payload) == decision


def test_malformed_public_connector_enablement_payloads_fail_closed():
    decision = evaluate_public_connector_enablement({"venue_id": "deribit"})

    assert decision.accepted is False
    assert decision.rejection_reasons == ("public_connector_enablement:malformed",)
    with pytest.raises(PublicConnectorEnablementError):
        public_connector_enablement_request_from_dict({"venue_id": "deribit"})
    with pytest.raises(PublicConnectorEnablementError):
        public_connector_enablement_decision_from_dict({"accepted": "yes"})


def test_aggregate_all_accepted_public_connector_enablement_decisions_accepts():
    aggregate = aggregate_public_connector_enablement_decisions(
        (
            evaluate_public_connector_enablement(_request(dialect_id=DIALECT_ID)),
            evaluate_public_connector_enablement(_request(dialect_id=DIALECT_ID)),
        )
    )

    assert aggregate.accepted is True
    assert aggregate.venue_id is VenueId.DERIBIT
    assert aggregate.dialect_id == DIALECT_ID
    assert aggregate.rejection_reasons == ()


def test_aggregate_any_rejected_or_pending_public_connector_enablement_decision_rejects():
    aggregate = aggregate_public_connector_enablement_decisions(
        (
            evaluate_public_connector_enablement(_request()),
            evaluate_public_connector_enablement(
                _request(connector_enablement_status=PublicConnectorEnablementStatus.PENDING)
            ),
        )
    )

    assert aggregate.accepted is False
    assert "public_connector_enablement:pending" in aggregate.rejection_reasons


def test_public_connector_enablement_is_deterministic_on_replay():
    request = _request()

    assert evaluate_public_connector_enablement(request) == evaluate_public_connector_enablement(request)
    assert public_connector_enablement_decision_to_dict(
        evaluate_public_connector_enablement(request)
    ) == public_connector_enablement_decision_to_dict(evaluate_public_connector_enablement(request))


def test_public_connector_enablement_module_has_no_network_file_or_client_imports():
    source = CONTRACT_PATH.read_text(encoding="utf-8")
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
    assert "client" not in source.lower()
    assert "endpoint" not in source.lower()
    assert "api_key" not in source.lower()
    assert "api_secret" not in source.lower()
    assert "getenv" not in source.lower()
    assert "os.environ" not in source.lower()


def test_public_connector_enablement_does_not_mutate_registry_or_ready_dialects():
    before = connector_ready_dialects()

    decision = evaluate_public_connector_enablement(_request())

    assert decision.accepted is True
    assert connector_ready_dialects() == before
    assert len(before) == 1
    assert before[0].dialect_id == "deribit:l2_orderbook:book_instrument_interval"

    source = CONTRACT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "crypto_core.venue.registry" not in imported_modules
    assert "crypto_core.venue.public_feed_dialects" not in imported_modules


def test_public_connector_enablement_has_no_live_or_order_paths():
    source = CONTRACT_PATH.read_text(encoding="utf-8").lower()

    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "orderintent" not in source
    assert "executionmode.live" not in source


def _request(**overrides: object) -> PublicConnectorEnablementRequest:
    values = {
        "venue_id": VenueId.DERIBIT,
        "dialect_id": DIALECT_ID,
        "operational_evidence_accepted": True,
        "static_registry_verified": True,
        "connector_enablement_status": PublicConnectorEnablementStatus.APPROVED,
        "reviewer_id": "phase22s-reviewer",
        "reviewed_at_iso": "2026-05-10T12:00:00Z",
        "approved_run_mode": PUBLIC_MARKET_DATA_ONLY_RUN_MODE,
        "evidence_refs": ("phase22s:manual-public-market-data-only-approval",),
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicConnectorEnablementRequest(**values)  # type: ignore[arg-type]
