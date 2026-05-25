from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49A.md")


def _normalized_doc_text() -> str:
    return " ".join(DOC.read_text(encoding="utf-8").split())


def test_phase49a_doc_records_report_only_scope_and_sources() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "status: BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_READY" in text
    assert "scope: REPORT_ONLY_CAMPAIGN_TELEMETRY_AUDIT" in text
    assert "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json" in text
    assert "docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_APPROVAL_47B.json" in text


def test_phase49a_doc_records_bounds_and_fail_closed_checks() -> None:
    text = _normalized_doc_text()

    for required in (
        "hard cap remains `3`",
        "`per_session_max_trades=2`",
        "`max_campaign_sessions=3`",
        "`sessions_requested=sessions_attempted=sessions_accepted=3`",
        "`sessions_rejected=0`",
        "`aggregate_trades_requested=aggregate_trades_filled=aggregate_ledger_mutations=6`",
        "`duplicate_mutation_blocked=true`",
        "fail closed on malformed counts, unsafe scope flags, connector drift, or any non-`PASS` campaign execution verdict",
    ):
        assert required in text


def test_phase49a_doc_records_non_scope_and_next_phase() -> None:
    text = _normalized_doc_text()

    assert "does not execute another campaign, session, or run" in text
    assert "does not mutate ledger state" in text
    assert "paper campaign performance evaluation only" in text
    assert "must not enable schedulers, automatic loops, shadow trading, or live trading" in text
