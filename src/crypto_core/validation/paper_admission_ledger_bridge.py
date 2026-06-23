"""Paper admission ledger bridge — deterministic, paper-only, fail-closed append of a paper evidence
admission record (with proven episode chain lineage) into the EXISTING append-only ``EvidenceJournal``.

Phase-map slice 4 (``docs/crypto_core/paper_trading_phase_map.md`` §7.4): *append admission records to an
existing evidence journal/store — no new store proliferation.* This bridge **reuses** the existing
``crypto_core.audit.evidence_journal.EvidenceJournal`` (it does NOT invent a parallel store/ledger): it
consumes an already-built ``PaperEvidenceAdmissionRecord`` (the realized-PnL evidence admission decision),
the ``PaperSessionRealizedPnlEvidenceManifest`` that record admitted, and the deterministic
``PaperEndToEndEpisode`` (intent → fill → position → realized-PnL) being journaled; it re-proves them at their
digest trust boundaries, proves the record↔episode chain lineage, and — only when everything re-proves —
appends ONE deterministic, token-safe, digest-bound entry to the journal. It is a *bridge / probe*, not an
engine: it runs no backtest, recomputes no fills/positions/PnL, reconstructs no manifest/aggregate, and adds
no runtime/persistence/scheduler/execution/venue path. It journals already-produced artifacts; it never
builds, executes, routes, schedules, connects, or mutates anything beyond appending one journal entry.

Strong record↔episode chain lineage (closes connector P2 ``record_to_episode_lineage_insufficient``):
weak shared identity (market_symbol / correlation_id / caller episode_id+run_id) is NOT sufficient — a
digest-valid ADMITTED record from one aggregate/session and a digest-valid READY episode from a *different*
realized-PnL chain could otherwise bind. READY now additionally requires a genuine shared-digest membership
proof using EXISTING contracts: the admitted manifest's ``source_event_digests`` (each computed with the SAME
contract as the PUBLIC ``paper_realized_pnl_event_digest``) MUST contain the episode's
``realized_pnl_event_digest`` (the episode's own bound realized-PnL event self-digest). That proves the
admitted evidence chain *contains the exact realized event the episode produced* — record → manifest (digest
binding: ``manifest.manifest_digest == record.manifest_digest`` and ``manifest.aggregate_digest ==
record.aggregate_digest``, manifest self-digest re-proven) and manifest → episode (event-digest membership).
No fake equality between distinct contracts; no invented mapping; if membership cannot be proven, fail closed
with ``record_episode_lineage_unproven`` and do NOT produce READY for episode-bound journal admission.

Why a curated journal payload (not the raw artifact dict): the journal's scope guard rejects forbidden
tokens, and ``paper_evidence_admission_record_to_dict`` carries hard-safety attestation key NAMES that
themselves contain forbidden tokens (``order_routed`` / ``scheduler_enabled`` / ``auto_loop_enabled`` /
``live_api_called`` / ``venue_order_id_created`` / …). Appending that raw dict would fail the journal guard.
So the bridge appends a small, token-safe, digest-bound summary payload (statuses, bound digests incl. the
proven lineage event digest, gross audit context) — the full safety attestations live on the FROZEN bridge
artifact's own self-digest, never in the journal payload.

Fail-closed: any digest mismatch, a non-ADMITTED record, a non-READY episode/manifest, an unsafe/over-claiming
flag, an id/symbol/correlation mismatch, an unproven record↔episode lineage, a wrong prior-journal head
anchor, or a journal-level append rejection maps to a frozen REJECTED bridge artifact and the journal is left
UNCHANGED (the single append happens only after every precheck passes). Call-level malformed input
(wrong-typed journal/record/episode/manifest, malformed expected digest / prior-head anchor, empty/forbidden
ids, malformed metadata) raises ``PaperAdmissionLedgerBridgeError`` before any work. Deterministic and
immutable; no wall-clock/random/IO/network/persistence. PAPER ONLY — NOT PRDV4 Stage 4 completion, NOT
live/shadow readiness, NOT a profitability/edge proof, NOT production execution.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.audit.evidence_journal import (
    EvidenceArtifactType,
    EvidenceJournal,
    EvidenceJournalError,
)
from crypto_core.validation.paper_end_to_end_episode import (
    PaperEndToEndEpisode,
    PaperEndToEndEpisodeStatus,
    paper_end_to_end_episode_digest,
)
from crypto_core.validation.paper_evidence_admission_record import (
    PaperEvidenceAdmissionRecord,
    PaperEvidenceAdmissionStatus,
    paper_evidence_admission_record_digest,
)
from crypto_core.validation.paper_session_realized_pnl_evidence_manifest import (
    PaperSessionRealizedPnlEvidenceManifest,
    PaperSessionRealizedPnlEvidenceManifestStatus,
    paper_session_realized_pnl_evidence_manifest_digest,
)

_SCHEMA_VERSION = "paper-admission-ledger-bridge.v1"
_JOURNAL_ENTRY_PAYLOAD_SCHEMA_VERSION = "paper-admission-ledger-entry.v1"
_EXPECTED_ADMISSION_SCHEMA_VERSION = "paper-evidence-admission-record.v1"
_EXPECTED_EPISODE_SCHEMA_VERSION = "paper-end-to-end-episode.v1"
_EXPECTED_MANIFEST_SCHEMA_VERSION = "paper-session-realized-pnl-evidence-manifest.v1"
_ENTRY_TYPE = EvidenceArtifactType.PAPER_EVIDENCE_ADMISSION_RECORD

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Scope guard mirrors the sibling validation modules (word-bounded). Market-data terms scrubbed first.
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


class PaperAdmissionLedgerBridgeError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed journal/record/episode/manifest / ids / digests)."""


class PaperAdmissionLedgerBridgeStatus(str, Enum):
    """Terminal bridge verdict. Never an execution / capital / live / readiness action."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperAdmissionLedgerBridge:
    """Deterministic, immutable, digest-bound result of appending one admission record to the evidence journal.

    READY iff the admission record (ADMITTED), the admitted manifest (READY), and the episode (READY) all
    re-prove their digests, are paper-safe and non-over-claiming, agree on market/correlation/episode/run
    identity, the manifest is the one the record admitted, the episode's realized-PnL event digest is a member
    of the manifest's source-event digests (strong record↔episode chain lineage), the supplied prior-journal
    head anchor matches the journal, and exactly one token-safe entry was appended. Otherwise REJECTED with
    reason codes and the journal left unchanged. ``paper_only`` True; every safety / non-overclaim attestation
    False. PAPER ONLY — NOT PRDV4 Stage 4 completion, NOT live/shadow readiness, NOT profitability/edge proof.
    """

    schema_version: str
    status: PaperAdmissionLedgerBridgeStatus
    ready: bool
    appended: bool
    entry_type: str
    correlation_id: str
    episode_id: str
    run_id: str
    market_symbol: str
    # Admission-record provenance (re-proven, bound by value).
    admission_status: str
    admission_digest: str
    expected_admission_digest: str
    admission_correlation_id: str
    manifest_digest: str
    expected_manifest_digest: str
    manifest_status: str
    aggregate_id: str
    aggregate_digest: str
    session_bridge_count: int
    event_count: int
    computed_event_count: int
    closed_units_total: str
    realized_pnl_total: str
    # Episode provenance + proven record->episode chain lineage (re-proven, bound by value).
    episode_status: str
    episode_digest: str
    expected_episode_digest: str
    episode_run_digest: str
    order_intent_digest: str
    realized_pnl_event_digest: str
    source_event_digest_count: int
    # Journal append / ledger semantics.
    prior_journal_head_digest: str | None
    expected_prior_journal_head_digest: str | None
    prior_journal_entry_count: int
    appended_entry_seq: int
    appended_entry_digest: str
    appended_payload_digest: str
    resulting_journal_head_digest: str | None
    resulting_journal_entry_count: int
    rejection_reasons: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    ledger_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    capital_reserved: bool = False
    capital_mutated: bool = False
    balance_mutated: bool = False
    order_routed: bool = False
    venue_order_id_created: bool = False
    exchange_order_id_created: bool = False
    client_order_id_created: bool = False
    route_id_created: bool = False
    execution_instruction_created: bool = False
    execution_authorized: bool = False
    live_position_mutated: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    # Non-overclaim attestations (a READY ledger bridge proves none of these).
    prdv4_stage4_complete: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    production_execution: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    """Exact plain ``str`` (no subclass) that is non-empty after strip."""
    return type(value) is str and value.strip() != ""


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _plain_str_or_empty(value: object) -> str:
    """Return ``value`` only if it is an exact plain ``str`` (no subclass); else ``""`` (fail-closed)."""
    return value if type(value) is str else ""


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:metadata_malformed")
        pairs.append([pair[0], pair[1]])
    return pairs


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


def _record_is_paper_safe(record: PaperEvidenceAdmissionRecord) -> bool:
    return (
        record.paper_only is True
        and record.gross_only is True
        and record.fees_included is False
        and record.unrealized_pnl_included is False
        and record.total_pnl_computed is False
        and record.equity_or_capital_computed is False
        and record.capital_reserved is False
        and record.capital_mutated is False
        and record.balance_mutated is False
        and record.live_position_mutated is False
        and record.real_money_enabled is False
        and record.real_orders_enabled is False
        and record.order_routed is False
        and record.venue_order_id_created is False
        and record.exchange_order_id_created is False
        and record.client_order_id_created is False
        and record.route_id_created is False
        and record.execution_instruction_created is False
        and record.live_api_called is False
        and record.scheduler_enabled is False
        and record.auto_loop_enabled is False
        and record.connector_invoked is False
    )


def _manifest_is_paper_safe(manifest: PaperSessionRealizedPnlEvidenceManifest) -> bool:
    return (
        manifest.paper_only is True
        and manifest.gross_only is True
        and manifest.fees_included is False
        and manifest.unrealized_pnl_included is False
        and manifest.total_pnl_computed is False
        and manifest.equity_or_capital_computed is False
        and manifest.capital_reserved is False
        and manifest.capital_mutated is False
        and manifest.balance_mutated is False
        and manifest.live_position_mutated is False
        and manifest.real_money_enabled is False
        and manifest.real_orders_enabled is False
        and manifest.order_routed is False
        and manifest.venue_order_id_created is False
        and manifest.exchange_order_id_created is False
        and manifest.client_order_id_created is False
        and manifest.route_id_created is False
        and manifest.execution_instruction_created is False
        and manifest.live_api_called is False
        and manifest.scheduler_enabled is False
        and manifest.auto_loop_enabled is False
        and manifest.connector_invoked is False
    )


def _episode_is_paper_safe(episode: PaperEndToEndEpisode) -> bool:
    return (
        episode.paper_only is True
        and episode.real_orders_enabled is False
        and episode.real_money_enabled is False
        and episode.capital_reserved is False
        and episode.capital_mutated is False
        and episode.balance_mutated is False
        and episode.order_routed is False
        and episode.venue_order_id_created is False
        and episode.exchange_order_id_created is False
        and episode.client_order_id_created is False
        and episode.route_id_created is False
        and episode.execution_instruction_created is False
        and episode.execution_authorized is False
        and episode.live_position_mutated is False
        and episode.live_api_called is False
        and episode.scheduler_enabled is False
        and episode.auto_loop_enabled is False
        and episode.connector_invoked is False
        and episode.prdv4_stage4_complete is False
        and episode.live_ready is False
        and episode.shadow_ready is False
        and episode.profitability_proven is False
        and episode.edge_proven is False
        and episode.production_execution is False
    )


def _reprove_artifact_digest(*, artifact: object, recompute, stored: object, expected: str, label: str) -> str | None:
    """Re-prove an input artifact's self-digest via its PUBLIC serializer AND the caller's expected anchor.

    Returns a fail-closed reason code on any failure, else ``None``. The stored digest must be an exact plain
    lowercase-hex64 string equal BOTH to the recomputed digest and to the caller's independent ``expected``
    anchor, so a forged/foreign/tampered artifact (or a wrong expectation) can never be journaled. A
    serializer that raises is reported as ``<label>_malformed``.
    """
    try:
        recomputed = recompute(artifact)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        return f"paper_admission_ledger_bridge:{label}_malformed"
    if not _is_hex64_string(stored) or stored != recomputed or stored != expected:
        return f"paper_admission_ledger_bridge:{label}_digest_mismatch"
    return None


def _source_event_digests(manifest: PaperSessionRealizedPnlEvidenceManifest) -> frozenset[str]:
    """Exact plain hex64 source-event digests carried by the admitted manifest (others ignored, fail-closed)."""
    raw = manifest.source_event_digests
    if not isinstance(raw, tuple):
        return frozenset()
    return frozenset(item for item in raw if _is_hex64_string(item))


def _build_journal_payload(
    record: PaperEvidenceAdmissionRecord,
    episode: PaperEndToEndEpisode,
    *,
    source_event_digest_count: int,
) -> dict[str, object]:
    """Curated, token-safe, digest-bound journal payload (NOT the raw artifact dicts; see module docstring).

    Built only after every precheck passes, so the record/episode fields are already re-proven and scope-clean.
    No hard-safety attestation key names are included (their token-bearing names would trip the journal guard);
    the bound digests (incl. the proven lineage realized-PnL event digest) + statuses + gross audit context are
    sufficient provenance, and the journal recomputes the payload digest itself. Every value is an exact plain
    primitive.
    """
    return {
        "schema_version": _JOURNAL_ENTRY_PAYLOAD_SCHEMA_VERSION,
        "admission_status": _plain_str_or_empty(
            record.status.value if isinstance(record.status, PaperEvidenceAdmissionStatus) else ""
        ),
        "admitted": record.admitted is True,
        "admission_digest": _plain_str_or_empty(record.admission_digest),
        "expected_manifest_digest": _plain_str_or_empty(record.expected_manifest_digest),
        "manifest_digest": _plain_str_or_empty(record.manifest_digest),
        "aggregate_id": _plain_str_or_empty(record.aggregate_id),
        "aggregate_digest": _plain_str_or_empty(record.aggregate_digest),
        "market_symbol": _plain_str_or_empty(record.market_symbol),
        "session_bridge_count": record.session_bridge_count,
        "event_count": record.event_count,
        "computed_event_count": record.computed_event_count,
        "closed_units_total": _plain_str_or_empty(record.closed_units_total),
        "realized_pnl_total": _plain_str_or_empty(record.realized_pnl_total),
        "episode_status": _plain_str_or_empty(
            episode.status.value if isinstance(episode.status, PaperEndToEndEpisodeStatus) else ""
        ),
        "episode_ready": episode.ready is True,
        "episode_id": _plain_str_or_empty(episode.episode_id),
        "run_id": _plain_str_or_empty(episode.run_id),
        "episode_digest": _plain_str_or_empty(episode.episode_digest),
        "realized_pnl_event_digest": _plain_str_or_empty(episode.realized_pnl_event_digest),
        "source_event_digest_count": source_event_digest_count,
    }


def append_paper_admission_record_to_evidence_journal(
    journal: EvidenceJournal,
    record: PaperEvidenceAdmissionRecord,
    episode: PaperEndToEndEpisode,
    manifest: PaperSessionRealizedPnlEvidenceManifest,
    *,
    expected_admission_digest: str,
    expected_episode_digest: str,
    expected_prior_journal_head_digest: str | None,
    episode_id: str,
    run_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperAdmissionLedgerBridge:
    """Append an ADMITTED ``record`` (with proven ``episode`` chain lineage) into the EXISTING ``journal``.

    ``journal`` must be an ``EvidenceJournal``, ``record`` a ``PaperEvidenceAdmissionRecord``, ``episode`` a
    ``PaperEndToEndEpisode``, ``manifest`` the ``PaperSessionRealizedPnlEvidenceManifest`` the record admitted;
    ``expected_admission_digest`` / ``expected_episode_digest`` exact plain 64-lowercase-hex ``str`` (the
    caller's INDEPENDENT anchors); ``expected_prior_journal_head_digest`` either ``None`` (empty journal) or
    hex64; ``episode_id`` / ``run_id`` / ``correlation_id`` exact plain non-empty ``str``; ``metadata``
    ``Mapping[str, str]`` or ``None``. A wrong type, malformed digest/anchor, empty id, a forbidden
    BIST/live/order token, or malformed metadata raises ``PaperAdmissionLedgerBridgeError`` before any work.

    READY only when: each artifact re-digests to its stored digest AND (record/episode) the caller's expected
    anchor; the record is ADMITTED + paper-safe; the episode is READY + paper-safe + non-over-claiming; the
    manifest is the one the record admitted (``manifest.manifest_digest == record.manifest_digest`` and
    ``manifest.aggregate_digest == record.aggregate_digest``, manifest self-digest re-proven) + READY +
    paper-safe; record/manifest/episode agree on ``market_symbol``; the caller's ``episode_id`` / ``run_id`` /
    ``correlation_id`` match the episode and the record shares the same ``correlation_id``; the episode's
    ``realized_pnl_event_digest`` is a member of ``manifest.source_event_digests`` (strong record↔episode chain
    lineage — the admitted evidence chain contains the exact realized event the episode produced); the supplied
    prior-journal head anchor equals the journal head; and exactly one token-safe entry is appended (the
    journal's own duplicate/token guards still apply). Every other outcome maps fail-closed to a REJECTED
    artifact with the journal left UNCHANGED. Deterministic and immutable; no wall-clock/random/IO; paper only.
    """
    if not isinstance(journal, EvidenceJournal):
        raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:journal_malformed")
    if not isinstance(record, PaperEvidenceAdmissionRecord):
        raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:record_malformed")
    if not isinstance(episode, PaperEndToEndEpisode):
        raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:episode_malformed")
    if not isinstance(manifest, PaperSessionRealizedPnlEvidenceManifest):
        raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:manifest_malformed")
    if not _is_hex64_string(expected_admission_digest):
        raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:expected_admission_digest_invalid")
    if not _is_hex64_string(expected_episode_digest):
        raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:expected_episode_digest_invalid")
    if expected_prior_journal_head_digest is not None and not _is_hex64_string(expected_prior_journal_head_digest):
        raise PaperAdmissionLedgerBridgeError(
            "paper_admission_ledger_bridge:expected_prior_journal_head_digest_invalid"
        )
    for name, value in (("episode_id", episode_id), ("run_id", run_id), ("correlation_id", correlation_id)):
        if not _is_plain_non_empty_string(value):
            raise PaperAdmissionLedgerBridgeError(f"paper_admission_ledger_bridge:{name}_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(episode_id, run_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:scope_violation")

    hard: list[str] = []

    # Trust boundaries: re-prove each artifact's self-digest via its PUBLIC serializer AND the caller anchor.
    admission_reason = _reprove_artifact_digest(
        artifact=record,
        recompute=paper_evidence_admission_record_digest,
        stored=record.admission_digest,
        expected=expected_admission_digest,
        label="admission",
    )
    if admission_reason is not None:
        hard.append(admission_reason)
    episode_reason = _reprove_artifact_digest(
        artifact=episode,
        recompute=paper_end_to_end_episode_digest,
        stored=episode.episode_digest,
        expected=expected_episode_digest,
        label="episode",
    )
    if episode_reason is not None:
        hard.append(episode_reason)
    # The manifest's trust anchor is the digest the ADMITTED record carries (the record is independently
    # re-proven above), so this single re-proof binds the manifest self-consistency AND record->manifest.
    record_manifest_digest = _plain_str_or_empty(record.manifest_digest)
    manifest_reason = _reprove_artifact_digest(
        artifact=manifest,
        recompute=paper_session_realized_pnl_evidence_manifest_digest,
        stored=manifest.manifest_digest,
        expected=record_manifest_digest,
        label="manifest",
    )
    if manifest_reason is not None:
        hard.append(manifest_reason)
    manifest_aggregate_digest = _plain_str_or_empty(manifest.aggregate_digest)
    if not _is_hex64_string(manifest_aggregate_digest) or manifest_aggregate_digest != _plain_str_or_empty(
        record.aggregate_digest
    ):
        hard.append("paper_admission_ledger_bridge:aggregate_binding_mismatch")

    # Schema + status + paper-safety re-proof per artifact.
    if record.schema_version != _EXPECTED_ADMISSION_SCHEMA_VERSION:
        hard.append("paper_admission_ledger_bridge:admission_schema_invalid")
    elif record.status is not PaperEvidenceAdmissionStatus.ADMITTED or record.admitted is not True:
        hard.append("paper_admission_ledger_bridge:admission_not_admitted")
    if not _record_is_paper_safe(record):
        hard.append("paper_admission_ledger_bridge:admission_unsafe_flags")

    if manifest.schema_version != _EXPECTED_MANIFEST_SCHEMA_VERSION:
        hard.append("paper_admission_ledger_bridge:manifest_schema_invalid")
    elif manifest.status is not PaperSessionRealizedPnlEvidenceManifestStatus.READY or manifest.ready is not True:
        hard.append("paper_admission_ledger_bridge:manifest_not_ready")
    if not _manifest_is_paper_safe(manifest):
        hard.append("paper_admission_ledger_bridge:manifest_unsafe_flags")

    if episode.schema_version != _EXPECTED_EPISODE_SCHEMA_VERSION:
        hard.append("paper_admission_ledger_bridge:episode_schema_invalid")
    elif episode.status is not PaperEndToEndEpisodeStatus.READY or episode.ready is not True:
        hard.append("paper_admission_ledger_bridge:episode_not_ready")
    if not _episode_is_paper_safe(episode):
        hard.append("paper_admission_ledger_bridge:episode_unsafe_flags")

    # Cross-artifact identity: same market (record/manifest/episode); caller ids match the (digest-proven)
    # episode; record shares the same audit correlation. The distinct contracts are linked ONLY by genuinely
    # shared identity values + the chain-lineage proof below, never by claiming distinct self-digests are equal.
    episode_symbol = _plain_str_or_empty(episode.market_symbol)
    if (
        episode_symbol == ""
        or episode_symbol != _plain_str_or_empty(record.market_symbol)
        or episode_symbol != _plain_str_or_empty(manifest.market_symbol)
    ):
        hard.append("paper_admission_ledger_bridge:symbol_mismatch")
    if _plain_str_or_empty(episode.episode_id) != episode_id:
        hard.append("paper_admission_ledger_bridge:episode_id_mismatch")
    if _plain_str_or_empty(episode.run_id) != run_id:
        hard.append("paper_admission_ledger_bridge:run_id_mismatch")
    if _plain_str_or_empty(episode.correlation_id) != correlation_id:
        hard.append("paper_admission_ledger_bridge:episode_correlation_mismatch")
    if _plain_str_or_empty(record.correlation_id) != correlation_id:
        hard.append("paper_admission_ledger_bridge:admission_correlation_mismatch")

    # Strong record -> episode chain lineage: the admitted evidence chain MUST contain the exact realized-PnL
    # event the episode produced. The manifest's source-event digests use the SAME contract as the public
    # paper_realized_pnl_event_digest, so the episode's bound realized_pnl_event_digest MUST be one of them.
    # Weak identity (symbol/correlation/ids) alone is insufficient; membership is the genuine proof.
    source_event_digests = _source_event_digests(manifest)
    episode_event_digest = _plain_str_or_empty(episode.realized_pnl_event_digest)
    if not _is_hex64_string(episode_event_digest) or episode_event_digest not in source_event_digests:
        hard.append("paper_admission_ledger_bridge:record_episode_lineage_unproven")

    # Prior-journal anchor: the supplied head must match the journal head BEFORE any append. verify_chain never
    # raises; it reports accepted (a broken prior journal is itself fail-closed).
    verification = journal.verify_chain()
    prior_entry_count = verification.entry_count
    prior_head_digest = verification.head_digest
    if not verification.accepted:
        hard.append("paper_admission_ledger_bridge:prior_journal_unverifiable")
    elif prior_head_digest != expected_prior_journal_head_digest:
        hard.append("paper_admission_ledger_bridge:prior_journal_head_digest_mismatch")

    rejection_reasons = tuple(sorted(set(hard)))

    appended = False
    appended_entry_seq = -1
    appended_entry_digest = ""
    appended_payload_digest = ""
    resulting_entry_count = prior_entry_count
    resulting_head_digest = prior_head_digest

    if not rejection_reasons:
        payload = _build_journal_payload(record, episode, source_event_digest_count=len(source_event_digests))
        try:
            entry = journal.append(_ENTRY_TYPE, payload, correlation_id=correlation_id)
        except EvidenceJournalError:
            # Token/duplicate/chain rejection from the journal's own guard: fail closed, journal unchanged.
            rejection_reasons = ("paper_admission_ledger_bridge:journal_append_rejected",)
        else:
            appended = True
            appended_entry_seq = entry.journal_seq
            appended_entry_digest = entry.entry_digest
            appended_payload_digest = entry.payload_digest
            post = journal.verify_chain()
            resulting_entry_count = post.entry_count
            resulting_head_digest = post.head_digest
            # Post-append invariants of the EvidenceJournal contract (a violation means a corrupt journal,
            # never a normal content path) — re-raise rather than silently bind an inconsistent result.
            if (
                resulting_entry_count != prior_entry_count + 1
                or resulting_head_digest != entry.entry_digest
                or entry.journal_seq != prior_entry_count
            ):
                raise PaperAdmissionLedgerBridgeError("paper_admission_ledger_bridge:journal_post_append_invariant")

    status = (
        PaperAdmissionLedgerBridgeStatus.READY
        if appended and not rejection_reasons
        else PaperAdmissionLedgerBridgeStatus.REJECTED
    )

    return _finalize_bridge(
        status=status,
        appended=appended,
        record=record,
        episode=episode,
        manifest=manifest,
        source_event_digest_count=len(source_event_digests),
        expected_admission_digest=expected_admission_digest,
        expected_episode_digest=expected_episode_digest,
        expected_prior_journal_head_digest=expected_prior_journal_head_digest,
        prior_journal_head_digest=prior_head_digest,
        prior_journal_entry_count=prior_entry_count,
        appended_entry_seq=appended_entry_seq,
        appended_entry_digest=appended_entry_digest,
        appended_payload_digest=appended_payload_digest,
        resulting_journal_head_digest=resulting_head_digest,
        resulting_journal_entry_count=resulting_entry_count,
        episode_id=episode_id,
        run_id=run_id,
        correlation_id=correlation_id,
        rejection_reasons=rejection_reasons,
        metadata=metadata_pairs,
    )


def _finalize_bridge(
    *,
    status: PaperAdmissionLedgerBridgeStatus,
    appended: bool,
    record: PaperEvidenceAdmissionRecord,
    episode: PaperEndToEndEpisode,
    manifest: PaperSessionRealizedPnlEvidenceManifest,
    source_event_digest_count: int,
    expected_admission_digest: str,
    expected_episode_digest: str,
    expected_prior_journal_head_digest: str | None,
    prior_journal_head_digest: str | None,
    prior_journal_entry_count: int,
    appended_entry_seq: int,
    appended_entry_digest: str,
    appended_payload_digest: str,
    resulting_journal_head_digest: str | None,
    resulting_journal_entry_count: int,
    episode_id: str,
    run_id: str,
    correlation_id: str,
    rejection_reasons: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> PaperAdmissionLedgerBridge:
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status,
        "ready": status is PaperAdmissionLedgerBridgeStatus.READY,
        "appended": appended,
        "entry_type": _ENTRY_TYPE.value,
        "correlation_id": correlation_id,
        "episode_id": episode_id,
        "run_id": run_id,
        "market_symbol": _plain_str_or_empty(episode.market_symbol),
        "admission_status": record.status.value if isinstance(record.status, PaperEvidenceAdmissionStatus) else "",
        "admission_digest": _plain_str_or_empty(record.admission_digest),
        "expected_admission_digest": expected_admission_digest,
        "admission_correlation_id": _plain_str_or_empty(record.correlation_id),
        "manifest_digest": _plain_str_or_empty(record.manifest_digest),
        "expected_manifest_digest": _plain_str_or_empty(record.expected_manifest_digest),
        "manifest_status": manifest.status.value
        if isinstance(manifest.status, PaperSessionRealizedPnlEvidenceManifestStatus)
        else "",
        "aggregate_id": _plain_str_or_empty(record.aggregate_id),
        "aggregate_digest": _plain_str_or_empty(record.aggregate_digest),
        "session_bridge_count": record.session_bridge_count,
        "event_count": record.event_count,
        "computed_event_count": record.computed_event_count,
        "closed_units_total": _plain_str_or_empty(record.closed_units_total),
        "realized_pnl_total": _plain_str_or_empty(record.realized_pnl_total),
        "episode_status": episode.status.value if isinstance(episode.status, PaperEndToEndEpisodeStatus) else "",
        "episode_digest": _plain_str_or_empty(episode.episode_digest),
        "expected_episode_digest": expected_episode_digest,
        "episode_run_digest": _plain_str_or_empty(episode.episode_run_digest),
        "order_intent_digest": _plain_str_or_empty(episode.order_intent_digest),
        "realized_pnl_event_digest": _plain_str_or_empty(episode.realized_pnl_event_digest),
        "source_event_digest_count": source_event_digest_count,
        "prior_journal_head_digest": prior_journal_head_digest,
        "expected_prior_journal_head_digest": expected_prior_journal_head_digest,
        "prior_journal_entry_count": prior_journal_entry_count,
        "appended_entry_seq": appended_entry_seq,
        "appended_entry_digest": appended_entry_digest,
        "appended_payload_digest": appended_payload_digest,
        "resulting_journal_head_digest": resulting_journal_head_digest,
        "resulting_journal_entry_count": resulting_journal_entry_count,
        "rejection_reasons": rejection_reasons,
        "metadata": metadata,
    }
    seed = PaperAdmissionLedgerBridge(ledger_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_admission_ledger_bridge_digest(seed))


def _replace_digest(bridge: PaperAdmissionLedgerBridge, digest: str) -> PaperAdmissionLedgerBridge:
    fields = _bridge_fields(bridge)
    fields["ledger_digest"] = digest
    return PaperAdmissionLedgerBridge(**fields)  # type: ignore[arg-type]


def _bridge_fields(bridge: PaperAdmissionLedgerBridge) -> dict[str, object]:
    return {
        "schema_version": bridge.schema_version,
        "status": bridge.status,
        "ready": bridge.ready,
        "appended": bridge.appended,
        "entry_type": bridge.entry_type,
        "correlation_id": bridge.correlation_id,
        "episode_id": bridge.episode_id,
        "run_id": bridge.run_id,
        "market_symbol": bridge.market_symbol,
        "admission_status": bridge.admission_status,
        "admission_digest": bridge.admission_digest,
        "expected_admission_digest": bridge.expected_admission_digest,
        "admission_correlation_id": bridge.admission_correlation_id,
        "manifest_digest": bridge.manifest_digest,
        "expected_manifest_digest": bridge.expected_manifest_digest,
        "manifest_status": bridge.manifest_status,
        "aggregate_id": bridge.aggregate_id,
        "aggregate_digest": bridge.aggregate_digest,
        "session_bridge_count": bridge.session_bridge_count,
        "event_count": bridge.event_count,
        "computed_event_count": bridge.computed_event_count,
        "closed_units_total": bridge.closed_units_total,
        "realized_pnl_total": bridge.realized_pnl_total,
        "episode_status": bridge.episode_status,
        "episode_digest": bridge.episode_digest,
        "expected_episode_digest": bridge.expected_episode_digest,
        "episode_run_digest": bridge.episode_run_digest,
        "order_intent_digest": bridge.order_intent_digest,
        "realized_pnl_event_digest": bridge.realized_pnl_event_digest,
        "source_event_digest_count": bridge.source_event_digest_count,
        "prior_journal_head_digest": bridge.prior_journal_head_digest,
        "expected_prior_journal_head_digest": bridge.expected_prior_journal_head_digest,
        "prior_journal_entry_count": bridge.prior_journal_entry_count,
        "appended_entry_seq": bridge.appended_entry_seq,
        "appended_entry_digest": bridge.appended_entry_digest,
        "appended_payload_digest": bridge.appended_payload_digest,
        "resulting_journal_head_digest": bridge.resulting_journal_head_digest,
        "resulting_journal_entry_count": bridge.resulting_journal_entry_count,
        "rejection_reasons": bridge.rejection_reasons,
        "metadata": bridge.metadata,
    }


def _bridge_payload_from(bridge: PaperAdmissionLedgerBridge) -> dict[str, object]:
    return {
        "schema_version": bridge.schema_version,
        "status": bridge.status.value,
        "ready": bridge.ready,
        "appended": bridge.appended,
        "entry_type": bridge.entry_type,
        "correlation_id": bridge.correlation_id,
        "episode_id": bridge.episode_id,
        "run_id": bridge.run_id,
        "market_symbol": bridge.market_symbol,
        "admission_status": bridge.admission_status,
        "admission_digest": bridge.admission_digest,
        "expected_admission_digest": bridge.expected_admission_digest,
        "admission_correlation_id": bridge.admission_correlation_id,
        "manifest_digest": bridge.manifest_digest,
        "expected_manifest_digest": bridge.expected_manifest_digest,
        "manifest_status": bridge.manifest_status,
        "aggregate_id": bridge.aggregate_id,
        "aggregate_digest": bridge.aggregate_digest,
        "session_bridge_count": bridge.session_bridge_count,
        "event_count": bridge.event_count,
        "computed_event_count": bridge.computed_event_count,
        "closed_units_total": bridge.closed_units_total,
        "realized_pnl_total": bridge.realized_pnl_total,
        "episode_status": bridge.episode_status,
        "episode_digest": bridge.episode_digest,
        "expected_episode_digest": bridge.expected_episode_digest,
        "episode_run_digest": bridge.episode_run_digest,
        "order_intent_digest": bridge.order_intent_digest,
        "realized_pnl_event_digest": bridge.realized_pnl_event_digest,
        "source_event_digest_count": bridge.source_event_digest_count,
        "prior_journal_head_digest": bridge.prior_journal_head_digest,
        "expected_prior_journal_head_digest": bridge.expected_prior_journal_head_digest,
        "prior_journal_entry_count": bridge.prior_journal_entry_count,
        "appended_entry_seq": bridge.appended_entry_seq,
        "appended_entry_digest": bridge.appended_entry_digest,
        "appended_payload_digest": bridge.appended_payload_digest,
        "resulting_journal_head_digest": bridge.resulting_journal_head_digest,
        "resulting_journal_entry_count": bridge.resulting_journal_entry_count,
        "rejection_reasons": list(bridge.rejection_reasons),
        "metadata": _serialize_metadata(bridge.metadata),
        "paper_only": bridge.paper_only,
        "real_orders_enabled": bridge.real_orders_enabled,
        "real_money_enabled": bridge.real_money_enabled,
        "capital_reserved": bridge.capital_reserved,
        "capital_mutated": bridge.capital_mutated,
        "balance_mutated": bridge.balance_mutated,
        "order_routed": bridge.order_routed,
        "venue_order_id_created": bridge.venue_order_id_created,
        "exchange_order_id_created": bridge.exchange_order_id_created,
        "client_order_id_created": bridge.client_order_id_created,
        "route_id_created": bridge.route_id_created,
        "execution_instruction_created": bridge.execution_instruction_created,
        "execution_authorized": bridge.execution_authorized,
        "live_position_mutated": bridge.live_position_mutated,
        "live_api_called": bridge.live_api_called,
        "scheduler_enabled": bridge.scheduler_enabled,
        "auto_loop_enabled": bridge.auto_loop_enabled,
        "connector_invoked": bridge.connector_invoked,
        "prdv4_stage4_complete": bridge.prdv4_stage4_complete,
        "live_ready": bridge.live_ready,
        "shadow_ready": bridge.shadow_ready,
        "profitability_proven": bridge.profitability_proven,
        "edge_proven": bridge.edge_proven,
        "production_execution": bridge.production_execution,
    }


def paper_admission_ledger_bridge_to_dict(bridge: PaperAdmissionLedgerBridge) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for a bridge (deterministic shape, includes self-digest)."""
    payload = _bridge_payload_from(bridge)
    payload["ledger_digest"] = bridge.ledger_digest
    return payload


def paper_admission_ledger_bridge_digest(bridge: PaperAdmissionLedgerBridge) -> str:
    """Recompute the canonical bridge digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_bridge_payload_from(bridge))


__all__ = [
    "PaperAdmissionLedgerBridge",
    "PaperAdmissionLedgerBridgeError",
    "PaperAdmissionLedgerBridgeStatus",
    "append_paper_admission_record_to_evidence_journal",
    "paper_admission_ledger_bridge_digest",
    "paper_admission_ledger_bridge_to_dict",
]
