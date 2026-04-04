"""Multi-timeframe iDeal reads — requires ``BIST_IDEAL_DATA_PATH`` with files per suffix."""

from __future__ import annotations

import os
import tempfile

import pytest

from bist_core.live.data_feed import IdealDataFeed


def test_file_path_includes_timeframe_suffix() -> None:
    with tempfile.TemporaryDirectory() as d:
        feed = IdealDataFeed(d)
        p = feed._file_path("ASELS", "05")
        assert "IMKBH'ASELS.05" in p.replace("/", "\\")
        assert feed._file_path("x", "G").endswith("IMKBH'X.G")


@pytest.mark.skipif(
    not (os.environ.get("BIST_IDEAL_DATA_PATH") or "").strip(),
    reason="BIST_IDEAL_DATA_PATH not set — point to IMKBH folder containing IMKBH'<SYM>.<tf> files",
)
def test_timeframes_parse() -> None:
    f = IdealDataFeed()

    for tf in ["01", "05", "60", "G"]:
        bars = f.read_new("ASELS", timeframe=tf)

        assert isinstance(bars, list)

        if bars:
            closes = [b.close for b in bars]

            assert min(closes) > 0
            assert max(closes) < 10000
            assert len({round(float(x), 2) for x in closes}) > 5
