"""Phase 27L source snapshot manifest acceptance metadata tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import _parse_md_table_rows

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md"
)

_EXPECTED = {
    "DERIBIT_NOTIFICATIONS": (
        "https://docs.deribit.com/#notifications",
        "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd",
    ),
    "DERIBIT_ENVIRONMENT": (
        "https://docs.deribit.com/#json-rpc-over-websocket",
        "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd",
    ),
    "DERIBIT_RATE_LIMITS": (
        "https://docs.deribit.com/#rate-limits",
        "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd",
    ),
    "DERIBIT_INSTRUMENTS": (
        "https://docs.deribit.com/#public-get_instruments",
        "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd",
    ),
    "DERIBIT_TICKER": (
        "https://docs.deribit.com/#ticker-instrument_name-interval",
        "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd",
    ),
    "DERIBIT_RESTRICTED": (
        "https://docs.deribit.com/#restricted-countries",
        "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd",
    ),
}


def _source_rows() -> dict[str, dict[str, str]]:
    rows = _parse_md_table_rows(MANIFEST.read_text(encoding="utf-8"))
    return {row["source_id"]: row for row in rows if row.get("source_id", "").startswith("DERIBIT_")}


def test_phase27l_manifest_has_six_source_snapshot_rows() -> None:
    rows = _source_rows()
    assert set(rows) == set(_EXPECTED)


def test_phase27l_manifest_preserves_source_ids_urls_hashes_and_retrieval_status() -> None:
    rows = _source_rows()

    for source_id, (official_url, content_sha256) in _EXPECTED.items():
        row = rows[source_id]
        assert row["official_url"] == official_url
        assert row["content_sha256"] == content_sha256
        assert row["retrieval_status"] == "REVIEWED_APPROVED"
        assert int(row["content_size_bytes"]) == 939778


def test_phase27l_manifest_records_complete_acceptance_metadata() -> None:
    for row in _source_rows().values():
        assert row["acceptance_decision"] == "APPROVE"
        assert row["accepted_by"] == "demir_operator"
        assert row["accepted_at_iso"] == "2026-05-19T00:00:00Z"
        assert row["acceptance_scope"] == "Phase27K_SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE"
        assert "DERIBIT_SOURCE_SNAPSHOT_ACCEPTANCE_AUDIT_27K.md" in row["evidence_refs"]
