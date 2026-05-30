from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_promotion_post_audit import (
    audit_deribit_paper_promotion_execution_post_audit,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE59_AUDIT = Path("docs/crypto_core/DERIBIT_PAPER_PROMOTION_EXECUTION_TELEMETRY_AUDIT_59B.json")
PHASE58_EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_58B.json")
POST_AUDIT = Path("docs/crypto_core/DERIBIT_PAPER_PROMOTION_EXECUTION_POST_AUDIT_60B.json")
FALSE_EXECUTION_FLAGS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase59_audit() -> dict[str, object]:
    return _json(PHASE59_AUDIT)


def _phase58_execution() -> dict[str, object]:
    return _json(PHASE58_EXECUTION)


def _post_audit() -> dict[str, object]:
    return _json(POST_AUDIT)


def _expected_post_audit() -> dict[str, object]:
    return audit_deribit_paper_promotion_execution_post_audit(_phase59_audit(), _phase58_execution()).artifact_payload


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def test_phase60b_artifact_has_required_schema_and_source_references() -> None:
    artifact = _post_audit()

    assert PHASE59_AUDIT.exists() and PHASE58_EXECUTION.exists() and POST_AUDIT.exists()
    assert artifact["schema_version"] == "deribit_paper_promotion_execution_post_audit.v1"
    assert artifact["phase"] == "60"
    assert artifact["source"] == "deterministic_phase60_paper_promotion_execution_post_audit"
    assert artifact["source_phase59_telemetry_audit"] == str(PHASE59_AUDIT).replace("\\", "/")
    assert artifact["source_phase58_promotion_execution"] == str(PHASE58_EXECUTION).replace("\\", "/")


def test_phase60b_artifact_matches_runtime_output() -> None:
    artifact = _post_audit()

    assert artifact == _expected_post_audit()
    assert artifact["post_audit_status"] == "POST_AUDITED"
    assert artifact["post_audit_verdict"] == "PASS"
    assert artifact["promotion_telemetry_audit_verdict"] == "PASS"
    assert artifact["promotion_execution_status"] == "EXECUTED"
    assert artifact["promotion_granted"] is True
    assert artifact["paper_promoted"] is True
    assert artifact["report_only"] is True
    assert artifact["no_new_execution"] is True


def test_phase60b_artifact_preserves_no_live_scope_connector_count_and_hashes() -> None:
    artifact = _post_audit()

    assert len(connector_ready_dialects()) == 1 and artifact["connector_ready_dialects_count"] == 1
    for field in FALSE_EXECUTION_FLAGS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
    assert (
        artifact["source_phase59_telemetry_audit_sha256"]
        == "54f374a799c315b1f3b51ffd7bf04e3fd989d9e5ee29f58bcc291538fd2412ef"
    )
    assert (
        artifact["source_phase58_promotion_execution_sha256"]
        == "67a04f318c99d14fcb59eeb64c0f5b2216f6ced5c2c76e88ff265dc77599c7f8"
    )
    assert artifact["post_audit_checks"] == [
        "source_hashes_stable",
        "no_live_scope_preserved",
        "no_private_execution_scope_preserved",
        "no_scheduler_loop_scope_preserved",
        "connector_ready_dialects_preserved",
    ]
    assert artifact["next_blocker"] == "PAPER_PROMOTED_RUNTIME_READINESS_NOT_READY"
