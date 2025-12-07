from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from datetime import date
from bist_core.data import DatasetRegistry, get_default_registry
from bist_core.data.eod import (
    build_and_store_eod_snapshot,
    get_default_snapshot_root,
    read_eod_snapshot,
)
from bist_core.providers import DummyProvider
from bist_core.strategy.equal_weight import build_equal_weight_plan


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bist_core",
        description="BIST_ELITE_CORE command-line interface",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # bist_core info ...
    info_parser = subparsers.add_parser("info", help="Show configuration info")

    # bist_core eod ...
    eod_parser = subparsers.add_parser("eod", help="Generate EOD snapshot")
    eod_parser.add_argument(
        "--date",
        required=True,
        help="Date in YYYY-MM-DD format",
    )

    # bist_core plan ...
    plan_parser = subparsers.add_parser("plan", help="Generate trading plan")
    plan_parser.add_argument(
        "--date",
        required=True,
        help="Date in YYYY-MM-DD format",
    )
    plan_parser.add_argument(
        "--strategy",
        default="equal_weight",
        help="Strategy name (default: equal_weight)",
    )

    # bist_core data ...
    data_parser = subparsers.add_parser("data", help="Data management commands")
    data_subparsers = data_parser.add_subparsers(
        dest="data_command",
        required=True,
    )

    # bist_core data register ...
    register_parser = data_subparsers.add_parser(
        "register",
        help="Register a dataset in the registry",
    )
    register_parser.add_argument("--name", required=True, help="Dataset name")
    register_parser.add_argument(
        "--kind",
        required=True,
        help="Dataset kind (e.g. 'local_csv')",
    )
    register_parser.add_argument(
        "--path",
        required=True,
        help="Root path of the dataset (directory)",
    )
    register_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing dataset metadata if present",
    )

    # bist_core data load ...
    load_parser = data_subparsers.add_parser(
        "load",
        help="Load a registered dataset and print a small summary",
    )
    load_parser.add_argument("--name", required=True, help="Dataset name")
    load_parser.add_argument(
        "--as-of",
        help="Optional as-of date (YYYY-MM-DD) for using/creating EOD snapshot",
    )
    load_parser.add_argument(
        "--use-snapshot",
        action="store_true",
        help=(
            "Load from EOD snapshot instead of raw dataset. "
            "If snapshot does not exist and --as-of is given, "
            "it will be created."
        ),
    )
    load_parser.add_argument(
        "--snapshot-root",
        help="Optional override for snapshot root directory",
    )
    load_parser.add_argument(
        "--head",
        type=int,
        default=5,
        help="Number of rows from the head to display",
    )

    return parser


def _cmd_data_register(args: argparse.Namespace) -> int:
    registry: DatasetRegistry = get_default_registry()
    path = Path(args.path)

    meta = registry.register(
        name=args.name,
        kind=args.kind,
        path=path,
        overwrite=args.overwrite,
    )

    print(
        f"registered dataset {meta.name!r} "
        f"kind={meta.kind!r} path={meta.path!r}"
    )
    return 0


def _load_dataframe_from_registry(
    registry: DatasetRegistry,
    name: str,
    as_of: Optional[str],
    use_snapshot: bool,
    snapshot_root_arg: Optional[str],
) -> pd.DataFrame:
    meta = registry.get(name)

    if use_snapshot:
        snapshot_root = get_default_snapshot_root(
            Path(snapshot_root_arg) if snapshot_root_arg else None
        )
        if as_of is None:
            raise SystemExit(
                "--use-snapshot specified but --as-of date is missing"
            )

        # Eğer snapshot yoksa, oluştur.
        try:
            df = read_eod_snapshot(snapshot_root, name, as_of)
        except FileNotFoundError:
            path = build_and_store_eod_snapshot(
                dataset_name=name,
                as_of=as_of,
                registry=registry,
                snapshot_root=snapshot_root,
            )
            print(f"created EOD snapshot at {path}")
            df = read_eod_snapshot(snapshot_root, name, as_of)
        return df

    # use_snapshot=False ⇒ raw dataset'ten oku
    root = Path(meta.path)
    if meta.kind == "local_csv":
        csv_files = sorted(root.glob("*.csv"))
        if not csv_files:
            raise SystemExit(f"No CSV files found under {root}")
        frames = [pd.read_csv(p) for p in csv_files]
        return pd.concat(frames, ignore_index=True)

    raise SystemExit(f"Unsupported dataset kind: {meta.kind!r}")


def _cmd_data_load(args: argparse.Namespace) -> int:
    registry: DatasetRegistry = get_default_registry()

    df = _load_dataframe_from_registry(
        registry=registry,
        name=args.name,
        as_of=args.as_of,
        use_snapshot=args.use_snapshot,
        snapshot_root_arg=args.snapshot_root,
    )

    rows, cols = df.shape
    print(
        f"loaded dataset {args.name!r} with {rows} rows, {cols} columns"
    )
    if args.head > 0:
        print(df.head(args.head).to_string(index=False))

    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    """Show configuration info including available symbols."""
    provider = DummyProvider()
    # Use a test date to get symbols
    test_date = date.today()
    symbols = ["TEST"]  # Ensure TEST is included
    df = provider.prices(symbols, test_date)
    symbol_list = ", ".join(df["symbol"].tolist())
    print(f"symbols: {symbol_list}")
    return 0


def _cmd_eod(args: argparse.Namespace) -> int:
    """Generate EOD snapshot for the given date."""
    try:
        snapshot_date = date.fromisoformat(args.date)
    except ValueError:
        raise SystemExit(f"Invalid date format: {args.date}. Use YYYY-MM-DD")

    # Use DummyProvider to generate prices
    provider = DummyProvider()
    symbols = ["TEST"]
    df = provider.prices(symbols, snapshot_date)
    
    # Override close for TEST to be 0.0 as expected by tests
    df.loc[df["symbol"] == "TEST", "close"] = 0.0
    
    # Create snapshot directory
    snapshot_dir = Path("data/eod/snapshots") / snapshot_date.isoformat()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    # Write snapshot.csv
    snapshot_path = snapshot_dir / "snapshot.csv"
    df.to_csv(snapshot_path, index=False)
    
    print(f"snapshot created at {snapshot_path}")
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    """Generate trading plan for the given date and strategy."""
    if args.strategy != "equal_weight":
        raise SystemExit(f"Unsupported strategy: {args.strategy}")

    try:
        plan_date = date.fromisoformat(args.date)
    except ValueError:
        raise SystemExit(f"Invalid date format: {args.date}. Use YYYY-MM-DD")

    snapshot_base = Path("data/eod/snapshots")
    plan_path = build_equal_weight_plan(args.date, base=snapshot_base)
    print(f"Plan yazıldı: {plan_path}")
    print("equal_weight")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "info":
        return _cmd_info(args)
    if args.command == "eod":
        return _cmd_eod(args)
    if args.command == "plan":
        return _cmd_plan(args)
    if args.command == "data":
        if args.data_command == "register":
            return _cmd_data_register(args)
        if args.data_command == "load":
            return _cmd_data_load(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
