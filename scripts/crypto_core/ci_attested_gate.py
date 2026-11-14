"""Required ``tests`` check of the crypto_core CI: accept only attempt-attested shard evidence.

Runs as the ``tests`` job of ``.github/workflows/ci.yml`` (``if: always()``, so the required check is never
skipped and always decides), after ``lint`` and every ``test-shard`` job, in a fresh checkout of the tested commit::

    python -m scripts.crypto_core.ci_attested_gate --evidence-dir DIR --shards N --fail-under 70

It exits 0 only if every check below passes for THIS workflow run and THIS run attempt:

1. ``needs``: ``lint`` and ``test-shard`` report ``success``.  Necessary, never sufficient: an aggregate matrix
   result says nothing about which attempt produced which shard.
2. Producers: the GitHub Actions API lists, for this run and exactly this attempt, one job named ``lint`` and one
   job named ``pytest shard K of N`` for every K, each with this ``run_attempt``, this run's head SHA,
   ``status=completed`` and ``conclusion=success``, and no other ``pytest shard`` job.  A job carried over from an
   earlier attempt, a cancelled, failed, skipped or unfinished producer, and any missing, ambiguous, incomplete or
   unreadable metadata fail the check.
3. Evidence: ``DIR`` holds exactly the N artifacts named for this run and this attempt, each with exactly
   ``report.json`` and ``coverage.sqlite``.  Every report names this repository, run, attempt (exactly: an earlier
   attempt never satisfies a later one), commit, tree and checkout root, its own shard, the canonical invocation and
   environment, this interpreter's major.minor version and exit status 0, and it seals the SHA-256 of its coverage.
4. Suite: all shards collected the same duplicate-free tests in the same file order, each ran exactly its whole-file
   share of ``ci_shard_plan.assign_files``, the shares are disjoint and cover the collection, and every selected test
   passed, skipped, xfailed or xpassed.
5. Source universe, derived from the gate's own checkout and never from any artifact: the reportable Python files of
   ``src/crypto_core`` in the committed tree, by coverage.py's own discovery rule (``find_python_files``: a plainly
   named ``.py``/``.pyw`` file in a chain of packages below the source directory).  It must equal what that rule
   finds in this checkout, every file must be a regular file at its own path, and no entry under the source
   directory of the committed tree may be a symbolic link or a submodule.
6. Coverage, evaluated only after 1-5 pass: coverage records every file it discovers, executed or not, so every
   shard's coverage file must be readable statement data naming exactly the source universe at the paths coverage
   gives them in this checkout -- a missing file, and any foreign, traversing, aliased or otherwise noncanonical
   path, fails -- with every recorded line inside its committed file.  Their exact line union is rebuilt and
   re-verified, coverage's own report over exactly the source universe gives the total (an unanalysable file fails
   instead of leaving the denominator), its per-file analysis must account for the same statements, and the union
   must reach ``--fail-under`` by coverage's own fail-under rule, the rule the serial gate applied through
   pytest-cov.  Shard percentages are never averaged.

Any violation, error or interruption exits nonzero.  ``CRYPTO_CORE_TESTS_GATE=PASS`` is printed only as the last
line of a run in which every check passed.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import tokenize
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from coverage import Coverage, CoverageData
from coverage.exceptions import CoverageException
from coverage.files import find_python_files
from coverage.results import should_fail_under

from scripts.crypto_core import ci_shard_plan as plan

VERDICT = "CRYPTO_CORE_TESTS_GATE"
CREDENTIAL_ENV = "GITHUB_TOKEN"
NEEDS_ENV = "CRYPTO_CORE_CI_NEEDS"
RUN_HEAD_ENV = "CRYPTO_CORE_CI_RUN_HEAD_SHA"
REQUIRED_NEEDS = ("lint", "test-shard")
PAGE_SIZE = 100
MAX_PAGES = 10
HTTP_TIMEOUT_SECONDS = 30
RETRY_DELAYS_SECONDS = (10, 20)
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_POSITIVE_INT = re.compile(r"[1-9][0-9]{0,18}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_REPORT_FIELDS = frozenset(
    {
        "schema",
        "repository",
        "run_id",
        "run_attempt",
        "head",
        "tree",
        "root",
        "python",
        "shard_index",
        "shard_count",
        "invocation",
        "environment",
        "collection",
        "selected",
        "outcomes",
        "exitstatus",
        "coverage_sha256",
    }
)
_JOB_FIELDS = (("id", int), ("name", str), ("run_id", int), ("run_attempt", int), ("status", str), ("head_sha", str))
# The file-name rule of coverage.py's ``find_python_files``, verbatim: a file it measures although nothing ran it.
_SOURCE_FILE_NAME = re.compile(r"^[^.#~!$@%^&*()+=,]+\.pyw?$")
_REGULAR_FILE_MODES = ("100644", "100755")


class GateError(Exception):
    """A precondition of the gate itself failed."""


@dataclass(frozen=True)
class Context:
    """The workflow run attempt this gate judges, and its own checkout."""

    repository: str
    run_id: int
    run_attempt: int
    sha: str
    run_head_sha: str
    api_url: str
    root: Path
    tree: str
    needs: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class SourceUniverse:
    """The source files whose statements form the coverage denominator, from the gate's own checkout."""

    files: tuple[str, ...]  # repository-relative POSIX paths, sorted
    paths: Mapping[str, str]  # the exact path coverage records for each file in this checkout -> its relative path
    line_counts: Mapping[str, int]  # relative path -> physical lines of the committed file


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> object:
    raise ValueError(f"non-finite JSON number {name}")


def _loads(text: str) -> object:
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _brief(value: object) -> str:
    if isinstance(value, (list, dict)) and len(value) > 8:
        return f"<{type(value).__name__} of {len(value)}>"
    return repr(value)


def _git(root: Path, *args: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise GateError("git is not available to the gate")
    completed = subprocess.run(  # noqa: S603 - fixed git argv, no shell, no caller-supplied executable
        [executable, *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace", check=False
    )
    if completed.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed in the gate's checkout: {completed.stderr.strip()[:300]}")
    return completed.stdout.strip()


def _api_base(raw: str) -> str | None:
    try:
        parts = urllib.parse.urlsplit(raw)
        host = parts.hostname
    except ValueError:
        return None
    if parts.query or parts.fragment or parts.username or parts.password or not host:
        return None
    # Plain http is accepted only for a loopback test double: the token never leaves the machine.
    if parts.scheme == "https" or (parts.scheme == "http" and host in LOOPBACK_HOSTS):
        return raw.rstrip("/")
    return None


def read_context(environ: Mapping[str, str], cwd: Path) -> tuple[Context | None, list[str]]:
    problems: list[str] = []
    repository = environ.get("GITHUB_REPOSITORY", "")
    run_id = environ.get("GITHUB_RUN_ID", "")
    run_attempt = environ.get("GITHUB_RUN_ATTEMPT", "")
    sha = environ.get("GITHUB_SHA", "")
    run_head_sha = environ.get(RUN_HEAD_ENV, "")
    for name, value, pattern in (
        ("GITHUB_REPOSITORY", repository, _REPOSITORY),
        ("GITHUB_RUN_ID", run_id, _POSITIVE_INT),
        ("GITHUB_RUN_ATTEMPT", run_attempt, _POSITIVE_INT),
        ("GITHUB_SHA", sha, _COMMIT),
        (RUN_HEAD_ENV, run_head_sha, _COMMIT),
    ):
        if pattern.fullmatch(value) is None:
            problems.append(f"{name} is missing or malformed")
    api_url = _api_base(environ.get("GITHUB_API_URL", ""))
    if api_url is None:
        problems.append("GITHUB_API_URL is missing or not an https URL")
    token = environ.get(CREDENTIAL_ENV, "")
    if not token:
        problems.append(f"{CREDENTIAL_ENV} is not set, so the producer jobs cannot be attested")
    needs = environ.get(NEEDS_ENV)
    if needs is None:
        problems.append(f"{NEEDS_ENV} is not set")
    root = cwd.resolve()
    head = tree = dirty = ""
    try:
        head = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
        tree = _git(root, "rev-parse", "--verify", "HEAD^{tree}")
        dirty = _git(root, "status", "--porcelain", "--untracked-files=no")
    except GateError as error:
        problems.append(str(error))
    else:
        if head != sha:
            problems.append(f"the gate's checkout {head} is not GITHUB_SHA {sha}")
        if dirty:
            problems.append("tracked files of the gate's checkout differ from its commit")
    if problems or api_url is None or needs is None:
        return None, problems
    context = Context(
        repository=repository,
        run_id=int(run_id),
        run_attempt=int(run_attempt),
        sha=sha,
        run_head_sha=run_head_sha,
        api_url=api_url,
        root=root,
        tree=tree,
        needs=needs,
        token=token,
    )
    return context, []


def check_needs(raw: str) -> list[str]:
    try:
        needs = _loads(raw)
    except ValueError:
        return [f"{NEEDS_ENV} is not valid JSON"]
    if not isinstance(needs, dict) or set(needs) != set(REQUIRED_NEEDS):
        return [f"needs must name exactly {', '.join(REQUIRED_NEEDS)}"]
    violations = []
    for name in REQUIRED_NEEDS:
        entry = needs[name]
        result = entry.get("result") if isinstance(entry, dict) else None
        if result != "success":
            violations.append(f"needs.{name}.result is {result!r}, not 'success'")
    return violations


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface a redirect as an HTTP error instead of following it with the token."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get_json(url: str, token: str) -> tuple[object, str | None, bool]:
    """``(payload, error, transient)`` for one authenticated GET."""
    request = urllib.request.Request(url)  # noqa: S310 - validated https GitHub API base or loopback test double
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "crypto-core-ci-tests-gate")
    # The ephemeral job token (actions: read) is never printed, persisted or sent on a redirect.
    request.add_unredirected_header("Authorization", "Bearer " + token)
    body = b""
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        return None, f"GitHub API answered HTTP {status}", status >= 500 or status == 429
    except OSError as error:  # URLError, timeouts and connection failures
        return None, f"GitHub API unreachable ({type(error).__name__})", True
    try:
        return _loads(body.decode("utf-8")), None, False
    except ValueError:
        return None, "GitHub API returned malformed JSON", False


def _job_problem(job: object) -> str | None:
    if not isinstance(job, dict):
        return "a job entry is not a JSON object"
    for name, kind in _JOB_FIELDS:
        if type(job.get(name)) is not kind:
            return f"job metadata field {name!r} is missing or not {kind.__name__}"
    if "conclusion" not in job or not (job["conclusion"] is None or isinstance(job["conclusion"], str)):
        return "job metadata field 'conclusion' is missing or invalid"
    return None


def list_attempt_jobs(ctx: Context) -> tuple[list[dict] | None, str | None, bool]:
    """All jobs of this run attempt, paginated to completion: ``(jobs, error, transient)``."""
    jobs: list[dict] = []
    seen: set[int] = set()
    total: int | None = None
    base = f"{ctx.api_url}/repos/{ctx.repository}/actions/runs/{ctx.run_id}/attempts/{ctx.run_attempt}/jobs"
    for page in range(1, MAX_PAGES + 1):
        payload, error, transient = _get_json(f"{base}?per_page={PAGE_SIZE}&page={page}", ctx.token)
        if error is not None:
            return None, f"listing the jobs of run {ctx.run_id} attempt {ctx.run_attempt}: {error}", transient
        if not isinstance(payload, dict) or type(payload.get("total_count")) is not int:
            return None, "the jobs response has no integer total_count", False
        page_jobs = payload.get("jobs")
        if not isinstance(page_jobs, list) or len(page_jobs) > PAGE_SIZE:
            return None, "the jobs response has no valid jobs page", False
        if total is None:
            total = payload["total_count"]
            if not 0 <= total <= PAGE_SIZE * MAX_PAGES:
                return None, f"the jobs response has an implausible total_count {total}", False
        elif payload["total_count"] != total:
            return None, f"total_count changed from {total} to {payload['total_count']} between pages", True
        for job in page_jobs:
            problem = _job_problem(job)
            if problem is not None:
                return None, problem, False
            if job["id"] in seen:
                return None, f"job {job['id']} is listed twice", False
            seen.add(job["id"])
            jobs.append(job)
        if len(jobs) == total:
            return jobs, None, False
        if len(jobs) > total or not page_jobs:
            return None, f"incomplete jobs listing: {len(jobs)} jobs for total_count {total}", True
    return None, f"the jobs listing did not complete within {MAX_PAGES} pages", False


def judge_producers(jobs: list[dict], ctx: Context, shards: int) -> tuple[list[str], list[str]]:
    """``(violations, unfinished)`` for the producer jobs of this exact run attempt."""
    required = [plan.LINT_JOB] + [plan.shard_job_name(index, shards) for index in range(1, shards + 1)]
    by_name: dict[str, list[dict]] = {}
    for job in jobs:
        by_name.setdefault(job["name"], []).append(job)
    violations: list[str] = []
    unfinished: list[str] = []
    for name in required:
        found = by_name.get(name, [])
        if len(found) != 1:
            violations.append(
                f"producer {name!r}: {len(found)} jobs in run {ctx.run_id} attempt {ctx.run_attempt}, expected exactly 1"
            )
            continue
        job = found[0]
        where = f"producer {name!r} (job {job['id']})"
        if job["run_id"] != ctx.run_id:
            violations.append(f"{where} belongs to run {job['run_id']}, not {ctx.run_id}")
        if job["run_attempt"] != ctx.run_attempt:
            violations.append(f"{where} ran in attempt {job['run_attempt']}, not the current attempt {ctx.run_attempt}")
        if job["head_sha"] != ctx.run_head_sha:
            violations.append(f"{where} ran for head {job['head_sha']}, not {ctx.run_head_sha}")
        if job["status"] != "completed":
            unfinished.append(f"{where} is {job['status']!r}, not completed")
        elif job["conclusion"] != "success":
            violations.append(f"{where} concluded {job['conclusion']!r}, not 'success'")
    for name in sorted(by_name):
        if name.startswith(plan.SHARD_JOB_PREFIX) and name not in required:
            violations.append(f"unexpected producer job {name!r} in this attempt")
    return violations, unfinished


def attest_producers(ctx: Context, shards: int) -> list[str]:
    """Violations of the producer attestation; transient API failures and unfinished jobs are retried, bounded."""
    delays = list(RETRY_DELAYS_SECONDS)
    while True:
        jobs, error, transient = list_attempt_jobs(ctx)
        if jobs is not None:
            violations, unfinished = judge_producers(jobs, ctx, shards)
            if violations or not unfinished or not delays:
                return violations + unfinished
        elif not transient or not delays:
            return [error or "the jobs listing failed"]
        time.sleep(delays.pop(0))


def _artifact_problem(entry: Path) -> str | None:
    if entry.is_symlink() or not entry.is_dir():
        return "is not a directory"
    names = sorted(child.name for child in entry.iterdir())
    if names != sorted((plan.COVERAGE_FILE, plan.REPORT_FILE)):
        return f"holds {names}, expected exactly {plan.REPORT_FILE} and {plan.COVERAGE_FILE}"
    for name in names:
        if (entry / name).is_symlink() or not (entry / name).is_file():
            return f"{name} is not a regular file"
    return None


def _report_problems(report: object, index: int, ctx: Context, shards: int, coverage_sha256: str) -> list[str]:
    if not isinstance(report, dict):
        return ["the report is not a JSON object"]
    if set(report) != _REPORT_FIELDS:
        missing = sorted(_REPORT_FIELDS - set(report))
        unexpected = sorted(set(report) - _REPORT_FIELDS)
        return [f"report fields differ: missing {missing}, unexpected {unexpected}"]
    expected = {
        "schema": plan.SCHEMA,
        "repository": ctx.repository,
        "run_id": ctx.run_id,
        "run_attempt": ctx.run_attempt,
        "head": ctx.sha,
        "tree": ctx.tree,
        "root": str(ctx.root),
        "shard_index": index,
        "shard_count": shards,
        "invocation": plan.shard_invocation(index, shards),
        "environment": plan.CANONICAL_ENVIRONMENT,
        "exitstatus": 0,
        "coverage_sha256": coverage_sha256,
    }
    problems = [
        f"{name} is {_brief(report[name])}, expected {_brief(value)}"
        for name, value in expected.items()
        if type(report[name]) is not type(value) or report[name] != value
    ]
    python = report["python"]
    if not isinstance(python, str) or python.split(".")[:2] != list(platform.python_version_tuple()[:2]):
        problems.append(f"python {python!r} differs from the gate's {platform.python_version()}")
    for name in ("collection", "selected"):
        if not isinstance(report[name], list) or not all(isinstance(item, str) for item in report[name]):
            problems.append(f"{name} is not a list of node ids")
    outcomes = report["outcomes"]
    if not isinstance(outcomes, dict) or not all(isinstance(value, str) for value in outcomes.values()):
        problems.append("outcomes is not a mapping of node id to outcome")
    return problems


def load_evidence(evidence_dir: Path, ctx: Context, shards: int) -> tuple[dict[int, tuple[dict, Path]], list[str]]:
    """Reports and coverage files of exactly this run attempt's shard artifacts."""
    if not evidence_dir.is_dir():
        return {}, [
            f"no artifact of run {ctx.run_id} attempt {ctx.run_attempt} was downloaded ({evidence_dir} missing)"
        ]
    expected = {plan.artifact_name(ctx.run_id, ctx.run_attempt, index, shards): index for index in range(1, shards + 1)}
    present = {entry.name: entry for entry in evidence_dir.iterdir()}
    violations = [
        f"unexpected evidence {name!r}: not an artifact of run {ctx.run_id} attempt {ctx.run_attempt}"
        for name in sorted(set(present) - set(expected))
    ]
    loaded: dict[int, tuple[dict, Path]] = {}
    for name, index in expected.items():
        entry = present.get(name)
        if entry is None:
            violations.append(f"shard {index}: artifact {name!r} of the current attempt is missing")
            continue
        problem = _artifact_problem(entry)
        if problem is not None:
            violations.append(f"shard {index}: artifact {name!r} {problem}")
            continue
        try:
            report = _loads((entry / plan.REPORT_FILE).read_bytes().decode("utf-8"))
        except (OSError, ValueError) as error:
            violations.append(f"shard {index}: {plan.REPORT_FILE} is not valid JSON ({type(error).__name__})")
            continue
        coverage_file = entry / plan.COVERAGE_FILE
        problems = _report_problems(report, index, ctx, shards, hashlib.sha256(coverage_file.read_bytes()).hexdigest())
        if problems:
            violations.extend(f"shard {index}: {problem}" for problem in problems)
            continue
        loaded[index] = (report, coverage_file)
    return loaded, violations


def check_suite(reports: dict[int, dict], shards: int) -> list[str]:
    """Identical complete collections, exact whole-file plan shares, and only accepted outcomes."""
    reference = reports[1]["collection"]
    reference_set = set(reference)
    if not reference:
        return ["shard 1 collected no tests"]
    reference_files = [path for path, _ in plan.files_in_order(reference)]
    violations: list[str] = []
    for index, report in sorted(reports.items()):
        collection = report["collection"]
        if len(set(collection)) != len(collection):
            violations.append(f"shard {index}: the collection lists a node id twice")
        if set(collection) != reference_set:
            missing = len(reference_set - set(collection))
            extra = len(set(collection) - reference_set)
            violations.append(f"shard {index}: collected another suite than shard 1 ({missing} missing, {extra} extra)")
        elif [path for path, _ in plan.files_in_order(collection)] != reference_files:
            violations.append(f"shard {index}: collected the test files in another order than shard 1")
    if violations:
        return violations
    plan_shares = plan.plan_selection(reference, shards)
    covered: set[str] = set()
    for index, report in sorted(reports.items()):
        selected = report["selected"]
        chosen = set(selected)
        share = set(plan_shares[index])
        if len(chosen) != len(selected):
            violations.append(f"shard {index}: the selection lists a node id twice")
        if not chosen:
            violations.append(f"shard {index}: selected no tests")
        if chosen != share:
            violations.append(
                f"shard {index}: the selection is not its whole-file plan share "
                f"({len(share - chosen)} missing, {len(chosen - share)} foreign)"
            )
        if covered & chosen:
            violations.append(f"shard {index}: the selection overlaps another shard")
        covered |= chosen
        outcomes = report["outcomes"]
        if set(outcomes) != chosen:
            violations.append(
                f"shard {index}: outcomes cover {len(set(outcomes) & chosen)} of {len(chosen)} selected tests "
                f"and {len(set(outcomes) - chosen)} unselected ones"
            )
        rejected = sorted(nodeid for nodeid, outcome in outcomes.items() if outcome not in plan.ACCEPTED_OUTCOMES)
        if rejected:
            violations.append(
                f"shard {index}: {len(rejected)} tests did not pass, e.g. {rejected[0]} -> {outcomes[rejected[0]]}"
            )
    if covered != reference_set:
        violations.append(
            f"the selections cover {len(covered & reference_set)} of {len(reference_set)} collected tests"
        )
    return violations


def _committed_files(ctx: Context) -> tuple[set[str], list[str]]:
    """Regular files under the source directory of the committed tree, and its entries that are anything else."""
    listing = _git(ctx.root, "ls-tree", "-r", "-z", "--full-tree", ctx.tree, "--", plan.SOURCE_DIR)
    files: set[str] = set()
    problems: list[str] = []
    for record in listing.split("\0"):
        meta, _, path = record.partition("\t")
        if not path.startswith(plan.SOURCE_DIR + "/"):
            continue
        mode = meta.split(" ", 1)[0]
        if mode in _REGULAR_FILE_MODES:
            files.add(path)
        else:  # 120000 is a symbolic link, 160000 a submodule: neither has one unambiguous source identity
            problems.append(f"{path} in the committed tree has mode {mode}, not a regular file")
    return files, problems


def _reportable(path: str, packages: set[str]) -> bool:
    """coverage.py's ``find_python_files`` rule: a plainly named file in a chain of packages below the source dir."""
    directory, _, name = path.rpartition("/")
    if _SOURCE_FILE_NAME.match(name) is None:
        return False
    while directory != plan.SOURCE_DIR:
        if directory not in packages:
            return False
        directory = directory.rpartition("/")[0]
    return True


def _line_count(path: Path) -> int:
    """Physical lines of a Python source file, numbered as the interpreter numbers them."""
    with tokenize.open(path) as handle:  # the source encoding, and universal newlines like the tokenizer
        text = handle.read()
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def source_universe(ctx: Context) -> tuple[SourceUniverse | None, list[str]]:
    """The reportable Python files of ``src/crypto_core`` in the tested commit, from the gate's own checkout alone.

    Besides every file a test executes, coverage measures every file its own discovery finds under the source
    directory, executed or not, so each shard's coverage must name exactly these files.  They are the committed
    tree's files under coverage's discovery rule, and coverage's discovery in this checkout must find exactly them.
    """
    try:
        committed, problems = _committed_files(ctx)
    except GateError as error:
        return None, [str(error)]
    packages = {path.rpartition("/")[0] for path in committed if path.rpartition("/")[2] == "__init__.py"}
    files = sorted(path for path in committed if _reportable(path, packages))
    if not files:
        problems.append(f"the committed tree {ctx.tree} holds no reportable Python file under {plan.SOURCE_DIR}")
    source_root = ctx.root.joinpath(*plan.SOURCE_DIR.split("/"))
    discovered = {Path(name).relative_to(ctx.root).as_posix() for name in find_python_files(str(source_root), False)}
    extra = sorted(discovered - set(files))
    if extra:
        problems.append(
            f"coverage's own discovery in this checkout finds {len(extra)} source files that the committed tree "
            f"does not hold, e.g. {extra[0]}"
        )
    absent = sorted(set(files) - discovered)
    if absent:
        problems.append(
            f"coverage's own discovery in this checkout misses {len(absent)} committed source files, e.g. {absent[0]}"
        )
    paths: dict[str, str] = {}
    line_counts: dict[str, int] = {}
    for relative in files:
        path = ctx.root.joinpath(*relative.split("/"))
        # The checkout's file is the committed file only at its own path: no link, junction or alias in between.
        resolved = os.path.realpath(path)
        if resolved != str(path) or not os.path.isfile(resolved):
            problems.append(f"{relative} is not a regular file at its own path in this checkout ({resolved})")
            continue
        try:
            line_counts[relative] = _line_count(path)
        except (OSError, SyntaxError, ValueError) as error:
            problems.append(f"{relative} is not readable Python source ({type(error).__name__})")
            continue
        paths[str(path)] = relative
    if problems:
        return None, problems
    return SourceUniverse(files=tuple(files), paths=paths, line_counts=line_counts), []


def _shard_coverage_problems(index: int, executed: dict[str, set[int]], universe: SourceUniverse) -> list[str]:
    """A shard's coverage must name exactly the source universe, by exact path, with lines inside each file."""
    problems: list[str] = []
    foreign = sorted(name for name in executed if name not in universe.paths)
    if foreign:
        problems.append(
            f"shard {index}: coverage names {len(foreign)} paths that are not the canonical path of a source file of "
            f"this checkout, e.g. {foreign[0]!r}"
        )
    missing = sorted(relative for name, relative in universe.paths.items() if name not in executed)
    if missing:
        problems.append(
            f"shard {index}: coverage omits {len(missing)} of the {len(universe.files)} source files of "
            f"{plan.SOURCE_DIR}, e.g. {missing[0]}"
        )
    for name, relative in sorted(universe.paths.items(), key=lambda item: item[1]):
        count = universe.line_counts[relative]
        # Line 0 is the module prologue on Python 3.11+; any line past the end is data of another source.
        beyond = sorted(number for number in executed.get(name, ()) if not 0 <= number <= count)
        if beyond:
            problems.append(
                f"shard {index}: coverage records line {beyond[-1]} of {relative}, which has {count} lines "
                "in this checkout"
            )
            break
    if not any(executed.values()):
        problems.append(f"shard {index}: coverage recorded no executed line")
    return problems


def _merge_shard(
    index: int, path: Path, universe: SourceUniverse, union: CoverageData, lines: dict[str, set[int]]
) -> list[str]:
    """Verify one shard's coverage against the source universe; merge it into the union only when it is complete."""
    data = CoverageData(basename=str(path))
    try:
        data.read()
        if data.has_arcs():
            return [f"shard {index}: coverage holds branch data; the serial gate measured statements"]
        executed = {name: set(data.lines(name) or ()) for name in data.measured_files()}
        problems = _shard_coverage_problems(index, executed, universe)
        if not problems:
            for name, numbers in executed.items():
                lines.setdefault(name, set()).update(numbers)
            union.update(data)
        return problems
    except (CoverageException, sqlite3.Error) as error:
        return [f"shard {index}: coverage data is unreadable: {error}"]
    finally:
        data.close()


def _report_union(union_file: str, universe: SourceUniverse, out: TextIO) -> tuple[float, int, int, int] | str:
    """Coverage's own statement report over exactly the source universe: ``(total, precision, statements, missed)``."""
    reporter = Coverage(data_file=union_file, source=[plan.SOURCE_DIR], config_file=True)
    morfs = sorted(universe.paths)
    try:
        reporter.load()
        precision = int(reporter.get_option("report:precision"))
        # ignore_errors=False: a source file coverage cannot analyse fails the gate instead of leaving the denominator.
        total = reporter.report(morfs=morfs, ignore_errors=False, file=out, precision=precision)
        statements = missed = 0
        for morf in morfs:
            _, executable, _, missing, _ = reporter.analysis2(morf)
            statements += len(executable)
            missed += len(missing)
        return total, precision, statements, missed
    except (CoverageException, OSError, ValueError) as error:
        return f"the coverage report over the verified union failed: {type(error).__name__}: {error}"
    finally:
        with contextlib.suppress(CoverageException):
            reporter.get_data().close()


def check_coverage(
    coverage_files: dict[int, Path], universe: SourceUniverse, fail_under: float, out: TextIO
) -> list[str]:
    """Verify every shard's coverage against the source universe, rebuild their exact union, apply the floor to it."""
    lines: dict[str, set[int]] = {}
    problems: list[str] = []
    reported: tuple[float, int, int, int] | str = "the coverage union was not reported"
    with tempfile.TemporaryDirectory(prefix="crypto-core-coverage-union-", ignore_cleanup_errors=True) as work:
        union_file = os.path.join(work, "union.coverage")
        union = CoverageData(basename=union_file)
        try:
            for index, path in sorted(coverage_files.items()):
                problems += _merge_shard(index, path, universe, union, lines)
            if problems:
                return problems
            if union.measured_files() != set(universe.paths):
                return ["the coverage union lists other files than the source universe"]
            differing = sorted(
                universe.paths[name] for name, executed in lines.items() if set(union.lines(name) or ()) != executed
            )
            if differing:
                return [f"the coverage union differs from the shards' line union in {differing[0]}"]
        finally:
            union.close()
        reported = _report_union(union_file, universe, out)
    if isinstance(reported, str):
        return [reported]
    total, precision, statements, missed = reported
    analysed = 100.0 * (statements - missed) / statements if statements else 100.0
    if not math.isclose(total, analysed, rel_tol=0.0, abs_tol=1e-9):
        return [
            f"coverage's report total {total!r} is not its own analysis of the {len(universe.files)} source files "
            f"({statements} statements, {missed} missed)"
        ]
    out.write(
        f"Coverage union of all {len(universe.files)} source files of {plan.SOURCE_DIR}: "
        f"{statements} statements, {missed} missed\n"
    )
    failed = should_fail_under(total, fail_under, precision)
    out.write(
        f"{'FAIL ' if failed else ''}Required test coverage of {fail_under:g}% "
        f"{'not reached' if failed else 'reached'}. Total coverage: {total:.2f}%\n"
    )
    if failed:
        return [f"coverage of the verified union, {total:.2f}%, is below the {fail_under:g}% floor"]
    return []


def _section(out: TextIO, name: str, problems: list[str], ok: str) -> None:
    out.write(f"[{name}] {'FAIL' if problems else 'ok'}: {'; '.join(problems[:3]) if problems else ok}\n")


def _verdict(out: TextIO, violations: list[str]) -> int:
    if violations:
        out.write(f"{len(violations)} violations:\n")
        for violation in violations:
            out.write(f"  - {violation}\n")
        out.write(f"{VERDICT}=FAIL\n")
        return 1
    out.write(f"{VERDICT}=PASS\n")
    return 0


def run(evidence_dir: Path, shards: int, fail_under: float, environ: Mapping[str, str], cwd: Path, out: TextIO) -> int:
    out.write(f"crypto_core tests gate: {shards} shards, coverage floor {fail_under:g}%\n")
    ctx, problems = read_context(environ, cwd)
    if ctx is None:
        return _verdict(out, problems)
    out.write(f"run {ctx.run_id} attempt {ctx.run_attempt}, commit {ctx.sha}, tree {ctx.tree}\n")
    needs = check_needs(ctx.needs)
    _section(out, "needs", needs, "lint and test-shard succeeded")
    producers = attest_producers(ctx, shards)
    _section(out, "producers", producers, f"lint and {shards} shard jobs completed successfully in this attempt")
    evidence, evidence_problems = load_evidence(evidence_dir, ctx, shards)
    _section(out, "evidence", evidence_problems, f"{shards} artifacts of this attempt, each bound to its shard")
    violations = needs + producers + evidence_problems
    if not evidence_problems:
        suite = check_suite({index: report for index, (report, _) in evidence.items()}, shards)
        sizes = " / ".join(str(len(evidence[index][0]["selected"])) for index in sorted(evidence))
        tally = Counter(outcome for report, _ in evidence.values() for outcome in report["outcomes"].values())
        summary = f"{len(evidence[1][0]['collection'])} tests collected identically; ran {sizes}; {dict(sorted(tally.items()))}"
        _section(out, "suite", suite, summary)
        violations += suite
    universe, source_problems = source_universe(ctx)
    found = f"{len(universe.files)} reportable files of {plan.SOURCE_DIR} in tree {ctx.tree}" if universe else ""
    _section(out, "source", source_problems, f"{found}, exactly as coverage itself discovers them in this checkout")
    violations += source_problems
    if violations or universe is None:
        return _verdict(
            out, [*violations, "coverage was not evaluated: the shard evidence or the source universe is not verified"]
        )
    coverage = check_coverage({index: path for index, (_, path) in evidence.items()}, universe, fail_under, out)
    _section(out, "coverage", coverage, "the verified union over every source file reaches the floor")
    return _verdict(out, coverage)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ci_attested_gate", description="Required crypto_core tests check.")
    parser.add_argument("--evidence-dir", type=Path, required=True, help="downloaded artifacts of this attempt")
    parser.add_argument("--shards", type=int, required=True, help="number of pytest shards")
    parser.add_argument("--fail-under", type=float, required=True, help="coverage floor of the union, in percent")
    args = parser.parse_args(argv)
    if not 1 <= args.shards <= plan.MAX_SHARDS:
        parser.error(f"--shards must be within 1..{plan.MAX_SHARDS}")
    if not 0 < args.fail_under <= 100:
        parser.error("--fail-under must be within (0, 100]")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    code = run(args.evidence_dir, args.shards, args.fail_under, os.environ, Path.cwd(), sys.stdout)
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
