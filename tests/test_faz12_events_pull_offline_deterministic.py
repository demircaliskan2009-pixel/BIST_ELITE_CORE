from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_events_pull_offline_deterministic(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    input_path = tmp_path / "input.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"symbol":"BBB","ts":"2099-01-01T09:00:00Z","kind":"KAP","title":"B1"}',
                '{"symbol":"AAA","ts":"2099-01-01T10:00:00Z","kind":"KAP","title":"A1"}',
                '{"symbol":"AAA","ts":"2099-01-01T10:00:00Z","kind":"KAP","title":"A1"}',
                '{"symbol":"CCC","ts":"2099-01-01T08:00:00Z","kind":"KAP","title":"C1"}',
                '{"symbol":"DDD","ts":"2099-01-01T11:00:00Z","title":"MissingKind"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    outdir = tmp_path / "out" / "2099-01-01"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "events",
            "pull",
            "--day",
            "2099-01-01",
            "--provider",
            "offline_file",
            "--input",
            str(input_path),
            "--outdir",
            str(outdir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )

    assert result.returncode == 0
    manifest = (outdir / "_manifest.json").read_text(encoding="utf-8")
    assert '"rejected": 1' in manifest
    assert '"duplicates": 1' in manifest

    out_path = outdir / "events.jsonl"
    content = out_path.read_text(encoding="utf-8")
    expected = "\n".join(
        [
            '{"symbol": "AAA", "ts": "2099-01-01T10:00:00Z", "kind": "KAP", "title": "A1", "url": null, "tags": null, "payload": null}',
            '{"symbol": "BBB", "ts": "2099-01-01T09:00:00Z", "kind": "KAP", "title": "B1", "url": null, "tags": null, "payload": null}',
            '{"symbol": "CCC", "ts": "2099-01-01T08:00:00Z", "kind": "KAP", "title": "C1", "url": null, "tags": null, "payload": null}',
            "",
        ]
    )
    assert content == expected
