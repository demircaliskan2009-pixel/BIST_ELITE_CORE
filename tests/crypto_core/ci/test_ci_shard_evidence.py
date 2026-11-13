"""crypto_core CI shards: the whole-file plan and the attempt-bound evidence every shard seals.

The plan tests are pure.  The plugin tests run real pytest shards, with the exact CI invocation, in a throwaway git
project that has the canonical layout (``src/crypto_core``, ``tests/crypto_core``) and byte copies of the real CI
scripts.  The project helpers here are shared with ``test_ci_attested_gate``.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from coverage import CoverageData

from scripts.crypto_core import ci_shard_evidence as shard_evidence
from scripts.crypto_core import ci_shard_plan as plan

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_SCRIPTS = ("ci_shard_plan.py", "ci_shard_evidence.py", "ci_attested_gate.py")
FIXTURE_REPOSITORY = "crypto-core/ci-fixture"
REPORT_FIELDS = set(
    "schema repository run_id run_attempt head tree root python shard_index shard_count invocation environment "
    "collection selected outcomes exitstatus coverage_sha256".split()
)
USAGE_ERROR = int(pytest.ExitCode.USAGE_ERROR)

# The serial gate's pytest arguments before the shards replaced it (main f1de3edf, .github/workflows/ci.yml).
SERIAL_GATE_ARGS = [
    "-q",
    "-W",
    "error",
    "--cov=src/crypto_core",
    "--cov-report=term",
    "--cov-fail-under=70",
    "tests/crypto_core",
]

FIXTURE_FILES = {
    "pytest.ini": "[pytest]\npythonpath = src .\ntestpaths = tests\n",
    "src/crypto_core/__init__.py": "",
    "src/crypto_core/alpha.py": (
        "def double(value):\n    return value * 2\n\n\n"
        "def parity(value):\n    if value % 2:\n        return 'odd'\n    return 'even'\n"
    ),
    "src/crypto_core/beta.py": (
        "def clamp(value, low, high):\n    if value < low:\n        return low\n"
        "    if value > high:\n        return high\n    return value\n"
    ),
    "src/crypto_core/gamma.py": (
        "def describe(items):\n    if not items:\n        return 'empty'\n    return ','.join(sorted(items))\n"
    ),
    "src/crypto_core/idle.py": "def unused():\n    return None\n",
    "tests/crypto_core/test_a_alpha.py": (
        "from crypto_core import alpha\n\n\n"
        "def test_double():\n    assert alpha.double(2) == 4\n\n\n"
        "def test_odd():\n    assert alpha.parity(3) == 'odd'\n\n\n"
        "def test_even():\n    assert alpha.parity(4) == 'even'\n"
    ),
    "tests/crypto_core/test_b_beta.py": (
        "import pytest\n\nfrom crypto_core import beta\n\n\n"
        "@pytest.mark.parametrize(('value', 'expected'), [(-1, 0), (11, 10), (5, 5)], ids=['low', 'high', 'mid'])\n"
        "def test_clamp(value, expected):\n    assert beta.clamp(value, 0, 10) == expected\n"
    ),
    "tests/crypto_core/test_c_gamma.py": (
        "import pytest\n\nfrom crypto_core import gamma\n\n\n"
        "def test_empty():\n    assert gamma.describe([]) == 'empty'\n\n\n"
        "def test_items():\n    assert gamma.describe(['b', 'a']) == 'a,b'\n\n\n"
        "@pytest.mark.skip(reason='fixture: a legitimate skip')\n"
        "def test_skipped():\n    raise AssertionError('never runs')\n"
    ),
    "tests/crypto_core/test_d_outcomes.py": (
        "import pytest\n\nfrom crypto_core import alpha\n\n\n"
        "def test_passes():\n    assert alpha.double(1) == 2\n\n\n"
        "@pytest.mark.xfail(reason='fixture: an expected failure', strict=False)\n"
        "def test_expected_failure():\n    assert alpha.double(1) == 3\n\n\n"
        "@pytest.mark.xfail(reason='fixture: an unexpected pass', strict=False)\n"
        "def test_unexpected_pass():\n    assert alpha.double(1) == 2\n"
    ),
}

# Planned with the default per-test weight (no fixture file is a measured crypto_core file): a | b c | d.
FIXTURE_SHARES = {
    1: ["test_a_alpha.py"],
    2: ["test_b_beta.py", "test_c_gamma.py"],
    3: ["test_d_outcomes.py"],
}
FIXTURE_OUTCOMES = {
    "tests/crypto_core/test_a_alpha.py::test_double": "passed",
    "tests/crypto_core/test_a_alpha.py::test_odd": "passed",
    "tests/crypto_core/test_a_alpha.py::test_even": "passed",
    "tests/crypto_core/test_b_beta.py::test_clamp[low]": "passed",
    "tests/crypto_core/test_b_beta.py::test_clamp[high]": "passed",
    "tests/crypto_core/test_b_beta.py::test_clamp[mid]": "passed",
    "tests/crypto_core/test_c_gamma.py::test_empty": "passed",
    "tests/crypto_core/test_c_gamma.py::test_items": "passed",
    "tests/crypto_core/test_c_gamma.py::test_skipped": "skipped",
    "tests/crypto_core/test_d_outcomes.py::test_passes": "passed",
    "tests/crypto_core/test_d_outcomes.py::test_expected_failure": "xfailed",
    "tests/crypto_core/test_d_outcomes.py::test_unexpected_pass": "xpassed",
}


def _git_executable() -> str:
    executable = shutil.which("git")
    assert executable is not None, "git is required by the CI shard tests"
    return executable


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git argv in a throwaway test project, no shell
        [_git_executable(), *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace", check=False
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def make_project(root: Path, files: dict[str, str] | None = None) -> str:
    """Create a committed git project with the canonical layout and the real CI scripts; return its HEAD."""
    for relative, text in {**FIXTURE_FILES, **(files or {})}.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    (root / "scripts" / "crypto_core").mkdir(parents=True, exist_ok=True)
    for name in CI_SCRIPTS:
        shutil.copyfile(REPO_ROOT / "scripts" / "crypto_core" / name, root / "scripts" / "crypto_core" / name)
    git(root, "init", "-q")
    git(root, "config", "core.autocrlf", "false")
    git(root, "add", "-A")
    git(root, "-c", "user.name=ci-fixture", "-c", "user.email=ci-fixture@example.invalid", "commit", "-q", "-m", "x")
    return git(root, "rev-parse", "HEAD")


def shard_env(head: str, run_id: int, run_attempt: int, **overrides: str | None) -> dict[str, str]:
    """A child environment like a GitHub Actions shard job's, without the parent's pytest or coverage settings."""
    dropped = ("PYTEST_", "COVERAGE_", "GITHUB_", "CRYPTO_CORE_CI_")
    env = {name: value for name, value in os.environ.items() if not name.startswith(dropped) and name != "PYTHONPATH"}
    env.update(
        {
            "PYTHONWARNINGS": "error",
            "GITHUB_REPOSITORY": FIXTURE_REPOSITORY,
            "GITHUB_RUN_ID": str(run_id),
            "GITHUB_RUN_ATTEMPT": str(run_attempt),
            "GITHUB_SHA": head,
        }
    )
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env


def run_pytest(root: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - this interpreter running pytest in a throwaway project, no shell
        [sys.executable, "-m", "pytest", *args],
        cwd=root,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )


def seal_shards(root: Path, head: str, run_id: int, run_attempt: int, store: Path, count: int = 3) -> dict[int, Path]:
    """Run every shard with the exact CI invocation and keep each sealed evidence directory under ``store``."""
    sealed = {}
    for index in range(1, count + 1):
        completed = run_pytest(root, plan.shard_invocation(index, count), shard_env(head, run_id, run_attempt))
        assert completed.returncode == 0, completed.stdout + completed.stderr
        target = store / f"attempt-{run_attempt}" / f"shard-{index}"
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(root / plan.EVIDENCE_DIR, target)
        sealed[index] = target
    return sealed


def read_report(evidence: Path) -> dict:
    return json.loads((evidence / plan.REPORT_FILE).read_bytes().decode("utf-8"))


@pytest.fixture(scope="module")
def sealed_project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, dict[int, Path]]:
    root = tmp_path_factory.mktemp("shard_project")
    head = make_project(root)
    return root, head, seal_shards(root, head, 4242, 3, tmp_path_factory.mktemp("shard_store"))


# --- the plan --------------------------------------------------------------------------------------------------


def _random_collection(rng: random.Random) -> list[str]:
    files = [f"tests/crypto_core/pkg{rng.randrange(4)}/test_case_{index:03d}.py" for index in range(rng.randint(1, 40))]
    return [f"{path}::test_{number}" for path in files for number in range(rng.randint(1, 30))]


def test_every_file_lands_whole_in_exactly_one_shard_and_shards_are_contiguous(monkeypatch: pytest.MonkeyPatch):
    rng = random.Random(20261113)  # noqa: S311 - seeded, reproducible test data, not cryptography
    for _ in range(150):
        nodeids = _random_collection(rng)
        files = plan.files_in_order(nodeids)
        for path, _ in files:
            if rng.random() < 0.2:
                monkeypatch.setitem(plan.FILE_WEIGHT_MS, path, rng.randint(1_000, 900_000))
        for count in range(1, 7):
            assignment = plan.assign_files(files, count)
            order = [assignment[path] for path, _ in files]
            assert set(assignment) == {path for path, _ in files}
            assert all(1 <= shard <= count for shard in order)
            assert order == sorted(order), "a shard must be one contiguous run of files"
            shares = plan.plan_selection(nodeids, count)
            assert sorted(nodeid for share in shares.values() for nodeid in share) == sorted(nodeids)
            for shard, share in shares.items():
                assert all(assignment[plan.node_file(nodeid)] == shard for nodeid in share)
        monkeypatch.undo()


def test_the_plan_ignores_order_inside_a_file_and_is_deterministic():
    rng = random.Random(7)  # noqa: S311 - seeded, reproducible test data, not cryptography
    nodeids = _random_collection(rng)
    files = [path for path, _ in plan.files_in_order(nodeids)]
    shuffled = []
    for path in files:
        group = [nodeid for nodeid in nodeids if plan.node_file(nodeid) == path]
        rng.shuffle(group)
        shuffled.extend(group)
    for count in (1, 2, 3, 4):
        reference = {shard: set(share) for shard, share in plan.plan_selection(nodeids, count).items()}
        assert {shard: set(share) for shard, share in plan.plan_selection(shuffled, count).items()} == reference


def test_shards_are_balanced_and_non_empty_when_no_file_outweighs_a_share():
    rng = random.Random(11)  # noqa: S311 - seeded, reproducible test data, not cryptography
    for _ in range(100):
        files = [(f"tests/crypto_core/test_w{index}.py", rng.randint(1, 400)) for index in range(rng.randint(3, 60))]
        weights = {path: plan.file_weight(path, tests) for path, tests in files}
        total, heaviest = sum(weights.values()), max(weights.values())
        for count in range(1, 6):
            assignment = plan.assign_files(files, count)
            loads = [
                sum(weight for path, weight in weights.items() if assignment[path] == shard)
                for shard in range(1, count + 1)
            ]
            assert max(loads) * count <= total + heaviest * count, "a shard exceeds its share by more than one file"
            if heaviest * count <= total:
                assert all(loads), "a shard is empty although every file fits in one share"


def test_measured_weights_name_crypto_core_test_files_and_new_files_use_the_default():
    assert plan.FILE_WEIGHT_MS, "the measured weights are missing"
    assert list(plan.FILE_WEIGHT_MS) == sorted(plan.FILE_WEIGHT_MS)
    for path, weight in plan.FILE_WEIGHT_MS.items():
        assert path.startswith("tests/crypto_core/") and Path(path).name.startswith("test_") and path.endswith(".py")
        assert type(weight) is int and weight >= 1_000
    assert plan.DEFAULT_MS_PER_TEST >= 1
    unlisted = "tests/crypto_core/test_added_after_the_measurement.py"
    assert unlisted not in plan.FILE_WEIGHT_MS
    assert plan.file_weight(unlisted, 7) == 7 * plan.DEFAULT_MS_PER_TEST
    collection = [
        "tests/crypto_core/test_one.py::test_a",
        f"{unlisted}::test_new",
        "tests/crypto_core/test_two.py::test_b",
    ]
    for count in (1, 2, 3):
        shares = plan.plan_selection(collection, count)
        assert sum(nodeid == f"{unlisted}::test_new" for share in shares.values() for nodeid in share) == 1


@pytest.mark.parametrize(
    ("files", "count"),
    [
        ([("tests/crypto_core/test_a.py", 1)], 0),
        ([("tests/crypto_core/test_a.py", 1)], plan.MAX_SHARDS + 1),
        ([], 3),
        ([("tests/crypto_core/test_a.py", 1), ("tests/crypto_core/test_a.py", 2)], 2),
    ],
    ids=["zero-shards", "too-many-shards", "empty-collection", "duplicate-file"],
)
def test_the_plan_refuses_invalid_input(files: list[tuple[str, int]], count: int):
    with pytest.raises(ValueError):
        plan.assign_files(files, count)


def test_a_shard_runs_the_serial_gates_selection_and_leaves_the_floor_to_the_gate():
    invocation = plan.shard_invocation(2, 3)
    plugin_args = ["-p", plan.PLUGIN_MODULE, "--ci-shard=2/3", f"--ci-evidence-dir={plan.EVIDENCE_DIR}"]
    assert invocation[: len(plugin_args)] == plugin_args
    serial_without_report_and_floor = [
        "--cov-report=" if arg == "--cov-report=term" else arg
        for arg in SERIAL_GATE_ARGS
        if arg != "--cov-fail-under=70"
    ]
    assert invocation[len(plugin_args) :] == serial_without_report_and_floor
    assert plan.artifact_name(43, 2, 1, 3) == "crypto-core-pytest-run-43-attempt-2-shard-1-of-3"
    assert plan.shard_job_name(1, 3) == "pytest shard 1 of 3"


# --- outcome classification ------------------------------------------------------------------------------------

PASSED, FAILED, SKIPPED = ("passed", False), ("failed", False), ("skipped", False)


@pytest.mark.parametrize(
    ("phases", "expected"),
    [
        ({"setup": PASSED, "call": PASSED, "teardown": PASSED}, "passed"),
        ({"setup": PASSED, "call": FAILED, "teardown": PASSED}, "failed"),
        ({"setup": SKIPPED, "teardown": PASSED}, "skipped"),
        ({"setup": ("skipped", True), "teardown": PASSED}, "xfailed"),
        ({"setup": PASSED, "call": ("skipped", True), "teardown": PASSED}, "xfailed"),
        ({"setup": PASSED, "call": ("passed", True), "teardown": PASSED}, "xpassed"),
        ({"setup": PASSED, "call": SKIPPED, "teardown": PASSED}, "skipped"),
        ({"setup": FAILED, "teardown": PASSED}, "error"),
        ({"setup": PASSED, "call": PASSED, "teardown": FAILED}, "error"),
        ({"setup": PASSED, "call": PASSED, "teardown": SKIPPED}, "error"),
        ({"setup": PASSED, "call": PASSED}, "incomplete"),
        ({"setup": PASSED, "teardown": PASSED}, "incomplete"),
        ({}, "incomplete"),
        ({"setup": PASSED, "call": PASSED, "call#duplicate": PASSED, "teardown": PASSED}, "error"),
    ],
    ids=[
        "passed",
        "failed",
        "skipped",
        "xfail-in-setup",
        "xfailed",
        "xpassed",
        "skip-in-call",
        "setup-error",
        "teardown-error",
        "teardown-skip",
        "no-teardown",
        "no-call",
        "never-ran",
        "duplicate-report",
    ],
)
def test_outcomes_are_classified_as_pytest_counts_them(phases: dict[str, tuple[str, bool]], expected: str):
    assert shard_evidence.classify(phases) == expected


# --- real shards ---------------------------------------------------------------------------------------------


def test_real_shards_seal_complete_disjoint_evidence_bound_to_run_attempt_commit_and_shard(sealed_project):
    root, head, sealed = sealed_project
    tree = git(root, "rev-parse", "HEAD^{tree}")
    reports = {index: read_report(path) for index, path in sealed.items()}
    collection = reports[1]["collection"]
    assert sorted(collection) == sorted(FIXTURE_OUTCOMES)
    assert all(plan.node_file(nodeid) not in plan.FILE_WEIGHT_MS for nodeid in collection), "fixture files are new"
    union: list[str] = []
    for index, report in reports.items():
        assert set(report) == REPORT_FIELDS
        assert report["schema"] == plan.SCHEMA
        assert (report["repository"], report["run_id"], report["run_attempt"]) == (FIXTURE_REPOSITORY, 4242, 3)
        assert (report["head"], report["tree"], report["root"]) == (head, tree, str(root.resolve()))
        assert (report["shard_index"], report["shard_count"]) == (index, 3)
        assert report["invocation"] == plan.shard_invocation(index, 3)
        assert report["environment"] == plan.CANONICAL_ENVIRONMENT
        assert report["python"].split(".")[:2] == [str(sys.version_info[0]), str(sys.version_info[1])]
        assert report["collection"] == collection, "every shard collects the whole suite"
        assert sorted({Path(plan.node_file(nodeid)).name for nodeid in report["selected"]}) == FIXTURE_SHARES[index]
        assert report["outcomes"] == {nodeid: FIXTURE_OUTCOMES[nodeid] for nodeid in report["selected"]}
        assert report["exitstatus"] == 0
        coverage_file = sealed[index] / plan.COVERAGE_FILE
        assert report["coverage_sha256"] == hashlib.sha256(coverage_file.read_bytes()).hexdigest()
        assert sorted(path.name for path in sealed[index].iterdir()) == [plan.COVERAGE_FILE, plan.REPORT_FILE]
        data = CoverageData(basename=str(coverage_file))
        data.read()
        try:
            assert not data.has_arcs()
            source = os.path.normcase(str(root.resolve() / "src" / "crypto_core"))
            assert all(os.path.normcase(name).startswith(source) for name in data.measured_files())
            assert any(Path(name).name == "idle.py" for name in data.measured_files()), "unexecuted files count"
        finally:
            data.close()
        union.extend(report["selected"])
    assert sorted(union) == sorted(collection), "the shards' selections are disjoint and complete"


def test_a_failing_shard_records_every_non_passing_outcome_and_exits_nonzero(tmp_path: Path):
    files = {
        "tests/crypto_core/test_e_broken.py": (
            "import pytest\n\nfrom crypto_core import alpha\n\n\n"
            "@pytest.fixture\ndef broken_setup():\n    raise RuntimeError('setup fails')\n\n\n"
            "@pytest.fixture\ndef broken_teardown():\n    yield\n    raise RuntimeError('teardown fails')\n\n\n"
            "def test_fails():\n    assert alpha.double(2) == 5\n\n\n"
            "def test_setup_error(broken_setup):\n    assert broken_setup is None\n\n\n"
            "def test_teardown_error(broken_teardown):\n    assert broken_teardown is None\n"
        )
    }
    head = make_project(tmp_path, files)
    completed = run_pytest(tmp_path, plan.shard_invocation(1, 1), shard_env(head, 9, 1))
    assert completed.returncode == int(pytest.ExitCode.TESTS_FAILED), completed.stdout + completed.stderr
    report = read_report(tmp_path / plan.EVIDENCE_DIR)
    assert report["exitstatus"] == int(pytest.ExitCode.TESTS_FAILED)
    broken = {nodeid.split("::")[1]: outcome for nodeid, outcome in report["outcomes"].items() if "broken" in nodeid}
    assert broken == {"test_fails": "failed", "test_setup_error": "error", "test_teardown_error": "error"}


@pytest.mark.parametrize(
    ("overrides", "marker"),
    [
        ({"GITHUB_RUN_ATTEMPT": None}, "GITHUB_RUN_ATTEMPT"),
        ({"GITHUB_RUN_ATTEMPT": "0"}, "GITHUB_RUN_ATTEMPT"),
        ({"GITHUB_RUN_ID": "run-1"}, "GITHUB_RUN_ID"),
        ({"GITHUB_REPOSITORY": None}, "GITHUB_REPOSITORY"),
        ({"GITHUB_SHA": "0" * 40}, "is not GITHUB_SHA"),
    ],
    ids=["no-attempt", "attempt-zero", "malformed-run-id", "no-repository", "foreign-commit"],
)
def test_a_shard_refuses_to_run_outside_its_exact_github_run_attempt_and_commit(
    sealed_project, tmp_path: Path, overrides: dict[str, str | None], marker: str
):
    root, head, _ = sealed_project
    args = plan.shard_invocation(1, 3)
    args[3] = f"--ci-evidence-dir={tmp_path / 'evidence'}"
    completed = run_pytest(root, args, shard_env(head, 4242, 3, **overrides))
    assert completed.returncode == USAGE_ERROR
    assert marker in completed.stderr
    assert not (tmp_path / "evidence").exists()


def test_a_shard_refuses_modified_tracked_files(tmp_path: Path):
    head = make_project(tmp_path)
    test_file = tmp_path / "tests" / "crypto_core" / "test_a_alpha.py"
    test_file.write_bytes(test_file.read_bytes() + b"\n\ndef test_added_after_checkout():\n    assert True\n")
    completed = run_pytest(tmp_path, plan.shard_invocation(1, 3), shard_env(head, 1, 1))
    assert completed.returncode == USAGE_ERROR
    assert "tracked files differ" in completed.stderr
    assert not (tmp_path / plan.EVIDENCE_DIR).exists()


@pytest.mark.parametrize(
    ("args", "marker"),
    [
        (["-p", plan.PLUGIN_MODULE, "-q", "tests/crypto_core"], "are both required"),
        (["-p", plan.PLUGIN_MODULE, "--ci-shard=1/3", "-q", "tests/crypto_core"], "are both required"),
        (["-p", plan.PLUGIN_MODULE, "--ci-shard=0/3", "--ci-evidence-dir=fresh", "tests/crypto_core"], "K/N"),
        (["-p", plan.PLUGIN_MODULE, "--ci-shard=4/3", "--ci-evidence-dir=fresh", "tests/crypto_core"], "K/N"),
        (["-p", plan.PLUGIN_MODULE, "--ci-shard=1/17", "--ci-evidence-dir=fresh", "tests/crypto_core"], "K/N"),
        (["-p", plan.PLUGIN_MODULE, "--ci-shard=one/3", "--ci-evidence-dir=fresh", "tests/crypto_core"], "K/N"),
        (["-p", plan.PLUGIN_MODULE, "--ci-shard=1/3", "--ci-evidence-dir=src", "tests/crypto_core"], "already exists"),
    ],
    ids=[
        "no-options",
        "no-evidence-dir",
        "shard-zero",
        "shard-beyond-count",
        "too-many-shards",
        "not-numeric",
        "dir-exists",
    ],
)
def test_a_shard_refuses_incomplete_or_invalid_shard_options(sealed_project, args: list[str], marker: str):
    root, head, _ = sealed_project
    completed = run_pytest(root, args, shard_env(head, 4242, 3))
    assert completed.returncode == USAGE_ERROR
    assert marker in completed.stderr
    assert not (root / "fresh").exists()
