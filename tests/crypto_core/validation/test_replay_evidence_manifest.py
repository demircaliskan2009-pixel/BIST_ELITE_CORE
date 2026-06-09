"""Tests for the replay evidence manifest (deterministic paper-only chain record over a bridge result)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from crypto_core.validation.backtest_replay_admission import (
    BacktestReplayAdmissionResult,
    BacktestReplayAdmissionStatus,
    BacktestReplayWindow,
)
from crypto_core.validation.backtest_replay_bridge import BacktestReplayBridgeResult
from crypto_core.validation.replay_evidence_manifest import (
    ReplayEvidenceManifest,
    ReplayEvidenceManifestError,
    ReplayEvidenceManifestStatus,
    build_replay_evidence_manifest,
    replay_evidence_manifest_to_dict,
)

_SOURCE = "offline-replay-v1"
_HIST = "historical-perp-journal-v1"
_ADMISSION = "1" * 64
_BUNDLE = "f" * 64
_BRIDGE = "e" * 64
_CORR = "corr:replay-evidence-manifest-001"
_LEDGER = {"STRATEGY_SPEC": "a" * 64, "LEAKAGE_BIAS_REPAINT": "b" * 64, "PIT_PARITY": "c" * 64}


def _replay_result(
    *,
    status: BacktestReplayAdmissionStatus = BacktestReplayAdmissionStatus.ACCEPTED,
    rejection_reasons: tuple[str, ...] = (),
    needs_research_reasons: tuple[str, ...] = (),
    replay_source_id: str = _SOURCE,
    historical_data_source_id: str = _HIST,
    decision_ledger_digests: dict | None = None,
    evidence_digest_by_stage: dict | None = None,
) -> BacktestReplayAdmissionResult:
    accepted = status is BacktestReplayAdmissionStatus.ACCEPTED and not rejection_reasons and not needs_research_reasons
    return BacktestReplayAdmissionResult(
        accepted=accepted,
        status=status,
        strategy_id="bridge-s01",
        strategy_digest="d" * 64,
        replay_source_id=replay_source_id,
        historical_data_source_id=historical_data_source_id,
        replay_window=BacktestReplayWindow(start_ns=1_000, end_ns=2_000),
        decision_ledger_digests=dict(_LEDGER) if decision_ledger_digests is None else decision_ledger_digests,
        evidence_digest_by_stage=evidence_digest_by_stage or {},
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
    )


def _bridge_result(
    *,
    status: BacktestReplayAdmissionStatus = BacktestReplayAdmissionStatus.ACCEPTED,
    admission_digest: str = _ADMISSION,
    bridge_digest: str = _BRIDGE,
    replay: BacktestReplayAdmissionResult | None = "default",  # sentinel
    rejection_reasons: tuple[str, ...] = (),
    needs_research_reasons: tuple[str, ...] = (),
) -> BacktestReplayBridgeResult:
    if replay == "default":
        replay = _replay_result(
            status=status, rejection_reasons=rejection_reasons, needs_research_reasons=needs_research_reasons
        )
    accepted = status is BacktestReplayAdmissionStatus.ACCEPTED
    return BacktestReplayBridgeResult(
        schema_version="backtest-replay-bridge.v1",
        status=status,
        accepted=accepted,
        admission_digest=admission_digest,
        strategy_id="bridge-s01",
        strategy_digest="d" * 64,
        replay_admission_status=replay.status.value if replay is not None else None,
        replay_admission_result=replay,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        correlation_id="corr:bridge",
        bridge_digest=bridge_digest,
    )


def _manifest(bridge_result=None, **overrides):
    bridge_result = _bridge_result() if bridge_result is None else bridge_result
    kwargs = {
        "bundle_digest": _BUNDLE,
        "admission_digest": bridge_result.admission_digest,
        "replay_source_id": _SOURCE,
        "historical_data_source_id": _HIST,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_replay_evidence_manifest(bridge_result, **kwargs)


def test_accepted_chain_builds_ready_manifest():
    manifest = _manifest()
    assert isinstance(manifest, ReplayEvidenceManifest)
    assert manifest.status is ReplayEvidenceManifestStatus.READY
    assert manifest.ready is True
    assert manifest.bundle_digest == _BUNDLE
    assert manifest.admission_digest == _ADMISSION
    assert manifest.bridge_digest == _BRIDGE
    assert manifest.replay_source_id == _SOURCE
    assert dict(manifest.decision_ledger_digests) == _LEDGER
    assert manifest.rejection_reasons == ()
    assert len(manifest.manifest_digest) == 64
    assert manifest.paper_only is True
    assert manifest.real_orders_enabled is False


def test_non_accepted_bridge_propagates():
    rejected = _bridge_result(
        status=BacktestReplayAdmissionStatus.REJECTED, replay=None, rejection_reasons=("backtest_replay_admission:x",)
    )
    assert _manifest(rejected).status is ReplayEvidenceManifestStatus.REJECTED

    needs = _bridge_result(
        status=BacktestReplayAdmissionStatus.NEEDS_RESEARCH, needs_research_reasons=("backtest_replay_admission:y",)
    )
    assert _manifest(needs).status is ReplayEvidenceManifestStatus.NEEDS_RESEARCH

    insufficient = _bridge_result(status=BacktestReplayAdmissionStatus.INSUFFICIENT_EVIDENCE)
    assert _manifest(insufficient).status is ReplayEvidenceManifestStatus.INSUFFICIENT_EVIDENCE


def test_admission_digest_mismatch_rejects():
    manifest = _manifest(admission_digest="9" * 64)
    assert manifest.status is ReplayEvidenceManifestStatus.REJECTED
    assert "replay_evidence_manifest:admission_digest_mismatch" in manifest.rejection_reasons


def test_invalid_digests_reject():
    assert _manifest(bundle_digest="bad").status is ReplayEvidenceManifestStatus.REJECTED
    assert _manifest(admission_digest="bad").status is ReplayEvidenceManifestStatus.REJECTED
    bad_bridge = _bridge_result(bridge_digest="not-a-digest")
    manifest = _manifest(bad_bridge)
    assert manifest.status is ReplayEvidenceManifestStatus.REJECTED
    assert "replay_evidence_manifest:bridge_digest_invalid" in manifest.rejection_reasons


def test_missing_replay_result_insufficient():
    bridge = _bridge_result(status=BacktestReplayAdmissionStatus.ACCEPTED, replay=None)
    manifest = _manifest(bridge)
    assert manifest.status is ReplayEvidenceManifestStatus.INSUFFICIENT_EVIDENCE
    assert "replay_evidence_manifest:replay_admission_result_missing" in manifest.rejection_reasons


def test_replay_source_id_mismatch_rejects():
    manifest = _manifest(replay_source_id="other-source")
    assert manifest.status is ReplayEvidenceManifestStatus.REJECTED
    assert "replay_evidence_manifest:replay_source_id_mismatch" in manifest.rejection_reasons


def test_malformed_ledger_or_evidence_digest_rejects():
    bad_ledger = _bridge_result(replay=_replay_result(decision_ledger_digests={"STRATEGY_SPEC": "bad"}))
    manifest = _manifest(bad_ledger)
    assert manifest.status is ReplayEvidenceManifestStatus.REJECTED
    assert "replay_evidence_manifest:decision_ledger_digest_malformed" in manifest.rejection_reasons

    bad_evidence = _bridge_result(replay=_replay_result(evidence_digest_by_stage={"STRATEGY_SPEC": "bad"}))
    manifest = _manifest(bad_evidence)
    assert manifest.status is ReplayEvidenceManifestStatus.REJECTED
    assert "replay_evidence_manifest:evidence_digest_malformed" in manifest.rejection_reasons


def test_empty_ledger_digests_insufficient():
    empty = _bridge_result(replay=_replay_result(decision_ledger_digests={}))
    manifest = _manifest(empty)
    assert manifest.status is ReplayEvidenceManifestStatus.INSUFFICIENT_EVIDENCE
    assert "replay_evidence_manifest:decision_ledger_digests_missing" in manifest.rejection_reasons


def test_forbidden_scope_in_source_id_rejects():
    replay = _replay_result(replay_source_id="live_feed")
    bridge = _bridge_result(replay=replay)
    manifest = _manifest(bridge, replay_source_id="live_feed")
    assert manifest.status is ReplayEvidenceManifestStatus.REJECTED
    assert "replay_evidence_manifest:forbidden_scope_token" in manifest.rejection_reasons


def test_wrong_type_and_bad_metadata_raise():
    with pytest.raises(ReplayEvidenceManifestError):
        build_replay_evidence_manifest(
            {"status": "ACCEPTED"},  # type: ignore[arg-type]
            bundle_digest=_BUNDLE,
            admission_digest=_ADMISSION,
            replay_source_id=_SOURCE,
            historical_data_source_id=_HIST,
            correlation_id=_CORR,
        )
    with pytest.raises(ReplayEvidenceManifestError):
        _manifest(correlation_id="")
    with pytest.raises(ReplayEvidenceManifestError):
        _manifest(metadata={"k": 5})
    with pytest.raises(ReplayEvidenceManifestError):
        _manifest(metadata={5: "v"})


def test_metadata_recorded_and_deterministic():
    first = _manifest(metadata={"scope": "crypto_only", "note": "ofi"})
    second = _manifest(metadata={"note": "ofi", "scope": "crypto_only"})
    assert first.metadata == (("note", "ofi"), ("scope", "crypto_only"))
    assert first.manifest_digest == second.manifest_digest
    assert replay_evidence_manifest_to_dict(first) == replay_evidence_manifest_to_dict(second)


def test_material_change_changes_digest():
    base = _manifest()
    assert _manifest(bundle_digest="0" * 64).manifest_digest != base.manifest_digest


def test_immutable_and_no_forbidden_fields():
    manifest = _manifest()
    with pytest.raises(FrozenInstanceError):
        manifest.status = ReplayEvidenceManifestStatus.REJECTED  # type: ignore[misc]
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
    assert {field.name for field in fields(manifest)}.isdisjoint(forbidden)
    payload = replay_evidence_manifest_to_dict(manifest)
    assert payload["schema_version"] == "replay-evidence-manifest.v1"
    assert set(payload).isdisjoint(forbidden)
