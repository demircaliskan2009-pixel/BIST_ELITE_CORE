#!/usr/bin/env python3
"""FAZ582: Midas Stage-1 order ticket export — CSV + TXT from orders_intent v2. No network, no secrets."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ALLOWED_ORDER_TYPES = frozenset({"MARKET", "LIMIT"})
CSV_HEADER = ("day", "symbol", "side", "qty", "order_type", "limit_price", "notes")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_orders(path: Path) -> tuple[int, dict | None, str | None]:
    """Load orders_intent from file. Returns (exit_code, data, error). Exit 2 = file IO error."""
    if not path.is_file():
        return 2, None, "orders_file_not_found"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return 2, None, f"orders_file_invalid:{e!s}"
    return 0, data, None


def _validate_and_normalize(data: dict) -> tuple[list[dict] | None, str | None]:
    """
    Validate orders_intent v2 and normalize actions. Returns (rows, error).
    Rows sorted by symbol then side. order_type: missing->MARKET, only MARKET/LIMIT allowed.
    """
    if not isinstance(data, dict):
        return None, "orders_intent_not_dict"
    if "day" not in data:
        return None, "orders_intent_missing_day"
    if not isinstance(data.get("day"), str):
        return None, "orders_intent_day_not_str"
    if "actions" not in data:
        return None, "orders_intent_missing_actions"
    if not isinstance(data.get("actions"), list):
        return None, "orders_intent_actions_not_list"

    day = data["day"]
    rows: list[dict] = []
    for i, action in enumerate(data["actions"]):
        if not isinstance(action, dict):
            return None, "orders_intent_action_not_dict"
        symbol = (action.get("symbol") or "").strip()
        side = (action.get("side") or "").strip()
        if not symbol:
            return None, "orders_intent_action_missing_symbol"
        if not side:
            return None, "orders_intent_action_missing_side"

        order_type = (action.get("order_type") or "MARKET").strip().upper()
        if not order_type:
            order_type = "MARKET"
        if order_type not in ALLOWED_ORDER_TYPES:
            return None, f"order_type_unsupported:{order_type}"

        limit_price = action.get("limit_price")
        if limit_price is not None and order_type == "MARKET":
            limit_price = ""
        elif limit_price is not None:
            limit_price = str(limit_price).strip()
        else:
            limit_price = "" if order_type == "MARKET" else ""

        qty = action.get("qty")
        qty_str = str(qty).strip() if qty is not None else ""
        notes = (action.get("notes") or "").strip()

        rows.append({
            "day": day,
            "symbol": symbol,
            "side": side,
            "qty": qty_str,
            "order_type": order_type,
            "limit_price": limit_price,
            "notes": notes,
        })

    # Sort by symbol then side for stability
    rows.sort(key=lambda r: (r["symbol"], r["side"]))
    return rows, None


def _write_output(out_dir: Path, day: str, rows: list[dict]) -> tuple[bool, str | None]:
    """Write order_ticket.csv and order_ticket.txt. Returns (ok, error)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "order_ticket.csv"
    txt_path = out_dir / "order_ticket.txt"

    try:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(CSV_HEADER)
            for r in rows:
                w.writerow([r[k] for k in CSV_HEADER])

        lines = [
            f"order_ticket {day}",
            f"actions={len(rows)}",
            "",
        ]
        for r in rows:
            lines.append(f"{r['symbol']} {r['side']} {r['order_type']} qty={r['qty'] or '-'} limit={r['limit_price'] or '-'}")
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as e:
        return False, f"file_io_error:{e!s}"

    return True, None


def run(orders_path: Path, out_dir: Path | None = None) -> tuple[int, str | None, Path | None]:
    """
    Load orders, validate, write CSV+TXT. Returns (exit_code, error_message, out_dir_used).
    Exit: 0 ok, 1 validation, 2 file IO.
    If out_dir is None, uses data/out/order_ticket/<DAY>/.
    """
    exit_code, data, load_err = _load_orders(orders_path)
    if exit_code != 0:
        return exit_code, load_err, None

    rows, val_err = _validate_and_normalize(data)
    if val_err is not None:
        return 1, val_err, None

    if out_dir is None:
        out_dir = _repo_root() / "data" / "out" / "order_ticket" / data["day"]
    elif not out_dir.is_absolute():
        out_dir = (_repo_root() / out_dir).resolve()

    ok, write_err = _write_output(out_dir, data["day"], rows)
    if not ok:
        return 2, write_err, None

    return 0, None, out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="FAZ582: Midas Stage-1 order ticket export (CSV+TXT)")
    parser.add_argument("--orders", required=True, help="Path to orders_intent.json")
    parser.add_argument("--out", default=None, help="Output dir (default: data/out/order_ticket/<DAY>/)")
    args = parser.parse_args()

    orders_path = Path(args.orders)
    if not orders_path.is_absolute():
        orders_path = (_repo_root() / orders_path).resolve()

    out_dir = None
    if args.out:
        p = Path(args.out)
        out_dir = p if p.is_absolute() else (_repo_root() / p).resolve()

    exit_code, err, written_dir = run(orders_path, out_dir)
    if err:
        print(err, file=sys.stderr)
        return exit_code

    print(f"order_ticket exported to {written_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
