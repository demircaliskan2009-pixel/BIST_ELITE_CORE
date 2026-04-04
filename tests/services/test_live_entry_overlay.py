from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from bist_core.services.live_entry_overlay import (
    augment_result_with_live_entry_context,
    pick_live_payload,
    pick_result_entry_price,
)
from bist_core.vendors.ideal_01_tail import build_ideal_01_bridge_row


def _load_vendor_test_module():
    root = Path(__file__).resolve().parents[2]
    test_mod_path = root / "tests" / "vendors" / "test_ideal_01_tail.py"
    spec = importlib.util.spec_from_file_location("ideal01_vendor_test_mod_for_live_entry_overlay", test_mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ideal01_vendor_test_mod_for_live_entry_overlay"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_pick_result_entry_price_prefers_entry_field() -> None:
    got = pick_result_entry_price({"entry": 71.0, "entry_price": 72.0})
    assert got == 71.0


def test_pick_result_entry_price_uses_entry_price_alias() -> None:
    got = pick_result_entry_price({"entry_price": 72.4})
    assert got == 72.4


def test_pick_live_payload_prefers_explicit_payload() -> None:
    explicit = {"current_price": 72.65}
    got = pick_live_payload({"live_payload": {"current_price": 71.0}}, explicit_live_payload=explicit)
    assert got is explicit


def test_augment_result_with_live_entry_context_marks_missed_entry() -> None:
    got = augment_result_with_live_entry_context(
        {"symbol": "AKBNK", "entry": 71.0},
        {"current_price": 72.6500015258789, "last_price": 72.65, "price": 72.65},
    )

    assert got["live_entry_price"] == 71.0
    assert got["live_current_price"] == 72.65
    assert got["live_gap_pct"] == 2.3239
    assert got["live_entry_status"] == "extended_above_entry"
    assert got["live_entry_summary_code"] == "entry_missed_wait_pullback"
    assert got["entry_missed"] is True
    assert got["should_wait_pullback"] is True
    assert "giriş kaçmış" in got["live_entry_text"]
    assert "geri çekilme" in got["live_entry_text"]


def test_augment_result_with_live_entry_context_marks_discount() -> None:
    got = augment_result_with_live_entry_context(
        {"symbol": "AKBNK", "entry": 73.5},
        {"current_price": 72.6500015258789},
    )

    assert got["live_entry_status"] == "below_entry_discount"
    assert got["is_discount_to_entry"] is True
    assert "indirimli" in got["live_entry_text"]


def test_augment_result_with_live_entry_context_returns_original_without_entry() -> None:
    base = {"symbol": "AKBNK"}
    got = augment_result_with_live_entry_context(base, {"current_price": 72.65})
    assert got == base


def test_augment_result_with_live_entry_context_uses_result_embedded_live_payload() -> None:
    got = augment_result_with_live_entry_context(
        {
            "symbol": "AKBNK",
            "entry": 71.0,
            "live_payload": {"current_price": 72.6500015258789, "price": 72.65},
        }
    )

    assert got["live_entry_status"] == "extended_above_entry"
    assert got["entry_missed"] is True


def test_augment_result_with_live_entry_context_works_with_vendor_bridge_row(tmp_path: Path) -> None:
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
    got = augment_result_with_live_entry_context({"symbol": "AKBNK", "entry": 71.0}, row)

    assert row["current_price"] == 72.65
    assert got["live_current_price"] == 72.65
    assert got["live_entry_status"] == "extended_above_entry"
    assert got["entry_missed"] is True
    assert got["should_wait_pullback"] is True
