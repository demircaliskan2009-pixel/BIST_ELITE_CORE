from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _start_server(root: Path) -> tuple[ThreadingHTTPServer, int]:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format, *args):  # noqa: A002
            return

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


def _find_pipeline_manifest(outdir: Path, day: str) -> Path:
    candidates = sorted(outdir.rglob("pipeline_manifest.json"))
    if not candidates:
        raise AssertionError(f"pipeline_manifest.json missing under outdir={outdir}")

    for p in candidates:
        if p.parent.name == day:
            return p
    return candidates[0]


def test_faz28_eod_manifest_includes_events_raw_cache(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]

    # Minimal snapshot so EOD marketdata stage can run
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    day = "2099-01-01"
    (snapshots_dir / f"{day}.csv").write_text(
        "symbol,date,close\nAAA,2099-01-01,10\n",
        encoding="utf-8",
    )

    # Serve existing KAP HTML fixture locally (no external network)
    fixtures_dir = repo_root / "tests" / "fixtures"
    fixture = fixtures_dir / "kap_sample.html"
    assert fixture.exists(), "tests/fixtures/kap_sample.html not found"

    httpd, port = _start_server(fixtures_dir)
    try:
        outdir = tmp_path / "out"
        raw_dir = tmp_path / "kap_raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "src")
        env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshots_dir)
        env["BIST_KAP_RAW_DIR"] = str(raw_dir)
        env["BIST_KAP_BASE_URL"] = f"http://127.0.0.1:{port}"
        env["BIST_KAP_URL_TEMPLATE"] = "/kap_sample.html"

        cmd = [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--events-provider",
            "kap_html",
        ]
        p = subprocess.run(cmd, env=env, capture_output=True, text=True)
        assert p.returncode == 0, f"stdout:\n{p.stdout}\nstderr:\n{p.stderr}"

        manifest_path = _find_pipeline_manifest(outdir, day)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert "events" in manifest, "events stage missing in pipeline manifest"
        events = manifest["events"]
        assert isinstance(events, dict), "events stage payload must be a dict"
        assert "raw_cache" in events, "events stage must include raw_cache"
        raw_cache = events["raw_cache"]
        assert isinstance(raw_cache, dict), "raw_cache must be a dict"
        assert raw_cache.get("path"), "raw_cache.path missing/empty"
        assert raw_cache.get("sha256"), "raw_cache.sha256 missing/empty"
    finally:
        httpd.shutdown()
        httpd.server_close()
