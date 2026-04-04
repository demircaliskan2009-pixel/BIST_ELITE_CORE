from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from .config import ProviderConfig
from .factory import build_market_data_provider
from .snapshot_export import export_market_data_provider_to_snapshot_root


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Refresh snapshot root from the configured market data provider."
    )
    p.add_argument("--out-root", required=True, help="Snapshot root to write into.")
    p.add_argument("--start-date", default=None, help="Optional inclusive YYYY-MM-DD.")
    p.add_argument("--end-date", default=None, help="Optional inclusive YYYY-MM-DD.")
    p.add_argument("--clean", action="store_true", help="Delete output root before writing.")
    return p


def main() -> int:
    args = build_parser().parse_args()

    cfg = ProviderConfig.from_env(os.environ).validate(must_exist=True)
    provider = build_market_data_provider(cfg)

    out_root = Path(args.out_root)
    if args.clean and out_root.exists():
        shutil.rmtree(out_root)

    summary = export_market_data_provider_to_snapshot_root(
        provider=provider,
        out_root=out_root,
        start_date=args.start_date,
        end_date=args.end_date,
        symbols=None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
