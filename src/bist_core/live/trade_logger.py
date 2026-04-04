"""Append-only trade log with safe in-place close updates (stdlib only, deterministic)."""

from __future__ import annotations

import csv
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bist_core.analytics.expectancy import tracker

# Exactly: timestamp,symbol,action,entry,stop,target,edge,confidence,status
FIELDNAMES = [
    "timestamp",
    "symbol",
    "action",
    "entry",
    "stop",
    "target",
    "edge",
    "confidence",
    "status",
]


def _utc_ts() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_float(v: Any) -> float:
    try:
        x = float(v)
        return x if x == x else 0.0
    except (TypeError, ValueError):
        return 0.0


def _normalize_symbol(s: str) -> str:
    return str(s).upper().replace("IMKBH'", "").strip()


def _safe_float(x, default=0.0):
    try:
        v = float(x)
        if v != v:  # NaN check
            return default
        if v == float("inf") or v == float("-inf"):
            return default
        return v
    except:
        return default


def _is_enter_action(action: str) -> bool:
    a = str(action).strip().lower()
    return a.startswith("enter")


def _is_short_action(action: str) -> bool:
    return str(action).strip().lower() == "enter_short"


def _closed_status(win: bool, exit_px: float, pnl: float) -> str:
    """Nine-column CSV: pack exit + pnl into ``status`` as CLOSED_WIN|exit|pnl (or CLOSED_LOSS|...)."""
    tag = "CLOSED_WIN" if win else "CLOSED_LOSS"
    return f"{tag}|{exit_px}|{round(pnl, 8)}"


class TradeLogger:
    """CSV trade log at ``logs/trades.csv`` (created automatically)."""

    def __init__(self, file_path: str = "logs/trades.csv") -> None:
        self._path = os.path.normpath(file_path)
        self._ensure_file()

    def _ensure_file(self) -> None:
        d = os.path.dirname(self._path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        if not os.path.isfile(self._path):
            with open(self._path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
                w.writeheader()

    def _read_rows(self) -> List[Dict[str, str]]:
        if not os.path.isfile(self._path) or os.path.getsize(self._path) == 0:
            return []
        rows: List[Dict[str, str]] = []
        with open(self._path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                if not row:
                    continue
                rows.append({k: (row.get(k) or "").strip() for k in FIELDNAMES})
        return rows

    def _write_rows_atomic(self, rows: List[Dict[str, str]]) -> None:
        d = os.path.dirname(self._path) or "."
        fd, tmp = tempfile.mkstemp(prefix="trades_", suffix=".csv", dir=d)
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
                w.writeheader()
                for row in rows:
                    w.writerow({k: row.get(k, "") for k in FIELDNAMES})
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _has_open(self, symbol: str, rows: Optional[List[Dict[str, str]]] = None) -> bool:
        u = str(symbol).strip().upper()
        data = rows if rows is not None else self._read_rows()
        for row in data:
            if str(row.get("symbol", "")).strip().upper() != u:
                continue
            st = str(row.get("status", "")).strip().upper()
            # Only bare OPEN counts; closed rows use CLOSED_*|... in status.
            if st == "OPEN":
                return True
        return False

    def _get_open_position(
        self, symbol: str, rows: Optional[List[Dict[str, str]]] = None
    ) -> Optional[Dict[str, str]]:
        u = str(symbol).strip().upper()
        data = rows if rows is not None else self._read_rows()
        for row in data:
            if str(row.get("symbol", "")).strip().upper() != u:
                continue
            st = str(row.get("status", "")).strip().upper()
            if st == "OPEN":
                return row
        return None

    def log_new_trade(self, decision: Dict[str, Any]) -> bool:
        """
        Append one row with status=OPEN if action starts with 'enter' and symbol not already OPEN.
        Returns True if a row was written.
        """
        if not isinstance(decision, dict):
            return False
        action = str(decision.get("action", "")).strip()
        if not _is_enter_action(action):
            return False
        sym = str(decision.get("symbol", "")).strip()
        if not sym:
            return False
        sym_u = sym.upper()

        rows = self._read_rows()

        edge_score = decision.get("edge_score")
        if edge_score is None:
            raise RuntimeError("EDGE_SSOT_VIOLATION")
        edge_new = float(edge_score)

        existing = self._get_open_position(sym_u, rows)
        if existing:
            edge_old = _safe_float(existing.get("edge"), 0.0)
            decision_lbl = "allow" if edge_new > edge_old else "block"
            print(
                {
                    "LOGGER_POSITION_CHECK": {
                        "symbol": sym_u,
                        "edge_old": edge_old,
                        "edge_new": edge_new,
                        "decision": decision_lbl,
                    }
                },
                flush=True,
            )
            EPS = 1e-6

            if edge_new < (edge_old - EPS):
                return False

        row = {
            "timestamp": _utc_ts(),
            "symbol": sym_u,
            "action": action,
            "entry": str(_parse_float(decision.get("entry"))),
            "stop": str(_parse_float(decision.get("stop_loss"))),
            "target": str(_parse_float(decision.get("target"))),
            "edge": str(_parse_float(edge_new)),
            "confidence": str(_parse_float(decision.get("confidence"))),
            "status": "OPEN",
        }

        rows.append(row)
        self._write_rows_atomic(rows)
        return True

    def update_trade(
        self,
        symbol: str,
        exit_price: float,
        *,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Close first OPEN row for ``symbol``: status set to CLOSED_WIN|exit|pnl or CLOSED_LOSS|exit|pnl.
        Returns True if a row was updated.
        """
        sym_u = str(symbol).strip().upper()
        try:
            ex = float(exit_price)
            if ex != ex:
                return False
        except (TypeError, ValueError):
            return False

        rows = self._read_rows()
        updated = False
        for i, row in enumerate(rows):
            if str(row.get("symbol", "")).strip().upper() != sym_u:
                continue
            st = str(row.get("status", "")).strip().upper()
            if st != "OPEN":
                continue

            entry = _parse_float(row.get("entry"))
            act = str(row.get("action", "")).strip().lower()
            if _is_short_action(act):
                pnl = entry - ex
            else:
                pnl = ex - entry

            if reason is not None:
                r = str(reason).lower()
                if "target_hit" in r and pnl <= 0:
                    raise RuntimeError("INVALID PNL: target_hit but pnl <= 0")
                if ("stop_loss" in r or "stop_hit" in r) and pnl >= 0:
                    raise RuntimeError("INVALID PNL: stop_hit but pnl >= 0")

            win = pnl > 0.0
            edge = _safe_float(row.get("edge"), 0.0)
            rows[i] = {
                **row,
                "status": _closed_status(win, ex, pnl),
            }
            tracker.record_trade(edge, pnl)

            print(
                {
                    "EDGE_PNL_FINAL": {
                        "edge": edge,
                        "pnl": float(pnl),
                        "result": "WIN" if pnl > 0 else "LOSS",
                    }
                },
                flush=True,
            )
            updated = True
            break

        if updated:
            self._write_rows_atomic(rows)
        return updated


def update_trade_close(symbol: str, pnl: float) -> bool:
    """Close latest OPEN row for ``symbol`` using explicit price-delta ``pnl`` (per share)."""
    tl = TradeLogger()
    try:
        pnl_v = float(pnl)
        if pnl_v != pnl_v:
            return False
    except (TypeError, ValueError):
        return False

    rows = tl._read_rows()
    sym_n = _normalize_symbol(symbol)

    open_rows = [
        (i, row)
        for i, row in enumerate(rows)
        if _normalize_symbol(str(row.get("symbol") or "")) == sym_n
        and row.get("status") == "OPEN"
    ]

    if not open_rows:
        print({"ERROR_NO_OPEN_ROW": symbol}, flush=True)
        return False

    open_rows.sort(
        key=lambda x: x[1].get("timestamp", ""), reverse=True
    )

    idx, row = open_rows[0]

    entry = _parse_float(row.get("entry"))
    act = str(row.get("action", "")).strip().lower()
    if _is_short_action(act):
        ex = entry - pnl_v
    else:
        ex = entry + pnl_v

    win = pnl_v > 0.0
    edge = _safe_float(row.get("edge"), 0.0)
    CLOSED_STATUS = _closed_status(win, ex, pnl_v)
    row["status"] = CLOSED_STATUS
    rows[idx] = row

    extra_rm = [
        i
        for i, r in enumerate(rows)
        if i != idx
        and _normalize_symbol(str(r.get("symbol") or "")) == sym_n
        and r.get("status") == "OPEN"
    ]
    for j in sorted(extra_rm, reverse=True):
        rows.pop(j)
        if j < idx:
            idx -= 1

    tracker.record_trade(edge, pnl_v)

    print(
        {
            "EDGE_PNL_LINK_FINAL": {
                "edge": float(edge),
                "pnl": float(pnl),
                "abs_pnl": abs(float(pnl)),
                "result": "WIN" if pnl > 0 else "LOSS",
            }
        },
        flush=True,
    )

    try:
        tl._write_rows_atomic(rows)
    except Exception:
        return False

    verify = tl._read_rows()
    for vr in verify:
        if (
            _normalize_symbol(str(vr.get("symbol") or "")) == sym_n
            and str(vr.get("status", "")).strip().upper() == "OPEN"
        ):
            return False

    return True


__all__ = [
    "TradeLogger",
    "FIELDNAMES",
    "update_trade_close",
    "_safe_float",
    "_normalize_symbol",
]
