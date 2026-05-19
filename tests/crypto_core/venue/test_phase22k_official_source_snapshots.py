from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import VenueId
from crypto_core.venue.official_source_snapshots import (
    OfficialSourceSnapshot,
    OfficialSourceSnapshotError,
    OfficialSourceSnapshotStatus,
    official_source_snapshot_from_dict,
    official_source_snapshot_result_to_dict,
    official_source_snapshot_to_dict,
    sha256_hex_from_bytes,
    sha256_hex_from_text,
    validate_official_source_snapshot,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

SNAPSHOT_MODULE_PATH = Path("src/crypto_core/venue/official_source_snapshots.py")
DERIBIT_DRAFT_PATH = Path("docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md")
CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
DIALECT_ID = "deribit:l2_orderbook:placeholder"


def test_valid_supplied_snapshot_accepted():
    result = validate_official_source_snapshot(_snapshot())

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.snapshot_id == "deribit-notifications-snapshot-2026-05-09"
    assert result.source_id == "DERIBIT_NOTIFICATIONS"
    assert result.venue_id is VenueId.DERIBIT
    assert result.content_sha256 == _VALID_HASH
    assert OfficialSourceSnapshotStatus.ACCEPTED.value == "accepted"
    assert OfficialSourceSnapshotStatus.REJECTED.value == "rejected"


def test_missing_source_id_rejected():
    result = validate_official_source_snapshot(replace(_snapshot(), source_id=""))

    assert result.accepted is False
    assert result.rejection_reasons == ("official_snapshot:missing_source_id",)


def test_missing_official_url_rejected():
    result = validate_official_source_snapshot(replace(_snapshot(), official_url=""))

    assert result.accepted is False
    assert result.rejection_reasons == ("official_snapshot:missing_url",)


def test_content_hash_unavailable_rejected():
    result = validate_official_source_snapshot(replace(_snapshot(), content_sha256="CONTENT_HASH_UNAVAILABLE"))

    assert result.accepted is False
    assert result.rejection_reasons == ("official_snapshot:invalid_hash",)


def test_invalid_hash_length_rejected():
    result = validate_official_source_snapshot(replace(_snapshot(), content_sha256="abc123"))

    assert result.accepted is False
    assert result.rejection_reasons == ("official_snapshot:invalid_hash",)


def test_uppercase_hash_rejected():
    result = validate_official_source_snapshot(replace(_snapshot(), content_sha256=_VALID_HASH.upper()))

    assert result.accepted is False
    assert result.rejection_reasons == ("official_snapshot:invalid_hash",)


@pytest.mark.parametrize("content_size_bytes", (0, -1))
def test_zero_or_negative_size_rejected(content_size_bytes: int):
    result = validate_official_source_snapshot(replace(_snapshot(), content_size_bytes=content_size_bytes))

    assert result.accepted is False
    assert result.rejection_reasons == ("official_snapshot:invalid_size",)


def test_missing_reviewer_rejected():
    result = validate_official_source_snapshot(replace(_snapshot(), reviewer_id=""))

    assert result.accepted is False
    assert result.rejection_reasons == ("official_snapshot:missing_reviewer",)


def test_missing_reviewed_at_rejected():
    result = validate_official_source_snapshot(replace(_snapshot(), reviewed_at_iso=""))

    assert result.accepted is False
    assert result.rejection_reasons == ("official_snapshot:missing_review_time",)


def test_manual_review_status_not_approved_rejected():
    result = validate_official_source_snapshot(replace(_snapshot(), manual_review_status="PENDING"))

    assert result.accepted is False
    assert result.rejection_reasons == ("official_snapshot:manual_review_not_approved",)


def test_preexisting_rejection_reason_rejected():
    result = validate_official_source_snapshot(
        replace(_snapshot(), rejection_reasons=("manual_review:source_mismatch",))
    )

    assert result.accepted is False
    assert result.rejection_reasons == ("official_snapshot:preexisting_rejection",)


def test_serializer_roundtrip_json_safe():
    payload = official_source_snapshot_to_dict(_snapshot())
    restored = official_source_snapshot_from_dict(json.loads(json.dumps(payload)))
    result_payload = official_source_snapshot_result_to_dict(validate_official_source_snapshot(restored))

    assert official_source_snapshot_to_dict(restored) == payload
    assert result_payload["accepted"] is True
    assert json.loads(json.dumps(result_payload)) == result_payload


def test_corrupt_payload_raises_explicit_error():
    with pytest.raises(OfficialSourceSnapshotError):
        official_source_snapshot_from_dict({"snapshot_id": "missing-required-fields"})


def test_sha256_hex_from_text_deterministic():
    first = sha256_hex_from_text("Deribit official source snapshot")
    second = sha256_hex_from_text("Deribit official source snapshot")

    assert first == second
    assert first == _VALID_HASH
    assert len(first) == 64
    assert first == first.lower()


def test_sha256_hex_from_bytes_deterministic():
    first = sha256_hex_from_bytes(b"Deribit official source snapshot")
    second = sha256_hex_from_bytes(b"Deribit official source snapshot")

    assert first == second
    assert first == _VALID_HASH
    assert len(first) == 64
    assert first == first.lower()


def test_snapshot_contract_has_no_network_file_or_client_imports():
    source = SNAPSHOT_MODULE_PATH.read_text(encoding="utf-8").lower()
    tree = ast.parse(source)
    forbidden_import_roots = {
        "aiohttp",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "socket",
        "websocket",
        "websockets",
    }
    imports: set[str] = set()
    function_names: set[str] = set()
    call_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.FunctionDef):
            function_names.add(node.name)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            call_names.add(node.func.id)

    assert forbidden_import_roots.isdisjoint(imports)
    assert {"connect", "recv", "receive", "send", "subscribe", "start", "stop"}.isdisjoint(function_names)
    assert {"place_order", "cancel_order", "open"}.isdisjoint(function_names)
    assert "open" not in call_names
    assert "endpoint" not in source
    assert "api_key" not in source
    assert "api_secret" not in source
    assert "getenv" not in source


def test_deribit_docs_still_blocked_until_snapshots_supplied():
    combined = _deribit_docs()

    assert "`operational_status`: `BLOCKED`" in combined
    assert "`official_source_snapshots_supplied`: `false`" in combined
    assert "`official_source_snapshot_hashes_validated`: `false`" in combined
    assert "`manual_hash_required`: `YES`" in combined
    assert "CONTENT_HASH_UNAVAILABLE" in combined
    assert "`operational_status`: `READY`" not in combined


def test_static_registry_verified_but_connector_disabled():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value == "verified_from_official_docs"
    assert spec.enabled_for_connector is False


def test_connector_ready_dialects_remains_empty():
    assert connector_ready_dialects() == ()


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


_VALID_HASH = sha256_hex_from_text("Deribit official source snapshot")


def _snapshot(**overrides: object) -> OfficialSourceSnapshot:
    values = {
        "snapshot_id": "deribit-notifications-snapshot-2026-05-09",
        "source_id": "DERIBIT_NOTIFICATIONS",
        "venue_id": VenueId.DERIBIT,
        "official_url": "https://docs.deribit.com/#notifications",
        "retrieved_at_iso": "2026-05-09T00:00:00Z",
        "content_sha256": _VALID_HASH,
        "content_size_bytes": 32,
        "reviewer_id": "phase22k-manual-review",
        "reviewed_at_iso": "2026-05-10T00:00:00Z",
        "manual_review_status": "APPROVED",
        "rejection_reasons": (),
    }
    values.update(overrides)
    return OfficialSourceSnapshot(**values)  # type: ignore[arg-type]


def _deribit_docs() -> str:
    return "\n".join(
        (
            DERIBIT_DRAFT_PATH.read_text(encoding="utf-8"),
            CHECKLIST_PATH.read_text(encoding="utf-8"),
        )
    )


def _execution_request() -> ExecutionRequest:
    edge_signal = EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=0.5,
        score=0.5,
        evidence={"ofi": 0.5},
        timestamp_ns=100,
        is_valid=True,
        block_reason=None,
    )
    return ExecutionRequest(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        size=0.01,
        price_hint=50_000.0,
        risk_evaluation=RiskEvaluation(
            decision=RiskDecision.APPROVED,
            block_reason=None,
            system_state=SystemState.NORMAL,
            edge_signal=edge_signal,
            no_trade_decision=NoTradeDecision.allow(),
            evidence={},
            timestamp_ns=100,
        ),
        timestamp_ns=100,
    )
