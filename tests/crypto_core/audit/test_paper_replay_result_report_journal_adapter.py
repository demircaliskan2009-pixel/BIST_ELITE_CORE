"""Tests for the PaperReplayResultReport -> EvidenceJournal audit bridge."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalEntry,
    EvidenceJournalError,
)
from crypto_core.audit.paper_replay_result_report_journal_adapter import (
    PaperReplayResultReportJournalAdapterError,
    append_paper_replay_result_report_to_evidence_journal,
    build_and_append_paper_replay_result_report_from_deterministic_replay,
)
from crypto_core.validation.deterministic_replay_executor import (
    build_deterministic_replay_input,
    execute_deterministic_replay,
)
from crypto_core.validation.paper_replay_result_report import (
    PaperReplayOutcomeStatus,
    PaperReplayResultReport,
    PaperReplayResultReportStatus,
    build_paper_replay_result_report,
    paper_replay_result_report_to_dict,
)
from crypto_core.validation.paper_replay_result_report_adapter import (
    PaperReplayResultReportAdapterError,
)
from crypto_core.validation.paper_replay_run_plan import (
    PaperReplayRunPlan,
    PaperReplayRunPlanStatus,
    paper_replay_run_plan_to_dict,
)


def _run_plan(**overrides) -> PaperReplayRunPlan:
    base = {
        "schema_version": "paper-replay-run-plan.v1",
        "status": PaperReplayRunPlanStatus.READY,
        "ready": True,
        "run_plan_id": "run-plan-001",
        "replay_mode": "offline_paper_replay",
        "requested_replay_id": "paper-replay-001",
        "operator_id": "operator-quant-1",
        "strategy_id": "bridge-s01",
        "strategy_digest": "d" * 64,
        "bundle_digest": "f" * 64,
        "admission_digest": "1" * 64,
        "bridge_digest": "e" * 64,
        "manifest_digest": "2" * 64,
        "intake_digest": "9" * 64,
        "intake_status": "READY",
        "replay_source_id": "offline-replay-v1",
        "historical_data_source_id": "historical-perp-journal-v1",
        "metadata": (),
        "rejection_reasons": (),
        "needs_research_reasons": (),
        "correlation_id": "corr:run-plan-001",
        "run_plan_digest": "0" * 64,
    }
    base.update(overrides)
    run_plan = PaperReplayRunPlan(**base)
    if "run_plan_digest" in overrides:
        return run_plan
    payload = paper_replay_run_plan_to_dict(run_plan)
    payload.pop("run_plan_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(run_plan, run_plan_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _report(*, outcome=PaperReplayOutcomeStatus.COMPLETED, metadata=None, run_plan=None) -> PaperReplayResultReport:
    run_plan = _run_plan() if run_plan is None else run_plan
    return build_paper_replay_result_report(
        run_plan,
        result_report_id="result-report-001",
        outcome_status=outcome,
        replay_trace_digest="3" * 64,
        metrics_digest="4" * 64,
        decision_trace_digest="5" * 64,
        correlation_id="corr:report-1",
        metadata=metadata,
    )


def _reseal_report(report: PaperReplayResultReport) -> PaperReplayResultReport:
    payload = paper_replay_result_report_to_dict(report)
    payload.pop("result_report_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(report, result_report_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _events() -> list[dict[str, object]]:
    return [
        {"event_type": "mark_price", "symbol": "BTC-PERP", "mark_price": "100.5", "sequence": 1},
        {"event_type": "mark_price", "symbol": "BTC-PERP", "mark_price": "101.0", "sequence": 2},
    ]


def _replay_pair():
    run_plan = _run_plan()
    replay_input = build_deterministic_replay_input(run_plan, events=_events(), correlation_id="corr:replay-1")
    return replay_input, execute_deterministic_replay(replay_input)


def _append(journal, report, correlation_id="corr:journal-1"):
    return append_paper_replay_result_report_to_evidence_journal(journal, report, correlation_id=correlation_id)


# 1 / 13. valid READY report appends one PAPER_REPLAY_RESULT_REPORT entry (False attestations)


def test_ready_report_appends_one_paper_replay_result_report_entry():
    report = _report()
    assert report.status is PaperReplayResultReportStatus.READY
    journal = EvidenceJournal()

    entry = _append(journal, report)

    assert isinstance(entry, EvidenceJournalEntry)
    assert entry.entry_type is EvidenceArtifactType.PAPER_REPLAY_RESULT_REPORT
    assert entry.payload["real_orders_enabled"] is False
    assert entry.payload["real_money_enabled"] is False
    assert journal.entry_count == 1
    assert journal.verify_chain().accepted is True


# 2. valid REJECTED report also appends (any-status)


def test_rejected_report_also_appends():
    report = _report(outcome=PaperReplayOutcomeStatus.REJECTED)
    assert report.status is PaperReplayResultReportStatus.REJECTED
    journal = EvidenceJournal()

    entry = _append(journal, report, correlation_id="corr:journal-2")

    assert entry.entry_type is EvidenceArtifactType.PAPER_REPLAY_RESULT_REPORT
    assert journal.entry_count == 1
    assert journal.verify_chain().accepted is True


# 3. appended payload equals paper_replay_result_report_to_dict(report)


def test_appended_payload_equals_canonical_to_dict():
    report = _report()
    journal = EvidenceJournal()

    entry = _append(journal, report)

    assert entry.payload == paper_replay_result_report_to_dict(report)


# 4. payload_digest deterministic and verify_chain accepted


def test_payload_digest_deterministic_and_chain_accepted():
    first_journal = EvidenceJournal()
    second_journal = EvidenceJournal()

    first = _append(first_journal, _report())
    second = _append(second_journal, _report())

    assert first.payload_digest == second.payload_digest
    assert first_journal.verify_chain().accepted is True
    assert second_journal.verify_chain().accepted is True


# 5. repeated append of same report payload fails closed; journal unchanged


def test_duplicate_report_append_fails_closed_and_journal_unchanged():
    report = _report()
    journal = EvidenceJournal()
    _append(journal, report, correlation_id="corr:a")
    head_before = journal.head_digest

    with pytest.raises(EvidenceJournalError):
        _append(journal, report, correlation_id="corr:b")  # identical payload -> payload_digest_replay

    assert journal.entry_count == 1
    assert journal.head_digest == head_before


# 6. forged result_report_digest fails before append; journal unchanged


def test_forged_result_report_digest_fails_before_append():
    report = replace(_report(), result_report_digest="0" * 64)
    journal = EvidenceJournal()

    with pytest.raises(PaperReplayResultReportJournalAdapterError) as exc:
        _append(journal, report)

    assert "result_report_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 0
    assert journal.head_digest is None


# 7. forged schema_version fails before append; journal unchanged


def test_forged_schema_version_fails_before_append():
    report = replace(_report(), schema_version="evil")
    journal = EvidenceJournal()

    with pytest.raises(PaperReplayResultReportJournalAdapterError) as exc:
        _append(journal, report)

    assert "report_schema_version_unexpected" in str(exc.value)
    assert journal.entry_count == 0


# 8. wrong journal/report types raise bridge Error


def test_wrong_types_raise_bridge_error():
    with pytest.raises(PaperReplayResultReportJournalAdapterError):
        _append("not-a-journal", _report())
    with pytest.raises(PaperReplayResultReportJournalAdapterError):
        _append(EvidenceJournal(), {"not": "a-report"})
    with pytest.raises(PaperReplayResultReportJournalAdapterError):
        _append(EvidenceJournal(), _report(), correlation_id="")


# 9. malformed direct-constructed report internals do not leak raw exception


def test_malformed_report_internals_raise_bridge_error_not_raw():
    report = replace(_report(), metadata=123)  # to_dict iterates metadata -> raw TypeError if unguarded
    journal = EvidenceJournal()

    with pytest.raises(PaperReplayResultReportJournalAdapterError) as exc:
        _append(journal, report)

    assert "report_malformed" in str(exc.value)
    assert journal.entry_count == 0


# 10. forbidden token in correlation / report payload fails closed


def test_forbidden_correlation_token_fails_closed():
    journal = EvidenceJournal()
    with pytest.raises(EvidenceJournalError):
        _append(journal, _report(), correlation_id="order_router_loop")
    assert journal.entry_count == 0


def test_forbidden_payload_metadata_token_fails_closed():
    report = _report(metadata={"note": "order_router"})
    journal = EvidenceJournal()
    with pytest.raises(EvidenceJournalError):
        _append(journal, report, correlation_id="corr:ok")
    assert journal.entry_count == 0


# 11. convenience helper builds report from deterministic replay output and appends it


def test_convenience_helper_builds_and_appends():
    replay_input, replay_output = _replay_pair()
    journal = EvidenceJournal()

    report, entry = build_and_append_paper_replay_result_report_from_deterministic_replay(
        journal,
        replay_input,
        replay_output,
        report_id="result-report-conv-1",
        correlation_id="corr:conv-1",
    )

    assert isinstance(report, PaperReplayResultReport)
    assert entry.entry_type is EvidenceArtifactType.PAPER_REPLAY_RESULT_REPORT
    assert journal.entry_count == 1
    assert entry.payload["result_report_digest"] == report.result_report_digest
    assert entry.payload == paper_replay_result_report_to_dict(report)
    assert journal.verify_chain().accepted is True


# 12. convenience helper rejects tampered replay through adapter path; journal unchanged


def test_convenience_helper_rejects_tampered_replay_output_and_journal_unchanged():
    replay_input, replay_output = _replay_pair()
    tampered = replace(replay_output, output_digest="0" * 64)
    journal = EvidenceJournal()

    with pytest.raises(PaperReplayResultReportAdapterError):
        build_and_append_paper_replay_result_report_from_deterministic_replay(
            journal,
            replay_input,
            tampered,
            report_id="result-report-conv-1",
            correlation_id="corr:conv-1",
        )

    assert journal.entry_count == 0
    assert journal.head_digest is None


def test_convenience_helper_wrong_journal_type_raises_bridge_error():
    replay_input, replay_output = _replay_pair()
    with pytest.raises(PaperReplayResultReportJournalAdapterError):
        build_and_append_paper_replay_result_report_from_deterministic_replay(
            "not-a-journal",
            replay_input,
            replay_output,
            report_id="result-report-conv-1",
            correlation_id="corr:conv-1",
        )


# 14. real_orders_enabled=True / real_money_enabled=True does not append


def test_true_attestation_report_does_not_append():
    # stale-digest True flag -> bridge digest re-proof rejects before append
    stale = replace(_report(), real_orders_enabled=True)
    journal = EvidenceJournal()
    with pytest.raises(PaperReplayResultReportJournalAdapterError) as exc:
        _append(journal, stale)
    assert "result_report_digest_mismatch" in str(exc.value)
    assert journal.entry_count == 0

    # self-consistent (resealed) True flag -> journal token guard rejects, journal unchanged
    sealed = _reseal_report(replace(_report(), real_orders_enabled=True))
    journal_two = EvidenceJournal()
    with pytest.raises(EvidenceJournalError) as exc_two:
        _append(journal_two, sealed)
    assert "paper_safety_attestation_not_false" in str(exc_two.value)
    assert journal_two.entry_count == 0


def test_true_money_attestation_resealed_report_does_not_append():
    sealed = _reseal_report(replace(_report(), real_money_enabled=True))
    journal = EvidenceJournal()
    with pytest.raises(EvidenceJournalError) as exc:
        _append(journal, sealed)
    assert "paper_safety_attestation_not_false" in str(exc.value)
    assert journal.entry_count == 0


# 15. module purity


def test_module_purity_no_impure_imports():
    import crypto_core.audit.paper_replay_result_report_journal_adapter as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level: set[str] = set()
    crypto_submodules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
            parts = node.module.split(".")
            if parts[0] == "crypto_core" and len(parts) > 1:
                crypto_submodules.add(parts[1])
    impure = {
        "os",
        "sys",
        "io",
        "pathlib",
        "time",
        "datetime",
        "threading",
        "asyncio",
        "multiprocessing",
        "socket",
        "subprocess",
        "random",
        "secrets",
        "uuid",
        "requests",
        "http",
        "urllib",
        "sqlite3",
    }
    assert top_level.isdisjoint(impure)
    assert crypto_submodules.isdisjoint({"service", "connector", "runtime", "venue", "execution", "orchestrator"})


# 16. no live/order/scheduler/connector/BIST implementation surface (exact public API only)


def test_no_forbidden_implementation_surface():
    import crypto_core.audit.paper_replay_result_report_journal_adapter as mod

    assert set(mod.__all__) == {
        "PaperReplayResultReportJournalAdapterError",
        "append_paper_replay_result_report_to_evidence_journal",
        "build_and_append_paper_replay_result_report_from_deterministic_replay",
    }
