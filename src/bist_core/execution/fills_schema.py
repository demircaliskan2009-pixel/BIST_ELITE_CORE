"""FAZ597: Fills CSV schema — validate, normalize. Offline, deterministic."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

REQUIRED_COLS = ["ts", "symbol", "side", "qty", "price"]
OPTIONAL_COLS = ["fee_try"]
VALID_SIDES = frozenset({"BUY", "SELL"})


@dataclass
class Fill:
    ts: str  # ISO format
    symbol: str
    side: str
    qty: int
    price: Decimal
    fee_try: Decimal
    _row_index: int = 0


def _normalize_header(row: dict) -> dict:
    """Case-insensitive header lookup; return normalized keys."""
    col_map = {c.upper(): c for c in REQUIRED_COLS + OPTIONAL_COLS}
    out = {}
    for k, v in row.items():
        uk = (k or "").strip().upper()
        if uk in col_map:
            out[col_map[uk]] = v
    return out


def _parse_ts(val: str) -> str:
    """Parse timestamp; return ISO string. Naive treated as local."""
    s = (val or "").strip()
    if not s:
        raise ValueError("ts empty")
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt.isoformat()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.isoformat()
        except ValueError:
            continue
    raise ValueError(f"ts invalid: {s!r}")


def read_fills_csv(path: Path) -> list[Fill]:
    """
    Read fills CSV. Strict header match (case-insensitive).
    Validate: qty>0, price>0, side in {BUY,SELL}.
    Parse ts as datetime; use Decimal for price/fee_try.
    Return sorted by (ts, symbol, side) stable; tie-breaker by row index.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"fills file not found: {path}")

    fills: list[Fill] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        raw_headers = reader.fieldnames or []
        header_upper = {h.strip().upper() for h in raw_headers if h}
        required_upper = {c.upper() for c in REQUIRED_COLS}
        if not required_upper.issubset(header_upper):
            missing = required_upper - header_upper
            raise ValueError(f"fills CSV missing required columns: {missing}")

        for idx, row in enumerate(reader):
            nr = _normalize_header(row)
            if not all(nr.get(c) for c in REQUIRED_COLS):
                continue
            try:
                ts = _parse_ts(nr["ts"])
                symbol = (nr["symbol"] or "").strip().upper()
                if not symbol:
                    raise ValueError("symbol empty")
                side = (nr["side"] or "").strip().upper()
                if side not in VALID_SIDES:
                    raise ValueError(f"side must be BUY or SELL: {side!r}")
                qty = int(float(nr["qty"]))
                if qty <= 0:
                    raise ValueError(f"qty must be > 0: {qty}")
                price = Decimal(str(nr["price"]))
                if price <= 0:
                    raise ValueError(f"price must be > 0: {price}")
                fee_str = (nr.get("fee_try") or "").strip()
                fee_try = Decimal(fee_str) if fee_str else Decimal("0")
                if fee_try < 0:
                    raise ValueError(f"fee_try must be >= 0: {fee_try}")
            except (ValueError, TypeError) as e:
                raise ValueError(f"row {idx + 2}: {e}") from e

            fills.append(
                Fill(
                    ts=ts,
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    price=price,
                    fee_try=fee_try,
                    _row_index=idx,
                )
            )

    fills.sort(key=lambda f: (f.ts, f.symbol, f.side, f._row_index))
    return fills
