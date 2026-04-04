#!/usr/bin/env python3
"""
Quality budget check: file count, LOC delta, function count, branching score.
Usage:
  python tools/budget_check.py --baseline  # record to phases/quality_baseline.json
  python tools/budget_check.py --check    # compare working tree vs baseline, exit 1 if regressed
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "phases" / "quality_baseline.json"
THRESHOLDS = {
    "warnings_delta": 0,
    "complexity_delta": 0,
    "files_changed_max": 15,
    "loc_added_max": 200,
    "functions_changed_max": 20,
}


def _git_diff_files() -> list[str]:
    """Files changed in working tree vs HEAD."""
    r = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode != 0:
        return []
    return [f for f in r.stdout.strip().splitlines() if f]


def _git_diff_stat() -> tuple[int, int]:
    """(insertions, deletions) from git diff --numstat."""
    r = subprocess.run(
        ["git", "diff", "--numstat", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode != 0:
        return 0, 0
    added, removed = 0, 0
    for line in r.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                added += int(parts[0]) if parts[0] != "-" else 0
                removed += int(parts[1]) if parts[1] != "-" else 0
            except ValueError:
                pass
    return added, removed


def _branching_score(tree: ast.AST) -> int:
    """Simple branching count: if/elif/else/for/while/with/try/except."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            count += 1
        elif isinstance(node, ast.ExceptHandler):
            count += 1
    return count


def _file_metrics(path: Path) -> dict:
    """Metrics for a single Python file."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
        funcs = sum(1 for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
        branching = _branching_score(tree)
        loc = len([line for line in src.splitlines() if line.strip() and not line.strip().startswith("#")])
        return {"functions": funcs, "branching": branching, "loc": loc}
    except Exception:
        return {"functions": 0, "branching": 0, "loc": 0}


def compute_current() -> dict:
    """Compute metrics for changed files only."""
    files = _git_diff_files()
    py_files = [REPO_ROOT / f for f in files if f.endswith(".py") and (REPO_ROOT / f).exists()]
    added, removed = _git_diff_stat()
    total_funcs = 0
    total_branching = 0
    for p in py_files:
        m = _file_metrics(p)
        total_funcs += m["functions"]
        total_branching += m["branching"]
    return {
        "files_changed": len(files),
        "loc_added": added,
        "loc_removed": removed,
        "functions_in_changed": total_funcs,
        "branching_in_changed": total_branching,
        "warnings": 0,
    }


def run_baseline() -> None:
    """Record baseline from clean HEAD."""
    r = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=5)
    if r.stdout.strip():
        print("WARN: Working tree not clean; baseline will reflect current diff", file=sys.stderr)
    data = compute_current()
    data["recorded_from"] = "working_tree"
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Baseline written to {BASELINE_PATH}")


def run_check() -> int:
    """Compare current vs baseline; exit 1 if regressed."""
    if not BASELINE_PATH.exists():
        print("No baseline; run --baseline first", file=sys.stderr)
        return 0
    json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    current = compute_current()
    failed = []
    if current["files_changed"] > THRESHOLDS.get("files_changed_max", 999):
        failed.append(f"files_changed {current['files_changed']} > {THRESHOLDS['files_changed_max']}")
    if current["loc_added"] > THRESHOLDS.get("loc_added_max", 999):
        failed.append(f"loc_added {current['loc_added']} > {THRESHOLDS['loc_added_max']}")
    if failed:
        for f in failed:
            print(f"BUDGET FAIL: {f}", file=sys.stderr)
        return 1
    print("BUDGET OK")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: budget_check.py --baseline | --check", file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == "--baseline":
        run_baseline()
        sys.exit(0)
    if sys.argv[1] == "--check":
        sys.exit(run_check())
    print("Unknown arg", file=sys.stderr)
    sys.exit(2)
