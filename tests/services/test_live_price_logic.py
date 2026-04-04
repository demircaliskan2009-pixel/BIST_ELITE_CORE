from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from bist_core.services.live_price_logic import (
    classify_live_entry_status,
    compute_entry_gap_pct,
    pick_live_reference_price,
)
from bist_core.vendors.ideal_01_tail import build_ideal_01_bridge_row


def _load_vendor_test_module():
    root = Path(__file__).resolve().parents[2]
    test_mod_path = root / "tests" / "vendors" / "test_ideal_01_tail.py"
    spec = importlib.util.spec_from_file_location("ideal01_vendor_test_mod_for_live_price_logic", test_mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ideal01_vendor_test_mod_for_live_price_logic"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_pick_live_reference_price_prefers_current_price() -> None:
    payload = {
        "last_price": 72.10,
        "price": 72.20,
        "current_price": 72.6500015258789,
        "close": 72.30,
    }
    assert pick_live_reference_price(payload) == 72.65


def test_compute_entry_gap_pct_positive_gap() -> None:
    payload = {"current_price": 72.65}
    assert compute_entry_gap_pct(71.0, payload) == 2.3239


def test_classify_live_entry_status_marks_extended_above_entry() -> None:
    payload = {"current_price": 72.65}
    got = classify_live_entry_status(71.0, payload)
    assert got["status"] == "extended_above_entry"
    assert got["entry_missed"] is True
    assert got["should_wait_pullback"] is True
    assert got["summary_code"] == "entry_missed_wait_pullback"


def test_classify_live_entry_status_marks_near_entry() -> None:
    payload = {"current_price": 72.65}
    got = classify_live_entry_status(72.40, payload)
    assert got["status"] == "near_entry"
    assert got["entry_missed"] is False
    assert got["should_wait_pullback"] is False


def test_classify_live_entry_status_marks_discount() -> None:
    payload = {"current_price": 72.65}
    got = classify_live_entry_status(73.50, payload)
    assert got["status"] == "below_entry_discount"
    assert got["is_discount_to_entry"] is True
    assert got["entry_missed"] is False


def test_classify_live_entry_status_works_with_vendor_bridge_row(tmp_path: Path) -> None:
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

    row = build_ideal_01_bridge_row(p)
    got = classify_live_entry_status(71.0, row)

    assert row["current_price"] == 72.65
    assert got["live_price"] == 72.65
    assert got["status"] == "extended_above_entry"
    assert got["entry_missed"] is True
    assert got["should_wait_pullback"] is True
