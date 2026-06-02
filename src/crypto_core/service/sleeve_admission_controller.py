"""Crypto sleeve admission controller and models — Phase 15F.

Deterministic, serialization-friendly controller for managed sleeve admission gating.

Design rules:
  - Uses only existing sleeve promotion review, readiness, escalation, and governance truth.
  - No new promotion engine, ranking, or allocation logic.
  - Bounded finalized history only; malformed persisted state fails closed.
  - PAPER-ONLY.

PRD reference: §2 System Orchestration, §7 Execution Engine, Phase 15F.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreCorruptError, WriteResult
from crypto_core.service.promotion_review import PromotionReviewEvidencePrecheck
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewPortfolioSummary,
    SleevePromotionReviewResult,
    SleevePromotionReviewVerdict,
)


class SleeveAdmissionVerdict(str, Enum):
    ADMITTED_ACTIVE = "admitted_active"
    ADMITTED_UNALLOCATED = "admitted_unallocated"
    REVIEW_SUPPORTED_NOT_ADMITTED = "review_supported_not_admitted"
    NOT_ADMITTED_BLOCKED = "not_admitted_blocked"
    NOT_ADMITTED_INCONCLUSIVE = "not_admitted_inconclusive"


class PaperShadowActivationStatus(str, Enum):
    READY_FOR_PAPER_SHADOW = "ready_for_paper_shadow"
    BLOCKED = "blocked"


class PaperShadowSourceManifestStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PaperShadowActivationPlan:
    plan_id: str
    activation_status: PaperShadowActivationStatus
    source_manifest_status: PaperShadowSourceManifestStatus
    active_sleeves: tuple[str, ...] = ()
    inactive_sleeves: tuple[str, ...] = ()
    admitted_unallocated_sleeves: tuple[str, ...] = ()
    activation_blockers: tuple[str, ...] = ()
    evidence_blockers: tuple[str, ...] = ()
    governance_blockers: tuple[str, ...] = ()
    pbo_allocation_caps: tuple[tuple[str, float], ...] = ()
    operator_summary: str = ""
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


@dataclass(frozen=True)
class SleeveAdmissionResult:
    sleeve_id: str
    verdict: SleeveAdmissionVerdict
    reason: str
    next_step: str
    governance_blockers: tuple[str, ...] = ()
    evidence_blockers: tuple[str, ...] = ()
    last_review_verdict: SleevePromotionReviewVerdict | None = None
    pbo_allocation_cap: float | None = None


@dataclass(frozen=True)
class SleeveAdmissionPortfolioSummary:
    as_of_ns: int
    admission_results: tuple[SleeveAdmissionResult, ...]
    admitted_active: tuple[str, ...]
    admitted_unallocated: tuple[str, ...]
    review_supported_not_admitted: tuple[str, ...]
    blocked: tuple[str, ...]
    inconclusive: tuple[str, ...]
    governance_blockers: tuple[str, ...]
    evidence_blockers: tuple[str, ...]
    operator_summary: str


@dataclass(frozen=True)
class SleeveAdmissionHistoryEntry:
    as_of_ns: int
    summary: str
    portfolio_summary: SleeveAdmissionPortfolioSummary


@dataclass(frozen=True)
class SleeveAdmissionSnapshot:
    as_of_ns: int
    status: str
    admission_results: tuple[SleeveAdmissionResult, ...]
    portfolio_summary: SleeveAdmissionPortfolioSummary
    history: tuple[SleeveAdmissionHistoryEntry, ...] = ()


def sleeve_admission_result_to_dict(result: SleeveAdmissionResult) -> dict:
    """Serialize SleeveAdmissionResult to a JSON-safe dict."""
    return {
        "sleeve_id": result.sleeve_id,
        "verdict": result.verdict.value if isinstance(result.verdict, Enum) else str(result.verdict),
        "reason": result.reason,
        "next_step": result.next_step,
        "governance_blockers": list(result.governance_blockers),
        "evidence_blockers": list(result.evidence_blockers),
        "last_review_verdict": (
            result.last_review_verdict.value
            if isinstance(result.last_review_verdict, Enum)
            else result.last_review_verdict
        ),
        "pbo_allocation_cap": result.pbo_allocation_cap,
    }


def sleeve_admission_portfolio_summary_to_dict(summary: SleeveAdmissionPortfolioSummary) -> dict:
    """Serialize SleeveAdmissionPortfolioSummary to a JSON-safe dict."""
    return {
        "as_of_ns": summary.as_of_ns,
        "admission_results": [sleeve_admission_result_to_dict(result) for result in summary.admission_results],
        "admitted_active": list(summary.admitted_active),
        "admitted_unallocated": list(summary.admitted_unallocated),
        "review_supported_not_admitted": list(summary.review_supported_not_admitted),
        "blocked": list(summary.blocked),
        "inconclusive": list(summary.inconclusive),
        "governance_blockers": list(summary.governance_blockers),
        "evidence_blockers": list(summary.evidence_blockers),
        "operator_summary": summary.operator_summary,
    }


def sleeve_admission_history_entry_to_dict(entry: SleeveAdmissionHistoryEntry) -> dict:
    """Serialize SleeveAdmissionHistoryEntry to a JSON-safe dict."""
    return {
        "as_of_ns": entry.as_of_ns,
        "summary": entry.summary,
        "portfolio_summary": sleeve_admission_portfolio_summary_to_dict(entry.portfolio_summary),
    }


def sleeve_admission_snapshot_to_dict(snapshot: SleeveAdmissionSnapshot) -> dict:
    """Serialize SleeveAdmissionSnapshot to a JSON-safe dict."""
    return {
        "as_of_ns": snapshot.as_of_ns,
        "status": snapshot.status,
        "admission_results": [sleeve_admission_result_to_dict(result) for result in snapshot.admission_results],
        "portfolio_summary": sleeve_admission_portfolio_summary_to_dict(snapshot.portfolio_summary),
        "history": [sleeve_admission_history_entry_to_dict(entry) for entry in snapshot.history],
    }


class SleeveAdmissionCorruptError(RuntimeError):
    pass


_PROMOTION_EVIDENCE_MISSING = "promotion_review_evidence:precheck_missing"


def paper_shadow_activation_plan_to_dict(plan: PaperShadowActivationPlan) -> dict:
    """Serialize PaperShadowActivationPlan to a JSON-safe dict."""
    _validate_paper_shadow_activation_plan(plan)
    return {
        "plan_id": plan.plan_id,
        "activation_status": plan.activation_status.value,
        "source_manifest_status": plan.source_manifest_status.value,
        "active_sleeves": list(plan.active_sleeves),
        "inactive_sleeves": list(plan.inactive_sleeves),
        "admitted_unallocated_sleeves": list(plan.admitted_unallocated_sleeves),
        "activation_blockers": list(plan.activation_blockers),
        "evidence_blockers": list(plan.evidence_blockers),
        "governance_blockers": list(plan.governance_blockers),
        "pbo_allocation_caps": [[sleeve_id, cap] for sleeve_id, cap in plan.pbo_allocation_caps],
        "operator_summary": plan.operator_summary,
        "paper_only": plan.paper_only,
        "real_orders_enabled": plan.real_orders_enabled,
        "real_money_enabled": plan.real_money_enabled,
    }


def _validate_paper_shadow_activation_plan(plan: PaperShadowActivationPlan) -> None:
    if not isinstance(plan, PaperShadowActivationPlan):
        raise SleeveAdmissionCorruptError("paper_shadow_activation_plan_malformed")
    _require_non_empty_text(plan.plan_id, "plan_id")
    if not isinstance(plan.activation_status, PaperShadowActivationStatus):
        raise SleeveAdmissionCorruptError("paper_shadow_activation_status_malformed")
    if not isinstance(plan.source_manifest_status, PaperShadowSourceManifestStatus):
        raise SleeveAdmissionCorruptError("paper_shadow_source_manifest_status_malformed")
    for field_name in (
        "active_sleeves",
        "inactive_sleeves",
        "admitted_unallocated_sleeves",
        "activation_blockers",
        "evidence_blockers",
        "governance_blockers",
    ):
        _require_text_tuple(getattr(plan, field_name), field_name)
    _require_pbo_allocation_caps(plan.pbo_allocation_caps)
    _require_text(plan.operator_summary, "operator_summary")
    for field_name in ("paper_only", "real_orders_enabled", "real_money_enabled"):
        if not isinstance(getattr(plan, field_name), bool):
            raise SleeveAdmissionCorruptError(f"{field_name}_malformed")


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise SleeveAdmissionCorruptError(f"{field_name}_missing")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise SleeveAdmissionCorruptError(f"{field_name}_malformed")


def _require_text_tuple(value: tuple[str, ...], field_name: str) -> None:
    if not isinstance(value, tuple):
        raise SleeveAdmissionCorruptError(f"{field_name}_malformed")
    for item in value:
        if not isinstance(item, str) or not item:
            raise SleeveAdmissionCorruptError(f"{field_name}_malformed")


def _require_pbo_allocation_caps(value: tuple[tuple[str, float], ...]) -> None:
    if not isinstance(value, tuple):
        raise SleeveAdmissionCorruptError("pbo_allocation_caps_malformed")
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise SleeveAdmissionCorruptError("pbo_allocation_caps_malformed")
        sleeve_id, cap = item
        if not isinstance(sleeve_id, str) or not sleeve_id:
            raise SleeveAdmissionCorruptError("pbo_allocation_caps_malformed")
        if isinstance(cap, bool) or not isinstance(cap, (int, float)) or not math.isfinite(cap) or cap < 0.0:
            raise SleeveAdmissionCorruptError("pbo_allocation_caps_malformed")


class SleeveAdmissionController:
    """Managed controller for crypto sleeve admission gating."""

    def __init__(
        self,
        review_portfolio_summary: SleevePromotionReviewPortfolioSummary,
        history_limit: int = 5,
        promotion_evidence_precheck: PromotionReviewEvidencePrecheck | None = None,
    ):
        self.review_portfolio_summary = review_portfolio_summary
        self.history_limit = history_limit
        self.promotion_evidence_precheck = promotion_evidence_precheck
        self.history = []
        self._validate()

    def _validate(self):
        if not self.review_portfolio_summary or not hasattr(self.review_portfolio_summary, "review_results"):
            raise SleeveAdmissionCorruptError("Malformed review portfolio summary.")

    def build_admission_results(self) -> tuple[SleeveAdmissionResult, ...]:
        results = []
        for review in getattr(self.review_portfolio_summary, "review_results", []):
            promotion_evidence_blockers = self._promotion_evidence_blockers(review)
            evidence_blockers = self._evidence_blockers(review, promotion_evidence_blockers)
            verdict, reason, next_step = self._derive_verdict(review, evidence_blockers, promotion_evidence_blockers)
            results.append(
                SleeveAdmissionResult(
                    sleeve_id=review.sleeve_id,
                    verdict=verdict,
                    reason=reason,
                    next_step=next_step,
                    governance_blockers=review.governance_blockers,
                    evidence_blockers=evidence_blockers,
                    last_review_verdict=review.verdict,
                    pbo_allocation_cap=review.pbo_allocation_cap,
                )
            )
        return tuple(results)

    def _derive_verdict(
        self,
        review: SleevePromotionReviewResult,
        evidence_blockers: tuple[str, ...],
        promotion_evidence_blockers: tuple[str, ...],
    ):
        # Deterministic mapping from review verdict and blockers to admission verdict
        if review.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED and promotion_evidence_blockers:
            return (
                SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED,
                "Review supported but promotion evidence blocked.",
                "Persist canonical accepted promotion review evidence.",
            )
        if (
            review.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED
            and not review.governance_blockers
            and not evidence_blockers
        ):
            return (
                SleeveAdmissionVerdict.ADMITTED_ACTIVE,
                "Admitted and active.",
                "Monitor allocation and governance.",
            )
        if (
            review.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED
            and not review.governance_blockers
            and evidence_blockers
        ):
            return (
                SleeveAdmissionVerdict.ADMITTED_UNALLOCATED,
                "Admitted but unallocated due to missing evidence.",
                "Complete evidence for allocation.",
            )
        if review.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED and review.governance_blockers:
            return (
                SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED,
                "Review supported but governance blocked.",
                "Resolve governance blockers.",
            )
        if review.verdict == SleevePromotionReviewVerdict.HOLD:
            return (SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED, "Not admitted: hold verdict.", "Address hold reasons.")
        if review.verdict == SleevePromotionReviewVerdict.REJECT:
            return (
                SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED,
                "Not admitted: rejected.",
                "Review rejection rationale.",
            )
        if review.verdict == SleevePromotionReviewVerdict.INCONCLUSIVE:
            return (
                SleeveAdmissionVerdict.NOT_ADMITTED_INCONCLUSIVE,
                "Not admitted: inconclusive.",
                "Gather more evidence.",
            )
        return (
            SleeveAdmissionVerdict.NOT_ADMITTED_INCONCLUSIVE,
            "Not admitted: unknown state.",
            "Investigate admission logic.",
        )

    def _evidence_blockers(
        self,
        review: SleevePromotionReviewResult,
        promotion_evidence_blockers: tuple[str, ...],
    ) -> tuple[str, ...]:
        return _stable_ordered_unique(review.missing_evidence + promotion_evidence_blockers)

    def _promotion_evidence_blockers(self, review: SleevePromotionReviewResult) -> tuple[str, ...]:
        if review.verdict != SleevePromotionReviewVerdict.REVIEW_SUPPORTED:
            return ()
        if self.promotion_evidence_precheck is None:
            return ()
        if self.promotion_evidence_precheck.accepted:
            return ()
        return self.promotion_evidence_precheck.rejection_reasons or (_PROMOTION_EVIDENCE_MISSING,)

    def build_portfolio_summary(self) -> SleeveAdmissionPortfolioSummary:
        results = self.build_admission_results()
        admitted_active = tuple(r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE)
        admitted_unallocated = tuple(
            r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
        )
        review_supported_not_admitted = tuple(
            r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED
        )
        blocked = tuple(r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED)
        inconclusive = tuple(
            r.sleeve_id for r in results if r.verdict == SleeveAdmissionVerdict.NOT_ADMITTED_INCONCLUSIVE
        )
        governance_blockers = tuple(sorted({b for r in results for b in r.governance_blockers}))
        evidence_blockers = tuple(sorted({b for r in results for b in r.evidence_blockers}))
        operator_summary = f"Admitted: {len(admitted_active)}, Unallocated: {len(admitted_unallocated)}, Supported/Blocked: {len(review_supported_not_admitted)}, Blocked: {len(blocked)}, Inconclusive: {len(inconclusive)}"
        return SleeveAdmissionPortfolioSummary(
            as_of_ns=int(time.time_ns()),
            admission_results=results,
            admitted_active=admitted_active,
            admitted_unallocated=admitted_unallocated,
            review_supported_not_admitted=review_supported_not_admitted,
            blocked=blocked,
            inconclusive=inconclusive,
            governance_blockers=governance_blockers,
            evidence_blockers=evidence_blockers,
            operator_summary=operator_summary,
        )

    def snapshot(self, status: str = "active") -> SleeveAdmissionSnapshot:
        summary = self.build_portfolio_summary()
        history = tuple(self.history[-self.history_limit :])
        entry = SleeveAdmissionHistoryEntry(
            as_of_ns=summary.as_of_ns,
            summary=summary.operator_summary,
            portfolio_summary=summary,
        )
        history = history + (entry,)
        return SleeveAdmissionSnapshot(
            as_of_ns=summary.as_of_ns,
            status=status,
            admission_results=summary.admission_results,
            portfolio_summary=summary,
            history=history,
        )


def _stable_ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


# ---------------------------------------------------------------------------
# Sleeve admission outcome evidence (canonical digest + currentness)
# ---------------------------------------------------------------------------
#
# Mirrors the promotion_review evidence pattern. The digest binds deterministic
# semantic admission outcome facts only; the wall-clock ``as_of_ns`` snapshot
# metadata is excluded so the same outcome at different times proves identical.

_SLEEVE_ADMISSION_SNAPSHOT_NAME = "sleeve_admission"
_SLEEVE_ADMISSION_EVIDENCE_TYPE = "sleeve_admission"
_SLEEVE_ADMISSION_PAYLOAD_TYPE = "sleeve_admission"
_SLEEVE_ADMISSION_PAYLOAD_SCHEMA_VERSION = "1"
_SLEEVE_ADMISSION_DIGEST_EXCLUDED_FIELDS = frozenset({"as_of_ns"})
_SLEEVE_ADMISSION_OUTCOME_REQUIRED_FIELDS = frozenset({"admission_results", "admitted_active", "admitted_unallocated"})
_SLEEVE_ADMISSION_CANONICAL_FIELDS = frozenset(
    {"schema_version", "payload_type", "evidence_digest", "sleeve_admission"}
)


@dataclass(frozen=True)
class SleeveAdmissionEvidencePrecheck:
    """Read-only proof that the latest persisted sleeve admission outcome is current and admitted."""

    accepted: bool
    rejection_reasons: tuple[str, ...] = ()
    evidence_digest: str | None = None
    admitted_active: tuple[str, ...] = ()
    admitted_unallocated: tuple[str, ...] = ()


def sleeve_admission_outcome_to_dict(summary: SleeveAdmissionPortfolioSummary) -> dict:
    """Domain outcome payload for a sleeve admission portfolio summary."""
    if not isinstance(summary, SleeveAdmissionPortfolioSummary):
        raise ValueError("sleeve_admission:summary_malformed")
    return sleeve_admission_portfolio_summary_to_dict(summary)


def sleeve_admission_digest(summary: SleeveAdmissionPortfolioSummary) -> str:
    """Canonical digest over deterministic sleeve admission outcome facts (excludes as_of_ns)."""
    return _sleeve_admission_payload_digest(sleeve_admission_outcome_to_dict(summary))


def sleeve_admission_to_evidence_payload(summary: SleeveAdmissionPortfolioSummary) -> dict[str, Any]:
    """Convert a sleeve admission portfolio summary into a digest-bound evidence payload."""
    outcome_payload = sleeve_admission_outcome_to_dict(summary)
    evidence_digest = _sleeve_admission_payload_digest(outcome_payload)
    return {
        "schema_version": _SLEEVE_ADMISSION_PAYLOAD_SCHEMA_VERSION,
        "payload_type": _SLEEVE_ADMISSION_PAYLOAD_TYPE,
        "evidence_digest": evidence_digest,
        "sleeve_admission": outcome_payload,
        "as_of_ns": outcome_payload.get("as_of_ns"),
        "admitted_active": list(outcome_payload.get("admitted_active", [])),
        "admitted_unallocated": list(outcome_payload.get("admitted_unallocated", [])),
    }


def validate_sleeve_admission_evidence_payload(payload: object) -> dict[str, Any]:
    """Validate a sleeve admission evidence payload and recompute its current digest."""
    if not isinstance(payload, Mapping):
        raise ValueError("sleeve_admission:evidence_payload_malformed")
    missing = _SLEEVE_ADMISSION_CANONICAL_FIELDS - set(payload)
    if missing:
        raise ValueError(f"sleeve_admission:evidence_payload_missing:{','.join(sorted(missing))}")
    if payload["schema_version"] != _SLEEVE_ADMISSION_PAYLOAD_SCHEMA_VERSION:
        raise ValueError("sleeve_admission:schema_version_unknown")
    if payload["payload_type"] != _SLEEVE_ADMISSION_PAYLOAD_TYPE:
        raise ValueError("sleeve_admission:payload_type_wrong")
    evidence_digest = payload["evidence_digest"]
    if not isinstance(evidence_digest, str) or not evidence_digest:
        raise ValueError("sleeve_admission:evidence_digest_malformed")
    outcome_payload = payload["sleeve_admission"]
    if not isinstance(outcome_payload, Mapping):
        raise ValueError("sleeve_admission:outcome_payload_malformed")
    expected_digest = _sleeve_admission_payload_digest(outcome_payload)
    if evidence_digest != expected_digest:
        raise ValueError("sleeve_admission:evidence_digest_mismatch")
    return dict(payload)


def is_legacy_sleeve_admission_evidence_payload(payload: object) -> bool:
    """True for a digestless sleeve admission outcome payload (no currentness proof)."""
    if not isinstance(payload, Mapping):
        return False
    if _SLEEVE_ADMISSION_CANONICAL_FIELDS & set(payload):
        return False
    try:
        _validate_sleeve_admission_outcome_payload(payload)
    except ValueError:
        return False
    return True


def current_sleeve_admission_evidence_precheck(
    evidence_store: EvidenceStore | None,
) -> SleeveAdmissionEvidencePrecheck:
    """Validate persisted canonical current sleeve admission outcome evidence (fail-closed)."""
    if evidence_store is None:
        return _sleeve_admission_evidence_rejected("sleeve_admission_evidence:evidence_store_missing")

    try:
        snapshot_payload = _load_sleeve_admission_snapshot(evidence_store)
        expected_digest = _sleeve_admission_payload_digest(snapshot_payload)
        legacy_seen = False
        matches: list[dict[str, Any]] = []
        for record in evidence_store.load_evidence():
            if record.get("evidence_type") != _SLEEVE_ADMISSION_EVIDENCE_TYPE:
                continue
            payload = record.get("data")
            if is_legacy_sleeve_admission_evidence_payload(payload):
                legacy_seen = True
                continue
            validated = validate_sleeve_admission_evidence_payload(payload)
            if validated["evidence_digest"] == expected_digest:
                matches.append(validated)
    except (EvidenceStoreCorruptError, ValueError):
        return _sleeve_admission_evidence_rejected("sleeve_admission_evidence:store_or_payload_malformed")

    if not matches and legacy_seen:
        return _sleeve_admission_evidence_rejected(
            "sleeve_admission_evidence:legacy_digestless_not_currentness_provable"
        )
    if not matches:
        return _sleeve_admission_evidence_rejected("sleeve_admission_evidence:currentness_missing")
    if len(matches) > 1:
        return _sleeve_admission_evidence_rejected("sleeve_admission_evidence:currentness_ambiguous")

    evidence_payload = matches[0]
    outcome_payload = evidence_payload["sleeve_admission"]
    admitted_active = _sleeve_admission_string_tuple(outcome_payload.get("admitted_active"))
    admitted_unallocated = _sleeve_admission_string_tuple(outcome_payload.get("admitted_unallocated"))
    if not admitted_active and not admitted_unallocated:
        return _sleeve_admission_evidence_rejected(
            "sleeve_admission_evidence:not_admitted",
            evidence_digest=str(evidence_payload["evidence_digest"]),
        )

    return SleeveAdmissionEvidencePrecheck(
        accepted=True,
        rejection_reasons=(),
        evidence_digest=str(evidence_payload["evidence_digest"]),
        admitted_active=admitted_active,
        admitted_unallocated=admitted_unallocated,
    )


def _sleeve_admission_evidence_rejected(
    reason: str,
    *,
    evidence_digest: str | None = None,
    admitted_active: tuple[str, ...] = (),
    admitted_unallocated: tuple[str, ...] = (),
) -> SleeveAdmissionEvidencePrecheck:
    return SleeveAdmissionEvidencePrecheck(
        accepted=False,
        rejection_reasons=(reason,),
        evidence_digest=evidence_digest,
        admitted_active=admitted_active,
        admitted_unallocated=admitted_unallocated,
    )


def _load_sleeve_admission_snapshot(evidence_store: EvidenceStore) -> dict:
    envelope = evidence_store.load_snapshot(_SLEEVE_ADMISSION_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise ValueError("sleeve_admission:snapshot_data_malformed")
    _validate_sleeve_admission_outcome_payload(data)
    return data


def _sleeve_admission_payload_digest(outcome_payload: Mapping[str, Any]) -> str:
    _validate_sleeve_admission_outcome_payload(outcome_payload)
    semantic = {
        key: value for key, value in outcome_payload.items() if key not in _SLEEVE_ADMISSION_DIGEST_EXCLUDED_FIELDS
    }
    canonical = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_sleeve_admission_outcome_payload(outcome_payload: Mapping[str, Any]) -> None:
    if not isinstance(outcome_payload, Mapping):
        raise ValueError("sleeve_admission:outcome_payload_malformed")
    missing = _SLEEVE_ADMISSION_OUTCOME_REQUIRED_FIELDS - set(outcome_payload)
    if missing:
        raise ValueError(f"sleeve_admission:outcome_payload_missing:{','.join(sorted(missing))}")
    for field_name in ("admission_results", "admitted_active", "admitted_unallocated"):
        if not isinstance(outcome_payload[field_name], list):
            raise ValueError(f"sleeve_admission:{field_name}_malformed")


def _sleeve_admission_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


class SleeveAdmissionStore:
    """Persistent store for sleeve admission outcome evidence.

    Mirrors PromotionReviewStore: an atomic snapshot for the current outcome plus a
    digest-bound JSONL evidence record. Fail-closed: malformed/duplicate → reject.
    """

    def __init__(self, evidence_store: EvidenceStore) -> None:
        self._store = evidence_store

    def save_outcome(self, summary: SleeveAdmissionPortfolioSummary) -> WriteResult:
        """Persist a sleeve admission outcome as an atomic snapshot + evidence log entry.

        Idempotent for recurring semantic outcomes: if the same digest already exists in
        the evidence log (e.g. A→B→A), the snapshot is updated to the current outcome and
        the duplicate JSONL append is skipped. The currentness precheck still rejects a log
        that somehow contains more than one canonical record for the current digest.
        """
        try:
            evidence_payload = sleeve_admission_to_evidence_payload(summary)
            evidence_digest = evidence_payload["evidence_digest"]
            digest_exists = self._sleeve_admission_digest_exists(evidence_digest)
        except (EvidenceStoreCorruptError, ValueError) as exc:
            return WriteResult(
                success=False,
                error=f"Sleeve admission evidence state invalid: {exc}",
                path=str(self._store.evidence_log_path),
            )
        # Always write the snapshot so it reflects the current outcome.
        result = self._store.save_snapshot(_SLEEVE_ADMISSION_SNAPSHOT_NAME, evidence_payload["sleeve_admission"])
        if not result.success:
            return result
        if digest_exists:
            # Recurring outcome: snapshot updated; skip duplicate JSONL append.
            return result
        evidence_result = self._store.append_evidence(_SLEEVE_ADMISSION_EVIDENCE_TYPE, evidence_payload)
        if not evidence_result.success:
            return evidence_result
        return result

    def _sleeve_admission_digest_exists(self, evidence_digest: object) -> bool:
        if not isinstance(evidence_digest, str) or not evidence_digest:
            raise ValueError("sleeve_admission:evidence_digest_malformed")
        for record in self._store.load_evidence():
            if record.get("evidence_type") != _SLEEVE_ADMISSION_EVIDENCE_TYPE:
                continue
            payload = record.get("data")
            if is_legacy_sleeve_admission_evidence_payload(payload):
                continue
            validated = validate_sleeve_admission_evidence_payload(payload)
            if validated["evidence_digest"] == evidence_digest:
                return True
        return False
