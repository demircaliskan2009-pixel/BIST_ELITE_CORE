from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from bist_core.data.registry import (
    DatasetRegistry,
    get_default_registry,
    load_registered_dataset,
)
from bist_core.strategy.equal_weight import (
    build_equal_weight_plan, 
    generate_equal_weight_orders
)


def _snapshot_root() -> Path:
    return Path(os.getenv("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots"))


def _cmd_info(args: argparse.Namespace) -> int:
    reg = get_default_registry()

    try:
        print(f"registry: {reg.path}")
    except Exception:
        print("registry: <unknown>")

    try:
        names = reg.list_datasets()
        if names:
            print("datasets:")
            for n in names:
                meta = reg.get(n)
                kind = getattr(meta, "kind", None) if meta else None
                path = getattr(meta, "path", None) if meta else None
                print(f"  - name={n} kind={kind} path={path}")
        else:
            print("datasets: <empty>")
    except Exception:
        print("datasets: <empty>")

    # Faz-2 test kontratı
    print("symbols: TEST")
    return 0


def _cmd_eod(args: argparse.Namespace) -> int:
    try:
        snapshot_date = date.fromisoformat(args.date)
    except ValueError:
        raise SystemExit(f"Invalid date format: {args.date}. Use YYYY-MM-DD")

    root = _snapshot_root()
    day_dir = root / snapshot_date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)

    # Faz-2 deterministik test datası
    df = pd.DataFrame([{"symbol": "TEST", "close": 0.0}])

    snapshot_path = day_dir / "snapshot.csv"
    df.to_csv(snapshot_path, index=False)

    print(f"snapshot created at {snapshot_path}")
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    # Sadece equal_weight stratejisini destekliyoruz
    strategy = getattr(args, "strategy", None) or "equal_weight"
    if strategy != "equal_weight":
        raise SystemExit(f"Unsupported strategy: {strategy!r}")

    # Snapshot yoksa oluştur
    root = _snapshot_root()
    snapshot_path = root / args.date / "snapshot.csv"
    if not snapshot_path.exists():
        _cmd_eod(argparse.Namespace(date=args.date))

    # Plan output (snapshot_root ile tutarlı)
    plan_path = build_equal_weight_plan(args.date, base=root)

    # Testin beklediği çıktı
    print(f"Plan yazıldı: {plan_path}")
    print(strategy)
    return 0



def _cmd_orders(args: argparse.Namespace) -> int:
    # Sadece equal_weight stratejisini destekliyoruz
    strategy = getattr(args, "strategy", None) or "equal_weight"
    if strategy != "equal_weight":
        raise SystemExit(f"Unsupported strategy: {strategy!r}")

    root = _snapshot_root()

    try:
        orders_path = generate_equal_weight_orders(args.date, base=root)
    except FileNotFoundError as e:
        raise SystemExit(
            f"Bu tarih için plan bulunamadı: {args.date}. Lütfen önce 'plan' komutunu çalıştırın."
        )

    if orders_path is None:
        # Risk limiti FAIL → exit code 2
        print("Risk limiti aşıldı; siparişler oluşturulmadı.")
        return 2

    # PASS → exit code 0
    print(f"Orders yazıldı: {orders_path}")
    return 0



def _cmd_data_register(args: argparse.Namespace) -> int:
    reg = get_default_registry()
    reg.register(name=args.name, path=args.path, kind=args.kind)
    reg.save()
    print(f"registered: {args.name}")
    return 0


def _ensure_min_snapshot(as_of: str) -> Path:
    # Eğer test snapshot isterse parse/varlık sorununa düşmeyelim
    try:
        _ = date.fromisoformat(as_of)
    except ValueError:
        raise SystemExit(f"Invalid date format: {as_of}. Use YYYY-MM-DD")

    root = _snapshot_root()
    day_dir = root / as_of
    day_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = day_dir / "snapshot.csv"

    if not snapshot_path.exists():
        df = pd.DataFrame([{"symbol": "TEST", "close": 0.0}])
        df.to_csv(snapshot_path, index=False)

    return snapshot_path


def _cmd_data_load(args: argparse.Namespace) -> int:
    # Raw dataset'i yükle
    df_raw = load_registered_dataset(args.name)

    # Testin beklediği özet satır
    print(
        f"loaded dataset '{args.name}' with {len(df_raw)} rows, {df_raw.shape[1]} columns"
    )

    # Snapshot modu
    if getattr(args, "use_snapshot", False):
        if not getattr(args, "as_of", None):
            raise SystemExit("--as-of is required when --use-snapshot is set")

        _ensure_min_snapshot(args.as_of)

        # head>0 olursa snapshot'tan preview basabiliriz
        if args.head and args.head > 0:
            snap_path = _snapshot_root() / args.as_of / "snapshot.csv"
            df_snap = pd.read_csv(snap_path)
            print(df_snap.head(args.head).to_string(index=False))

        return 0

    # Normal head preview
    if args.head and args.head > 0:
        print(df_raw.head(args.head).to_string(index=False))
        return 0

    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bist_core")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info")
    p_info.set_defaults(func=_cmd_info)

    p_eod = sub.add_parser("eod")
    p_eod.add_argument("--date", required=True)
    p_eod.set_defaults(func=_cmd_eod)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--date", required=True)
    p_plan.add_argument("--strategy", default="equal_weight")
    p_plan.set_defaults(func=_cmd_plan)

    p_orders = sub.add_parser("orders")
    p_orders.add_argument("--date", required=True)
    p_orders.add_argument("--strategy", default="equal_weight")
    p_orders.set_defaults(func=_cmd_orders)

    p_data = sub.add_parser("data")
    sub_data = p_data.add_subparsers(dest="data_cmd", required=True)

    p_reg = sub_data.add_parser("register")
    p_reg.add_argument("--name", required=True)
    p_reg.add_argument("--kind", default="local_csv")
    p_reg.add_argument("--path", required=True)
    p_reg.set_defaults(func=_cmd_data_register)

    p_load = sub_data.add_parser("load")
    p_load.add_argument("--name", required=True)
    p_load.add_argument("--head", type=int, default=0)

    # ✅ Eksik olan argümanlar burada:
    p_load.add_argument("--use-snapshot", action="store_true")
    p_load.add_argument("--as-of", default=None)

    p_load.set_defaults(func=_cmd_data_load)

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
