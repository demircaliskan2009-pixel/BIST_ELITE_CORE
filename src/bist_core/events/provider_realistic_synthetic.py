"""Realistic Synthetic Event Provider — stress-test the event engine.

Generates ~70 corporate events per year per symbol with:
  - Realistic Turkish/English headlines containing sentiment keywords
  - Diverse event types (earnings, contracts, investments, management, etc.)
  - Sentiment distribution: ~45% positive, ~30% negative, ~15% neutral, ~10% mixed
  - Aligned with BIST trading hours (earnings after close, others intraday)
  - Fully deterministic via MD5 hash (same inputs → same events every run)

For backtest stress-testing ONLY. Not for live use.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Final, Sequence

from bist_core.events.event_types import EventRecord, EventType
from bist_core.events.provider_base import EventDataProvider

_TRT: Final = timezone(timedelta(hours=3))
_EVENTS_PER_YEAR: Final[int] = 70

# ---------------------------------------------------------------------------
# Headline pools — rich with classifier-recognized sentiment keywords
# ---------------------------------------------------------------------------

_POSITIVE_HEADLINES: Final[list[tuple[str, EventType]]] = [
    # Turkish — contains keywords: kar, artış, büyüme, rekor, güçlü, olumlu, yeni sözleşme, kapasite artışı, stratejik ortaklık, pay geri alım, temettü artışı, gelir artışı, devralma
    ("{sym} net kar %{pct} arttı — beklentilerin üzerinde büyüme", EventType.EARNINGS),
    ("{sym} büyük ihale kazandı — {val} milyon TL yeni sözleşme", EventType.CONTRACT),
    ("{sym} rekor gelir açıkladı — güçlü büyüme devam ediyor", EventType.EARNINGS),
    ("{sym} yeni yatırım anlaşması imzaladı — kapasite artışı planlanıyor", EventType.INVESTMENT),
    ("{sym} stratejik ortaklık anlaşması — olumlu gelişme", EventType.PARTNERSHIP),
    ("{sym} kapasite artışı yatırımına onay — büyüme sürüyor", EventType.CAPACITY),
    ("{sym} pay geri alım programı başlatıldı — güçlü nakit akışı", EventType.BUYBACK),
    ("{sym} temettü artışı açıkladı — olumlu sinyal", EventType.DIVIDEND),
    ("{sym} yeni sözleşme imzaladı — gelir artışı bekleniyor", EventType.CONTRACT),
    ("{sym} ihracat anlaşması — güçlü talep devam ediyor", EventType.CONTRACT),
    ("{sym} stratejik yatırım kararı — büyüme hedefleniyor", EventType.INVESTMENT),
    ("{sym} kar marjı iyileşti — güçlü operasyonel performans", EventType.EARNINGS),
    ("{sym} önemli ihale kazandı — rekor büyüklükte sözleşme", EventType.CONTRACT),
    ("{sym} gelir artışı %{pct} — beklentileri aştı", EventType.EARNINGS),
    # English — contains keywords: profit, growth, increase, record, strong, positive, new contract, revenue growth, capacity expansion, strategic partnership, buyback, share repurchase, dividend increase, acquisition, upgraded, milestone
    ("{sym} profit increased {pct}% — beat estimates strong growth", EventType.EARNINGS),
    ("{sym} record revenue growth — expansion underway", EventType.EARNINGS),
    ("{sym} major new contract awarded — {val}M TL revenue growth", EventType.CONTRACT),
    ("{sym} strategic partnership signed — positive outlook", EventType.PARTNERSHIP),
    ("{sym} share repurchase program — strong cash position", EventType.BUYBACK),
    ("{sym} capacity expansion approved — new investment milestone", EventType.CAPACITY),
]

_NEGATIVE_HEADLINES: Final[list[tuple[str, EventType]]] = [
    # Turkish — contains keywords: zarar, düşüş, azalış, olumsuz, zayıf, dava, soruşturma, durma, askıya, ceza, istifa, yeniden yapılandırma, değer düşüklüğü, temerrüt, borç
    ("{sym} zarar açıkladı — düşüş devam ediyor", EventType.EARNINGS),
    ("{sym} beklentinin altında bilanço — zayıf performans", EventType.EARNINGS),
    ("{sym} gelir düşüşü %{pct} — olumsuz tablo", EventType.EARNINGS),
    ("{sym} hakkında soruşturma başlatıldı — ceza riski", EventType.REGULATORY),
    ("{sym} borç arttı — olumsuz görünüm", EventType.GENERAL_DISCLOSURE),
    ("{sym} CEO istifa etti — yönetim değişikliği belirsizlik", EventType.MANAGEMENT),
    ("{sym} üretim durma kararı — azalış bekleniyor", EventType.CAPACITY),
    ("{sym} dava açıldı — önemli ceza riski olumsuz", EventType.REGULATORY),
    ("{sym} kar düşüşü — zayıf talep olumsuz", EventType.EARNINGS),
    ("{sym} sözleşme iptali — zarar bekleniyor", EventType.CONTRACT),
    # English — contains keywords: loss, decline, decrease, negative, weak, miss, underperform, lawsuit, investigation, halt, suspension, penalty, fine, downgrade, departure, resignation, restructuring, impairment, writedown, default, debt, liquidity concern
    ("{sym} reported loss — decline continues", EventType.EARNINGS),
    ("{sym} weak revenue — underperformed estimates negative outlook", EventType.EARNINGS),
    ("{sym} investigation launched — penalty risk", EventType.REGULATORY),
    ("{sym} production halt — suspension of operations", EventType.CAPACITY),
    ("{sym} debt increased — negative credit outlook liquidity concern", EventType.GENERAL_DISCLOSURE),
]

_NEUTRAL_HEADLINES: Final[list[tuple[str, EventType]]] = [
    ("{sym} yıllık olağan genel kurul toplandı", EventType.GENERAL_DISCLOSURE),
    ("{sym} mali tablo açıklama takvimi güncellendi", EventType.GENERAL_DISCLOSURE),
    ("{sym} düzenleyici bildirim yayınlandı", EventType.REGULATORY),
    ("{sym} yönetim kurulu toplantı gündemi açıklandı", EventType.MANAGEMENT),
    ("{sym} bağımsız denetim raporu sunuldu", EventType.GENERAL_DISCLOSURE),
    ("{sym} annual general assembly meeting held", EventType.GENERAL_DISCLOSURE),
    ("{sym} regulatory compliance filing submitted", EventType.REGULATORY),
    ("{sym} board of directors meeting scheduled", EventType.MANAGEMENT),
]

_MIXED_HEADLINES: Final[list[tuple[str, EventType]]] = [
    ("{sym} gelir arttı ancak kar marjı düştü — karışık tablo", EventType.EARNINGS),
    ("{sym} yeni sözleşme ama borç artışı kaygısı", EventType.CONTRACT),
    ("{sym} büyüme güçlü ancak maliyet artışı endişesi", EventType.EARNINGS),
    ("{sym} revenue growth but margin decline — mixed", EventType.EARNINGS),
]


def _hash_int(seed: str) -> int:
    """Deterministic hash → unsigned integer."""
    return int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)


def _fill_headline(template: str, sym: str, seed: str) -> str:
    """Fill headline placeholders deterministically."""
    h = _hash_int(seed + "_fill")
    pct = 15 + (h % 120)  # 15-134%
    val = 50 + (h % 450)  # 50-499 million TL
    return template.replace("{sym}", sym).replace("{pct}", str(pct)).replace("{val}", str(val))


class RealisticSyntheticEventProvider(EventDataProvider):
    """Event provider with realistic headlines for engine stress-testing.

    Distribution per year per symbol (~70 events):
      - ~31 positive (45%)
      - ~21 negative (30%)
      - ~11 neutral  (15%)
      - ~7  mixed    (10%)

    All timing and selection is fully deterministic via MD5 hash.
    Same (symbol, year, event_index) → same event every run.
    """

    def provider_name(self) -> str:
        return "realistic_synthetic"

    def fetch_events(
        self,
        symbols: Sequence[str],
        start_ts: int,
        end_ts: int,
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        start_dt = datetime.fromtimestamp(start_ts, tz=_TRT)
        end_dt = datetime.fromtimestamp(end_ts, tz=_TRT)

        for year in range(start_dt.year, end_dt.year + 1):
            for symbol in symbols:
                year_events = self._generate_year(symbol, year, start_ts, end_ts)
                events.extend(year_events)

        return events

    def _generate_year(
        self,
        symbol: str,
        year: int,
        start_ts: int,
        end_ts: int,
    ) -> list[EventRecord]:
        """Generate ~70 events for one symbol for one year."""
        events: list[EventRecord] = []

        for idx in range(_EVENTS_PER_YEAR):
            seed = f"{symbol}_{year}_{idx}"
            h = _hash_int(seed)

            # Sentiment category by hash
            cat_val = h % 100
            if cat_val < 45:
                pool = _POSITIVE_HEADLINES
                cat = "pos"
            elif cat_val < 75:
                pool = _NEGATIVE_HEADLINES
                cat = "neg"
            elif cat_val < 90:
                pool = _NEUTRAL_HEADLINES
                cat = "neu"
            else:
                pool = _MIXED_HEADLINES
                cat = "mix"

            # Pick headline from pool
            headline_idx = _hash_int(seed + "_hl") % len(pool)
            template, event_type = pool[headline_idx]
            headline = _fill_headline(template, symbol, seed)

            # Timing: month + day via hash
            month = 1 + (_hash_int(seed + "_m") % 12)
            day = 1 + (_hash_int(seed + "_d") % 28)

            # Earnings: announced after market close at 18:30 TRT
            # Others: during BIST trading session 10:00-16:59 TRT
            if event_type == EventType.EARNINGS:
                hour, minute = 18, 30
            else:
                hour = 10 + (_hash_int(seed + "_h") % 7)  # 10-16
                minute = _hash_int(seed + "_min") % 60

            try:
                event_dt = datetime(year, month, day, hour, minute, tzinfo=_TRT)
            except ValueError:
                # Invalid date (e.g. Feb 30) → clamp to 28th
                try:
                    event_dt = datetime(year, month, 28, hour, minute, tzinfo=_TRT)
                except ValueError:
                    continue  # pragma: no cover

            event_ts = int(event_dt.timestamp())
            if event_ts < start_ts or event_ts > end_ts:
                continue

            raw_id = f"rsyn_{symbol}_{year}_{idx}_{cat}"
            events.append(EventRecord(
                symbol=symbol.upper(),
                timestamp=event_ts,
                event_type=event_type,
                headline=headline,
                source="realistic_synthetic",
                raw_id=raw_id,
            ))

        return events
