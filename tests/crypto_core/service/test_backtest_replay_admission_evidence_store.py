from __future__ import annotations

import json
from pathlib import Path

from crypto_core.service.evidence_store import (
    EvidenceStore,
    backtest_replay_admission_to_evidence_payload,
)
from crypto_core.validation.backtest_replay_admission import (
    BacktestReplayAdmissionResult,
    BacktestReplayAdmissionStatus,
    BacktestReplayWindow,
    backtest_replay_admission_digest,
    backtest_replay_admission_to_dict,
)


def _accepted_result() -> BacktestReplayAdmissionResult:
    return BacktestReplayAdmissionResult(
        accepted=True,
        status=BacktestReplayAdmissionStatus.ACCEPTED,
        strategy_id="admission-evidence-s01",
        strategy_digest="a" * 64,
        replay_source_id="offline-replay-v1",
        historical_data_source_id="historical-perp-journal-v1",
        replay_window=BacktestReplayWindow(start_ns=1_000, end_ns=2_000),
        decision_ledger_digests={"STRATEGY_SPEC": "b" * 64},
        evidence_digest_by_stage={"STRATEGY_SPEC": "b" * 64},
        rejection_reasons=(),
        needs_research_reasons=(),
    )


def _rejected_result() -> BacktestReplayAdmissionResult:
    return BacktestReplayAdmissionResult(
        accepted=False,
        status=BacktestReplayAdmissionStatus.REJECTED,
        strategy_id="admission-evidence-s01",
        strategy_digest="a" * 64,
        replay_source_id="offline-replay-v1",
        historical_data_source_id="historical-perp-journal-v1",
        replay_window=BacktestReplayWindow(start_ns=1_000, end_ns=2_000),
        decision_ledger_digests={},
        evidence_digest_by_stage={},
        rejection_reasons=("backtest_replay_admission:lbr_ledger_output_digest_mismatch",),
        needs_research_reasons=(),
    )


def _raw_lines(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_accepted_admission_result_appends(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")

    result = store.append_backtest_replay_admission_record(_accepted_result())

    assert result.success is True
    loaded = store.load_evidence()
    assert len(loaded) == 1
    assert loaded[0]["evidence_type"] == "audit_record"
    assert loaded[0]["timestamp_ns"] == 0
    assert loaded[0]["data"]["payload_type"] == "backtest_replay_admission"


def test_payload_digest_equals_admission_digest(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    admission = _accepted_result()

    store.append_backtest_replay_admission_record(admission)

    loaded = store.load_evidence()
    assert loaded[0]["data"]["evidence_digest"] == backtest_replay_admission_digest(admission)


def test_loaded_payload_preserves_key_fields(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    admission = _accepted_result()

    store.append_backtest_replay_admission_record(admission)

    data = store.load_evidence()[0]["data"]
    assert data["payload_type"] == "backtest_replay_admission"
    assert data["accepted"] is True
    assert data["status"] == BacktestReplayAdmissionStatus.ACCEPTED.value
    assert data["strategy_id"] == "admission-evidence-s01"
    assert data["backtest_replay_admission_result"] == backtest_replay_admission_to_dict(admission)


def test_duplicate_admission_digest_rejects(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    admission = _accepted_result()

    first = store.append_backtest_replay_admission_record(admission)
    second = store.append_backtest_replay_admission_record(admission)

    assert first.success is True
    assert second.success is False
    assert "Duplicate backtest replay admission evidence digest" in (second.error or "")
    assert store.evidence_line_count() == 1


def test_non_result_input_rejects_fail_closed(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")

    result = store.append_backtest_replay_admission_record({"not": "a result"})  # type: ignore[arg-type]

    assert result.success is False
    assert "result_malformed" in (result.error or "")
    assert not store.evidence_log_path.exists()


def test_rejected_admission_result_is_persistable(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    admission = _rejected_result()

    result = store.append_backtest_replay_admission_record(admission)

    assert result.success is True
    data = store.load_evidence()[0]["data"]
    assert data["accepted"] is False
    assert data["status"] == BacktestReplayAdmissionStatus.REJECTED.value
    assert "backtest_replay_admission:lbr_ledger_output_digest_mismatch" in data["rejection_reasons"]
    assert data["evidence_digest"] == backtest_replay_admission_digest(admission)


def test_evidence_payload_is_deterministic() -> None:
    first = backtest_replay_admission_to_evidence_payload(_accepted_result())
    second = backtest_replay_admission_to_evidence_payload(_accepted_result())

    assert first == second
    assert first["evidence_digest"] == second["evidence_digest"]


def test_no_runtime_timestamp_in_admission_payload(tmp_path: Path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")

    store.append_backtest_replay_admission_record(_accepted_result())

    raw = _raw_lines(store.evidence_log_path)
    assert raw[0]["timestamp_ns"] == 0
    data = raw[0]["data"]
    assert "timestamp_ns" not in data
    assert "created_at" not in data


def test_admission_and_decision_ledger_dedup_namespaces_isolated(tmp_path: Path) -> None:
    # Admission and decision-ledger evidence share the "audit_record" bucket but are discriminated by
    # payload_type; an admission digest must not be seen by the decision-ledger dedup check.
    store = EvidenceStore(evidence_dir=tmp_path / "evidence")
    admission = _accepted_result()

    assert store.append_backtest_replay_admission_record(admission).success is True
    digest = backtest_replay_admission_digest(admission)
    assert store._backtest_replay_admission_digest_exists(digest) is True
    assert store._decision_ledger_digest_exists(digest) is False
