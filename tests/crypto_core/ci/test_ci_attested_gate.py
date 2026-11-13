"""The required ``tests`` gate accepts only complete shard evidence of the current run attempt.

Real evidence comes from real pytest shards (the helpers of ``test_ci_shard_evidence``) sealed in a throwaway git
project for attempts 1 and 2 of one workflow run.  The GitHub Actions API is a deterministic loopback test double
serving the jobs of the judged run attempt.  Every case runs the real gate CLI (``ci_attested_gate.main`` in
process, or the module as a subprocess) and asserts its exit code and verdict line.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import test_ci_shard_evidence as shards
from coverage import Coverage, CoverageData

from scripts.crypto_core import ci_attested_gate as gate
from scripts.crypto_core import ci_shard_plan as plan

RUN_ID = 31337
RUN_HEAD = "ab" * 20  # the run's head commit: a pull request head, unlike the checked-out merge commit
FAKE_CREDENTIAL = "fixture-actions-read-credential-6c1d"
SHARDS = 3
SUCCESS_NEEDS = json.dumps(
    {"lint": {"result": "success", "outputs": {}}, "test-shard": {"result": "success", "outputs": {}}}
)
UNION_COVERAGE = "Total coverage: 88.89%"  # 16 of the fixture's 18 statements; idle.py never runs
PASS_LINE = f"{gate.VERDICT}=PASS"
FAIL_LINE = f"{gate.VERDICT}=FAIL"


def _listing(total: int, jobs: list[dict]) -> bytes:
    return json.dumps({"total_count": total, "jobs": jobs}).encode()


@dataclass(frozen=True)
class World:
    root: Path
    head: str
    sealed: dict[int, dict[int, Path]]  # run attempt -> shard -> sealed evidence directory


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
    root = tmp_path_factory.mktemp("gate_project")
    head = shards.make_project(root)
    store = tmp_path_factory.mktemp("gate_store")
    return World(root, head, {attempt: shards.seal_shards(root, head, RUN_ID, attempt, store) for attempt in (1, 2)})


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request: object, client_address: object) -> None:
        return None  # a client that hung up (the killed gate) is expected, not a test failure


class FakeActionsApi:
    """Loopback stand-in for ``GET /repos/{repository}/actions/runs/{run}/attempts/{attempt}/jobs``."""

    def __init__(self) -> None:
        api = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                api.requests.append((parsed.path, query, self.headers.get("Authorization")))
                if api.hold is not None:
                    api.hold.wait(timeout=60)
                status, body, headers = api.answer(parsed.path, int(query.get("page", ["1"])[0]))
                self.send_response(status)
                for name, value in {"Content-Type": "application/json", **headers}.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self.server = _QuietServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.reset()

    def reset(self) -> None:
        self.requests: list[tuple[str, dict, str | None]] = []
        self.path = ""
        self.pages: dict[int, tuple[int, bytes, dict[str, str]]] = {}
        self.beyond_total = 0
        self.sequence: list[tuple[int, bytes, dict[str, str]]] = []
        self.hold: threading.Event | None = None

    def serve_jobs(
        self, attempt: int, jobs: list[dict], *, page_size: int = 100, total_count: int | None = None
    ) -> None:
        self.path = f"/repos/{shards.FIXTURE_REPOSITORY}/actions/runs/{RUN_ID}/attempts/{attempt}/jobs"
        total = len(jobs) if total_count is None else total_count
        chunks = [jobs[start : start + page_size] for start in range(0, max(len(jobs), 1), page_size)]
        self.pages = {number: (200, _listing(total, chunk), {}) for number, chunk in enumerate(chunks, start=1)}
        self.beyond_total = total

    def serve_pages(self, attempt: int, pages: dict[int, bytes], beyond_total: int) -> None:
        self.path = f"/repos/{shards.FIXTURE_REPOSITORY}/actions/runs/{RUN_ID}/attempts/{attempt}/jobs"
        self.pages = {number: (200, body, {}) for number, body in pages.items()}
        self.beyond_total = beyond_total

    def serve_sequence(self, attempt: int, answers: list[tuple[int, bytes, dict[str, str]]]) -> None:
        self.path = f"/repos/{shards.FIXTURE_REPOSITORY}/actions/runs/{RUN_ID}/attempts/{attempt}/jobs"
        self.sequence = list(answers)

    def answer(self, path: str, page: int) -> tuple[int, bytes, dict[str, str]]:
        if path != self.path:
            return 404, b'{"message": "Not Found"}', {}
        if self.sequence:
            return self.sequence.pop(0) if len(self.sequence) > 1 else self.sequence[0]
        return self.pages.get(page, (200, _listing(self.beyond_total, []), {}))

    def close(self) -> None:
        if self.hold is not None:
            self.hold.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)


@pytest.fixture(scope="module")
def api_server() -> Iterator[FakeActionsApi]:
    server = FakeActionsApi()
    yield server
    server.close()


@pytest.fixture
def api(api_server: FakeActionsApi) -> Iterator[FakeActionsApi]:
    api_server.reset()
    yield api_server
    if api_server.hold is not None:
        api_server.hold.set()


def job(name: str, attempt: int, *, job_id: int, **fields: object) -> dict:
    record = {
        "id": job_id,
        "run_id": RUN_ID,
        "run_attempt": attempt,
        "name": name,
        "status": "completed",
        "conclusion": "success",
        "head_sha": RUN_HEAD,
        "workflow_name": "ci",
    }
    record.update(fields)
    return record


def attempt_jobs(attempt: int, changes: dict[str, dict | None] | None = None) -> list[dict]:
    """The jobs of one run attempt as GitHub lists them; ``changes`` edits (or, with None, removes) jobs by name."""
    names = [plan.LINT_JOB, *(plan.shard_job_name(index, SHARDS) for index in range(1, SHARDS + 1))]
    jobs = [job(name, attempt, job_id=1000 * attempt + number) for number, name in enumerate(names)]
    jobs.append(job("codeql", attempt, job_id=1000 * attempt + 10))
    jobs.append(job("slow-tests", attempt, job_id=1000 * attempt + 11, conclusion="skipped"))
    jobs.append(job("tests", attempt, job_id=1000 * attempt + 12, status="in_progress", conclusion=None))
    edited = []
    for record in jobs:
        change = (changes or {}).get(record["name"], {})
        if change is not None:
            edited.append({**record, **change})
    return edited


def lay_out(tmp_path: Path, sources: dict[str, Path]) -> Path:
    """An evidence directory as download-artifact leaves it: one sub-directory per artifact name."""
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True)
    for name, source in sources.items():
        shutil.copytree(source, evidence / name)
    return evidence


def current(world: World, attempt: int, *, from_attempt: dict[int, int] | None = None) -> dict[str, Path]:
    """Artifacts named for ``attempt``; shard K's content comes from attempt ``from_attempt[K]`` (default: same)."""
    origin = from_attempt or {}
    return {
        plan.artifact_name(RUN_ID, attempt, index, SHARDS): world.sealed[origin.get(index, attempt)][index]
        for index in range(1, SHARDS + 1)
    }


def edit_report(evidence: Path, artifact: str, change: Callable[[dict], None]) -> None:
    path = evidence / artifact / plan.REPORT_FILE
    report = json.loads(path.read_bytes().decode("utf-8"))
    change(report)
    path.write_bytes(json.dumps(report).encode("utf-8"))


def reseal(evidence: Path, artifact: str) -> None:
    digest = hashlib.sha256((evidence / artifact / plan.COVERAGE_FILE).read_bytes()).hexdigest()
    edit_report(evidence, artifact, lambda report: report.update(coverage_sha256=digest))


def base_env(world: World, api: FakeActionsApi, attempt: int) -> dict[str, str]:
    return {
        "GITHUB_REPOSITORY": shards.FIXTURE_REPOSITORY,
        "GITHUB_RUN_ID": str(RUN_ID),
        "GITHUB_RUN_ATTEMPT": str(attempt),
        "GITHUB_SHA": world.head,
        "GITHUB_API_URL": api.url,
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
        gate.CREDENTIAL_ENV: FAKE_CREDENTIAL,
        gate.NEEDS_ENV: SUCCESS_NEEDS,
        gate.RUN_HEAD_ENV: RUN_HEAD,
    }


@pytest.fixture
def run_gate(world: World, api: FakeActionsApi, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(gate, "RETRY_DELAYS_SECONDS", (0, 0))

    def run(evidence: Path, attempt: int, *, env: dict[str, str | None] | None = None, fail_under: str = "70"):
        monkeypatch.chdir(world.root)
        for name, value in {**base_env(world, api, attempt), **(env or {})}.items():
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)
        code = gate.main(["--evidence-dir", str(evidence), "--shards", str(SHARDS), "--fail-under", fail_under])
        return code, capsys.readouterr().out

    return run


def assert_pass(code: int, out: str) -> None:
    assert code == 0, out
    assert out.rstrip().splitlines()[-1] == PASS_LINE
    assert FAKE_CREDENTIAL not in out


def assert_fail(code: int, out: str, *markers: str) -> None:
    assert code == 1, out
    assert out.rstrip().splitlines()[-1] == FAIL_LINE
    assert PASS_LINE not in out
    assert FAKE_CREDENTIAL not in out
    for marker in markers:
        assert marker in out, f"{marker!r} missing from:\n{out}"


# --- passing runs ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("attempt", [1, 2], ids=["first-run", "rerun-of-all-jobs"])
def test_a_complete_attempt_with_every_producer_attested_passes(world, api, run_gate, tmp_path, attempt):
    api.serve_jobs(attempt, attempt_jobs(attempt))
    code, out = run_gate(lay_out(tmp_path, current(world, attempt)), attempt)
    assert_pass(code, out)
    assert f"Required test coverage of 70% reached. {UNION_COVERAGE}" in out
    assert "12 tests collected identically; ran 3 / 6 / 3" in out, "legitimate skip, xfail and xpass are accepted"
    assert api.requests, "the producers were attested through the API"
    assert all(auth == f"Bearer {FAKE_CREDENTIAL}" for _, _, auth in api.requests)
    assert all(query["per_page"] == [str(gate.PAGE_SIZE)] for _, query, _ in api.requests)


def test_paginated_job_metadata_is_read_to_completion(world, api, run_gate, tmp_path):
    api.serve_jobs(2, attempt_jobs(2), page_size=2)
    code, out = run_gate(lay_out(tmp_path, current(world, 2)), 2)
    assert_pass(code, out)
    assert [query["page"] for _, query, _ in api.requests] == [["1"], ["2"], ["3"], ["4"]]


def test_an_unfinished_producer_is_retried_and_passes_only_once_attested_complete(world, api, run_gate, tmp_path):
    running = json.dumps(
        {"total_count": 7, "jobs": attempt_jobs(2, {"pytest shard 2 of 3": {"status": "in_progress"}})}
    )
    done = json.dumps({"total_count": 7, "jobs": attempt_jobs(2)})
    api.serve_sequence(2, [(200, running.encode(), {}), (200, done.encode(), {})])
    code, out = run_gate(lay_out(tmp_path, current(world, 2)), 2)
    assert_pass(code, out)
    assert len(api.requests) == 2


def _coverage_percent(coverage_file: Path) -> float:
    reporter = Coverage(data_file=str(coverage_file), source=[plan.SOURCE_DIR])
    try:
        reporter.load()
        return reporter.report(file=io.StringIO())
    finally:
        reporter.get_data().close()


def test_the_floor_applies_to_the_union_never_to_one_shard_or_an_average(world, api, run_gate, tmp_path, monkeypatch):
    monkeypatch.chdir(world.root)
    partial = [_coverage_percent(world.sealed[1][index] / plan.COVERAGE_FILE) for index in range(1, SHARDS + 1)]
    assert max(partial) < 80 and sum(partial) / len(partial) < 80, partial
    api.serve_jobs(1, attempt_jobs(1))
    code, out = run_gate(lay_out(tmp_path, current(world, 1)), 1, fail_under="80")
    assert_pass(code, out)
    assert f"Required test coverage of 80% reached. {UNION_COVERAGE}" in out


# --- the inherited blocker and the retry and cancellation matrix -------------------------------------------------


def test_p2_reproducer_a_cancelled_current_shard_is_never_replaced_by_an_earlier_attempts_success(
    world, api, run_gate, tmp_path
):
    """CURRENT_ATTEMPT=2: shards 1-2 of attempt 2 succeeded, shard 3 of attempt 2 was cancelled, attempt 1's shard-3
    artifact is still in the run and ``needs`` reports the matrix as success.  The rejected design accepted this."""
    api.serve_jobs(2, attempt_jobs(2, {"pytest shard 3 of 3": {"conclusion": "cancelled"}}))
    stale = plan.artifact_name(RUN_ID, 1, 3, SHARDS)
    sources = current(world, 2)
    del sources[plan.artifact_name(RUN_ID, 2, 3, SHARDS)]
    sources[stale] = world.sealed[1][3]
    code, out = run_gate(lay_out(tmp_path, sources), 2)
    assert_fail(
        code,
        out,
        "producer 'pytest shard 3 of 3' (job 2003) concluded 'cancelled'",
        f"unexpected evidence '{stale}'",
        f"shard 3: artifact '{plan.artifact_name(RUN_ID, 2, 3, SHARDS)}' of the current attempt is missing",
        "coverage was not evaluated",
    )


def test_p2_variant_an_earlier_attempts_report_under_the_current_name_is_rejected(world, api, run_gate, tmp_path):
    api.serve_jobs(2, attempt_jobs(2, {"pytest shard 3 of 3": {"conclusion": "cancelled"}}))
    code, out = run_gate(lay_out(tmp_path, current(world, 2, from_attempt={3: 1})), 2)
    assert_fail(code, out, "shard 3: run_attempt is 1, expected 2", "concluded 'cancelled'")


@pytest.mark.parametrize("renamed", [False, True], ids=["stale-name", "renamed-into-current-attempt"])
def test_2_2_1_evidence_fails_even_when_every_current_producer_and_the_matrix_succeeded(
    world, api, run_gate, tmp_path, renamed
):
    api.serve_jobs(2, attempt_jobs(2))
    sources = current(world, 2, from_attempt={3: 1})
    if not renamed:
        del sources[plan.artifact_name(RUN_ID, 2, 3, SHARDS)]
        sources[plan.artifact_name(RUN_ID, 1, 3, SHARDS)] = world.sealed[1][3]
    code, out = run_gate(lay_out(tmp_path, sources), 2)
    assert_fail(code, out, "run_attempt is 1, expected 2" if renamed else "of the current attempt is missing")


def test_2_2_1_evidence_fails_when_the_shard_job_succeeded_only_in_an_earlier_attempt(world, api, run_gate, tmp_path):
    carried = {"pytest shard 3 of 3": {"run_attempt": 1, "id": 1003}}
    api.serve_jobs(2, attempt_jobs(2, carried))
    code, out = run_gate(lay_out(tmp_path, current(world, 2, from_attempt={3: 1})), 2)
    assert_fail(code, out, "ran in attempt 1, not the current attempt 2", "shard 3: run_attempt is 1, expected 2")


@pytest.mark.parametrize("listing", ["absent", "listed-from-attempt-1"])
def test_a_rerun_of_failed_jobs_only_fails_and_requires_a_full_rerun(world, api, run_gate, tmp_path, listing):
    carried = ["lint", "pytest shard 1 of 3", "pytest shard 2 of 3"]
    if listing == "absent":
        changes: dict[str, dict | None] = {name: None for name in carried}
    else:
        changes = {name: {"run_attempt": 1} for name in carried}
    api.serve_jobs(2, attempt_jobs(2, changes))
    sources = {plan.artifact_name(RUN_ID, 1, index, SHARDS): world.sealed[1][index] for index in (1, 2)}
    sources[plan.artifact_name(RUN_ID, 2, 3, SHARDS)] = world.sealed[2][3]
    code, out = run_gate(lay_out(tmp_path, sources), 2)
    marker = "0 jobs in run" if listing == "absent" else "ran in attempt 1, not the current attempt 2"
    assert_fail(code, out, marker, "shard 1: artifact", "unexpected evidence")


@pytest.mark.parametrize("uploaded", [False, True], ids=["cancelled-before-execution", "cancelled-after-upload"])
def test_a_cancelled_current_shard_fails_whether_or_not_it_uploaded_evidence(world, api, run_gate, tmp_path, uploaded):
    api.serve_jobs(2, attempt_jobs(2, {"pytest shard 2 of 3": {"conclusion": "cancelled"}}))
    sources = current(world, 2)
    if not uploaded:
        del sources[plan.artifact_name(RUN_ID, 2, 2, SHARDS)]
    code, out = run_gate(lay_out(tmp_path, sources), 2)
    assert_fail(code, out, "producer 'pytest shard 2 of 3' (job 2002) concluded 'cancelled'")
    if uploaded:
        assert "[evidence] ok" in out, "the artifact alone never turns a cancelled producer into a success"


def test_a_stale_artifact_next_to_complete_current_evidence_fails(world, api, run_gate, tmp_path):
    api.serve_jobs(2, attempt_jobs(2))
    sources = current(world, 2)
    sources[plan.artifact_name(RUN_ID, 1, 2, SHARDS)] = world.sealed[1][2]
    code, out = run_gate(lay_out(tmp_path, sources), 2)
    assert_fail(code, out, f"unexpected evidence '{plan.artifact_name(RUN_ID, 1, 2, SHARDS)}'")


def test_a_missing_current_artifact_or_evidence_directory_fails(world, api, run_gate, tmp_path):
    api.serve_jobs(2, attempt_jobs(2))
    sources = current(world, 2)
    del sources[plan.artifact_name(RUN_ID, 2, 1, SHARDS)]
    code, out = run_gate(lay_out(tmp_path, sources), 2)
    assert_fail(code, out, "shard 1: artifact", "of the current attempt is missing")
    code, out = run_gate(tmp_path / "never-downloaded", 2)
    assert_fail(code, out, "was downloaded")


def test_a_cancelled_or_killed_gate_never_reports_a_pass(world, api, tmp_path):
    api.serve_jobs(2, attempt_jobs(2))
    api.hold = threading.Event()
    env = {**shards.shard_env(world.head, RUN_ID, 2), **base_env(world, api, 2)}
    args = ["--evidence-dir", str(lay_out(tmp_path, current(world, 2))), "--shards", "3", "--fail-under", "70"]
    process = subprocess.Popen(  # noqa: S603 - this interpreter running the gate module in a test project, no shell
        [sys.executable, "-m", "scripts.crypto_core.ci_attested_gate", *args],
        cwd=world.root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    stdout = ""
    try:
        deadline = time.monotonic() + 60
        while not api.requests and time.monotonic() < deadline:
            time.sleep(0.05)
        assert api.requests, "the gate never reached the producer attestation"
        process.terminate()
        stdout, _ = process.communicate(timeout=60)
    finally:
        api.hold.set()
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=60)
    assert process.returncode != 0
    assert PASS_LINE not in stdout


# --- producer attestation ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "marker"),
    [
        ({"lint": {"conclusion": "failure"}}, "producer 'lint' (job 2000) concluded 'failure'"),
        ({"pytest shard 1 of 3": {"conclusion": "skipped"}}, "concluded 'skipped'"),
        ({"pytest shard 1 of 3": {"conclusion": "timed_out"}}, "concluded 'timed_out'"),
        ({"pytest shard 1 of 3": None}, "producer 'pytest shard 1 of 3': 0 jobs"),
        ({"pytest shard 1 of 3": {"run_id": 99}}, "belongs to run 99"),
        ({"pytest shard 1 of 3": {"head_sha": "cd" * 20}}, "ran for head"),
        ({"pytest shard 1 of 3": {"status": "queued", "conclusion": None}}, "is 'queued', not completed"),
        ({"pytest shard 1 of 3": {"name": "pytest shard 2 of 3"}}, "producer 'pytest shard 2 of 3': 2 jobs"),
        ({"codeql": {"name": "pytest shard 4 of 3"}}, "unexpected producer job 'pytest shard 4 of 3'"),
        ({"codeql": {"name": "pytest shard 1 of 4"}}, "unexpected producer job 'pytest shard 1 of 4'"),
    ],
    ids=[
        "lint-failed",
        "shard-skipped",
        "shard-timed-out",
        "shard-missing",
        "foreign-run",
        "foreign-head",
        "never-finished",
        "duplicate-identity",
        "foreign-shard-index",
        "foreign-shard-count",
    ],
)
def test_producer_metadata_must_attest_each_current_job_exactly_once(world, api, run_gate, tmp_path, changes, marker):
    api.serve_jobs(2, attempt_jobs(2, changes))
    code, out = run_gate(lay_out(tmp_path, current(world, 2)), 2)
    assert_fail(code, out, marker, "coverage was not evaluated")


@pytest.mark.parametrize(
    ("answers", "marker"),
    [
        ([(403, b'{"message": "Resource not accessible by integration"}', {})], "HTTP 403"),
        ([(404, b'{"message": "Not Found"}', {})], "HTTP 404"),
        ([(500, b"{}", {})], "HTTP 500"),
        ([(302, b"", {"Location": "http://127.0.0.1:9/elsewhere"})], "HTTP 302"),
        ([(200, b"<html>not json</html>", {})], "malformed JSON"),
        ([(200, b'{"total_count": 7, "jobs": [], "total_count": 7}', {})], "malformed JSON"),
        ([(200, b'{"jobs": []}', {})], "no integer total_count"),
        ("total-9-of-7", "incomplete jobs listing: 7 jobs for total_count 9"),
        ([(200, _listing(7, [*attempt_jobs(2)[:6], attempt_jobs(2)[0]]), {})], "is listed twice"),
        ([(200, _listing(7, [{**attempt_jobs(2)[1], "run_attempt": "2"}, *attempt_jobs(2)[2:]]), {})], "'run_attempt'"),
        ([(200, _listing(7, [{"id": 1}]), {})], "job metadata field"),
    ],
    ids=[
        "forbidden",
        "attempt-not-found",
        "server-error-persists",
        "redirect",
        "not-json",
        "duplicate-key",
        "no-total",
        "incomplete",
        "duplicate-job",
        "mistyped-field",
        "missing-fields",
    ],
)
def test_unavailable_incomplete_or_malformed_job_metadata_fails_closed(world, api, run_gate, tmp_path, answers, marker):
    if answers == "total-9-of-7":
        api.serve_jobs(2, attempt_jobs(2), total_count=9)
    else:
        api.serve_sequence(2, answers)
    code, out = run_gate(lay_out(tmp_path, current(world, 2)), 2)
    assert_fail(code, out, marker)


def test_a_transient_api_failure_is_retried_but_never_assumed(world, api, run_gate, tmp_path):
    api.serve_sequence(2, [(503, b"{}", {}), (200, _listing(7, attempt_jobs(2)), {})])
    code, out = run_gate(lay_out(tmp_path, current(world, 2)), 2)
    assert_pass(code, out)
    api.reset()
    api.serve_pages(2, {1: _listing(8, attempt_jobs(2)[:4]), 2: _listing(9, attempt_jobs(2)[4:])}, beyond_total=9)
    code, out = run_gate(lay_out(tmp_path / "again", current(world, 2)), 2)
    assert_fail(code, out, "total_count changed from 8 to 9 between pages")


@pytest.mark.parametrize(
    ("needs", "marker"),
    [
        ({"lint": {"result": "failure"}, "test-shard": {"result": "success"}}, "needs.lint.result is 'failure'"),
        ({"lint": {"result": "success"}, "test-shard": {"result": "cancelled"}}, "needs.test-shard.result"),
        ({"lint": {"result": "success"}, "test-shard": {"result": "skipped"}}, "is 'skipped'"),
        ({"lint": {"result": "success"}}, "needs must name exactly"),
        ({"lint": {"result": "success"}, "test-shard": {"result": "success"}, "x": {}}, "needs must name exactly"),
        ("not json", "is not valid JSON"),
        (None, f"{gate.NEEDS_ENV} is not set"),
    ],
    ids=["lint-failed", "matrix-cancelled", "matrix-skipped", "missing", "extra", "not-json", "unset"],
)
def test_the_needs_context_is_necessary_but_never_sufficient(world, api, run_gate, tmp_path, needs, marker):
    api.serve_jobs(2, attempt_jobs(2))
    raw = needs if needs is None or isinstance(needs, str) else json.dumps(needs)
    code, out = run_gate(lay_out(tmp_path, current(world, 2)), 2, env={gate.NEEDS_ENV: raw})
    assert_fail(code, out, marker)


@pytest.mark.parametrize(
    ("env", "marker"),
    [
        ({gate.CREDENTIAL_ENV: None}, f"{gate.CREDENTIAL_ENV} is not set"),
        ({"GITHUB_API_URL": "http://api.github.example"}, "GITHUB_API_URL is missing or not an https URL"),
        ({"GITHUB_RUN_ATTEMPT": "0"}, "GITHUB_RUN_ATTEMPT is missing or malformed"),
        ({"GITHUB_RUN_ID": None}, "GITHUB_RUN_ID is missing or malformed"),
        ({gate.RUN_HEAD_ENV: "main"}, f"{gate.RUN_HEAD_ENV} is missing or malformed"),
        ({"GITHUB_SHA": "cd" * 20}, "the gate's checkout"),
    ],
    ids=["no-token", "plain-http-api", "attempt-zero", "no-run-id", "malformed-run-head", "foreign-checkout"],
)
def test_the_gate_refuses_an_unprovable_run_context(world, api, run_gate, tmp_path, env, marker):
    api.serve_jobs(2, attempt_jobs(2))
    code, out = run_gate(lay_out(tmp_path, current(world, 2)), 2, env=env)
    assert_fail(code, out, marker)
    assert not api.requests, "nothing is attested before the run context is proven"


def test_the_gate_refuses_modified_tracked_files_in_its_own_checkout(world, api, run_gate, tmp_path):
    api.serve_jobs(2, attempt_jobs(2))
    tracked = world.root / "src" / "crypto_core" / "gamma.py"
    original = tracked.read_bytes()
    tracked.write_bytes(original + b"\nEXTRA = 1\n")
    try:
        code, out = run_gate(lay_out(tmp_path, current(world, 2)), 2)
        assert_fail(code, out, "tracked files of the gate's checkout differ")
    finally:
        tracked.write_bytes(original)


# --- evidence provenance and the suite -----------------------------------------------------------------------------

SHARD_2 = plan.artifact_name(RUN_ID, 2, 2, SHARDS)


def _move_file_first(report: dict) -> None:
    last_file = [nodeid for nodeid in report["collection"] if "test_d_outcomes" in nodeid]
    report["collection"] = last_file + [nodeid for nodeid in report["collection"] if nodeid not in last_file]


def _drop_selected(report: dict) -> None:
    dropped = report["selected"].pop()
    del report["outcomes"][dropped]


def _set_first_outcome(outcome: str) -> Callable[[dict], None]:
    return lambda report: report["outcomes"].update({report["selected"][0]: outcome})


REPORT_EDITS = [
    ("schema", lambda r: r.update(schema="crypto_core.ci.shard_evidence.v0"), "shard 2: schema is"),
    ("run-id", lambda r: r.update(run_id=RUN_ID + 1), "shard 2: run_id is 31338, expected 31337"),
    ("earlier-attempt", lambda r: r.update(run_attempt=1), "shard 2: run_attempt is 1, expected 2"),
    ("later-attempt", lambda r: r.update(run_attempt=3), "shard 2: run_attempt is 3, expected 2"),
    ("attempt-as-text", lambda r: r.update(run_attempt="2"), "shard 2: run_attempt is '2', expected 2"),
    ("repository", lambda r: r.update(repository="someone/else"), "shard 2: repository is"),
    ("head", lambda r: r.update(head="cd" * 20), "shard 2: head is"),
    ("tree", lambda r: r.update(tree="cd" * 20), "shard 2: tree is"),
    ("root", lambda r: r.update(root="/elsewhere"), "shard 2: root is"),
    ("shard-index", lambda r: r.update(shard_index=3), "shard 2: shard_index is 3, expected 2"),
    ("shard-count", lambda r: r.update(shard_count=4), "shard 2: shard_count is 4, expected 3"),
    ("narrowed-invocation", lambda r: r["invocation"].extend(["-k", "beta"]), "shard 2: invocation is"),
    ("addopts", lambda r: r["environment"].update(PYTEST_ADDOPTS="-k beta"), "shard 2: environment is"),
    ("warnings-relaxed", lambda r: r["environment"].update(PYTHONWARNINGS=None), "shard 2: environment is"),
    ("python", lambda r: r.update(python="3.0.1"), "shard 2: python '3.0.1' differs"),
    ("exit-status", lambda r: r.update(exitstatus=1), "shard 2: exitstatus is 1, expected 0"),
    ("exit-status-bool", lambda r: r.update(exitstatus=False), "shard 2: exitstatus is False, expected 0"),
    ("extra-field", lambda r: r.update(note="trust me"), "report fields differ"),
    ("missing-field", lambda r: r.pop("tree"), "report fields differ"),
    ("digest", lambda r: r.update(coverage_sha256="0" * 64), "shard 2: coverage_sha256 is"),
    ("collection-missing", lambda r: r["collection"].pop(0), "shard 2: collected another suite than shard 1"),
    ("collection-duplicate", lambda r: r["collection"].append(r["collection"][-1]), "lists a node id twice"),
    ("file-order", _move_file_first, "shard 2: collected the test files in another order"),
    ("selection-partial-file", _drop_selected, "shard 2: the selection is not its whole-file plan share (1 missing"),
    ("selection-foreign", lambda r: r.update(selected=r["collection"]), "(0 missing, 6 foreign)"),
    ("outcome-missing", lambda r: r["outcomes"].pop(r["selected"][0]), "shard 2: outcomes cover 5 of 6"),
    ("outcome-extra", lambda r: r["outcomes"].update({r["collection"][0]: "passed"}), "and 1 unselected"),
    ("outcome-failed", _set_first_outcome("failed"), "shard 2: 1 tests did not pass"),
    ("outcome-error", _set_first_outcome("error"), "-> error"),
    ("outcome-incomplete", _set_first_outcome("incomplete"), "-> incomplete"),
]


@pytest.mark.parametrize(("edit", "marker"), [(e, m) for _, e, m in REPORT_EDITS], ids=[i for i, _, _ in REPORT_EDITS])
def test_evidence_not_bound_to_this_attempt_commit_shard_and_complete_suite_fails(
    world, api, run_gate, tmp_path, edit, marker
):
    api.serve_jobs(2, attempt_jobs(2))
    evidence = lay_out(tmp_path, current(world, 2))
    edit_report(evidence, SHARD_2, edit)
    code, out = run_gate(evidence, 2)
    assert_fail(code, out, marker)


@pytest.mark.parametrize(
    ("damage", "marker"),
    [
        ("flip-byte", "shard 2: coverage_sha256 is"),
        ("extra-file", "holds ['coverage.sqlite', 'notes.txt', 'report.json']"),
        ("no-coverage", "holds ['report.json']"),
        ("report-not-json", "shard 2: report.json is not valid JSON"),
        ("report-duplicate-key", "shard 2: report.json is not valid JSON"),
    ],
)
def test_damaged_or_incomplete_artifacts_fail(world, api, run_gate, tmp_path, damage, marker):
    api.serve_jobs(2, attempt_jobs(2))
    evidence = lay_out(tmp_path, current(world, 2))
    artifact = evidence / SHARD_2
    if damage == "flip-byte":
        data = bytearray((artifact / plan.COVERAGE_FILE).read_bytes())
        data[len(data) // 2] ^= 0xFF
        (artifact / plan.COVERAGE_FILE).write_bytes(bytes(data))
    elif damage == "extra-file":
        (artifact / "notes.txt").write_bytes(b"x")
    elif damage == "no-coverage":
        (artifact / plan.COVERAGE_FILE).unlink()
    elif damage == "report-not-json":
        (artifact / plan.REPORT_FILE).write_bytes(b"{not json")
    else:
        text = (artifact / plan.REPORT_FILE).read_bytes().decode("utf-8")
        (artifact / plan.REPORT_FILE).write_bytes(text.replace('{"schema"', '{"exitstatus":0,"schema"', 1).encode())
    code, out = run_gate(evidence, 2)
    assert_fail(code, out, marker)


# --- coverage integrity and the floor ----------------------------------------------------------------------------


def _replace_coverage(path: Path, root: Path, kind: str) -> None:
    path.unlink()
    if kind == "corrupt":
        path.write_bytes(b"SQLite format 3\x00" + b"\x00" * 64)
        return
    data = CoverageData(basename=str(path))
    source = root.resolve() / "src" / "crypto_core"
    try:
        if kind == "branch":
            data.add_arcs({str(source / "beta.py"): {(1, 2), (2, -1)}})
        elif kind == "outside":
            data.add_lines({str(source / "beta.py"): {1}, str(root.resolve() / "tests" / "crypto_core" / "x.py"): {1}})
        elif kind == "absent":
            data.add_lines({str(source / "beta.py"): {1}, str(source / "deleted.py"): {1}})
        else:
            data.add_lines({str(source / "beta.py"): set()})
            data.touch_files([str(source / "gamma.py")])
    finally:
        data.close()


@pytest.mark.parametrize(
    ("kind", "marker"),
    [
        ("corrupt", "shard 2: coverage data is unreadable"),
        ("branch", "shard 2: coverage holds branch data"),
        ("outside", "shard 2: coverage measured 1 files outside src/crypto_core"),
        ("absent", "shard 2: coverage names 1 files absent from this checkout"),
        ("nothing-executed", "shard 2: coverage recorded no executed line"),
    ],
)
def test_resealed_but_invalid_coverage_data_fails(world, api, run_gate, tmp_path, kind, marker):
    api.serve_jobs(2, attempt_jobs(2))
    evidence = lay_out(tmp_path, current(world, 2))
    _replace_coverage(evidence / SHARD_2 / plan.COVERAGE_FILE, world.root, kind)
    reseal(evidence, SHARD_2)
    code, out = run_gate(evidence, 2)
    assert_fail(code, out, marker)


def test_a_union_below_the_floor_fails(world, api, run_gate, tmp_path):
    api.serve_jobs(2, attempt_jobs(2))
    code, out = run_gate(lay_out(tmp_path, current(world, 2)), 2, fail_under="95")
    assert_fail(code, out, f"FAIL Required test coverage of 95% not reached. {UNION_COVERAGE}", "below the 95% floor")


def test_the_gate_module_runs_as_the_ci_command(world, api, tmp_path):
    api.serve_jobs(2, attempt_jobs(2))
    env = {**shards.shard_env(world.head, RUN_ID, 2), **base_env(world, api, 2)}
    evidence = lay_out(tmp_path, current(world, 2))

    def cli(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - this interpreter running the gate module in a test project, no shell
            [sys.executable, "-m", "scripts.crypto_core.ci_attested_gate", *args],
            cwd=world.root,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )

    passed = cli("--evidence-dir", str(evidence), "--shards", "3", "--fail-under", "70")
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert passed.stdout.rstrip().splitlines()[-1] == PASS_LINE
    failed = cli("--evidence-dir", str(evidence), "--shards", "2", "--fail-under", "70")
    assert failed.returncode == 1
    assert failed.stdout.rstrip().splitlines()[-1] == FAIL_LINE
    for shards_arg, floor_arg in (("0", "70"), ("17", "70"), ("3", "0"), ("3", "101"), ("3", "nan")):
        assert cli("--evidence-dir", str(evidence), "--shards", shards_arg, "--fail-under", floor_arg).returncode == 2
    assert cli("--evidence-dir", str(evidence), "--shards", "3").returncode == 2
