from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from bist_core.datasets.registry import DatasetRegistry


def _parse_meta(items: Optional[List[str]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not items:
        return out
    for it in items:
        if "=" not in it:
            raise ValueError(f"Invalid --meta '{it}'. Use key=value.")
        k, v = it.split("=", 1)
        k = k.strip()
        if not k:
            raise ValueError(f"Invalid --meta '{it}'. Empty key.")
        out[k] = v
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bist-core data")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("register", help="Register a dataset path into the persistent registry.")
    pr.add_argument("--name", required=True)
    pr.add_argument("--path", required=True)
    pr.add_argument("--kind", default="csv")
    pr.add_argument("--meta", action="append", default=[], help="key=value (repeatable)")
    pr.add_argument("--update", action="store_true", help="Allow updating existing record")
    pr.set_defaults(_fn=_cmd_register)

    pl = sub.add_parser("list", help="List registered dataset names.")
    pl.set_defaults(_fn=_cmd_list)

    ps = sub.add_parser("show", help="Show one dataset record as JSON.")
    ps.add_argument("name")
    ps.set_defaults(_fn=_cmd_show)

    # Alias kept for forward-compat + possible existing tests
    pld = sub.add_parser("load", help="Resolve dataset to a path (prints the path).")
    pld.add_argument("name")
    pld.set_defaults(_fn=_cmd_load)

    return p


def _cmd_register(args: argparse.Namespace) -> int:
    reg = DatasetRegistry().load()
    meta = _parse_meta(args.meta)
    rec = reg.register(
        name=args.name,
        path=Path(args.path),
        kind=args.kind,
        meta=meta,
        allow_update=bool(args.update),
    )
    reg.save()
    print(json.dumps(rec.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    reg = DatasetRegistry().load()
    for name in reg.list_names():
        print(name)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    reg = DatasetRegistry().load()
    rec = reg.get(args.name)
    print(json.dumps(rec.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    reg = DatasetRegistry().load()
    p = reg.resolve_path(args.name)
    print(str(p))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    try:
        ns = parser.parse_args(argv)
        return int(ns._fn(ns))
    except SystemExit as e:
        # argparse help / parse errors
        return int(getattr(e, "code", 2) or 0)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2
