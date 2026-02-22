#!/usr/bin/env python3
"""FAZ576: Live run manifest — inputs, outputs, symbols, horizons, versions, sha. Deterministic."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_sha() -> str:
    """Return short git sha or empty string. Deterministic."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_repo_root()),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _python_version() -> str:
    return sys.version.split()[0]


def build_manifest(
    day: str,
    out_root: Path,
    snapshot_root: Path,
    paths: dict[str, Path],
    symbols: list[str],
    top_n: int,
    horizons: list[int] | None = None,
) -> dict:
    """
    Build run manifest. Deterministic ordering.
    Returns dict with schema_version, inputs, outputs, symbols, horizons, versions, sha.
    """
    horizons = horizons or [1, 5, 20]
    reports_dir = paths.get("reports") or (out_root / "reports" / day)
    reports_dir = Path(reports_dir)

    # Collect output paths (discoverable from manifest)
    outputs: list[str] = []
    daily_scan = paths.get("daily_scan")
    ask_dir = paths.get("ask")
    outcomes_dir = paths.get("outcomes")

    if daily_scan:
        day_dir = Path(daily_scan)
        scan_json = day_dir / "scan.json"
        if scan_json.is_file():
            outputs.append(str(scan_json.resolve()))
        strategies = day_dir / "strategies.jsonl"
        if strategies.is_file():
            outputs.append(str(strategies.resolve()))

    if ask_dir and ask_dir.is_dir():
        for p in sorted(ask_dir.glob("*.json")):
            if p.stem and not p.name.startswith("."):
                outputs.append(str(p.resolve()))

    if outcomes_dir:
        outcomes_file = outcomes_dir / "strategy_outcomes.jsonl"
        if outcomes_file.is_file():
            outputs.append(str(outcomes_file.resolve()))

    # Reports
    for name in ("performance.json", "performance.csv", "scoreboard.json", "scoreboard.csv", "summary.html"):
        p = reports_dir / name
        if p.is_file():
            outputs.append(str(p.resolve()))
    for h in (1, 3, 5, 20):
        for ext in ("json", "csv"):
            p = reports_dir / f"topn_h{h}.{ext}"
            if p.is_file():
                outputs.append(str(p.resolve()))
        for ext in ("json", "csv", "html"):
            p = reports_dir / f"topn_bundle_h{h}.{ext}"
            if p.is_file():
                outputs.append(str(p.resolve()))

    outputs = sorted(outputs)

    return {
        "schema_version": 1,
        "day": day,
        "inputs": {
            "day": day,
            "top_n": int(top_n),
            "out_root": str(out_root.resolve()),
            "snapshot_root": str(snapshot_root.resolve()),
        },
        "outputs": outputs,
        "symbols": sorted(symbols),
        "horizons": sorted(horizons),
        "versions": {
            "python": _python_version(),
            "script": "live_daily_runner",
        },
        "sha": _git_sha(),
    }


def write_manifest(manifest: dict, reports_dir: Path) -> Path:
    """Write run_manifest.json. Returns path."""
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "run_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="FAZ576: Build live run manifest")
    p.add_argument("--day", required=True)
    p.add_argument("--out-root", default="data/log")
    p.add_argument("--snapshot-root", default=None)
    p.add_argument("--top-n", type=int, default=5)
    args = p.parse_args()

    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = (_repo_root() / out_root).resolve()
    snapshot_root = args.snapshot_root or os.environ.get("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots")
    snapshot_root = Path(snapshot_root)
    if not snapshot_root.is_absolute():
        snapshot_root = (_repo_root() / snapshot_root).resolve()

    paths = {
        "daily_scan": out_root / "daily_scan" / args.day,
        "ask": out_root / "ask" / args.day,
        "outcomes": out_root / "outcomes" / args.day,
        "reports": out_root / "reports" / args.day,
    }
    symbols: list[str] = []
    scan_path = paths["daily_scan"].parent / args.day / "scan.json"
    if scan_path.is_file():
        try:
            data = json.loads(scan_path.read_text(encoding="utf-8"))
            ranked = data.get("ranked") or []
            symbols = sorted(
                item["symbol"] for item in ranked
                if isinstance(item, dict) and item.get("symbol")
            )
        except (json.JSONDecodeError, OSError):
            pass
    if not symbols and paths["ask"].is_dir():
        symbols = sorted(
            p.stem for p in paths["ask"].glob("*.json")
            if p.stem and not p.name.startswith(".")
        )

    manifest = build_manifest(
        day=args.day,
        out_root=out_root,
        snapshot_root=snapshot_root,
        paths=paths,
        symbols=symbols,
        top_n=args.top_n,
    )
    written = write_manifest(manifest, paths["reports"])
    print(str(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
