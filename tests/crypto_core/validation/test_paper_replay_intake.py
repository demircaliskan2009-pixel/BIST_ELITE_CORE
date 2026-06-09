"""Tests for the paper replay intake gate (first paper-only consumer of a READY manifest)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from crypto_core.validation.paper_replay_intake import (
    PaperReplayIntake,
    PaperReplayIntakeError,
    PaperReplayIntakeStatus,
    build_paper_replay_intake,
    paper_replay_intake_to_dict,
)
from crypto_core.validation.replay_evidence_manifest import (
    ReplayEvidenceManifest,
    ReplayEvidenceManifestStatus,
    replay_evidence_manifest_to_dict,
)

_SOURCE = "offline-replay-v1"
_HIST = "historical-perp-journal-v1"
_BUNDLE = "f" * 64
_ADMISSION = "1" * 64
_BRIDGE = "e" * 64
_CORR = "corr:paper-replay-intake-001"
_REPLAY_ID = "paper-replay-001"
_OPERATOR = "operator-quant-1"
_LEDGER = (("LEAKAGE_BIAS_REPAINT", "b" * 64), ("PIT_PARITY", "c" * 64), ("STRATEGY_SPEC", "a" * 64))


def _manifest(**overrides) -> ReplayEvidenceManifest:
    base = {
        "schema_version": "replay-evidence-manifest.v1",
        "status": ReplayEvidenceManifestStatus.READY,
        "ready": True,
        "strategy_id": "bridge-s01",
        "strategy_digest": "d" * 64,
        "bundle_digest": _BUNDLE,
        "admission_digest": _ADMISSION,
        "bridge_digest": _BRIDGE,
        "replay_source_id": _SOURCE,
        "historical_data_source_id": _HIST,
        "replay_admission_status": "ACCEPTED",
        "decision_ledger_digests": _LEDGER,
        "evidence_digest_by_stage": (),
        "metadata": (),
        "rejection_reasons": (),
        "needs_research_reasons": (),
        "correlation_id": "corr:manifest-001",
        "manifest_digest": "0" * 64,
    }
    base.update(overrides)
    manifest = ReplayEvidenceManifest(**base)
    if "manifest_digest" in overrides:
        return manifest
    payload = replay_evidence_manifest_to_dict(manifest)
    payload.pop("manifest_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(manifest, manifest_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _intake(manifest=None, **overrides):
    manifest = _manifest() if manifest is None else manifest
    kwargs = {
        "requested_replay_id": _REPLAY_ID,
        "operator_id": _OPERATOR,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_paper_replay_intake(manifest, **kwargs)


def test_ready_manifest_builds_ready_intake():
    intake = _intake()
    assert isinstance(intake, PaperReplayIntake)
    assert intake.status is PaperReplayIntakeStatus.READY
    assert intake.ready is True
    assert intake.requested_replay_id == _REPLAY_ID
    assert intake.operator_id == _OPERATOR
    assert intake.manifest_status == "READY"
    assert intake.bundle_digest == _BUNDLE
    assert intake.replay_source_id == _SOURCE
    assert intake.rejection_reasons == ()
    assert len(intake.intake_digest) == 64
    assert intake.paper_only is True
    assert intake.real_orders_enabled is False
    assert intake.real_money_enabled is False


def test_forged_manifest_digest_rejects_before_ready():
    # 64-hex but not the recomputed digest -> boundary re-proof fails.
    forged = _manifest(manifest_digest="0" * 64)
    intake = _intake(forged)
    assert intake.status is PaperReplayIntakeStatus.REJECTED
    assert intake.ready is False
    assert "paper_replay_intake:manifest_digest_mismatch" in intake.rejection_reasons


def test_tampered_manifest_field_rejects():
    genuine = _manifest()
    tampered = replace(genuine, strategy_id="forged-strategy")  # keeps stale manifest_digest
    intake = _intake(tampered)
    assert intake.status is PaperReplayIntakeStatus.REJECTED
    assert "paper_replay_intake:manifest_digest_mismatch" in intake.rejection_reasons


def test_non_ready_manifest_statuses_propagate():
    rejected = _manifest(
        status=ReplayEvidenceManifestStatus.REJECTED, ready=False, rejection_reasons=("replay_evidence_manifest:x",)
    )
    assert _intake(rejected).status is PaperReplayIntakeStatus.REJECTED

    needs = _manifest(
        status=ReplayEvidenceManifestStatus.NEEDS_RESEARCH,
        ready=False,
        needs_research_reasons=("replay_evidence_manifest:y",),
    )
    assert _intake(needs).status is PaperReplayIntakeStatus.NEEDS_RESEARCH

    insufficient = _manifest(status=ReplayEvidenceManifestStatus.INSUFFICIENT_EVIDENCE, ready=False)
    assert _intake(insufficient).status is PaperReplayIntakeStatus.INSUFFICIENT_EVIDENCE


def test_invalid_chain_digests_reject():
    assert _intake(_manifest(bundle_digest="bad")).status is PaperReplayIntakeStatus.REJECTED
    assert _intake(_manifest(admission_digest="bad")).status is PaperReplayIntakeStatus.REJECTED
    assert _intake(_manifest(bridge_digest="bad")).status is PaperReplayIntakeStatus.REJECTED
    bad_manifest_digest = _intake(_manifest(manifest_digest="bad"))
    assert bad_manifest_digest.status is PaperReplayIntakeStatus.REJECTED
    assert "paper_replay_intake:manifest_digest_invalid" in bad_manifest_digest.rejection_reasons


def test_malformed_or_forbidden_identity_rejects():
    assert _intake(requested_replay_id="").status is PaperReplayIntakeStatus.REJECTED
    assert _intake(operator_id="").status is PaperReplayIntakeStatus.REJECTED

    forbidden = _intake(requested_replay_id="live_execution_run")
    assert forbidden.status is PaperReplayIntakeStatus.REJECTED
    assert "paper_replay_intake:forbidden_scope_token" in forbidden.rejection_reasons

    bist = _intake(operator_id="bist30-desk")
    assert bist.status is PaperReplayIntakeStatus.REJECTED
    assert "paper_replay_intake:bist_scope_leakage" in bist.rejection_reasons

    bad_source = _intake(_manifest(replay_source_id="scheduler_loop"))
    assert bad_source.status is PaperReplayIntakeStatus.REJECTED
    assert "paper_replay_intake:forbidden_scope_token" in bad_source.rejection_reasons


@pytest.mark.parametrize(
    ("kwargs", "manifest"),
    (
        ({"requested_replay_id": "order"}, None),
        ({"requested_replay_id": "orders"}, None),
        ({"requested_replay_id": "real_order"}, None),
        ({"requested_replay_id": "order-routing"}, None),
        ({"operator_id": "desk_order_router"}, None),
        ({"metadata": {"note": "real-orders"}}, None),
        ({}, _manifest(historical_data_source_id="paper-order-source")),
    ),
)
def test_plain_order_scope_tokens_reject(kwargs, manifest):
    intake = _intake(manifest=manifest, **kwargs)

    assert intake.status is PaperReplayIntakeStatus.REJECTED
    assert intake.ready is False
    assert "paper_replay_intake:forbidden_scope_token" in intake.rejection_reasons


@pytest.mark.parametrize("value", ("border-study", "orderly-paper-review", "preorder-check"))
def test_unrelated_order_substrings_do_not_reject(value):
    assert _intake(requested_replay_id=value).status is PaperReplayIntakeStatus.READY


def test_wrong_type_and_bad_metadata_raise():
    with pytest.raises(PaperReplayIntakeError):
        build_paper_replay_intake(
            {"status": "READY"},  # type: ignore[arg-type]
            requested_replay_id=_REPLAY_ID,
            operator_id=_OPERATOR,
            correlation_id=_CORR,
        )
    with pytest.raises(PaperReplayIntakeError):
        _intake(correlation_id="")
    with pytest.raises(PaperReplayIntakeError):
        _intake(metadata={"k": 5})
    with pytest.raises(PaperReplayIntakeError):
        _intake(metadata={5: "v"})


def test_metadata_normalized_and_deterministic():
    first = _intake(metadata={"scope": "crypto_only", "desk": "micro"})
    second = _intake(metadata={"desk": "micro", "scope": "crypto_only"})
    assert first.metadata == (("desk", "micro"), ("scope", "crypto_only"))
    assert first.intake_digest == second.intake_digest
    assert paper_replay_intake_to_dict(first) == paper_replay_intake_to_dict(second)
    assert paper_replay_intake_to_dict(first)["intake_digest"] == first.intake_digest


def test_material_change_changes_digest():
    base = _intake()
    assert _intake(requested_replay_id="paper-replay-002").intake_digest != base.intake_digest
    assert _intake(operator_id="operator-quant-2").intake_digest != base.intake_digest


def test_immutable_and_no_forbidden_fields():
    intake = _intake()
    with pytest.raises(FrozenInstanceError):
        intake.status = PaperReplayIntakeStatus.REJECTED  # type: ignore[misc]
    forbidden = {
        "order",
        "route",
        "venue",
        "exchange",
        "scheduler",
        "live",
        "runtime",
        "persistence",
        "store",
        "engine",
    }
    assert {field.name for field in fields(intake)}.isdisjoint(forbidden)
    payload = paper_replay_intake_to_dict(intake)
    assert payload["schema_version"] == "paper-replay-intake.v1"
    assert set(payload).isdisjoint(forbidden)
