"""Verify the mandatory crypto_core CI test shards and enforce the unchanged coverage floor on their union.

The required ``tests`` job of ``.github/workflows/ci.yml`` runs this module with ``if: always()``: it runs -- and
fails -- whenever a prerequisite failed, was cancelled, was skipped or produced no evidence (a skipped job would
otherwise report success to branch protection). It exits 0 only when every condition below holds, and otherwise
prints one ``::error::`` line per defect and exits 1:

1. every required job -- ``lint`` (the Ruff gates) and the ``test-shard`` matrix -- concluded ``success``;
2. exactly one evidence directory per shard ``1..N`` exists and holds exactly ``report.json`` and
   ``coverage.sqlite``;
3. every report is well formed and names this head, this run (an earlier attempt of it at most) and its own shard,
   ran the canonical invocation without ``PYTEST_ADDOPTS``, and exited 0;
4. all reports carry the identical, duplicate-free collection; each shard selected exactly what
   :func:`ci_test_shard.partition` assigns it, so the selections are disjoint and cover the collection; every
   selected test has exactly one accepted outcome (passed, skipped, xfailed, xpassed);
5. every coverage file matches the digest its report recorded and holds line data measured only under the source
   root, and the combined data equals the exact union of the shards' lines;
6. the total of that union passes ``--fail-under`` by pytest-cov's own rule (``should_fail_under`` at the
   configured precision); shard percentages are never averaged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import coverage
from coverage.exceptions import CoverageException
from coverage.results import should_fail_under

from scripts.crypto_core.ci_test_shard import (
    ACCEPTED_OUTCOMES,
    CANONICAL_PYTEST_ARGS,
    COVERAGE_NAME,
    REPORT_NAME,
    REPORT_SCHEMA,
    canonical_args,
    file_of,
    partition,
    sha256_file,
)

REQUIRED_JOBS = ("lint", "test-shard")
EVIDENCE_PREFIX = "crypto-core-test-shard-"
_REPORT_TYPES: dict[str, type] = {
    "schema": str,
    "shard": int,
    "shard_count": int,
    "head": str,
    "run_id": str,
    "run_attempt": str,
    "invocation_args": list,
    "pytest_addopts": str,
    "exit_status": int,
    "collected": list,
    "selected": list,
    "outcomes": dict,
    "file_seconds": dict,
    "coverage_sha256": str,
}
_SHOWN = 10


@dataclass(frozen=True)
class Shard:
    index: int
    report: dict[str, Any]
    coverage_path: Path


def _sample(items: Sequence[str]) -> str:
    shown = ", ".join(items[:_SHOWN])
    return shown + (f" ... (+{len(items) - _SHOWN} more)" if len(items) > _SHOWN else "")


def check_needs(needs: object, required: Sequence[str] = REQUIRED_JOBS) -> list[str]:
    """Every required job concluded ``success``; anything else -- failure, cancelled, skipped, absent -- fails."""
    if not isinstance(needs, dict):
        return ["needs: not a JSON object"]
    errors = []
    if set(needs) != set(required):
        errors.append(f"needs: expected exactly {sorted(required)}, got {sorted(needs)}")
    for job in required:
        entry = needs.get(job)
        result = entry.get("result") if isinstance(entry, dict) else None
        if result != "success":
            errors.append(f"job {job}: result {result!r}, required 'success'")
    return errors


def load_evidence(evidence_dir: Path, shard_count: int) -> tuple[list[str], list[Shard]]:
    """Exactly one evidence directory per shard, each with exactly the report and the raw coverage data."""
    expected = {f"{EVIDENCE_PREFIX}{index}": index for index in range(1, shard_count + 1)}
    present = sorted(path.name for path in evidence_dir.iterdir()) if evidence_dir.is_dir() else []
    errors = [f"evidence: unexpected entry {name!r}" for name in present if name not in expected]
    shards = []
    for name, index in expected.items():
        directory = evidence_dir / name
        if not directory.is_dir():
            errors.append(f"shard {index}: evidence {name!r} is missing")
            continue
        files = sorted(path.name for path in directory.iterdir())
        if files != sorted((COVERAGE_NAME, REPORT_NAME)):
            errors.append(f"shard {index}: evidence holds {files}, expected {sorted((COVERAGE_NAME, REPORT_NAME))}")
            continue
        try:
            report = json.loads((directory / REPORT_NAME).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            errors.append(f"shard {index}: report is unreadable: {error}")
            continue
        shards.append(Shard(index, report, directory / COVERAGE_NAME))
    return errors, shards


def check_report(
    shard: Shard,
    shard_count: int,
    head: str,
    run_id: str,
    run_attempt: str,
    canonical: Sequence[str] = CANONICAL_PYTEST_ARGS,
) -> list[str]:
    """One shard's report: structure, identity (head, run, shard), invocation, exit status, ids and outcomes."""
    label = f"shard {shard.index}"
    report = shard.report
    if not isinstance(report, dict) or set(report) != set(_REPORT_TYPES):
        keys = sorted(report) if isinstance(report, dict) else type(report).__name__
        return [f"{label}: report fields {keys} are not {sorted(_REPORT_TYPES)}"]
    wrong = [
        key for key, kind in _REPORT_TYPES.items() if isinstance(report[key], bool) or not isinstance(report[key], kind)
    ]
    lists = ("invocation_args", "collected", "selected")
    wrong += [key for key in lists if key not in wrong and not all(isinstance(item, str) for item in report[key])]
    if "outcomes" not in wrong and not all(isinstance(value, str) for value in report["outcomes"].values()):
        wrong.append("outcomes")
    seconds = report["file_seconds"].values() if "file_seconds" not in wrong else ()
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in seconds):
        wrong.append("file_seconds")
    if wrong:
        return [f"{label}: report fields of the wrong type: {wrong}"]
    errors = []
    if report["schema"] != REPORT_SCHEMA:
        errors.append(f"{label}: schema {report['schema']!r} is not {REPORT_SCHEMA!r}")
    if report["shard"] != shard.index or report["shard_count"] != shard_count:
        errors.append(
            f"{label}: report is for shard {report['shard']}/{report['shard_count']}, not {shard.index}/{shard_count}"
        )
    if report["head"] != head:
        errors.append(f"{label}: tested head {report['head']!r} is not {head!r}")
    if report["run_id"] != run_id:
        errors.append(f"{label}: evidence of run {report['run_id']!r}, not of this run {run_id!r}")
    attempt = report["run_attempt"]
    if not attempt.isdigit() or not run_attempt.isdigit() or not 1 <= int(attempt) <= int(run_attempt):
        errors.append(f"{label}: run attempt {attempt!r} is not an attempt of this run up to {run_attempt!r}")
    if report["pytest_addopts"]:
        errors.append(f"{label}: PYTEST_ADDOPTS was set: {report['pytest_addopts']!r}")
    args = report["invocation_args"]
    if canonical_args(args) != list(canonical) or args.count(f"--ci-shard={shard.index}/{shard_count}") != 1:
        errors.append(f"{label}: invocation {args} is not the canonical shard invocation")
    if report["exit_status"] != 0:
        errors.append(f"{label}: pytest exit status {report['exit_status']}")
    collected, selected = report["collected"], report["selected"]
    if not collected:
        errors.append(f"{label}: collected no test")
    if not selected:
        errors.append(f"{label}: selected no test")
    for key, ids in (("collected", collected), ("selected", selected)):
        duplicates = sorted(node_id for node_id, count in Counter(ids).items() if count > 1)
        if duplicates:
            errors.append(f"{label}: duplicate {key} node ids: {_sample(duplicates)}")
    known = set(collected)
    foreign = [node_id for node_id in selected if node_id not in known]
    if foreign:
        errors.append(f"{label}: selected node ids outside its own collection: {_sample(foreign)}")
    outcomes = report["outcomes"]
    unselected = sorted(set(outcomes) - set(selected))
    if unselected:
        errors.append(f"{label}: outcomes for unselected node ids: {_sample(unselected)}")
    missing = [node_id for node_id in selected if node_id not in outcomes]
    if missing:
        errors.append(f"{label}: {len(missing)} selected tests never reported an outcome: {_sample(missing)}")
    rejected = sorted(
        f"{node_id} [{outcome}]" for node_id, outcome in outcomes.items() if outcome not in ACCEPTED_OUTCOMES
    )
    if rejected:
        errors.append(f"{label}: {len(rejected)} tests did not pass: {_sample(rejected)}")
    return errors


def check_partition(shards: Sequence[Shard], shard_count: int) -> list[str]:
    """One identical collection, re-partitioned here: each selection exact, together disjoint and complete."""
    reference = shards[0].report["collected"]
    errors = [
        f"shard {shard.index}: collection ({len(shard.report['collected'])} ids) differs from shard "
        f"{shards[0].index} ({len(reference)} ids)"
        for shard in shards[1:]
        if shard.report["collected"] != reference
    ]
    if errors:
        return errors
    assignment = partition(reference, shard_count)
    seen: Counter[str] = Counter()
    for shard in shards:
        expected = [node_id for node_id in reference if assignment[file_of(node_id)] == shard.index]
        if shard.report["selected"] != expected:
            errors.append(
                f"shard {shard.index}: selection ({len(shard.report['selected'])} ids) is not its partition ({len(expected)} ids)"
            )
        seen.update(shard.report["selected"])
    overlap = sorted(node_id for node_id, count in seen.items() if count > 1)
    if overlap:
        errors.append(f"{len(overlap)} node ids ran in more than one shard: {_sample(overlap)}")
    uncovered = [node_id for node_id in reference if node_id not in seen]
    if uncovered:
        errors.append(f"{len(uncovered)} collected node ids ran in no shard: {_sample(uncovered)}")
    return errors


def combine_coverage(
    shards: Sequence[Shard], combined: Path, source_root: Path, fail_under: float, out: TextIO
) -> tuple[list[str], float | None]:
    """Combine the authentic raw data, prove the result is the exact union, then apply the floor to it."""
    root = Path(os.path.realpath(source_root))
    union: dict[str, set[int]] = {}
    errors = []
    for shard in shards:
        label = f"shard {shard.index}"
        if sha256_file(shard.coverage_path) != shard.report["coverage_sha256"]:
            errors.append(f"{label}: coverage data does not match the digest its report recorded")
            continue
        data = coverage.CoverageData(basename=str(shard.coverage_path))
        try:
            data.read()
            measured = sorted(data.measured_files())
            has_arcs = data.has_arcs()
            lines = {path: set(data.lines(path) or ()) for path in measured}
        except CoverageException as error:
            errors.append(f"{label}: coverage data is unreadable: {error}")
            continue
        if has_arcs:
            errors.append(f"{label}: coverage data holds branch arcs; the gate measures lines")
        if not measured:
            errors.append(f"{label}: coverage data measured no file")
        outside = [path for path in measured if not Path(os.path.realpath(path)).is_relative_to(root)]
        if outside:
            errors.append(f"{label}: coverage measured files outside {root}: {_sample(outside)}")
        for path, numbers in lines.items():
            union.setdefault(path, set()).update(numbers)
    if errors:
        return errors, None
    if combined.exists():
        combined.unlink()
    cov = coverage.Coverage(data_file=str(combined))
    cov.combine([str(shard.coverage_path) for shard in shards], strict=True, keep=True)
    cov.save()
    data = cov.get_data()
    merged = {path: set(data.lines(path) or ()) for path in data.measured_files()}
    if merged != union:
        return ["combined coverage is not the exact union of the shards' line data"], None
    precision = cov.config.precision
    total = cov.report(ignore_errors=True, file=out, precision=precision)
    if should_fail_under(total, fail_under, precision):
        errors.append(f"coverage total {total:.2f}% of the verified union is below --fail-under={fail_under:g}")
    return errors, total


def main(argv: Sequence[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shards", type=int, required=True, help="the number of mandatory shards")
    parser.add_argument("--evidence", type=Path, required=True, help="directory of the downloaded shard evidence")
    parser.add_argument("--head", required=True, help="the commit this aggregator checked out")
    parser.add_argument("--expected-head", required=True, help="the commit of this workflow run (github.sha)")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--needs", required=True, help="toJSON(needs) of the aggregating job")
    parser.add_argument("--source-root", type=Path, required=True, help="the coverage source (src/crypto_core)")
    parser.add_argument("--fail-under", type=float, required=True)
    parser.add_argument("--combined-coverage", type=Path, required=True, help="where to write the combined data")
    args = parser.parse_args(argv)

    errors = []
    if args.shards < 1:
        errors.append(f"--shards must be positive: {args.shards}")
    if args.head != args.expected_head:
        errors.append(f"aggregator checkout {args.head!r} is not the run's commit {args.expected_head!r}")
    try:
        needs = json.loads(args.needs)
    except ValueError:
        needs = None
    errors += check_needs(needs)
    shards: list[Shard] = []
    if args.shards >= 1:
        load_errors, shards = load_evidence(args.evidence, args.shards)
        errors += load_errors
        report_errors = [
            error
            for shard in shards
            for error in check_report(shard, args.shards, args.expected_head, args.run_id, args.run_attempt)
        ]
        errors += report_errors
        if not load_errors and not report_errors:
            errors += check_partition(shards, args.shards)
    total = None
    if not errors:
        coverage_errors, total = combine_coverage(
            shards, args.combined_coverage, args.source_root, args.fail_under, out
        )
        errors += coverage_errors

    tally: Counter[str] = Counter()
    for shard in shards:
        report = shard.report
        if isinstance(report, dict) and isinstance(report.get("outcomes"), dict):
            outcomes = Counter(map(str, report["outcomes"].values()))
            tally.update(outcomes)
            seconds = report.get("file_seconds")
            numeric = isinstance(seconds, dict) and all(isinstance(value, (int, float)) for value in seconds.values())
            busy = f"{sum(seconds.values()):.0f}" if numeric else "unknown"
            selected = report.get("selected")
            count = len(selected) if isinstance(selected, list) else "unknown"
            print(
                f"shard {shard.index}: {count} selected, {dict(sorted(outcomes.items()))}, test seconds {busy}",
                file=out,
            )
    if shards and isinstance(shards[0].report, dict) and isinstance(shards[0].report.get("collected"), list):
        collected = shards[0].report["collected"]
        digest = hashlib.sha256("\n".join(map(str, collected)).encode("utf-8")).hexdigest()
        print(f"collection: {len(collected)} node ids, sha256 {digest}", file=out)
    print(f"outcomes: {dict(sorted(tally.items()))}", file=out)
    if total is not None:
        print(f"coverage of the verified union: {total:.2f}% (fail-under {args.fail_under:g})", file=out)
    for error in errors:
        print(f"::error::{error}", file=out)
    print(f"CRYPTO_CORE_CI_TESTS_VERDICT={'FAIL' if errors else 'PASS'}", file=out)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
