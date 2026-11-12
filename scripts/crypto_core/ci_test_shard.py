"""Deterministic file-level sharding of the crypto_core pytest suite for CI, with per-shard evidence.

Every mandatory ``test-shard`` job of ``.github/workflows/ci.yml`` loads this module as a pytest plugin
(``-p scripts.crypto_core.ci_test_shard``); without ``--ci-shard`` the plugin is inert.

A shard collects the WHOLE canonical suite, assigns every collected test FILE to exactly one shard with
:func:`partition` -- a pure function of the collected node ids, the measured weights below and the shard count --
deselects the tests of every other shard, runs its own, and writes one JSON report: the complete collection in
order, its own selection, the outcome of every selected test, the pytest exit status, the tested head, the raw
invocation and the SHA-256 of its raw coverage data file. ``scripts/crypto_core/ci_test_aggregate.py`` (the
required ``tests`` job) recomputes the partition from the reports and accepts nothing it cannot re-derive.

Whole files, never parts of one, are the unit, and each shard is one contiguous run of files in collection order:
neighbouring test modules share expensive worlds cached at module level (``edge_*``, ``governed_paper_*``,
``historical_*``), so keeping them in one process makes each shard rebuild far less than a weight-balanced scatter
would. A file absent from :data:`FILE_WEIGHTS` -- every newly added file included -- is still collected and
assigned (its weight is :data:`DEFAULT_TEST_WEIGHT_MS` per test), so no test can fall outside the partition; a
stale or missing weight changes only the balance, never the selection.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

REPORT_SCHEMA = "crypto_core_ci_test_shard_report_v1"
PLUGIN = "scripts.crypto_core.ci_test_shard"
REPORT_NAME = "report.json"
COVERAGE_NAME = "coverage.sqlite"
# The one canonical pytest invocation of a shard, minus this plugin's own arguments. It is the serial gate's
# invocation without ``--cov-report=term --cov-fail-under=70``: the floor is applied once, to the verified union.
CANONICAL_PYTEST_ARGS = ("-q", "-W", "error", "--cov=src/crypto_core", "--cov-report=", "tests/crypto_core")
ACCEPTED_OUTCOMES = frozenset({"passed", "skipped", "xfailed", "xpassed"})
_OWN_OPTIONS = ("--ci-shard=", "--ci-shard-head=", "--ci-shard-report=")

# What the heaviest test files cost, in whole seconds: the time each file's tests took INSIDE its shard in a local
# contiguous three-shard run of main f1de3edf with coverage on -- so a file's weight includes the cached worlds it had
# to build where it sat. Relative units (that run was roughly 1.4x slower than a CI runner). Files under 5 s are
# left to the default, which is the same run's ~10 ms per test. Refresh from the shard reports' ``file_seconds``.
FILE_WEIGHTS: Mapping[str, int] = {
    "tests/crypto_core/ci/test_ci_test_shard.py": 8,
    "tests/crypto_core/service/test_phase10e.py": 95,
    "tests/crypto_core/service/test_phase20b.py": 6,
    "tests/crypto_core/validation/test_authenticated_pit_ingress.py": 193,
    "tests/crypto_core/validation/test_authenticated_pit_ingress_oracle.py": 292,
    "tests/crypto_core/validation/test_edge_kill_quarantine_decision.py": 1110,
    "tests/crypto_core/validation/test_edge_leakage_bias_evidence.py": 52,
    "tests/crypto_core/validation/test_edge_paper_admission_decision.py": 91,
    "tests/crypto_core/validation/test_edge_pre_paper_validation_evidence.py": 224,
    "tests/crypto_core/validation/test_edge_strategy_spec_admission.py": 8,
    "tests/crypto_core/validation/test_edge_walk_forward_oos_evidence.py": 48,
    "tests/crypto_core/validation/test_governed_admitted_variant_paper_execution.py": 1020,
    "tests/crypto_core/validation/test_governed_paper_allocation_envelope.py": 12,
    "tests/crypto_core/validation/test_governed_paper_entry_safety.py": 257,
    "tests/crypto_core/validation/test_governed_paper_execution_authority.py": 684,
    "tests/crypto_core/validation/test_governed_paper_kill_switch.py": 68,
    "tests/crypto_core/validation/test_governed_paper_protective_ledger.py": 124,
    "tests/crypto_core/validation/test_governed_paper_protective_lineage.py": 116,
    "tests/crypto_core/validation/test_governed_paper_regime_state.py": 645,
    "tests/crypto_core/validation/test_governed_paper_sizing_chain.py": 69,
    "tests/crypto_core/validation/test_governed_paper_system_safety.py": 54,
    "tests/crypto_core/validation/test_historical_decision_run.py": 39,
    "tests/crypto_core/validation/test_historical_execution_economics.py": 316,
    "tests/crypto_core/validation/test_historical_execution_protective_lifecycle.py": 370,
    "tests/crypto_core/validation/test_historical_execution_stress.py": 15,
    "tests/crypto_core/validation/test_historical_ohlc_bar_archive.py": 8,
    "tests/crypto_core/validation/test_historical_pit_dataset.py": 7,
    "tests/crypto_core/validation/test_historical_walk_forward_metrics.py": 133,
    "tests/crypto_core/validation/test_machine_time_drand_quicknet_chain_profile.py": 32,
    "tests/crypto_core/validation/test_machine_time_drand_quicknet_verifier_profile.py": 92,
    "tests/crypto_core/validation/test_machine_time_source_registry.py": 11,
    "tests/crypto_core/validation/test_mt4_blst_dependency_admission_evidence.py": 7,
    "tests/crypto_core/validation/test_mt4_s3c_static_worker_qualification.py": 32,
    "tests/crypto_core/validation/test_mt4_s3c_trusted_attestation.py": 7,
    "tests/crypto_core/validation/test_paper_portfolio_allocation_decision.py": 456,
    "tests/crypto_core/validation/test_paper_portfolio_governance_decision.py": 30,
    "tests/crypto_core/validation/test_paper_sleeve_correlation_evidence.py": 32,
    "tests/crypto_core/validation/test_paper_sleeve_daily_valuation_evidence.py": 8,
    "tests/crypto_core/validation/test_paper_sleeve_drawdown_evidence.py": 15,
    "tests/crypto_core/validation/test_paper_sleeve_performance_evidence.py": 8,
    "tests/crypto_core/validation/test_paper_sleeve_promotion_demotion_decision.py": 76,
    "tests/crypto_core/validation/test_paper_vs_backtest_methodology_v2.py": 5,
    "tests/crypto_core/validation/test_regime_conditioned_performance_evidence.py": 28,
    "tests/crypto_core/validation/test_regime_feature_series_evidence.py": 9,
    "tests/crypto_core/validation/test_regime_filter_admission_decision.py": 34,
    "tests/crypto_core/validation/test_regime_label_evidence.py": 7,
    "tests/crypto_core/validation/test_regime_stability_evidence.py": 14,
    "tests/crypto_core/validation/test_roughtime_v19_attested_operational_day_digest_binding.py": 112,
    "tests/crypto_core/validation/test_roughtime_v19_request_in_signed_response.py": 68,
    "tests/crypto_core/validation/test_roughtime_v19_signed_response_verification.py": 7,
    "tests/crypto_core/validation/test_strategy_executable_binding.py": 12,
}
DEFAULT_TEST_WEIGHT_MS = 10


def file_of(node_id: str) -> str:
    """The test file of a pytest node id (the rootdir-relative path before the first ``::``)."""
    return node_id.split("::", 1)[0]


def partition(node_ids: Sequence[str], shard_count: int) -> dict[str, int]:
    """Assign every file of ``node_ids`` to exactly one shard in ``1..shard_count``, as contiguous runs of files.

    Files keep their first-appearance (collection) order; shard ``k`` takes the files whose weight midpoint falls in
    the ``k``-th of ``shard_count`` equal parts of the total weight. Integer arithmetic keeps the result identical on
    every platform. A shard can only come out empty if one file outweighs a whole part; the aggregator then refuses
    the empty shard, so that can never pass silently.
    """
    if isinstance(shard_count, bool) or not isinstance(shard_count, int) or shard_count < 1:
        raise ValueError(f"shard_count must be a positive integer: {shard_count!r}")
    tests_per_file: dict[str, int] = {}
    for node_id in node_ids:
        path = file_of(node_id)
        tests_per_file[path] = tests_per_file.get(path, 0) + 1
    weights = {
        path: FILE_WEIGHTS[path] * 1000 if path in FILE_WEIGHTS else DEFAULT_TEST_WEIGHT_MS * count
        for path, count in tests_per_file.items()
    }
    total = sum(weights.values())
    assignment: dict[str, int] = {}
    before = 0
    for path, weight in weights.items():
        assignment[path] = min(shard_count, (2 * before + weight) * shard_count // (2 * total) + 1)
        before += weight
    return assignment


def parse_shard(spec: str) -> tuple[int, int]:
    """``"K/N"`` -> ``(K, N)`` with ``1 <= K <= N``."""
    shard_text, separator, count_text = spec.partition("/")
    if not separator or not shard_text.isdigit() or not count_text.isdigit():
        raise ValueError(f"--ci-shard must be K/N: {spec!r}")
    shard, count = int(shard_text), int(count_text)
    if not 1 <= shard <= count:
        raise ValueError(f"--ci-shard must satisfy 1 <= K <= N: {spec!r}")
    return shard, count


def canonical_args(invocation_args: Sequence[str]) -> list[str]:
    """The invocation without this plugin: drops ``-p PLUGIN`` and the ``--ci-shard*=`` options."""
    remaining: list[str] = []
    skip_next = False
    for index, arg in enumerate(invocation_args):
        if skip_next:
            skip_next = False
        elif arg == "-p" and index + 1 < len(invocation_args) and invocation_args[index + 1] == PLUGIN:
            skip_next = True
        elif not arg.startswith(_OWN_OPTIONS):
            remaining.append(arg)
    return remaining


def classify(phases: Sequence[tuple[str, str, bool]]) -> str:
    """One outcome per test from its (when, outcome, wasxfail) phase reports; ``incomplete`` if it never finished."""
    whens = {when for when, _, _ in phases}
    if any(outcome == "failed" for _, outcome, _ in phases):
        return "failed" if ("call", "failed") in {(when, outcome) for when, outcome, _ in phases} else "error"
    if "setup" not in whens or "teardown" not in whens:
        return "incomplete"
    skipped = [wasxfail for _, outcome, wasxfail in phases if outcome == "skipped"]
    if skipped:
        return "xfailed" if any(skipped) else "skipped"
    calls = [wasxfail for when, outcome, wasxfail in phases if when == "call" and outcome == "passed"]
    if calls:
        return "xpassed" if calls[0] else "passed"
    return "incomplete"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ShardRecorder:
    """Selects one shard's files and records what that shard actually collected, ran and measured."""

    def __init__(self, shard: int, shard_count: int, head: str, report_path: Path, invocation_args: Sequence[str]):
        self.shard = shard
        self.shard_count = shard_count
        self.head = head
        self.report_path = report_path
        self.invocation_args = list(invocation_args)
        self.collected: list[str] = []
        self.selected: list[str] = []
        self.phases: dict[str, list[tuple[str, str, bool]]] = {}
        self.file_seconds: dict[str, float] = {}

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config: pytest.Config, items: list[pytest.Item]) -> None:
        node_ids = [item.nodeid for item in items]
        assignment = partition(node_ids, self.shard_count)
        keep = [item for item in items if assignment[file_of(item.nodeid)] == self.shard]
        drop = [item for item in items if assignment[file_of(item.nodeid)] != self.shard]
        if drop:
            config.hook.pytest_deselected(items=drop)
        items[:] = keep
        self.collected = node_ids
        self.selected = [item.nodeid for item in keep]

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.phases.setdefault(report.nodeid, []).append((report.when, report.outcome, hasattr(report, "wasxfail")))
        path = file_of(report.nodeid)
        self.file_seconds[path] = self.file_seconds.get(path, 0.0) + report.duration

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        # pytest-cov saves its data when the test loop ends, before any sessionfinish hook runs.
        coverage_file = os.environ.get("COVERAGE_FILE", "")
        coverage_path = Path(coverage_file) if coverage_file else None
        report = {
            "schema": REPORT_SCHEMA,
            "shard": self.shard,
            "shard_count": self.shard_count,
            "head": self.head,
            "run_id": os.environ.get("GITHUB_RUN_ID", ""),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            "invocation_args": self.invocation_args,
            "pytest_addopts": os.environ.get("PYTEST_ADDOPTS", ""),
            "exit_status": int(exitstatus),
            "collected": self.collected,
            "selected": self.selected,
            "outcomes": {node_id: classify(phases) for node_id, phases in self.phases.items()},
            # Informational (balance diagnostics, weight refresh): the test time each file took inside this shard.
            "file_seconds": {path: round(seconds, 3) for path, seconds in self.file_seconds.items()},
            "coverage_sha256": sha256_file(coverage_path) if coverage_path and coverage_path.is_file() else None,
        }
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, indent=0) + "\n", encoding="utf-8", newline="\n")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("crypto_core_ci_shard", "crypto_core CI test sharding")
    group.addoption("--ci-shard", default=None, metavar="K/N", help="run only the test files of shard K of N")
    group.addoption("--ci-shard-head", default=None, help="the git commit under test (recorded in the report)")
    group.addoption("--ci-shard-report", default=None, help="where to write the shard report (JSON)")


def pytest_configure(config: pytest.Config) -> None:
    spec = config.getoption("ci_shard")
    if spec is None:
        return
    try:
        shard, shard_count = parse_shard(spec)
    except ValueError as error:
        raise pytest.UsageError(str(error)) from error
    head = config.getoption("ci_shard_head")
    report = config.getoption("ci_shard_report")
    if not head or not report:
        raise pytest.UsageError("--ci-shard needs --ci-shard-head and --ci-shard-report")
    recorder = ShardRecorder(shard, shard_count, head, Path(report), config.invocation_params.args)
    config.pluginmanager.register(recorder, "crypto_core_ci_shard_recorder")
