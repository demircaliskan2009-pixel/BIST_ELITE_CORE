from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")
PHASE38_FILES = (
    Path("docs/crypto_core/FIRST_PAPER_TRADE_SMOKE_PROOF_38A.md"),
    Path("docs/crypto_core/DERIBIT_FIRST_PAPER_TRADE_SMOKE_PROOF_38B.json"),
    Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_38H.md"),
)


def test_phase38g_connector_ready_dialect_and_validator_state_are_preserved() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    dialects = connector_ready_dialects()
    spec = get_public_feed_dialect("deribit:l2_orderbook:book_instrument_interval")

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(dialects) == 1
    assert spec.max_gap_tolerance == 0
    assert spec.max_staleness_ns == 2_000_000_000
    assert spec.max_receive_lag_ns == 1_000_000_000
    assert spec.supports_checksum is False


def test_phase38g_public_feed_dialects_source_is_not_changed_for_phase38() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")

    assert "deribit:l2_orderbook:book_instrument_interval" in text
    assert "supports_checksum=False" in text
    assert "max_gap_tolerance=0" in text
    assert "enabled_for_connector=True" in text


def test_phase38g_phase38_files_have_no_bist_leakage() -> None:
    for path in PHASE38_FILES:
        assert "bist" not in path.read_text(encoding="utf-8").lower()
