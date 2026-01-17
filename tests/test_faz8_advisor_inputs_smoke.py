from __future__ import annotations

from bist_core.services.advisor import build_advice_for_symbol


def test_advisor_inputs_smoke_fail_closed() -> None:
    advice = build_advice_for_symbol("TEST", "2099-01-01")
    assert advice.text, "Advice.text boş olmamalı"
    assert advice.decision_raw in {"BUY", "WATCH", "PASS"}
    assert "güvenli mod" in advice.text.lower()
