"""The required ``tests`` aggregator fails closed on every incomplete, foreign or failed piece of shard evidence.

Each case starts from one valid two-shard evidence set (which passes) and breaks exactly one thing.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path

import coverage
import pytest

from scripts.crypto_core.ci_test_aggregate import EVIDENCE_PREFIX, main
from scripts.crypto_core.ci_test_shard import (
    CANONICAL_PYTEST_ARGS,
    COVERAGE_NAME,
    PLUGIN,
    REPORT_NAME,
    REPORT_SCHEMA,
    file_of,
    partition,
    sha256_file,
)

HEAD = "0123456789abcdef0123456789abcdef01234567"
OTHER_HEAD = "fedcba9876543210fedcba9876543210fedcba98"
COLLECTION = [
    "tests/crypto_core/test_one.py::test_a",
    "tests/crypto_core/test_one.py::test_b[x]",
    "tests/crypto_core/test_two.py::test_c",
    "tests/crypto_core/test_three.py::test_d",
    "tests/crypto_core/test_three.py::TestE::test_e",
]
SOURCE = "".join(f"value_{index} = {index}\n" for index in range(10))  # ten statements on lines 1..10
LINES = {1: {1, 2, 3, 4, 5}, 2: {6, 7, 8}}  # union 8 of 10 = 80%; the two shard percentages average 40%
NEEDS = {"lint": {"result": "success", "outputs": {}}, "test-shard": {"result": "success", "outputs": {}}}


class Evidence:
    def __init__(self, root: Path) -> None:
        self.root = root / "evidence"
        self.source = root / "src" / "crypto_core"
        self.source.mkdir(parents=True)
        self.module = self.source / "mod.py"
        self.module.write_text(SOURCE, encoding="utf-8")
        self.combined = root / "combined.sqlite"
        self.needs = json.loads(json.dumps(NEEDS))
        self.head = HEAD
        self.fail_under = "70"
        assignment = partition(COLLECTION, 2)
        for index in (1, 2):
            directory = self.directory(index)
            directory.mkdir(parents=True)
            data = coverage.CoverageData(basename=str(directory / COVERAGE_NAME))
            data.add_lines({str(self.module): sorted(LINES[index])})
            data.write()
            selected = [node_id for node_id in COLLECTION if assignment[file_of(node_id)] == index]
            self.write(
                index,
                {
                    "schema": REPORT_SCHEMA,
                    "shard": index,
                    "shard_count": 2,
                    "head": HEAD,
                    "run_id": "7",
                    "run_attempt": "1",
                    "invocation_args": [
                        "-p",
                        PLUGIN,
                        f"--ci-shard={index}/2",
                        f"--ci-shard-head={HEAD}",
                        "--ci-shard-report=r",
                        *CANONICAL_PYTEST_ARGS,
                    ],
                    "pytest_addopts": "",
                    "exit_status": 0,
                    "collected": list(COLLECTION),
                    "selected": selected,
                    "outcomes": dict.fromkeys(selected, "passed"),
                    "file_seconds": {file_of(node_id): 0.5 for node_id in selected},
                    "coverage_sha256": sha256_file(directory / COVERAGE_NAME),
                },
            )

    def directory(self, index: int) -> Path:
        return self.root / f"{EVIDENCE_PREFIX}{index}"

    def report(self, index: int) -> dict:
        return json.loads((self.directory(index) / REPORT_NAME).read_text(encoding="utf-8"))

    def write(self, index: int, report: object) -> None:
        (self.directory(index) / REPORT_NAME).write_text(json.dumps(report), encoding="utf-8")

    def edit(self, index: int, **changes: object) -> None:
        report = self.report(index)
        report.update(changes)
        self.write(index, report)

    def run(self) -> tuple[int, str]:
        out = io.StringIO()
        code = main(
            [
                "--shards",
                "2",
                "--evidence",
                str(self.root),
                "--head",
                self.head,
                "--expected-head",
                HEAD,
                "--run-id",
                "7",
                "--run-attempt",
                "2",
                "--needs",
                json.dumps(self.needs),
                "--source-root",
                str(self.source),
                "--fail-under",
                self.fail_under,
                "--combined-coverage",
                str(self.combined),
            ],
            out=out,
        )
        return code, out.getvalue()


@pytest.fixture
def evidence(tmp_path: Path) -> Evidence:
    return Evidence(tmp_path)


def test_complete_authentic_evidence_passes_on_the_exact_union_of_the_shards_coverage(evidence: Evidence) -> None:
    code, out = evidence.run()
    assert code == 0, out
    assert "::error::" not in out and "CRYPTO_CORE_CI_TESTS_VERDICT=PASS" in out
    assert "collection: 5 node ids" in out and "outcomes: {'passed': 5}" in out
    assert "coverage of the verified union: 80.00% (fail-under 70)" in out
    assert evidence.combined.is_file()
    # the raw shard data is kept, unchanged, so its recorded digests still verify
    for index in (1, 2):
        assert sha256_file(evidence.directory(index) / COVERAGE_NAME) == evidence.report(index)["coverage_sha256"]


def test_an_earlier_attempt_of_the_same_run_is_still_evidence_of_this_commit(evidence: Evidence) -> None:
    evidence.edit(1, run_attempt="2")
    assert evidence.run()[0] == 0


def _needs(job: str, result: object) -> Callable[[Evidence], None]:
    def mutate(evidence: Evidence) -> None:
        evidence.needs[job] = {"result": result, "outputs": {}}

    return mutate


def _drop_need(job: str) -> Callable[[Evidence], None]:
    return lambda evidence: evidence.needs.pop(job)


def _remove(index: int, name: str) -> Callable[[Evidence], None]:
    return lambda evidence: (evidence.directory(index) / name).unlink()


def _edit(index: int, **changes: object) -> Callable[[Evidence], None]:
    return lambda evidence: evidence.edit(index, **changes)


def _rewrite(index: int, change: Callable[[dict], object]) -> Callable[[Evidence], None]:
    def mutate(evidence: Evidence) -> None:
        report = evidence.report(index)
        change(report)
        evidence.write(index, report)

    return mutate


def _missing_shard_index(evidence: Evidence, index: int) -> None:
    for path in evidence.directory(index).iterdir():
        path.unlink()
    evidence.directory(index).rmdir()


def _missing_shard(evidence: Evidence) -> None:
    _missing_shard_index(evidence, 2)


def _unexpected_shard(evidence: Evidence) -> None:
    evidence.directory(3).mkdir()


def _extra_file(evidence: Evidence) -> None:
    (evidence.directory(1) / "stale.sqlite").write_bytes(b"")


def _malformed(evidence: Evidence) -> None:
    (evidence.directory(1) / REPORT_NAME).write_text("{not json", encoding="utf-8")


def _not_an_object(evidence: Evidence) -> None:
    evidence.write(1, ["a", "list"])


def _incomplete_collection(evidence: Evidence) -> None:
    # shard 2 is self-consistent but never collected a test that shard 1 owns
    owned_by_one = evidence.report(1)["selected"][0]
    report = evidence.report(2)
    report["collected"] = [node_id for node_id in COLLECTION if node_id != owned_by_one]
    evidence.write(2, report)


def _selected_outside_collection(evidence: Evidence) -> None:
    report = evidence.report(2)
    report["collected"] = [node_id for node_id in COLLECTION if node_id not in report["selected"][:1]]
    evidence.write(2, report)


def _moved_selection(evidence: Evidence) -> None:
    one, two = evidence.report(1), evidence.report(2)
    moved = two["selected"].pop()
    one["selected"].append(moved)
    one["outcomes"][moved] = two["outcomes"].pop(moved)
    evidence.write(1, one)
    evidence.write(2, two)


def _overlapping_selection(evidence: Evidence) -> None:
    one, two = evidence.report(1), evidence.report(2)
    one["selected"].append(two["selected"][0])
    one["outcomes"][two["selected"][0]] = "passed"
    evidence.write(1, one)


def _duplicate_collected(evidence: Evidence) -> None:
    for index in (1, 2):
        report = evidence.report(index)
        report["collected"] = [*COLLECTION, COLLECTION[0]]
        evidence.write(index, report)


def _outcome(index: int, outcome: str) -> Callable[[Evidence], None]:
    def mutate(evidence: Evidence) -> None:
        report = evidence.report(index)
        report["outcomes"][report["selected"][0]] = outcome
        evidence.write(index, report)

    return mutate


def _missing_outcome(evidence: Evidence) -> None:
    report = evidence.report(1)
    report["outcomes"].pop(report["selected"][0])
    evidence.write(1, report)


def _foreign_outcome(evidence: Evidence) -> None:
    report = evidence.report(1)
    report["outcomes"]["tests/crypto_core/test_other.py::test_z"] = "passed"
    evidence.write(1, report)


def _tampered_coverage(evidence: Evidence) -> None:
    path = evidence.directory(2) / COVERAGE_NAME
    data = coverage.CoverageData(basename=str(path))
    data.add_lines({str(evidence.module): [9, 10]})
    data.write()


def _corrupt_coverage(evidence: Evidence) -> None:
    path = evidence.directory(2) / COVERAGE_NAME
    path.write_bytes(b"not a coverage database")
    evidence.edit(2, coverage_sha256=sha256_file(path))


def _foreign_source(evidence: Evidence) -> None:
    outside = evidence.root.parent / "elsewhere.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    path = evidence.directory(1) / COVERAGE_NAME
    data = coverage.CoverageData(basename=str(path))
    data.add_lines({str(outside): [1]})
    data.write()
    evidence.edit(1, coverage_sha256=sha256_file(path))


def _branch_data(evidence: Evidence) -> None:
    path = evidence.directory(1) / COVERAGE_NAME
    path.unlink()
    data = coverage.CoverageData(basename=str(path))
    data.add_arcs({str(evidence.module): [(-1, 1), (1, 2)]})
    data.write()
    evidence.edit(1, coverage_sha256=sha256_file(path))


def _floor(value: str) -> Callable[[Evidence], None]:
    def mutate(evidence: Evidence) -> None:
        evidence.fail_under = value

    return mutate


def _aggregator_head(evidence: Evidence) -> None:
    evidence.head = OTHER_HEAD


NEGATIVE_CASES = {
    "lint-failed": (_needs("lint", "failure"), "job lint: result 'failure', required 'success'"),
    "shard-job-failed": (_needs("test-shard", "failure"), "job test-shard: result 'failure'"),
    "shard-job-cancelled": (_needs("test-shard", "cancelled"), "job test-shard: result 'cancelled'"),
    "shard-job-skipped": (_needs("test-shard", "skipped"), "job test-shard: result 'skipped'"),
    "shard-job-absent": (_drop_need("test-shard"), "job test-shard: result None"),
    "unexpected-job": (_needs("other", "success"), "needs: expected exactly ['lint', 'test-shard']"),
    "shard-evidence-missing": (_missing_shard, "shard 2: evidence 'crypto-core-test-shard-2' is missing"),
    "unexpected-shard-evidence": (_unexpected_shard, "evidence: unexpected entry 'crypto-core-test-shard-3'"),
    "extra-artifact-file": (_extra_file, "shard 1: evidence holds"),
    "coverage-artifact-missing": (_remove(2, COVERAGE_NAME), "shard 2: evidence holds ['report.json']"),
    "report-artifact-missing": (_remove(1, REPORT_NAME), "shard 1: evidence holds ['coverage.sqlite']"),
    "malformed-report": (_malformed, "shard 1: report is unreadable"),
    "report-not-an-object": (_not_an_object, "shard 1: report fields list are not"),
    "report-field-missing": (_rewrite(1, lambda report: report.pop("outcomes")), "shard 1: report fields"),
    "report-field-extra": (_edit(1, verdict="pass"), "shard 1: report fields"),
    "report-field-type": (_edit(1, exit_status=False), "shard 1: report fields of the wrong type: ['exit_status']"),
    "outcome-type": (
        _rewrite(1, lambda report: report["outcomes"].update(dict.fromkeys(report["selected"], 1))),
        "['outcomes']",
    ),
    "wrong-schema": (_edit(1, schema="v0"), "shard 1: schema 'v0'"),
    "wrong-shard-index": (_edit(2, shard=1), "shard 2: report is for shard 1/2, not 2/2"),
    "wrong-shard-count": (_edit(2, shard_count=3), "shard 2: report is for shard 2/3, not 2/2"),
    "wrong-head": (_edit(1, head=OTHER_HEAD), f"shard 1: tested head '{OTHER_HEAD}' is not '{HEAD}'"),
    "stale-run": (_edit(1, run_id="6"), "shard 1: evidence of run '6', not of this run '7'"),
    "future-attempt": (_edit(1, run_attempt="3"), "shard 1: run attempt '3' is not an attempt of this run up to '2'"),
    "pytest-addopts": (_edit(2, pytest_addopts="-k fast"), "shard 2: PYTEST_ADDOPTS was set: '-k fast'"),
    "narrowed-invocation": (
        _rewrite(1, lambda report: report["invocation_args"].__setitem__(-1, "tests/crypto_core/validation")),
        "shard 1: invocation",
    ),
    "foreign-shard-option": (
        _rewrite(1, lambda report: report["invocation_args"].__setitem__(2, "--ci-shard=2/2")),
        "is not the canonical shard invocation",
    ),
    "pytest-failed": (_edit(1, exit_status=1), "shard 1: pytest exit status 1"),
    "nothing-collected": (_edit(1, collected=[]), "shard 1: collected no test"),
    "nothing-selected": (_edit(1, selected=[], outcomes={}), "shard 1: selected no test"),
    "duplicate-node-ids": (_duplicate_collected, "duplicate collected node ids: tests/crypto_core/test_one.py::test_a"),
    "incomplete-collection": (_incomplete_collection, "shard 2: collection (4 ids) differs from shard 1 (5 ids)"),
    "selected-outside-collection": (
        _selected_outside_collection,
        "shard 2: selected node ids outside its own collection",
    ),
    "selection-not-partition": (_moved_selection, "is not its partition"),
    "overlapping-selection": (_overlapping_selection, "shard 1: selection"),
    "failed-test": (_outcome(2, "failed"), "shard 2: 1 tests did not pass"),
    "errored-test": (_outcome(1, "error"), "[error]"),
    "incomplete-test": (_outcome(1, "incomplete"), "[incomplete]"),
    "missing-outcome": (_missing_outcome, "shard 1: 1 selected tests never reported an outcome"),
    "unselected-outcome": (_foreign_outcome, "shard 1: outcomes for unselected node ids"),
    "coverage-digest-mismatch": (
        _tampered_coverage,
        "shard 2: coverage data does not match the digest its report recorded",
    ),
    "corrupt-coverage": (_corrupt_coverage, "shard 2: coverage data is unreadable"),
    "coverage-outside-source": (_foreign_source, "shard 1: coverage measured files outside"),
    "branch-coverage": (_branch_data, "shard 1: coverage data holds branch arcs"),
    "below-floor": (_floor("90"), "coverage total 80.00% of the verified union is below --fail-under=90"),
    "aggregator-wrong-checkout": (
        _aggregator_head,
        f"aggregator checkout '{OTHER_HEAD}' is not the run's commit '{HEAD}'",
    ),
}


@pytest.mark.parametrize("case", sorted(NEGATIVE_CASES))
def test_every_incomplete_foreign_or_failed_piece_of_evidence_fails_the_required_check(
    evidence: Evidence, case: str
) -> None:
    mutate, message = NEGATIVE_CASES[case]
    mutate(evidence)
    code, out = evidence.run()
    assert code == 1, out
    assert message in out, out
    assert "CRYPTO_CORE_CI_TESTS_VERDICT=FAIL" in out
    assert "coverage of the verified union" not in out or case == "below-floor"


def test_no_evidence_at_all_fails_with_every_shard_missing(evidence: Evidence) -> None:
    for index in (1, 2):
        _missing_shard_index(evidence, index)
    evidence.root.rmdir()
    code, out = evidence.run()
    assert code == 1
    assert "shard 1: evidence 'crypto-core-test-shard-1' is missing" in out
    assert "shard 2: evidence 'crypto-core-test-shard-2' is missing" in out


def test_needs_that_are_not_a_json_object_fail(evidence: Evidence) -> None:
    out = io.StringIO()
    argv = ["--shards", "2", "--evidence", str(evidence.root), "--head", HEAD, "--expected-head", HEAD, "--run-id", "7"]
    argv += ["--run-attempt", "1", "--needs", "not json", "--source-root", str(evidence.source), "--fail-under", "70"]
    argv += ["--combined-coverage", str(evidence.combined)]
    assert main(argv, out=out) == 1
    assert "needs: not a JSON object" in out.getvalue()
