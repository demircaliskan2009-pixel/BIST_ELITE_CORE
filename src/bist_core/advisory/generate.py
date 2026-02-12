"""Generate advice_records.jsonl (schema v1) under outdir/advice/<day>/; stable sort by symbol; deterministic floats."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bist_core.models.base import ModelPlugin


def _resolve_model_plugin(
    model_plugin: Optional["ModelPlugin"],
    cache_root: Optional[Path] = None,
) -> Optional["ModelPlugin"]:
    """
    If model_plugin is None and USE_OPENAI_MODEL=1 + OPENAI_API_KEY are set,
    return OpenAIModel instance. Otherwise return model_plugin as-is.
    cache_root: if provided, cache_dir = cache_root / "_cache" / "openai".
    """
    if model_plugin is not None:
        return model_plugin
    if os.environ.get("USE_OPENAI_MODEL") == "1" and os.environ.get("OPENAI_API_KEY", "").strip():
        try:
            from bist_core.models.openai_model import OpenAIModel
            cache_dir = (cache_root / "_cache" / "openai") if cache_root else None
            return OpenAIModel(cache_dir=cache_dir)
        except (ImportError, ValueError):
            return None
    return None


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


def _score_to_side(score: float) -> str:
    """Map score to BUY/SELL/HOLD (deterministic)."""
    if score > 0:
        return "BUY"
    if score < 0:
        return "SELL"
    return "HOLD"


def generate_advice(
    day: str,
    snapshot_root: Path | str,
    outdir: Path | str,
    *,
    symbols: Optional[List[str]] = None,
    top_n: Optional[int] = None,
    safe_mode_reason: Optional[str] = None,
    model_plugin: Optional["ModelPlugin"] = None,
) -> Dict[str, Any]:
    """
    Write outdir/advice/<day>/advice_records.jsonl (schema v1); stable sort by symbol; deterministic floats.
    If model_plugin is set, use model.predict(features) for scores; else use build_advice_for_symbol.
    Returns {path, total, errors, records} for pipeline use.
    When USE_OPENAI_MODEL=1 and OPENAI_API_KEY are set, OpenAIModel is used automatically.
    """
    root = Path(snapshot_root)
    out_path = Path(outdir)
    day_str = str(day)
    close_map = _load_close_map(root, day_str)
    symbols = sorted(symbols) if symbols is not None else sorted(close_map.keys())

    model_plugin = _resolve_model_plugin(model_plugin, cache_root=out_path)

    records: List[Dict[str, Any]] = []
    errors = 0

    if model_plugin is not None:
        features = [
            {"symbol": s, "close": close_map.get(s, 0.0)}
            for s in symbols
        ]
        try:
            scores = model_plugin.predict(features)
        except RuntimeError:
            raise
        except Exception:
            scores = [0.0] * len(symbols)
            errors += len(symbols)
        if len(scores) != len(symbols):
            scores = (scores + [0.0] * len(symbols))[:len(symbols)]
        for i, symbol in enumerate(symbols):
            close = close_map.get(symbol, 0.0)
            score = float(scores[i]) if i < len(scores) else 0.0
            side = _score_to_side(score)
            reason = "model"
            if safe_mode_reason:
                reason = f"Güvenli mod: {safe_mode_reason} " + reason
            records.append(
                _record_v1(symbol=symbol, score=score, side=side, reason=reason, close=close)
            )
    else:
        from bist_core.services.advisor import build_advice_for_symbol

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
