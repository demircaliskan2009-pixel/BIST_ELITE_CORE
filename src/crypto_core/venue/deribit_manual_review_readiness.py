"""Phase 25B/25F — Deribit human-review worksheet validator.

Fail-closed deterministic validator for the three human-review surfaces that
gate Deribit B1-B5:
  1. Source Snapshot Manifest  (B2 — 6 source rows)
  2. Claim Review Worksheet    (B2 — 23 claim rows)
  3. Operational Policy Review Worksheet (B3 — 7 policy rows)

Phase separation:
  Phase 25 covers B2/B3 evidence review completion only.
  Connector enablement (B5) is a distinct PUBLIC_MARKET_DATA_ONLY phase that
  requires separate explicit authorization.

This module:
- approves source snapshot rows only when explicit acceptance metadata exists.
- does NOT change operational_status.
- does NOT enable connector_ready_dialects.
- does NOT read credentials, private API, or network.
- is read-only over committed documentation files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md")
CLAIM_WORKSHEET_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md")
POLICY_WORKSHEET_PATH = Path(
    "docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md"
)

_PENDING_SENTINEL = "PENDING"
_APPROVED_VALUE = "APPROVE"
_APPROVED_LEGACY = "APPROVED"
_REJECT_VALUE = "REJECT"
_REJECTED_LEGACY = "REJECTED"
_DEFER_VALUE = "DEFER"

# Minimum expected row counts per surface — enforces fail-closed on truncated worksheets.
_MANIFEST_EXPECTED_ROW_COUNT = 6
_CLAIM_EXPECTED_ROW_COUNT = 23
_POLICY_EXPECTED_ROW_COUNT = 7

# The separate_connector_enablement policy row must remain DEFER in Phase 25.
# It is NOT a failure for B2/B3 evidence review completion; connector enablement
# is a distinct PUBLIC_MARKET_DATA_ONLY phase requiring explicit authorization.
_CONNECTOR_ENABLEMENT_ROW_ID = "separate_connector_enablement"
_INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING = "INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING"
_INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_PATH = Path(
    "docs/crypto_core/DERIBIT_INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE.md"
)


# ---------------------------------------------------------------------------
# Typed result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeribitReviewRowResult:
    row_id: str
    surface: str  # "source_snapshot" | "claim_review" | "policy_review"
    status: str  # "PENDING" | "REVIEWED" | "APPROVED" | "REJECTED" | "DEFERRED" | "MISSING"
    missing_metadata: tuple[str, ...]
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class DeribitManualReviewReadinessResult:
    """Fail-closed result of the three Deribit human-review surfaces.

    Phase separation:
      evidence_review_complete — True when all B2/B3 source-snapshot, claim,
        and policy rows carry a non-PENDING/non-REJECTED human decision with
        required metadata, EXCLUDING the `separate_connector_enablement` policy
        row (exempt: must remain DEFERRED in Phase 25).

      ready_for_engineering_patch — True when evidence_review_complete is True.
        Signals that dialect policy values in public_feed_dialects.py may be
        updated. Does NOT enable connector readiness.

      connector_enablement_ready — True only after the separate
        PUBLIC_MARKET_DATA_ONLY connector enablement policy row is explicitly
                approved, independent human-origin approval provenance is present,
                and the Deribit static public dialect is connector-ready.

      accepted — True only when every row on every surface (including
        separate_connector_enablement) is non-PENDING, non-REJECTED, and
        non-DEFERRED.
    """

    accepted: bool
    evidence_review_complete: bool
    ready_for_engineering_patch: bool
    connector_enablement_ready: bool
    b1_b5_status: dict[str, str]  # e.g. {"B1": "BLOCKED", ...}
    missing_metadata: tuple[str, ...]
    pending_rows: tuple[str, ...]
    rejected_rows: tuple[str, ...]
    deferred_rows: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    row_results: tuple[DeribitReviewRowResult, ...]


# ---------------------------------------------------------------------------
# Internal markdown table parser
# ---------------------------------------------------------------------------


def _parse_md_table_rows(text: str) -> list[dict[str, str]]:
    """Parse a simple pipe-delimited markdown table into a list of dicts.

    Returns one dict per data row (skips header and separator rows).
    Column values are stripped of leading/trailing whitespace and backticks.
    """
    rows: list[dict[str, str]] = []
    header: list[str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.split("|")[1:-1]]
        if header is None:
            header = cells
            continue
        # Skip separator row (contains only dashes)
        if all(set(c.replace("-", "").replace(":", "")) == set() for c in cells):
            continue
        if len(cells) >= len(header):
            rows.append(dict(zip(header, cells)))
    return rows


def _is_pending(value: str) -> bool:
    return value.strip().upper() == _PENDING_SENTINEL


def _is_approved(value: str) -> bool:
    v = value.strip().upper()
    return v in (_APPROVED_VALUE, _APPROVED_LEGACY)


def _is_rejected(value: str) -> bool:
    v = value.strip().upper()
    return v in (_REJECT_VALUE, _REJECTED_LEGACY)


def _is_deferred(value: str) -> bool:
    return value.strip().upper() == _DEFER_VALUE


def _is_provided(value: str) -> bool:
    return bool(value.strip()) and not _is_pending(value)


def _independent_human_connector_approval_provenance_ready() -> bool:
    """Return True only when separate human-origin approval evidence exists."""
    if not _INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_PATH.exists():
        return False

    text = _INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_PATH.read_text(encoding="utf-8")
    required_markers = (
        "independent_human_origin: true",
        "decision: APPROVE",
        "approval_scope: Phase27F_PUBLIC_MARKET_DATA_ONLY_CONNECTOR_ENABLEMENT",
        "separate_from_ai_enablement_pr: true",
    )
    return all(marker in text for marker in required_markers)


# ---------------------------------------------------------------------------
# Per-surface validators
# ---------------------------------------------------------------------------


def _validate_manifest(manifest_text: str) -> list[DeribitReviewRowResult]:
    """Validate source snapshot manifest rows.

    Explicit acceptance metadata is required for APPROVED. REVIEWED_APPROVED
    retrieval_status alone is intentionally not sufficient.
    """
    rows = _parse_md_table_rows(manifest_text)
    results: list[DeribitReviewRowResult] = []

    for row in rows:
        source_id = row.get("source_id", "").strip().strip("`")
        if not source_id:
            continue

        missing: list[str] = []
        retrieval_status = row.get("retrieval_status", _PENDING_SENTINEL)
        acceptance_decision = row.get("acceptance_decision", _PENDING_SENTINEL)
        accepted_by = row.get("accepted_by", _PENDING_SENTINEL)
        accepted_at = row.get("accepted_at_iso", _PENDING_SENTINEL)
        acceptance_scope = row.get("acceptance_scope", _PENDING_SENTINEL)
        sha = row.get("content_sha256", "")
        if _is_pending(retrieval_status) or "PENDING" in retrieval_status.upper():
            missing.append(f"{source_id}:manual_review_pending")
        if not sha or _is_pending(sha):
            missing.append(f"{source_id}:content_sha256_missing")
        if missing:
            status = "PENDING"
            rr = tuple(missing)
        elif _is_rejected(acceptance_decision):
            status = "REJECTED"
            rr: tuple[str, ...] = (f"{source_id}:rejected",)
        elif _is_deferred(acceptance_decision):
            status = "DEFERRED"
            rr = (f"{source_id}:deferred",)
        elif _is_approved(acceptance_decision):
            for col, val in (
                ("accepted_by", accepted_by),
                ("accepted_at_iso", accepted_at),
                ("acceptance_scope", acceptance_scope),
            ):
                if not _is_provided(val):
                    missing.append(f"{source_id}:{col}_pending")
            if missing:
                status = "REVIEWED"
                rr = tuple(missing)
            else:
                status = "APPROVED"
                rr = ()
        else:
            status = "REVIEWED"
            rr = ()
        results.append(
            DeribitReviewRowResult(
                row_id=source_id,
                surface="source_snapshot",
                status=status,
                missing_metadata=tuple(missing),
                rejection_reasons=rr,
            )
        )

    return results


def _validate_claims(claim_text: str) -> list[DeribitReviewRowResult]:
    """Validate claim review worksheet rows.

    Each row must have non-PENDING reviewer_id, reviewed_at_iso, and decision.
    Missing metadata → PENDING. No expected-ID list is hardcoded here;
    expected-ID coverage is asserted in the test suite.
    """
    rows = _parse_md_table_rows(claim_text)
    results: list[DeribitReviewRowResult] = []

    for row in rows:
        claim_id = row.get("claim_id", "").strip().strip("`")
        if not claim_id:
            continue

        missing: list[str] = []
        decision = row.get("decision", _PENDING_SENTINEL)
        reviewer_id = row.get("reviewer_id", _PENDING_SENTINEL)
        reviewed_at = row.get("reviewed_at_iso", _PENDING_SENTINEL)

        for col, val in (
            ("reviewer_id", reviewer_id),
            ("reviewed_at_iso", reviewed_at),
            ("decision", decision),
        ):
            if _is_pending(val):
                missing.append(f"{claim_id}:{col}_pending")

        if _is_approved(decision) and not missing:
            status = "APPROVED"
            rr: tuple[str, ...] = ()
        elif _is_rejected(decision):
            status = "REJECTED"
            rr = tuple(missing) if missing else (f"{claim_id}:rejected",)
        elif _is_deferred(decision):
            status = "DEFERRED"
            rr = tuple(missing) if missing else (f"{claim_id}:deferred",)
        else:
            status = "PENDING"
            rr = tuple(missing)

        results.append(
            DeribitReviewRowResult(
                row_id=claim_id,
                surface="claim_review",
                status=status,
                missing_metadata=tuple(missing),
                rejection_reasons=rr,
            )
        )

    return results


def _validate_policies(policy_text: str) -> list[DeribitReviewRowResult]:
    """Validate operational policy review worksheet rows.

    Same metadata requirements as claim rows. No expected-ID list is
    hardcoded here; expected-ID coverage is asserted in the test suite.
    """
    rows = _parse_md_table_rows(policy_text)
    results: list[DeribitReviewRowResult] = []

    for row in rows:
        policy_id = row.get("policy_id", "").strip().strip("`")
        if not policy_id:
            continue

        missing: list[str] = []
        decision = row.get("decision", _PENDING_SENTINEL)
        reviewer_id = row.get("reviewer_id", _PENDING_SENTINEL)
        reviewed_at = row.get("reviewed_at_iso", _PENDING_SENTINEL)

        for col, val in (
            ("reviewer_id", reviewer_id),
            ("reviewed_at_iso", reviewed_at),
            ("decision", decision),
        ):
            if _is_pending(val):
                missing.append(f"{policy_id}:{col}_pending")

        if _is_approved(decision) and not missing:
            status = "APPROVED"
            rr: tuple[str, ...] = ()
        elif _is_rejected(decision):
            status = "REJECTED"
            rr = tuple(missing) if missing else (f"{policy_id}:rejected",)
        elif _is_deferred(decision):
            status = "DEFERRED"
            rr = tuple(missing) if missing else (f"{policy_id}:deferred",)
        else:
            status = "PENDING"
            rr = tuple(missing)

        results.append(
            DeribitReviewRowResult(
                row_id=policy_id,
                surface="policy_review",
                status=status,
                missing_metadata=tuple(missing),
                rejection_reasons=rr,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_deribit_manual_review_readiness(
    *,
    manifest_path: Path = MANIFEST_PATH,
    claim_worksheet_path: Path = CLAIM_WORKSHEET_PATH,
    policy_worksheet_path: Path = POLICY_WORKSHEET_PATH,
) -> DeribitManualReviewReadinessResult:
    """Parse and validate all three human-review worksheets.

    Fail-closed: returns accepted=False and ready_for_engineering_patch=False
    unless every row on every surface has an explicit non-PENDING human
    reviewer decision with all required metadata populated.

    This function is read-only. It does not edit any file, does not change
    operational_status, does not set static_registry_verified, and does not
    enable connector_ready_dialects.
    """
    all_row_results: list[DeribitReviewRowResult] = []
    load_errors: list[str] = []

    for path, loader, expected_count in (
        (manifest_path, _validate_manifest, _MANIFEST_EXPECTED_ROW_COUNT),
        (claim_worksheet_path, _validate_claims, _CLAIM_EXPECTED_ROW_COUNT),
        (policy_worksheet_path, _validate_policies, _POLICY_EXPECTED_ROW_COUNT),
    ):
        if not path.exists():
            load_errors.append(f"worksheet_missing:{path}")
            continue
        text = path.read_text(encoding="utf-8")
        surface_results = loader(text)
        if len(surface_results) < expected_count:
            load_errors.append(f"worksheet_truncated:{path}:expected_{expected_count}_got_{len(surface_results)}")
        all_row_results.extend(surface_results)

    # Aggregate across all rows
    missing_meta: list[str] = []
    pending_rows: list[str] = []
    rejected_rows: list[str] = []
    deferred_rows: list[str] = []
    all_rejection_reasons: list[str] = []

    for rr in all_row_results:
        if rr.missing_metadata:
            missing_meta.extend(rr.missing_metadata)
        if rr.status == "PENDING" or rr.status == "MISSING":
            pending_rows.append(f"{rr.surface}:{rr.row_id}")
        elif rr.status == "REJECTED":
            rejected_rows.append(f"{rr.surface}:{rr.row_id}")
        elif rr.status == "DEFERRED":
            deferred_rows.append(f"{rr.surface}:{rr.row_id}")
        all_rejection_reasons.extend(rr.rejection_reasons)

    all_rejection_reasons.extend(load_errors)

    # accepted only when zero pending, zero rejected, zero deferred, zero load
    # errors, and all expected rows were found
    accepted = (
        len(load_errors) == 0
        and len(pending_rows) == 0
        and len(rejected_rows) == 0
        and len(deferred_rows) == 0
        and len(missing_meta) == 0
    )

    # evidence_review_complete: same as accepted but exempts a still-deferred
    # separate_connector_enablement row until its dedicated B5 phase runs.
    _ce_deferred_key = f"policy_review:{_CONNECTOR_ENABLEMENT_ROW_ID}"
    other_deferred = [r for r in deferred_rows if r != _ce_deferred_key]
    evidence_review_complete = (
        len(load_errors) == 0
        and len(pending_rows) == 0
        and len(rejected_rows) == 0
        and len(other_deferred) == 0
        and len(missing_meta) == 0
    )

    static_registry_verified = _deribit_static_registry_verified()
    independent_human_provenance_ready = _independent_human_connector_approval_provenance_ready()
    if not independent_human_provenance_ready:
        all_rejection_reasons.append(_INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE_MISSING)

    connector_enablement_ready = (
        _deribit_connector_enablement_ready(
            all_row_results,
            static_registry_verified=static_registry_verified,
        )
        and independent_human_provenance_ready
    )

    # B1-B5 status map (coarse summary — engineering detail in row_results)
    b1_b5: dict[str, str] = {
        "B1": "BLOCKED",  # B1 gates on B2+B3+B4 — always blocked while those are blocked
        "B2": "BLOCKED"
        if any(rr.surface in ("source_snapshot", "claim_review") and rr.status != "APPROVED" for rr in all_row_results)
        else "READY",
        "B3": "BLOCKED"
        if any(
            rr.surface == "policy_review"
            and rr.status != "APPROVED"
            and not (rr.row_id == _CONNECTOR_ENABLEMENT_ROW_ID and rr.status == "DEFERRED")
            for rr in all_row_results
        )
        else "READY",
        "B4": "READY" if static_registry_verified else "BLOCKED",
        "B5": "READY" if connector_enablement_ready else "BLOCKED",
    }
    # B1 stays BLOCKED until B2, B3, B4 are each READY
    if b1_b5["B2"] == "READY" and b1_b5["B3"] == "READY" and b1_b5["B4"] == "READY":
        b1_b5["B1"] = "READY_FOR_HUMAN_GATE"
    else:
        b1_b5["B1"] = "BLOCKED"

    accepted = accepted and b1_b5["B1"] != "BLOCKED"

    return DeribitManualReviewReadinessResult(
        accepted=accepted,
        evidence_review_complete=evidence_review_complete,
        ready_for_engineering_patch=evidence_review_complete,
        connector_enablement_ready=connector_enablement_ready,
        b1_b5_status=b1_b5,
        missing_metadata=tuple(dict.fromkeys(missing_meta)),
        pending_rows=tuple(dict.fromkeys(pending_rows)),
        rejected_rows=tuple(rejected_rows),
        deferred_rows=tuple(deferred_rows),
        rejection_reasons=tuple(dict.fromkeys(all_rejection_reasons)),
        row_results=tuple(all_row_results),
    )


def _deribit_static_registry_verified() -> bool:
    """Return True only when Deribit static dialect policy fields are verified."""
    from crypto_core.data.public_feed_dialect import (
        FeedChecksumModel,
        FeedDialectVerificationStatus,
        FeedSequenceModel,
        public_feed_dialect_rejection_reasons,
    )
    from crypto_core.venue.contracts import VenueId
    from crypto_core.venue.public_feed_dialects import dialects_for_venue

    for spec in dialects_for_venue(VenueId.DERIBIT):
        if (
            spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS
            and spec.supports_delta_stream is True
            and spec.supports_checksum is False
            and spec.checksum_model is FeedChecksumModel.NONE
            and spec.sequence_model is FeedSequenceModel.SNAPSHOT_DELTA_RANGE
            and spec.requires_heartbeat is True
            and spec.supports_resync is True
            and spec.max_gap_tolerance == 0
            and spec.max_staleness_ns == 2_000_000_000
            and spec.max_receive_lag_ns == 1_000_000_000
            and bool(spec.official_doc_refs)
            and public_feed_dialect_rejection_reasons(spec) == ()
        ):
            return True
    return False


def _deribit_connector_enablement_ready(
    row_results: list[DeribitReviewRowResult],
    *,
    static_registry_verified: bool,
) -> bool:
    """Return True only for the approved Deribit public-market-data B5 gate."""
    from crypto_core.venue.contracts import VenueId
    from crypto_core.venue.public_feed_dialects import connector_ready_dialects

    if static_registry_verified is not True:
        return False

    connector_row = next(
        (row for row in row_results if row.surface == "policy_review" and row.row_id == _CONNECTOR_ENABLEMENT_ROW_ID),
        None,
    )
    if connector_row is None or connector_row.status != "APPROVED":
        return False

    ready_deribit_specs = tuple(spec for spec in connector_ready_dialects() if spec.venue_id is VenueId.DERIBIT)
    return len(ready_deribit_specs) == 1 and len(connector_ready_dialects()) == 1
