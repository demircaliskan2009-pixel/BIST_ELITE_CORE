from typing import Any, Dict, List

from ..models import EODBar, PriceBand


def round_to_tick(p: float, tick: float) -> float:
    return round(round(p / tick) * tick, 2)


def within_band(pc: float, p: float, up: float, dn: float) -> bool:
    return pc * (1 - dn / 100) <= p <= pc * (1 + up / 100)


def _compute_momentum_signal(arr: List[EODBar], mom_fast: int, mom_slow: int) -> int:
    """
    Momentum sinyali hesaplar.

    Args:
        arr: Sembole ait bar listesi (tarih sıralı, son gün en sonda)
        mom_fast: Hızlı MA gün sayısı
        mom_slow: Yavaş MA gün sayısı

    Returns:
        1: fast_ma > slow_ma (pozitif momentum)
        -1: fast_ma < slow_ma (negatif momentum)
        0: Yeterli veri yok veya eşit
    """
    if len(arr) < mom_slow:
        return 0

    fast_bars = arr[-mom_fast:]
    slow_bars = arr[-mom_slow:]

    fast_ma = sum(b.close for b in fast_bars) / len(fast_bars)
    slow_ma = sum(b.close for b in slow_bars) / len(slow_bars)

    if fast_ma > slow_ma:
        return 1
    elif fast_ma < slow_ma:
        return -1
    return 0


def _compute_news_signal(events_for_symbol: List[Dict[str, Any]], strat_cfg: Dict[str, Any]) -> int:
    """
    KAP haber sinyali hesaplar.

    Args:
        events_for_symbol: Sembole ait KAP event listesi
        strat_cfg: Strateji konfigürasyonu (kap_positive_keywords, kap_negative_keywords)

    Returns:
        1: Pozitif haber bulundu
        -1: Negatif haber bulundu (pozitiften öncelikli)
        0: Haber yok veya nötr
    """
    if not events_for_symbol:
        return 0

    positive_keywords = [kw.lower() for kw in strat_cfg.get("kap_positive_keywords", [])]
    negative_keywords = [kw.lower() for kw in strat_cfg.get("kap_negative_keywords", [])]

    for event in events_for_symbol:
        # Event dict'inden metin al (headline, title, body, raw içinden)
        text = ""
        if isinstance(event, dict):
            text = (
                event.get("headline", "")
                + " "
                + event.get("title", "")
                + " "
                + event.get("body", "")
                + " "
                + str(event.get("raw", {}).get("headline", ""))
                + " "
                + str(event.get("raw", {}).get("title", ""))
            )
        text_lower = text.lower()

        # Önce negatif kontrol et (öncelikli)
        for neg_kw in negative_keywords:
            if neg_kw in text_lower:
                return -1

        # Sonra pozitif kontrol et
        for pos_kw in positive_keywords:
            if pos_kw in text_lower:
                return 1

    return 0


def _compute_volume_signal(arr: List[EODBar], vol_lookback: int = 20, threshold: float = 1.5) -> int:
    """
    Hacim sinyali hesaplar.

    Args:
        arr: Sembole ait bar listesi (tarih sıralı, son gün en sonda)
        vol_lookback: Ortalama hacim hesaplama için geriye bakış gün sayısı
        threshold: Son gün hacminin ortalamaya oranı eşiği (default 1.5)

    Returns:
        1: Son gün hacmi >= threshold * ortalama hacim
        0: Yeterli veri yok veya eşik altında
    """
    if len(arr) < vol_lookback:
        return 0

    last_vol = arr[-1].volume
    if last_vol <= 0:
        return 0

    avg_vol = sum(b.volume for b in arr[-vol_lookback:]) / vol_lookback

    if last_vol >= threshold * avg_vol:
        return 1
    return 0


def decide(symbols: List[str], bars: List[EODBar], bands: List[PriceBand], kap_events, cfg, gates_cfg, strat_cfg):
    """
    Her sembol için karar verir (BUY/WATCH/PASS).

    Args:
        symbols: Değerlendirilecek sembol listesi
        bars: Tüm semboller için EOD bar listesi
        bands: Fiyat bandları
        kap_events: KAP event'leri (dict: {symbol: [event_dict, ...]})
        cfg: Core config
        gates_cfg: Gates config
        strat_cfg: Strateji config (mom_weight, kap_weight, vol_weight, score_buy, score_watch, vb.)

    Returns:
        Her sembol için dict listesi: [{'symbol': ..., 'decision': ..., 'decision_raw': ..., 'score': ..., 'signals': ..., ...}, ...]
    """
    out, by = [], {}
    for b in bars:
        by.setdefault(b.symbol, []).append(b)

    # kap_events dict formatına normalize et
    kap_dict = {}
    if isinstance(kap_events, dict):
        kap_dict = kap_events
    elif isinstance(kap_events, list):
        # List ise sembole göre grupla
        for event in kap_events:
            if isinstance(event, dict):
                sym = event.get("symbol")
                if sym:
                    if sym not in kap_dict:
                        kap_dict[sym] = []
                    kap_dict[sym].append(event)

    # Config'ten ağırlıkları ve eşikleri al
    mom_weight = strat_cfg.get("mom_weight", 1.0)
    kap_weight = strat_cfg.get("kap_weight", 1.0)
    vol_weight = strat_cfg.get("vol_weight", 0.5)
    score_buy = strat_cfg.get("score_buy", 1.5)
    score_watch = strat_cfg.get("score_watch", 0.5)
    mom_fast = strat_cfg.get("mom_fast", 5)
    mom_slow = strat_cfg.get("mom_slow", 20)
    vol_lookback = strat_cfg.get("vol_window", 20)

    for s in symbols:
        arr = sorted(by.get(s, []), key=lambda x: x.date)
        if not arr:
            continue

        last = arr[-1]

        # Band kontrolü
        band = next((b for b in bands if b.price_min <= last.close <= b.price_max), None)
        if not band:
            out.append(
                {
                    "symbol": s,
                    "date": last.date.isoformat(),
                    "last_close": last.close,
                    "decision": "PASS",
                    "decision_raw": "PASS",
                    "reason": "no_band",
                    "plan": None,
                }
            )
            continue

        # Entry/stop/t1 hesapları
        entry = round_to_tick(last.close * 1.01, band.tick)
        stop = round_to_tick(last.close * 0.98, band.tick)
        t1 = round_to_tick(last.close * 1.03, band.tick)

        def ok(px):
            return within_band(last.close, px, band.up_limit_pct, band.down_limit_pct)

        if not (ok(entry) and ok(stop) and ok(t1)):
            out.append(
                {
                    "symbol": s,
                    "date": last.date.isoformat(),
                    "last_close": last.close,
                    "decision": "PASS",
                    "decision_raw": "PASS",
                    "reason": "band_violation",
                    "plan": None,
                }
            )
            continue

        # Band geçtiyse skorlama yap
        # Momentum sinyali
        mom_signal = _compute_momentum_signal(arr, mom_fast, mom_slow)

        # Haber sinyali
        events_for_symbol = kap_dict.get(s, [])
        news_signal = _compute_news_signal(events_for_symbol, strat_cfg)

        # Hacim sinyali
        vol_signal = _compute_volume_signal(arr, vol_lookback=vol_lookback)

        # Toplam skor
        score = mom_weight * mom_signal + kap_weight * news_signal + vol_weight * vol_signal

        # Karar belirleme
        if score >= score_buy:
            decision_raw = "BUY"
        elif score >= score_watch:
            decision_raw = "WATCH"
        else:
            decision_raw = "PASS"

        # Geriye dönük uyumluluk: 'decision' alanı eski testler için
        # BUY/WATCH -> WATCH, PASS -> PASS
        if decision_raw in ("BUY", "WATCH"):
            decision = "WATCH"
        else:
            decision = "PASS"

        # Çıktı kaydı
        result = {
            "symbol": s,
            "date": last.date.isoformat(),
            "last_close": last.close,
            "decision": decision,
            "decision_raw": decision_raw,
            "score": round(score, 3),
            "signals": {"mom": mom_signal, "news": news_signal, "vol": vol_signal},
            "plan": None if decision_raw == "PASS" else {"entry": entry, "stop": stop, "t1": t1},
        }

        out.append(result)

    return out
