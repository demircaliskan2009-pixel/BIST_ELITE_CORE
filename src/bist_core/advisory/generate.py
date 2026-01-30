"""Generate advice_records.jsonl (schema v1) under outdir/advice/<day>/; stable sort by symbol; deterministic floats."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_close_map(snapshot_root: Path, day_str: str) -> Dict[str, float]:
    """Load symbol -> close from snapshot_root/<day>/snapshot.csv. Deterministic (sorted)."""
    path = snapshot_root / day_str / "snapshot.csv"
    if not path.is_file():
        return {}
    out: Dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            sym = row.get("symbol", "").strip()
            if not sym:
                continue
            c = row.get("close")
            try:
                out[sym] = round(float(c), 6) if c not in (None, "") else 0.0
            except (TypeError, ValueError):
                out[sym] = 0.0
    return dict(sorted(out.items()))


def _record_v1(
    symbol: str,
    score: float,
    side: str,
    reason: str,
    close: float,
) -> Dict[str, Any]:
    """Schema v1: symbol, score, side, reason, inputs.close."""
    return {
        "symbol": symbol,
        "score": round(float(score), 6),
        "side": str(side).upper() if str(side).upper() in ("BUY", "SELL") else "HOLD",
        "reason": str(reason),
        "inputs": {"close": round(float(close), 6)},
    }


def generate_advice(
    day: str,
    snapshot_root: Path | str,
    outdir: Path | str,
    *,
    symbols: Optional[List[str]] = None,
    top_n: Optional[int] = None,
    safe_mode_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Write outdir/advice/<day>/advice_records.jsonl (schema v1); stable sort by symbol; deterministic floats.
    Returns {path, total, errors, records} for pipeline use.
    """
    root = Path(snapshot_root)
    out_path = Path(outdir)
    day_str = str(day)
    close_map = _load_close_map(root, day_str)
    symbols = sorted(symbols) if symbols is not None else sorted(close_map.keys())

    from bist_core.services.advisor import build_advice_for_symbol

    records: List[Dict[str, Any]] = []
    errors = 0
    for symbol in symbols:
        close = close_map.get(symbol, 0.0)
        try:
            advice = build_advice_for_symbol(symbol, day_str, root=root)
            raw = str(advice.decision_raw or "PASS").upper()
            side = "BUY" if raw == "BUY" else ("SELL" if raw == "SELL" else "HOLD")
            reason = advice.text or ""
            if safe_mode_reason:
                reason = f"Güvenli mod: {safe_mode_reason} " + reason
            rec = _record_v1(
                symbol=advice.symbol,
                score=advice.score,
                side=side,
                reason=reason,
                close=close,
            )
        except Exception:
            rec = _record_v1(symbol=symbol, score=0.0, side="HOLD", reason="advice_error", close=close)
            errors += 1
        records.append(rec)

    if top_n is not None and top_n > 0 and records:
        records = sorted(records, key=lambda r: (-float(r["score"]), r["symbol"]))[:top_n]
    records = sorted(records, key=lambda r: r["symbol"])

    advice_dir = out_path / "advice" / day_str
    advice_dir.mkdir(parents=True, exist_ok=True)
    target = advice_dir / "advice_records.jsonl"
    tmp = target.with_name(target.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False))
            f.write("\n")
    tmp.replace(target)

    return {
        "path": str(advice_dir),
        "total": len(records),
        "errors": errors,
        "records": records,
    }
