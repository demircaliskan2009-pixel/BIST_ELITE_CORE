from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path
import json
from typing import Any, Dict, List, Optional

from bist_core import config
from bist_core.services.marketdata import MarketData
from bist_core.services.eod_adapters import build_bars_for_day, build_bands_for_day
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
        bars = build_bars_for_day(day_str, md)
        cfg = config.CORE
        bands = build_bands_for_day(day_str, md, cfg)

        kap_events = _load_kap_events(md, day_str)

        gates_cfg = _load_json_config("config/gates.json")
        strat_cfg = _load_json_config("config/strategy.json")

        if not bars:
            return _safe_advice(symbol, day, "NoBars")

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
            return _safe_advice(symbol, day, "NoDecision")

        result = decisions[0]

        decision_raw = result.get("decision_raw", result.get("decision", "PASS"))
        score = float(result.get("score", 0.0))
        signals = result.get("signals", [])
        plan = result.get("plan")

        text = _render_advice_text(symbol, day, decision_raw, score, signals, plan)

        return Advice(
            symbol=symbol,
            date=day,
            decision_raw=decision_raw,
            score=score,
            signals=signals,
            plan=plan,
            text=text,
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
) -> str:
    decision_sentence = f"{symbol} için karar {decision_raw}; skor {score:.2f}."

    summaries = _summarize_signals(signals)
    if summaries:
        signal_sentence = "Sinyal özeti: " + ", ".join(summaries[:4]) + "."
    else:
        signal_sentence = (
            "Sinyal seti boş ya da sınırlı, karar mevcut fiyat verisine dayalı."
        )

    plan_sentence = ""
    if isinstance(plan, dict):
        entry = plan.get("entry")
        stop = plan.get("stop")
        t1 = plan.get("t1")
        if entry is not None or stop is not None or t1 is not None:
            plan_sentence = (
                f"Plan: entry {entry}, stop {stop}, t1 {t1}."
            )

    coverage_note = ""
    if decision_raw == "PASS" and score == 0.0 and not summaries:
        coverage_note = (
            "Not: Hacim/turnover verisi yoksa hacim sinyali devre dışı kalır."
        )

    reconsider_sentence = (
        "Fiyat bandı dışına çıkma, ters haber akışı veya güçlü hacim kırılması olursa "
        "yeniden değerlendir."
    )

    first_paragraph = f"{decision_sentence} {signal_sentence}"
    second_paragraph = " ".join(
        part for part in [plan_sentence, coverage_note, reconsider_sentence] if part
    )

    return f"{first_paragraph}\n\n{second_paragraph}".strip()


def _safe_date(value: Date | str) -> Date:
    if isinstance(value, Date):
        return value
    try:
        return Date.fromisoformat(value)
    except Exception:
        return Date.today()


def _safe_advice(symbol: str, day: Date | str, err: str) -> Advice:
    day_value = _safe_date(day)
    return Advice(
        symbol=symbol,
        date=day_value,
        decision_raw="PASS",
        score=0.0,
        signals=[],
        plan=None,
        text=(
            f"Güvenli mod: {err}. "
            "Veri veya karar üretilemedi; snapshot ve konfigürasyonu kontrol edin."
        ),
    )


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
