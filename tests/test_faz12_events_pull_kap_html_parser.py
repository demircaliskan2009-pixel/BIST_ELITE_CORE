from __future__ import annotations

import json
import os
import socketserver
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path


def _start_server(directory: Path) -> tuple[socketserver.TCPServer, int]:
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(
        *args, directory=str(directory), **kwargs
    )
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, httpd.server_address[1]


def test_events_pull_kap_html_parser(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    fixtures = repo_root / "tests" / "fixtures"
    httpd, port = _start_server(fixtures)
    try:
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
                "kap_html",
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--url-template",
                "/kap_sample.html",
                "--input",
                "unused",
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
        events_path = outdir / "events.jsonl"
        assert events_path.exists()
        lines = events_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        records = [json.loads(line) for line in lines]
        assert records[0]["symbol"] == "AKBNK"
        assert records[0]["title"] == "Capital Action"
        assert records[1]["symbol"] == "ASELS"
        assert records[2]["symbol"] == "THYAO"
    finally:
        httpd.shutdown()
