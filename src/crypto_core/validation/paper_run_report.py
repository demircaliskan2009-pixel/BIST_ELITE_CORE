"""Paper run report — deterministic, paper-only, operator-readable summary of one ADMITTED paper evidence
admission record.

A small, immutable, fail-closed *report / probe* that binds a ``PaperEvidenceAdmissionRecord`` (the artifact
merged in PR #290) into one canonical, operator-readable summary of a paper run's realized-PnL evidence. It is
the first integration-first slice from ``docs/crypto_core/paper_trading_phase_map.md``: it *consumes and binds
by digest*, it is NOT an engine. It runs no backtest, simulates no fills, recomputes no positions/realized
PnL, reconstructs no aggregate/bridge/rollup/manifest, and adds no runtime/persistence/scheduler/execution/
venue path. It derives its verdict solely from the admission record's already-proven status, digest, and
paper-safety attestations.

Single canonical snapshot + independent expected digest: the supplied admission record is serialized EXACTLY
ONCE via the PUBLIC ``paper_evidence_admission_record_to_dict`` and ROUND-TRIPPED through canonical JSON into
exact plain primitives (plain ``str``/builtins — no ``str`` subclass with custom hash/equality). The admission
self-digest is recomputed FROM that single snapshot (the SAME digest contract as the PUBLIC
``paper_evidence_admission_record_digest``, but never CALLING it — closing a TOCTOU where a second
serialization/read could diverge) and must equal BOTH the snapshot's bound ``admission_digest`` AND a
caller-supplied ``expected_admission_digest`` (the caller's INDEPENDENT provenance/trust anchor). A READY
report requires that triple-digest binding, an ADMITTED paper-safe admission record (expected schema,
``admitted`` True, all hard-safety flags False), clean scope-guarded ids/symbol/correlation/metadata, and
canonical finite gross totals. Every other outcome maps fail-closed to REJECTED. Wrong-typed/None admission,
malformed expected digest, empty run id / correlation id, or malformed/forbidden-token metadata raise
``PaperRunReportError``.

Trust boundary: ``expected_admission_digest`` is the caller's independent anchor — this report does NOT
re-derive the admission payload, the manifest, or the aggregate, so a self-consistent admission record paired
with its own (matching) expected digest is reported READY on the caller's authority. The report faithfully
summarizes a digest-bound admission record; it is NOT, by itself, an independent tamper-proof of the
underlying economics, and it carries forward (does not re-verify) the admission's own manifest/aggregate
digest bindings.

Non-overclaim: a READY report is a *deterministic paper-substrate report*. It is NOT PRDV4 Stage 4 ("Paper
Trading") completion (which requires >=30-day paper trading, paper-vs-backtest metrics, and the
Sharpe>=50%-of-backtest gate), NOT live readiness, NOT shadow readiness, NOT proof of economic profitability,
and NOT proof of independent strategy edge. Those attestations are carried as explicit ``False`` flags.

Gross only: it carries no fees, no unrealized PnL, no total PnL, no equity/capital/margin/balance; reserves/
mutates no capital; routes no order; creates no venue/exchange/client order id / route id / execution
instruction; calls no live/private API; schedules nothing; runs no auto-loop; performs no
wall-clock/random/IO/persistence/network. It does NOT import or use ``crypto_core.service.readiness`` or
``crypto_core.execution.paper_adapter`` (or any shadow/live/runtime service surface), no Deribit, no BIST.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_evidence_admission_record import (
    PaperEvidenceAdmissionRecord,
    paper_evidence_admission_record_to_dict,
)

_SCHEMA_VERSION = "paper-run-report.v1"
_EXPECTED_ADMISSION_SCHEMA_VERSION = "paper-evidence-admission-record.v1"
_EXPECTED_ADMISSION_STATUS = "ADMITTED"
# The upstream manifest status the admission record must itself carry for an ADMITTED run (re-proven here so a
# self-consistent/resealed admission cannot surface a non-READY manifest as a READY report).
_EXPECTED_MANIFEST_STATUS = "READY"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Strict decimal-string grammar (mirrors the consumed artifacts): optional sign, no leading zeros (except a
# bare ``0``), optional fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"Infinity"``.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling realized-PnL/admission modules (word-bounded). Market-data terms scrubbed first.
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

# Admission hard-safety attestations that MUST be False for a paper-only admission record to be report-READY.
_ADMISSION_FALSE_FLAGS = (
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


class PaperRunReportError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed/None admission, bad expected digest/run id/correlation/metadata)."""


class PaperRunReportStatus(str, Enum):
    """Terminal report verdict over one admission record. Never an execution / capital / live / readiness action."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperRunReport:
    """Deterministic, immutable, digest-bound, operator-readable report over one paper evidence admission record.

    Summarizes the admitted/rejected paper run by value (admission/manifest/aggregate digests, market symbol,
    event/session counts, gross realized-PnL totals) so an operator can inspect the run without reading every
    lower-level artifact. Gross only; computes no fills/positions/fees/unrealized/total PnL/equity/capital/
    margin/balance; reconstructs no aggregate/manifest. ``paper_only`` / ``gross_only`` are True; every
    hard-safety attestation is False; every non-overclaim attestation is False. PAPER ONLY — NOT PRDV4 Stage 4
    completion, NOT live/shadow readiness, NOT profitability/edge proof.
    """

    schema_version: str
    status: PaperRunReportStatus
    ready: bool
    run_id: str
    correlation_id: str
    admission_status: str
    admission_digest: str
    expected_admission_digest: str
    manifest_digest: str
    expected_manifest_digest: str
    aggregate_id: str
    aggregate_digest: str
    market_symbol: str
    session_bridge_count: int
    event_count: int
    computed_event_count: int
    closed_units_total: str
    realized_pnl_total: str
    rejection_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    report_digest: str
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
    # Non-overclaim attestations (a READY report proves none of these).
    prdv4_stage4_complete: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_plain_non_empty_string(value: object) -> bool:
    """Exact plain ``str`` (no subclass) that is non-empty after strip.

    Caller-supplied ids are validated with ``type(value) is str`` (not ``isinstance``) so a ``str`` subclass
    overriding ``strip()``/``__eq__``/``__hash__`` cannot smuggle an effectively-empty or scope-violating value
    past the gate.
    """
    return type(value) is str and value.strip() != ""


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
        raise PaperRunReportError("paper_run_report:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        # Exact plain ``str`` only (no subclass) so a custom-hash/eq/strip ``str`` subclass cannot bypass the
        # uniqueness or scope guard or collapse into a collision-prone key.
        if type(key) is not str or type(value) is not str:
            raise PaperRunReportError("paper_run_report:metadata_malformed")
        items.append((str(key), str(value)))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    """Canonicalize report metadata to a list of exact two-item ``[str, str]`` pairs (no blind ``list(...)``).

    ``metadata`` is the already-normalized tuple of sorted unique-key ``(str, str)`` pairs produced by
    ``_normalize_metadata``; the exact shape is re-asserted before binding so a malformed/lossy container can
    never collapse into a valid-looking, collision-prone payload.
    """
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise PaperRunReportError("paper_run_report:metadata_malformed")
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


def _capture_admission_snapshot(admission: PaperEvidenceAdmissionRecord) -> dict[str, object] | None:
    """Serialize the admission record via the PUBLIC serializer EXACTLY ONCE and ROUND-TRIP through canonical JSON.

    The admission object is read once here and never again — neither for digest, status, identity, totals,
    flags, nor metadata. The returned dict is exact plain primitives (plain ``str``/builtins — no ``str``
    subclass with custom hash/equality), so every report-bound field, the admission-digest recompute, and the
    scope re-proof all derive from this single snapshot (closing a TOCTOU where a second serialization/read
    could diverge from the bound payload). Returns ``None`` (fail-closed) on any serialization failure.
    """
    try:
        raw = paper_evidence_admission_record_to_dict(admission)
        payload = json.loads(json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
    except Exception:  # noqa: BLE001 - any serialization failure is a fail-closed rejection, not a crash
        return None
    return payload if isinstance(payload, dict) else None


def _recompute_admission_digest(snapshot: dict[str, object]) -> str | None:
    """Recompute the admission self-digest FROM the single captured snapshot (no second admission read).

    Uses the same contract as the admission module's PUBLIC ``paper_evidence_admission_record_digest``:
    SHA-256 over canonical JSON of the admission payload EXCLUDING the ``admission_digest`` self field.
    Recomputing from the snapshot (rather than re-serializing the record) guarantees the digest proven here
    covers the exact bytes the report binds. Returns ``None`` (fail-closed) on a non-serializable snapshot.
    """
    digest_input = {key: value for key, value in snapshot.items() if key != "admission_digest"}
    try:
        return _canonical_digest(digest_input)
    except (TypeError, ValueError):
        return None


def _admission_scope_reasons(snapshot: dict[str, object]) -> list[str]:
    """Structurally re-prove + scope-guard the admission record's INTERNAL identity fields from the snapshot.

    The triple-digest binding only proves the snapshot is self-consistent and matches the caller's expected
    anchor — a forged-but-self-consistent admission record could still carry a non-string ``correlation_id``, a
    nested/non-string ``metadata`` value, or forbidden tokens in ``aggregate_id`` / ``market_symbol`` that a
    naive scan would miss. Each is re-proven (correlation id = exact non-empty ``str``; metadata = list of
    exact two-item ``[str, str]`` pairs, unique keys; ids non-empty ``str``) and scope-scanned. Malformed
    shape is itself a rejection (nested values are never stringified). Returns fail-closed reason codes.
    """
    reasons: list[str] = []

    aggregate_id = snapshot.get("aggregate_id")
    market_symbol = snapshot.get("market_symbol")
    if not _is_non_empty_string(aggregate_id) or not _is_non_empty_string(market_symbol):
        reasons.append("paper_run_report:admission_id_or_symbol_invalid")
    if _has_scope_violation(aggregate_id, market_symbol):
        reasons.append("paper_run_report:admission_scope_violation")

    correlation = snapshot.get("correlation_id")
    if type(correlation) is not str or correlation.strip() == "":
        reasons.append("paper_run_report:admission_correlation_id_invalid")
    elif _has_scope_violation(correlation):
        reasons.append("paper_run_report:admission_scope_violation")

    metadata = snapshot.get("metadata")
    if not isinstance(metadata, list):
        reasons.append("paper_run_report:admission_metadata_malformed")
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
            reasons.append("paper_run_report:admission_metadata_malformed")
        if scope_violation:
            reasons.append("paper_run_report:admission_scope_violation")

    return reasons


def build_paper_run_report(
    admission: PaperEvidenceAdmissionRecord,
    *,
    expected_admission_digest: str,
    run_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperRunReport:
    """Build a deterministic, digest-bound, operator-readable paper run report over one admission record.

    ``admission`` must be a ``PaperEvidenceAdmissionRecord`` and ``expected_admission_digest`` an exact plain
    64-lowercase-hex ``str`` — the caller's INDEPENDENT provenance/trust anchor for the admission record. A
    wrong-typed/None admission, a malformed expected digest, an empty ``run_id`` / ``correlation_id``, or non
    ``Mapping[str, str]`` / forbidden-token metadata raises ``PaperRunReportError``.

    The admission record is captured EXACTLY ONCE (PUBLIC serializer + canonical-JSON round-trip into exact
    plain primitives); its self-digest is recomputed FROM that single snapshot (never via a second admission
    read) and must equal BOTH the snapshot's bound ``admission_digest`` AND ``expected_admission_digest``. The
    report is READY only when that triple-digest binding holds, the snapshot is an ADMITTED paper-safe
    admission record (expected schema, ``admitted`` True, all hard-safety flags False), its scope-guarded
    ids/symbol/correlation/metadata are clean, and its gross totals are canonical finite decimals
    (``closed_units_total`` >= 0). Every other outcome maps fail-closed to REJECTED. The caller-supplied
    expected digest is recorded on EVERY built report (READY or REJECTED) and bound into the report digest.
    Deterministic and immutable; no wall-clock/random/IO; gross only; NOT PRDV4 Stage 4 / live / shadow
    readiness and NOT a profitability/edge proof.
    """
    if not isinstance(admission, PaperEvidenceAdmissionRecord):
        raise PaperRunReportError("paper_run_report:admission_malformed")
    if not _is_hex64_string(expected_admission_digest):
        raise PaperRunReportError("paper_run_report:expected_admission_digest_invalid")
    if not _is_plain_non_empty_string(run_id):
        raise PaperRunReportError("paper_run_report:run_id_invalid")
    if not _is_plain_non_empty_string(correlation_id):
        raise PaperRunReportError("paper_run_report:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(run_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperRunReportError("paper_run_report:scope_violation")

    hard: list[str] = []
    warnings: list[str] = []

    snapshot = _capture_admission_snapshot(admission)
    # Defaults bound even when the admission record is unserializable/malformed (report still records REJECTED).
    admission_status = ""
    admission_digest = ""
    manifest_digest = ""
    expected_manifest_digest = ""
    aggregate_id = ""
    aggregate_digest = ""
    market_symbol = ""
    session_bridge_count = 0
    event_count = 0
    computed_event_count = 0
    closed_units_total = "0"
    realized_pnl_total = "0"

    if snapshot is None:
        hard.append("paper_run_report:admission_payload_invalid")
    else:
        admission_status = snapshot.get("status") if isinstance(snapshot.get("status"), str) else ""
        admission_digest = snapshot.get("admission_digest") if isinstance(snapshot.get("admission_digest"), str) else ""
        manifest_digest = snapshot.get("manifest_digest") if isinstance(snapshot.get("manifest_digest"), str) else ""
        expected_manifest_digest = (
            snapshot.get("expected_manifest_digest")
            if isinstance(snapshot.get("expected_manifest_digest"), str)
            else ""
        )
        aggregate_id = snapshot.get("aggregate_id") if isinstance(snapshot.get("aggregate_id"), str) else ""
        aggregate_digest = snapshot.get("aggregate_digest") if isinstance(snapshot.get("aggregate_digest"), str) else ""
        market_symbol = snapshot.get("market_symbol") if isinstance(snapshot.get("market_symbol"), str) else ""

        # Single-snapshot digest re-proof: recompute the admission digest from THIS snapshot (no second read)
        # and require it to equal both the snapshot's bound digest and the caller's expected anchor.
        recomputed = _recompute_admission_digest(snapshot)
        if not _is_hex64_string(admission_digest):
            hard.append("paper_run_report:admission_digest_invalid")
        elif recomputed is None or recomputed != admission_digest:
            hard.append("paper_run_report:admission_digest_mismatch")
        elif expected_admission_digest != recomputed:
            hard.append("paper_run_report:expected_admission_digest_mismatch")

        if snapshot.get("schema_version") != _EXPECTED_ADMISSION_SCHEMA_VERSION:
            hard.append("paper_run_report:admission_schema_invalid")
        if admission_status != _EXPECTED_ADMISSION_STATUS or snapshot.get("admitted") is not True:
            hard.append("paper_run_report:admission_not_admitted")
        if snapshot.get("paper_only") is not True or snapshot.get("gross_only") is not True:
            hard.append("paper_run_report:admission_safety_violation")
        if any(snapshot.get(flag) is not False for flag in _ADMISSION_FALSE_FLAGS):
            hard.append("paper_run_report:admission_safety_violation")

        # Carried-forward manifest digests must be present, well-formed, AND mutually consistent. The report
        # does not re-derive the manifest, but a READY report must not surface an admission whose own manifest
        # provenance is malformed or internally inconsistent (a forged/resealed admitted record could carry
        # manifest_digest != expected_manifest_digest).
        if not _is_hex64_string(manifest_digest) or not _is_hex64_string(expected_manifest_digest):
            hard.append("paper_run_report:admission_manifest_digest_invalid")
        elif manifest_digest != expected_manifest_digest:
            hard.append("paper_run_report:admission_manifest_digest_mismatch")
        # Carried aggregate digest must be a well-formed lowercase hex64 — never silently dropped.
        if not _is_hex64_string(aggregate_digest):
            hard.append("paper_run_report:admission_aggregate_digest_invalid")

        # Re-prove the upstream ADMITTED structural invariants from the snapshot. ``admitted`` True alone is
        # never sufficient: a self-consistent/resealed admission could still carry a non-READY manifest status
        # or non-empty upstream rejection reasons.
        if snapshot.get("manifest_status") != _EXPECTED_MANIFEST_STATUS:
            hard.append("paper_run_report:admission_manifest_not_ready")
        if snapshot.get("rejection_reasons") != []:
            hard.append("paper_run_report:admission_upstream_rejected")

        hard.extend(_admission_scope_reasons(snapshot))

        # Aggregate-context counts (bound for audit) must be coherent non-negative ints, no sub-count may
        # exceed the realized ``event_count`` (computed events / session bridges <= events), AND each must meet
        # the minimum a genuinely-READY manifest carries. A genuine READY manifest has at least one COMPUTED
        # realized event across at least one session bridge (the manifest marks computed_event_count == 0 as
        # INSUFFICIENT_EVIDENCE), so an all-zero / empty forged-but-self-consistent admission must fail closed.
        counts = {name: snapshot.get(name) for name in ("session_bridge_count", "event_count", "computed_event_count")}
        if any(not _is_int(value) or value < 0 for value in counts.values()):
            hard.append("paper_run_report:admission_count_invalid")
        else:
            session_bridge_count = counts["session_bridge_count"]
            event_count = counts["event_count"]
            computed_event_count = counts["computed_event_count"]
            if computed_event_count > event_count or session_bridge_count > event_count:
                hard.append("paper_run_report:admission_count_incoherent")
            if event_count < 1 or computed_event_count < 1 or session_bridge_count < 1:
                hard.append("paper_run_report:admission_insufficient_events")

        # Gross totals must be canonical finite decimal strings; closed units must be non-negative.
        realized_candidate = snapshot.get("realized_pnl_total")
        closed_candidate = snapshot.get("closed_units_total")
        realized_value = _canonical_decimal(realized_candidate)
        closed_value = _canonical_decimal(closed_candidate)
        if realized_value is None:
            hard.append("paper_run_report:admission_totals_malformed")
        elif isinstance(realized_candidate, str):
            realized_pnl_total = realized_candidate
        if closed_value is None or closed_value < 0:
            hard.append("paper_run_report:admission_totals_malformed")
        elif isinstance(closed_candidate, str):
            closed_units_total = closed_candidate

        # A zero-event run cannot carry nonzero gross totals (impossible/forged) — fail closed.
        if (
            _is_int(counts["event_count"])
            and counts["event_count"] == 0
            and realized_value is not None
            and closed_value is not None
            and (realized_value != 0 or closed_value != 0)
        ):
            hard.append("paper_run_report:admission_empty_run_nonzero_totals")

    # ``warnings`` is reserved for truthful, non-blocking operator notes. An empty/all-zero run is no longer
    # a READY-with-warning path — it is rejected as insufficient evidence above — so no warning is emitted here.
    rejection_reasons = tuple(sorted(set(hard)))
    status = PaperRunReportStatus.REJECTED if rejection_reasons else PaperRunReportStatus.READY

    return _finalize_report(
        status=status,
        run_id=run_id,
        correlation_id=correlation_id,
        admission_status=admission_status,
        admission_digest=admission_digest,
        expected_admission_digest=expected_admission_digest,
        manifest_digest=manifest_digest,
        expected_manifest_digest=expected_manifest_digest,
        aggregate_id=aggregate_id,
        aggregate_digest=aggregate_digest,
        market_symbol=market_symbol,
        session_bridge_count=session_bridge_count,
        event_count=event_count,
        computed_event_count=computed_event_count,
        closed_units_total=closed_units_total,
        realized_pnl_total=realized_pnl_total,
        rejection_reasons=rejection_reasons,
        warnings=tuple(sorted(set(warnings))),
        metadata=metadata_pairs,
    )


def _finalize_report(
    *,
    status: PaperRunReportStatus,
    run_id: str,
    correlation_id: str,
    admission_status: str,
    admission_digest: str,
    expected_admission_digest: str,
    manifest_digest: str,
    expected_manifest_digest: str,
    aggregate_id: str,
    aggregate_digest: str,
    market_symbol: str,
    session_bridge_count: int,
    event_count: int,
    computed_event_count: int,
    closed_units_total: str,
    realized_pnl_total: str,
    rejection_reasons: tuple[str, ...],
    warnings: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> PaperRunReport:
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status,
        "ready": status is PaperRunReportStatus.READY,
        "run_id": run_id,
        "correlation_id": correlation_id,
        "admission_status": admission_status,
        "admission_digest": admission_digest,
        "expected_admission_digest": expected_admission_digest,
        "manifest_digest": manifest_digest,
        "expected_manifest_digest": expected_manifest_digest,
        "aggregate_id": aggregate_id,
        "aggregate_digest": aggregate_digest,
        "market_symbol": market_symbol,
        "session_bridge_count": session_bridge_count,
        "event_count": event_count,
        "computed_event_count": computed_event_count,
        "closed_units_total": closed_units_total,
        "realized_pnl_total": realized_pnl_total,
        "rejection_reasons": rejection_reasons,
        "warnings": warnings,
        "metadata": metadata,
    }
    seed = PaperRunReport(report_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_run_report_digest(seed))


def _replace_digest(report: PaperRunReport, digest: str) -> PaperRunReport:
    fields = _report_fields(report)
    fields["report_digest"] = digest
    return PaperRunReport(**fields)  # type: ignore[arg-type]


def _report_fields(report: PaperRunReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "status": report.status,
        "ready": report.ready,
        "run_id": report.run_id,
        "correlation_id": report.correlation_id,
        "admission_status": report.admission_status,
        "admission_digest": report.admission_digest,
        "expected_admission_digest": report.expected_admission_digest,
        "manifest_digest": report.manifest_digest,
        "expected_manifest_digest": report.expected_manifest_digest,
        "aggregate_id": report.aggregate_id,
        "aggregate_digest": report.aggregate_digest,
        "market_symbol": report.market_symbol,
        "session_bridge_count": report.session_bridge_count,
        "event_count": report.event_count,
        "computed_event_count": report.computed_event_count,
        "closed_units_total": report.closed_units_total,
        "realized_pnl_total": report.realized_pnl_total,
        "rejection_reasons": report.rejection_reasons,
        "warnings": report.warnings,
        "metadata": report.metadata,
    }


def _report_payload_from(report: PaperRunReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "status": report.status.value,
        "ready": report.ready,
        "run_id": report.run_id,
        "correlation_id": report.correlation_id,
        "admission_status": report.admission_status,
        "admission_digest": report.admission_digest,
        "expected_admission_digest": report.expected_admission_digest,
        "manifest_digest": report.manifest_digest,
        "expected_manifest_digest": report.expected_manifest_digest,
        "aggregate_id": report.aggregate_id,
        "aggregate_digest": report.aggregate_digest,
        "market_symbol": report.market_symbol,
        "session_bridge_count": report.session_bridge_count,
        "event_count": report.event_count,
        "computed_event_count": report.computed_event_count,
        "closed_units_total": report.closed_units_total,
        "realized_pnl_total": report.realized_pnl_total,
        "rejection_reasons": list(report.rejection_reasons),
        "warnings": list(report.warnings),
        "metadata": _serialize_metadata(report.metadata),
        "paper_only": report.paper_only,
        "gross_only": report.gross_only,
        "fees_included": report.fees_included,
        "unrealized_pnl_included": report.unrealized_pnl_included,
        "total_pnl_computed": report.total_pnl_computed,
        "equity_or_capital_computed": report.equity_or_capital_computed,
        "capital_reserved": report.capital_reserved,
        "capital_mutated": report.capital_mutated,
        "balance_mutated": report.balance_mutated,
        "live_position_mutated": report.live_position_mutated,
        "real_money_enabled": report.real_money_enabled,
        "real_orders_enabled": report.real_orders_enabled,
        "order_routed": report.order_routed,
        "venue_order_id_created": report.venue_order_id_created,
        "exchange_order_id_created": report.exchange_order_id_created,
        "client_order_id_created": report.client_order_id_created,
        "route_id_created": report.route_id_created,
        "execution_instruction_created": report.execution_instruction_created,
        "live_api_called": report.live_api_called,
        "scheduler_enabled": report.scheduler_enabled,
        "auto_loop_enabled": report.auto_loop_enabled,
        "connector_invoked": report.connector_invoked,
        "prdv4_stage4_complete": report.prdv4_stage4_complete,
        "live_ready": report.live_ready,
        "shadow_ready": report.shadow_ready,
        "profitability_proven": report.profitability_proven,
        "edge_proven": report.edge_proven,
    }


def paper_run_report_to_dict(report: PaperRunReport) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for a run report (deterministic shape, includes self-digest)."""
    payload = _report_payload_from(report)
    payload["report_digest"] = report.report_digest
    return payload


def paper_run_report_digest(report: PaperRunReport) -> str:
    """Recompute the canonical report digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_report_payload_from(report))


__all__ = [
    "PaperRunReport",
    "PaperRunReportError",
    "PaperRunReportStatus",
    "build_paper_run_report",
    "paper_run_report_digest",
    "paper_run_report_to_dict",
]
