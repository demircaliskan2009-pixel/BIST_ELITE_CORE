"""
FAZ96: Release check — full tests, alignment gate, artifacts schema.
Exit 0 if all pass, 2 if any fail. Run from repo root.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_tests(root: Path) -> tuple[bool, str]:
    """Run full pytest. Return (ok, message)."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if r.returncode != 0:
            return False, r.stderr or r.stdout or f"pytest exit {r.returncode}"
        return True, "tests passed"
    except subprocess.TimeoutExpired:
        return False, "pytest timeout"
    except Exception as e:
        return False, str(e)


def _run_alignment_gate(root: Path) -> tuple[bool, str]:
    """Run scripts/verify_alignment.py. Return (ok, message)."""
    script = root / "scripts" / "verify_alignment.py"
    if not script.is_file():
        return False, f"script not found: {script}"
    try:
        r = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            return False, r.stderr or f"alignment gate exit {r.returncode}"
        return True, "alignment gate passed"
    except Exception as e:
        return False, str(e)


def _check_artifacts_schema(root: Path) -> tuple[bool, str]:
    """Check key config/artifact schemas: config/strategy.json, config/core.json. Return (ok, message)."""
    errors = []
    strategy_path = root / "config" / "strategy.json"
    if not strategy_path.is_file():
        errors.append(f"missing {strategy_path}")
    else:
        try:
            data = json.loads(strategy_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                errors.append("config/strategy.json: not a dict")
            else:
                for key in ("mom_fast", "mom_slow", "score_buy", "score_watch"):
                    if key not in data:
                        errors.append(f"config/strategy.json: missing key {key!r}")
        except json.JSONDecodeError as e:
            errors.append(f"config/strategy.json: invalid JSON: {e}")

    core_path = root / "config" / "core.json"
    if not core_path.is_file():
        errors.append(f"missing {core_path}")
    else:
        try:
            data = json.loads(core_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                errors.append("config/core.json: not a dict")
        except json.JSONDecodeError as e:
            errors.append(f"config/core.json: invalid JSON: {e}")

    if errors:
        return False, "; ".join(errors)
    return True, "artifacts schema ok"


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release check: tests, alignment gate, artifacts schema.")
    parser.add_argument("--tests-only", action="store_true", help="Run only full tests")
    parser.add_argument("--alignment-only", action="store_true", help="Run only alignment gate")
    parser.add_argument("--schema-only", action="store_true", help="Run only artifacts schema check")
    parsed = parser.parse_args(args)

    root = _repo_root()
    run_tests = parsed.tests_only or (not parsed.alignment_only and not parsed.schema_only)
    run_alignment = parsed.alignment_only or (not parsed.tests_only and not parsed.schema_only)
    run_schema = parsed.schema_only or (not parsed.tests_only and not parsed.alignment_only)

    failed = []
    if run_tests:
        ok, msg = _run_tests(root)
        if not ok:
            failed.append(("tests", msg))
        else:
            print("tests: ok")
    if run_alignment:
        ok, msg = _run_alignment_gate(root)
        if not ok:
            failed.append(("alignment", msg))
        else:
            print("alignment: ok")
    if run_schema:
        ok, msg = _check_artifacts_schema(root)
        if not ok:
            failed.append(("schema", msg))
        else:
            print("artifacts schema: ok")

    if failed:
        for name, msg in failed:
            print(f"{name}: FAIL — {msg}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
