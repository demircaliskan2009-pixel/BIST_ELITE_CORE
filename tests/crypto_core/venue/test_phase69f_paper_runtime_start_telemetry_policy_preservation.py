from __future__ import annotations

from tests.crypto_core.venue.test_phase69b_paper_runtime_start_telemetry_artifact import _artifact


def test_phase69f_preserves_paper_only_promotion_scope() -> None:
    artifact = _artifact()

    assert artifact["paper_promoted"] is True
    assert artifact["promotion_granted"] is True
    assert artifact["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"


def test_phase69f_preserves_source_provenance_chain_hashes() -> None:
    artifact = _artifact()

    assert (
        artifact["source_phase68_runtime_start_execution_sha256"]
        == "bc402eea5067accf3d57219fec979bc857386ef43bfad4eee60a9e92d9c9f550"
    )
    assert (
        artifact["source_phase67_runtime_start_approval_sha256"]
        == "04d4603923a12d518bc49c95800f439558bfb35460f91ff2d6f28b45fd49e5ef"
    )
    assert (
        artifact["source_phase65_runtime_enablement_execution_sha256"]
        == "d60bfd007a2c2733a95c09d538abdeb9d253b4bb977e995e36fc7c729ee9c54d"
    )


def test_phase69f_execution_checks_record_policy_guards() -> None:
    artifact = _artifact()

    assert artifact["execution_checks"] == [
        "source_phase68_runtime_start_execution_exists",
        "phase68_runtime_start_executed",
        "runtime_enabled_true",
        "runtime_started_true",
        "no_live_scope_preserved",
        "no_private_execution_scope_preserved",
        "no_scheduler_loop_scope_preserved",
        "no_campaign_session_run_scope_preserved",
        "source_phase67_65_provenance_stable",
        "connector_ready_dialects_preserved",
    ]
