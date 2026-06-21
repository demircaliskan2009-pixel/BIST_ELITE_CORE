"""Paper evidence admission record — deterministic, paper-only admission decision over a READY realized-PnL
evidence manifest.

A small, immutable, fail-closed *admission record* that decides whether a ``PaperSessionRealizedPnlEvidenceManifest``
(the artifact merged in PR #288) is admissible into the paper/backtest evidence pipeline. It is a *gate /
consumer*, not an engine: it runs no backtest, recomputes no fills/positions/realized PnL, reconstructs no
aggregate/bridge/rollup, and adds no runtime/persistence/scheduler/execution/venue path. It derives its
verdict solely from the manifest's already-proven status, digest, and paper-safety attestations.

Single canonical snapshot + independent expected digest: the supplied manifest is serialized EXACTLY ONCE via
the PUBLIC ``paper_session_realized_pnl_evidence_manifest_to_dict`` and ROUND-TRIPPED through canonical JSON
into exact plain primitives (plain ``str``/builtins — no ``str`` subclass with custom hash/equality). The
manifest self-digest is recomputed FROM that single snapshot (the SAME digest contract as the PUBLIC
``paper_session_realized_pnl_evidence_manifest_digest``, but never CALLING it — closing a TOCTOU where a
second serialization/read could diverge) and must equal BOTH the snapshot's bound ``manifest_digest`` AND a
caller-supplied ``expected_manifest_digest`` (the caller's INDEPENDENT provenance/trust anchor). ADMITTED
requires that triple-digest binding, a READY paper-safe manifest (expected schema, ``ready`` True, all
hard-safety flags False), clean scope-guarded manifest id/symbol/correlation/metadata, and canonical finite
gross totals. Every other outcome maps fail-closed to REJECTED. Wrong-typed/None manifest, malformed expected
digest, empty correlation id, or malformed/forbidden-token metadata raise ``PaperEvidenceAdmissionError``.

Trust boundary: ``expected_manifest_digest`` is the caller's independent anchor — this record does NOT
re-derive the manifest payload or reconstruct the aggregate, so a fully self-consistent manifest paired with
its own (matching) expected digest is admitted on the caller's authority. It is not, by itself, an
independent tamper-proof of the underlying economics; it pins the single snapshot to the expected digest and
re-checks the manifest's admission invariants.

Gross only: it carries no fees, no unrealized PnL, no total PnL, no equity/capital/margin/balance; reserves/
mutates no capital; routes no order; creates no venue/exchange/client order id / route id / execution
instruction; calls no live/private API; schedules nothing; runs no auto-loop; performs no
wall-clock/random/IO/persistence/network; touches no
connector/scheduler/runtime/venue/execution/service/session/data/portfolio/orchestrator/temporal surface, no
Deribit, no BIST. Does NOT assert per-episode membership (inherited from the manifest's documented boundary).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_session_realized_pnl_evidence_manifest import (
    PaperSessionRealizedPnlEvidenceManifest,
    paper_session_realized_pnl_evidence_manifest_to_dict,
)

_SCHEMA_VERSION = "paper-evidence-admission-record.v1"
_EXPECTED_MANIFEST_SCHEMA_VERSION = "paper-session-realized-pnl-evidence-manifest.v1"
_EXPECTED_MANIFEST_STATUS = "READY"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Strict decimal-string grammar (mirrors the manifest): optional sign, no leading zeros (except a bare
# ``0``), optional fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"Infinity"``.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling realized-PnL modules (word-bounded). Market-data terms scrubbed first.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")

# Manifest hard-safety attestations that MUST be False for a paper-only manifest to be admissible.
_MANIFEST_FALSE_FLAGS = (
    "fees_included",
    "unrealized_pnl_included",
    "total_pnl_computed",
    "equity_or_capital_computed",
    "capital_reserved",
    "capital_mutated",
    "balance_mutated",
    "live_position_mutated",
    "real_money_enabled",
    "real_orders_enabled",
    "order_routed",
    "venue_order_id_created",
    "exchange_order_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
)


class PaperEvidenceAdmissionError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed/None manifest, bad expected digest/correlation/metadata)."""


class PaperEvidenceAdmissionStatus(str, Enum):
    """Terminal admissibility verdict for a realized-PnL evidence manifest. Never an execution / capital / live action."""

    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperEvidenceAdmissionRecord:
    """Deterministic, immutable digest-bound admission decision over one paper realized-PnL evidence manifest.

    Records the admitted/rejected verdict, the manifest digest it was decided against (and the caller's
    independent expected anchor), and the manifest's gross audit context by value. Gross only; computes no
    fills/positions/fees/unrealized/total PnL/equity/capital/margin/balance; reconstructs no aggregate. Does
    NOT assert per-episode membership. ``paper_only`` / ``gross_only`` are True; every hard-safety attestation
    is False. PAPER ONLY.
    """

    schema_version: str
    status: PaperEvidenceAdmissionStatus
    admitted: bool
    manifest_digest: str
    expected_manifest_digest: str
    manifest_status: str
    aggregate_id: str
    aggregate_digest: str
    market_symbol: str
    session_bridge_count: int
    event_count: int
    computed_event_count: int
    closed_units_total: str
    realized_pnl_total: str
    rejection_reasons: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    admission_digest: str
    paper_only: bool = True
    gross_only: bool = True
    fees_included: bool = False
    unrealized_pnl_included: bool = False
    total_pnl_computed: bool = False
    equity_or_capital_computed: bool = False
    capital_reserved: bool = False
    capital_mutated: bool = False
    balance_mutated: bool = False
    live_position_mutated: bool = False
    real_money_enabled: bool = False
    real_orders_enabled: bool = False
    order_routed: bool = False
    venue_order_id_created: bool = False
    exchange_order_id_created: bool = False
    client_order_id_created: bool = False
    route_id_created: bool = False
    execution_instruction_created: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            return True
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperEvidenceAdmissionError("paper_evidence_admission_record:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperEvidenceAdmissionError("paper_evidence_admission_record:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    """Canonicalize record metadata to a list of exact two-item ``[str, str]`` pairs (no blind ``list(...)``).

    ``metadata`` is the already-normalized tuple of sorted unique-key ``(str, str)`` pairs produced by
    ``_normalize_metadata``; the exact shape is re-asserted before binding so a malformed/lossy container can
    never collapse into a valid-looking, collision-prone payload.
    """
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise PaperEvidenceAdmissionError("paper_evidence_admission_record:metadata_malformed")
        pairs.append([pair[0], pair[1]])
    return pairs


def _parse_decimal(value: object) -> Decimal | None:
    """Return an exact finite ``Decimal`` for a strict decimal string, else ``None`` (no float/bool path)."""
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _render_decimal(value: Decimal) -> str:
    """Render an exact ``Decimal`` as a canonical plain-decimal string (context-independent). Never normalize()."""
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _canonical_decimal(value: object) -> Decimal | None:
    """Parse a strict decimal string that is ALSO already in canonical render form, else ``None``."""
    parsed = _parse_decimal(value)
    if parsed is None or _render_decimal(parsed) != value:
        return None
    return parsed


def _capture_manifest_snapshot(manifest: PaperSessionRealizedPnlEvidenceManifest) -> dict[str, object] | None:
    """Serialize the manifest via the PUBLIC serializer EXACTLY ONCE and ROUND-TRIP through canonical JSON.

    The manifest object is read once here and never again — neither for digest, status, identity, totals,
    flags, nor metadata. The returned dict is exact plain primitives (plain ``str``/builtins — no ``str``
    subclass with custom hash/equality), so every admission-bound field, the manifest-digest recompute, and
    the scope re-proof all derive from this single snapshot (closing a TOCTOU where a second serialization/
    read could diverge from the bound payload). Returns ``None`` (fail-closed) on any serialization failure.
    """
    try:
        raw = paper_session_realized_pnl_evidence_manifest_to_dict(manifest)
        payload = json.loads(json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
    except Exception:  # noqa: BLE001 - any serialization failure is a fail-closed rejection, not a crash
        return None
    return payload if isinstance(payload, dict) else None


def _recompute_manifest_digest(snapshot: dict[str, object]) -> str | None:
    """Recompute the manifest self-digest FROM the single captured snapshot (no second manifest read).

    Uses the same contract as the manifest module's PUBLIC ``paper_session_realized_pnl_evidence_manifest_digest``:
    SHA-256 over canonical JSON of the manifest payload EXCLUDING the ``manifest_digest`` self field.
    Recomputing from the snapshot (rather than re-serializing the manifest) guarantees the digest proven here
    covers the exact bytes the admission binds. Returns ``None`` (fail-closed) on a non-serializable snapshot.
    """
    digest_input = {key: value for key, value in snapshot.items() if key != "manifest_digest"}
    try:
        return _canonical_digest(digest_input)
    except (TypeError, ValueError):
        return None


def _manifest_scope_reasons(snapshot: dict[str, object]) -> list[str]:
    """Structurally re-prove + scope-guard the manifest's INTERNAL identity fields from the single snapshot.

    The triple-digest binding only proves the snapshot is self-consistent and matches the caller's expected
    anchor — a forged-but-self-consistent manifest could still carry a non-string ``correlation_id``, a
    nested/non-string ``metadata`` value, or forbidden tokens in ``aggregate_id`` / ``market_symbol`` that a
    naive scan would miss. Each is re-proven (correlation id = exact non-empty ``str``; metadata = list of
    exact two-item ``[str, str]`` pairs, unique keys; ids non-empty ``str``) and scope-scanned. Malformed
    shape is itself a rejection (nested values are never stringified). Returns fail-closed reason codes.
    """
    reasons: list[str] = []

    aggregate_id = snapshot.get("aggregate_id")
    market_symbol = snapshot.get("market_symbol")
    if not _is_non_empty_string(aggregate_id) or not _is_non_empty_string(market_symbol):
        reasons.append("paper_evidence_admission_record:manifest_id_or_symbol_invalid")
    if _has_scope_violation(aggregate_id, market_symbol):
        reasons.append("paper_evidence_admission_record:manifest_scope_violation")

    correlation = snapshot.get("correlation_id")
    if type(correlation) is not str or correlation.strip() == "":
        reasons.append("paper_evidence_admission_record:manifest_correlation_id_invalid")
    elif _has_scope_violation(correlation):
        reasons.append("paper_evidence_admission_record:manifest_scope_violation")

    metadata = snapshot.get("metadata")
    if not isinstance(metadata, list):
        reasons.append("paper_evidence_admission_record:manifest_metadata_malformed")
    else:
        keys: list[str] = []
        malformed = False
        scope_violation = False
        for pair in metadata:
            if not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
                malformed = True
                continue
            keys.append(pair[0])
            if _has_scope_violation(pair[0], pair[1]):
                scope_violation = True
        if malformed or len(set(keys)) != len(keys):
            reasons.append("paper_evidence_admission_record:manifest_metadata_malformed")
        if scope_violation:
            reasons.append("paper_evidence_admission_record:manifest_scope_violation")

    return reasons


def build_paper_evidence_admission_record(
    manifest: PaperSessionRealizedPnlEvidenceManifest,
    *,
    expected_manifest_digest: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperEvidenceAdmissionRecord:
    """Decide admission of one paper realized-PnL evidence manifest as a deterministic, digest-bound record.

    ``manifest`` must be a ``PaperSessionRealizedPnlEvidenceManifest`` and ``expected_manifest_digest`` an
    exact plain 64-lowercase-hex ``str`` — the caller's INDEPENDENT provenance/trust anchor for the manifest.
    A wrong-typed/None manifest, a malformed expected digest, an empty ``correlation_id``, or non
    ``Mapping[str, str]`` / forbidden-token metadata raises ``PaperEvidenceAdmissionError``.

    The manifest is captured EXACTLY ONCE (PUBLIC serializer + canonical-JSON round-trip into exact plain
    primitives); the manifest self-digest is recomputed FROM that single snapshot (never via a second
    manifest read) and must equal BOTH the snapshot's bound ``manifest_digest`` AND ``expected_manifest_digest``.
    ADMITTED only when that triple-digest binding holds, the snapshot is a READY paper-safe manifest (expected
    schema, ``ready`` True, all hard-safety flags False), its scope-guarded id/symbol/correlation/metadata are
    clean, and its gross totals are canonical finite decimals (``closed_units_total`` >= 0). Every other
    outcome maps fail-closed to REJECTED. The caller-supplied expected digest is recorded on EVERY built
    record (ADMITTED or REJECTED) and bound into the admission digest. Deterministic and immutable; no
    wall-clock/random/IO; gross only.
    """
    if not isinstance(manifest, PaperSessionRealizedPnlEvidenceManifest):
        raise PaperEvidenceAdmissionError("paper_evidence_admission_record:manifest_malformed")
    if not _is_hex64_string(expected_manifest_digest):
        raise PaperEvidenceAdmissionError("paper_evidence_admission_record:expected_manifest_digest_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperEvidenceAdmissionError("paper_evidence_admission_record:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperEvidenceAdmissionError("paper_evidence_admission_record:scope_violation")

    hard: list[str] = []

    snapshot = _capture_manifest_snapshot(manifest)
    # Defaults bound even when the manifest is unserializable/malformed (record still records REJECTED).
    manifest_digest = ""
    manifest_status = ""
    aggregate_id = ""
    aggregate_digest = ""
    market_symbol = ""
    session_bridge_count = 0
    event_count = 0
    computed_event_count = 0
    closed_units_total = "0"
    realized_pnl_total = "0"

    if snapshot is None:
        hard.append("paper_evidence_admission_record:manifest_payload_invalid")
    else:
        manifest_digest = snapshot.get("manifest_digest") if isinstance(snapshot.get("manifest_digest"), str) else ""
        manifest_status = snapshot.get("status") if isinstance(snapshot.get("status"), str) else ""
        aggregate_id = snapshot.get("aggregate_id") if isinstance(snapshot.get("aggregate_id"), str) else ""
        aggregate_digest = snapshot.get("aggregate_digest") if isinstance(snapshot.get("aggregate_digest"), str) else ""
        market_symbol = snapshot.get("market_symbol") if isinstance(snapshot.get("market_symbol"), str) else ""

        # Single-snapshot digest re-proof: recompute the manifest digest from THIS snapshot (no second read)
        # and require it to equal both the snapshot's bound digest and the caller's expected anchor.
        recomputed = _recompute_manifest_digest(snapshot)
        if not _is_hex64_string(manifest_digest):
            hard.append("paper_evidence_admission_record:manifest_digest_invalid")
        elif recomputed is None or recomputed != manifest_digest:
            hard.append("paper_evidence_admission_record:manifest_digest_mismatch")
        elif expected_manifest_digest != recomputed:
            hard.append("paper_evidence_admission_record:expected_manifest_digest_mismatch")

        if snapshot.get("schema_version") != _EXPECTED_MANIFEST_SCHEMA_VERSION:
            hard.append("paper_evidence_admission_record:manifest_schema_invalid")
        if manifest_status != _EXPECTED_MANIFEST_STATUS or snapshot.get("ready") is not True:
            hard.append("paper_evidence_admission_record:manifest_not_ready")
        if snapshot.get("paper_only") is not True or snapshot.get("gross_only") is not True:
            hard.append("paper_evidence_admission_record:manifest_safety_violation")
        if any(snapshot.get(flag) is not False for flag in _MANIFEST_FALSE_FLAGS):
            hard.append("paper_evidence_admission_record:manifest_safety_violation")

        hard.extend(_manifest_scope_reasons(snapshot))

        # Aggregate-context counts (bound for audit) must be coherent non-negative ints.
        counts = {name: snapshot.get(name) for name in ("session_bridge_count", "event_count", "computed_event_count")}
        if any(not _is_int(value) or value < 0 for value in counts.values()):
            hard.append("paper_evidence_admission_record:manifest_count_invalid")
        else:
            session_bridge_count = counts["session_bridge_count"]
            event_count = counts["event_count"]
            computed_event_count = counts["computed_event_count"]

        # Gross totals must be canonical finite decimal strings; closed units must be non-negative.
        realized_candidate = snapshot.get("realized_pnl_total")
        closed_candidate = snapshot.get("closed_units_total")
        if _canonical_decimal(realized_candidate) is None:
            hard.append("paper_evidence_admission_record:manifest_totals_malformed")
        elif isinstance(realized_candidate, str):
            realized_pnl_total = realized_candidate
        closed_value = _canonical_decimal(closed_candidate)
        if closed_value is None or closed_value < 0:
            hard.append("paper_evidence_admission_record:manifest_totals_malformed")
        elif isinstance(closed_candidate, str):
            closed_units_total = closed_candidate

    rejection_reasons = tuple(sorted(set(hard)))
    status = PaperEvidenceAdmissionStatus.REJECTED if rejection_reasons else PaperEvidenceAdmissionStatus.ADMITTED

    return _finalize_record(
        status=status,
        manifest_digest=manifest_digest,
        expected_manifest_digest=expected_manifest_digest,
        manifest_status=manifest_status,
        aggregate_id=aggregate_id,
        aggregate_digest=aggregate_digest,
        market_symbol=market_symbol,
        session_bridge_count=session_bridge_count,
        event_count=event_count,
        computed_event_count=computed_event_count,
        closed_units_total=closed_units_total,
        realized_pnl_total=realized_pnl_total,
        rejection_reasons=rejection_reasons,
        correlation_id=correlation_id,
        metadata=metadata_pairs,
    )


def _finalize_record(
    *,
    status: PaperEvidenceAdmissionStatus,
    manifest_digest: str,
    expected_manifest_digest: str,
    manifest_status: str,
    aggregate_id: str,
    aggregate_digest: str,
    market_symbol: str,
    session_bridge_count: int,
    event_count: int,
    computed_event_count: int,
    closed_units_total: str,
    realized_pnl_total: str,
    rejection_reasons: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperEvidenceAdmissionRecord:
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status,
        "admitted": status is PaperEvidenceAdmissionStatus.ADMITTED,
        "manifest_digest": manifest_digest,
        "expected_manifest_digest": expected_manifest_digest,
        "manifest_status": manifest_status,
        "aggregate_id": aggregate_id,
        "aggregate_digest": aggregate_digest,
        "market_symbol": market_symbol,
        "session_bridge_count": session_bridge_count,
        "event_count": event_count,
        "computed_event_count": computed_event_count,
        "closed_units_total": closed_units_total,
        "realized_pnl_total": realized_pnl_total,
        "rejection_reasons": rejection_reasons,
        "correlation_id": correlation_id,
        "metadata": metadata,
    }
    seed = PaperEvidenceAdmissionRecord(admission_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_evidence_admission_record_digest(seed))


def _replace_digest(record: PaperEvidenceAdmissionRecord, digest: str) -> PaperEvidenceAdmissionRecord:
    fields = _record_fields(record)
    fields["admission_digest"] = digest
    return PaperEvidenceAdmissionRecord(**fields)  # type: ignore[arg-type]


def _record_fields(record: PaperEvidenceAdmissionRecord) -> dict[str, object]:
    return {
        "schema_version": record.schema_version,
        "status": record.status,
        "admitted": record.admitted,
        "manifest_digest": record.manifest_digest,
        "expected_manifest_digest": record.expected_manifest_digest,
        "manifest_status": record.manifest_status,
        "aggregate_id": record.aggregate_id,
        "aggregate_digest": record.aggregate_digest,
        "market_symbol": record.market_symbol,
        "session_bridge_count": record.session_bridge_count,
        "event_count": record.event_count,
        "computed_event_count": record.computed_event_count,
        "closed_units_total": record.closed_units_total,
        "realized_pnl_total": record.realized_pnl_total,
        "rejection_reasons": record.rejection_reasons,
        "correlation_id": record.correlation_id,
        "metadata": record.metadata,
    }


def _record_payload_from(record: PaperEvidenceAdmissionRecord) -> dict[str, object]:
    return {
        "schema_version": record.schema_version,
        "status": record.status.value,
        "admitted": record.admitted,
        "manifest_digest": record.manifest_digest,
        "expected_manifest_digest": record.expected_manifest_digest,
        "manifest_status": record.manifest_status,
        "aggregate_id": record.aggregate_id,
        "aggregate_digest": record.aggregate_digest,
        "market_symbol": record.market_symbol,
        "session_bridge_count": record.session_bridge_count,
        "event_count": record.event_count,
        "computed_event_count": record.computed_event_count,
        "closed_units_total": record.closed_units_total,
        "realized_pnl_total": record.realized_pnl_total,
        "rejection_reasons": list(record.rejection_reasons),
        "correlation_id": record.correlation_id,
        "metadata": _serialize_metadata(record.metadata),
        "paper_only": record.paper_only,
        "gross_only": record.gross_only,
        "fees_included": record.fees_included,
        "unrealized_pnl_included": record.unrealized_pnl_included,
        "total_pnl_computed": record.total_pnl_computed,
        "equity_or_capital_computed": record.equity_or_capital_computed,
        "capital_reserved": record.capital_reserved,
        "capital_mutated": record.capital_mutated,
        "balance_mutated": record.balance_mutated,
        "live_position_mutated": record.live_position_mutated,
        "real_money_enabled": record.real_money_enabled,
        "real_orders_enabled": record.real_orders_enabled,
        "order_routed": record.order_routed,
        "venue_order_id_created": record.venue_order_id_created,
        "exchange_order_id_created": record.exchange_order_id_created,
        "client_order_id_created": record.client_order_id_created,
        "route_id_created": record.route_id_created,
        "execution_instruction_created": record.execution_instruction_created,
        "live_api_called": record.live_api_called,
        "scheduler_enabled": record.scheduler_enabled,
        "auto_loop_enabled": record.auto_loop_enabled,
        "connector_invoked": record.connector_invoked,
    }


def paper_evidence_admission_record_to_dict(record: PaperEvidenceAdmissionRecord) -> dict[str, object]:
    """Canonical, JSON-ready mapping for an admission record (deterministic shape, includes self-digest)."""
    payload = _record_payload_from(record)
    payload["admission_digest"] = record.admission_digest
    return payload


def paper_evidence_admission_record_digest(record: PaperEvidenceAdmissionRecord) -> str:
    """Recompute the canonical admission digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_record_payload_from(record))


__all__ = [
    "PaperEvidenceAdmissionError",
    "PaperEvidenceAdmissionRecord",
    "PaperEvidenceAdmissionStatus",
    "build_paper_evidence_admission_record",
    "paper_evidence_admission_record_digest",
    "paper_evidence_admission_record_to_dict",
]
