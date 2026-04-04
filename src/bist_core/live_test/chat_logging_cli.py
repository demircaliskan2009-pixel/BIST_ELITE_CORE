from __future__ import annotations

import argparse
import json
from pathlib import Path

from .chat_logging import load_response_json, log_from_chat_payload

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Log live-test recommendations from a saved chat response json.")
    p.add_argument("--root", default="data/live_test", help="Live-test store root")
    p.add_argument("--response-json", required=True, help="Path to saved gateway response JSON")
    p.add_argument("--source", default="gateway_chat")
    p.add_argument("--timeframe", default=None)
    p.add_argument("--request-id", default=None)
    return p

def main() -> int:
    args = _build_parser().parse_args()
    payload = load_response_json(args.response_json)
    meta = {}
    if args.request_id:
        meta["request_id"] = args.request_id

    records = log_from_chat_payload(
        root=Path(args.root),
        response_json=payload,
        source=args.source,
        timeframe=args.timeframe,
        request_meta=meta,
    )

    print(json.dumps({
        "ok": True,
        "count": len(records),
        "records": [x.to_dict() for x in records],
    }, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
