"""Phase 27M manifest approval parser fail-closed tests."""

from __future__ import annotations

from crypto_core.venue.deribit_manual_review_readiness import _validate_manifest

_HASH = "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd"


def _manifest_row(
    *,
    retrieval_status: str = "REVIEWED_APPROVED",
    acceptance_decision: str = "APPROVE",
    accepted_by: str = "demir_operator",
    accepted_at_iso: str = "2026-05-19T00:00:00Z",
    acceptance_scope: str = "Phase27K_SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE",
) -> str:
    return (
        "| source_id | official_url | retrieved_at_iso | retrieval_status | content_sha256 | content_size_bytes"
        " | local_temp_path | acceptance_decision | accepted_by | accepted_at_iso | acceptance_scope | evidence_refs |\n"
        "|---|---|---|---|---|---:|---|---|---|---|---|---|\n"
        "| `DERIBIT_ENVIRONMENT` | `https://docs.deribit.com/#json-rpc-over-websocket`"
        f" | `2026-05-10T07:51:22Z` | `{retrieval_status}` | `{_HASH}` | 939778"
        " | `.tmp_official_sources/deribit/20260510/DERIBIT_ENVIRONMENT.html`"
        f" | `{acceptance_decision}` | `{accepted_by}` | `{accepted_at_iso}` | `{acceptance_scope}`"
        " | `DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md;DERIBIT_SOURCE_SNAPSHOT_ACCEPTANCE_AUDIT_27K.md` |\n"
    )


def test_phase27m_explicit_acceptance_metadata_promotes_manifest_row_to_approved() -> None:
    rows = _validate_manifest(_manifest_row())
    assert len(rows) == 1
    assert rows[0].status == "APPROVED"
    assert rows[0].missing_metadata == ()
    assert rows[0].rejection_reasons == ()


def test_phase27m_reviewed_approved_without_acceptance_metadata_remains_reviewed() -> None:
    rows = _validate_manifest(
        _manifest_row(
            acceptance_decision="PENDING",
            accepted_by="PENDING",
            accepted_at_iso="PENDING",
            acceptance_scope="PENDING",
        )
    )
    assert rows[0].status == "REVIEWED"
    assert rows[0].status != "APPROVED"


def test_phase27m_incomplete_acceptance_metadata_remains_reviewed_and_blocking() -> None:
    rows = _validate_manifest(_manifest_row(accepted_at_iso="PENDING"))
    assert rows[0].status == "REVIEWED"
    assert any("accepted_at_iso_pending" in item for item in rows[0].missing_metadata)


def test_phase27m_pending_retrieval_status_remains_pending_even_with_acceptance_fields() -> None:
    rows = _validate_manifest(_manifest_row(retrieval_status="SUPPLIED_HASHED_PENDING_REVIEW"))
    assert rows[0].status == "PENDING"
    assert any("manual_review_pending" in item for item in rows[0].missing_metadata)


def test_phase27m_reject_and_defer_fail_closed() -> None:
    rejected = _validate_manifest(_manifest_row(acceptance_decision="REJECT"))[0]
    deferred = _validate_manifest(_manifest_row(acceptance_decision="DEFER"))[0]

    assert rejected.status == "REJECTED"
    assert rejected.rejection_reasons == ("DERIBIT_ENVIRONMENT:rejected",)
    assert deferred.status == "DEFERRED"
    assert deferred.rejection_reasons == ("DERIBIT_ENVIRONMENT:deferred",)
