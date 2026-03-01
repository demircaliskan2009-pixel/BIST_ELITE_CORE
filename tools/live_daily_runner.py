#!/usr/bin/env python3
"""FAZ566: Live daily runner — scan, ask, evaluate, report. Offline. Deterministic. Fail-closed."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_dirs(out_root: Path, day: str) -> dict[str, Path]:
    """Create output directories. Returns paths dict."""
    daily_scan = out_root / "daily_scan" / day
    ask_dir = out_root / "ask" / day
    outcomes_dir = out_root / "outcomes" / day
    reports_dir = out_root / "reports" / day
    for d in (daily_scan, ask_dir, outcomes_dir, reports_dir):
        d.mkdir(parents=True, exist_ok=True)
    return {
        "daily_scan": daily_scan,
        "ask": ask_dir,
        "outcomes": outcomes_dir,
        "reports": reports_dir,
    }


def _run_scan(
    day: str,
    top_n: int,
    snapshot_root: Path,
    scan_out_base: Path,
    env: dict[str, str],
) -> tuple[int, list[str]]:
    """Run scan, return (exit_code, symbols). Writes scan_out_base/day/scan.json."""
    scan_out_base.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "bist_core.cli",
        "scan",
        "--day",
        day,
        "--top-n",
        str(top_n),
        "--out",
        str(scan_out_base),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
    if r.returncode != 0:
        return r.returncode, []
    scan_path = scan_out_base / day / "scan.json"
    if not scan_path.is_file():
        return 0, []
    data = json.loads(scan_path.read_text(encoding="utf-8"))
    ranked = data.get("ranked") or []
    return 0, [item["symbol"] for item in ranked if isinstance(item, dict) and item.get("symbol")]


def _run_ask(symbol: str, day: str, ask_dir: Path, env: dict[str, str]) -> int:
    """Run ask for one symbol. Returns exit code."""
    cmd = [
        sys.executable,
        "-m",
        "bist_core.cli",
        "ask",
        symbol,
        "--day",
        day,
        "--out",
        str(ask_dir.parent),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=60)
    return r.returncode


def _run_evaluate_outcomes(
    strategies_path: Path,
    outcomes_path: Path,
    snapshot_root: Path,
    env: dict[str, str],
) -> int:
    """Run evaluate-outcomes. Returns exit code."""
    cmd = [
        sys.executable,
        "-m",
        "bist_core.cli",
        "evaluate-outcomes",
        "--strategies",
        str(strategies_path),
        "--outcomes",
        str(outcomes_path),
        "--snapshot-root",
        str(snapshot_root),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
    return r.returncode


def _run_performance_report(outcomes_path: Path, json_path: Path, csv_path: Path, env: dict[str, str]) -> int:
    """Run performance-report for JSON and CSV. Returns exit code."""
    for out_path, extra in [(json_path, []), (csv_path, ["--csv"])]:
        cmd = [
            sys.executable,
            "-m",
            "bist_core.cli",
            "performance-report",
            "--outcomes",
            str(outcomes_path),
            "--out",
            str(out_path),
            *extra,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=30)
        if r.returncode != 0:
            return r.returncode
    return 0


def run_live_daily(
    day: str,
    top_n: int = 5,
    out_root: str | Path = "data/log",
    snapshot_root: str | Path | None = None,
) -> tuple[int, list[str], dict[str, Path]]:
    """
    Run live daily workflow: scan -> ask -> evaluate -> report.
    Returns (exit_code, symbols, paths). Fail-closed: nonzero on programmer/config errors.
    Missing snapshot => scan may return empty; we continue with empty symbols (exit 0).
    """
    out_root = Path(out_root)
    if snapshot_root is None:
        snapshot_root = Path(os.environ.get("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots"))
    else:
        snapshot_root = Path(snapshot_root)

    paths = _ensure_dirs(out_root, day)
    strategies_path = paths["daily_scan"] / "strategies.jsonl"
    outcomes_path = paths["outcomes"] / "strategy_outcomes.jsonl"
    json_report = paths["reports"] / "performance.json"
    csv_report = paths["reports"] / "performance.csv"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)
    env["BIST_CORE_STRATEGY_LOG"] = str(strategies_path)
    env["BIST_CORE_STRATEGY_OUTCOMES"] = str(outcomes_path)
    env.pop("BIST_CORE_ALLOW_NETWORK", None)

    code, symbols = _run_scan(day, top_n, snapshot_root, paths["daily_scan"].parent, env)
    if code != 0:
        return code, [], paths

    for sym in symbols:
        ac = _run_ask(sym, day, paths["ask"], env)
        if ac != 0:
            pass

    if strategies_path.is_file():
        ec = _run_evaluate_outcomes(strategies_path, outcomes_path, snapshot_root, env)
        if ec != 0:
            pass

    if outcomes_path.is_file():
        pc = _run_performance_report(outcomes_path, json_report, csv_report, env)
        if pc != 0:
            return pc, symbols, paths

    # FAZ572: Scoreboard (BUY/SELL/HOLD + horizon returns) when bars exist
    horizons = [1, 5, 20]
    try:
        from tools.scoreboard_report import build_scoreboard, write_scoreboard

        report = build_scoreboard(day, out_root, snapshot_root, horizons)
        write_scoreboard(report, paths["reports"])
    except Exception:
        pass  # Best-effort; do not fail run

    # FAZ583/FAZ590: TopN horizon ranking (topn_h1, topn_h3, topn_h5, topn_h20)
    scan_json = out_root / "daily_scan" / day / "scan.json"
    if not scan_json.is_file():
        print("faz590: scan.json not found, skipping topn/bundle/risk_plan", file=sys.stderr)
    else:
        try:
            topn_script = _repo_root() / "tools" / "topn_horizon_rank.py"
            for h in (1, 3, 5, 20):
                cmd = [
                    sys.executable,
                    str(topn_script),
                    "--day",
                    day,
                    "--horizon",
                    str(h),
                    "--top",
                    str(top_n),
                    "--scan",
                    str(scan_json),
                    "--out-root",
                    str(out_root),
                    "--snapshot-root",
                    str(snapshot_root),
                ]
                r = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120
                )
                if r.returncode == 2:
                    print(f"faz590: topn_h{h} input missing (exit 2), continuing", file=sys.stderr)
                elif r.returncode == 1:
                    raise RuntimeError(f"topn_horizon_rank exit 1: {r.stderr or r.stdout}")
        except RuntimeError:
            raise
        except Exception as e:
            print(f"faz590: topn_horizon_rank error: {e}", file=sys.stderr)

        # FAZ591: TopN bundle (topn_bundle_h1, h3, h5, h20) via subprocess
        reports_root = out_root / "reports"
        bundle_script = _repo_root() / "tools" / "topn_bundle_report.py"
        for h in (1, 3, 5, 20):
            cmd = [
                sys.executable,
                str(bundle_script),
                "--day",
                day,
                "--horizon",
                str(h),
                "--top",
                str(top_n),
                "--reports-root",
                str(reports_root),
                "--snapshot-root",
                str(snapshot_root),
            ]
            r = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120
            )
            if r.returncode == 2:
                print(f"faz591: topn_bundle_h{h} input missing (exit 2), continuing", file=sys.stderr)
            elif r.returncode == 1:
                raise RuntimeError(f"topn_bundle_report exit 1: {r.stderr or r.stdout}")

        # FAZ591: Risk plan (risk_plan_h1, h3, h5, h20) via subprocess
        risk_script = _repo_root() / "tools" / "risk_sizer.py"
        for h in (1, 3, 5, 20):
            cmd = [
                sys.executable,
                str(risk_script),
                "--day",
                day,
                "--horizon",
                str(h),
                "--top",
                str(top_n),
                "--reports-root",
                str(reports_root),
                "--snapshot-root",
                str(snapshot_root),
            ]
            r = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120
            )
            if r.returncode == 2:
                print(f"faz591: risk_plan_h{h} input missing (exit 2), continuing", file=sys.stderr)
            elif r.returncode == 1:
                raise RuntimeError(f"risk_sizer exit 1: {r.stderr or r.stdout}")

        # FAZ592: Pick lock (picks_h1, h3, h5, h20) via subprocess
        picks_root = out_root / "picks"
        lock_script = _repo_root() / "tools" / "pick_lock.py"
        for h in (1, 3, 5, 20):
            cmd = [
                sys.executable,
                str(lock_script),
                "--day",
                day,
                "--horizon",
                str(h),
                "--top",
                str(top_n),
                "--reports-root",
                str(reports_root),
                "--picks-root",
                str(picks_root),
            ]
            r = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=60
            )
            if r.returncode == 2:
                print(f"faz592: picks_h{h} input missing (exit 2), continuing", file=sys.stderr)
            elif r.returncode == 1:
                raise RuntimeError(f"pick_lock exit 1: {r.stderr or r.stdout}")

        # FAZ592: Pick eval (eval_h1, h3, h5, h20) — PENDING when exit snapshot missing, OK when present
        eval_script = _repo_root() / "tools" / "pick_eval.py"
        for h in (1, 3, 5, 20):
            cmd = [
                sys.executable,
                str(eval_script),
                "--day",
                day,
                "--horizon",
                str(h),
                "--picks-root",
                str(picks_root),
                "--snapshot-root",
                str(snapshot_root),
            ]
            r = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=60
            )
            if r.returncode == 2:
                print(f"faz592: eval_h{h} picks missing (exit 2), continuing", file=sys.stderr)
            elif r.returncode == 1:
                raise RuntimeError(f"pick_eval exit 1: {r.stderr or r.stdout}")

    # FAZ571: Summary HTML (before manifest so it's discoverable)
    try:
        from tools.live_publish_summary import publish_summary

        publish_summary(day, out_root)
    except Exception:
        pass  # Best-effort; do not fail run

    # FAZ576: Run manifest (inputs, outputs, symbols, horizons, versions, sha)
    try:
        from tools.live_manifest import build_manifest, write_manifest

        manifest = build_manifest(
            day=day,
            out_root=out_root,
            snapshot_root=snapshot_root,
            paths=paths,
            symbols=symbols,
            top_n=top_n,
            horizons=horizons,
        )
        write_manifest(manifest, paths["reports"])
    except Exception:
        pass  # Best-effort; do not fail run

    return 0, symbols, paths


def main() -> int:
    """Exit 0=ok, 2=validation block, 1=programmer error."""
    import argparse

    p = argparse.ArgumentParser(description="FAZ566: Live daily runner")
    p.add_argument("--day", required=True, help="YYYY-MM-DD")
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--out-root", default="data/log")
    p.add_argument("--snapshot-root", default=None)
    args = p.parse_args()
    snap = args.snapshot_root if args.snapshot_root else None
    try:
        code, symbols, paths = run_live_daily(
            day=args.day,
            top_n=args.top_n,
            out_root=args.out_root,
            snapshot_root=snap,
        )
        print(f"TOP{len(symbols)}: {', '.join(symbols) or '(none)'}")
        print(f"Scan: {paths['daily_scan']}")
        print(f"Ask: {paths['ask']}")
        print(f"Outcomes: {paths['outcomes']}")
        print(f"Reports: {paths['reports']}")
        return int(code) if code is not None else 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
