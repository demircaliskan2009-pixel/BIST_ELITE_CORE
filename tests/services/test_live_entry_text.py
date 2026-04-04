from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from bist_core.services.live_entry_text import (
    append_live_entry_text,
    build_live_entry_context,
    build_live_entry_text,
)
from bist_core.vendors.ideal_01_tail import build_ideal_01_bridge_row


def _load_vendor_test_module():
    root = Path(__file__).resolve().parents[2]
    test_mod_path = root / "tests" / "vendors" / "test_ideal_01_tail.py"
    spec = importlib.util.spec_from_file_location("ideal01_vendor_test_mod_for_live_entry_text", test_mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ideal01_vendor_test_mod_for_live_entry_text"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_build_live_entry_text_marks_missed_entry() -> None:
    got = build_live_entry_context(71.0, {"current_price": 72.65})
    assert got["status"] == "extended_above_entry"
    assert got["entry_missed"] is True
    assert got["should_wait_pullback"] is True
    assert "giriş kaçmış" in got["text"]
    assert "geri çekilme" in got["text"]


def test_build_live_entry_text_marks_near_entry() -> None:
    got = build_live_entry_context(72.40, {"current_price": 72.65})
    assert got["status"] == "near_entry"
    assert got["entry_missed"] is False
    assert "yakın" in got["text"]


def test_build_live_entry_text_marks_discount() -> None:
    got = build_live_entry_context(73.50, {"current_price": 72.65})
    assert got["status"] == "below_entry_discount"
    assert got["is_discount_to_entry"] is True
    assert "indirimli" in got["text"]


def test_build_live_entry_text_returns_empty_without_live_price() -> None:
    assert build_live_entry_text(71.0, None) == ""


def test_append_live_entry_text_appends_sentence() -> None:
    got = append_live_entry_text("Plan korunuyor", 71.0, {"current_price": 72.65})
    assert got.startswith("Plan korunuyor")
    assert "giriş kaçmış" in got


def test_build_live_entry_text_works_with_vendor_bridge_row(tmp_path: Path) -> None:
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
    got = build_live_entry_context(71.0, row)

    assert row["current_price"] == 72.65
    assert got["live_price"] == 72.65
    assert got["status"] == "extended_above_entry"
    assert "giriş kaçmış" in got["text"]


def test_build_live_entry_text_formats_percent_as_suffix() -> None:
    got = build_live_entry_context(71.0, {"current_price": 72.65})
    assert got["gap_text"] == "+2.32%"
    assert "+2.32%" in got["text"]
    assert "%+2.32" not in got["text"]


def test_build_live_entry_text_near_entry_keeps_clean_parentheses_format() -> None:
    got = build_live_entry_context(72.40, {"current_price": 72.65})
    assert got["gap_text"] == "+0.35%"
    assert "(+0.35%)" in got["text"]
    assert "%+0.35" not in got["text"]
