"""Phase 26AR — Deep Research evidence pack for Deribit regional/legal access."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_PACK_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_REGIONAL_LEGAL_ACCESS_RESEARCH_PACK_26AR.md"
MANIFEST_PATH = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md"
)


def _content() -> str:
    return RESEARCH_PACK_PATH.read_text(encoding="utf-8")


def test_phase26ar_research_pack_exists() -> None:
    assert RESEARCH_PACK_PATH.exists(), "Research pack document must exist"


def test_phase26ar_research_pack_non_empty() -> None:
    assert len(_content()) > 100


def test_phase26ar_verdict_block_present() -> None:
    content = _content()
    assert "VERDICT=TURKEY_PUBLIC_MARKET_DATA_DOCS_CLEAR_ENOUGH_FOR_OPERATOR_REVIEW" in content


def test_phase26ar_confidence_medium() -> None:
    assert "CONFIDENCE=MEDIUM" in _content()


def test_phase26ar_turkey_not_restricted_finding() -> None:
    content = _content()
    assert "TURKEY_RESTRICTED_STATUS=NO" in content
    assert "Turkey is not listed" in content


def test_phase26ar_unauth_public_api_finding() -> None:
    content = _content()
    assert "UNAUTH_PUBLIC_API_STATUS=YES" in content
    assert "Unauthenticated" in content


def test_phase26ar_no_turkey_legal_clearance_limitation() -> None:
    content = _content()
    assert "No Turkey" in content or "No Deribit documentation" in content or "NOT FOUND" in content


def test_phase26ar_public_data_geo_safe_harbor_limitation() -> None:
    assert "NO_EXPLICIT_PUBLIC_DATA_GEO_SAFE_HARBOR" in _content()


def test_phase26ar_unhashed_terms_and_llms_excluded_from_evidence() -> None:
    content = _content()
    assert "UNHASHED_TERMS_AND_LLMS_SOURCES_EXCLUDED_FROM_APPROVAL_EVIDENCE" in content
    assert "`DERIBIT_TERMS" not in content
    assert "`DERIBIT_DOCS_LLMS`" not in content
    assert "not use Terms or `llms.txt` as evidence" in content


def test_phase26ar_official_sources_are_manifest_rows() -> None:
    content = _content()
    manifest = MANIFEST_PATH.read_text(encoding="utf-8")
    for source_id in ("DERIBIT_RESTRICTED", "DERIBIT_ENVIRONMENT"):
        assert f"`{source_id}`" in content
        assert f"`{source_id}`" in manifest
    for excluded_source in ("DERIBIT_TERMS_PANAMA", "DERIBIT_TERMS_FZE", "DERIBIT_DOCS_LLMS"):
        assert f"`{excluded_source}`" not in content


def test_phase26ar_non_legal_advice_warning_present() -> None:
    content = _content()
    assert "NON-LEGAL-ADVICE" in content or "non-legal-advice" in content.lower()


def test_phase26ar_no_connector_enablement_claim() -> None:
    content = _content()
    assert "CAN_ENABLE_CONNECTOR_NOW=NO" in content
    assert "connector_ready_dialects" not in content or "changes" not in content


def test_phase26ar_no_private_api_claim() -> None:
    content = _content()
    assert "NO_LOGIN_NO_PRIVATE_API" in content


def test_phase26ar_can_approve_claim_row_now() -> None:
    assert "CAN_APPROVE_CLAIM_ROW_NOW=YES_WITH_OPERATOR_METADATA_AND_SCOPE_LIMITS" in _content()


def test_phase26ar_cannot_approve_policy_row_automatically() -> None:
    assert "CAN_APPROVE_POLICY_LEGAL_ROW_NOW=NO_AUTOMATIC_APPROVAL_OPERATOR_SIGNOFF_REQUIRED" in _content()
