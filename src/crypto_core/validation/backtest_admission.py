"""Backtest admission gate — deterministic paper-only admissibility decision over a validation bundle.

A single, deterministic, fail-closed consumer that decides whether a strategy — already summarised by a
``StrategyValidationBundle`` — is admissible to replay/backtest. It is a *gate*, not an engine: it runs
no backtest, mirrors no StrategySpec/DataRequirement/PIT/LBR contract, and adds no runtime/persistence/
scheduler/execution/venue path. It derives its verdict solely from the bundle's already-computed status,
evidence digests, and paper-safety flags.

Design rules:
  - Consume the bundle only: the input must be a ``StrategyValidationBundle`` instance (never a mapping);
    a wrong-typed bundle or an invalid ``correlation_id`` / ``min_decision_records`` raises a typed error.
  - Admit narrowly: ADMITTED only when the bundle is ACCEPTED + accepted, paper-only with both real
    flags false, the bundle digest (and every evidence digest) is canonical 64-hex, there are at least
    ``min_decision_records`` decision records, and the optional source-packet requirement is satisfied.
  - Fail closed: any safety-flag breach, malformed digest, or BIST/live/order/scheduler leakage in an
    identity field forces REJECTED; a hard bundle rejection forces REJECTED; missing/insufficient
    evidence forces INSUFFICIENT_EVIDENCE; a NEEDS_RESEARCH bundle (absent hard rejection) propagates.
  - Deterministic: a canonical SHA-256 ``admission_digest`` over the material fields; no wall-clock/
    random/IO. Frozen dataclass; ``paper_only=True`` and no order/route/venue/scheduler field.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.strategy_validation_bundle import (
    StrategyValidationBundle,
    StrategyValidationBundleStatus,
)

_SCHEMA_VERSION = "backtest-admission.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

# Safely-detectable BIST markers and forbidden live/order/scheduler config tokens (word-bounded, matching
# the source-packet policy so "delivery"/"kappa"/"ideal" do not false-match but suffixed forms do).
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"\b(?:private_api|order_router|auto_loop|shadow_live_execution|credentials|scheduler)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)


class BacktestAdmissionError(RuntimeError):
    """Raised when admission inputs are malformed at the call level (wrong type / bad id or bound)."""


class BacktestAdmissionStatus(str, Enum):
    """Terminal admissibility verdict for replay/backtest. Never an order/live action."""

    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class BacktestAdmissionDecision:
    """Deterministic, immutable admissibility decision over a validation bundle. PAPER ONLY."""

    schema_version: str
    status: BacktestAdmissionStatus
    admitted: bool
    strategy_id: str
    strategy_digest: str
    bundle_status: str
    bundle_digest: str
    source_packet_digest: str | None
    decision_record_count: int
    min_decision_records: int
    require_source_packet: bool
    require_accepted_bundle: bool
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    correlation_id: str
    admission_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 1


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("backtest_admission:bist_scope_leakage")
        if _FORBIDDEN_PATTERN.search(text):
            reasons.append("backtest_admission:forbidden_scope_token")
    return tuple(reasons)


def build_backtest_admission_decision(
    bundle: StrategyValidationBundle,
    *,
    min_decision_records: int = 3,
    require_source_packet: bool = False,
    require_accepted_bundle: bool = True,
    correlation_id: str,
) -> BacktestAdmissionDecision:
    """Decide whether a strategy summarised by ``bundle`` is admissible to replay/backtest.

    ``bundle`` must be a ``StrategyValidationBundle`` instance. A wrong-typed bundle, an empty
    ``correlation_id``, a non-positive ``min_decision_records``, or non-boolean toggles raise
    ``BacktestAdmissionError``. ADMITTED requires an ACCEPTED + accepted, paper-only, digest-valid bundle
    with enough decision records and the optional source packet; every other outcome maps fail-closed to
    REJECTED / INSUFFICIENT_EVIDENCE / NEEDS_RESEARCH. The decision is deterministic and immutable.
    """
    if not isinstance(bundle, StrategyValidationBundle):
        raise BacktestAdmissionError("backtest_admission:bundle_malformed")
    if not _is_non_empty_string(correlation_id):
        raise BacktestAdmissionError("backtest_admission:correlation_id_invalid")
    if not _is_positive_int(min_decision_records):
        raise BacktestAdmissionError("backtest_admission:min_decision_records_invalid")
    if not isinstance(require_source_packet, bool) or not isinstance(require_accepted_bundle, bool):
        raise BacktestAdmissionError("backtest_admission:toggle_malformed")

    decision_record_count = len(bundle.decision_record_digests)

    hard: list[str] = []
    if not bundle.paper_only:
        hard.append("backtest_admission:not_paper_only")
    if bundle.real_orders_enabled:
        hard.append("backtest_admission:real_orders_enabled")
    if bundle.real_money_enabled:
        hard.append("backtest_admission:real_money_enabled")
    if not _is_sha256_hex(bundle.bundle_digest):
        hard.append("backtest_admission:bundle_digest_invalid")
    if any(not _is_sha256_hex(digest) for digest in bundle.decision_record_digests):
        hard.append("backtest_admission:decision_record_digest_invalid")
    if bundle.source_packet_digest is not None and not _is_sha256_hex(bundle.source_packet_digest):
        hard.append("backtest_admission:source_packet_digest_invalid")
    if require_accepted_bundle and bundle.status is StrategyValidationBundleStatus.ACCEPTED and not bundle.accepted:
        hard.append("backtest_admission:bundle_accepted_mismatch")
    hard.extend(_scope_violations(bundle.strategy_id, bundle.correlation_id, correlation_id))

    blocking: list[str] = list(hard)
    needs: list[str] = []

    if bundle.status is StrategyValidationBundleStatus.REJECTED:
        blocking.append("backtest_admission:bundle_rejected")
        blocking.extend(bundle.terminal_rejection_reasons)
    elif bundle.status is StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE:
        blocking.append("backtest_admission:bundle_insufficient_evidence")
    elif bundle.status is StrategyValidationBundleStatus.NEEDS_RESEARCH:
        needs.append("backtest_admission:bundle_needs_research")
        needs.extend(bundle.terminal_needs_research_reasons)

    insufficient_records = decision_record_count < min_decision_records
    if insufficient_records:
        blocking.append("backtest_admission:insufficient_decision_records")
    missing_source_packet = require_source_packet and not bundle.source_packet_digest
    if missing_source_packet:
        blocking.append("backtest_admission:source_packet_required")

    has_hard = bool(hard) or bundle.status is StrategyValidationBundleStatus.REJECTED
    insufficient = (
        insufficient_records
        or missing_source_packet
        or bundle.status is StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE
    )
    admitted_ok = (
        bundle.status is StrategyValidationBundleStatus.ACCEPTED
        and (bundle.accepted or not require_accepted_bundle)
        and bundle.paper_only
        and not bundle.real_orders_enabled
        and not bundle.real_money_enabled
        and _is_sha256_hex(bundle.bundle_digest)
        and decision_record_count >= min_decision_records
        and (not require_source_packet or bool(bundle.source_packet_digest))
        and not hard
    )

    if has_hard:
        status = BacktestAdmissionStatus.REJECTED
    elif insufficient:
        status = BacktestAdmissionStatus.INSUFFICIENT_EVIDENCE
    elif bundle.status is StrategyValidationBundleStatus.NEEDS_RESEARCH:
        status = BacktestAdmissionStatus.NEEDS_RESEARCH
    elif admitted_ok:
        status = BacktestAdmissionStatus.ADMITTED
    else:
        status = BacktestAdmissionStatus.INSUFFICIENT_EVIDENCE

    return _assemble(
        status=status,
        bundle=bundle,
        decision_record_count=decision_record_count,
        min_decision_records=min_decision_records,
        require_source_packet=require_source_packet,
        require_accepted_bundle=require_accepted_bundle,
        rejection_reasons=_sorted_unique(tuple(blocking)),
        needs_research_reasons=_sorted_unique(tuple(needs)),
        correlation_id=correlation_id,
    )


def _assemble(
    *,
    status: BacktestAdmissionStatus,
    bundle: StrategyValidationBundle,
    decision_record_count: int,
    min_decision_records: int,
    require_source_packet: bool,
    require_accepted_bundle: bool,
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
    correlation_id: str,
) -> BacktestAdmissionDecision:
    admitted = status is BacktestAdmissionStatus.ADMITTED
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "admitted": admitted,
        "strategy_id": bundle.strategy_id,
        "strategy_digest": bundle.strategy_digest,
        "bundle_status": bundle.status.value,
        "bundle_digest": bundle.bundle_digest,
        "source_packet_digest": bundle.source_packet_digest,
        "decision_record_count": decision_record_count,
        "min_decision_records": min_decision_records,
        "require_source_packet": require_source_packet,
        "require_accepted_bundle": require_accepted_bundle,
        "rejection_reasons": list(rejection_reasons),
        "needs_research_reasons": list(needs_research_reasons),
        "correlation_id": correlation_id,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return BacktestAdmissionDecision(
        schema_version=_SCHEMA_VERSION,
        status=status,
        admitted=admitted,
        strategy_id=bundle.strategy_id,
        strategy_digest=bundle.strategy_digest,
        bundle_status=bundle.status.value,
        bundle_digest=bundle.bundle_digest,
        source_packet_digest=bundle.source_packet_digest,
        decision_record_count=decision_record_count,
        min_decision_records=min_decision_records,
        require_source_packet=require_source_packet,
        require_accepted_bundle=require_accepted_bundle,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        admission_digest=_canonical_digest(payload),
    )


def backtest_admission_decision_to_dict(decision: BacktestAdmissionDecision) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a backtest admission decision (deterministic shape)."""
    return {
        "schema_version": decision.schema_version,
        "status": decision.status.value,
        "admitted": decision.admitted,
        "strategy_id": decision.strategy_id,
        "strategy_digest": decision.strategy_digest,
        "bundle_status": decision.bundle_status,
        "bundle_digest": decision.bundle_digest,
        "source_packet_digest": decision.source_packet_digest,
        "decision_record_count": decision.decision_record_count,
        "min_decision_records": decision.min_decision_records,
        "require_source_packet": decision.require_source_packet,
        "require_accepted_bundle": decision.require_accepted_bundle,
        "rejection_reasons": list(decision.rejection_reasons),
        "needs_research_reasons": list(decision.needs_research_reasons),
        "correlation_id": decision.correlation_id,
        "admission_digest": decision.admission_digest,
        "paper_only": decision.paper_only,
        "real_orders_enabled": decision.real_orders_enabled,
        "real_money_enabled": decision.real_money_enabled,
    }


__all__ = [
    "BacktestAdmissionDecision",
    "BacktestAdmissionError",
    "BacktestAdmissionStatus",
    "backtest_admission_decision_to_dict",
    "build_backtest_admission_decision",
]
