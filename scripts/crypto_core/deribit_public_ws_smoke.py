from __future__ import annotations

import argparse
import json
import sys

from crypto_core.data.deribit_public_ws_harness import (
    DERIBIT_DEFAULT_PUBLIC_CHANNEL,
    DERIBIT_OFFICIAL_PUBLIC_WS_URL,
    DERIBIT_PUBLIC_WS_OPERATOR_AUTHORIZATION,
    DeribitPublicWsSmokeConfig,
    deribit_public_ws_smoke_result_to_dict,
    run_deribit_public_ws_smoke_test,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Quarantined Deribit public WebSocket smoke check. PUBLIC MARKET DATA ONLY. NO TRADING.",
    )
    parser.add_argument("--url", default=DERIBIT_OFFICIAL_PUBLIC_WS_URL)
    parser.add_argument("--channel", action="append", default=None)
    parser.add_argument("--duration-seconds", type=float, default=5.0)
    parser.add_argument("--max-messages", type=int, default=10)
    parser.add_argument("--max-receive-lag-ms", type=int, default=5_000)
    parser.add_argument("--authorization", default=DERIBIT_PUBLIC_WS_OPERATOR_AUTHORIZATION)
    args = parser.parse_args(argv)

    print("WARNING: PUBLIC MARKET DATA ONLY. NO TRADING. NO CREDENTIALS. NO ORDERS.", file=sys.stderr)
    config = DeribitPublicWsSmokeConfig(
        ws_url=args.url,
        channels=tuple(args.channel or (DERIBIT_DEFAULT_PUBLIC_CHANNEL,)),
        operator_authorization=args.authorization,
        dry_run=True,
        duration_seconds=args.duration_seconds,
        max_messages=args.max_messages,
        max_receive_lag_ms=args.max_receive_lag_ms,
    )
    result = run_deribit_public_ws_smoke_test(config)
    print(json.dumps(deribit_public_ws_smoke_result_to_dict(result), indent=2, sort_keys=True))
    return 0 if result.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
