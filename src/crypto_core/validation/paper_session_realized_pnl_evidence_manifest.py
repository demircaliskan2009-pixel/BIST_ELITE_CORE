"""Paper session realized-PnL evidence manifest — deterministic, paper-only record of an admitted
realized-PnL aggregate evidence chain.

A small, immutable, fail-closed *evidence manifest* that records — by digest — the provenance/action chain
already proven by one ``PaperSessionRealizedPnlAggregate`` (the artifact merged in PR #287). It is the
first consumer of that aggregate: it does **not** recompute fills, positions, transitions, per-fill
realized PnL, sessions, bridges, rollups, or the aggregate itself, and it does **not** reconstruct upstream
bridges (the aggregate already re-proves them transitively). It is a *consumer / cross-check* artifact, not
a second builder: it re-proves the supplied aggregate's self-digest via the PUBLIC
``paper_session_realized_pnl_aggregate_digest``, binds the aggregate's gross totals / counts / digest chains
into one frozen, digest-bound manifest, and cross-checks the aggregate's internal count/chain consistency.

Gross only: it carries no fees, no unrealized PnL, no total PnL, no equity/capital/margin/balance; it
reserves/mutates no capital; routes no order; creates no venue/exchange/client order id / route id /
execution instruction; calls no live/private API; schedules nothing; runs no auto-loop; performs no
wall-clock/random/IO/persistence/network; and touches no
connector/scheduler/runtime/venue/execution/service/session/data/portfolio/orchestrator/temporal surface,
no Deribit, no BIST.

Re-proof + canonicalization: the supplied aggregate is serialized once via the PUBLIC
``paper_session_realized_pnl_aggregate_to_dict`` and ROUND-TRIPPED through canonical JSON, so every bound
value is an exact plain primitive (plain ``str``/builtins — no ``str`` subclass with custom hash/equality);
the bound ``aggregate_digest`` must equal the PUBLIC recomputed digest, and the aggregate's status must be
``COMPUTED`` with paper-safe attestations. READY requires a consistent aggregate with at least one COMPUTED
realized event; a structurally valid aggregate with zero computed realized events is INSUFFICIENT_EVIDENCE;
any digest mismatch / count or chain inconsistency / malformed digest / safety or scope violation is
REJECTED. Wrong-typed/None aggregate, empty correlation id, malformed/forbidden-token metadata raise
``PaperSessionRealizedPnlEvidenceManifestError``.

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
from enum import Enum

from crypto_core.validation.paper_session_realized_pnl_aggregate import (
    PaperSessionRealizedPnlAggregate,
    paper_session_realized_pnl_aggregate_digest,
    paper_session_realized_pnl_aggregate_to_dict,
)

_MANIFEST_SCHEMA_VERSION = "paper-session-realized-pnl-evidence-manifest.v1"
_EXPECTED_AGGREGATE_STATUS = "COMPUTED"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

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


def _canonical_aggregate_payload(aggregate: PaperSessionRealizedPnlAggregate) -> dict[str, object] | None:
    """Serialize the aggregate via the PUBLIC serializer and ROUND-TRIP through canonical JSON.

    Returns an exact plain-primitive dict (plain ``str``/builtins — no ``str`` subclass with custom
    hash/equality), so the manifest binds/cross-checks exact primitives and its uniqueness set membership
    uses standard string hashing. Returns ``None`` (fail-closed) if the aggregate cannot be canonically
    serialized. The aggregate object itself is never read for identity after this single capture.
    """
    try:
        raw = paper_session_realized_pnl_aggregate_to_dict(aggregate)
        payload = json.loads(json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
    except Exception:  # noqa: BLE001 - any serialization failure is a fail-closed rejection, not a crash
        return None
    return payload if isinstance(payload, dict) else None


def build_paper_session_realized_pnl_evidence_manifest(
    aggregate: PaperSessionRealizedPnlAggregate,
    *,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSessionRealizedPnlEvidenceManifest:
    """Record one paper realized-PnL aggregate as a deterministic, digest-bound evidence manifest.

    ``aggregate`` must be a ``PaperSessionRealizedPnlAggregate``; a wrong-typed/None aggregate, an empty
    ``correlation_id``, or non ``Mapping[str, str]`` / forbidden-token metadata raises
    ``PaperSessionRealizedPnlEvidenceManifestError``. The aggregate is canonicalized once (PUBLIC serializer
    + canonical-JSON round-trip) and its self-digest re-proven via the PUBLIC
    ``paper_session_realized_pnl_aggregate_digest``. The manifest is READY only when the aggregate's status
    is ``COMPUTED``, its paper-safe attestations hold, its bound digest chains are canonical 64-hex with
    counts/uniqueness consistent, and it has at least one COMPUTED realized event; a consistent aggregate
    with zero computed realized events is INSUFFICIENT_EVIDENCE; every other outcome maps fail-closed to
    REJECTED. Deterministic and immutable: no reconstruction of upstream bridges, no wall-clock/random/IO,
    gross only.
    """
    if not isinstance(aggregate, PaperSessionRealizedPnlAggregate):
        raise PaperSessionRealizedPnlEvidenceManifestError(
            "paper_session_realized_pnl_evidence_manifest:aggregate_malformed"
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

    payload = _canonical_aggregate_payload(aggregate)
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

    if payload is None:
        hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_payload_invalid")
    else:
        aggregate_id = payload.get("aggregate_id") if isinstance(payload.get("aggregate_id"), str) else ""
        aggregate_digest = payload.get("aggregate_digest") if isinstance(payload.get("aggregate_digest"), str) else ""
        market_symbol = payload.get("market_symbol") if isinstance(payload.get("market_symbol"), str) else ""

        # Digest re-proof: the bound aggregate_digest must equal the PUBLIC recomputed digest.
        try:
            expected_digest = paper_session_realized_pnl_aggregate_digest(aggregate)
        except Exception:  # noqa: BLE001 - unrecomputable digest is a fail-closed rejection
            expected_digest = None
        if not _is_hex64_string(aggregate_digest):
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_digest_invalid")
        elif expected_digest is None or aggregate_digest != expected_digest:
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_digest_mismatch")

        if payload.get("status") != _EXPECTED_AGGREGATE_STATUS:
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_status_invalid")
        if payload.get("paper_only") is not True or payload.get("gross_only") is not True:
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_safety_violation")
        if any(payload.get(flag) is not False for flag in _AGGREGATE_FALSE_FLAGS):
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_safety_violation")

        if not _is_non_empty_string(market_symbol) or _has_scope_violation(market_symbol, aggregate_id):
            hard.append("paper_session_realized_pnl_evidence_manifest:aggregate_scope_or_symbol_invalid")

        for key in _DIGEST_TUPLE_KEYS:
            value = payload.get(key)
            if not isinstance(value, list) or any(not _is_hex64_string(item) for item in value):
                hard.append("paper_session_realized_pnl_evidence_manifest:digest_chain_malformed")
                chains[key] = ()
            else:
                chains[key] = tuple(value)

        counts = {
            name: payload.get(name)
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
                    event_count=event_count,
                    computed_event_count=computed_event_count,
                    no_realized_event_count=no_realized_event_count,
                    chains=chains,
                )
            )

        for total_key in ("closed_units_total", "realized_pnl_total"):
            if not _is_non_empty_string(payload.get(total_key)):
                hard.append("paper_session_realized_pnl_evidence_manifest:total_malformed")
        closed_units_total = (
            payload.get("closed_units_total") if _is_non_empty_string(payload.get("closed_units_total")) else "0"
        )
        realized_pnl_total = (
            payload.get("realized_pnl_total") if _is_non_empty_string(payload.get("realized_pnl_total")) else "0"
        )

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
    event_count: int,
    computed_event_count: int,
    no_realized_event_count: int,
    chains: dict[str, tuple[str, ...]],
) -> list[str]:
    """Cross-check the aggregate's bound counts against its digest-chain lengths and uniqueness."""
    reasons: list[str] = []
    bridge_scoped = ("session_sequence_digests", "bridge_digests", "rollup_digests")
    event_scoped = ("source_event_digests", "fill_simulation_result_digests", "position_transition_digests")
    if any(len(chains[key]) != session_bridge_count for key in bridge_scoped):
        reasons.append("paper_session_realized_pnl_evidence_manifest:bridge_count_mismatch")
    if any(len(chains[key]) != event_count for key in event_scoped):
        reasons.append("paper_session_realized_pnl_evidence_manifest:event_count_mismatch")
    if computed_event_count + no_realized_event_count != event_count:
        reasons.append("paper_session_realized_pnl_evidence_manifest:event_count_incoherent")
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
