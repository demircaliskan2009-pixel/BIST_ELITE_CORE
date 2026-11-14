"""Shared contract of the crypto_core CI pytest shards and the required ``tests`` gate.

The canonical crypto_core suite (``tests/crypto_core``) runs in parallel ``test-shard`` jobs of
``.github/workflows/ci.yml``.  Every shard collects the WHOLE suite and runs only the whole test files that
``assign_files`` gives it (``scripts/crypto_core/ci_shard_evidence.py``).  The required ``tests`` job
(``scripts/crypto_core/ci_attested_gate.py``) recomputes the same plan from the shards' own collections and
accepts only evidence of the current run attempt that covers every collected test exactly once.

This module holds what both sides must agree on: the evidence schema and file names, the exact shard invocation
and environment, the artifact and producer-job names, the accepted outcomes and the deterministic plan.
"""

from __future__ import annotations

from collections.abc import Sequence

SCHEMA = "crypto_core.ci.shard_evidence.v1"
REPORT_FILE = "report.json"
COVERAGE_FILE = "coverage.sqlite"
EVIDENCE_DIR = "ci-shard-evidence"
PLUGIN_MODULE = "scripts.crypto_core.ci_shard_evidence"
SOURCE_DIR = "src/crypto_core"
SUITE_DIR = "tests/crypto_core"
MAX_SHARDS = 16

# The serial gate ran ``python -m pytest -q -W error --cov=src/crypto_core --cov-report=term --cov-fail-under=70
# tests/crypto_core``.  A shard keeps the same test path, verbosity, warning policy and coverage source; it adds
# only the shard plugin, prints no partial coverage table and leaves the 70% floor to the gate, which applies it to
# the exact union of all shards' raw coverage (never to one shard's partial percentage).
SUITE_ARGS = ("-q", "-W", "error", f"--cov={SOURCE_DIR}", "--cov-report=", SUITE_DIR)

# Environment that would change what pytest collects or how coverage is recorded.  A shard records these values
# literally and the gate accepts only this exact snapshot (``None`` means unset).
CANONICAL_ENVIRONMENT = {
    "PYTEST_ADDOPTS": None,
    "PYTEST_PLUGINS": None,
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": None,
    "PYTHONWARNINGS": "error",
    "COVERAGE_FILE": None,
    "COVERAGE_RCFILE": None,
}

ACCEPTED_OUTCOMES = ("passed", "skipped", "xfailed", "xpassed")

LINT_JOB = "lint"
SHARD_JOB_PREFIX = "pytest shard "


def shard_invocation(index: int, count: int) -> list[str]:
    """The exact pytest arguments of shard ``index`` of ``count`` (``python -m pytest <these>``)."""
    return ["-p", PLUGIN_MODULE, f"--ci-shard={index}/{count}", f"--ci-evidence-dir={EVIDENCE_DIR}", *SUITE_ARGS]


def shard_job_name(index: int, count: int) -> str:
    """The GitHub Actions job name of shard ``index`` (``name: pytest shard ${{ matrix.shard }} of N``)."""
    return f"{SHARD_JOB_PREFIX}{index} of {count}"


def artifact_name(run_id: int, run_attempt: int, index: int, count: int) -> str:
    """The artifact a shard uploads: bound by name to one workflow run and one run attempt."""
    return f"crypto-core-pytest-run-{run_id}-attempt-{run_attempt}-shard-{index}-of-{count}"


# Pytest wall time per test file, in milliseconds, of the accepted serial ``tests`` job on main f1de3edf
# (GitHub Actions run 43219583077, job 131187380505: Python 3.11, coverage on), attributed by splitting each
# timestamped ``-q`` progress line's elapsed time equally over its tests.  Files under one second are not listed
# and weigh ``DEFAULT_MS_PER_TEST`` per collected test, which is also how a new file enters the plan.  Weights only
# place the cuts between shards: whatever they say, every collected file is assigned to exactly one shard.
DEFAULT_MS_PER_TEST = 5
FILE_WEIGHT_MS = {
    "tests/crypto_core/service/test_phase10e.py": 12_021,
    "tests/crypto_core/service/test_phase11a.py": 2_967,
    "tests/crypto_core/service/test_phase20c.py": 1_398,
    "tests/crypto_core/service/test_phase20g.py": 1_132,
    "tests/crypto_core/service/test_phase20h.py": 1_950,
    "tests/crypto_core/service/test_phase20i.py": 1_237,
    "tests/crypto_core/service/test_phase20j.py": 1_299,
    "tests/crypto_core/service/test_phase8a.py": 2_193,
    "tests/crypto_core/service/test_phase8b.py": 2_442,
    "tests/crypto_core/service/test_phase8c.py": 1_942,
    "tests/crypto_core/temporal/test_temporal_scheduler.py": 11_672,
    "tests/crypto_core/test_phase11b_ext_regime_propagation.py": 17_179,
    "tests/crypto_core/validation/test_authenticated_pit_ingress.py": 103_335,
    "tests/crypto_core/validation/test_authenticated_pit_ingress_oracle.py": 164_379,
    "tests/crypto_core/validation/test_backtest_admission.py": 8_384,
    "tests/crypto_core/validation/test_backtest_replay_admission.py": 19_562,
    "tests/crypto_core/validation/test_backtest_replay_bridge.py": 2_442,
    "tests/crypto_core/validation/test_deterministic_paper_replay_harness.py": 1_560,
    "tests/crypto_core/validation/test_edge_idea_intake_evidence.py": 114_330,
    "tests/crypto_core/validation/test_edge_kill_quarantine_decision.py": 758_042,
    "tests/crypto_core/validation/test_edge_leakage_bias_evidence.py": 73_039,
    "tests/crypto_core/validation/test_edge_paper_admission_decision.py": 71_264,
    "tests/crypto_core/validation/test_edge_pre_paper_validation_evidence.py": 102_762,
    "tests/crypto_core/validation/test_edge_pre_paper_validation_policy.py": 6_282,
    "tests/crypto_core/validation/test_edge_source_packet_evidence.py": 5_021,
    "tests/crypto_core/validation/test_edge_strategy_spec_admission.py": 3_663,
    "tests/crypto_core/validation/test_edge_trial_count_chain.py": 3_283,
    "tests/crypto_core/validation/test_edge_walk_forward_oos_evidence.py": 120_146,
    "tests/crypto_core/validation/test_governed_admitted_variant_paper_execution.py": 332_096,
    "tests/crypto_core/validation/test_governed_paper_allocation_envelope.py": 111_975,
    "tests/crypto_core/validation/test_governed_paper_ctr_qualification.py": 5_761,
    "tests/crypto_core/validation/test_governed_paper_entry_safety.py": 190_190,
    "tests/crypto_core/validation/test_governed_paper_execution_authority.py": 460_135,
    "tests/crypto_core/validation/test_governed_paper_kill_switch.py": 127_986,
    "tests/crypto_core/validation/test_governed_paper_protective_authority.py": 7_530,
    "tests/crypto_core/validation/test_governed_paper_protective_ledger.py": 41_070,
    "tests/crypto_core/validation/test_governed_paper_protective_lineage.py": 102_299,
    "tests/crypto_core/validation/test_governed_paper_regime_state.py": 175_084,
    "tests/crypto_core/validation/test_governed_paper_sizing_chain.py": 66_792,
    "tests/crypto_core/validation/test_governed_paper_system_safety.py": 66_697,
    "tests/crypto_core/validation/test_governed_paper_typed_identity.py": 4_091,
    "tests/crypto_core/validation/test_historical_decision_run.py": 21_832,
    "tests/crypto_core/validation/test_historical_execution_economics.py": 141_924,
    "tests/crypto_core/validation/test_historical_execution_economics_policy.py": 97_530,
    "tests/crypto_core/validation/test_historical_execution_protective_lifecycle.py": 127_375,
    "tests/crypto_core/validation/test_historical_execution_stress.py": 63_225,
    "tests/crypto_core/validation/test_historical_ohlc_bar_archive.py": 13_332,
    "tests/crypto_core/validation/test_historical_pit_dataset.py": 4_484,
    "tests/crypto_core/validation/test_historical_walk_forward_metric_policy.py": 12_510,
    "tests/crypto_core/validation/test_historical_walk_forward_metrics.py": 73_093,
    "tests/crypto_core/validation/test_leakage_bias_repaint.py": 4_597,
    "tests/crypto_core/validation/test_machine_time_drand_quicknet_chain_profile.py": 17_400,
    "tests/crypto_core/validation/test_machine_time_drand_quicknet_verifier_profile.py": 44_554,
    "tests/crypto_core/validation/test_machine_time_policy.py": 7_296,
    "tests/crypto_core/validation/test_machine_time_source_registry.py": 6_457,
    "tests/crypto_core/validation/test_machine_time_source_trust_snapshot.py": 5_210,
    "tests/crypto_core/validation/test_mt4_blst_dependency_admission_evidence.py": 8_175,
    "tests/crypto_core/validation/test_mt4_s3c_static_worker_qualification.py": 8_471,
    "tests/crypto_core/validation/test_mt4_s3c_trusted_attestation.py": 4_038,
    "tests/crypto_core/validation/test_paper_admission_ledger_bridge.py": 1_073,
    "tests/crypto_core/validation/test_paper_allocator_intent_draft.py": 1_793,
    "tests/crypto_core/validation/test_paper_attested_operational_day_evidence.py": 1_350,
    "tests/crypto_core/validation/test_paper_daily_return_series_evidence.py": 1_085,
    "tests/crypto_core/validation/test_paper_deterministic_time_window_adapter.py": 1_212,
    "tests/crypto_core/validation/test_paper_governor_decision.py": 1_173,
    "tests/crypto_core/validation/test_paper_portfolio_allocation_decision.py": 141_869,
    "tests/crypto_core/validation/test_paper_portfolio_governance_decision.py": 14_590,
    "tests/crypto_core/validation/test_paper_portfolio_performance_path_policy.py": 1_893,
    "tests/crypto_core/validation/test_paper_sleeve_admission_review_readiness.py": 2_777,
    "tests/crypto_core/validation/test_paper_sleeve_correlation_evidence.py": 15_166,
    "tests/crypto_core/validation/test_paper_sleeve_daily_valuation_evidence.py": 4_770,
    "tests/crypto_core/validation/test_paper_sleeve_drawdown_evidence.py": 7_454,
    "tests/crypto_core/validation/test_paper_sleeve_equity_basis_policy.py": 1_228,
    "tests/crypto_core/validation/test_paper_sleeve_performance_evidence.py": 4_254,
    "tests/crypto_core/validation/test_paper_sleeve_promotion_demotion_decision.py": 43_854,
    "tests/crypto_core/validation/test_paper_stage4_comparison_evidence_v2.py": 1_569,
    "tests/crypto_core/validation/test_paper_stage4_completion_decision_v2.py": 1_091,
    "tests/crypto_core/validation/test_paper_vs_backtest_comparator_bridge.py": 1_237,
    "tests/crypto_core/validation/test_paper_vs_backtest_methodology.py": 1_190,
    "tests/crypto_core/validation/test_paper_vs_backtest_methodology_v2.py": 4_171,
    "tests/crypto_core/validation/test_pbo.py": 1_845,
    "tests/crypto_core/validation/test_pipeline.py": 1_649,
    "tests/crypto_core/validation/test_pit_parity.py": 1_557,
    "tests/crypto_core/validation/test_regime_conditioned_performance_evidence.py": 12_791,
    "tests/crypto_core/validation/test_regime_feature_policy.py": 2_710,
    "tests/crypto_core/validation/test_regime_feature_series_evidence.py": 10_804,
    "tests/crypto_core/validation/test_regime_filter_admission_decision.py": 8_796,
    "tests/crypto_core/validation/test_regime_label_evidence.py": 8_222,
    "tests/crypto_core/validation/test_regime_stability_evidence.py": 9_356,
    "tests/crypto_core/validation/test_replay_evidence_manifest.py": 1_376,
    "tests/crypto_core/validation/test_roughtime_v19_attested_operational_day_digest_binding.py": 70_489,
    "tests/crypto_core/validation/test_roughtime_v19_certificate_verification.py": 6_168,
    "tests/crypto_core/validation/test_roughtime_v19_kernel.py": 2_545,
    "tests/crypto_core/validation/test_roughtime_v19_request_in_signed_response.py": 91_041,
    "tests/crypto_core/validation/test_roughtime_v19_request_inclusion.py": 1_198,
    "tests/crypto_core/validation/test_roughtime_v19_signed_response_verification.py": 8_374,
    "tests/crypto_core/validation/test_secondary_metrics_policy.py": 2_598,
    "tests/crypto_core/validation/test_strategy_executable_binding.py": 4_166,
    "tests/crypto_core/validation/test_strategy_executable_profiles.py": 1_934,
    "tests/crypto_core/venue/test_phase96a_paper_runtime_heartbeat_blocker_chain_continuity_doc.py": 1_287,
    "tests/crypto_core/venue/test_phase96c_paper_runtime_heartbeat_blocker_chain_continuity_validation.py": 1_287,
    "tests/crypto_core/venue/test_phase96d_paper_runtime_heartbeat_blocker_chain_continuity_fail_closed.py": 1_287,
    "tests/crypto_core/venue/test_phase97a_paper_runtime_heartbeat_blocker_chain_continuity_doc.py": 1_287,
    "tests/crypto_core/venue/test_phase97c_paper_runtime_heartbeat_blocker_chain_continuity_validation.py": 1_287,
    "tests/crypto_core/venue/test_phase97d_paper_runtime_heartbeat_blocker_chain_continuity_fail_closed.py": 1_287,
    "tests/crypto_core/venue/test_phase98a_paper_runtime_heartbeat_blocker_chain_continuity_doc.py": 1_287,
    "tests/crypto_core/venue/test_phase98c_paper_runtime_heartbeat_blocker_chain_continuity_validation.py": 1_287,
    "tests/crypto_core/venue/test_phase98d_paper_runtime_heartbeat_blocker_chain_continuity_fail_closed.py": 1_287,
    "tests/crypto_core/venue/test_phase99a_paper_runtime_heartbeat_blocker_chain_continuity_doc.py": 1_287,
    "tests/crypto_core/venue/test_phase99c_paper_runtime_heartbeat_blocker_chain_continuity_validation.py": 1_287,
    "tests/crypto_core/venue/test_phase99d_paper_runtime_heartbeat_blocker_chain_continuity_fail_closed.py": 1_287,
}


def node_file(nodeid: str) -> str:
    """The test file of a pytest node id (``path/to/test_x.py::Class::test[param]`` -> ``path/to/test_x.py``)."""
    return nodeid.split("::", 1)[0]


def files_in_order(nodeids: Sequence[str]) -> list[tuple[str, int]]:
    """``(test file, collected test count)`` in order of each file's first appearance."""
    counts: dict[str, int] = {}
    for nodeid in nodeids:
        path = node_file(nodeid)
        counts[path] = counts.get(path, 0) + 1
    return list(counts.items())


def file_weight(path: str, tests: int) -> int:
    """Measured weight of a test file in milliseconds, or the per-test default for an unlisted file."""
    measured = FILE_WEIGHT_MS.get(path)
    if measured is not None:
        return measured
    return max(1, tests * DEFAULT_MS_PER_TEST)


def assign_files(files: Sequence[tuple[str, int]], count: int) -> dict[str, int]:
    """Assign every test file, whole, to one shard ``1..count``; shards are contiguous runs in collection order.

    A file goes to the shard whose equal share of the total weight contains the midpoint of the file's own weight
    interval.  Midpoints strictly increase along the order, so shard numbers never decrease, and integer
    arithmetic makes the plan identical in every process that sees the same files in the same order.
    """
    if not 1 <= count <= MAX_SHARDS:
        raise ValueError(f"shard count must be within 1..{MAX_SHARDS}, got {count}")
    if not files:
        raise ValueError("cannot plan shards for an empty collection")
    paths = [path for path, _ in files]
    if len(set(paths)) != len(paths):
        raise ValueError("a test file appears twice in the plan input")
    weights = [file_weight(path, tests) for path, tests in files]
    total = sum(weights)
    assignment: dict[str, int] = {}
    start = 0
    for path, weight in zip(paths, weights):
        assignment[path] = min(count, (2 * start + weight) * count // (2 * total) + 1)
        start += weight
    return assignment


def plan_selection(nodeids: Sequence[str], count: int) -> dict[int, list[str]]:
    """Node ids of each shard ``1..count``, in collection order, for one complete collection."""
    assignment = assign_files(files_in_order(nodeids), count)
    selection: dict[int, list[str]] = {index: [] for index in range(1, count + 1)}
    for nodeid in nodeids:
        selection[assignment[node_file(nodeid)]].append(nodeid)
    return selection
