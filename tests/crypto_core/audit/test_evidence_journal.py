from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError

import pytest

import crypto_core.audit.evidence_journal as evidence_journal_module
from crypto_core.audit import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalEntry,
    EvidenceJournalError,
    EvidenceJournalVerification,
    evidence_journal_entry_digest,
    evidence_journal_entry_to_dict,
)


def _payload(artifact_id: str = "artifact-001") -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "chain": {"step": "source_packet", "values": [1, 2, 3]},
        "metadata": {"producer": "paper_replay_intake"},
    }


def _journal_with_two_entries() -> EvidenceJournal:
    journal = EvidenceJournal()
    journal.append(EvidenceArtifactType.SOURCE_PACKET, _payload("a"), correlation_id="corr-001")
    journal.append(EvidenceArtifactType.STRATEGY_VALIDATION_BUNDLE, _payload("b"), correlation_id="corr-002")
    return journal


def test_public_exports_from_crypto_core_audit_work() -> None:
    assert EvidenceArtifactType.SOURCE_PACKET.value == "SOURCE_PACKET"
    assert EvidenceJournalError.__mro__[1] is RuntimeError
    assert EvidenceJournalEntry.__name__ == "EvidenceJournalEntry"
    assert EvidenceJournalVerification.__name__ == "EvidenceJournalVerification"
    assert callable(evidence_journal_entry_to_dict)
    assert callable(evidence_journal_entry_digest)


def test_empty_journal_verifies_ok() -> None:
    verification = EvidenceJournal().verify_chain()

    assert verification.accepted is True
    assert verification.entry_count == 0
    assert verification.head_digest is None


def test_genesis_append_assigns_seq_zero_and_no_parent() -> None:
    journal = EvidenceJournal()
    entry = journal.append(EvidenceArtifactType.SOURCE_PACKET, _payload(), correlation_id="corr-001")

    assert entry.schema_version == "1.0"
    assert entry.journal_seq == 0
    assert entry.prev_entry_digest is None
    assert entry.entry_digest == journal.head_digest
    assert journal.entry_count == 1
    assert evidence_journal_entry_digest(entry) == entry.entry_digest


def test_multi_append_chain_and_stable_head_digest() -> None:
    first = _journal_with_two_entries()
    second = _journal_with_two_entries()

    assert first.entry_count == 2
    assert first.head_digest == second.head_digest
    assert [entry.entry_digest for entry in first.snapshot()] == [entry.entry_digest for entry in second.snapshot()]
    assert first.snapshot()[1].prev_entry_digest == first.snapshot()[0].entry_digest


def test_identical_fresh_journals_produce_identical_digests() -> None:
    first = _journal_with_two_entries()
    second = _journal_with_two_entries()

    assert tuple(e.entry_digest for e in first.snapshot()) == tuple(e.entry_digest for e in second.snapshot())
    assert tuple(e.payload_digest for e in first.snapshot()) == tuple(e.payload_digest for e in second.snapshot())


def test_duplicate_payload_digest_replay_refused() -> None:
    journal = EvidenceJournal()
    first = journal.append(EvidenceArtifactType.SOURCE_PACKET, _payload(), correlation_id="corr-001")

    with pytest.raises(EvidenceJournalError):
        journal.append(
            EvidenceArtifactType.BACKTEST_ADMISSION_DECISION,
            _payload(),
            correlation_id="corr-002",
            payload_digest=first.payload_digest,
        )


def test_duplicate_entry_digest_replay_detected_by_verification() -> None:
    journal = EvidenceJournal()
    entry = journal.append(EvidenceArtifactType.SOURCE_PACKET, _payload(), correlation_id="corr-001")
    journal._entries.append(entry)

    verification = journal.verify_chain()

    assert verification.accepted is False
    assert "evidence_journal:entry_digest_replay" in verification.rejection_reasons


def test_second_genesis_refused_with_backdoor_mutation() -> None:
    journal = _journal_with_two_entries()
    second = journal.snapshot()[1]
    object.__setattr__(second, "prev_entry_digest", None)

    verification = journal.verify_chain()

    assert verification.accepted is False
    assert "evidence_journal:second_genesis" in verification.rejection_reasons


def test_prev_digest_fork_refused_with_backdoor_mutation() -> None:
    journal = _journal_with_two_entries()
    second = journal.snapshot()[1]
    object.__setattr__(second, "prev_entry_digest", "0" * 64)

    verification = journal.verify_chain()

    assert verification.accepted is False
    assert "evidence_journal:prev_entry_digest_mismatch" in verification.rejection_reasons


def test_unknown_entry_type_refused() -> None:
    with pytest.raises(EvidenceJournalError):
        EvidenceJournal().append("UNKNOWN", _payload(), correlation_id="corr-001")


def test_caller_payload_digest_mismatch_refused() -> None:
    with pytest.raises(EvidenceJournalError):
        EvidenceJournal().append(
            EvidenceArtifactType.SOURCE_PACKET,
            _payload(),
            correlation_id="corr-001",
            payload_digest="0" * 64,
        )


def test_non_string_keys_refused() -> None:
    with pytest.raises(EvidenceJournalError):
        EvidenceJournal().append(EvidenceArtifactType.SOURCE_PACKET, {1: "bad"}, correlation_id="corr-001")


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), -float("inf")])
def test_nan_and_infinity_refused(bad_value: float) -> None:
    with pytest.raises(EvidenceJournalError):
        EvidenceJournal().append(
            EvidenceArtifactType.SOURCE_PACKET,
            {"artifact_id": "bad", "value": bad_value},
            correlation_id="corr-001",
        )


def test_non_serializable_payload_refused_without_raw_type_error_escape() -> None:
    with pytest.raises(EvidenceJournalError):
        EvidenceJournal().append(
            EvidenceArtifactType.SOURCE_PACKET,
            {"artifact_id": "bad", "value": object()},
            correlation_id="corr-001",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"created_at": "fixed"},
        {"timestamp": "fixed"},
        {"timestamp_ns": 1},
        {"time_ns": 1},
        {"policy": "utcnow"},
        {"policy": "now"},
        {"wall_clock": "bad"},
        {"market": "BIST"},
        {"scope": "live"},
        {"private_api": "enabled"},
        {"credential": "bad"},
        {"secret": "bad"},
        {"api_key": "bad"},
        {"order": "bad"},
        {"orders": "bad"},
        {"scheduler": "bad"},
        {"auto_loop": "bad"},
        {"connector_ready": "bad"},
        {"shadow": "bad"},
    ],
)
def test_wall_clock_bist_and_forbidden_tokens_refused(payload: dict[str, object]) -> None:
    with pytest.raises(EvidenceJournalError):
        EvidenceJournal().append(EvidenceArtifactType.SOURCE_PACKET, payload, correlation_id="corr-001")


def test_order_book_market_data_term_is_not_a_false_positive() -> None:
    entry = EvidenceJournal().append(
        EvidenceArtifactType.SOURCE_PACKET,
        {"order_book": {"best_bid": 1}},
        correlation_id="corr-001",
    )

    assert entry.journal_seq == 0


def test_payload_tamper_after_append_causes_read_and_verify_failure() -> None:
    journal = EvidenceJournal()
    entry = journal.append(EvidenceArtifactType.SOURCE_PACKET, _payload(), correlation_id="corr-001")
    entry.payload["artifact_id"] = "tampered"

    assert journal.verify_chain().accepted is False
    with pytest.raises(EvidenceJournalError):
        journal.get_by_sequence(0)
    with pytest.raises(EvidenceJournalError):
        journal.snapshot()


def test_entry_digest_tamper_causes_read_and_verify_failure() -> None:
    journal = EvidenceJournal()
    entry = journal.append(EvidenceArtifactType.SOURCE_PACKET, _payload(), correlation_id="corr-001")
    object.__setattr__(entry, "entry_digest", "0" * 64)

    assert journal.verify_chain().accepted is False
    with pytest.raises(EvidenceJournalError):
        journal.get_by_entry_digest("0" * 64)


def test_sequence_discontinuity_causes_failure() -> None:
    journal = _journal_with_two_entries()
    second = journal.snapshot()[1]
    object.__setattr__(second, "journal_seq", 3)

    verification = journal.verify_chain()

    assert verification.accepted is False
    assert "evidence_journal:sequence_discontinuity" in verification.rejection_reasons


def test_parent_discontinuity_causes_failure() -> None:
    journal = _journal_with_two_entries()
    second = journal.snapshot()[1]
    object.__setattr__(second, "prev_entry_digest", "f" * 64)

    verification = journal.verify_chain()

    assert verification.accepted is False
    assert "evidence_journal:prev_entry_digest_mismatch" in verification.rejection_reasons


def test_get_by_sequence_verifies_before_return_and_missing_seq_raises() -> None:
    journal = _journal_with_two_entries()

    assert journal.get_by_sequence(1).journal_seq == 1
    with pytest.raises(EvidenceJournalError):
        journal.get_by_sequence(99)

    object.__setattr__(journal.snapshot()[0], "entry_digest", "1" * 64)
    with pytest.raises(EvidenceJournalError):
        journal.get_by_sequence(0)


def test_get_by_entry_digest_verifies_before_return() -> None:
    journal = _journal_with_two_entries()
    entry = journal.snapshot()[1]

    assert journal.get_by_entry_digest(entry.entry_digest) == entry
    object.__setattr__(journal.snapshot()[0], "entry_digest", "1" * 64)
    with pytest.raises(EvidenceJournalError):
        journal.get_by_entry_digest(entry.entry_digest)


def test_get_by_payload_digest_verifies_before_return() -> None:
    journal = _journal_with_two_entries()
    entry = journal.snapshot()[1]

    assert journal.get_by_payload_digest(entry.payload_digest) == entry
    object.__setattr__(journal.snapshot()[0], "entry_digest", "1" * 64)
    with pytest.raises(EvidenceJournalError):
        journal.get_by_payload_digest(entry.payload_digest)


def test_snapshot_is_immutable_tuple() -> None:
    journal = _journal_with_two_entries()
    snapshot = journal.snapshot()

    assert isinstance(snapshot, tuple)
    with pytest.raises(TypeError):
        snapshot[0] = snapshot[1]


def test_frozen_dataclass_mutation_raises() -> None:
    entry = EvidenceJournal().append(EvidenceArtifactType.SOURCE_PACKET, _payload(), correlation_id="corr-001")

    with pytest.raises(FrozenInstanceError):
        entry.correlation_id = "changed"


def test_forbidden_mutator_methods_absent() -> None:
    for method_name in ("update", "delete", "truncate", "compact", "clear"):
        assert not hasattr(EvidenceJournal, method_name)


def test_module_stays_pure() -> None:
    source = ast.parse(evidence_journal_module.__loader__.get_source(evidence_journal_module.__name__))
    imported_modules: set[str] = set()
    for node in ast.walk(source):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module.split(".")[0])

    assert not {"os", "pathlib", "time", "threading"} & imported_modules
    assert not any(
        node.module and "crypto_core.service" in node.module
        for node in ast.walk(source)
        if isinstance(node, ast.ImportFrom)
    )
    assert not any(
        node.module and "crypto_core.validation" in node.module
        for node in ast.walk(source)
        if isinstance(node, ast.ImportFrom)
    )
