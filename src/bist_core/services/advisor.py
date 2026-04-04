from __future__ import annotations

from datetime import date as _dt_date, datetime as _dt_datetime

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

# FAZ593_SCORE_ENRICHMENT_START
def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None

def _bar_num(bar: Any, key: str) -> Optional[float]:
    if isinstance(bar, dict):
        return _coerce_float(bar.get(key))
    return _coerce_float(getattr(bar, key, None))

def _augment_engine_result_with_bar_context(result: Dict[str, Any], bars_for_symbol: List[Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result

    closes = [x for x in (_bar_num(b, "close") for b in bars_for_symbol) if x is not None]
    vols = [x for x in (_bar_num(b, "volume") for b in bars_for_symbol) if x is not None]

    if len(closes) < 2:
        return result

    c = closes[-1]
    p1 = closes[-2]
    ret1 = ((c / p1) - 1.0) if p1 else 0.0

    win20 = closes[-20:] if len(closes) >= 20 else closes
    hh = max(win20)
    ll = min(win20)
    range_pos = 0.5 if hh == ll else (c - ll) / (hh - ll)

    vol_ratio = None
    if len(vols) >= 6:
        base = [v for v in vols[-6:-1] if v is not None and v > 0]
        if base and vols[-1] and vols[-1] > 0:
            vol_ratio = vols[-1] / (sum(base) / len(base))

    out = dict(result)
    base_score = float(out.get("score", 0.0))

    ret_component = max(min(ret1 * 5.0, 0.22), -0.22)
    range_component = max(min((range_pos - 0.50) * 0.45, 0.22), -0.22)

    vol_component = 0.0
    if vol_ratio is not None:
        vol_component = max(min((vol_ratio - 1.0) * 0.18, 0.18), -0.10)

    entry_component = 0.0
    entry_gap_pct = None
    entry_status = None

    plan_obj = out.get("plan")
    plan_preview = dict(plan_obj) if isinstance(plan_obj, dict) else {}
    entry = _coerce_float(plan_preview.get("entry"))
    if entry is not None and entry > 0:
        entry_gap = (c / entry) - 1.0
        entry_gap_pct = entry_gap * 100.0

        if entry_gap > 0.01:
            entry_status = "extended_above_entry"
            entry_component = -min(0.55, 0.10 + max(0.0, entry_gap - 0.01) * 8.0)
        elif entry_gap < -0.01:
            entry_status = "below_entry_trigger"
            entry_component = max(-0.18, entry_gap * 3.0)
        else:
            entry_status = "near_entry"
            entry_component = max(0.08, 0.16 - abs(entry_gap) * 8.0)

    adj = base_score + ret_component + range_component + vol_component + entry_component
    out["score"] = round(adj, 4)

    raw = str(out.get("decision_raw", "PASS") or "PASS").upper()
    if adj >= 1.35:
        out["decision_raw"] = "BUY"
    elif adj >= 0.35:
        out["decision_raw"] = "WATCH" if raw in ("PASS", "WATCH", "HOLD") else raw
    else:
        out["decision_raw"] = "PASS" if raw in ("PASS", "WATCH", "HOLD") else raw

    signals = out.get("signals", {})
    if isinstance(signals, dict):
        sig = dict(signals)
        sig["ret1_pct"] = round(ret1 * 100.0, 2)
        sig["range_pos"] = round(range_pos, 3)
        if vol_ratio is not None:
            sig["vol_ratio"] = round(vol_ratio, 2)
        if entry_gap_pct is not None:
            sig["entry_gap_pct"] = round(entry_gap_pct, 2)
        sig["score_components"] = {
            "base": round(base_score, 4),
            "ret1": round(ret_component, 4),
            "range": round(range_component, 4),
            "volume": round(vol_component, 4),
            "entry": round(entry_component, 4),
        }
        out["signals"] = sig

    plan = out.get("plan")
    if isinstance(plan, dict):
        plan = dict(plan)
        plan["current_close"] = round(c, 4)
        if entry_status is not None:
            plan["entry_status"] = entry_status
        if entry_gap_pct is not None:
            plan["entry_gap_pct"] = round(entry_gap_pct, 2)
        out["plan"] = plan

    return out
# FAZ593_SCORE_ENRICHMENT_END

# FAZ594_LIVE_BRIDGE_OVERLAY_START
def _overlay_live_bridge_context(result: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result

    try:
        from bist_core.vendors.ideal_bridge_runtime import get_live_bridge_row
        row = get_live_bridge_row(symbol)
    except Exception:
        row = None

    if not row:
        return result

    out = dict(result)

    plan_obj = out.get("plan")
    plan = dict(plan_obj) if isinstance(plan_obj, dict) else {}

    signals_obj = out.get("signals")
    signals = dict(signals_obj) if isinstance(signals_obj, dict) else {}

    live_close = _coerce_float(row.get("current_close"))
    live_source = row.get("current_close_source")
    live_vs_g = _coerce_float(row.get("delta_current_vs_g_close_pct"))

    if live_close is not None:
        plan["current_close"] = round(live_close, 4)
        plan["live_current_close"] = round(live_close, 4)
    if live_source:
        plan["live_current_close_source"] = str(live_source)
    if live_vs_g is not None:
        plan["live_vs_g_close_pct"] = round(live_vs_g, 4)

    entry = _coerce_float(plan.get("entry"))
    if live_close is not None and entry is not None and entry > 0:
        live_gap = (live_close / entry) - 1.0
        plan["entry_gap_pct"] = round(live_gap * 100.0, 2)
        if live_close > entry * 1.01:
            plan["entry_status"] = "extended_above_entry"
        elif live_close < entry * 0.99:
            plan["entry_status"] = "below_entry_trigger"
        else:
            plan["entry_status"] = "near_entry"

    out["plan"] = plan

    if live_close is not None:
        signals["live_current_close"] = round(live_close, 4)
    if live_source:
        signals["live_current_close_source"] = str(live_source)
    if live_vs_g is not None:
        signals["live_vs_g_close_pct"] = round(live_vs_g, 4)

    if "entry_gap_pct" in plan:
        signals["entry_gap_pct"] = plan["entry_gap_pct"]

    out["signals"] = signals
    return out
# FAZ594_LIVE_BRIDGE_OVERLAY_END

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

def _safe_date(value):
    if value is None:
        raise ValueError("date is required")

    if hasattr(value, "to_pydatetime"):
        try:
            value = value.to_pydatetime()
        except Exception:
            pass

    if isinstance(value, _dt_datetime):
        return value.date()

    if isinstance(value, _dt_date):
        return value

    if hasattr(value, "date") and not isinstance(value, str):
        try:
            coerced = value.date()
            if isinstance(coerced, _dt_datetime):
                return coerced.date()
            if isinstance(coerced, _dt_date):
                return coerced
        except Exception:
            pass

    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("date is required")

        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y"):
            try:
                return _dt_datetime.strptime(text, fmt).date()
            except ValueError:
                pass

        try:
            return _dt_date.fromisoformat(text[:10])
        except Exception as exc:
            raise ValueError(f"invalid date: {value!r}") from exc

    raise TypeError(f"unsupported date value: {type(value).__name__}")


def _iter_available_snapshot_dates(root: Path | str | None = None) -> list[_dt_date]:
    base_root = Path(root) if root is not None else Path("data")
    snap_root = base_root / "eod" / "snapshots"
    if not snap_root.exists():
        return []

    out: list[_dt_date] = []
    for child in snap_root.iterdir():
        if not child.is_dir():
            continue
        try:
            out.append(_dt_date.fromisoformat(child.name))
        except Exception:
            continue
    return sorted(set(out))


def _resolve_effective_snapshot_date(value, root: Path | str | None = None):
    wanted = _safe_date(value)
    available = _iter_available_snapshot_dates(root=root)
    if not available:
        return wanted

    eligible = [x for x in available if x <= wanted]
    if eligible:
        return eligible[-1]
    return available[-1]

def build_advice_for_symbol(
    symbol: str,
    date: Date | str,
    root: Optional[Path | str] = None,
) -> Advice:
    date = _resolve_effective_snapshot_date(date, root=root)
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

        result = _augment_engine_result_with_bar_context(result, bars_for_symbol)
        result = _overlay_live_bridge_context(result, symbol)
        decision_raw = str(result.get("decision_raw", decision_raw) or "PASS").upper()
        score = float(result.get("score", score))
        signals = result.get("signals", signals)
        plan = result.get("plan", plan)

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
    def _num(v):
        try:
            if v is None or v == "":
                return None
            return float(v)
        except Exception:
            return None

    sig = dict(signals) if isinstance(signals, dict) else {}
    plan_obj = dict(plan) if isinstance(plan, dict) else {}

    decision_sentence = f"{symbol} için karar {decision_raw}; skor {score:.2f}."

    summaries = _summarize_signals(signals)
    if summaries:
        driver_sentence = "Ana sinyaller: " + ", ".join(summaries[:4]) + "."
    else:
        driver_sentence = "Ana sinyaller sınırlı; karar mevcut fiyat ve temel kural setine dayanıyor."

    comps = sig.get("score_components")
    comps = comps if isinstance(comps, dict) else {}
    comp_bits = []
    for key, label in (
        ("base", "baz"),
        ("ret1", "ret1"),
        ("range", "range"),
        ("volume", "hacim"),
        ("entry", "giriş"),
    ):
        val = _num(comps.get(key))
        if val is not None:
            comp_bits.append(f"{label} {val:+.2f}")
    score_components_sentence = ""
    if comp_bits:
        score_components_sentence = "Skor bileşenleri: " + ", ".join(comp_bits) + "."

    entry = _num(plan_obj.get("entry"))
    stop = _num(plan_obj.get("stop"))
    t1 = _num(plan_obj.get("t1"))
    current_close = _num(plan_obj.get("current_close"))
    live_source = plan_obj.get("live_current_close_source")
    live_vs_g_close_pct = _num(plan_obj.get("live_vs_g_close_pct"))
    entry_status = plan_obj.get("entry_status")

    entry_gap_pct = _num(sig.get("entry_gap_pct"))
    if entry_gap_pct is None:
        entry_gap_pct = _num(plan_obj.get("entry_gap_pct"))

    plan_sentence = ""
    if entry is not None or stop is not None or t1 is not None:
        plan_sentence = (
            f"İşlem planı: entry {entry if entry is not None else '-'}, "
            f"stop {stop if stop is not None else '-'}, "
            f"t1 {t1 if t1 is not None else '-'}."
        )

    status_map = {
        "extended_above_entry": "entry seviyesinin üzerinde; plan kovalanmamalı, geri çekilme veya yeniden teyit beklenmeli",
        "below_entry_trigger": "entry seviyesinin altında; tetik henüz oluşmamış olabilir",
        "near_entry": "entry seviyesine yakın",
    }

    live_bits = []
    if current_close is not None:
        if live_source:
            live_bits.append(f"Canlı fiyat ({live_source}) {current_close}")
        else:
            live_bits.append(f"Mevcut fiyat {current_close}")
    if entry_status in status_map:
        live_bits.append(status_map[entry_status])
    if entry_gap_pct is not None:
        live_bits.append(f"entry gap {entry_gap_pct:+.2f}%")
    if live_vs_g_close_pct is not None:
        live_bits.append(f"Canlı/EOD farkı {live_vs_g_close_pct:+.2f}%")

    live_sentence = ""
    if live_bits:
        live_sentence = "Canlı bağlam: " + "; ".join(live_bits) + "."

    coverage_note = ""
    if decision_raw == "PASS" and score == 0.0 and not has_ohlcv:
        coverage_note = (
            "Kapsam notu: sadece close verisi mevcut; hacim/turnover eksik olduğu için "
            "hacim katkısı devre dışı."
        )

    reconsider_sentence = (
        "Senaryo iptal / yeniden değerlendirme: fiyat bandı dışına taşma, ters KAP/haber akışı "
        "veya güçlü ters hacim kırılması."
    )

    first_paragraph = " ".join(
        part for part in [
            decision_sentence,
            driver_sentence,
            score_components_sentence,
        ] if part
    ).strip()

    second_paragraph = " ".join(
        part for part in [
            plan_sentence,
            live_sentence,
            coverage_note,
            reconsider_sentence,
        ] if part
    ).strip()

    events_paragraph = _render_events_section(events, events_errors)

    return "\n\n".join(
        part for part in [first_paragraph, second_paragraph, events_paragraph] if part
    ).strip()


def _insufficient_history_advice(
    symbol: str,
    day: Date | str,
    bars_count: int,
    lookback_required: int,
) -> Advice:
    """Deterministic InsufficientHistory gate: return Advice (no exception). Fail-closed."""
    day_value = _safe_date(day)
    day_str = day_value.isoformat()
    try:
        events, events_errors = _load_events(symbol, day_str)
        events_paragraph = _render_events_section(events, events_errors)
    except Exception:
        events_paragraph = "Olaylar (KAP/diğer):\nKAP/olay verisi yok veya erişilemedi."
    text = (
        f"Güvenli mod: InsufficientHistory (NoBars).\n"
        f"Yetersiz bar sayısı (mevcut: {bars_count}, gerekli: {lookback_required}).\n"
        "Daha fazla veri bekleyin."
    )
    text = f"{text}\n\n{events_paragraph}"
    return Advice(
        symbol=symbol,
        date=day_value,
        decision_raw="PASS",
        score=0.0,
        signals=[],
        plan=None,
        text=text,
        reason="InsufficientHistory",
        next_action="Wait for more data",
        bars_count=bars_count,
        lookback_required=lookback_required,
        gates={"history_gate": {"outcome": "FAIL", "reason": "InsufficientHistory"}},
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
        ret1_pct = signals.get("ret1_pct")
        range_pos = signals.get("range_pos")
        vol_ratio = signals.get("vol_ratio")
        live_source = signals.get("live_current_close_source")
        live_vs_g_close_pct = signals.get("live_vs_g_close_pct")
        if mom is not None:
            summaries.append(_format_momentum(mom))
        if news is not None:
            summaries.append(_format_news(news))
        if vol is not None:
            summaries.append(_format_volume(vol))
        if ret1_pct is not None:
            summaries.append(f"Günlük değişim {float(ret1_pct):+.2f}%")
        if range_pos is not None:
            summaries.append(f"20g bant konumu {float(range_pos):.2f}")
        if vol_ratio is not None:
            summaries.append(f"Hacim oranı {float(vol_ratio):.2f}x")
        if live_source is not None:
            summaries.append(f"Canlı kaynak {live_source}")
        if live_vs_g_close_pct is not None:
            summaries.append(f"Canlı/EOD farkı {float(live_vs_g_close_pct):+.2f}%")
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


def _append_live_entry_commentary_if_possible(
    text: str,
    *,
    entry_price=None,
    live_payload=None,
):
    try:
        if entry_price is None or live_payload is None:
            return text
        from bist_core.services.live_entry_text import append_live_entry_text
        return append_live_entry_text(text, entry_price, live_payload)
    except Exception:
        return text


def build_live_entry_augmented_text(
    base_text: str,
    *,
    entry_price=None,
    live_payload=None,
):
    return _append_live_entry_commentary_if_possible(
        base_text,
        entry_price=entry_price,
        live_payload=live_payload,
    )


def build_chat_response_for_text(
    text: str | None,
    day,
    *,
    known_symbols=None,
    scan_universe=None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
    **advisor_kwargs,
):
    from bist_core.services.advisor_chat_service import build_advisor_chat_service_result

    return build_advisor_chat_service_result(
        text=text,
        day=day,
        known_symbols=known_symbols,
        scan_universe=scan_universe,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
        advisor_kwargs=advisor_kwargs or None,
    )


def render_chat_response_text(
    text: str | None,
    day,
    *,
    known_symbols=None,
    scan_universe=None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
    **advisor_kwargs,
) -> str:
    from bist_core.services.advisor_chat_service import render_advisor_chat_text

    return render_advisor_chat_text(
        text=text,
        day=day,
        known_symbols=known_symbols,
        scan_universe=scan_universe,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
        advisor_kwargs=advisor_kwargs or None,
    )


def render_chat_response_markdown(
    text: str | None,
    day,
    *,
    known_symbols=None,
    scan_universe=None,
    market_overview_text: str | None = None,
    default_scan_n: int = 5,
    **advisor_kwargs,
) -> str:
    from bist_core.services.advisor_chat_service import render_advisor_chat_markdown

    return render_advisor_chat_markdown(
        text=text,
        day=day,
        known_symbols=known_symbols,
        scan_universe=scan_universe,
        market_overview_text=market_overview_text,
        default_scan_n=default_scan_n,
        advisor_kwargs=advisor_kwargs or None,
    )
