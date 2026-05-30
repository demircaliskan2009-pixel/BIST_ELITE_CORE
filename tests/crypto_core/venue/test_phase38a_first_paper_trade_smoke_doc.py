from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/FIRST_PAPER_TRADE_SMOKE_PROOF_38A.md")


def test_phase38a_smoke_proof_doc_records_verified_phase37_state() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "status: FIRST_DETERMINISTIC_PAPER_TRADE_SMOKE_PROOF_READY" in text
    assert "| `main` | `44e49100a7f49d9b307c5816d8523bb621820e11` |" in text
    assert "| `accepted` | `True` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "| `explicit_operator_triggered_paper_trade_gate_status` | `READY` |" in text
    assert "| `automatic_paper_loop_status` | `NO` |" in text
    assert "| `live_or_shadow_status` | `NO` |" in text


def test_phase38a_smoke_proof_doc_keeps_scope_offline_and_paper_only() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "deterministic fixture" in text
    assert "explicit operator trigger" in text
    assert "phase37 paper trade gate" in text
    assert "no network call" in text
    assert "does not add private api" in text
    assert "exchange orders" in text
    assert "scheduler" in text
    assert "automatic paper loops" in text
    assert "shadow trading" in text
    assert "live trading" in text
