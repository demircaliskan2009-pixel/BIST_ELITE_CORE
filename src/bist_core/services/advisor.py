from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from functools import lru_cache
from pathlib import Path
import json
from typing import Any, Dict, List, Optional, Tuple

from bist_core import config
from bist_core.services import eventstore
from bist_core.services.marketdata import MarketData
from bist_core.services.eod_adapters import build_bars_window, build_bands_for_day, resolve_snapshots_base, materialize_snapshots_from_inbox
from bist_core.strategy import engine


@dataclass
class Advice:
    symbol: str
    date: Date
    decision_raw: str
    score: float
    signals: Any
    plan: Any | None
    text: str
    reason: Optional[str] = None  # HOLD: explicit reason (e.g. InsufficientHistory)
    next_action: Optional[str] = None  # HOLD: explicit next action
    bars_count: Optional[int] = None  # FAZ144: bars available for symbol
    lookback_required: Optional[int] = None  # FAZ144: required lookback from strat_cfg
    gates: Optional[Dict[str, Dict[str, str]]] = None  # FAZ386: PASS/FAIL per gate with reason


def _build_gates_from_engine_result(
    decision_raw: str,
    score: float,
    engine_reason: Optional[str],
) -> Dict[str, Dict[str, str]]:
    """FAZ386: Build gates dict from engine result; deterministic key order."""
    if engine_reason == "no_band":
        return {"band": {"outcome": "FAIL", "reason": "no_band"}}
    if engine_reason == "band_violation":
        return {
            "band": {"outcome": "PASS", "reason": "OK"},
            "levels": {"outcome": "FAIL", "reason": "band_violation"},
        }
    score_ok = decision_raw in ("BUY", "WATCH")
    return {
        "band": {"outcome": "PASS", "reason": "OK"},
        "levels": {"outcome": "PASS", "reason": "OK"},
        "score": {"outcome": "PASS" if score_ok else "FAIL", "reason": f"score={score:.2f}"},
    }


def build_advice_for_symbol(
    symbol: str,
    date: Date | str,
    root: Optional[Path | str] = None,
) -> Advice:
    try:
        day = Date.fromisoformat(date) if isinstance(date, str) else date

        # Config helper'ını kullanarak kurulum adımlarını takip et
        config.load_config()

        base = Path(root) if root is not None else Path("data/eod/snapshots")
        md = MarketData(base)

        day_str = day.isoformat()
        bars, bands, kap_events, gates_cfg, strat_cfg = _get_day_context(day_str, str(base))

        if not bars:
            return _safe_advice(
                symbol, day, "NoBars", gates={"bars_available": {"outcome": "FAIL", "reason": "NoBars"}}
            )

        bars_for_symbol = [b for b in bars if b.symbol == symbol]
        mom_slow = strat_cfg.get("mom_slow", 20)
        vol_window = strat_cfg.get("vol_window", 20)
        required_lookback = max(mom_slow, vol_window)

        if len(bars_for_symbol) < required_lookback:
            return _insufficient_history_advice(symbol, day, len(bars_for_symbol), required_lookback)

        cfg = config.CORE
        decisions = engine.decide(
            symbols=[symbol],
            bars=bars,
            bands=bands,
            kap_events=kap_events,
            cfg=cfg,
            gates_cfg=gates_cfg,
            strat_cfg=strat_cfg,
        )
        if not decisions:
            return _insufficient_history_advice(symbol, day, len(bars_for_symbol), required_lookback)

        result = decisions[0]

        decision_raw = result.get("decision_raw", result.get("decision", "PASS"))
        score = float(result.get("score", 0.0))
        signals = result.get("signals", [])
        plan = result.get("plan")
        engine_reason = result.get("reason")

        gates = _build_gates_from_engine_result(decision_raw, score, engine_reason)

        has_ohlcv = False
        try:
            if hasattr(md, "has_ohlcv"):
                has_ohlcv = md.has_ohlcv(day_str)
        except Exception:
            has_ohlcv = False

        events, events_errors = _load_events(symbol, day_str)

        text = _render_advice_text(
            symbol,
            day,
            decision_raw,
            score,
            signals,
            plan,
            has_ohlcv,
            events,
            events_errors,
        )

        return Advice(
            symbol=symbol,
            date=day,
            decision_raw=decision_raw,
            score=score,
            signals=signals,
            plan=plan,
            text=text,
            bars_count=len(bars_for_symbol),
            lookback_required=required_lookback,
            gates=gates,
        )
    except Exception as exc:
        err = exc.__class__.__name__
        return _safe_advice(symbol, _safe_date(date), err)


def _render_advice_text(
    symbol: str,
    day: Date,
    decision_raw: str,
    score: float,
    signals: Any,
    plan: Any | None,
    has_ohlcv: bool,
    events: list[eventstore.EventRecord],
    events_errors: list[str],
) -> str:
    decision_sentence = f"{symbol} için karar {decision_raw}; skor {score:.2f}."

    summaries = _summarize_signals(signals)
    if summaries:
        signal_sentence = "Sinyal özeti: " + ", ".join(summaries[:4]) + "."
    else:
        signal_sentence = "Sinyal seti boş ya da sınırlı, karar mevcut fiyat verisine dayalı."

    plan_sentence = ""
    if isinstance(plan, dict):
        entry = plan.get("entry")
        stop = plan.get("stop")
        t1 = plan.get("t1")
        if entry is not None or stop is not None or t1 is not None:
            plan_sentence = f"Plan: entry {entry}, stop {stop}, t1 {t1}."

    coverage_note = ""
    if decision_raw == "PASS" and score == 0.0 and not has_ohlcv:
        coverage_note = "Eksik veri: sadece close var; hacim/turnover olmadığı için hacim sinyali devre dışı."

    reconsider_sentence = (
        "Fiyat bandı dışına çıkma, ters haber akışı veya güçlü hacim kırılması olursa yeniden değerlendir."
    )

    first_paragraph = f"{decision_sentence} {signal_sentence}"
    second_paragraph = " ".join(part for part in [plan_sentence, coverage_note, reconsider_sentence] if part)
    events_paragraph = _render_events_section(events, events_errors)

    return f"{first_paragraph}\n\n{second_paragraph}\n\n{events_paragraph}".strip()


def _safe_date(value: Date | str) -> Date:
    if isinstance(value, Date):
        return value
    try:
        return Date.fromisoformat(value)
    except Exception:
        return Date.today()


def _insufficient_history_advice(
    symbol: str,
    day: Date | str,
    bars_count: int,
    required_lookback: int,
) -> Advice:
    """Fail-closed: bars var ama yetersiz; PASS + Güvenli mod + NoDecision."""
    day_value = _safe_date(day)
    day_str = day_value.isoformat()
    events, events_errors = _load_events(symbol, day_str)
    events_paragraph = _render_events_section(events, events_errors)
    err_detail = f"NoDecision: InsufficientHistory: {bars_count} < {required_lookback}"
    text = (
        f"Güvenli mod: {err_detail}. "
        f"Mevcut bar sayısı: {bars_count}, gerekli lookback: {required_lookback}. "
        "Daha fazla günlük veri ekleyin."
    )
    text = f"{text}\n\n{events_paragraph}"
    gates = {
        "bars_available": {"outcome": "PASS", "reason": "OK"},
        "lookback": {"outcome": "FAIL", "reason": f"InsufficientHistory: {bars_count} < {required_lookback}"},
    }
    return Advice(
        symbol=symbol,
        date=day_value,
        decision_raw="PASS",
        score=0.0,
        signals=[],
        plan=None,
        text=text,
        reason="InsufficientHistory",
        next_action="Daha fazla günlük veri ekleyin.",
        bars_count=bars_count,
        lookback_required=required_lookback,
        gates=gates,
    )


def _safe_advice(
    symbol: str,
    day: Date | str,
    err: str,
    gates: Optional[Dict[str, Dict[str, str]]] = None,
) -> Advice:
    """Fail-closed: PASS + Güvenli mod + NoBars/NoDecision marker."""
    day_value = _safe_date(day)
    day_str = day_value.isoformat()
    try:
        events, events_errors = _load_events(symbol, day_str)
        events_paragraph = _render_events_section(events, events_errors)
    except Exception:
        events_paragraph = "Olaylar (KAP/diğer):\nKAP/olay verisi yok veya erişilemedi."
    # Ensure NoBars or NoDecision in text (canonical markers)
    marker = err if err in ("NoBars", "NoDecision") else f"NoDecision: {err}"
    text = f"Güvenli mod: {marker}. Veri veya karar üretilemedi; snapshot ve konfigürasyonu kontrol edin."
    text = f"{text}\n\n{events_paragraph}"
    return Advice(
        symbol=symbol,
        date=day_value,
        decision_raw="PASS",
        score=0.0,
        signals=[],
        plan=None,
        text=text,
        gates=gates,
    )


@lru_cache(maxsize=64)
def _get_day_context(
    day_str: str, root_path_str: str
) -> Tuple[
    List[Any],
    List[Any],
    Dict[str, Any],
    Dict[str, Any],
    Dict[str, Any],
]:
    """
    Aynı gün ve root için bars, bands, kap_events, gates_cfg, strat_cfg bir kez hazırlanır.
    Cache sayesinde tekrar çağrılınca pahalı hesaplar yapılmaz.
    """
    root = Path(root_path_str)
    md = MarketData(root)

    strat_cfg = _load_json_config("config/strategy.json")
    mom_slow = strat_cfg.get("mom_slow", 20)
    vol_window = strat_cfg.get("vol_window", 20)
    lookback = max(mom_slow, vol_window) + 1

    data_root = Path(root) if root else Path("data")

    base = resolve_snapshots_base(data_root)

    materialize_snapshots_from_inbox(data_root=data_root, snapshots_base=base, symbols=None, end_day=day_str, lookback=lookback)

    bars = build_bars_window(day_str, md, base, lookback)
    cfg = config.CORE
    bands = build_bands_for_day(day_str, md, cfg)
    kap_events = _load_kap_events(md, day_str)
    gates_cfg = _load_json_config("config/gates.json")

    return (bars, bands, kap_events, gates_cfg, strat_cfg)


def _load_kap_events(md: MarketData, day: str):
    prov = getattr(md, "_prov", None)
    if prov and hasattr(prov, "kap_events"):
        try:
            return prov.kap_events(day)
        except Exception:
            return {}
    return {}


def _load_json_config(rel_path: str) -> Dict[str, Any]:
    try:
        cfg_path = config.REPO_ROOT / rel_path
        with cfg_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_events(
    symbol: str,
    day_str: str,
) -> tuple[list[eventstore.EventRecord], list[str]]:
    try:
        return eventstore.load_events_for_symbol_day(symbol, day_str)
    except Exception as exc:
        return [], [f"EventStoreError:{exc.__class__.__name__}"]


def _render_events_section(
    events: list[eventstore.EventRecord],
    errors: list[str],
) -> str:
    header = "Olaylar (KAP/diğer):"
    if events:
        items = [f"- {ev.title}" for ev in events[:3]]
        return "\n".join([header, *items])
    if errors:
        return f"{header}\nKAP/olay verisi yok veya erişilemedi."
    return f"{header}\nKAP/olay verisi yok veya erişilemedi."


def _summarize_signals(signals: Any) -> List[str]:
    summaries: List[str] = []

    if isinstance(signals, dict):
        mom = signals.get("mom")
        news = signals.get("news")
        vol = signals.get("vol")
        if mom is not None:
            summaries.append(_format_momentum(mom))
        if news is not None:
            summaries.append(_format_news(news))
        if vol is not None:
            summaries.append(_format_volume(vol))
        return [s for s in summaries if s]

    if isinstance(signals, list):
        for item in signals:
            if isinstance(item, str):
                summaries.append(item)
                continue
            if isinstance(item, dict):
                label = item.get("label") or item.get("name") or item.get("signal")
                value = item.get("value")
                if label is not None and value is not None:
                    summaries.append(f"{label}: {value}")
                elif label is not None:
                    summaries.append(str(label))
                continue
            summaries.append(str(item))

    return [s for s in summaries if s]


def _format_momentum(value: int) -> str:
    if value > 0:
        return "Momentum pozitif"
    if value < 0:
        return "Momentum negatif"
    return "Momentum nötr"


def _format_news(value: int) -> str:
    if value > 0:
        return "KAP haberleri pozitif"
    if value < 0:
        return "KAP haberleri negatif"
    return "KAP haberleri nötr"


def _format_volume(value: int) -> str:
    if value > 0:
        return "Hacim artışı var"
    return "Hacim artışı yok"
