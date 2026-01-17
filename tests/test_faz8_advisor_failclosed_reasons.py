from __future__ import annotations

from bist_core.services.advisor import build_advice_for_symbol


def test_advisor_fail_closed_reason_marker() -> None:
    advice = build_advice_for_symbol("TEST", "2099-01-01")
    assert advice.decision_raw == "PASS"
    text = advice.text.lower()
    assert "güvenli mod" in text
    assert "nobars" in text or "nodecision" in text
