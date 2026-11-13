"""Pytest plugin for one crypto_core CI shard: run its whole-file share and seal attempt-bound evidence.

Loaded only by the ``test-shard`` jobs of ``.github/workflows/ci.yml``, exactly as
``python -m pytest <ci_shard_plan.shard_invocation(K, N)>``.  The shard collects the whole canonical suite,
keeps the whole test files that ``ci_shard_plan.assign_files`` gives shard K, runs them unchanged, and at session
end writes ``report.json`` and ``coverage.sqlite`` (a byte copy of pytest-cov's ``.coverage`` data file) into the
evidence directory, which must not exist beforehand.

The report binds the shard to the GitHub repository, workflow run and run attempt (``GITHUB_REPOSITORY``,
``GITHUB_RUN_ID``, ``GITHUB_RUN_ATTEMPT``), the checked-out commit and tree (which must equal ``GITHUB_SHA`` with
every tracked file unmodified), the interpreter version, its shard identity, the literal invocation and
environment, the complete collection, its selection, every selected test's outcome, pytest's exit status and the
SHA-256 of the coverage copy.  The plugin only records: whether the evidence is acceptable is decided by
``scripts/crypto_core/ci_attested_gate.py``, the required ``tests`` check.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts.crypto_core import ci_shard_plan as plan

_SHARD_SPEC = re.compile(r"([1-9][0-9]?)/([1-9][0-9]?)")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_POSITIVE_INT = re.compile(r"[1-9][0-9]{0,18}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_PLUGIN_NAME = "crypto_core_ci_shard_evidence"
_DUPLICATE = "#duplicate"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("crypto_core CI shard")
    group.addoption("--ci-shard", default=None, metavar="K/N", help="run shard K of N (whole test files)")
    group.addoption("--ci-evidence-dir", default=None, metavar="DIR", help="new directory for the shard evidence")


def pytest_configure(config: pytest.Config) -> None:
    config.pluginmanager.register(ShardEvidence.from_config(config), _PLUGIN_NAME)


def classify(phases: dict[str, tuple[str, bool]]) -> str:
    """One test's outcome from its ``(outcome, wasxfail)`` per reported phase, as pytest's summary counts it.

    Anything but a complete, single-report setup/call/teardown sequence is ``incomplete`` or ``error``.
    """
    if any(key.endswith(_DUPLICATE) for key in phases):
        return "error"
    setup, call, teardown = phases.get("setup"), phases.get("call"), phases.get("teardown")
    if setup is None or teardown is None:
        return "incomplete"
    if setup[0] == "failed" or teardown[0] != "passed":
        return "error"
    if setup[0] == "skipped":
        return "xfailed" if setup[1] else "skipped"
    if call is None:
        return "incomplete"
    if call[0] == "failed":
        return "failed"
    if call[0] == "skipped":
        return "xfailed" if call[1] else "skipped"
    return "xpassed" if call[1] else "passed"


def _git(root: Path, *args: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise pytest.UsageError("crypto_core CI shard: git is required to bind the shard to its checkout")
    completed = subprocess.run(  # noqa: S603 - fixed git argv, no shell, no caller-supplied executable
        [executable, *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace", check=False
    )
    if completed.returncode != 0:
        raise pytest.UsageError(f"crypto_core CI shard: git {' '.join(args)} failed: {completed.stderr.strip()[:300]}")
    return completed.stdout.strip()


def _github_context(environ: Mapping[str, str]) -> tuple[str, int, int, str]:
    repository = environ.get("GITHUB_REPOSITORY", "")
    run_id = environ.get("GITHUB_RUN_ID", "")
    run_attempt = environ.get("GITHUB_RUN_ATTEMPT", "")
    sha = environ.get("GITHUB_SHA", "")
    invalid = [
        name
        for name, value, pattern in (
            ("GITHUB_REPOSITORY", repository, _REPOSITORY),
            ("GITHUB_RUN_ID", run_id, _POSITIVE_INT),
            ("GITHUB_RUN_ATTEMPT", run_attempt, _POSITIVE_INT),
            ("GITHUB_SHA", sha, _COMMIT),
        )
        if pattern.fullmatch(value) is None
    ]
    if invalid:
        raise pytest.UsageError(
            "crypto_core CI shard: the GitHub Actions run context is missing or malformed: " + ", ".join(invalid)
        )
    return repository, int(run_id), int(run_attempt), sha


class ShardEvidence:
    """Selects shard ``index`` of ``count`` and records the evidence that the gate verifies."""

    def __init__(
        self,
        *,
        index: int,
        count: int,
        root: Path,
        evidence_dir: Path,
        repository: str,
        run_id: int,
        run_attempt: int,
        head: str,
        tree: str,
        environment: dict[str, str | None],
    ) -> None:
        self.index = index
        self.count = count
        self.root = root
        self.evidence_dir = evidence_dir
        self.repository = repository
        self.run_id = run_id
        self.run_attempt = run_attempt
        self.head = head
        self.tree = tree
        self.environment = environment
        self.started_at = time.time()
        self.invocation: list[str] = []
        self.collection: list[str] = []
        self.selected: list[str] = []
        self.phases: dict[str, dict[str, tuple[str, bool]]] = {}

    @classmethod
    def from_config(cls, config: pytest.Config) -> ShardEvidence:
        spec = config.getoption("--ci-shard")
        evidence = config.getoption("--ci-evidence-dir")
        if spec is None or evidence is None:
            raise pytest.UsageError("crypto_core CI shard: --ci-shard=K/N and --ci-evidence-dir=DIR are both required")
        match = _SHARD_SPEC.fullmatch(spec)
        if match is None or not int(match.group(1)) <= int(match.group(2)) <= plan.MAX_SHARDS:
            raise pytest.UsageError(
                f"crypto_core CI shard: --ci-shard must be K/N with 1 <= K <= N <= {plan.MAX_SHARDS}, got {spec!r}"
            )
        root = Path(config.invocation_params.dir).resolve()
        evidence_dir = root / evidence
        if evidence_dir.exists() or evidence_dir.is_symlink():
            raise pytest.UsageError(f"crypto_core CI shard: evidence directory {evidence_dir} already exists")
        repository, run_id, run_attempt, sha = _github_context(os.environ)
        head = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
        tree = _git(root, "rev-parse", "--verify", "HEAD^{tree}")
        if head != sha:
            raise pytest.UsageError(f"crypto_core CI shard: checked-out HEAD {head} is not GITHUB_SHA {sha}")
        if _git(root, "status", "--porcelain", "--untracked-files=no"):
            raise pytest.UsageError("crypto_core CI shard: tracked files differ from the checked-out commit")
        shard = cls(
            index=int(match.group(1)),
            count=int(match.group(2)),
            root=root,
            evidence_dir=evidence_dir,
            repository=repository,
            run_id=run_id,
            run_attempt=run_attempt,
            head=head,
            tree=tree,
            environment={name: os.environ.get(name) for name in plan.CANONICAL_ENVIRONMENT},
        )
        shard.invocation = list(config.invocation_params.args)
        return shard

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, session: pytest.Session, config: pytest.Config, items: list) -> None:
        # trylast: record the collection exactly as every other plugin and conftest left it, then deselect.
        self.collection = [item.nodeid for item in items]
        if not items:
            return
        assignment = plan.assign_files(plan.files_in_order(self.collection), self.count)
        keep = [item for item in items if assignment[plan.node_file(item.nodeid)] == self.index]
        drop = [item for item in items if assignment[plan.node_file(item.nodeid)] != self.index]
        if drop:
            config.hook.pytest_deselected(items=drop)
        items[:] = keep
        self.selected = [item.nodeid for item in keep]

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        phases = self.phases.setdefault(report.nodeid, {})
        key = report.when if report.when not in phases else report.when + _DUPLICATE
        phases[key] = (report.outcome, hasattr(report, "wasxfail"))

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        try:
            self._seal(int(exitstatus))
        except (OSError, RuntimeError) as error:
            if reporter is not None:
                reporter.write_line(f"crypto_core CI shard: evidence NOT sealed: {error}", red=True)
            session.exitstatus = pytest.ExitCode.INTERNAL_ERROR
            return
        if reporter is not None:
            reporter.write_line(
                f"crypto_core CI shard {self.index}/{self.count}: {len(self.selected)} of {len(self.collection)} "
                f"collected tests selected; evidence sealed in {self.evidence_dir}"
            )

    def _seal(self, exitstatus: int) -> None:
        source = self.root / ".coverage"
        if not source.is_file() or source.stat().st_mtime < self.started_at:
            raise RuntimeError(f"pytest-cov did not write {source} in this session (--cov={plan.SOURCE_DIR} missing?)")
        self.evidence_dir.mkdir(parents=True)
        coverage_copy = self.evidence_dir / plan.COVERAGE_FILE
        shutil.copyfile(source, coverage_copy)
        outcomes = {nodeid: classify(self.phases.get(nodeid, {})) for nodeid in self.selected}
        for nodeid, phases in self.phases.items():
            outcomes.setdefault(nodeid, classify(phases))  # a report for an unselected test: the gate rejects it
        report = {
            "schema": plan.SCHEMA,
            "repository": self.repository,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "head": self.head,
            "tree": self.tree,
            "root": str(self.root),
            "python": platform.python_version(),
            "shard_index": self.index,
            "shard_count": self.count,
            "invocation": self.invocation,
            "environment": self.environment,
            "collection": self.collection,
            "selected": self.selected,
            "outcomes": outcomes,
            "exitstatus": exitstatus,
            "coverage_sha256": hashlib.sha256(coverage_copy.read_bytes()).hexdigest(),
        }
        text = json.dumps(report, ensure_ascii=True, separators=(",", ":")) + "\n"
        (self.evidence_dir / plan.REPORT_FILE).write_bytes(text.encode("ascii"))
