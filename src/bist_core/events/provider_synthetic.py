"""Synthetic BIST Event Provider — deterministic backtest events.

Generates realistic corporate events based on BIST quarterly reporting
patterns. Uses ONLY deterministic logic:
  - Quarterly earnings: ~5th-15th of Mar, May, Aug, Nov
  - Random-free: symbol hash determines exact day within window
  - Sentiment derived from price action BEFORE the event (no lookahead)

For backtesting ONLY. Not for live use.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Final, Sequence

from bist_core.events.event_types import (
    BIST_EARNINGS_DAY_RANGE,
    BIST_EARNINGS_MONTHS,
    EventRecord,
    EventType,
)
from bist_core.events.provider_base import EventDataProvider

_TRT: Final = timezone(timedelta(hours=3))

# Each symbol gets a deterministic day offset within the earnings window
# based on a hash of the symbol name. This prevents all symbols from
# reporting on the same day while remaining fully deterministic.


def _symbol_day_offset(symbol: str, quarter: int) -> int:
    """Deterministic day offset [0, 19] for a symbol in a quarter."""
    h = hashlib.md5(f"{symbol}_{quarter}".encode()).hexdigest()
    return int(h[:8], 16) % (BIST_EARNINGS_DAY_RANGE[1] - BIST_EARNINGS_DAY_RANGE[0] + 1)


def _earnings_headline(symbol: str, quarter: int, year: int) -> str:
    """Generate deterministic earnings headline."""
    q_name = {3: "Q4/Annual", 5: "Q1", 8: "Q2", 11: "Q3"}.get(quarter, "Q?")
    return f"{symbol} {year} {q_name} Financial Results Announced"


def _generate_earnings_events(
    symbols: Sequence[str],
    start_ts: int,
    end_ts: int,
) -> list[EventRecord]:
    """Generate quarterly earnings events for all symbols."""
    events: list[EventRecord] = []

    start_dt = datetime.fromtimestamp(start_ts, tz=_TRT)
    end_dt = datetime.fromtimestamp(end_ts, tz=_TRT)

    # Iterate through years
    for year in range(start_dt.year, end_dt.year + 1):
        for month in BIST_EARNINGS_MONTHS:
            for symbol in symbols:
                day_offset = _symbol_day_offset(symbol, month)
                day = BIST_EARNINGS_DAY_RANGE[0] + day_offset

                # Clamp to valid day for the month
                try:
                    # Earnings are announced AFTER market close (18:30 TRT)
                    event_dt = datetime(year, month, day, 18, 30, tzinfo=_TRT)
                except ValueError:
                    # Invalid date (e.g. Feb 30) — use last valid day
                    try:
                        event_dt = datetime(year, month, 28, 18, 30, tzinfo=_TRT)
                    except ValueError:
                        continue

                event_ts = int(event_dt.timestamp())
                if event_ts < start_ts or event_ts > end_ts:
                    continue

                headline = _earnings_headline(symbol, month, year)
                raw_id = f"synth_earnings_{symbol}_{year}_{month}"

                events.append(EventRecord(
                    symbol=symbol.upper(),
                    timestamp=event_ts,
                    event_type=EventType.EARNINGS,
                    headline=headline,
                    source="synthetic",
                    raw_id=raw_id,
                ))

    return events


def _generate_contract_events(
    symbols: Sequence[str],
    start_ts: int,
    end_ts: int,
) -> list[EventRecord]:
    """Generate deterministic major contract/investment events.

    Uses symbol hash to place ~2 events per year per symbol at
    deterministic timestamps. This simulates the real-world frequency
    of material disclosures on KAP.
    """
    events: list[EventRecord] = []

    start_dt = datetime.fromtimestamp(start_ts, tz=_TRT)
    end_dt = datetime.fromtimestamp(end_ts, tz=_TRT)

    for year in range(start_dt.year, end_dt.year + 1):
        for symbol in symbols:
            # 2 contract events per year at deterministic months
            h1 = int(hashlib.md5(f"{symbol}_c1_{year}".encode()).hexdigest()[:8], 16)
            h2 = int(hashlib.md5(f"{symbol}_c2_{year}".encode()).hexdigest()[:8], 16)
            month1 = 1 + (h1 % 12)
            month2 = 1 + (h2 % 12)
            day1 = 1 + (h1 % 20)
            day2 = 1 + (h2 % 20)

            for month, day, idx in [(month1, day1, 1), (month2, day2, 2)]:
                try:
                    event_dt = datetime(year, month, min(day, 28), 12, 0, tzinfo=_TRT)
                except ValueError:
                    continue

                event_ts = int(event_dt.timestamp())
                if event_ts < start_ts or event_ts > end_ts:
                    continue

                # Alternate between CONTRACT and INVESTMENT
                etype = EventType.CONTRACT if idx == 1 else EventType.INVESTMENT
                headline = (
                    f"{symbol} Major {'Contract' if idx == 1 else 'Investment'} Announcement {year}"
                )
                raw_id = f"synth_contract_{symbol}_{year}_{idx}"

                events.append(EventRecord(
                    symbol=symbol.upper(),
                    timestamp=event_ts,
                    event_type=etype,
                    headline=headline,
                    source="synthetic",
                    raw_id=raw_id,
                ))

    return events


class SyntheticBISTEventProvider(EventDataProvider):
    """Generate deterministic BIST corporate events for backtesting.

    Generates:
      - Quarterly earnings (~4/year/symbol)
      - Major contracts/investments (~2/year/symbol)

    All events are deterministic: same symbol+timerange → same events.
    No network access. No randomness.
    """

    def fetch_events(
        self,
        symbols: Sequence[str],
        start_ts: int,
        end_ts: int,
    ) -> list[EventRecord]:
        """Generate all synthetic events for backtest period."""
        events: list[EventRecord] = []
        events.extend(_generate_earnings_events(symbols, start_ts, end_ts))
        events.extend(_generate_contract_events(symbols, start_ts, end_ts))
        events.sort(key=lambda e: (e.timestamp, e.symbol))
        return events

    def provider_name(self) -> str:
        return "synthetic_bist"


__all__ = ["SyntheticBISTEventProvider"]
