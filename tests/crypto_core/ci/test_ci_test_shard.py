"""The CI shard plugin: a total, disjoint, deterministic file partition and faithful per-shard evidence.

The end-to-end tests run real ``pytest`` shards of a tiny throwaway project through the plugin and the real
aggregator CLI, so the selection, the outcome classification, the coverage union and a mandatory shard failure are
proven on the actual mechanism, not on a model of it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.crypto_core import ci_test_shard as shard_module
from scripts.crypto_core.ci_test_shard import (
    CANONICAL_PYTEST_ARGS,
    COVERAGE_NAME,
    PLUGIN,
    REPORT_NAME,
    canonical_args,
    classify,
    file_of,
    parse_shard,
    partition,
)

REPO = Path(__file__).resolve().parents[3]
HEAD = "0123456789abcdef0123456789abcdef01234567"


def node_ids(tests_per_file: dict[str, int]) -> list[str]:
    return [f"{path}::test_{index}[case-{index}]" for path, count in tests_per_file.items() for index in range(count)]


# -- partition ---------------------------------------------------------------------------------------------------


def test_every_collected_file_lands_in_exactly_one_shard_as_one_contiguous_run_in_collection_order() -> None:
    ids = node_ids({"tests/a.py": 3, "tests/b.py": 1, "tests/c.py": 50, "tests/d.py": 7, "tests/e.py": 2})
    order = list(dict.fromkeys(file_of(node_id) for node_id in ids))
    for shard_count in (1, 2, 3, 4, 6):
        assignment = partition(ids, shard_count)
        assert list(assignment) == order
        shards = [assignment[path] for path in order]
        assert shards == sorted(shards) and set(shards) <= set(range(1, shard_count + 1))
        assert partition(list(ids), shard_count) == assignment
        selected = [
            node_id for index in range(1, shard_count + 1) for node_id in ids if assignment[file_of(node_id)] == index
        ]
        assert selected == ids


def test_a_file_never_splits_and_parametrized_ids_stay_with_their_file() -> None:
    ids = ["tests/p.py::test_x[a::b]", "tests/p.py::test_x[c]", "tests/p.py::Test::test_y", "tests/q.py::test_z"]
    assert {file_of(node_id) for node_id in ids} == {"tests/p.py", "tests/q.py"}
    assignment = partition(ids, 2)
    assert len({assignment[file_of(node_id)] for node_id in ids[:3]}) == 1


def test_each_file_goes_to_the_part_of_the_total_weight_that_holds_its_midpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weights = {"tests/w1.py": 4, "tests/w2.py": 1, "tests/w3.py": 1, "tests/w4.py": 3, "tests/w5.py": 3}
    monkeypatch.setattr(shard_module, "FILE_WEIGHTS", weights)
    ids = node_ids(dict.fromkeys(weights, 1))
    # total 12 s, thirds end at 4 and 8; midpoints 2 | 4.5, 5.5, 7.5 | 10.5
    assert partition(ids, 3) == {
        "tests/w1.py": 1,
        "tests/w2.py": 2,
        "tests/w3.py": 2,
        "tests/w4.py": 2,
        "tests/w5.py": 3,
    }
    # the same files in the reverse collection order: midpoints 1.5, 4.5 | 6.5, 7.5 | 10
    reverse = node_ids(dict.fromkeys(reversed(weights), 1))
    assert partition(reverse, 3) == {
        "tests/w5.py": 1,
        "tests/w4.py": 2,
        "tests/w3.py": 2,
        "tests/w2.py": 2,
        "tests/w1.py": 3,
    }


def test_measured_weights_outrank_test_counts_and_unweighted_files_are_still_assigned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shard_module, "FILE_WEIGHTS", {"tests/heavy.py": 3})
    # heavy weighs 3 s; each unweighted file 100 tests x 10 ms = 1 s: halves end at 2.5 s; midpoints 1.5 | 3.5, 4.5
    ids = node_ids({"tests/heavy.py": 1, "tests/new_a.py": 100, "tests/new_b.py": 100})
    assert partition(ids, 2) == {"tests/heavy.py": 1, "tests/new_a.py": 2, "tests/new_b.py": 2}
    # by test count alone heavy.py (one test) weighs 10 ms and new_a.py rides along with it
    monkeypatch.setattr(shard_module, "FILE_WEIGHTS", {})
    assert partition(ids, 2) == {"tests/heavy.py": 1, "tests/new_a.py": 1, "tests/new_b.py": 2}


def test_only_a_file_that_outweighs_a_whole_part_can_leave_a_shard_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    # The aggregator refuses an empty shard ("selected no test"), so this can never pass silently.
    monkeypatch.setattr(shard_module, "FILE_WEIGHTS", {"tests/huge.py": 100})
    assert partition(node_ids({"tests/huge.py": 1, "tests/tiny.py": 1}), 3) == {"tests/huge.py": 2, "tests/tiny.py": 3}


@pytest.mark.parametrize("shard_count", [0, -1, True, 2.0, "3"])
def test_a_non_positive_or_non_integer_shard_count_is_refused(shard_count: object) -> None:
    with pytest.raises(ValueError, match="shard_count"):
        partition(["tests/a.py::t"], shard_count)  # type: ignore[arg-type]


def test_the_measured_weights_are_positive_whole_seconds_of_crypto_core_test_files() -> None:
    # A weight that outlives its file is harmless (it only changes balance), so file existence is not asserted.
    assert shard_module.FILE_WEIGHTS
    for path, seconds in shard_module.FILE_WEIGHTS.items():
        assert path.startswith("tests/crypto_core/") and path.endswith(".py"), path
        assert isinstance(seconds, int) and not isinstance(seconds, bool) and seconds > 0, path


# -- arguments and outcomes --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("spec", "expected"), [("1/1", (1, 1)), ("1/3", (1, 3)), ("3/3", (3, 3))])
def test_a_shard_spec_is_k_of_n(spec: str, expected: tuple[int, int]) -> None:
    assert parse_shard(spec) == expected


@pytest.mark.parametrize("spec", ["0/3", "4/3", "3", "a/3", "1/0", "-1/3", " 1/3", "1/3/4", "1/", "/3"])
def test_a_malformed_shard_spec_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match="--ci-shard"):
        parse_shard(spec)


def test_the_canonical_invocation_drops_only_the_plugin_and_its_own_options() -> None:
    raw = [
        "-p",
        PLUGIN,
        "--ci-shard=2/3",
        f"--ci-shard-head={HEAD}",
        "--ci-shard-report=/r.json",
        *CANONICAL_PYTEST_ARGS,
    ]
    assert canonical_args(raw) == list(CANONICAL_PYTEST_ARGS)
    assert canonical_args([*raw, "-k", "slow"]) == [*CANONICAL_PYTEST_ARGS, "-k", "slow"]
    assert canonical_args(["-p", "other", *CANONICAL_PYTEST_ARGS]) == ["-p", "other", *CANONICAL_PYTEST_ARGS]
    assert canonical_args(["--ci-shard", "2/3", *CANONICAL_PYTEST_ARGS])[:2] == ["--ci-shard", "2/3"]


@pytest.mark.parametrize(
    ("phases", "outcome"),
    [
        ([("setup", "passed", False), ("call", "passed", False), ("teardown", "passed", False)], "passed"),
        ([("setup", "skipped", False), ("teardown", "passed", False)], "skipped"),
        ([("setup", "passed", False), ("call", "skipped", False), ("teardown", "passed", False)], "skipped"),
        ([("setup", "passed", False), ("call", "skipped", True), ("teardown", "passed", False)], "xfailed"),
        ([("setup", "passed", False), ("call", "passed", True), ("teardown", "passed", False)], "xpassed"),
        ([("setup", "passed", False), ("call", "failed", False), ("teardown", "passed", False)], "failed"),
        ([("setup", "failed", False), ("teardown", "passed", False)], "error"),
        ([("setup", "passed", False), ("call", "passed", False), ("teardown", "failed", False)], "error"),
        ([("setup", "passed", False), ("call", "passed", False)], "incomplete"),
        ([("setup", "passed", False), ("teardown", "passed", False)], "incomplete"),
        ([], "incomplete"),
    ],
)
def test_each_test_gets_one_outcome_and_an_unfinished_test_is_incomplete(phases: list, outcome: str) -> None:
    assert classify(phases) == outcome


# -- end to end: real pytest shards, real coverage, the real aggregator CLI ---------------------------------------

_SOURCE = "def add(a, b):\n    return a + b\n\n\ndef unused():\n    return 1\n"
_ALPHA = """\
import pytest

from crypto_core.calc import add


@pytest.mark.parametrize("a", [1, 2, 3])
def test_add(a):
    assert add(a, 1) == a + 1


def test_individual_skip():
    pytest.skip("an individual pytest skip is a valid outcome")


@pytest.mark.xfail(reason="known", strict=True)
def test_known_failure():
    assert add(1, 1) == 3
"""
_GAMMA = """\
import os


def test_gamma():
    assert os.environ.get("CI_SHARD_E2E_FAIL") != "1"
"""
_NEEDS_OK = json.dumps(
    {"lint": {"result": "success", "outputs": {}}, "test-shard": {"result": "success", "outputs": {}}}
)


def make_project(root: Path) -> Path:
    (root / "src" / "crypto_core").mkdir(parents=True)
    (root / "src" / "crypto_core" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "crypto_core" / "calc.py").write_text(_SOURCE, encoding="utf-8")
    tests = root / "tests" / "crypto_core"
    tests.mkdir(parents=True)
    (tests / "test_ci_e2e_alpha.py").write_text(_ALPHA, encoding="utf-8")
    (tests / "test_ci_e2e_beta.py").write_text("def test_beta():\n    assert True\n", encoding="utf-8")
    (tests / "test_ci_e2e_gamma.py").write_text(_GAMMA, encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\npythonpath = src\n", encoding="utf-8")
    return root


def child_env(**extra: str) -> dict[str, str]:
    # Never inherit this process's COVERAGE_FILE: a child writing to it would overwrite the running shard's own data.
    drop = ("PYTEST_", "COVERAGE_", "COV_CORE_", "CI_SHARD_E2E_")
    env = {key: value for key, value in os.environ.items() if not key.startswith(drop)}
    env.update(PYTHONPATH=str(REPO), PYTHONWARNINGS="error", PYTHONIOENCODING="utf-8")
    env.update(GITHUB_RUN_ID="7", GITHUB_RUN_ATTEMPT="1", **extra)
    return env


def run(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # args are this test's own fixed argv (sys.executable and the throwaway project), never external input
    return subprocess.run(  # noqa: S603
        args, cwd=cwd, env=env, capture_output=True, encoding="utf-8", errors="replace", timeout=600, check=False
    )


def run_shard(project: Path, evidence: Path, index: int, count: int, **extra: str) -> subprocess.CompletedProcess[str]:
    directory = evidence / f"crypto-core-test-shard-{index}"
    directory.mkdir(parents=True)
    args = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        PLUGIN,
        f"--ci-shard={index}/{count}",
        f"--ci-shard-head={HEAD}",
        f"--ci-shard-report={directory / REPORT_NAME}",
        *CANONICAL_PYTEST_ARGS,
    ]
    return run(args, project, child_env(COVERAGE_FILE=str(directory / COVERAGE_NAME), **extra))


def run_aggregator(
    project: Path, evidence: Path, needs: str = _NEEDS_OK, fail_under: str = "70"
) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        "-m",
        "scripts.crypto_core.ci_test_aggregate",
        "--shards",
        "2",
        "--evidence",
        str(evidence),
        "--head",
        HEAD,
        "--expected-head",
        HEAD,
        "--run-id",
        "7",
        "--run-attempt",
        "1",
        "--needs",
        needs,
        "--source-root",
        str(project / "src" / "crypto_core"),
        "--fail-under",
        fail_under,
        "--combined-coverage",
        str(evidence.parent / "combined.sqlite"),
    ]
    return run(args, REPO, child_env())


def report_of(evidence: Path, index: int) -> dict:
    return json.loads((evidence / f"crypto-core-test-shard-{index}" / REPORT_NAME).read_text(encoding="utf-8"))


def test_real_shards_select_disjoint_complete_files_and_the_aggregator_accepts_their_exact_union(
    tmp_path: Path,
) -> None:
    project, evidence = make_project(tmp_path / "project"), tmp_path / "evidence"
    first, second = run_shard(project, evidence, 1, 2), run_shard(project, evidence, 2, 2)
    assert (first.returncode, second.returncode) == (0, 0), first.stdout + first.stderr + second.stdout + second.stderr
    one, two = report_of(evidence, 1), report_of(evidence, 2)
    assert one["collected"] == two["collected"] and len(one["collected"]) == 7
    assert sorted(one["selected"] + two["selected"]) == sorted(one["collected"])
    assert {file_of(node_id) for node_id in one["selected"]} == {"tests/crypto_core/test_ci_e2e_alpha.py"}
    assert one["outcomes"] == {
        "tests/crypto_core/test_ci_e2e_alpha.py::test_add[1]": "passed",
        "tests/crypto_core/test_ci_e2e_alpha.py::test_add[2]": "passed",
        "tests/crypto_core/test_ci_e2e_alpha.py::test_add[3]": "passed",
        "tests/crypto_core/test_ci_e2e_alpha.py::test_individual_skip": "skipped",
        "tests/crypto_core/test_ci_e2e_alpha.py::test_known_failure": "xfailed",
    }
    assert two["outcomes"] == dict.fromkeys(two["selected"], "passed")
    assert (one["head"], one["run_id"], one["run_attempt"], one["exit_status"], one["pytest_addopts"]) == (
        HEAD,
        "7",
        "1",
        0,
        "",
    )
    assert canonical_args(one["invocation_args"]) == list(CANONICAL_PYTEST_ARGS)

    verdict = run_aggregator(project, evidence)
    assert verdict.returncode == 0, verdict.stdout + verdict.stderr
    assert "CRYPTO_CORE_CI_TESTS_VERDICT=PASS" in verdict.stdout
    assert "outcomes: {'passed': 5, 'skipped': 1, 'xfailed': 1}" in verdict.stdout
    # calc.py: 4 statements, 3 run by shard 1 alone; shard 2 alone measured none. The union is 75%; an average of the
    # two shard percentages would have been 37.5%.
    assert "coverage of the verified union: 75.00% (fail-under 70)" in verdict.stdout
    below = run_aggregator(project, evidence, fail_under="80")
    assert below.returncode == 1 and "below --fail-under=80" in below.stdout


def test_a_failing_test_fails_its_shard_and_the_aggregator_names_it_even_if_the_job_result_were_success(
    tmp_path: Path,
) -> None:
    project, evidence = make_project(tmp_path / "project"), tmp_path / "evidence"
    assert run_shard(project, evidence, 1, 2).returncode == 0
    failed = run_shard(project, evidence, 2, 2, CI_SHARD_E2E_FAIL="1")
    assert failed.returncode == 1, failed.stdout + failed.stderr
    report = report_of(evidence, 2)
    assert report["exit_status"] == 1
    assert report["outcomes"]["tests/crypto_core/test_ci_e2e_gamma.py::test_gamma"] == "failed"
    for needs in (_NEEDS_OK, json.dumps({"lint": {"result": "success"}, "test-shard": {"result": "failure"}})):
        verdict = run_aggregator(project, evidence, needs=needs)
        assert verdict.returncode == 1
        assert "shard 2: pytest exit status 1" in verdict.stdout
        assert "test_ci_e2e_gamma.py::test_gamma [failed]" in verdict.stdout
        assert "CRYPTO_CORE_CI_TESTS_VERDICT=FAIL" in verdict.stdout


def test_a_shard_that_never_ran_leaves_no_evidence_and_fails_the_gate(tmp_path: Path) -> None:
    project, evidence = make_project(tmp_path / "project"), tmp_path / "evidence"
    assert run_shard(project, evidence, 1, 2).returncode == 0
    skipped = json.dumps({"lint": {"result": "success"}, "test-shard": {"result": "skipped"}})
    verdict = run_aggregator(project, evidence, needs=skipped)
    assert verdict.returncode == 1
    assert "job test-shard: result 'skipped', required 'success'" in verdict.stdout
    assert "shard 2: evidence 'crypto-core-test-shard-2' is missing" in verdict.stdout
