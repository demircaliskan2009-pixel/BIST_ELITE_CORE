from __future__ import annotations

from bist_core.services import advisor as advisor_mod


def test_build_live_entry_augmented_text_appends_missed_entry_commentary() -> None:
    got = advisor_mod.build_live_entry_augmented_text(
        "Plan korunuyor.",
        entry_price=71.0,
        live_payload={
            "symbol": "AKBNK",
            "source_period": "01",
            "current_price": 72.6500015258789,
            "last_price": 72.65,
            "price": 72.65,
        },
    )

    assert got.startswith("Plan korunuyor.")
    assert "giriş kaçmış" in got
    assert "geri çekilme" in got


def test_build_live_entry_augmented_text_returns_base_text_when_missing_context() -> None:
    got = advisor_mod.build_live_entry_augmented_text(
        "Plan korunuyor.",
        entry_price=None,
        live_payload=None,
    )
    assert got == "Plan korunuyor."
