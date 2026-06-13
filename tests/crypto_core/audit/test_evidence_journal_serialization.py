from __future__ import annotations

import ast

import pytest

import crypto_core.audit.evidence_journal as evidence_journal_module
from crypto_core.audit import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalError,
    evidence_journal_entry_to_dict,
    evidence_journal_from_dict,
    evidence_journal_to_dict,
)


def _payload(artifact_id: str = "artifact-001") -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "chain": {"step": "source_packet", "values": [1, 2, 3]},
        "metadata": {"producer": "paper_replay_intake"},
    }


def _journal() -> EvidenceJournal:
    journal = EvidenceJournal()
    journal.append(EvidenceArtifactType.SOURCE_PACKET, _payload("a"), correlation_id="corr-001")
    journal.append(EvidenceArtifactType.STRATEGY_VALIDATION_BUNDLE, _payload("b"), correlation_id="corr-002")
    journal.append(EvidenceArtifactType.BACKTEST_ADMISSION_DECISION, _payload("c"), correlation_id="corr-003")
    return journal


def _exported_journal() -> dict[str, object]:
    return evidence_journal_to_dict(_journal())


def _entries(exported: dict[str, object]) -> list[dict[str, object]]:
    entries = exported["entries"]
    assert isinstance(entries, list)
    assert all(isinstance(entry, dict) for entry in entries)
    return entries


def test_public_exports_from_crypto_core_audit_include_journal_serializers() -> None:
    assert callable(evidence_journal_to_dict)
    assert callable(evidence_journal_from_dict)


def test_empty_journal_round_trip_preserves_count_and_head() -> None:
    exported = evidence_journal_to_dict(EvidenceJournal())
    loaded = evidence_journal_from_dict(exported)

    assert loaded.entry_count == 0
    assert loaded.head_digest is None
    assert loaded.snapshot() == ()


def test_non_empty_round_trip_preserves_chain_and_entry_digests() -> None:
    journal = _journal()
    exported = evidence_journal_to_dict(journal)
    loaded = evidence_journal_from_dict(exported)

    assert loaded.entry_count == journal.entry_count
    assert loaded.head_digest == journal.head_digest
    assert [entry.payload_digest for entry in loaded.snapshot()] == [
        entry.payload_digest for entry in journal.snapshot()
    ]
    assert [entry.entry_digest for entry in loaded.snapshot()] == [entry.entry_digest for entry in journal.snapshot()]
    assert [evidence_journal_entry_to_dict(entry) for entry in loaded.snapshot()] == exported["entries"]


def test_export_envelope_contains_strict_fields() -> None:
    exported = evidence_journal_to_dict(_journal())

    assert set(exported) == {"schema_version", "entry_count", "head_digest", "entries"}
    assert exported["schema_version"] == "evidence-journal.v1"
    assert exported["entry_count"] == 3
    assert exported["head_digest"] == _journal().head_digest
    assert len(_entries(exported)) == 3


def test_payload_tamper_in_exported_dict_raises() -> None:
    exported = _exported_journal()
    payload = _entries(exported)[0]["payload"]
    assert isinstance(payload, dict)
    payload["artifact_id"] = "tampered"

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_stored_payload_digest_tamper_raises() -> None:
    exported = _exported_journal()
    _entries(exported)[0]["payload_digest"] = "0" * 64

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_stored_entry_digest_tamper_raises() -> None:
    exported = _exported_journal()
    _entries(exported)[0]["entry_digest"] = "0" * 64

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_stored_prev_entry_digest_tamper_raises() -> None:
    exported = _exported_journal()
    _entries(exported)[1]["prev_entry_digest"] = "0" * 64

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_stored_journal_seq_tamper_raises() -> None:
    exported = _exported_journal()
    _entries(exported)[1]["journal_seq"] = 9

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_reordered_entries_raise() -> None:
    exported = _exported_journal()
    entries = _entries(exported)
    exported["entries"] = [entries[1], entries[0], entries[2]]

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_drop_middle_entry_raises() -> None:
    exported = _exported_journal()
    entries = _entries(exported)
    exported["entries"] = [entries[0], entries[2]]

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_drop_final_entry_raises_on_wrapper_count_and_head_mismatch() -> None:
    exported = _exported_journal()
    exported["entries"] = _entries(exported)[:-1]

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_duplicate_replayed_payload_entry_raises() -> None:
    exported = _exported_journal()
    entries = _entries(exported)
    entries[1]["payload"] = entries[0]["payload"]

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_wrapper_head_digest_tamper_raises() -> None:
    exported = _exported_journal()
    exported["head_digest"] = "0" * 64

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_wrapper_entry_count_tamper_raises() -> None:
    exported = _exported_journal()
    exported["entry_count"] = 99

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_missing_wrapper_field_raises() -> None:
    exported = _exported_journal()
    del exported["head_digest"]

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_extra_wrapper_field_raises() -> None:
    exported = _exported_journal()
    exported["extra"] = "bad"

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_wrong_wrapper_schema_version_raises() -> None:
    exported = _exported_journal()
    exported["schema_version"] = "evidence-journal.v2"

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_non_mapping_input_raises_evidence_journal_error() -> None:
    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(["not", "a", "mapping"])


def test_non_list_entries_raises_evidence_journal_error() -> None:
    exported = _exported_journal()
    exported["entries"] = {"bad": "entry"}

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_malformed_entry_object_raises_without_raw_exception_escape() -> None:
    exported = _exported_journal()
    exported["entries"] = ["bad-entry"]

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


def test_forbidden_token_payload_still_rejected_on_load() -> None:
    exported = _exported_journal()
    _entries(exported)[0]["payload"] = {"scope": "live"}

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(exported)


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
