from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from bist_core.services.advisor import build_advice_for_symbol
from bist_core.services.eod_adapters import build_bars_window, resolve_snapshots_base
from bist_core.services.marketdata import MarketData
from bist_core.services.scan_ranking import rank_scan_candidates
from bist_core.services.symbol_comparison import compare_symbol_results

FAIL_CLOSED_OUTPUT = "INSUFFICIENT EVIDENCE"
LOOKBACK_DAYS = 21


def _fail_closed(reason: str, **extra: Any) -> dict[str, Any]:
    out = {
        "status": "rejected",
        "reason": reason or FAIL_CLOSED_OUTPUT,
        "output": FAIL_CLOSED_OUTPUT,
    }
    out.update(extra)
    return out


def _coerce_symbol(value: Any) -> str:
    return str(value or "").upper().strip()


def _coerce_symbols(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        items = [part.strip() for part in values.replace(",", " ").split() if part.strip()]
    elif isinstance(values, (list, tuple, set)):
        items = [str(item or "").strip() for item in values if str(item or "").strip()]
    else:
        return []

    out: list[str] = []
    for item in items:
        symbol = _coerce_symbol(item)
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def _snapshot_root() -> Path:
    raw = os.environ.get("BIST_CORE_SNAPSHOT_DIR") or "data/eod/snapshots"
    return resolve_snapshots_base(Path(raw))


def _latest_snapshot_day(root: Path) -> str | None:
    if not root.exists() or not root.is_dir():
        return None
    days = sorted(child.name for child in root.iterdir() if child.is_dir())
    valid = [day for day in days if len(day) == 10]
    return valid[-1] if valid else None


def _market_data_and_day() -> tuple[MarketData | None, str | None, Path]:
    root = _snapshot_root()
    day = _latest_snapshot_day(root)
    if day is None:
        return None, None, root
    try:
        return MarketData(root), day, root
    except Exception:
        return None, day, root


def _available_symbols(md: MarketData, day: str) -> set[str]:
    try:
        return {str(symbol).upper().strip() for symbol in md.symbols(day)}
    except Exception:
        return set()


def _advice_payload(symbol: str, day: str, root: Path) -> dict[str, Any] | None:
    try:
        advice = build_advice_for_symbol(symbol, day, root=root)
    except Exception:
        return None

    plan = dict(advice.plan) if isinstance(advice.plan, dict) else {}
    signals = dict(advice.signals) if isinstance(advice.signals, dict) else {}
    return {
        "symbol": advice.symbol,
        "date": advice.date.isoformat() if hasattr(advice.date, "isoformat") else str(advice.date),
        "decision": advice.decision_raw,
        "score": float(advice.score),
        "signals": signals,
        "plan": plan,
        "reason": advice.reason,
        "next_action": advice.next_action,
        "text": advice.text,
        "bars_count": advice.bars_count,
        "lookback_required": advice.lookback_required,
        "gates": dict(advice.gates) if isinstance(advice.gates, dict) else {},
        "entry_status": plan.get("entry_status"),
        "entry_gap_pct": plan.get("entry_gap_pct"),
        "live_gap_pct": signals.get("entry_gap_pct", plan.get("entry_gap_pct")),
        "current_close": plan.get("current_close"),
        "current_close_source": plan.get("live_current_close_source") or plan.get("current_close_source"),
    }


def inspect_symbol_state(symbol: Any) -> dict[str, Any]:
    resolved = _coerce_symbol(symbol)
    if not resolved:
        return _fail_closed("INVALID SYMBOL")

    md, day, root = _market_data_and_day()
    if md is None or day is None:
        return _fail_closed(FAIL_CLOSED_OUTPUT)

    available = _available_symbols(md, day)
    if resolved not in available:
        return _fail_closed("SYMBOL NOT FOUND", symbol=resolved, day=day)

    payload = _advice_payload(resolved, day, root)
    if payload is None:
        return _fail_closed(FAIL_CLOSED_OUTPUT, symbol=resolved, day=day)

    plan = payload.get("plan") or {}
    signals = payload.get("signals") or {}
    return {
        "status": "ok",
        "symbol": resolved,
        "day": day,
        "score_breakdown": dict(signals.get("score_components") or {}),
        "signals": signals,
        "entry": plan.get("entry"),
        "stop": plan.get("stop"),
        "target": plan.get("t1"),
        "current_price_context": {
            "current_close": plan.get("current_close"),
            "current_close_source": plan.get("live_current_close_source") or plan.get("current_close_source"),
            "entry_status": plan.get("entry_status"),
            "entry_gap_pct": plan.get("entry_gap_pct"),
            "live_vs_g_close_pct": plan.get("live_vs_g_close_pct"),
        },
    }


def inspect_ranking(symbols: Any) -> dict[str, Any]:
    resolved = _coerce_symbols(symbols)
    if not resolved:
        return _fail_closed("INVALID SYMBOL LIST")

    md, day, root = _market_data_and_day()
    if md is None or day is None:
        return _fail_closed(FAIL_CLOSED_OUTPUT)

    available = _available_symbols(md, day)
    valid_symbols = [symbol for symbol in resolved if symbol in available]
    if not valid_symbols:
        return _fail_closed("SYMBOLS NOT FOUND", symbols=resolved, day=day)

    rows = [payload for symbol in valid_symbols if (payload := _advice_payload(symbol, day, root)) is not None]
    if not rows:
        return _fail_closed(FAIL_CLOSED_OUTPUT, symbols=valid_symbols, day=day)

    ranked = rank_scan_candidates(rows, top_n=len(rows))
    score_values = [float(row.get("score", 0.0)) for row in ranked.get("ranked") or []]
    return {
        "status": "ok",
        "day": day,
        "sorted_ranking": ranked.get("ranked") or [],
        "score_dispersion": {
            "count": len(score_values),
            "unique_scores": len({round(value, 6) for value in score_values}),
            "spread": round(max(score_values) - min(score_values), 4) if score_values else 0.0,
        },
        "ranking_reasons": {
            "summary": ranked.get("summary") or "",
            "leader_reasons": list((ranked.get("breakdown") or {}).get("leader_reasons") or []),
            "runner_reasons": list((ranked.get("breakdown") or {}).get("runner_reasons") or []),
        },
    }


def inspect_comparison(symbols: Any) -> dict[str, Any]:
    resolved = _coerce_symbols(symbols)
    if len(resolved) < 2:
        return _fail_closed("INVALID SYMBOL LIST")

    md, day, root = _market_data_and_day()
    if md is None or day is None:
        return _fail_closed(FAIL_CLOSED_OUTPUT)

    available = _available_symbols(md, day)
    valid_symbols = [symbol for symbol in resolved if symbol in available]
    if len(valid_symbols) < 2:
        return _fail_closed("SYMBOLS NOT FOUND", symbols=resolved, day=day)

    rows = [payload for symbol in valid_symbols if (payload := _advice_payload(symbol, day, root)) is not None]
    if len(rows) < 2:
        return _fail_closed(FAIL_CLOSED_OUTPUT, symbols=valid_symbols, day=day)

    compared = compare_symbol_results(rows)
    pairwise = compared.get("pairwise") or {}
    return {
        "status": "ok",
        "day": day,
        "comparison_matrix": list((compared.get("decision_object") or {}).get("diff_table") or []),
        "strengths_weaknesses": {
            "leader": list(pairwise.get("leader_reasons") or []),
            "runner_up": list(pairwise.get("runner_reasons") or []),
        },
        "leader_selection_reason": {
            "leader": (compared.get("leader") or {}).get("symbol"),
            "summary": compared.get("summary") or "",
            "pairwise": pairwise,
        },
    }


def validate_dataset(symbol: Any) -> dict[str, Any]:
    resolved = _coerce_symbol(symbol)
    if not resolved:
        return _fail_closed("INVALID SYMBOL")

    md, day, root = _market_data_and_day()
    if md is None or day is None:
        return _fail_closed(FAIL_CLOSED_OUTPUT)

    available = _available_symbols(md, day)
    if resolved not in available:
        return _fail_closed("SYMBOL NOT FOUND", symbol=resolved, day=day)

    missing_fields: list[str] = []
    anomalies: list[str] = []
    completeness = {"close_map": False, "ohlcv": False, "bars_window": False}

    try:
        close_map = md.close_map(day)
        completeness["close_map"] = resolved in close_map and close_map.get(resolved) is not None
        if not completeness["close_map"]:
            missing_fields.append("close")
    except Exception:
        close_map = {}
        missing_fields.append("close")

    ohlcv_row: dict[str, Any] = {}
    try:
        if md.has_ohlcv(day):
            ohlcv_map = md.ohlcv_map(day)
            if resolved in ohlcv_map:
                ohlcv_row = dict(ohlcv_map.get(resolved) or {})
                completeness["ohlcv"] = True
    except Exception:
        ohlcv_row = {}

    for field_name in ("open", "high", "low", "close", "volume"):
        if field_name not in ohlcv_row:
            missing_fields.append(field_name)

    try:
        bars = build_bars_window(day, md, root, LOOKBACK_DAYS)
    except Exception:
        bars = []
    symbol_bars = [bar for bar in bars if getattr(bar, "symbol", None) == resolved]
    completeness["bars_window"] = bool(symbol_bars)
    if not symbol_bars:
        anomalies.append("missing_bars_window")

    seen_days: set[str] = set()
    for bar in symbol_bars:
        bar_day = getattr(bar, "date", None)
        bar_key = bar_day.isoformat() if hasattr(bar_day, "isoformat") else str(bar_day)
        if bar_key in seen_days:
            anomalies.append("duplicate_bar_day")
        seen_days.add(bar_key)

        close_value = getattr(bar, "close", None)
        high_value = getattr(bar, "high", None)
        low_value = getattr(bar, "low", None)
        volume_value = getattr(bar, "volume", None)
        if close_value is None:
            anomalies.append("missing_close_value")
        if high_value is not None and low_value is not None and float(high_value) < float(low_value):
            anomalies.append("high_below_low")
        if volume_value is not None and int(volume_value) < 0:
            anomalies.append("negative_volume")

    if completeness["close_map"] and ohlcv_row:
        close_value = close_map.get(resolved)
        if close_value is not None and ohlcv_row.get("close") is not None:
            try:
                if round(float(close_value), 6) != round(float(ohlcv_row.get("close")), 6):
                    anomalies.append("close_mismatch")
            except Exception:
                anomalies.append("close_mismatch")

    return {
        "status": "ok",
        "symbol": resolved,
        "day": day,
        "data_completeness": completeness,
        "missing_fields": sorted(set(missing_fields)),
        "anomalies": sorted(set(anomalies)),
    }
