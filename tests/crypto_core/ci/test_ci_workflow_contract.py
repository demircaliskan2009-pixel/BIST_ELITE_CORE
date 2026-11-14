"""``.github/workflows/ci.yml`` keeps the required checks, their evidence boundary and CodeQL exactly as intended.

The required contexts are ``tests`` (the attested gate), ``codeql`` (this workflow's CodeQL job) and the
repository's ``CodeQL`` code-scanning check.  A change that weakens one of them, or lets the shard invocation,
artifact names or producer job names drift from ``scripts/crypto_core/ci_shard_plan.py``, fails here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.crypto_core import ci_attested_gate as gate
from scripts.crypto_core import ci_shard_plan as plan

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ci.yml"
MATRIX_SHARD = "${{ matrix.shard }}"
SHARD_COUNT = 3
JOB_ENV = {"PYTHONPATH": "${{ github.workspace }}/src", "PYTHONWARNINGS": "error", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
INSTALL = (
    "set -euo pipefail\n"
    "python -m pip install --upgrade pip\n"
    "if [ -f requirements-dev.txt ]; then\n"
    "  python -m pip install -r requirements-dev.txt\n"
    "elif [ -f requirements.txt ]; then\n"
    "  python -m pip install -r requirements.txt pytest\n"
    "else\n"
    "  python -m pip install pytest\n"
    "fi\n"
    "python -m pip install pytest-cov ruff\n"
)
SETUP_PYTHON = {
    "python-version": "3.11",
    "cache": "pip",
    "cache-dependency-path": "requirements.txt\nrequirements-dev.txt\npyproject.toml\n",
}
EVIDENCE_PATH = "${{ runner.temp }}/ci-shard-evidence"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_bytes().decode("utf-8"))


def steps_by_name(job: dict) -> dict[str, dict]:
    steps = {step["name"]: step for step in job["steps"]}
    assert len(steps) == len(job["steps"]), "step names must be unique"
    return steps


def assert_standard_setup(job: dict) -> None:
    steps = steps_by_name(job)
    assert steps["Checkout"] == {"name": "Checkout", "uses": "actions/checkout@v4"}
    assert steps["Setup Python"] == {"name": "Setup Python", "uses": "actions/setup-python@v5", "with": SETUP_PYTHON}
    assert steps["Install dependencies"] == {"name": "Install dependencies", "run": INSTALL}
    assert job["env"] == JOB_ENV
    assert job["runs-on"] == "ubuntu-latest"


def test_triggers_jobs_and_workflow_permissions(workflow: dict):
    triggers = workflow.get("on", workflow.get(True))  # YAML 1.1 reads the bare key `on` as True
    assert triggers == {
        "push": {"branches": ["main"]},
        "pull_request": {"branches": ["main"]},
        "schedule": [{"cron": "0 2 * * 0"}],
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"lint", "test-shard", "tests", "slow-tests", "codeql"}
    for name, job in workflow["jobs"].items():
        assert "continue-on-error" not in job, name
        assert all("continue-on-error" not in step for step in job["steps"]), name


def test_the_required_tests_check_is_an_always_running_attested_gate(workflow: dict):
    tests = workflow["jobs"]["tests"]
    assert tests["name"] == "tests"
    assert tests["needs"] == ["lint", "test-shard"]
    assert tests["if"] == "${{ always() }}", "a skipped required job would report success"
    assert tests["permissions"] == {"actions": "read", "contents": "read"}
    assert_standard_setup(tests)
    steps = steps_by_name(tests)
    assert list(steps) == [
        "Checkout",
        "Setup Python",
        "Install dependencies",
        "Download shard evidence of this run attempt",
        "Verify attested shard evidence and the coverage floor",
    ]
    assert all("if" not in step for step in tests["steps"]), "every gate step runs only after the previous succeeded"
    download = steps["Download shard evidence of this run attempt"]
    assert download["uses"] == "actions/download-artifact@v4"
    assert download["with"] == {
        "pattern": "crypto-core-pytest-run-${{ github.run_id }}-attempt-${{ github.run_attempt }}-shard-*",
        "path": EVIDENCE_PATH,
    }
    verify = steps["Verify attested shard evidence and the coverage floor"]
    assert verify["env"] == {
        gate.NEEDS_ENV: "${{ toJSON(needs) }}",
        gate.RUN_HEAD_ENV: "${{ github.event.pull_request.head.sha || github.sha }}",
        gate.CREDENTIAL_ENV: "${{ github.token }}",
    }
    assert verify["run"] == (
        "set -euo pipefail\npython -m scripts.crypto_core.ci_attested_gate "
        f'--evidence-dir "{EVIDENCE_PATH}" --shards {SHARD_COUNT} --fail-under 70\n'
    )


def test_every_shard_runs_the_canonical_invocation_and_uploads_attempt_bound_evidence(workflow: dict):
    shard = workflow["jobs"]["test-shard"]
    assert shard["name"] == plan.shard_job_name(MATRIX_SHARD, SHARD_COUNT)  # the producer identity the gate attests
    assert shard["strategy"] == {"fail-fast": False, "matrix": {"shard": list(range(1, SHARD_COUNT + 1))}}
    assert shard["timeout-minutes"] == 120
    assert "if" not in shard and "needs" not in shard
    assert_standard_setup(shard)
    steps = steps_by_name(shard)
    assert list(steps) == [
        "Checkout",
        "Setup Python",
        "Install dependencies",
        "Run pytest shard with coverage",
        "Upload shard evidence of this run attempt",
    ]
    invocation = " ".join(plan.shard_invocation(MATRIX_SHARD, SHARD_COUNT))
    assert steps["Run pytest shard with coverage"]["run"] == f"set -euo pipefail\npython -m pytest {invocation}\n"
    upload = steps["Upload shard evidence of this run attempt"]
    assert "if" not in upload, "evidence is uploaded only after the pytest step succeeded"
    assert upload["uses"] == "actions/upload-artifact@v4"
    assert upload["with"] == {
        "name": plan.artifact_name("${{ github.run_id }}", "${{ github.run_attempt }}", MATRIX_SHARD, SHARD_COUNT),
        "path": f"{plan.EVIDENCE_DIR}/",
        "if-no-files-found": "error",
        "retention-days": 30,
    }


def test_lint_keeps_both_ruff_gates_on_the_crypto_core_scope(workflow: dict):
    lint = workflow["jobs"]["lint"]
    assert lint["name"] == plan.LINT_JOB
    assert_standard_setup(lint)
    steps = steps_by_name(lint)
    assert list(steps) == ["Checkout", "Setup Python", "Install dependencies", "Ruff lint", "Ruff format check"]
    scope = "src/crypto_core tests/crypto_core scripts/crypto_core"
    assert steps["Ruff lint"]["run"] == f"ruff check {scope} --output-format=github"
    assert steps["Ruff format check"]["run"] == f"ruff format --check {scope}"


def test_codeql_runs_in_parallel_with_its_configuration_unchanged(workflow: dict):
    codeql = workflow["jobs"]["codeql"]
    assert "needs" not in codeql and "if" not in codeql, "CodeQL needs no pytest output and is never skipped"
    assert codeql["name"] == "codeql"
    assert codeql["runs-on"] == "ubuntu-latest"
    assert codeql["timeout-minutes"] == 30
    assert codeql["permissions"] == {"actions": "read", "contents": "read", "security-events": "write"}
    assert codeql["steps"] == [
        {"name": "Checkout", "uses": "actions/checkout@v4"},
        {
            "name": "Initialize CodeQL",
            "uses": "github/codeql-action/init@v4",
            "with": {"languages": "python", "build-mode": "none", "queries": "security-and-quality"},
        },
        {
            "name": "Perform CodeQL Analysis",
            "uses": "github/codeql-action/analyze@v4",
            "with": {"category": "/language:python"},
        },
    ]


def test_the_weekly_slow_suite_is_unchanged(workflow: dict):
    slow = workflow["jobs"]["slow-tests"]
    assert slow["if"] == "github.event_name == 'schedule'"
    assert slow["timeout-minutes"] == 60
    assert_standard_setup(slow)
    assert steps_by_name(slow)["Run full suite including slow tests"]["run"] == (
        "set -euo pipefail\npython -m pytest -q --runslow --cov=src/crypto_core --cov-report=term --cov-fail-under=70\n"
    )
