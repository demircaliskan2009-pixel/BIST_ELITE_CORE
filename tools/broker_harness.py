#!/usr/bin/env python3
"""FAZ578: Broker harness — load orders_intent from file, run DryRunExecutionProvider deterministically. No network."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run_harness(orders_path: Path, provider=None) -> tuple[int, dict]:
    """
    Load orders_intent from file, run provider.submit_orders(orders, dry_run=True).
    Returns (exit_code, result).
    Exit: 0=ok, 1=validation failed, 2=file/IO error.
    """
    if not orders_path.is_file():
        return 2, {"ok": False, "errors": ["orders_file_not_found"], "broker": "dry_run", "sent": 0}

    try:
        orders = json.loads(orders_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return 2, {"ok": False, "errors": [f"orders_file_invalid:{e!s}"], "broker": "dry_run", "sent": 0}

    if provider is None:
        sys.path.insert(0, str(_repo_root() / "src"))
        from bist_core.execution import DryRunExecutionProvider
        provider = DryRunExecutionProvider()

    result = provider.submit_orders(orders, dry_run=True)
    exit_code = 0 if result.get("ok") else 1
    return exit_code, result


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="FAZ578: Broker harness — validate orders_intent via DryRunExecutionProvider")
    p.add_argument("--orders", required=True, help="Path to orders_intent.json")
    args = p.parse_args()

    path = Path(args.orders)
    if not path.is_absolute():
        path = (_repo_root() / path).resolve()

    exit_code, result = run_harness(path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
