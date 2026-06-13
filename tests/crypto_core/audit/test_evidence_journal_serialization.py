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


def _exported_journal_with_anchors() -> tuple[dict[str, object], int, str | None]:
    journal = _journal()
    return evidence_journal_to_dict(journal), journal.entry_count, journal.head_digest


def _load_with_anchors(
    exported: dict[str, object],
    expected_entry_count: int,
    expected_head_digest: str | None,
) -> EvidenceJournal:
    return evidence_journal_from_dict(
        exported,
        expected_entry_count=expected_entry_count,
        expected_head_digest=expected_head_digest,
    )


def _entries(exported: dict[str, object]) -> list[dict[str, object]]:
    entries = exported["entries"]
    assert isinstance(entries, list)
    assert all(isinstance(entry, dict) for entry in entries)
    return entries


def _entry_digest(entry: dict[str, object]) -> str:
    entry_digest = entry["entry_digest"]
    assert isinstance(entry_digest, str)
    return entry_digest


def test_public_exports_from_crypto_core_audit_include_journal_serializers() -> None:
    assert callable(evidence_journal_to_dict)
    assert callable(evidence_journal_from_dict)


def test_empty_journal_round_trip_preserves_count_and_head() -> None:
    journal = EvidenceJournal()
    exported = evidence_journal_to_dict(journal)
    loaded = evidence_journal_from_dict(
        exported,
        expected_entry_count=journal.entry_count,
        expected_head_digest=journal.head_digest,
    )

    assert loaded.entry_count == 0
    assert loaded.head_digest is None
    assert loaded.snapshot() == ()


def test_non_empty_round_trip_preserves_chain_and_entry_digests() -> None:
    journal = _journal()
    exported = evidence_journal_to_dict(journal)
    loaded = evidence_journal_from_dict(
        exported,
        expected_entry_count=journal.entry_count,
        expected_head_digest=journal.head_digest,
    )

    assert loaded.entry_count == journal.entry_count
    assert loaded.head_digest == journal.head_digest
    assert [entry.payload_digest for entry in loaded.snapshot()] == [
        entry.payload_digest for entry in journal.snapshot()
    ]
    assert [entry.entry_digest for entry in loaded.snapshot()] == [entry.entry_digest for entry in journal.snapshot()]
    assert [evidence_journal_entry_to_dict(entry) for entry in loaded.snapshot()] == exported["entries"]


def test_export_envelope_contains_strict_fields() -> None:
    journal = _journal()
    exported = evidence_journal_to_dict(journal)

    assert set(exported) == {"schema_version", "entry_count", "head_digest", "entries"}
    assert exported["schema_version"] == "evidence-journal.v1"
    assert exported["entry_count"] == journal.entry_count
    assert exported["head_digest"] == journal.head_digest
    assert len(_entries(exported)) == 3


def test_blind_import_without_expected_anchors_raises() -> None:
    exported, _expected_entry_count, _expected_head_digest = _exported_journal_with_anchors()

    with pytest.raises(TypeError):
        evidence_journal_from_dict(exported)


def test_external_anchor_detects_final_truncation_with_rewritten_wrapper() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    entries = _entries(exported)
    exported["entries"] = entries[:-1]
    exported["entry_count"] = 2
    exported["head_digest"] = _entry_digest(entries[1])

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_external_anchor_detects_full_rollback_with_rewritten_wrapper() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    entries = _entries(exported)
    exported["entries"] = entries[:1]
    exported["entry_count"] = 1
    exported["head_digest"] = _entry_digest(entries[0])

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_wrong_expected_entry_count_raises_with_otherwise_valid_envelope() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count - 1, expected_head_digest)


def test_wrong_expected_head_digest_raises_with_otherwise_valid_envelope() -> None:
    exported, expected_entry_count, _expected_head_digest = _exported_journal_with_anchors()

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, "0" * 64)


def test_empty_journal_import_requires_empty_external_anchors() -> None:
    journal = EvidenceJournal()
    exported = evidence_journal_to_dict(journal)

    loaded = evidence_journal_from_dict(
        exported,
        expected_entry_count=0,
        expected_head_digest=None,
    )

    assert loaded.entry_count == 0
    assert loaded.head_digest is None


@pytest.mark.parametrize("bad_expected_entry_count", [True, -1, "3", None])
def test_malformed_expected_entry_count_raises(bad_expected_entry_count: object) -> None:
    exported, _expected_entry_count, expected_head_digest = _exported_journal_with_anchors()

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(
            exported,
            expected_entry_count=bad_expected_entry_count,
            expected_head_digest=expected_head_digest,
        )


@pytest.mark.parametrize("bad_expected_head_digest", [True, 3, ["bad"]])
def test_malformed_expected_head_digest_raises(bad_expected_head_digest: object) -> None:
    exported, expected_entry_count, _expected_head_digest = _exported_journal_with_anchors()

    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(
            exported,
            expected_entry_count=expected_entry_count,
            expected_head_digest=bad_expected_head_digest,
        )


def test_payload_tamper_in_exported_dict_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    payload = _entries(exported)[0]["payload"]
    assert isinstance(payload, dict)
    payload["artifact_id"] = "tampered"

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_stored_payload_digest_tamper_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    _entries(exported)[0]["payload_digest"] = "0" * 64

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_stored_entry_digest_tamper_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    _entries(exported)[0]["entry_digest"] = "0" * 64

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_stored_prev_entry_digest_tamper_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    _entries(exported)[1]["prev_entry_digest"] = "0" * 64

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_stored_journal_seq_tamper_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    _entries(exported)[1]["journal_seq"] = 9

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_reordered_entries_raise() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    entries = _entries(exported)
    exported["entries"] = [entries[1], entries[0], entries[2]]

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_drop_middle_entry_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    entries = _entries(exported)
    exported["entries"] = [entries[0], entries[2]]

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_drop_final_entry_raises_on_wrapper_count_and_head_mismatch() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    exported["entries"] = _entries(exported)[:-1]

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_duplicate_replayed_payload_entry_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    entries = _entries(exported)
    entries[1]["payload"] = entries[0]["payload"]

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_wrapper_head_digest_tamper_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    exported["head_digest"] = "0" * 64

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_wrapper_entry_count_tamper_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    exported["entry_count"] = 99

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_missing_wrapper_field_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    del exported["head_digest"]

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_extra_wrapper_field_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    exported["extra"] = "bad"

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_wrong_wrapper_schema_version_raises() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    exported["schema_version"] = "evidence-journal.v2"

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_non_mapping_input_raises_evidence_journal_error() -> None:
    with pytest.raises(EvidenceJournalError):
        evidence_journal_from_dict(
            ["not", "a", "mapping"],
            expected_entry_count=0,
            expected_head_digest=None,
        )


def test_non_list_entries_raises_evidence_journal_error() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    exported["entries"] = {"bad": "entry"}

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_malformed_entry_object_raises_without_raw_exception_escape() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    exported["entries"] = ["bad-entry"]

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


def test_forbidden_token_payload_still_rejected_on_load() -> None:
    exported, expected_entry_count, expected_head_digest = _exported_journal_with_anchors()
    _entries(exported)[0]["payload"] = {"scope": "live"}

    with pytest.raises(EvidenceJournalError):
        _load_with_anchors(exported, expected_entry_count, expected_head_digest)


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
