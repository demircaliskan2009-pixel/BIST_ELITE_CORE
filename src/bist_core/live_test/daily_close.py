from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .evaluator import evaluate_open_recommendations
from .reporting import build_report, export_records_csv, write_report_json


def run_daily_close(
    *,
    root: str | Path,
    snapshot_root: str | Path,
    max_holding_days: int = 5,
    json_out: str | Path | None = None,
    csv_out: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    snapshot_path = Path(snapshot_root)

    json_path = Path(json_out) if json_out else root_path / "report.json"
    csv_path = Path(csv_out) if csv_out else root_path / "report_records.csv"

    eval_summary = evaluate_open_recommendations(
        root=root_path,
        snapshot_root=snapshot_path,
        max_holding_days=int(max_holding_days),
    )
    report = build_report(root_path)
    written_json = write_report_json(report, json_path)
    written_csv = export_records_csv(root=root_path, out_path=csv_path)

    return {
        "root": str(root_path),
        "snapshot_root": str(snapshot_path),
        "max_holding_days": int(max_holding_days),
        "evaluate": eval_summary,
        "report": report,
        "json_out": str(written_json),
        "csv_out": str(written_csv),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Evaluate open live-test records and export fresh reports.")
    p.add_argument("--root", default="data/live_test", help="Live-test root path.")
    p.add_argument("--snapshot-root", default="data/eod/snapshots", help="Snapshot root path.")
    p.add_argument("--max-holding-days", type=int, default=5)
    p.add_argument("--json-out", default=None, help="Optional report.json output path.")
    p.add_argument("--csv-out", default=None, help="Optional report_records.csv output path.")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    payload = run_daily_close(
        root=Path(args.root),
        snapshot_root=Path(args.snapshot_root),
        max_holding_days=int(args.max_holding_days),
        json_out=args.json_out,
        csv_out=args.csv_out,
    )
    print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
