from __future__ import annotations

import json
import subprocess
import sys


def _run_rules_explain(extra_args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "rules",
            "explain",
            "--file",
            "src/bist_core/policy/bist_ruleset.example.json",
            "--symbol",
            "AAA",
            "--price",
            "10",
            "--side",
            "BUY",
            "--qty",
            "100",
            "--day",
            "2025-01-02",
            *extra_args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )


def test_rules_explain_default_exit_code() -> None:
    result = _run_rules_explain([])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["allowed"] is False
    assert "violations" in payload


def test_rules_explain_strict_exit_code() -> None:
    result = _run_rules_explain(["--strict-exit"])
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["allowed"] is False
