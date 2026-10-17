"""Translate actual local pytest JUnit evidence into a per-test qualification matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def matrix(junit, command):
    data = Path(junit).read_bytes()
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("junit too large")
    root = ET.fromstring(data)  # noqa: S314 -- bounded, locally generated pytest evidence; never remote XML
    rows = []
    for case in root.iter("testcase"):
        failure = case.find("failure")
        error, skipped = case.find("error"), case.find("skipped")
        status = "FAIL" if failure is not None or error is not None else "BLOCKED" if skipped is not None else "PASS"
        detail = failure if failure is not None else error if error is not None else skipped
        rows.append(
            {
                "TEST_ID": case.get("classname", "") + "." + case.get("name", ""),
                "ACTUAL_COMMAND": command,
                "PLATFORM": platform.platform(),
                "EXPECTED_RESULT": "all named regression assertions hold; verification never implies operational admission",
                "ACTUAL_RESULT": detail.get("message", "") if detail is not None else "pytest assertions passed",
                "PASS_FAIL_BLOCKED": status,
                "EVIDENCE": {"junit": str(Path(junit).absolute()), "sha256": hashlib.sha256(data).hexdigest()},
            }
        )
    return {
        "evidence_class": "CANDIDATE_TEST_EVIDENCE_ONLY",
        "summary": dict(Counter(row["PASS_FAIL_BLOCKED"] for row in rows)),
        "tests": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", required=True)
    parser.add_argument("--actual-command", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    Path(args.output).write_text(
        json.dumps(matrix(args.junit, args.actual_command), indent=2, sort_keys=True), encoding="utf-8"
    )
