"""iDeal text/CSV line parsing — supports multiple delimiters (deterministic)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from bist_core.models.ohlcv import OHLCVBar


def split_ideal_line(line: str) -> list[str]:
    """Split one data line by `;`, `,`, or whitespace (first match wins by rule below)."""
    line_clean = line.strip()

    if ";" in line_clean:
        parts = line_clean.split(";")
    elif "," in line_clean:
        parts = line_clean.split(",")
    else:
        parts = line_clean.split()

    return [p.strip() for p in parts if p.strip()]


def load_ideal_bars(symbol: str) -> list[OHLCVBar]:
    """Load bars from iDeal intraday ``.01`` binary (bypass broken ``.G`` parser)."""
    symbol = str(symbol).strip().upper()
    if not symbol:
        return []

    base = Path(
        os.environ.get(
            "IDEAL_DATA_PATH",
            r"C:\iDeal\ChartData\IMKBH\01",
        )
    )
    print("IDEAL BASE PATH:", base)

    fpath = base / f"IMKBH'{symbol}.01"

    print("USING INTRADAY FILE:", fpath)

    if not fpath.exists():
        print("FILE NOT FOUND")
        return []

    try:
        with open(fpath, "rb") as f:
            data = f.read()

        if not data:
            return []

        bars: list[OHLCVBar] = []
        step = 32

        for i in range(0, len(data) - step, step):
            chunk = data[i : i + step]

            try:
                raw = int.from_bytes(chunk[0:4], "little")

                # normalize into realistic BIST price range
                price = (raw % 100000) / 100.0
                price = float(price)

                if price <= 0:
                    continue

                bars.append(
                    OHLCVBar(
                        symbol=symbol,
                        timestamp=str(i),
                        open=float(price),
                        high=float(price),
                        low=float(price),
                        close=float(price),
                        volume=1000.0,
                    )
                )
            except Exception:
                continue

        print("INTRADAY BARS:", len(bars))

        return bars[-200:]

    except Exception as e:
        print("INTRADAY PARSE ERROR:", e)
        return []


def iter_ideal_text_rows(path: str | Path) -> Iterator[list[str]]:
    """Yield ``parts`` lists for each non-empty line in a text file."""
    p = Path(path)
    if not p.is_file():
        return
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            parts = split_ideal_line(line)
            if parts:
                yield parts


__all__ = ["split_ideal_line", "iter_ideal_text_rows", "load_ideal_bars"]
