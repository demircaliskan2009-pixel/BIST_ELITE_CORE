from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluator import evaluate_open_recommendations
from .reporting import build_report, export_records_csv, write_report_json
from .store import (
    append_recommendation,
    close_recommendation,
    compute_stats,
    list_recommendations,
    recommendations_path,
)


def _load_meta(args) -> dict:
    if getattr(args, "meta_file", None):
        return json.loads(Path(args.meta_file).read_text(encoding="utf-8-sig"))
    if getattr(args, "meta_json", None):
        return json.loads(args.meta_json)
    return {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Live test recommendation logging/reporting CLI.")
    p.add_argument("--root", default="data/live_test", help="Store root path.")
    sub = p.add_subparsers(dest="command", required=True)

    log_p = sub.add_parser("log", help="Append recommendation.")
    log_p.add_argument("--source", required=True)
    log_p.add_argument("--symbol", required=True)
    log_p.add_argument("--day", required=True)
    log_p.add_argument("--decision", required=True)
    log_p.add_argument("--timeframe", default=None)
    log_p.add_argument("--score", type=float, default=None)
    log_p.add_argument("--entry", type=float, default=None)
    log_p.add_argument("--stop", type=float, default=None)
    log_p.add_argument("--target", type=float, default=None)
    log_p.add_argument("--rationale", default=None)
    log_p.add_argument("--invalidation", default=None)
    log_p.add_argument("--meta-json", default=None)
    log_p.add_argument("--meta-file", default=None)

    close_p = sub.add_parser("close", help="Close recommendation.")
    close_p.add_argument("--id", required=True)
    close_p.add_argument("--outcome-label", required=True)
    close_p.add_argument("--realized-return-r", type=float, default=None)
    close_p.add_argument("--realized-return-pct", type=float, default=None)
    close_p.add_argument("--note", default=None)

    list_p = sub.add_parser("list", help="List recommendations.")
    list_p.add_argument("--status", default=None)
    list_p.add_argument("--symbol", default=None)
    list_p.add_argument("--limit", type=int, default=20)

    sub.add_parser("stats", help="Compute summary stats.")

    eval_p = sub.add_parser("evaluate-open", help="Evaluate and auto-close open recommendations.")
    eval_p.add_argument("--snapshot-root", required=True)
    eval_p.add_argument("--max-holding-days", type=int, default=5)

    report_p = sub.add_parser("report", help="Build live-test report and optionally export.")
    report_p.add_argument("--format", choices=("json", "csv"), default="json")
    report_p.add_argument("--out", default=None)

    return p


def main() -> int:
    args = _build_parser().parse_args()
    root = Path(args.root)

    if args.command == "log":
        meta = _load_meta(args)
        rec = append_recommendation(
            root=root,
            source=args.source,
            symbol=args.symbol,
            day=args.day,
            decision=args.decision,
            timeframe=args.timeframe,
            score=args.score,
            entry=args.entry,
            stop=args.stop,
            target=args.target,
            rationale=args.rationale,
            invalidation=args.invalidation,
            metadata=meta,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "recommendation_id": rec.recommendation_id,
                    "path": str(recommendations_path(root)),
                    "record": rec.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "close":
        rec = close_recommendation(
            root=root,
            recommendation_id=args.id,
            outcome_label=args.outcome_label,
            realized_return_r=args.realized_return_r,
            realized_return_pct=args.realized_return_pct,
            outcome_note=args.note,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "recommendation_id": rec.recommendation_id,
                    "record": rec.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "list":
        records = [
            x.to_dict()
            for x in list_recommendations(
                root=root,
                status=args.status,
                symbol=args.symbol,
                limit=args.limit,
            )
        ]
        print(json.dumps({"ok": True, "count": len(records), "records": records}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "stats":
        print(json.dumps({"ok": True, "stats": compute_stats(root)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "evaluate-open":
        result = evaluate_open_recommendations(
            root=root,
            snapshot_root=Path(args.snapshot_root),
            max_holding_days=int(args.max_holding_days),
        )
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "report":
        report = build_report(root)

        if args.format == "json":
            out_path = None if not args.out else write_report_json(report, args.out)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "format": "json",
                        "out": None if out_path is None else str(out_path),
                        "report": report,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        out_csv = export_records_csv(root=root, out_path=args.out)
        print(
            json.dumps(
                {
                    "ok": True,
                    "format": "csv",
                    "out": str(out_csv),
                    "report": report,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
