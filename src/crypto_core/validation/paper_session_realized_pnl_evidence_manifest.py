"""Paper session realized-PnL evidence manifest — deterministic, paper-only record of an admitted
realized-PnL aggregate evidence chain.

A small, immutable, fail-closed *evidence manifest* that records — by digest — the provenance/action chain
already proven by one ``PaperSessionRealizedPnlAggregate`` (the artifact merged in PR #287). It is the
first consumer of that aggregate: it does **not** recompute fills, positions, transitions, per-fill
realized PnL, sessions, bridges, rollups, or the aggregate itself, and it does **not** reconstruct upstream
bridges (the aggregate already re-proves them transitively). It is a *consumer / cross-check* artifact, not
a second builder: it recomputes the supplied aggregate's self-digest FROM a single canonical snapshot using
the SAME digest contract as the PUBLIC ``paper_session_realized_pnl_aggregate_digest`` (it never CALLS that
helper, so the bytes proven are exactly the bytes bound — no second serialization/read), binds the
aggregate's gross totals / counts / digest chains into one frozen, digest-bound manifest, structurally
re-proves the aggregate's internal ``correlation_id`` / ``metadata`` / ``reason_codes`` (scope-guarding each,
since the bound digest covers them but a naive direct-string scan would skip a non-string id, nested
metadata, or non-empty reason codes), and cross-checks the aggregate's internal count/chain consistency.

Gross only: it carries no fees, no unrealized PnL, no total PnL, no equity/capital/margin/balance; it
reserves/mutates no capital; routes no order; creates no venue/exchange/client order id / route id /
execution instruction; calls no live/private API; schedules nothing; runs no auto-loop; performs no
wall-clock/random/IO/persistence/network; and touches no
connector/scheduler/runtime/venue/execution/service/session/data/portfolio/orchestrator/temporal surface,
no Deribit, no BIST.

Single snapshot + independent expected digest: the supplied aggregate is serialized EXACTLY ONCE via the
PUBLIC ``paper_session_realized_pnl_aggregate_to_dict`` and ROUND-TRIPPED through canonical JSON into exact
plain primitives (plain ``str``/builtins — no ``str`` subclass with custom hash/equality); the aggregate
self-digest is recomputed FROM that single snapshot (never a second serialization/read, closing a TOCTOU
where the bound payload and the digest-covered payload could diverge) and must equal BOTH the snapshot's
bound ``aggregate_digest`` AND a caller-supplied ``expected_aggregate_digest`` — the latter is the caller's
INDEPENDENT provenance/trust anchor. The manifest does NOT reconstruct upstream bridges and does NOT
independently re-derive the aggregate payload: a fully self-consistent aggregate paired with its own
(matching) expected digest is recorded on the caller's authority, so this manifest is not by itself an
independent tamper-proof of the aggregate's economics — it pins the single snapshot to the expected digest
and re-checks the aggregate's internal invariants. The caller-supplied ``expected_aggregate_digest`` is
recorded on EVERY built manifest (READY, REJECTED, or INSUFFICIENT_EVIDENCE) and bound into the manifest
digest, so two different (wrong) expected anchors over the same aggregate produce distinct manifest
payloads/digests. READY requires the triple-digest binding, a ``COMPUTED`` paper-safe aggregate (expected
schema, ``aggregate_computed`` True, hard-safety flags False), a clean scope-guarded id/symbol and a
structurally re-proven internal ``correlation_id`` (exact non-empty ``str``) / ``metadata`` (exact two-item
string pairs, unique keys) / ``reason_codes`` (present and empty), canonical 64-hex digest chains with
coherent counts/uniqueness, canonical finite gross totals (``closed_units_total`` >= 0), and at least one
COMPUTED realized event; zero computed realized events is INSUFFICIENT_EVIDENCE; every other outcome maps
fail-closed to REJECTED. Wrong-typed/None aggregate, malformed expected digest, empty manifest correlation
id, or malformed/forbidden-token manifest metadata raise ``PaperSessionRealizedPnlEvidenceManifestError``.

SCOPE / membership boundary: like the aggregate it records, this manifest does **not** prove that each
rolled-up realized event belongs to a specific episode of its session (no shared identifier exists to
cross-check). Event-to-episode membership is intentionally NOT claimed here (no false membership proof).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_session_realized_pnl_aggregate import (
    PaperSessionRealizedPnlAggregate,
    paper_session_realized_pnl_aggregate_to_dict,
)

_MANIFEST_SCHEMA_VERSION = "paper-session-realized-pnl-evidence-manifest.v1"
_EXPECTED_AGGREGATE_SCHEMA_VERSION = "paper-session-realized-pnl-aggregate.v1"
_EXPECTED_AGGREGATE_STATUS = "COMPUTED"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Strict decimal-string grammar (mirrors the aggregate): optional sign, no leading zeros (except a bare
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

# Aggregate payload fields the manifest binds/cross-checks (exact plain primitives after canonicalization).
_DIGEST_TUPLE_KEYS = (
    "session_sequence_digests",
    "bridge_digests",
    "rollup_digests",
    "source_event_digests",
    "fill_simulation_result_digests",
    "position_transition_digests",
)
# Hard-safety aggregate attestations that MUST be False for a paper-only aggregate to be admissible.
_AGGREGATE_FALSE_FLAGS = (
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


class PaperSessionRealizedPnlEvidenceManifestError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed/None aggregate, bad correlation id, bad metadata)."""


class PaperSessionRealizedPnlEvidenceManifestStatus(str, Enum):
    """Terminal readiness of the realized-PnL evidence manifest. Never an execution / capital / live action."""

    READY = "READY"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperSessionRealizedPnlEvidenceManifest:
    """Deterministic, immutable digest-bound evidence manifest over one paper realized-PnL aggregate.

    Records the aggregate's gross totals / counts / provenance+action digest chains by digest and a terminal
    readiness. Gross only; never computes fills, positions, fees, unrealized/total PnL, equity, capital,
    margin, or balances; reconstructs no upstream bridge. Does NOT assert per-episode membership (see module
    docstring). ``paper_only`` / ``gross_only`` are True; every hard-safety attestation is False. PAPER ONLY.
    """

    schema_version: str
    status: PaperSessionRealizedPnlEvidenceManifestStatus
    ready: bool
    aggregate_id: str
    aggregate_digest: str
    expected_aggregate_digest: str
    market_symbol: str
    session_bridge_count: int
    session_sequence_digests: tuple[str, ...]
    bridge_digests: tuple[str, ...]
    rollup_digests: tuple[str, ...]
    source_event_digests: tuple[str, ...]
    fill_simulation_result_digests: tuple[str, ...]
    position_transition_digests: tuple[str, ...]
    episode_count_total: int
    event_count: int
    computed_event_count: int
    no_realized_event_count: int
    closed_units_total: str
    realized_pnl_total: str
    rejection_reasons: tuple[str, ...]
    insufficient_evidence_reasons: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    manifest_digest: str
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
        raise PaperSessionRealizedPnlEvidenceManifestError(
            "paper_session_realized_pnl_evidence_manifest:metadata_malformed"
        )
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperSessionRealizedPnlEvidenceManifestError(
                "paper_session_realized_pnl_evidence_manifest:metadata_malformed"
            )
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


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


def _capture_aggregate_snapshot(aggregate: PaperSessionRealizedPnlAggregate) -> dict[str, object] | None:
    """Serialize the aggregate via the PUBLIC serializer EXACTLY ONCE and ROUND-TRIP through canonical JSON.

    The aggregate object is read once here and never again — neither for digest, identity, totals, counts,
    flags, nor metadata. The returned dict is exact plain primitives (plain ``str``/builtins — no ``str``
    subclass with custom hash/equality), so every manifest-bound field, the aggregate-digest recompute, and
    the uniqueness set membership all derive from this single snapshot (closing a TOCTOU where a second
    serialization/read could diverge from the bound payload). Returns ``None`` (fail-closed) on any
    serialization failure.
    """
    try:
        raw = paper_session_realized_pnl_aggregate_to_dict(aggregate)
        payload = json.loads(json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
    except Exception:  # noqa: BLE001 - any serialization failure is a fail-closed rejection, not a crash
        return None
    return payload if isinstance(payload, dict) else None


def _recompute_aggregate_digest(snapshot: dict[str, object]) -> str | None:
    """Recompute the aggregate self-digest FROM the single captured snapshot (no second aggregate read).

    Uses the same contract as the aggregate module's PUBLIC ``paper_session_realized_pnl_aggregate_digest``:
    SHA-256 over canonical JSON of the aggregate payload EXCLUDING the ``aggregate_digest`` self field.
    Recomputing from the snapshot (rather than re-serializing the aggregate) guarantees the digest proven
    here covers the exact bytes the manifest binds. Returns ``None`` (fail-closed) on a non-serializable
    snapshot.
    """
    digest_input = {key: value for key, value in snapshot.items() if key != "aggregate_digest"}
    try:
        return _canonical_digest(digest_input)
    except (TypeError, ValueError):
        return None


def _aggregate_internal_scope_reasons(snapshot: dict[str, object]) -> list[str]:
    """Structurally re-prove and scope-guard the aggregate's INTERNAL ``correlation_id`` / ``metadata`` /
    ``reason_codes`` from the single normalized snapshot; return fail-closed REJECTED reason codes.

    The triple-digest binding only proves the snapshot is self-consistent and matches the caller's expected
    anchor — a forged-but-self-consistent aggregate can still carry a non-string ``correlation_id``,
    nested/non-string ``metadata``, or a non-empty ``reason_codes`` that the bound digest covers. A naive scan
    of only direct string values would skip those and let the manifest READY. Each field is therefore
    re-proven against the aggregate's serialization contract (correlation id = exact non-empty ``str``;
    metadata = list of exact two-item ``[str, str]`` pairs with unique keys; reason_codes = present and empty
    for a COMPUTED aggregate) and scope-scanned. Malformed shape is itself a rejection — nested values are
    never stringified to be scanned. Returns reason codes (never raises — these are snapshot-internal, not
    call-level input).
    """
    reasons: list[str] = []

    correlation = snapshot.get("correlation_id")
    if type(correlation) is not str or correlation.strip() == "":
        reasons.append("paper_session_realized_pnl_evidence_manifest:aggregate_correlation_id_invalid")
    elif _has_scope_violation(correlation):
        reasons.append("paper_session_realized_pnl_evidence_manifest:aggregate_scope_violation")

    metadata = snapshot.get("metadata")
    if not isinstance(metadata, list):
        reasons.append("paper_session_realized_pnl_evidence_manifest:aggregate_metadata_malformed")
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
            reasons.append("paper_session_realized_pnl_evidence_manifest:aggregate_metadata_malformed")
        if scope_violation:
            reasons.append("paper_session_realized_pnl_evidence_manifest:aggregate_scope_violation")

    reason_codes = snapshot.get("reason_codes")
    if not isinstance(reason_codes, list) or reason_codes:
        reasons.append("paper_session_realized_pnl_evidence_manifest:aggregate_reason_codes_invalid")

    return reasons


def build_paper_session_realized_pnl_evidence_manifest(
    aggregate: PaperSessionRealizedPnlAggregate,
    *,
    expected_aggregate_digest: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSessionRealizedPnlEvidenceManifest:
    """Record one paper realized-PnL aggregate as a deterministic, digest-bound evidence manifest.

    ``aggregate`` must be a ``PaperSessionRealizedPnlAggregate`` and ``expected_aggregate_digest`` an exact
    plain 64-lowercase-hex ``str`` — the caller's INDEPENDENT provenance/trust anchor for the aggregate. A
    wrong-typed/None aggregate, a malformed expected digest, an empty ``correlation_id``, or non
    ``Mapping[str, str]`` / forbidden-token metadata raises ``PaperSessionRealizedPnlEvidenceManifestError``.

    The aggregate is captured EXACTLY ONCE (PUBLIC serializer + canonical-JSON round-trip into exact plain
    primitives); the aggregate self-digest is recomputed FROM that single snapshot (never via a second
    aggregate read) and must equal BOTH the snapshot's bound ``aggregate_digest`` AND
    ``expected_aggregate_digest`` (which is recorded on every built manifest and bound into the manifest
    digest). The manifest is READY only when that triple-digest binding holds, the snapshot is a ``COMPUTED``
    paper-safe aggregate (expected schema, ``aggregate_computed`` True, all hard-safety flags False), its
    scope-guarded id/symbol and structurally re-proven internal ``correlation_id`` (exact non-empty ``str``)
    / ``metadata`` (exact two-item string pairs, unique keys) / ``reason_codes`` (present and empty) are
    clean, its bound digest chains are canonical 64-hex with coherent counts/uniqueness, its gross totals are
    canonical finite decimals (``closed_units_total`` >= 0), and it has at least one COMPUTED realized event;
    a consistent aggregate with zero computed realized events is INSUFFICIENT_EVIDENCE; every other outcome
    maps fail-closed to REJECTED.

    Trust boundary: ``expected_aggregate_digest`` is the caller's independent anchor — the manifest does NOT
    reconstruct upstream bridges and does NOT independently re-derive the aggregate payload, so a fully
    self-consistent aggregate paired with its own (matching) expected digest is recorded on the caller's
    authority. Deterministic and immutable; no wall-clock/random/IO; gross only.
    """
    if not isinstance(aggregate, PaperSessionRealizedPnlAggregate):
        raise PaperSessionRealizedPnlEvidenceManifestError(
            "paper_session_realized_pnl_evidence_manifest:aggregate_malformed"
        )
    if not _is_hex64_string(expected_aggregate_digest):
        raise PaperSessionRealizedPnlEvidenceManifestError(
            "paper_session_realized_pnl_evidence_manifest:expected_aggregate_digest_invalid"
        )
    if not _is_non_empty_string(correlation_id):
        raise PaperSessionRealizedPnlEvidenceManifestError(
            "paper_session_realized_pnl_evidence_manifest:correlation_id_invalid"
        )
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperSessionRealizedPnlEvidenceManifestError(
            "paper_session_realized_pnl_evidence_manifest:scope_violation"
        )

    hard: list[str] = []
    insufficient: list[str] = []

    snapshot = _capture_aggregate_snapshot(aggregate)
    # Defaults bound even when the aggregate is unserializable/malformed (manifest still records REJECTED).
    aggregate_id = ""
    aggregate_digest = ""
    market_symbol = ""
    chains: dict[str, tuple[str, ...]] = dict.fromkeys(_DIGEST_TUPLE_KEYS, ())
    session_bridge_count = 0
    episode_count_total = 0
    event_count = 0
    computed_event_count = 0
    no_realized_event_count = 0
    closed_units_total = "0"
    realized_pnl_total = "0"

    if snapshot is None:
        hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_payload_invalid")
    else:
        aggregate_id = snapshot.get("aggregate_id") if isinstance(snapshot.get("aggregate_id"), str) else ""
        aggregate_digest = snapshot.get("aggregate_digest") if isinstance(snapshot.get("aggregate_digest"), str) else ""
        market_symbol = snapshot.get("market_symbol") if isinstance(snapshot.get("market_symbol"), str) else ""

        # Single-snapshot digest re-proof: recompute the aggregate digest from THIS snapshot (no second
        # read) and require it to equal both the snapshot's bound digest and the caller's expected anchor.
        recomputed = _recompute_aggregate_digest(snapshot)
        if not _is_hex64_string(aggregate_digest):
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_digest_invalid")
        elif recomputed is None or recomputed != aggregate_digest:
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_digest_mismatch")
        elif expected_aggregate_digest != recomputed:
            hard.append("paper_session_realized_pnl_evidence_manifest:expected_aggregate_digest_mismatch")

        if snapshot.get("schema_version") != _EXPECTED_AGGREGATE_SCHEMA_VERSION:
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_schema_invalid")
        if snapshot.get("status") != _EXPECTED_AGGREGATE_STATUS:
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_status_invalid")
        if snapshot.get("aggregate_computed") is not True:
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_not_computed")
        if snapshot.get("paper_only") is not True or snapshot.get("gross_only") is not True:
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_safety_violation")
        if any(snapshot.get(flag) is not False for flag in _AGGREGATE_FALSE_FLAGS):
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_safety_violation")

        if not _is_non_empty_string(aggregate_id) or not _is_non_empty_string(market_symbol):
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_id_or_symbol_invalid")
        if _has_scope_violation(aggregate_id, market_symbol):
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_scope_violation")
        # Structurally re-prove + scope-guard the aggregate's INTERNAL correlation_id / metadata /
        # reason_codes from the single snapshot: the bound digest covers them, but a non-string id, a
        # nested/non-string metadata value, or a non-empty reason_codes would slip past a naive
        # direct-string scan and reach READY. Snapshot-internal violations map fail-closed to REJECTED.
        hard.extend(_aggregate_internal_scope_reasons(snapshot))

        for key in _DIGEST_TUPLE_KEYS:
            value = snapshot.get(key)
            if not isinstance(value, list) or any(not _is_hex64_string(item) for item in value):
                hard.append("paper_session_realized_pnl_evidence_manifest:digest_chain_malformed")
                chains[key] = ()
            else:
                chains[key] = tuple(value)

        counts = {
            name: snapshot.get(name)
            for name in (
                "session_bridge_count",
                "episode_count_total",
                "event_count",
                "computed_event_count",
                "no_realized_event_count",
            )
        }
        if any(not _is_int(value) or value < 0 for value in counts.values()):
            hard.append("paper_session_realized_pnl_evidence_manifest:count_malformed")
        else:
            session_bridge_count = counts["session_bridge_count"]
            episode_count_total = counts["episode_count_total"]
            event_count = counts["event_count"]
            computed_event_count = counts["computed_event_count"]
            no_realized_event_count = counts["no_realized_event_count"]
            hard.extend(
                _count_chain_violations(
                    session_bridge_count=session_bridge_count,
                    episode_count_total=episode_count_total,
                    event_count=event_count,
                    computed_event_count=computed_event_count,
                    no_realized_event_count=no_realized_event_count,
                    chains=chains,
                )
            )

        # Totals must be canonical finite decimal strings (rejects NaN/Infinity/sci/empty/non-canonical);
        # closed units must be non-negative. Canonical zero "0" is preserved.
        realized_candidate = snapshot.get("realized_pnl_total")
        closed_candidate = snapshot.get("closed_units_total")
        if _canonical_decimal(realized_candidate) is None:
            hard.append("paper_session_realized_pnl_evidence_manifest:realized_pnl_total_malformed")
        elif isinstance(realized_candidate, str):
            realized_pnl_total = realized_candidate
        closed_value = _canonical_decimal(closed_candidate)
        if closed_value is None or closed_value < 0:
            hard.append("paper_session_realized_pnl_evidence_manifest:closed_units_total_invalid")
        elif isinstance(closed_candidate, str):
            closed_units_total = closed_candidate

        if not hard and computed_event_count == 0:
            insufficient.append("paper_session_realized_pnl_evidence_manifest:no_computed_realized_events")

    rejection_reasons = tuple(sorted(set(hard)))
    insufficient_reasons = tuple(sorted(set(insufficient)))
    if rejection_reasons:
        status = PaperSessionRealizedPnlEvidenceManifestStatus.REJECTED
    elif insufficient_reasons:
        status = PaperSessionRealizedPnlEvidenceManifestStatus.INSUFFICIENT_EVIDENCE
    else:
        status = PaperSessionRealizedPnlEvidenceManifestStatus.READY

    return _finalize_manifest(
        status=status,
        aggregate_id=aggregate_id,
        aggregate_digest=aggregate_digest,
        expected_aggregate_digest=expected_aggregate_digest,
        market_symbol=market_symbol,
        session_bridge_count=session_bridge_count,
        session_sequence_digests=chains["session_sequence_digests"],
        bridge_digests=chains["bridge_digests"],
        rollup_digests=chains["rollup_digests"],
        source_event_digests=chains["source_event_digests"],
        fill_simulation_result_digests=chains["fill_simulation_result_digests"],
        position_transition_digests=chains["position_transition_digests"],
        episode_count_total=episode_count_total,
        event_count=event_count,
        computed_event_count=computed_event_count,
        no_realized_event_count=no_realized_event_count,
        closed_units_total=closed_units_total,
        realized_pnl_total=realized_pnl_total,
        rejection_reasons=rejection_reasons,
        insufficient_evidence_reasons=insufficient_reasons,
        correlation_id=correlation_id,
        metadata=metadata_pairs,
    )


def _count_chain_violations(
    *,
    session_bridge_count: int,
    episode_count_total: int,
    event_count: int,
    computed_event_count: int,
    no_realized_event_count: int,
    chains: dict[str, tuple[str, ...]],
) -> list[str]:
    """Cross-check the aggregate's bound counts against its digest-chain lengths, coherence, and uniqueness."""
    reasons: list[str] = []
    bridge_scoped = ("session_sequence_digests", "bridge_digests", "rollup_digests")
    event_scoped = ("source_event_digests", "fill_simulation_result_digests", "position_transition_digests")
    if session_bridge_count < 1:
        reasons.append("paper_session_realized_pnl_evidence_manifest:bridge_count_invalid")
    if any(len(chains[key]) != session_bridge_count for key in bridge_scoped):
        reasons.append("paper_session_realized_pnl_evidence_manifest:bridge_count_mismatch")
    if any(len(chains[key]) != event_count for key in event_scoped):
        reasons.append("paper_session_realized_pnl_evidence_manifest:event_count_mismatch")
    if computed_event_count + no_realized_event_count != event_count:
        reasons.append("paper_session_realized_pnl_evidence_manifest:event_count_incoherent")
    # Each real bridge contributes >=1 episode and >=1 event, so both totals must dominate the bridge count.
    if episode_count_total < session_bridge_count or event_count < session_bridge_count:
        reasons.append("paper_session_realized_pnl_evidence_manifest:count_incoherent")
    # Uniqueness the aggregate already enforces must not be reintroduced here (rollup_digests are not unique).
    for key in ("bridge_digests", "session_sequence_digests", *event_scoped):
        chain = chains[key]
        if len(set(chain)) != len(chain):
            reasons.append("paper_session_realized_pnl_evidence_manifest:duplicate_digest_in_chain")
            break
    return reasons


def _finalize_manifest(
    *,
    status: PaperSessionRealizedPnlEvidenceManifestStatus,
    aggregate_id: str,
    aggregate_digest: str,
    expected_aggregate_digest: str,
    market_symbol: str,
    session_bridge_count: int,
    session_sequence_digests: tuple[str, ...],
    bridge_digests: tuple[str, ...],
    rollup_digests: tuple[str, ...],
    source_event_digests: tuple[str, ...],
    fill_simulation_result_digests: tuple[str, ...],
    position_transition_digests: tuple[str, ...],
    episode_count_total: int,
    event_count: int,
    computed_event_count: int,
    no_realized_event_count: int,
    closed_units_total: str,
    realized_pnl_total: str,
    rejection_reasons: tuple[str, ...],
    insufficient_evidence_reasons: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperSessionRealizedPnlEvidenceManifest:
    fields: dict[str, object] = {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        "status": status,
        "ready": status is PaperSessionRealizedPnlEvidenceManifestStatus.READY,
        "aggregate_id": aggregate_id,
        "aggregate_digest": aggregate_digest,
        "expected_aggregate_digest": expected_aggregate_digest,
        "market_symbol": market_symbol,
        "session_bridge_count": session_bridge_count,
        "session_sequence_digests": session_sequence_digests,
        "bridge_digests": bridge_digests,
        "rollup_digests": rollup_digests,
        "source_event_digests": source_event_digests,
        "fill_simulation_result_digests": fill_simulation_result_digests,
        "position_transition_digests": position_transition_digests,
        "episode_count_total": episode_count_total,
        "event_count": event_count,
        "computed_event_count": computed_event_count,
        "no_realized_event_count": no_realized_event_count,
        "closed_units_total": closed_units_total,
        "realized_pnl_total": realized_pnl_total,
        "rejection_reasons": rejection_reasons,
        "insufficient_evidence_reasons": insufficient_evidence_reasons,
        "correlation_id": correlation_id,
        "metadata": metadata,
    }
    seed = PaperSessionRealizedPnlEvidenceManifest(manifest_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_session_realized_pnl_evidence_manifest_digest(seed))


def _replace_digest(
    manifest: PaperSessionRealizedPnlEvidenceManifest, digest: str
) -> PaperSessionRealizedPnlEvidenceManifest:
    fields = _manifest_fields(manifest)
    fields["manifest_digest"] = digest
    return PaperSessionRealizedPnlEvidenceManifest(**fields)  # type: ignore[arg-type]


def _manifest_fields(manifest: PaperSessionRealizedPnlEvidenceManifest) -> dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "status": manifest.status,
        "ready": manifest.ready,
        "aggregate_id": manifest.aggregate_id,
        "aggregate_digest": manifest.aggregate_digest,
        "expected_aggregate_digest": manifest.expected_aggregate_digest,
        "market_symbol": manifest.market_symbol,
        "session_bridge_count": manifest.session_bridge_count,
        "session_sequence_digests": manifest.session_sequence_digests,
        "bridge_digests": manifest.bridge_digests,
        "rollup_digests": manifest.rollup_digests,
        "source_event_digests": manifest.source_event_digests,
        "fill_simulation_result_digests": manifest.fill_simulation_result_digests,
        "position_transition_digests": manifest.position_transition_digests,
        "episode_count_total": manifest.episode_count_total,
        "event_count": manifest.event_count,
        "computed_event_count": manifest.computed_event_count,
        "no_realized_event_count": manifest.no_realized_event_count,
        "closed_units_total": manifest.closed_units_total,
        "realized_pnl_total": manifest.realized_pnl_total,
        "rejection_reasons": manifest.rejection_reasons,
        "insufficient_evidence_reasons": manifest.insufficient_evidence_reasons,
        "correlation_id": manifest.correlation_id,
        "metadata": manifest.metadata,
    }


def _manifest_payload_from(manifest: PaperSessionRealizedPnlEvidenceManifest) -> dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "status": manifest.status.value,
        "ready": manifest.ready,
        "aggregate_id": manifest.aggregate_id,
        "aggregate_digest": manifest.aggregate_digest,
        "expected_aggregate_digest": manifest.expected_aggregate_digest,
        "market_symbol": manifest.market_symbol,
        "session_bridge_count": manifest.session_bridge_count,
        "session_sequence_digests": list(manifest.session_sequence_digests),
        "bridge_digests": list(manifest.bridge_digests),
        "rollup_digests": list(manifest.rollup_digests),
        "source_event_digests": list(manifest.source_event_digests),
        "fill_simulation_result_digests": list(manifest.fill_simulation_result_digests),
        "position_transition_digests": list(manifest.position_transition_digests),
        "episode_count_total": manifest.episode_count_total,
        "event_count": manifest.event_count,
        "computed_event_count": manifest.computed_event_count,
        "no_realized_event_count": manifest.no_realized_event_count,
        "closed_units_total": manifest.closed_units_total,
        "realized_pnl_total": manifest.realized_pnl_total,
        "rejection_reasons": list(manifest.rejection_reasons),
        "insufficient_evidence_reasons": list(manifest.insufficient_evidence_reasons),
        "correlation_id": manifest.correlation_id,
        "metadata": [list(pair) for pair in manifest.metadata],
        "paper_only": manifest.paper_only,
        "gross_only": manifest.gross_only,
        "fees_included": manifest.fees_included,
        "unrealized_pnl_included": manifest.unrealized_pnl_included,
        "total_pnl_computed": manifest.total_pnl_computed,
        "equity_or_capital_computed": manifest.equity_or_capital_computed,
        "capital_reserved": manifest.capital_reserved,
        "capital_mutated": manifest.capital_mutated,
        "balance_mutated": manifest.balance_mutated,
        "live_position_mutated": manifest.live_position_mutated,
        "real_money_enabled": manifest.real_money_enabled,
        "real_orders_enabled": manifest.real_orders_enabled,
        "order_routed": manifest.order_routed,
        "venue_order_id_created": manifest.venue_order_id_created,
        "exchange_order_id_created": manifest.exchange_order_id_created,
        "client_order_id_created": manifest.client_order_id_created,
        "route_id_created": manifest.route_id_created,
        "execution_instruction_created": manifest.execution_instruction_created,
        "live_api_called": manifest.live_api_called,
        "scheduler_enabled": manifest.scheduler_enabled,
        "auto_loop_enabled": manifest.auto_loop_enabled,
        "connector_invoked": manifest.connector_invoked,
    }


def paper_session_realized_pnl_evidence_manifest_to_dict(
    manifest: PaperSessionRealizedPnlEvidenceManifest,
) -> dict[str, object]:
    """Canonical, JSON-ready mapping for an evidence manifest (deterministic shape, includes self-digest)."""
    payload = _manifest_payload_from(manifest)
    payload["manifest_digest"] = manifest.manifest_digest
    return payload


def paper_session_realized_pnl_evidence_manifest_digest(
    manifest: PaperSessionRealizedPnlEvidenceManifest,
) -> str:
    """Recompute the canonical manifest digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_manifest_payload_from(manifest))


__all__ = [
    "PaperSessionRealizedPnlEvidenceManifest",
    "PaperSessionRealizedPnlEvidenceManifestError",
    "PaperSessionRealizedPnlEvidenceManifestStatus",
    "build_paper_session_realized_pnl_evidence_manifest",
    "paper_session_realized_pnl_evidence_manifest_digest",
    "paper_session_realized_pnl_evidence_manifest_to_dict",
]
