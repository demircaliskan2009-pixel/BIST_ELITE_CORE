from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from bist_core.vendors.ideal_01_tail import build_ideal_01_bridge_row


def _load_vendor_test_module():
    root = Path(__file__).resolve().parents[2]
    test_mod_path = root / "tests" / "vendors" / "test_ideal_01_tail.py"
    spec = importlib.util.spec_from_file_location("ideal01_vendor_test_mod", test_mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ideal01_vendor_test_mod"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_live_bridge_payload_contract(tmp_path: Path) -> None:
    mod = _load_vendor_test_module()

    p = tmp_path / "IMKBH'AKBNK.01"
    p.write_bytes(
        b"".join(
            [
                mod._pack_bar(20018518, 72.55, 72.60, 72.50, 72.55, 624007, 45275084),
                mod._pack_bar(20018519, 72.55, 72.65, 72.55, 72.6500015258789, 732956, 53204712),
            ]
        )
    )

    got = build_ideal_01_bridge_row(p)

    assert got["symbol"] == "AKBNK"
    assert got["source_file"] == "IMKBH'AKBNK.01"
    assert got["source_period"] == "01"

    assert got["current_open"] == got["last_open"] == got["open"] == 72.55
    assert got["current_high"] == got["last_high"] == got["high"] == 72.65
    assert got["current_low"] == got["last_low"] == got["low"] == 72.55
    assert got["current_close"] == got["current_price"] == got["last_price"] == got["last_close"] == got["close"] == 72.65

    assert got["current_volume"] == got["volume"] == 732956
    assert got["current_turnover"] == got["turnover"] == 53204712

    assert got["raw_time_code"] == got["last_raw_time_code"] == 20018519
    assert got["header_bytes"] == 0
    assert got["record_bytes"] == 32
